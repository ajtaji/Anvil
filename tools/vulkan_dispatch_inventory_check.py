#!/usr/bin/env python3
"""Hostile gate for the registry-owned Vulkan 1.0 dispatch inventory.

This checks the current source classification without requiring missing core
commands to pretend success.  Its mutations operate on the generated model,
not product files.  Integration may consume the same rows only after adding
real vkGetInstanceProcAddr/vkGetDeviceProcAddr entry points and callable
deterministic-unsupported stubs for every row it chooses to expose.
"""

from __future__ import annotations

import argparse
import os
import pathlib
from dataclasses import replace

from vulkan_dispatch_inventory import (Command, InventoryError, PIN_SHA256,
                                       Parameter, _dispatch, inventory, procaddr)

STATUSES = frozenset(("declared_callable", "deterministic_unsupported", "missing"))
DISPATCH = frozenset(("global", "instance", "device", "gipa", "gdpa"))


def validate(commands: dict[str, Command]) -> None:
    if len(commands) != 137:
        raise InventoryError(f"core 1.0 command count is {len(commands)}, wanted 137")
    for key, cmd in commands.items():
        if key != cmd.name or not key.startswith("vk") or key != key.strip():
            raise InventoryError(f"non-exact command name/key {key!r}/{cmd.name!r}")
        if not cmd.return_type or cmd.dispatch not in DISPATCH or cmd.status not in STATUSES:
            raise InventoryError(f"{key}: incomplete return/dispatch/status")
        if cmd.dispatch != _dispatch(cmd.name, cmd.parameters):
            raise InventoryError(f"{key}: dispatch {cmd.dispatch}, registry prototype implies {_dispatch(cmd.name, cmd.parameters)}")
        if cmd.status == "missing":
            if cmd.source is not None or cmd.line is not None:
                raise InventoryError(f"{key}: missing command claims a source")
        elif cmd.source is None or cmd.line is None:
            raise InventoryError(f"{key}: callable status has no source declaration")
        seen = set()
        for param in cmd.parameters:
            if not param.name or not param.type or param.name in seen:
                raise InventoryError(f"{key}: invalid or duplicate parameter {param.name!r}")
            if param.name not in param.declaration or param.type not in param.declaration:
                raise InventoryError(f"{key}: declaration lost exact type/name: {param.declaration!r}")
            seen.add(param.name)
        if cmd.prototype != (f"{cmd.return_type} {cmd.name}(" +
                             ", ".join(p.declaration for p in cmd.parameters) + ")"):
            raise InventoryError(f"{key}: prototype rendering drift")
        if cmd.alias:
            target = commands.get(cmd.alias)
            if target is None:
                raise InventoryError(f"{key}: alias target {cmd.alias} is not core")
            if (cmd.return_type, cmd.parameters) != (target.return_type, target.parameters):
                raise InventoryError(f"{key}: alias prototype differs from {cmd.alias}")

        available = cmd.status != "missing"
        expected = {
            "gipa-null": available and cmd.dispatch == "global",
            "gipa-instance": available and cmd.dispatch in ("instance", "device", "gipa", "gdpa"),
            "gdpa-device": available and cmd.dispatch in ("device", "gdpa"),
        }
        for query, wanted in expected.items():
            if procaddr(cmd, query, exposed=available) != wanted:
                raise InventoryError(f"{key}: {query} resolution differs from dispatch contract")


def mutated(commands: dict[str, Command], name: str, change) -> dict[str, Command]:
    out = dict(commands)
    out[name] = change(out[name])
    return out


def require_red(label: str, commands: dict[str, Command]) -> None:
    try:
        validate(commands)
    except InventoryError:
        print(f"  RED  {label}")
        return
    raise AssertionError(f"{label}: inventory mutation passed")


