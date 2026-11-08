"""Real startup layout and shared payload-range policy on Zentaji."""
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
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Anvil/Hal/hal.pbi"
IncludeFile "Anvil/Core/format.pbi"
IncludeFile "Zentaji/Board/memory.pbi"
IncludeFile "Anvil/Core/memrange.pbi"
Global Dim report.q[18]
Procedure.i Main(table.i,source.i,context.i)
 Protected stage.i,top.i,ram.i,bottom.i,n.i,old.i
 If HwPayWindows()<>0 Or InPayload(0,0)<>0 Or HwStageAddr()<>0 Or HwAddrCheck(0,0,0)<>#HW_ADDR_UNKNOWN : ProcedureReturn 1 : EndIf
 If ZentajiMemoryBind(context+1)<>0 Or ZentajiMemoryBind(context)<>1 Or ZentajiMemoryBind(context)<>1 : ProcedureReturn 2 : EndIf
 stage=HwStageAddr() : top=HwPayHi(0) : ram=PeekQ(context+#ZEN_BOOT_RAM) : bottom=PeekQ(context+#ZEN_BOOT_STACK_BOTTOM)
 report[0]=HwMonLo() : report[1]=HwMonHi() : report[2]=HwMonBytes() : report[3]=HwMonStack()
 report[4]=HwPayWindows() : report[5]=HwPayLo(0) : report[6]=top : report[7]=PayloadTop(stage)
 For n=0 To 2 : report[8+n*2]=HwMonRegionLo(n) : report[9+n*2]=HwMonRegionHi(n) : Next
 report[14]=HwPayLo(-1) : report[15]=HwPayHi(1) : report[16]=HwMonRegionLo(3) : report[17]=HwMonRegionHi(-1)
 If HwMonRegions()<>3 Or InPayload(stage,top)<>1 Or InPayload(stage,stage)<>1 Or InPayload(top,top)<>1 : ProcedureReturn 3 : EndIf
 If InPayload(stage-1,stage)<>0 Or InPayload(top,top+1)<>0 Or InPayload(0,ram-1)<>0 Or InPayload(-1,top)<>0 Or InPayload(stage,stage-1)<>0 : ProcedureReturn 4 : EndIf
 If HitsMonitor(0,0)<>1 Or HitsMonitor(stage-1,stage)<>1 Or HitsMonitor(top,top+1)<>2 Or HitsMonitor(ram-1,ram-1)<>3 : ProcedureReturn 5 : EndIf
 If gMonHitLo<>HwMonStack() Or gMonHitHi<>ram-1 Or gMonHitWhich<>2 Or HitsMonitor(stage,top)<>0 : ProcedureReturn 6 : EndIf
 If PayloadTop(stage-1)<>0 Or PayloadTop(top+1)<>0 Or PayloadTop(-1)<>0 : ProcedureReturn 7 : EndIf
 If HwAddrCheck(0,ram-1,0)<>#HW_ADDR_SAFE Or HwAddrCheck(stage,top,1)<>#HW_ADDR_SAFE : ProcedureReturn 8 : EndIf
 If HwAddrCheck(ram-1,ram,0)<>#HW_ADDR_ABSENT Or HwAddrBlockLo()<>ram Or HwAddrBlockHi()<>$7FFFFFFFFFFFFFFF : ProcedureReturn 9 : EndIf
 If HwAddrCheck($FFFF000000010000,$FFFF000000010007,0)<>#HW_ADDR_UNKNOWN Or HwAddrCheck(4,3,1)<>#HW_ADDR_UNKNOWN Or HwAddrCheck(0,0,2)<>#HW_ADDR_UNKNOWN : ProcedureReturn 10 : EndIf
 PokeQ(stage,$1122334455667788) : PokeQ(top-7,$8877665544332211)
 If UartInit(0)<>1 : ProcedureReturn 11 : EndIf
 PutMonitorMap()
 If ZentajiConsoleDrain()<>1 : ProcedureReturn 12 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
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
    with tempfile.TemporaryDirectory(prefix='anvil-zen-memory-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode())
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        for ram,boot in ((2<<20,False),(4<<20,False),((8<<20)+123,False),(4<<20,True)):
            disks={15:(bytearray(zexpack.disk_image(wrapped)),True)} if boot else {}
            m=I.Machine(ram_size=ram,cores=2,disks=disks,display_modes=[(1,1,60000)])
            if boot:m.power_on(1,15)
            else:m.load_image(wrapped)
            assert not L.capture(m,str(td));out=run([L.EXE,td/'machine.txt','--max','1000000','--ram',td/'final.bin'])
            assert ' exit=2A ' in out,(ram,boot,out[-2000:])
            m.run(1000000);c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,(ram,boot,c.state,c.r[1])
            assert (td/'final.bin').read_bytes()==m.ram
            state=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            last=meta['image_end'];stage=(last+4095)&-4096;stack=(ram&-16)-(1<<20);bottom=stack-meta['stack_bytes']
            expected=[meta['load'],last-1,last-meta['load'],stack,1,stage,bottom-1,bottom-1,0,stage-1,bottom,stack-1,stack,ram-1]+[(1<<64)-1]*4
            assert list(struct.unpack_from('<18Q',m.ram,ref.sym['GLOBAL_REPORT']))==expected
            assert struct.unpack_from('<Q',m.ram,stage)[0]==0x1122334455667788 and struct.unpack_from('<Q',m.ram,bottom-8)[0]==0x8877665544332211
            output=bytes(m.serial[0].out)
            for value in (meta['load'],last-1,stage,stack,bottom,ram-1):assert ('%08X'%value).encode() in output,(value,output)
            assert b'ARM' not in output and b'ROM workspace and loader stack' in output
            if boot:assert bytes(m.disks[15].image)==bytes(disks[15][0])==(td/'disk15.img').read_bytes()
            print('PASS memory layout RAM=%d ROM=%s: actual startup, independent extents, shared range boundaries, native/twin state/RAM and map output'%(ram,boot),flush=True)


if __name__=='__main__':main()
