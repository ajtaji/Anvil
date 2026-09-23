#!/usr/bin/env python3
"""touch_emitted_check.py - the Goodix touch driver, the Waveshare panel MCU,
and the repeated-start transfer they both needed, executed against a model
of the bus.

      python tools/a64/touch_emitted_check.py --compiler C:/path/to/PureMetalForge.exe
      python tools/a64/touch_emitted_check.py --compiler C:/path/to/PureMetalForge.exe --mutate

WHAT THIS PROVES

  It builds RaspberryPi4/Tests/touch_goodix_compile.pi4 with the
  real compiler and runs the real image on tools/a64/a64_interp.py, with
  three things modelled underneath it:

    * a BCM2711 BSC master at $FE804000, register by register, that
      dispatches framed transactions to a table of I2C slaves;
    * a Goodix GT911 at $14, with a 16-bit register pointer and a
      scripted sequence of touch frames;
    * a Waveshare panel-control MCU at $45, which records every byte
      written to it.

  Then it grades what went on the wire, not just what the probe printed.

THE ONE THING IT EXISTS FOR

  I2cWriteRead() is a mid-transaction poke at a controller. The BCM2835
  state-machine workaround used by Linux starts the write with an EMPTY
  FIFO, waits for TXW, fills as much as TXD allows, and queues READ|ST in
  the same TXW handling step that enqueues the last byte. Nothing in the
  tree could observe that order, or whether a STOP came out in the middle,
  because no model of this controller existed.

  Now one does, and THE GT911 MODEL FORGETS ITS REGISTER POINTER ON A
  STOP. So a driver that writes the pointer, stops, and then reads gets
  0xFF back and fails visibly, instead of getting plausible bytes from
  somewhere else in the register map. Mutation 3 is exactly that mistake
  and it must go red.

WHAT IT CANNOT PROVE, AND THE LIST IS SHORT AND IMPORTANT

  * The gate itself touches no real controller, MCU or panel. Its register
    behavior is derived from the BCM2711 manual and Linux driver, plus the
    narrow C=I2CEN/no-ST abort transition separately measured on silicon;
    executing the same emitted code in a model is still not hardware proof.
  * The model's "a STOP loses the pointer" rule is STRICTER THAN THE
    DATASHEET, because there is no Goodix datasheet on this machine and
    the claim comes from the comments in two drivers. Being stricter is
    the right direction for a gate - it forbids a pattern nobody has
    shown to be safe - but it means a green run here does NOT prove a
    real GT911 would have failed the two-transaction path.
  * DONE-before-the-first-TXW, delayed TA, an initially empty TXW, partial
    FIFO refill, and the immediate phase switch are EXERCISED here. That
    proves the emitted state transitions, not their timing on real silicon.
  * The axis transform is graded against the numbers in a device-tree
    overlay. If the overlay is wrong about this panel, this gate is wrong
    with it, in the same direction, and only a finger will say so.
  * The functional touch fixture is BSC1 on GPIO 2/3. The panel is on BSC0
    at GPIO 44/45. The independent abort-resume fixture selects and models
    BSC0, but addresses no device; the shipping touch path also selects BSC0.
"""

import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("PMF_REPO")
                    or pathlib.Path(__file__).resolve().parents[2])
sys.path.insert(0, str(HERE))

from a64_interp import A64, attach_symbols            # noqa: E402
from a64_target import TARGETS                        # noqa: E402

print("[gate] tree under test: %s" % ROOT, file=sys.stderr)

PMF_COMPILER = None
PROBE = ROOT / "RaspberryPi4" / "Tests" / "touch_goodix_compile.pi4"
ABORT_PROBE = (ROOT / "RaspberryPi4" / "Tests" /
               "i2c_abort_resume_probe.pi4")
DRV_TOUCH = ROOT / "RaspberryPi4" / "Lib" / "touch_goodix.pi4"
DRV_PANEL = (ROOT / "RaspberryPi4" / "Tests" / "Fixtures" /
             "dsi_panel_v1.pi4")
DRV_I2C = ROOT / "RaspberryPi4" / "Lib" / "i2c.pi4"
WORK = ROOT / "_work" / "touch"

G = TARGETS["pi4"]
LOAD = G["load"]
STACK = G["stack"]
UART_DR = G["uart_dr"]

LOADER_LR = 0xDEADBEE0
STEP_LIMIT = 80_000_000

# One microsecond of virtual time per interpreter step. This remains coarse
# enough to keep the probe's deliberate multi-second delays practical, while
# a 20 ms I2C no-progress deadline still spans thousands of emitted
# instructions instead of expiring in procedure overhead.
CNTFRQ = 54_000_000
TICKS_PER_STEP = CNTFRQ // 1_000_000


# =====================================================================
#  THE BSC MASTER
#
#  Register numbers and bits are re-derived here from the LIBRARY's own
#  constants rather than transcribed, so a rename in i2c.pi4 that this
#  file did not follow fails loudly instead of grading the wrong offset.
# =====================================================================

def lib_consts(text, names):
    out = {}
    for n in names:
        m = re.search(r"^#%s\s*=\s*\$([0-9A-Fa-f]+)" % re.escape(n),
                      text, re.M)
        if not m:
            m2 = re.search(r"^#%s\s*=\s*(-?\d+)" % re.escape(n), text, re.M)
            if not m2:
                raise SystemExit(
                    "i2c.pi4 no longer defines #%s, so this gate would be "
                    "checking an offset it invented. Fix the gate, do not "
                    "hardcode the number." % n)
            out[n] = int(m2.group(1))
        else:
            out[n] = int(m.group(1), 16)
    return out


I2C_TEXT = DRV_I2C.read_text(encoding="utf-8", errors="replace")
C = lib_consts(I2C_TEXT, [
    "BSC0_BASE", "BSC1_BASE", "BSC_C_OFF", "BSC_S_OFF", "BSC_DLEN_OFF", "BSC_A_OFF",
    "BSC_FIFO_OFF", "BSC_DIV_OFF", "BSC_DEL_OFF", "BSC_CLKT_OFF",
    "BSC_C_I2CEN", "BSC_C_ST", "BSC_C_CLEAR", "BSC_C_READ",
    "BSC_S_CLKT", "BSC_S_ERR", "BSC_S_RXF", "BSC_S_TXE", "BSC_S_RXD",
    "BSC_S_TXD", "BSC_S_RXR", "BSC_S_TXW", "BSC_S_DONE", "BSC_S_TA",
    "I2C_OK", "I2C_NACK", "I2C_TIMEOUT", "I2C_ARG", "I2C_NOSR",
    "I2C_PIN_SDA", "I2C_PIN_SCL",
])
BSC_BASE = C["BSC1_BASE"]
BSC_SIZE = 0x20

# GPIO, so I2cInit()'s pin muxing lands somewhere and I2cPinsMuxed() can
# read it back. A flat register file is enough: gpio.pi4 computes every
# address itself and this gate does not grade the pin arithmetic - that
# is already a64_anvil_check's job, executed, on this same library.
GPIO_BASE = 0xFE200000
GPIO_SIZE = 0x100

# The property mailbox. i2c.pi4 asks the firmware for the divider's source
# clock; a model that refuses makes it fall back to the nominal constant,
# which is a perfectly honest path and the one this gate takes. Modelling
# the mailbox faithfully belongs to a64_display_check, not here.
MBOX_BASE = 0xFE00B880
MBOX_SIZE = 0x80


class Slave:
    """An I2C slave. The BSC calls start/write/read/stop on it."""

    def __init__(self, addr):
        self.addr = addr
        self.stops = 0

    def write(self, data):
        """Return True if every byte was acknowledged."""
        raise NotImplementedError

    def read(self, n):
        """Return exactly n bytes."""
        raise NotImplementedError

    def stop(self):
        self.stops += 1


class PanelMcu(Slave):
    """The Waveshare panel-control MCU at 0x45.

    Linux never reads it, so neither does this: a read is answered with
    0xFF and counted, because a driver that started reading this device
    would be doing something no source on this disk supports.
    """

    def __init__(self, addr=0x45):
        Slave.__init__(self, addr)
        self.writes = []          # (reg, val) in order
        self.regs = {}
        self.bad_len = 0
        self.reads = 0

    def write(self, data):
        if len(data) != 2:
            # Every documented write to this device is register+value.
            self.bad_len += 1
            return False
        self.writes.append((data[0], data[1]))
        self.regs[data[0]] = data[1]
        return True

    def read(self, n):
        self.reads += 1
        return bytes([0xFF] * n)


class Goodix(Slave):
    """A GT911 (or GT9271) with a 16-bit register pointer.

    THE POINTER DIES ON A STOP. That is this model's whole reason for
    existing; see the module docstring for how sure we are of it.
    """

    def __init__(self, addr=0x5D, prodid=b"9271", firmware=0x1060,
                 config=0x41, max_points=10, xmax=800, ymax=1280,
                 trigger=1, not_ready_before_frame=2):
        Slave.__init__(self, addr)
        self.regs = {}
        self.ptr = None                  # None = no valid pointer
        self.prodid = prodid
        self.max_points = max_points
        self.xmax = xmax
        self.ymax = ymax
        self.trigger = trigger
        self.not_ready_before_frame = not_ready_before_frame

        # 0x8140: four id bytes then a 16-bit little-endian version.
        for i, b in enumerate(prodid[:4]):
            self.regs[0x8140 + i] = b
        self.regs[0x8144] = firmware & 0xFF
        self.regs[0x8145] = (firmware >> 8) & 0xFF

        # THE CONFIG BLOCK, at the offsets goodix_read_config uses
        # (goodix.c:1072, with RESOLUTION_LOC / MAX_CONTACTS_LOC /
        # TRIGGER_LOC at goodix.c:47-49). It is modelled rather than left
        # as one version byte because the driver now reports these two
        # resolutions and the board SCALES every coordinate by them - so
        # a read at the wrong offset, or big-endian, puts a finger in the
        # wrong place with nothing anywhere reporting an error.
        self.regs[0x8047] = config
        self.regs[0x8048] = xmax & 0xFF
        self.regs[0x8049] = (xmax >> 8) & 0xFF
        self.regs[0x804A] = ymax & 0xFF
        self.regs[0x804B] = (ymax >> 8) & 0xFF
        self.regs[0x804C] = max_points & 0x0F
        self.regs[0x804D] = trigger & 0x03
        self.regs[0x814E] = 0x00

        self.script = []                 # frames still to deliver
        self.armed = False               # a frame is sitting in the regs
        self.not_ready_left = 0
        self.frames_delivered = 0
        self.status_clears = 0
        self.reads_without_pointer = 0
        self.pointer_writes = 0
        self.reads = []                  # (reg, n) for every read served

    # ---- the script -------------------------------------------------
    def push_frame(self, points, claim=None):
        """points: list of (id, x, y, size). claim overrides the count
        byte, which is how an impossible frame is injected."""
        self.script.append((points, claim))

    def _arm_next(self):
        if self.armed or not self.script:
            return
        if self.not_ready_left > 0:
            self.not_ready_left -= 1
            return
        points, claim = self.script.pop(0)
        n = len(points) if claim is None else claim
        self.regs[0x814E] = 0x80 | (n & 0x0F)
        for i, (pid, x, y, sz) in enumerate(points):
            base = 0x814F + i * 8
            self.regs[base + 0] = pid & 0x0F
            self.regs[base + 1] = x & 0xFF
            self.regs[base + 2] = (x >> 8) & 0xFF
            self.regs[base + 3] = y & 0xFF
            self.regs[base + 4] = (y >> 8) & 0xFF
            self.regs[base + 5] = sz & 0xFF
            self.regs[base + 6] = (sz >> 8) & 0xFF
            self.regs[base + 7] = 0
        self.armed = True
        self.frames_delivered += 1
        self.not_ready_left = self.not_ready_before_frame

    # ---- the bus ----------------------------------------------------
    def write(self, data):
        if len(data) < 2:
            return False
        self.ptr = (data[0] << 8) | data[1]
        self.pointer_writes += 1
        for i, b in enumerate(data[2:]):
            reg = self.ptr + i
            self.regs[reg] = b
            if reg == 0x814E and b == 0:
                # The buffer release. The controller is now free to build
                # the next frame.
                self.armed = False
                self.status_clears += 1
        if len(data) > 2:
            self.ptr = self.ptr + len(data) - 2
        return True

    def read(self, n):
        if self.ptr is None:
            # A read with no pointer. On real silicon this returns
            # something; here it returns the byte that cannot be mistaken
            # for data, and it is counted so the gate can say so.
            self.reads_without_pointer += 1
            return bytes([0xFF] * n)
        if self.ptr == 0x814E:
            self._arm_next()
        self.reads.append((self.ptr, n))
        out = bytearray()
        for i in range(n):
            out.append(self.regs.get(self.ptr + i, 0x00))
        self.ptr += n
        return bytes(out)


