#!/usr/bin/env python3
"""Grade the compiled banner status caption on the A64 oracle.

This is an emitted-code gate.  It builds RaspberryPi4/Tests/
banner_status_emitted_gate.pi4 with the real compiler over the REAL
Anvil/Hal/hal.pbi and the REAL RaspberryPi4/Board/banner_status.pi4, runs
the image in the A64 interpreter with a hard stop armed on any MMIO
access, and reads the captions the image composed out of DRAM.

It then compiles the SAME fixture a second time with #ANVIL_BANNER_FAN at
0 and requires two different things of that image: that the fan half is
gone from every caption, and that the text it would have written is not
in the image at all - a compile-time constant that only skips the code at
run time is not a constant a board with no fan can rely on.

Finally it applies a list of plausible mistakes to the product source,
one at a time, and requires the gate to go red for each; and it makes the
same demand of the source-level statements about where the sample is
taken, which are what keeps the caption out of the seam.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \
      py -3 tools/banner_status_emitted_check.py
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
GATE = ROOT / "RaspberryPi4" / "Tests" / "banner_status_emitted_gate.pi4"
STATUS = ROOT / "RaspberryPi4" / "Board" / "banner_status.pi4"
HAL = ROOT / "Anvil" / "Hal" / "hal.pbi"
FAN = ROOT / "Anvil" / "Core" / "fan_cmd.pbi"
PARSE = ROOT / "Anvil" / "Core" / "parse.pbi"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 20_000_000
MMIO = 0xFC000000

OUT = 0x06000000
SLOT = 0x100
META = 0x06010000

CLOCK = "2026-09-11 06:53:40 CDT"
LONG = "0123456789" * 12
FAN_LITERAL = b"    fan "

# slot -> the caption that scenario has to have composed, with the fan
# half compiled in and with it compiled out.
EXPECT_FAN_ON = {
    0: CLOCK,
    1: CLOCK + "    112 F",
    2: CLOCK + "    112 F    fan 63%",
    3: CLOCK + "    112 F    fan 0%",
    4: CLOCK + "    112 F    fan 100%",
    5: CLOCK + "    fan 100%",
    6: CLOCK + "    23 F",
    7: CLOCK + "    112 F",
    8: CLOCK + "    112 F",
    9: CLOCK + "    112 F",
    10: CLOCK + "    100 F",
    11: CLOCK + "    101 F",
    12: (LONG + "    112")[:127],
    13: CLOCK,
}

EXPECT_FAN_OFF = {
    0: CLOCK,
    1: CLOCK + "    112 F",
    2: CLOCK + "    112 F",
    3: CLOCK + "    112 F",
    4: CLOCK + "    112 F",
    5: CLOCK,
    6: CLOCK + "    23 F",
    7: CLOCK + "    112 F",
    8: CLOCK + "    112 F",
    9: CLOCK + "    112 F",
    10: CLOCK + "    100 F",
    11: CLOCK + "    101 F",
    12: (LONG + "    112")[:127],
    13: CLOCK,
}

# What each scenario is for, so a failure says which statement broke.
NOTE = {
    0: "a repaint before the first tick gets the clock alone",
    1: "a thermometer and no modulator: the temperature, nothing about a fan",
    2: "a hardware modulator at 62.5 percent rounds to a whole 63",
    3: "a claimed pin at rest is a fan being used, shown at zero",
    4: "software modulation at full",
    5: "no thermometer: the sentinel is not a reading",
    6: "below freezing, the rounding rule's other side",
    7: "a running modulator with no readable duty says nothing",
    8: "the repaint accessor returns the last composition",
    9: "a released pin that still reads back a duty is not a fan",
    10: "37.999 C is 100 F",
    11: "38.056 C is 101 F",
    12: "a caption that already fills the row stays inside its buffer",
    13: "a board that has not sampled yet has no temperature to show",
}

# Plausible mistakes in the caption itself.  Each MUST turn the gate red.
MUTANTS = (
    (
        "the caption asks the seam instead of the published sample",
        "status",
        "  t = HwTempSampled()\n",
        "  t = HwTempMilliC()\n",
    ),
    (
        "the no-thermometer sentinel is treated as a reading",
        "status",
        "  If t <> #HW_TEMP_NONE\n",
        "  If t <> 0\n",
    ),
    (
        "the duty is shown without asking whether a modulator is running",
        "status",
        "  If HwPwmKind() <> #HW_PWM_KIND_NONE\n",
        "  If 1 <> 0\n",
    ),
    (
        "the duty is truncated to a percent instead of rounded",
        "status",
        "    p = BannerStatusPutDec(p, (duty + 5) / 10)\n",
        "    p = BannerStatusPutDec(p, duty / 10)\n",
    ),
    (
        "a caption that does not fit is written past the end of its buffer",
        "status",
        "  While p < #BANNER_STATUS_MAX And PeekA(*s + i) <> 0\n",
        "  While PeekA(*s + i) <> 0\n",
    ),
    (
        "the decimal append is not bounded either",
        "status",
        "  While d > 0 And p < #BANNER_STATUS_MAX\n",
        "  While d > 0\n",
    ),
    (
        "a repaint recomposes instead of returning what the tick composed",
        "status",
        "  If gBannerStatusBuf[0] = 0\n    BannerStatusPut(0, WallClockCaption())\n  EndIf\n",
        "  BannerStatusPut(0, WallClockCaption())\n",
    ),
    (
        "the temperature loses its separator and runs into the clock",
        "status",
        '    p = BannerStatusPut(p, "    ")\n',
        '    p = BannerStatusPut(p, "")\n',
    ),
    (
        "the published sample is not a sentinel before anything samples",
        "hal",
        "Global gHwTempSampledMilliC.i = #HW_TEMP_NONE\n",
        "Global gHwTempSampledMilliC.i = 0\n",
    ),
)

# The statements that keep the caption out of the seam.  These are source
# facts, not executed ones: they are about WHERE a call is written, and a
# fixture cannot run the monitor's whole boot walk to show the loop.  Each
# is self-tested below by breaking the text in memory and requiring the
# check to notice.
def code_only(text: str) -> str:
    """The source with its comments removed.  Every statement below is about
    what the program DOES; a procedure named in a comment that explains why
    it is NOT called must not read as a call."""
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(";"):
            out.append("")
            continue
        head = line
        if '"' not in line:
            head = line.split(";", 1)[0]
        out.append(head)
    return "\n".join(out) + "\n"


def body_of(text: str, header: str) -> str:
    """One procedure's body, from its header line to its EndProcedure."""
    at = text.find(header)
    if at < 0:
        return ""
    end = text.find("EndProcedure", at)
    return text[at:end if end > 0 else len(text)]


