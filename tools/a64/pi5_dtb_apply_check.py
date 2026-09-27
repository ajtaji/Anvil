#!/usr/bin/env python3
"""pi5_dtb_apply_check.py - what the -t pi5 monitor takes from the LIVE device tree, executed.

Builds the real RaspberryPi4/Board/board.pi4 -t pi5 and runs, under
tools/a64/a64_interp.py:

  Pi5DtbApply (board.pi4, through Anvil/Core/fdt.pbi), once per pinned Pi 5
  DTB placed where the firmware leaves it ($2EFEC600, the address measured
  on 2026-09-26) with gBootDtb pointing at it:
    * dma.pi4's channel mask must be /axi/dma@10600's brcm,dma-channel-mask,
      read here independently from the same blob;
    * sdio.pi4's pinctrl stepping must be C0 (1) when the tree has a
      "brcm,bcm2712c0-pinctrl" node, D0 (2) for "brcm,bcm2712d0-pinctrl",
      and stay UNSET (0) for a tree naming neither (bcm2712-d-rpi-5-b.dtb
      is one) - the Wi-Fi library then refuses rather than guess;
    * with the tree's magic broken, nothing is applied (mask 0, stepping 0)
      and the console says so - never a guess.

  WifiRadioUp (wifi.pi4) on the modelled BCM2712 SD card of
  tools/a64/pi5_sd_save_check.py with NO radio firmware on it: it must
  return 0, name the missing file on the console, and touch no SDIO2
  register (the model refuses any address that is not the SD host or the
  console) - `wifi` refuses by name, it does not hang.

Like the other Pi 5 update gates it compiles a copy of board.pi4 without the
tracked compiler's `#PMF_CHIP = 2711` bridge line, and says so.

    py -3 tools/a64/pi5_dtb_apply_check.py --compiler PureMetalForge.exe [--dtb-dir DIR]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pi5_desk as d                                   # noqa: E402
from pi5_serial_update_check import build_monitor, UART0, MON_LOAD    # noqa: E402
import pi5_sd_save_check as sdm                        # noqa: E402

DEFAULT_DTB_DIR = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5\Boot staging")
DTBS = ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb")
DTB_AT = 0x2EFEC600


def dtb_facts(b: bytes):
    """Independent: the dma@10600 mask and which pinctrl stepping the tree names."""
    _, _, off_s, off_str = struct.unpack_from(">IIII", b, 0)
    name = lambda o: b[off_str + o: b.index(b"\0", off_str + o)].decode()
    p, path, mask, c0, d0 = off_s, [], None, False, False
    while True:
        t = struct.unpack_from(">I", b, p)[0]
        p += 4
        if t == 1:
            e = b.index(b"\0", p)
            path.append(b[p:e].decode())
            p = (e + 4) & ~3
        elif t == 2:
            path.pop()
        elif t == 3:
            ln, no = struct.unpack_from(">II", b, p)
            p += 8
            v = b[p:p + ln]
            p = (p + ln + 3) & ~3
            n = name(no)
            if n == "brcm,dma-channel-mask" and "/".join(path) == "/axi/dma@10600":
                mask = struct.unpack(">I", v)[0]
            if n == "compatible":
                parts = v.split(b"\0")
                c0 |= b"brcm,bcm2712c0-pinctrl" in parts
                d0 |= b"brcm,bcm2712d0-pinctrl" in parts
        elif t == 9:
            break
    return mask, (1 if c0 else 2 if d0 else 0)


class Console:
    def __init__(self, inner=None):
        self.inner = inner
        self.tx = bytearray()

    def __call__(self, addr, size, value):
        if UART0 <= addr < UART0 + 0x1000:
            off = addr - UART0
            if value is not None and off == 0:
                self.tx.append(value & 0xFF)
            if value is None and off == 0x18:
                return 0x10
            return 0
        if self.inner is not None:
            return self.inner(addr, size, value)
        d.die("touched $%X, which this scenario models nothing at" % addr)


def glob(syms, name):
    k = "global_" + name.lower()
    if k not in syms:
        d.die("the image has no global %s" % name)
    return syms[k]


def apply(img, procs, syms, blob: bytes):
    d.LOAD = MON_LOAD
    con = Console()
    m = d.Machine(img, procs, con)
    m.poke(DTB_AT, blob)
    m.poke(glob(syms, "gBootDtb"), DTB_AT.to_bytes(8, "little"))
    m.call("Pi5DtbApply", limit=200_000_000)
    mask = int.from_bytes(m.peek(glob(syms, "dma_mask40"), 8), "little")
    kind = int.from_bytes(m.peek(glob(syms, "sdio_pinctrl"), 8), "little")
    return mask, kind, con.tx.decode("ascii", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--dtb-dir", type=pathlib.Path, default=DEFAULT_DTB_DIR)
    args = ap.parse_args()
    cc = d.compiler(args.compiler)
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    try:
        img, procs, syms = build_monitor(cc, ROOT / "_work" / "pi5_dtb_apply")
        for name in DTBS:
            blob = (args.dtb_dir / name).read_bytes()
            want_mask, want_kind = dtb_facts(blob)
            mask, kind, out = apply(img, procs, syms, blob)
            check(want_mask is not None and mask == want_mask,
                  "%s: DMA channel mask $%X (the tree says $%X)" % (name, mask, want_mask or 0))
            check(kind == want_kind,
                  "%s: pinctrl stepping %d (the tree says %d%s)" % (name, kind, want_kind,
                  ", neither stepping: left unset, so `wifi` refuses" if want_kind == 0 else ""))
        bad = bytearray((args.dtb_dir / DTBS[0]).read_bytes())
        bad[0] ^= 0xFF
        mask, kind, out = apply(img, procs, syms, bytes(bad))
        check(mask == 0 and kind == 0 and "did not check" in out,
              "a tree with a broken magic: nothing applied, and the console says so")

        # wifi with no radio firmware on the card: a refusal by name, no SDIO2 access
        card = sdm.make_card(b"\0" * 600, b"kernel=ANVIL5.IMG\n")
        host = sdm.SdHost(card)
        con = Console(host)
        d.LOAD = MON_LOAD
        m = d.Machine(img, procs, con)
        r = m.signed(m.call("WifiRadioUp", limit=400_000_000))
        out = con.tx.decode("ascii", "replace")
        check(r == 0, "wifi with no firmware files: WifiRadioUp refuses (returned %d)" % r)
        check("BRCMFW.BIN" in out and "is not on" in out,
              "... and names the missing file on the console")
    except d.GateFail as e:
        print("pi5_dtb_apply_check: FAIL - %s" % e)
        return 1
    if fails:
        print("pi5_dtb_apply_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_dtb_apply_check: PASS - DMA mask and pin stepping from three live-DTB copies, a broken tree refused, `wifi` refuses by name. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