class Bsc:
    """The BCM2711 BSC master, as much of it as a polled driver sees.

    THE TXW HOLD IS THE INTERESTING PART. The model delays TA/TXW, starts
    with an empty FIFO, and accepts at most `tx_chunk` bytes per TXW event.
    Once the last write byte is queued, the next status observation emits
    STOP; correct code therefore queues READ|ST in that same TXW handling
    step. Reads have independent wire progress: bytes enter the 16-byte FIFO,
    DLEN counts down, RXR rises at 3/4 full, and the controller—not a FIFO
    read—sets DONE when the requested length has arrived. `patience=0` makes
    DONE arrive before the first TXW and exercises NOSR.
    """

    def __init__(self, base=BSC_BASE, patience=2, tx_chunk=1, stall=False,
                 stall_writes=0, abort_delay=0, abort_never=False,
                 tx_gap_reads=1, abort_residue=b"", turnaround_reads=0,
                 rxr_without_rxd=False):
        self.base = base
        self.patience = patience
        self.devices = {}
        self.regs = {C["BSC_C_OFF"]: 0, C["BSC_S_OFF"]: 0,
                     C["BSC_DLEN_OFF"]: 0, C["BSC_A_OFF"]: 0,
                     C["BSC_DIV_OFF"]: 0x5DC, C["BSC_DEL_OFF"]: 0,
                     C["BSC_CLKT_OFF"]: 0x40}
        self.dlen_programmed = 0
        self.txbuf = bytearray()
        self.rxbuf = bytearray()
        self.read_data = bytearray()
        self.read_left = 0
        self.active = False
        self.is_read = False
        self.err = False
        self.clkt = False
        self.done = False
        self.ta = False
        self.write_left = 0
        self.write_data = bytearray()
        self.tx_chunk = tx_chunk
        self.stall = stall
        self.stall_writes = stall_writes
        self.stall_this = False
        self.abort_delay = abort_delay
        self.abort_never = abort_never
        self.abort_pending = 0
        self.abort_completions = 0
        self.abort_residue = bytes(abort_residue)
        self.tx_slots = 0
        self.tx_gap = False
        self.tx_gap_reads = tx_gap_reads
        self.tx_gap_left = 0
        self.start_delay = 2
        self.prefilled_starts = 0
        self.txw_events = 0
        self.phase_switches = 0
        self.polls = 0
        self.status_reads = 0
        self.cur = None
        # Optional silicon-observed write/read turnaround: RXD can describe
        # the shared FIFO before a read byte could have arrived. It expires
        # with controller progress; FIFO reads during it steal outgoing data.
        self.turnaround_reads = turnaround_reads
        self.turnaround_left = 0
        self.turnaround_fifo = bytearray()
        self.turnaround_fifo_reads = 0
        self.fifo_reads = 0
        self.rxr_without_rxd = rxr_without_rxd

        # Everything worth grading that is not a register.
        self.starts = 0
        self.repeated_starts = 0
        self.stops = 0
        self.nacks = 0
        self.unknown_reads = []
        self.unknown_writes = []
        self.register_writes = []

    def add(self, dev):
        self.devices[dev.addr] = dev

    def contains(self, addr):
        return self.base <= addr < self.base + BSC_SIZE

    # ---- transaction machinery -------------------------------------
    def _emit_stop(self):
        if (self.cur is not None and not self.is_read and
                self.write_left == 0 and self.write_data):
            if not self.cur.write(bytes(self.write_data)):
                self.nacks += 1
                self.err = True
        if self.cur is not None:
            self.cur.stop()
        self.stops += 1
        self.active = False
        self.ta = False
        self.done = True
        self.cur = None

    def _complete_abort(self):
        """Finish a controller-disable abort without committing its write.

        Real BSC abort completion is not synchronous with the C write. TA
        can remain visible and DONE can arrive later. Keeping that interval
        in the model is what catches a recovery path that clears S too early.
        """
        if self.cur is not None:
            self.cur.stop()
        self.stops += 1
        self.active = False
        self.ta = False
        self.done = True
        self.regs[C["BSC_DLEN_OFF"]] = 0
        self.cur = None
        self.write_left = 0
        self.write_data = bytearray()
        self.read_data = bytearray()
        self.read_left = 0
        self.tx_slots = 0
        self.tx_gap = False
        self.tx_gap_left = 0
        self.stall_this = False
        self.abort_pending = 0
        self.abort_completions += 1

    def _begin(self, is_read, repeated):
        addr = self.regs[C["BSC_A_OFF"]] & 0x7F
        dlen = self.regs[C["BSC_DLEN_OFF"]] & 0xFFFF
        self.read_data = bytearray()
        self.read_left = 0
        if not repeated:
            self.starts += 1
            dev = self.devices.get(addr)
            if dev is None:
                # Nothing acknowledged the address.
                self.nacks += 1
                self.err = True
                self.done = True
                self.active = False
                self.ta = False
                self.cur = None
                return
            self.cur = dev
        else:
            self.repeated_starts += 1
            if self.cur is None:
                self.err = True
                self.done = True
                self.active = False
                self.ta = False
                return

        # The repeated-start workaround explicitly begins with an empty
        # FIFO. Reject prefill in the model so the old TA shortcut cannot
        # accidentally pass this gate again.
        if not repeated and not is_read and self.txbuf:
            self.prefilled_starts += 1
            self.err = True
            self.done = True
            self.active = False
            self.ta = False
            self.cur = None
            return

        if repeated:
            self.phase_switches += 1
            if self.write_left != 0:
                self.err = True
                self.done = True
                self.active = False
                self.ta = False
                return
            if self.write_data and not self.cur.write(bytes(self.write_data)):
                self.nacks += 1
                self.err = True
                self.done = True
                self.active = False
                self.ta = False
                self.cur = None
                return

        self.active = True
        self.ta = bool(repeated or is_read)
        self.done = False
        self.polls = 0
        self.is_read = is_read
        if is_read:
            self.rxbuf = bytearray()
            self.read_data = bytearray(self.cur.read(dlen))
            if len(self.read_data) != dlen:
                raise AssertionError("model slave returned %d bytes for DLEN %d" %
                                     (len(self.read_data), dlen))
            self.read_left = dlen
            self.write_left = 0
            if repeated and self.turnaround_reads:
                self.turnaround_left = self.turnaround_reads
                self.turnaround_fifo = bytearray(self.write_data)
        else:
            self.write_left = dlen
            self.write_data = bytearray()
            self.tx_slots = 0
            self.tx_gap = False
            self.tx_gap_left = 0
            self.stall_this = self.stall
            if self.stall_writes > 0:
                self.stall_writes -= 1
                self.stall_this = True

    # ---- the register window ---------------------------------------
    def read32(self, off):
        if off == C["BSC_S_OFF"]:
            self.status_reads += 1
            if self.turnaround_fifo and not self.turnaround_left:
                self.turnaround_fifo = bytearray()
            if self.turnaround_left:
                self.turnaround_left -= 1
                s = C["BSC_S_TA"] | C["BSC_S_TXD"]
                if self.turnaround_fifo:
                    s |= C["BSC_S_RXD"]
                return s
            # CLEAR with I2CEN off requests an asynchronous abort but cannot
            # advance the controller state machine.  BCM2711 says disabled
            # controllers perform no transfers, and Linux explicitly warns
            # that the abort NACK/STOP remains queued for the next enable.
            # The old fixture decremented this countdown on status reads alone,
            # which let production "recover" while the engine was disabled --
            # precisely the state silicon disproved (C=0, S.TA=1).
            enabled = bool(self.regs[C["BSC_C_OFF"]] & C["BSC_C_I2CEN"])
            if self.abort_pending:
                if self.abort_never:
                    pass
                elif enabled:
                    self.abort_pending -= 1
                    if self.abort_pending == 0:
                        self._complete_abort()
            elif self.active and not self.is_read:
                self.polls += 1
                if self.stall_this:
                    # A stuck transfer can still have entered TA. It simply
                    # never reaches TXW/DONE until the driver aborts it.
                    if not self.ta and self.polls > self.start_delay:
                        self.ta = True
                elif self.patience == 0:
                    self._emit_stop()
                elif not self.ta and self.polls > self.start_delay:
                    self.ta = True
                elif self.ta and self.write_left == 0:
                    # The driver has already queued every byte. Its only
                    # safe action was READ|ST before asking status again.
                    self._emit_stop()
                elif self.ta and self.tx_gap:
                    # A configurable number of empty observations separates
                    # refill events. Long-but-sub-deadline gaps prove that
                    # byte progress resets the production deadline.
                    self.tx_gap_left -= 1
                    if self.tx_gap_left <= 0:
                        self.tx_gap = False
                elif self.ta and self.tx_slots == 0:
                    self.tx_slots = min(self.tx_chunk, self.write_left)
                    self.txw_events += 1
            elif self.active and self.is_read and not self.rxr_without_rxd:
                # One status observation advances one bus byte when FIFO
                # space exists. DLEN and DONE belong to this wire-side state;
                # reading FIFO only removes an already received byte.
                if self.read_left > 0 and len(self.rxbuf) < 16:
                    index = len(self.read_data) - self.read_left
                    self.rxbuf.append(self.read_data[index])
                    self.read_left -= 1
                    self.regs[C["BSC_DLEN_OFF"]] = self.read_left
                    if self.read_left == 0:
                        self._emit_stop()
            s = 0
            if self.err:
                s |= C["BSC_S_ERR"]
            if self.clkt:
                s |= C["BSC_S_CLKT"]
            if self.done:
                s |= C["BSC_S_DONE"]
            if self.ta:
                s |= C["BSC_S_TA"]
            if self.rxbuf:
                s |= C["BSC_S_RXD"]
            if len(self.rxbuf) >= 16:
                s |= C["BSC_S_RXF"]
            if self.active and self.is_read and len(self.rxbuf) >= 12:
                s |= C["BSC_S_RXR"]
            if self.active and self.is_read and self.rxr_without_rxd:
                s |= C["BSC_S_RXR"]
            if self.active and not self.is_read and self.tx_slots > 0:
                s |= C["BSC_S_TXD"]
            if self.active and not self.is_read and self.tx_slots > 0:
                s |= C["BSC_S_TXW"]
            if not self.txbuf:
                s |= C["BSC_S_TXE"]
            return s
        if off == C["BSC_FIFO_OFF"]:
            self.fifo_reads += 1
            if self.turnaround_fifo:
                self.turnaround_fifo_reads += 1
                return self.turnaround_fifo.pop(0)
            if self.rxbuf:
                return self.rxbuf.pop(0)
            return 0
        if off in self.regs:
            return self.regs[off]
        self.unknown_reads.append(off)
        return 0

    def write32(self, off, val):
        val &= 0xFFFFFFFF
        self.register_writes.append((off, val))
        if off == C["BSC_S_OFF"]:
            if val & C["BSC_S_ERR"]:
                self.err = False
            if val & C["BSC_S_CLKT"]:
                self.clkt = False
            if val & C["BSC_S_DONE"]:
                self.done = False
                if not self.active:
                    # BCM2711 exposes zero while DONE is asserted, then the
                    # last programmed DLEN again once TA=0/DONE=0.
                    self.regs[C["BSC_DLEN_OFF"]] = self.dlen_programmed
            return
        if off == C["BSC_DLEN_OFF"]:
            self.dlen_programmed = val & 0xFFFF
            self.regs[off] = self.dlen_programmed
            return
        if off == C["BSC_FIFO_OFF"]:
            self.txbuf.append(val & 0xFF)
            if self.active and not self.is_read:
                if self.tx_slots <= 0 or self.write_left <= 0:
                    self.err = True
                    self.done = True
                    self.active = False
                    self.ta = False
                else:
                    self.write_data.append(val & 0xFF)
                    self.txbuf.pop()
                    self.write_left -= 1
                    self.tx_slots -= 1
                    if self.tx_slots == 0 and self.write_left > 0:
                        self.tx_gap = True
                        self.tx_gap_left = self.tx_gap_reads
            return
        if off == C["BSC_C_OFF"]:
            self.regs[off] = val
            if val & C["BSC_C_CLEAR"]:
                if self.active and self.abort_delay > 0:
                    # CLEAR requests an abort. The bus-visible completion is
                    # deliberately delayed.  The build-24 controller retained
                    # RXD after completion, so a disabled CLEAR is not modelled
                    # as proof that the FIFO is empty; only a later idle CLEAR
                    # may discard the injected residue.
                    if self.abort_pending == 0:
                        self.abort_pending = self.abort_delay
                        if self.abort_residue:
                            self.rxbuf = bytearray(self.abort_residue)
                elif self.active:
                    self.txbuf = bytearray()
                    self.rxbuf = bytearray()
                    self.read_data = bytearray()
                    self.read_left = 0
                    if self.cur is not None:
                        self.cur.stop()
                    self.stops += 1
                    self.active = False
                    self.ta = False
                    self.cur = None
                    self.write_left = 0
                    self.write_data = bytearray()
                    self.tx_slots = 0
                    self.tx_gap = False
                    self.tx_gap_left = 0
                else:
                    self.txbuf = bytearray()
                    self.rxbuf = bytearray()
                    self.read_data = bytearray()
                    self.read_left = 0
            if val & C["BSC_C_ST"]:
                # A new START cannot outrun an unfinished abort. If a broken
                # recovery tries, the later abort DONE is what its next poll
                # observes, reproducing the stale-status contamination.
                if self.abort_pending == 0:
                    self._begin(bool(val & C["BSC_C_READ"]), self.active)
            return
        if off in self.regs:
            self.regs[off] = val
            return
        self.unknown_writes.append((off, val))


