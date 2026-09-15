#!/usr/bin/env python3
r"""Executable gate for Anvil's pure decisions, identity seam and network shape.

    python tools/a64/a64_anvil_check.py --compiler <PureMetalForge.exe>

Builds BOTH monitors the way tools/build.py builds them -
RaspberryPi4/Board/board.pi4 (-t pi4) and ArduinoQ/Board/board.unoq
(-t unoq --entry-returns) - records each build with tools/build_count.py,
loads the images into tools/a64/a64_interp.py with flat memory, and calls
real procedures by their .sym entries. Nothing expected is read out of the
procedure under test: addresses are computed here, window edges come from
the board's own constants or are recomputed here from the image size, and
digests are recomputed by an independent crc32.

Sections, in order:
  layout     the image, its measured extent and BSS against the memory map
  parse      ParseDotted and PayloadTop
  address    the address-safety seam on both boards, executed on the Q
  i2c        pin muxing, the stall verdict, the divider arithmetic
  info       the monitor extent each board prints, and where it came from
  7          the build number: markers in board files only, and version's
             machine line, prose line and crc32 content stamp
  8          each board names itself; no board name in the shared core;
             exactly one banner and one version command in the tree
  9          the width table, the help paragraph and the commands agree
  10         `net recv` placement refusals, executed
  netcon     where the network console lives and when it arms
  static     a stored address takes the lease's path
  ll         RFC 3927 link-local constants, order and executed picker
  K          one address per interface, executed on the per-interface stack
  rule 12    no personal name, host-language name or role noun in the
             Anvil / Pi 4 / UNO Q sources
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

from a64_interp import A64, attach_symbols                       # noqa: E402
import build_count                                               # noqa: E402

SOURCE = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
MAP = ROOT / "RaspberryPi4" / "Board" / "memmap.pi4"
QSOURCE = ROOT / "ArduinoQ" / "Board" / "board.unoq"
BY = "tools/a64/a64_anvil_check.py"

# Set by main(): the compiler, and where the two images were written.
COMPILER = ""
IMG = pathlib.Path()
QIMG = pathlib.Path()

# The source extensions of this tree's board and core files. A whole-tree
# check reads these, and only the ones git tracks or would track.
SOURCE_EXTS = (".pi4", ".pbi", ".unoq", ".pi3", ".rockpi4c")


def _is_scratch(rel: pathlib.PurePath) -> bool:
    return any(part.startswith("_") for part in rel.parts[:-1])


def source_files() -> list[pathlib.Path]:
    """Every board/core source that is part of the tree, sorted, absolute.

    Tracked files plus untracked files that are not ignored, from git, so a
    packager's staging copy or a gate's scratch root is never read as a
    second definition, and a new file that is not yet added still is. With
    no git to ask, a walk that skips any underscore-prefixed directory.
    """
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard",
             "-z", "--"] + ["*" + e for e in SOURCE_EXTS],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            rels = [p for p in r.stdout.decode("utf-8", "replace").split("\0")
                    if p]
            if rels:
                return sorted(p for p in (ROOT / rel for rel in rels)
                              if p.is_file() and not _is_scratch(
                                  p.relative_to(ROOT)))
    except OSError:
        pass
    out = []
    for e in SOURCE_EXTS:
        out += [p for p in ROOT.rglob("*" + e)
                if not _is_scratch(p.relative_to(ROOT))]
    return sorted(set(out))


def printed_literals(line: str) -> list[str]:
    """The string literals in the CODE part of one source line.

    Scans rather than splits: a `;` inside quotes is text, and a `"` inside
    a comment is not a literal. An unterminated literal yields what was
    gathered, so a board name cannot hide behind a typo.
    """
    out: list[str] = []
    buf: list[str] = []
    in_str = False
    esc = False
    for ch in line:
        if in_str:
            if esc:
                buf.append(ch)
                esc = False
            elif ch == "\\":
                buf.append(ch)
                esc = True
            elif ch == '"':
                out.append("".join(buf))
                buf = []
                in_str = False
            else:
                buf.append(ch)
        elif ch == '"':
            in_str = True
        elif ch == ";":
            break
    if in_str:
        out.append("".join(buf))
    return out


def code_of(text: str) -> str:
    """Source with whole-line comments removed."""
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith(";"))


def code_cut(text: str) -> str:
    """Source with everything from the first `;` on each line removed."""
    return "\n".join(ln.split(";", 1)[0] for ln in text.splitlines())


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def proc_body(code: str, header_re: str):
    m = re.search(r"(?ms)^" + header_re + r".*?^EndProcedure", code)
    return m.group(0) if m else None


def const(text: str, name: str) -> int:
    m = re.search(r"^\s*#%s\s*=\s*(\$?)([0-9A-Fa-f]+)" % name, text, re.M)
    if not m:
        raise SystemExit("The constant #%s could not be found, so the gate "
                         "cannot compute what it expects." % name)
    return int(m.group(2), 16 if m.group(1) else 10)


SCRATCH = 0x10000000
STACK = 0x10010000
SENTINEL = 0xDEADBEE0
STEP_LIMIT = 200000
PRINT_STEPS = 8000000
MASK64 = 0xFFFFFFFFFFFFFFFF

LOAD_RE = r"^\s*LoadAddress\s+\$([0-9A-Fa-f]+)"


def load_addr(path: pathlib.Path) -> int:
    m = re.search(LOAD_RE, path.read_text(encoding="utf-8", errors="replace"),
                  re.M)
    if not m:
        raise SystemExit("There is no LoadAddress line in %s, so the image's "
                         "link address is unknown." % path)
    return int(m.group(1), 16)


# =====================================================================
#  BUILD
# =====================================================================
def compile_board(source: pathlib.Path, target: str, image: pathlib.Path,
                  extra: list[str]) -> None:
    """Compile one whole board file and count the build.

    Placement (LoadAddress, BssAddress) is declared in each board file, so
    no placement flag is passed; the flags are the ones tools/build.py
    uses for the same target.
    """
    image.parent.mkdir(parents=True, exist_ok=True)
    cmd = [COMPILER, "--compile", source.relative_to(ROOT).as_posix(),
           "-t", target, *extra, "-o", str(image)]
    r = subprocess.run(cmd, cwd=ROOT, text=True,
                       env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not image.is_file():
        raise SystemExit("The %s build of %s failed, so nothing below can be "
                         "checked:\n%s" % (target, source.name, r.stdout))
    counted = build_count.record_build(source, target, image, by=BY,
                                       compiler=COMPILER)
    print("[gate] build count: %s" % counted.message, file=sys.stderr)


def build() -> None:
    compile_board(SOURCE, "pi4", IMG, [])


def build_q() -> None:
    compile_board(QSOURCE, "unoq", QIMG, ["--entry-returns"])


# =====================================================================
#  SYMBOLS, CPU, CALLS
# =====================================================================
def read_sym(img: pathlib.Path) -> dict[str, int]:
    """name -> value from the compiler's .sym: code symbols are offsets
    from the link address (_start is 0), BSS symbols are absolute."""
    out: dict[str, int] = {}
    for line in pathlib.Path(str(img) + ".sym").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                out[k.strip().lower()] = int(v)
            except ValueError:
                pass
    if out.get("_start") != 0:
        raise SystemExit("_start is not 0 in %s.sym, so code symbols are not "
                         "offsets and every call below would miss." % img)
    return out


CURRENT_EL_RAW = 0x8
SYSREG_READS = {
    0xD5384240: "CurrentEL",
    0xD53BE000: "CNTFRQ_EL0",
    0xD53BE020: "CNTPCT_EL0",
    0xD53BE040: "CNTVCT_EL0",
}
SYSREG_HZ = 54000000


def answer_sysregs(cpu: A64) -> None:
    """Answer the read-only system registers the banner and timeouts read.

    The value does not matter to what is graded: section 8 requires the
    banner's digit to equal what HwIdEl() returns on the same image, and
    both go through this shim. The counter advances on every read so a
    wait for it to move cannot spin forever.
    """
    real_step = cpu.step
    ticks = [0]

    def step(_r=real_step, _c=cpu, _t=ticks) -> None:
        word = (_c.memory.get(_c.pc, 0)
                | (_c.memory.get(_c.pc + 1, 0) << 8)
                | (_c.memory.get(_c.pc + 2, 0) << 16)
                | (_c.memory.get(_c.pc + 3, 0) << 24))
        which = SYSREG_READS.get(word & 0xFFFFFFE0)
        if which is not None:
            rt = word & 31
            if which == "CurrentEL":
                v = CURRENT_EL_RAW
            elif which == "CNTFRQ_EL0":
                v = SYSREG_HZ
            else:
                _t[0] += 1000
                v = _t[0]
            if rt != 31:
                _c.x[rt] = v
            _c.pc += 4
            return
        _r()

    cpu.step = step                                  # type: ignore[method-assign]


def make_cpu_for(img: pathlib.Path, load: int) -> A64:
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[load + i] = b
    attach_symbols(cpu, img, load)
    answer_sysregs(cpu)
    return cpu


def call3(cpu: A64, entry: int, a0: int, a1: int, a2: int,
          limit: int = STEP_LIMIT) -> int:
    """One call at an ABSOLUTE entry, returning x0."""
    cpu.x = [0] * 31
    cpu.x[0] = a0 & MASK64
    cpu.x[1] = a1 & MASK64
    cpu.x[2] = a2 & MASK64
    cpu.x[30] = SENTINEL
    cpu.sp = STACK
    cpu.pc = entry
    for _ in range(limit):
        if cpu.pc == SENTINEL:
            return cpu.x[0] & MASK64
        cpu.step()
    raise SystemExit("A procedure at $%X never returned within %d steps."
                     % (entry, limit))


def read_cstring(cpu: A64, addr: int, limit: int = 1000) -> str:
    out = []
    for i in range(limit):
        b = cpu.memory.get(addr + i, 0)
        if b == 0:
            break
        out.append(chr(b))
    return "".join(out)


def put_string(cpu: A64, text: str) -> int:
    for i, b in enumerate(text.encode("latin-1")):
        cpu.memory[SCRATCH + i] = b
    cpu.memory[SCRATCH + len(text)] = 0
    return SCRATCH


def poke64(cpu: A64, a: int, v: int) -> None:
    for i in range(8):
        cpu.memory[a + i] = (v >> (8 * i)) & 0xFF


def peek64(cpu: A64, a: int) -> int:
    v = 0
    for i in range(8):
        v |= cpu.memory.get(a + i, 0) << (8 * i)
    return v


def signed(v: int) -> int:
    return v - (1 << 64) if v & (1 << 63) else v


def quad(a: int, b: int, c: int, d: int) -> int:
    """First octet in the most significant byte, as the IP stack holds it."""
    return (a << 24) | (b << 16) | (c << 8) | d


class Ctx:
    """Everything the sections share: both images, and the verdicts."""

    def __init__(self) -> None:
        self.fails: list[str] = []
        self.cases = 0

    def case(self, ok: bool, message: str) -> bool:
        self.cases += 1
        if not ok:
            self.fails.append(message)
        return ok

    # ---- the Pi 4 image -------------------------------------------------
    def cpu(self) -> A64:
        return make_cpu_for(IMG, self.load)

    def call(self, cpu: A64, name: str, *args, limit: int = STEP_LIMIT) -> int:
        """A call by symbol name with up to eight arguments."""
        cpu.x = [0] * 31
        for i, a in enumerate(args):
            cpu.x[i] = a & MASK64
        cpu.x[30] = SENTINEL
        cpu.sp = STACK
        cpu.pc = self.load + self.sym[name]
        for _ in range(limit):
            if cpu.pc == SENTINEL:
                return cpu.x[0] & MASK64
            cpu.step()
        raise SystemExit("%s never returned within %d steps." % (name, limit))


# =====================================================================
#  THE WINDOW EDGES
# =====================================================================
#  Two of the Pi 4's edges are no longer constants in Anvil main: the
#  monitor's code window ends, and the low payload window starts, at the
#  image's own end rounded up to #MON_GRAIN (RaspberryPi4/Board/memmap.pi4,
#  HwMonHi and HwPayLo, which read __image_end__). So those two are
#  EXECUTED on the built image and required to equal what is computed here
#  from the image file's size and #MON_GRAIN; the rest are the declared
#  constants. An edge that moves in only one of the two turns this red.
def window_edges(ctx: Ctx) -> dict[str, int]:
    text = MAP.read_text(encoding="utf-8", errors="replace")
    out: dict[str, int] = {}
    for name in ("PAY0_HI", "PAY1_LO", "PAY1_HI", "MON_LO", "MON_DATA_LO",
                 "MON_DATA_HI", "AB_BASE", "AB_BYTES", "MON_GRAIN"):
        out[name] = const(text, name)
    grain = out["MON_GRAIN"]
    size = IMG.stat().st_size
    end = ctx.load + size

    def up(a: int) -> int:
        return ((a + grain - 1) // grain) * grain

    cpu = ctx.cpu()
    got_lo = ctx.call(cpu, "hwmonlo")
    got_hi = ctx.call(cpu, "hwmonhi")
    got_p0 = ctx.call(cpu, "hwpaylo", 0)
    ctx.case(got_lo == out["MON_LO"] == ctx.load,
             "HwMonLo() answers $%X, #MON_LO is $%X and the image is linked at "
             "$%X - the three must be one address" % (got_lo, out["MON_LO"],
                                                     ctx.load))
    ctx.case(got_hi == up(end) - 1,
             "HwMonHi() answers $%X; the image is %d bytes at $%X, so its end "
             "rounded up to #MON_GRAIN makes the code window end at $%X"
             % (got_hi, size, ctx.load, up(end) - 1))
    ctx.case(got_p0 == up(end),
             "HwPayLo(0) answers $%X and the low payload window must start at "
             "the image end rounded up to #MON_GRAIN, $%X" % (got_p0, up(end)))
    for i, lo, hi in ((0, None, "PAY0_HI"), (1, "PAY1_LO", "PAY1_HI")):
        if lo:
            ctx.case(ctx.call(cpu, "hwpaylo", i) == out[lo],
                     "HwPayLo(%d) disagrees with #%s" % (i, lo))
        ctx.case(ctx.call(cpu, "hwpayhi", i) == out[hi],
                 "HwPayHi(%d) disagrees with #%s" % (i, hi))
    out["MON_HI"] = up(end) - 1
    out["PAY0_LO"] = up(end)
    return out


def section_layout(ctx: Ctx) -> None:
    """The built image against the map the monitor publishes."""
    e = ctx.edges
    code_end = ctx.load + IMG.stat().st_size
    ab_lo, ab_hi = e["AB_BASE"], e["AB_BASE"] + e["AB_BYTES"] - 1
    # 1. The code must not reach the autoboot page, which in Anvil main
    #    sits just below the image (memmap.pi4, #AB_BASE).
    ctx.case(not (ab_hi >= ctx.load and ab_lo < code_end),
             "the image $%08X..$%08X overlaps the autoboot page $%08X..$%08X"
             % (ctx.load, code_end - 1, ab_lo, ab_hi))
    ctx.case(code_end <= e["PAY0_LO"],
             "the image ends at $%08X, inside the low payload window starting "
             "$%08X" % (code_end, e["PAY0_LO"]))
    # 2. BSS is where #MON_DATA_LO says and fits under #MON_DATA_HI.
    #    Anvil main's .sym also lists absolute labels INSIDE the image
    #    (string literals, local labels, __image_end__), so "any value at
    #    or above the load address" is no longer BSS. BSS is the Globals -
    #    the global_* symbols the .sym.meta sizes - bracketed by the
    #    compiler's own __bss_start__ / __bss_end__, and both are required
    #    to agree.
    sizes: dict[str, int] = {}
    for line in pathlib.Path(str(IMG) + ".sym.meta").read_text(
            encoding="utf-8", errors="replace").splitlines():
        parts = line.split("|")
        if len(parts) >= 2:
            try:
                sizes[parts[0].strip().lower()] = int(parts[1])
            except ValueError:
                pass
    lo = hi = None
    for name, addr in ctx.sym.items():
        if not name.startswith("global_") or name not in sizes:
            continue
        top = addr + sizes[name]
        lo = addr if lo is None else min(lo, addr)
        hi = top if hi is None else max(hi, top)
    bs, be = ctx.sym.get("__bss_start__"), ctx.sym.get("__bss_end__")
    if ctx.case(bs is not None and be is not None,
                "the .sym has no __bss_start__ / __bss_end__, so the Globals "
                "cannot be bracketed"):
        ctx.case(lo is not None and bs <= lo and hi is not None and hi <= be,
                 "the Globals $%s..$%s are not inside __bss_start__ $%08X .. "
                 "__bss_end__ $%08X" % ("%08X" % lo if lo is not None else "?",
                                        "%08X" % hi if hi is not None else "?",
                                        bs, be))
        lo, hi = bs, be
    if not ctx.case(lo is not None,
                    "the .sym has no BSS symbols, so the layout cannot be "
                    "checked - a failure, not a pass"):
        return
    ctx.case(lo == e["MON_DATA_LO"],
             "BSS starts at $%08X but #MON_DATA_LO is $%08X. The board file's "
             "BssAddress and the constant disagree, so HitsMonitor() guards "
             "memory the variables are not in" % (lo, e["MON_DATA_LO"]))
    ctx.case(hi - 1 <= e["MON_DATA_HI"],
             "BSS ends at $%08X, past #MON_DATA_HI $%08X"
             % (hi - 1, e["MON_DATA_HI"]))
    # 3. And it is not inside the image window.
    ctx.case(not (lo <= e["MON_HI"] and hi - 1 >= e["MON_LO"]),
             "BSS $%08X..$%08X is inside the monitor's code window "
             "$%08X..$%08X" % (lo, hi - 1, e["MON_LO"], e["MON_HI"]))


# =====================================================================
#  ParseDotted and PayloadTop
# =====================================================================
GOOD = [
    ("0.0.0.0", quad(0, 0, 0, 0)),
    ("1.2.3.4", quad(1, 2, 3, 4)),
    ("192.168.1.50", quad(192, 168, 1, 50)),
    ("10.0.0.1", quad(10, 0, 0, 1)),
    ("169.254.183.67", quad(169, 254, 183, 67)),
    ("255.255.255.0", quad(255, 255, 255, 0)),
    ("255.0.0.0", quad(255, 0, 0, 0)),
    # $FFFFFFFF is a legal broadcast and distinct from the -1 sentinel only
    # because .i is 64 bits wide.
    ("255.255.255.255", 0xFFFFFFFF),
    ("127.0.0.1", quad(127, 0, 0, 1)),
    # Leading zeroes are decimal, not octal.
    ("010.001.001.001", quad(10, 1, 1, 1)),
]

BAD = [
    ("", "empty"),
    ("192.168.1", "three fields"),
    ("192.168.1.50.7", "five fields"),
    ("192.168.1.", "trailing dot"),
    (".1.2.3.4", "leading dot"),
    ("192.168..1", "empty field"),
    ("256.1.1.1", "a field above 255"),
    ("300.1.1.1", "a field above 255, three digits"),
    ("1.2.3.4x", "junk after the last field"),
    ("1.2.3.4 ", "a trailing space"),
    (" 1.2.3.4", "a leading space"),
    ("1.2.3.4/24", "a prefix length"),
    ("abc", "not numbers at all"),
    ("1.2.3.-1", "a minus sign"),
    ("0001.2.3.4", "four digits in one field"),
    ("1234.2.3.4", "four digits in one field, larger"),
    ("1.2.3.4.", "four fields and a trailing dot"),
    ("192,168,1,50", "commas instead of stops"),
    ("::1", "an IPv6 address"),
]


def section_parse(ctx: Ctx) -> None:
    cpu = ctx.cpu()
    for text, expected in GOOD:
        got = ctx.call(cpu, "parsedotted", put_string(cpu, text))
        ctx.case(got == expected, "ParseDotted(%r) gave $%X, wanted $%X"
                 % (text, got, expected))
    for text, why in BAD:
        got = signed(ctx.call(cpu, "parsedotted", put_string(cpu, text)))
        ctx.case(got == -1, "ParseDotted(%r) gave %d and should have refused "
                 "(%s)" % (text, got, why))
    # SettingsGet() answers 0 for a missing key and callers pass it here.
    ctx.case(signed(ctx.call(cpu, "parsedotted", 0)) == -1,
             "ParseDotted(0) did not refuse a null pointer")

    e = ctx.edges
    lo0, hi0, lo1, hi1 = e["PAY0_LO"], e["PAY0_HI"], e["PAY1_LO"], e["PAY1_HI"]
    for addr, expected, what in (
            (lo0, hi0, "the bottom of the low window"),
            (lo0 + 0x1000, hi0, "inside the low window"),
            (hi0, hi0, "the last byte of the low window"),
            (lo1, hi1, "the bottom of the high window"),
            (hi1, hi1, "the last byte of the high window"),
            (lo0 - 1, 0, "one byte below the low window - the monitor"),
            (hi0 + 1, 0, "one byte above the low window - the payload stack"),
            (lo1 - 1, 0, "one byte below the high window - the bank gap"),
            (hi1 + 1, 0, "one byte above the high window - the peripherals"),
            (0, 0, "address zero - the firmware spin table"),
            (e["MON_LO"], 0, "the monitor's own base")):
        got = ctx.call(cpu, "payloadtop", addr)
        ctx.case(got == expected, "PayloadTop($%X) gave $%X, wanted $%X - %s"
                 % (addr, got, expected, what))


# =====================================================================
#  THE ADDRESS-SAFETY SEAM
# =====================================================================
HW_ADDR_SAFE = 0
HW_ADDR_UNCLOCKED = 1
HW_ADDR_UNKNOWN = 2

# (address, expected answer, a word the reason must contain, why). The
# device-tree citations are to the Linux kernel's
# arch/arm64/boot/dts/qcom/agatti.dtsi (v6.12), cited, not copied.
Q_CASES = [
    (0x04AC0004, HW_ADDR_UNCLOCKED, "wrapper",
     "the QUPv3 wrapper version register - the read that stalled the board "
     "(agatti.dtsi:1178, wrapper at 0x04AC0000+0x2000)"),
    (0x04AC0000, HW_ADDR_UNCLOCKED, "wrapper", "the wrapper's first byte"),
    (0x04AC1FFF, HW_ADDR_UNCLOCKED, "wrapper", "the wrapper's last byte"),
    (0x04A80000, HW_ADDR_UNCLOCKED, "serial",
     "serial engine 0 (agatti.dtsi:1190) - below the wrapper, not inside it"),
    (0x04A8C000, HW_ADDR_UNCLOCKED, "serial", "serial engine 3"),
    (0x04A94000, HW_ADDR_UNCLOCKED, "serial", "serial engine 5, the SPI link"),
    (0x05900000, HW_ADDR_UNCLOCKED, "graphics",
     "the Adreno register window (agatti.dtsi:1699)"),
    (0x0593FFFF, HW_ADDR_UNCLOCKED, "graphics",
     "the last byte of the Adreno register window"),
    (0x059A0000, HW_ADDR_UNCLOCKED, "graphics",
     "the GPU's own address translator, behind the graphics CX domain"),
    (0x04744000, HW_ADDR_UNCLOCKED, "storage",
     "the first storage-card controller, behind a managed power domain"),
    (0x0A600000, HW_ADDR_UNCLOCKED, "audio",
     "the audio subsystem, not marked disabled anywhere"),
    (0x04453000, HW_ADDR_UNCLOCKED, "random",
     "the random-number generator (agatti.dtsi:1004 gives it a managed "
     "clock)"),
    (0x00500000, HW_ADDR_SAFE, None, "the pin controller"),
    (0x007FFFFF, HW_ADDR_SAFE, None, "the last byte of the pin controller"),
    (0x05990000, HW_ADDR_SAFE, None,
     "the graphics CLOCK controller, next door to the window that hung"),
    (0x40000000, HW_ADDR_SAFE, None, "the base of the first memory bank"),
    (0x7D9FFFFF, HW_ADDR_SAFE, None, "the last byte of the first bank"),
    (0x80000000, HW_ADDR_SAFE, None, "the base of the second bank"),
    (0x13FFFFFFF, HW_ADDR_SAFE, None,
     "the last byte of memory, above 4 GB - catches 32-bit arithmetic"),
    (0x01400000, HW_ADDR_UNKNOWN, "clock controller",
     "the main clock controller: always-on by declaration, not proven"),
    (0x7DA00000, HW_ADDR_UNKNOWN, "gap",
     "the reserved gap between the memory banks"),
    (0x04A90000, HW_ADDR_UNKNOWN, "engine 4",
     "serial engine 4, the console's engine, which the board declines to "
     "claim either way"),
    (0x0F200000, HW_ADDR_UNKNOWN, "interrupt controller",
     "the interrupt controller: always-on by declaration, unread here"),
    (0x30000000, HW_ADDR_UNKNOWN, None, "an address in no table at all"),
]


def section_address(ctx: Ctx) -> None:
    # ---- 1. every command that takes an address calls the guard -------
    for rel, least in (("Anvil/Core/memcmd.pbi", 10),
                       ("Anvil/Core/hash_cmd.pbi", 2),
                       ("Anvil/Core/fs_cmd.pbi", 2),
                       ("Anvil/Core/usb_cmd.pbi", 1),
                       ("Anvil/Core/bootfile_cmd.pbi", 1)):
        n = len(re.findall(r"\bAddrAllowed\s*\(", read(rel)))
        ctx.case(n >= least,
                 "%s calls AddrAllowed %d time(s) and should call it at least "
                 "%d - a command that takes an address from the operator is "
                 "not asking the board about it" % (rel, n, least))
    for name in ("HwAddrCheck", "HwAddrReason", "HwAddrBlockLo",
                 "HwAddrBlockHi", "HwAddrReport"):
        for rel in ("RaspberryPi4/Board/hw_addr.pi4",
                    "ArduinoQ/Board/hw_addr_q.unoq"):
            body = read(rel)
            ctx.case(("Procedure.i " + name) in body
                     or ("Procedure " + name) in body,
                     "%s does not define %s - a board must supply the whole "
                     "seam" % (rel, name))
    ctx.case(not re.search(r"\$[0-9A-Fa-f]{4,}",
                           code_cut(read("Anvil/Core/addrsafe.pbi"))),
             "Anvil/Core/addrsafe.pbi has a hex literal in CODE, which on past "
             "form is a chip address. The core asks the board and names no "
             "chip")

    # ---- 2. the Pi 4 answers SAFE for everything -----------------------
    cpu = ctx.cpu()
    for addr, what in ((0x04AC0004, "the address that hung the other board"),
                       (ctx.edges["MON_LO"], "the monitor's own base"),
                       (0xFE201000, "the serial port's registers"),
                       (0x00000000, "address zero")):
        got = ctx.call(cpu, "hwaddrcheck", addr, addr + 3, 0)
        ctx.case(got == HW_ADDR_SAFE,
                 "the Pi 4 answered %d for $%X (%s) and every address on that "
                 "board answers SAFE" % (got, addr, what))

    # ---- 3. the UNO Q's table -------------------------------------------
    q, qload, qsym = ctx.qcpu, ctx.qload, ctx.qsym
    for want in ("hwaddrcheck", "hwaddrreason", "hwaddrblocklo",
                 "hwaddrblockhi", "addrforcearmedfor", "forceage",
                 "global_gforceon", "global_gforceat", "global_gforceage"):
        if want not in qsym:
            raise SystemExit("The UNO Q image has no %s; it was renamed or "
                             "removed." % want)
    qcheck = qload + qsym["hwaddrcheck"]
    qreason = qload + qsym["hwaddrreason"]
    for addr, expect, word, why in Q_CASES:
        got = call3(q, qcheck, addr, addr, 0)
        if not ctx.case(got == expect, "the UNO Q answered %d for $%X, wanted "
                        "%d - %s" % (got, addr, expect, why)):
            continue
        if expect == HW_ADDR_SAFE:
            continue
        ptr = call3(q, qreason, 0, 0, 0)
        text = read_cstring(q, ptr) if ptr else ""
        if word is None:
            ctx.case(not (expect == HW_ADDR_UNCLOCKED and not text),
                     "the UNO Q refused $%X as UNCLOCKED with no reason at "
                     "all - the refusal has to name the block" % addr)
        else:
            ctx.case(word.lower() in text.lower(),
                     "the UNO Q's reason for $%X does not mention %r, so it is "
                     "not naming the right block. It said: %r"
                     % (addr, word, text[:120]))
    for addr in (0x04AC0004, 0x05900000, 0x04A94000):
        call3(q, qcheck, addr, addr, 0)
        blo = call3(q, qload + qsym["hwaddrblocklo"], 0, 0, 0)
        bhi = call3(q, qload + qsym["hwaddrblockhi"], 0, 0, 0)
        ctx.case(blo <= addr <= bhi,
                 "the UNO Q refused $%X and reported the block as $%X..$%X, "
                 "which does not contain it" % (addr, blo, bhi))
    ctx.case(call3(q, qcheck, 0x04ABFFF0, 0x04AC000F, 0) == HW_ADDR_UNCLOCKED,
             "a range STRADDLING the start of the wrapper was not refused")
    ctx.case(call3(q, qcheck, 0x007FFFF0, 0x0080000F, 0) != HW_ADDR_SAFE,
             "a range HALF OUTSIDE the pin controller answered SAFE")
    ctx.case(call3(q, qcheck, 0x04AC0004, 0x04AC0007, 1) == HW_ADDR_UNCLOCKED,
             "a WRITE to the wrapper was not refused")

    # ---- the override: arms, matches only itself, expires ---------------
    on, at, age = (qsym["global_gforceon"], qsym["global_gforceat"],
                   qsym["global_gforceage"])
    farm = qload + qsym["addrforcearmedfor"]
    fage = qload + qsym["forceage"]
    poke64(q, on, 0)
    poke64(q, at, 0)
    poke64(q, age, 0)
    ctx.case(call3(q, farm, 0x04AC0004, 0, 0) == 0,
             "the override said it was armed when nothing had armed it")
    poke64(q, on, 1)
    poke64(q, at, 0x04AC0004)
    poke64(q, age, 0)
    for probe, want, what in ((0x04AC0004, 1, "the armed address"),
                              (0x04AC0000, 0, "four bytes below it"),
                              (0x04AC0008, 0, "four bytes above it"),
                              (0x00000000, 0, "an unrelated address")):
        ctx.case(call3(q, farm, probe, 0, 0) == want,
                 "the override answered wrongly for $%X (%s) - it must match "
                 "the start address exactly" % (probe, what))
    call3(q, fage, 0, 0, 0)
    ctx.case(call3(q, farm, 0x04AC0004, 0, 0) == 1,
             "the override expired after ONE command line - it has to survive "
             "the line after the one that armed it")
    call3(q, fage, 0, 0, 0)
    ctx.case(call3(q, farm, 0x04AC0004, 0, 0) == 0,
             "the override was STILL ARMED after two command lines")
    ctx.case(peek64(q, on) == 0, "ForceAge left gForceOn set after expiry")


# =====================================================================
#  THE I2C BUS: PINS MUXED, A STALL IS NOT A DIAGNOSIS, THE BUS RATE
# =====================================================================
UART_DR = 0xFE201000            # PL011 data register, RaspberryPi4/Lib/uart.pi4
UART_FR = 0xFE201018            # PL011 flag register
FR_RXFE = 16                    # bit 4 - receive FIFO empty


def section_i2c(ctx: Ctx) -> None:
    i2c_code = code_cut(read("Anvil/Core/i2c_cmd.pbi"))
    ups = len(re.findall(r"\bHwI2cUp\s*\(", i2c_code))
    ctx.case(ups == 1,
             "Anvil/Core/i2c_cmd.pbi calls HwI2cUp %d times and must call it "
             "exactly once, in the dispatcher, so every subcommand's path "
             "brings the pins up" % ups)
    tail = i2c_code[i2c_code.find("Procedure CmdI2c"):]
    ctx.case("Procedure CmdI2c" in i2c_code and "HwI2cUp" in tail,
             "the single HwI2cUp call is not inside CmdI2c")
    for name in ("HwI2cPin", "HwI2cPinFunc", "HwI2cPinReady",
                 "HwI2cPadLevel", "HwI2cUp"):
        for rel in ("RaspberryPi4/Board/hw_i2c.pi4",
                    "ArduinoQ/Board/hw_i2c_q.unoq"):
            ctx.case(("Procedure.i " + name) in read(rel),
                     "%s does not define %s - a board supplies the whole pin "
                     "seam" % (rel, name))
    verdicts = len(re.findall(r"\bI2cBusVerdict\s*\(", i2c_code))
    ctx.case(verdicts >= 4,
             "I2cBusVerdict appears %d times in Anvil/Core/i2c_cmd.pbi and "
             "should appear at least 4 - its definition, the pin report, the "
             "timeout sentence and the scan" % verdicts)
    ctx.case("the bus looks wedged" not in i2c_code,
             "Anvil/Core/i2c_cmd.pbi still contains the unconditional \"the "
             "bus looks wedged\" sentence")

    lib = read("RaspberryPi4/Lib/i2c.pi4")
    gpio_lib = read("RaspberryPi4/Lib/gpio.pi4")
    sda_pin = const(lib, "I2C_PIN_SDA")
    scl_pin = const(lib, "I2C_PIN_SCL")
    alt0 = const(gpio_lib, "PIN_ALT0")
    gpio_base = const(gpio_lib, "GPIO_BASE")
    gplev0 = gpio_base + const(gpio_lib, "GPLEV0_OFF")
    cpu = ctx.cpu()
    sym = ctx.sym

    def fsel_of(pin: int) -> int:
        word = cpu.raw_load(gpio_base + (pin // 10) * 4, 4)
        return (word >> ((pin % 10) * 3)) & 7

    if ctx.case("i2cinit" in sym, "the Pi 4 image has no I2cInit"):
        for pin in (sda_pin, scl_pin):
            cpu.raw_store(gpio_base + (pin // 10) * 4, 0, 4)
        ctx.case(fsel_of(sda_pin) == 0 and fsel_of(scl_pin) == 0,
                 "the fixture did not start with both bus pins as inputs")
        ctx.call(cpu, "i2cinit")
        for pin, what in ((sda_pin, "SDA"), (scl_pin, "SCL")):
            got = fsel_of(pin)
            ctx.case(got == alt0,
                     "after I2cInit, GPIO %d (%s) has function-select code %d "
                     "and should have %d. A controller cannot reach a pin that "
                     "is still a plain input" % (pin, what, got, alt0))
        other = 9 if sda_pin != 9 else 8
        ctx.case(fsel_of(other) == 0,
                 "I2cInit changed the function of GPIO %d, which shares a "
                 "select register with the bus pins" % other)
        if "i2cpinsmuxed" in sym:
            ctx.case(ctx.call(cpu, "i2cpinsmuxed") == 1,
                     "I2cPinsMuxed said the bus pins were not on the I2C "
                     "function immediately after I2cInit set them")
            reg = gpio_base + (scl_pin // 10) * 4
            saved = cpu.raw_load(reg, 4)
            cpu.raw_store(reg, saved & ~(7 << ((scl_pin % 10) * 3)), 4)
            ctx.case(ctx.call(cpu, "i2cpinsmuxed") == 0,
                     "I2cPinsMuxed said the bus was ready with only ONE pin "
                     "muxed")
            cpu.raw_store(reg, saved, 4)
        if "i2cpadlevel" in sym:
            for bits, want, what in ((1 << sda_pin, 1, "high"), (0, 0, "low")):
                cpu.raw_store(gplev0, bits, 4)
                got = ctx.call(cpu, "i2cpadlevel", sda_pin)
                ctx.case(got == want, "I2cPadLevel(%d) read %d for a pad "
                         "sitting %s" % (sda_pin, got, what))

    V_UNKNOWN, V_WEDGED, V_IDLE = 0, 1, 2
    if ctx.case("i2ctimeoutverdict" in sym,
                "the Pi 4 image has no I2cTimeoutVerdict"):
        for sda, scl, want, what in (
                (1, 1, V_IDLE, "both lines high - a healthy bus at rest"),
                (0, 1, V_WEDGED, "the data line held low"),
                (1, 0, V_WEDGED, "the clock line held low"),
                (0, 0, V_WEDGED, "both lines held low"),
                (-1, 1, V_UNKNOWN, "the data pad cannot be read"),
                (1, -1, V_UNKNOWN, "the clock pad cannot be read"),
                (-1, -1, V_UNKNOWN, "neither pad can be read"),
                (-1, 0, V_UNKNOWN, "unreadable wins over low"),
                (0, -1, V_UNKNOWN, "the other way round")):
            got = ctx.call(cpu, "i2ctimeoutverdict", sda, scl)
            ctx.case(got == want, "I2cTimeoutVerdict(%d, %d) answered %d, "
                     "wanted %d - %s" % (sda, scl, got, want, what))

    # ---- the rate comes from the clock that feeds the divider ----------
    for rel in ("RaspberryPi4/Board/hw_i2c.pi4",
                "ArduinoQ/Board/hw_i2c_q.unoq"):
        text = read(rel)
        for name in ("HwI2cSourceHz", "HwI2cSourceWhere",
                     "HwI2cRateMin", "HwI2cRateMax"):
            ctx.case(bool(re.search(r"^Procedure(\.i)?\s+%s\s*\(" % name,
                                    text, re.M)),
                     "%s does not define %s, so the core cannot say what "
                     "clock that board's bus rate is derived from"
                     % (rel, name))
    ctx.case("150 MHz core clock" not in i2c_code,
             "Anvil/Core/i2c_cmd.pbi still prints the nominal 150 MHz caveat "
             "beside a rate derived from a measured clock")
    for name in ("HwI2cSourceHz", "HwI2cSourceWhere", "HwI2cRateMin",
                 "HwI2cRateMax"):
        ctx.case(name in i2c_code, "Anvil/Core/i2c_cmd.pbi never calls %s"
                 % name)
    ctx.case("#HW_I2C_RANGE" in i2c_code,
             "Anvil/Core/i2c_cmd.pbi does not handle #HW_I2C_RANGE, so an "
             "unreachable rate is clamped in silence")
    lib_code = code_cut(lib)
    nominal = len(re.findall(r"#I2C_CORE_NOMINAL_HZ", lib_code))
    ctx.case(nominal == 2,
             "#I2C_CORE_NOMINAL_HZ appears %d times in the code of "
             "RaspberryPi4/Lib/i2c.pi4 and must appear exactly twice: its "
             "definition and the one labelled fallback" % nominal)
    ctx.case(not re.search(r"#I2C_CORE_HZ\b", lib_code),
             "RaspberryPi4/Lib/i2c.pi4 still uses #I2C_CORE_HZ")

    cdiv_min = const(lib, "I2C_CDIV_MIN")
    cdiv_max = const(lib, "I2C_CDIV_MAX")

    def want_cdiv(src: int, hz: int) -> int:
        if src <= 0 or hz <= 0:
            return 0
        d = -(-src // hz)
        if d & 1:
            d += 1
        return max(cdiv_min, min(cdiv_max, d))

    def want_rate(src: int, cdiv: int) -> int:
        if src <= 0:
            return 0
        if cdiv == 0:
            cdiv = 32768            # BCM2711 datasheet Table 30: 0 selects 32768
        if cdiv < 0:
            return 0
        return src // cdiv

    # The clock the Pi 4 divider was measured to be fed from, by
    # RaspberryPi4/Examples/Diagnostics/pi4I2cScl.pi4.
    MEASURED_CORE = 500000992
    sources = (MEASURED_CORE, 150000000, 200000000, 250000000)
    rates = (7700, 10000, 100000, 400000, 1000000, 10000000)
    if ctx.case(all(n in sym for n in ("i2ccdivfor", "i2cratefor",
                                       "i2cratemin", "i2cratemax")),
                "the Pi 4 image is missing the pure divider arithmetic "
                "(I2cCdivFor, I2cRateFor, I2cRateMin, I2cRateMax)"):
        for src in sources:
            got = ctx.call(cpu, "i2cratemin", src)
            ctx.case(got == src // cdiv_max, "I2cRateMin(%d) answered %d, "
                     "wanted %d" % (src, got, src // cdiv_max))
            got = ctx.call(cpu, "i2cratemax", src)
            ctx.case(got == src // cdiv_min, "I2cRateMax(%d) answered %d, "
                     "wanted %d" % (src, got, src // cdiv_min))
            for hz in rates:
                want = want_cdiv(src, hz)
                got = ctx.call(cpu, "i2ccdivfor", src, hz)
                if not ctx.case(got == want, "I2cCdivFor(%d, %d) answered %d, "
                                "wanted %d" % (src, hz, got, want)):
                    continue
                ctx.case(got & 1 == 0, "I2cCdivFor(%d, %d) returned the ODD "
                         "divider %d, which the hardware rounds down" %
                         (src, hz, got))
                rate = ctx.call(cpu, "i2cratefor", src, got)
                if ctx.case(rate == want_rate(src, got),
                            "I2cRateFor(%d, %d) answered %d, wanted %d"
                            % (src, got, rate, want_rate(src, got))):
                    ctx.case(not (rate > hz and
                                  src // cdiv_min >= hz >= src // cdiv_max),
                             "asking for %d Hz from a %d Hz source produced %d "
                             "Hz, FASTER than was asked for" % (hz, src, rate))
        for src, hz in ((0, 100000), (-1, 100000), (MEASURED_CORE, 0),
                        (MEASURED_CORE, -5)):
            got = signed(ctx.call(cpu, "i2ccdivfor", src, hz))
            ctx.case(got == 0, "I2cCdivFor(%d, %d) answered %d and must "
                     "answer 0" % (src, hz, got))
        got = ctx.call(cpu, "i2cratefor", MEASURED_CORE, 0)
        ctx.case(got == MEASURED_CORE // 32768,
                 "I2cRateFor(%d, 0) answered %d - a CDIV of 0 selects 32768"
                 % (MEASURED_CORE, got))

        hw_code = code_cut(read("RaspberryPi4/Board/hw_i2c.pi4"))
        up_body = hw_code[hw_code.find("Procedure.i HwI2cUp"):]
        up_body = up_body[:up_body.find("EndProcedure")]
        ctx.case("I2cUp()" in up_body and "I2cInit" not in up_body,
                 "RaspberryPi4/Board/hw_i2c.pi4's HwI2cUp must call I2cUp and "
                 "not I2cInit; I2cInit reprograms the divider on every command "
                 "line")
        if ctx.case("i2cup" in sym and "i2cisup" in sym,
                    "the Pi 4 image has no I2cUp / I2cIsUp reachable (I2cUp "
                    "present: %s, I2cIsUp present: %s)"
                    % ("i2cup" in sym, "i2cisup" in sym)):
            bsc = const(lib, "BSC1_BASE")
            div_off = const(lib, "BSC_DIV_OFF")
            c_off = const(lib, "BSC_C_OFF")
            i2cen = const(lib, "BSC_C_I2CEN")
            ctx.call(cpu, "i2cinit")
            ctx.case(ctx.call(cpu, "i2cisup") == 1,
                     "I2cIsUp said the bus was not up immediately after "
                     "I2cInit brought it up")
            chosen = 1252
            cpu.raw_store(bsc + div_off, chosen, 4)
            ctx.call(cpu, "i2cup")
            got = cpu.raw_load(bsc + div_off, 4) & 0xFFFF
            ctx.case(got == chosen,
                     "I2cUp on a bus that was already up changed the divider "
                     "from %d to %d" % (chosen, got))
            cpu.raw_store(bsc + c_off, 0, 4)
            ctx.case(ctx.call(cpu, "i2cisup") == 0,
                     "I2cIsUp called a bus with the controller DISABLED up")
            ctx.call(cpu, "i2cup")
            ctx.case((cpu.raw_load(bsc + c_off, 4) & i2cen) != 0,
                     "I2cUp left the controller disabled on a bus that was "
                     "down")
        for hz, tol in ((100000, 1000), (400000, 4000)):
            d = ctx.call(cpu, "i2ccdivfor", MEASURED_CORE, hz)
            rate = ctx.call(cpu, "i2cratefor", MEASURED_CORE, d)
            ctx.case(abs(rate - hz) <= tol,
                     "from the %d Hz clock the divider is fed by, a request "
                     "for %d Hz produced %d Hz" % (MEASURED_CORE, hz, rate))


# =====================================================================
#  CONSOLE CAPTURE
# =====================================================================
def pi4_console(ctx: Ctx, cpu: A64, name: str, *args) -> str:
    """One printing call on the Pi 4 image, captured off the PL011.

    The flag register is forced to 'receive FIFO empty' first: it reads 0
    out of flat memory, which means a key is waiting, and the output
    break would stop long prints after one line.
    """
    for k, b in enumerate(FR_RXFE.to_bytes(4, "little")):
        cpu.memory[UART_FR + k] = b
    out = bytearray()
    real = cpu.store

    def spy(addr: int, value: int, size: int, _r=real, _o=out) -> None:
        if addr == UART_DR:
            _o.append(value & 0xFF)
            return
        if addr == UART_FR:
            return
        _r(addr, value, size)

    cpu.store = spy                                  # type: ignore[method-assign]
    try:
        ctx.call(cpu, name, *args, limit=PRINT_STEPS)
    finally:
        cpu.store = real                             # type: ignore[method-assign]
    return out.decode("latin-1")


def q_console(ctx: Ctx, name: str, *args) -> str:
    """One printing call on the UNO Q image, read back out of its
    transcript buffer (the firmware offer is skipped with no firmware)."""
    q, qsym = ctx.qcpu, ctx.qsym
    poke64(q, qsym["global_gqpend"], -1)
    poke64(q, qsym["global_gqloglen"], 0)
    a = list(args) + [0, 0, 0]
    call3(q, ctx.qload + qsym[name], a[0], a[1], a[2], PRINT_STEPS)
    n = peek64(q, qsym["global_gqloglen"])
    if n < 0 or n > 200000:
        raise SystemExit("The UNO Q transcript length is %d, so the harness "
                         "is reading the wrong global." % n)
    base = qsym["global_gqlog"]
    return "".join(chr(q.memory.get(base + i, 0)) for i in range(n))


# =====================================================================
#  INFO: WHERE THE MONITOR IS, ON BOTH BOARDS
# =====================================================================
def section_info(ctx: Ctx) -> None:
    e = ctx.edges
    if ctx.case("hwaddrreport" in ctx.sym,
                "the Pi 4 image has no HwAddrReport"):
        text = pi4_console(ctx, ctx.cpu(), "hwaddrreport").lower()
        # Anvil main prints the image's MEASURED extent (memrange.pbi,
        # PutMonitorMap: HwMonLo() to HwMonLo() + HwMonBytes() - 1) and the
        # reserved code window to HwMonHi(); both are computed here.
        size = IMG.stat().st_size
        for value, what in ((e["MON_LO"], "the monitor's code, low"),
                            (e["MON_LO"] + size - 1, "the image's last byte"),
                            (e["MON_HI"], "the monitor's code window, high"),
                            (e["MON_DATA_LO"], "the monitor's data, low"),
                            (e["MON_DATA_HI"], "the monitor's data, high")):
            ctx.case("%08x" % value in text,
                     "the Pi 4's info section does not print %08X (%s). It "
                     "said: %r" % (value, what, text[:300]))
        # The provenance. Anvil main no longer has a compile-time extent on
        # this board: RaspberryPi4/Board/hw_addr.pi4 HwAddrReport says the
        # line is MEASURED from the image itself.
        ctx.case("measured" in text,
                 "the Pi 4's info section prints the monitor extent without "
                 "saying it was measured from the image")

    q, qsym = ctx.qcpu, ctx.qsym
    for want in ("hwaddrreport", "global_gqlog", "global_gqloglen",
                 "global_gqimgbase", "global_gqimgsize", "global_gqimgknown",
                 "global_gqpend"):
        if want not in qsym:
            raise SystemExit("The UNO Q image has no %s; it was renamed or "
                             "removed." % want)
    fake_base, fake_size = 0x9ABCD000, 0x00034000
    poke64(q, qsym["global_gqimgknown"], 1)
    poke64(q, qsym["global_gqimgbase"], fake_base)
    poke64(q, qsym["global_gqimgsize"], fake_size)
    text = q_console(ctx, "hwaddrreport").lower()
    for value, what in ((fake_base, "the base the firmware gave"),
                        (fake_base + fake_size - 1, "its last byte")):
        ctx.case("%08x" % value in text,
                 "the UNO Q's info section does not print %08X (%s); on this "
                 "board only the firmware can supply it. It said: %r"
                 % (value, what, text[:300]))
    ctx.case("loaded-image" in text,
             "the UNO Q prints the monitor extent without saying it came from "
             "the firmware's loaded-image record")
    poke64(q, qsym["global_gqimgknown"], -1)
    poke64(q, qsym["global_gqimgbase"], 0)
    poke64(q, qsym["global_gqimgsize"], 0)
    blind = q_console(ctx, "hwaddrreport").lower()
    ctx.case("whole of memory" in blind,
             "with the firmware refusing to say where it loaded the image, "
             "the UNO Q's info section did not say the extent is the whole of "
             "memory. It said: %r" % blind[:300])


# =====================================================================
#  TYPING AT THE MONITOR
# =====================================================================
def type_line(cpu: A64, table: dict, args: str) -> None:
    """Put a command line's ARGUMENTS in the monitor's line buffer.

    Every Cmd* reads its arguments from gLine through ArgWord() and
    ParseHex(); gPos and gAbort are what the main loop would have set, and
    this harness is the main loop. gBase (the default address) and
    gMemWidth (the width suffix) are cleared too.
    """
    g = table["global_gline"]
    for k, ch in enumerate(args.encode("latin-1")):
        cpu.memory[g + k] = ch
    cpu.memory[g + len(args)] = 0
    for name in ("global_gpos", "global_gabort", "global_gbase",
                 "global_gmemwidth"):
        if name in table:
            poke64(cpu, table[name], 0)


# =====================================================================
#  7. THE BUILD NUMBER
# =====================================================================
#  SOURCE: the marker is on exactly one line of each BOARD file and on no
#  line of the shared core - a number in Anvil/ would be raised by
#  whichever board was built last and count nothing (PMF-BLD-003).
#  EXECUTED: CmdVersion runs on the Q's image and the TEXT is graded, off
#  the board's own transcript, against the source and an independent crc32.
BOARD_FILES = ("RaspberryPi4/Board/board.pi4", "ArduinoQ/Board/board.unoq")
MARKER_RE = r";\s*pmf:build\b"


def marked_lines(text: str, kind: str) -> list[int]:
    return [i + 1 for i, ln in enumerate(text.splitlines())
            if re.search(r";\s*%s\b" % kind, ln) and ln.split(";")[0].strip()]


def section_build_markers(ctx: Ctx) -> None:
    """Source only, and run BEFORE the builds, so a marker defect the
    compiler also refuses is still reported for what it is."""
    for rel in BOARD_FILES:
        btext = ctx.board_text[rel]
        n = len(marked_lines(btext, "pmf:build"))
        ctx.case(n == 1,
                 "%s carries %d build-number marker lines and must carry "
                 "exactly one. With none, version cannot tell one build from "
                 "another; with two, nothing can say which one the program "
                 "prints" % (rel, n))
        for kind in ("pmf:builddate", "pmf:buildtime"):
            n = len(marked_lines(btext, kind))
            ctx.case(n == 1, "%s carries %d '%s' markers and must carry "
                     "exactly one" % (rel, n, kind))
    core = sorted((ROOT / "Anvil").rglob("*.pbi"))
    ctx.case(len(core) >= 40, "only %d shared-core files were found under "
             "Anvil/, so the marker scan examined nothing" % len(core))
    for path in core:
        bad = marked_lines(path.read_text(encoding="utf-8", errors="replace"),
                           r"pmf:build(date|time)?")
        ctx.case(not bad,
                 "%s carries a build-number marker on line(s) %s. This is the "
                 "SHARED CORE: every board builds it, so a number here is "
                 "raised by whichever board was built last and counts "
                 "nothing. The marker belongs in the board file (PMF-BLD-003)"
                 % (path.relative_to(ROOT).as_posix(), bad))


def section_build_number(ctx: Ctx) -> None:
    q, qsym = ctx.qcpu, ctx.qsym
    if not ctx.case("cmdversion" in qsym,
                    "the UNO Q image has no CmdVersion, so nothing prints a "
                    "build number"):
        return
    qsrc = ctx.board_text["ArduinoQ/Board/board.unoq"]
    want = const(qsrc, "ANVIL_BUILD")
    want_date = const(qsrc, "ANVIL_BUILD_DATE")
    want_time = const(qsrc, "ANVIL_BUILD_TIME")

    # A real, small extent at the link address, so the digest can be
    # recomputed here over the same bytes of QIMG.
    STAMP_LEN = 4096
    poke64(q, qsym["global_gqimgknown"], 1)
    poke64(q, qsym["global_gqimgbase"], ctx.qload)
    poke64(q, qsym["global_gqimgsize"], STAMP_LEN)
    type_line(q, qsym, "full")          # the digest is opt-in: `version full`
    vtext = q_console(ctx, "cmdversion")

    m = re.search(r"^build (\d+) date (\d+) time (\d+)\s*$", vtext, re.M)
    if ctx.case(bool(m),
                "version does not carry the machine-readable 'build N date N "
                "time N' line. It said: %r" % vtext[:300]):
        for got, wanted, what in ((int(m.group(1)), want, "build number"),
                                  (int(m.group(2)), want_date, "build date"),
                                  (int(m.group(3)), want_time, "build time")):
            ctx.case(got == wanted,
                     "version's machine-readable line says the %s is %d and "
                     "the source says %s. The line a script reads and the "
                     "constant in the file have to be the same number"
                     % (what, got, wanted))
    ctx.case(bool(re.search(r"This is build %d\b" % want, vtext)),
             "the UNO Q's version output does not say 'This is build %s'. It "
             "said: %r" % (want, vtext[:300]))
    ctx.case("crc32" in vtext.lower(),
             "version prints a build number without pointing at the digest. A "
             "number says WHICH build this is and only a hash says WHAT is in "
             "it. It said: %r" % vtext[:300])
    want_crc = zlib.crc32(QIMG.read_bytes()[:STAMP_LEN]) & 0xFFFFFFFF
    m = re.search(r"crc32 is ([0-9A-F]{8})", vtext)
    if ctx.case(bool(m),
                "version printed no digest of the image it is running from, "
                "on a board that told it the extent. It said: %r"
                % vtext[:600]):
        ctx.case(int(m.group(1), 16) == want_crc,
                 "version's digest over %d bytes at the link address is %s and "
                 "an independent crc32 of the same bytes is %08X"
                 % (STAMP_LEN, m.group(1), want_crc))
    ctx.case(("%d bytes" % STAMP_LEN) in vtext,
             "version does not print the image extent the BOARD reported (%d "
             "bytes). It said: %r" % (STAMP_LEN, vtext[:600]))

    poke64(q, qsym["global_gqimgknown"], -1)
    poke64(q, qsym["global_gqimgbase"], 0)
    poke64(q, qsym["global_gqimgsize"], 0)
    type_line(q, qsym, "full")
    btext = q_console(ctx, "cmdversion")
    ctx.case(not re.search(r"crc32 is ([0-9A-F]{8})", btext),
             "with the firmware refusing to say where it loaded the image, "
             "version still printed a digest. It said: %r" % btext[:600])
    ctx.case("cannot say how long its own image is" in btext,
             "with no extent to hash, version did not say why there is no "
             "digest. It said: %r" % btext[:600])


# =====================================================================
#  8. THE BOARD SAYS WHICH BOARD IT IS
# =====================================================================
ID_SEAM = ("HwIdBoard", "HwIdCpu", "HwIdTarget", "HwIdEl",
           "HwIdSayConsole", "HwIdSayImage", "HwIdImageBase",
           "HwIdImageLen", "HwIdSayImageWhere")

# Words that identify a machine. A path under another board's directory
# is printed text like any other and counts.
BOARD_WORDS = (
    r"Raspberry\s*Pi", r"\bUNO\s*Q\b", r"\bPL011\b",
    r"Cortex-A\d\d", r"\bBCM2711\b", r"\bQCM2290\b",
    r"\btarget\s+pi4\b", r"\btarget\s+unoq\b",
)


def section_identity(ctx: Ctx) -> None:
    # ---- 8a. no board name in a core string literal --------------------
    for d in ("Anvil/Core", "Anvil/Hal"):
        for path in sorted((ROOT / d).glob("*.pbi")):
            rel = path.relative_to(ROOT).as_posix()
            hits = []
            for i, ln in enumerate(path.read_text(
                    encoding="utf-8", errors="replace").splitlines(), 1):
                for lit in printed_literals(ln):
                    if any(re.search(w, lit, re.I) for w in BOARD_WORDS):
                        hits.append("%d: %r" % (i, lit[:70]))
            ctx.case(not hits,
                     "%s prints a board's own name from the SHARED CORE: %s. "
                     "Every other board then inherits that identity. Ask the "
                     "HwId* seam instead" % (rel, "; ".join(hits[:4])))

    # ---- 8b. both boards supply the seam, and there is one of each ------
    for name in ID_SEAM:
        for rel in ("RaspberryPi4/Board/hw_id.pi4",
                    "ArduinoQ/Board/hw_id_q.unoq"):
            ctx.case(bool(re.search(r"^Procedure(\.i)?\s+%s\s*\(" % name,
                                    read(rel), re.M)),
                     "%s does not define %s - a board supplies the whole "
                     "identity seam" % (rel, name))
    tree = source_files()
    ctx.case(len(tree) >= 200, "only %d source files were found in the tree, "
             "so the one-definition scan examined nothing" % len(tree))
    for proc, what in ((r"Procedure\s+Banner\s*\(", "banner"),
                       (r"Procedure\s+CmdVersion\s*\(", "version command")):
        found = [p.relative_to(ROOT).as_posix() for p in tree
                 if re.search("^" + proc, p.read_text(
                     encoding="utf-8", errors="replace"), re.M)]
        ctx.case(len(found) == 1,
                 "the tree defines the %s in %d places (%s) and must define it "
                 "in exactly one. A board-local copy is how a board stays "
                 "right while the core stays wrong"
                 % (what, len(found), ", ".join(found) or "none"))

    # ---- 8c. each image names itself, executed ---------------------------
    cpu = ctx.cpu()

    def pi4_run(name: str) -> str:
        type_line(cpu, ctx.sym, "")
        return pi4_console(ctx, cpu, name)

    def q_run(name: str) -> str:
        type_line(ctx.qcpu, ctx.qsym, "")
        return q_console(ctx, name)

    for who, runner, table, mine, mytarget, theirs in (
            ("the Pi 4", pi4_run, ctx.sym, "Raspberry Pi 4", "pi4",
             ("Arduino UNO Q", "unoq")),
            ("the UNO Q", q_run, ctx.qsym, "Arduino UNO Q", "unoq",
             ("Raspberry Pi 4", "pi4"))):
        for entry, cmd in (("banner", "the banner"), ("cmdversion", "version")):
            if not ctx.case(entry in table, "%s's image has no %s"
                            % (who, entry)):
                continue
            text = runner(entry)
            ctx.case(mine in text, "%s's %s does not name %r. It said: %r"
                     % (who, cmd, mine, text[:300]))
            for wrong in theirs:
                ctx.case(not re.search(r"\b%s\b" % re.escape(wrong), text),
                         "%s's %s says %r, which is the other board - the "
                         "monitor describing a computer it is not running on. "
                         "It said: %r" % (who, cmd, wrong, text[:300]))
        if "cmdversion" in table:
            text = runner("cmdversion")
            ctx.case(("for target " + mytarget) in text,
                     "%s's version does not say 'for target %s'. It said: %r"
                     % (who, mytarget, text[:300]))
        if "hwidel" in table and "banner" in table:
            if table is ctx.sym:
                el = ctx.call(cpu, "hwidel")
            else:
                el = call3(ctx.qcpu, ctx.qload + table["hwidel"], 0, 0, 0)
            text = runner("banner")
            ctx.case(("exception level %d" % el) in text,
                     "%s's banner does not print 'exception level %d', which is what "
                     "HwIdEl() answers on the same image - the digit has to be "
                     "the one the processor reports. It said: %r"
                     % (who, el, text[:300]))

    # ---- 8d. the payload-window sizes describe the printed addresses ----
    SIZE_LINE = re.compile(
        r"the (low|high) window\s+([0-9A-F]+) to ([0-9A-F]+)\s+"
        r"\(about (\d+) (bytes|KB|MB|GB)\)")
    for who, runner, table in (("the Pi 4", pi4_run, ctx.sym),
                               ("the UNO Q", q_run, ctx.qsym)):
        if not ctx.case("putwindows" in table, "%s's image has no PutWindows"
                        % who):
            continue
        text = runner("putwindows")
        rows = SIZE_LINE.findall(text)
        if not ctx.case(len(rows) == 2,
                        "%s's payload-window paragraph did not print two "
                        "windows with a range and a size on each. It said: %r"
                        % (who, text[:400])):
            continue
        for which, lo_s, hi_s, num, unit in rows:
            lo, hi = int(lo_s, 16), int(hi_s, 16)
            real = hi - lo + 1
            mib = real // (1024 * 1024)
            if mib >= 1024:
                want, want_unit = (mib + 512) // 1024, "GB"
            elif mib >= 1:
                want, want_unit = mib, "MB"
            elif real // 1024 >= 1:
                want, want_unit = real // 1024, "KB"
            else:
                want, want_unit = real, "bytes"
            ctx.case((int(num), unit) == (want, want_unit),
                     "%s says its %s window is %08X..%08X and calls that %s %s. "
                     "It is %d bytes, which is %d %s"
                     % (who, which, lo, hi, num, unit, real, want, want_unit))


# =====================================================================
#  9. HELP AND BEHAVIOUR AGREE ABOUT THE WIDTH SUFFIX
# =====================================================================
#  The width TABLE in Anvil/Core/memcmd.pbi is read by executing it, the
#  help paragraph by executing it, and the behaviour by executing the
#  commands; all three are diffed.
def section_width(ctx: Ctx) -> None:
    sym = ctx.sym
    for want in ("wtname", "wtdefsize", "wtscales", "putwidthrule",
                 "cmdmem", "cmdfill", "cmdcopy", "cmdcompare"):
        if want not in sym:
            raise SystemExit("The Pi 4 image has no %s; the width table or its "
                             "readers were renamed." % want)
    cpu = ctx.cpu()
    WT_N = 6
    rows_ = []
    for i in range(WT_N + 2):
        ptr = ctx.call(cpu, "wtname", i)
        if ptr == 0:
            break
        rows_.append((i, read_cstring(cpu, ptr), ctx.call(cpu, "wtdefsize", i),
                      ctx.call(cpu, "wtscales", i)))
    ctx.case(len(rows_) == WT_N,
             "the width table has %d rows and this gate expects %d. A row "
             "nothing exercises is a row that can be wrong" % (len(rows_), WT_N))

    type_line(cpu, sym, "")
    rule = pi4_console(ctx, cpu, "putwidthrule")
    for _i, name, size, scales in rows_:
        ctx.case(bool(re.search(r"\b%s\b" % re.escape(name), rule)),
                 "the width-suffix help does not mention %r. It said: %r"
                 % (name, rule))
        unit = {1: "bytes", 2: "halfwords", 4: "words"}.get(size, "?")
        verb = "groups by" if scales == 0 else "counts"
        line = "%s %s %s" % (name, verb, unit)
        ctx.case(line in rule,
                 "the width-suffix help does not say %r, which is what the "
                 "table's row for %s says. It said: %r" % (line, name, rule))

    e = ctx.edges
    COUNT = 8
    PROBE = {
        "md": ("cmdmem", "%X %X" % (e["PAY0_LO"] + 0x1000, COUNT)),
        "fill": ("cmdfill", "%X AA %X" % (e["PAY0_LO"], COUNT)),
        "copy": ("cmdcopy", "%X %X %X"
                 % (e["PAY0_LO"], e["PAY0_LO"] + 0x2000, COUNT)),
        "compare": ("cmdcompare", "%X %X %X"
                    % (e["PAY0_LO"], e["PAY0_LO"] + 0x2000, COUNT)),
    }
    TOTAL = re.compile(r"(\d+) bytes")
    for _i, name, size, scales in rows_:
        if name not in PROBE:
            continue            # mm / nm read keys at a sub-prompt; see 9c
        entry, args = PROBE[name]
        for suffix, width in ((".b", 1), (".w", 2), (".l", 4), ("", 0)):
            eff = width if width else size
            want_bytes = COUNT * eff if scales else COUNT
            type_line(cpu, sym, args)
            poke64(cpu, sym["global_gmemwidth"], width)
            out = pi4_console(ctx, cpu, entry)
            m = TOTAL.search(out)
            if ctx.case(bool(m),
                        "%s%s printed no byte total. Every command in this "
                        "family has to say how much memory it touched. It "
                        "said: %r" % (name, suffix, out[:300])):
                ctx.case(int(m.group(1)) == want_bytes,
                         "%s%s with a count of %d touched %s bytes and the "
                         "width table says it should touch %d. The table has "
                         "row size %d and %s the count. It said: %r"
                         % (name, suffix, COUNT, m.group(1), want_bytes, size,
                            "scales" if scales else "does not scale",
                            out[:300]))
    rows = {r[1]: r for r in rows_}
    if ctx.case("mm" in rows and "nm" in rows,
                "the width table has lost mm or nm"):
        ctx.case(rows["mm"][2:] == rows["nm"][2:],
                 "the width table gives mm and nm different rules (%r vs %r) "
                 "and ONE procedure serves both" % (rows["mm"][2:],
                                                    rows["nm"][2:]))
    ctx.case("md" in rows and rows["md"][3] == 0,
             "the width table no longer says the memory dump keeps its count "
             "in bytes")


# =====================================================================
#  10. `net recv` - THE PLACEMENT REFUSALS, EXECUTED AND READ BACK
# =====================================================================
def section_netrecv(ctx: Ctx) -> None:
    e = ctx.edges
    if ctx.case("netrecvplacerefused" in ctx.sym,
                "the Pi 4 image has no NetRecvPlaceRefused"):
        cpu = ctx.cpu()

        def refusal(addr: int, length: int) -> tuple[int, str]:
            captured = bytearray()
            real = cpu.store

            def spy(a, v, size, _r=real, _o=captured):
                if a == UART_DR:
                    _o.append(v & 0xFF)
                    return
                if a == UART_FR:
                    return
                _r(a, v, size)

            for k, b in enumerate(FR_RXFE.to_bytes(4, "little")):
                cpu.memory[UART_FR + k] = b
            cpu.store = spy                          # type: ignore[method-assign]
            try:
                rc = ctx.call(cpu, "netrecvplacerefused", addr, length,
                              limit=PRINT_STEPS)
            finally:
                cpu.store = real                     # type: ignore[method-assign]
            return rc, captured.decode("latin-1").lower()

        rc, text = refusal(e["MON_LO"], 0x1000)
        ctx.case(rc == 1, "net recv aimed at the monitor's own code window "
                 "(%08X) was ALLOWED" % e["MON_LO"])
        for value in (e["MON_LO"], e["MON_HI"]):
            ctx.case("%08x" % value in text,
                     "the net recv monitor refusal does not print %08X, so it "
                     "refuses without saying what it hit. It said: %r"
                     % (value, text[:300]))
        ctx.case("monitor" in text, "the net recv monitor refusal never uses "
                 "the word monitor: %r" % text[:200])
        rc, text = refusal(e["MON_DATA_LO"], 0x1000)
        ctx.case(rc == 1 and "%08x" % e["MON_DATA_LO"] in text,
                 "net recv aimed at the monitor's DATA window (%08X) returned "
                 "%d and said %r; wanted a refusal naming that window"
                 % (e["MON_DATA_LO"], rc, text[:200]))
        gap = e["PAY0_HI"] + 1
        rc, text = refusal(gap, 0x1000)
        ctx.case(rc == 1, "net recv aimed at %08X, one octet past the low "
                 "payload window, was ALLOWED" % gap)
        for value in (e["PAY0_LO"], e["PAY0_HI"], e["PAY1_LO"], e["PAY1_HI"]):
            ctx.case("%08x" % value in text,
                     "the net recv out-of-window refusal does not print %08X; "
                     "it has to print both windows. It said: %r"
                     % (value, text[:300]))
        rc, text = refusal(e["PAY1_LO"], (1 << 63) - 1)
        ctx.case(rc == 1 and "64-bit" in text,
                 "net recv with a length that wraps a 64-bit add returned %d "
                 "and said %r; wanted a refusal naming the wrap"
                 % (rc, text[:200]))
        rc, text = refusal(e["PAY0_LO"], 0x1000)
        ctx.case(rc == 0 and not text.strip(),
                 "net recv into the low payload window at %08X was REFUSED "
                 "(%d) or printed something (%r)" % (e["PAY0_LO"], rc,
                                                     text[:200]))

    recv_code = code_of(read("Anvil/Core/netrecv.pbi"))
    word = next((w for w in ("Print(", "PrintN(", "UartWrite", "ArgWord",
                             "ParseHex") if w in recv_code), None)
    ctx.case(word is None,
             "Anvil/Core/netrecv.pbi calls %s and must not; the receiver "
             "carries no console and no parser so it can be driven with "
             "byte-exact frames in a harness" % word)
    cmd_src = read("Anvil/Core/netrecv_cmd.pbi")
    n = code_of(cmd_src).count("NetRecvPlaceRefused(")
    ctx.case(n == 2, "Anvil/Core/netrecv_cmd.pbi has %d code mentions of "
             "NetRecvPlaceRefused; wanted 2 - its definition and the ONE call "
             "in CmdNetRecv" % n)
    ctx.case("NetRecvRelease()" in cmd_src,
             "Anvil/Core/netrecv_cmd.pbi never calls NetRecvRelease, so the "
             "listener it opens stays armed")


# =====================================================================
#  THE NETWORK CONSOLE - WHERE IT LIVES AND WHEN IT ARMS
# =====================================================================
def section_netcon(ctx: Ctx) -> None:
    con = ROOT / "Anvil" / "Core" / "netconsole.pbi"
    if not ctx.case(con.exists(), "Anvil/Core/netconsole.pbi does not exist"):
        return
    con_code = code_of(con.read_text(encoding="utf-8", errors="replace"))
    for word in ("Cyw43", "Genet", "Sdio", "Wpa2", "wifi_", "gWifi"):
        ctx.case(word not in con_code,
                 "Anvil/Core/netconsole.pbi names %r in CODE. The console must "
                 "reach every wire through the HwLink*(kind, ...) seam" % word)
    for name in ("HwLinkRecv(", "HwLinkRxPtr(", "HwLinkTxMax(",
                 "HwLinkMacPtr(", "HwLinkOfferRaw(", "HwLinkNoteRx(",
                 "HwLinkConsoleArmed(", "NetIfUsable(", "NetIfNext("):
        ctx.case(name in con_code,
                 "Anvil/Core/netconsole.pbi never calls %s; the seam is the "
                 "console's only way to a wire" % name.rstrip("("))
    ctx.case("netcon_LinkOwns" not in con_code
             and "netcon_KindHoldingAddress" not in con_code,
             "Anvil/Core/netconsole.pbi still has the single-address sweep "
             "(netcon_LinkOwns / netcon_KindHoldingAddress)")
    rearm = proc_body(con_code, r"Procedure NetConsoleRearm\(\)")
    if ctx.case(bool(rearm), "Anvil/Core/netconsole.pbi has no "
                "NetConsoleRearm"):
        ctx.case("NetIfPreferred(" in rearm,
                 "NetConsoleRearm does not take the interface it announces "
                 "from NetIfPreferred, the one home of the preference order")
        ctx.case("netcon_Disarm()" not in rearm,
                 "NetConsoleRearm still disarms when the announced interface "
                 "changes, which forgets a peer on the other link")

    wifi_code = code_of(read("RaspberryPi4/Lib/wifi.pi4"))
    for word in ("WifiConsole", "WifiPollUdp", "WifiSendPeer", "gConOn",
                 "gConPeerOk"):
        ctx.case(word not in wifi_code,
                 "RaspberryPi4/Lib/wifi.pi4 still has %r in CODE; a second "
                 "console beside the radio is how one copy gets fixed and the "
                 "other does not" % word)

    hwl = read("RaspberryPi4/Board/hw_link.pi4")
    hwl_code = code_of(hwl)
    offer = proc_body(hwl_code, r"Procedure\.i HwLinkOfferUdp\(")
    if ctx.case(bool(offer), "RaspberryPi4/Board/hw_link.pi4 has no "
                "HwLinkOfferUdp"):
        ctx.case("NetIfUsable(" in offer,
                 "HwLinkOfferUdp does not ask NetIfUsable about the interface "
                 "the frame arrived on")
        ctx.case("NetConsoleOfferUdp(p, kind)" in offer,
                 "HwLinkOfferUdp does not hand the datagram to "
                 "NetConsoleOfferUdp with the arrival interface")
        ctx.case("ProcedureReturn NetConsoleOfferUdp" in offer,
                 "HwLinkOfferUdp does not pass the dispatcher's answer straight "
                 "through; a 2 means a reply is staged")
        ctx.case("#HW_LINK_WIFI" not in offer,
                 "HwLinkOfferUdp names #HW_LINK_WIFI")
    ctx.case("Procedure.i HwLinkReady(" in hwl,
             "RaspberryPi4/Board/hw_link.pi4 does not define HwLinkReady")
    ctx.case("GenetPhyLinkUp()" in hwl,
             "RaspberryPi4/Board/hw_link.pi4's readiness answer does not read "
             "the PHY")

    ctx.case(bool(re.search(r"(?m)^\s*#NETCON_PORT\s*=\s*5555\s*$",
                            read("Anvil/Hal/hal.pbi"))),
             "Anvil/Hal/hal.pbi does not define #NETCON_PORT = 5555")
    stray = [rel for rel in ("Anvil/Core/netconsole.pbi",
                             "RaspberryPi4/Lib/wifi.pi4",
                             "Anvil/Core/net_cmd.pbi", "Anvil/Core/xfer.pbi",
                             "RaspberryPi4/Board/screen_cmd.pi4")
             if re.search(r"\b5555\b", code_of(read(rel)))]
    ctx.case(not stray, "the console's port number is written out as 5555 in "
             "CODE in %s; it is #NETCON_PORT" % ", ".join(stray))

    boot_code = code_of(read("RaspberryPi4/Board/boot.pi4"))
    at_wired = boot_code.find("EthBootWired()")
    at_join = boot_code.find("WifiJoinKnown()")
    ctx.case(at_wired >= 0, "RaspberryPi4/Board/boot.pi4 never calls "
             "EthBootWired")
    ctx.case(at_join >= 0, "RaspberryPi4/Board/boot.pi4 never calls "
             "WifiJoinKnown")
    ctx.case(at_wired < 0 or at_join < 0 or at_wired < at_join,
             "RaspberryPi4/Board/boot.pi4 brings the wired link up AFTER the "
             "wireless auto-join")
    n = boot_code.count("NetConsoleRearm()")
    ctx.case(n >= 2, "RaspberryPi4/Board/boot.pi4 arms the console %d time(s) "
             "and both bring-ups need one" % n)

    eth_code = code_of(read("RaspberryPi4/Board/eth.pi4"))
    body = proc_body(eth_code, r"Procedure EthBootWired\(\)")
    if ctx.case(bool(body), "RaspberryPi4/Board/eth.pi4 has no EthBootWired"):
        ctx.case("ForEver" not in body and "Repeat" not in body,
                 "EthBootWired contains an unbounded loop")
        ctx.case(body.count("CmdDhcp()") == 1,
                 "EthBootWired calls CmdDhcp %d times and must call it once"
                 % body.count("CmdDhcp()"))
        ctx.case("EthCableIn()" in body, "EthBootWired does not ask "
                 "EthCableIn first")

    parse = read("Anvil/Core/parse.pbi")
    stubs = read("ArduinoQ/Board/qstubs_q.unoq")
    for name in ("NetConsoleRearm()", "NetConsolePump()", "NetConsoleGetc()"):
        ctx.case(name in parse, "Anvil/Core/parse.pbi does not call %s" % name)
        ctx.case(name.rstrip("()") in stubs,
                 "ArduinoQ/Board/qstubs_q.unoq does not answer %s; the core "
                 "is one set of bytes for every board" % name)


# =====================================================================
#  A STATIC ADDRESS ARMS THE CONSOLE, BY THE PATH A LEASE TAKES
# =====================================================================
def section_static(ctx: Ctx) -> None:
    netcfg_code = code_of(read("Anvil/Core/netcfg.pbi"))
    ncmd_code = code_of(read("Anvil/Core/net_cmd.pbi"))
    eth = read("RaspberryPi4/Board/eth.pi4")
    eth_code = code_of(eth)
    con_code = code_of(read("Anvil/Core/netconsole.pbi"))

    bound = proc_body(netcfg_code, r"Procedure NetAddressBound\(")
    if ctx.case(bool(bound), "Anvil/Core/netcfg.pbi has no NetAddressBound"):
        for need in ("NetIfSet(kind, ip, mask, gw, src)", "gEthIp = ip",
                     "HwLinkAddressBound(", "NetConsoleRearm()"):
            ctx.case(need in bound,
                     "NetAddressBound does not do %r. Record, tell the board "
                     "and arm the console are what every address source does"
                     % need)
    told = sum(len(re.findall(r"HwLinkAddressBound\(", code_of(read(rel))))
               for rel in ("Anvil/Core/netcfg.pbi", "Anvil/Core/net_cmd.pbi",
                           "RaspberryPi4/Board/eth.pi4",
                           "RaspberryPi4/Board/boot.pi4",
                           "RaspberryPi4/Lib/wifi.pi4",
                           "Anvil/Core/netconsole.pbi"))
    # Anvil main has TWO tails that tell the board: NetAddressBound (an
    # address arrives) and NetAddressLost (a lease is withdrawn from one
    # interface, Anvil/Core/netcfg.pbi). Each calls it exactly once; any
    # other caller is a second copy of a tail.
    lost = proc_body(netcfg_code, r"Procedure NetAddressLost\(")
    ctx.case(bool(bound) and bound.count("HwLinkAddressBound(") == 1,
             "NetAddressBound does not tell the board exactly once")
    ctx.case(bool(lost) and lost.count("HwLinkAddressBound(kind, 0, 0, 0)") == 1,
             "NetAddressLost does not tell the board, exactly once, that the "
             "interface has no address")
    ctx.case(told == 3,
             "HwLinkAddressBound appears %d times in CODE across the network "
             "files and must appear exactly three times - the board's "
             "definition, NetAddressBound's call and NetAddressLost's call. "
             "A further caller is a further copy of the tail" % told)

    # THE LEASE PATH. In Anvil main the lease is bound by the per-interface
    # DHCP client in Anvil/Core/netconsole.pbi (NetDhcpTick), which both boot
    # and CmdDhcp drive; CmdDhcp no longer binds it itself.
    ctx.case("NetAddressBound(kind, DhcpClientIp(kind), DhcpClientMask(kind), "
             "DhcpClientGateway(kind), #NET_ADDR_LEASE)" in con_code,
             "the DHCP client in Anvil/Core/netconsole.pbi does not hand its "
             "lease to NetAddressBound with #NET_ADDR_LEASE, so the lease "
             "path goes around the shared tail")
    dh = proc_body(ncmd_code, r"Procedure\.i CmdDhcp\(\)")
    if ctx.case(bool(dh), "Anvil/Core/net_cmd.pbi has no Procedure.i CmdDhcp"):
        ctx.case("NetDhcpAcquire(" in dh,
                 "CmdDhcp does not go through NetDhcpAcquire, the one client "
                 "that binds a lease through NetAddressBound")
        ctx.case("gEthIp = ip" not in dh,
                 "CmdDhcp still writes gEthIp itself; that is NetAddressBound's "
                 "job")
        ctx.case(bool(re.search(r"(?m)^\s*ProcedureReturn 1\s*$", dh)),
                 "CmdDhcp never answers 1, so no caller can tell a lease from "
                 "a silence")

    st = proc_body(ncmd_code, r"Procedure\.i NetStaticApply\(\)")
    if ctx.case(bool(st), "Anvil/Core/net_cmd.pbi has no NetStaticApply"):
        for need in ("EthHasIpConfig()", "HwLinkStaticUp()",
                     "#NET_ADDR_SAVED", "NetAddressBound("):
            ctx.case(need in st, "NetStaticApply does not use %r" % need)
        ctx.case("NetSetIPv4(" not in st and "NetSetMac(" not in st,
                 "NetStaticApply configures the IP layer itself; pairing a "
                 "hardware address with an IPv4 address has one home")
    setter = proc_body(ncmd_code, r"Procedure CmdNet\(\)")
    ctx.case(bool(setter) and "NetStaticApply()" in (setter or ""),
             "CmdNet never calls NetStaticApply, so net address writes strings "
             "into a store and puts nothing on the wire")
    ctx.case(bool(setter) and "IN USE NOW" in (setter or ""),
             "`net` does not name the address the board is actually holding "
             "when the settings store has none")

    sup = proc_body(eth_code, r"Procedure\.i HwLinkStaticUp\(\)")
    if ctx.case(bool(sup), "RaspberryPi4/Board/eth.pi4 has no HwLinkStaticUp"):
        ctx.case(not any(w in sup for w in ("ForEver", "Repeat", "While")),
                 "HwLinkStaticUp contains a loop, and the boot path calls it")
        # The bring-up is eth_HwUpLocal() in Anvil main (eth.pi4).
        at = [sup.find(w) for w in ("EthHasIpConfig()", "EthCableIn()",
                                    "eth_HwUpLocal()")]
        ctx.case(min(at) >= 0 and at[0] < at[1] < at[2],
                 "HwLinkStaticUp does not ask EthHasIpConfig, then EthCableIn, "
                 "and only then pay for eth_HwUpLocal")
        ctx.case("LinkKind()" in sup, "HwLinkStaticUp does not answer "
                 "LinkKind()")
    bw = proc_body(eth_code, r"Procedure EthBootWired\(\)")
    if ctx.case(bool(bw), "RaspberryPi4/Board/eth.pi4 has no EthBootWired"):
        ctx.case(bw.count("NetStaticApply()") == 1,
                 "EthBootWired calls NetStaticApply %d times and must call it "
                 "exactly once" % bw.count("NetStaticApply()"))
        a_cable, a_dhcp, a_static, a_ll = (bw.find(w) for w in (
            "EthCableIn()", "CmdDhcp()", "NetStaticApply()",
            "NetLinkLocalAcquire("))
        ctx.case(min(a_cable, a_dhcp, a_static, a_ll) >= 0
                 and a_cable < a_dhcp < a_static < a_ll,
                 "EthBootWired's order is not cable, lease, saved address, "
                 "link-local")
        ctx.case("#HW_LINK_WIRED" in bw,
                 "EthBootWired does not name the WIRED link when it acquires")
    for phrase in ("wired: no cable", "wired: lease from ",
                   "wired: saved address ", "wired: link-local "):
        ctx.case(phrase in eth, "RaspberryPi4/Board/eth.pi4's boot log never "
                 "says %r" % phrase)
    ctx.case(ncmd_code.count("NetAddrFromText(") >= 2,
             "Anvil/Core/net_cmd.pbi prints NetAddrFromText in fewer than two "
             "places; both `net` and `net link` must say where the address "
             "came from")


# =====================================================================
#  RFC 3927 LINK-LOCAL
# =====================================================================
def section_linklocal(ctx: Ctx) -> None:
    net_code = code_of(read("Anvil/Network/net.pbi"))
    ll_code = code_of(read("Anvil/Core/netll.pbi"))
    hwl_code = code_of(read("RaspberryPi4/Board/hw_link.pi4"))
    eth = read("RaspberryPi4/Board/eth.pi4")
    eth_code = code_of(eth)
    boot_code = code_of(read("RaspberryPi4/Board/boot.pi4"))
    netcfg_code = code_of(read("Anvil/Core/netcfg.pbi"))

    recv = proc_body(hwl_code, r"Procedure\.i HwLinkRecv\(")
    if ctx.case(bool(recv), "RaspberryPi4/Board/hw_link.pi4 has no "
                "HwLinkRecv"):
        ctx.case("GenetRecv(" in recv,
                 "HwLinkRecv never calls GenetRecv, only GenetRecvWait, which "
                 "refuses a non-positive timeout before looking at the ring - "
                 "so an ms = 0 console poll never sees a frame")
        ctx.case("ms <= 0" in recv or "ms < 1" in recv,
                 "HwLinkRecv does not test for a non-positive slice; ms = 0 "
                 "means look and do not wait")
    ctx.case("ms = 0" in read("Anvil/Hal/hal.pbi"),
             "Anvil/Hal/hal.pbi does not state what ms = 0 means for "
             "HwLinkRecv")

    probe = proc_body(net_code, r"Procedure\.i NetArpProbe\(")
    ctx.case(bool(probe) and "net_ArpLlFrame(kind, 0," in probe,
             "NetArpProbe does not build its frame with a ZERO sender protocol "
             "address [RFC 3927 s2.2]")
    ann = proc_body(net_code, r"Procedure\.i NetArpAnnounce\(")
    ctx.case(bool(ann) and "net_ArpLlFrame(kind, ip, ip)" in ann,
             "NetArpAnnounce does not put the address in BOTH protocol "
             "address fields [RFC 3927 s2.4]")
    llframe = proc_body(net_code, r"Procedure\.i net_ArpLlFrame\(") or ""
    ctx.case("#NET_ARP_OP_REQUEST" in llframe,
             "net_ArpLlFrame does not emit an ARP REQUEST")
    ctx.case(bool(llframe) and not re.search(r"net_(if)?IpSet", llframe),
             "net_ArpLlFrame depends on the interface having an IPv4 address; "
             "a probe is sent before there is one")

    # RFC 3927 section 2.2.1 and 2.1, written out here rather than read back.
    for name, want in (("#NET_LL_PROBE_WAIT_MS", 1000),
                       ("#NET_LL_PROBE_NUM", 3),
                       ("#NET_LL_PROBE_MIN_MS", 1000),
                       ("#NET_LL_PROBE_MAX_MS", 2000),
                       ("#NET_LL_ANNOUNCE_WAIT_MS", 2000),
                       ("#NET_LL_ANNOUNCE_NUM", 2),
                       ("#NET_LL_ANNOUNCE_INTERVAL_MS", 2000),
                       ("#NET_LL_MAX_CONFLICTS", 10),
                       ("#NET_LL_RATE_LIMIT_MS", 60000),
                       ("#NET_LL_DEFEND_INTERVAL_MS", 10000)):
        m = re.search(re.escape(name) + r"\s*=\s*(\d+)", net_code)
        ctx.case(bool(m) and int(m.group(1)) == want,
                 "%s is %s in Anvil/Network/net.pbi and RFC 3927 section "
                 "2.2.1 says %d" % (name, m.group(1) if m else "missing", want))
    for name, want in (("#NET_LL_PREFIX", 0xA9FE0000),
                       ("#NET_LL_MASK", 0xFFFF0000),
                       ("#NET_LL_FIRST", 0xA9FE0100),
                       ("#NET_LL_LAST", 0xA9FEFEFF)):
        m = re.search(re.escape(name) + r"\s*=\s*\$([0-9A-Fa-f]+)", net_code)
        ctx.case(bool(m) and int(m.group(1), 16) == want,
                 "%s must be $%08X [RFC 3927 s2.1]" % (name, want))

    arp = proc_body(net_code, r"Procedure\.i net_RecvArp\(")
    if ctx.case(bool(arp), "Anvil/Network/net.pbi has no net_RecvArp"):
        at_watch = arp.find("net_LlSeeArp(")
        # Anvil main's early returns (per-interface records):
        # "If net_ifIpSet[kind] = 0 And net_ifAlt[kind] = 0" and "If mine = 0".
        at_noip = arp.find("If net_ifIpSet[kind] = 0")
        at_nottpa = arp.find("If mine = 0")
        ctx.case(at_watch >= 0, "net_RecvArp never calls net_LlSeeArp")
        ctx.case(at_noip >= 0 and at_nottpa >= 0,
                 "net_RecvArp's early returns have been rewritten; re-check "
                 "that the link-local watcher still runs before them")
        ctx.case(at_watch < 0 or at_noip < 0 or at_nottpa < 0
                 or (at_watch < at_noip and at_watch < at_nottpa),
                 "net_RecvArp tests for a link-local conflict AFTER giving up "
                 "on frames with no address set or addressed to somebody else "
                 "- exactly the frames a probe has to see")
    see = proc_body(net_code, r"Procedure\.i net_LlSeeArp\(")
    if ctx.case(bool(see), "Anvil/Network/net.pbi has no net_LlSeeArp"):
        ctx.case("net_Same" in see, "net_LlSeeArp does not exclude frames sent "
                 "by THIS board")
        ctx.case("#NET_LL_PROBING" in see and "spa = 0" in see,
                 "net_LlSeeArp does not treat another host's probe for our "
                 "candidate as a conflict [RFC 3927 s2.2.1]")
        ctx.case("net_llGiveUp" in see and "#NET_LL_DEFEND_INTERVAL_MS" in see,
                 "net_LlSeeArp does not implement defend-once [RFC 3927 s2.5]")

    acq = proc_body(ll_code, r"Procedure\.i NetLinkLocalAcquire\(")
    if ctx.case(bool(acq), "Anvil/Core/netll.pbi has no NetLinkLocalAcquire"):
        ctx.case("LinkUseKind(kind)" in acq, "NetLinkLocalAcquire does not NAME "
                 "the link it is acquiring on")
        ctx.case("NetSetMac(" in acq, "NetLinkLocalAcquire does not set the "
                 "interface's hardware address from the link it is using")
        ctx.case("#NET_ADDR_LINKLOCAL" in acq and "NetAddressBound(" in acq,
                 "NetLinkLocalAcquire does not end in NetAddressBound with "
                 "#NET_ADDR_LINKLOCAL")
        ctx.case("HwLinkOpen(" in acq, "NetLinkLocalAcquire does not re-derive "
                 "the preference order after binding")
    ctx.case("LinkUseKind(prev)" not in ll_code,
             "Anvil/Core/netll.pbi restores the link with LinkUseKind, which "
             "re-applies the one-link override rather than undoing it")
    ctx.case("LinkForget()" in ll_code, "Anvil/Core/netll.pbi never gives the "
             "link back to the policy layer")
    ctx.case(not re.search(r"SettingsSet\(|DhcpStore\(", ll_code),
             "Anvil/Core/netll.pbi writes the settings store; a self-assigned "
             "address must never be saved")
    watch = proc_body(ll_code, r"Procedure\.i netll_Watch\(")
    ctx.case(bool(watch) and "LinkPumpNet(" in watch,
             "netll_Watch does not PUMP while it waits")
    ctx.case(not (watch and re.search(r"\bdelay\(", watch)),
             "netll_Watch calls delay(); the waiting is the listening")
    tryone = proc_body(ll_code, r"Procedure\.i netll_TryOne\(")
    if ctx.case(bool(tryone), "Anvil/Core/netll.pbi has no netll_TryOne"):
        for need in ("#NET_LL_PROBE_NUM", "#NET_LL_ANNOUNCE_NUM",
                     "#NET_LL_ANNOUNCE_WAIT_MS", "NetArpProbe(",
                     "NetArpAnnounce(", "#NET_LL_CLAIMED"):
            ctx.case(need in tryone, "netll_TryOne does not use %r" % need)

    ctx.case("NetLinkLocalAcquire(#HW_LINK_WIFI)" in boot_code,
             "RaspberryPi4/Board/boot.pi4 never takes a link-local address on "
             "the RADIO")
    ctx.case(bool(re.search(r"If gWifiHaveIp = 0 And NetIfHas\(#HW_LINK_WIFI\) "
                            r"= 0", boot_code)),
             "RaspberryPi4/Board/boot.pi4 does not gate the radio's link-local "
             "acquire on the RADIO's own record (NetIfHas(#HW_LINK_WIFI))")
    ctx.case(not re.search(r"If gWifiHaveIp = 0 And NetIPv4\(\) = 0",
                           boot_code),
             "RaspberryPi4/Board/boot.pi4 still asks the single-address "
             "question before the radio takes an address of its own")

    bound = proc_body(netcfg_code, r"Procedure NetAddressBound\(")
    ctx.case(bool(bound) and "gEthLlIp = 0" in bound,
             "NetAddressBound does not clear the link-local record when an "
             "address from another source is bound")
    has = proc_body(netcfg_code, r"Procedure\.i EthHasIpConfig\(\)")
    if ctx.case(bool(has) and "gEthLlIp" in has,
                "EthHasIpConfig does not fall back to the link-local address"):
        a_s, a_l = has.find("SettingsHas("), has.find("gEthLlIp")
        ctx.case(0 <= a_s < a_l, "EthHasIpConfig reads its link-local fallback "
                 "before the settings store; a saved address must win")
    stored = 0
    for rel in ("Anvil/Core/netll.pbi", "Anvil/Core/netcfg.pbi",
                "RaspberryPi4/Board/eth.pi4", "RaspberryPi4/Board/boot.pi4"):
        for mm in re.finditer(r"(SettingsSet|DhcpStore)\s*\([^\n]*",
                              code_of(read(rel))):
            stored += "gEthLlIp" in mm.group(0)
    ctx.case(stored == 0, "the link-local address is written to the settings "
             "store in %d place(s)" % stored)

    # ---- executed on the built image --------------------------------------
    cpu = ctx.cpu()
    for ip, want, why in (
            (0xA9FE0000, 0, "169.254.0.0 is in the reserved first 256"),
            (0xA9FE00FF, 0, "169.254.0.255 is in the reserved first 256"),
            (0xA9FE0100, 1, "169.254.1.0 is the first selectable address"),
            (0xA9FEFEFF, 1, "169.254.254.255 is the last selectable address"),
            (0xA9FEFF00, 0, "169.254.255.0 is in the reserved last 256"),
            (0xA9FEFFFF, 0, "169.254.255.255 is the subnet broadcast"),
            (0xA9FDFFFF, 0, "169.253.255.255 is outside the block"),
            (0xA9FF0000, 0, "169.255.0.0 is outside the block")):
        got = ctx.call(cpu, "netllselectable", ip)
        ctx.case(got == want, "NetLlSelectable(%08X) answered %d and must "
                 "answer %d - %s [RFC 3927 s2.1]" % (ip, got, want, why))
    for ip, want in ((0xA9FE0000, 1), (0xA9FEFFFF, 1), (0xA9FE8001, 1),
                     (0xC0A80101, 0), (0x0A2F7701, 0), (0xA9FD0001, 0)):
        got = ctx.call(cpu, "netislinklocal", ip)
        ctx.case(got == want, "NetIsLinkLocal(%08X) answered %d, want %d"
                 % (ip, got, want))

    WIRED = ctx.hw_wired

    def seeded(mac):
        c = ctx.cpu()
        for i, b in enumerate(mac):
            c.memory[SCRATCH + 0x200 + i] = b
        ok = ctx.call(c, "netsetmac", WIRED, SCRATCH + 0x200)
        if ok != 1:
            raise SystemExit("NetSetMac refused a good hardware address, so "
                             "the link-local picker cannot be seeded.")
        ctx.call(c, "netllseedfrommac", WIRED)
        return c

    def picks(mac, n):
        c = seeded(mac)
        return [ctx.call(c, "netllpick") & 0xFFFFFFFF for _ in range(n)]

    bench_mac = [0xDC, 0xA6, 0x32, 0x5B, 0x77, 0xC8]
    other_mac = [0xB8, 0x27, 0xEB, 0x01, 0x02, 0x03]
    a, b, c = picks(bench_mac, 6), picks(bench_mac, 6), picks(other_mac, 6)
    ctx.case(a == b, "NetLlPick is not repeatable from one hardware address: "
             "%s then %s [RFC 3927 s2.1]" % (a, b))
    ctx.case(a[0] != c[0], "two different hardware addresses pick the same "
             "first candidate (%08X)" % a[0])
    for ip in a + c:
        ctx.case(0xA9FE0100 <= ip <= 0xA9FEFEFF,
                 "NetLlPick produced %08X, outside the range RFC 3927 section "
                 "2.1 allows a host to select" % ip)
    ctx.case(len(set(a)) == len(a), "NetLlPick repeated an address inside six "
             "draws (%s)" % [hex(x) for x in a])
    c = seeded(bench_mac)
    delays = [ctx.call(c, "netllrandms", 1000, 2000) for _ in range(24)]
    ctx.case(all(1000 <= d <= 2000 for d in delays),
             "NetLlRandMs(1000, 2000) produced %s" % sorted(set(delays))[:6])
    ctx.case(len(set(delays)) >= 4, "NetLlRandMs answered %d distinct values "
             "out of 24 draws; the RFC's intervals are ranges on purpose"
             % len(set(delays)))
    ctx.case(ctx.call(c, "netllrandms", 500, 500) == 500,
             "NetLlRandMs does not answer the bound itself when the range is "
             "empty")

    ab = proc_body(eth_code, r"Procedure HwLinkAddressBound\(")
    if ctx.case(bool(ab), "RaspberryPi4/Board/eth.pi4 has no "
                "HwLinkAddressBound"):
        ctx.case("HwLinkOpen(" in ab, "HwLinkAddressBound does not re-derive "
                 "the interface preference order after a radio lease")
        a_open = eth_code.find("Procedure.i HwLinkOpen(")
        a_ab = eth_code.find("Procedure HwLinkAddressBound(")
        ctx.case(0 <= a_open < a_ab, "HwLinkAddressBound is defined before "
                 "HwLinkOpen, which it calls")

    nc_code = code_of(read("Anvil/Core/netconsole.pbi"))
    bu = proc_body(nc_code, r"Procedure\.i netcon_BuildUdp\(")
    ctx.case(bool(bu) and "netcon_BuildUdpTo(" in bu,
             "netcon_BuildUdp does not build through netcon_BuildUdpTo")
    # The frame is built in netcon_BuildUdpTo in Anvil main.
    bto = proc_body(nc_code, r"Procedure\.i netcon_BuildUdpTo\(")
    ctx.case(bool(bto) and re.search(r"While i < 60", bto or ""),
             "netcon_BuildUdpTo does not zero-fill its frame up to the "
             "60-octet 802.3 minimum, so a short console reply is a runt")

    board_code = code_of(read("RaspberryPi4/Board/board.pi4"))
    at_pr = board_code.find('Print("pmf> ")')
    at_fl = board_code.find("NetConsoleFlush()", at_pr) if at_pr >= 0 else -1
    at_rd = board_code.find("ReadLine()", at_pr) if at_pr >= 0 else -1
    ctx.case(at_pr >= 0 and 0 <= at_fl < at_rd,
             "RaspberryPi4/Board/board.pi4 does not flush the network console "
             "between printing 'pmf> ' and reading the line")


# =====================================================================
#  K. ONE ADDRESS PER INTERFACE - EXECUTED, NOT READ
# =====================================================================
#  In Anvil main the IP stack itself keeps one record per interface
#  (Anvil/Network/net.pbi: net_ifMac, net_ifIp, net_ifAlt, ... indexed by
#  kind, and every Net* call takes the kind). The old "point the one stack
#  at an interface" layer (NetIfActivate, NetUseIPv4, netif_active) no
#  longer exists, so the pairing is graded where it now lives: each
#  interface's own MAC and address, read back per kind, never displaced by
#  the other interface's.
#
#  What cannot run here: HwLinkReady(wired) reads the PHY over MMIO this
#  interpreter does not model, so readiness is driven through the radio,
#  whose answer is a global (gWifiKeyed).
def section_interfaces(ctx: Ctx) -> None:
    WIRED, WIFI = ctx.hw_wired, ctx.hw_wifi
    netif = read("Anvil/Core/netif.pbi")
    ADDR_LEASE = const(netif, "NET_ADDR_LEASE")
    ADDR_SAVED = const(netif, "NET_ADDR_SAVED")
    ADDR_LL = const(netif, "NET_ADDR_LINKLOCAL")
    IN_REPLY = const(read("Anvil/Network/net.pbi"), "NET_IN_REPLY")
    IN_UDP = const(read("Anvil/Network/net.pbi"), "NET_IN_UDP")
    OWNER_NET = const(read("Anvil/Core/netconsole.pbi"), "NETCON_OWNER_NET")
    sym = ctx.sym
    LL = quad(169, 254, 170, 250)
    LLMASK = quad(255, 255, 0, 0)
    HOMEIP = quad(192, 168, 1, 12)
    HOMEMASK = quad(255, 255, 255, 0)
    HOMEGW = quad(192, 168, 1, 2)
    SELF137 = quad(192, 168, 137, 1)
    MASK24 = quad(255, 255, 255, 0)
    WIRED_MAC = [0xDC, 0xA6, 0x32, 0x5B, 0x77, 0xC8]
    WIFI_MAC = [0xDC, 0xA6, 0x32, 0x5B, 0x77, 0xC9]
    PEER_MAC = [0x02, 0x11, 0x22, 0x33, 0x44, 0x55]
    call = ctx.call

    def be32(cpu, addr):
        return ((cpu.memory.get(addr, 0) << 24)
                | (cpu.memory.get(addr + 1, 0) << 16)
                | (cpu.memory.get(addr + 2, 0) << 8)
                | cpu.memory.get(addr + 3, 0))

    def mac_at(cpu, addr):
        return [cpu.memory.get(addr + i, 0) for i in range(6)]

    def two_link_cpu():
        """Both interfaces have a hardware address, reached through the
        seam exactly as the board hands them over."""
        cpu = ctx.cpu()
        for i, b in enumerate(WIRED_MAC):
            cpu.memory[SCRATCH + 0x200 + i] = b
        poke64(cpu, sym["global_ghwwiredmacptr"], SCRATCH + 0x200)
        wifi_mac = call(cpu, "hwlinkmacptr", WIFI)
        for i, b in enumerate(WIFI_MAC):
            cpu.memory[wifi_mac + i] = b
        return cpu

    # ---- NetAddrFromText, executed: three sources, three sentences ------
    seen = {}
    for src, ip in ((0, 0), (ADDR_LEASE, HOMEIP),
                    (ADDR_SAVED, quad(192, 168, 137, 2)), (ADDR_LL, LL)):
        cpu = two_link_cpu()
        if src:
            call(cpu, "netifset", WIRED, ip, MASK24 if src != ADDR_LL
                 else LLMASK, 0, src)
        seen[src] = read_cstring(cpu, call(cpu, "netaddrfromtext", WIRED))
    ctx.case(seen[0] == "", "NetAddrFromText answers %r for an interface with "
             "no address, and must answer nothing" % seen[0])
    ctx.case("lease" in seen[ADDR_LEASE].lower(),
             "NetAddrFromText does not call a lease a lease: %r"
             % seen[ADDR_LEASE])
    ctx.case("not a lease" in seen[ADDR_SAVED].lower(),
             "NetAddrFromText does not say a stored address is not a lease: "
             "%r" % seen[ADDR_SAVED])
    ctx.case("169.254" in seen[ADDR_LL],
             "NetAddrFromText says nothing about 169.254 for an address the "
             "board gave itself: %r" % seen[ADDR_LL])
    ctx.case(len({seen[ADDR_LEASE], seen[ADDR_SAVED], seen[ADDR_LL]}) == 3,
             "NetAddrFromText gives two address sources the same sentence; a "
             "lease, a stored address and a link-local address fail "
             "differently")

    # ---- K1. two interfaces addressed at once, neither displaces --------
    cpu = two_link_cpu()
    ok_w = call(cpu, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
    ok_r = call(cpu, "netifset", WIFI, HOMEIP, HOMEMASK, HOMEGW, ADDR_LEASE)
    ctx.case(ok_w == 1 and ok_r == 1,
             "NetIfSet refused one of two good records (wired %d, radio %d)"
             % (ok_w, ok_r))
    got = call(cpu, "netipv4", WIRED)
    ctx.case(got == LL, "THE RADIO'S LEASE TOOK THE CABLE'S ADDRESS: after "
             "binding 169.254.170.250 to the wired interface and 192.168.1.12 "
             "to the radio, NetIPv4(wired) answers %08X" % got)
    got = call(cpu, "netipv4", WIFI)
    ctx.case(got == HOMEIP, "NetIPv4(radio) answers %08X, want %08X"
             % (got, HOMEIP))
    got = call(cpu, "netifcount")
    ctx.case(got == 2, "NetIfCount answers %d with two interfaces addressed"
             % got)
    ctx.case(call(cpu, "netifsrc", WIRED) == ADDR_LL,
             "the wired record lost its source (link-local) when the radio "
             "bound its lease")
    ctx.case(call(cpu, "netifsrc", WIFI) == ADDR_LEASE,
             "the radio's record does not say its address is a lease")
    cpu = two_link_cpu()
    call(cpu, "netifset", WIFI, HOMEIP, HOMEMASK, HOMEGW, ADDR_LEASE)
    call(cpu, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
    ctx.case(call(cpu, "netipv4", WIFI) == HOMEIP,
             "the CABLE taking an address displaced the RADIO's")

    # ---- K2. each interface carries its own MAC with its own address ----
    for kind, want_ip, want_mac in ((WIRED, LL, WIRED_MAC),
                                    (WIFI, HOMEIP, WIFI_MAC)):
        ctx.case(call(cpu, "netipv4", kind) == want_ip,
                 "interface %d holds %08X, want %08X"
                 % (kind, call(cpu, "netipv4", kind), want_ip))
        call(cpu, "netgetmac", kind, SCRATCH + 0x300)
        got_mac = mac_at(cpu, SCRATCH + 0x300)
        ctx.case(got_mac == want_mac,
                 "interface %d carries the hardware address %s and its own is "
                 "%s. A MAC from one interface with the address of another is "
                 "filtered out by every switch and access point on the path"
                 % (kind, got_mac, want_mac))

    # ---- K3. the console answers on each interface, as that interface ---
    for kind, src_ip, src_mac, peer_ip in (
            (WIRED, LL, WIRED_MAC, quad(169, 254, 183, 67)),
            (WIFI, HOMEIP, WIFI_MAC, quad(192, 168, 1, 20))):
        cpu = two_link_cpu()
        call(cpu, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
        call(cpu, "netifset", WIFI, HOMEIP, HOMEMASK, HOMEGW, ADDR_LEASE)
        poke64(cpu, sym["global_gconon"], 1)
        poke64(cpu, sym["global_gconowner"], OWNER_NET)
        poke64(cpu, sym["global_gconpeerok"], 1)
        poke64(cpu, sym["global_gconpeerkind"], kind)
        poke64(cpu, sym["global_gconpeerdstip"], src_ip)
        poke64(cpu, sym["global_gconpeerip"], peer_ip)
        poke64(cpu, sym["global_gconpeerport"], 40000)
        for i, b in enumerate(PEER_MAC):
            cpu.memory[sym["global_gconpeermac"] + i] = b
        payload = b"hello world, a payload past the runt edge"
        for i, b in enumerate(payload):
            cpu.memory[SCRATCH + 0x400 + i] = b
        n = call(cpu, "netcon_buildudp", SCRATCH + 0x400, len(payload))
        tx = sym["global_gcontx"]
        if not ctx.case(n >= 60, "netcon_BuildUdp built a %d-octet frame for "
                        "the console on kind %d" % (n, kind)):
            continue
        ctx.case(mac_at(cpu, tx + 6) == src_mac,
                 "THE CONSOLE ANSWERS OUT OF THE WRONG INTERFACE: kind %d "
                 "replied with source MAC %s, its own is %s"
                 % (kind, mac_at(cpu, tx + 6), src_mac))
        got = be32(cpu, tx + 14 + 12)
        ctx.case(got == src_ip, "THE CONSOLE ANSWERS AS THE WRONG ADDRESS: a "
                 "peer that spoke to %08X on kind %d was replied to from %08X"
                 % (src_ip, kind, got))
        got = be32(cpu, tx + 14 + 16)
        ctx.case(got == peer_ip, "the console reply on kind %d is addressed "
                 "to %08X, want the peer at %08X" % (kind, got, peer_ip))
    # A short reply is padded with ZEROES to 60 octets.
    cpu.memory.update({tx + i: 0xEE for i in range(60)})
    n = call(cpu, "netcon_buildudp", SCRATCH + 0x400, 2)
    ctx.case(n == 60 and all(cpu.memory.get(tx + i, 0) == 0
                             for i in range(14 + 20 + 8 + 2, 60)),
             "a 2-byte console reply is %d octets or its pad is not zeroed; "
             "the 802.3 minimum is 60 and the pad must not carry the last "
             "frame's octets" % n)

    # ---- K4. a second address on one interface, and the source for a
    #      destination ---------------------------------------------------
    cpu = two_link_cpu()
    call(cpu, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
    ctx.case(call(cpu, "netifsetalt", WIRED, SELF137, MASK24) == 1,
             "NetIfSetAlt refused 192.168.137.1/24 as a second address on the "
             "wired interface")
    ctx.case(call(cpu, "netipv4", WIRED) == LL,
             "the alias replaced the primary address instead of joining it")
    ctx.case(call(cpu, "netipv4alt", WIRED) == SELF137,
             "the alias did not reach the IP layer")
    for dst, want, why in (
            (quad(192, 168, 137, 2), SELF137,
             "a host on the SERVED subnet must be answered as its neighbour"),
            (quad(169, 254, 183, 67), LL,
             "a host on the link-local subnet must be answered as its "
             "neighbour"),
            (quad(8, 8, 8, 8), LL,
             "off both subnets the source is the primary address")):
        got = call(cpu, "netsrcfor", WIRED, dst)
        ctx.case(got == want, "NetSrcFor(wired, %08X) answers %08X and must "
                 "answer %08X - %s" % (dst, got, want, why))
    ctx.case(call(cpu, "netonlink", WIRED, quad(192, 168, 137, 9)) == 1,
             "NetOnLink says a host on the alias's own subnet is off-link")
    # ---- K4b. a broadcast is answered as the asker's neighbour ----------
    for asker, want in ((quad(169, 254, 183, 67), LL),
                        (quad(192, 168, 137, 5), SELF137)):
        c2 = two_link_cpu()
        call(c2, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
        call(c2, "netifsetalt", WIRED, SELF137, MASK24)
        call(c2, "netifset", WIFI, HOMEIP, HOMEMASK, HOMEGW, ADDR_LEASE)
        f = SCRATCH + 0x600
        for i in range(80):
            c2.memory[f + i] = 0
        for i in range(6):
            c2.memory[f + i] = 0xFF
            c2.memory[f + 6 + i] = PEER_MAC[i]
        c2.memory[f + 12], c2.memory[f + 13] = 0x08, 0x00
        h = f + 14
        c2.memory[h + 0] = 0x45
        c2.memory[h + 3] = 0x1C
        c2.memory[h + 8] = 64
        c2.memory[h + 9] = 17
        for i in range(4):
            c2.memory[h + 12 + i] = (asker >> (8 * (3 - i))) & 0xFF
            c2.memory[h + 16 + i] = 0xFF
        ck = 0
        for i in range(0, 20, 2):
            ck += (c2.memory.get(h + i, 0) << 8) | c2.memory.get(h + i + 1, 0)
            ck = (ck & 0xFFFF) + (ck >> 16)
        ck = (~ck) & 0xFFFF
        c2.memory[h + 10], c2.memory[h + 11] = ck >> 8, ck & 0xFF
        u = h + 20
        c2.memory[u + 1] = 0x99
        c2.memory[u + 2], c2.memory[u + 3] = 0x15, 0xB3          # 5555
        c2.memory[u + 5] = 8
        call(c2, "netudpbind", WIRED, 5555)
        rc = call(c2, "netinput", WIRED, f, 42)
        if ctx.case(rc == IN_UDP, "a UDP broadcast from %08X to port 5555 on "
                    "the wired interface was not delivered (NetInput %d)"
                    % (asker, rc)):
            frm = call(c2, "netudprxfrom")
            got = call(c2, "netsrcfor", WIRED, frm)
            ctx.case(frm == asker and got == want,
                     "after a broadcast from %08X the board would answer FROM "
                     "%08X and the asker can only receive %08X. A broadcast "
                     "names neither of the board's addresses, so the asker's "
                     "own subnet has to decide" % (asker, got, want))
    call(cpu, "netifset", WIRED, quad(169, 254, 9, 9), LLMASK, 0, ADDR_LL)
    ctx.case(call(cpu, "netipv4alt", WIRED) == SELF137,
             "the served address was lost when the interface's primary "
             "address changed")

    # ---- K5. ARP defends both addresses, answering with the one asked ---
    for tpa, spa, why in (
            (LL, quad(169, 254, 183, 67), "the link-local address"),
            (SELF137, quad(192, 168, 137, 2), "the served address")):
        c3 = two_link_cpu()
        call(c3, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
        call(c3, "netifsetalt", WIRED, SELF137, MASK24)
        f = SCRATCH + 0x500
        for i in range(64):
            c3.memory[f + i] = 0
        for i in range(6):
            c3.memory[f + i] = 0xFF
            c3.memory[f + 6 + i] = PEER_MAC[i]
        c3.memory[f + 12], c3.memory[f + 13] = 0x08, 0x06
        a = f + 14
        c3.memory[a + 1] = 1
        c3.memory[a + 2], c3.memory[a + 3] = 0x08, 0x00
        c3.memory[a + 4], c3.memory[a + 5] = 6, 4
        c3.memory[a + 7] = 1
        for i in range(6):
            c3.memory[a + 8 + i] = PEER_MAC[i]
        for i in range(4):
            c3.memory[a + 14 + i] = (spa >> (8 * (3 - i))) & 0xFF
            c3.memory[a + 24 + i] = (tpa >> (8 * (3 - i))) & 0xFF
        rc = call(c3, "netinput", WIRED, f, 42)
        if ctx.case(rc == IN_REPLY, "an ARP request for %08X - %s - was not "
                    "answered (NetInput returned %d)" % (tpa, why, rc)):
            out = call(c3, "netoutbuf")
            got = be32(c3, out + 14 + 14)
            ctx.case(got == tpa, "the ARP reply for %08X announces %08X as the "
                     "sender protocol address" % (tpa, got))

    # ---- K6. the DHCP server exchange, end to end ------------------------
    dh = read("Anvil/Core/dhcpd.pbi")
    POOL_LO, POOL_HI = const(dh, "DHCPD_POOL_LO"), const(dh, "DHCPD_POOL_HI")
    ctx.case(const(dh, "DHCPD_SELF") == SELF137 and POOL_LO == quad(
        192, 168, 137, 2) and POOL_HI == quad(192, 168, 137, 20),
             "the DHCP server no longer serves 192.168.137.1 with the pool "
             ".2 to .20")
    DISCOVER, OFFER, REQUEST, ACK, NAK = 1, 2, 3, 5, 6     # RFC 2132 s9.6
    CLIENT_MAC = [0x02, 0xAB, 0xCD, 0xEF, 0x00, 0x01]

    def bootp(c, msg_type, req_ip=0, op=1, mac=None, xid=0x12345678):
        m = SCRATCH + 0x800
        for i in range(400):
            c.memory[m + i] = 0
        c.memory[m + 0] = op
        c.memory[m + 1] = 1
        c.memory[m + 2] = 6
        for i in range(4):
            c.memory[m + 4 + i] = (xid >> (8 * (3 - i))) & 0xFF
        for i, b in enumerate(mac or CLIENT_MAC):
            c.memory[m + 28 + i] = b
        for i, b in enumerate((0x63, 0x82, 0x53, 0x63)):
            c.memory[m + 236 + i] = b
        o = 240
        c.memory[m + o], c.memory[m + o + 1], c.memory[m + o + 2] = \
            53, 1, msg_type
        o += 3
        if req_ip:
            c.memory[m + o], c.memory[m + o + 1] = 50, 4
            for i in range(4):
                c.memory[m + o + 2 + i] = (req_ip >> (8 * (3 - i))) & 0xFF
            o += 6
        c.memory[m + o] = 255
        return m, o + 1

    def serving_cpu():
        c = two_link_cpu()
        call(c, "netifset", WIRED, LL, LLMASK, 0, ADDR_LL)
        call(c, "dhcpdstart", WIRED)
        return c

    def options(c, b, n):
        opts, i = {}, b + 240
        while i < b + n + 64 and c.memory.get(i, 0) != 255:
            if c.memory.get(i, 0) == 0:
                i += 1
                continue
            ln = c.memory.get(i + 1, 0)
            opts[c.memory.get(i, 0)] = [c.memory.get(i + 2 + j, 0)
                                        for j in range(ln)]
            i += 2 + ln
        return opts

    c = serving_cpu()
    ctx.case(call(c, "dhcpdon") == 1, "DhcpdStart refused the wired link, so "
             "a laptop set to DHCP at the other end of the cable gets nothing")
    ctx.case(call(c, "netipv4alt", WIRED) == SELF137,
             "the DHCP server did not take 192.168.137.1 as the interface's "
             "second address, so it serves an address it does not answer at")
    ctx.case(call(two_link_cpu(), "dhcpdstart", WIFI) == 0,
             "DhcpdStart accepted the radio, which is joined to somebody "
             "else's network")
    m, n = bootp(c, DISCOVER)
    if ctx.case(call(c, "dhcpdinput", WIRED, m, n, 0) == 1,
                "a DHCPDISCOVER was not answered at all"):
        out = call(c, "netoutbuf")
        b = out + 14 + 20 + 8
        ctx.case(c.memory.get(b, 0) == 2, "the OFFER is not a BOOTREPLY")
        offered = be32(c, b + 16)
        ctx.case(POOL_LO <= offered <= POOL_HI,
                 "the OFFER hands out %08X, outside the pool" % offered)
        ctx.case(be32(c, out + 14 + 12) == SELF137,
                 "the OFFER is not SOURCED from the server's own address, so "
                 "a client discards a reply whose source does not match the "
                 "server identifier inside it")
        opts = options(c, b, n)
        ctx.case(opts.get(53) == [OFFER], "the reply to a DISCOVER is not a "
                 "DHCPOFFER (option 53 = %r)" % opts.get(53))
        ctx.case(opts.get(1) == [255, 255, 255, 0], "the OFFER carries no "
                 "255.255.255.0 netmask (option 1 = %r)" % opts.get(1))
        ctx.case(opts.get(51) == [0, 0, 0x0E, 0x10], "the OFFER's lease is "
                 "not one hour (option 51 = %r)" % opts.get(51))
        ctx.case(6 not in opts, "the OFFER carries a DNS server option; this "
                 "board is not a resolver")
        m, n = bootp(c, REQUEST, req_ip=offered)
        if ctx.case(call(c, "dhcpdinput", WIRED, m, n, 0) == 1,
                    "a DHCPREQUEST for the address just offered was not "
                    "answered"):
            out = call(c, "netoutbuf")
            b = out + 14 + 20 + 8
            ctx.case(be32(c, b + 16) == offered, "the ACK hands out %08X "
                     "after offering %08X" % (be32(c, b + 16), offered))
            ctx.case(c.memory.get(b + 242, 0) == ACK,
                     "the reply to a REQUEST is not a DHCPACK")
            ctx.case(call(c, "dhcpdleased") == 1, "the server acknowledged a "
                     "lease and does not count it as handed out")
        m, n = bootp(c, DISCOVER)
        call(c, "dhcpdinput", WIRED, m, n, 0)
        out = call(c, "netoutbuf")
        ctx.case(be32(c, out + 14 + 20 + 8 + 16) == offered,
                 "a second DISCOVER from the same hardware address was "
                 "offered a different address")
        m, n = bootp(c, DISCOVER, mac=[0x02, 0x99, 0x88, 0x77, 0x66, 0x55])
        call(c, "dhcpdinput", WIRED, m, n, 0)
        out = call(c, "netoutbuf")
        ctx.case(be32(c, out + 14 + 20 + 8 + 16) != offered,
                 "two different machines were offered the same address")
    c = serving_cpu()
    m, n = bootp(c, REQUEST, req_ip=quad(10, 0, 0, 5))
    if ctx.case(call(c, "dhcpdinput", WIRED, m, n, 0) == 1,
                "a DHCPREQUEST outside the pool was ignored instead of NAK'd "
                "[RFC 2131 s4.3.2]"):
        out = call(c, "netoutbuf")
        ctx.case(c.memory.get(out + 14 + 20 + 8 + 242, 0) == NAK,
                 "the reply to a REQUEST outside the pool is not a DHCPNAK")

    # ---- K7. a real server ends the server role --------------------------
    c = serving_cpu()
    m, n = bootp(c, OFFER, op=2)
    call(c, "dhcpdinput", WIRED, m, n, quad(192, 168, 137, 254))
    ctx.case(call(c, "dhcpdon") == 0, "an OFFER from a REAL DHCP server on the "
             "segment did not end this board's server role")
    ctx.case(call(c, "netipv4alt", WIRED) == 0,
             "the board stopped serving and kept answering at 192.168.137.1")
    c = serving_cpu()
    m, n = bootp(c, OFFER, op=2)
    call(c, "dhcpdsawserver", m, n, SELF137)
    ctx.case(call(c, "dhcpdon") == 1, "the DHCP server stood down on hearing "
             "an OFFER from its OWN address")

    # ---- K8. the preference order ----------------------------------------
    c = two_link_cpu()
    poke64(c, sym["global_gwifikeyed"], 1)
    call(c, "netifset", WIFI, HOMEIP, HOMEMASK, HOMEGW, ADDR_LEASE)
    ctx.case(call(c, "netifpreferred") == WIFI, "with only the radio addressed "
             "and ready, NetIfPreferred does not answer the radio")
    call(c, "linksetpin", WIRED)
    ctx.case(call(c, "netifpreferred") == 0,
             "pinned to the wired interface with no usable wired address, "
             "NetIfPreferred fell back to the radio. A pin is an instruction")
    nif_code = code_of(netif)
    pref = proc_body(nif_code, r"Procedure\.i NetIfPreferred\(\)")
    ctx.case(bool(pref) and 0 <= pref.find("#HW_LINK_WIRED") <
             pref.find("#HW_LINK_WIFI"),
             "NetIfPreferred does not try the WIRED interface before the "
             "radio; the wire has priority and this is its one home")

    # ---- K9. every consumer of the wire parses as the arrival interface --
    nc_code = code_of(read("Anvil/Core/netconsole.pbi"))
    link_code = code_of(read("RaspberryPi4/Lib/link.pi4"))
    pump = proc_body(nc_code, r"Procedure netcon_PumpOne\(")
    ctx.case(bool(pump) and "HwLinkRecv(kind," in pump
             and "NetInput(kind," in pump,
             "the console pump does not hand NetInput the interface the frame "
             "was read from")
    lp = proc_body(link_code, r"Procedure\.i LinkPumpKind\(")
    ctx.case(bool(lp) and "HwLinkRecv(kind," in lp and "NetInput(kind," in lp,
             "LinkPumpKind hands NetInput a frame without the interface it "
             "arrived on; a frame judged against another interface's address "
             "is ignored")
    lpn = proc_body(link_code, r"Procedure\.i LinkPumpNet\(")
    ctx.case(bool(lpn) and "LinkPumpKind(" in lpn,
             "LinkPumpNet no longer goes through LinkPumpKind")
    callers = []
    for rel in ("Anvil/Core/netconsole.pbi", "RaspberryPi4/Lib/link.pi4",
                "RaspberryPi4/Lib/wifi.pi4", "Anvil/Core/netrecv.pbi",
                "Anvil/Core/net_cmd.pbi", "RaspberryPi4/Lib/tcp.pi4",
                "RaspberryPi4/Board/eth.pi4",
                "RaspberryPi4/Board/hw_link.pi4", "Anvil/Core/netll.pbi",
                "Anvil/Core/dhcpd.pbi"):
        n = len(re.findall(r"NetInput\s*\(", code_of(read(rel))))
        if n:
            callers.append((rel, n))
    unexpected = [c_ for c_ in callers if c_[0] not in (
        "Anvil/Core/netconsole.pbi", "RaspberryPi4/Lib/link.pi4",
        "RaspberryPi4/Lib/wifi.pi4")]
    ctx.case(not unexpected,
             "NetInput is called from %s as well; every caller has to pass the "
             "interface the frame arrived on, and a new one is a new place to "
             "forget it" % ", ".join("%s (%d)" % c_ for c_ in unexpected))
    outer = proc_body(nc_code, r"Procedure NetConsolePump\(\)")
    ctx.case(bool(outer) and "NetIfNext(" in outer,
             "NetConsolePump does not walk NetIfNext, so the console reads one "
             "interface while announcing two")


# =====================================================================
#  RULE 12 OVER THE ANVIL, PI 4 AND UNO Q SOURCES
# =====================================================================
#  No source names the one person behind this project or the language the
#  toolchain is written in, and no role noun stands in for that person.
#  Write what was decided, not who decided it.
#
#  THE WORDS THEMSELVES ARE NOT IN THIS REPOSITORY IN ANY FORM. They are
#  read at run time from the file named by PMF_ATTRIBUTION_WORDS, which
#  lives outside the tree. One entry per line, a flag and a word:
#
#      capitalised <word>   matched as a whole word written with a capital
#      capitals    <word>   matched as a whole word written in capitals
#      identifier  <word>   matched in any case, also inside identifiers
#
#  Blank lines and lines starting with # are ignored. With no such file the
#  word half of this section prints one line saying it was not run; the
#  role-noun half needs no list and always runs.
#  tools/a64/anvil_identity_sabotage.py control 9 plants every listed word
#  and requires this scan to go red.
WORDS_ENV = "PMF_ATTRIBUTION_WORDS"
WORD_FLAGS = ("capitalised", "capitals", "identifier")
ORIG_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def load_words():
    """[(flag, word)] from the external list, or None when there is none.
    A malformed list is an error, not an abstention."""
    path = os.environ.get(WORDS_ENV, "")
    if not path or not os.path.isfile(path):
        return None
    words = []
    for n, line in enumerate(pathlib.Path(path).read_text(
            encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] not in WORD_FLAGS or \
                not parts[1].isalpha():
            raise SystemExit("line %d of the %s word list is not '<%s> "
                             "<letters>', so the scan cannot be trusted."
                             % (n, WORDS_ENV, "|".join(WORD_FLAGS)))
        words.append((parts[0], parts[1].lower()))
    if not words:
        raise SystemExit("the %s word list is empty, so the scan would "
                         "examine nothing." % WORDS_ENV)
    return words


ROLE = re.compile(r"\b(the owner|an owner|owner's|owners'|the boss|boss's)\b",
                  re.I)

# A two-letter capitals entry is also a part suffix and a Bluetooth flag.
ABBR_EXEMPT = re.compile(r"328P/|packet-boundary", re.I)

# "owner" of a resource - a register, a contact, a lane, a binding, a
# snapshot - is not a person. Each entry is pinned by the wording the
# Anvil sources actually use, so a new sentence is judged on its own.
ROLE_EXEMPT = re.compile(
    r"owner-draw|ownerdraw|owner-drawn"
    r"|owner of the machine|an owner field|already has an owner"
    # the board's own end user, and a peripheral's IOMMU owner
    r"|a passphrase the owner|the owner writes|the owner may open"
    r"|description of the owner|ASK THE OWNER"
    r"|An owner then reads ITS OWN routed lane"
    r"|route one contact event\. Returns the owner"
    r"|not an owner id|An owner id"
    r"|One hit rectangle per owner, installed from that owner's own layout"
    r"|could not be given an owner; ten simultaneous contacts"
    r"|ONE RECTANGLE PER OWNER, FROM THAT OWNER'S LAYOUT"
    r"|Returns the owner the event was routed to"
    r"|NOT get an owner here"
    r"|a procedure that prints the owner|supplied by the owner"
    r"|prints the owner's name for the refusal sentence"
    r"|an owner that did not name itself"
    r"|calls the owner's own detach procedure"
    r"|The owner's pump hands"
    r"|holds one interface, so an owner is"
    r"|puts it in that owner's own lane"
    r"|Refuse another owner's secondary"
    r"|refused until the owner cancels or consumes completion"
    r"|overwrite the owner which holds the old snapshot"
    r"|THE OWNER GETS ITS OWN RELEASE"
    r"|Releasing the owner is what reopens the seam"
    r"|consume an owner byte already admitted"
    r"|restoration without replacing the owner"
    r"|dispatcher decides the owner from the real"
    r"|It returns the owner, so a test can state",
    re.I)


def scan_text(text: str, words) -> list[tuple[int, str, str]]:
    """Hits as (line, category, text). Categories are the entry's flag
    ("word-capitalised", ...) or "role"; `words` None skips the word half."""
    hits = []
    for i, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if words:
            orig = ORIG_TOKEN.findall(line)
            low = [t.lower() for t in orig]
            for flag, word in words:
                if flag == "identifier":
                    hit = any(word in t for t in low)
                elif flag == "capitalised":
                    hit = any(t[:1].isupper() and t.lower() == word
                              for t in orig)
                else:
                    hit = any(t.isupper() and t.lower() == word
                              for t in orig) and not ABBR_EXEMPT.search(line)
                if hit:
                    hits.append((i, "word-" + flag, line))
        if ROLE.search(line) and not ROLE_EXEMPT.search(line):
            hits.append((i, "role", line))
    return hits


def attribution_subset() -> int:
    words = load_words()
    subset = []
    for d in ("Anvil", "RaspberryPi4", "ArduinoQ", "tools/a64"):
        base = ROOT / d
        if base.is_dir():
            for ext in ("*.pi4", "*.pbi", "*.unoq"):
                subset += [p for p in base.rglob(ext)
                           if "Reference" not in p.parts
                           and not _is_scratch(p.relative_to(ROOT))]
    subset = sorted(set(subset))
    if len(subset) < 60:
        print("a64_anvil_check attribution: the subset came back with only %d "
              "files, so this examined nothing and has not passed."
              % len(subset))
        return 2
    bad = []
    for path in subset:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for ln, cat, line in scan_text(text, words):
            bad.append("  %-18s %s:%d  %s" % (cat, rel, ln, line.strip()[:80]))
    print()
    if words is None:
        print("a64_anvil_check attribution: word scan not run - %s names no "
              "word list." % WORDS_ENV)
    if bad:
        print("a64_anvil_check attribution: FAIL - %d lines across the Anvil, "
              "Pi 4 and UNO Q sources carry a listed word or a role noun for "
              "a person." % len(bad))
        for b in bad[:40]:
            print(b)
        return 1
    print("a64_anvil_check attribution: PASS - %d Anvil / Pi 4 / UNO Q sources, "
          "%sno role noun." % (len(subset), "no listed word (%d entries), "
                               % len(words) if words else ""))
    return 0


def attribution_self_test() -> list[str]:
    """The role matcher must catch and honour its exemptions, and each word
    rule must behave on invented stand-in words (the real list is proven by
    anvil_identity_sabotage.py control 9)."""
    bad = []
    if "role" not in [c for _, c, _ in scan_text("; the owner ruled.", None)]:
        bad.append("the rule-12 matcher missed a planted role hit")
    if scan_text("; An owner then reads ITS OWN routed lane.", None):
        bad.append("the rule-12 matcher flagged an exempt role line")
    fake = [("capitalised", "zorvek"), ("capitals", "qx"),
            ("identifier", "blimtango")]
    for text, want in (("; Zorvek said so.", "word-capitalised"),
                       ("; QX gets this wrong.", "word-capitals"),
                       ("x = MyBLIMTANGOLexer", "word-identifier")):
        if want not in [c for _, c, _ in scan_text(text, fake)]:
            bad.append("the rule-12 word rule %s missed its stand-in" % want)
    for text in ("; zorvek in lower case", "; qx = 1", "; 328P/QX"):
        if scan_text(text, fake):
            bad.append("the rule-12 word rules flagged %r" % text)
    return bad


# =====================================================================
#  MAIN
# =====================================================================
def main() -> int:
    global COMPILER, IMG, QIMG
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--work", default=None,
                    help="directory for the two images (default: a temporary "
                         "directory removed afterwards)")
    args = ap.parse_args()
    if not args.compiler:
        print("a64_anvil_check: no compiler was named. Pass --compiler with "
              "the path of PureMetalForge.exe, or set PMF_COMPILER.")
        return 2
    COMPILER = str(pathlib.Path(args.compiler).resolve())
    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="anvil-check-") as tmp:
        work = pathlib.Path(args.work).resolve() if args.work else \
            pathlib.Path(tmp)
        IMG = work / "anvilcheck.img"
        QIMG = work / "anvilcheck-q.img"
        rc = run_sections()
    return rc


def run_sections() -> int:
    ctx = Ctx()
    # The board files are read BEFORE they are built: counting a build may
    # raise a marker, and the image carries the number it was compiled with.
    ctx.board_text = {rel: read(rel) for rel in BOARD_FILES}
    ctx.load = load_addr(SOURCE)
    ctx.qload = load_addr(QSOURCE)
    section_build_markers(ctx)
    try:
        build()
        build_q()
    except SystemExit as error:
        for f in ctx.fails:
            print("  FAIL " + f)
        print("  FAIL %s" % error)
        print()
        print("a64_anvil_check: FAIL - a board did not build; %d source "
              "case(s) failed before it" % len(ctx.fails))
        return 1
    ctx.sym = read_sym(IMG)
    ctx.qsym = read_sym(QIMG)
    ctx.qcpu = make_cpu_for(QIMG, ctx.qload)
    hal = read("Anvil/Hal/hal.pbi")
    ctx.hw_wired = const(hal, "HW_LINK_WIRED")
    ctx.hw_wifi = const(hal, "HW_LINK_WIFI")
    for what in attribution_self_test():
        ctx.case(False, what)
    ctx.edges = window_edges(ctx)
    for section in (section_layout, section_parse, section_address,
                    section_i2c, section_info, section_build_number,
                    section_identity, section_width, section_netrecv,
                    section_netcon, section_static, section_linklocal,
                    section_interfaces):
        before = (ctx.cases, len(ctx.fails))
        section(ctx)
        print("[gate] %-22s %3d cases, %d failing"
              % (section.__name__[8:], ctx.cases - before[0],
                 len(ctx.fails) - before[1]), file=sys.stderr)

    print()
    rc = 0
    if ctx.fails:
        for f in ctx.fails:
            print("  FAIL " + f)
        print()
        print("a64_anvil_check: FAIL - %d of %d cases" % (len(ctx.fails),
                                                          ctx.cases))
        rc = 1
    else:
        print("a64_anvil_check: PASS - %d cases, every address computed here"
              % ctx.cases)
        print("           and not read out of the monitor")
        print()
        print("  NOT COVERED HERE: the network pump against a modelled MAC,")
        print("  PHY and server; the BSC controller end to end (a scan against")
        print("  real devices is silicon work); mm and nm, which read keys at a")
        print("  sub-prompt (their table rows are checked against each other);")
        print("  and which clock feeds the I2C divider, which was measured on")
        print("  the pin by RaspberryPi4/Examples/Diagnostics/pi4I2cScl.pi4.")
    return rc or attribution_subset()


if __name__ == "__main__":
    raise SystemExit(main())
