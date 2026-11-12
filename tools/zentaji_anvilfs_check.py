"""Verify AnvilFS copy-on-write and mount recovery on native Zentaji disk I/O."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

from anvilfs_image import build_image
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
CONTROL = 0x100000
SOURCE = r'''
#ANVIL_JOURNAL_FS=1
XIncludeFile "Zentaji/Board/disk.pbi"
XIncludeFile "Anvil/Storage/fat32.pbi"
XIncludeFile "Anvil/Storage/exfat.pbi"
XIncludeFile "Anvil/Storage/filesystem.pbi"

Global operation.i,stopAt.i
Global Dim bytes.a[10000]

ProcedureNaked CutPower(code.i)
 ASM
  HALT r1
  JR r254
 EndASM
EndProcedure

Procedure.i ProbeWrite(lba.i,count.i,*buffer)
 operation=operation+1
 If ZentajiDiskWriteBuffered(lba,count,*buffer)=0 : ProcedureReturn 0 : EndIf
 If operation=stopAt : CutPower($100+operation) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ProbeFlush()
 operation=operation+1
 If ZentajiDiskFlush()=0 : ProcedureReturn 0 : EndIf
 If operation=stopAt : CutPower($100+operation) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ProbeClock()
 ProcedureReturn 0
EndProcedure

Procedure.i StagedPartitionSwitch()
 Protected handle.i
 FsSetRangeReader(@ZentajiDiskRead)
 FsSetRangeWriter(@ZentajiDiskWrite)
 FsSetBlockFlusher(@ZentajiDiskFlush)
 ExFatProfileSetClock(@ProbeClock)
 FsSetJournalDevice(ZentajiDiskSectors(),@ZentajiDiskWriteBuffered)
 If FsMount(1)=0 Or FsPartition()<>1 : ProcedureReturn 21 : EndIf
 handle=FsMountBegin(2)
 If handle=0 Or FsMountPending()=0 : ProcedureReturn 22 : EndIf
 If FsMountStep(handle)<>1 Or FsMountPending()<>0 : ProcedureReturn 23 : EndIf
 If FsType()<>#FS_JOURNAL Or FsPartition()<>2 : ProcedureReturn 24 : EndIf
 If FsOpen("2:/project/copy.bin")=0 Or FsSize()<>6000 : ProcedureReturn 25 : EndIf
 If FsSelectPartition(1)<>0 Or FsPartition()<>2 : ProcedureReturn 26 : EndIf
 FsClose()
 If FsSelectPartition(1)=0 Or FsPartition()<>1 : ProcedureReturn 27 : EndIf
 If FsUnmount()=0 Or ZentajiDiskClose()=0 : ProcedureReturn 28 : EndIf
 ProcedureReturn $2A
EndProcedure

Procedure.i Main()
 Protected i.i,mode.i=PeekQ($100000),wanted.i=PeekQ($100010),first.i,blocks.i,length.i
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3)
 PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)=0 Or ZentajiDiskOpen(0)=0 : ProcedureReturn 1 : EndIf
 If mode=5 : ProcedureReturn StagedPartitionSwitch() : EndIf
 If mode=2 Or mode=4
  If JfTryMount(1,ZentajiDiskSectors(),@ZentajiDiskRead,0,0)<>-1 : ProcedureReturn 2 : EndIf
  If mode=2 And jfError<>#JF_E_JOURNAL : ProcedureReturn 3 : EndIf
  If mode=4 And jfError<>#JF_E_FORMAT : ProcedureReturn 4 : EndIf
  ProcedureReturn $2A
 EndIf
 If JfTryMount(1,ZentajiDiskSectors(),@ZentajiDiskRead,@ProbeWrite,@ProbeFlush)<>1 : ProcedureReturn 5 : EndIf
 If JfExtent("project/copy.bin",@first,@blocks,@length)=0 : ProcedureReturn 6 : EndIf
 If first<2048 Or blocks<>16 Or length<>6000 : ProcedureReturn 7 : EndIf
 If JfOpen("project/copy.bin")=0 : ProcedureReturn 8 : EndIf
 operation=0 : stopAt=PeekQ($100008)
 If mode=0
  For i=0 To 5999 : bytes[i]=(i*7+213)&255 : Next
  If JfOverwrite(@bytes[0],6000,0)<>0 Or jfError<>#JF_E_RO : ProcedureReturn 9 : EndIf
  If JfOverwrite(@bytes[0],6000,1)=0 Or operation<>15 : ProcedureReturn 10 : EndIf
 Else
  If JfRead(@bytes[0],10000)<>6000 : ProcedureReturn 11 : EndIf
  For i=0 To 5999
   If wanted=0
    If bytes[i]<>((i*13+37)&255) : ProcedureReturn 12 : EndIf
   Else
    If bytes[i]<>((i*7+213)&255) : ProcedureReturn 13 : EndIf
   EndIf
  Next
  If mode=3
   If JfSeek(4095)=0 : ProcedureReturn 14 : EndIf
   bytes[0]=21 : bytes[1]=22
   If JfWrite(@bytes[0],2,1)<>2 Or jfPosition<>4097 : ProcedureReturn 15 : EndIf
   If JfTruncate(4097,1)=0 Or JfTruncate(8205,1)=0 : ProcedureReturn 16 : EndIf
   If JfSeek(4094)=0 Or JfRead(@bytes[0],4112)<>4111 : ProcedureReturn 17 : EndIf
   If bytes[0]<>((4094*13+37)&255) Or bytes[1]<>21 Or bytes[2]<>22 : ProcedureReturn 18 : EndIf
   For i=3 To 4110
    If bytes[i]<>0 : ProcedureReturn 19 : EndIf
   Next
  EndIf
 EndIf
 If ZentajiDiskClose()=0 : ProcedureReturn 20 : EndIf
 ProcedureReturn $2A
EndProcedure
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler")
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--probe", type=Path)
    args = parser.parse_args()
    zen_tools = args.zen_tools.resolve()
    sys.path.insert(0, str(zen_tools))
    from zen_native_fixture import Fixture

    zenemu = zen_tools / ("zenemu.exe" if os.name == "nt" else "zenemu")
    work = args.keep.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if args.probe:
        image = args.probe.read_bytes()
    else:
        source = work / "anvilfs_probe.zentaji"
        compiled = work / "anvilfs_probe.zex"
        source.write_text(SOURCE, encoding="ascii")
        built = subprocess.run(
            [str(resolve_compiler(args.compiler)), "--compile", str(source), "-o", str(compiled)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True, timeout=120,
        )
        (work / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        assert built.returncode == 0, built.stdout[-4000:] + built.stderr
        image = compiled.read_bytes()

    def run(label, medium, exit_code=0x2A, mode=0, cut=0, wanted=0, readonly=False):
        folder = work / label
        fixture = Fixture(ram_size=2 << 20, cores=2, disks={0: (medium, readonly)})
        fixture.load_image(image)
        struct.pack_into("<QQQ", fixture.ram, CONTROL, mode, cut, wanted)
        config = fixture.write(folder)
        config.write_text(config.read_text().replace("disk-memory 0 ", "disk 0 "), encoding="ascii")
        native = subprocess.run(
            [str(zenemu), str(config), "--max", "25000000"], capture_output=True, text=True, timeout=45,
        )
        (folder / "native.log").write_text(native.stdout + native.stderr, encoding="utf-8")
        assert native.returncode == 0, (label, native.stdout[-2000:], native.stderr)
        assert re.search(rf"^END .* exit={exit_code:X} ", native.stdout, re.M), (label, native.stdout[-2000:])
        return (folder / "disk0.img").read_bytes()

    with tempfile.TemporaryDirectory(prefix="anvilfs-seed-") as temp:
        root = Path(temp) / "seed"
        (root / "project").mkdir(parents=True)
        old = bytes((i * 13 + 37) & 255 for i in range(6000))
        (root / "project" / "copy.bin").write_bytes(old)
        original = Path(temp) / "seed.img"
        build_image(original, 2 << 20, root)
        medium = original.read_bytes()

    run("patch-and-truncate", medium, mode=3)
    new = run("complete", medium)
    run("read-complete", new, mode=1, wanted=1)
    for cut in (1, 3, 6, 7, 10, 14):
        snapshot = run(f"cut-{cut}", medium, exit_code=0x100 + cut, cut=cut)
        if cut == 7:
            assert run("dirty-readonly", snapshot, mode=2, readonly=True) == snapshot
        run(f"recover-{cut}", snapshot, mode=1, wanted=int(cut >= 7))
    corrupt = bytearray(medium)
    first = struct.unpack_from("<I", corrupt, 454)[0]
    corrupt[(first + 152) * 512 + 24] ^= 1
    assert run("corrupt-entry", corrupt, mode=4, readonly=True) == corrupt
    overlap = bytearray(medium)
    overlap[462:478] = overlap[446:462]
    assert run("overlapping-partitions", overlap, mode=4, readonly=True) == overlap
    two_partitions = bytearray(medium + medium[first * 512:])
    two_partitions[462:478] = two_partitions[446:462]
    struct.pack_into("<I", two_partitions, 470, len(medium) // 512)
    assert run("staged-partition-switch", two_partitions, mode=5) == two_partitions
    result = dict(probe_sha256=hashlib.sha256(image).hexdigest(),
                  interruption_points=[1, 3, 6, 7, 10, 14], read_only_refusal=True,
                  corrupt_entry_refusal=True, overlapping_partition_refusal=True,
                  patch_and_truncate=True, staged_partition_switch=True)
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS AnvilFS file bytes before and after commit, recovery, read-only refusal, and cross-page writes")


if __name__ == "__main__":
    main()
