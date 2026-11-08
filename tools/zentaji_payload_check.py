"""Exercise the actual Zentaji CPU call boundary, independently of board policy."""
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
IncludeFile "Anvil/Kernel/Zentaji/payload_call.pbi"
ProcedureNaked TestVectors(value.i)
 ASM
  MTCR r0,r1,EVEC
  JR r254
 EndASM
EndProcedure
ProcedureNaked TestProtection(value.i)
 ASM
  MTCR r0,r1,PROT
  JR r254
 EndASM
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected entry.i=$280008,stack.i=$2F0000,bytes.i=16384,expect.i,rc.i,scenario.i
 If ZentajiPayloadEnter(0,0,0,0,0)<>0 Or ZentajiPayloadLastError()<>#ZEN_PAYLOAD_E_CONTEXT : ProcedureReturn 6 : EndIf
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 1 : EndIf
 scenario=PeekQ($300008)
 Select scenario
  Case 1 : entry=entry+1 : expect=#ZEN_PAYLOAD_E_ENTRY
  Case 2 : stack=stack-1 : expect=#ZEN_PAYLOAD_E_STACK
  Case 3 : stack=HwMonStack() : expect=#ZEN_PAYLOAD_E_STACK
  Case 4 : bytes=16368 : expect=#ZEN_PAYLOAD_E_STACK
  Case 5 : stack=entry+16384 : expect=#ZEN_PAYLOAD_E_STACK
  Case 6 : entry=-8 : expect=#ZEN_PAYLOAD_E_ENTRY
  Case 7 : entry=HwMonLo() : expect=#ZEN_PAYLOAD_E_ENTRY
  Case 8 : zenPayloadActive=1 : expect=#ZEN_PAYLOAD_E_ACTIVE
  Case 9 : ZenCpuSwapStatus(1) : expect=#ZEN_PAYLOAD_E_CONTEXT
  Case 10 : TestVectors($283000) : expect=#ZEN_PAYLOAD_E_CONTEXT
  Case 11 : TestProtection(1) : expect=#ZEN_PAYLOAD_E_CONTEXT
  Case 12 : stack=0 : expect=#ZEN_PAYLOAD_E_STACK
  Case 14 : bytes=-16 : expect=#ZEN_PAYLOAD_E_STACK
  Case 15 : stack=$7FFFFFFFFFFFFFF0 : expect=#ZEN_PAYLOAD_E_STACK
  Case 16 : PokeQ(context+8,1) : PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,0) : expect=#ZEN_PAYLOAD_E_UNAVAILABLE
  Case 17 : PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,0) : expect=#ZEN_PAYLOAD_E_CONTEXT
  Case 18 : PokeQ(context+8,99) : expect=#ZEN_PAYLOAD_E_CONTEXT
 EndSelect
 rc=ZentajiPayloadEnter(context,entry,$1122334455667788,stack,bytes)
 If scenario=9 : ZenCpuSwapStatus(0) : EndIf
 If scenario=10 : TestVectors(PeekQ(context+#ZEN_BOOT_VECTORS)) : EndIf
 If scenario=11 : TestProtection(0) : EndIf
 If expect<>0
  If rc<>0 Or ZentajiPayloadLastError()<>expect Or ZentajiPayloadReturnValue()<>0 : ProcedureReturn 2 : EndIf
  zenPayloadActive=0
  ProcedureReturn 42
 EndIf
 If *zenPayloadCaller<>@ZentajiPayloadUnavailable : ProcedureReturn 7 : EndIf
 If rc<>1 Or ZentajiPayloadLastError()<>0 Or zenPayloadActive<>0 Or ZentajiPayloadReturnValue()<>$8877665544332211 : ProcedureReturn 3 : EndIf
 ; A second launch must receive the new zero argument, not the first argument.
 If ZentajiPayloadEnter(context,entry,0,stack,bytes)<>1 Or ZentajiPayloadReturnValue()<>$8877665544332211 : ProcedureReturn 4 : EndIf
 If PeekQ($281000)<>0 Or PeekQ($281008)<>2 : ProcedureReturn 5 : EndIf
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
    with tempfile.TemporaryDirectory(prefix='anvil-zen-payload-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode())
        run([cc,'--compile',src,'--entry-returns','-o',image])
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,assembly,_=B.pack(image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        owned=A.Asm();owned.assemble(assembly)
        assert meta['image_end']<0x280008
        count=0
        for scenario,rom in [(n,False) for n in range(19)]+[(20,False),(21,False),(0,True),(13,True)]:
            lines=['.org $280008','LIQ r16,$281000','ST64 r1,[r16]','LD64 r17,[r16+8]','ADDI r17,r17,1','ST64 r17,[r16+8]']
            # Validate every promised entry register and FP mode before clobbering it.
            for r in range(2,16):lines+=['BNEI r%d,0,payload_bad'%r]
            lines+=['LIQ r17,$2F0000','BNE r255,r17,payload_bad','MFCR r17,STATUS','BNEI r17,0,payload_bad','MFCR r17,FPCR','BNEI r17,0,payload_bad','MFCR r17,FPSR','BNEI r17,0,payload_bad']
            if scenario==13:
                lines+=['OR r128,r254,r0','LIQ r1,$%X'%meta['context'],'LIQ r2,$280008','LIQ r3,$DEADBEEF','LIQ r4,$2F0000','LI r5,16384','LIQ r16,$%X'%ref.sym['ZPROC_ZENTAJIPAYLOADENTER'],'CALLR r16,r254','BNEI r1,0,payload_bad','OR r254,r128,r0']
            for r in range(128,254):lines+=['LIQ r%d,$%X'%(r,0xCAFE00000000+r)]
            lines+=['LIQ r16,$282000']
            for v in range(32,64):lines+=['VLD v%d,r16,r0,0,0,7,0'%v]
            lines+=['LI r17,-1']
            for k in range(1,8):lines+=['KMOV r%d,r17,0'%k]
            lines+=['LIQ r17,$283000','MTCR r0,r17,EVEC','LI r17,3','MTCR r0,r17,FPCR','LI r17,31','MTCR r0,r17,FPSR','LI r255,3','LIQ r1,$8877665544332211']
            if scenario==20:lines+=['LI r17,1','MTCR r0,r17,PROT']
            if scenario==21:lines+=['LI r17,16','MTCR r0,r17,STATUS']
            lines+=['JR r254','payload_bad:','LI r1,$BAD','HALT r1']
            payload=A.Asm();address,code=payload.assemble('\n'.join(lines)+'\n')
            files=[['anvil.zex',bytearray(wrapped),True]] if rom else []
            m=I.Machine(ram_size=8<<20,cores=2,hostfiles=files,display_modes=[(1,1,60000)])
            if rom:m.power_on(0,0)
            else:m.load_image(wrapped)
            # Avoid the ROM memory-count probe at each 64KB boundary.
            m.ram[address:address+len(code)]=code;m.ram[0x282000:0x282040]=bytes(range(64));struct.pack_into('<Q',m.ram,0x300008,scenario)
            # The protection refusal is exercised with a real all-RWX page table.
            m.ram[0x380040:0x380040+2048]=bytes([7])*2048
            c=m.cores[0];c.cr[I.CR['PTBASE']]=0x380040;c.cr[I.CR['PTPAGES']]=2048
            c.cr[I.CR['FPCR']]=2;c.cr[I.CR['FPSR']]=9
            for n in range(32,64):c.v[n]=int.from_bytes(bytes((n+j)&255 for j in range(64)),'little')
            for n in range(1,8):c.k[n]=n*0x11223344556677
            assert not L.capture(m,str(td))
            snapshots=[];arguments=[];pending=None;original=m.step
            def observe(core):
                nonlocal pending
                if core.pc==address:
                    arguments.append(core.r[1])
                    assert core.r[2:16]==[0]*14 and core.r[255]==0x2F0000
                    assert core.cr[I.CR['STATUS']]==0 and core.cr[I.CR['PROT']]==0
                    assert core.cr[I.CR['FPCR']]==0 and core.cr[I.CR['FPSR']]==0
                if core.pc==owned.sym['ANVIL_ZEN_PAYLOAD_CALL']:
                    assert pending is None
                    pending=(core.r[254],list(core.r[128:256]),list(core.v[32:]),list(core.k),core.cr[I.CR['FPCR']],core.cr[I.CR['FPSR']])
                if pending and core.pc==pending[0]:
                    assert list(core.r[128:256])==pending[1],('kept scalar/SP/link',scenario)
                    assert list(core.v[32:])==pending[2] and list(core.k)==pending[3],('vector/mask',scenario)
                    assert core.cr[I.CR['FPCR']]==pending[4] and core.cr[I.CR['FPSR']]==pending[5]
                    assert core.cr[I.CR['STATUS']]==0 and core.cr[I.CR['EVEC']]==meta['vectors']
                    assert core.r[1]==0x8877665544332211
                    snapshots.append(pending);pending=None
                original(core)
            m.step=observe
            out=run([L.EXE,td/'machine.txt','--max','1000000','--ram',td/'final.bin']);m.run(1000000)
            want=0x5A02 if scenario==20 else 0x5A01 if scenario==21 else 42
            assert c.state=='HALTED' and c.exit==want,(scenario,rom,c.state,c.exit,bytes(m.serial[0].out))
            assert (td/'final.bin').read_bytes()==m.ram
            state=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            assert m.cores[1].state=='PARKED'
            calls=struct.unpack_from('<Q',m.ram,0x281008)[0]
            if scenario in (0,13):assert len(snapshots)==2 and pending is None and calls==2 and arguments==[0x1122334455667788,0]
            elif scenario>=20:assert not snapshots and pending is not None and calls==1 and c.r[255]==3 and arguments==[0x1122334455667788]
            else:assert not snapshots and pending is None and calls==0 and not arguments
            count+=1
            print('PASS payload boundary scenario=%d ROM=%s: native/twin full state/RAM, calls=%d'%(scenario,rom,calls),flush=True)
        print('PASS %d actual CPU-boundary cases: entry arguments/stack/FP state, complete kept-register restoration despite foreign SP/vectors, repeat/nested entry, refusal before jump and unsafe-return fail-stop'%count)


if __name__=='__main__':main()
