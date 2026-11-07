"""Real ROM -> Anvil-owned startup -> reuse of the same boot disk queues."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
IncludeFile "Zentaji/Board/disk.pbi"
Global Dim block.a[4096]
Global Dim sector.a[512]
Procedure.i Main(table.i,source.i,context.i)
 Protected disk.i,base.i,n.i
 If source<>1 Or table<>$FFFF000000010000 Or ZentajiBootContextValid(context)<>1 : ProcedureReturn 1 : EndIf
 disk=PeekA(table+36) : base=#ZEN_DISK_BASE+disk*65536
 If PeekQ(base+$10)<>0 Or PeekQ(base+$60)<>0 Or PeekQ(base+$68)<>0 Or PeekQ(base+$70)<>0 Or PeekQ(base+$78)<>0 Or PeekQ(base+$80)<>0 Or PeekQ(base+$88)<>0 Or PeekQ(base+$90)<>0 Or PeekQ(base+$98)<>0 : ProcedureReturn 2 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3)
 PokeQ(#ZEN_IDLE_INTC+$220,3) : PokeQ(#ZEN_IDLE_INTC+$228,1)
 PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(50)<>1 : ProcedureReturn 3 : EndIf
 If ZentajiDiskOpen(disk)<>1 : ProcedureReturn 4 : EndIf
 If ZentajiDiskRead(0,8,@block[0])<>1 Or PeekQ(@block[0])<>$31494A41544E455A : ProcedureReturn 5 : EndIf
 If ZentajiDiskRead(8,1,@sector[0])<>1 : ProcedureReturn 6 : EndIf
 If ZentajiDiskWrite(0,1,@sector[0])<>0 Or ZentajiDiskLastError()<>#ZEN_DISK_E_READONLY : ProcedureReturn 7 : EndIf
 If ZentajiDiskClose()<>1 Or ZentajiDiskOpen(disk)<>1 : ProcedureReturn 8 : EndIf
 For n=0 To 511 : PokeA(@sector[0]+n,0) : Next
 If ZentajiDiskRead(8,1,@sector[0])<>1 Or ZentajiDiskClose()<>1 : ProcedureReturn 9 : EndIf
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 10 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-boot-disk-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';compiled=td/'probe.zex'
        src.write_bytes(SOURCE.replace('\n','\r\n').encode('utf-8'))
        run([cc,'--compile',src,'-o',compiled])
        ref=A.Asm();origin,data=ref.assemble(Path(str(compiled)+'.asm').read_text(encoding='utf-8-sig'))
        assert compiled.read_bytes()==zexpack.header(origin,origin,data)+data
        wrapped,meta,_,_=B.pack(compiled.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig')))
        medium=zexpack.disk_image(wrapped)
        for disk in (0,15):
            m=I.Machine(ram_size=2<<20,cores=2,disks={disk:(bytearray(medium),True)},display_modes=[(16,16,60000)])
            m.power_on(1,disk)
            assert not L.capture(m,str(td))
            native=run([L.EXE,td/'machine.txt','--max','1000000','--ram',td/'final.bin'])
            m.run(1000000);c=m.cores[0]
            assert c.state=='HALTED' and c.r[1]==42,(disk,c.state,c.r[1],hex(c.pc),bytes(m.serial[0].out).decode('ascii',errors='replace'),c.cr)
            assert not c.perf['exceptions'] and m.cores[1].state=='PARKED'
            assert (td/'final.bin').read_bytes()==m.ram
            line=next(s[6:] for s in native.splitlines() if s.startswith('STATE '))
            assert line.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],disk
            at=ref.sym['GLOBAL_BLOCK'];assert m.ram[at:at+4096]==medium[:4096]
            at=ref.sym['GLOBAL_SECTOR'];assert m.ram[at:at+512]==wrapped[64:576]
            d=m.disks[disk]
            assert not d.busy and not d.held and not d.ctrl and not d.irq_status and not d.irq_enable
            assert not any((d.sq_base,d.sq_n,d.sq_head,d.sq_tail,d.cq_base,d.cq_n,d.cq_head,d.cq_tail)) and d.phase==1
            assert bytes(d.image)==medium and c.r[255]==meta['minimum_ram_bytes']-1048576
            assert (td/('disk%d.img'%disk)).read_bytes()==medium
            print('PASS actual ROM disk%d -> owned Anvil supervisor startup -> same-disk acquire/read/refuse readonly write/close/reopen/read: full native/twin state/RAM, independent header/payload bytes, clean queues and unchanged host image'%disk,flush=True)


if __name__=='__main__':main()
