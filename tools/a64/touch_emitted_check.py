#!/usr/bin/env python3
"""touch_emitted_check.py - the Goodix touch driver, the Waveshare panel MCU,
and the repeated-start transfer they both needed, executed against a model
of the bus.

      python tools/a64/touch_emitted_check.py --pmfc C:/path/to/pmfc.exe
      python tools/a64/touch_emitted_check.py --pmfc C:/path/to/pmfc.exe --mutate

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

  I2cWriteRead() is new. It is a mid-transaction poke at a controller -
  start a write, wait for ACTIVE, re-aim DLEN and set READ|ST - and that
  is the exact shape of the repeated-start bug this project has already
  paid for twice on the RP2040 and RP2350. Nothing in the tree could
  observe whether a STOP came out in the middle, because no model of this
  controller existed.

  Now one does, and THE GT911 MODEL FORGETS ITS REGISTER POINTER ON A
  STOP. So a driver that writes the pointer, stops, and then reads gets
  0xFF back and fails visibly, instead of getting plausible bytes from
  somewhere else in the register map. Mutation 3 is exactly that mistake
  and it must go red.

WHAT IT CANNOT PROVE, AND THE LIST IS SHORT AND IMPORTANT

  * Nothing here has touched a real controller, a real MCU or a real
    panel. Every number came out of a Linux driver, and a Linux driver
    is evidence about a register map, not about this silicon.
  * The model's "a STOP loses the pointer" rule is STRICTER THAN THE
    DATASHEET, because there is no Goodix datasheet on this machine and
    the claim comes from the comments in two drivers. Being stricter is
    the right direction for a gate - it forbids a pattern nobody has
    shown to be safe - but it means a green run here does NOT prove a
    real GT911 would have failed the two-transaction path.
  * The TA race that I2cWriteRead returns #I2C_NOSR for is EXERCISED here
    by a deliberately impatient controller variant, which proves the code
    path. It does not predict whether real silicon ever loses that race.
  * The axis transform is graded against the numbers in a device-tree
    overlay. If the overlay is wrong about this panel, this gate is wrong
    with it, in the same direction, and only a finger will say so.
  * The bus is BSC1 on GPIO 2/3. The panel is on BSC0 at GPIO 44/45.
    Nothing here models BSC0, because nothing in the tree drives it yet.
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

PMFC = None
PROBE = ROOT / "RaspberryPi4" / "Tests" / "touch_goodix_compile.pi4"
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

# One millisecond of virtual time per interpreter step. The probe spends
# about six seconds inside delay(); at this rate that is six thousand
# steps of spinning instead of three hundred million.
CNTFRQ = 54_000_000
TICKS_PER_STEP = CNTFRQ // 1000


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
    "BSC1_BASE", "BSC_C_OFF", "BSC_S_OFF", "BSC_DLEN_OFF", "BSC_A_OFF",
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

    THE STOP IS THE INTERESTING PART. A write transaction does not finish
    the instant its bytes are gone: the controller stays ACTIVE, and only
    emits a STOP once nobody has re-armed it. `patience` is how many reads
    of the status register that takes. Set it to 0 and the controller
    finishes before it ever reports ACTIVE, which is the race
    I2cWriteRead returns #I2C_NOSR for.
    """

    def __init__(self, base=BSC_BASE, patience=2):
        self.base = base
        self.patience = patience
        self.devices = {}
        self.regs = {C["BSC_C_OFF"]: 0, C["BSC_S_OFF"]: 0,
                     C["BSC_DLEN_OFF"]: 0, C["BSC_A_OFF"]: 0,
                     C["BSC_DIV_OFF"]: 0x5DC, C["BSC_DEL_OFF"]: 0,
                     C["BSC_CLKT_OFF"]: 0x40}
        self.txbuf = bytearray()
        self.rxbuf = bytearray()
        self.active = False
        self.is_read = False
        self.err = False
        self.clkt = False
        self.done = False
        self.ta = False
        self.write_left = 0
        self.polls = 0
        self.cur = None

        # Everything worth grading that is not a register.
        self.starts = 0
        self.repeated_starts = 0
        self.stops = 0
        self.nacks = 0
        self.unknown_reads = []
        self.unknown_writes = []

    def add(self, dev):
        self.devices[dev.addr] = dev

    def contains(self, addr):
        return self.base <= addr < self.base + BSC_SIZE

    # ---- transaction machinery -------------------------------------
    def _emit_stop(self):
        if self.cur is not None:
            self.cur.stop()
        self.stops += 1
        self.active = False
        self.ta = False
        self.done = True
        self.cur = None

    def _begin(self, is_read, repeated):
        addr = self.regs[C["BSC_A_OFF"]] & 0x7F
        dlen = self.regs[C["BSC_DLEN_OFF"]] & 0xFFFF
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

        self.active = True
        self.ta = True
        self.done = False
        self.polls = 0
        self.is_read = is_read
        if is_read:
            self.rxbuf = bytearray(self.cur.read(dlen))
            self.write_left = 0
        else:
            self.write_left = dlen
            self._drain_tx()

    def _drain_tx(self):
        if self.write_left > 0 and len(self.txbuf) >= self.write_left:
            data = bytes(self.txbuf[:self.write_left])
            del self.txbuf[:self.write_left]
            self.write_left = 0
            if not self.cur.write(data):
                self.nacks += 1
                self.err = True
                self.done = True
                self.active = False
                self.ta = False
                self.cur = None

    # ---- the register window ---------------------------------------
    def read32(self, off):
        if off == C["BSC_S_OFF"]:
            if self.active and not self.is_read and self.write_left == 0:
                self.polls += 1
                if self.polls > self.patience:
                    self._emit_stop()
            elif self.active and self.is_read and not self.rxbuf:
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
            if self.active and not self.is_read and self.write_left > 0:
                s |= C["BSC_S_TXD"]
            if not self.txbuf:
                s |= C["BSC_S_TXE"]
            return s
        if off == C["BSC_FIFO_OFF"]:
            if self.rxbuf:
                return self.rxbuf.pop(0)
            return 0
        if off in self.regs:
            return self.regs[off]
        self.unknown_reads.append(off)
        return 0

    def write32(self, off, val):
        val &= 0xFFFFFFFF
        if off == C["BSC_S_OFF"]:
            if val & C["BSC_S_ERR"]:
                self.err = False
            if val & C["BSC_S_CLKT"]:
                self.clkt = False
            if val & C["BSC_S_DONE"]:
                self.done = False
            return
        if off == C["BSC_FIFO_OFF"]:
            self.txbuf.append(val & 0xFF)
            if self.active and not self.is_read:
                self._drain_tx()
            return
        if off == C["BSC_C_OFF"]:
            self.regs[off] = val
            if val & C["BSC_C_CLEAR"]:
                self.txbuf = bytearray()
                self.rxbuf = bytearray()
            if val & C["BSC_C_ST"]:
                self._begin(bool(val & C["BSC_C_READ"]), self.active)
            return
        if off in self.regs:
            self.regs[off] = val
            return
        self.unknown_writes.append((off, val))


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

