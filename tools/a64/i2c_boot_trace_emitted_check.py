#!/usr/bin/env python3
"""Execute the opt-in boot I2C trace against the public A64/BSC model.

The gate compares trace-off and trace-on executions of the same existing MCU
and Goodix transactions. It grades the wire/MMIO write sequence, the bounded
paired RAM records, preflight-recovery annotation, saturation, and a readback
entry which is forbidden from touching MMIO or FIFO.
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("PMF_REPO") or HERE.parents[1]).resolve()
sys.path.insert(0, str(HERE))

import touch_emitted_check as touch  # noqa: E402

PROBE = ROOT / "RaspberryPi4" / "Tests" / "i2c_boot_trace_emitted_gate.pi4"
I2C = ROOT / "RaspberryPi4" / "Lib" / "i2c.pi4"
DSI = ROOT / "RaspberryPi4" / "Lib" / "dsi_panel_v2.pi4"
HW_TOUCH = ROOT / "RaspberryPi4" / "Board" / "hw_touch.pi4"
WORK = ROOT / "_work" / "i2c_boot_trace"
IMAGE = WORK / "i2c_boot_trace.img"
LOAD = 0x00500000
BSS = 0x00600000
STACK = 0x00800000
RETURN = 0xDEADBEE0


class IdentityMcu(touch.Slave):
    """The three read-only MCU identity bytes, with pointer surviving STOP."""

    def __init__(self):
        super().__init__(0x45)
        self.pointer = None
        self.pointer_writes = []
        self.reads = []
        self.regs = {0x97: 0x65, 0x98: 0x01, 0x99: 0x01}

    def write(self, data):
        if len(data) != 1:
            return False
        self.pointer = data[0]
        self.pointer_writes.append(data[0])
        return True

    def read(self, n):
        if self.pointer is None:
            return bytes([0xFF] * n)
        self.reads.append((self.pointer, n))
        return bytes(self.regs.get(self.pointer + i, 0xFF) for i in range(n))


class AuditBsc(touch.Bsc):
    def __init__(self, **kwargs):
        super().__init__(base=touch.C["BSC0_BASE"], **kwargs)
        self.read_offsets = []
        self.fifo_reads = 0

    def read32(self, off):
        self.read_offsets.append(off)
        if off == touch.C["BSC_FIFO_OFF"]:
            self.fifo_reads += 1
        return super().read32(off)


def symbols(image):
    return touch.image_symbols(image)


def u64(cpu, syms, name):
    return cpu.raw_load(syms["global_" + name], 8)


def s64(v):
    return v - (1 << 64) if v & (1 << 63) else v


def execute(cpu, step, entry):
    cpu.pc = entry
    cpu.x[30] = RETURN
    for _ in range(20_000_000):
        if cpu.pc == RETURN:
            return cpu.x[0]
        step()
    raise SystemExit("emitted boot-trace entry did not return")


def run(mode, seeded=None, goodix_present=True):
    blob = IMAGE.read_bytes()
    cpu = touch.A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    touch.attach_symbols(cpu, IMAGE, LOAD)
    syms = symbols(IMAGE)
    cpu.raw_store(syms["global_trace_fixture_mode"], mode, 8)
    cpu.sp = STACK

    bsc = AuditBsc(abort_delay=2,
                   abort_never=(seeded == "never"))
    mcu = IdentityMcu()
    goodix = touch.Goodix(addr=0x5D)
    bsc.add(mcu)
    if goodix_present:
        bsc.add(goodix)
    if seeded:
        bsc.active = True
        bsc.is_read = False
        bsc.ta = True
        bsc.cur = mcu
        bsc.write_left = 1
        bsc.stall_this = True

    console = bytearray()
    touch.install(cpu, bsc, console)
    steps = [0]
    plain = touch.A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = touch.CNTFRQ
            cpu.pc += 4
        elif (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = steps[0] * touch.TICKS_PER_STEP
            cpu.pc += 4
        else:
            plain()

    # Call the emitted procedure directly so the gate can seed the mode in
    # zeroed BSS. The image's public entry remains a returning Main.
    execute(cpu, step, LOAD + syms["main"])
    before_readback = (len(bsc.read_offsets), len(bsc.register_writes),
                       bsc.fifo_reads, bsc.starts, bsc.repeated_starts,
                       bsc.stops)
    execute(cpu, step, LOAD + syms["tracefixturereadback"])
    after_readback = (len(bsc.read_offsets), len(bsc.register_writes),
                      bsc.fifo_reads, bsc.starts, bsc.repeated_starts,
                      bsc.stops)
    return cpu, syms, bsc, mcu, goodix, before_readback, after_readback, steps[0]


def records(cpu, syms):
    count = u64(cpu, syms, "trace_fixture_count")
    base = syms["global_i2c_trace_words"]
    return [[s64(cpu.raw_load(base + (i * 9 + j) * 8, 8))
             for j in range(9)] for i in range(count)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmfc", default=os.environ.get("PMFC"),
                    help="external PureMetal compiler (or set PMFC)")
    ap.add_argument("--skip-mutations", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.pmfc:
        raise SystemExit("pass --pmfc or set PMFC")
    pmfc = pathlib.Path(args.pmfc).expanduser().resolve()
    if not pmfc.is_file():
        raise SystemExit("compiler not found: %s" % pmfc)

    touch.PMFC = pmfc
    WORK.mkdir(parents=True, exist_ok=True)
    touch.build(PROBE.relative_to(ROOT).as_posix(), IMAGE,
                bss_addr=BSS, load_addr=LOAD, stack_addr=STACK)

    fails = []
    checks = [0]

    def check(label, condition, detail=""):
        checks[0] += 1
        if not condition:
            fails.append("%s: %s" % (label, detail))

    default = run(-1)
    off = run(0)
    on = run(1)
    sat = run(2)
    recovered = run(1, seeded="recover")
    refused = run(1, seeded="never")
    missing = run(1, goodix_present=False)

    for label, result in (("default", default), ("off", off),
                          ("on", on), ("saturation", sat)):
        cpu, syms, bsc, mcu, goodix, before, after, steps = result
        check(label + " returned", u64(cpu, syms, "trace_fixture_done") == 0x49545243)
        check(label + " MCU identity", u64(cpu, syms, "trace_fixture_mcu") == 1)
        check(label + " Goodix identity", u64(cpu, syms, "trace_fixture_goodix") == 0x5D)
        check(label + " readback is RAM-only", before == after,
              "MMIO/transaction counters changed %r -> %r" % (before, after))
        check(label + " no unknown MMIO", not bsc.unknown_reads and not bsc.unknown_writes,
              "reads=%r writes=%r" % (bsc.unknown_reads, bsc.unknown_writes))

    off_cpu, off_syms, off_bsc, off_mcu, off_goodix, _, _, _ = off
    def_cpu, def_syms, def_bsc, def_mcu, def_goodix, _, _, _ = default
    on_cpu, on_syms, on_bsc, on_mcu, on_goodix, _, _, _ = on
    check("zero-BSS default is off",
          u64(def_cpu, def_syms, "trace_fixture_count") == 0)
    check("trace defaults/inert off", u64(off_cpu, off_syms, "trace_fixture_count") == 0)
    check("off has no overflow", u64(off_cpu, off_syms, "trace_fixture_overflow") == 0)
    check("explicit off adds no register access",
          (def_bsc.read_offsets, def_bsc.register_writes) ==
          (off_bsc.read_offsets, off_bsc.register_writes))
    check("explicit off adds no bus/device traffic",
          (def_bsc.starts, def_bsc.repeated_starts, def_bsc.stops,
           def_mcu.pointer_writes, def_mcu.reads,
           def_goodix.pointer_writes, def_goodix.reads) ==
          (off_bsc.starts, off_bsc.repeated_starts, off_bsc.stops,
           off_mcu.pointer_writes, off_mcu.reads,
           off_goodix.pointer_writes, off_goodix.reads))
    check("trace does not alter register writes",
          off_bsc.register_writes == on_bsc.register_writes)
    check("trace does not alter starts/stops",
          (off_bsc.starts, off_bsc.repeated_starts, off_bsc.stops) ==
          (on_bsc.starts, on_bsc.repeated_starts, on_bsc.stops))
    check("trace does not alter MCU traffic",
          (off_mcu.pointer_writes, off_mcu.reads) ==
          (on_mcu.pointer_writes, on_mcu.reads))
    check("trace does not alter Goodix traffic",
          (off_goodix.pointer_writes, off_goodix.reads,
           off_goodix.status_clears) ==
          (on_goodix.pointer_writes, on_goodix.reads,
           on_goodix.status_clears))

    recs = records(on_cpu, on_syms)
    expected = []
    for p in (1, 3, 5):
        expected += [(p, 1), (p, 4), (p, 7), (p, 2),
                     (p + 1, 1), (p + 1, 6), (p + 1, 7), (p + 1, 2)]
    # The six-byte combined identity read is shorter than RXR's 3/4 FIFO
    # threshold. Its receive bytes are therefore drained by DONE; there is no
    # separate RX milestone. Plain MCU reads still report RX because I2cXfer
    # begins directly in read direction and may service RXD.
    expected += [(7, e) for e in (1, 4, 5, 7, 2)]
    check("seven transactions with milestones", len(recs) == 29, "records=%d" % len(recs))
    check("phase and edge order",
          [(r[1], r[0]) for r in recs] == expected,
          repr([(r[1], r[0]) for r in recs]))
    check("real results retained",
          len([r for r in recs if r[0] == 2 and r[2] == 0]) == 7)
    check("healthy preflight did not recover",
          all(r[3] == 0 for r in recs if r[0] == 2))
    progress = [r for r in recs if r[0] in (4, 5, 6, 7)]
    check("milestones reuse status without snapshots",
          progress and all(r[5] == 0xFFFFFFFF and r[7] == 0xFFFFFFFF and
                           r[8] == 0xFFFFFFFF
                           for r in progress))
    check("snapshot excludes FIFO",
          on_bsc.fifo_reads == off_bsc.fifo_reads,
          "off=%d on=%d" % (off_bsc.fifo_reads, on_bsc.fifo_reads))
    check("exact trace read overhead",
          len(on_bsc.read_offsets) - len(off_bsc.read_offsets) == 14 * 4,
          "off=%d on=%d" % (len(off_bsc.read_offsets), len(on_bsc.read_offsets)))
    check("only C/S/DLEN/A added",
          sorted(on_bsc.read_offsets).count(touch.C["BSC_FIFO_OFF"]) ==
          sorted(off_bsc.read_offsets).count(touch.C["BSC_FIFO_OFF"]))

    sat_cpu, sat_syms = sat[0], sat[1]
    sat_recs = records(sat_cpu, sat_syms)
    check("bounded below fixed capacity", len(sat_recs) <= 64)
    check("overflow is loud", u64(sat_cpu, sat_syms, "trace_fixture_overflow") == 1)
    check("first history retained", sat_recs[:29] == recs)
    tail = sat_recs[29:]
    check("no orphan transaction",
          all(tail[i][0] == 1 and tail[i + 1][0] == 3 and tail[i + 2][0] == 2
              for i in range(0, len(tail), 3)))

    recovered_recs = records(recovered[0], recovered[1])
    check("successful preflight recovery annotated",
          any(r[0] == 3 for r in recovered_recs) and
          any(r[0] == 2 and r[3] == 1 and r[2] == 0 for r in recovered_recs),
          repr(recovered_recs[:3]))
    refused_recs = records(refused[0], refused[1])
    check("failed preflight recovery annotated",
          any(r[0] == 3 and r[2] == touch.C["I2C_TIMEOUT"] for r in refused_recs) and
          any(r[0] == 2 and r[3] == -1 and r[2] == touch.C["I2C_TIMEOUT"] for r in refused_recs),
          repr(refused_recs[:3]))
    check("failed recovery starts no new transfer",
          refused[2].starts == 0 and refused[2].repeated_starts == 0,
          "starts=%d repeated=%d" % (refused[2].starts,
                                      refused[2].repeated_starts))

    missing_recs = records(missing[0], missing[1])
    missing_faults = [r for r in missing_recs if r[0] == 3]
    check("failed Goodix identities preserve pre-cleanup faults",
          [r[1] for r in missing_faults] == [7, 8] and
          all(r[2] == touch.C["I2C_NACK"] and
              (r[6] & touch.C["BSC_S_ERR"]) for r in missing_faults),
          repr(missing_faults))
    check("failed Goodix identities still end with real results",
          [r[2] for r in missing_recs if r[0] == 2][-2:] ==
          [touch.C["I2C_NACK"], touch.C["I2C_NACK"]])

    i2c_text = I2C.read_text(encoding="utf-8", errors="strict")
    dsi_text = DSI.read_text(encoding="utf-8", errors="strict")
    hw_text = HW_TOUCH.read_text(encoding="utf-8", errors="strict")
    check("capture has an off-before-MMIO guard",
          "If i2c_trace_on = 0 Or i2c_trace_count >= #I2C_TRACE_MAX" in i2c_text)
    dsi_proc = dsi_text[dsi_text.index("Procedure.i DsiV2Read(reg.i)"):]
    check("MCU hook precedes existing write",
          dsi_proc.index("traced = I2cTraceBegin(phase)") <
          dsi_proc.index("r = I2cWrite(#DSI_V2_ADDR"))
    check("Goodix window brackets existing begin",
          "I2cTraceGoodixWindow(1)\n  a = Gt9Begin()\n  I2cTraceGoodixWindow(0)" in
          hw_text.replace("\r\n", "\n"))

    if fails:
        print("i2c_boot_trace_emitted_check: FAIL - %d/%d" %
              (len(fails), checks[0]))
        for failure in fails:
            print("  * " + failure)
        return 1
    if not args.skip_mutations:
        source_text = I2C.read_text(encoding="utf-8")
        mutations = (
            ("missing repeated-start milestone",
             "        I2cTraceMilestone(#I2C_TRACE_EDGE_SWITCH, s)\n", ""),
            ("missing combined TX milestone",
             "      I2cTraceMilestone(#I2C_TRACE_EDGE_TX, s)\n      While i < wn",
             "      While i < wn"),
        )
        for label, old, new in mutations:
            if source_text.count(old) != 1:
                raise SystemExit("mutation anchor is not unique: " + label)
            with tempfile.TemporaryDirectory(prefix="anvil-i2c-trace-mutant-") as td:
                staged = pathlib.Path(td)
                shutil.copytree(ROOT / "RaspberryPi4", staged / "RaspberryPi4")
                shutil.copy2(pmfc.parent / "keywords.def", staged / "keywords.def")
                compiler_intrinsics = pmfc.parent / "RaspberryPi4/Intrinsics"
                if compiler_intrinsics.is_dir():
                    shutil.copytree(compiler_intrinsics,
                                    staged / "RaspberryPi4/Intrinsics",
                                    dirs_exist_ok=True)
                mutant_i2c = staged / "RaspberryPi4/Lib/i2c.pi4"
                mutant_i2c.write_text(source_text.replace(old, new, 1), encoding="utf-8")
                env = os.environ.copy()
                env["PMF_REPO"] = str(staged)
                run_mutant = subprocess.run(
                    [sys.executable, str(pathlib.Path(__file__).resolve()),
                     "--pmfc", str(pmfc), "--skip-mutations"], env=env,
                    capture_output=True, text=True, timeout=120)
                if run_mutant.returncode == 0:
                    raise SystemExit("compiled mutation survived: " + label)
                if "i2c_boot_trace_emitted_check: FAIL" not in run_mutant.stdout:
                    raise SystemExit("mutation did not reach emitted assertions: " + label +
                                     "\n" + run_mutant.stdout + run_mutant.stderr)
            print("  rejected compiled mutation: " + label)
    total_steps = sum(x[7] for x in
                      (default, off, on, sat, recovered, refused, missing))
    print("i2c_boot_trace_emitted_check: PASS - %d checks, %d instructions" %
          (checks[0], total_steps))
    print("  off/on wire sequence identical; normal trace 29 records; capacity 64")
    print("  readback RAM-only; FIFO never sampled by the trace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
