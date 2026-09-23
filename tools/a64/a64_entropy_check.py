#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/entropy.pi4 - the BCM2711 RNG200.

    python tools/a64/a64_entropy_check.py --compiler <PureMetalForge.exe>
    python tools/a64/a64_entropy_check.py --compiler <PureMetalForge.exe> --mutate

WHAT THIS GATE CAN AND CANNOT DO, STATED FIRST

THERE IS NO ORACLE FOR A HARDWARE ENTROPY SOURCE.  A random number
generator has no expected output by construction, so nothing here can ever
say "the numbers the block produced were right".  Any report that claims
otherwise is wrong, and the library's own header says the same thing.

WHAT IS CHECKABLE, AND IS CHECKED HERE, IS EVERYTHING AROUND THE NUMBERS:

  1. THE REGISTER MAP IS A QUOTATION.  Every offset and mask in
     entropy.pi4 carries a line-number citation (`; :NNN`) into
     raspberrypi/linux rpi-6.12.y drivers/char/hw_random/iproc-rng200.c.
     That driver is third-party source and is not copied into this tree;
     each cited #define is pinned below with its value AND its line, and
     the gate requires entropy.pi4's value and its cited line to match the
     pin.  A citation nobody checks is decoration.  Every offset is then
     re-checked against the pinned values of the two OTHER drivers
     (mainline Linux v6.12 and U-Boot v2025.01), which come from different
     trees and must agree.

  2. THE COMPOSED WORDS ARE RE-DERIVED.  entropy.pi4 spells the programmed
     values as finished literals, because a constant declaration in that
     language may not contain arithmetic.  This gate rebuilds each one from
     the shift and mask constants and requires the literal to match.

  3. THE BASE ADDRESS AGREES WITH THE DEVICE TREE.  entropy.pi4's literal
     is compared with the rng@ node of the Raspberry Pi device tree
     (raspberrypi/linux rpi-6.12.y, bcm2711.dtsi, pinned), translated
     through the soc ranges property, and the node's declared length is
     checked against the highest register offset.

  4. THE MMIO TRANSCRIPT IS EXACT.  The library is built into a real image
     by PureMetalForge.exe, executed instruction by instruction in
     tools/a64/a64_interp.py, and every load and store inside the RNG200
     aperture is recorded and compared against the sequence the driver
     performs.

  5. THE FIFO IS NEVER READ EMPTY.  The model raises immediately if
     RNG_FIFO_DATA is read while its modelled FIFO count is zero.

  6. THE STUCK DETECTOR IS DRIVEN WITH KNOWN ANSWERS: constant,
     alternating, period 7, period 64 (must be caught), period 65 and a
     32-bit counter (must NOT be caught), all ones, all zeros, and a
     balanced stream.  This is a test of the DETECTOR, not of any hardware.

  7. THE DIAGNOSTIC RaspberryPi4/Examples/Diagnostics/pi4Entropy.pi4 IS
     EXECUTED against a block that answers and a block that never starts.

WHAT IS NOT ASSERTED, AND MUST NOT BE READ INTO A PASS:

  * That any of this runs on silicon.  The RNG200 in this file is a model
    written from the same driver the library was written against, so it
    CANNOT catch a shared misreading of that driver.
  * That the hardware's output is random, unpredictable, unbiased, or
    carries any particular entropy rate.
  * That the spin budgets are long enough for the real block.
