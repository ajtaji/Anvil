"""Compile a full-record HTTPS POST and independent echoed-body verification."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=['32768-byte-post']
    names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/web_client.pbi','Anvil/Network/web_event_stream.pbi','RaspberryPi4/Lib/mmu.pi4']
    s=r'''#WEB_KERNEL_BINDING=0
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
XIncludeFile "Anvil/Network/web_client.pbi"
XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
Global u.WebUrl,q.WebRequest,a.WebResponse,c.WebClient
Global Dim host.a[256]
Global Dim target.a[1024]
Global Dim qh.a[1024]
Global Dim ah.a[4096]
Global Dim line.a[1024]
Global Dim tx.a[16384]
Global Dim rx.a[4096]
Global Dim out.a[1024]
Global Dim body.a[32768]
Global *pet,*clock
Global table.i
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Main()
 Define i.i,j.i,rc.i,v.i,n.i,start.i,offset.i,total.i,t.i,elapsed.i,maxStep.i,maxService.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$54534E31)
 rc=WebPayloadBind(table) : If rc<>0 : ProcedureReturn 1 : EndIf
 pet=PeekI(table+16+6*8) : clock=PeekI(table+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 For i=0 To 32767 : body[i]=65+(i % 26) : Next
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=1024
 v="https://httpbingo.org/post" : n=0 : While PeekA(v+n)<>0 : n=n+1 : Wend
 rc=WebUrlParse(v,n,1,@u)
 If rc=0 : rc=WebRequestInit(@q,@u,"POST",4,32768,0,@qh[0],1024) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"User-Agent",10,"Anvil",5) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"Content-Type",12,"text/plain",10) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"Accept-Encoding",15,"identity",8) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 If rc=0 : rc=WebResponseInit(@a,@line[0],1024,@ah[0],4096,0) : EndIf
 start=clock()/1000
 If rc=0 : rc=WebClientStart(@c,@u,@q,@a,@tx[0],16384,@rx[0],4096,start,30000) : EndIf
 While rc=0
  pet() : t=clock() : WebPayloadService(1) : elapsed=clock()-t
  If elapsed>maxService : maxService=elapsed : EndIf
  t=clock() : rc=WebClientStep(@c,@body[0]+offset,32768-offset,1,@out[0],1024,clock()/1000)
  elapsed=clock()-t : If elapsed>maxStep : maxStep=elapsed : EndIf
  offset=offset+c\consumed
  If total+c\written>60000 : rc=-999 : Break : EndIf
  For j=0 To c\written-1 : PokeA($E1C00100+total+j,out[j]) : Next
  total=total+c\written
 Wend
 PokeI($E1C00008,rc) : PokeI($E1C00010,a\status) : PokeI($E1C00018,offset)
 PokeI($E1C00020,total) : PokeI($E1C00028,maxStep) : PokeI($E1C00030,maxService)
 PokeI($E1C00038,clock()/1000-start)
 WebClientClose(@c) : MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
'''
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
