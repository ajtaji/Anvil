"""Compile physical CPU qualification with a deliberately fragmented fake transport."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,reference):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=json.loads(Path(reference).read_text())
 assert [row['host'] for row in rows]==['www.openbsd.org','www.sqlite.org']
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
Global *pet,*clock,*savedOpen,*savedClose
Global opens.i,closes.i
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
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global Dim streams.a[2048]
Global Dim headers.a[2048]
Global Dim responseHeaders.a[32768]
Global Dim line.a[8192]
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i CountOpen(host.i,port.i,protocols.i,bytes.i)
 opens=opens+1 : ProcedureReturn savedOpen(host,port,protocols,bytes)
EndProcedure
Procedure.i CountClose(handle.i)
 closes=closes+1 : ProcedureReturn savedClose(handle)
EndProcedure
Procedure.i Probe(index.i)
 Define rc.i,started.i,now.i,before.i,cost.i,maxStep.i,maxService.i,received.i,p.i,destination.i,handle.i,i.i
 p=$E1C00100+index*128 : destination=$E1C01000+index*200000
 url\secure=1 : url\host="www.openbsd.org" : url\hostLength=15
 If index=1 : url\host="www.sqlite.org" : url\hostLength=14 : EndIf
 url\port=443 : url\target="/" : url\targetLength=1
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 rc=WebRequestInit(@request,@url,"GET",3,0,1,@headers[0],2048) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestFinishHeaders(@request) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebResponseInit(@response,@line[0],8192,@responseHeaders[0],32768,0) : If rc<>0 : ProcedureReturn rc : EndIf
 opens=0 : closes=0 : started=clock()
 rc=H2ClientStartNegotiated(@c,@url,@buffers,started,45000000) : If rc<>0 : ProcedureReturn rc : EndIf
 While clock()-started<45000000
  pet() : before=clock() : WebPayloadService(1) : cost=clock()-before
  If cost>maxService : maxService=cost : EndIf
  now=clock() : rc=H2ClientStep(@c,now) : cost=clock()-now
  If cost>maxStep : maxStep=cost : EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  If c\state=4 : Break : EndIf
  If c\state=3 : ProcedureReturn -9501 : EndIf
 Wend
 If c\state<>4 : ProcedureReturn -9502 : EndIf
 handle=c\connection\handle
 rc=WebTransportAlpn(@c\connection,@field[0],16)
 PokeI(p+16,rc)
 If rc=8
  If h2cEqual(@field[0],8,"http/1.1")=0 : ProcedureReturn -9503 : EndIf
 ElseIf rc<>0
  ProcedureReturn -9504
 EndIf
 rc=H2ClientTakeHttp1(@c,@moved) : If rc<>0 : ProcedureReturn rc : EndIf
 If moved\handle<>handle Or c\connection\handle<>0 : ProcedureReturn -9505 : EndIf
 H2ClientClose(@c)
 rc=WebClientAdopt(@wc,@moved,@request,@response,@tx[0],16384,@rx[0],16384,started,45000000)
 If rc<>0 : ProcedureReturn rc : EndIf
 If wc\connection\handle<>handle Or moved\handle<>0 Or opens<>1 Or closes<>0 : ProcedureReturn -9506 : EndIf
 While clock()-started<45000000
  pet() : before=clock() : WebPayloadService(1) : cost=clock()-before
  If cost>maxService : maxService=cost : EndIf
  now=clock() : rc=WebClientStep(@wc,0,0,1,destination+received,196608-received,now) : cost=clock()-now
  If cost>maxStep : maxStep=cost : EndIf
  received=received+wc\written
  If rc<0 : ProcedureReturn rc : EndIf
  If rc=1 : Break : EndIf
  If received>=196608 : ProcedureReturn -9507 : EndIf
 Wend
 If rc<>1 : ProcedureReturn -9508 : EndIf
 WebClientClose(@wc) : H2ClientClose(@c) : WebTransportClose(@moved)
 PokeI(p+8,response\status) : PokeI(p+24,received) : PokeI(p+32,opens) : PokeI(p+40,closes)
 PokeI(p+48,clock()-started) : PokeI(p+56,maxStep) : PokeI(p+64,maxService)
 If opens<>1 Or closes<>1 : ProcedureReturn -9509 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i,index.i
 rc=WebPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8) : clock=PeekI(services+16+11*8)
 savedOpen=PeekI(services+16+90*8) : savedClose=PeekI(services+16+83*8)
 webpTlsOpenAlpn=@CountOpen : webpTlsClose=@CountClose
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 1048575 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$48324642) : PokeI($E1C00008,2)
 For index=0 To 1
  rc=Probe(index) : PokeI($E1C00100+index*128,rc)
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
    ap.add_argument('--reference',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve(),a.reference)
