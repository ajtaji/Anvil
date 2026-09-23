#!/usr/bin/env python3
# ======================================================================
#  read_anvil_proof.py - find and decode the Arduino UNO Q probe's proof.
#
#  The probe (ArduinoQ/Examples/Diagnostics/anvilqprobe.unoq) writes a NON-VOLATILE UEFI
#  variable "AnvilProof" whose data begins with the 8-byte ASCII magic
#  "ANVILQ01" followed by a fixed little-endian struct. U-Boot persists
#  NV variables to /boot/efi/ubootefi.var and Linux exposes them under
#  /sys/firmware/efi/efivars, so the proof survives the machine returning
#  to Linux. This tool searches whatever files it is given for the magic
#  and decodes the struct - it does NOT need to parse U-Boot's variable
#  store format, so it is robust to that format's details.
#
#  Struct after the 8-byte magic (all <Q, little-endian):
#     +8   MIDR_EL1
#     +16  CNTFRQ_EL0 (Hz)
#     +24  CurrentEL raw  (EL = value >> 2)
#     +32  CNTPCT_EL0 sample #1
#     +40  EFI ImageHandle
#     +48  EFI SystemTable
#     +56  SystemTable signature word (should be 0x5453595320494249)
#     +64  CNTPCT_EL0 sample #2
#
#  Usage: read_anvil_proof.py <file> [<file> ...]
# ======================================================================
import sys, struct

MAGIC = b"ANVILQ01"

def decode(buf, off):
    def q(o):
        return struct.unpack_from("<Q", buf, off + o)[0]
    midr   = q(8)
    cntfrq = q(16)
    elraw  = q(24)
    pct1   = q(32)
    ih     = q(40)
    st     = q(48)
    stsig  = q(56)
    pct2   = q(64)
    print("  MAGIC            %s" % buf[off:off+8].decode("latin1"))
    print("  MIDR_EL1         0x%016x" % midr)
    impl = (midr >> 24) & 0xff
    part = (midr >> 4) & 0xfff
    rev  = midr & 0xf
    varr = (midr >> 20) & 0xf
    print("                   implementer=0x%02x (0x51=Qualcomm) partnum=0x%03x (0x801=Cortex-A53) variant=%d rev=%d"
          % (impl, part, varr, rev))
    print("  CNTFRQ_EL0       %d Hz  (%.2f MHz)" % (cntfrq, cntfrq / 1e6))
    print("  CurrentEL(raw)   0x%x  -> EL%d" % (elraw, (elraw >> 2) & 3))
    print("  CNTPCT_EL0 #1    0x%016x (%d)" % (pct1, pct1))
    print("  CNTPCT_EL0 #2    0x%016x (%d)  delta=%d" % (pct2, pct2, pct2 - pct1))
    print("  EFI ImageHandle  0x%016x" % ih)
    print("  EFI SystemTable  0x%016x" % st)
    ok = (stsig == 0x5453595320494249)
    print("  ST signature     0x%016x  %s" % (stsig, "(== 'IBI SYST' EFI_SYSTEM_TABLE)" if ok else "(UNEXPECTED)"))
    return ok

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: read_anvil_proof.py <file> [<file> ...]")
    found = 0
    for path in sys.argv[1:]:
        try:
            buf = open(path, "rb").read()
        except OSError as e:
            print("[skip] %s: %s" % (path, e))
            continue
        off = buf.find(MAGIC)
        if off < 0:
            print("[----] %s: proof magic NOT present" % path)
            continue
        print("[FOUND] %s: proof at offset 0x%x" % (path, off))
        decode(buf, off)
        found += 1
        print()
    sys.exit(0 if found else 2)

if __name__ == "__main__":
    main()
