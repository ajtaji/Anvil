"""Build live secure WebSocket echo qualification for physical Pi4.
Uses resident ABI1.10 hardware-seeded randomness for nonces and masks.
No desktop entropy pool, fixed masks, or unverified TLS.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/websocket_frame.pbi','Anvil/Network/websocket_handshake.pbi','Anvil/Crypto/sha1.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/web_client.pbi','Anvil/Network/websocket_client.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_random.pbi']
    cases=['secure-resident-echo']
    s='#WEB_KERNEL_BINDING=0\n'+'\n'.join(x for n in names for x in (root/n).read_text(encoding='utf8').splitlines() if not x.startswith(('XIncludeFile','#WEB_KERNEL_BINDING=')))+r'''
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
Global Dim nonce.a[16]
Global Dim closeCode.a[2]
Global randomBytesUsed.i,wtable.i
Global *wirePet,*wireTime
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Main()
 Define i.i,rc.i,start.i,now.i,queued.i,closing.i,frames.i,total.i,began.i,cost.i,maxCost.i,url.i
 CaptureTable()
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57534C31)
 rc=WebPayloadBind(wtable) : PokeI($E1C00008,rc)
 If rc<>0 : ProcedureReturn 1 : EndIf
 *wirePet=PeekI(wtable+16+6*8) : *wireTime=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 rc=WebRandomBind(wtable) : PokeI($E1C00060,rc)
 If rc=0 : rc=WebRandomReady() : EndIf
 PokeI($E1C00068,rc)
 If rc<>1 : MmuDisableCachedFlushed() : ProcedureReturn 3 : EndIf
 began=wireTime() : rc=WebRandomBytes(@nonce[0],16) : randomBytesUsed=rc
 PokeI($E1C00070,wireTime()-began)
 If rc<>16 : MmuDisableCachedFlushed() : ProcedureReturn 4 : EndIf
 closeCode[0]=3 : closeCode[1]=232
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=3072
 url="wss://httpbingo.org/websocket/echo"
 rc=WebSocketUrlParse(url,34,0,@u,@scratch[0],512)
 If rc=0 : rc=WebSocketRequestInit(@q,@u,@headers[0],1024,@nonce[0],@key[0],@accept[0],@scratch[0]) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"User-Agent",10,"Anvil",5) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 If rc=0 : rc=WebResponseInit(@a,@line[0],512,@response[0],2048,0) : EndIf
 If rc=0 : rc=WebResponseAllowUpgrade(@a) : EndIf
 If rc=0 : rc=WebSocketFrameInit(@f,@ctrl[0],1024) : EndIf
 start=wireTime()/1000
 If rc=0 : rc=WebClientStart(@h,@u,@q,@a,@tx[0],512,@rx[0],512,start,10000) : EndIf
 If rc=0 : rc=WebSocketClientBind(@ws,@h,@f,@accept[0],0,0,webRandomBytesFn,@scratch[0]) : EndIf
 While rc>=0 And rc<>2
  wirePet() : WebPayloadService(1) : now=wireTime()/1000
  began=wireTime() : rc=WebSocketClientStep(@ws,@output[0],3,now)
  cost=wireTime()-began : If cost>maxCost : maxCost=cost : EndIf
  For i=0 To ws\written-1
   If total<1024 : PokeA($E1C00100+total,output[i]) : EndIf
   total=total+1
  Next
  If rc=1 : frames=frames+1 : EndIf
  If rc>=0 And ws\state=1 And queued=0
   rc=WebSocketClientSend(@ws,1,"Anvil websocket",15,now) : queued=1
  ElseIf rc=1 And ws\fin And total=15 And closing=0
   rc=WebSocketClientSend(@ws,8,@closeCode[0],2,now) : closing=1
  EndIf
  If now-start>12000 : rc=-999 : Break : EndIf
 Wend
 PokeI($E1C00010,rc) : PokeI($E1C00018,ws\state) : PokeI($E1C00020,a\status)
 PokeI($E1C00028,total) : PokeI($E1C00030,frames) : PokeI($E1C00038,wireTime()/1000-start)
 PokeI($E1C00040,maxCost) : PokeI($E1C00048,randomBytesUsed) : PokeI($E1C00050,u\secure)
 PokeI($E1C00058,f\controlLength)
 For i=0 To f\controlLength-1 : PokeA($E1C00600+i,ctrl[i]) : Next
 If rc<>2 : WebSocketClientAbort(@ws) : EndIf
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
