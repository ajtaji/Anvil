#!/usr/bin/env python3
"""Desk gate for the passive target-neutral Vulkan shader IR.

The emitted fixture constructs IR records directly and runs the production
verifier.  It deliberately does not include or call the SPIR-V parser, Vulkan
pipeline, V3D backend, or hardware.  ``--mutate`` recompiles plausible broken
versions of the production verifier and proves that the emitted cases reject
them.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_ir.pbi"
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_ir_gate.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
MMIO = 0xFC000000
STEP_LIMIT = 30_000_000
MAGIC = 0x564B4952

REQUIRED = (
    "; Current front-end storage bounds, not SPIR-V or IR architectural limits.",
    "#ANVIL_IR_MAX_ID          = 192",
    "Structure AvkIrType Align #PB_Structure_AlignC",
    "Structure AvkIrDecoration Align #PB_Structure_AlignC",
    "Structure AvkIrBlock Align #PB_Structure_AlignC",
    "Structure AvkIrNode Align #PB_Structure_AlignC",
    "sourceId.i",
    "sourceOpcode.i",
    "Procedure.i AnvilVkIrVerify(*m.AvkIrModule)",
    "If *m\\blockCount <> 1",
    "If *n\\blockId <> *m\\entryBlockId",
    "If *n\\kind <> #ANVIL_IR_OP_RETURN",
    "If *n\\sourceId <> 0 Or *n\\resultType <> 0",
    "If *n\\sourceId = 0 Or *n\\operandCount <> 2",
    "#ANVIL_IR_OP_FADD              = 8",
    "#ANVIL_IR_OP_FMUL              = 9",
    "#ANVIL_IR_SPV_FADD = 129",
    "#ANVIL_IR_SPV_FMUL = 133",
    "Procedure.i avkIrFloatLanes(*m.AvkIrModule, typeId.i)",
    "If avkIrValueType(*m, *n\\operand0) <> *n\\resultType",
    "If avkIrValueType(*m, *n\\operand1) <> *n\\resultType",
    "#ANVIL_IR_DEC_NO_CONTRACTION   = 11",
    "#ANVIL_IR_DEC_FP_FAST_MATH_MODE = 12",
)

FORBIDDEN = (
    "XIncludeFile", "AnvilVkSpirv", "AnvilVkPipeline",
    "PokeA(", "PokeL(", "PokeN(", "Mailbox(", "Mmio(",
)

MUTANTS = (
    (
        "duplicate definitions become legal",
        "If avkIrPriorId(*m, id, 2, i) <> 0",
        "If avkIrPriorId(*m, id, 2, i) < 0",
    ),
    (
        "self-use becomes dominant",
        "If *n\\blockId <> blockId Or def >= nodeIndex",
        "If *n\\blockId <> blockId Or def > nodeIndex",
    ),
    (
        "float width is no longer fixed at 32",
        "If *t\\width <> 32 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\\sourceOpcode, i) : EndIf",
        "If *t\\width < 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, id, *t\\sourceOpcode, i) : EndIf",
    ),
    (
        "variable storage may disagree with its pointer",
        "If *t\\kind <> #ANVIL_IR_TYPE_POINTER Or *t\\storageClass <> *v\\storageClass",
        "If *t\\kind <> #ANVIL_IR_TYPE_POINTER Or *t\\storageClass = *v\\storageClass",
    ),
    (
        "duplicate decorations become legal",
        "If *prior\\sourceId = *d\\sourceId And *prior\\member = *d\\member And *prior\\kind = *d\\kind",
        "If *prior\\sourceId = 0 And *prior\\member = *d\\member And *prior\\kind = *d\\kind",
    ),
    (
        "multi-block CFG becomes representable without dominance",
        "If *m\\blockCount <> 1 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *m\\entryBlockId, #ANVIL_IR_SPV_LABEL, -1) : EndIf",
        "If *m\\blockCount < 1 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_UNSUPPORTED, *m\\entryBlockId, #ANVIL_IR_SPV_LABEL, -1) : EndIf",
    ),
    (
        "a non-Return final instruction is accepted",
        "If *n\\kind <> #ANVIL_IR_OP_RETURN : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TERMINATOR, *n\\sourceId, *n\\sourceOpcode, *m\\nodeCount - 1) : EndIf",
        "If *n\\kind = 0 : ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TERMINATOR, *n\\sourceId, *n\\sourceOpcode, *m\\nodeCount - 1) : EndIf",
    ),
    (
        "AccessChain may index past a structure",
        "If index < 0 Or index >= *u\\memberCount",
        "If index < 0 Or index > *u\\memberCount",
    ),
    (
        "sample coordinates may be vec3",
        "If *t = 0 Or *t\\kind <> #ANVIL_IR_TYPE_VECTOR Or *t\\componentCount <> 2",
        "If *t = 0 Or *t\\kind <> #ANVIL_IR_TYPE_VECTOR Or *t\\componentCount <> 3",
    ),
    (
        "source opcode no longer matches the IR operation",
        "If avkIrExpectedNodeOpcode(*n\\kind) = 0 Or *n\\sourceOpcode <> avkIrExpectedNodeOpcode(*n\\kind)",
        "If avkIrExpectedNodeOpcode(*n\\kind) = 0 Or *n\\sourceOpcode = 0",
    ),
    (
        "OpFAdd is mislabeled as OpFMul",
        "If kind = #ANVIL_IR_OP_FADD : ProcedureReturn #ANVIL_IR_SPV_FADD : EndIf",
        "If kind = #ANVIL_IR_OP_FADD : ProcedureReturn #ANVIL_IR_SPV_FMUL : EndIf",
    ),
    (
        "integer arithmetic passes as float32",
        "If lanes < 1\n        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\\sourceId, *n\\sourceOpcode, i)",
        "If lanes < 0\n        ProcedureReturn avkIrFail(#ANVIL_IR_ERR_TYPE, *n\\sourceId, *n\\sourceOpcode, i)",
    ),
    (
        "mixed right operand type is accepted",
        "If avkIrValueType(*m, *n\\operand1) <> *n\\resultType",
        "If avkIrValueType(*m, *n\\operand1) < 0",
    ),
    (
        "floating-point control decorations are silently accepted",
        "ElseIf *d\\kind = #ANVIL_IR_DEC_NO_CONTRACTION Or *d\\kind = #ANVIL_IR_DEC_FP_FAST_MATH_MODE",
        "ElseIf *d\\kind = -1 Or *d\\kind = -2",
    ),
)


def locate(env_name: str, explicit: str | None, fallbacks: list[pathlib.Path]) -> pathlib.Path:
    candidates = ([pathlib.Path(explicit)] if explicit else [])
    if os.environ.get(env_name):
        candidates.append(pathlib.Path(os.environ[env_name]))
    candidates.extend(fallbacks)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(f"vulkan IR gate: {env_name} was not found; pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_ir_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan IR gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_contract(text: str) -> list[str]:
    failures: list[str] = []
    for token in REQUIRED:
        if token not in text:
            failures.append("missing source contract: " + token)
    for token in FORBIDDEN:
        if token.lower() in text.lower():
            failures.append("passive target-neutral IR owns forbidden token: " + token)
    return failures


def build(compiler: pathlib.Path, suffix: str, module_text: str | None = None) -> pathlib.Path:
    # A second reviewer may run this gate concurrently. A process-unique,
    # minimal PMF root prevents image collisions AND makes mutations unable to
    # rewrite the shared repository while another worker is reviewing it.
    work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vulkan_ir_"))
    vulkan = work / "Anvil" / "Graphics" / "Vulkan"
    tests = vulkan / "Tests"
    tests.mkdir(parents=True, exist_ok=True)
    (vulkan / MODULE.name).write_text(
        MODULE.read_text(encoding="utf-8") if module_text is None else module_text,
        encoding="utf-8")
    shutil.copy2(GATE, tests / GATE.name)
    source = tests / GATE.name
    intrinsics = ROOT / "RaspberryPi4" / "Intrinsics"
    if intrinsics.is_dir():
        shutil.copytree(intrinsics, work / "RaspberryPi4" / "Intrinsics", dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / f"{suffix}.img"
    command = [
        str(compiler), "--compile", source.relative_to(work).as_posix(),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(command, cwd=work, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise SystemExit("vulkan IR gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= MMIO:
            raise SystemExit(f"vulkan IR gate: unexpected MMIO read at ${addr:08X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= MMIO:
            raise SystemExit(f"vulkan IR gate: unexpected MMIO write at ${addr:08X}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"vulkan IR gate: fixture did not return in {STEP_LIMIT} instructions")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def grade(cpu, report: int) -> tuple[int, list[str]]:
    failures: list[str] = []
    if u64(cpu, report) != MAGIC:
        return 0, [f"bad report magic at ${report:X}: {u64(cpu, report):X}"]
    checks = u64(cpu, report + 8)
    failed = u64(cpu, report + 16)
    if checks < 25:
        failures.append(f"fixture ran only {checks} checks")
    if failed:
        rows = []
        for i in range(checks):
            if u64(cpu, report + (8 + i) * 8) == 0:
                diag = [u64(cpu, report + (64 + i * 4 + field) * 8)
                        for field in range(4)]
                diag[0] = diag[0] - (1 << 64) if diag[0] >> 63 else diag[0]
                diag[3] = diag[3] - (1 << 64) if diag[3] >> 63 else diag[3]
                rows.append(f"{i + 1}[err={diag[0]},id={diag[1]},op={diag[2]},idx={diag[3]}]")
        failures.append(f"{failed} emitted checks failed: " + ",".join(rows))
    return checks, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate("PMF_COMPILER", args.compiler, [
        pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"),
    ])
    interp = locate("PMF_A64_INTERP", args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"])
    a64 = load_interpreter(interp)
    original = MODULE.read_text(encoding="utf-8")

    failures = source_contract(original)
    if failures:
        print("vulkan_ir_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1

    cpu, report, steps = execute(a64, build(compiler, "base"))
    checks, failures = grade(cpu, report)
    if failures:
        print(f"vulkan_ir_check: FAIL ({checks} emitted checks, {steps:,} instructions)")
        for failure in failures:
            print("  " + failure)
        return 1

    print(f"vulkan_ir_check: PASS - {checks} emitted checks, {steps:,} instructions")
    print("  passive target-neutral records preserve source id/opcode, type, storage and decorations")
    print("  FAdd/FMul cover float32 scalar and vec2/vec3/vec4 with exact type identity")
    print("  current-subset shapes plus deterministic hostile verifier cases")
    print("  one-block SSA dominance and final Return are explicit; Phi/multi-block remain refused")

    if not args.mutate:
        print("  (run with --mutate to prove the gate catches plausible verifier mistakes)")
        return 0

    missed = 0
    for name, fixed, broken in MUTANTS:
        count = original.count(fixed)
        if count != 1:
            print(f"  STALE  {name}: anchor appears {count} times")
            missed += 1
            continue
        try:
            mutant = original.replace(fixed, broken, 1)
            mcpu, mreport, _ = execute(a64, build(compiler, "mutant", mutant))
            _, dynamic_failures = grade(mcpu, mreport)
            caught = bool(dynamic_failures)
            detail = dynamic_failures[0] if dynamic_failures else ""
        except SystemExit as exc:
            caught, detail = True, str(exc).splitlines()[0]
        if caught:
            print(f"  RED    {name} - {detail[:100]}")
        else:
            print(f"  GREEN  {name} <-- emitted gate did not notice")
            missed += 1

    if missed:
        print(f"vulkan_ir_check: FAIL - {missed} of {len(MUTANTS)} mutations escaped")
        return 1
    print(f"vulkan_ir_check: all {len(MUTANTS)} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
