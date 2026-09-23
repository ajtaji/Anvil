#!/usr/bin/env python3
"""Execute the one-byte BSC0/MCU timeline diagnostic on the A64 model.

This checks emitted code and MMIO order.  It cannot prove that the MCU, panel
or BCM2711 will answer; the returning probe's RAM record exists for that.
"""

import argparse
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("PMF_REPO") or HERE.parents[1])
sys.path.insert(0, str(HERE))

import touch_emitted_check as touch                         # noqa: E402


PROBE = (ROOT / "RaspberryPi4" / "Tests" /
         "i2c_mcu_write_timeline_probe.pi4")
WORK = ROOT / "_work" / "i2c_mcu_timeline"
LOAD = 0x00500000
BSS = 0x00600000
STACK = 0x00800000
SNAP_C = 0
SNAP_S = 1


class PointerMcu(touch.Slave):
    """The harmless operation under test: accept only pointer byte 0x97."""

    def __init__(self):
        touch.Slave.__init__(self, 0x45)
        self.frames = []

    def write(self, data):
        self.frames.append(bytes(data))
        return data == b"\x97"

    def read(self, n):
        raise AssertionError("the timeline probe attempted an MCU read")


def read_u32(cpu, addr):
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path to external PureMetal compiler (or set PMF_COMPILER)")
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit("i2c MCU timeline gate: pass --compiler or set PMF_COMPILER")
    touch.PMF_COMPILER = pathlib.Path(args.compiler).expanduser().resolve()
    if not touch.PMF_COMPILER.is_file():
        raise SystemExit("i2c MCU timeline gate: compiler not found: %s"
                         % touch.PMF_COMPILER)

    WORK.mkdir(parents=True, exist_ok=True)
    img = WORK / "i2c_mcu_timeline.img"
    touch.build(PROBE.relative_to(ROOT).as_posix(), img, bss_addr=BSS,
                load_addr=LOAD, stack_addr=STACK)
    symbols = touch.image_symbols(img)
    fails = []
    cases = 0

    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("%s: %s" % (name, detail))

    def q(cpu, name, signed=False):
        value = touch.memory_u64(cpu, symbols, name)
        return touch.signed_u64(value) if signed else value

    def after(cpu):
        addr = symbols["global_probe_after"]
        return [read_u32(cpu, addr + 4 * i) for i in range(7)]

    def ready_bus(**kwargs):
        bus = touch.Bsc(base=touch.C["BSC0_BASE"], **kwargs)
        bus.regs[touch.C["BSC_C_OFF"]] = touch.C["BSC_C_I2CEN"]
        dev = PointerMcu()
        bus.add(dev)
        return bus, dev

    # Normal path: exactly one address frame and one pointer byte, with every
    # controller event coming from execution of the emitted PureMetal image.
    bus, dev = ready_bus()
    cpu, out, steps = touch.run(img, bus, load_addr=LOAD, stack_addr=STACK)
    writes = [(off, val) for off, val in bus.register_writes
              if off == touch.C["BSC_FIFO_OFF"]]
    check("success image returned", cpu.x[0] == 0,
          "Main returned %d" % cpu.x[0])
    check("success result and no recovery", q(cpu, "probe_result", True) == 0
          and q(cpu, "probe_recover_ok", True) == -1,
          "result=%d recover=%d" % (q(cpu, "probe_result", True),
                                    q(cpu, "probe_recover_ok", True)))
    check("exactly one 0x97 byte reached MCU 0x45",
          bus.starts == 1 and dev.frames == [b"\x97"] and
          writes == [(touch.C["BSC_FIFO_OFF"], 0x97)],
          "starts=%d frames=%r FIFO writes=%r"
          % (bus.starts, dev.frames, writes))
    check("TA/TXW/TXD/enqueue were observed",
          q(cpu, "probe_ta_ticks") > 0 and
          q(cpu, "probe_txw_ticks") >= q(cpu, "probe_ta_ticks") and
          q(cpu, "probe_txd_ticks") >= q(cpu, "probe_ta_ticks") and
          q(cpu, "probe_enqueue_ticks") >= q(cpu, "probe_txd_ticks") and
          q(cpu, "probe_ta_s") & touch.C["BSC_S_TA"] and
          q(cpu, "probe_txw_s") & touch.C["BSC_S_TXW"] and
          q(cpu, "probe_txd_s") & touch.C["BSC_S_TXD"] and
          q(cpu, "probe_enqueue_s") & touch.C["BSC_S_TXD"],
          "ticks TA/TXW/TXD/enq=%d/%d/%d/%d"
          % (q(cpu, "probe_ta_ticks"), q(cpu, "probe_txw_ticks"),
             q(cpu, "probe_txd_ticks"), q(cpu, "probe_enqueue_ticks")))
    check("DONE completed without ERR or CLKT",
          q(cpu, "probe_done_ticks") >= q(cpu, "probe_enqueue_ticks") and
          q(cpu, "probe_done_s") & touch.C["BSC_S_DONE"] and
          q(cpu, "probe_err_ticks") == 0 and
          q(cpu, "probe_clkt_ticks") == 0,
          "DONE/ERR/CLKT ticks=%d/%d/%d status=$%X"
          % (q(cpu, "probe_done_ticks"), q(cpu, "probe_err_ticks"),
             q(cpu, "probe_clkt_ticks"), q(cpu, "probe_done_s")))
    check("success published complete bounded record",
          q(cpu, "probe_done") == 0x49324D57 and
          q(cpu, "probe_hz") == touch.CNTFRQ and
          0 < q(cpu, "probe_total_ticks") < touch.CNTFRQ // 50,
          "done=$%X hz=%d total=%d steps=%d"
          % (q(cpu, "probe_done"), q(cpu, "probe_hz"),
             q(cpu, "probe_total_ticks"), steps))

    # An ordinary transaction which makes no progress must hit the real 20 ms
    # architectural-counter bound, then and only then use production recovery.
    stalled, stalled_dev = ready_bus(stall_writes=1, abort_delay=3)
    stalled_cpu, stalled_out, stalled_steps = touch.run(
        img, stalled, load_addr=LOAD, stack_addr=STACK)
    final = after(stalled_cpu)
    check("stalled write timed out then recovered",
          q(stalled_cpu, "probe_result", True) == touch.C["I2C_TIMEOUT"] and
          q(stalled_cpu, "probe_recover_ok", True) == 1 and
          not stalled.active and not stalled.abort_pending,
          "result=%d recover=%d active=%r pending=%d"
          % (q(stalled_cpu, "probe_result", True),
             q(stalled_cpu, "probe_recover_ok", True), stalled.active,
             stalled.abort_pending))
    check("stalled write observed TA but never invented FIFO progress",
          q(stalled_cpu, "probe_ta_ticks") > 0 and
          q(stalled_cpu, "probe_txd_ticks") == 0 and
          q(stalled_cpu, "probe_enqueue_ticks") == 0 and
          stalled_dev.frames == [],
          "TA/TXD/enq=%d/%d/%d frames=%r"
          % (q(stalled_cpu, "probe_ta_ticks"),
             q(stalled_cpu, "probe_txd_ticks"),
             q(stalled_cpu, "probe_enqueue_ticks"), stalled_dev.frames))
    check("stalled write used 20 ms deadline and ended enabled-idle",
          q(stalled_cpu, "probe_total_ticks") >= touch.CNTFRQ // 50 and
          q(stalled_cpu, "probe_total_ticks") < touch.CNTFRQ // 40 and
          final[SNAP_C] == touch.C["BSC_C_I2CEN"] and
          not (final[SNAP_S] & touch.C["BSC_S_TA"]),
          "total=%d C=$%X S=$%X steps=%d"
          % (q(stalled_cpu, "probe_total_ticks"),
             final[SNAP_C], final[SNAP_S], stalled_steps))

    # An address NACK must retain its specific result even though recovery is
    # subsequently used to normalize the controller.
    nack = touch.Bsc(base=touch.C["BSC0_BASE"])
    nack.regs[touch.C["BSC_C_OFF"]] = touch.C["BSC_C_I2CEN"]
    nack_cpu, nack_out, nack_steps = touch.run(
        img, nack, load_addr=LOAD, stack_addr=STACK)
    check("NACK remains distinct across recovery",
          q(nack_cpu, "probe_result", True) == touch.C["I2C_NACK"] and
          q(nack_cpu, "probe_recover_ok", True) == 1 and
          q(nack_cpu, "probe_err_ticks") > 0 and
          q(nack_cpu, "probe_err_s") & touch.C["BSC_S_ERR"],
          "result=%d recover=%d ERR tick/status=%d/$%X"
          % (q(nack_cpu, "probe_result", True),
             q(nack_cpu, "probe_recover_ok", True),
             q(nack_cpu, "probe_err_ticks"), q(nack_cpu, "probe_err_s")))

    # Refusal is read-only: neither disabled-idle nor enabled-busy is the exact
    # enabled-idle precondition under which this diagnostic is meaningful.
    disabled = touch.Bsc(base=touch.C["BSC0_BASE"])
    disabled_cpu, disabled_out, disabled_steps = touch.run(
        img, disabled, load_addr=LOAD, stack_addr=STACK)
    check("disabled controller is refused without MMIO writes",
          q(disabled_cpu, "probe_result", True) == -10 and
          disabled.register_writes == [] and disabled.starts == 0,
          "result=%d writes=%r starts=%d"
          % (q(disabled_cpu, "probe_result", True),
             disabled.register_writes, disabled.starts))

    busy, busy_dev = ready_bus(stall=True)
    busy.active = True
    busy.ta = True
    busy.stall_this = True
    busy.write_left = 1
    busy.cur = busy_dev
    busy_cpu, busy_out, busy_steps = touch.run(
        img, busy, load_addr=LOAD, stack_addr=STACK)
    check("active controller is refused without MMIO writes",
          q(busy_cpu, "probe_result", True) == -10 and
          busy.register_writes == [] and busy.starts == 0 and busy.ta,
          "result=%d writes=%r starts=%d TA=%r"
          % (q(busy_cpu, "probe_result", True), busy.register_writes,
             busy.starts, busy.ta))

    if fails:
        print("i2c_mcu_timeline_check: FAIL - %d" % len(fails))
        for failure in fails:
            print("  * " + failure)
        return 1
    print("i2c_mcu_timeline_check: PASS - %d cases" % cases)
    print("  emitted one-byte MCU pointer transaction, event timeline,")
    print("  20 ms failure/recovery, and read-only refusal paths executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
