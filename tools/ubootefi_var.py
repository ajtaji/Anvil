#!/usr/bin/env python3
# ======================================================================
#  ubootefi_var.py - read / add / remove variables in U-Boot's EFI
#                    variable store file (/boot/efi/ubootefi.var).
#
#  WHY THIS EXISTS: on the Arduino UNO Q, U-Boot's EFI runtime does not
#  let Linux write EFI variables (efivarfs is mounted read-only), so
#  `bootctl set-oneshot` fails with "Read-only file system". The store is
#  a plain file that U-Boot LOADS at boot, so a one-shot boot selection
#  can be seeded by editing that file directly. The only integrity check
#  is a CRC32 (Secure Boot is in setup mode), and if the CRC is wrong
#  U-Boot discards the store and auto-boots the default - so a bad edit is
#  non-destructive (the board still boots Debian).
#
#  FORMAT (little-endian), verified by round-trip against the live file:
#     u64 reserved (0)
#     u8  magic[8] = "UbEfiVa\x01"
#     u32 length            total store length in bytes
#     u32 crc32             crc32 of bytes[24:length]
#     entries[]  from offset 24, each (the whole entry padded to 8 bytes):
#         u32 datalength    length of the value bytes only
#         u32 attributes
#         u64 time          (0)
#         u8  guid[16]
#         u16 name[]        null-terminated UTF-16LE
#         u8  data[datalength]
#         u8  pad[]          zero pad so the next entry is 8-byte aligned
#
#  Usage:
#     ubootefi_var.py verify  <file>
#     ubootefi_var.py list    <file>
#     ubootefi_var.py add     <in> <out> <GUID> <Name> --str <VALUE> [--attr 0x7]
#     ubootefi_var.py remove  <in> <out> <GUID> <Name>
#  <GUID> is the usual 8-4-4-4-12 hex form. --str stores VALUE as a
#  null-terminated UTF-16LE string (how systemd-boot stores LoaderEntry*).
# ======================================================================
import sys, struct, binascii

# The header above is COMMENTS, not a docstring, so __doc__ is None here.
# main() used to `sys.exit(__doc__)` when it was short of arguments, which
# is sys.exit(None) - EXIT 0, IN TOTAL SILENCE, the exact shape of tid 502.
# A bare run of this tool printed nothing and reported success. Found and
# fixed while sweeping the siblings for that bug, 2026-09-03.
USAGE = """\
ubootefi_var.py - read / add / remove variables in U-Boot's EFI variable store.

    ubootefi_var.py verify  <file>
    ubootefi_var.py list    <file>
    ubootefi_var.py add     <in> <out> <GUID> <Name> --str <VALUE> [--attr 0x7]
    ubootefi_var.py remove  <in> <out> <GUID> <Name>

<GUID> is the usual 8-4-4-4-12 hex form. --str stores VALUE as a
null-terminated UTF-16LE string (how systemd-boot stores LoaderEntry*)."""

MAGIC = b"UbEfiVa\x01"
HDR = 24  # reserved(8)+magic(8)+length(4)+crc(4)

def guid_to_bytes(s):
    s = s.replace("{", "").replace("}", "").strip()
    p = s.split("-")
    d1 = int(p[0], 16); d2 = int(p[1], 16); d3 = int(p[2], 16)
    d4 = bytes.fromhex(p[3]) + bytes.fromhex(p[4])
    return struct.pack("<IHH", d1, d2, d3) + d4

def bytes_to_guid(b):
    d1, d2, d3 = struct.unpack_from("<IHH", b, 0)
    return "%08x-%04x-%04x-%s-%s" % (d1, d2, d3,
        binascii.hexlify(b[8:10]).decode(), binascii.hexlify(b[10:16]).decode())

def align8(n):
    return (n + 7) & ~7

def parse(d):
    assert d[8:16] == MAGIC, "bad magic %r" % d[8:16]
    length, crc = struct.unpack_from("<II", d, 16)
    body = d[24:length]
    want = binascii.crc32(body) & 0xffffffff
    ok = (want == crc)
    entries = []
    off = 24
    while off + 32 <= length:
        dlen, attr = struct.unpack_from("<II", d, off)
        time, = struct.unpack_from("<Q", d, off + 8)
        guid = d[off + 16:off + 32]
        # UTF-16LE null-terminated name
        p = off + 32
        nm = b""
        while p + 1 < length:
            w = d[p:p + 2]
            p += 2
            if w == b"\x00\x00":
                break
            nm += w
        name = nm.decode("utf-16-le")
        data = d[p:p + dlen]
        entries.append({"attr": attr, "time": time, "guid": guid,
                        "name": name, "data": data})
        off = align8(p + dlen)
    return length, crc, ok, entries