"""

from __future__ import annotations
import os

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB = ROOT / "RaspberryPi4" / "Lib" / "entropy.pi4"
COMPILER: str = ""
WORK: pathlib.Path = pathlib.Path(".")   # a temporary directory, set by main()

LOAD = 0x00400000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STACK = 0x03000000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

RNG_LO = 0xFE104000
RNG_HI = 0xFE104027

H_CMD = 0x06000000
H_BUF = 0x06100000
H_OUT = 0x0A000000

STEP_LIMIT = 400_000_000

MASK32 = 0xFFFFFFFF

# The ops the harness understands.  One image, many runs.
OP_BEGIN = 1
OP_RESTART = 2
OP_WARMUP = 3
OP_WORDS = 4
OP_BYTES = 5
OP_STUCK = 6
OP_FULL = 7
OP_STOP = 8

FAILURES: list[str] = []
CHECKS = 0


def check(ok: bool, what: str) -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(what)


# =====================================================================
#  1 + 2 + 3.  THE CITATIONS, OPENED
# =====================================================================
#  The library's constants are parsed out of its own text.  Nothing is
#  copied into this file, so a constant that changes in the library
#  changes here too, and a citation that stops being true fails.
# =====================================================================
# =====================================================================
#  THE PINNED VENDOR FACTS (cited, not copied)
# =====================================================================
#  raspberrypi/linux, branch rpi-6.12.y,
#  drivers/char/hw_random/iproc-rng200.c.   name: (value, line)
RPI_IPROC_RNG200 = {
    "RNG_CTRL_OFFSET": (0x00, 21),
    "RNG_CTRL_RNG_RBGEN_MASK": (0x1FFF, 22),
    "RNG_CTRL_RNG_RBGEN_ENABLE": (0x01, 23),
    "RNG_CTRL_RNG_DIV_CTRL_SHIFT": (13, 24),
    "RNG_SOFT_RESET_OFFSET": (0x04, 26),
    "RNG_SOFT_RESET": (0x01, 27),
    "RBG_SOFT_RESET_OFFSET": (0x08, 29),
    "RBG_SOFT_RESET": (0x01, 30),
    "RNG_TOTAL_BIT_COUNT_OFFSET": (0x0C, 32),
    "RNG_TOTAL_BIT_COUNT_THRESHOLD_OFFSET": (0x10, 34),
    "RNG_INT_STATUS_OFFSET": (0x18, 36),
    "RNG_INT_STATUS_MASTER_FAIL_LOCKOUT_IRQ_MASK": (0x80000000, 37),
    "RNG_INT_STATUS_STARTUP_TRANSITIONS_MET_IRQ_MASK": (0x00020000, 38),
    "RNG_INT_STATUS_NIST_FAIL_IRQ_MASK": (0x20, 39),
    "RNG_INT_STATUS_TOTAL_BITS_COUNT_IRQ_MASK": (0x01, 40),
    "RNG_INT_ENABLE_OFFSET": (0x1C, 42),
    "RNG_FIFO_DATA_OFFSET": (0x20, 44),
    "RNG_FIFO_COUNT_OFFSET": (0x24, 46),
    "RNG_FIFO_COUNT_RNG_FIFO_COUNT_MASK": (0xFF, 47),
    "RNG_FIFO_COUNT_RNG_FIFO_THRESHOLD_SHIFT": (8, 48),
}
#  The same fork, the bcm2711 path's body:
#    :215  val = 0x40000;   written to RNG_TOTAL_BIT_COUNT_THRESHOLD_OFFSET,
#          commented as discarding the less random initial numbers
#    :177-178  val = rng_readl(... RNG_TOTAL_BIT_COUNT_OFFSET); if (val > 16)
#    :256  of_device_is_compatible(dev->of_node, "brcm,bcm2711-rng200")
#          selects that path by name
RPI_WARMUP_THRESHOLD = 0x40000
RPI_READY_BITS = 16

#  Linux v6.12 (revision adc218676eef25575469234709c2d87185ca223a),
#  drivers/char/hw_random/iproc-rng200.c.   name: (value, line)
LINUX_IPROC_RNG200 = {
    "RNG_CTRL_OFFSET": (0x00, 20),
    "RNG_CTRL_RNG_RBGEN_MASK": (0x1FFF, 21),
    "RNG_CTRL_RNG_RBGEN_ENABLE": (0x01, 22),
    "RNG_SOFT_RESET_OFFSET": (0x04, 24),
    "RNG_SOFT_RESET": (0x01, 25),
    "RBG_SOFT_RESET_OFFSET": (0x08, 27),
    "RBG_SOFT_RESET": (0x01, 28),
    "RNG_INT_STATUS_OFFSET": (0x18, 30),
    "RNG_INT_STATUS_MASTER_FAIL_LOCKOUT_IRQ_MASK": (0x80000000, 31),
    "RNG_INT_STATUS_STARTUP_TRANSITIONS_MET_IRQ_MASK": (0x00020000, 32),
    "RNG_INT_STATUS_NIST_FAIL_IRQ_MASK": (0x20, 33),
    "RNG_INT_STATUS_TOTAL_BITS_COUNT_IRQ_MASK": (0x01, 34),
    "RNG_FIFO_DATA_OFFSET": (0x20, 36),
    "RNG_FIFO_COUNT_OFFSET": (0x24, 38),
    "RNG_FIFO_COUNT_RNG_FIFO_COUNT_MASK": (0xFF, 39),
}

#  Das U-Boot v2025.01 (revision 6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72),
#  drivers/rng/iproc_rng200.c.   name: (value, line)
UBOOT_IPROC_RNG200 = {
    "RNG_CTRL_OFFSET": (0x00, 15),
    "RNG_CTRL_RNG_RBGEN_MASK": (0x1FFF, 16),
    "RNG_CTRL_RNG_RBGEN_ENABLE": (0x01, 17),
    "RNG_SOFT_RESET_OFFSET": (0x04, 20),
    "RNG_SOFT_RESET": (0x01, 21),
    "RBG_SOFT_RESET_OFFSET": (0x08, 23),
    "RBG_SOFT_RESET": (0x01, 24),
    "RNG_INT_STATUS_OFFSET": (0x18, 26),
    "RNG_INT_STATUS_MASTER_FAIL_LOCKOUT_IRQ_MASK": (0x80000000, 27),
    "RNG_INT_STATUS_NIST_FAIL_IRQ_MASK": (0x20, 28),
    "RNG_FIFO_DATA_OFFSET": (0x20, 30),
    "RNG_FIFO_COUNT_OFFSET": (0x24, 32),
    "RNG_FIFO_COUNT_RNG_FIFO_COUNT_MASK": (0xFF, 33),
}

#  THE PI 3 BLOCK, KEPT AS THE COUNTER-EXAMPLE.  Linux v6.12,
#  drivers/char/hw_random/bcm2835-rng.c.   name: (value, line)
LINUX_BCM2835_RNG = {
    "RNG_DATA": (0x8, 19),
    "RNG_WARMUP_COUNT": (0x40000, 26),
}

#  raspberrypi/linux rpi-6.12.y, arch/arm64/boot/dts/broadcom/bcm2711.dtsi
#    :41   ranges = <0x7e000000  0x0 0xfe000000  0x01800000>, ...
#    :125-128  rng@7e104000 { compatible = "brcm,bcm2711-rng200";
#                             reg = <0x7e104000 0x28>; };
DT_SOC_RANGE_7E = (0x7E000000, 0xFE000000, 0x01800000)
DT_RNG_REG = (0x7E104000, 0x28)


def parse_pi4_constants(path: pathlib.Path) -> dict[str, int]:
    out: dict[str, int] = {}
    pat = re.compile(r"^\s*#([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\$[0-9A-Fa-f]+|-?\d+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        raw = m.group(2)
        out[m.group(1)] = int(raw[1:], 16) if raw.startswith("$") else int(raw)
    return out


def parse_pi4_citations(path: pathlib.Path) -> dict[str, int]:
    """#NAME = value   ; :NNN     ->  {NAME: NNN}

    The trailing `; :213` on a constant line is the line of
    rpi-6.12.y_iproc-rng200.c it was read out of.
    """
    out: dict[str, int] = {}
    pat = re.compile(
        r"^\s*#([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\S+\s*;\s*:(\d+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


#  entropy.pi4 constant  ->  the C #define it quotes
CITED = {
    "RNG_CTRL_OFF":           "RNG_CTRL_OFFSET",
    "RNG_CTRL_RBGEN_MASK":    "RNG_CTRL_RNG_RBGEN_MASK",
    "RNG_CTRL_RBGEN_ENABLE":  "RNG_CTRL_RNG_RBGEN_ENABLE",
    "RNG_CTRL_DIV_SHIFT":     "RNG_CTRL_RNG_DIV_CTRL_SHIFT",
    "RNG_SOFT_RESET_OFF":     "RNG_SOFT_RESET_OFFSET",
    "RNG_SOFT_RESET_BIT":     "RNG_SOFT_RESET",
    "RBG_SOFT_RESET_OFF":     "RBG_SOFT_RESET_OFFSET",
    "RBG_SOFT_RESET_BIT":     "RBG_SOFT_RESET",
    "RNG_TOTAL_BITS_OFF":     "RNG_TOTAL_BIT_COUNT_OFFSET",
    "RNG_TOTAL_BITS_THR_OFF": "RNG_TOTAL_BIT_COUNT_THRESHOLD_OFFSET",
    "RNG_INT_STATUS_OFF":     "RNG_INT_STATUS_OFFSET",
    "RNG_INT_MASTER_FAIL":    "RNG_INT_STATUS_MASTER_FAIL_LOCKOUT_IRQ_MASK",
    "RNG_INT_STARTUP_MET":    "RNG_INT_STATUS_STARTUP_TRANSITIONS_MET_IRQ_MASK",
    "RNG_INT_NIST_FAIL":      "RNG_INT_STATUS_NIST_FAIL_IRQ_MASK",
    "RNG_INT_TOTAL_BITS":     "RNG_INT_STATUS_TOTAL_BITS_COUNT_IRQ_MASK",
    "RNG_INT_ENABLE_OFF":     "RNG_INT_ENABLE_OFFSET",
    "RNG_FIFO_DATA_OFF":      "RNG_FIFO_DATA_OFFSET",
    "RNG_FIFO_COUNT_OFF":     "RNG_FIFO_COUNT_OFFSET",
    "RNG_FIFO_COUNT_MASK":    "RNG_FIFO_COUNT_RNG_FIFO_COUNT_MASK",
    "RNG_FIFO_THR_SHIFT":     "RNG_FIFO_COUNT_RNG_FIFO_THRESHOLD_SHIFT",
}


def check_citations(K: dict[str, int],
                    lib: pathlib.Path = LIB) -> None:
    cites = parse_pi4_citations(lib)
    rpi = RPI_IPROC_RNG200
    lnx = LINUX_IPROC_RNG200
    ubt = UBOOT_IPROC_RNG200

    for ours, theirs in CITED.items():
        check(ours in K, "entropy.pi4 defines #%s" % ours)
        check(theirs in rpi,
              "the pinned rpi-6.12.y iproc-rng200.c table names %s" % theirs)
        if ours not in K or theirs not in rpi:
            continue
        val, line = rpi[theirs]
        check(K[ours] == val,
              "#%s = %#x but %s = %#x" % (ours, K[ours], theirs, val))
        # THE CITATION'S LINE MUST BE THE PINNED LINE.
        check(cites.get(ours) == line,
              "#%s cites :%s, %s is really at :%d"
              % (ours, cites.get(ours), theirs, line))
        # The other two trees, where they carry the same name.
        for name, table in (("mainline", lnx), ("u-boot", ubt)):
            if theirs in table:
                check(table[theirs][0] == val,
                      "%s disagrees on %s: %#x vs %#x"
                      % (name, theirs, table[theirs][0], val))

    # 2. the composed words, re-derived from the fields.
    check(K["ENTROPY_ENABLE_WORD"]
          == ((3 << K["RNG_CTRL_DIV_SHIFT"]) | K["RNG_CTRL_RBGEN_MASK"]),
          "#ENTROPY_ENABLE_WORD is not (3 << DIV_SHIFT) | RBGEN_MASK")
    check(K["ENTROPY_FIFO_THR_WORD"] == (2 << K["RNG_FIFO_THR_SHIFT"]),
          "#ENTROPY_FIFO_THR_WORD is not 2 << FIFO_THR_SHIFT")

    # the warm-up value and the software gate, from the pinned driver body
    check(K["ENTROPY_WARMUP_BITS"] == RPI_WARMUP_THRESHOLD,
          "#ENTROPY_WARMUP_BITS is not the driver's 0x40000")
    check(K["ENTROPY_READY_BITS"] == RPI_READY_BITS,
          "#ENTROPY_READY_BITS is not the driver's 16")

    # THE PI 3 TRAP.  The header claims the two blocks overlap and differ;
    # the pinned Pi 3 map must still disagree with this library's.
    check(LINUX_BCM2835_RNG["RNG_DATA"][0] != K["RNG_FIFO_DATA_OFF"],
          "the two blocks now agree on where the data register is - "
          "the header's overlap warning needs rewriting")


def check_base(K: dict[str, int]) -> None:
    # ANVIL MAIN CHANGE: the older tree also compared this literal with
    # #SOC_RNG_BASE in RaspberryPi4/Lib/soc.pi4.  Anvil main has no soc.pi4
    # (entropy.pi4:58 and :430-435 still mention it), so the base is
    # compared with the device tree, which is the independent source.
    bus, span = DT_RNG_REG
    child, parent, size = DT_SOC_RANGE_7E
    check(child <= bus < child + size,
          "the pinned soc range does not cover the rng@ node")
    phys = bus - child + parent
    check(phys == K["ENTROPY_BASE"],
          "the device tree puts the RNG at $%X, entropy.pi4 says $%X"
          % (phys, K["ENTROPY_BASE"]))
    # the block length in the dtsi must cover the highest register
    highest = max(K[n] for n in K if n.startswith(("RNG_", "RBG_"))
                  and n.endswith("_OFF"))
    check(highest + 4 == span,
          "dtsi says the block is $%X long; the highest offset used is "
          "$%X + 4 = $%X" % (span, highest, highest + 4))


# =====================================================================
#  THE RNG200 MODEL
# =====================================================================
#  Written from the same driver the library was written from, which is
#  stated in the docstring as the limit of what it can prove.  What it
#  is good for is the ORDER and the GUARDS: it records every access and
#  it explodes on a read of an empty FIFO.
# =====================================================================
class Rng200:
    def __init__(self, stream, *, enabled=False, health=0,
                 bits_per_poll=8, fifo_after=0):
        self.reg = {0x00: 0, 0x04: 0, 0x08: 0, 0x0C: 0, 0x10: 0,
                    0x18: health, 0x1C: 0, 0x24: 0}
        if enabled:
            self.reg[0x00] = 0x1  # somebody else's one-bit enable
        self.stream = list(stream)
        self.pos = 0
        self.log: list[tuple[str, int, int]] = []
        self.total_bits = 0
        self.bits_per_poll = bits_per_poll
        self.fifo = 0
        self.fifo_after = fifo_after       # polls of an empty FIFO first
        self.polls = 0
        self.empty_reads = 0
        self.fifo_threshold = 0

    def enabled(self) -> bool:
        return (self.reg[0x00] & 0x1FFF) != 0

    def load(self, off: int) -> int:
        if off == 0x0C:
            # TOTAL_BIT_COUNT advances only while the block is enabled.
            if self.enabled():
                self.total_bits += self.bits_per_poll
            self.log.append(("r", off, self.total_bits))
            return self.total_bits & MASK32
        if off == 0x24:
            if self.enabled():
                if self.polls >= self.fifo_after and self.pos < len(self.stream):
                    self.fifo = min(4, len(self.stream) - self.pos)
                else:
                    self.fifo = 0
                self.polls += 1
            v = (self.fifo & 0xFF) | (self.fifo_threshold << 8)
            self.log.append(("r", off, v))
            return v
        if off == 0x20:
            if self.fifo <= 0:
                self.empty_reads += 1
                raise SystemExit(
                    "FATAL: the library read RNG_FIFO_DATA with the FIFO "
                    "empty.  That returns a number on real silicon and the "
                    "number is not entropy.")
            self.fifo -= 1
            v = self.stream[self.pos] & MASK32 if self.pos < len(self.stream) else 0
            self.pos += 1
            self.log.append(("r", off, v))
            return v
        v = self.reg.get(off, 0) & MASK32
        self.log.append(("r", off, v))
        return v

    def store(self, off: int, value: int) -> None:
        value &= MASK32
        self.log.append(("w", off, value))
        if off == 0x24:
            self.fifo_threshold = (value >> 8) & 0xFF
            return
        if off == 0x18:
            # write-1-to-clear is how the driver clears all status
            self.reg[0x18] &= ~value & MASK32
            return
        if off == 0x00:
            was = self.enabled()
            self.reg[0x00] = value
            if not was and self.enabled():
                self.total_bits = 0
                self.polls = 0
            return
        self.reg[off] = value

    def writes(self) -> list[tuple[int, int]]:
        return [(o, v) for k, o, v in self.log if k == "w"]


# =====================================================================
#  THE HARNESS
# =====================================================================
HARNESS = r'''
; ======================================================================
;  entropyharness.pi4 - GENERATED BY tools/a64/a64_entropy_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "__LIB__"

#H_CMD = $06000000
#H_BUF = $06100000
#H_OUT = $0A000000

Procedure.i Main()
  Define op.i
  Define a1.i
  Define a2.i
  Define st.i

  op = PeekN(#H_CMD)
  a1 = PeekN(#H_CMD + 4)
  a2 = PeekN(#H_CMD + 8)

  st = 0
  If op = 1
    st = EntropyBegin()
  ElseIf op = 2
    st = EntropyRestart()
  ElseIf op = 3
    st = EntropyWarmupWait(a1)
  ElseIf op = 4
    st = EntropyWords(#H_BUF, a1, a2)
  ElseIf op = 5
    st = EntropyBytes(#H_BUF, a1, a2)
  ElseIf op = 6
    st = EntropyStuckCheck(#H_BUF, a1)
  ElseIf op = 7
    st = EntropyBegin()
    If st > 0
      st = EntropyWarmupWait(a2)
      If st > 0
        st = EntropyWords(#H_BUF, a1, a2)
      EndIf
    EndIf
  ElseIf op = 8
    EntropyStop()
    st = 1
  EndIf

  PokeI(#H_OUT +   0, st)
  PokeI(#H_OUT +   8, EntropyStuckWords())
  PokeI(#H_OUT +  16, EntropyStuckOnes())
  PokeI(#H_OUT +  24, EntropyStuckBits())
  PokeI(#H_OUT +  32, EntropyStuckPeriod())
  PokeI(#H_OUT +  40, EntropyStuckZeroWords())
  PokeI(#H_OUT +  48, EntropyStuckOnesWords())
  PokeI(#H_OUT +  56, EntropyWordsRead())
  PokeI(#H_OUT +  64, EntropyTimeouts())
  PokeI(#H_OUT +  72, EntropyHealthStops())
  PokeI(#H_OUT +  80, EntropyEnabled())
  PokeI(#H_OUT +  88, EntropyCtrl())
  ProcedureReturn st
EndProcedure
'''


def build(lib: pathlib.Path, img: pathlib.Path) -> None:
    harness = img.parent / "entropyharness.pi4"
    try:
        rel = lib.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        rel = lib.resolve().as_posix()       # a mutant copy outside the tree
    harness.write_text(HARNESS.replace("__LIB__", rel), encoding="utf-8")
    cmd = [COMPILER, "--compile", str(harness), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("The entropy harness did not build:\n" + r.stdout)


def run(img: pathlib.Path, op: int, a1: int = 0, a2: int = 0,
        rng: Rng200 | None = None, prefill: bytes = b"") -> dict:
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    for i, b in enumerate(prefill):
        mem[H_BUF + i] = b
    for off, val in ((0, op), (4, a1), (8, a2)):
        for i in range(4):
            mem[H_CMD + off + i] = (val >> (8 * i)) & 0xFF
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    if rng is None:
        rng = Rng200([])

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            return 0
        if RNG_LO <= addr <= RNG_HI:
            if size != 4:
                raise SystemExit(
                    "FATAL: a %d-byte access to the RNG200 at $%X.  These "
                    "are 32-bit device registers." % (size, addr))
            return rng.load(addr - RNG_LO)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if UART_LO <= addr <= UART_HI:
            return
        if RNG_LO <= addr <= RNG_HI:
            if size != 4:
                raise SystemExit(
                    "FATAL: a %d-byte write to the RNG200 at $%X." % (size, addr))
            rng.store(addr - RNG_LO, value)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while cpu.pc != LOADER_LR:
        cpu.step()
        steps += 1
        if steps > STEP_LIMIT:
            raise SystemExit("the harness never returned (%d steps)" % steps)

    def out(i):
        v = sum(mem.get(H_OUT + i * 8 + j, 0) << (8 * j) for j in range(8))
        return v - (1 << 64) if v >> 63 else v

    return {
        "st": out(0), "words": out(1), "ones": out(2), "bits": out(3),
        "period": out(4), "zerow": out(5), "onesw": out(6),
        "read": out(7), "timeouts": out(8), "healthstops": out(9),
        "enabled": out(10), "ctrl": out(11),
        "buf": bytes(mem.get(H_BUF + i, 0) for i in range(4096 * 4)),
        "rng": rng, "steps": steps,
    }


# =====================================================================
#  4 + 5.  THE TRANSCRIPTS
# =====================================================================
def check_behaviour(img: pathlib.Path, K: dict[str, int]) -> None:
    OK = K["ENTROPY_OK"]
    ALREADY = K["ENTROPY_ALREADY"]
    TIMEOUT = K["ENTROPY_ERR_TIMEOUT"]
    HEALTH = K["ENTROPY_ERR_HEALTH"]
    OFF = K["ENTROPY_ERR_OFF"]
    ARG = K["ENTROPY_ERR_ARG"]
    ENABLE = K["ENTROPY_ENABLE_WORD"]
    THRW = K["ENTROPY_FIFO_THR_WORD"]
    WARM = K["ENTROPY_WARMUP_BITS"]

    # --- EntropyBegin on a cold block: exactly three writes, in order
    rng = Rng200([])
    r = run(img, OP_BEGIN, rng=rng)
    check(r["st"] == OK, "EntropyBegin on a cold block returned %d" % r["st"])
    check(rng.writes() == [(0x10, WARM), (0x24, THRW), (0x00, ENABLE)],
          "EntropyBegin's write transcript is %r" % (rng.writes(),))

    # --- EntropyBegin on a block somebody else enabled: NO writes
    rng = Rng200([], enabled=True)
    r = run(img, OP_BEGIN, rng=rng)
    check(r["st"] == ALREADY,
          "EntropyBegin on a running block returned %d, wanted #ENTROPY_ALREADY"
          % r["st"])
    check(rng.writes() == [],
          "EntropyBegin touched a running block: %r" % (rng.writes(),))

    # --- EntropyRestart: the driver's asymmetric reset, then the full
    #     bcm2711 enable
    rng = Rng200([], enabled=True)
    r = run(img, OP_RESTART, rng=rng)
    want = [
        (0x00, 0x0),          # disable: RBGEN field cleared
        (0x18, 0xFFFFFFFF),   # clear all status
        (0x08, 0x1),          # RBG reset asserted FIRST
        (0x04, 0x1),          # RNG reset asserted second
        (0x04, 0x0),          # RNG released FIRST
        (0x08, 0x0),          # RBG released last
        (0x10, WARM),         # ... then the full bcm2711 programming
        (0x24, THRW),
        (0x00, ENABLE),
    ]
    check(r["st"] == OK, "EntropyRestart returned %d" % r["st"])
    check(rng.writes() == want,
          "EntropyRestart transcript:\n  got  %r\n  want %r"
          % (rng.writes(), want))

    # --- the warm-up wait really waits
    rng = Rng200([], bits_per_poll=4)      # 4 bits per poll: 5 polls to pass 16
    run(img, OP_BEGIN, rng=rng)
    before = len([1 for k, o, _ in rng.log if k == "r" and o == 0x0C])
    r = run(img, OP_WARMUP, 1000, rng=rng)
    polls = len([1 for k, o, _ in rng.log if k == "r" and o == 0x0C]) - before
    check(r["st"] == OK, "EntropyWarmupWait returned %d" % r["st"])
    check(polls >= 5,
          "the warm-up wait returned after %d polls; 16 bits at 4 per poll "
          "needs at least 5" % polls)

    # --- the warm-up wait gives up rather than hanging
    rng = Rng200([], bits_per_poll=0)
    run(img, OP_BEGIN, rng=rng)
    r = run(img, OP_WARMUP, 200, rng=rng)
    check(r["st"] == TIMEOUT,
          "a warm-up that never completes returned %d, wanted a timeout"
          % r["st"])
    check(r["timeouts"] == 1, "the timeout was not counted")

    # --- warm-up on a block that is not enabled: OFF, not TIMEOUT
    rng = Rng200([])
    r = run(img, OP_WARMUP, 1000, rng=rng)
    check(r["st"] == OFF,
          "EntropyWarmupWait on a disabled block returned %d, wanted "
          "#ENTROPY_ERR_OFF" % r["st"])

    # --- reading words: the right bytes, little-endian, no empty reads
    stream = [0x01234567, 0x89ABCDEF, 0xDEADBEEF, 0x00000001,
              0xFFFFFFFF, 0x5A5A5A5A, 0x0F0F0F0F, 0x12345678]
    rng = Rng200(stream, fifo_after=3)     # three empty polls before data
    r = run(img, OP_FULL, len(stream), 100000, rng=rng)
    check(r["st"] == len(stream),
          "EntropyWords returned %d, wanted %d" % (r["st"], len(stream)))
    got = [int.from_bytes(r["buf"][i * 4:i * 4 + 4], "little")
           for i in range(len(stream))]
    check(got == stream, "the words came back as %r" % (got,))
    check(rng.empty_reads == 0, "the library read an empty FIFO")
    check(r["read"] == len(stream), "EntropyWordsRead() is %d" % r["read"])

    # --- a run that cannot be satisfied times out having written what
    #     it managed, and says so
    rng = Rng200([0x11111111, 0x22222222])
    r = run(img, OP_FULL, 8, 500, rng=rng)
    check(r["st"] == TIMEOUT,
          "a short source returned %d, wanted a timeout" % r["st"])
    check(r["read"] == 2,
          "it consumed %d words before giving up, wanted 2" % r["read"])

    # --- health bits each stop the read, before any FIFO access
    for name, bit in (("MASTER_FAIL_LOCKOUT", K["RNG_INT_MASTER_FAIL"]),
                      ("NIST_FAIL", K["RNG_INT_NIST_FAIL"])):
        rng = Rng200([0xAAAAAAAA] * 8, health=bit)
        run(img, OP_BEGIN, rng=rng)
        r = run(img, OP_WORDS, 4, 1000, rng=rng)
        check(r["st"] == HEALTH,
              "%s did not stop the read (returned %d)" % (name, r["st"]))
        check(r["healthstops"] == 1, "%s was not counted" % name)
        check(not any(o == 0x20 for k, o, _ in rng.log),
              "%s: the FIFO was read anyway" % name)

    # --- STARTUP_TRANSITIONS_MET is NOT treated as a failure
    rng = Rng200([0x11111111] * 4, health=K["RNG_INT_STARTUP_MET"])
    run(img, OP_BEGIN, rng=rng)
    r = run(img, OP_WORDS, 4, 1000, rng=rng)
    check(r["st"] == 4,
          "STARTUP_TRANSITIONS_MET was treated as a fault (returned %d)"
          % r["st"])

    # --- reading from a block that was never enabled
    rng = Rng200([0x11111111] * 4)
    r = run(img, OP_WORDS, 4, 1000, rng=rng)
    check(r["st"] == OFF,
          "EntropyWords on a disabled block returned %d" % r["st"])

    # --- the argument refusals
    rng = Rng200([0x11111111] * 4)
    run(img, OP_BEGIN, rng=rng)
    r = run(img, OP_WORDS, 0, 1000, rng=rng)
    check(r["st"] == ARG, "EntropyWords(_, 0, _) returned %d" % r["st"])

    # --- EntropyBytes: a partial final word, and the discard
    stream = [0x44332211, 0x88776655]
    rng = Rng200(stream)
    run(img, OP_BEGIN, rng=rng)
    r = run(img, OP_BYTES, 6, 100000, rng=rng)
    check(r["st"] == 6, "EntropyBytes(6) returned %d" % r["st"])
    check(r["buf"][:6] == bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66]),
          "EntropyBytes gave %r" % (r["buf"][:6],))
    check(rng.pos == 2,
          "EntropyBytes(6) consumed %d words; 6 bytes needs exactly 2"
          % rng.pos)

    # --- EntropyStop clears only the RBGEN field
    rng = Rng200([])
    run(img, OP_BEGIN, rng=rng)
    n = len(rng.writes())
    r = run(img, OP_STOP, rng=rng)
    #  ONLY the RBGEN field is cleared.  The divider field survives,
    #  exactly as iproc_rng200_enable_set(false) leaves it
    #  (v6.12_iproc-rng200.c:52-58).  Writing a bare 0 here would look
    #  tidier and would silently discard the sample-rate setting.
    check(rng.writes()[n:] == [(0x00, ENABLE & ~0x1FFF)],
          "EntropyStop wrote %r, wanted the RBGEN field cleared and the "
          "divider kept" % (rng.writes()[n:],))

    # --- NOTHING outside the block's own $28 bytes was ever touched
    check(all(0 <= o <= 0x24 for _, o, _ in rng.log),
          "an access landed outside the RNG200's $28-byte window")


# =====================================================================
#  6.  THE STUCK DETECTOR, ON KNOWN ANSWERS
# =====================================================================
def lcg_words(n: int, seed: int = 0x2545F491) -> list[int]:
    """A balanced, aperiodic-over-n stream.  NOT a claim about the
    hardware - it exists to prove the detector does not fire on
    something that looks like a working source."""
    out = []
    x = seed
    for _ in range(n):
        x = (x * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        out.append((x >> 32) & MASK32)
    return out


def balance(w: int) -> int:
    """The nearest word to w carrying EXACTLY 16 set bits.

    WHY THE PERIODIC TEST STREAMS ARE BUILT OUT OF THESE.  A period-p
    stream made of p arbitrary words repeats that period's bit
    imbalance N/p times, so a seven-word period that happens to be
    eight bits heavy arrives 584 bits heavy over 512 words and trips
    the BIAS check as well.  The case would still go red, and it would
    go red for the wrong reason - it would no longer be testing the
    cycle search at all.  Sixteen set bits per word makes the ones
    count exactly half by construction, so a periodic case can only
    ever fail on CYCLE.
    """
    b = 0
    while bin(w).count("1") > 16:
        w &= w - 1                       # clear the lowest set bit
    while bin(w).count("1") < 16:
        while (w >> b) & 1:
            b += 1
        w |= 1 << b
    return w & MASK32


def balanced_words(n: int, seed: int = 0x2545F491) -> list[int]:
    return [balance(w) for w in lcg_words(n, seed)]


def check_stuck(img: pathlib.Path, K: dict[str, int]) -> None:
    ALLEQ = K["ENTROPY_STUCK_ALLEQUAL"]
    CYCLE = K["ENTROPY_STUCK_CYCLE"]
    BIAS = K["ENTROPY_STUCK_BIAS"]
    SHORT = K["ENTROPY_STUCK_SHORT"]

    N = 512
    cases = [
        ("all zero", [0x00000000] * N, ALLEQ | BIAS),
        ("all ones", [0xFFFFFFFF] * N, ALLEQ | BIAS),
        ("one repeated balanced word", [0xAAAAAAAA] * N, ALLEQ),
        ("period 2", [0x0F0F0F0F, 0xF0F0F0F0] * (N // 2), CYCLE),
        ("period 7", (balanced_words(7) * (N // 7 + 1))[:N], CYCLE),
        ("period 64", (balanced_words(64) * (N // 64))[:N], CYCLE),
        # 65 is one past the search bound.  It MUST NOT be caught: a
        # detector that reports a period it did not look for is lying,
        # and this is the case that catches an off-by-one in the loop.
        ("period 65 - must NOT be caught", (balanced_words(65) * 8)[:N], 0),
        # A COUNTER IS THE CLASSIC THING THIS DETECTOR CANNOT SEE, and
        # saying so out loud in the gate is the point - the library's
        # header claims exactly this blindness and here it is,
        # asserted.  The low half IS the counter; the high half is its
        # complement, which makes every word carry exactly sixteen set
        # bits so the BIAS check cannot fire and the case is decided by
        # the cycle search alone.  Utterly predictable, and it passes.
        ("a counter - must NOT be caught",
         [(i & 0xFFFF) | ((~i & 0xFFFF) << 16) for i in range(N)], 0),
        ("a pseudo-random stream - must NOT be caught", lcg_words(N), 0),
    ]
    for name, words, want in cases:
        pre = b"".join(w.to_bytes(4, "little") for w in words)
        r = run(img, OP_STUCK, len(words), prefill=pre)
        check(r["st"] == want,
              "stuck detector on %s: got %d, wanted %d" % (name, r["st"], want))
        check(r["words"] == len(words),
              "stuck detector on %s recorded %d words" % (name, r["words"]))
        check(r["bits"] == len(words) * 32,
              "stuck detector on %s recorded %d bits" % (name, r["bits"]))
        ones = sum(bin(w).count("1") for w in words)
        check(r["ones"] == ones,
              "stuck detector on %s counted %d set bits, really %d"
              % (name, r["ones"], ones))

    # the periods it reports
    r = run(img, OP_STUCK, N,
            prefill=b"".join(w.to_bytes(4, "little")
                             for w in (balanced_words(7) * 100)[:N]))
    check(r["period"] == 7, "it reported period %d for a period-7 stream"
          % r["period"])
    r = run(img, OP_STUCK, N, prefill=b"\x00" * (N * 4))
    check(r["period"] == 1, "an all-equal stream reported period %d"
          % r["period"])
    check(r["zerow"] == N, "it counted %d zero words of %d" % (r["zerow"], N))

    # a sample too small to say anything says so instead of passing
    for n in (0, 1):
        r = run(img, OP_STUCK, n, prefill=b"\x00" * 8)
        check(r["st"] == SHORT,
              "a %d-word sample returned %d, wanted #ENTROPY_STUCK_SHORT"
              % (n, r["st"]))

    # THE BIAS BAND, at its edges.  Built by hand so the count is exact.
    #  bits = 512*32 = 16384; band = 16384*10/2000 = 81 either side.
    bits = N * 32
    band = (bits * K["ENTROPY_STUCK_BIAS_PPT"]) // 2000
    for extra, want, label in ((band, 0, "exactly at the band edge"),
                               (band + 1, BIAS, "one bit past the band")):
        target = bits // 2 + extra
        words = biased_words(N, extra)
        check(sum(bin(w).count("1") for w in words) == target,
              "the gate's own biased stream is wrong")
        r = run(img, OP_STUCK, N,
                prefill=b"".join(w.to_bytes(4, "little") for w in words))
        check(r["st"] == want,
              "bias %s: got %d, wanted %d" % (label, r["st"], want))


def biased_words(n: int, extra: int) -> list[int]:
    """n balanced words with `extra` further bits set, spread one per
    word so the stream stays aperiodic and non-constant.

    The bias case has to be decided BY THE BIAS CHECK.  A stream that
    is also constant, or also periodic, would go red either way and
    would say nothing about where the band is.
    """
    out = balanced_words(n, seed=0x13579BDF)
    i = 0
    while extra > 0:
        w = out[i % n]
        b = 0
        while (w >> b) & 1:
            b += 1
        out[i % n] = w | (1 << b)
        extra -= 1
        i += 1
    return out


# =====================================================================
#  7.  THE DIAGNOSTIC ITSELF IS EXECUTED
# =====================================================================
#  RaspberryPi4/Examples/Diagnostics/pi4Entropy.pi4 is the program that
#  will be run on the board.  A diagnostic that has never run is a
#  diagnostic that fails on the bench, at the one moment when the board
#  is attached and somebody is waiting.
#
#  It is run twice against the same model the library is tested with:
#  once on a block that answers, and once on a block that is dead.  The
#  console output is captured and read.  What is asserted is that it
#  RUNS, REACHES ITS VERDICT, and prints the honesty paragraph - not
#  what the numbers are, because on the real part they will be
#  different numbers and that is the whole point of it.
# =====================================================================
DIAG = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4Entropy.pi4"


def check_diagnostic() -> None:
    img = WORK / "pi4Entropy.img"
    cmd = [COMPILER, "--compile", str(DIAG), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    check(r.returncode == 0 and "pmfc: OK" in r.stdout,
          "pi4Entropy.pi4 does not build:\n" + r.stdout[-600:])
    if r.returncode != 0:
        return

    for label, rng, want_zero in (
            ("a block that answers",
             Rng200(lcg_words(6000), bits_per_poll=64), True),
            ("a block that never starts",
             Rng200([], bits_per_poll=0), False)):
        out, ret = run_uart(img, rng)
        text = out.decode("latin-1")
        check("pi4Entropy" in text,
              "%s: the diagnostic printed nothing recognisable" % label)
        check("NOT A RANDOMNESS TEST" in text,
              "%s: the honesty line is gone from the diagnostic" % label)
        check("RNG_CTRL" in text and "FIFO_COUNT" in text,
              "%s: the register dump is missing" % label)
        if want_zero:
            check(ret == 0,
                  "%s: the diagnostic returned %d, wanted a clean 0\n%s"
                  % (label, ret, text[-800:]))
            check("NOT STUCK" in text,
                  "%s: no verdict line\n%s" % (label, text[-800:]))
        else:
            check(ret < 0,
                  "%s: the diagnostic returned %d, wanted a refusal"
                  % (label, ret))
            check("TIMEOUT" in text,
                  "%s: a dead block did not report a timeout\n%s"
                  % (label, text[-800:]))


def run_uart(img: pathlib.Path, rng: "Rng200"):
    """Run an image with the RNG200 model and the console captured."""
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    uart = bytearray()

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            return 0                     # the PL011 flags: never busy
        if RNG_LO <= addr <= RNG_HI:
            return rng.load(addr - RNG_LO)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if UART_LO <= addr <= UART_HI:
            if addr == UART_DR:
                uart.append(value & 0xFF)
            return
        if RNG_LO <= addr <= RNG_HI:
            rng.store(addr - RNG_LO, value)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    steps = 0
    while cpu.pc != LOADER_LR:
        cpu.step()
        steps += 1
        if steps > STEP_LIMIT:
            raise SystemExit("pi4Entropy never returned\n"
                             + uart.decode("latin-1"))
    ret = cpu.x[0]
    if ret >> 63:
        ret -= 1 << 64
    return bytes(uart), ret


# =====================================================================
#  MUTATION
# =====================================================================
#  A gate that cannot be made to fail has not been shown to test
#  anything.  Each mutation is a plausible mistake, not a
#  syntax error, and every one must go red.
# =====================================================================
MUTATIONS = [
    ("the warm-up threshold is never programmed",
     "  EntropySetReg(#RNG_TOTAL_BITS_THR_OFF, #ENTROPY_WARMUP_BITS)\n", ""),
    ("the enable word loses the divider field",
     "#ENTROPY_ENABLE_WORD = $00007FFF", "#ENTROPY_ENABLE_WORD = $00001FFF"),
    ("the FIFO data register is the Pi 3's $08",
     "#RNG_FIFO_DATA_OFF      = $20", "#RNG_FIFO_DATA_OFF      = $08"),
    ("the FIFO count is not checked before a read",
     "      If EntropyFifoCount() > 0", "      If 1 = 1"),
    ("the warm-up gate is >= instead of >",
     "    If EntropyTotalBits() > #ENTROPY_READY_BITS",
     "    If EntropyTotalBits() >= 0"),
    ("the reset order is symmetric",
     "  v = EntropyReg(#RNG_SOFT_RESET_OFF)\n"
     "  EntropySetReg(#RNG_SOFT_RESET_OFF, v & ~#RNG_SOFT_RESET_BIT)\n\n"
     "  v = EntropyReg(#RBG_SOFT_RESET_OFF)\n"
     "  EntropySetReg(#RBG_SOFT_RESET_OFF, v & ~#RBG_SOFT_RESET_BIT)\n",
     "  v = EntropyReg(#RBG_SOFT_RESET_OFF)\n"
     "  EntropySetReg(#RBG_SOFT_RESET_OFF, v & ~#RBG_SOFT_RESET_BIT)\n\n"
     "  v = EntropyReg(#RNG_SOFT_RESET_OFF)\n"
     "  EntropySetReg(#RNG_SOFT_RESET_OFF, v & ~#RNG_SOFT_RESET_BIT)\n"),
    ("an already-enabled block is re-programmed",
     "  If EntropyEnabled() = 1\n    ProcedureReturn #ENTROPY_ALREADY\n  EndIf\n",
     ""),
    ("the NIST_FAIL bit is ignored",
     "  If (s & #RNG_INT_NIST_FAIL) <> 0\n    ProcedureReturn 0\n  EndIf\n", ""),
    ("the master-fail bit is ignored",
     "  If (s & #RNG_INT_MASTER_FAIL) <> 0\n    ProcedureReturn 0\n  EndIf\n", ""),
    ("the cycle search stops one short",
     "    While p <= #ENTROPY_STUCK_MAXCYCLE", "    While p < #ENTROPY_STUCK_MAXCYCLE"),
    ("the bias band is a hundred times too wide",
     "#ENTROPY_STUCK_BIAS_PPT = 10", "#ENTROPY_STUCK_BIAS_PPT = 1000"),
    ("a one-word sample passes",
     "  If words < 2", "  If words < 0"),
    ("the base address is off by a page",
     "#ENTROPY_BASE = $FE104000", "#ENTROPY_BASE = $FE105000"),
]


def mutate() -> int:
    """Run every mutation against a COPY, never against the library.

    A gate that writes a deliberate defect into a source file, even for two
    seconds, is a gate that can ship one if it is killed before it restores
    the file, or if another process builds from the tree meanwhile.  The
    copy lives in a temporary directory and the harness includes it by
    path, so the real library is never opened for writing at all.
    """
    original = LIB.read_text(encoding="utf-8")
    WORK.mkdir(parents=True, exist_ok=True)
    copy = WORK / "entropy_mut.pi4"
    survivors = []
    try:
        #  THE CONTROL, AND IT RUNS FIRST.  An UNMUTATED copy must PASS.
        #  Without it, a copy that does not build would raise on every
        #  mutation and every line would read "caught" while nothing was
        #  being tested - the most comfortable way for a mutation suite
        #  to be worthless.
        copy.write_text(original, encoding="utf-8")
        if not gate_passes(copy):
            print("  CONTROL FAILED - an unmutated copy does not pass, so")
            print("  every 'caught' below would be meaningless. Stopping.")
            return 1
        print("  %-52s %s" % ("control: the unmutated copy passes", "ok"))
        for name, old, new in MUTATIONS:
            if old not in original:
                survivors.append("%s - the anchor text is gone" % name)
                continue
            copy.write_text(original.replace(old, new, 1), encoding="utf-8")
            try:
                caught = not gate_passes(copy)
            except SystemExit:
                caught = True          # a FATAL from the model counts
            except Exception:
                caught = True
            print("  %-52s %s" % (name[:52], "caught" if caught else "SURVIVED"))
            if not caught:
                survivors.append(name)
    finally:
        if copy.exists():
            copy.unlink()
    if survivors:
        print("\n%d MUTATION(S) SURVIVED - the gate does not test them:"
              % len(survivors))
        for s in survivors:
            print("  " + s)
        return 1
    print("\nall %d mutations caught" % len(MUTATIONS))
    return 0


def gate_passes(lib: pathlib.Path = LIB) -> bool:
    global FAILURES, CHECKS
    saved_f, saved_c = FAILURES, CHECKS
    FAILURES, CHECKS = [], 0
    try:
        K = parse_pi4_constants(lib)
        check_citations(K, lib)
        check_base(K)
        img = WORK / "entropyharness.img"
        build(lib, img)
        check_behaviour(img, K)
        check_stuck(img, K)
        ok = not FAILURES
    finally:
        FAILURES, CHECKS = saved_f, saved_c
    return ok


def main(argv: list[str] | None = None) -> int:
    global COMPILER, WORK
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    COMPILER = args.compiler

    with tempfile.TemporaryDirectory(prefix="entropycheck-") as td:
        WORK = pathlib.Path(td)
        if args.mutate:
            print("MUTATION RUN - every line must read 'caught'")
            return mutate()

        K = parse_pi4_constants(LIB)
        check_citations(K)
        check_base(K)
        img = WORK / "entropyharness.img"
        build(LIB, img)
        check_behaviour(img, K)
        check_stuck(img, K)
        check_diagnostic()

    print("a64_entropy_check: %d checks, %d failed" % (CHECKS, len(FAILURES)))
    for f in FAILURES:
        print("  FAIL: " + f)
    if FAILURES:
        return 1
    print("\nWHAT THIS RUN DID NOT PROVE, and the report must say so:")
    print("  * nothing here touched real silicon")
    print("  * no statement of any kind was made about the quality of the")
    print("    hardware's output - there is no oracle for that")
    return 0


if __name__ == "__main__":
    sys.exit(main())
