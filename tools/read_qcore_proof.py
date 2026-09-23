#!/usr/bin/env python3
# ======================================================================
#  read_qcore_proof.py - find and decode the Arduino UNO Q core-on-Q
#                        proof written by ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqcoreproof.unoq.
#
#  The proof image writes two NON-VOLATILE UEFI variables:
#    AnvilQBin  a compact struct, magic "ANVILQC1" + fixed <Q fields
#    AnvilQTxt  the core-formatted human-readable report
#  U-Boot persists NV variables to /boot/efi/ubootefi.var, and Linux also
#  exposes them under /sys/firmware/efi/efivars, so both survive the board
#  returning to Debian. This tool decodes whatever files it is given: it
#  first tries to parse a U-Boot variable store (to pull AnvilQTxt out by
#  name), and always falls back to a raw search for the "ANVILQC1" magic,
#  so it works on ubootefi.var, on a raw efivars blob, or on any dump.
#
#  Struct after the 8-byte magic (all <Q, little-endian):
#     +8   MIDR_EL1              +80  buffer address
#     +16  CNTFRQ_EL0 (Hz)       +88  buffer length
#     +24  CurrentEL raw         +96  DRAM base
#     +32  CNTPCT_EL0 #1         +104 DRAM top
#     +40  CNTPCT_EL0 #2         +112 EFI ImageHandle
#     +48  CRC32 (Q-computed)    +120 EFI SystemTable
#     +56  InPayload(buf)        +128 SystemTable signature
#     +64  HitsMonitor(buf)      +136 HwInfoIsQ
#     +72  HitsMonitor(mon)
#
#  Usage: read_qcore_proof.py <file> [<file> ...]
# ======================================================================
import sys, struct, os

MAGIC = b"ANVILQC1"
HOST_EXPECT_CRC = 0x399208A7          # zlib.crc32 of buf[i]=(i*167+13)&0xFF, N=4096
ST_SIG = 0x5453595320494249           # "IBI SYST"

def decode(buf, off):
    def q(o): return struct.unpack_from("<Q", buf, off + o)[0]
    midr   = q(8);  cntfrq = q(16); elraw  = q(24)
    pct1   = q(32); pct2   = q(40); crc    = q(48) & 0xFFFFFFFF
    inpay  = q(56); hitbuf = q(64); hitmon = q(72)
    bufa   = q(80); bufl   = q(88)
    dbase  = q(96); dtop   = q(104)
    ih     = q(112); st    = q(120); stsig = q(128); isq = q(136)

    impl = (midr >> 24) & 0xff; part = (midr >> 4) & 0xfff
    varr = (midr >> 20) & 0xf; rev = midr & 0xf

    print("  MAGIC            %s" % buf[off:off+8].decode("latin1"))
    print("  --- HwInfo (the Q's identity) ---")
    print("  MIDR_EL1         0x%016x  implementer=0x%02x(0x51=Qualcomm) part=0x%03x(0x801=A53) var=%d rev=%d"
          % (midr, impl, part, varr, rev))
    print("  HwInfoIsQ        %d  (1 => MIDR is a QCM2290 Cortex-A53)" % isq)
    print("  CNTFRQ_EL0       %d Hz (%.2f MHz)" % (cntfrq, cntfrq/1e6))
    print("  CurrentEL(raw)   0x%x -> EL%d" % (elraw, (elraw >> 2) & 3))
    print("  DRAM             base 0x%x  top 0x%x  (%.2f GB)" % (dbase, dtop, (dtop-dbase)/2**30))
    print("  --- HwTimer (arch timer, live execution) ---")
    print("  CNTPCT_EL0 #1    0x%016x (%d)" % (pct1, pct1))
    print("  CNTPCT_EL0 #2    0x%016x (%d)  delta=%d" % (pct2, pct2, pct2 - pct1))
    print("  --- core compute (crc.pbi KNOWN-ANSWER TEST) ---")
    print("  buffer           addr 0x%x  len %d" % (bufa, bufl))
    print("  crc32 Q-computed 0x%08x" % crc)
    print("  crc32 host-expect0x%08x" % HOST_EXPECT_CRC)
    crc_ok = (crc == HOST_EXPECT_CRC)
    print("  CRC KAT          %s" % ("MATCH - core compute correct on Q silicon" if crc_ok
                                     else "*** MISMATCH ***"))
    print("  --- core memrange (memrange.pbi) ---")
    print("  InPayload(buf)   %d  (expect 1: buffer is in Q DRAM)" % inpay)
    print("  HitsMonitor(buf) %d  (expect 0)" % hitbuf)
    print("  HitsMonitor(mon) %d  (expect non-zero)" % hitmon)
    print("  --- UEFI ---")
    print("  ImageHandle      0x%016x" % ih)
    print("  SystemTable      0x%016x" % st)
    st_ok = (stsig == ST_SIG)
    print("  ST signature     0x%016x  %s" % (stsig, "(== 'IBI SYST')" if st_ok else "(UNEXPECTED)"))

    pct_ok = (pct2 > pct1)
    allok = crc_ok and st_ok and pct_ok and inpay == 1 and hitbuf == 0 and hitmon != 0 and isq == 1
    print("  VERDICT          %s" % ("PASS - Anvil core runs correctly on the Q's A53"
                                     if allok else "INCOMPLETE/FAIL - see fields above"))
    return allok

def try_uboot_store(buf):
    # Pull AnvilQTxt out of a U-Boot EFI variable store, if this file is one.
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import ubootefi_var as ub
        _, _, ok, entries = ub.parse(buf)
        for e in entries:
            if e["name"] == "AnvilQTxt":
                txt = e["data"].split(b"\x00", 1)[0].decode("latin1")
                print("  --- AnvilQTxt (core-formatted report) ---")
                for line in txt.splitlines():
                    print("    " + line)
    except Exception:
        pass

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: read_qcore_proof.py <file> [<file> ...]")
    found = 0
    for path in sys.argv[1:]:
        try:
            buf = open(path, "rb").read()
        except OSError as e:
            print("[skip] %s: %s" % (path, e)); continue
        off = buf.find(MAGIC)
        if off < 0:
            print("[----] %s: proof magic NOT present" % path); continue
        print("[FOUND] %s: ANVILQC1 at offset 0x%x" % (path, off))
        decode(buf, off)
        try_uboot_store(buf)
        found += 1
        print()
    sys.exit(0 if found else 2)

if __name__ == "__main__":
    main()
