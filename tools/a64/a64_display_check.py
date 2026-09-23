#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/display.pi4 - the HDMI framebuffer.

There is no monitor and no VideoCore in this gate.  Both are modelled: a
PL011 that swallows characters, and a VideoCore property-mailbox firmware
that answers the framebuffer tags - CLAMPING the mode that is asked for and
returning a PADDED pitch, because those two cases break the arithmetic and a
model that answered "yes, 1920x1080, pitch 7680" would test nothing.

The program executed is RaspberryPi4/Examples/Diagnostics/pi4DisplayProbe.pi4,
built with the board's flags and run on tools/a64/a64_interp.py.  Its serial
output is captured and printed.

THE ONE RULE THAT MAKES THE MODEL WORTH HAVING
  A FRAMEBUFFER SET TAG ONLY COUNTS TOWARDS AN ALLOCATE THAT IS IN THE SAME
  MESSAGE, AFTER IT.  Anything else is discarded, and the tag's response
  reports the stale state the firmware still has.

  display.pi4 once sent seven single-tag messages.  Booted through U-Boot that
  worked; booted straight from the firmware it returned success and produced
  a 2 x 2 framebuffer with a pitch of 64 in front of a 1920 x 1080 panel.  A
  model that accumulated state across messages passed that library.  This
  model does not, and --mutate demonstrates it.

  The shape the library sends follows U-Boot v2025.01,
  arch/arm/mach-bcm283x/msg.c:
      :140-157  bcm2835_get_video_size()    one message, GET_PHYSICAL_W_H
      :35-47    struct msg_setup            ONE message, NINE tags
      :159-204  bcm2835_set_video_params()  fills them, sends once, and reads
                size, pitch, framebuffer address and size from that response

WHY THE HARNESS ASSERTS AS WELL AS THE PROGRAM
  A program that reads its own writes through its own address arithmetic
  agrees with itself by construction.  This file reaches into the modelled
  framebuffer at addresses IT computes from the pitch IT chose, and the
  strongest assertion is one the program cannot make: EVERY PADDING BYTE IS
  STILL ZERO.  The surface is 160 pixels wide at 4 bytes each on a pitch of
  704; a library that addressed rows as base + y*width*bpp would put row y
  into row y-1's padding.

TWO HDMI SOCKETS
  The modelled firmware has TWO displays with the DispmanX ids the real one
  uses - index 0 is id 2 (HDMI0), index 1 is id 7 (HDMI1) - different at every
  index, because sending an id where an index belongs is the mistake the
  driver invites.  The gate runs the probe twice:
  * the DEFAULT run selects nothing, and NO selection tag may go out.
  * the SELECTED run asks for display 1 first: three messages - the count,
    the query WITH the selection in front of it, then the selection followed
    by the same nine tags.  Every surface, geometry and glyph assertion must
    still pass.
  Whether a selection survives the end of a message is not stated by any
  source consulted, so the model treats it as message-scoped (the strict
  reading) and display.pi4 leads every framebuffer message with it.

THIRD-PARTY SOURCES ARE CITED, NOT COPIED.  The tag numbers the model answers
are PINNED below from two independent upstream headers, each value with the
line it came from, and the gate requires the two readings to agree before it
runs; the display-selection tags are pinned from a third header.  None of the
headers is part of this repository.  The model and mailbox.pi4 are therefore
independent readings: a number typed wrongly into mailbox.pi4 leaves the
model not recognising the tag, its response bit clear, and the transport
refusing - which the gate reports.

  python tools/a64/a64_display_check.py --compiler <PureMetalForge.exe>
  python tools/a64/a64_display_check.py --compiler <PureMetalForge.exe> --mutate
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB = ROOT / "RaspberryPi4" / "Lib" / "display.pi4"
MBXLIB = ROOT / "RaspberryPi4" / "Lib" / "mailbox.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4DisplayProbe.pi4"
DISPLAY_INCLUDE = 'XIncludeFile "RaspberryPi4/Lib/display.pi4"'

LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000

# ---------------------------------------------------------------------
#  THE PINNED TAG NUMBERS
# ---------------------------------------------------------------------
# KERNEL: Linux, include/soc/bcm2835/raspberrypi-firmware.h,
#         enum rpi_firmware_property_tag.
# UBOOT:  U-Boot v2025.01, arch/arm/mach-bcm283x/include/mach/mbox.h.
# Row: key -> ((kernel symbol, kernel line, value),
#              (U-Boot symbol, U-Boot line, value))
FIRMWARE_TAGS = {
    "ALLOCATE": (("RPI_FIRMWARE_FRAMEBUFFER_ALLOCATE", 97, 0x00040001),
                 ("BCM2835_MBOX_TAG_ALLOCATE_BUFFER", 270, 0x00040001)),
    "GETPHYS": (("RPI_FIRMWARE_FRAMEBUFFER_GET_PHYSICAL_WIDTH_HEIGHT", 99, 0x00040003),
                ("BCM2835_MBOX_TAG_GET_PHYSICAL_W_H", 313, 0x00040003)),
    "GETPITCH": (("RPI_FIRMWARE_FRAMEBUFFER_GET_PITCH", 104, 0x00040008),
                 ("BCM2835_MBOX_TAG_GET_PITCH", 410, 0x00040008)),
    "SETPHYS": (("RPI_FIRMWARE_FRAMEBUFFER_SET_PHYSICAL_WIDTH_HEIGHT", 120, 0x00048003),
                ("BCM2835_MBOX_TAG_SET_PHYSICAL_W_H", 315, 0x00048003)),
    "SETVIRT": (("RPI_FIRMWARE_FRAMEBUFFER_SET_VIRTUAL_WIDTH_HEIGHT", 121, 0x00048004),
                ("BCM2835_MBOX_TAG_SET_VIRTUAL_W_H", 335, 0x00048004)),
    "SETDEPTH": (("RPI_FIRMWARE_FRAMEBUFFER_SET_DEPTH", 122, 0x00048005),
                 ("BCM2835_MBOX_TAG_SET_DEPTH", 354, 0x00048005)),
    "SETORDER": (("RPI_FIRMWARE_FRAMEBUFFER_SET_PIXEL_ORDER", 123, 0x00048006),
                 ("BCM2835_MBOX_TAG_SET_PIXEL_ORDER", 371, 0x00048006)),
    "SETALPHA": (("RPI_FIRMWARE_FRAMEBUFFER_SET_ALPHA_MODE", 124, 0x00048007),
                 ("BCM2835_MBOX_TAG_SET_ALPHA_MODE", 391, 0x00048007)),
    "SETOFFSET": (("RPI_FIRMWARE_FRAMEBUFFER_SET_VIRTUAL_OFFSET", 125, 0x00048009),
                  ("BCM2835_MBOX_TAG_SET_VIRTUAL_OFFSET", 426, 0x00048009)),
    "SETOVERSCAN": (("RPI_FIRMWARE_FRAMEBUFFER_SET_OVERSCAN", 126, 0x0004800A),
                    ("BCM2835_MBOX_TAG_SET_OVERSCAN", 445, 0x0004800A)),
}