SOURCE_CHECK_COUNT = 9


def source_checks(status_raw: str, fan_raw: str, parse_raw: str, hal_raw: str) -> list[str]:
    status = code_only(status_raw)
    fan = code_only(fan_raw)
    parse = code_only(parse_raw)
    hal = code_only(hal_raw)
    bad: list[str] = []
    if "HwTempMilliC(" in status:
        bad.append("banner_status.pi4 calls the temperature seam; it must read "
                   "HwTempSampled(), because the caption is composed from the "
                   "screen service and the boot walk reaches that")
    if "Procedure.i HwTempSampled()" not in hal:
        bad.append("hal.pbi no longer declares HwTempSampled(); the published "
                   "sample is the hardware layer's vocabulary")
    if "Procedure.i HwTempSampleNow()" not in fan:
        bad.append("fan_cmd.pbi no longer defines HwTempSampleNow(); one place "
                   "reads the temperature seam periodically")
    if "Procedure HwTempSampleTick()" not in fan:
        bad.append("fan_cmd.pbi no longer defines HwTempSampleTick()")

    sampler = body_of(fan, "Procedure.i HwTempSampleNow()")
    if "gHwTempSampledMilliC = HwTempMilliC()" not in sampler:
        bad.append("HwTempSampleNow() no longer publishes what the seam said, so "
                   "nothing a reader can see would ever change")

    tick = body_of(fan, "Procedure HwTempSampleTick()")
    if "HwTempSampleNow()" not in tick:
        bad.append("HwTempSampleTick() no longer takes a sample")

    policy = body_of(fan, "Procedure FanTick()")
    if "HwTempSampleNow()" not in policy or "HwTempMilliC(" in policy:
        bad.append("FanTick no longer reads through the sampler, so an armed board "
                   "would read the seam twice and the banner could disagree with "
                   "the policy that is acting on it")

    if "HwTempSampleTick()" not in parse:
        bad.append("the prompt spin no longer takes the temperature; nothing would "
                   "sample on a board with no fan armed")
    else:
        # AND IT HAS TO BE THE PROMPT SPIN, not somewhere on the paint path.
        spin = parse.split("HwTempSampleTick()")[0]
        if "FanTick()" not in spin[-4000:]:
            bad.append("the sample is no longer taken beside FanTick in the prompt "
                       "spin, which is the one loop nothing in the service table "
                       "reaches")
    return bad


