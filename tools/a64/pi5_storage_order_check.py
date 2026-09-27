#!/usr/bin/env python3
"""pi5_storage_order_check.py - the Pi 5 StorageUp probe order (SD, NVMe, USB), executed.

Builds the real RaspberryPi4/Board/board.pi4 -t pi5 and runs StorageUp
(RaspberryPi4/Board/storage.pi4) under tools/a64/a64_interp.py against:

  the SD card      pi5_sd_save_check.py's BCM2712 SDHCI + card model, or the
                   same host with NO card in the slot;
  the NVMe port    pcie1 ($10_0011_0000) with its link never coming up - no
                   drive plugged in;
  USB              a64_usb_kbd_pi5_check.py's pcie2 + RP1 xHCI model, with
                   a64_usb_msc_pi5_check.py's Bulk-Only stick (a FAT32 disk)
                   on a port, or nothing on the bus.

Scenarios:
  card+stick   the card wins; USB is never enumerated (RP1's xHCI untouched).
  stick        no card, no drive: the stick mounts, gMedium = 1, and
               HwStorageReport names a USB stick.
  nothing      no card, no drive, no stick: StorageUp returns 0 and says
               "Nothing usable on the SD card, an NVMe drive or USB." within
               BOUND_MS of model time - a boot without media is not held up.

    py -3 tools/a64/pi5_storage_order_check.py --compiler PureMetalForge.exe
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_usb_kbd_pi5_check as K                     # noqa: E402
import a64_usb_msc_pi5_check as M                     # noqa: E402
import pi5_sd_save_check as SD                        # noqa: E402
from a64_interp import A64, attach_symbols            # noqa: E402
from pmf_compiler import resolve_compiler             # noqa: E402

MON_LOAD, STACK, LR = 0x80000, 0x3000000, 0xDEADBEE0   # the link address (THE BCM2712 MAP)
UART0 = 0x1F00030000
PCIE1, PCIE1_SIZE = 0x1000110000, 0x10000
BOUND_MS = 5000


def die(msg):
    raise SystemExit("pi5_storage_order_check: FAIL - " + msg)


def build(cc, work):
    work.mkdir(parents=True, exist_ok=True)
    text = (ROOT / "RaspberryPi4/Board/board.pi4").read_text(encoding="utf-8").replace("\r\n", "\n")
    text = "\n".join(l for l in text.split("\n") if l.rstrip("\r") != "#PMF_CHIP = 2711")
    src = work / "board_pi5.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "anvil5.img"
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5", "-o", str(img)], cwd=str(ROOT),
                       env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        die("the -t pi5 monitor would not build:\n" + r.stdout[-1500:] + r.stderr[-500:])
    procs, syms = {}, {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = MON_LOAD + int(f[1])
    for line in pathlib.Path(str(img) + ".sym").read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                syms[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return img, procs, syms


class NoCardHost(SD.SdHost):
    """The BCM2712 SD host with the slot empty: PRESENT_STATE card-inserted
    clear, and every card command times out."""
    def __call__(self, addr, size, value):
        if SD.SD <= addr < SD.SD + 0x260 and value is None and addr - SD.SD == 0x24:
            return 0x00000000
        return super().__call__(addr, size, value)

    def command(self, v):
        self.cmds.append((v >> 24) & 0x3F)
        self.intr |= 0x8000 | 0x10000


def run(img, procs, syms, card, stick, call="StorageUp", then=None, limit=400_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[MON_LOAD + i] = b
    attach_symbols(cpu, img, MON_LOAD)
    topo = {3: M.BotStick(M.make_disk("fat32"))} if stick else {}
    ctl = M.Rp1MscCtl(cpu, topo, "healthy")
    if "global_xh_bulkbounce" in syms:
        b0 = syms["global_xh_bulkbounce"]
        ctl.bounce = (b0, b0 + 4096 + 64)
    K.install(cpu, ctl)
    usb_load, usb_store = cpu.load, cpu.store
    host = SD.SdHost(SD.make_card(b"OLD" * 700, b"kernel=ANVIL5.IMG\n")) if card else NoCardHost({})
    tx = bytearray()
    pcie1 = []

    def dev(addr, value):
        if UART0 <= addr < UART0 + 0x1000:
            off = addr - UART0
            if value is None:
                return 0x10 if off == 0x18 else 0
            if off == 0:
                tx.append(value & 0xFF)
            return 0
        if PCIE1 <= addr < PCIE1 + PCIE1_SIZE:
            pcie1.append((addr - PCIE1, value))
            return 0                             # no drive: the link never trains
        if SD.SD <= addr < SD.SD + 0x260 or SD.CFG <= addr < SD.CFG + 0x200:
            return host(addr, 4, value)
        return None

    def load(addr, size):
        if addr >= 0x1_0000_0000:
            v = dev(addr, None)
            if v is not None:
                return v
        return usb_load(addr, size)

    def store(addr, value, size):
        if addr >= 0x1_0000_0000 and dev(addr, value) is not None:
            return
        usb_store(addr, value, size)

    cpu.load, cpu.store = load, store
    t0 = ctl.ticks
    rc = None
    for name in [call] + ([then] if then else []):
        cpu.pc, cpu.sp, cpu.x[30] = procs[name.lower()], STACK, LR
        n = 0
        while cpu.pc != LR:
            n += 1
            if n > limit:
                die("%s never returned in %d steps - IT HUNG" % (name, limit))
            cpu.step()
        if rc is None:
            rc = cpu.x[0]
    ms = (ctl.ticks - t0) * 1000 // K.CNTFRQ
    medium = int.from_bytes(bytes(cpu.memory.get(syms["global_gmedium"] + i, 0) for i in range(8)), "little")
    return rc, ms, tx.decode("ascii", "replace"), medium, ctl, host, pcie1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    args = ap.parse_args()
    if not args.compiler:
        die("pass --compiler or set PMF_COMPILER")
    cc = str(pathlib.Path(resolve_compiler(args.compiler)).resolve())
    img, procs, syms = build(cc, ROOT / "_work" / "pi5_storage_order")
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    rc, ms, out, med, ctl, host, p1 = run(img, procs, syms, card=True, stick=True)
    check(rc == 1 and med == 2 or rc == 1 and "SD card" in out,
          "card+stick: StorageUp mounts the card (rc %d, gMedium %d)" % (rc, med))
    check(not ctl.rp1_touched and not p1, "card+stick: neither NVMe nor USB was probed")

    rc, ms, out, med, ctl, host, p1 = run(img, procs, syms, card=False, stick=True, then="HwStorageReport")
    check(rc == 1 and med == 1 and "Mounted the USB stick" in out,
          "stick: no card, no drive - the USB stick mounts (rc %d, gMedium %d; %r)" % (rc, med, out.strip()[-120:]))
    check("The medium is a USB stick" in out, "stick: HwStorageReport names a USB stick")
    check(bool(p1), "stick: the NVMe port was tried before USB")
    check(not ctl.violations, "stick: the USB model saw no misuse (%s)" % ctl.violations[:2])

    rc, ms, out, med, ctl, host, p1 = run(img, procs, syms, card=False, stick=False)
    check(rc == 0, "nothing: StorageUp returns 0 (rc %d)" % rc)
    check("Nothing usable on the SD card, an NVMe drive or USB." in out,
          "nothing: the console says so (%r)" % out.strip()[-160:])
    check(ms <= BOUND_MS, "nothing: in %d ms of model time (bound %d ms)" % (ms, BOUND_MS))
    check("SD card slot is being tried" not in out, "nothing: the Pi 4's card retry tail is not reached")
    if fails:
        print("pi5_storage_order_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_storage_order_check: PASS - SD, then NVMe, then USB; nothing at all falls through in "
          "bounded time. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