def run_bsc_receive_model_checks(fails):
    """Check documented receive state independently of emitted product code."""

    def expect(label, condition, detail):
        if not condition:
            fails.append("BSC receive model %s: %s" % (label, detail))

    # A one-byte transfer completes from wire-side DLEN progress while the
    # byte remains available in FIFO. Consuming it cannot be what creates
    # DONE or STOP.
    one = Bsc()
    one_dev = PanelMcu()
    one.add(one_dev)
    one.write32(C["BSC_A_OFF"], one_dev.addr)
    one.write32(C["BSC_DLEN_OFF"], 1)
    one.write32(C["BSC_C_OFF"], C["BSC_C_I2CEN"] | C["BSC_C_ST"] |
                C["BSC_C_READ"])
    status = one.read32(C["BSC_S_OFF"])
    expect("one-byte completion",
           status & C["BSC_S_DONE"] and status & C["BSC_S_RXD"] and
           not (status & C["BSC_S_TA"]) and
           one.regs[C["BSC_DLEN_OFF"]] == 0 and len(one.rxbuf) == 1,
           "DONE/RXD/TA/DLEN/FIFO were %X/%d/%d" %
           (status, one.regs[C["BSC_DLEN_OFF"]], len(one.rxbuf)))
    stops = one.stops
    one.read32(C["BSC_FIFO_OFF"])
    expect("FIFO pop is observational",
           one.done and one.stops == stops and len(one.rxbuf) == 0,
           "FIFO pop changed done=%r stops=%d fifo=%d" %
           (one.done, one.stops, len(one.rxbuf)))
    one.write32(C["BSC_S_OFF"], C["BSC_S_DONE"])
    expect("idle DLEN recalls programmed value",
           one.regs[C["BSC_DLEN_OFF"]] == 1,
           "DLEN=%d after DONE clear" % one.regs[C["BSC_DLEN_OFF"]])

    # With more bytes requested than FIFO capacity, receive progresses to
    # RXR, then RXF and stalls with DLEN remaining. FIFO space permits wire
    # progress to resume and only exhausting DLEN completes the transfer.
    many = Bsc()
    many_dev = PanelMcu()
    many.add(many_dev)
    many.write32(C["BSC_A_OFF"], many_dev.addr)
    many.write32(C["BSC_DLEN_OFF"], 20)
    many.write32(C["BSC_C_OFF"], C["BSC_C_I2CEN"] | C["BSC_C_ST"] |
                 C["BSC_C_READ"])
    for _ in range(12):
        status = many.read32(C["BSC_S_OFF"])
    expect("RXR threshold",
           status & C["BSC_S_RXR"] and status & C["BSC_S_TA"] and
           not (status & C["BSC_S_DONE"]) and len(many.rxbuf) == 12 and
           many.regs[C["BSC_DLEN_OFF"]] == 8,
           "status=%X fifo=%d DLEN=%d" %
           (status, len(many.rxbuf), many.regs[C["BSC_DLEN_OFF"]]))
    for _ in range(4):
        status = many.read32(C["BSC_S_OFF"])
    expect("RXF stalls wire",
           status & C["BSC_S_RXF"] and status & C["BSC_S_RXR"] and
           many.regs[C["BSC_DLEN_OFF"]] == 4 and len(many.rxbuf) == 16,
           "status=%X fifo=%d DLEN=%d" %
           (status, len(many.rxbuf), many.regs[C["BSC_DLEN_OFF"]]))
    before_left, before_stops = many.read_left, many.stops
    many.read32(C["BSC_FIFO_OFF"])
    expect("active FIFO pop does not complete",
           many.active and not many.done and many.read_left == before_left and
           many.stops == before_stops,
           "active=%r done=%r left=%d stops=%d" %
           (many.active, many.done, many.read_left, many.stops))
    for _ in range(4):
        many.read32(C["BSC_FIFO_OFF"])
    for _ in range(4):
        status = many.read32(C["BSC_S_OFF"])
    expect("wire completion after resumed space",
           status & C["BSC_S_DONE"] and not (status & C["BSC_S_TA"]) and
           many.regs[C["BSC_DLEN_OFF"]] == 0 and many.stops == 1,
           "status=%X DLEN=%d stops=%d" %
           (status, many.regs[C["BSC_DLEN_OFF"]], many.stops))
    many.write32(C["BSC_C_OFF"], C["BSC_C_I2CEN"] | C["BSC_C_CLEAR"])
    expect("idle CLEAR empties FIFO only",
           not many.rxbuf and many.done and
           many.regs[C["BSC_DLEN_OFF"]] == 0,
           "fifo=%d done=%r DLEN=%d" %
           (len(many.rxbuf), many.done, many.regs[C["BSC_DLEN_OFF"]]))
    many.write32(C["BSC_S_OFF"], C["BSC_S_DONE"])
    expect("DONE clear recalls configured DLEN",
           not many.done and many.regs[C["BSC_DLEN_OFF"]] == 20,
           "done=%r DLEN=%d" %
           (many.done, many.regs[C["BSC_DLEN_OFF"]]))
    return 9


def install(cpu, bsc, console):
    mem = cpu.memory

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if bsc.contains(addr):
            if size != 4 or (addr & 3):
                raise AssertionError(
                    "the image read %d byte(s) at $%08X inside the BSC "
                    "register window; every register there is 32 bits"
                    % (size, addr))
            return bsc.read32(addr - bsc.base)
        if GPIO_BASE <= addr < GPIO_BASE + GPIO_SIZE:
            return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))
        if MBOX_BASE <= addr < MBOX_BASE + MBOX_SIZE:
            # MAIL0_STA reading EMPTY for ever: the firmware never answers,
            # so i2c.pi4 falls back to its labelled nominal clock. That is
            # a real path in the library and the one this gate takes.
            return 0x40000000
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if bsc.contains(addr):
            if size != 4 or (addr & 3):
                raise AssertionError(
                    "the image wrote %d byte(s) at $%08X inside the BSC "
                    "register window" % (size, addr))
            bsc.write32(addr - bsc.base, value)
            return
        if addr == UART_DR:
            console.append(value & 0xFF)
            return
        if MBOX_BASE <= addr < MBOX_BASE + MBOX_SIZE:
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store


# =====================================================================
#  BUILD AND RUN
# =====================================================================

def build(probe_rel, out, bss_addr=None, load_addr=LOAD, stack_addr=STACK):
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PMF_COMPILER), "--compile", probe_rel, "-t", G["flag"],
           "--load-addr", hex(load_addr), "--stack-addr", hex(stack_addr),
           "--entry-returns", "-o", str(out)]
    if bss_addr is not None:
        cmd[7:7] = ["--bss-addr", hex(bss_addr)]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    r = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img, bsc, counter_hz=CNTFRQ, load_addr=LOAD, stack_addr=STACK):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[load_addr + i] = b
    attach_symbols(cpu, img, load_addr)
    cpu.pc = load_addr
    cpu.sp = stack_addr
    cpu.x[30] = LOADER_LR

    console = bytearray()
    install(cpu, bsc, console)

    steps = [0]
    plain_step = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:          # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = counter_hz
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:          # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = steps[0] * TICKS_PER_STEP
            cpu.pc += 4
            return
        plain_step()

    for _ in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, console.decode("latin-1"), steps[0]
        step()
    raise SystemExit("the probe never returned (%d steps)\n%s"
                     % (steps[0], console.decode("latin-1")))


def image_symbols(img):
    """Read the compiler's exact emitted global addresses for a probe."""
    sym_path = pathlib.Path(str(img) + ".sym")
    if not sym_path.is_file():
        raise SystemExit("symbol sidecar missing for emitted probe: %s"
                         % sym_path)
    symbols = {}
    for line in sym_path.read_text(encoding="utf-8",
                                   errors="strict").splitlines():
        name, sep, value = line.partition("=")
        if sep:
            symbols[name.strip().lower()] = int(value.strip(), 0)
    return symbols


