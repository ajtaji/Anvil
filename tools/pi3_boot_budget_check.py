#!/usr/bin/env python3
"""Budget gate for the Pi 3 cold boot: E5 must fit its watchdog, with room.

Both of the loader's never-fed watchdogs are fifteen seconds. The early storage
watchdog covers E0-E6, which is the cold A/B mount; the trial watchdog covers
L0-L6, which verifies and copies the selected slot. Neither budget was ever
stated, so when the mount's cost rose with a card's cluster size nothing caught
it and the board reset thirteen times out of thirteen.

This states them, in the two units a desk replay can measure honestly:

  * SINGLE-BLOCK READS, because on this board one block is one SD command and
    the command is what costs time;
  * INSTRUCTIONS, because that is what catches work done per byte rather than
    per block - the shape that made hashing a slot cost about twenty-nine
    million uncached accesses.

It does NOT convert either into seconds. Time per command belongs to the board;
what this gate owns is that the work does not grow behind anyone's back.

    python tools/pi3_boot_budget_check.py --compiler <PureMetalForge.exe>
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base  # noqa: E402

ROOT = base.ROOT
SIG = b"\x55\xaa"
JMP = b"\xeb\x58\x90"

# The mount's budget, per cluster size.
#
# WHY 1600 AND NOT 100. A fabricated volume costs about 78 reads at 4 KiB
# clusters, but replaying the REAL card - its own bytes, taken off it while it
# was failing - cost 1,039. The difference is where a formatter actually put
# things, which a reconstruction does not reproduce and a budget must survive.
# So the number is set above the worst real measurement, not above the tidy
# synthetic one; 1,039 reads is a boot, 1,600 is the line, and anything that
# needs more than that has changed shape and should be looked at.
# Each cluster size is paired with a volume big enough to be LEGAL at it:
# FAT32 needs at least 65,525 clusters, so a 1 GiB volume cannot carry 32 KiB
# clusters and the mount is right to refuse one.
MOUNT_BUDGET = (
    (8, 2_097_152, '4 KiB clusters, 1 GiB', 1600, 6_000_000),
    (64, 62_500_000, '32 KiB clusters, 32 GB', 1600, 6_000_000),
)

# Hashing a slot: reads scale with the image, instructions must NOT scale with
# its BYTES. 96 instructions per block is generous for a ranged read plus a
# single hash call; a per-byte copy needs thousands.
HASH_INSTRUCTIONS_PER_BLOCK = 4096

REAL_FILES = [
    # The files are preallocated to the fixed 14 MiB A/B extents.  Their
    # directory sizes are deliberately larger than the current logical
    # payloads: the record carries the payload length and hash, while the
    # loader's extent map protects the whole reserved slot.
    (b'ANVILA  BIN', 0xE00000, False),
    (b'ANVILB  BIN', 0xE00000, False),
    (b'P3CTRLA BIN', 512, False),
    (b'P3CTRLB BIN', 512, False),
    (b'KERNEL8 IMG', 165_544, False),
    (b'BCM2710 DTB', 34_731, False),
    (b'BOOTCODEBIN', 52_624, False),
    (b'CONFIG  TXT', 915, False),
    (b'FIXUP   DAT', 7_381, False),
    (b'START   ELF', 3_022_976, False),
    (b'OVERLAYS   ', 0, True),
]

# These are the current card's record payload lengths, not the 14 MiB slot
# allocations above.  E5 hashes the record length for each slot; keeping the
# two values distinct catches a fixture that accidentally measures one generic
# small image twice.
CARD_SLOT_PAYLOAD_BYTES = (183_980, 301_488)


def container(data: bytes) -> bytes:
    pmf = bytearray(128)
    struct.pack_into('<8sIIQQQQQII', pmf, 0, b'PMFBOOT\0', 2, 128,
                     0x200000, 0x200000, len(data), 0x1100000, 4096, 0, 0)
    pmf[64:96] = hashlib.sha256(data).digest()
    struct.pack_into('<IIQ', pmf, 96, 1, 2837, 0x1f00000)
    pmf = bytes(pmf) + data
    header = bytearray(128)
    struct.pack_into('<8sIIIIQQ', header, 0, b'P3SLOT\0\0', 1, 128, 2837, 64,
                     0x1f00000, len(pmf))
    header[40:72] = hashlib.sha256(pmf).digest()
    return bytes(header) + pmf


def record(slot: int, generation: int, data: bytes, state: int = 3) -> bytes:
    b = bytearray(512)
    struct.pack_into('<IIQQII', b, 0, 0x42413350, 2, generation, len(data), slot, 0x200000)
    b[32:64] = hashlib.sha256(data).digest()
    struct.pack_into('<I', b, 64, state)
    struct.pack_into('<I', b, 508, zlib.crc32(b[:508]))
    return bytes(b)


def build(files, cs: int, total_sectors: int):
    """A FAT32 volume of the given geometry, laid out as a format leaves one."""
    disk = {}
    part = 2048
    mbr = bytearray(512)
    mbr[446] = 0x80
    mbr[450] = 0x0c
    struct.pack_into('<II', mbr, 454, part, total_sectors)
    mbr[466] = 0x07
    struct.pack_into('<II', mbr, 470, part + total_sectors, 60_000_000)
    mbr[510:] = SIG
    disk[0] = bytes(mbr)

    reserved = 32
    clusters = (total_sectors - reserved) // cs
    fat_sectors = ((clusters + 2) * 4 + 511) // 512
    fat_sectors = ((fat_sectors + cs - 1) // cs) * cs

    v = bytearray(512)
    v[:3] = JMP
    v[3:11] = b'ANVIL   '
    struct.pack_into('<H', v, 11, 512)
    v[13] = cs
    struct.pack_into('<H', v, 14, reserved)
    v[16] = 2
    v[21] = 0xf8
    struct.pack_into('<I', v, 28, part)
    struct.pack_into('<I', v, 32, total_sectors)
    struct.pack_into('<I', v, 36, fat_sectors)
    struct.pack_into('<I', v, 44, 2)
    struct.pack_into('<HH', v, 48, 1, 6)
    v[66] = 0x29
    v[82:90] = b'FAT32   '
    v[510:] = SIG
    disk[part] = bytes(v)

    fat_lba = part + reserved
    data_lba = fat_lba + 2 * fat_sectors
    cb = cs * 512
    fat = {}

    def put_fat(cluster, value):
        sector = fat_lba + (cluster * 4) // 512
        off = (cluster * 4) % 512
        buf = bytearray(fat.get(sector, bytes(512)))
        struct.pack_into('<I', buf, off, value)
        fat[sector] = bytes(buf)

    def lba_of(cluster):
        return data_lba + (cluster - 2) * cs

    put_fat(0, 0x0ffffff8)
    put_fat(1, 0x0fffffff)
    put_fat(2, 0x0fffffff)

    root = bytearray(cb)
    first = 3
    placed = {}
    sub = None
    at = 0
    root[at:at + 11] = b'ANVIL_PI3  '
    root[at + 11] = 0x08
    at += 32
    for name, size, is_dir in files:
        count = 1 if is_dir else max(1, (size + cb - 1) // cb)
        for n in range(count):
            put_fat(first + n, 0x0fffffff if n == count - 1 else first + n + 1)
        root[at:at + 11] = name
        root[at + 11] = 0x10 if is_dir else 0x20
        struct.pack_into('<H', root, at + 26, first)
        struct.pack_into('<I', root, at + 28, 0 if is_dir else size)
        placed[name] = first
        if is_dir:
            sub = first
        at += 32
        first += count
    for s in range(cs):
        disk[data_lba + s] = bytes(root[s * 512:(s + 1) * 512])

    if sub is not None:
        d = bytearray(cb)
        d[0:11] = b'.          '
        d[11] = 0x10
        struct.pack_into('<H', d, 26, sub)
        d[32:43] = b'..         '
        d[43] = 0x10
        for s in range(cs):
            disk[lba_of(sub) + s] = bytes(d[s * 512:(s + 1) * 512])

    disk.update(fat)
    # Populate both logical images at their real record lengths.  The slot
    # directory entries remain the fixed 14 MiB allocations above; only the
    # prefix named by each A/B record is hashed during E5 verification.
    payloads = [
        container(bytes((i * 7 + 3) & 255 for i in range(CARD_SLOT_PAYLOAD_BYTES[0] - 256))),
        container(bytes((i * 11 + 5) & 255 for i in range(CARD_SLOT_PAYLOAD_BYTES[1] - 256))),
    ]
    for slot, name in enumerate((b'ANVILA  BIN', b'ANVILB  BIN')):
        payload = payloads[slot]
        start = lba_of(placed[name])
        for off in range(0, len(payload), 512):
            disk[start + off // 512] = payload[off:off + 512].ljust(512, b'\0')
    disk[lba_of(placed[b'P3CTRLA BIN'])] = record(0, 4, payloads[0])
    disk[lba_of(placed[b'P3CTRLB BIN'])] = record(1, 5, payloads[1])
    return disk, placed, lba_of


def compile_fixture(compiler, root, out):
    r = subprocess.run(
        [str(compiler), '--compile', 'RaspberryPi3/Tests/update_ab_gate.pi3',
         '-t', 'pi3', '--entry-returns', '--load-addr', hex(base.LOAD),
         '--stack-addr', hex(base.STACK), '-s', '-o', str(out)],
        cwd=root, env=dict(os.environ, PMF_ROOT=str(root)),
        capture_output=True, text=True)
    if r.returncode or not out.exists():
        raise SystemExit(r.stdout + r.stderr)
    return base.parse_symbols(out), out.read_bytes()


class Rig:
    def __init__(self, a64, sym, blob, disk):
        self.a64, self.sym, self.disk = a64, sym, disk
        self.cpu = a64.A64()
        self.cpu.sp = base.STACK
        self.cpu.memory = {base.LOAD + i: b for i, b in enumerate(blob)}
        self.reads = 0
        self.steps = 0
        self.sha = None

    def get(self, p, n):
        return bytes(self.cpu.memory.get(p + i, 0) for i in range(n))

    def put(self, p, data):
        for i, b in enumerate(data):
            self.cpu.memory[p + i] = b

    def call(self, name, *argv, budget=400_000_000):
        cpu = self.cpu
        sym = self.sym
        hooks = {base.LOAD + sym[n]: n for n in
                 ['pi3sdreadblock', 'pi3sdwriteblock', 'sha256begin',
                  'sha256update', 'sha256end', 'sha256of'] if n in sym}
        cpu.pc = base.LOAD + sym[name.lower()]
        cpu.x[30] = base.RETURN_PC
        for i, v in enumerate(argv):
            cpu.x[i] = v
        start = self.steps
        while self.steps - start < budget:
            if cpu.pc == base.RETURN_PC:
                return cpu.x[0]
            hook = hooks.get(cpu.pc)
            if hook:
                a, b, d = cpu.x[:3]
                if hook == 'pi3sdreadblock':
                    self.reads += 1
                    self.put(b, self.disk.get(a, bytes(512)))
                elif hook == 'sha256begin':
                    self.sha = hashlib.sha256()
                elif hook == 'sha256update':
                    self.sha.update(self.get(a, b))
                elif hook == 'sha256end':
                    self.put(a, self.sha.digest())
                elif hook == 'sha256of':
                    self.put(d, hashlib.sha256(self.get(a, b)).digest())
                cpu.x[0] = 1
                cpu.pc = cpu.x[30]
            else:
                cpu.step()
                self.steps += 1
        raise TimeoutError(name + ' exceeded ' + str(budget) + ' instructions')


def mount_cost(a64, sym, blob, cs, total):
    disk, placed, lba_of = build(REAL_FILES, cs, total)
    rig = Rig(a64, sym, blob, disk)
    rig.call('Pi3UpdateConfigure', 0x2000000, 0xE00000, 0, 0x3C000000, 0x1000000, 0x1000)
    before_reads, before_steps = rig.reads, rig.steps
    ok = rig.call('Pi3UpdateMount')
    return ok, rig.reads - before_reads, rig.steps - before_steps


def hash_cost(a64, sym, blob, slot, image_bytes):
    """Cost of hashing one real logical slot prefix into staging.

    The interpreter's SHA hook is an oracle for correctness; its host hashing
    time is deliberately excluded from the instruction budget.
    """
    cs, total = 8, 2_097_152
    files = list(REAL_FILES)
    disk, placed, lba_of = build(files, cs, total)
    rig = Rig(a64, sym, blob, disk)
    rig.call('Pi3UpdateConfigure', 0x2000000, 0xE00000, 0, 0x3C000000, 0x1000000, 0x1000)
    if rig.call('Pi3UpdateMount') != 1:
        raise SystemExit('the budget fixture would not mount')
    before_reads, before_steps = rig.reads, rig.steps
    ok = rig.call('pi3UpHashSlot', slot, image_bytes, 0x2000000)
    return ok, rig.reads - before_reads, rig.steps - before_steps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler', required=True)
    args = ap.parse_args()
    checks = 0

    with tempfile.TemporaryDirectory(prefix='pi3-budget-') as tmp:
        out = pathlib.Path(tmp) / 'ab.img'
        sym, blob = compile_fixture(args.compiler, ROOT, out)
        a64 = base.load_interp(base.INTERP)

        print(f'{"E5 - cold A/B mount (SHA hook; host SHA time excluded)":40s} '
              f'{"reads":>8s} {"budget":>8s} '
              f'{"instructions":>14s} {"budget":>14s}')
        for cs, total, name, read_budget, step_budget in MOUNT_BUDGET:
            ok, reads, steps = mount_cost(a64, sym, blob, cs, total)
            label = '  ' + name
            print(f'{label:40s} {reads:8d} {read_budget:8d} {steps:14d} {step_budget:14d}')
            if ok != 1:
                raise SystemExit(f'FAIL: the mount refused at {cs * 512} byte clusters')
            if reads > read_budget or steps > step_budget:
                raise SystemExit(
                    f'FAIL: the mount is over budget at {cs * 512} byte clusters '
                    f'({reads} reads, {steps} instructions). The early storage '
                    f'watchdog is fifteen seconds and does not move; the work has to.')
            checks += 3

        # Hashing must scale with BLOCKS, never with bytes.  Use the larger
        # current logical payload; E5 hashes both A and B during its mount,
        # while this separate check covers the same contiguous staging path
        # used by L1/L3/L4.  SHA itself is an interpreter hook here, so this
        # is not a native SHA timing claim.
        image_bytes = CARD_SLOT_PAYLOAD_BYTES[1]
        ok, reads, steps = hash_cost(a64, sym, blob, 1, image_bytes)
        blocks = (image_bytes + 511) // 512
        allowed = blocks * HASH_INSTRUCTIONS_PER_BLOCK
        print()
        print(f'L1 - hashing {image_bytes} bytes into staging '
              f'(interpreter SHA hook; native SHA timing excluded): '
              f'{reads} reads, {steps} instructions (budget {allowed})')
        if ok != 1:
            raise SystemExit('FAIL: hashing the slot refused')
        if steps > allowed:
            raise SystemExit(
                f'FAIL: hashing costs {steps} instructions for {blocks} blocks. '
                f'That is per-byte work, which is what a copy out of the read '
                f'buffer looks like; read into staging and hash there.')
        checks += 2

        # THE MUTANT. Put the byte-at-a-time copy back and the same hash must
        # blow the same budget - otherwise this gate is measuring nothing.
        with tempfile.TemporaryDirectory(prefix='pi3-budget-mutant-') as mut:
            mroot = pathlib.Path(mut)
            for rel in ('RaspberryPi3/Lib/timer.pbi', 'RaspberryPi3/Lib/uart.pbi',
                        'RaspberryPi3/Lib/mailbox.pbi', 'RaspberryPi3/Lib/sdhost.pbi',
                        'RaspberryPi3/Lib/update_ab.pbi', 'RaspberryPi3/Lib/boot_memory.pbi',
                        'RaspberryPi3/Tests/update_ab_gate.pi3',
                        'RaspberryPi3/Intrinsics/bcm2837_hardware.def',
                        'Anvil/Storage/fat32.pbi', 'Anvil/Storage/exfat.pbi',
                        'Anvil/Storage/filesystem.pbi', 'Anvil/Storage/ab_record.pbi',
                        'RaspberryPi3/Lib/boot_record.pbi',
                        'Anvil/Core/sha256.pbi',
                        'Anvil/Core/crc.pbi'):
                src = ROOT / rel
                if not src.is_file():
                    continue
                dst = mroot / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
            ab = mroot / 'RaspberryPi3/Lib/update_ab.pbi'
            text = ab.read_text(encoding='utf-8')
            old = ('    If Pi3SdReadBlocks(pi3_up_lba[slot], blocks, destination) = 0 : '
                   'ProcedureReturn 0 : EndIf\n'
                   '    ; The read has completed; the next operation is pure SHA work over RAM.\n'
                   '    pi3UpMountMark(40 + slot)\n'
                   '    Sha256Update(destination, bytes)\n')
            new = ('    offset = 0\n'
                   '    buffer = @pi3_up_sector[0]\n'
                   '    While offset < bytes\n'
                   '      If Pi3SdReadBlock(pi3_up_lba[slot] + offset / 512, buffer) = 0 : ProcedureReturn 0 : EndIf\n'
                   '      take = bytes - offset\n'
                   '      If take > 512 : take = 512 : EndIf\n'
                   '      Sha256Update(buffer, take)\n'
                   '      For blocks = 0 To take - 1 : PokeA(destination + offset + blocks, PeekA(buffer + blocks)) : Next\n'
                   '      offset = offset + take\n'
                   '    Wend\n')
            if old not in text:
                raise SystemExit('the ranged staging read is not where the mutant expects it')
            ab.write_text(text.replace(old, new, 1), encoding='utf-8')
            msym, mblob = compile_fixture(args.compiler, mroot, mroot / 'mutant.img')
            ok, mreads, msteps = hash_cost(a64, msym, mblob, 1, image_bytes)
            print(f'  mutant with the byte copy restored: {msteps} instructions '
                  f'(budget {allowed})')
            if msteps <= allowed:
                raise SystemExit(
                    'FAIL: the byte-copy mutant came in under budget, so this '
                    'budget does not actually catch per-byte work')
            checks += 1

    print()
    print(f'pi3_boot_budget_check PASS {checks} checks; stated budgets for E5 and '
          f'for slot hashing, one mutant; reads and instructions only, no seconds claimed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
