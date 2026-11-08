"""Real ROM/PMF applications discover the text ABI; no fixed kernel addresses."""
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
APP=r'''XIncludeFile "Anvil/Hal/text_service_api.pbi"
Procedure.q Main(table.i)
 Protected dispatch.i,handle.i,calls.i,i.i,input.i
 Protected *fill.NativeTextFillRequest=$600180,*write.NativeTextWriteRequest=$6001C0
 Protected *cursor.NativeTextCursorRequest=$600200,*scroll.NativeTextScrollRequest=$600240
 If PeekL(table)<>$53564E41 Or PeekL(table+4)<>1 Or PeekL(table+8)<16 Or PeekL(table+12)<216 : ProcedureReturn $BAD01 : EndIf
 For i=0 To 215 : If PeekQ(table+16+i*8)=0 : ProcedureReturn $BAD02 : EndIf : Next
 calls=PeekQ($600000)+1 : PokeQ($600000,calls)
 If CallFunctionFast(PeekQ(table+16+208*8),#NTX_QUERY,0,$600100,SizeOf(NativeTextApi))<>0 : ProcedureReturn $BAD03 : EndIf
 If PeekL($600100)<>#NTX_MAGIC Or PeekL($600104)<>1 Or PeekL($60010C)<>40 Or PeekQ($600110)<>1 : ProcedureReturn $BAD04 : EndIf
 dispatch=PeekQ($600120)
 handle=CallFunctionFast(dispatch,#NTX_OPEN,0,$600140,SizeOf(NativeTextOpenRequest))
 If handle<>calls Or PeekQ($600140)<>40 Or PeekQ($600148)<>10 : ProcedureReturn $BAD05 : EndIf
 PokeQ($600280,3)
 input=CallFunctionFast(PeekQ(table+16+39*8),1,0,$600280,40)
 If input<>calls : ProcedureReturn $BAD06 : EndIf
 *fill\x=1 : *fill\y=1 : *fill\width=4 : *fill\height=3 : *fill\cell=$02010058
 If CallFunctionFast(dispatch,#NTX_FILL,handle,$600180,SizeOf(NativeTextFillRequest))<>0 : ProcedureReturn $BAD07 : EndIf
 PokeL($600300,$04030041) : PokeL($600304,$040300E9) : PokeL($600308,$04032500)
 *write\x=2 : *write\y=2 : *write\width=3 : *write\height=1 : *write\cells=$600300 : *write\stride=3
 If CallFunctionFast(dispatch,#NTX_WRITE,handle,$6001C0,SizeOf(NativeTextWriteRequest))<>0 : ProcedureReturn $BAD08 : EndIf
 *scroll\top=1 : *scroll\bottom=5 : *scroll\lines=1 : *scroll\cell=$0605002E
 If CallFunctionFast(dispatch,#NTX_SCROLL,handle,$600240,SizeOf(NativeTextScrollRequest))<>0 : ProcedureReturn $BAD09 : EndIf
 *cursor\x=4 : *cursor\y=2 : *cursor\style=2
 If CallFunctionFast(dispatch,#NTX_CURSOR,handle,$600200,SizeOf(NativeTextCursorRequest))<>0 : ProcedureReturn $BAD0A : EndIf
 PokeQ($600010,calls)
 If CallFunctionFast(dispatch,#NTX_PRESENT,handle,0,0)<>0 : ProcedureReturn $BAD0B : EndIf
 DAMAGE
 ; Return with both text and input sessions open. The monitor must retire them.
 ProcedureReturn $1122334455667788
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case',choices=('repeat-return','damaged-text-owner'));a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    artifact=ROOT/'build/zentaji/anvil.zex';image=artifact.read_bytes()
    meta=json.loads(Path(str(artifact)+'.boot.json').read_text(encoding='utf-8'))
    mapping=json.loads(Path(str(artifact)+'.zmap').read_text(encoding='utf-8'))
    assert hashlib.sha256(image).hexdigest()==meta['image_sha256']==mapping['image']
    for row in mapping['sources']:
        p=(ROOT/row['path']).resolve()
        assert p.is_relative_to(ROOT) and hashlib.sha256(p.read_bytes().replace(b'\r',b'')).hexdigest()==row['sha256'],p
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    expected=[0x70020]*400
    for y in range(1,4):expected[y*40+1:y*40+5]=[0x2010058]*4
    expected[82:85]=[0x4030041,0x40300e9,0x4032500]
    old=expected[:]
    for y in range(1,5):expected[y*40:(y+1)*40]=old[(y+1)*40:(y+2)*40] if y<4 else [0x605002e]*40
    with tempfile.TemporaryDirectory(prefix='anvil-text-boot-') as tmp:
        td=Path(tmp)
        for name,damage,calls,code in [('repeat-return','',2,0),('damaged-text-owner','PokeQ($FFFF0000001A0048,0)',1,0x5B05)]:
            if a.case and name!=a.case:continue
            src=td/'app.zentaji';app=td/'app.zex';src.write_text(APP.replace('DAMAGE',damage),encoding='utf-8')
            run([cc,'--compile',src,'--load-addr','0x280008','--stack-addr','0x2F0000','--entry-returns','--wants-services','-o',app])
            ref=A.Asm();org,body=ref.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'))
            assert app.read_bytes()==zexpack.header(org,org,body,stack=0x2F0000)+body
            pmf=Path(str(app)+'.pmf').read_bytes();assert pmf[128:]==body and pmf[64:96]==hashlib.sha256(body).digest()
            print('Checking published text '+name+': independently assembled %d-byte app body'%len(body),flush=True)
            medium=E.build(4096);E.seed_file(medium,pmf,'APP.PMF');boot=zexpack.disk_image(image)
            medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
            m=I.Machine(ram_size=8<<20,cores=2,disks={15:(bytearray(medium),False)},display_modes=[(320,160,60000),(640,480,60000)]);m.power_on(1,15)
            assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text(encoding='utf-8').replace('disk-memory ','disk '),encoding='utf-8')
            commands=['boot APP.PMF']*calls+(['halt'] if code==0 else []);scheduled=[];seen=set();verifications=0
            frames=[];advance=m.display.advance
            def observe(t):
                advance(t);frames.append('FRAME %d %08X'%(m.display.vsyncs,m.display.crc()))
            m.display.advance=observe
            def operator(core):
                nonlocal verifications
                output=bytes(m.serial[0].out);count=output.count(b'Verifying ')
                if count>verifications:verifications=count;print('Text proof: real PMF verification %d started'%count,flush=True)
                ready=struct.unpack_from('<Q',m.ram,0x600010)[0]
                if ready and ready not in seen:
                    got=list(struct.unpack_from('<400I',m.ram,m.text.cells))
                    assert got==expected,(name,ready,[(n,x,y) for n,(x,y) in enumerate(zip(got,expected)) if x!=y][:5])
                    assert (m.text.cx,m.text.cy,m.text.style)==(4,2,2)
                    seen.add(ready);print('Text proof: actual cell grid/session %d observed'%ready,flush=True)
                if len(scheduled)<len(commands) and output.count(b'pmf> ')>len(scheduled):
                    assert m.input.mctrl==0 and m.input.irq_enable==0
                    assert m.text.style==0x101 and m.text.cells!=0
                    tick=max(m.time,core.cr[I.CR['CYCLE']])+100
                    line=[(tick,b) for b in (commands[len(scheduled)]+'\r').encode()]
                    scheduled.append(line);m.serial[0].incoming.extend(line)
            m.on_slice=operator;m.run(100000000);m.on_slice=None;c=m.cores[0];output=bytes(m.serial[0].out)
            assert c.state=='HALTED' and c.exit==code,(name,c.state,c.exit,output[-3000:])
            assert seen==set(range(1,calls+1)) and struct.unpack_from('<Q',m.ram,0x600000)[0]==calls,name
            if code==0:assert output.count(b'The payload returned, r1 = $1122334455667788')==2 and len(scheduled)==3 and b'Anvil stopped.' in output
            else:assert output.count(b'pmf> ')==1 and b'Payload return failed (0x5B05)' in output and b'The payload returned' not in output
            assert bytes(m.disks[15].image)==bytes(medium) and E.root_files(bytes(m.disks[15].image))=={'APP.PMF':pmf}
            with cfg.open('a',encoding='utf-8') as stream:
                for line in scheduled:
                    for tick,b in line:stream.write('serial 0 $%X %02X\n'%(tick,b))
            native=run([L.EXE,cfg,'--max','100000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram
            state=next(s[6:] for s in native.splitlines() if s.startswith('STATE '))
            assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            assert (td/'disk15.img').read_bytes()==bytes(medium) and m.cores[1].state=='PARKED'
            win=run([zt/('zenwin.exe' if os.name=='nt' else 'zenwin'),cfg,'--headless','--max','100000000'])
            assert [s for s in win.splitlines() if s.startswith('FRAME ')]==frames
            for row in mapping['code']:
                pc=int(row['pc'],16);n=row['size'];assert m.ram[pc:pc+n]==image[64+pc-meta['load']:64+pc-meta['load']+n]
            outcome='both input/text scopes retired' if code==0 else 'foreign text owner failed-stop5B05 before reuse'
            print('PASS published text '+name+': real ROM/PMF/SHA/table208/discovered dispatch, cells/cursor/present, '+outcome+'; exact native/twin RAM/state/frames and independent immutable disk/monitor oracle',flush=True)


if __name__=='__main__':main()