SOURCE_MUTANTS = (
    ("the caption reads the seam again", "status",
     "  t = HwTempSampled()", "  t = HwTempMilliC()"),
    ("the prompt spin stops sampling", "parse",
     "    HwTempSampleTick()\n", ""),
    ("the policy reads the seam behind the sampler's back", "fan",
     "  t = HwTempSampleNow()\n", "  t = HwTempMilliC()\n"),
    ("the sampler stops publishing", "fan",
     "  gHwTempSampledMilliC = HwTempMilliC()\n", "  HwTempMilliC()\n"),
)


def locate(env_name: str, given: str | None, fallbacks) -> pathlib.Path:
    for candidate in [given, os.environ.get(env_name)]:
        if candidate:
            path = pathlib.Path(candidate).expanduser()
            if path.is_file():
                return path.resolve()
    for path in fallbacks:
        if path.is_file():
            return path.resolve()
    raise SystemExit(f"banner status gate: {env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_banner_status_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"banner status gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def stage(work: pathlib.Path, status_text: str, hal_text: str, gate_text: str) -> pathlib.Path:
    """A very small root: the two product sources, the gate, the intrinsics
    table and the pin aliases.  Staging means a mutation never touches the
    repository."""
    (work / "Anvil" / "Hal").mkdir(parents=True, exist_ok=True)
    (work / "RaspberryPi4" / "Board").mkdir(parents=True, exist_ok=True)
    (work / "RaspberryPi4" / "Tests").mkdir(parents=True, exist_ok=True)
    (work / "Anvil" / "Hal" / "hal.pbi").write_text(hal_text, encoding="utf-8")
    (work / "RaspberryPi4" / "Board" / "banner_status.pi4").write_text(status_text, encoding="utf-8")
    (work / "RaspberryPi4" / "Tests" / GATE.name).write_text(gate_text, encoding="utf-8")
    src = ROOT / "RaspberryPi4" / "Intrinsics"
    if src.is_dir():
        shutil.copytree(src, work / "RaspberryPi4" / "Intrinsics", dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    if (ROOT / "keywords.def").is_file():
        shutil.copy2(ROOT / "keywords.def", work / "keywords.def")
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> bytes:
    image = work / "banner_status_gate.img"
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
        raise SystemExit("banner status gate: compile failed\n" + run.stdout)
    return image.read_bytes()


def execute(a64, blob: bytes, work: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(blob):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, work / "banner_status_gate.img", LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(f"banner status gate: unexpected MMIO {kind} at ${addr:08X} - "
                             "this file is supposed to touch no hardware at all")

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"banner status gate: the probe did not return in {STEP_LIMIT} instructions")


def caption(cpu, slot: int) -> str:
    at = OUT + slot * SLOT
    out = []
    for i in range(SLOT):
        byte = cpu.memory.get(at + i, 0)
        if byte == 0:
            break
        out.append(chr(byte))
    return "".join(out)


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def grade(cpu, rc: int, expect: dict[int, str], fan_on: bool) -> tuple[list[str], int]:
    bad: list[str] = []
    checks = 0
    checks += 1
    if rc != 0:
        bad.append(f"the probe returned {rc}, not 0")
    for slot in sorted(expect):
        got = caption(cpu, slot)
        checks += 1
        if got != expect[slot]:
            bad.append(f"slot {slot} ({NOTE[slot]}): got {got!r}, wanted {expect[slot]!r}")
    # THE CAPTION NEVER READS THE SEAM, proven by execution and not by a grep.
    checks += 1
    seam = u64(cpu, META)
    if seam != 0:
        bad.append(f"the caption called the temperature seam {seam} time(s); it must read "
                   "the published sample, or the compiler is right to refuse the build")
    checks += 1
    if u64(cpu, META + 8) != 127:
        bad.append("the caption buffer is no longer 127 characters plus its terminator")
    # The bounded scenario has to fill the buffer exactly and stop.
    checks += 1
    if len(caption(cpu, 12)) != 127:
        bad.append(f"the bounded caption is {len(caption(cpu, 12))} characters, not the "
                   "127 the buffer holds")
    if not fan_on:
        checks += 1
        if any("fan" in caption(cpu, s) for s in expect):
            bad.append("a caption still mentions a fan with the constant at 0")
    return bad, checks


def run_once(a64, compiler, status_text, hal_text, gate_text, work_root, tag):
    with tempfile.TemporaryDirectory(prefix="anvil-banner-status-", dir=work_root) as temporary:
        work = pathlib.Path(temporary)
        source = stage(work, status_text, hal_text, gate_text)
        blob = build(compiler, work, source)
        cpu, rc, steps = execute(a64, blob, work)
        return cpu, rc, steps, blob


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--no-mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate("PMF_COMPILER", args.compiler, [ROOT / "PureMetalForge.exe", ROOT / "compiler"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    status_text = STATUS.read_text(encoding="utf-8")
    hal_text = HAL.read_text(encoding="utf-8")
    gate_text = GATE.read_text(encoding="utf-8")
    fan_text = FAN.read_text(encoding="utf-8")
    parse_text = PARSE.read_text(encoding="utf-8")

    fan_off_gate = gate_text.replace("#ANVIL_BANNER_FAN = 1", "#ANVIL_BANNER_FAN = 0")
    if fan_off_gate == gate_text:
        raise SystemExit("banner status gate: the fixture no longer declares "
                         "#ANVIL_BANNER_FAN, so the constant cannot be compiled out")

    with tempfile.TemporaryDirectory(prefix="anvil-banner-status-root-") as root:
        cpu, rc, steps, blob = run_once(a64, compiler, status_text, hal_text,
                                        gate_text, root, "product")
        bad, checks = grade(cpu, rc, EXPECT_FAN_ON, True)
        if FAN_LITERAL not in blob:
            bad.append("the fan text is not in the image even with the constant at 1")
            checks += 1
        else:
            checks += 1

        # The same fixture with the fan half compiled out.
        ocpu, orc, osteps, oblob = run_once(a64, compiler, status_text, hal_text,
                                            fan_off_gate, root, "fan off")
        obad, ochecks = grade(ocpu, orc, EXPECT_FAN_OFF, False)
        ochecks += 1
        if FAN_LITERAL in oblob:
            obad.append("the fan text is still in the image with #ANVIL_BANNER_FAN at 0; "
                        "a constant that only skips the code at run time is not a constant "
                        "a board with no fan can rely on")
        bad += [("fan compiled out: " + b) for b in obad]
        checks += ochecks

        source_bad = source_checks(status_text, fan_text, parse_text, hal_text)
        checks += SOURCE_CHECK_COUNT
        bad += source_bad

        if bad:
            print(f"banner_status_emitted_check: FAIL - {checks} checks")
            for failure in bad:
                print("  " + failure)
            return 1

        print(f"banner_status_emitted_check: PASS - {checks} checks over "
              f"{steps + osteps:,} executed A64 instructions")
        print("  14 captions composed by the real BannerCaption over the real HAL")
        print("  conversion; the seam was supplied and counted and was never called")
        print(f"  the same fixture rebuilt with the fan constant at 0: the fan half is "
              f"absent from every caption and the text is not in the image "
              f"({len(blob):,} B with it, {len(oblob):,} B without)")
        print(f"  {SOURCE_CHECK_COUNT} source statements about where the sample is taken")

        if args.no_mutate:
            return 0

        print()
        missed = 0
        for name, where, fixed, broken in MUTANTS:
            text = {"status": status_text, "hal": hal_text}[where]
            if text.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor is not in {where} exactly once")
                missed += 1
                continue
            mutated = text.replace(fixed, broken, 1)
            try:
                mcpu, mrc, msteps, mblob = run_once(
                    a64, compiler,
                    mutated if where == "status" else status_text,
                    mutated if where == "hal" else hal_text,
                    gate_text, root, name)
            except SystemExit as exc:
                print(f"  STALE  {name} - the mutation did not build, so the gate's checks")
                print(f"         were never exercised: {str(exc).splitlines()[0][:100]}")
                missed += 1
                continue
            mbad, _ = grade(mcpu, mrc, EXPECT_FAN_ON, True)
            if mbad:
                print(f"  rejected: {name} ({len(mbad)} checks failed, first: {mbad[0][:90]})")
            else:
                print(f"  GREEN    {name}  <-- THE GATE DID NOT NOTICE")
                missed += 1

        for name, where, fixed, broken in SOURCE_MUTANTS:
            text = {"status": status_text, "fan": fan_text, "parse": parse_text}[where]
            if text.count(fixed) < 1:
                print(f"  STALE  {name} - its anchor is not in {where}")
                missed += 1
                continue
            mutated = text.replace(fixed, broken, 1)
            probe = source_checks(
                mutated if where == "status" else status_text,
                mutated if where == "fan" else fan_text,
                mutated if where == "parse" else parse_text,
                hal_text)
            if probe:
                print(f"  rejected: {name} (source: {probe[0][:90]})")
            else:
                print(f"  GREEN    {name}  <-- THE SOURCE CHECKS DID NOT NOTICE")
                missed += 1

        total = len(MUTANTS) + len(SOURCE_MUTANTS)
        if missed:
            print(f"\nbanner_status_emitted_check: {missed} of {total} mutations were not caught")
            return 1
        print(f"\nbanner_status_emitted_check: all {total} mutations rejected")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
