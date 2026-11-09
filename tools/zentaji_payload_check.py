"""Exercise the actual Zentaji CPU call boundary, independently of board policy."""
import argparse
import hashlib
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
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-zen-payload-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode())
        run([cc,'--compile',src,'--entry-returns','-o',image])
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        wrapped,meta,assembly,_=B.pack(image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        owned=A.Asm();owned.assemble(assembly)
        assert meta['image_end']<0x280008
        app_source=td/'app.zentaji';app=td/'app.zex'
        app_source.write_text('Procedure.q Main(argument.q)\nPokeQ($281000,argument)\nPokeQ($281008,PeekQ($281008)+1)\nProcedureReturn $8877665544332211\nEndProcedure\n')
        run([cc,'--compile',app_source,'--load-addr','0x280008','--stack-addr','0x2F0000','--entry-returns','-o',app])
        compiled=app.read_bytes();ar=A.Asm();load,body=ar.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'))
        assert compiled==zexpack.header(load,load,body,stack=0x2F0000)+body and load==0x280008 and load+len(body)<0x281000
        pmf=Path(str(app)+'.pmf').read_bytes()
        assert pmf[:8]==b'PMFBOOT\0' and struct.unpack_from('<II',pmf,8)==(2,128)
        assert struct.unpack_from('<5Q',pmf,16)==(load,load,len(body),load+len(body),0)
        assert struct.unpack_from('<II',pmf,56)==(1,0) and pmf[64:96]==hashlib.sha256(body).digest()
        assert struct.unpack_from('<IIQ',pmf,96)==(2,1,0x2F0000) and not any(pmf[112:128]) and pmf[128:]==body
        count=0
        for scenario,rom in [(n,False) for n in range(19)]+[(20,False),(21,False),(0,True),(13,True),(22,False),(22,True)]:
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
            if scenario==22:address,code=load,pmf[128:]
            files=[['anvil.zex',bytearray(wrapped),True]] if rom else []
            m=I.Fixture(ram_size=8<<20,cores=2,hostfiles=files,display_modes=[(1,1,60000)])
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
            fixture=m
            out=run([L.EXE,td/'machine.txt','--max','1000000','--ram',td/'final.bin'])
            m=runner.execute(fixture,1000000,td);c=m.cores[0]
            snapshots=[];arguments=[];pending=None
            commands=['break 0 $%X'%owned.sym['ANVIL_ZEN_PAYLOAD_CALL'],'continue 1000000']
            boundary=runner.debug_snapshot(fixture,commands,td).core()
            for launch in range(2):
                if boundary.state=='HALTED':break
                assert boundary.pc==owned.sym['ANVIL_ZEN_PAYLOAD_CALL']
                pending=(boundary.r[254],list(boundary.r[128:256]),list(boundary.v[32:]),list(boundary.k),boundary.cr[I.CR['FPCR']],boundary.cr[I.CR['FPSR']])
                commands+=['clear','break 0 $%X'%address,'continue 1000000']
                entry=runner.debug_snapshot(fixture,commands,td).core()
                assert entry.pc==address and entry.state=='RUNNING'
                arguments.append(entry.r[1])
                assert entry.r[2:16]==[0]*14 and entry.r[255]==0x2F0000
                assert entry.cr[I.CR['STATUS']]==0 and entry.cr[I.CR['PROT']]==0
                assert entry.cr[I.CR['FPCR']]==0 and entry.cr[I.CR['FPSR']]==0
                commands+=['clear','break 0 $%X'%pending[0],'continue 1000000']
                returned=runner.debug_snapshot(fixture,commands,td).core()
                if returned.state=='HALTED':break
                assert returned.pc==pending[0]
                assert returned.r[128:256]==pending[1],('kept scalar/SP/link',scenario)
                assert returned.v[32:]==pending[2] and returned.k==pending[3],('vector/mask',scenario)
                assert returned.cr[I.CR['FPCR']]==pending[4] and returned.cr[I.CR['FPSR']]==pending[5]
                assert returned.cr[I.CR['STATUS']]==0 and returned.cr[I.CR['EVEC']]==meta['vectors']
                assert returned.r[1]==0x8877665544332211
                snapshots.append(pending);pending=None
                if launch==0:
                    commands+=['clear','break 0 $%X'%owned.sym['ANVIL_ZEN_PAYLOAD_CALL'],'continue 1000000']
                    boundary=runner.debug_snapshot(fixture,commands,td).core()
            want=0x5A02 if scenario==20 else 0x5A01 if scenario==21 else 42
            assert c.state=='HALTED' and c.exit==want,(scenario,rom,c.state,c.exit,bytes(m.serial[0].out))
            assert (td/'final.bin').read_bytes()==m.ram
            I.assert_same_state(out,m)
            assert m.cores[1].state=='PARKED'
            calls=struct.unpack_from('<Q',m.ram,0x281008)[0]
            if scenario in (0,13,22):assert len(snapshots)==2 and pending is None and calls==2 and arguments==[0x1122334455667788,0]
            elif scenario in (20,21):assert not snapshots and pending is not None and calls==1 and c.r[255]==3 and arguments==[0x1122334455667788]
            else:assert not snapshots and pending is None and calls==0 and not arguments
            count+=1
            if scenario==22:
                assert bytes(m.ram[load:load+len(body)])==body
            print('PASS payload boundary scenario=%d ROM=%s: native full state/RAM, calls=%d'%(scenario,rom,calls),flush=True)
        print('PASS real placed compiler PMF body through owned CPU boundary twice, direct and ROM: args/results/caller stack restored; harness placement, not shared-loader integration')
        print('PASS %d actual CPU-boundary cases: entry arguments/stack/FP state, complete kept-register restoration despite foreign SP/vectors, repeat/nested entry, refusal before jump and unsafe-return fail-stop'%count)


if __name__=='__main__':main()