def memory_u64(cpu, symbols, name):
    """Read one emitted PureMetal `.i` global without host ABI guessing."""
    key = ("global_" + name).lower()
    if key not in symbols:
        raise SystemExit("emitted symbol missing: %s" % key)
    addr = symbols[key]
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def signed_u64(value):
    return value - (1 << 64) if value & (1 << 63) else value


# The frames the model plays. Deliberately not all the same shape:
#   a single touch, then five, then ten (the maximum), then a frame with
#   no touches at all (which must still be cleared), then one that claims
#   eleven, which is impossible and must be refused.
SCRIPT = [
    ([(0, 100, 200, 30)], None),
    ([(i, 50 * i + 1, 60 * i + 2, 10 + i) for i in range(5)], None),
    ([(i, 7 * i + 3, 11 * i + 5, 20 + i) for i in range(10)], None),
    ([], None),
    ([(0, 1, 2, 3)], 11),
]


def make_bus(patience=2, goodix_kwargs=None, stall=False, **bsc_kwargs):
    """The bench bus: a GT9271 at $5D, which is what the v2 overlay's
    goodix@5d node describes and what is plugged into this board."""
    bsc = Bsc(patience=patience, stall=stall, **bsc_kwargs)
    g = Goodix(**(goodix_kwargs or {}))
    for points, claim in SCRIPT:
        g.push_frame(points, claim)
    bsc.add(g)
    bsc.add(PanelMcu())
    return bsc, g, bsc.devices[0x45]


def make_bus_v1(patience=2):
    """A v1 board: a GT911 at $14 and NOTHING at $5D.

    THE SECOND ADDRESS IS THE ONE THAT GETS FORGOTTEN. The driver probes
    $5D first now, because that is the bench panel; a fallback nobody
    exercises is a fallback that is wrong the day somebody plugs the
    other board in, and this run is what exercises it.

    Its config block is a LANDSCAPE one - 1280 x 800, five contacts -
    which is also the proof that the resolution and the contact count
    are READ off the part rather than assumed from the panel this tree
    happens to have been written against."""
    return make_bus(patience=patience, goodix_kwargs=dict(
        addr=0x14, prodid=b"911\x00", xmax=1280, ymax=800,
        max_points=5, trigger=0))


def grade(out, bsc, g, mcu, fails):
    cases = [0]

    def check(name, ok, detail):
        cases[0] += 1
        if not ok:
            fails.append("%s: %s" % (name, detail))

    # ---- the probe's own verdict ------------------------------------
    nfail = out.count("  FAIL ")
    check("the probe reports no failures of its own", nfail == 0,
          "the probe printed %d FAIL line(s); the first is %r"
          % (nfail, next((l for l in out.splitlines()
                          if "  FAIL " in l), "")))
    check("the probe ran its whole check list",
          out.count("  ok   ") >= 8,
          "only %d ok lines; sections 1, 3 and 5 assert more than eight "
          "between them, so the probe stopped part way"
          % out.count("  ok   "))
    check("the probe finished", "=== done" in out,
          "no done line - the probe returned early")

    # ---- THE REPEATED START, which is why this gate exists ----------
    # EXACTLY ONE pointerless read is legitimate and expected: i2c.pi4's
    # I2cProbe asks whether an address acknowledges by doing a one-byte
    # read, which by construction carries no register pointer. Section 2
    # of the probe does that once at $14. Any OTHER pointerless read is
    # the two-transaction path, and it is the thing this gate exists for.
    check("only the address probe read without a register pointer",
          g.reads_without_pointer == 1,
          "%d read(s) reached the controller with no pointer, and exactly "
          "one - the address probe - is legitimate. The rest are reads "
          "after a STOP threw the pointer away, which on real silicon "
          "return believable bytes from the wrong register instead of "
          "failing" % g.reads_without_pointer)
    check("the controller saw repeated starts",
          bsc.repeated_starts > 0,
          "not one repeated start was issued in the whole run, so "
          "I2cWriteRead either was not called or did not reach step 7")
    check("every combined write began with an empty FIFO",
          bsc.prefilled_starts == 0,
          "%d write(s) prefilled the FIFO before ST; the upstream BCM2835 "
          "repeated-start workaround explicitly starts empty"
          % bsc.prefilled_starts)
    check("TXW flow control drove the write phase",
          bsc.txw_events >= bsc.repeated_starts * 2,
          "%d TXW event(s) served %d repeated start(s); the model only "
          "accepts one pointer byte per TXW, so partial refill did not run"
          % (bsc.txw_events, bsc.repeated_starts))
    check("each phase switch happened while the write remained active",
          bsc.phase_switches == bsc.repeated_starts,
          "%d active phase switch(es), %d repeated start(s)"
          % (bsc.phase_switches, bsc.repeated_starts))
    check("every Goodix read followed a repeated start",
          bsc.repeated_starts >= len(g.reads),
          "%d reads were served but only %d repeated starts went out"
          % (len(g.reads), bsc.repeated_starts))

    # ---- identity ---------------------------------------------------
    check("the probe found the controller at $5D",
          "address = 93" in out,
          "the probe did not report address 93 ($5D), which is the "
          "address the v2 overlay's goodix@5d node gives the panel on "
          "this bench; it printed %r"
          % next((l for l in out.splitlines() if "address" in l), ""))
    check("the product id string was read and printed",
          "product id = 9271" in out,
          "the four ASCII id bytes did not come through; the line was %r"
          % next((l for l in out.splitlines() if "product id" in l), ""))
    check("the firmware version was read",
          "firmware version = 4192" in out,
          "the 16-bit little-endian version at 0x8144 did not decode to "
          "0x1060; the line was %r"
          % next((l for l in out.splitlines()
                  if "firmware version" in l), ""))
    check("the config version was read",
          "config version = 65" in out,
          "the config block's version byte did not read 0x41; the line "
          "was %r" % next((l for l in out.splitlines()
                           if "config version" in l), ""))
    check("the identity read asked for six bytes at 0x8140",
          (0x8140, 6) in g.reads,
          "the id read was %r, and four bytes would silently skip the "
          "firmware version" % [r for r in g.reads if r[0] == 0x8140])

    # ---- THE CONFIG BLOCK, which is where the mapping's inputs are ---
    # goodix.c:1072 reads it once at probe and takes x_max, y_max, the
    # contact count and the trigger type out of it. Anvil reads seven
    # bytes because those are the five numbers it wants; asking for one
    # would leave the resolution unknown and every coordinate unscalable.
    check("the config block was read as one seven-byte burst",
          (0x8047, 7) in g.reads,
          "the config read was %r; one byte gets the version and none of "
          "the resolution, and two separate reads would put a STOP where "
          "the pointer has to survive"
          % [r for r in g.reads if r[0] == 0x8047])
    check("the x range came back little-endian",
          "x range = %d" % g.xmax in out,
          "the model's x_max is %d; the probe printed %r. Big-endian "
          "here reads %d, which is a plausible-looking number and would "
          "scale every finger wrong with no error anywhere"
          % (g.xmax, next((l for l in out.splitlines()
                           if "x range" in l), ""),
             ((g.xmax & 0xFF) << 8) | (g.xmax >> 8)))
    check("the y range came back little-endian",
          "y range = %d" % g.ymax in out,
          "the model's y_max is %d; the probe printed %r"
          % (g.ymax, next((l for l in out.splitlines()
                           if "y range" in l), "")))
    check("the contact count came out of the config block, not a constant",
          "contact slots = %d" % g.max_points in out,
          "the model's config block declares %d contacts and the probe "
          "printed %r. A hardcoded ten would pass on this bench's part "
          "and accept frames a five-point controller cannot produce"
          % (g.max_points, next((l for l in out.splitlines()
                                 if "contact slots" in l), "")))
    check("the trigger type came out of the config block",
          "trigger type asked for = %d" % g.trigger in out,
          "the model declares trigger type %d; the probe printed %r"
          % (g.trigger, next((l for l in out.splitlines()
                              if "trigger type" in l), "")))

    # ---- the frame handshake ----------------------------------------
    check("every frame the model played was seen",
          "frames seen = %d" % g.frames_delivered in out,
          "the model delivered %d frames; the probe reported %r"
          % (g.frames_delivered,
             next((l for l in out.splitlines()
                   if "frames seen" in l), "")))
    check("the impossible frame was refused",
          "frames refused for an impossible count = 1" in out,
          "a frame claiming eleven touches was not refused; the line was "
          "%r" % next((l for l in out.splitlines()
                       if "impossible" in l), ""))
    check("the buffer flag was released once per frame",
          g.status_clears == g.frames_delivered + 1,
          "the controller saw %d writes of zero to 0x814E for %d frames "
          "plus the one Gt9Begin sends. Miss one and a real controller "
          "produces no further frame at all"
          % (g.status_clears, g.frames_delivered))
    check("no frame was cleared before it was ready",
          g.status_clears <= g.frames_delivered + 1,
          "%d clears for %d frames - a clear while the ready bit was low "
          "throws away the frame being assembled"
          % (g.status_clears, g.frames_delivered))

    # ---- coordinates ------------------------------------------------
    # Frame 3 is ten points, the widest read the driver ever does.
    check("the ten-touch frame was reported whole",
          "frame with 10 touch(es)" in out,
          "the maximum-size frame did not come through; the driver's "
          "buffer or its contact stride is wrong")
    check("the five-touch frame was reported whole",
          "frame with 5 touch(es)" in out,
          "the five-point frame did not come through")
    # Point 0 of frame 1: raw (100,200) -> screen (1279-200, 100).
    check("a coordinate survived the little-endian decode",
          "raw 100,200" in out,
          "the first frame's raw coordinates did not read 100,200 - the "
          "X/Y bytes are being assembled the wrong way round")
    # THERE IS NO TRANSFORM CHECK HERE ANY MORE AND ITS ABSENCE IS THE
    # POINT. The screen mapping left this driver: a contact becomes a
    # pixel in the display layer, through the same rotation and scale
    # the console's own pixels go through, and it is graded at all four
    # rotations and every corner by section J of pi4DsiScreenProbe.pi4
    # under tools/a64/a64_dsiscreen_check.py. A copy of that check here
    # would be a second opinion about which way up the panel is, which
    # is exactly the shape the move was made to remove.
    # THE LAST CONTACT OF THE WIDEST FRAMES, and these two exist because
    # a contact stride of seven survived an earlier version of this gate:
    # with one touch in the frame, a wrong stride reads the same bytes as
    # a right one, and only the Nth contact moves. Frame 2's point 4 is
    # raw (201,242) and frame 3's point 9 is raw (66,104).
    check("the fifth contact of the five-touch frame is where it was put",
          "id 4  raw 201,242" in out,
          "the last point of the five-touch frame did not decode; a "
          "contact stride that is wrong by one byte reads correctly for "
          "contact 0 and drifts by one byte per contact after it")
    check("the tenth contact of the ten-touch frame is where it was put",
          "id 9  raw 66,104" in out,
          "the last point of the ten-touch frame did not decode; nine "
          "strides of drift is where a stride error is unmissable")

    # ---- the panel MCU ----------------------------------------------
    want = [(0xC0, 1), (0xC2, 1), (0xAC, 1),
            (0xAB, 0xFF), (0xAA, 1),      # level 0   -> 0xFF
            (0xAB, 0x7F), (0xAA, 1),      # level 128 -> 0x7F
            (0xAB, 0x00), (0xAA, 1),      # level 255 -> 0x00
            (0xAD, 1)]
    check("the panel MCU saw exactly the documented sequence",
          mcu.writes == want,
          "wrote %s, wanted %s"
          % (["%02X=%02X" % w for w in mcu.writes],
             ["%02X=%02X" % w for w in want]))
    check("the backlight value is inverted",
          (0xAB, 0x00) in mcu.writes and (0xAB, 0xFF) in mcu.writes,
          "full brightness must reach the MCU as 0x00 and dark as 0xFF; "
          "the levels written were %s"
          % [hex(v) for r, v in mcu.writes if r == 0xAB])
    check("every backlight level was committed",
          len([1 for r, v in mcu.writes if r == 0xAA])
          == len([1 for r, v in mcu.writes if r == 0xAB]),
          "%d level writes and %d commits - a level with no 0xAA after it "
          "never takes effect"
          % (len([1 for r, v in mcu.writes if r == 0xAB]),
             len([1 for r, v in mcu.writes if r == 0xAA])))
    # Same exemption: the address scan read-probes 0x45 once. Nothing
    # else may, because no source on this disk documents a readable
    # register on that device.
    check("the panel MCU was only address-probed, never read for data",
          mcu.reads == 1,
          "%d read(s) were aimed at 0x45; one is the address probe and "
          "no source on this disk documents a readable register there"
          % mcu.reads)
    check("every write to the MCU was register-plus-value",
          mcu.bad_len == 0,
          "%d write(s) were not two bytes long" % mcu.bad_len)

    # ---- the bus itself ---------------------------------------------
    check("no register outside the modelled BSC window was read",
          not bsc.unknown_reads,
          "read offsets %s" % [hex(o) for o in bsc.unknown_reads])
    check("no register outside the modelled BSC window was written",
          not bsc.unknown_writes,
          "wrote %s" % [(hex(o), hex(v)) for o, v in bsc.unknown_writes])
    # THE DRIVER'S OWN ORDER, NOT THE PROBE'S ADDRESS SCAN. Section 2
    # walks the four addresses in numeric order and always will; what
    # matters is which one Gt9Begin asks FIRST, because that is the one
    # whose bus code survives when nothing answers. $5D is the bench
    # panel, so $5D is first, and the reads the model saw say so.
    first_reads = [r for r in g.reads if r[0] == 0x8140]
    check("the driver read the identity at the address that answered",
          bool(first_reads),
          "no read of 0x8140 reached the controller at all, so the "
          "probe never asked it what it was")
    check("the run left no transfer half-open", not bsc.active,
          "the controller is still ACTIVE at the end of the run, which "
          "on silicon is a bus held for ever")

    return cases[0]


