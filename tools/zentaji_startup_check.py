"""Actual Zentaji supervisor startup/vector ownership and ROM boot proof."""
import argparse
import json
import hashlib
from pathlib import Path
import os
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
ProcedureNaked.i ProbeSp()
 ASM
  OR r1,r255,r0
  JR r254
 EndASM
EndProcedure
ProcedureNaked.i ProbeEvec()
 ASM
  MFCR r1,EVEC
  JR r254
 EndASM
EndProcedure
ProcedureNaked ProbeWait()
 ASM
  WFI
  JR r254
 EndASM
EndProcedure
ProcedureNaked TestFault()
 ASM
  LI r255,3
  BRK $1234
  HALT r0
 EndASM
EndProcedure
Procedure.i Main(table.i,source.i,context.i,zero.i)
 Protected sp.i,saved.i,call.i
 If table<>$FFFF000000010000 Or source<>PeekQ(context+#ZEN_BOOT_SOURCE) Or zero<>0 Or ZentajiBootContextValid(context)<>1 : ProcedureReturn 1 : EndIf
 If ProbeEvec()<>PeekQ(context+#ZEN_BOOT_VECTORS) : ProcedureReturn 2 : EndIf
 sp=ProbeSp()
 If sp<PeekQ(context+#ZEN_BOOT_STACK_BOTTOM) Or sp>=PeekQ(context+#ZEN_BOOT_STACK_TOP) : ProcedureReturn 3 : EndIf
 If ZentajiBootContextValid(context+1)<>0 Or ZentajiBootContextValid(-1)<>0 : ProcedureReturn 4 : EndIf
 saved=PeekQ(context+#ZEN_BOOT_VECTORS)
 PokeQ(context+#ZEN_BOOT_VECTORS,$7FFFFFFFFFFFF000)
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 5 : EndIf
 PokeQ(context+#ZEN_BOOT_VECTORS,saved)
 call=PeekQ(context+#ZEN_BOOT_PAYLOAD_CALL)
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,0)
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 6 : EndIf
 PokeQ(context+8,1)
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 7 : EndIf
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,call)
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 8 : EndIf
 PokeQ(context+8,2)
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 9 : EndIf
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,call+1)
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 10 : EndIf
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,PeekQ(context+#ZEN_BOOT_VECTORS))
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 11 : EndIf
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,context)
 If ZentajiBootContextValid(context)<>0 : ProcedureReturn 12 : EndIf
 PokeQ(context+#ZEN_BOOT_PAYLOAD_CALL,call)
 FAULT
 ProcedureReturn 42
EndProcedure
'''
FAULTS={
 'normal':'',
 'bad-sp-break':'TestFault()',
 'tx-busy-fault':'PokeQ($FFFF000000100060,1)\nPokeQ($FFFF000000100068,$90000)\nPokeQ($FFFF000000100070,8192)\nTestFault()',
 'nmi':'PokeQ($FFFF00000004F050,0)',
 'watchdog':'PokeQ($FFFF000000050808,1000000)\nPokeQ($FFFF000000050800,1)\nProbeWait()',
}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT));passed=0
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-startup-proof-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';compiled=td/'probe.zex'
        variants={}
        variants_raw={}
        variants_maps={}
        for name,fault in FAULTS.items():
            src=td/(name+'.zentaji');compiled=td/(name+'.zex')
            src.write_text(SOURCE.replace(' FAULT',' '+fault),encoding='utf-8');run([cc,'--compile',src,'-o',compiled])
            raw=compiled.read_bytes();variants_raw[name]=raw;variants_maps[name]=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig'))
            wrapped,meta,asm,mapping=B.pack(raw,zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=variants_maps[name])
            assert mapping['image']==hashlib.sha256(wrapped).hexdigest()
            assert [r for r in mapping['code'] if int(r['pc'],16)<meta['vectors']]==variants_maps[name]['code']
            startup_rows=[r for r in mapping['code'] if int(r['pc'],16)>=meta['vectors']]
            assert startup_rows and all(Path(r['source'])==B.STARTUP for r in startup_rows)
            assert any(int(r['pc'],16)==meta['entry'] for r in startup_rows)
            ref=A.Asm();org,data=ref.assemble(asm)
            assert wrapped==zexpack.header(org,meta['entry'],data)+data,name
            assert wrapped[64:64+len(raw)-64]==raw[64:],name
            import opcodes as Z
            for cause in range(64):
                at=meta['vectors']-org+cause*64
                assert int.from_bytes(data[at:at+8],'little')==Z.encode('LI',rd=200,imm32=cause)
                target=meta['vectors']+cause*64+8+int.from_bytes(data[at+12:at+16],'little',signed=True)*8
                assert target==ref.sym['ANVIL_ZEN_FAULT'] and not any(data[at+16:at+64])
            variants[name]=(wrapped,meta,ref)
        image,meta,ref=variants['normal']
        assert meta['context_version']==2 and meta['payload_call']==ref.sym['ANVIL_ZEN_PAYLOAD_CALL']
        def direct(image,ram=2<<20,cores=2):
            m=I.Machine(ram_size=ram,cores=cores,display_modes=[(16,16,60000)]);m.load_image(image)
            m.cores[0].r[255]=0xDEADBEF0
            return m
        def check(name,m,exit_code=42,serial=None,steps=1000000,active=0):
            nonlocal passed
            assert not L.capture(m,str(td)),name
            native=run([L.EXE,td/'machine.txt','--max',str(steps),'--ram',td/'final.bin']);m.run(steps)
            states=[s for s in native.splitlines() if s.startswith('STATE ')]
            assert states[0][6:].split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],name
            assert (td/'final.bin').read_bytes()==m.ram,name
            c=m.cores[active];assert c.state=='HALTED' and c.exit==exit_code,(name,c.state,c.exit,bytes(m.serial[0].out))
            serial_bytes=bytes(m.serial[0].out)
            native_serial=[s.split(' ',1)[1] for s in native.splitlines() if s.startswith('SERIAL0 ')]
            assert (native_serial[0] if native_serial else '')==serial_bytes.hex().upper(),name
            if serial is not None:assert serial_bytes==serial,(name,serial_bytes,serial)
            assert all(c.state=='PARKED' for i,c in enumerate(m.cores) if i!=active),name
            passed+=1
            return c
        for ram in [2<<20,(2<<20)+7,8<<20]:
            m=direct(image,ram);c=check('direct-ram-'+str(ram),m,serial=b'')
            ctx=meta['context'];q=lambda off:int.from_bytes(m.ram[ctx+off:ctx+off+8],'little')
            assert [q(x) for x in (0,8,16,24,32,40,48,56,64,72,80,88,96,104,112,120)]==[0x4E455A4C49564E41,2,128,I.DEV+0x10000,2,ram,0xDEADBEF0,((ram&-16)-1048576)-65536,(ram&-16)-1048576,meta['vectors'],meta['compiled_entry'],0,meta['load'],meta['image_end'],65536,ref.sym['ANVIL_ZEN_PAYLOAD_CALL']]
            assert c.cr[I.CR['EVEC']]==meta['vectors'] and c.r[255]==(ram&-16)-1048576
        for name,reason,mutate,ram in [
            ('wrong-table',1,lambda m:setattr(m.cores[0],'r',[0 if i==1 else x for i,x in enumerate(m.cores[0].r)]),2<<20),
            ('wrong-status',2,lambda m:m.cores[0].cr.__setitem__(I.CR['STATUS'],1),2<<20),
            ('wrong-source',5,lambda m:m.cores[0].r.__setitem__(2,3),2<<20),
            ('small-ram',6,lambda m:None,1<<20),
        ]:
            m=direct(image,ram);mutate(m);c=check(name,m,reason,f'Anvil startup refused code={reason:016X}\r\n'.encode())
            assert c.cr[I.CR['EVEC']]==I.DEV+0xF000 and c.r[255]==0xDEADBEF0,name
        m=direct(image);m.cores[0].state='PARKED';c=m.cores[1];c.state='RUNNING';c.pc=meta['entry'];c.r[1]=I.DEV+0x10000;c.r[2]=2;c.r[255]=0xDEADBEF0
        check('secondary-entry-refused',m,3,b'Anvil startup refused code=0000000000000003\r\n',active=1)
        m=direct(image);c=m.cores[0];pages=len(m.ram)//4096;base=0x180000
        m.ram[base:base+pages]=bytes([7])*pages
        c.cr[I.CR['PTBASE']]=base;c.cr[I.CR['PTPAGES']]=pages;c.cr[I.CR['PROT']]=1
        check('protected-entry-refused',m,4,b'Anvil startup refused code=0000000000000004\r\n')
        bss_raw=bytearray(variants_raw['normal']);struct.pack_into('<Q',bss_raw,32,129)
        bss_image,bm,ba,bmap=B.pack(bytes(bss_raw),zt/('zasm.exe' if os.name=='nt' else 'zasm'),16384)
        m=I.Machine(ram_size=2<<20,cores=2,display_modes=[(16,16,60000)]);m.ram[:]=bytes([0xA5])*len(m.ram);m.load_image(bss_image)
        check('original-bss-and-min-stack',m,serial=b'')
        at=struct.unpack_from('<Q',bss_raw,16)[0]+len(bss_raw)-64
        assert not any(m.ram[at:at+129])
        returns_src=td/'returns.zentaji';returns_image=td/'returns.zex'
        returns_src.write_text(SOURCE.replace(' FAULT',''),encoding='utf-8')
        run([cc,'--compile',returns_src,'--entry-returns','-o',returns_image])
        returning,rm,ra,rmap=B.pack(returns_image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(returns_image)+'.zmap').read_text(encoding='utf-8-sig')))
        rr=A.Asm();rr.assemble(ra);m=direct(returning);c=check('callable-entry-return',m,serial=b'')
        assert c.r[254]==rr.sym['ANVIL_ZEN_RETURNED'] and c.r[255]==(2<<20)-1048576
        img,md,r=variants['tx-busy-fault'];m=direct(img)
        check('TX-block-busy-fault',m,267,b'')
        assert m.serial[0].txdropped==0 and m.cores[0].r[255]==3
        raw=compiled.read_bytes()
        # Preserve original BSS addresses as zero bytes in the wrapped payload.
        # Malformed cases are rejected before assembly.
        for off,value in [(48,1),(60,1),(8,meta['entry']+1),(24,0)]:
            damaged=bytearray(image);struct.pack_into('<Q' if off!=60 else '<I',damaged,off,value)
            try:B.inspect(damaged)
            except ValueError:pass
            else:raise AssertionError(('accepted invalid header',off))
        damaged=bytearray(image);damaged[64]^=1
        try:B.inspect(damaged)
        except ValueError:pass
        else:raise AssertionError('accepted bad CRC')
        overlap,om,oa,omap=B.pack(variants_raw['normal'],zt/'zasm.exe',1048576)
        m=direct(overlap);check('stack-image-overlap',m,7,b'Anvil startup refused code=0000000000000007\r\n')
        for name,cause in [('bad-sp-break',11),('nmi',13),('watchdog',14)]:
            img,md,r=variants[name];m=direct(img);m.cores[0].cr[I.CR['EPC']]=0xAA55;m.cores[0].cr[I.CR['EINFO']]=0xBB66
            c=check(name,m,256+cause)
            pc=c.cr[I.CR['NEPC' if cause in (13,14,15) else 'EPC']];info=c.cr[I.CR['NEINFO' if cause in (13,14,15) else 'EINFO']]
            assert bytes(m.serial[0].out)==f'Anvil exception cause={cause:016X} pc={pc:016X} info={info:016X}\r\n'.encode(),name
            assert c.cr[I.CR['EVEC']]==md['vectors'],name
            if name=='bad-sp-break':assert c.r[255]==3 and info==0x1234
            if name=='nmi':assert info==1 and c.cr[I.CR['EPC']]==0xAA55
        for disk in [False,True]:
            files=[] if disk else [['anvil.zex',bytearray(image),False]]
            disks={0:(bytearray(zexpack.disk_image(image)),True)} if disk else None
            m=I.Machine(ram_size=2<<20,cores=2,hostfiles=files,disks=disks,display_modes=[(16,16,60000)]);m.power_on(int(disk),0)
            c=check('actual-ROM-'+('disk' if disk else 'hostfile'),m,serial=b'Zentaji boot ROM v1\r\nboot: starting the image\r\n')
            assert c.cr[I.CR['EVEC']]==meta['vectors']
        from unittest.mock import patch
        output=td/'published.zex';raw=variants_raw['normal'];compiled=td/'normal.zex'
        run([sys.executable,B.__file__,compiled,output,'--zasm',zt/('zasm.exe' if os.name=='nt' else 'zasm')])
        assert output.read_bytes()==image
        assert json.loads(Path(str(output)+'.boot.json').read_text())['image_sha256']==meta['image_sha256']
        existing={p:p.read_bytes() for p in [output,Path(str(output)+'.boot.json'),Path(str(output)+'.asm'),Path(str(output)+'.zmap')]}
        real_replace=os.replace;failed=False
        def fail_once(src,dst):
            nonlocal failed
            if Path(dst)==Path(str(output)+'.boot.json') and not failed:
                failed=True;raise OSError('planted publication failure')
            return real_replace(src,dst)
        try:
            with patch('os.replace',side_effect=fail_once):B.publish(output,b'new image',{'new':True},'new assembly',{'new':True})
        except OSError:pass
        else:raise AssertionError('planted publication failure escaped')
        assert failed and all(p.read_bytes()==v for p,v in existing.items())
        collision=td/'collision.asm';collision.write_bytes(raw)
        bad=subprocess.run([sys.executable,B.__file__,collision,td/'collision','--zasm',zt/('zasm.exe' if os.name=='nt' else 'zasm')],capture_output=True,text=True)
        assert bad.returncode and 'sidecars must differ' in bad.stderr and collision.read_bytes()==raw
        bad_map=Path(str(compiled)+'.zmap');saved_map=bad_map.read_bytes()
        bad=subprocess.run([sys.executable,B.__file__,compiled,bad_map,'--zasm',zt/('zasm.exe' if os.name=='nt' else 'zasm')],capture_output=True,text=True)
        assert bad.returncode and bad_map.read_bytes()==saved_map
        for change in ['image','hash','extent','type']:
            mapping=json.loads(saved_map)
            if change=='image':mapping['image']='0'*64
            elif change=='hash':mapping['sources'][0]['sha256']='bad'
            elif change=='extent':mapping['code'][0]['pc']=f'{meta["vectors"]:016X}'
            else:mapping['code'][0]['line']=True
            bad_map.write_text(json.dumps(mapping),encoding='utf-8')
            bad=subprocess.run([sys.executable,B.__file__,compiled,output,'--zasm',zt/('zasm.exe' if os.name=='nt' else 'zasm')],capture_output=True,text=True)
            assert bad.returncode and all(p.read_bytes()==v for p,v in existing.items()),(change,bad.stdout,bad.stderr)
        bad_map.write_bytes(saved_map)
        print('PASS executable/map/metadata/assembly publication transaction rollback and compiler-input sidecar collision refusal')
        # The production native debugger validates/loads the merged map and steps
        # from real startup assembly to the original high-level source.
        merged=json.loads(Path(str(output)+'.zmap').read_text())
        cfg=td/'debug-machine.txt';cfg.write_text('machine $200000 1 1000 0\nimage '+output.as_posix()+'\n',encoding='utf-8')
        main_line=next(i for i,l in enumerate(SOURCE.splitlines(),1) if l.startswith('Procedure.i Main('))
        pc=next(int(r['pc'],16) for r in merged['code'] if Path(r['source'])==td/'normal.zentaji' and r['line']==main_line)
        commands=td/'debug.txt';commands.write_text(f'break 0 ${meta["entry"]:X}\ncontinue\nclear\nline 0\nbreak 0 ${pc:X}\ncontinue\nclear\nline 0\ncontinue\n',encoding='utf-8')
        debug=run([L.EXE,cfg,'--debug',commands,'--debug-image',output])
        assert 'DBG source-line ' in debug and 'exit=2A ' in debug,debug
        assert f'pc=${pc:X}' in debug,debug
        print('PASS merged original-language/startup instruction maps and real native source break/step into the wrapped guest')
        import zentaji_prompt_check as P
        prompt_source='IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"\n'+P.SOURCE.replace('Procedure.i Main(scenario.i)','Procedure.i Main(table.i,source.i,context.i)\n Protected scenario.i=21\n If ZentajiBootContextValid(context)<>1 : ProcedureReturn 90 : EndIf')
        src=td/'prompt.zentaji';compiled=td/'prompt.zex'
        src.write_text(prompt_source,encoding='utf-8');run([cc,'--compile',src,'-o',compiled])
        prompt,pm,pa,pmap=B.pack(compiled.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(compiled)+'.zmap').read_text(encoding='utf-8-sig')))
        for disk in [False,True]:
            files=[] if disk else [['anvil-prompt.zex',bytearray(prompt),False]]
            disks={0:(bytearray(zexpack.disk_image(prompt)),True)} if disk else None
            m=I.Machine(ram_size=2<<20,cores=2,hostfiles=files,disks=disks,display_modes=[(16,16,60000)])
            m.power_on(int(disk),0);m.serial[0].incoming=[(400000000,b) for b in b'OK\r']
            c=check('ROM-shared-ReadLine-'+('disk' if disk else 'hostfile'),m,serial=b'Zentaji boot ROM v1\r\nboot: starting the image\r\npmf> OK\r\n',steps=4000000)
            assert c.cr[I.CR['EVEC']]==pm['vectors']
        print('PASS actual ROM -> owned startup -> full shared ReadLine, both host-file and disk: timed serial input, service/message activity and exact native/twin state/RAM/output; unrelated hardware providers remain counted adapters')
        print(f'PASS startup: {passed} real Forge/native/twin full-state/RAM cases; owned SP/EVEC/context, malformed handoff/overlap, damaged-SP BRK/NMI/watchdog reporting and actual ROM host-file/disk boot; independent assembly and header refusals')


if __name__=='__main__':main()
