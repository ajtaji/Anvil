"""Compile cooperative WebSocket client fixtures for physical Pi4.
Transport and RNG are controlled doubles; cryptographic handshake hashing and
HTTP/WebSocket owners are real. The deterministic RNG is for this proof only.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/websocket_frame.pbi','Anvil/Network/websocket_handshake.pbi','Anvil/Crypto/sha1.pbi','Anvil/Network/web_client.pbi','Anvil/Network/websocket_client.pbi']
    cases=list(range(8))
    s='\n'.join('XIncludeFile "'+n+'"' for n in names[:6])+r'''
Structure WebConnection
 secure.i
 handle.i
 address.i
 host.i
 port.i
EndStructure
Global mode.i,closed.i,sent.i,wireLen.i,wireOff.i,requestLen.i,rngCalls.i
Global Dim incoming.a[2048]
Global Dim outgoing.a[4096]
Procedure.i WebTransportOpen(*c.WebConnection)
 *c\handle=1 : ProcedureReturn 0
EndProcedure
Procedure.i WebTransportState(*c.WebConnection)
 If mode=4 And wireOff=wireLen : ProcedureReturn 2 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i WebTransportSend(*c.WebConnection,p.i,n.i)
 Define i.i,take.i
 If mode=5 And sent>=requestLen : ProcedureReturn n+1 : EndIf
 take=n : If take>3 : take=3 : EndIf
 If mode=1 : take=1 : EndIf
 For i=0 To take-1 : outgoing[sent+i]=PeekA(p+i) : Next
 sent=sent+take : ProcedureReturn take
EndProcedure
Procedure.i WebTransportRecv(*c.WebConnection,p.i,n.i)
 Define i.i,take.i
 If sent<requestLen : ProcedureReturn 0 : EndIf
 take=wireLen-wireOff : If take>n : take=n : EndIf
 If mode=1 And take>1 : take=1 : EndIf
 For i=0 To take-1 : PokeA(p+i,incoming[wireOff+i]) : Next
 wireOff=wireOff+take : ProcedureReturn take
EndProcedure
Procedure WebTransportClose(*c.WebConnection)
 closed=closed+1 : *c\handle=0
EndProcedure
'''
    s+='\n'.join(x for x in (root/names[6]).read_text(encoding='utf8').splitlines() if not x.startswith('XIncludeFile'))+'\n'
    s+=(root/names[7]).read_text(encoding='utf8')+r'''
Global u.WebUrl,q.WebRequest,a.WebResponse,h.WebClient,f.WebSocketFrame,ws.WebSocketClient
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim headers.a[1024]
Global Dim response.a[2048]
Global Dim line.a[512]
Global Dim key.a[25]
Global Dim accept.a[29]
Global Dim scratch.i[64]
Global Dim ctrl.a[125]
Global Dim tx.a[512]
Global Dim rx.a[512]
Global Dim output.a[4]
Procedure.i FixtureRandom(p.i,n.i)
 Define i.i
 rngCalls=rngCalls+1
 If mode=2 : ProcedureReturn -1 : EndIf
 For i=0 To n-1 : PokeA(p+i,17*rngCalls+i) : Next
 ProcedureReturn n
EndProcedure
Procedure Run(which.i,n.i)
 Define i.i,rc.i,p.i,started.i,tick.i,plain.i,frames.i,queued.i,k.i
 mode=which : closed=0 : sent=0 : wireLen=n : wireOff=0 : requestLen=0 : rngCalls=0
 For i=0 To n-1 : Read.a incoming[i] : Next
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=3072
 rc=WebSocketUrlParse("ws://example.com/chat",21,1,@u,@scratch[0],512)
 If rc=0 : rc=WebSocketRequestInit(@q,@u,@headers[0],1024,"the sample nonce",@key[0],@accept[0],@scratch[0]) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 requestLen=q\length
 If rc=0 : rc=WebResponseInit(@a,@line[0],512,@response[0],2048,0) : EndIf
 If rc=0 : rc=WebResponseAllowUpgrade(@a) : EndIf
 If rc=0 : rc=WebSocketFrameInit(@f,@ctrl[0],1024) : EndIf
 If rc=0 : rc=WebClientStart(@h,@u,@q,@a,@tx[0],512,@rx[0],512,0,4000) : EndIf
 If rc=0 : rc=WebSocketClientBind(@ws,@h,@f,@accept[0],0,0,@FixtureRandom,@scratch[0]) : EndIf
 p=$E1C00100+which*1024
 While rc>=0 And rc<>2 And tick<5000
  rc=WebSocketClientStep(@ws,@output[0],2,tick)
  For k=0 To ws\written-1 : PokeA(p+64+plain,output[k]) : plain=plain+1 : Next
  If rc=1 : frames=frames+1 : EndIf
  If ws\state=1 And queued=0
   If mode=6
    WebSocketClientAbort(@ws) : rc=ws\error
   ElseIf mode=7
    rc=WebSocketClientSend(@ws,8,0,0,tick)
   Else
    rc=WebSocketClientSend(@ws,1,"Hello",5,tick)
   EndIf
   queued=1
  EndIf
  tick=tick+1
 Wend
 PokeI(p,rc) : PokeI(p+8,ws\state) : PokeI(p+16,closed) : PokeI(p+24,plain)
 PokeI(p+32,frames) : PokeI(p+40,sent-requestLen) : PokeI(p+48,rngCalls) : PokeI(p+56,tick)
 For i=requestLen To sent-1 : PokeA(p+256+i-requestLen,outgoing[i]) : Next
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57534331) : PokeI($E1C00008,8)
'''
    wires=[]
    for i in cases:
        accept='x'*28 if i==3 else 's3pPLMBiTxaQ9kYGzzhZRbK+xOo='
        raw=('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode()
        if i not in (2,3,5,6,7):raw+=b'\x89\x01!\x01\x01H\x80\x01i'
        if i not in (2,3,4,5,6,7):raw+=b'\x88\x02\x03\xe8'
        wires.append(raw);s+=f' Restore Case{i}\n Run({i},{len(raw)})\n'
    s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for i,raw in enumerate(wires):s+=f'Case{i}:\n Data.a '+','.join(map(str,raw))+'\n'
    s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
