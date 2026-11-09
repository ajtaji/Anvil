"""Zentaji real disk queues, 512-sector adapter and shared FAT32 proof."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
IncludeFile "Zentaji/Board/disk.pbi"
Procedure.i PrepareDisk()
 PokeQ(#ZEN_IDLE_INTC+$120,3)
 PokeQ(#ZEN_IDLE_INTC+$220,3)
 PokeQ(#ZEN_IDLE_INTC+$228,1)
 PokeQ(#ZEN_IDLE_INTC+$F008,514)
 ProcedureReturn ZentajiPromptIdlePrepare(50)
EndProcedure
Procedure.i Main(scenario.i)
 Protected n.i,tag.q
 If scenario=1
  If ZentajiDiskOpen(0)<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_CONTEXT : ProcedureReturn 1 : EndIf
  ProcedureReturn 42
 EndIf
 If PrepareDisk()<>1 : ProcedureReturn 2 : EndIf
 If scenario=2
  If ZentajiDiskOpen(16)<>0 Or ZentajiDiskOpen(-1)<>0 Or ZentajiDiskOpen(15)<>0 : ProcedureReturn 3 : EndIf
  ProcedureReturn 42
 EndIf
 If scenario=3
  PokeQ(#ZEN_DISK_BASE+$60,$C0000) : PokeQ(#ZEN_DISK_BASE+$68,2)
  PokeQ(#ZEN_DISK_BASE+$80,$C0080) : PokeQ(#ZEN_DISK_BASE+$88,2)
  PokeQ(#ZEN_DISK_BASE+$10,1)
  If ZentajiDiskOpen(0)<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_FOREIGN Or PeekQ(#ZEN_DISK_BASE+$60)<>$C0000 : ProcedureReturn 4 : EndIf
  ProcedureReturn 42
 EndIf
 If scenario=4
  PokeQ(#ZEN_DISK_BASE+$60,$C0000) : PokeQ(#ZEN_DISK_BASE+$68,8)
  PokeQ(#ZEN_DISK_BASE+$80,$C0100) : PokeQ(#ZEN_DISK_BASE+$88,4)
  PokeQ(#ZEN_DISK_BASE+$20,2)
 EndIf
 If ZentajiDiskOpen(0)<>1 Or ZentajiDiskSectors()<>64 : ProcedureReturn 5 : EndIf
 If scenario=0
  If ZentajiDiskRead(7,10,$D0001)<>1 : ProcedureReturn 6 : EndIf
 ElseIf scenario=4
  If ZentajiDiskRead(0,1,$D0000)<>1 Or ZentajiDiskClose()<>1 : ProcedureReturn 7 : EndIf
  If PeekQ(#ZEN_DISK_BASE+$10)<>0 Or PeekQ(#ZEN_DISK_BASE+$60)<>$C0000 Or PeekQ(#ZEN_DISK_BASE+$68)<>8 Or PeekQ(#ZEN_DISK_BASE+$80)<>$C0100 Or PeekQ(#ZEN_DISK_BASE+$88)<>4 Or PeekQ(#ZEN_DISK_BASE+$20)<>2 : ProcedureReturn 8 : EndIf
  If PeekQ(#ZEN_DISK_BASE+$70)<>0 Or PeekQ(#ZEN_DISK_BASE+$78)<>0 Or PeekQ(#ZEN_DISK_BASE+$90)<>0 Or PeekQ(#ZEN_DISK_BASE+$98)<>0 : ProcedureReturn 9 : EndIf
  If ZentajiDiskOpen(0)<>1 : ProcedureReturn 10 : EndIf
 ElseIf scenario=5
  If ZentajiDiskRead(-1,1,$D0000)<>0 Or ZentajiDiskRead(64,1,$D0000)<>0 Or ZentajiDiskRead(63,2,$D0000)<>0 Or ZentajiDiskRead(0,-1,$D0000)<>0 : ProcedureReturn 11 : EndIf
  If ZentajiDiskRead(0,1,$FFFF000000000000)<>0 Or ZentajiDiskRead(0,1,$1FFFFF)<>0 Or ZentajiDiskRead(0,1,@zenDisk)<>0 Or ZentajiDiskRead(0,1,zenDisk\sq)<>0 Or ZentajiDiskRead(0,1,zenDisk\bounce)<>0 : ProcedureReturn 12 : EndIf
  If zenDisk\tag<>0 Or ZentajiDiskRead(64,0,0)<>1 : ProcedureReturn 13 : EndIf
 ElseIf scenario=6
  For n=0 To 5119 : PokeA($D0000+n,(n*13+7)&255) : Next
  If ZentajiDiskWrite(7,10,$D0000)<>1 Or ZentajiDiskFlush()<>1 Or ZentajiDiskRead(7,10,$D4001)<>1 : ProcedureReturn 14 : EndIf
 ElseIf scenario=7
  For n=0 To 4095 : PokeA($D0000+n,(n*7+3)&255) : Next
  If ZentajiDiskWrite(8,8,$D0000)<>1 Or zenDisk\tag<>1 Or ZentajiDiskRead(8,8,$D4000)<>1 : ProcedureReturn 15 : EndIf
 ElseIf scenario=8
  If ZentajiDiskWrite(0,1,$D0000)<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_READONLY Or zenDisk\tag<>0 Or ZentajiDiskRead(0,1,$D0000)<>1 : ProcedureReturn 16 : EndIf
 ElseIf scenario=9
  For n=0 To 19
   If ZentajiDiskRead(n,1,$D0000+n*512)<>1 : ProcedureReturn 17 : EndIf
  Next
  If zenDisk\tag<>20 Or zenDisk\head<>0 Or zenDisk\phase<>1 : ProcedureReturn 18 : EndIf
 ElseIf scenario=10 Or scenario=11
  If ZentajiDiskTimeoutUs(1)<>1 : ProcedureReturn 19 : EndIf
  For n=0 To 511 : PokeA($D0000+n,$CC) : Next
  If scenario=10
   If ZentajiDiskRead(8,1,$D0000)<>0 : ProcedureReturn 20 : EndIf
  Else
   If ZentajiDiskWrite(8,8,$D0000)<>0 : ProcedureReturn 21 : EndIf
  EndIf
  If ZentajiDiskLastError()<>#ZEN_DISK_E_TIMEOUT Or ZentajiDiskMode()<>2 Or zenDisk\pending<>1 : ProcedureReturn 22 : EndIf
  If ZentajiDiskRead(0,1,$D2000)<>0 : ProcedureReturn 23 : EndIf
  For n=0 To 511 : PokeA($D0000+n,$77) : Next
  HwPromptIdleWait()
  If ZentajiDiskClose()<>1 Or ZentajiDiskOpen(0)<>1 : ProcedureReturn 24 : EndIf
  If ZentajiDiskRead(8,1,$D2000)<>1 : ProcedureReturn 25 : EndIf
 ElseIf scenario=12
  tag=zenDisk\tag
  If ZentajiDiskCommand(9,0)<>0 Or ZentajiDiskDeviceStatus()<>1 Or ZentajiDiskLastError()<>#ZEN_DISK_E_DEVICE Or zenDisk\pending<>0 Or ZentajiDiskMode()<>1 : ProcedureReturn 26 : EndIf
  If ZentajiDiskRead(0,1,$D0000)<>1 : ProcedureReturn 27 : EndIf
 ElseIf scenario=13
  PokeQ(#ZEN_IDLE_INTC+$F008,0)
  If ZentajiDiskRead(0,1,$D0000)<>0 Or zenDisk\tag<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_CONTEXT : ProcedureReturn 28 : EndIf
  PokeQ(#ZEN_IDLE_INTC+$F008,514)
 ElseIf scenario=14
  PokeQ(#ZEN_DISK_BASE+$20,2)
  If ZentajiDiskRead(0,1,$D0000)<>0 Or ZentajiDiskMode()<>2 Or zenDisk\tag<>0 Or ZentajiDiskClose()<>0 : ProcedureReturn 29 : EndIf
  ProcedureReturn 42
 ElseIf scenario=16 Or scenario=17
  If ZentajiDiskTimeoutUs(1)<>1 Or ZentajiDiskRead(8,1,$D0000)<>0 Or zenDisk\pending<>1 : ProcedureReturn 32 : EndIf
  HwPromptIdleWait()
  If scenario=16 : PokeQ(zenDisk\cq+zenDisk\head*16,zenDisk\tag+1) : Else : PokeU(zenDisk\cq+zenDisk\head*16+14,1-zenDisk\phase) : EndIf
  If ZentajiDiskClose()<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_COMPLETION Or zenDisk\pending<>1 Or ZentajiDiskMode()<>2 Or PeekQ(#ZEN_DISK_BASE+$90)<>zenDisk\head : ProcedureReturn 33 : EndIf
  ProcedureReturn 42
 ElseIf scenario=18
  zenDisk\owner=1
  If ZentajiDiskRead(0,1,$D0000)<>0 Or ZentajiDiskMode()<>1 Or zenDisk\tag<>0 Or ZentajiDiskTimeoutUs(1)<>0 : ProcedureReturn 34 : EndIf
  zenDisk\owner=0
  If ZentajiDiskRead(0,1,$D0000)<>1 : ProcedureReturn 35 : EndIf
 ElseIf scenario=15
  If ZentajiDiskFlush()<>1 Or ZentajiDiskTimeoutUs(0)<>0 Or ZentajiDiskTimeoutUs(2000001)<>0 Or ZentajiDiskTimeoutUs(100000)<>1 : ProcedureReturn 30 : EndIf
 EndIf
 If ZentajiDiskClose()<>1 Or ZentajiDiskSectors()<>0 Or ZentajiDiskClose()<>1 : ProcedureReturn 31 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--fat-only',action='store_true')
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args,timeout=60):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    disk=bytes((i*17+(i//512)*3+11)&255 for i in range(8*4096))
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-zen-disk-') as tmp:
        td=Path(tmp)
        if not a.fat_only:
            src=td/'disk.zentaji';image=td/'disk.zex';src.write_text(SOURCE,encoding='utf-8')
            out=run([cc,'--compile',src,'-o',image]);assert 'is READ but never' not in out,out
            ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'));assert image.read_bytes()==zexpack.header(org,org,data)+data
            for scenario,active in [(s,0) for s in range(19)]+[(0,1)]:
                m=I.Fixture(ram_size=2<<20,cores=2,disks={0:(bytearray(disk),scenario==8)},display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());c=m.cores[active];c.r[1]=scenario
                if active:
                    m.cores[0].state='PARKED';c.pc=int.from_bytes(image.read_bytes()[8:16],'little');c.r[255]=2<<20;c.state='RUNNING'
                for r in range(128,253):c.r[r]=0x10000+r*13
                for r in range(32,64):c.v[r]=sum((r*100+j)<<(64*j) for j in range(8))
                fixture=m;m=runner.execute(fixture,4000000,td);c=m.cores[active]
                assert not L.capture(fixture,str(td))
                if scenario==6:
                    cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
                native=run([L.EXE,td/'machine.txt','--max','4000000','--ram',td/'final.bin'])
                assert c.state=='HALTED' and c.r[1]==42,(scenario,c.state,c.r[1],c.cr)
                assert (td/'final.bin').read_bytes()==m.ram,scenario
                I.assert_same_state(native,m)
                assert c.r[128:253]==[0x10000+r*13 for r in range(128,253)] and c.r[255]==2<<20,scenario
                assert c.v[32:]==[sum((r*100+j)<<(64*j) for j in range(8)) for r in range(32,64)],scenario
                want=bytearray(disk)
                if scenario==0:assert m.ram[0xD0001:0xD0001+5120]==disk[7*512:17*512]
                if scenario==6:
                    expected=bytes((i*13+7)&255 for i in range(5120));want[7*512:17*512]=expected;assert m.ram[0xD4001:0xD4001+5120]==expected
                if scenario==7:
                    expected=bytes((i*7+3)&255 for i in range(4096));want[4096:8192]=expected;assert m.ram[0xD4000:0xD4000+4096]==expected
                if scenario==9:assert m.ram[0xD0000:0xD0000+20*512]==disk[:20*512]
                if scenario==10:assert m.ram[0xD0000:0xD0000+512]==b'\x77'*512 and m.ram[0xD2000:0xD2000+512]==disk[4096:4608]
                if scenario==11:
                    expected=b'\xCC'*512+bytes(3584);want[4096:8192]=expected;assert m.ram[0xD2000:0xD2000+512]==b'\xCC'*512
                assert bytes(m.disks[0].image)==want,scenario
                if scenario==6:
                    persisted=(td/'disk0.img').read_bytes()
                    assert persisted==want,'guest write/FLUSH did not persist exact host image bytes'
                    print('PASS exact host backing persisted after actual driver FUA writes and FLUSH',flush=True)
                assert all(other.state=='PARKED' for i,other in enumerate(m.cores) if i!=active),scenario
            print('PASS 20 actual Forge/reference/native full-state/RAM/medium cases: aligned/unaligned and cross-4KB 512-sector I/O, partial/full writes, queue phase wrap, read-only/bounds/ownership/refusals, flush/device errors, timeout quarantine and late DMA retirement/reopen, corrupted tag/phase, owner mismatch and actual core1 execution')
        # Reuse the existing independent FAT fixture, not a second filesystem.
        sys.path.insert(0,str(ROOT/'tools/a64'))
        import a64_fat_check as F
        import zentaji_boot_image as B
        import json
        sparse=F.build();sectors=(max(71104,max(sparse.s)+1)+7)&-8
        fatdisk=bytearray(sectors*512)
        for lba,sector in sparse.s.items():fatdisk[lba*512:(lba+1)*512]=sector
        fat_source=r'''
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
IncludeFile "Zentaji/Board/disk.pbi"
IncludeFile "Anvil/Storage/fat32.pbi"
Global Dim filebuf.a[4096]
Global visits.i,ranges.i
Procedure.i RangeVisit(lba.i,blocks.i,context.i)
 ranges=ranges+1
 ProcedureReturn Bool(lba>=0 And blocks>0 And lba<=ZentajiDiskSectors()-blocks)
EndProcedure
Procedure.i EntryVisit(*name,depth.i,lba.i,bytes.i,attr.i,context.i)
 visits=visits+1
 ProcedureReturn 1
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected n.i,tag.q
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 1 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3) : PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)<>1 Or ZentajiDiskOpen(0)<>1 : ProcedureReturn 2 : EndIf
 FatSetRangeReader(@ZentajiDiskRead) : FatSetRangeWriter(@ZentajiDiskWrite) : FatSetBlockFlusher(@ZentajiDiskFlush)
 If FatMount(1)<>1 Or FatBytesPerCluster()<>512 Or fat_partLba<>63 : ProcedureReturn 3 : EndIf
 tag=zenDisk\tag
 If FatWalkRoot(0,0)<>0 Or FatLastError()<>#FAT_ERR_CHAINLOOP : ProcedureReturn 12 : EndIf
 If FatWalkAllocations(0,@RangeVisit,0)<>0 Or FatLastError()<>#FAT_ERR_CHAINLOOP : ProcedureReturn 13 : EndIf
 If FatWalkAllocations(@EntryVisit,0,0)<>0 Or FatLastError()<>#FAT_ERR_CHAINLOOP Or ranges<>0 Or visits<>0 Or zenDisk\tag<>tag : ProcedureReturn 14 : EndIf
 If FatWalkRoot(@RangeVisit,0)<>1 : ProcedureReturn 4 : EndIf
 ; The established fixture intentionally contains corrupt file/subdirectory
 ; chains. The complete allocation walk must refuse them, not loop or bless it.
 If FatWalkAllocations(@EntryVisit,@RangeVisit,0)<>0 Or visits<1 Or ranges<1 : ProcedureReturn 5 : EndIf
 If FatOpen("PMF.IMG")<>1 Or FatSize()<>2500 : ProcedureReturn 6 : EndIf
 For n=0 To 4095 : filebuf[n]=$CC : Next
 If FatRead(@filebuf[0],2500)<>2500 Or FatRead(@filebuf[2500],32)<>0 : ProcedureReturn 7 : EndIf
 If FatRewind()<>1 : ProcedureReturn 8 : EndIf
 For n=0 To 2400 Step 100
  If FatRead(@filebuf[n],100)<>100 : ProcedureReturn 9 : EndIf
 Next
 FatClose()
 If FatOpen("NOFILE.TXT")<>0 : ProcedureReturn 10 : EndIf
 If ZentajiDiskClose()<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 11 : EndIf
 ProcedureReturn 42
EndProcedure
'''
        src=td/'shared-fat.zentaji';compiled=td/'shared-fat.zex';src.write_text(fat_source,encoding='utf-8')
        out=run([cc,'--compile',src,'-o',compiled]);assert 'is READ but never' not in out,out
        aref=A.Asm();aref.assemble(Path(str(compiled)+'.asm').read_text(encoding='utf-8-sig'))
        wrapped,meta,assembly,mapping=B.pack(compiled.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig')))
        m=I.Fixture(ram_size=2<<20,cores=2,disks={0:(bytearray(fatdisk),True)},display_modes=[(1,1,60000)]);m.load_image(wrapped)
        assert not L.capture(m,str(td));native=run([L.EXE,td/'machine.txt','--max','8000000','--ram',td/'final.bin']);m=runner.execute(m,8000000,td)
        c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,('FAT',c.state,c.r[1],c.cr)
        assert (td/'final.bin').read_bytes()==m.ram
        I.assert_same_state(native,m)
        at=aref.sym['GLOBAL_FILEBUF'];assert m.ram[at:at+2500]==F.content(2500) and m.ram[at+2500:at+4096]==b'\xCC'*(4096-2500)
        assert bytes(m.disks[0].image)==fatdisk and c.r[255]==meta['minimum_ram_bytes']-1048576 and m.cores[1].state=='PARKED'
        print('PASS actual shared FAT32 over real Zentaji queues with owned startup stack/vectors: MBR/partition/FSInfo mount, root/allocation walk with corrupt-chain refusal, fragmented file reads/rewind/chunks/EOF/not-found; exact native state/RAM and independent file/medium bytes')



if __name__=='__main__':main()
