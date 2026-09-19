#!/usr/bin/env python3
"""Registry-owned Vulkan 1.0 command and dispatch inventory.

The only API oracle is KhronosGroup/Vulkan-Headers tag v1.4.350, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`, registry/vk.xml canonical
SHA-256 `50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08`.

This is a design/build tool, not a loader.  It does not infer prototypes from
Anvil.  It first constructs the exact core-1.0 command set from vk.xml, then
audits Anvil's public Procedure declarations and classifies every command as:

* declared_callable: a callable Procedure declaration exists with matching
  command name, arity and void/value return shape. This does not certify the
  command's semantics and is not, by itself, permission to expose a pointer;
* deterministic_unsupported: a future callable Procedure explicitly marked
  `ANVIL_VK_DETERMINISTIC_UNSUPPORTED` exists with the same ABI;
* missing: no callable Procedure exists, so proc-address lookup must be null.

The dispatch rules are the Vulkan 1.0 command-function-pointer rules:
GIPA(NULL) exposes only the three global commands; GIPA(instance) exposes core
dispatchable commands; GDPA(device) exposes only device/device-child commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from typing import Iterable

PIN_SHA256 = "50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08"
CRLF_CHECKOUT_SHA256 = "f6f43874297ce094769714de2fc51ec683c12eed9b7615da20b34ab4a2f81470"
ROOT = pathlib.Path(__file__).resolve().parent.parent
VK_ROOT = ROOT / "Anvil" / "Graphics" / "Vulkan"
DISPATCHABLE = frozenset(("VkInstance", "VkPhysicalDevice", "VkDevice",
                          "VkQueue", "VkCommandBuffer"))
DEVICE_DISPATCH = frozenset(("VkDevice", "VkQueue", "VkCommandBuffer"))
GLOBAL_NAMES = frozenset(("vkCreateInstance", "vkEnumerateInstanceExtensionProperties",
                          "vkEnumerateInstanceLayerProperties"))


class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    declaration: str


@dataclass(frozen=True)
class Command:
    name: str
    return_type: str
    parameters: tuple[Parameter, ...]
    alias: str | None
    dispatch: str
    status: str = "missing"
    source: str | None = None
    line: int | None = None

    @property
    def prototype(self) -> str:
        return f"{self.return_type} {self.name}(" + ", ".join(p.declaration for p in self.parameters) + ")"


@dataclass(frozen=True)
class PublicProcedure:
    name: str
    returns_value: bool
    parameters: tuple[str, ...]
    source: str
    line: int
    unsupported: bool


def pinned_registry_bytes(path: pathlib.Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest == PIN_SHA256:
        return data, "canonical-lf"
    # Git's Windows checkout conversion changes only line endings.  Accept it
    # only when BOTH its known byte hash and canonicalised content hash match.
    normal = data.replace(b"\r\n", b"\n")
    if digest == CRLF_CHECKOUT_SHA256 and hashlib.sha256(normal).hexdigest() == PIN_SHA256:
        return normal, "git-crlf-checkout-normalized"
    raise InventoryError(f"vk.xml SHA-256 {digest}, wanted pinned {PIN_SHA256}")


def _decl(node: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext()).strip())


def _api_vulkan(node: ET.Element) -> bool:
    api = node.get("api")
    return api is None or "vulkan" in api.split(",")


def _dispatch(name: str, params: tuple[Parameter, ...]) -> str:
    if name == "vkGetInstanceProcAddr":
        return "gipa"
    if name == "vkGetDeviceProcAddr":
        return "gdpa"
    if name in GLOBAL_NAMES or not params or params[0].type not in DISPATCHABLE:
        return "global"
    if params[0].type in ("VkInstance", "VkPhysicalDevice"):
        return "instance"
    return "device"


def registry_commands(data: bytes) -> dict[str, Command]:
    root = ET.fromstring(data)
    nodes: dict[str, ET.Element] = {}
    for node in root.findall("./commands/command"):
        if not _api_vulkan(node):
            continue
        name = node.get("name") or node.findtext("proto/name")
        if name:
            nodes[name] = node
    required: list[str] = []
    features = [f for f in root.findall("./feature")
                if f.get("number") == "1.0" and "vulkan" in (f.get("api") or "").split(",")]
    if not features:
        raise InventoryError("registry has no Vulkan VK_VERSION_1_0 feature")
    for feature in features:
        for req in feature.findall("require"):
            if not _api_vulkan(req):
                continue
            required.extend(n.get("name") for n in req.findall("command")
                            if n.get("name") and _api_vulkan(n))

    cache: dict[str, Command] = {}
    active: set[str] = set()

    def resolve(name: str) -> Command:
        if name in cache:
            return cache[name]
        if name in active or name not in nodes:
            raise InventoryError(f"bad command alias or absent command {name}")
        active.add(name)
        node = nodes[name]
        alias = node.get("alias")
        if alias:
            target = resolve(alias)
            cmd = replace(target, name=name, alias=alias,
                          dispatch=_dispatch(name, target.parameters))
        else:
            proto = node.find("proto")
            if proto is None or proto.findtext("name") != name:
                raise InventoryError(f"{name} has no exact prototype")
            params = tuple(Parameter(p.findtext("name") or "", p.findtext("type") or "", _decl(p))
                           for p in node.findall("param") if _api_vulkan(p))
            if any(not p.name or not p.type for p in params):
                raise InventoryError(f"{name} has an incomplete parameter")
            cmd = Command(name, proto.findtext("type") or "", params, None,
                          _dispatch(name, params))
        active.remove(name)
        cache[name] = cmd
        return cmd

    result = {name: resolve(name) for name in required}
    if len(result) != len(set(required)):
        raise InventoryError("duplicate core command requirement")
    return dict(sorted(result.items()))


PROC_RE = re.compile(r"^\s*Procedure(?:\.([A-Za-z][A-Za-z0-9_]*))?\s+"
                     r"(vk[A-Za-z0-9_]+)\(([^\n]*)\)\s*$", re.MULTILINE)


def _pb_param_name(text: str) -> str:
    text = text.strip()
    match = re.match(r"\*?([A-Za-z_][A-Za-z0-9_]*)", text)
    return match.group(1) if match else ""


def public_procedures(root: pathlib.Path = VK_ROOT) -> dict[str, PublicProcedure]:
    result: dict[str, PublicProcedure] = {}
    for path in sorted(root.glob("vk_*.pbi")) + sorted(root.glob("vk_*.pi4")):
        text = path.read_text(encoding="utf-8")
        for match in PROC_RE.finditer(text):
            suffix, name, raw_params = match.groups()
            params = tuple(_pb_param_name(p) for p in raw_params.split(",")) if raw_params.strip() else ()
            line = text.count("\n", 0, match.start()) + 1
            prefix = text[max(0, match.start() - 300):match.start()]
            proc = PublicProcedure(name, suffix is not None, params,
                                   path.relative_to(ROOT).as_posix(), line,
                                   "ANVIL_VK_DETERMINISTIC_UNSUPPORTED" in prefix)
            if name in result:
                raise InventoryError(f"duplicate public Procedure {name}")
            result[name] = proc
    return result


def classify(commands: dict[str, Command], procedures: dict[str, PublicProcedure]) -> dict[str, Command]:
    extra = sorted(set(procedures) - set(commands))
    if extra:
        raise InventoryError("public non-core or misspelled Procedures: " + ", ".join(extra))
    out = {}
    for name, cmd in commands.items():
        proc = procedures.get(name)
        if proc is None:
            out[name] = cmd
            continue
        errors = []
        if len(proc.parameters) != len(cmd.parameters):
            errors.append(f"arity {len(proc.parameters)}, registry {len(cmd.parameters)}")
        if proc.returns_value != (cmd.return_type != "void"):
            errors.append(f"return shape {'value' if proc.returns_value else 'void'}, registry {cmd.return_type}")
        if errors:
            raise InventoryError(f"{name} at {proc.source}:{proc.line}: " + "; ".join(errors))
        status = "deterministic_unsupported" if proc.unsupported else "declared_callable"
        out[name] = replace(cmd, status=status, source=proc.source, line=proc.line)
    return out


def procaddr(command: Command | None, query: str, exposed: bool = False,
             handle_valid: bool = True) -> bool:
    """Whether the future table must return a non-null pointer.

    `query` is `gipa-null`, `gipa-instance`, or `gdpa-device`.  Invalid handles
    are deliberately outside this pure table; public entry points validate
    handles before applying it. A declaration is necessary but never
    sufficient: `exposed` is the future separately reviewed semantic
    allowlist decision for this exact name.
    """
    if command is None or command.status == "missing" or not exposed or not handle_valid:
        return False
    if query == "gipa-null":
        # Self-resolution with a null instance was added in Vulkan 1.2. The
        # inventory is VK_VERSION_1_0, whose global set is exactly the three
        # commands in GLOBAL_NAMES.
        return command.dispatch == "global"
    if query == "gipa-instance":
        return command.dispatch in ("instance", "device", "gipa", "gdpa")
    if query == "gdpa-device":
        return command.dispatch in ("device", "gdpa")
    raise InventoryError(f"unknown proc-address query {query}")


def inventory(registry: pathlib.Path, source_root: pathlib.Path = VK_ROOT):
    data, transport = pinned_registry_bytes(registry)
    commands = classify(registry_commands(data), public_procedures(source_root))
    return commands, transport


def serialise(commands: Iterable[Command]) -> list[dict]:
    rows = []
    for cmd in commands:
        row = asdict(cmd)
        row["parameters"] = [asdict(p) for p in cmd.parameters]
        row["prototype"] = cmd.prototype
        row["gipa_null"] = procaddr(cmd, "gipa-null")
        row["gipa_instance"] = procaddr(cmd, "gipa-instance")
        row["gdpa_device"] = procaddr(cmd, "gdpa-device")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=os.environ.get("VULKAN_REGISTRY"))
    parser.add_argument("--source-root", type=pathlib.Path, default=VK_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.registry:
        raise SystemExit("set VULKAN_REGISTRY to pinned v1.4.350 registry/vk.xml or pass --registry")
    try:
        commands, transport = inventory(pathlib.Path(args.registry), args.source_root)
    except (OSError, ET.ParseError, InventoryError) as exc:
        raise SystemExit(f"vulkan_dispatch_inventory: {exc}") from exc
    rows = serialise(commands.values())
    counts = {status: sum(r["status"] == status for r in rows)
              for status in ("declared_callable", "deterministic_unsupported", "missing")}
    if args.json:
        print(json.dumps({"registry_sha256": PIN_SHA256, "transport": transport,
                          "counts": counts, "commands": rows}, indent=2))
    else:
        print(f"Vulkan 1.0: {len(rows)} commands; " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        for row in rows:
            print(f"{row['status']:27} {row['dispatch']:8} {row['prototype']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
