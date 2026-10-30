"""Compile a verified HTTP/2 GET probe using shared transport, frames and HPACK.

Exercises the reusable asynchronous engine, concurrent GETs and receive credit.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,cancel_first=False):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=['https://httpbin.org/delay/5' if cancel_first else 'https://httpbin.org/uuid','https://httpbin.org/bytes/70000']
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

Procedure.i Probe()
 Define rc.i,now.i,started.i,before.i,cost.i,maxStep.i,maxService.i,sent.i,ended.i,i.i,id.i,slot.i,p.i,n.i,peak.i
 url\secure=1 : url\host="httpbin.org" : url\hostLength=11 : url\port=443
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 started=clock()
 rc=H2ClientStart(@c,@url,@buffers,started,45000000) : If rc<>0 : ProcedureReturn rc : EndIf
 While ended<2 And clock()-started<45000000
  pet() : before=clock() : WebPayloadService(1) : cost=clock()-before
  If cost>maxService : maxService=cost : EndIf
  now=clock() : rc=H2ClientStep(@c,now) : cost=clock()-now
  If cost>maxStep : maxStep=cost : EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  If rc>0
   id=c\eventStream : slot=(id-1)/2
   If slot<0 Or slot>1 : ProcedureReturn -9101 : EndIf
   p=$E1C00100+slot*64
   If rc=#H2_FIELD
    PokeI(p+8,PeekI(p+8)+1)
    If h2cEqual(c\name,c\nameLength,":status")
     If c\valueLength<>3 : ProcedureReturn -9102 : EndIf
     PokeI(p,(PeekA(c\value)-48)*100+(PeekA(c\value+1)-48)*10+PeekA(c\value+2)-48)
    EndIf
   EndIf
   If rc=#H2_DATA
    n=PeekI(p+16)
    If n+c\dataBytes>131072 : ProcedureReturn -9103 : EndIf
    For i=0 To c\dataBytes-1 : PokeA($E1C01000+slot*131072+n+i,PeekA(c\data+i)) : Next
    PokeI(p+16,n+c\dataBytes)
   EndIf
   If rc=#H2_END : ended=ended+1 : PokeI(p+24,1) : EndIf
   If rc=#H2_RESET Or rc=#H2_GOAWAY : ProcedureReturn -9104 : EndIf
   rc=H2ClientConsume(@c) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If c\state=3 And c\txLength=0 And c\event=0 And sent<2
   If sent=0 : rc=H2ClientGet(@c,"/uuid",5) : Else : rc=H2ClientGet(@c,"/bytes/70000",12) : EndIf
   If c\activeStreams>peak : peak=c\activeStreams : EndIf
   If rc>0 : sent=sent+1 : Else : If rc<>#H2_BUSY : ProcedureReturn rc : EndIf : EndIf
  EndIf
 Wend
 PokeI($E1C00038,peak) : PokeI($E1C00010,sent) : PokeI($E1C00018,ended) : PokeI($E1C00020,maxStep) : PokeI($E1C00028,maxService) : PokeI($E1C00030,clock()-started)
 If ended<>2 : ProcedureReturn -9105 : EndIf
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
 PokeI($E1C00000,$48324832)
 rc=Probe() : PokeI($E1C00008,rc)
 H2ClientClose(@c)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 if cancel_first:
  s=s.replace('n.i,peak.i','n.i,peak.i,cancelled.i')
  s=s.replace('now=clock() : rc=H2ClientStep(@c,now)','If sent=2 And cancelled=0 And c\\txLength=0 And c\\event=0\n   rc=H2ClientCancelStream(@c,1) : If rc<>0 : ProcedureReturn rc : EndIf\n   cancelled=1 : PokeI($E1C00040,1)\n  EndIf\n  now=clock() : rc=H2ClientStep(@c,now)')
  s=s.replace('H2ClientGet(@c,"/uuid",5)','H2ClientGet(@c,"/delay/5",8)')
  s=s.replace('If rc=#H2_RESET Or rc=#H2_GOAWAY : ProcedureReturn -9104 : EndIf','If rc=#H2_GOAWAY : ProcedureReturn -9104 : EndIf\n   If rc=#H2_RESET\n    If slot<>0 Or cancelled<>1 : ProcedureReturn -9104 : EndIf\n    ended=ended+1 : PokeI(p+24,2)\n   EndIf')
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1cfffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--cancel-first',action='store_true')
    a=ap.parse_args();build(a.compiler,a.out.resolve(),a.cancel_first)
