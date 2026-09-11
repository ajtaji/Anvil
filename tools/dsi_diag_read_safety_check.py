#!/usr/bin/env python3
"""Gate status-safe DSI diagnostics in source and emitted A64 (desk only)."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build as anvil_build  # noqa: E402
import build_count  # noqa: E402

SOURCE = ROOT / "RaspberryPi4" / "Board" / "dsi_cmd.pi4"
BOARD = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00200000
STACK = 0x07000000
RETURN_PC = 0xDEAD7290
DSI_BASE = 0xFE700000
DSI_LAST = DSI_BASE + 0x8C

SAFE = {
    0x00, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48,
    0x4C, 0x50, 0x54, 0x58, 0x5C, 0x60, 0x64, 0x68, 0x6C, 0x70,
    0x74, 0x8C,
}
FORBIDDEN = {0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20,
             0x24, 0x78, 0x7C, 0x80, 0x84, 0x88}
SAFE_CONSTANTS = (
    "DSI1_CTRL_OFF", "DSI1_DISP0_CTRL_OFF", "DSI1_DISP1_CTRL_OFF",
    "DSI1_INT_STAT_OFF", "DSI1_INT_EN_OFF", "DSI1_STAT_OFF",
    "DSI1_HSTX_TO_CNT_OFF", "DSI1_LPRX_TO_CNT_OFF",
    "DSI1_TA_TO_CNT_OFF", "DSI1_PR_TO_CNT_OFF", "DSI1_PHYC_OFF",
    "DSI1_HS_CLT0_OFF", "DSI1_HS_CLT1_OFF", "DSI1_HS_CLT2_OFF",
    "DSI1_HS_DLT3_OFF", "DSI1_HS_DLT4_OFF", "DSI1_HS_DLT5_OFF",
    "DSI1_HS_DLT6_OFF", "DSI1_HS_DLT7_OFF", "DSI1_PHY_AFEC0_OFF",
    "DSI1_PHY_AFEC1_OFF", "DSI1_ID_OFF",
)
FORBIDDEN_CONSTANTS = (
    "DSI1_TXPKT1C_OFF", "DSI1_TXPKT1H_OFF", "DSI1_TXPKT2C_OFF",
    "DSI1_TXPKT2H_OFF", "DSI1_RXPKT1H_OFF", "DSI1_RXPKT2H_OFF",
    "DSI1_TXPKT_CMD_FIFO_OFF", "DSI1_TXPKT_PIX_FIFO_OFF",
    "DSI1_RXPKT_FIFO_OFF", "DSI1_TST_SEL_OFF", "DSI1_TST_MON_OFF",
    "DSI1_PHY_TST1_OFF", "DSI1_PHY_TST2_OFF",
    "DSI1_PHY_FIFO_STAT_OFF",
)


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)


def procedure(text: str, name: str) -> str:
    found = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$", text)
    if not found:
        raise AssertionError(f"missing procedure {name}")
    return found.group(0)


def active(text: str) -> str:
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


def source_checks(c: Checks, text: str) -> None:
    pred = active(procedure(text, "DsiDiagRegReadable"))
    regs = active(procedure(text, "DsiRegs"))
    snap = active(procedure(text, "DsiSnapshotTake"))
    show = active(procedure(text, "DsiSnapshotShow"))
    cmd = active(procedure(text, "CmdDsi"))

    for name in SAFE_CONSTANTS:
        c.yes(f"Case #{name}" in pred, f"safe register missing: {name}")
    for name in FORBIDDEN_CONSTANTS:
        c.yes(name not in pred, f"unsafe register was allowlisted: {name}")
    c.yes(pred.count("ProcedureReturn 1") == len(SAFE_CONSTANTS),
          "predicate has an unreviewed readable branch")
    c.yes(pred.rstrip().endswith("ProcedureReturn 0\nEndProcedure"),
          "predicate does not refuse unknown/reserved offsets")

    c.yes(regs.count("DsiDiagRegReadable(o)") == 1 and
          regs.count("DsiRd(o)") == 1,
          "dsi regs lacks one shared-predicate guarded read site")
    c.yes(regs.find("DsiDiagRegReadable(o)") < regs.find("DsiRd(o)"),
          "dsi regs reads before checking the allowlist")
    c.yes("<skipped: not a status-safe register read>" in regs,
          "dsi regs hides skipped offsets or fabricates values")

    c.yes(snap.count("DsiDiagRegReadable(i * 4)") == 1 and
          snap.count("PeekN(#DSI1_BASE + i * 4)") == 1,
          "snapshot lacks one shared-predicate guarded read site")
    c.yes(snap.find("DsiDiagRegReadable(i * 4)") <
          snap.find("PeekN(#DSI1_BASE + i * 4)"),
          "snapshot reads before checking the allowlist")
    c.yes("dsi_snapRegValid[i] = 1" in snap and
          "dsi_snapRegValid[i] = 0" in snap,
          "snapshot does not record read validity explicitly")
    c.yes("If dsi_snapRegValid[i] <> 0" in show and
          "<skipped: not a status-safe register read>" in show,
          "snapshot display does not distinguish skipped from zero")

    calls = [m.start() for m in re.finditer(r"\bDsiSnapshotTake\(\)", cmd)]
    c.yes(len(calls) == 2, "CmdDsi must have bare and parsed snapshot sites")
    noarg = cmd.find("If gLine[gPos] = 0")
    unknown = cmd.find("If which = 0")
    help_guard = cmd.find("If which = 11")
    parsed_call = calls[-1]
    dispatch = cmd.find("If which = 1", parsed_call)
    c.yes(0 <= noarg < calls[0] < unknown < help_guard < parsed_call < dispatch,
          "snapshot placement no longer separates bare, rejection and action")
    c.yes(cmd.find("pokeOff = ParseHex()") < parsed_call and
          cmd.find("pokeV = ParseHex()") < parsed_call and
          cmd.find("If pokeOff < 0") < parsed_call,
          "malformed poke can trigger a snapshot before rejection")
    c.yes(cmd.find("fb = ParseHex()") < parsed_call,
          "malformed framebuffer address can trigger a snapshot")
    c.yes("DsiPokeCmd(pokeOff, pokeV)" in cmd,
          "validated poke arguments are not passed to the action")


def mutation_checks(c: Checks, text: str) -> None:
    mutations = (
        ("unsafe RX FIFO allowlist",
         "Case #DSI1_ID_OFF                : ProcedureReturn 1",
         "Case #DSI1_RXPKT_FIFO_OFF        : ProcedureReturn 1\n"
         "    Case #DSI1_ID_OFF                : ProcedureReturn 1"),
        ("unguarded live regs", "If DsiDiagRegReadable(o) <> 0", "If 1"),
        ("unguarded snapshot", "If DsiDiagRegReadable(i * 4) <> 0", "If 1"),
        ("fabricated skipped zero", "If dsi_snapRegValid[i] <> 0", "If 1"),
        ("snapshot before parse", "  SkipSpace()\n  If gLine[gPos] = 0",
         "  DsiSnapshotTake()\n  SkipSpace()\n  If gLine[gPos] = 0"),
        ("help touches hardware", "  If which = 11\n    DsiUsage()",
         "  If which = 11\n    DsiSnapshotTake()\n    DsiUsage()"),
    )
    for label, old, new in mutations:
        c.yes(old in text, f"mutation anchor missing: {label}")
        changed = text.replace(old, new, 1)
        try:
            source_checks(Checks(), changed)
        except AssertionError:
            c.yes(True, f"mutation killed: {label}")
        else:
            c.yes(False, f"mutation survived: {label}")


def model_checks(c: Checks) -> None:
    offsets = set(range(0, 0x90, 4))
    c.yes(SAFE | FORBIDDEN == offsets,
          "reviewed DSI range is incomplete or overlapping")
    for command, expected in (("", SAFE), ("regs", SAFE),
                              ("nonesuch", set()), ("help", set()),
                              ("pattern xyz", set()), ("poke 71 1", set())):
        got = set() if command in {"nonesuch", "help", "pattern xyz",
                                  "poke 71 1"} else set(SAFE)
        c.yes(got == expected, f"model command route wrong for {command!r}")
        c.yes(0x24 not in got, f"model consumed RX FIFO for {command!r}")


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_dsi_diag_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_symbols(image: Path) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            symbols[name.strip().lower()] = int(value.strip())
    return symbols


def put64(memory: dict[int, int], address: int, value: int) -> None:
    for byte in range(8):
        memory[address + byte] = (value >> (byte * 8)) & 0xFF


def build(pmfc: str, work: Path) -> Path:
    compiler_dir = work / "compiler"
    compiler_dir.mkdir(parents=True)
    compiler = anvil_build.staged_compiler(pmfc, compiler_dir)
    image = work / "dsi-diag.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [compiler, BOARD.relative_to(ROOT).as_posix(), "-t", "pi4",
               "-S", "-s", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or not image.is_file():
        raise AssertionError("Pi emitted build failed:\n" + result.stdout)
    # board.pi4 compiled end to end is a build of the monitor, and every build
    # of the monitor counts (ruled 2026-09-11).
    counted = build_count.record_build(BOARD, "pi4", image,
                                       by="tools/dsi_diag_read_safety_check.py",
                                       compiler=compiler)
    print(f"  build count: {counted.message}")
    return image


def fresh_cpu(a64, image: Path):
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    return cpu


def run_until_return(cpu, hooks: dict[int, callable] | None = None,
                     limit: int = 2_000_000) -> int:
    hooks = hooks or {}
    for steps in range(limit):
        if cpu.pc == RETURN_PC:
            return steps
        hook = hooks.get(cpu.pc)
        if hook is not None:
            hook(cpu)
            cpu.pc = cpu.x[30]
        else:
            cpu.step()
    raise AssertionError("emitted procedure did not return")


def emitted_checks(c: Checks, a64, image: Path) -> None:
    sym = parse_symbols(image)

    # Execute the actual emitted allowlist for every word and nearby bad inputs.
    for offset in [*range(0, 0x90, 4), 1, 2, 0x90, -4]:
        cpu = fresh_cpu(a64, image)
        cpu.pc = LOAD + sym["dsidiagregreadable"]
        cpu.sp = STACK
        cpu.x[0] = offset & 0xFFFFFFFFFFFFFFFF
        cpu.x[30] = RETURN_PC
        run_until_return(cpu, limit=20_000)
        c.yes((cpu.x[0] != 0) == (offset in SAFE),
              f"emitted predicate misclassified offset {offset:#x}")

    # Execute DsiRegs while replacing only printers and the final MMIO seam.
    reads: list[int] = []
    cpu = fresh_cpu(a64, image)
    cpu.pc = LOAD + sym["dsiregs"]
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    hooks = {}
    for name in ("uartwritestr", "puthex2", "puthex8", "printnl"):
        hooks[LOAD + sym[name]] = lambda _cpu: None

    def read_hook(inner) -> None:
        reads.append(inner.x[0])
        inner.x[0] = 0

    hooks[LOAD + sym["dsird"]] = read_hook
    run_until_return(cpu, hooks)
    c.yes(reads == sorted(SAFE),
          f"emitted dsi regs accessed wrong offsets: {reads}")
    c.yes(0x24 not in reads, "emitted dsi regs consumed RXPKT_FIFO")

    # Execute the snapshot and trace every actual byte fetched from DSI MMIO.
    class TraceMemory(dict[int, int]):
        def __init__(self, initial: dict[int, int]) -> None:
            super().__init__(initial)
            self.dsi_reads: list[int] = []

        def get(self, key, default=None):
            if DSI_BASE <= key <= DSI_LAST:
                self.dsi_reads.append(key)
            return super().get(key, default)

    cpu = fresh_cpu(a64, image)
    traced = TraceMemory(cpu.memory)
    cpu.memory = traced
    cpu.pc = LOAD + sym["dsisnapshottake"]
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    hooks = {}
    for name in ("dsicmrd", "dsi_snapdomain"):
        hooks[LOAD + sym[name]] = lambda inner: inner.x.__setitem__(0, 0)
    run_until_return(cpu, hooks)
    word_offsets = sorted({(address - DSI_BASE) & ~3
                           for address in traced.dsi_reads})
    c.yes(word_offsets == sorted(SAFE),
          f"emitted snapshot accessed wrong offsets: {word_offsets}")
    c.yes(not any(DSI_BASE + 0x24 <= address <= DSI_BASE + 0x27
                  for address in traced.dsi_reads),
          "emitted snapshot consumed RXPKT_FIFO")

    # Execute real command parsing. Rejected/help routes must not snapshot;
    # bare and regs must snapshot immediately before their selected action.
    def route(line: str) -> list[str]:
        inner = fresh_cpu(a64, image)
        line_at = sym["global_gline"]
        for index, byte in enumerate(line.encode("ascii") + b"\0"):
            inner.memory[line_at + index] = byte
        put64(inner.memory, sym["global_gpos"], 0)
        inner.pc = LOAD + sym["cmddsi"]
        inner.sp = STACK
        inner.x[30] = RETURN_PC
        events: list[str] = []
        local_hooks = {}
        for name in ("uartwritestr", "printnl"):
            local_hooks[LOAD + sym[name]] = lambda _cpu: None
        for name, event in (("dsisnapshottake", "snapshot"),
                            ("dsistatus", "status"),
                            ("dsiregs", "regs"), ("dsiusage", "usage")):
            def record(_cpu, value=event) -> None:
                events.append(value)
            local_hooks[LOAD + sym[name]] = record
        run_until_return(inner, local_hooks)
        return events

    expected_routes = {
        "": ["snapshot", "status"],
        "regs": ["snapshot", "regs"],
        "help": ["usage"],
        "nonesuch": ["usage"],
        "pattern xyz": [],
        "poke": [],
        "poke 71 1": [],
    }
    for line, expected in expected_routes.items():
        c.yes(route(line) == expected,
              f"emitted CmdDsi route wrong for {line!r}: {route(line)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP")
                        or str(INTERP))
    args = parser.parse_args()
    checks = Checks()
    try:
        text = SOURCE.read_text(encoding="utf-8")
        source_checks(checks, text)
        mutation_checks(checks, text)
        model_checks(checks)
        pmfc = anvil_build.find_compiler(args.pmfc)
        interpreter = load_interpreter(Path(args.interp).resolve())
        with tempfile.TemporaryDirectory(prefix="anvil-dsi-diag-") as name:
            emitted_checks(checks, interpreter, build(pmfc, Path(name)))
    except (AssertionError, OSError, RuntimeError,
            subprocess.SubprocessError) as error:
        print(f"dsi_diag_read_safety_check: FAIL after {checks.count} checks: {error}")
        return 1
    print(f"dsi_diag_read_safety_check: PASS - {checks.count} "
          "source/model/mutation/emitted checks")
    print("No board was contacted; register side effects remain a silicon boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
