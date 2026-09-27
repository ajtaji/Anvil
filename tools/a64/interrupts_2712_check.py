#!/usr/bin/env python3
"""Desk gate for the BCM2712 (-t pi5) arm of RaspberryPi4/Lib/interrupts.pi4.

Runs the real driver, built -t pi5, against a register-level GIC-400 model at
the Pi 5 addresses - distributor $10_7FFF_9000, CPU interface $10_7FFF_A000
(bcm2712.dtsi:266-274 and the pinned DTB; TF-A rpi_hw.h:98-99) - and then
runs the shared scheduler timer (Anvil/Kernel/Scheduler/timer_el3.pbi, INTID
29 = secure physical timer PPI 13, bcm2712.dtsi:582-590) on top of it with
the existing tools/scheduler_context_timer_check.py model, relocated.

Checked, at EL2 and EL3, for GICD_TYPER line counts of 256, 320 and 512:
  * enable: ISENABLER bit set for SDIO2's INTID 306 and for the last line;
  * priority $A0 and target CPU0 written, and the originals restored at
    shutdown;
  * the line count comes from TYPER: the last line claims, one past refuses;
    1023 and an SGI refuse;
  * ack/EOI: the full IAR value goes back to EOIR after the handler; an
    unhandled line is masked before its EOI;
  * spurious 1020..1023: no EOI, dispatch reports handled;
  * a TYPER above the GIC-400's 512 INTIDs is refused with ZERO MMIO writes;
  * nothing touches the Pi 4 GIC at $FF84_1000 (the model faults on it).
--mutate builds broken copies of interrupts.pi4 and demands each fails.

Register model only; the board decides. Run with py -3 -B in PowerShell:
  py -3 -B tools/a64/interrupts_2712_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB_REL = pathlib.Path("RaspberryPi4/Lib/interrupts.pi4")
DEF_REL = pathlib.Path("RaspberryPi4/Intrinsics/bcm2711_hardware.def")
PROBE_REL = pathlib.Path("RaspberryPi5/Tests/interrupts_2712_gate.pi5")
TIMER_REL = [pathlib.Path("Anvil/Kernel/Scheduler/Tests/timer_el3.pi4"),
             pathlib.Path("Anvil/Kernel/Scheduler/timer_el3.pbi")]

D, C = 0x10_7FFF_9000, 0x10_7FFF_A000
PI4_LO, PI4_HI = 0xFF841000, 0xFF843000

spec = importlib.util.spec_from_file_location("irq2712_a64", ROOT / "tools/a64/a64_interp.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class Fail(Exception):
    pass


class Model(mod.A64):
    def __init__(self):
        super().__init__()
        self.writes = []

    def load(self, addr, size):
        if PI4_LO <= addr < PI4_HI:
            raise Fail("read of the Pi 4 GIC at $%X on a -t pi5 build" % addr)
        return super().load(addr, size)

    def store(self, addr, value, size):
        if PI4_LO <= addr < PI4_HI:
            raise Fail("write to the Pi 4 GIC at $%X on a -t pi5 build" % addr)
        if D <= addr < C + 0x2000:
            self.writes.append((addr, value & ((1 << (size * 8)) - 1), size))
        if D + 0x100 <= addr < D + 0x180:          # ISENABLERn: write-1-to-set
            return super().store(addr, self.load(addr, size) | value, size)
        if D + 0x180 <= addr < D + 0x200:          # ICENABLERn: write-1-to-clear
            return super().store(addr - 0x80, self.load(addr - 0x80, size) & ~value, size)
        return super().store(addr, value, size)


def build(root, compiler, src_rel, out):
    r = subprocess.run([compiler, "--compile", str(root / src_rel), "-t", "pi5",
                        "--load-addr", "0x400000", "--stack-addr", "0x3000000",
                        "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)),
                       capture_output=True, text=True)
    if r.returncode or not out.exists():
        raise Fail("build failed\n" + r.stdout[-1500:] + r.stderr)
    if "target BCM2712" not in r.stdout:
        raise Fail("the compiler did not build for BCM2712")
    return out


def run(img, el, typer_lines, raw):
    cpu = Model()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[0x400000 + i] = b
    cpu.enable_system_registers(el=el, preset={0xD51CC000: 0x8000, 0xD51EC000: 0x8000,
                                               0xD51B4220: 0x3C0, 0xD51800A0: 0})
    itl = typer_lines // 32 - 1
    for addr, value in ((D + 0xFE8, 0x20), (D + 8, 0x43B), (C + 0xFC, 0x0202143B),
                        (D + 4, 0x400 | itl), (D, 3), (C, 0x1E7), (C + 4, 0xFF), (C + 0xC, raw)):
        mod.A64.store(cpu, addr, value, 4)
    for w in range(max(1, typer_lines // 32)):
        mod.A64.store(cpu, D + 0x80 + 4 * w, 0xFFFFFFFF, 4)     # the stub's groups
    mod.A64.store(cpu, D + 0x400 + 306, 0xC0, 1)
    mod.A64.store(cpu, D + 0x800 + 306, 8, 1)
    mod.A64.store(cpu, 0x6000400, typer_lines, 8)
    cpu.pc, cpu.sp, cpu.x[30] = 0x400000, 0x3000000, 0xDEAD0000
    for _ in range(3_000_000):
        if cpu.pc == 0xDEAD0000:
            break
        cpu.step()
    else:
        raise Fail("the probe did not return")
    return cpu


def scenarios(img):
    errs = []

    def need(c, what):
        if not c:
            errs.append(what)

    for el in (2, 3):
        for lines in (320, 512):
            last = lines - 1
            for raw in (306, last, 29, 40, 7 | (2 << 10), 1020, 1023):
                tag = f"EL{el} lines {lines} IAR {raw}"
                try:
                    cpu = run(img, el, lines, raw)
                except Fail as e:
                    errs.append(f"{tag}: {e}")
                    continue
                out = [cpu.load(0x6000000 + i * 8, 8) for i in range(14)]
                spurious = (raw & 1023) >= 1020
                handled = raw in (306, last, 29)
                want = [1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, int(handled or spurious), 1]
                need(out == want, f"{tag}: results {out} want {want}")
                # enable bits, priority and target, set during the run
                en = [(a, v) for a, v, s in cpu.writes if a == D + 0x100 + (306 // 32) * 4]
                need(en and en[0][1] == 1 << (306 & 31), f"{tag}: ISENABLER9 bit 18 not written for 306")
                en_last = [(a, v) for a, v, s in cpu.writes if a == D + 0x100 + (last // 32) * 4 and v == 1 << (last & 31)]
                need(bool(en_last), f"{tag}: the last line {last} was not enabled")
                need((D + 0x400 + 306, 0xA0, 1) in cpu.writes, f"{tag}: priority $A0 not written for 306")
                need((D + 0x800 + 306, 1, 1) in cpu.writes, f"{tag}: target CPU0 not written for 306")
                need(cpu.load(D + 0x400 + 306, 1) == 0xC0 and cpu.load(D + 0x800 + 306, 1) == 8,
                     f"{tag}: 306's priority/target not restored at shutdown")
                eois = [v for a, v, s in cpu.writes if a == C + 0x10]
                need(eois == ([] if spurious else [raw]), f"{tag}: EOIs {eois}")
                calls = cpu.load(0x6000100, 8) + cpu.load(0x6000108, 8)
                need(calls == int(handled), f"{tag}: handler ran {calls} times")
                if raw == 40:
                    mask = [i for i, w in enumerate(cpu.writes) if w[0] == D + 0x184 and w[1] == 1 << 8]
                    eoi = [i for i, w in enumerate(cpu.writes) if w[0] == C + 0x10]
                    need(mask and eoi and mask[0] < eoi[0], f"{tag}: unhandled line not masked before EOI")
                need(cpu.load(D, 4) == 3 and cpu.load(C, 4) == 0x1E7 and cpu.load(C + 4, 4) == 0xFF,
                     f"{tag}: controller state not restored")
                need((D, 3 if el == 3 else 1, 4) in cpu.writes and (C, 0x1E7 if el == 3 else 1, 4) in cpu.writes,
                     f"{tag}: GICD/GICC_CTLR not programmed for EL{el}")
        # 256 lines: 306 is beyond TYPER and must refuse; the last is 255.
        cpu = run(img, el, 256, 1023)
        out = [cpu.load(0x6000000 + i * 8, 8) for i in range(14)]
        need(out[0] == 1 and out[1] == 0 and out[5] == 0 and out[6] == 1,
             f"EL{el} lines 256: {out} (306 must refuse, 255 must claim)")
        # More lines than a GIC-400 has: refuse with zero writes.
        cpu = run(img, el, 544, 1023)
        need(cpu.load(0x6000000, 8) == 0 and not cpu.writes,
             f"EL{el} TYPER 544 lines: init {cpu.load(0x6000000, 8)}, writes {cpu.writes[:4]}")
    return errs


def timer_on_top(root, compiler):
    """tools/scheduler_context_timer_check.py, unchanged except for the GIC
    base and -t pi5: the shared scheduler timer must pass on the 2712 arm."""
    src = (root / "tools/scheduler_context_timer_check.py").read_text(encoding="utf-8")
    for old, new in (("d,c=0xff841000,0xff842000", "d,c=0x107fff9000,0x107fffa000"),
                     ("'-t','pi4'", "'-t','pi5'")):
        if src.count(old) != 1:
            raise Fail(f"scheduler_context_timer_check.py changed shape ({old!r})")
        src = src.replace(old, new)
    src = src.replace("import build_count\n", "")
    src = src.replace("build_count.record_build(", "(lambda *a, **k: None)(")
    ns = {"__name__": "timer2712", "__file__": str(root / "tools/scheduler_context_timer_check.py")}
    old_argv, old_path = sys.argv, list(sys.path)
    sys.path.insert(0, str(root / "tools"))
    sys.argv = ["timer2712", "--compiler", compiler]
    try:
        exec(compile(src, "scheduler_context_timer_check(2712)", "exec"), ns)
        ns["main"]()
    except AssertionError as e:
        raise Fail(f"scheduler timer on the 2712 GIC: {e}")
    finally:
        sys.argv, sys.path[:] = old_argv, old_path


MUTANTS = [
    ("distributor at the Pi 4 address", "#IG_D = $107FFF9000", "#IG_D = $FF841000"),
    ("distributor and CPU interface swapped", "#IG_D = $107FFF9000\n#IG_C = $107FFFA000", "#IG_D = $107FFFA000\n#IG_C = $107FFF9000"),
    ("the Pi 4 256-slot bound", "#IG_SLOTS = 512", "#IG_SLOTS = 256"),
    ("TYPER bound removed", "  If count > #IG_SLOTS\n    ProcedureReturn 0\n  EndIf\n", ""),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="irq2712-") as td:
        td = pathlib.Path(td)
        try:
            errs = scenarios(build(ROOT, compiler, PROBE_REL, td / "irq.img"))
        except Fail as e:
            errs = [str(e)]
        for e in errs:
            print("FAIL", e)
        print(f"interrupts_2712_check: 28 dispatch cases + 4 bound cases, {len(errs)} failure(s)")
        rc |= 1 if errs else 0
        try:
            timer_on_top(ROOT, compiler)
        except Fail as e:
            print("FAIL", e)
            rc = 1
        if a.mutate:
            src = (ROOT / LIB_REL).read_text(encoding="utf-8").replace("\r\n", "\n")
            killed = 0
            for i, (label, old, new) in enumerate(MUTANTS):
                if src.count(old) != 1:
                    print(f"MUTANT {label}: pattern not found once - list is stale")
                    rc = 1
                    continue
                mroot = td / f"m{i}"
                for rel in (LIB_REL, DEF_REL, PROBE_REL):
                    (mroot / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, mroot / rel)
                (mroot / LIB_REL).write_text(src.replace(old, new), encoding="utf-8")
                try:
                    merr = scenarios(build(mroot, compiler, PROBE_REL, td / f"m{i}.img"))
                except Fail as e:
                    merr = [str(e)]
                killed += bool(merr)
                print(f"MUTANT {label}: {'killed' if merr else 'SURVIVED'}"
                      + (f" ({merr[0].splitlines()[0][:100]})" if merr else ""))
            print(f"mutants: {killed}/{len(MUTANTS)} killed")
            if killed != len(MUTANTS):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