def run_clean(probe_rel, work, fails):
    img = work / "touch.img"
    build(probe_rel, img)
    bsc, g, mcu = make_bus()
    cpu, out, steps = run(img, bsc)
    n = grade(out, bsc, g, mcu, fails)

    # Main() returns its own failure count.
    if cpu.x[0] & 0xFFFFFFFF:
        fails.append("the probe returned %d from Main()"
                     % (cpu.x[0] & 0xFFFFFFFF))
    n += 1
    return n, out, steps


def run_turnaround_rxd(probe_rel, work, fails):
    """Run emitted product code with physical write/read-boundary RXD.

    The transient expires independently of software. This does not invent a
    controller that completes only when FIFO is left alone; it checks solely
    that RXD without the documented read qualifiers is not consumed.
    """
    img = work / "touch.img"
    bsc, g, mcu = make_bus(turnaround_reads=2)
    cpu, out, steps = run(img, bsc)
    cases = 0

    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("turnaround RXD: %s: %s" % (name, detail))

    check("outgoing FIFO was not read",
          bsc.turnaround_fifo_reads == 0,
          "%d FIFO read(s) consumed outgoing bytes" %
          bsc.turnaround_fifo_reads)
    check("identity output remained exact",
          "product id = 9271" in out and "firmware version = 4192" in out,
          "identity output was corrupted: %r" %
          [line for line in out.splitlines() if "product id" in line or
           "firmware version" in line])
    check("combined reads completed",
          bsc.repeated_starts > 0 and not bsc.active and
          "=== done" in out and not (cpu.x[0] & 0xFFFFFFFF),
          "repeated=%d active=%r return=%d" %
          (bsc.repeated_starts, bsc.active, cpu.x[0] & 0xFFFFFFFF))
    return cases


def run_rxr_without_rxd(work, fails):
    """A contradictory RXR-without-RXD status is not byte progress."""
    img = work / "touch.img"
    bsc, g, mcu = make_bus(rxr_without_rxd=True)
    cpu, out, steps = run(img, bsc)
    cases = 0

    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("RXR without RXD: %s: %s" % (name, detail))

    check("bounded timeout remained live", "code at $5D = -4" in out,
          "the inconsistent threshold did not reach #I2C_TIMEOUT")
    check("no nonexistent byte was consumed", bsc.fifo_reads == 0,
          "%d empty FIFO read(s)" % bsc.fifo_reads)
    check("execution stayed bounded", steps < STEP_LIMIT,
          "%d instructions reached the interpreter ceiling" % steps)
    return cases


def run_v1(probe_rel, work, fails):
    """The same image against a v1 board: a GT911 at $14, nothing at $5D.

    WHAT THIS PROVES THAT THE MAIN RUN CANNOT. The driver asks $5D
    first, so on this bus its first identity read is a NACK and the
    SECOND address is what answers - the fallback path, which nothing
    else in this gate touches. And the GT911's config block says 1280 x
    800 with five contacts, so a driver that had quietly kept the bench
    panel's numbers as defaults would report the wrong resolution and
    the wrong contact count here while passing every check in the main
    run.
    """
    img = work / "touch.img"
    bsc, g, mcu = make_bus_v1()
    cpu, out, steps = run(img, bsc)
    cases = 0

    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("v1: %s: %s" % (name, detail))

    check("the fallback address was reached", "address = 20" in out,
          "the driver did not find the GT911 at $14 after $5D refused. "
          "The second address is the one that gets forgotten, and a v1 "
          "board would read as a dead bus; the line was %r"
          % next((l for l in out.splitlines() if "address" in l), ""))
    check("its own product id came back", "product id = 911" in out,
          "the id string was not 911; the line was %r"
          % next((l for l in out.splitlines() if "product id" in l), ""))
    check("its own x range was read, not the other panel's",
          "x range = 1280" in out,
          "this part's config block declares 1280 across and the probe "
          "printed %r - a driver carrying a default would say 800"
          % next((l for l in out.splitlines() if "x range" in l), ""))
    check("its own y range was read", "y range = 800" in out,
          "the line was %r"
          % next((l for l in out.splitlines() if "y range" in l), ""))
    check("its own contact count was read", "contact slots = 5" in out,
          "this part declares five contact slots and the probe printed "
          "%r; a hardcoded ten would accept a frame this controller "
          "cannot produce"
          % next((l for l in out.splitlines()
                  if "contact slots" in l), ""))
    # THE COUNT IS NOT DECORATION - it is what a frame is refused
    # against. The script plays a ten-point frame, which a five-slot
    # controller must not be believed about.
    # TWO, AND THE SECOND ONE IS THE WHOLE POINT. On the bench bus this
    # count is 1 - only the frame that claims eleven is impossible. Here
    # the controller declares FIVE slots, so the script's TEN-POINT
    # FRAME becomes impossible too, and a driver that refused against a
    # hardcoded ten would accept it, index five contacts past the end of
    # its arrays and report five fingers nobody put on the glass.
    check("a frame wider than the DECLARED count was refused",
          "frames refused for an impossible count = 2" in out,
          "with five slots declared, both the ten-point frame and the "
          "eleven-claim frame must be refused - two, not one. The line "
          "was %r, and a count of 1 means the refusal is against a "
          "constant rather than against what the part said about itself"
          % next((l for l in out.splitlines()
                  if "impossible" in l), ""))
    check("nothing was read at $5D without a pointer more than once",
          g.reads_without_pointer <= 1,
          "%d pointerless read(s)" % g.reads_without_pointer)
    check("the v1 run left no transfer half-open", not bsc.active,
          "the controller is still ACTIVE at the end of the run")
    return cases


def run_nosr(probe_rel, work, fails):
    """The impatient controller emits STOP before its first TXW hold.

    I2cWriteRead must REFUSE, not read anyway. This is the one path in
    that procedure that a healthy bus never exercises, and it is the path
    whose whole job is to stop a wrong coordinate reaching a caller.
    """
    img = work / "touch.img"
    bsc, g, mcu = make_bus(patience=0)
    cpu, out, steps = run(img, bsc)
    cases = 0

    cases += 1
    if g.reads_without_pointer != 1:
        fails.append(
            "nosr: with the controller finishing before its first TXW, "
            "%d pointerless read(s) went out where only the one "
            "address probe is legitimate. I2cWriteRead must return "
            "#I2C_NOSR and read nothing, or a lost race becomes a wrong "
            "coordinate" % g.reads_without_pointer)
    cases += 1
    if bsc.repeated_starts:
        fails.append(
            "nosr: %d repeated start(s) were issued by a controller that "
            "never offered TXW, so the model and driver disagree about the "
            "phase boundary" % bsc.repeated_starts)
    cases += 1
    if "no Goodix answered" not in out:
        fails.append(
            "nosr: the probe did not report the controller as missing. "
            "It must fail visibly rather than print an identity read out "
            "of a transfer that had no pointer")
    cases += 1
    # The code from $5D specifically, not "the last code" - the last one
    # is always $14's, and $14 is the address we did not expect on this
    # bench. The interesting failure is the one a single last-code would
    # overwrite.
    if "code at $5D = -8" not in out:
        fails.append(
            "nosr: the probe did not print -8 (#I2C_NOSR) for $5D. The "
            "whole point of giving that failure its own number is that it "
            "arrives as a number: %r"
            % next((l for l in out.splitlines()
                    if "code at $5D" in l), ""))
    return cases


