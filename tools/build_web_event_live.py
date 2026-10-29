"""Compile live verified HTTPS server-sent events."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=['three-live-events']
    names=['Anvil/Network/web_client.pbi','Anvil/Network/web_event_stream.pbi','RaspberryPi4/Lib/mmu.pi4']
    s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global u.WebUrl,q.WebRequest,a.WebResponse,client.WebClient,f.WebEventStream
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim qh.a[1024]
Global Dim ah.a[4096]
Global Dim line.a[1024]
Global Dim tx.a[512]
Global Dim rx.a[512]
Global Dim output.a[17]
Global Dim eline.a[256]
Global Dim edata.a[256]
Global Dim ename.a[32]
Global Dim eid.a[64]
Global Dim last.a[64]
Global Dim media.a[128]
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
 Define i.i,rc.i,start.i,n.i,off.i,events.i,p.i,step.i,ready.i,ctype.i,v.i,eof.i,received.i
 CaptureTable()
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$53534C31)
 rc=WebPayloadBind(wtable)
 If rc<>0 : ProcedureReturn 1 : EndIf
 wirePet=PeekI(wtable+16+6*8) : wireTime=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=3072
 v="https://httpbingo.org/sse?delay=0s&duration=2s&count=3"
 n=0 : While PeekA(v+n)<>0 : n=n+1 : Wend
 rc=WebUrlParse(v,n,1,@u)
 If rc=0 : rc=WebRequestInit(@q,@u,"GET",3,0,0,@qh[0],1024) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"User-Agent",10,"Anvil",5) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"Accept",6,"text/event-stream",17) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"Accept-Encoding",15,"identity",8) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 If rc=0 : rc=WebResponseInit(@a,@line[0],1024,@ah[0],4096,0) : EndIf
 If rc=0 : rc=WebEventStreamInit(@f,@eline[0],256,@edata[0],256,@ename[0],32,@eid[0],@last[0],64) : EndIf
 start=wireTime()/1000
 If rc=0 : rc=WebClientStart(@client,@u,@q,@a,@tx[0],512,@rx[0],512,start,15000) : EndIf
 While rc=0
  wirePet() : WebPayloadService(1)
  step=WebClientStep(@client,0,0,1,@output[0],17,wireTime()/1000)
  If step<0 : rc=step : Break : EndIf
  If ready=0 And a\state>=#WEB_RESPONSE_LENGTH
   For i=0 To 1023 : PokeA($E1C01000+i,ah[i]) : Next
   For i=0 To client\written-1 : PokeA($E1C01400+i,output[i]) : Next
   ctype=WebResponseHeader(@a,"content-type",0,@media[0],128)
   If a\status<>200 Or ctype<17 : rc=-990 : Break : EndIf
   If wqEqual(@media[0],17,"text/event-stream")=0 : rc=-991 : Break : EndIf
   If ctype>17 And media[17]<>59 : rc=-992 : Break : EndIf
   v=WebResponseHeader(@a,"content-encoding",0,@media[0],128)
   If v<>#WEB_RESPONSE_NOTFOUND : rc=-993 : Break : EndIf
   ready=1
  EndIf
  n=client\written : received=received+n : off=0
  While off<n
   rc=WebEventStreamFeed(@f,@output[off],n-off) : off=off+f\consumed
   If rc<0 : Break : EndIf
   If rc=1
    If events>=3 Or f\dataLength>192 Or f\eventLength>16 : rc=-994 : Break : EndIf
    p=$E1C00100+events*256
    PokeI(p,f\dataLength) : PokeI(p+8,f\eventLength) : PokeI(p+16,wireTime()/1000-start) : PokeI(p+24,step)
    For i=0 To f\dataLength-1 : PokeA(p+32+i,edata[i]) : Next
    For i=0 To f\eventLength-1 : PokeA(p+224+i,ename[i]) : Next
    events=events+1 : rc=WebEventStreamNext(@f)
   EndIf
  Wend
  If rc<0 : Break : EndIf
  If step=1 : eof=WebEventStreamEof(@f) : rc=1 : Break : EndIf
  If wireTime()/1000-start>15000 : rc=-995 : Break : EndIf
 Wend
 PokeI($E1C00008,rc) : PokeI($E1C00010,a\status) : PokeI($E1C00018,events)
 PokeI($E1C00020,wireTime()/1000-start) : PokeI($E1C00028,eof) : PokeI($E1C00030,received)
 WebClientClose(@client)
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
