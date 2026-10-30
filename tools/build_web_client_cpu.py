"""Physical HTTP client lifecycle proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile cooperative HTTP lifecycle qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Network/byte_order.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/web_client.pbi']
contract=(r/'Anvil/Network/web_transport.pbi').read_text(encoding='utf8')
connection=re.search(r'Structure WebConnection.*?EndStructure',contract,re.S).group(0)
s=connection+'\n'+'\n'.join(x for n in names for x in (r/n).read_text(encoding='utf8').splitlines() if not x.startswith('XIncludeFile'))+'''
Global u.WebUrl,q.WebRequest,a.WebResponse,client.WebClient,q2.WebRequest,a2.WebResponse
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim qh.a[1024]
Global Dim ah.a[1024]
Global Dim line.a[512]
Global Dim qh2.a[1024]
Global Dim ah2.a[1024]
Global Dim line2.a[512]
Global Dim tx.a[128]
Global Dim rx.a[128]
Global Dim output.a[64]
Global mode.i,wire.i,wireBytes.i,position.i,closes.i,sends.i,round.i,step.i
Procedure.i WebTransportOpen(*c.WebConnection) : *c\\handle=1 : ProcedureReturn 0 : EndProcedure
Procedure.i WebTransportState(*c.WebConnection)
 If mode=5 And sends>6 : ProcedureReturn -77 : EndIf
 If mode=2 : ProcedureReturn 0 : EndIf
 If mode=6 And position=wireBytes : ProcedureReturn 2 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i WebTransportSend(*c.WebConnection,p.i,n.i)
 If n>3 : n=3 : EndIf
 sends=sends+n : ProcedureReturn n
EndProcedure
Procedure.i WebTransportRecv(*c.WebConnection,p.i,n.i)
 Define i.i,take.i,*request.WebRequest
 *request=client\\request
 If mode<>1 And (*request\\state<>2 Or client\\txOffset<>client\\txLength) : ProcedureReturn 0 : EndIf
 take=wireBytes-position : If take>5 : take=5 : EndIf : If take>n : take=n : EndIf
 For i=0 To take-1 : PokeA(p+i,PeekA(wire+position+i)) : Next
 position=position+take : ProcedureReturn take
EndProcedure
Procedure WebTransportClose(*c.WebConnection)
 If *c\\handle>0 : closes=closes+1 : *c\\handle=0 : EndIf
EndProcedure
Procedure Record(index.i,kind.i)
 Define rc.i,off.i,out.i,p.i,i.i,cap.i,nextRc.i,*response.WebResponse
 mode=kind : position=0 : closes=0 : sends=0 : round=0 : step=0
 wire=?normal : wireBytes=41
 If mode=1 : wire=?early : wireBytes=45 : EndIf
 If mode=6 : wire=?short : wireBytes=40 : EndIf
 u\\host=@host[0] : u\\hostCapacity=256 : u\\target=@target[0] : u\\targetCapacity=3072
 rc=WebUrlParse("http://example.com/",19,0,@u)
 If rc=0
  If mode=4 : rc=WebRequestInit(@q,@u,"POST",4,-1,1,@qh[0],1024) : Else : rc=WebRequestInit(@q,@u,"POST",4,3,1,@qh[0],1024) : EndIf
 EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 If rc=0 : rc=WebResponseInit(@a,@line[0],512,@ah[0],1024,0) : EndIf
 If rc=0 : rc=WebClientStart(@client,@u,@q,@a,@tx[0],128,@rx[0],128,0,1000) : EndIf
 For i=0 To 63 : output[i]=0 : Next
 While rc=0
  step=step+1 : cap=1 : If (step & 1)=0 : cap=0 : EndIf
  If mode=2 : step=1001 : EndIf
  If mode=3 And step=3 : rc=WebClientCancel(@client) : Break : EndIf
  rc=WebClientStep(@client,?body+off,3-off,1,@output[out],cap,step)
  off=off+client\\consumed : out=out+client\\written
  If step>2000 : rc=-999 : Break : EndIf
 Wend
 nextRc=-999
 If mode=7 And rc=1
  nextRc=WebRequestInit(@q2,@u,"POST",4,3,1,@qh2[0],1024)
  If nextRc=0 : nextRc=WebRequestFinishHeaders(@q2) : EndIf
  If nextRc=0 : nextRc=WebResponseInit(@a2,@line2[0],512,@ah2[0],1024,0) : EndIf
  If nextRc=0 : nextRc=WebClientNext(@client,@q2,@a2,step,1000) : EndIf
  If nextRc=0
   position=0 : off=0 : round=1 : rc=0
   While rc=0
    step=step+1
    rc=WebClientStep(@client,?body+off,3-off,1,@output[out],1,step)
    off=off+client\\consumed : out=out+client\\written
    If step>2000 : rc=-999 : Break : EndIf
   Wend
  EndIf
 EndIf
 *response=client\\response
 p=$E1C00100+index*256
 For i=0 To 255 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,client\\state) : PokeI(p+16,*response\\status) : PokeI(p+24,out)
 PokeI(p+32,closes) : PokeI(p+40,*response\\reusable) : PokeI(p+48,nextRc) : PokeI(p+56,sends)
 For i=0 To 63 : PokeA(p+80+i,output[i]) : Next
 WebClientClose(@client) : PokeI(p+64,closes)
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57455831)
 For i=0 To 7 : Record(i,i) : Next
 PokeI($E1C00008,8)
 ProcedureReturn 0
EndProcedure
DataSection
'''
raw={'normal':b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc','early':b'HTTP/1.1 413 Large\r\nContent-Length: 3\r\n\r\nno!','short':b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nab'}
for n,b in raw.items():
 s=s.replace({'normal':'wire=?normal : wireBytes=41','early':'wire=?early : wireBytes=45','short':'wire=?short : wireBytes=40'}[n],f'wire=?{n} : wireBytes={len(b)}')
 s+=n+':\n Data.a '+','.join(map(str,b))+'\n'
s+='body:\n Data.a 97,98,99\nEndDataSection\n';p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names+['Anvil/Network/web_transport.pbi']},cases=list(range(8))),indent=2),encoding='utf8')
