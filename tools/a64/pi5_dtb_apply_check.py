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
      and the console says so - never a guess;
    * a tree naming BOTH steppings (bcm2712-rpi-5-b.dtb with one node added
      here whose compatible is "brcm,bcm2712d0-pinctrl") contradicts itself:
      the stepping stays UNSET and the console says so. The DMA mask is still
      applied - the contradiction is the radio's, not the DMA engine's;
    * mmu.pi4's RAM size (mmu_ramBytes) must be MmuSetRamBytes' reading of
      the /memory reg entry that starts at 0, worked out here independently
      from the tree's #address-cells/#size-cells: the pinned trees carry the
      640 MiB placeholder (ignored: under 1 GiB), and the same tree with that
      entry rewritten to 8 GiB, 5 GiB - 4 MiB (-> 4 GiB), 768 MiB (ignored),
      128 GiB (-> stops at the SoC window, 64 GiB) and 8 GiB starting at
      1 GiB (no bank at 0: ignored). "Ignored" means the value set before the
      call is still there.

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


MMU_SENTINEL = 0x40000000          # what Main's global initialiser leaves: 1 GiB
SOC_WINDOW = 0x1000000000         # mmu.pi4 #MMU_PERIPH_BASE on the BCM2712 (axi ranges)


def memory_reg(b: bytes):
    """Independent: (offset of the first memory node's reg value, its length,
    address cells, size cells)."""
    _, _, off_s, off_str = struct.unpack_from(">IIII", b, 0)
    name = lambda o: b[off_str + o: b.index(b"\0", off_str + o)].decode()
    p, depth, cells, props = off_s, 0, [2, 1], None
    while True:
        t = struct.unpack_from(">I", b, p)[0]
        p += 4
        if t == 1:
            e = b.index(b"\0", p)
            depth += 1
            props = {}
            p = (e + 4) & ~3
        elif t == 2:
            depth -= 1
        elif t == 3:
            ln, no = struct.unpack_from(">II", b, p)
            p += 8
            v, at = b[p:p + ln], p
            p = (p + ln + 3) & ~3
            n = name(no)
            if depth == 1 and n == "#address-cells":
                cells[0] = struct.unpack(">I", v)[0]
            if depth == 1 and n == "#size-cells":
                cells[1] = struct.unpack(">I", v)[0]
            props[n] = (v, at)
            if "reg" in props and props.get("device_type", (b"",))[0].rstrip(b"\0") == b"memory":
                return props["reg"][1], len(props["reg"][0]), cells[0], cells[1]
        elif t == 9:
            d.die("the tree has no memory node")


def want_ram(b: bytes, before: int) -> int:
    """MmuSetRamBytes(size of the reg entry at address 0), independently."""
    at, ln, ac, sc = memory_reg(b)
    cell = lambda o, n: int.from_bytes(b[o:o + 4 * n], "big")
    size = 0
    for k in range(ln // (4 * (ac + sc))):
        o = at + 4 * (ac + sc) * k
        if cell(o, ac) == 0:
            size = cell(o + 4 * ac, sc)
            break
    if size < 0x40000000:
        return before
    return (min(size, SOC_WINDOW) >> 30) << 30


def with_memory(b: bytes, addr: int, size: int) -> bytes:
    at, ln, ac, sc = memory_reg(b)
    if ln != 4 * (ac + sc):
        d.die("the memory node has %d bytes of reg, not one entry" % ln)
    return b[:at] + addr.to_bytes(4 * ac, "big") + size.to_bytes(4 * sc, "big") + b[at + ln:]


def with_node(blob: bytes, compat: bytes) -> bytes:
    """blob with one more child of the root, `pinctrl-both`, whose compatible
    is compat. The structure block precedes the strings block (dtc's layout,
    asserted), so the strings move up by the node's length."""
    h = list(struct.unpack_from(">10I", blob, 0))
    total, off_s, off_str, size_str, size_s = h[1], h[2], h[3], h[8], h[9]
    root_end = off_s + size_s - 8
    if struct.unpack_from(">II", blob, root_end) != (2, 9) or off_str < off_s + size_s:
        d.die("the DTB is not laid out as dtc lays it out; the added node has nowhere to go")
    k = blob.find(b"compatible\0", off_str, off_str + size_str)
    if k < 0:
        d.die("the DTB's strings block has no \"compatible\"")
    name = b"pinctrl-both\0"
    val = compat + b"\0"
    node = (struct.pack(">I", 1) + name + b"\0" * (-len(name) % 4)
            + struct.pack(">III", 3, len(val), k - off_str) + val + b"\0" * (-len(val) % 4)
            + struct.pack(">I", 2))
    n = len(node)
    h[1], h[3], h[9] = total + n, off_str + n, size_s + n
    return struct.pack(">10I", *h) + blob[40:root_end] + node + blob[root_end:]


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
    m.poke(glob(syms, "mmu_ramBytes"), MMU_SENTINEL.to_bytes(8, "little"))
    m.call("Pi5DtbApply", limit=200_000_000)
    mask = int.from_bytes(m.peek(glob(syms, "dma_mask40"), 8), "little")
    kind = int.from_bytes(m.peek(glob(syms, "sdio_pinctrl"), 8), "little")
    apply.ram = int.from_bytes(m.peek(glob(syms, "mmu_ramBytes"), 8), "little")
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
            check(apply.ram == want_ram(blob, MMU_SENTINEL),
                  "%s: MMU RAM size $%X (the tree's bank at 0 gives $%X)"
                  % (name, apply.ram, want_ram(blob, MMU_SENTINEL)))
        base = (args.dtb_dir / DTBS[0]).read_bytes()
        for addr, size, what in ((0, 0x200000000, "8 GiB"), (0, 0x13FC00000, "5 GiB - 4 MiB"),
                                 (0, 0x30000000, "768 MiB"), (0, 0x2000000000, "128 GiB"),
                                 (0x40000000, 0x200000000, "8 GiB at 1 GiB")):
            blob = with_memory(base, addr, size)
            want = want_ram(blob, MMU_SENTINEL)
            apply(img, procs, syms, blob)
            check(apply.ram == want, "/memory rewritten to %s: MMU RAM size $%X (want $%X)"
                  % (what, apply.ram, want))
        bad = bytearray((args.dtb_dir / DTBS[0]).read_bytes())
        bad[0] ^= 0xFF
        mask, kind, out = apply(img, procs, syms, bytes(bad))
        check(mask == 0 and kind == 0 and "did not check" in out,
              "a tree with a broken magic: nothing applied, and the console says so")

        both = with_node((args.dtb_dir / DTBS[0]).read_bytes(), b"brcm,bcm2712d0-pinctrl")
        want_mask, _ = dtb_facts(both)
        mask, kind, out = apply(img, procs, syms, both)
        check(kind == 0 and "BOTH" in out and mask == want_mask,
              "a tree naming both C0 and D0 pinctrl: stepping left unset (%d), the console says so, "
              "the DMA mask still $%X" % (kind, mask))

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
    print("pi5_dtb_apply_check: PASS - DMA mask and pin stepping from three live-DTB copies, the MMU RAM size from /memory, a broken tree and a two-stepping tree refused, `wifi` refuses by name. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