# THE DISPLAY-SELECTION TAGS come from a THIRD header: the raspberrypi/linux
# downstream copy of include/soc/bcm2835/raspberrypi-firmware.h, a superset
# of the upstream enum.  When these were pinned, neither of the two headers
# above carried DISPLAY_NUM, NUM_DISPLAYS or GET_DISPLAY_ID at all: upstream
# Linux has no firmware-KMS driver and U-Boot never selects a display.  That
# absence is why a Pi 4 with two HDMI sockets once had a display library that
# could not name one, and it is why a third citation exists.
DISPLAY_TAGS = {
    "GETDISPLAYID": ("RPI_FIRMWARE_FRAMEBUFFER_GET_DISPLAY_ID", 122, 0x00040016),
    "SETDISPLAYNUM": ("RPI_FIRMWARE_FRAMEBUFFER_SET_DISPLAY_NUM", 123, 0x00048013),
    "GETNUMDISPLAYS": ("RPI_FIRMWARE_FRAMEBUFFER_GET_NUM_DISPLAYS", 124, 0x00040013),
}

# The pixel-order and alpha-mode VALUES, from the same U-Boot mbox.h.
UBOOT_VALUES = {
    "ORDER_BGR": ("BCM2835_MBOX_PIXEL_ORDER_BGR", 373, 0),
    "ORDER_RGB": ("BCM2835_MBOX_PIXEL_ORDER_RGB", 374, 1),
    "ALPHA_IGNORED": ("BCM2835_MBOX_ALPHA_MODE_IGNORED", 395, 2),
}


def firmware_tags() -> dict[str, int]:
    """The ten framebuffer tag numbers, both readings required to agree."""
    out = {}
    for key, ((ksym, kline, kv), (usym, uline, uv)) in FIRMWARE_TAGS.items():
        if kv != uv:
            raise SystemExit(
                f"The two pinned readings disagree about {key}: the kernel "
                f"header's {ksym} (line {kline}) is ${kv:08X} but U-Boot's "
                f"{usym} (line {uline}) is ${uv:08X}.")
        out[key] = kv
    return out


def display_tags() -> dict[str, int]:
    """The three display-selection tag numbers.

    They must not collide with any framebuffer tag: a pinned value that did
    would make the model answer a selection as a framebuffer operation.
    """
    out = {k: v for k, (_sym, _line, v) in DISPLAY_TAGS.items()}
    clash = set(out.values()) & set(firmware_tags().values())
    if clash:
        raise SystemExit("A pinned display-selection tag collides with a "
                         f"framebuffer tag: {sorted(hex(c) for c in clash)}.")
    return out


def uboot_value(key: str) -> int:
    return UBOOT_VALUES[key][2]


# ---------------------------------------------------------------------
#  THE MODELLED BOARD
# ---------------------------------------------------------------------
# The PL011: bus $7E201000 through bcm2711.dtsi's soc ranges is ARM $FE201000.
UART_DR = 0xFE201000
UART_FR = 0xFE201018

# The VideoCore mailbox, from bcm283x.dtsi through the same ranges.
MBX_READ = 0xFE00B880
MBX_STATUS0 = 0xFE00B898
MBX_WRITE = 0xFE00B8A0
MBX_STATUS1 = 0xFE00B8B8
MBX_EMPTY = 0x40000000
MBX_CHANNEL = 8
BUS_OFFSET = 0xC0000000
RESP_BIT = 0x80000000

# CNTFRQ_EL0, set by the firmware's armstub from OSC_FREQ, 54000000 on BCM2711.
CNTFRQ = 54_000_000
# Interpreter steps per counter tick.  Only matters in that the counter
# ADVANCES.
STEPS_PER_TICK = 16

# THE PANEL and THE MODE THE FIRMWARE WILL ACTUALLY ALLOCATE are different
# numbers.  PANEL_* is what get-physical reports; MODE_* is the largest the
# modelled firmware hands over.  The gap is the clamp - the board's firmware
# really does return less than it is asked for (1824 x 984 out of 1920 x
# 1080).  Small, because every instruction is interpreted.
PANEL_W = 192
PANEL_H = 112
MODE_W = 160
MODE_H = 96
MODE_DEPTH = 32
PAD = 64                       # bytes of padding on every row
PITCH = MODE_W * 4 + PAD       # 704, and NOT 640
FB_ARM = 0x1E000000            # above the probe's $4000000 safety floor
FB_BUS = FB_ARM + BUS_OFFSET
FB_SIZE = PITCH * MODE_H

# THE STATE BEFORE ANYBODY CONFIGURES IT - what makes the gate able to fail.
# Straight from the firmware, a set-physical sent alone answered 2 x 2 and a
# get-pitch alone answered 64.
STALE_W = 2
STALE_H = 2
STALE_DEPTH = 16
STALE_PITCH = 64
# Overscan the firmware is already carrying; U-Boot zeroes all four
# explicitly (msg.c:182-186).
STALE_OVERSCAN = (8, 8, 8, 8)
# A pixel order left the other way round by an earlier boot: order 1 under
# U-Boot, order 0 booting direct.
STALE_ORDER = 1
STALE_ALPHA = 0

SAFE_FLOOR = 0x4000000

