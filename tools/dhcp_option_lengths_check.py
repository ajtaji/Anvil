#!/usr/bin/env python3
"""EVERY DHCP OPTION THE BOARD BUILDS SAYS ITS OWN LENGTH TRUTHFULLY.

Anvil/Network/dhcp.pbi writes each option as three statements:

    dhcp_out[p + 0] = <code>
    dhcp_out[p + 1] = <length>
    ...the value...
    p = p + <advance>

and the advance must be the length plus the two bytes of code and length.
Until 2026-10-15 DhcpBuildReboot wrote option 50 (requested IP) with length
5 and advanced 6: the server read the next option's code byte as a fifth
address byte and every option after it misaligned. That is the INIT-REBOOT
request every rejoin sends after a link loss, the router ignored it, and the
board sat keyed with no address until a reset (which starts in INIT and
sends a DISCOVER instead). No gate built that packet, so nothing saw it.

This gate reads the source - it runs nothing, so it needs no board and no
emulator - and checks every option block of every builder: the advance is
length + 2, a 4-byte value (net_PutBE32) is length 4, and a block whose
shape it cannot read is a FAILURE, not a skip.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Anvil" / "Network" / "dhcp.pbi"

CODE = re.compile(r"^\s*dhcp_out\[p \+ 0\] = (#?\w+)\s*(;.*)?$")
LEN = re.compile(r"^\s*dhcp_out\[p \+ 1\] = (\d+)\s*(;.*)?$")
ADV = re.compile(r"^\s*p = p \+ (\d+)\s*(;.*)?$")
RET = re.compile(r"^\s*ProcedureReturn p \+ (\d+)\s*(;.*)?$")
PROC = re.compile(r"^\s*Procedure(?:\.\w+)?\s+(\w+)\(")


def main() -> int:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    proc = "?"
    blocks = 0
    bad = []
    i = 0
    while i < len(lines):
        m = PROC.match(lines[i])
        if m:
            proc = m.group(1)
        m = CODE.match(lines[i])
        if not m:
            i += 1
            continue
        code = m.group(1)
        where = "%s:%d (%s, option %s)" % (SRC.name, i + 1, proc, code)
        ml = LEN.match(lines[i + 1]) if i + 1 < len(lines) else None
        if not ml:
            bad.append("%s: no `dhcp_out[p + 1] = <length>` on the next line" % where)
            i += 1
            continue
        length = int(ml.group(1))
        adv = None
        put32 = False
        j = i + 2
        while j < len(lines) and j < i + 40:
            if "net_PutBE32(@dhcp_out[p + 2]" in lines[j]:
                put32 = True
            ma = ADV.match(lines[j]) or RET.match(lines[j])
            if ma:
                adv = int(ma.group(1))
                break
            if CODE.match(lines[j]) or PROC.match(lines[j]):
                break
            j += 1
        blocks += 1
        if adv is None:
            bad.append("%s: length %d, but no `p = p + N` advance was found" % (where, length))
        elif adv != length + 2:
            bad.append("%s: length byte %d but the builder advances %d (it must be length + 2 = %d)"
                       % (where, length, adv, length + 2))
        if put32 and length != 4:
            bad.append("%s: writes a 4-byte value (net_PutBE32) but says length %d" % (where, length))
        i = j if j > i else i + 1
    print("dhcp_option_lengths_check: %d option blocks in %s" % (blocks, SRC.relative_to(ROOT)))
    if blocks < 6:
        bad.append("only %d option blocks found - the reader no longer matches the source" % blocks)
    for b in bad:
        print("  FAIL  " + b)
    print("RESULT: %s" % ("PASS" if not bad else "FAIL - %d problem(s)" % len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
