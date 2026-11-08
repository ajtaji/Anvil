"""Actual shared FAT32/exFAT facade and HwFile seam over Zentaji disk queues."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Zentaji/Board/disk.pbi"
IncludeFile "Anvil/Hal/hal.pbi"
IncludeFile "Anvil/Core/wallclock.pbi"
IncludeFile "Anvil/Storage/fat32.pbi"
IncludeFile "Anvil/Storage/exfat.pbi"
IncludeFile "Anvil/Storage/filesystem.pbi"
IncludeFile "Anvil/Storage/hwfile.pbi"
Global Dim payload.a[2048]
Global Dim readbuf.a[4096]
Global Dim listed.a[256]
Global visits.i,ranges.i
Global Dim clockReport.q[3]
Procedure.i RangeVisit(lba.i,blocks.i,context.i)
 ranges=ranges+1
 ProcedureReturn Bool(lba>=0 And blocks>0 And lba<=ZentajiDiskSectors()-blocks)
EndProcedure
Procedure.i EntryVisit(*name,depth.i,lba.i,bytes.i,attr.i,context.i)
 visits=visits+1
 ProcedureReturn 1
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected n.i,tag.q,rc.i,count.i
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 1 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3) : PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)<>1 Or ZentajiDiskOpen(0)<>1 : ProcedureReturn 2 : EndIf
 If WallClockInit()<>1 : ProcedureReturn 3 : EndIf
 If WallClockSet(1794009600,#WALLCLOCK_SRC_RTC)<>0 Or WallClockLastError()<>#WALLCLOCK_ERR_SOURCE : ProcedureReturn 24 : EndIf
 If WallClockRtcAdmit(2)<>0 Or WallClockRtcAdmit(1)<>1 Or WallClockSet(1794009600,#WALLCLOCK_SRC_RTC)<>1 Or WallClockTrusted()<>1 : ProcedureReturn 25 : EndIf
 If WallClockRtcAdmit(0)<>1 Or WallClockTrusted()<>0 : ProcedureReturn 26 : EndIf
 If WallClockSet(1794009600,#WALLCLOCK_SRC_MANUAL)<>1 : ProcedureReturn 3 : EndIf
 clockReport[0]=Ticks() : clockReport[1]=HwMicros() : clockReport[2]=Ticks()
 ExFatProfileSetClock(@HwMicros)
 FsSetRangeReader(@ZentajiDiskRead) : FsSetRangeWriter(0) : FsSetBlockFlusher(@ZentajiDiskFlush)
 If FsMount(1)<>1 Or FsType()<>#FS_FAT : ProcedureReturn 4 : EndIf
 gHwFileMounted=1 : gHwFileWritable=1 : gHwFileWriter=@ZentajiDiskWrite
 For n=0 To 2047 : payload[n]=(n*7+n/512+31)&255 : Next
 If HwFileWriteAll("CHECK.BIN",@payload[0],1500)<>1 Or fs_writer<>0 : ProcedureReturn 5 : EndIf
 If HwFileOpen("CHECK.BIN")<>1 Or HwFileSize()<>1500 : ProcedureReturn 6 : EndIf
 If HwFileReadAt(0,@readbuf[0],300)<>300 Or HwFileReadAt(300,@readbuf[300],700)<>700 Or HwFileReadAt(100,@readbuf[1500],501)<>501 : ProcedureReturn 7 : EndIf
 HwFileClose()
 If HwFileWriteAll("CHECK.BIN",@payload[0],700)<>1 : ProcedureReturn 8 : EndIf
 If HwDirCreate("Folder")<>1 Or HwFileRename("CHECK.BIN","Folder/Long file name.bin")<>1 : ProcedureReturn 9 : EndIf
 If HwFileWriteAll("Folder/Long file name.bin",@payload[0],1800)<>1 : ProcedureReturn 10 : EndIf
 If HwDirCreate("Empty")<>1 Or HwDirRemove("Empty")<>1 : ProcedureReturn 11 : EndIf
 If HwFileWriteAll("DELETE.TXT",@payload[0],32)<>1 Or HwFileRemove("DELETE.TXT")<>1 : ProcedureReturn 12 : EndIf
 If HwFileOpen("DELETE.TXT")<>0 Or HwFileLastError()<>#HW_FILE_NOTFOUND : ProcedureReturn 13 : EndIf
 tag=zenDisk\tag : gHwFileWritable=0
 If HwFileWriteAll("NO.TXT",@payload[0],32)<>0 Or HwFileLastError()<>#HW_FILE_READONLY Or zenDisk\tag<>tag Or fs_writer<>0 : ProcedureReturn 14 : EndIf
 gHwFileWritable=1
 If FsRename("Folder/Long file name.bin","2:BAD.BIN")<>0 Or FsErrorKind()<>#FS_FACADE Or FsLastError()<>#FS_E_CROSS_VOLUME : ProcedureReturn 15 : EndIf
 If HwFileOpen("Folder/Long file name.bin")<>1 Or HwFileSize()<>1800 : ProcedureReturn 16 : EndIf
 If FsSelectPartition(2)<>0 Or FsLastError()<>#FS_E_BUSY Or FsPartition()<>1 : ProcedureReturn 17 : EndIf
 If HwFileReadAt(0,@readbuf[2048],1800)<>1800 : ProcedureReturn 18 : EndIf
 HwFileClose()
 If HwDirOpen("Folder")<>1 : ProcedureReturn 19 : EndIf
 rc=HwDirNext()
 While rc=1
  If HwDirIsDir()=0
   count=count+1
   If HwDirSize()<>1800 Or HwDirNameUtf8(@listed[0],256)<>18 : ProcedureReturn 20 : EndIf
  EndIf
  rc=HwDirNext()
 Wend
 If rc<>0 Or count<>1 : ProcedureReturn 21 : EndIf
 If FsWalkRoot(@RangeVisit,0)<>1 Or FsWalkAllocations(@EntryVisit,@RangeVisit,0)<>1 Or visits<1 Or ranges<2 : ProcedureReturn 22 : EndIf
 If FsFlush()<>1 Or FsUnmount()<>1 Or ZentajiDiskClose()<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 23 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt));sys.path.insert(0,str(ROOT/'tools/a64'))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    import a64_fat_check as F
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args,timeout=120):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        assert p.returncode==0,(p.returncode,p.stdout[-5000:],p.stderr)
        return p.stdout
    sparse=F.build()
    for base in (F.FAT_LBA,F.FAT1_LBA):
        for lba in range(base,base+F.FAT_SECS):sparse.s[lba]=bytearray(512)
        for cluster,value in [(0,0x0FFFFFF8),(1,0x0FFFFFFF),(2,F.EOC)]:sparse.u32(base,cluster*4,value)
    sparse.s[F.DATA_LBA]=bytearray(512)
    F.fsinfo(sparse,F.PART_LBA,F.CLUSTERS-1,3)
    sectors=(max(71104,max(sparse.s)+1)+7)&-8
    medium=bytearray(sectors*512)
    for lba,sector in sparse.s.items():medium[lba*512:(lba+1)*512]=sector
    with tempfile.TemporaryDirectory(prefix='anvil-zen-storage-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';compiled=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode())
        out=run([cc,'--compile',src,'-o',compiled]);assert 'is READ but never' not in out,out
        ref=A.Asm();origin,data=ref.assemble(Path(str(compiled)+'.asm').read_text(encoding='utf-8-sig'))
        assert compiled.read_bytes()==zexpack.header(origin,origin,data)+data
        wrapped,meta,_,_=B.pack(compiled.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig')))
        m=I.Machine(ram_size=4<<20,cores=2,disks={0:(bytearray(medium),False)},display_modes=[(1,1,60000)]);m.load_image(wrapped)
        assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
        out=run([L.EXE,cfg,'--max','12000000','--ram',td/'final.bin'])
        assert ' exit=2A ' in out,('native guest did not finish successfully',out[-2500:])
        m.run(12000000);c=m.cores[0]
        assert c.state=='HALTED' and c.r[1]==42,(c.state,c.r[1],hex(c.pc),c.cr)
        assert (td/'final.bin').read_bytes()==m.ram
        line=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert line.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
        assert (td/'disk0.img').read_bytes()==bytes(m.disks[0].image)
        import zentaji_storage_oracle as O
        expected=bytes((n*7+n//512+31)&255 for n in range(2048))
        at=ref.sym['GLOBAL_READBUF'];assert m.ram[at:at+1000]==expected[:1000] and m.ram[at+1500:at+2001]==expected[100:601] and m.ram[at+2048:at+3848]==expected[:1800]
        at=ref.sym['GLOBAL_LISTED'];assert bytes(m.ram[at:at+19])==b'Long file name.bin\0'
        at=ref.sym['GLOBAL_CLOCKREPORT'];before,us,after=struct.unpack_from('<3Q',m.ram,at)
        assert before*1000000//100000000<=us<=after*1000000//100000000
        proof=O.check(bytes(m.disks[0].image),medium,expected)
        print('PASS full shared filesystem/hwfile over real persistent queues: native/twin state/RAM/host image; '+proof,flush=True)


if __name__=='__main__':main()