def run_timeout(work, fails):
    """Execute the real counter deadline and stopped-counter fallback."""
    d = work / "timeout"
    d.mkdir(parents=True, exist_ok=True)
    src = DRV_I2C.read_text(encoding="utf-8", errors="replace")
    anchor = "#I2C_SPIN_MAX  = 2000000"
    if src.count(anchor) != 1:
        fails.append("timeout: the I2C spin-bound anchor changed; the emitted "
                     "timeout path was not exercised")
        return 1
    timed_i2c = d / "timeout_i2c.pi4"
    timed_i2c.write_text(src, encoding="utf-8")

    probe = PROBE.read_text(encoding="utf-8", errors="replace")
    inc = 'XIncludeFile "RaspberryPi4/Lib/i2c.pi4"'
    if probe.count(inc) != 1:
        fails.append("timeout: the probe's I2C include changed; the timed "
                     "test build was not made")
        return 1
    short_probe = d / "timeout_probe.pi4"
    short_probe.write_text(
        probe.replace(inc, 'XIncludeFile "%s"' %
                      timed_i2c.relative_to(ROOT).as_posix()),
        encoding="utf-8")
    img = d / "timeout.img"
    build(short_probe.relative_to(ROOT).as_posix(), img)
    bsc, g, mcu = make_bus(stall=True)
    cpu, out, steps = run(img, bsc)

    cases = 0
    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("timeout: %s: %s" % (name, detail))

    check("timeout and address NACK remain distinct",
          "code at $5D = -4" in out and "code at $14 = -2" in out,
          "the present-but-stalled $5D path must report #I2C_TIMEOUT and "
          "the absent $14 fallback must report #I2C_NACK")
    check("no read phase begins after a stalled write",
          bsc.repeated_starts == 0,
          "%d repeated start(s) escaped a write phase with no TXW"
          % bsc.repeated_starts)
    check("timeout recovery leaves the controller idle",
          not bsc.active and not bsc.txbuf and not bsc.rxbuf,
          "active=%r, tx=%d, rx=%d after recovery"
          % (bsc.active, len(bsc.txbuf), len(bsc.rxbuf)))
    check("recovery preserves the last requested address",
          bsc.regs[C["BSC_A_OFF"]] == 0x14,
          "A changed to $%02X instead of retaining the final fallback address"
          % bsc.regs[C["BSC_A_OFF"]])

    check("live counter expires before the spin fallback",
          bsc.status_reads < 100000,
          "%d status reads means the 2,000,000-spin fallback, not the "
          "20 ms architectural-counter deadline, ended the wait"
          % bsc.status_reads)

    # The independent fallback is compiled short only in this desk fixture.
    fallback_i2c = d / "fallback_i2c.pi4"
    fallback_i2c.write_text(src.replace(anchor, "#I2C_SPIN_MAX  = 16"),
                            encoding="utf-8")
    fallback_probe = d / "fallback_probe.pi4"
    fallback_probe.write_text(
        probe.replace(inc,
                      'XIncludeFile "%s"' %
                      fallback_i2c.relative_to(ROOT).as_posix()),
        encoding="utf-8")
    fallback_img = d / "fallback.img"
    build(fallback_probe.relative_to(ROOT).as_posix(), fallback_img)
    fb_bsc, fb_g, fb_mcu = make_bus(stall=True)
    fb_cpu, fb_out, fb_steps = run(fallback_img, fb_bsc, counter_hz=0)
    check("zero CNTFRQ uses the finite spin fallback",
          "code at $5D = -4" in fb_out and not fb_bsc.active,
          "the stopped-counter run did not return timeout and idle")
    return cases


def run_abort_resume_probe(work, fails):
    """Execute the no-ST diagnostic against both finite and stuck aborts.

    This is intentionally independent from I2cRecover().  It answers only
    whether C=I2CEN can advance an abort which was queued while the engine was
    disabled, and whether the diagnostic restores C=0 when TA never falls.
    """
    d = work / "abort_resume"
    img = d / "abort_resume.img"
    probe_load = 0x00500000
    probe_bss = 0x00600000
    probe_stack = 0x00800000
    build(ABORT_PROBE.relative_to(ROOT).as_posix(), img,
          bss_addr=probe_bss, load_addr=probe_load, stack_addr=probe_stack)
    symbols = image_symbols(img)

    required = [
        "probe_done", "probe_status", "probe_before_c", "probe_before_s",
        "probe_after_c", "probe_after_s", "probe_hz",
        "probe_elapsed_ticks", "probe_polls",
    ]
    for name in required:
        if ("global_" + name).lower() not in symbols:
            fails.append("abort-resume: emitted symbol missing: global_%s"
                         % name)
            return 1

    cases = 0

    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("abort-resume: %s: %s" % (name, detail))

    def queued_abort(never=False):
        bsc = Bsc(base=C["BSC0_BASE"], abort_delay=3, abort_never=never)
        bsc.active = True
        bsc.ta = True
        bsc.abort_pending = 3
        bsc.regs[C["BSC_C_OFF"]] = 0
        return bsc

    # Negative control for the old fixture: MMIO status reads are observations,
    # not clocks.  A disabled engine must retain its queued abort and TA.
    finite = queued_abort()
    for _ in range(5):
        finite.read32(C["BSC_S_OFF"])
    check("disabled status reads cannot advance a queued abort",
          finite.abort_pending == 3 and finite.ta and
          finite.abort_completions == 0,
          "disabled observations left pending=%d TA=%r completions=%d"
          % (finite.abort_pending, finite.ta, finite.abort_completions))
    finite.register_writes = []

    cpu, out, steps = run(img, finite, load_addr=probe_load,
                          stack_addr=probe_stack)
    value = lambda name: memory_u64(cpu, symbols, name)
    check("finite queued abort probe returned", cpu.x[0] == 0,
          "Main returned %d" % cpu.x[0])
    check("probe sampled the disabled active entry state",
          value("probe_before_c") == 0 and
          value("probe_before_s") & C["BSC_S_TA"],
          "before C=$%X S=$%X"
          % (value("probe_before_c"), value("probe_before_s")))
    check("I2CEN without ST let the queued abort quiesce",
          signed_u64(value("probe_status")) == 1 and
          finite.abort_completions == 1 and not finite.ta,
          "status=%d completions=%d TA=%r"
          % (signed_u64(value("probe_status")),
             finite.abort_completions, finite.ta))
    check("successful probe issued only the no-ST enable",
          finite.register_writes == [(C["BSC_C_OFF"], C["BSC_C_I2CEN"])],
          "register writes were %r" % (finite.register_writes,))
    check("successful probe did not create an I2C transaction",
          finite.starts == 0 and finite.repeated_starts == 0 and
          not finite.unknown_writes,
          "starts=%d repeated=%d unknown=%r"
          % (finite.starts, finite.repeated_starts,
             finite.unknown_writes))
    check("successful probe published bounded evidence",
          value("probe_done") == 0x49324152 and
          value("probe_hz") == CNTFRQ and
          value("probe_polls") > 0 and
          value("probe_elapsed_ticks") < CNTFRQ // 50,
          "done=$%X hz=%d polls=%d elapsed=%d ticks steps=%d"
          % (value("probe_done"), value("probe_hz"),
             value("probe_polls"), value("probe_elapsed_ticks"), steps))

    stuck = queued_abort(never=True)
    stuck_cpu, stuck_out, stuck_steps = run(
        img, stuck, load_addr=probe_load, stack_addr=probe_stack)
    stuck_value = lambda name: memory_u64(stuck_cpu, symbols, name)
    check("permanently active probe returned", stuck_cpu.x[0] == 0,
          "Main returned %d" % stuck_cpu.x[0])
    check("permanently active TA expired fail-closed",
          signed_u64(stuck_value("probe_status")) == -1 and stuck.ta and
          stuck.abort_completions == 0,
          "status=%d TA=%r completions=%d"
          % (signed_u64(stuck_value("probe_status")), stuck.ta,
             stuck.abort_completions))
    check("failed probe restored C=0 after one no-ST enable",
          stuck.register_writes == [
              (C["BSC_C_OFF"], C["BSC_C_I2CEN"]),
              (C["BSC_C_OFF"], 0),
          ] and stuck_value("probe_after_c") == 0,
          "writes=%r after C=$%X"
          % (stuck.register_writes, stuck_value("probe_after_c")))
    check("failed probe did not create an I2C transaction",
          stuck.starts == 0 and stuck.repeated_starts == 0 and
          not stuck.unknown_writes,
          "starts=%d repeated=%d unknown=%r"
          % (stuck.starts, stuck.repeated_starts, stuck.unknown_writes))
    check("failed probe used architectural deadline before spin fallback",
          stuck_value("probe_hz") == CNTFRQ and
          stuck_value("probe_polls") < 200000 and
          stuck_value("probe_elapsed_ticks") >= CNTFRQ // 50 and
          stuck_value("probe_elapsed_ticks") < CNTFRQ // 40,
          "hz=%d polls=%d elapsed=%d ticks steps=%d"
          % (stuck_value("probe_hz"), stuck_value("probe_polls"),
             stuck_value("probe_elapsed_ticks"), stuck_steps))

    # The diagnostic is valid only for the exact state observed after build 24:
    # C=0 with TA=1.  It must remain read-only for both an unexpectedly enabled
    # active controller and an already-idle disabled controller.
    enabled = queued_abort(never=True)
    enabled.regs[C["BSC_C_OFF"]] = C["BSC_C_I2CEN"]
    enabled_cpu, enabled_out, enabled_steps = run(
        img, enabled, load_addr=probe_load, stack_addr=probe_stack)
    enabled_value = lambda name: memory_u64(enabled_cpu, symbols, name)
    check("enabled active precondition is refused without writes",
          signed_u64(enabled_value("probe_status")) == -2 and
          enabled.register_writes == [] and
          enabled_value("probe_before_c") == C["BSC_C_I2CEN"] and
          enabled_value("probe_before_s") & C["BSC_S_TA"] and
          enabled_value("probe_after_c") == C["BSC_C_I2CEN"] and
          enabled_value("probe_after_s") & C["BSC_S_TA"],
          "status=%d writes=%r before=$%X/$%X after=$%X/$%X steps=%d"
          % (signed_u64(enabled_value("probe_status")),
             enabled.register_writes, enabled_value("probe_before_c"),
             enabled_value("probe_before_s"),
             enabled_value("probe_after_c"),
             enabled_value("probe_after_s"), enabled_steps))

    idle = Bsc(base=C["BSC0_BASE"])
    idle_cpu, idle_out, idle_steps = run(
        img, idle, load_addr=probe_load, stack_addr=probe_stack)
    idle_value = lambda name: memory_u64(idle_cpu, symbols, name)
    check("already-idle precondition is refused without writes",
          signed_u64(idle_value("probe_status")) == -2 and
          idle.register_writes == [] and
          idle_value("probe_before_c") == 0 and
          not (idle_value("probe_before_s") & C["BSC_S_TA"]) and
          idle_value("probe_after_c") == 0 and
          not (idle_value("probe_after_s") & C["BSC_S_TA"]),
          "status=%d writes=%r before=$%X/$%X after=$%X/$%X steps=%d"
          % (signed_u64(idle_value("probe_status")), idle.register_writes,
             idle_value("probe_before_c"), idle_value("probe_before_s"),
             idle_value("probe_after_c"), idle_value("probe_after_s"),
             idle_steps))
    return cases


