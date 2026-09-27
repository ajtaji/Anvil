#!/usr/bin/env python3
"""pi5_net_boot_check.py - the Pi 5 boot's network step (#CAP_NET = 1), executed to its end.

Builds the real RaspberryPi4/Board/board.pi4 -t pi5 and runs BootNetUp
(RaspberryPi4/Board/boot.pi4) - EthBootWired, then NetConsoleRearm, exactly
as Main does - under tools/a64/a64_interp.py, against the GEM / BCM54213PE /
pcie2 + RP1 / GPIO 32 / write-back-cache model of tools/a64/a64_gem_pi5_check.py
(imported, not copied), a VideoCore mailbox that answers the MAC tag, and a
wire on which NOTHING ever answers. Time is the model's counter
(54 MHz, the gem gate's ticks per instruction).

The claim: BootNetUp RETURNS, within a stated bound, whatever the cable -
the prompt comes after it. Scenarios:

  no-cable        a PHY that answers with no link: "wired: no cable", no
                  DHCP, back in well under a second.
  rp1-down        the PCIe link to RP1 down: back at once, RP1 never touched.
  cable-silent    cable in, a PHY held in reset at power-up (so the 5 s link
                  wait is taken), no DHCP server, nothing saved: DHCP gives
                  up, a link-local address is taken, back within the bound.
  clock-stopped   the same with eth_cfg found with the GEM clock generator
                  killed and memory powered down: repaired, same bound.

THE BOUND IS THE PI 4's. EthBootWired, CmdDhcp (#DHCP_TRIES x #DHCP_REPLY_MS)
and NetLinkLocalAcquire are the same procedures on both chips; only the
cable probe and the MAC start fork, each bounded by #ETH_LINK_MS. The gate
reads those constants from the source and requires the elapsed time to be
under their sum plus the link-local worst case (#NETLL, 19 s, netll.pbi).

    py -3 tools/a64/pi5_net_boot_check.py --compiler PureMetalForge.exe
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
import a64_gem_pi5_check as G                          # noqa: E402
from a64_interp import A64, AlignmentFault, attach_symbols   # noqa: E402
from pmf_compiler import resolve_compiler               # noqa: E402

MON_LOAD, STACK, LR = 0x200000, 0x3000000, 0xDEADBEE0
UART0 = 0x1F00030000
MBX = 0x107C013880
TAG_MAC = 0x00010003
MAC = bytes.fromhex("2ccf67000001")
LL_WORST_MS = 19000          # netll.pbi: "nine seconds if nobody objects, nineteen in the worst case"


def die(msg):
    raise SystemExit("pi5_net_boot_check: FAIL - " + msg)


def const(rel, name):
    t = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\s*#%s\s*=\s*(\d+)" % name, t, re.M)
    if not m:
        die("%s no longer defines #%s" % (rel, name))
    return int(m.group(1))


def build(cc, work, eth_text=None):
    work.mkdir(parents=True, exist_ok=True)
    text = (ROOT / "RaspberryPi4/Board/board.pi4").read_text(encoding="utf-8").replace("\r\n", "\n")
    if eth_text is not None:
        # A MUTANT: board.pi4 includes this copy of eth.pi4 instead of the tree's.
        inc = 'XIncludeFile "RaspberryPi4/Board/eth.pi4"'
        if text.count(inc) != 1:
            die("board.pi4 no longer includes eth.pi4 exactly once")
        mut = work / "eth_mut.pi4"
        mut.write_text(eth_text, encoding="utf-8")
        text = text.replace(inc, 'XIncludeFile "%s"' % mut.resolve().as_posix())
    if not re.search(r"CompilerIf #PMF_CHIP = 2712\n(?:.*\n)*?\s+#CAP_NET\s+= 1", text):
        die("the 2712 capability block does not set #CAP_NET = 1 - the boot network step is not compiled")
    text = "\n".join(l for l in text.split("\n") if l.rstrip("\r") != "#PMF_CHIP = 2711")
    src = work / "board_pi5.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "anvil5.img"
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5", "-o", str(img)], cwd=str(ROOT),
                       env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        die("the -t pi5 monitor would not build:\n" + r.stdout[-1500:] + r.stderr[-500:])
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = MON_LOAD + int(f[1])
    return img, procs


def run(img, procs, k, scen, limit=40_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[MON_LOAD + i] = b
    attach_symbols(cpu, img, MON_LOAD)
    cpu.cntpct_per_instruction = G.TICKS
    bd = G.Board(cpu, "healthy" if scen == "cable-silent" else scen, k)
    bd.pending = []
    cache = bd.cache
    tx = bytearray()
    mbx = {"pending": [], "tags": []}

    def mailbox(addr, value):
        off = addr - MBX
        if value is None:
            if off == 0x18:
                return 0 if mbx["pending"] else 0x40000000
            if off == 0x38:
                return 0
            if off == 0x00 and mbx["pending"]:
                return mbx["pending"].pop(0)
            bd.fail("mailbox read at +$%X with nothing pending" % off)
            return 0
        if off != 0x20:
            bd.fail("mailbox written at +$%X" % off)
            return 0
        a = value & ~0xF
        rd = lambda o: sum(cpu.memory.get(a + o + i, 0) << (8 * i) for i in range(4))

        def wr(o, v):
            for i in range(4):
                cpu.memory[a + o + i] = (v >> (8 * i)) & 0xFF
        tag = rd(8)
        mbx["tags"].append(tag)
        if tag == TAG_MAC:
            for i, b in enumerate(MAC):
                cpu.memory[a + 20 + i] = b
            wr(16, 0x80000006)
        else:
            wr(16, 0x80000000 | rd(12))
        wr(4, 0x80000000)
        mbx["pending"].append(value)
        return 0

    def dev(addr, sz, value):
        if UART0 <= addr < UART0 + 0x1000:
            off = addr - UART0
            if value is None:
                return 0x10 if off == 0x18 else 0
            if off == 0:
                tx.append(value & 0xFF)
            return 0
        if MBX <= addr < MBX + 0x40:
            return mailbox(addr, value)
        return bd.mmio(addr, sz, value)

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        if addr >= 0xFC000000:
            return dev(addr, sz, None) & ((1 << (8 * sz)) - 1)
        if cache.covers(addr) and not cpu.fetching:
            return cache.load(addr, sz)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        value &= (1 << (8 * sz)) - 1
        if addr >= 0xFC000000:
            dev(addr, sz, value)
            return
        if cache.covers(addr):
            cache.store(addr, value, sz)
            return
        for i in range(sz):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)
    cpu.pc, cpu.sp, cpu.x[30] = procs["bootnetup"], STACK, LR
    t0 = cpu.cntpct
    n = 0
    returned = False
    try:
        while True:
            if cpu.pc == LR:
                returned = True
                break
            n += 1
            if n > limit:
                break
            if n % G.DELIVER_EVERY == 0:
                bd.deliver()
            ins = load(cpu.pc, 4)
            if (ins & 0xFFFFFFE0) == 0xD53BE000:
                cpu.x[ins & 31] = G.CNTFRQ
                cpu.pc += 4
                cpu.cntpct += G.TICKS
                continue
            op = G.DC_OPS.get(ins & 0xFFFFFFE0)
            if op is not None:
                cache.dc(op, cpu.x[ins & 31])
                cpu.pc += 4
                cpu.cntpct += G.TICKS
                continue
            plain()
    except AlignmentFault as f:
        bd.fail(f.message())
    except RuntimeError as e:
        bd.fail("the interpreter stopped: %s" % e)
    ms = (cpu.cntpct - t0) / G.MS
    return returned, ms, tx.decode("ascii", "replace"), bd, mbx["tags"]

# THE MUTANT: the 2712 fault branch removed from EthBootWired, which is the
# wording before 2026-09-27 - an RP1 link fault printed as "wired: no cable".
# The rp1-down wording checks must go red; a mutant that does not BUILD is an
# error, not a catch.
WORDING_MUTANT = (
    "    If GemError() <> #GEM_ERR_NO_LINK\n",
    "    If 0\n",
)


def mutant(cc, k):
    eth = (ROOT / "RaspberryPi4/Board/eth.pi4").read_text(encoding="utf-8").replace("\r\n", "\n")
    old, new = WORDING_MUTANT
    if eth.count(old) != 1:
        die("the wording mutant's anchor matched %d times in eth.pi4" % eth.count(old))
    try:
        img, procs = build(cc, ROOT / "_work" / "pi5_net_boot_mut", eth.replace(old, new))
    except SystemExit as e:
        die("the wording mutant did not build - a mutant that does not build proves nothing: %s" % str(e)[:300])
    ok, ms, out, bd, tags = run(img, procs, k, "rp1-down")
    red = ("no cable" in out) or ("could not be reached" not in out)
    print("  mutant %s  an RP1 fault printed as a missing cable (%r)" % ("RED  " if red else "ALIVE", out.strip()[-120:]))
    return red


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    args = ap.parse_args()
    if not args.compiler:
        die("pass --compiler or set PMF_COMPILER")
    cc = str(pathlib.Path(resolve_compiler(args.compiler)).resolve())
    link_ms = const("RaspberryPi4/Board/eth_globals.pi4", "ETH_LINK_MS")
    tries = const("Anvil/Core/net_cmd.pbi", "DHCP_TRIES")
    reply = const("Anvil/Core/net_cmd.pbi", "DHCP_REPLY_MS")
    bound = 2 * link_ms + tries * reply + LL_WORST_MS
    print("  the bound, from the source: cable probe %d + MAC start %d + DHCP %d x %d + link-local %d = %d ms"
          % (link_ms, link_ms, tries, reply, LL_WORST_MS, bound))
    src = G.DEFAULT_SOURCES if G.DEFAULT_SOURCES.exists() else None
    k = G.constants(src)
    img, procs = build(cc, ROOT / "_work" / "pi5_net_boot")
    boot = (ROOT / "RaspberryPi4/Board/boot.pi4").read_text(encoding="utf-8", errors="replace")
    fails = []

    def check(ok, what):
        print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    check(re.search(r"CompilerIf #PMF_CHIP = 2712\s+CompilerIf #CAP_NET = 0.*?CompilerElse.*?EthBootWired\(\)",
                    boot, re.S) is not None,
          "boot.pi4: the 2712 BootNetUp calls the same EthBootWired as the Pi 4")
    # rp1-down is a CONTROLLER fault and must never be called a missing
    # cable: it must say the controller could not be reached, give the
    # driver's and the PCIe layer's own words, and NOT say "no cable".
    for scen, want, cap_ms in (("no-cable", "wired: no cable", 1500),
                               ("rp1-down", "wired: the Ethernet controller could not be reached", 1500),
                               ("cable-silent", "wired: link-local", bound),
                               ("clock-stopped", "wired: link-local", bound)):
        ok, ms, out, bd, tags = run(img, procs, k, scen)
        check(ok, "%s: BootNetUp returned (the prompt follows it)" % scen)
        check(ms <= cap_ms, "%s: in %.0f ms of model time (bound %d ms)" % (scen, ms, cap_ms))
        check(want in out, "%s: the console says %r (%r)" % (scen, want, out.strip()[-160:]))
        check(not bd.bad, "%s: the hardware model saw no misuse (%s)" % (scen, "; ".join(bd.bad[:2])))
        if scen == "rp1-down":
            check(not bd.rp1_touched, "rp1-down: RP1 never touched")
            check("no cable" not in out, "rp1-down: an RP1 fault is not called a missing cable")
            check("gem error -3" in out and "pcie error -4" in out,
                  "rp1-down: the driver's and the PCIe layer's own words are printed")
        if scen == "no-cable":
            check("could not be reached" not in out, "no-cable: a real missing cable is not called a fault")
        if scen in ("cable-silent", "clock-stopped"):
            check(TAG_MAC in tags, "%s: the MAC came from the mailbox" % scen)
        if scen == "clock-stopped":
            check((bd.ecfg.get(0x14, 0) & 0x40) == 0 and (bd.ecfg.get(0x00, 0) & 0x10) == 0,
                  "clock-stopped: eth_cfg clock generator un-killed and memory powered")
    if not mutant(cc, k):
        fails.append("the wording mutant survived")
    if fails:
        print("pi5_net_boot_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_net_boot_check: PASS - the Pi 5 boot's network step returns within the Pi 4's bound with no "
          "cable, no RP1, a silent network and a stopped GEM clock. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
