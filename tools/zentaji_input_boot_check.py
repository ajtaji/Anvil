"""Real ROM -> counted Anvil -> separately compiled slot39 input application."""
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
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]
APP=r'''XIncludeFile "Anvil/Hal/input_service_api.pbi"
Procedure.q Main(table.i)
 Protected fn.i,handle.i,calls.i,i.i,rc.i,kind.i,total.i,texts.i,physical.i,pointer.i,wheel.i,wantX.i,wantY.i,wantWheel.i,n.i
 If PeekL(table)<>$53564E41 Or PeekL(table+4)<>1 Or PeekL(table+8)<15 Or PeekL(table+12)<208 : ProcedureReturn $BAD01 : EndIf
 fn=PeekQ(table+16+#NUI_SERVICE_SLOT*8)
 If CallFunctionFast(fn,#NUI_QUERY,0,$600800,SizeOf(NativeInputApi))<>0 : ProcedureReturn $BAD02 : EndIf
 If PeekL($600800)<>#NUI_MAGIC Or PeekL($600804)<>1 Or PeekL($60080C)<>32 Or PeekQ($600810)<>3 Or PeekQ($600818)=0 : ProcedureReturn $BAD03 : EndIf
 fn=PeekQ($600818)
 PokeQ($600840,3)
 handle=CallFunctionFast(fn,#NUI_OPEN,0,$600840,SizeOf(NativeInputOpenRequest))
 calls=PeekQ($600000)+1
 If handle<>calls Or PeekQ($600848)<>3 Or PeekQ($600850)<>320 Or PeekQ($600858)<>160 Or PeekQ($600860)<1 : ProcedureReturn $BAD04 : EndIf
 If calls>1
  If CallFunctionFast(fn,#NUI_POLL,handle-1,$600900,48)<>#NUI_ERR_STATE : ProcedureReturn $BAD05 : EndIf
 EndIf
 PokeQ($600000,calls) : PokeQ($600010,calls)
 wantX=0 : wantY=159 : wantWheel=4
 If calls=2 : wantX=12 : wantY=25 : wantWheel=3 : EndIf
 For i=1 To 10000
  rc=CallFunctionFast(fn,#NUI_POLL,handle,$600900,48)
  If rc<0 : ProcedureReturn $BAD10 : EndIf
  If rc=1
   If PeekL($600928)<>PeekQ($600860) : ProcedureReturn $BAD11 : EndIf
   If total>=32 : ProcedureReturn $BAD12 : EndIf
   For n=0 To 40 Step 8 : PokeQ($610000+(calls-1)*8192+total*48+n,PeekQ($600900+n)) : Next
   total=total+1 : kind=PeekL($600900)
   If kind=#AIE_TEXT
    If PeekL($600908)<>113 : ProcedureReturn $BAD13 : EndIf
    texts=texts+1
   ElseIf kind=#NUI_PHYSICAL_KEY
    physical=physical+1
   ElseIf kind=#NUI_POINTER And PeekL($60091C)=0
    If PeekL($600910)<>wantX Or PeekL($600914)<>wantY Or PeekL($600918)<>1 : ProcedureReturn $BAD14 : EndIf
    pointer=pointer+1
   ElseIf kind=#NUI_WHEEL
    If PeekL($600910)<>wantX Or PeekL($600914)<>wantY Or PeekL($60091C)<>wantWheel : ProcedureReturn $BAD15 : EndIf
    wheel=wheel+1
   EndIf
  EndIf
  If texts=2 And physical=3 And pointer=1 And wheel=1 : Break : EndIf
 Next
 If texts<>2 Or physical<>3 Or pointer<>1 Or wheel<>1 : ProcedureReturn $BAD16 : EndIf
 PokeQ($600100+(calls-1)*64,texts) : PokeQ($600108+(calls-1)*64,physical)
 PokeQ($600110+(calls-1)*64,pointer) : PokeQ($600118+(calls-1)*64,wheel)
 PokeQ($600120+(calls-1)*64,handle) : PokeQ($600128+(calls-1)*64,total)
 DAMAGE
 ; Deliberately return with NUI open, a key held and a mouse button held.
 ; The resident owner must close/fence this scope before the prompt resumes.
 ProcedureReturn $1122334455667788
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--case',choices=('repeat-open-return','foreign-capture','foreign-input-irq'));a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    image=(ROOT/'build/zentaji/anvil.zex').read_bytes();meta=json.loads((ROOT/'build/zentaji/anvil.zex.boot.json').read_text(encoding='utf-8'));mapping=json.loads((ROOT/'build/zentaji/anvil.zex.zmap').read_text(encoding='utf-8'))
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']==mapping['image']
    for row in mapping['sources']:
        p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
        assert p.resolve().is_relative_to(ROOT) and hashlib.sha256(p.read_bytes().replace(b'\r',b'')).hexdigest()==row['sha256'],p
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-input-boot-') as tmp:
        td=Path(tmp)
        for name,damage,calls,exit_code in [('repeat-open-return','',2,0),('foreign-capture','PokeQ($FFFF0000000A00B0,1)',1,0x5B06),('foreign-input-irq','PokeQ($FFFF0000000A0020,1)',1,0x5B06)]:
            if a.case and a.case!=name:continue
            src=td/'app.zentaji';app=td/'app.zex';src.write_text(APP.replace('DAMAGE',damage),encoding='utf-8')
            run([cc,'--compile',src,'--load-addr','0x280008','--stack-addr','0x2F0000','--entry-returns','--wants-services','-o',app])
            ref=A.Asm();org,body=ref.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'))
            assert app.read_bytes()==zexpack.header(org,org,body,stack=0x2F0000)+body
            pmf=Path(str(app)+'.pmf').read_bytes();assert pmf[128:]==body and pmf[64:96]==hashlib.sha256(body).digest()
            print('Checking published input '+name+': independently assembled %d-byte application body'%len(body),flush=True)
            medium=E.build(4096);E.seed_file(medium,pmf,'APP.PMF');boot=zexpack.disk_image(image)
            medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
            m=I.Machine(ram_size=8<<20,cores=2,disks={15:(bytearray(medium),False)},display_modes=[(320,160,60000),(640,480,60000)]);m.power_on(1,15)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text(encoding='utf-8').replace('disk-memory ','disk '),encoding='utf-8')
            commands=['boot APP.PMF']*calls+(['halt'] if exit_code==0 else []);scheduled=[];script=[];seen=set();last_verification=0
            def operator(core):
                nonlocal last_verification
                tick=max(m.time,core.cr[I.CR['CYCLE']])+100
                verification=bytes(m.serial[0].out).count(b'Verifying ')
                if verification>last_verification:
                    last_verification=verification
                    print('Input proof: real PMF verification %d started'%verification,flush=True)
                ready=struct.unpack_from('<Q',m.ram,0x600010)[0]
                if ready>0 and ready not in seen:
                    seen.add(ready)
                    print('Input proof: application session %d entered'%ready,flush=True)
                    def feed(at,kind,*fields):
                        m.input_feed(at,kind,*fields);script.append((at,kind,fields))
                    if ready==2:
                        feed(tick,'key',4,1,0,1,97);feed(tick,'key',4,0,0,0,0)
                        feed(tick,'mouse',1,100,16,0)
                    for fields in [(20,1,0,0,113),(20,1,0,1,113),(20,0,0,0,0),(4,1,0,0,0)]:feed(tick,'key',*fields)
                    feed(tick if ready==1 else tick+100000,'mouse',-2 if ready==1 else 12,200 if ready==1 else 25,17,4 if ready==1 else 3)
                if len(scheduled)<len(commands) and bytes(m.serial[0].out).count(b'pmf> ')>len(scheduled):
                    assert m.input.mctrl==0 and m.input.irq_enable==0
                    line=[(tick,b) for b in (commands[len(scheduled)]+'\r').encode()];scheduled.append(line);m.serial[0].incoming.extend(line)
            m.on_slice=operator;m.run(100000000);m.on_slice=None;c=m.cores[0];output=bytes(m.serial[0].out)
            assert c.state=='HALTED' and c.exit==exit_code,(name,c.state,c.exit,output[-3000:])
            assert struct.unpack_from('<Q',m.ram,0x600000)[0]==calls and seen==set(range(1,calls+1)),name
            for call in range(calls):
                counts=struct.unpack_from('<6q',m.ram,0x600100+call*64)
                assert counts[:5]==(2,3,1,1,call+1) and counts[5]==7+call,(name,counts)
                trace=[struct.unpack_from('<8iq2i',m.ram,0x610000+call*8192+i*48) for i in range(counts[5])]
                assert [r[2] for r in trace if r[0]==1]==[113,113],(name,trace)
                assert [(r[2],r[7]) for r in trace if r[0]==7]==[(20,1),(20,0),(4,1)],(name,trace)
                assert all(r[:8]==(1,1,113,0,-1,-1,0,0) for r in trace if r[0]==1)
                assert all(r[1]==1 and r[3:7]==(0,-1,-1,0) for r in trace if r[0]==7)
                assert [(r[4],r[5],r[6],r[7]) for r in trace if r[0]==5]==([(0,159,1,0)] if call==0 else [(1,100,0,4),(12,25,1,0)])
                assert [(r[4],r[5],r[6],r[7]) for r in trace if r[0]==6]==([(0,159,1,4)] if call==0 else [(12,25,1,3)])
                assert all(r[9]>0 and r[10]==0 for r in trace)
            if exit_code==0:
                assert len(scheduled)==3 and output.count(b'The payload returned, r1 = $1122334455667788')==2 and b'Anvil stopped.' in output
                assert b'? this monitor' not in output and m.input.queue==[]
            else:
                assert output.count(b'pmf> ')==1 and b'Payload return failed (0x5B06)' in output and b'The payload returned' not in output
            assert bytes(m.disks[15].image)==bytes(medium)
            assert E.root_files(bytes(m.disks[15].image))=={'APP.PMF':pmf}
            with cfg.open('a',encoding='utf-8') as stream:
                for line in scheduled:
                    for tick,b in line:stream.write('serial 0 $%X %02X\n'%(tick,b))
                for tick,kind,fields in script:stream.write('%s $%X %s\n'%(kind,tick,' '.join(str(x) for x in fields)))
            out=run([L.EXE,cfg,'--max','100000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram
            state=next(line[6:] for line in out.splitlines() if line.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            assert (td/'disk15.img').read_bytes()==bytes(medium) and m.cores[1].state=='PARKED'
            for row in mapping['code']:
                pc=int(row['pc'],16);n=row['size'];assert m.ram[pc:pc+n]==image[64+pc-meta['load']:64+pc-meta['load']+n]
            print('PASS published native input '+name+': real ROM/PMF/SHA/slot39 app, keyboard/mouse/repeat/held fences, calls=%d exit=%X, exact native/twin state/RAM and independent immutable exFAT/monitor oracle'%(calls,exit_code),flush=True)


if __name__=='__main__':main()