def run_delayed_abort_recovery(i2c_path, work, fails):
    """A failed combined transfer must not poison the next ordinary one.

    The BSC fixture keeps TA asserted after disabled CLEAR: status reads alone
    cannot advance the queued abort.  C=I2CEN without ST must run it for three
    observations, after which the production path clears residual FIFO data
    and sticky status while idle.  Only then may a normal MCU write/read run.
    """
    d = work / "delayed_abort"
    d.mkdir(parents=True, exist_ok=True)
    src = pathlib.Path(i2c_path).read_text(encoding="utf-8", errors="replace")
    anchor = "#I2C_SPIN_MAX  = 2000000"
    if src.count(anchor) != 1 and not re.search(
            r"^#I2C_SPIN_MAX\s*=\s*64$", src, re.M):
        fails.append("delayed-abort: the I2C spin-bound anchor changed; the "
                     "emitted recovery path was not exercised")
        return 1
    short_i2c = d / "recovery_i2c.pi4"
    short_i2c.write_text(src, encoding="utf-8")

    probe = d / "recovery_probe.pi4"
    probe.write_text(
        'XIncludeFile "RaspberryPi4/Lib/timer.pi4"\n'
        'XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"\n'
        'XIncludeFile "RaspberryPi4/Lib/gpio.pi4"\n'
        'XIncludeFile "%s"\n'
        'Global Dim wr.a[2]\n'
        'Global Dim rd.a[6]\n'
        'Procedure.i Main()\n'
        '  I2cUp()\n'
        '  wr[0] = $81 : wr[1] = $40\n'
        '  If I2cWriteRead($5D, @wr[0], 2, @rd[0], 6) <> #I2C_TIMEOUT\n'
        '    ProcedureReturn 11\n'
        '  EndIf\n'
        '  wr[0] = $AB : wr[1] = $55\n'
        '  If I2cWrite($45, @wr[0], 2) <> #I2C_OK\n'
        '    ProcedureReturn 12\n'
        '  EndIf\n'
        '  If I2cRead($45, @rd[0], 1) <> #I2C_OK\n'
        '    ProcedureReturn 13\n'
        '  EndIf\n'
        '  ProcedureReturn 0\n'
        'EndProcedure\n'
        % short_i2c.relative_to(ROOT).as_posix(),
        encoding="utf-8")

    img = d / "recovery.img"
    build(probe.relative_to(ROOT).as_posix(), img)
    bsc, g, mcu = make_bus()
    bsc.stall_writes = 1
    bsc.abort_delay = 3
    bsc.abort_residue = bytes([0xA5])
    cpu, out, steps = run(img, bsc)

    cases = 0
    def check(name, ok, detail):
        nonlocal cases
        cases += 1
        if not ok:
            fails.append("delayed-abort: %s: %s" % (name, detail))

    check("emitted probe returned success", cpu.x[0] == 0,
          "Main returned %d; 11=missing timeout, 12=next write failed, "
          "13=next read failed" % cpu.x[0])
    check("the delayed abort actually completed",
          bsc.abort_completions == 1,
          "%d delayed abort completion(s) were observed"
          % bsc.abort_completions)
    recovery_seq = [
        (C["BSC_C_OFF"], C["BSC_C_CLEAR"]),
        (C["BSC_C_OFF"], C["BSC_C_I2CEN"]),
        (C["BSC_C_OFF"], C["BSC_C_I2CEN"] | C["BSC_C_CLEAR"]),
        (C["BSC_S_OFF"], C["BSC_S_DONE"] | C["BSC_S_ERR"] |
         C["BSC_S_CLKT"]),
        (C["BSC_C_OFF"], C["BSC_C_I2CEN"]),
    ]
    check("recovery enables without ST then clears FIFO/status while idle",
          any(bsc.register_writes[i:i + len(recovery_seq)] == recovery_seq
              for i in range(len(bsc.register_writes) -
                             len(recovery_seq) + 1)),
          "required recovery subsequence missing from %r"
          % (bsc.register_writes,))
    check("the next ordinary MCU write completed exactly once",
          mcu.writes == [(0xAB, 0x55)],
          "MCU writes were %r" % (mcu.writes,))
    check("the next ordinary MCU read completed", mcu.reads == 1,
          "MCU reads=%d" % mcu.reads)
    check("no stale status or active transfer remained",
          not bsc.active and not bsc.done and not bsc.abort_pending,
          "active=%r DONE=%r abort_pending=%d"
          % (bsc.active, bsc.done, bsc.abort_pending))

    # A permanently asserted TA is not recoverable by software. The driver
    # must keep I2CEN off and refuse the next transaction; blindly issuing a
    # new START would make a bus fault look like an MCU failure.
    stuck, stuck_g, stuck_mcu = make_bus()
    stuck.stall_writes = 1
    stuck.abort_delay = 3
    stuck.abort_never = True
    stuck_cpu, stuck_out, stuck_steps = run(img, stuck)
    check("a permanently active abort refuses the next ordinary transfer",
          stuck_cpu.x[0] == 12,
          "Main returned %d instead of the next-write failure code 12"
          % stuck_cpu.x[0])
    check("no new START was issued over permanently active TA",
          stuck.starts == 1 and not stuck_mcu.writes,
          "starts=%d MCU writes=%r" % (stuck.starts, stuck_mcu.writes))
    check("the unrecovered controller remains disabled",
          (stuck.regs[C["BSC_C_OFF"]] & C["BSC_C_I2CEN"]) == 0,
          "C=$%08X still advertises I2CEN" % stuck.regs[C["BSC_C_OFF"]])
    return cases


def run_progress_deadline(work, fails):
    """A multi-byte transfer may exceed one window if bytes keep moving."""
    d = work / "progress_deadline"
    d.mkdir(parents=True, exist_ok=True)
    probe = d / "progress_probe.pi4"
    probe.write_text(
        'XIncludeFile "RaspberryPi4/Lib/timer.pi4"\n'
        'XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"\n'
        'XIncludeFile "RaspberryPi4/Lib/gpio.pi4"\n'
        'XIncludeFile "RaspberryPi4/Lib/i2c.pi4"\n'
        'Global Dim wr.a[2]\n'
        'Global Dim rd.a[6]\n'
        'Procedure.i Main()\n'
        '  I2cUp()\n'
        '  wr[0] = $81 : wr[1] = $40\n'
        '  ProcedureReturn I2cWriteRead($5D, @wr[0], 2, @rd[0], 6)\n'
        'EndProcedure\n', encoding="utf-8")
    img = d / "progress.img"
    build(probe.relative_to(ROOT).as_posix(), img)
    bsc, g, mcu = make_bus()
    bsc.tx_gap_reads = 120
    cpu, out, steps = run(img, bsc)
    elapsed_us = steps * TICKS_PER_STEP * 1_000_000 // CNTFRQ
    cases = 0
    cases += 1
    if cpu.x[0] != C["I2C_OK"]:
        fails.append("progress-deadline: the slow two-byte TXW refill "
                     "returned %d instead of success" % cpu.x[0])
    cases += 1
    if elapsed_us <= 20000:
        fails.append("progress-deadline: fixture took only %d us, so it did "
                     "not prove a transfer can outlive one 20 ms window"
                     % elapsed_us)
    cases += 1
    if bsc.repeated_starts != 1 or g.reads != [(0x8140, 6)]:
        fails.append("progress-deadline: repeated-start read was not intact: "
                     "Sr=%d reads=%r" % (bsc.repeated_starts, g.reads))
    return cases


# =====================================================================
#  THE NEGATIVE CONTROL - a gate nobody has seen go red is a gate nobody
#  should believe. Every edit below is a plausible mistake, several of
#  them are mistakes this project has actually made, and each MUST turn
#  this gate red.
# =====================================================================

MUTATIONS = [
    # --- touch_goodix.pi4 -------------------------------------------
    ("touch", "the register pointer goes out low byte first",
     "  hdr[0] = hdr0\n  hdr[1] = hdr1",
     "  hdr[0] = hdr1\n  hdr[1] = hdr0"),

    ("touch", "the buffer flag is never released after a frame",
     "  ; ALWAYS clear on a frame that was seen, including the zero-touch frame.\n  Gt9WriteReg(#GT9_REG_COOR, 0)\n  ProcedureReturn gt9_count",
     "  ProcedureReturn gt9_count"),

    ("touch", "the pointer write and the read become two transactions",
     "  r = I2cWriteRead(gt9_addr, @hdr, 2, @gt9_buf, n)",
     "  r = I2cWrite(gt9_addr, @hdr, 2)\n  If r = #I2C_OK\n    r = I2cRead(gt9_addr, @gt9_buf, n)\n  EndIf"),

    ("touch", "the coordinates are assembled big-endian",
     "      gt9_x[i] = (gt9_buf[base + 1] & $FF) | ((gt9_buf[base + 2] & $FF) << 8)",
     "      gt9_x[i] = ((gt9_buf[base + 1] & $FF) << 8) | (gt9_buf[base + 2] & $FF)"),

    ("touch", "a frame wider than the part can produce is believed",
     "  If n > gt9_maxpts",
     "  If n > 15"),

    ("touch", "the count is refused against a constant, not what the part said",
     "  If n > gt9_maxpts",
     "  If n > #GT9_MAX_POINTS"),

    ("touch", "the contact stride is seven bytes",
     "#GT9_CONTACT_SIZE = 8",
     "#GT9_CONTACT_SIZE = 7"),

    ("touch", "the identity read stops at four bytes and loses the version",
     "  If Gt9ReadReg(#GT9_REG_ID, 6) = 0",
     "  If Gt9ReadReg(#GT9_REG_ID, 4) = 0"),

    ("touch", "the flag is cleared even when no frame was ready",
     "  If (st & #GT9_STATUS_READY) = 0\n    ProcedureReturn #GT9_ENOTREADY\n  EndIf",
     "  If (st & #GT9_STATUS_READY) = 0\n    Gt9WriteReg(#GT9_REG_COOR, 0)\n    ProcedureReturn #GT9_ENOTREADY\n  EndIf"),

    ("touch", "the config resolution is assembled big-endian",
     "  gt9_xmax = (gt9_buf[#GT9_CFG_RES] & $FF) | ((gt9_buf[#GT9_CFG_RES + 1] & $FF) << 8)",
     "  gt9_xmax = ((gt9_buf[#GT9_CFG_RES] & $FF) << 8) | (gt9_buf[#GT9_CFG_RES + 1] & $FF)"),

    ("touch", "the resolution is read one byte late",
     "#GT9_CFG_RES      = 1",
     "#GT9_CFG_RES      = 2"),

    ("touch", "the config block is read as one byte, so no resolution is learned",
     "  If Gt9ReadReg(#GT9_REG_CONFIG, #GT9_CFG_HEAD) = 0",
     "  If Gt9ReadReg(#GT9_REG_CONFIG, 1) = 0"),

    ("touch", "the contact count is read from the trigger byte",
     "#GT9_CFG_CONTACTS = 5",
     "#GT9_CFG_CONTACTS = 6"),

    ("touch", "the contacts are read from the status byte rather than after it",
     "    If Gt9ReadReg(#GT9_REG_COOR + 1, n * #GT9_CONTACT_SIZE) = 0",
     "    If Gt9ReadReg(#GT9_REG_COOR, n * #GT9_CONTACT_SIZE) = 0"),

    # --- dsi_panel.pi4 -----------------------------------------------
    ("panel", "the backlight value is not inverted",
     "  If DsiPanelWrite(#DSI_PANEL_REG_BL_LEVEL, #DSI_PANEL_BL_MAX - level) = 0",
     "  If DsiPanelWrite(#DSI_PANEL_REG_BL_LEVEL, level) = 0"),

    ("panel", "the backlight level is never committed",
     "  If DsiPanelWrite(#DSI_PANEL_REG_BL_COMMIT, 1) = 0\n    ProcedureReturn 0\n  EndIf",
     "  "),

    ("panel", "the opening sequence loses its middle register",
     "  If DsiPanelWrite(#DSI_PANEL_REG_OPEN_B, 1) = 0\n    ProcedureReturn 0\n  EndIf",
     "  "),

    ("panel", "the opening sequence goes out in the wrong order",
     "  If DsiPanelWrite(#DSI_PANEL_REG_OPEN_A, 1) = 0\n    ProcedureReturn 0\n  EndIf\n  If DsiPanelWrite(#DSI_PANEL_REG_OPEN_B, 1) = 0",
     "  If DsiPanelWrite(#DSI_PANEL_REG_OPEN_B, 1) = 0\n    ProcedureReturn 0\n  EndIf\n  If DsiPanelWrite(#DSI_PANEL_REG_OPEN_A, 1) = 0"),

    # --- i2c.pi4, the new procedure ----------------------------------
    # WITHDRAWN, and the reason is worth more than the mutation was.
    # "the repeated start also sets CLEAR" was in this list and it stayed
    # GREEN. That is not a hole in the gate: it is not a defect. BCM2711
    # ARM Peripherals, Table 26, bits 5:4 - "If CLEAR and ST are both set
    # in the same operation, the FIFO is cleared before the new frame is
    # started." For a read there is nothing in the FIFO to lose, so the
    # extra bit is harmless. It is left out of the driver anyway, because
    # the manual's recipe does not have it and a step nobody can justify
    # is a step nobody can review - but it is NOT graded, because grading
    # something that is not wrong teaches the next reader a false rule.

    ("i2c", "the repeated start forgets to ask for a read",
     "  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)",
     "  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST)"),

    ("i2c", "the repeated-start write preloads the FIFO before ST",
     "  I2cWr(#BSC_DLEN_OFF, wn & $FFFF)\n  i = 0\n  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST)",
     "  I2cWr(#BSC_DLEN_OFF, wn & $FFFF)\n  i = 0\n  While i < wn\n    I2cWr(#BSC_FIFO_OFF, PeekA(*wbuf + i) & $FF)\n    i = i + 1\n  Wend\n  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST)"),

    ("i2c", "the phase switch waits for another status after the final byte",
     "      If i = wn\n        I2cWr(#BSC_DLEN_OFF, rn & $FFFF)",
     "      If i = wn And (I2cRd(#BSC_S_OFF) & #BSC_S_TXW) <> 0\n        I2cWr(#BSC_DLEN_OFF, rn & $FFFF)"),

    # THE ANCHOR HAD GONE STALE AND THE GATE SAID NOTHING - found
    # 2026-09-08. i2c.pi4 grew an I2cRecover() call in this arm at some
    # point; this mutation's anchor did not follow it, so it stopped
    # matching, could not be applied, and was reported as a mutation the
    # gate FAILED TO NOTICE - which is the opposite of what had happened.
    # The reporting half of that is fixed in run_mutations below: an
    # anchor that does not match is now a gate that DID NOT RUN, printed
    # as its own outcome with its reason, and it fails the run.
    ("i2c", "DONE before TXW is ignored instead of refused",
     "    If (s & #BSC_S_DONE) <> 0\n      I2cTraceMilestone(#I2C_TRACE_EDGE_DONE, s)\n      ; The write is over and a STOP went with it. Do NOT begin a plain read.\n      I2cTraceFault(s, #I2C_NOSR)\n      I2cRecover()\n      ProcedureReturn I2cTraceReturn(trace, #I2C_NOSR)\n    EndIf",
     "    If (s & #BSC_S_DONE) <> 0\n      I2cWr(#BSC_S_OFF, #BSC_S_DONE)\n      I2cWr(#BSC_DLEN_OFF, rn & $FFFF)\n      I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)\n      Break\n    EndIf"),

    ("i2c", "the read length is never written to DLEN",
     "        I2cWr(#BSC_DLEN_OFF, rn & $FFFF)\n        I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)",
     "        I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)"),

    ("i2c", "combined receive consumes unqualified turnaround RXD",
     "    If i < rn And (s & #BSC_S_RXR) <> 0",
     "    If i < rn And (s & #BSC_S_RXD) <> 0"),

    ("i2c", "recovery waits for the queued abort with the engine disabled",
     "  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN)\n\n  spin = #I2C_SPIN_MAX",
     "  spin = #I2C_SPIN_MAX"),
]