# The nine tags of the combined message, in bcm2835_set_video_params()'s
# order (msg.c:167-189).
UBOOT_ORDER = ["SETPHYS", "SETVIRT", "SETDEPTH", "SETORDER", "SETALPHA",
               "SETOFFSET", "SETOVERSCAN", "ALLOCATE", "GETPITCH"]

# TWO DISPLAYS.  The ids are the fixed per-socket identities in the downstream
# kernel's vc4_firmware_kms.c: 2 is HDMI0 and 7 is HDMI1.
NUM_DISPLAYS = 2
DISPLAY_IDS = [2, 7]


class Firmware:
    """The VideoCore, as far as the property channel is concerned.

    The framebuffer set-tags accumulate in ONE property message, and an
    ALLOCATE commits what that message accumulated BEFORE IT, falling back
    to the existing state for anything it did not set.  A message with no
    ALLOCATE changes nothing and its set-tags answer with the stale state.
    GET_PHYSICAL describes the DISPLAY, not the buffer, so it always answers
    the panel's real mode.  The allocate CLAMPS and reports success.
    """

    def __init__(self, tags: dict[str, int]) -> None:
        self.tags = tags
        self.by_number = {v: k for k, v in tags.items()}
        self.act_w = STALE_W
        self.act_h = STALE_H
        self.act_depth = STALE_DEPTH
        self.act_pitch = STALE_PITCH
        self.act_over = STALE_OVERSCAN
        self.act_order = STALE_ORDER
        self.act_alpha = STALE_ALPHA
        self.act_offset = (0, 0)
        self.allocated = False
        self.fb_base = 0
        self.fb_size = 0
        self.messages: list[list[str]] = []
        self.seen: list[str] = []
        self.unknown: list[int] = []
        self.requests: dict[str, list[int]] = {}
        self.commits = 0
        # The display in force is MESSAGE-SCOPED - a modelling choice, the
        # strict one.
        self.selections: list[int | None] = []
        self.alloc_display: int | None = None
        self.badindex: list[int] = []

    def _commit(self, txn: dict) -> None:
        w, h = txn.get("phys", (self.act_w, self.act_h))
        w = min(w, MODE_W)
        h = min(h, MODE_H)
        over = txn.get("over", self.act_over)
        w = max(0, w - over[2] - over[3])
        h = max(0, h - over[0] - over[1])
        depth = txn.get("depth", self.act_depth)
        if depth not in (16, 32):
            depth = MODE_DEPTH
        self.act_w, self.act_h = w, h
        self.act_depth = depth
        self.act_over = over
        self.act_order = txn.get("order", self.act_order)
        self.act_alpha = txn.get("alpha", self.act_alpha)
        self.act_offset = txn.get("offset", self.act_offset)
        if w > 0 and h > 0:
            self.act_pitch = w * (depth // 8) + PAD
            self.fb_base = FB_BUS
            self.fb_size = self.act_pitch * h
        else:
            self.act_pitch = STALE_PITCH
            self.fb_base = FB_BUS
            self.fb_size = 0
        self.allocated = True
        self.commits += 1

    def message(self, entries):
        """One whole property message. Returns a response per tag; None
        means "this firmware does not know that tag"."""
        txn: dict = {}
        resp = [None] * len(entries)
        deferred: list[int] = []
        alloc_here = False
        cur_display: int | None = None

        for i, (name, vals) in enumerate(entries):
            if name is None:
                continue
            if name == "SETDISPLAYNUM":
                # An INDEX into the display list, not a DispmanX id.
                cur_display = vals[0]
                if not 0 <= cur_display < NUM_DISPLAYS:
                    self.badindex.append(cur_display)
                # The reply is not established by any source consulted; it
                # is echoed only so the response bit can be set, and nothing
                # asserts it.
                resp[i] = [vals[0]]
            elif name == "GETNUMDISPLAYS":
                resp[i] = [NUM_DISPLAYS]
            elif name == "GETDISPLAYID":
                idx = vals[0]
                if 0 <= idx < NUM_DISPLAYS:
                    resp[i] = [DISPLAY_IDS[idx]]
                else:
                    self.badindex.append(idx)
                    resp[i] = [idx]
            elif name == "GETPHYS":
                resp[i] = [PANEL_W, PANEL_H]
            elif name == "SETPHYS":
                txn["phys"] = (vals[0], vals[1])
                deferred.append(i)
            elif name == "SETVIRT":
                txn["virt"] = (vals[0], vals[1])
                deferred.append(i)
            elif name == "SETDEPTH":
                txn["depth"] = vals[0]
                deferred.append(i)
            elif name == "SETORDER":
                txn["order"] = vals[0]
                deferred.append(i)
            elif name == "SETALPHA":
                txn["alpha"] = vals[0]
                deferred.append(i)
            elif name == "SETOFFSET":
                txn["offset"] = (vals[0], vals[1])
                deferred.append(i)
            elif name == "SETOVERSCAN":
                txn["over"] = (vals[0], vals[1], vals[2], vals[3])
                deferred.append(i)
            elif name == "ALLOCATE":
                self._commit(txn)
                alloc_here = True
                self.alloc_display = cur_display
                resp[i] = [self.fb_base, self.fb_size]
            elif name == "GETPITCH":
                resp[i] = [self.act_pitch if alloc_here else STALE_PITCH]
            else:
                resp[i] = None

        for i in deferred:
            name = entries[i][0]
            if name in ("SETPHYS", "SETVIRT"):
                resp[i] = [self.act_w, self.act_h]
            elif name == "SETDEPTH":
                resp[i] = [self.act_depth]
            elif name == "SETORDER":
                resp[i] = [self.act_order]
            elif name == "SETALPHA":
                resp[i] = [self.act_alpha]
            elif name == "SETOFFSET":
                resp[i] = list(self.act_offset)
            elif name == "SETOVERSCAN":
                resp[i] = list(self.act_over)
        self.selections.append(cur_display)
        return resp


class Board:
    """Everything the image can touch that is not DRAM."""

    def __init__(self, cpu: A64, fw: Firmware) -> None:
        self.cpu = cpu
        self.fw = fw
        self.uart = bytearray()
        self.reply: int | None = None
        self.steps = 0

    def mailbox_write(self, msg: int) -> None:
        """Parse a whole property buffer, answer it, write it back.  Every
        structural rule is checked and a violation stops the run."""
        chan = msg & 0xF
        if chan != MBX_CHANNEL:
            raise SystemExit(f"The image used mailbox channel {chan}, not 8.")
        bus = msg & ~0xF
        arm = bus - BUS_OFFSET
        if not 0 <= arm < 0x40000000:
            raise SystemExit(
                f"The buffer bus address ${bus:08X} is not in the dma-ranges "
                f"window; its ARM address would be ${arm:X}.")
        ld = self.cpu.load
        st = self.cpu.store

        total = ld(arm + 0, 4)
        if total < 12 or total % 4 or total > 4096:
            raise SystemExit(f"The property buffer size word is {total}.")
        code = ld(arm + 4, 4)
        if code != 0:
            raise SystemExit(
                f"The request code word was ${code:08X}, not 0 "
                "(the property channel sends a request code of zero).")

        parsed = []
        off = 8
        while True:
            if off + 4 > total:
                raise SystemExit("The tag list ran past the declared buffer "
                                 "size with no end tag.")
            tag = ld(arm + off, 4)
            if tag == 0:
                break
            if off + 12 > total:
                raise SystemExit(f"The tag header at +{off} runs past the buffer.")
            valbuf = ld(arm + off + 4, 4)
            vallen = ld(arm + off + 8, 4)
            if valbuf % 4:
                raise SystemExit(
                    f"Tag ${tag:08X} declares a {valbuf}-byte value buffer; "
                    "the firmware processes value buffers a word at a time.")
            if off + 12 + valbuf > total:
                raise SystemExit(
                    f"Tag ${tag:08X} at +{off} has a {valbuf}-byte value "
                    f"buffer that runs past the {total}-byte buffer.")
            if vallen & RESP_BIT:
                raise SystemExit(f"Tag ${tag:08X} arrived with the RESPONSE bit "
                                 "already set in its length word.")
            if vallen > valbuf:
                raise SystemExit(f"Tag ${tag:08X} says {vallen} request bytes in "
                                 f"a {valbuf}-byte value buffer.")
            words = [ld(arm + off + 12 + i * 4, 4) for i in range(valbuf // 4)]
            parsed.append((off, tag, valbuf, words))
            off += 12 + valbuf
        if not parsed:
            raise SystemExit("A property message arrived with no tags in it.")

        entries = []
        for _o, tag, _vb, words in parsed:
            name = self.fw.by_number.get(tag)
            if name is None:
                self.fw.unknown.append(tag)
            else:
                self.fw.requests[name] = list(words)
            entries.append((name, words))

        responses = self.fw.message(entries)

        names = [n if n is not None else f"${t:08X}"
                 for (n, _), (_o, t, _vb, _w) in zip(entries, parsed)]
        self.fw.messages.append(names)
        self.fw.seen.extend(n for n in names if not n.startswith("$"))

        for (o, _tag, valbuf, _w), resp in zip(parsed, responses):
            if resp is None:
                st(arm + o + 8, 0, 4)
                continue
            n = 0
            for i, v in enumerate(resp):
                if i * 4 < valbuf:
                    st(arm + o + 12 + i * 4, v & 0xFFFFFFFF, 4)
                    n = i + 1
            st(arm + o + 8, RESP_BIT | (n * 4), 4)
        st(arm + 4, 0x80000000, 4)
        self.reply = msg


def build(compiler: str, source: pathlib.Path, out: pathlib.Path) -> dict[str, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [compiler, "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out), "-s"]
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.is_file():
        raise SystemExit(f"The probe {source.name} did not build:\n" + r.stdout)
    syms = {}
    for line in out.with_suffix(".img.sym").read_text(
            encoding="utf-8-sig").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            syms[k] = int(v)
    return syms


def run(img: pathlib.Path, fw: Firmware, limit: int) -> tuple[A64, Board]:
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    lr = 0xDEADBEE0
    cpu.x[30] = lr

    board = Board(cpu, fw)
    mem = cpu.memory

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE: this closure replaces A64.load, so the guard
        # has to be called here.  With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a runaway on the part.
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return 0
            if addr == MBX_STATUS1:
                return 0
            if addr == MBX_STATUS0:
                return 0 if board.reply is not None else MBX_EMPTY
            if addr == MBX_READ:
                r = board.reply
                if r is None:
                    raise SystemExit("The image read an empty mailbox.")
                board.reply = None
                return r
            raise SystemExit(f"The image read unmodelled MMIO at ${addr:08X}.")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR:
                board.uart.append(value & 0xFF)
                return
            if addr == MBX_WRITE:
                board.mailbox_write(value & 0xFFFFFFFF)
                return
            raise SystemExit(f"The image wrote unmodelled MMIO at ${addr:08X}.")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    # The two counter registers mailbox.pi4 reads, modelled in the board:
    #   CNTFRQ_EL0 -> $D53BE000, CNTPCT_EL0 -> $D53BE020 (MRS Xt, <sysreg>)
    plain_step = A64.step.__get__(cpu)

    def step() -> None:
        board.steps += 1
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = board.steps // STEPS_PER_TICK
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step

    for _ in range(limit):
        if cpu.pc == lr:
            return cpu, board
        step()
    raise SystemExit(f"The probe never returned to its loader "
                     f"({board.steps} steps).\n" + board.uart.decode("latin-1"))


def px(cpu: A64, x: int, y: int) -> int:
    """The pixel at (x, y), addressed from THIS file's pitch."""
    a = FB_ARM + y * PITCH + x * 4
    return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(4))


def rgb(r: int, g: int, b: int) -> int:
    """DisplayRGB()'s packing, restated here rather than imported."""
    return (0xFF << 24) | (r << 16) | (g << 8) | b


CHECKS = [0]


def _ck(out, fails):
    def ck(cond, msg):
        CHECKS[0] += 1
        out.append(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails.append(msg)
    return ck


def check_surface(cpu: A64, out: list[str]) -> list[str]:
    """The assertions the running program cannot make about itself."""
    fails: list[str] = []
    ck = _ck(out, fails)

    top = FB_ARM + FB_SIZE
    strays = [a for a in cpu.memory if a >= SAFE_FLOOR and not (FB_ARM <= a < top)]
    ck(not strays,
       "every high write landed inside the surface"
       + ("" if not strays else f" ({len(strays)} strays, first ${min(strays):X})"))

    # THE PADDING IS UNTOUCHED - the shear assertion, and the one that
    # catches a geometry the library agrees with and the harness does not.
    dirty = 0
    first = None
    for y in range(MODE_H):
        rowpad = FB_ARM + y * PITCH + MODE_W * 4
        for i in range(PAD):
            if cpu.memory.get(rowpad + i, 0) != 0:
                dirty += 1
                if first is None:
                    first = (y, i)
    ck(dirty == 0,
       f"all {MODE_H * PAD} padding bytes are still zero"
       + ("" if not dirty else f" ({dirty} written, first row {first[0]} byte {first[1]})"))

    # THE PICTURE, at coordinates recomputed here from the mode.
    w, h = MODE_W, MODE_H
    rx, ry, rw, rh = w // 12, h // 12, w // 6, h // 8
    gap = rw // 4
    field = rgb(0, 0, 40)
    red, green, blue, white = rgb(255, 0, 0), rgb(0, 255, 0), rgb(0, 0, 255), rgb(255, 255, 255)
    out.append(f"  --   layout {rx},{ry} {rw}x{rh} gap {gap}")

    ck(px(cpu, rx + rw // 2, ry + rh // 2) == red, "red rectangle is where it was put")
    ck(px(cpu, rx + rw + gap + rw // 2, ry + rh // 2) == green, "green rectangle")
    ck(px(cpu, rx + 2 * (rw + gap) + rw // 2, ry + rh // 2) == blue, "blue rectangle")
    ck(px(cpu, rx, ry + rh + gap + rh // 2) == white, "white rectangle")
    ck(px(cpu, rx + rw, ry + rh // 2) == field, "the red fill stopped at its right edge")
    ck(px(cpu, rx - 2, ry - 2) == white, "the frame's top-left corner")
    ck(px(cpu, rx - 1, ry - 1) == field, "the frame is one pixel thick")

    bad = 0
    for y in range(ry, ry + rh):
        for x in range(rx, rx + rw):
            if px(cpu, x, y) != red:
                bad += 1
    ck(bad == 0, f"all {rw * rh} pixels of the red rectangle"
       + ("" if not bad else f" ({bad} wrong)"))
    return fails


def check_glyph(cpu: A64, blob: bytes, syms: dict[str, int], out: list[str]) -> list[str]:
    """Compare the drawn 'H' against the font bytes in the IMAGE FILE."""
    fails: list[str] = []
    ck = _ck(out, fails)
    cw, chh = 8, 16
    gx, gy = MODE_W - cw - 1, MODE_H - chh - 1
    base = syms["dsp_font8x16"]
    ch = ord("H")
    white, black = rgb(255, 255, 255), rgb(0, 0, 0)
    bad = []
    for r in range(chh):
        bits = blob[base + (ch - 32) * 16 + r]
        for c in range(cw):
            want = white if (bits & (128 >> c)) else black
            got = px(cpu, gx + c, gy + r)
            if got != want:
                bad.append((c, r, got, want))
    ck(not bad, f"the drawn 'H' matches the font table in the image, all "
       f"{cw * chh} pixels" + ("" if not bad else f" ({len(bad)} wrong, first {bad[0][:2]})"))
    return fails


def check_protocol(fw: Firmware, vals: dict[str, int], out: list[str],
                   select: int | None = None) -> list[str]:
    """WHAT WENT ON THE WIRE, AND IN HOW MANY MESSAGES.

    select is the display index the run was expected to ask for, or None.
    THE None CASE IS THE ANTI-REGRESSION CASE: no selection tag anywhere.
    """
    fails: list[str] = []
    ck = _ck(out, fails)
    msgs = fw.messages

    if select is None:
        ck(len(msgs) == 2,
           f"the firmware received exactly TWO messages (got {len(msgs)}: "
           + " | ".join(" ".join(m) for m in msgs) + ")")
        ck(bool(msgs) and msgs[0] == ["GETPHYS"],
           "message 1 is the get-physical query, alone"
           + ("" if not msgs else f" (got {' '.join(msgs[0])})"))
        combined = msgs[1] if len(msgs) > 1 else []
        ck(combined == UBOOT_ORDER,
           "message 2 carries all nine tags in U-Boot's order (msg.c:167-189)"
           + ("" if combined == UBOOT_ORDER
              else f"\n         got  {' '.join(combined)}"
                   f"\n         want {' '.join(UBOOT_ORDER)}"))
        ck("SETDISPLAYNUM" not in fw.seen,
           "no display was chosen, so NO selection tag went out at all")
        ck(all(s is None for s in fw.selections),
           f"no message selected a display (got {fw.selections})")
        ck(fw.alloc_display is None,
           "the allocate committed against the firmware's own choice of "
           f"display (got {fw.alloc_display})")
    else:
        ck(len(msgs) == 3,
           f"the firmware received exactly THREE messages (got {len(msgs)}: "
           + " | ".join(" ".join(m) for m in msgs) + ")")
        ck(bool(msgs) and msgs[0] == ["GETNUMDISPLAYS"],
           "message 1 asks how many displays there are, alone"
           + ("" if not msgs else f" (got {' '.join(msgs[0])})"))
        query = msgs[1] if len(msgs) > 1 else []
        want_query = ["SETDISPLAYNUM", "GETPHYS"]
        ck(query == want_query,
           "message 2 is the get-physical query WITH the selection in front "
           "of it" + ("" if query == want_query else f" (got {' '.join(query)})"))
        combined = msgs[2] if len(msgs) > 2 else []
        want_comb = ["SETDISPLAYNUM"] + UBOOT_ORDER
        ck(combined == want_comb,
           "message 3 is the selection followed by all nine tags in U-Boot's "
           "order" + ("" if combined == want_comb
                      else f"\n         got  {' '.join(combined)}"
                           f"\n         want {' '.join(want_comb)}"))
        ck(fw.selections[1:] == [select, select],
           f"both framebuffer messages selected display {select} "
           f"(got {fw.selections})")
        ck(fw.alloc_display == select,
           f"the allocate committed against display {select} "
           f"(got {fw.alloc_display})")
        sel = fw.requests.get("SETDISPLAYNUM")
        ck(sel == [select],
           f"set-display-num carried the INDEX {select}, not the DispmanX id "
           f"{DISPLAY_IDS[select]} (got {sel})")

    ck(not fw.badindex,
       "every display index the library sent was inside the list the "
       "firmware reported" + ("" if not fw.badindex else f" ({fw.badindex})"))

    if "ALLOCATE" in combined:
        for earlier in ("SETPHYS", "SETVIRT", "SETDEPTH", "SETORDER",
                        "SETALPHA", "SETOFFSET", "SETOVERSCAN"):
            if earlier in combined:
                ck(combined.index("ALLOCATE") > combined.index(earlier),
                   f"allocate comes after {earlier.lower()} in the message")
        if "GETPITCH" in combined:
            ck(combined.index("GETPITCH") > combined.index("ALLOCATE"),
               "get-pitch comes after allocate in the message")

    over = fw.requests.get("SETOVERSCAN")
    ck(over == [0, 0, 0, 0],
       "set-overscan asked for ZERO on all four edges (msg.c:183-186)"
       + ("" if over == [0, 0, 0, 0] else f" (got {over})"))
    alloc = fw.requests.get("ALLOCATE") or []
    alloc_ok = len(alloc) >= 1 and alloc[0] == 0x100 and all(w == 0 for w in alloc[1:])
    ck(alloc_ok,
       "allocate asked for $100 alignment (msg.c:188), with the rest of its "
       "value buffer zeroed" + ("" if alloc_ok else f" (got {alloc})"))
    alpha = fw.requests.get("SETALPHA")
    ck(alpha == [vals["ALPHA_IGNORED"]],
       f"set-alpha-mode asked for IGNORED ({vals['ALPHA_IGNORED']})"
       + ("" if alpha == [vals["ALPHA_IGNORED"]] else f" (got {alpha})"))
    order = fw.requests.get("SETORDER")
    ck(order == [vals["ORDER_BGR"]],
       f"set-pixel-order asked for BGR ({vals['ORDER_BGR']})"
       + ("" if order == [vals["ORDER_BGR"]] else f" (got {order})"))
    offs = fw.requests.get("SETOFFSET")
    ck(offs == [0, 0], "set-virtual-offset asked for (0,0) - no pan"
       + ("" if offs == [0, 0] else f" (got {offs})"))

    ck(fw.act_over == (0, 0, 0, 0),
       f"the firmware's overscan ended at zero (got {fw.act_over}; it was "
       f"carrying {STALE_OVERSCAN} before)")
    ck(fw.act_order == vals["ORDER_BGR"],
       f"the firmware's pixel order ended at BGR (got {fw.act_order}; it was "
       f"carrying {STALE_ORDER} before)")
    ck(fw.act_alpha == vals["ALPHA_IGNORED"],
       f"the firmware's alpha mode ended at IGNORED (got {fw.act_alpha})")
    ck(fw.commits == 1,
       f"exactly one allocate committed a transaction (got {fw.commits})")
    ck((fw.act_w, fw.act_h) == (MODE_W, MODE_H),
       f"the firmware settled on {MODE_W}x{MODE_H} (got {fw.act_w}x{fw.act_h})")
    ck(not fw.unknown,
       "the firmware recognised every tag it was sent"
       + ("" if not fw.unknown else f" ({[hex(t) for t in fw.unknown]})"))
    return fails


# ---------------------------------------------------------------------
#  THE MUTANTS - every one is a defect this library had or the defect its
#  header warns about.  Each is applied to a TEMPORARY COPY of display.pi4
#  and a copy of the probe includes it; RaspberryPi4/ is never written.
#  An anchor that does not match exactly once is an error, not a skip.
# ---------------------------------------------------------------------
_ADD_ALLOC = "  DspAdd(#DSP_TAG_ALLOCATE,    4,  8)\n"
_ADD_PITCH = "  DspAdd(#DSP_TAG_GETPITCH,    0,  4)\n"
_ADD_OVER = "  DspAdd(#DSP_TAG_SETOVERSCAN, 16, 16)\n"
_ADD_ORDER = "  DspAdd(#DSP_TAG_SETORDER,    4,  4)\n"
_COUNT = "  want = #DSP_MSG_TAGS\n"
_READ_ALLOC = ("  bus   = MailboxListWord(dsp_tix[#DSP_TAG_ALLOCATE], 0)\n"
               "  sz    = MailboxListWord(dsp_tix[#DSP_TAG_ALLOCATE], 1)\n")
_READ_PITCH = "  pitch = MailboxListWord(dsp_tix[#DSP_TAG_GETPITCH], 0)\n"

_SECOND_ALLOC = """  bus = 0
  sz = 0
  If DspStep(#DSP_TAG_ALLOCATE, 4, 8) <> 0
    MailboxSetWord(0, #MBX_FB_ALLOC_ALIGN)
    If MailboxSend() <> 0
      bus = MailboxWord(0)
      sz = MailboxWord(1)
    EndIf
  EndIf
"""
_SECOND_PITCH = """  pitch = 0
  If DspStep(#DSP_TAG_GETPITCH, 0, 4) <> 0
    If MailboxSend() <> 0
      pitch = MailboxWord(0)
    EndIf
  EndIf
"""

MUTATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("the original defect - allocate and get-pitch sent as their own messages",
     [(_ADD_ALLOC + _ADD_PITCH, "  ; mutation: allocate and pitch pulled out\n"),
      (_COUNT, "  want = #DSP_MSG_TAGS - 2\n"),
      (_READ_ALLOC + _READ_PITCH, _SECOND_ALLOC + _SECOND_PITCH)]),
    ("the pitch read from a SECOND message instead of the allocating one",
     [(_ADD_PITCH, "  ; mutation: get-pitch pulled out\n"),
      (_COUNT, "  want = #DSP_MSG_TAGS - 1\n"),
      (_READ_PITCH, _SECOND_PITCH)]),
    ("tags in the wrong order - allocate moved to the front",
     [(_ADD_ALLOC, ""),
      ("  DspAdd(#DSP_TAG_SETPHYS,     8,  8)\n",
       _ADD_ALLOC + "  DspAdd(#DSP_TAG_SETPHYS,     8,  8)\n")]),
    ("tags in the wrong order - get-pitch before allocate",
     [(_ADD_ALLOC + _ADD_PITCH, _ADD_PITCH + _ADD_ALLOC)]),
    ("overscan left unset - the firmware keeps whatever it was carrying",
     [(_ADD_OVER, "  ; mutation: overscan not sent\n"),
      (_COUNT, "  want = #DSP_MSG_TAGS - 1\n"),
      ("  MailboxListSetWord(dsp_tix[#DSP_TAG_SETOVERSCAN], 0, 0)\n", "")]),
    ("pixel order left unset - the firmware keeps the other boot's order",
     [(_ADD_ORDER, "  ; mutation: pixel order not sent\n"),
      (_COUNT, "  want = #DSP_MSG_TAGS - 1\n")]),
]

_SEL_ADD = ("  If dsp_sel >= 0\n"
            "    DspAdd(#DSP_TAG_SETDISPLAYNUM, 4, 4)\n"
            "  EndIf\n")
_SEL_SETWORD = ("  If dsp_sel >= 0\n"
                "    MailboxListSetWord(dsp_tix[#DSP_TAG_SETDISPLAYNUM], "
                "0, dsp_sel)\n"
                "  EndIf\n")
_SEL_QUERY_IF = "  rw = width\n  rh = height\n  If dsp_sel >= 0\n"
_SEL_PHYS = "  DspAdd(#DSP_TAG_SETPHYS,     8,  8)\n"
_SEL_PITCH = "  DspAdd(#DSP_TAG_GETPITCH,    0,  4)\n"

# Judged against the SELECTED run.
SEL_MUTATIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("the selection left out of the nine-tag message - sent once, assumed to stick",
     [(_SEL_ADD, "  ; mutation: selection not in the framebuffer message\n"),
      ("    want = #DSP_MSG_TAGS + 1\n", "    want = #DSP_MSG_TAGS\n"),
      (_SEL_SETWORD, "")]),
    ("the selection left off the get-physical query - the wrong socket asked",
     [(_SEL_QUERY_IF, "  rw = width\n  rh = height\n  If dsp_sel >= 99999\n")]),
    ("the DispmanX id sent where the index belongs",
     [("        MailboxListSetWord(selix, 0, dsp_sel)\n",
       "        MailboxListSetWord(selix, 0, #MBX_FB_DISPLAY_HDMI1)\n"),
      ("    MailboxListSetWord(dsp_tix[#DSP_TAG_SETDISPLAYNUM], 0, dsp_sel)\n",
       "    MailboxListSetWord(dsp_tix[#DSP_TAG_SETDISPLAYNUM], 0, "
       "#MBX_FB_DISPLAY_HDMI1)\n")]),
    ("the selection tag added last instead of first",
     [(_SEL_ADD + _SEL_PHYS, _SEL_PHYS),
      (_SEL_PITCH, _SEL_PITCH + _SEL_ADD)]),
]

# THE SELECTED RUN uses display 1, not 0: zero is where a bug lands by
# accident, and index 1's id (7) is furthest from its index.
SELECT_INDEX = 1
_PROBE_SELECT_ANCHOR = '  PutS("-- 4. DisplayInit(1920, 1080, 32)")\n'
_PROBE_SELECT_EDIT = (
    "  ; --- inserted by a64_display_check.py, the selected run -------\n"
    "  ; Not a mutation: the library is untouched. The probe is asked to\n"
    "  ; name a display before the framebuffer is set up.\n"
    "  DisplaySelect(%d)\n" % SELECT_INDEX
    + _PROBE_SELECT_ANCHOR)


def write_variant(work: pathlib.Path, lib_text: str,
                  probe_edits: tuple[tuple[str, str], ...] = ()) -> pathlib.Path:
    """A display.pi4 copy and a probe that includes it, in the work dir."""
    work.mkdir(parents=True, exist_ok=True)
    lib = work / "display_variant.pi4"
    lib.write_text(lib_text, encoding="utf-8")
    probe = PROBE.read_text(encoding="utf-8", errors="replace")
    if probe.count(DISPLAY_INCLUDE) != 1:
        raise SystemExit("pi4DisplayProbe.pi4 does not include display.pi4 "
                         "exactly once, so a variant cannot be substituted.")
    probe = probe.replace(DISPLAY_INCLUDE,
                          'XIncludeFile "%s"' % lib.resolve().as_posix())
    for old, new in probe_edits:
        n = probe.count(old)
        if n != 1:
            raise SystemExit(
                f"The probe edit anchor matched {n} times, not once: "
                f"{old.splitlines()[0][:70]!r}. pi4DisplayProbe.pi4 has changed "
                "shape and this edit needs re-reading.")
        probe = probe.replace(old, new)
    src = work / "pi4DisplayProbeVariant.pi4"
    src.write_text(probe, encoding="utf-8")
    return src


def mutate_text(edits: list[tuple[str, str]]) -> str:
    lib = LIB.read_text(encoding="utf-8", errors="replace")
    for old, new in edits:
        n = lib.count(old)
        if n != 1:
            raise SystemExit(
                f"The mutation anchor matched {n} times, not once: "
                f"{old.splitlines()[0][:70]!r}. display.pi4 has changed shape "
                "and this mutation needs re-reading.")
        lib = lib.replace(old, new)
    return lib


def mutate_pitch_text() -> str:
    """Every row address computed as width*bpp instead of the pitch."""
    lib = LIB.read_text(encoding="utf-8", errors="replace")
    mutant, n = re.subn(r"\* dsp_pitch\)", "* (dsp_w * dsp_bpp))", lib)
    if n < 8:
        raise SystemExit(f"The pitch mutation only matched {n} row addresses; "
                         "display.pi4 has changed shape and this needs re-reading.")
    return mutant


def variant_run(compiler: str, work: pathlib.Path, lib_text: str,
                tags: dict[str, int], vals: dict[str, int], limit: int,
                probe_edits=(), select: int | None = None,
                verbose: bool = False) -> bool:
    """Build and judge one variant.  Returns True if anything went red."""
    src = write_variant(work, lib_text, probe_edits)
    img = work / "variant.img"
    try:
        syms = build(compiler, src, img)
        blob = img.read_bytes()
        fw = Firmware(tags)
        cpu, board = run(img, fw, limit)
    except SystemExit as e:
        if verbose:
            raise
        print("     (the model refused it: %s)" % str(e).splitlines()[0][:90])
        return True
    log = board.uart.decode("latin-1")
    out: list[str] = []
    fails = check_surface(cpu, out)
    try:
        fails += check_glyph(cpu, blob, syms, out)
    except Exception:                                  # noqa: BLE001
        fails.append("the glyph check could not run")
    fails += check_protocol(fw, vals, out, select=select)
    prfails = cpu.load(syms["global_prfails"], 8)
    inlog = log.count("  FAIL ")
    x0 = cpu.x[0]
    if verbose:
        for line in out:
            print("  " + line)
        print(f"  the probe's own {cpu.load(syms['global_prchecks'], 8)} checks: "
              f"{prfails} failed ({inlog} FAIL lines); x0 = {x0}")
        print("  messages the firmware saw:")
        for i, m in enumerate(fw.messages):
            print(f"      {i + 1}. {' '.join(m)}")
    red = bool(fails) or prfails != 0 or inlog != 0 or x0 != 0
    if red and not verbose:
        print(f"     probe checks failed {prfails}, x0 {x0}, "
              f"harness assertions failed {len(fails)}")
        for f in fails[:3]:
            print("       - " + f.splitlines()[0])
    return red


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge executable (default: PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="break a copy of the library on purpose; every one must go RED")
    ap.add_argument("--limit", type=int, default=40_000_000)
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        raise SystemExit("No compiler was named. Pass --compiler or set "
                         "PMF_COMPILER to the PureMetalForge executable.")

    tags = firmware_tags()
    tags.update(display_tags())
    vals = {k: uboot_value(k) for k in UBOOT_VALUES}
    print("modelled firmware tags - two pinned readings, and they agree:")
    for k, v in sorted(tags.items(), key=lambda kv: kv[1]):
        note = "   (downstream header only)" if k in DISPLAY_TAGS else ""
        print(f"    {k:<14} ${v:08X}{note}")
    print(f"modelled displays: {NUM_DISPLAYS}, DispmanX ids {DISPLAY_IDS}")
    print(f"    pixel order BGR {vals['ORDER_BGR']} / RGB {vals['ORDER_RGB']}, "
          f"alpha IGNORED {vals['ALPHA_IGNORED']}")
    print(f"modelled panel: {PANEL_W}x{PANEL_H}; mode {MODE_W}x{MODE_H}x"
          f"{MODE_DEPTH}, pitch {PITCH} ({PAD} bytes of padding a row)")
    print(f"stale state before configuration: {STALE_W}x{STALE_H}, pitch "
          f"{STALE_PITCH}, overscan {STALE_OVERSCAN}, pixel order {STALE_ORDER}")

    with tempfile.TemporaryDirectory(prefix="anvil-display-") as td:
        work = pathlib.Path(td)
        img = work / "pi4DisplayProbe.img"
        syms = build(args.compiler, PROBE, img)
        blob = img.read_bytes()
        fw = Firmware(tags)
        cpu, board = run(img, fw, args.limit)

        log = board.uart.decode("latin-1")
        print("\n---------------- serial output ----------------")
        print(log.replace("\r\n", "\n").rstrip())
        print("-----------------------------------------------\n")

        out: list[str] = []
        fails = check_surface(cpu, out)
        fails += check_glyph(cpu, blob, syms, out)
        fails += check_protocol(fw, vals, out)
        print("harness assertions, computed here and not read back:")
        for line in out:
            print(line)

        prfails = cpu.load(syms["global_prfails"], 8)
        prchecks = cpu.load(syms["global_prchecks"], 8)
        x0 = cpu.x[0]
        inlog = log.count("  FAIL ")
        print(f"\nthe probe made {prchecks} checks of its own, {prfails} failed "
              f"({inlog} FAIL lines in the log); it returned x0 = {x0}")
        print("messages the firmware saw:")
        for i, m in enumerate(fw.messages):
            print(f"    {i + 1}. {' '.join(m)}")
        print(f"{board.steps} interpreter steps")

        if fails or prfails != 0 or inlog != 0 or x0 != 0:
            print("\na64_display_check: FAIL - the default path.")
            for f in fails:
                print("  !! " + f)
            return 1
        print("\nthe default path PASSES - one transaction, a clamped row-padded "
              "framebuffer, a correct picture, and no display selection.")

        print()
        print(f"the SELECTED path: the same library, the probe asking for "
              f"display {SELECT_INDEX} first")
        selbad = variant_run(args.compiler, work / "selected",
                             LIB.read_text(encoding="utf-8", errors="replace"),
                             tags, vals, args.limit,
                             ((_PROBE_SELECT_ANCHOR, _PROBE_SELECT_EDIT),),
                             select=SELECT_INDEX, verbose=True)
        if selbad:
            print("\na64_display_check: FAIL - the selected path.")
            return 1
        print("  the selected path PASSES.")
        harness_checks = CHECKS[0]

        if args.mutate:
            print()
            print("--mutate: breaking copies of the library; each must go RED")
            bad = 0
            total = 0
            allmuts = [(name, mutate_text(edits), (), None)
                       for name, edits in MUTATIONS]
            allmuts.append(("row addresses computed as width*bpp instead of "
                            "the pitch", mutate_pitch_text(), (), None))
            allmuts += [(name, mutate_text(edits),
                         ((_PROBE_SELECT_ANCHOR, _PROBE_SELECT_EDIT),),
                         SELECT_INDEX) for name, edits in SEL_MUTATIONS]
            for i, (name, text, edits, select) in enumerate(allmuts):
                total += 1
                print("  * %s" % name)
                if variant_run(args.compiler, work / ("mutant%02d" % i), text,
                               tags, vals, args.limit, edits, select=select):
                    print("    RED, as required")
                else:
                    print("    *** STILL GREEN - the gate does not catch this ***")
                    bad += 1
            if bad:
                print(f"\na64_display_check: FAIL - {bad} of {total} mutations "
                      "went unnoticed.")
                return 1
            print(f"  all {total} mutations caught")

    print(f"\na64_display_check: PASS - {harness_checks} harness assertions "
          f"over the default and selected runs, plus {prchecks} probe checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
