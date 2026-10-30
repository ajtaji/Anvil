"""Compile a verified HTTP/2 POST probe using shared transport, frames and HPACK.

Exercises shared WebRequest headers, streamed DATA uploads and response events.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,negotiate=False):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=['https://httpbin.org/post']
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_url.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/h2_frame.pbi','Anvil/Network/hpack_decode.pbi','Anvil/Network/hpack_tables.pbi','Anvil/Network/h2_client.pbi','Anvil/Network/h2_request.pbi','Anvil/Network/web_request.pbi']
 s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''


Global services.i
Global *pet,*clock
Global c.H2Client
Global buffers.H2Buffers
Global url.WebUrl
Global Dim tx.a[16384]
Global Dim rx.a[16384]
Global Dim block.a[65536]
Global Dim controls.a[1024]
Global Dim requestBlock.a[65536]
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global Dim streams.a[1024]
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure


Global request.WebRequest
Global Dim headers.a[32768]
Global Dim upload.a[70000]
Procedure.i Probe()
 Define rc.i,now.i,started.i,before.i,cost.i,maxStep.i,maxService.i,submitted.i,ended.i,i.i,position.i,received.i,status.i
 url\secure=1 : url\host="httpbin.org" : url\hostLength=11 : url\port=443 : url\target="/post" : url\targetLength=5
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\requestBlock=@requestBlock[0] : buffers\controls=@controls[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 For i=0 To 69999 : upload[i]=97 : Next
 rc=WebRequestInit(@request,@url,"POST",4,70000,1,@headers[0],32768) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestHeader(@request,"Content-Type",12,"text/plain",10) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestHeader(@request,"X-Anvil-Probe",13,"shared request",14) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestFinishHeaders(@request) : If rc<>0 : ProcedureReturn rc : EndIf
 started=clock()
 rc=H2ClientStart(@c,@url,@buffers,started,45000000) : If rc<>0 : ProcedureReturn rc : EndIf
 While clock()-started<45000000
  pet() : before=clock() : WebPayloadService(1) : cost=clock()-before
  If cost>maxService : maxService=cost : EndIf
  now=clock() : rc=H2ClientStep(@c,now) : cost=clock()-now
  If cost>maxStep : maxStep=cost : EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  If rc>0
   If c\eventStream<>1 : ProcedureReturn -9401 : EndIf
   If rc=#H2_FIELD And h2cEqual(c\name,c\nameLength,":status")
    status=(PeekA(c\value)-48)*100+(PeekA(c\value+1)-48)*10+PeekA(c\value+2)-48
   EndIf
   If rc=#H2_DATA
    If received+c\dataBytes>131072 : ProcedureReturn -9402 : EndIf
    For i=0 To c\dataBytes-1 : PokeA($E1C01000+received+i,PeekA(c\data+i)) : Next
    received=received+c\dataBytes
   EndIf
   If rc=#H2_END : ended=1 : EndIf
   If rc=#H2_RESET Or rc=#H2_GOAWAY : ProcedureReturn -9403 : EndIf
   rc=H2ClientConsume(@c) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If ended<>0 And c\txLength=0 And c\controlLength=0 : Break : EndIf
  If submitted=0 And c\state=3 And c\txLength=0 And c\controlLength=0
   rc=H2ClientRequest(@c,@request) : If rc<>1 : ProcedureReturn rc : EndIf
   submitted=1
  EndIf
  If submitted<>0 And request\state<>2 And ended=0
   rc=H2ClientData(@c,1,@upload[0]+position,70000-position,1)
   If rc<>#H2_BUSY
    If rc<0 : ProcedureReturn rc : EndIf
    position=position+rc
   EndIf
  EndIf
 Wend
 PokeI($E1C00010,position) : PokeI($E1C00018,received) : PokeI($E1C00020,status)
 PokeI($E1C00028,maxStep) : PokeI($E1C00030,maxService) : PokeI($E1C00038,clock()-started) : PokeI($E1C00040,request\state)
 If ended=0 : ProcedureReturn -9404 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i
 rc=WebPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8) : clock=PeekI(services+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 1048575 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4832504F)
 rc=Probe() : PokeI($E1C00008,rc)
 H2ClientClose(@c)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 if negotiate:s=s.replace('H2ClientStart(@c,','H2ClientStartNegotiated(@c,')
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1cfffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--negotiate',action='store_true')
    a=ap.parse_args();build(a.compiler,a.out.resolve(),a.negotiate)