SRC_OF = {"touch": DRV_TOUCH, "panel": DRV_PANEL, "i2c": DRV_I2C}


def mutate_one(job):
    global PMF_COMPILER
    idx, which, name, old, new, compiler = job
    PMF_COMPILER = pathlib.Path(compiler)
    d = WORK / "mut" / str(idx)
    d.mkdir(parents=True, exist_ok=True)

    # Copy the whole probe's dependency set into the mutant directory by
    # rewriting only the ONE include that names the mutated library, so
    # the other two are still the tree's own files.
    src_path = SRC_OF[which]
    src = src_path.read_text(encoding="utf-8", errors="replace")
    if src.count(old) != 1:
        return (name, None,
                "the anchor text appears %d times in %s, not once - the "
                "mutation could not be applied and proves nothing"
                % (src.count(old), src_path.name))
    mut_src = src.replace(old, new)
    if which == "i2c":
        # A mutation can intentionally strand the BSC in a state whose
        # production backstop is two million emitted loop iterations. The
        # bound is not the behavior being mutated, so shorten it for these
        # desk-only negative controls exactly as run_timeout does.
        spin_anchor = "#I2C_SPIN_MAX  = 2000000"
        if mut_src.count(spin_anchor) != 1:
            return (name, None, "the I2C spin-bound anchor changed; this "
                    "negative control could run without a finite desk bound")
        mut_src = mut_src.replace(spin_anchor, "#I2C_SPIN_MAX  = 64")
    mut = d / ("mut_" + src_path.name)
    mut.write_text(mut_src, encoding="utf-8")

    probe = PROBE.read_text(encoding="utf-8", errors="replace")
    if which == "panel":
        orig_inc = ('XIncludeFile '
                    '"RaspberryPi4/Tests/Fixtures/dsi_panel_v1.pi4"')
    else:
        orig_inc = 'XIncludeFile "RaspberryPi4/Lib/%s"' % src_path.name
    if probe.count(orig_inc) != 1:
        return (name, None,
                "the probe no longer includes %s exactly once, so the "
                "mutant library would not be the one built"
                % src_path.name)
    mut_probe = d / "mut_probe.pi4"
    mut_probe.write_text(
        probe.replace(orig_inc, 'XIncludeFile "%s"'
                      % mut.relative_to(ROOT).as_posix()),
        encoding="utf-8")

    rel = mut_probe.relative_to(ROOT).as_posix()
    fails = []
    try:
        run_clean(rel, d, fails)
        # THE v1 BUS COUNTS AS PART OF THE GATE HERE TOO. Two of the
        # mutations below - refusing a frame against a constant instead
        # of against what the part declared, and reading the contact
        # count from the wrong byte - are invisible on the bench bus,
        # where the declared count and the constant happen to be the
        # same ten. A negative control that only ran the bench bus would
        # report those two GREEN and teach the next reader that they are
        # safe.
        if not fails:
            run_v1(rel, d, fails)
        if not fails:
            run_nosr(rel, d, fails)
        if not fails and which == "i2c":
            run_turnaround_rxd(rel, d, fails)
        if not fails and which == "i2c":
            run_delayed_abort_recovery(mut, d, fails)
    except (SystemExit, AssertionError, KeyError, IndexError,
            ValueError, ZeroDivisionError) as e:
        return (name, True, "the run refused it: %s"
                % str(e).splitlines()[0][:90])
    return (name, bool(fails), fails[0].splitlines()[0][:90] if fails else "")


def run_mutations():
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(i, w, n, o, x, str(PMF_COMPILER))
            for i, (w, n, o, x) in enumerate(MUTATIONS)]
    workers = max(1, min(len(jobs), (os.cpu_count() or 4) - 2))
    print("negative control: %d mutations across %d workers"
          % (len(jobs), workers))
    bad = 0
    stale = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for name, red, note in pool.map(mutate_one, jobs):
            if red is None:
                # NOT APPLIED, WHICH IS A THIRD OUTCOME AND NOT A GREEN.
                # An anchor that no longer matches its file is a check
                # that did not run, and printing it as "the gate did not
                # notice" sends the next reader to look for a hole in
                # the gate instead of at a stale three lines of text.
                # It failed silently for an unknown number of runs
                # before 2026-09-08 because the reason was only printed
                # on the other branch.
                stale += 1
                print("  STALE %s  <-- THIS MUTATION DID NOT RUN" % name)
                print("        %s" % note)
            elif red:
                print("  RED   %s" % name)
                if note:
                    print("        %s" % note)
            else:
                bad += 1
                print("  GREEN %s  <-- THE GATE DID NOT NOTICE" % name)
    if bad or stale:
        print("\ntouch_emitted_check --mutate: FAIL - %d mutation(s) passed a "
              "gate that should have refused them, %d could not be applied "
              "at all" % (bad, stale))
        return 1
    print("\ntouch_emitted_check --mutate: PASS - every mutation went red")
    return 0


def main():
    global PMF_COMPILER
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--compiler", default=os.environ.get("PMF_COMPILER"),
        help="path to the external PureMetal compiler (or set PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="run the negative control (all cores)")
    ap.add_argument(
        "--abort-resume-only", action="store_true",
        help="run only the emitted C=I2CEN/no-ST abort diagnostic gate")
    ap.add_argument(
        "--model-only", action="store_true",
        help="run only the BSC receive-state self-checks (no compiler)")
    args = ap.parse_args()

    fails = []
    model_cases = run_bsc_receive_model_checks(fails)
    if args.model_only:
        if fails:
            print("touch_emitted_check --model-only: FAIL - %d" % len(fails))
            for f in fails:
                print("  * %s" % f)
            return 1
        print("touch_emitted_check --model-only: PASS - %d cases" % model_cases)
        print("           DLEN/DONE/RXR/RXF advance independently of FIFO reads.")
        return 0

    if args.compiler:
        PMF_COMPILER = pathlib.Path(args.compiler).expanduser().resolve()
    else:
        PMF_COMPILER = ROOT / "PureMetalForge.exe"
    if not PMF_COMPILER.is_file():
        raise SystemExit(
            "touch emitted gate: compiler not found; pass --compiler or set PMF_COMPILER")

    WORK.mkdir(parents=True, exist_ok=True)
    if args.abort_resume_only:
        cases = model_cases + run_abort_resume_probe(WORK, fails)
        if fails:
            print("touch_emitted_check --abort-resume-only: FAIL - %d"
                  % len(fails))
            for f in fails:
                print("  * %s" % f)
            return 1
        print("touch_emitted_check --abort-resume-only: PASS - %d cases"
              % cases)
        print("           emitted no-ST enable quiesced a finite queued abort;")
        print("           permanently active TA expired and restored C=0.")
        return 0

    rel = PROBE.relative_to(ROOT).as_posix()
    cases, out, steps = run_clean(rel, WORK, fails)
    cases += model_cases
    cases += run_turnaround_rxd(rel, WORK, fails)
    cases += run_rxr_without_rxd(WORK, fails)
    cases += run_v1(rel, WORK, fails)
    cases += run_nosr(rel, WORK, fails)
    cases += run_timeout(WORK, fails)
    cases += run_abort_resume_probe(WORK, fails)
    cases += run_delayed_abort_recovery(DRV_I2C, WORK, fails)
    cases += run_progress_deadline(WORK, fails)

    if fails:
        print("touch_emitted_check: FAIL - %d" % len(fails))
        for f in fails:
            print("  * %s" % f)
        print("\n--- the probe said ---")
        print(out)
        return 1

    print("touch_emitted_check: PASS - %d cases, %d model instructions"
          % (cases, steps))
    print("           the repeated start is OBSERVED on the wire, not "
          "assumed:")
    print("           a modelled GT911 that forgets its pointer on a STOP")
    print("           served every read from a live pointer.")
    print()
    print("WHAT IS NOT COVERED: no real controller, no real panel, no real")
    print("MCU. The 'a STOP loses the pointer' rule is stricter than any")
    print("document on this machine. The SCREEN MAPPING is not here at")
    print("all - it lives in the display layer now and is graded by")
    print("a64_dsiscreen_check. The functional touch fixture uses the")
    print("header bus; the independent abort-resume fixture selects BSC0")
    print("but addresses no device. No model run is physical touch proof.")

    if args.mutate:
        return run_mutations()
    return 0


if __name__ == "__main__":
    sys.exit(main())
