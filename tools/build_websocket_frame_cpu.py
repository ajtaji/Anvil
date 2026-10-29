"""Compile WebSocket frame fixtures for physical Pi4; no emulator."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Network/websocket_frame.pbi'];cases=[]
    def add(name,wire,rc,frames=0,plain=b'',control=b'',limit=1024):
        cases.append(dict(name=name,wire=wire.hex(),rc=rc,frames=frames,plain=plain.hex(),control=control.hex(),limit=limit))
    add('hello',b'\x81\x05Hello',1,1,b'Hello')
    add('empty',b'\x81\0',1,1)
    add('fragmented',b'\x01\x03Hel\x80\x02lo',1,2,b'Hello')
    add('interleaved-ping',b'\x01\x03Hel\x89\x01!\x80\x02lo',1,3,b'Hello',b'!')
    add('utf8-split',b'\x01\x01\xe2\x80\x02\x82\xac',1,2,'€'.encode())
    add('binary',b'\x82\x03\xff\0\x80',1,1,b'\xff\0\x80')
    add('16bit',b'\x82\x7e\0\x7e'+b'x'*126,1,1,b'x'*126)
    add('close',b'\x88\x05\x03\xe8bye',1,1,control=b'\x03\xe8bye')
    add('empty-close',b'\x88\0',1,1)
    add('pong',b'\x8a\x01!',1,1,control=b'!')
    add('masked-server',b'\x81\x80',-601)
    add('reserved-bit',b'\xc1\0',-601)
    add('reserved-opcode',b'\x83\0',-601)
    add('orphan-continuation',b'\x80\0',-601)
    add('nested-message',b'\x01\0\x82\0',-601,1)
    add('fragmented-control',b'\x09\0',-601)
    add('long-control',b'\x89\x7e',-601)
    add('nonminimal16',b'\x82\x7e\0\x01',-601)
    add('nonminimal64',b'\x82\x7f'+b'\0'*7+b'\x7e',-601)
    add('highbit-length',b'\x82\x7f\x80'+b'\0'*7,-602)
    add('message-limit',b'\x82\x05',-602,limit=4)
    add('fragment-limit',b'\x02\x02ab\x80\x03',-602,1,b'ab',limit=4)
    add('utf8-overlong',b'\x81\x02\xc0\x80',-603)
    add('utf8-surrogate',b'\x81\x03\xed\xa0\x80',-603,plain=b'\xed\xa0')
    add('utf8-incomplete',b'\x81\x01\xe2',-603,plain=b'\xe2')
    add('bad-close-length',b'\x88\x01x',-601,control=b'x')
    add('bad-close-code',b'\x88\x02\x03\xed',-601,control=b'\x03\xed')
    add('bad-close-text',b'\x88\x03\x03\xe8\xff',-603,control=b'\x03\xe8\xff')
    add('incomplete-frame',b'\x81\x05Hi',0,plain=b'Hi')
    s='XIncludeFile "Anvil/Network/websocket_frame.pbi"\n'+r'''
Global f.WebSocketFrame
Global Dim wire.a[1024]
Global Dim ctrl.a[125]
Global Dim output.a[8]
Procedure Run(index.i,n.i,limit.i)
 Define i.i,rc.i,off.i,p.i,frames.i,plain.i,controls.i,k.i,step.i,take.i,cap.i
 p=$E1C00100+index*384
 For i=0 To n-1 : Read.a wire[i] : Next
 rc=WebSocketFrameInit(@f,@ctrl[0],limit)
 While off<n And rc>=0
  take=1 : cap=1 : If step % 3=0 : cap=0 : EndIf
  rc=WebSocketFrameFeed(@f,@wire[off],take,@output[0],cap)
  off=off+f\consumed
  For k=0 To f\written-1 : PokeA(p+64+plain,output[k]) : plain=plain+1 : Next
  If rc=1
   frames=frames+1
   For k=0 To f\controlLength-1 : PokeA(p+208+controls,ctrl[k]) : controls=controls+1 : Next
   If off<n : rc=WebSocketFrameNext(@f) : EndIf
  EndIf
  step=step+1 : If step>4096 : rc=-999 : Break : EndIf
 Wend
 If rc<0 And f\controlLength>0
  For k=0 To f\controlLength-1 : PokeA(p+208+controls,ctrl[k]) : controls=controls+1 : Next
 EndIf
 PokeI(p,rc) : PokeI(p+8,frames) : PokeI(p+16,plain) : PokeI(p+24,controls) : PokeI(p+32,off)
 PokeI(p+40,WebSocketFrameEof(@f))
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57534631)
'''
    s+=f' PokeI($E1C00008,{len(cases)})\n'
    for i,c in enumerate(cases):s+=f' Restore Case{i}\n Run({i},{len(bytes.fromhex(c["wire"]))},{c["limit"]})\n'
    s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for i,c in enumerate(cases):s+=f'Case{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['wire'])))+'\n'
    s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