def hostile(commands: dict[str, Command]) -> int:
    implemented = next(c for c in commands.values() if c.status == "declared_callable")
    missing = next(c for c in commands.values() if c.status == "missing")
    tests = []

    wrong_key = dict(commands)
    wrong_key[implemented.name.upper()] = wrong_key.pop(implemented.name)
    tests.append(("case-folded command name", wrong_key))
    tests.append(("missing return type", mutated(commands, implemented.name,
                                                  lambda c: replace(c, return_type=""))))
    tests.append(("wrong dispatch level", mutated(commands, implemented.name,
                                                   lambda c: replace(c, dispatch="global" if c.dispatch != "global" else "device"))))
    tests.append(("callable source removed", mutated(commands, implemented.name,
                                                      lambda c: replace(c, source=None, line=None))))
    tests.append(("missing command claims source", mutated(commands, missing.name,
                                                            lambda c: replace(c, source="fake.pbi", line=1))))
    tests.append(("unknown implementation status", mutated(commands, missing.name,
                                                             lambda c: replace(c, status="partial"))))
    tests.append(("dangling command alias", mutated(commands, missing.name,
                                                     lambda c: replace(c, alias="vkNoSuchCommand"))))
    tests.append(("alias prototype differs from target",
                  mutated(commands, missing.name,
                          lambda c: replace(c, alias=implemented.name))))
    if implemented.parameters:
        p = implemented.parameters[0]
        bad = replace(p, declaration=p.declaration.replace(p.name, "wrongName"))
        tests.append(("prototype parameter name drift",
                      mutated(commands, implemented.name,
                              lambda c: replace(c, parameters=(bad,) + c.parameters[1:]))))
        tests.append(("prototype parameter dropped",
                      mutated(commands, implemented.name,
                              lambda c: replace(c, parameters=c.parameters[1:]))))
    for label, model in tests:
        require_red(label, model)

    # Lookup spelling is a byte-exact table key. No case folding, prefix or
    # suffix matching is permitted, and command aliases are separate names.
    for name in commands:
        if commands.get(name.lower()) is not None and name.lower() != name:
            raise AssertionError(f"case-insensitive lookup leaked {name}")
        if commands.get(name + "KHR") is not None and name + "KHR" not in commands:
            raise AssertionError(f"suffix lookup leaked {name}")

    # Exercise the resolver independent of current missing loader entrypoints.
    gipa = replace(commands["vkGetInstanceProcAddr"], status="declared_callable",
                   source="future_dispatch.pbi", line=1)
    gdpa = replace(commands["vkGetDeviceProcAddr"], status="declared_callable",
                   source="future_dispatch.pbi", line=2)
    create = replace(commands["vkCreateInstance"], status="declared_callable",
                     source="future_dispatch.pbi", line=3)
    phys = replace(commands["vkEnumeratePhysicalDevices"], status="declared_callable",
                   source="future_dispatch.pbi", line=4)
    device = replace(commands["vkDeviceWaitIdle"], status="declared_callable",
                     source="future_dispatch.pbi", line=5)
    matrix = (
        ("Vulkan 1.0 GIPA(NULL) does not resolve itself", procaddr(gipa, "gipa-null", True), False),
        ("GIPA(NULL) resolves an exposed global command", procaddr(create, "gipa-null", True), True),
        ("GIPA(NULL) hides exposed instance commands", procaddr(phys, "gipa-null", True), False),
        ("GIPA(instance) resolves exposed physical-device commands", procaddr(phys, "gipa-instance", True), True),
        ("GIPA(instance) resolves exposed device commands", procaddr(device, "gipa-instance", True), True),
        ("GDPA(device) resolves itself when exposed", procaddr(gdpa, "gdpa-device", True), True),
        ("GDPA(device) resolves exposed device commands", procaddr(device, "gdpa-device", True), True),
        ("GDPA(device) hides exposed physical-device commands", procaddr(phys, "gdpa-device", True), False),
        ("GDPA(device) hides exposed global commands", procaddr(create, "gdpa-device", True), False),
        ("unreviewed declaration resolves nothing", procaddr(device, "gdpa-device"), False),
        ("invalid handle resolves nothing", procaddr(device, "gdpa-device", True, False), False),
    )
    for label, got, want in matrix:
        if got != want:
            raise AssertionError(f"{label}: got {got}, wanted {want}")
    return len(tests) + len(matrix) + 2 * len(commands)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=os.environ.get("VULKAN_REGISTRY"))
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()
    if not args.registry:
        raise SystemExit("set VULKAN_REGISTRY to pinned v1.4.350 registry/vk.xml or pass --registry")
    commands, transport = inventory(pathlib.Path(args.registry))
    validate(commands)
    counts = {s: sum(c.status == s for c in commands.values()) for s in STATUSES}
    checks = hostile(commands) if args.mutate else 0
    print(f"vulkan_dispatch_inventory_check: PASS - pinned {PIN_SHA256[:12]}, "
          f"{len(commands)} exact core-1.0 commands, declared-callable={counts['declared_callable']}, "
          f"deterministic-unsupported={counts['deterministic_unsupported']}, missing={counts['missing']}")
    print(f"  registry transport: {transport}; every prototype, alias, dispatch level and lookup domain validated")
    if args.mutate:
        print(f"  {checks} hostile model/lookup checks passed")
    else:
        print("  (run with --mutate to prove command/prototype/dispatch drift goes red)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
