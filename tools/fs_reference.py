#!/usr/bin/env python3
"""Host-side reference for FAT32 and exFAT: format small volumes, parse them
back and check them against the published specifications, independently of
Anvil's own filesystem code.

This is the "different implementation" the file-operation gate
(tools/fileops_check.py) reads a finished medium with. Nothing here imports,
calls or shares a line with Anvil/Storage/*.pbi.

Specifications (cited by section, since neither document is kept in this
repository):
  [FATGEN] Microsoft EFI FAT32 File System Specification 1.03 ("fatgen103"):
           BPB layout, FAT type determination, FSInfo, FAT[0]/FAT[1] and the
           ClnShutBitMask / HrdErrBitMask bits, the directory entry, long
           directory entries and ChkSum(), the basis-name and numeric-tail
           algorithms, "." and ".." entries.
  [EXFAT]  Microsoft exFAT File System Specification (learn.microsoft.com,
           windows/win32/fileio/exfat-specification): 3.1 Main Boot Sector,
           3.1.13 VolumeFlags, 3.1.18 PercentInUse, 3.2 Extended Boot
           Sectors, 3.4 Main and Backup Boot Checksum, 4.1 FAT entries, 6.x
           generic directory entries and set checksum (6.3.3), 7.1
           Allocation Bitmap, 7.2 Up-case Table, 7.4 File entry and its
           timestamps / UtcOffset, 7.6 Stream Extension (ValidDataLength,
           DataLength, NoFatChain), 7.7 File Name and its invalid characters
           and reserved names, 7.7.? name hash.

check_fat32() and check_exfat() return a Report: `errors` are damage a repair
tool must fix by choosing (cross-links, entries naming free clusters, broken
checksums, sizes the chain cannot hold); `benign` are leftovers a repair tool
reclaims without losing data (lost clusters, orphaned long-name entries or
exFAT secondaries, a stale free count); `dirty` is the volume's own flag.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SEC = 512


# ======================================================================
#  common
# ======================================================================
@dataclass
class Entry:
    path: str
    is_dir: bool
    size: int
    data: bytes | None
    attr: int
    first: int
    times: dict = field(default_factory=dict)


@dataclass
class Report:
    kind: str
    errors: list = field(default_factory=list)
    benign: list = field(default_factory=list)
    dirty: bool = False
    tree: dict = field(default_factory=dict)      # path -> Entry
    info: dict = field(default_factory=dict)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def ben(self, msg: str) -> None:
        self.benign.append(msg)


def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def u64(b, o): return struct.unpack_from("<Q", b, o)[0]


def fat_date_ok(d: int) -> bool:
    return 1 <= (d >> 5) & 15 <= 12 and 1 <= d & 31 <= 31


def fat_time_ok(t: int) -> bool:
    return (t >> 11) <= 23 and (t >> 5) & 63 <= 59 and t & 31 <= 29


def mbr(img: bytearray, parts: list) -> None:
    """parts: list of (type, lba, sectors) for slots 1..4."""
    for i, (ptype, lba, count) in enumerate(parts):
        off = 0x1BE + 16 * i
        img[off:off + 16] = bytes([0, 0xFE, 0xFF, 0xFF, ptype, 0xFE, 0xFF, 0xFF]) + struct.pack("<II", lba, count)
    img[510] = 0x55
    img[511] = 0xAA


# The case fold the tests use to decide what "the same name" means. It is
# deliberately the plain Unicode simple upper-case of one code unit, which is
# what both formats' up-case tables approximate; the gate's names stay inside
# the ranges where Windows, Anvil and Python agree.
def fold(s: str) -> str:
    out = []
    for ch in s:
        u = ch.upper()
        out.append(u if len(u) == 1 and ord(u) < 0x10000 else ch)
    return "".join(out)


# ======================================================================
#  FAT32
# ======================================================================
FAT_EOC = 0x0FFFFFFF
FAT_CLEAN = 0x08000000
FAT_HARDERR = 0x04000000
SHORT_OK = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&")


def lfn_checksum(name11: bytes) -> int:
    s = 0
    for c in name11:
        s = (((s & 1) << 7) + (s >> 1) + c) & 0xFF
    return s


class Fat32Image:
    """A FAT32 volume inside a disk image, for formatting and fixtures."""

    def __init__(self, img: bytearray, part_lba: int):
        self.img = img
        self.p = part_lba
        b = self.sec(0)
        self.spc = b[13]
        self.rsvd = u16(b, 14)
        self.nfats = b[16]
        self.fatsz = u32(b, 36)
        self.totsec = u32(b, 32)
        self.root = u32(b, 44)
        self.fsinfo = u16(b, 48)
        self.data = self.rsvd + self.nfats * self.fatsz
        self.count = (self.totsec - self.data) // self.spc
        self.cbytes = self.spc * SEC

    def sec(self, n: int) -> memoryview:
        o = (self.p + n) * SEC
        return memoryview(self.img)[o:o + SEC]

    def fat(self, cl: int, copy: int = 0) -> int:
        o = (self.p + self.rsvd + copy * self.fatsz) * SEC + cl * 4
        return u32(self.img, o) & 0x0FFFFFFF

    def raw_fat(self, cl: int, copy: int = 0) -> int:
        return u32(self.img, (self.p + self.rsvd + copy * self.fatsz) * SEC + cl * 4)

    def set_fat(self, cl: int, v: int) -> None:
        for c in range(self.nfats):
            o = (self.p + self.rsvd + c * self.fatsz) * SEC + cl * 4
            old = u32(self.img, o)
            struct.pack_into("<I", self.img, o, (old & 0xF0000000) | (v & 0x0FFFFFFF))

    def clus_off(self, cl: int) -> int:
        return (self.p + self.data + (cl - 2) * self.spc) * SEC

    def set_fsinfo(self, free: int, nxt: int) -> None:
        o = (self.p + self.fsinfo) * SEC
        struct.pack_into("<II", self.img, o + 0x1E8, free & 0xFFFFFFFF, nxt & 0xFFFFFFFF)

    def free_count(self) -> int:
        return sum(1 for cl in range(2, self.count + 2) if self.fat(cl) == 0)

    def dir_slots(self, first: int):
        cl = first
        seen = 0
        while 2 <= cl < 0x0FFFFFF8 and seen <= self.count:
            base = self.clus_off(cl)
            for i in range(self.cbytes // 32):
                yield base + i * 32
            cl = self.fat(cl)
            seen += 1

    def add_root_entry(self, short11: bytes, attr: int, first: int, size: int, long: str | None = None,
                       ntres: int = 0, date: int = 0x0021, time: int = 0) -> None:
        ents = []
        if long is not None:
            units = list(long.encode("utf-16-le"))
            units = [units[i] | (units[i + 1] << 8) for i in range(0, len(units), 2)]
            n = (len(units) + 12) // 13
            pad = units + ([0] if len(units) % 13 else []) + [0xFFFF] * 13
            chk = lfn_checksum(short11)
            for k in range(n, 0, -1):
                e = bytearray(32)
                e[0] = k | (0x40 if k == n else 0)
                e[11] = 0x0F
                e[13] = chk
                chars = pad[(k - 1) * 13:(k - 1) * 13 + 13]
                for j, off in enumerate((1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)):
                    struct.pack_into("<H", e, off, chars[j])
                ents.append(bytes(e))
        e = bytearray(32)
        e[0:11] = short11
        e[11] = attr
        e[12] = ntres
        struct.pack_into("<HHH", e, 14, time, date, date)
        struct.pack_into("<H", e, 20, first >> 16)
        struct.pack_into("<HH", e, 22, time, date)
        struct.pack_into("<HI", e, 26, first & 0xFFFF, size)
        ents.append(bytes(e))
        slots = list(self.dir_slots(self.root))
        for i in range(len(slots)):
            if all(self.img[slots[j]] in (0, 0xE5) for j in range(i, i + len(ents))) and i + len(ents) <= len(slots):
                for j, ent in enumerate(ents):
                    self.img[slots[i + j]:slots[i + j] + 32] = ent
                return
        raise ValueError("root directory full in fixture")

    def alloc_contiguous(self, start: int, n: int) -> None:
        for k in range(n):
            self.set_fat(start + k, start + k + 1 if k + 1 < n else FAT_EOC)


def format_fat32(img: bytearray, part_lba: int, sectors: int, label: bytes = b"ANVILGATE  ") -> Fat32Image:
    rsvd, nfats, spc = 32, 2, 1
    fatsz = 1
    while True:
        clusters = (sectors - rsvd - nfats * fatsz) // spc
        need = ((clusters + 2) * 4 + SEC - 1) // SEC
        if need <= fatsz:
            break
        fatsz = need
    if clusters < 65525:
        raise ValueError("too small for FAT32: %d clusters" % clusters)
    o = part_lba * SEC
    img[o:o + (rsvd + nfats * fatsz + spc) * SEC] = bytes((rsvd + nfats * fatsz + spc) * SEC)
    b = bytearray(SEC)
    b[0:3] = b"\xEB\x58\x90"
    b[3:11] = b"MSWIN4.1"
    struct.pack_into("<HBHBHHBHHHII", b, 11, SEC, spc, rsvd, nfats, 0, 0, 0xF8, 0, 63, 255, part_lba, sectors)
    struct.pack_into("<IHHIHH", b, 36, fatsz, 0, 0, 2, 1, 6)
    b[64] = 0x80
    b[66] = 0x29
    struct.pack_into("<I", b, 67, 0x2026_0917)
    b[71:82] = label
    b[82:90] = b"FAT32   "
    b[510], b[511] = 0x55, 0xAA
    fsi = bytearray(SEC)
    struct.pack_into("<I", fsi, 0, 0x41615252)
    struct.pack_into("<I", fsi, 484, 0x61417272)
    struct.pack_into("<II", fsi, 488, clusters - 1, 3)
    struct.pack_into("<I", fsi, 508, 0xAA550000)
    third = bytearray(SEC)
    third[510], third[511] = 0x55, 0xAA
    for base in (0, 6):
        img[o + base * SEC:o + (base + 1) * SEC] = b
        img[o + (base + 1) * SEC:o + (base + 2) * SEC] = fsi
        img[o + (base + 2) * SEC:o + (base + 3) * SEC] = third
    v = Fat32Image(img, part_lba)
    for c in range(nfats):
        fo = (part_lba + rsvd + c * fatsz) * SEC
        struct.pack_into("<III", img, fo, 0x0FFFFFF8, 0x0FFFFFFF, FAT_EOC)
    v.add_root_entry(label, 0x08, 0, 0)
    return v


def _fat_short_name_text(e: bytes) -> str:
    base = e[0:8].rstrip(b" ")
    ext = e[8:11].rstrip(b" ")
    if base[:1] == b"\x05":
        base = b"\xE5" + base[1:]
    if e[12] & 0x08:
        base = base.lower()
    if e[12] & 0x10:
        ext = ext.lower()
    t = base.decode("latin-1")
    if ext:
        t += "." + ext.decode("latin-1")
    return t


def check_fat32(img: bytes, part_lba: int, read_data: bool = True) -> Report:
    r = Report("FAT32")
    try:
        v = Fat32Image(bytearray(img) if not isinstance(img, bytearray) else img, part_lba)
    except Exception as e:  # noqa: BLE001
        r.err("boot sector unreadable: %s" % e)
        return r
    b = bytes(v.sec(0))
    if b[510:512] != b"\x55\xAA" or u16(b, 11) != SEC:
        r.err("boot sector signature or sector size wrong")
        return r
    if v.count < 65525:
        r.err("cluster count %d is not FAT32" % v.count)
    # [FATGEN] backup boot sector at BPB_BkBootSec is the same as the boot sector
    bk = u16(b, 50)
    if bk and bytes(v.sec(bk)) != b:
        r.err("backup boot sector differs from the boot sector")
    # FATs mirrored ([FATGEN] BPB_ExtFlags bit 7 clear)
    if not u16(b, 40) & 0x80:
        for c in range(1, v.nfats):
            a = (part_lba + v.rsvd) * SEC
            z = (part_lba + v.rsvd + c * v.fatsz) * SEC
            # FAT[1]'s dirty bits are written copy by copy like any entry;
            # a difference there alone is the moment between two writes.
            if img[a + 8:a + (v.count + 2) * 4] != img[z + 8:z + (v.count + 2) * 4] or img[a:a + 4] != img[z:z + 4]:
                r.ben("FAT copy %d differs from FAT copy 0" % c)
    fat1 = v.raw_fat(1)
    r.dirty = not (fat1 & FAT_CLEAN)
    r.info["fat1"] = fat1
    if not (fat1 & FAT_HARDERR):
        r.err("FAT[1] records a hard error")
    if v.raw_fat(0) & 0x0FFFFFFF != 0x0FFFFF00 | b[21]:
        r.err("FAT[0] does not carry the media byte")

    owner: dict[int, str] = {}

    def chain(first: int, what: str) -> list:
        out = []
        cl = first
        while True:
            if not 2 <= cl <= v.count + 1:
                r.err("%s: chain reaches cluster %d outside the volume" % (what, cl))
                return out
            if cl in owner:
                r.err("%s: cluster %d is cross-linked with %s" % (what, cl, owner[cl]))
                return out
            owner[cl] = what
            out.append(cl)
            nxt = v.fat(cl)
            if nxt >= 0x0FFFFFF8:
                return out
            if nxt == 0:
                r.err("%s: chain runs into cluster %d which the FAT calls free" % (what, cl))
                return out
            if nxt == 0x0FFFFFF7:
                r.err("%s: chain reaches a bad-cluster mark" % what)
                return out
            cl = nxt

    queue = [("", v.root, 0)]
    while queue:
        dpath, first, parent = queue.pop(0)
        dchain = chain(first, dpath or "/")
        slots = [v.clus_off(c) + i * 32 for c in dchain for i in range(v.cbytes // 32)]
        if len(slots) > 65536:
            r.err("%s: directory holds more than 65536 entries" % (dpath or "/"))
        lfn = None
        ended = False
        shorts: dict[bytes, str] = {}
        longs: dict[str, str] = {}
        for idx, off in enumerate(slots):
            e = bytes(img[off:off + 32])
            if ended:
                if e[0] != 0:
                    r.ben("%s: slot %d after the end marker is not zero" % (dpath or "/", idx))
                continue
            if e[0] == 0:
                ended = True
                if lfn:
                    r.ben("%s: orphaned long-name entries before the end marker" % (dpath or "/"))
                lfn = None
                continue
            if e[0] == 0xE5:
                if lfn:
                    r.ben("%s: orphaned long-name entries (%d)" % (dpath or "/", len(lfn["ents"])))
                lfn = None
                continue
            attr = e[11]
            if attr & 0x3F == 0x0F:
                ordv = e[0] & 0x3F
                if e[12] != 0 or u16(e, 26) != 0 or not 1 <= ordv <= 20:
                    r.ben("%s: malformed long-name entry" % (dpath or "/"))
                    lfn = None
                    continue
                chars = [u16(e, o) for o in (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)]
                if e[0] & 0x40:
                    if lfn:
                        r.ben("%s: orphaned long-name entries" % (dpath or "/"))
                    lfn = {"n": ordv, "expect": ordv, "chk": e[13], "chars": {}, "ents": [off]}
                    lfn["chars"][ordv] = chars
                elif lfn and ordv == lfn["expect"] - 1 and e[13] == lfn["chk"]:
                    lfn["expect"] = ordv
                    lfn["chars"][ordv] = chars
                    lfn["ents"].append(off)
                else:
                    r.ben("%s: long-name entry out of sequence" % (dpath or "/"))
                    lfn = None
                continue
            if attr & 0x08:
                if dpath or lfn:
                    r.err("%s: volume label entry outside the root" % dpath)
                lfn = None
                continue
            name11 = e[0:11]
            long = None
            if lfn:
                if lfn["expect"] == 1 and lfn["chk"] == lfn_checksum(name11):
                    units = []
                    for k in range(1, lfn["n"] + 1):
                        units += lfn["chars"][k]
                    if 0 in units:
                        tail = units[units.index(0) + 1:]
                        units = units[:units.index(0)]
                        if any(c != 0xFFFF for c in tail):
                            r.ben("%s: long name padding is not FFFF" % (dpath or "/"))
                    long = struct.pack("<%dH" % len(units), *units).decode("utf-16-le", "replace")
                else:
                    r.ben("%s: orphaned long-name entries before %r" % (dpath or "/", name11))
                lfn = None
            first_c = (u16(e, 20) << 16) | u16(e, 26)
            size = u32(e, 28)
            if name11 in (b".          ", b"..         "):
                if not dpath:
                    r.err("/: dot entry in the root")
                elif idx > 1:
                    r.err("%s: dot entry not in the first two slots" % dpath)
                elif name11[1] == 0x20 and first_c != first:
                    r.err("%s: '.' names cluster %d, not %d" % (dpath, first_c, first))
                elif name11[1] == 0x2E and first_c != (parent if parent != v.root else 0):
                    r.err("%s: '..' names cluster %d, not its parent %d" % (dpath, first_c, parent if parent != v.root else 0))
                continue
            if dpath and idx < 2:
                r.err("%s: slot %d should be a dot entry" % (dpath, idx))
            if any(c not in SHORT_OK and c != 0x20 for c in name11) or name11[0] == 0x20:
                if not (name11[0] == 0x05):
                    r.err("%s: short name %r holds a character a short name may not" % (dpath or "/", name11))
            if name11 in shorts:
                r.err("%s: short name %r used twice" % (dpath or "/", name11))
            shorts[name11] = dpath
            display = long if long is not None else _fat_short_name_text(e)
            key = fold(display)
            if key in longs:
                r.err("%s: name %r collides with %r" % (dpath or "/", display, longs[key]))
            longs[key] = display
            path = (dpath + "/" + display) if dpath else "/" + display
            times = {"crt": (u16(e, 16), u16(e, 14), e[13]), "wrt": (u16(e, 24), u16(e, 22)), "acc": u16(e, 18)}
            for label, d in (("creation", u16(e, 16)), ("write", u16(e, 24)), ("access", u16(e, 18))):
                if not fat_date_ok(d):
                    r.err("%s: %s date %04X is not a date" % (path, label, d))
            if not fat_time_ok(u16(e, 22)) or not fat_time_ok(u16(e, 14)) or e[13] > 199:
                r.err("%s: a time field is not a time" % path)
            if attr & 0x10:
                if size != 0:
                    r.err("%s: directory with a nonzero size" % path)
                if not 2 <= first_c <= v.count + 1:
                    r.err("%s: directory with no cluster" % path)
                    continue
                r.tree[path] = Entry(path, True, 0, None, attr, first_c, times)
                queue.append((path, first_c, first))
            else:
                data = None
                if size == 0:
                    if first_c != 0:
                        r.err("%s: empty file with a first cluster" % path)
                    data = b""
                else:
                    ch = chain(first_c, path)
                    need = (size + v.cbytes - 1) // v.cbytes
                    if len(ch) < need:
                        r.err("%s: %d bytes need %d clusters, chain has %d" % (path, size, need, len(ch)))
                    elif len(ch) > need:
                        r.ben("%s: chain holds %d clusters, %d needed" % (path, len(ch), need))
                    if read_data:
                        data = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes]) for c in ch)[:size]
                r.tree[path] = Entry(path, False, size, data, attr, first_c, times)
        if lfn:
            r.ben("%s: orphaned long-name entries at the end" % (dpath or "/"))
    used = 0
    lost = 0
    for cl in range(2, v.count + 2):
        val = v.fat(cl)
        if val != 0:
            used += 1
            if cl not in owner and val != 0x0FFFFFF7:
                lost += 1
    if lost:
        r.ben("%d lost clusters" % lost)
    free = v.count - used
    r.info.update(free=free, count=v.count, cluster_bytes=v.cbytes)
    fo = (part_lba + v.fsinfo) * SEC
    fsi_free, fsi_next = u32(img, fo + 488), u32(img, fo + 492)
    r.info.update(fsinfo_free=fsi_free, fsinfo_next=fsi_next)
    if fsi_free != 0xFFFFFFFF and fsi_free != free:
        r.ben("FSInfo free count %d, the FAT says %d" % (fsi_free, free))
    if fsi_next != 0xFFFFFFFF and not 2 <= fsi_next <= v.count + 1:
        r.err("FSInfo next-free %d is outside the volume" % fsi_next)
    return r


# ======================================================================
#  exFAT
# ======================================================================
EX_EOC = 0xFFFFFFFF
EX_INVALID = set(range(0x20)) | {0x22, 0x2A, 0x2F, 0x3A, 0x3C, 0x3E, 0x3F, 0x5C, 0x7C}


def upcase_table() -> bytes:
    """A compressed up-case table [EXFAT 7.2]. The first 256 code units are
    mapped explicitly - ASCII and Latin-1 letters to their capitals, as the
    specification's recommended table does - and the rest are one identity
    run (FFFF, 65280). Real volumes carry the full recommended table; this
    one is kept short because the gate executes every byte of up-case
    handling instruction by instruction, and the names the gate uses stay
    inside the first 256 code points."""
    out = []
    for cp in range(256):
        if 0x61 <= cp <= 0x7A or (0xE0 <= cp <= 0xFE and cp != 0xF7):
            out.append(cp - 32)
        elif cp == 0xFF:
            out.append(0x178)
        elif cp == 0xB5:
            out.append(0x39C)
        else:
            out.append(cp)
    out += [0xFFFF, 0x10000 - 256]
    return struct.pack("<%dH" % len(out), *out)


def decode_upcase(t: bytes) -> list:
    m = list(range(0x10000))
    cp = 0
    i = 0
    n = len(t) // 2
    while i < n and cp < 0x10000:
        w = u16(t, i * 2)
        if w == 0xFFFF and i + 1 < n:
            cp += u16(t, (i + 1) * 2)
            i += 2
            continue
        m[cp] = w
        cp += 1
        i += 1
    return m


def boot_checksum(sectors: bytes) -> int:
    s = 0
    for i, c in enumerate(sectors[:11 * SEC]):
        if i in (106, 107, 112):
            continue
        s = ((s >> 1) | ((s & 1) << 31)) + c
        s &= 0xFFFFFFFF
    return s


def name_hash(units: list, up: list) -> int:
    h = 0
    for c in units:
        c = up[c]
        for byte in (c & 0xFF, c >> 8):
            h = (((h & 1) << 15) | (h >> 1)) + byte
            h &= 0xFFFF
    return h


def set_checksum(ents: bytes) -> int:
    s = 0
    for i, c in enumerate(ents):
        if i in (2, 3):
            continue
        s = (((s & 1) << 15) | (s >> 1)) + c
        s &= 0xFFFF
    return s


class ExfatImage:
    def __init__(self, img: bytearray, part_lba: int):
        self.img = img
        self.p = part_lba
        b = self.sec(0)
        self.vol = u64(b, 72)
        self.fat_off = u32(b, 80)
        self.fat_len = u32(b, 84)
        self.heap = u32(b, 88)
        self.count = u32(b, 92)
        self.root = u32(b, 96)
        self.bps = 1 << b[108]
        self.spc = 1 << b[109]
        self.cbytes = self.bps * self.spc
        assert self.bps == SEC

    def sec(self, n: int) -> memoryview:
        o = (self.p + n) * SEC
        return memoryview(self.img)[o:o + SEC]

    def fat(self, cl: int) -> int:
        return u32(self.img, (self.p + self.fat_off) * SEC + cl * 4)

    def set_fat(self, cl: int, v: int) -> None:
        struct.pack_into("<I", self.img, (self.p + self.fat_off) * SEC + cl * 4, v)

    def clus_off(self, cl: int) -> int:
        return (self.p + self.heap + (cl - 2) * self.spc) * SEC

    def stream_clusters(self, first: int, length: int, nofat: bool) -> list:
        n = (length + self.cbytes - 1) // self.cbytes
        if n == 0:
            return []
        if nofat:
            return list(range(first, first + n))
        out = [first]
        while len(out) < n:
            out.append(self.fat(out[-1]))
        return out

    def bitmap_first(self) -> tuple:
        rd = self.clus_off(self.root)
        for i in range(self.cbytes // 32):
            e = self.img[rd + i * 32:rd + i * 32 + 32]
            if e[0] == 0x81:
                return u32(e, 20), u64(e, 24)
        raise ValueError("no bitmap")

    def set_bit(self, cl: int, used: bool) -> None:
        first, _ = self.bitmap_first()
        o = self.clus_off(first) + (cl - 2) // 8
        bit = 1 << ((cl - 2) % 8)
        self.img[o] = (self.img[o] | bit) if used else (self.img[o] & ~bit & 0xFF)

    def fix_boot_checksums(self) -> None:
        for base in (0, 12):
            o = (self.p + base) * SEC
            s = boot_checksum(bytes(self.img[o:o + 11 * SEC]))
            self.img[o + 11 * SEC:o + 12 * SEC] = struct.pack("<I", s) * (SEC // 4)

    def add_root_file(self, name: str, data: bytes, first: int, valid: int | None = None,
                      nofat: bool = True, attr: int = 0x20, datalen: int | None = None) -> None:
        up = decode_upcase(self.upcase_bytes())
        units = [u16(name.encode("utf-16-le"), i) for i in range(0, len(name) * 2, 2)]
        length = len(data) if datalen is None else datalen
        valid = length if valid is None else valid
        nameents = (len(units) + 14) // 15
        ents = bytearray(32 * (2 + nameents))
        ents[0] = 0x85
        ents[1] = 1 + nameents
        struct.pack_into("<H", ents, 4, attr)
        for off in (8, 12, 16):
            struct.pack_into("<I", ents, off, 0x0021 << 16)
        ents[32] = 0xC0
        ents[33] = 1 | (2 if nofat else 0)
        ents[35] = len(units)
        struct.pack_into("<H", ents, 36, name_hash(units, up))
        struct.pack_into("<Q", ents, 40, valid)
        struct.pack_into("<I", ents, 52, first if length else 0)
        struct.pack_into("<Q", ents, 56, length)
        for k in range(nameents):
            o = 64 + k * 32
            ents[o] = 0xC1
            for j, cu in enumerate(units[k * 15:(k + 1) * 15]):
                struct.pack_into("<H", ents, o + 2 + j * 2, cu)
        struct.pack_into("<H", ents, 2, set_checksum(bytes(ents)))
        rd = self.clus_off(self.root)
        for i in range(self.cbytes // 32):
            if all(self.img[rd + (i + j) * 32] == 0 for j in range(len(ents) // 32)):
                self.img[rd + i * 32:rd + i * 32 + len(ents)] = ents
                break
        else:
            raise ValueError("root full")
        cls = self.stream_clusters(first, length, nofat)
        for k, cl in enumerate(cls):
            self.set_bit(cl, True)
            if not nofat:
                self.set_fat(cl, cls[k + 1] if k + 1 < len(cls) else EX_EOC)
        blob = bytes(data) + bytes(len(cls) * self.cbytes - len(data))
        for k, cl in enumerate(cls):
            o = self.clus_off(cl)
            self.img[o:o + self.cbytes] = blob[k * self.cbytes:(k + 1) * self.cbytes]

    def upcase_bytes(self) -> bytes:
        rd = self.clus_off(self.root)
        for i in range(self.cbytes // 32):
            e = self.img[rd + i * 32:rd + i * 32 + 32]
            if e[0] == 0x82:
                first, length = u32(e, 20), u64(e, 24)
                o = self.clus_off(first)
                return bytes(self.img[o:o + length])
        raise ValueError("no upcase")


def format_exfat(img: bytearray, part_lba: int, sectors: int, spc_shift: int = 3,
                 label: str = "PIDATA") -> ExfatImage:
    spc = 1 << spc_shift
    fat_off = 24
    fat_len = 1
    while True:
        heap = fat_off + fat_len
        heap = (heap + spc - 1) // spc * spc
        count = (sectors - heap) // spc
        need = ((count + 2) * 4 + SEC - 1) // SEC
        if need <= fat_len:
            break
        fat_len = need
    cbytes = spc * SEC
    up = upcase_table()
    bitmap_len = (count + 7) // 8
    bm_clusters = (bitmap_len + cbytes - 1) // cbytes
    up_clusters = (len(up) + cbytes - 1) // cbytes
    bm_first = 2
    up_first = bm_first + bm_clusters
    root = up_first + up_clusters
    o = part_lba * SEC
    img[o:o + heap * SEC + (root - 1) * cbytes] = bytes(heap * SEC + (root - 1) * cbytes)
    b = bytearray(SEC)
    b[0:3] = b"\xEB\x76\x90"
    b[3:11] = b"EXFAT   "
    struct.pack_into("<QQIIIIIIHHBBBB", b, 64, part_lba, sectors, fat_off, fat_len, heap, count, root,
                     0x20260917, 0x0100, 0, 9, spc_shift, 1, 0x80)
    b[510], b[511] = 0x55, 0xAA
    region = bytearray(12 * SEC)
    region[0:SEC] = b
    for s in range(1, 9):
        struct.pack_into("<I", region, s * SEC + SEC - 4, 0xAA550000)
    s = boot_checksum(bytes(region))
    region[11 * SEC:12 * SEC] = struct.pack("<I", s) * (SEC // 4)
    img[o:o + 12 * SEC] = region
    img[o + 12 * SEC:o + 24 * SEC] = region
    v = ExfatImage(img, part_lba)
    v.set_fat(0, 0xFFFFFFF8)
    v.set_fat(1, 0xFFFFFFFF)
    for first, n in ((bm_first, bm_clusters), (up_first, up_clusters), (root, 1)):
        for k in range(n):
            v.set_fat(first + k, first + k + 1 if k + 1 < n else EX_EOC)
    bm = bytearray(bitmap_len)
    for cl in range(2, root + 1):
        bm[(cl - 2) // 8] |= 1 << ((cl - 2) % 8)
    img[v.clus_off(bm_first):v.clus_off(bm_first) + bitmap_len] = bm
    img[v.clus_off(up_first):v.clus_off(up_first) + len(up)] = up
    img[v.clus_off(root):v.clus_off(root) + cbytes] = bytes(cbytes)
    rd = v.clus_off(root)
    lab = bytearray(32)
    lab[0] = 0x83
    lab[1] = len(label)
    lab[2:2 + 2 * len(label)] = label.encode("utf-16-le")
    img[rd:rd + 32] = lab
    e = bytearray(32)
    e[0] = 0x81
    struct.pack_into("<IQ", e, 20, bm_first, bitmap_len)
    img[rd + 32:rd + 64] = e
    e = bytearray(32)
    e[0] = 0x82
    csum = 0
    for c in up:
        csum = (((csum & 1) << 31) | (csum >> 1)) + c
        csum &= 0xFFFFFFFF
    struct.pack_into("<I", e, 4, csum)
    struct.pack_into("<IQ", e, 20, up_first, len(up))
    img[rd + 64:rd + 96] = e
    used = root - 1
    img[o + 112] = used * 100 // count
    v.fix_boot_checksums()
    return v


def _ex_time_ok(ts: int) -> bool:
    return fat_date_ok(ts >> 16) and fat_time_ok(ts & 0xFFFF)


def check_exfat(img: bytes, part_lba: int, read_data: bool = True) -> Report:
    r = Report("exFAT")
    img = img if isinstance(img, (bytes, bytearray)) else bytes(img)
    o = part_lba * SEC
    main = bytes(img[o:o + 12 * SEC])
    back = bytes(img[o + 12 * SEC:o + 24 * SEC])
    for nm, reg in (("main", main), ("backup", back)):
        if reg[3:11] != b"EXFAT   " or reg[510:512] != b"\x55\xAA":
            r.err("%s boot sector signature wrong" % nm)
            return r
        if any(reg[11:64]):
            r.err("%s boot sector MustBeZero bytes are not zero" % nm)
        s = boot_checksum(reg)
        if reg[11 * SEC:12 * SEC] != struct.pack("<I", s) * (SEC // 4):
            r.err("%s boot region checksum wrong" % nm)
        for k in range(1, 9):
            if u32(reg, k * SEC + SEC - 4) != 0xAA550000:
                r.err("%s extended boot sector %d signature wrong" % (nm, k))
    # [EXFAT 3.1.13, 3.1.18] VolumeFlags and PercentInUse are stale in the
    # backup; everything else must match.
    mm = bytearray(main)
    bb = bytearray(back)
    for i in (106, 107, 112):
        mm[i] = bb[i] = 0
    mm[11 * SEC:] = bb[11 * SEC:] = b""
    if mm != bb:
        r.err("backup boot region differs from the main one beyond VolumeFlags and PercentInUse")
    v = ExfatImage(img, part_lba)
    flags = u16(main, 106)
    r.dirty = bool(flags & 2)
    r.info["volume_flags"] = flags
    r.info["backup_volume_flags"] = u16(back, 106)
    if flags & 4:
        r.err("VolumeFlags records a media failure")
    if main[110] != 1:
        r.err("NumberOfFats is not 1")
    owner: dict[int, str] = {}

    def claim(first: int, length: int, nofat: bool, what: str) -> list:
        n = (length + v.cbytes - 1) // v.cbytes
        if n == 0:
            if first != 0:
                r.err("%s: zero length with a first cluster" % what)
            return []
        out = []
        cl = first
        for k in range(n):
            if not 2 <= cl <= v.count + 1:
                r.err("%s: cluster %d outside the heap" % (what, cl))
                return out
            if cl in owner:
                r.err("%s: cluster %d cross-linked with %s" % (what, cl, owner[cl]))
                return out
            owner[cl] = what
            out.append(cl)
            if nofat:
                cl = cl + 1
            else:
                nxt = v.fat(cl)
                if k + 1 == n:
                    if nxt < 0xFFFFFFF8:
                        r.ben("%s: FAT chain continues past DataLength" % what)
                elif not 2 <= nxt <= v.count + 1:
                    r.err("%s: FAT chain ends after %d of %d clusters" % (what, k + 1, n))
                    return out
                cl = nxt
        return out

    def chain_len(first: int) -> list:
        out = []
        cl = first
        while 2 <= cl <= v.count + 1 and len(out) <= v.count:
            out.append(cl)
            cl = v.fat(cl)
        return out

    root_cls = chain_len(v.root)
    for cl in root_cls:
        if cl in owner:
            r.err("root cluster %d cross-linked" % cl)
        owner[cl] = "/"
    rootbytes = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes]) for c in root_cls)
    bm_first = bm_len = up_first = up_len = None
    for i in range(len(rootbytes) // 32):
        e = rootbytes[i * 32:(i + 1) * 32]
        if e[0] == 0:
            break
        if e[0] == 0x81:
            bm_first, bm_len = u32(e, 20), u64(e, 24)
        if e[0] == 0x82:
            up_first, up_len = u32(e, 20), u64(e, 24)
            up_sum = u32(e, 4)
    if bm_first is None or up_first is None:
        r.err("allocation bitmap or up-case table entry missing")
        return r
    claim(bm_first, bm_len, False, "$bitmap")
    claim(up_first, up_len, False, "$upcase")
    upbytes = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes])
                       for c in chain_len(up_first))[:up_len]
    csum = 0
    for c in upbytes:
        csum = (((csum & 1) << 31) | (csum >> 1)) + c
        csum &= 0xFFFFFFFF
    if csum != up_sum:
        r.err("up-case table checksum wrong")
    up = decode_upcase(upbytes)
    bitmap = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes])
                      for c in chain_len(bm_first))[:bm_len]

    def is_used(cl: int) -> bool:
        return bool(bitmap[(cl - 2) // 8] >> ((cl - 2) % 8) & 1)

    queue = [("", root_cls)]
    while queue:
        dpath, cls = queue.pop(0)
        data = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes]) for c in cls)
        n = len(data) // 32
        names: dict[str, str] = {}
        i = 0
        ended = False
        while i < n:
            e = data[i * 32:(i + 1) * 32]
            t = e[0]
            if ended:
                if t & 0x80:
                    r.err("%s: in-use entry after the end-of-directory marker" % (dpath or "/"))
                i += 1
                continue
            if t == 0:
                ended = True
                i += 1
                continue
            if not t & 0x80:
                i += 1
                continue
            if t in (0x81, 0x82, 0x83):
                if dpath:
                    r.err("%s: volume metadata entry outside the root" % dpath)
                i += 1
                continue
            if t in (0xC0, 0xC1) or (t & 0x40):
                r.ben("%s: secondary entry %02X with no file entry before it" % (dpath or "/", t))
                i += 1
                continue
            if t != 0x85:
                if not (t & 0x20):
                    r.err("%s: unknown critical primary entry %02X" % (dpath or "/", t))
                i += 1
                continue
            sc = e[1]
            if not 2 <= sc <= 18 or i + sc >= n + 0:
                r.err("%s: file entry with SecondaryCount %d" % (dpath or "/", sc))
                i += 1
                continue
            ents = data[i * 32:(i + 1 + sc) * 32]
            if set_checksum(ents) != u16(e, 2):
                r.err("%s: entry set checksum wrong at slot %d" % (dpath or "/", i))
                i += 1 + sc
                continue
            st = ents[32:64]
            if st[0] != 0xC0:
                r.err("%s: file entry not followed by a stream extension" % (dpath or "/"))
                i += 1 + sc
                continue
            nlen = st[3]
            need = (nlen + 14) // 15
            units = []
            ok = True
            for k in range(need):
                ne = ents[64 + k * 32:96 + k * 32]
                if ne[0] != 0xC1:
                    ok = False
                    break
                units += [u16(ne, 2 + 2 * j) for j in range(15)]
            if not ok or sc < 1 + need:
                r.err("%s: file name entries missing" % (dpath or "/"))
                i += 1 + sc
                continue
            units = units[:nlen]
            name = struct.pack("<%dH" % nlen, *units).decode("utf-16-le", "replace")
            path = (dpath + "/" + name) if dpath else "/" + name
            if name_hash(units, up) != u16(st, 4):
                r.err("%s: name hash wrong" % path)
            if any(c in EX_INVALID for c in units) or name in (".", ".."):
                r.err("%s: invalid or reserved file name" % path)
            key = "".join(chr(up[c]) for c in units)
            if key in names:
                r.err("%s: name collides with %r" % (path, names[key]))
            names[key] = name
            attr = u16(e, 4)
            flg = st[1]
            nofat = bool(flg & 2)
            valid, first, length = u64(st, 8), u32(st, 20), u64(st, 24)
            if not flg & 1:
                r.err("%s: AllocationPossible clear" % path)
            if valid > length:
                r.err("%s: ValidDataLength %d > DataLength %d" % (path, valid, length))
            times = {"crt": u32(e, 8), "mod": u32(e, 12), "acc": u32(e, 16),
                     "crt10": e[20], "mod10": e[21], "crtoff": e[22], "modoff": e[23], "accoff": e[24]}
            for label in ("crt", "mod", "acc"):
                if not _ex_time_ok(times[label]):
                    r.err("%s: %s timestamp %08X is not a time" % (path, label, times[label]))
            if e[20] > 199 or e[21] > 199:
                r.err("%s: 10 ms field above 199" % path)
            cls2 = claim(first, length, nofat, path)
            for cl in cls2:
                if not is_used(cl):
                    r.err("%s: cluster %d not marked in the allocation bitmap" % (path, cl))
            if attr & 0x10:
                if length == 0 or length % v.cbytes or valid != length:
                    r.err("%s: directory DataLength %d / ValidDataLength %d" % (path, length, valid))
                r.tree[path] = Entry(path, True, 0, None, attr, first, times)
                queue.append((path, cls2))
            else:
                blob = None
                if read_data:
                    raw = b"".join(bytes(img[v.clus_off(c):v.clus_off(c) + v.cbytes]) for c in cls2)
                    blob = raw[:valid] + bytes(max(0, length - valid))
                    blob = blob[:length]
                r.tree[path] = Entry(path, False, length, blob, attr, first, times)
                r.info.setdefault("valid", {})[path] = valid
            i += 1 + sc
    lost = 0
    used = 0
    for cl in range(2, v.count + 2):
        if is_used(cl):
            used += 1
            if cl not in owner:
                lost += 1
    if lost:
        r.ben("%d lost clusters (marked used, owned by nothing)" % lost)
    pct = main[112]
    r.info.update(used=used, count=v.count, free=v.count - used, percent=pct, cluster_bytes=v.cbytes)
    if pct != 0xFF and abs(pct - used * 100 // v.count) > 1:
        r.ben("PercentInUse %d, the bitmap says %d" % (pct, used * 100 // v.count))
    return r