def build_entry(attr, guid_b, name, data):
    nm = name.encode("utf-16-le") + b"\x00\x00"
    raw = struct.pack("<I", len(data)) + struct.pack("<I", attr) + struct.pack("<Q", 0) + guid_b + nm + data
    raw = raw + b"\x00" * (align8(len(raw)) - len(raw))
    return raw

def serialize(entries):
    body = b""
    for e in entries:
        body += build_entry(e["attr"], e["guid"], e["name"], e["data"])
    length = HDR + len(body)
    out = bytearray()
    out += struct.pack("<Q", 0)
    out += MAGIC
    out += struct.pack("<I", length)
    out += struct.pack("<I", binascii.crc32(body) & 0xffffffff)
    out += body
    return bytes(out)

def cmd_verify(argv):
    d = open(argv[0], "rb").read()
    length, crc, ok, entries = parse(d)
    print("length=%d filelen=%d crc=0x%08x crc_ok=%s entries=%d" %
          (length, len(d), crc, ok, len(entries)))
    # round-trip: reserialize the parsed entries and compare
    rt = serialize(entries)
    same = (rt == d[:length])
    print("round-trip identical to bytes[:length]: %s" % same)
    return 0 if (ok and same) else 1

def cmd_list(argv):
    d = open(argv[0], "rb").read()
    _, _, ok, entries = parse(d)
    for e in entries:
        val = ""
        try:
            if len(e["data"]) >= 2 and len(e["data"]) % 2 == 0:
                cand = e["data"].decode("utf-16-le").rstrip("\x00")
                if cand.isprintable():
                    val = "val=" + ascii(cand)
        except Exception:
            val = ""
        line = "  %-20s %s attr=0x%x dlen=%d %s" % (
            e["name"], bytes_to_guid(e["guid"]), e["attr"], len(e["data"]), val)
        sys.stdout.buffer.write((line + "\n").encode("ascii", "backslashreplace"))
    return 0

def cmd_add(argv):
    inp, outp, guid, name = argv[0], argv[1], argv[2], argv[3]
    attr = 0x7
    value = None
    i = 4
    while i < len(argv):
        if argv[i] == "--str":
            i += 1; value = argv[i]
        elif argv[i] == "--attr":
            i += 1; attr = int(argv[i], 0)
        i += 1
    if value is None:
        sys.exit("add needs --str VALUE")
    d = open(inp, "rb").read()
    length, crc, ok, entries = parse(d)
    if not ok:
        sys.exit("refusing to edit: source CRC bad")
    gb = guid_to_bytes(guid)
    entries = [e for e in entries if not (e["name"] == name and e["guid"] == gb)]
    data = value.encode("utf-16-le") + b"\x00\x00"
    entries.append({"attr": attr, "guid": gb, "name": name, "data": data})
    out = serialize(entries)
    open(outp, "wb").write(out)
    l2, c2, ok2, e2 = parse(out)
    print("wrote %s: length=%d crc=0x%08x crc_ok=%s entries=%d (added %s=%r)" %
          (outp, l2, c2, ok2, len(e2), name, value))
    return 0 if ok2 else 1

def cmd_remove(argv):
    inp, outp, guid, name = argv[0], argv[1], argv[2], argv[3]
    d = open(inp, "rb").read()
    length, crc, ok, entries = parse(d)
    gb = guid_to_bytes(guid)
    n0 = len(entries)
    entries = [e for e in entries if not (e["name"] == name and e["guid"] == gb)]
    out = serialize(entries)
    open(outp, "wb").write(out)
    print("wrote %s: removed %d entry(ies) named %s" % (outp, n0 - len(entries), name))
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    if len(sys.argv) < 3:
        print("!! this tool needs a command and a file.")
        print(USAGE)
        return 2
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    # An unrecognised command used to raise KeyError and print a traceback.
    # It exited non-zero, so it was never the silent no-op of tid 502, but a
    # traceback is not a refusal: it names a dict lookup instead of naming
    # the commands. Swept with that bug, 2026-09-03.
    table = {"verify": cmd_verify, "list": cmd_list, "add": cmd_add,
             "remove": cmd_remove}
    if cmd not in table:
        print("!! not a command this tool knows: %r" % cmd)
        print("   known commands: %s" % ", ".join(sorted(table)))
        print(USAGE)
        return 2
    return table[cmd](rest)

if __name__ == "__main__":
    sys.exit(main())
