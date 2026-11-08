"""Refusal/ownership proofs for the production Zentaji storage lifecycle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Zentaji/Board/disk.pbi"
IncludeFile "Anvil/Hal/hal.pbi"
IncludeFile "Anvil/Core/wallclock.pbi"
IncludeFile "Zentaji/Board/storage.pbi"
Global Dim payload.a[32]
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
 Protected tag.q,handle.i
 #CASE=CASE_VALUE
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 1 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3) : PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)<>1 : ProcedureReturn 2 : EndIf
 If ZentajiStorageFromBoot(context+1,1)<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_BOOT : ProcedureReturn 3 : EndIf
 If ZentajiStorageFromBoot(context,1)<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_BOOT : ProcedureReturn 4 : EndIf
 If #CASE=1
  If ZentajiStorageConfigure(15,1)<>1 Or ZentajiStorageUp()<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_DISK Or ZentajiDiskMode()<>0 : ProcedureReturn 5 : EndIf
 ElseIf #CASE=2
  If ZentajiStorageConfigure(0,1)<>1 Or ZentajiDiskOpen(0)<>1 : ProcedureReturn 6 : EndIf
  tag=zenDisk\tag
  If ZentajiStorageUp()<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_BUSY Or zenDisk\tag<>tag : ProcedureReturn 7 : EndIf
  If ZentajiStorageDown()<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_BUSY Or ZentajiDiskOwned()<>1 Or zenDisk\tag<>tag : ProcedureReturn 8 : EndIf
  If ZentajiDiskClose()<>1 : ProcedureReturn 9 : EndIf
 ElseIf #CASE=3
  If ZentajiStorageConfigure(0,1)<>1 Or ZentajiStorageUp()<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_VOLUME : ProcedureReturn 10 : EndIf
  If gHwFileMounted<>0 Or gHwFileWriter<>0 Or HwFileWritable()<>0 Or ZentajiDiskMode()<>1 : ProcedureReturn 11 : EndIf
 ElseIf #CASE=4
  If UartInit(0)<>1 Or ZentajiStorageConfigure(0,1)<>1 Or HwStorageUp()<>1 : ProcedureReturn 12 : EndIf
  If gHwFileMounted<>1 Or HwFileWritable()<>0 Or gHwFileWriter<>0 : ProcedureReturn 13 : EndIf
  tag=zenDisk\tag
  If HwFileWriteAll("NO.BIN",@payload[0],32)<>0 Or HwFileLastError()<>#HW_FILE_READONLY Or zenDisk\tag<>tag Or fs_writer<>0 : ProcedureReturn 14 : EndIf
  If FsWalkRoot(@RangeVisit,0)<>0 Or FsLastError()<>#FS_E_ALLOCATION_UNSUPPORTED : ProcedureReturn 22 : EndIf
  If FsWalkAllocations(@EntryVisit,@RangeVisit,0)<>0 Or FsLastError()<>#FS_E_ALLOCATION_UNSUPPORTED Or visits<>0 Or ranges<>0 : ProcedureReturn 23 : EndIf
  HwStorageReport()
  handle=HwFilePrepareBegin("NO.BIN")
  If handle<=0 Or FsMountPending()<>1 : ProcedureReturn 15 : EndIf
  HwStorageReport()
  tag=zenDisk\tag
  If ZentajiStorageDown()<>0 Or ZentajiStorageLastError()<>#ZEN_STORAGE_E_BUSY Or zenDisk\tag<>tag : ProcedureReturn 16 : EndIf
  If HwStorageUp()<>1 Or FsMountPending()<>1 Or zenDisk\tag<>tag : ProcedureReturn 17 : EndIf
  If HwFilePrepareCancel(handle)<>1 Or FsMountPending()<>0 : ProcedureReturn 18 : EndIf
  If HwFileOpen("2:NO.BIN")<>0 Or FsType()<>#FS_NONE : ProcedureReturn 24 : EndIf
  HwStorageReport()
  If ZentajiConsoleDrain()<>1 : ProcedureReturn 19 : EndIf
 EndIf
 If ZentajiStorageDown()<>1 Or ZentajiStorageDown()<>1 Or ZentajiDiskMode()<>0 Or gHwFileMounted<>0 Or gHwFileWriter<>0 Or HwFileWritable()<>0 : ProcedureReturn 20 : EndIf
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 21 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case',type=int,choices=(1,2,3,4),action='append')
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-storage-lifecycle-') as tmp:
        td=Path(tmp)
        for case in (a.case or (1,2,3,4)):
            src=td/'probe.zentaji';compiled=td/'probe.zex';src.write_bytes(SOURCE.replace('CASE_VALUE',str(case)).replace('\n','\r\n').encode())
            run([cc,'--compile',src,'-o',compiled])
            ref=A.Asm();origin,data=ref.assemble(Path(str(compiled)+'.asm').read_text(encoding='utf-8-sig'))
            assert compiled.read_bytes()==zexpack.header(origin,origin,data)+data
            wrapped,_,_,_=B.pack(compiled.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig')))
            medium=bytearray(2104*512) if case==3 else E.build()
            m=I.Machine(ram_size=4<<20,cores=2,disks={0:(bytearray(medium),case==4)},display_modes=[(1,1,60000)]);m.load_image(wrapped)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
            out=run([L.EXE,cfg,'--max','3000000','--ram',td/'final.bin'])
            assert ' exit=2A ' in out,(case,'native failure',out[-2500:])
            m.run(3000000);c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,(case,c.state,c.r[1])
            assert (td/'final.bin').read_bytes()==m.ram
            line=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert line.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            assert (td/'disk0.img').read_bytes()==bytes(m.disks[0].image)==medium
            expected=(b'Zentaji disk 0 holds 2056 blocks of 512 bytes.\r\nMounted partition 1 uses exFAT; the medium is read-only.\r\n'
                      b'Zentaji disk 0 holds 2056 blocks of 512 bytes.\r\nA filesystem mount is in progress.\r\n'
                      b'Zentaji disk 0 holds 2056 blocks of 512 bytes.\r\nNo filesystem partition is currently mounted.\r\n') if case==4 else b''
            assert bytes(m.serial[0].out)==expected,(case,bytes(m.serial[0].out))
            print('PASS storage lifecycle case%d: native/twin state/RAM, unchanged host disk, exact output'%case,flush=True)


if __name__=='__main__':main()
