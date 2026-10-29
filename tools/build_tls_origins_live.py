"""Compile simultaneous verified HTTPS requests to different origins."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=['event-stream','example','trace','parallel']
    names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/web_client.pbi','Anvil/Network/web_event_stream.pbi','RaspberryPi4/Lib/mmu.pi4']
    s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global Dim u.WebUrl[4]
Global Dim q.WebRequest[4]
Global Dim a.WebResponse[4]
Global Dim client.WebClient[4]
Global Dim hosts.a[1024]
Global Dim targets.a[4096]
Global Dim qh.a[4096]
Global Dim ah.a[16384]
Global Dim lines.a[4096]
Global Dim tx.a[2048]
Global Dim rx.a[2048]
Global Dim output.a[64]
Global Dim done.i[4]
Global Dim handles.i[4]
Global f.WebEventStream
Global Dim eline.a[256]
Global Dim edata.a[256]
Global Dim ename.a[32]
Global Dim eid.a[64]
Global Dim last.a[64]
Global *wirePet,*wireTime
Global wtable.i
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Main()
 Define i.i,j.i,rc.i,start.i,n.i,v.i,all.i,step.i,p.i,off.i,events.i,h.i,ready.i
 CaptureTable()
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$544D4C31)
 rc=WebPayloadBind(wtable) : If rc<>0 : ProcedureReturn 1 : EndIf
 wirePet=PeekI(wtable+16+6*8) : wireTime=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 rc=WebEventStreamInit(@f,@eline[0],256,@edata[0],256,@ename[0],32,@eid[0],@last[0],64)
 start=wireTime()/1000
 For i=0 To 3
  u[i]\host=@hosts[i*256] : u[i]\hostCapacity=256 : u[i]\target=@targets[i*1024] : u[i]\targetCapacity=1024
  If i=0
   v="https://httpbingo.org/sse?delay=0s&duration=4s&count=3"
  ElseIf i=1
   v="https://example.com/"
  ElseIf i=2
   v="https://www.cloudflare.com/cdn-cgi/trace"
  Else
   v="https://httpbingo.org/base64/cGFyYWxsZWwgSFRUUFMgcmVwbHk="
  EndIf
  n=0 : While PeekA(v+n)<>0 : n=n+1 : Wend
  rc=WebUrlParse(v,n,1,@u[i])
  If rc=0 : rc=WebRequestInit(@q[i],@u[i],"GET",3,0,0,@qh[i*1024],1024) : EndIf
  If rc=0 : rc=WebRequestHeader(@q[i],"User-Agent",10,"Anvil",5) : EndIf
  If rc=0 : rc=WebRequestHeader(@q[i],"Accept-Encoding",15,"identity",8) : EndIf
  If rc=0 : rc=WebRequestFinishHeaders(@q[i]) : EndIf
  If rc=0 : rc=WebResponseInit(@a[i],@lines[i*1024],1024,@ah[i*4096],4096,0) : EndIf
  If rc=0 : rc=WebClientStart(@client[i],@u[i],@q[i],@a[i],@tx[i*512],512,@rx[i*512],512,start,20000) : EndIf
  handles[i]=client[i]\connection\handle
  If rc<0 : Break : EndIf
 Next
 While rc=0
  wirePet() : WebPayloadService(1) : all=1
  For i=0 To 3
   If done[i]=0
    all=0 : p=$E1C00100+i*2048
    step=WebClientStep(@client[i],0,0,1,@output[0],17,wireTime()/1000)
    If step<0 : rc=step : PokeI(p,rc) : Break : EndIf
    n=client[i]\written
    If i=0
     off=0
     While off<n
      rc=WebEventStreamFeed(@f,@output[off],n-off) : off=off+f\consumed
      If rc<0 : Break : EndIf
      If rc=1
       If events>=3 Or f\dataLength>192 Or f\eventLength>16 : rc=-994 : Break : EndIf
       h=$E1C03000+events*256
       PokeI(h,f\dataLength) : PokeI(h+8,f\eventLength) : PokeI(h+16,wireTime()/1000-start) : PokeI(h+24,step)
       For j=0 To f\dataLength-1 : PokeA(h+32+j,edata[j]) : Next
       For j=0 To f\eventLength-1 : PokeA(h+224+j,ename[j]) : Next
       events=events+1 : rc=WebEventStreamNext(@f)
      EndIf
     Wend
    Else
     off=PeekI(p+24)
     If off+n>1536 : rc=-993 : Break : EndIf
     For j=0 To n-1 : PokeA(p+64+off+j,output[j]) : Next
     PokeI(p+24,off+n)
    EndIf
    If rc<0 : Break : EndIf
    If step=1
     done[i]=1 : PokeI(p,1) : PokeI(p+8,a[i]\status) : PokeI(p+16,wireTime()/1000-start)
     If i=0 : rc=WebEventStreamEof(@f) : EndIf
     WebClientClose(@client[i])
    EndIf
   EndIf
  Next
  If rc<0 Or all : Break : EndIf
  If wireTime()/1000-start>20000 : rc=-995 : Break : EndIf
 Wend
 PokeI($E1C00008,rc) : PokeI($E1C00010,events) : PokeI($E1C00018,wireTime()/1000-start)
 For i=0 To 3 : PokeI($E1C00020+i*8,handles[i]) : WebClientClose(@client[i]) : Next
 MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
'''
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
