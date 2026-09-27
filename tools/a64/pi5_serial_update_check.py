#!/usr/bin/env python3
"""pi5_serial_update_check.py - the Pi 5 monitor's serial update path, executed.

Builds the REAL monitor, RaspberryPi4/Board/board.pi4 -t pi5, loads the image
at its own link address under tools/a64/a64_interp.py (through pi5_desk's
Machine), and runs the shipped procedures the host tools drive:

  receive   CmdBlock (Anvil/Core/xfer.pbi) - the `b <addr> <len> <crc32>`
            command tools/anvil.py block() sends - against a model of RP1
            UART0 at $1F_0003_0000, the header port the Pi 5 console is on.
            A clean payload must land byte for byte in the high payload
            window with "rdy" ... "ok"; the same payload with one byte
            flipped on the wire must end in "crc" and not "ok".
  reset     SafetyToFirmware (RaspberryPi4/Lib/safety.pi4), which `reset`
            reaches through HwReboot, against a model of the BCM2712 PM
            block at $10_7D20_0000: WDOG gets PASSWORD | 10 and RSTC gets
            PASSWORD | (RSTC & ~WRCFG) | FULL_RESET, in that order, and the
            boot-count word is cleared at $001FBF00 - never at $1000, which
            is inside the Pi 5 EL3 stub.

The write of the boot file between them (`save ANVIL5.IMG ...`) is the SD
card's; see tools/a64/pi5_sd_save_check.py.

THE VULKAN LANE'S `#PMF_CHIP = 2711` LINE: board.pi4 carries that one line
for the tracked compiler, which predates the predefined #PMF_CHIP; a -t pi5
build refuses it. Until the signed compiler lands and the line goes, this
gate compiles a copy of board.pi4 in _work/ with exactly that line removed,
and says so. Nothing tracked is written.

    py -3 tools/a64/pi5_serial_update_check.py --compiler PureMetalForge.exe
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import subprocess
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pi5_desk as d                                   # noqa: E402

MON_LOAD = 0x200000
UART0 = 0x1F00030000
PM = 0x107D200000
PAYLOAD_AT = 0x10000000          # the Pi 5 high payload window (memmap.pi4)
COUNT_ADDR = 0x001FBF00
OLD_COUNT_ADDR = 0x1000


class Stop(Exception):
    pass


def build_monitor(cc: str, work: pathlib.Path):
    work.mkdir(parents=True, exist_ok=True)
    src = (ROOT / "RaspberryPi4/Board/board.pi4").read_bytes().split(b"\n")
    keep = [l for l in src if l.rstrip(b"\r") != b"#PMF_CHIP = 2711"]
    if len(keep) != len(src):
        print("  (compiling a copy of board.pi4 without its %d `#PMF_CHIP = 2711` line)"
              % (len(src) - len(keep)))
    copy = work / "board_pi5.pi4"
    copy.write_bytes(b"\n".join(keep))
    img = work / "anvil5.img"
    r = subprocess.run([cc, "--compile", str(copy), "-t", "pi5", "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        d.die("the -t pi5 monitor would not build:\n" + r.stdout[-2500:] + r.stderr[-800:])
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = MON_LOAD + int(f[1])
    syms = {}
    for line in pathlib.Path(str(img) + ".sym").read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                syms[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return img, procs, syms


class Uart:
    """RP1 UART0 as the monitor drives it: DR +$00, FR +$18 (RXFE bit 4,
    TXFF bit 5, BUSY bit 3), everything else reads 0 and ignores writes."""
    def __init__(self):
        self.rx = bytearray()
        self.tx = bytearray()

    def __call__(self, addr, size, value):
        off = addr - UART0
        if off == 0x00:
            if value is None:
                return self.rx.pop(0) if self.rx else 0
            self.tx.append(value & 0xFF)
            return 0
        if off == 0x18 and value is None:
            return 0x10 if not self.rx else 0     # RXFE when empty; never TXFF/BUSY
        return 0


def machine(img, procs, model):
    d.LOAD = MON_LOAD          # the monitor runs where it is linked
    return d.Machine(img, procs, model)


def put_line(m, syms, text):
    base = syms.get("global_gline")
    pos = syms.get("global_gpos")
    if base is None or pos is None:
        d.die("the monitor image has no gLine / gPos symbols")
    m.poke(base, text.encode("ascii") + b"\0")
    m.poke(pos, (1).to_bytes(8, "little"))     # just past the command letter


def receive(img, procs, syms, payload, wire):
    u = Uart()
    m = machine(img, procs, u)
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    put_line(m, syms, "b %X %X %08X" % (PAYLOAD_AT, len(payload), crc))
    u.rx.extend(wire)
    m.call("CmdBlock", limit=60_000_000)
    return u.tx.decode("ascii", "replace"), m.peek(PAYLOAD_AT, len(payload))


def reset(img, procs):
    writes = []

    def pm(addr, size, value):
        if addr >= UART0 and addr < UART0 + 0x1000:
            return 0
        off = addr - PM
        if value is None:
            if off == 0x1C:
                return 0x00000130       # RSTC as found: WRCFG bits set, others
            return 0
        writes.append((off, value))
        if off == 0x1C:
            raise Stop()
        return 0
    m = machine(img, procs, pm)
    m.poke(COUNT_ADDR, (0x5A1E0001).to_bytes(4, "little"))
    m.poke(OLD_COUNT_ADDR, (0x12345678).to_bytes(4, "little"))
    try:
        m.call("SafetyToFirmware", limit=5_000_000)
    except Stop:
        pass
    return writes, m.peek(COUNT_ADDR, 4), m.peek(OLD_COUNT_ADDR, 4)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    args = ap.parse_args()
    cc = d.compiler(args.compiler)
    work = ROOT / "_work" / "pi5_serial_update"
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    try:
        img, procs, syms = build_monitor(cc, work)
        rnd = random.Random(2712)
        payload = bytes(rnd.randrange(256) for _ in range(3000))

        out, got = receive(img, procs, syms, payload, payload)
        check("rdy" in out, "receive: the board printed rdy before taking bytes")
        check(got == payload, "receive: all %d bytes landed at $%X exactly" % (len(payload), PAYLOAD_AT))
        check(out.rstrip().endswith("ok") and "crc" not in out.split("rdy", 1)[-1],
              "receive: the verdict is ok")

        bad = bytearray(payload)
        bad[1234] ^= 0x10
        out, got = receive(img, procs, syms, payload, bytes(bad))
        check("crc" in out and not out.rstrip().endswith("ok"),
              "receive: one flipped bit on the wire ends in crc, not ok (negative control)")

        writes, cnt, old = reset(img, procs)
        check(len(writes) == 2 and writes[0][0] == 0x24 and writes[1][0] == 0x1C,
              "reset: WDOG then RSTC, and nothing else in the PM block (%s)"
              % ", ".join("+$%X=$%08X" % w for w in writes))
        if len(writes) == 2:
            check(writes[0][1] == 0x5A00000A, "reset: WDOG = PASSWORD | 10 ticks ($%08X)" % writes[0][1])
            check(writes[1][1] == 0x5A000100 | 0x20, "reset: RSTC = PASSWORD | (as found & ~WRCFG) | FULL ($%08X)"
                  % writes[1][1])
        check(cnt == b"\0\0\0\0", "reset: the boot-count word at $%X is cleared" % COUNT_ADDR)
        check(old == (0x12345678).to_bytes(4, "little"),
              "reset: $1000 (inside the EL3 stub) is not written")
    except d.GateFail as e:
        print("pi5_serial_update_check: FAIL - %s" % e)
        return 1
    if fails:
        print("pi5_serial_update_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_serial_update_check: PASS - receive (clean + corrupted) and reset on the -t pi5 monitor. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
