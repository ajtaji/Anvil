"""Build WebSocket opening-handshake fixtures for physical Pi4."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/websocket_frame.pbi','Anvil/Network/websocket_handshake.pbi','Anvil/Crypto/sha1.pbi']
    accept='s3pPLMBiTxaQ9kYGzzhZRbK+xOo='
    valid=['Upgrade: websocket','Connection: Upgrade','Sec-WebSocket-Accept: '+accept]
    cases=[]
    def add(name,headers,rc=0,status='HTTP/1.1 101 Switching Protocols',allow=1,protocol=''):
        wire=(status+'\r\n'+'\r\n'.join(headers)+'\r\n\r\n').encode()+b'\x81\x02Hi'
        cases.append(dict(name=name,wire=wire.hex(),rc=rc,allow=allow,protocol=protocol,consumed=len(wire)-4))
    add('valid',valid)
    add('case-and-whitespace',['Upgrade: WebSocket','Connection: keep-alive, UpGrade','Sec-WebSocket-Accept:  '+accept+'  '])
    add('wrong-accept',valid[:2]+['Sec-WebSocket-Accept: '+'x'*28],-606)
    add('missing-accept',valid[:2],-606)
    add('duplicate-accept',valid+[valid[2]],-606)
    add('missing-upgrade',valid[1:],-606)
    add('duplicate-upgrade',valid+[valid[0]],-606)
    add('missing-connection',[valid[0],valid[2]],-606)
    add('wrong-connection',[valid[0],'Connection: keep-alive',valid[2]],-606)
    add('multiple-connection',[valid[0],'Connection: keep-alive','Connection: Upgrade',valid[2]])
    add('extension',valid+['Sec-WebSocket-Extensions: permessage-deflate'],-606)
    add('unsolicited-protocol',valid+['Sec-WebSocket-Protocol: chat'],-606)
    add('selected-protocol',valid+['Sec-WebSocket-Protocol: chat'],protocol='chat')
    add('declined-protocol',valid,protocol='chat')
    add('wrong-protocol',valid+['Sec-WebSocket-Protocol: Chat'],-606,protocol='chat')
    add('duplicate-protocol',valid+['Sec-WebSocket-Protocol: chat']*2,-606,protocol='chat')
    add('close-connection',[valid[0],'Connection: Upgrade, close',valid[2]],-522)
    add('content-length',valid+['Content-Length: 0'],-522)
    add('chunked',valid+['Transfer-Encoding: chunked'],-522)
    add('http10',valid,-522,status='HTTP/1.0 101 Switching Protocols')
    add('not-opted-in',valid,-526,allow=0)
    s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global u.WebUrl,q.WebRequest,a.WebResponse
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim headers.a[1024]
Global Dim response.a[2048]
Global Dim line.a[512]
Global Dim wire.a[2048]
Global Dim key.a[25]
Global Dim accept.a[29]
Global Dim scratch.i[64]
Global Dim digest.a[20]
Procedure Run(index.i,n.i,allow.i,protocol.i,protocolBytes.i)
 Define i.i,rc.i,used.i,p.i
 For i=0 To n-1 : Read.a wire[i] : Next
 rc=WebResponseInit(@a,@line[0],512,@response[0],2048,0)
 If allow : rc=WebResponseAllowUpgrade(@a) : EndIf
 While used<n And rc>=0 And a\state<>#WEB_RESPONSE_DONE
  rc=WebResponseFeed(@a,@wire[used],1,0,0) : used=used+a\consumed
 Wend
 If rc>=0 And a\state=#WEB_RESPONSE_DONE : rc=WebSocketHandshakeCheck(@a,@accept[0],protocol,protocolBytes,@scratch[0],512) : EndIf
 p=$E1C00100+index*64 : PokeI(p,rc) : PokeI(p+8,used) : PokeI(p+16,a\status)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i,nonce.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57534831)
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=3072
 rc=WebUrlParse("http://example.com/chat",23,1,@u)
 nonce="the sample nonce"
 Sha1Begin() : Sha1Update("prefix",6)
 If rc=0 : rc=WebSocketRequestInit(@q,@u,@headers[0],1024,nonce,@key[0],@accept[0],@scratch[0]) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 PokeI($E1C00010,rc) : PokeI($E1C00018,q\length)
 For i=0 To q\length-1 : PokeA($E1C03000+i,headers[i]) : Next
 For i=0 To 23 : PokeA($E1C03400+i,key[i]) : Next
 For i=0 To 27 : PokeA($E1C03420+i,accept[i]) : Next
 Sha1Update("suffix",6) : Sha1End(@digest[0])
 For i=0 To 19 : PokeA($E1C03440+i,digest[i]) : Next
'''
    s+=f' PokeI($E1C00008,{len(cases)})\n'
    for i,c in enumerate(cases):s+=f' Restore Case{i}\n Run({i},{len(bytes.fromhex(c["wire"]))},{c["allow"]},"{c["protocol"]}",{len(c["protocol"])})\n'
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
