#!/usr/bin/env python3
"""Focused emitted FsExtentOf fixtures; no board or medium is accessed.

Uses the file-operation gate's compiler and block-device harness, and the
independent filesystem formatter. The existing operation/power-cut corpus
is unchanged. This proves extent decisions, not hardware timing or durability.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile

import fileops_check as harness
import fs_reference as reference

ROOT = Path(__file__).resolve().parents[1]


def fixture(fs):
    disk = harness.build_disk()
    fat = fs == 'fat32'
    volume = (reference.Fat32Image(disk, harness.FAT_LBA) if fat else
              reference.ExfatImage(disk, harness.EX_LBA))
    last = volume.count + 1
    chain, frag = last - 10, last - 20
    end = reference.FAT_EOC if fat else reference.EX_EOC
    if fat:
        volume.alloc_contiguous(chain, 2)
        volume.add_root_entry(b'CHAIN   BIN', 0x20, chain, 700)
        volume.set_fat(frag, frag + 2)
        volume.set_fat(frag + 2, end)
        volume.add_root_entry(b'FRAG    BIN', 0x20, frag, 700)
        volume.set_fat(last, end)
        volume.add_root_entry(b'TAIL    BIN', 0x20, last, volume.cbytes)
        volume.add_root_entry(b'EMPTY   BIN', 0x20, 0, 0)
        volume.set_fsinfo(volume.free_count(), 8)
        first_case = ('B84DETAIL long name.img', 3, 2, 700)
        chain_size = 700
    else:
        volume.set_fat(chain, chain + 1)
        volume.set_fat(chain + 1, end)
        chain_size = volume.cbytes + 17
        volume.add_root_file('CHAIN.BIN', bytes(chain_size), chain, nofat=False)
        volume.set_fat(frag, frag + 2)
        volume.set_fat(frag + 2, end)
        volume.add_root_file('FRAG.BIN', bytes(chain_size), frag, nofat=False)
        volume.add_root_file('TAIL.BIN', bytes(volume.cbytes), last)
        volume.add_root_file('EMPTY.BIN', b'', 0, nofat=False)
        first_case = ('vdl.bin', volume.root + 1, 1, 3000)
    report = (reference.check_fat32(disk, harness.FAT_LBA, read_data=False) if fat else
              reference.check_exfat(disk, harness.EX_LBA, read_data=False))
    assert not report.errors, report.errors
    prefix = '1:/' if fat else '2:/'
    def good(name, first, clusters, size):
        return (prefix + name, 1, volume.clus_off(first) // 512,
                clusters * volume.cbytes // 512, size)
    cases = [good(*first_case), good('CHAIN.BIN', chain, 2, chain_size),
             good('TAIL.BIN', last, 1, volume.cbytes)]
    cases += [(prefix + name, 0, -101, -102, -103)
              for name in ('FRAG.BIN', 'EMPTY.BIN', 'MISSING.BIN', '')]
    return disk, cases


def program(fs, cases):
    # Reuse the real block callback fixture, replacing only its Main and data.
    prefix = harness.generate(fs).split('Procedure.i Main()', 1)[0]
    lines = [prefix, 'Global Dim extentOut.i[3]', 'Procedure.i Main()',
             '  Define result.i', '  FsSetRangeReader(@DiskRead)']
    for index, (_, wanted, first, blocks, size) in enumerate(cases, 1):
        lines += ['  extentOut[0] = -101 : extentOut[1] = -102 : extentOut[2] = -103',
                  f'  result = FsExtentOf(?extentPath{index}, @extentOut[0], @extentOut[1], @extentOut[2])',
                  f'  If result <> {wanted} : ProcedureReturn {index * 10 + 1} : EndIf',
                  f'  If extentOut[0] <> {first} : ProcedureReturn {index * 10 + 2} : EndIf',
                  f'  If extentOut[1] <> {blocks} : ProcedureReturn {index * 10 + 3} : EndIf',
                  f'  If extentOut[2] <> {size} : ProcedureReturn {index * 10 + 4} : EndIf',
                  f'  If FsIsOpen() <> 0 : ProcedureReturn {index * 10 + 5} : EndIf']
        if not wanted:
            lines += [f'  If FsLastError() = 0 : ProcedureReturn {index * 10 + 6} : EndIf']
    lines += ['  ProcedureReturn 0', 'EndProcedure', 'DataSection']
    lines += [harness.utf8_data(f'extentPath{i}', case[0]) for i, case in enumerate(cases, 1)]
    lines += ['EndDataSection', '']
    return '\n'.join(lines)


def run(fs, compiler, root, work):
    disk, cases = fixture(fs)
    image, symbols = harness.build(compiler, root, program(fs, cases), work)
    spec = importlib.util.spec_from_file_location('extent_a64', ROOT / 'tools/a64/a64_interp.py')
    machine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = machine
    spec.loader.exec_module(machine)
    device = harness.Run(fs, disk)
    result, instructions = harness.execute(machine, image, symbols, device, 10_000_000)
    assert not device.writes and device.disk == device.base, 'extent query wrote the medium'
    assert not device.host_failures, device.host_failures
    return result, instructions


def overwrite_program():
    """Exercise the real fixed overwrite primitive against the FAT fixture."""
    prefix = harness.generate('fat32').split('Procedure.i Main()', 1)[0]
    paths = {
        'tail': '1:/TAIL.BIN', 'frag': '1:/FRAG.BIN', 'missing': '1:/MISSING.BIN',
        'foreign': '2:/vdl.bin',
    }
    lines = [prefix, 'Procedure.i Main()', '  Define result.i',
             '  Define writes.i', '  Fill(512, 91)',
             '  FsSetRangeReader(@DiskRead)', '  FsSetRangeWriter(@DiskWrite)',
             '  result = FsOverwriteFixed(?tail, @gBuf[0], 512)',
             '  If result <> 1 Or PeekI($7F000028) <> 1 : ProcedureReturn 11 : EndIf',
             '  writes = PeekI($7F000028)',
             '  result = FsOverwriteFixed(?tail, @gBuf[0], 1024)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 12 : EndIf',
             '  result = FsOverwriteFixed(?tail, @gBuf[0], 513)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 13 : EndIf',
             '  result = FsOverwriteFixed(?missing, @gBuf[0], 512)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 14 : EndIf',
             '  result = FsOverwriteFixed(?frag, @gBuf[0], 512)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 15 : EndIf',
             '  FsSetRangeWriter(0)',
             '  result = FsOverwriteFixed(?tail, @gBuf[0], 512)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 16 : EndIf',
             '  FsSetRangeWriter(@DiskWrite)',
             '  result = FsOverwriteFixed(?foreign, @gBuf[0], 512)',
             '  If result <> 0 Or PeekI($7F000028) <> writes : ProcedureReturn 17 : EndIf',
             '  result = FsOverwriteFixed(?tail, @gBuf[0], 512)',
             '  If result <> 1 Or PeekI($7F000028) <> writes + 1 : ProcedureReturn 18 : EndIf',
             '  ProcedureReturn 0', 'EndProcedure', 'DataSection']
    lines += [harness.utf8_data(label, text) for label, text in paths.items()]
    lines += ['EndDataSection', '']
    return '\n'.join(lines)


def run_overwrite(compiler, work):
    disk = harness.build_disk()
    fat = reference.Fat32Image(disk, harness.FAT_LBA)
    fat.alloc_contiguous(5, 1)
    fat.add_root_entry(b'TAIL    BIN', 0x20, 5, 512)
    image, symbols = harness.build(compiler, ROOT, overwrite_program(), work)
    spec = importlib.util.spec_from_file_location('overwrite_a64', ROOT / 'tools/a64/a64_interp.py')
    machine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = machine
    spec.loader.exec_module(machine)
    device = harness.Run('fat32', disk)
    result, instructions = harness.execute(machine, image, symbols, device, 10_000_000)
    assert result == 0, f'FsOverwriteFixed case {result}'
    assert len(device.writes) == 2, device.writes
    assert device.writes[0][0] == device.writes[1][0], device.writes
    assert all(len(data) == 512 for _, data, _ in device.writes), device.writes
    return instructions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--mutate', action='store_true')
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    for fs in ('fat32', 'exfat'):
        with tempfile.TemporaryDirectory(prefix='fs-extent-') as tmp:
            result, steps = run(fs, compiler, ROOT, Path(tmp))
            assert result == 0, f'{fs}: case {result // 10}, assertion {result % 10}'
            print(f'PASS {fs}: seven extent cases, read-only; {steps:,} instructions', flush=True)
    with tempfile.TemporaryDirectory(prefix='fs-overwrite-') as tmp:
        steps = run_overwrite(compiler, Path(tmp))
        print(f'PASS fat32: FsOverwriteFixed exact/refusal/path cases; {steps:,} instructions', flush=True)
    if args.mutate:
        mutants = []
        for fs, file, stem in [('fat32', 'fat32.pbi', 'fat'), ('exfat', 'exfat.pbi', 'exfat')]:
            mutants.append((fs, file,
                f'If following <> cluster + 1 Or {stem}_ClusterValid(following) = 0',
                f'If {stem}_ClusterValid(following) = 0', 41, 'omitted contiguity check'))
        mutants.append(('exfat', 'exfat.pbi',
            'PokeI(*firstLba, exfat_partLba + exfat_ClusterSector(first, 0) * exfat_blocksPerSector)',
            'PokeI(*firstLba, exfat_ClusterSector(first, 0))', 12, 'partition-relative address'))
        for fs, file, old, new, wanted, name in mutants:
            with tempfile.TemporaryDirectory(prefix='fs-extent-mutant-') as tmp:
                root = Path(tmp) / 'tree'
                for sub in ('Anvil', 'RaspberryPi4', 'Boards'):
                    shutil.copytree(ROOT / sub, root / sub,
                                    ignore=shutil.ignore_patterns('Reference', '*.img*', '__pycache__'))
                path = root / 'Anvil/Storage' / file
                text = path.read_text(encoding='utf-8')
                assert text.count(old) == 1, 'mutation anchor changed'
                path.write_text(text.replace(old, new), encoding='utf-8')
                work = Path(tmp) / 'build'
                work.mkdir()
                result, _ = run(fs, compiler, root, work)
                assert result == wanted, f'{fs} {name} must fail at {wanted}, got {result}'
                print(f'PASS {fs}: {name} rejected by case {result // 10}', flush=True)
    print('Compiler SHA256:', hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
