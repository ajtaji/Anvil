#!/usr/bin/env python3
"""Source, registry, emitted-code and mutation gate for vk_semaphore.pbi.

This checks the unintegrated target-neutral binary semaphore transaction
engine.  It does not infer public Vulkan support and deliberately rejects any
source that adds public vkCreateSemaphore/vkDestroySemaphore entry points.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_semaphore.pbi"
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_semaphore_gate.pi4"
RESOURCE_CHECK = ROOT / "tools" / "vulkan_resource_check.py"
MAGIC = 0x564B534D
OUT = 0x06000000
ROWS = 0x06000100

MUTATIONS = (
    (
        "unsignaled wait accepted",
        "If avkSemTxSawWait[x] <> 0 Or avkSemTxFinal[x] <> #ANVIL_VK_SEM_SIGNALED",
        "If avkSemTxSawWait[x] <> 0 Or avkSemTxFinal[x] < 0",
    ),
    (
        "signal of signaled payload accepted",
        "If avkSemTxSawSignal[x] <> 0 Or avkSemTxFinal[x] <> #ANVIL_VK_SEM_UNSIGNALED",
        "If avkSemTxSawSignal[x] <> 0 Or avkSemTxFinal[x] < 0",
    ),
    (
        "cross-device semaphore accepted",
        "If avkSemDev[s] <> d Or avkSemDevGen[s] <> avkTokenGen(device)\n      avkSemaphoreClearReservation(t)",
        "If avkSemDev[s] < 0 Or avkSemDevGen[s] <> avkTokenGen(device)\n      avkSemaphoreClearReservation(t)",
    ),
    (
        "completion ignores consumed final state",
        "avkSemSignaled[s] = avkSemTxFinal[x]\n      avkSemPendingSignal[s] = 0",
        "avkSemSignaled[s] = #ANVIL_VK_SEM_SIGNALED\n      avkSemPendingSignal[s] = 0",
    ),
    (
        "rollback restores final instead of prior state",
        "avkSemSignaled[s] = avkSemTxPrior[x]\n        avkSemPendingSignal[s] = 0",
        "avkSemSignaled[s] = avkSemTxFinal[x]\n        avkSemPendingSignal[s] = 0",
    ),
    (
        "destroy ignores pending signal",
        "If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0\n    ProcedureReturn avkFault",
        "If avkSemPendingSignal[s] < 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0\n    ProcedureReturn avkFault",
    ),
    (
        "destroy ignores uncommitted reservation",
        "If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0\n    ProcedureReturn avkFault",
        "If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) < 0\n    ProcedureReturn avkFault",
    ),
    (
        "second reservation steals a payload",
        "If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0\n      avkSemaphoreClearReservation(t)",
        "If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) < 0\n      avkSemaphoreClearReservation(t)",
    ),
    (
        "reused device generation inherits reservation authority",
        "If avkSemDev[s] <> d Or avkSemDevGen[s] <> avkTokenGen(device)\n      avkSemaphoreClearReservation(t)",
        "If avkSemDev[s] <> d Or avkSemDevGen[s] < 0\n      avkSemaphoreClearReservation(t)",
    ),
    (
        "failed reservation leaves staged transaction active",
        "avkSemTxStage[t] = #ANVIL_VK_SEM_TX_FREE\nEndProcedure",
        "avkSemTxStage[t] = #ANVIL_VK_SEM_TX_RESERVED\nEndProcedure",
    ),
)


def load_harness():
    spec = importlib.util.spec_from_file_location("anvil_vksem_resource_gate", RESOURCE_CHECK)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load emitted-gate harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.GATE = GATE
    return module


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def emitted(harness, compiler: pathlib.Path, interpreter: pathlib.Path,
            mutation: tuple[str, str] | None = None):
    a64 = harness.load_interpreter(interpreter)
    sources: dict[str, str] = {}
    if mutation:
        before, after = mutation
        original = SOURCE.read_text(encoding="utf-8")
        if original.count(before) != 1:
            raise AssertionError("mutant anchor count is not one: " + before)
        sources[SOURCE.name] = original.replace(before, after, 1)
    cpu, rc, steps = harness.run_once(a64, compiler, sources)
    magic = u64(cpu, OUT)
    count = u64(cpu, OUT + 8)
    failures = u64(cpu, OUT + 16)
    failed_rows = [i + 1 for i in range(count) if u64(cpu, ROWS + i * 8) == 0]
    return rc, steps, magic, count, failures, failed_rows


def locate(value: str | None, choices: list[pathlib.Path], label: str) -> pathlib.Path:
    if value:
        choices.insert(0, pathlib.Path(value))
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise RuntimeError(label + " not found")


def registry_contract(registry: pathlib.Path) -> int:
    data = registry.read_bytes().replace(b"\r\n", b"\n")
    root = ET.fromstring(data)
    required = {
        "vkCreateSemaphore": ("VkResult", "VkDevice"),
        "vkDestroySemaphore": ("void", "VkDevice"),
    }
    found: dict[str, tuple[str, str]] = {}
    for command in root.findall("./commands/command"):
        proto = command.find("proto")
        if proto is None or proto.find("name") is None or proto.find("type") is None:
            continue
        name = proto.find("name").text or ""
        if name not in required:
            continue
        first = command.find("param/type")
        found[name] = (proto.find("type").text or "", "" if first is None else first.text or "")
    if found != required:
        raise AssertionError(f"pinned registry semaphore prototypes drifted: {found!r}")
    features = root.findall("./feature[@number='1.0']")
    if not features:
        raise AssertionError("pinned registry has no core version 1.0 feature")
    names = {node.get("name") for feature in features
             for node in feature.findall("./require/command")}
    if set(required) - names:
        raise AssertionError("semaphore commands are no longer core Vulkan 1.0")
    return 5


def source_contract(text: str) -> int:
    required = (
        "#ANVIL_VK_SEM_UNSIGNALED = 0",
        "#ANVIL_VK_SEM_SIGNALED = 1",
        "#ANVIL_VK_SEM_TX_RESERVED = 1",
        "#ANVIL_VK_SEM_TX_COMMITTED = 2",
        "Procedure.i avkSemaphoreReserve(",
        "Procedure.i avkSemaphoreCommit(",
        "Procedure.i avkSemaphoreComplete(",
        "Procedure.i avkSemaphoreRollback(",
        "Procedure.i avkSemaphoreResetDevice(",
        "avkSemTxPrior[x] = avkSemSignaled[s]",
        "avkSemSignaled[s] = avkSemTxFinal[x]",
        "avkSemSignaled[s] = avkSemTxPrior[x]",
        "avkSemPendingSignal[s] = avkSemTxSawSignal[x]",
        "avkSemPendingWait[s] = avkSemTxSawWait[x]",
        "avkSemaphoreReservedByAny(s)",
        "avkSemDevGen[s] = avkTokenGen(device)",
        "avkSemTxDevGen[t] = avkTokenGen(device)",
        "avkDevGen[avkSemTxDev[t]] <> avkSemTxDevGen[t]",
    )
    for token in required:
        if token not in text:
            raise AssertionError("source contract token missing: " + token)
    forbidden = (
        "Procedure.i vkCreateSemaphore(",
        "Procedure vkDestroySemaphore(",
        "VK_SEMAPHORE_TYPE_TIMELINE",
        "vkSignalSemaphore",
        "vkWaitSemaphores",
    )
    for token in forbidden:
        if token in text:
            raise AssertionError("unintegrated binary module makes unsupported claim: " + token)
    # The state arrays may change only in commit, completion, rollback,
    # creation/destruction and atomic device reset, never in validation.
    reserve = text.split("Procedure.i avkSemaphoreReserve(", 1)[1].split(
        "Procedure.i avkSemaphoreCommit(", 1)[0]
    if "avkSemSignaled[s] =" in reserve or "avkSemPendingSignal[s] =" in reserve:
        raise AssertionError("reserve mutates externally visible semaphore state")
    return len(required) + len(forbidden) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(argv)
    try:
        checks = registry_contract(args.registry)
        source = SOURCE.read_text(encoding="utf-8")
        checks += source_contract(source)
        harness = load_harness()
        compiler = locate(args.compiler, [ROOT / "PureMetalForge.exe",
            pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")], "PureMetalForge")
        interpreter = locate(args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"], "A64 interpreter")
        rc, steps, magic, count, failures, failed_rows = emitted(harness, compiler, interpreter)
        if (rc, magic, failures) != (0, MAGIC, 0) or count < 70:
            raise AssertionError(
                f"emitted gate rc={rc} magic={magic:#x} rows={count} "
                f"failures={failures} bad={failed_rows}")
        checks += count + 3
        print(f"PASS: {checks} semaphore registry/source/emitted checks; "
              f"{count} emitted rows, {steps:,} A64 instructions")
        if args.mutate:
            for label, before, after in MUTATIONS:
                mrc, _, mmagic, _, mfails, _ = emitted(
                    harness, compiler, interpreter, (before, after))
                if mrc == 0 and mmagic == MAGIC and mfails == 0:
                    raise AssertionError(label + " mutant survived")
                print("RED:", label)
        return 0
    except (AssertionError, OSError, RuntimeError, ET.ParseError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
