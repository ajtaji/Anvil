"""Compile physical CPU qualification with a deliberately fragmented fake transport."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=list(range(10))
 names=['RaspberryPi4/Lib/mmu.pi4', 'Anvil/Network/web_url.pbi', 'Anvil/Network/web_transport.pbi', 'Anvil/Network/h2_frame.pbi', 'Anvil/Network/hpack_decode.pbi', 'Anvil/Network/hpack_tables.pbi', 'Anvil/Network/h2_client.pbi', 'Anvil/Network/h2_request.pbi', 'Anvil/Network/web_request.pbi', 'Anvil/Network/web_response.pbi', 'Anvil/Network/web_client.pbi']
 s=r'''#WEB_KERNEL_BINDING=0
XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
XIncludeFile "Anvil/Network/h2_frame.pbi"
XIncludeFile "Anvil/Network/hpack_decode.pbi"
XIncludeFile "Anvil/Network/hpack_tables.pbi"
XIncludeFile "Anvil/Network/h2_client.pbi"
XIncludeFile "Anvil/Network/h2_request.pbi"
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_client.pbi"
Global services.i
Global *pet
Global c.H2Client
Global wc.WebClient
Global moved.WebConnection
Global buffers.H2Buffers
Global url.WebUrl
Global request.WebRequest
Global response.WebResponse
Global Dim tx.a[16384]
Global Dim rx.a[16384]
Global Dim block.a[65536]
Global Dim controls.a[1024]
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global Dim streams.a[2048]
Global Dim headers.a[2048]
Global Dim responseHeaders.a[2048]
Global Dim line.a[512]
Global Dim result.a[16]
Global Dim offer.a[32]
Global Dim outgoing.a[4096]
Global Dim incoming.a[128]
Global mode.i,opens.i,closes.i,offerBytes.i,outBytes.i,inAt.i,inBytes.i,sendCalls.i,recvCalls.i,alpnCalls.i
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i FakeOpen(host.i,port.i,protocols.i,bytes.i)
 Define i.i
 opens=opens+1 : offerBytes=bytes
 For i=0 To bytes-1 : offer[i]=PeekA(protocols+i) : Next
 ProcedureReturn 1
EndProcedure
Procedure.i FakeLegacyOpen(host.i,port.i)
 ProcedureReturn FakeOpen(host,port,0,0)
EndProcedure
Procedure.i FakeState(handle.i)
 If handle<>1 : ProcedureReturn -9401 : EndIf
 If mode=6 Or mode=7 : ProcedureReturn 0 : EndIf
 ProcedureReturn 4
EndProcedure
Procedure.i FakeAlpn(handle.i,destination.i,capacity.i)
 Define text.i,n.i,i.i
 alpnCalls=alpnCalls+1
 If mode=8 : ProcedureReturn -109 : EndIf
 If mode=2 Or mode=4 : ProcedureReturn 0 : EndIf
 text="h2" : n=2
 If mode=1 Or mode=5 : text="http/1.1" : n=8 : EndIf
 If mode=3 : text="spdy" : n=4 : EndIf
 For i=0 To n-1 : PokeA(destination+i,PeekA(text+i)) : Next
 ProcedureReturn n
EndProcedure
Procedure.i FakeClose(handle.i)
 If handle<>1 : ProcedureReturn -9402 : EndIf
 closes=closes+1 : ProcedureReturn 0
EndProcedure
Procedure.i FakeSend(handle.i,source.i,bytes.i)
 Define i.i,n.i
 sendCalls=sendCalls+1 : If (sendCalls % 4)=0 : ProcedureReturn 0 : EndIf
 n=bytes : If n>3 : n=3 : EndIf
 If outBytes+n>4096 : ProcedureReturn -9403 : EndIf
 For i=0 To n-1 : outgoing[outBytes+i]=PeekA(source+i) : Next
 outBytes=outBytes+n : ProcedureReturn n
EndProcedure
Procedure.i FakeRecv(handle.i,destination.i,bytes.i)
 Define i.i,n.i
 recvCalls=recvCalls+1 : If (recvCalls % 3)=0 : ProcedureReturn 0 : EndIf
 If mode<>0 And outBytes<request\length : ProcedureReturn 0 : EndIf
 n=inBytes-inAt : If n>bytes : n=bytes : EndIf : If n>5 : n=5 : EndIf
 For i=0 To n-1 : PokeA(destination+i,incoming[inAt+i]) : Next
 inAt=inAt+n : ProcedureReturn n
EndProcedure
Procedure.i Probe(p.i)
 Define i.i,tick.i,rc.i,n.i,text.i,bytes.i,terminal.i
 opens=0 : closes=0 : offerBytes=0 : outBytes=0 : inAt=0 : sendCalls=0 : recvCalls=0 : alpnCalls=0
 For i=0 To SizeOf(WebConnection)-1 : PokeA(@moved+i,0) : Next
 For i=0 To SizeOf(WebClient)-1 : PokeA(@wc+i,0) : Next
 url\secure=1 : url\host="example.org" : url\hostLength=11 : url\port=443 : url\target="/test" : url\targetLength=5
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\controls=@controls[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 rc=WebRequestInit(@request,@url,"GET",3,0,1,@headers[0],2048) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestFinishHeaders(@request) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebResponseInit(@response,@line[0],512,@responseHeaders[0],2048,0) : If rc<>0 : ProcedureReturn rc : EndIf
 If mode=0
  inBytes=9 : For i=0 To 8 : incoming[i]=0 : Next : incoming[3]=4
 Else
  text="HTTP/1.1 200 OK" : n=15 : inBytes=0
  For i=0 To n-1 : incoming[inBytes]=PeekA(text+i) : inBytes=inBytes+1 : Next
  incoming[inBytes]=13 : incoming[inBytes+1]=10 : inBytes=inBytes+2
  text="Content-Length: 2" : n=17
  For i=0 To n-1 : incoming[inBytes]=PeekA(text+i) : inBytes=inBytes+1 : Next
  incoming[inBytes]=13 : incoming[inBytes+1]=10 : inBytes=inBytes+2
  text="Connection: close" : n=17
  For i=0 To n-1 : incoming[inBytes]=PeekA(text+i) : inBytes=inBytes+1 : Next
  incoming[inBytes]=13 : incoming[inBytes+1]=10 : incoming[inBytes+2]=13 : incoming[inBytes+3]=10
  incoming[inBytes+4]=79 : incoming[inBytes+5]=75 : inBytes=inBytes+6
 EndIf
 If mode=9
  rc=WebClientStart(@wc,@url,@request,@response,@tx[0],16384,@rx[0],16384,0,10000)
 ElseIf mode=4 Or mode=5
  rc=H2ClientStart(@c,@url,@buffers,0,10000)
 Else
  n=10000 : If mode=6 : n=10 : EndIf
  rc=H2ClientStartNegotiated(@c,@url,@buffers,0,n)
 EndIf
 If rc<>0 : ProcedureReturn rc : EndIf
 If mode<>9
  For tick=1 To 1000
   pet()
   rc=H2ClientStep(@c,tick)
   If mode=7 And tick=3 : rc=H2ClientCancel(@c) : EndIf
   If rc<0 Or c\state=3 Or c\state=4 : Break : EndIf
  Next
  terminal=rc
  If mode=0
   If c\state<>3 Or rc<>0 : ProcedureReturn -9410 : EndIf
   If H2ClientTakeHttp1(@c,@moved)<>#H2_STATE : ProcedureReturn -9411 : EndIf
  ElseIf mode=1 Or mode=2
   If c\state<>4 Or outBytes<>0 Or rc<>0 : ProcedureReturn -9412 : EndIf
   rc=H2ClientStep(@c,tick+1)
   If rc<>0 Or c\state<>4 Or outBytes<>0 : ProcedureReturn -9413 : EndIf
   moved\handle=2
   If H2ClientTakeHttp1(@c,@moved)<>#H2_STATE Or c\connection\handle<>1 : ProcedureReturn -9414 : EndIf
   moved\handle=0
   If H2ClientTakeHttp1(@c,@c\connection)<>#H2_ARGUMENT : ProcedureReturn -9415 : EndIf
   rc=H2ClientTakeHttp1(@c,@moved)
   If rc<>0 Or c\state<>0 Or c\connection\handle<>0 Or moved\handle<>1 : ProcedureReturn -9416 : EndIf
   H2ClientClose(@c)
   If closes<>0 : ProcedureReturn -9417 : EndIf
   rc=WebClientAdopt(@wc,@moved,@request,@response,@tx[0],1,@rx[0],16384,0,10000)
   PokeI(p+64,rc)
   If rc<>#WEB_CLIENT_ARGUMENT Or moved\handle<>1 Or closes<>0 : ProcedureReturn -9418 : EndIf
   WebClientClose(@wc)
   rc=WebClientAdopt(@wc,@moved,@request,@response,@tx[0],16384,@rx[0],16384,0,10000)
   If rc<>0 Or moved\handle<>0 Or wc\connection\handle<>1 Or opens<>1 : ProcedureReturn -9419 : EndIf
   If H2ClientTakeHttp1(@c,@moved)<>#H2_STATE Or closes<>0 : ProcedureReturn -9420 : EndIf
   If WebClientAdopt(@wc,@wc\connection,@request,@response,@tx[0],16384,@rx[0],16384,0,10000)<>#WEB_CLIENT_ARGUMENT : ProcedureReturn -9421 : EndIf
  Else
   n=#H2_PROTOCOL
   If mode=6 : n=#H2_TIMEOUT : EndIf
   If mode=7 : n=#H2_CANCELLED : EndIf
   If mode=8 : n=-109 : EndIf
   If terminal<>n Or outBytes<>0 : ProcedureReturn -9422 : EndIf
  EndIf
 EndIf
 If mode=1 Or mode=2 Or mode=9
  bytes=0
  For tick=1 To 10000
   pet()
   rc=WebClientStep(@wc,0,0,1,@result[0]+bytes,1,tick)
   bytes=bytes+wc\written
   If rc<>0 Or bytes>2 : Break : EndIf
  Next
  If rc<>1 Or bytes<>2 Or response\status<>200 Or result[0]<>79 Or result[1]<>75 : ProcedureReturn -9423 : EndIf
  If WebClientStep(@wc,0,0,1,@result[0],1,tick+1)<>1 : ProcedureReturn -9424 : EndIf
 EndIf
 H2ClientClose(@c) : H2ClientClose(@c)
 WebClientClose(@wc) : WebClientClose(@wc)
 WebTransportClose(@moved)
 PokeI(p+8,terminal) : PokeI(p+16,opens) : PokeI(p+24,closes)
 PokeI(p+32,outBytes) : PokeI(p+40,offerBytes) : PokeI(p+48,response\status) : PokeI(p+56,bytes)
 PokeI(p+72,alpnCalls)
 For i=0 To offerBytes-1 : PokeA(p+128+i,offer[i]) : Next
 For i=0 To outBytes-1 : PokeA(p+256+i,outgoing[i]) : Next
 If opens<>1 Or closes<>1 : ProcedureReturn -9425 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i,p.i
 rc=WebPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 1048575 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$48324E47) : PokeI($E1C00008,10)
 webpTlsOpenAlpn=@FakeOpen : webpTlsOpen=@FakeLegacyOpen : webpTlsState=@FakeState : webpTlsAlpn=@FakeAlpn : webpTlsClose=@FakeClose : webpTlsSend=@FakeSend : webpTlsRecv=@FakeRecv
 For mode=0 To 9
  p=$E1C00100+mode*8192
  rc=Probe(p) : PokeI(p,rc)
  H2ClientClose(@c) : WebClientClose(@wc) : WebTransportClose(@moved)
 Next
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1cfffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
