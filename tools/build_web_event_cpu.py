"""Compile incremental HTTP event stream fixtures for physical Pi4 execution."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Network/web_event_stream.pbi'];cases=[]
    def add(name,wire,events=(),rc=0,last=b'',retry=3000,limit=128):
        cases.append(dict(name=name,wire=wire.hex(),events=[dict(data=d.hex(),event=e.hex(),id=i.hex()) for d,e,i in events],rc=rc,last=last.hex(),retry=retry,limit=limit))
    add('basic',b'data: hello\n\n',[(b'hello',b'message',b'')])
    add('multi-line-crlf',b'data: one\r\ndata: two\r\n\r\n',[(b'one\ntwo',b'message',b'')])
    add('cr-only',b'data: yes\r\r',[(b'yes',b'message',b'')])
    add('bom',b'\xef\xbb\xbfdata: yes\n\n',[(b'yes',b'message',b'')])
    add('empty-data',b'data\n\n',[(b'',b'message',b'')])
    add('comments',b':keepalive\nunknown: x\n\n')
    add('case-sensitive',b'Data: ignored\n\n')
    add('named-id',b'id: 42\nevent: turn\ndata: left\n\n',[(b'left',b'turn',b'42')],last=b'42')
    add('persistent-id',b'id: 4\n\ndata: a\n\ndata: b\n\n',[(b'a',b'message',b'4'),(b'b',b'message',b'4')],last=b'4')
    add('clear-id',b'id: 4\n\nid\ndata: a\n\n',[(b'a',b'message',b'')])
    add('null-id',b'id: 4\nid: x\0y\ndata: a\n\n',[(b'a',b'message',b'4')],last=b'4')
    add('unfinished-id',b'id: uncommitted\n')
    add('unfinished-data',b'data: lost\n')
    add('event-reset',b'event: ignored\n\ndata: a\n\n',[(b'a',b'message',b'')])
    add('one-space',b'data:  a:b\n\n',[(b' a:b',b'message',b'')])
    add('retry',b'retry: 25\nretry: nope\n\n',retry=25)
    add('retry-overflow',b'retry: 999999999999999999999999999\n\n',retry=2147483647)
    add('utf8',('data: euro € face U0001f600\n\n').encode(),[(('euro € face U0001f600').encode(),b'message',b'')])
    add('replacement',b'data: \xc0\x80\xe2x\xed\xa0\x80\n\n',[(b'\xef\xbf\xbd'*2+b'\xef\xbf\xbdx'+b'\xef\xbf\xbd'*3,b'message',b'')])
    add('line-limit',b'data: '+b'x'*140+b'\n\n',rc=-631)
    add('data-limit',b'data: abcdef\n\n',rc=-631,limit=4)
    add('data-null',b'data: a\0b\n\n',[(b'a\0b',b'message',b'')])
    s='XIncludeFile "Anvil/Network/web_event_stream.pbi"\n'+r'''
Global f.WebEventStream
Global Dim wire.a[512]
Global Dim line.a[128]
Global Dim data.a[128]
Global Dim event.a[32]
Global Dim ident.a[32]
Global Dim last.a[32]
Procedure Run(index.i,n.i,limit.i,fragment.i)
 Define i.i,rc.i,off.i,p.i,events.i,k.i,take.i,ep.i,probe.i,eof.i
 p=$E1C00100+index*512
 For i=0 To n-1 : Read.a wire[i] : Next
 rc=WebEventStreamInit(@f,@line[0],128,@data[0],limit,@event[0],32,@ident[0],@last[0],32)
 While off<n And rc>=0
  take=n-off : If fragment>0 And take>fragment : take=fragment : EndIf
  rc=WebEventStreamFeed(@f,@wire[off],take) : off=off+f\consumed
  If rc=1
   If events>=2 : rc=-998 : Break : EndIf
   ep=p+64+events*192
   PokeI(ep,f\dataLength) : PokeI(ep+8,f\eventLength) : PokeI(ep+16,f\lastIdLength)
   For k=0 To f\dataLength-1 : PokeA(ep+32+k,data[k]) : Next
   For k=0 To f\eventLength-1 : PokeA(ep+96+k,event[k]) : Next
   For k=0 To f\lastIdLength-1 : PokeA(ep+128+k,last[k]) : Next
   probe=WebEventStreamFeed(@f,@wire[0],1)
   If probe<>1 Or f\consumed<>0 : rc=-997 : Break : EndIf
   events=events+1 : rc=WebEventStreamNext(@f)
  EndIf
 Wend
 eof=WebEventStreamEof(@f)
 PokeI(p,rc) : PokeI(p+8,events) : PokeI(p+16,off) : PokeI(p+24,f\retry) : PokeI(p+32,f\lastIdLength) : PokeI(p+40,eof)
 For k=0 To f\lastIdLength-1 : PokeA(p+448+k,last[k]) : Next
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 32767 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$53534531)
'''
    cases=[dict(c,fragment=f) for f in [1,0] for c in cases]
    s+=f' PokeI($E1C00008,{len(cases)})\n'
    for i,c in enumerate(cases):s+=f' Restore Case{i}\n Run({i},{len(bytes.fromhex(c["wire"]))},{c["limit"]},{c["fragment"]})\n'
    s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for i,c in enumerate(cases):s+=f'Case{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['wire'])))+'\n'
    s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c07fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