def build(probe_rel, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PMFC), probe_rel, "-t", G["flag"],
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    r = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img, bsc):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    console = bytearray()
    install(cpu, bsc, console)

    steps = [0]
    plain_step = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:          # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
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


def make_bus(patience=2, goodix_kwargs=None):
    """The bench bus: a GT9271 at $5D, which is what the v2 overlay's
    goodix@5d node describes and what is plugged into this board."""
    bsc = Bsc(patience=patience)
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
    # rotations and every corner by section I of pi4DsiScreenProbe.pi4
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
    """The impatient controller: it emits its STOP before it ever reports
    ACTIVE, so the repeated start cannot be issued.

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
            "nosr: with the controller finishing before it reported "
            "ACTIVE, %d pointerless read(s) went out where only the one "
            "address probe is legitimate. I2cWriteRead must return "
            "#I2C_NOSR and read nothing, or a lost race becomes a wrong "
            "coordinate" % g.reads_without_pointer)
    cases += 1
    if bsc.repeated_starts:
        fails.append(
            "nosr: %d repeated start(s) were issued by a controller that "
            "was never ACTIVE, so the model and the driver disagree about "
            "what step 5 measures" % bsc.repeated_starts)
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

    ("i2c", "the write phase is started before the FIFO is loaded",
     "  I2cWr(#BSC_DLEN_OFF, wn & $FFFF)\n  i = 0\n  While i < wn",
     "  I2cWr(#BSC_DLEN_OFF, wn & $FFFF)\n  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST)\n  i = 0\n  While i < wn"),

    # THE ANCHOR HAD GONE STALE AND THE GATE SAID NOTHING - found
    # 2026-09-08. i2c.pi4 grew an I2cRecover() call in this arm at some
    # point; this mutation's anchor did not follow it, so it stopped
    # matching, could not be applied, and was reported as a mutation the
    # gate FAILED TO NOTICE - which is the opposite of what had happened.
    # The reporting half of that is fixed in run_mutations below: an
    # anchor that does not match is now a gate that DID NOT RUN, printed
    # as its own outcome with its reason, and it fails the run.
    ("i2c", "DONE before TA is read anyway instead of refused",
     "      ; The write is over and a STOP went with it. Do NOT read.\n      I2cWr(#BSC_S_OFF, #BSC_S_DONE)\n      a64_barrier()\n      I2cRecover()\n      ProcedureReturn #I2C_NOSR",
     "      I2cWr(#BSC_S_OFF, #BSC_S_DONE)\n      a64_barrier()\n      started = 1\n      Break"),

    ("i2c", "the read length is never written to DLEN",
     "  I2cWr(#BSC_DLEN_OFF, rn & $FFFF)\n  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)",
     "  I2cWr(#BSC_C_OFF, #BSC_C_I2CEN | #BSC_C_ST | #BSC_C_READ)"),
]

SRC_OF = {"touch": DRV_TOUCH, "panel": DRV_PANEL, "i2c": DRV_I2C}


def mutate_one(job):
    idx, which, name, old, new = job
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
    mut = d / ("mut_" + src_path.name)
    mut.write_text(src.replace(old, new), encoding="utf-8")

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
    except (SystemExit, AssertionError, KeyError, IndexError,
            ValueError, ZeroDivisionError) as e:
        return (name, True, "the run refused it: %s"
                % str(e).splitlines()[0][:90])
    return (name, bool(fails), fails[0].splitlines()[0][:90] if fails else "")


def run_mutations():
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(i, w, n, o, x)
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
    global PMFC
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pmfc", default=os.environ.get("PMFC"),
        help="path to the external PureMetal compiler (or set PMFC)")
    ap.add_argument("--mutate", action="store_true",
                    help="run the negative control (all cores)")
    args = ap.parse_args()

    if args.pmfc:
        PMFC = pathlib.Path(args.pmfc).expanduser().resolve()
    else:
        PMFC = ROOT / "pmfc.exe"
    if not PMFC.is_file():
        raise SystemExit(
            "touch emitted gate: compiler not found; pass --pmfc or set PMFC")

    WORK.mkdir(parents=True, exist_ok=True)
    fails = []
    rel = PROBE.relative_to(ROOT).as_posix()
    cases, out, steps = run_clean(rel, WORK, fails)
    cases += run_v1(rel, WORK, fails)
    cases += run_nosr(rel, WORK, fails)

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
    print("a64_dsiscreen_check. BSC0 on GPIO 44/45 - the bus the panel")
    print("is actually on - is not modelled; this probe deliberately")
    print("stays on the header bus the overlay's i2c1 override describes.")

    if args.mutate:
        return run_mutations()
    return 0


if __name__ == "__main__":
    sys.exit(main())
