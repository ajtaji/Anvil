"""Compile live verified HTTPS content tests with per-service TLS phase timing."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,cancel_handshakes=False,cancel_preparation=False,profile_root_file=False):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=['gzip','deflate']
    names=['Anvil/Core/crc_constants.pbi', 'Anvil/Core/crc.pbi', 'Anvil/Network/web_url.pbi', 'Anvil/Network/web_request.pbi', 'Anvil/Network/web_response.pbi', 'Anvil/Network/web_transport.pbi', 'Anvil/Network/web_client.pbi', 'Anvil/Network/web_inflate.pbi', 'Anvil/Network/web_content.pbi', 'Anvil/Network/web_content_response.pbi', 'RaspberryPi4/Lib/mmu.pi4']
    s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global u.WebUrl,q.WebRequest,a.WebResponse,client.WebClient,content.WebContent
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim qh.a[1024]
Global Dim ah.a[4096]
Global Dim line.a[1024]
Global Dim tx.a[512]
Global Dim rx.a[512]
Global Dim encoded.a[128]
Global Dim decoded.a[128]
Global Dim history.a[32768]
Global Dim workspace.i[1376]
Global *wirePet,*wireTime
Global wtable.i
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure Run(index.i,url.i,bytes.i)
 Define rc.i,start.i,p.i,i.i,out.i,httpRc.i,ready.i,encLen.i,encOff.i,steps.i,cap.i,began.i,duration.i,startCost.i,stepCost.i,serviceCost.i,decodeCost.i,lastState.i,nextState.i,slot.i
 p=$E1C00100+index*4096
 For i=0 To 4095 : PokeA(p+i,0) : Next
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=3072
 rc=WebUrlParse(url,bytes,1,@u)
 If rc=0 : rc=WebRequestInit(@q,@u,"GET",3,0,1,@qh[0],1024) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"User-Agent",10,"Anvil",5) : EndIf
 If rc=0 : rc=WebRequestHeader(@q,"Accept-Encoding",15,"gzip, deflate",13) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@q) : EndIf
 If rc=0 : rc=WebResponseInit(@a,@line[0],1024,@ah[0],4096,0) : EndIf
 start=wireTime()/1000
 began=wireTime()
 If rc=0 : rc=WebClientStart(@client,@u,@q,@a,@tx[0],512,@rx[0],512,start,20000) : EndIf
 startCost=wireTime()-began
 lastState=1
 While rc=0
  wirePet() : began=wireTime() : WebPayloadService(1)
  duration=wireTime()-began : If duration>serviceCost : serviceCost=duration : EndIf
  slot=p+128+lastState*16
  If lastState>=1 And lastState<=5
   If duration>PeekI(slot) : PokeI(slot,duration) : EndIf
  EndIf
  began=wireTime() : nextState=webpTlsState(client\connection\handle) : duration=wireTime()-began
  If lastState>=1 And lastState<=5
   If duration>PeekI(slot+8) : PokeI(slot+8,duration) : EndIf
  EndIf
  lastState=nextState
  If encOff=encLen And httpRc<>1
   encOff=0
   began=wireTime()
   httpRc=WebClientStep(@client,0,0,1,@encoded[0],128,wireTime()/1000)
   duration=wireTime()-began : If duration>stepCost : stepCost=duration : EndIf
   encLen=client\written
   If httpRc<0 : rc=httpRc : Break : EndIf
  EndIf
  If ready=0 And a\state>=#WEB_RESPONSE_LENGTH
   rc=WebContentFromResponse(@content,@a,@history[0],32768,@workspace[0],11008,65536)
   If rc<0 : Break : EndIf
   ready=1
  EndIf
  If ready
   cap=17 : If steps % 3=0 : cap=0 : EndIf
   began=wireTime()
   rc=WebContentFeed(@content,@encoded[encOff],encLen-encOff,Bool(httpRc=1),@decoded[0],cap)
   duration=wireTime()-began : If duration>decodeCost : decodeCost=duration : EndIf
   encOff=encOff+content\consumed
   For i=0 To content\written-1 : If out<2048 : PokeA(p+1024+out,decoded[i]) : EndIf : out=out+1 : Next
  EndIf
  steps=steps+1
  If wireTime()/1000-start>20000 : rc=-552 : Break : EndIf
 Wend
 PokeI(p,rc) : PokeI(p+8,a\status) : PokeI(p+16,content\mode) : PokeI(p+24,out) : PokeI(p+32,wireTime()/1000-start)
 PokeI(p+40,a\bodyBytes) : PokeI(p+48,content\members) : PokeI(p+56,steps)
 PokeI(p+64,startCost) : PokeI(p+72,stepCost) : PokeI(p+80,serviceCost) : PokeI(p+88,decodeCost)
 WebClientClose(@client)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57434431)
 rc=WebPayloadBind(wtable) : PokeI($E1C00010,rc)
 If rc<>0 : ProcedureReturn 1 : EndIf
 *wirePet=PeekI(wtable+16+6*8) : *wireTime=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 Run(0,"https://httpbingo.org/gzip",26)
 Run(1,"https://httpbingo.org/deflate",29)
 PokeI($E1C00008,2)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
    if cancel_handshakes:
        s=s.replace(' Define i.i,rc.i\n CaptureTable()', ' Define i.i,rc.i,h.i,st.i,began.i,cost.i,start.i\n CaptureTable()')
        s=s.replace(' MmuEnableCached()', ''' MmuEnableCached()
 PokeI($E1C00018,$43414E31)
 For i=0 To 1
  h=webpTlsOpen("httpbingo.org",443)
  PokeI($E1C03000+i*64,h)
  start=wireTime()/1000 : st=0 : cost=0
  While h>0 And wireTime()/1000-start<5000
   wirePet() : began=wireTime() : st=webpTlsState(h) : cost=wireTime()-began
   If st<0 Or st=4 : Break : EndIf
   If st=2+i And cost>=1500 : Break : EndIf
   WebPayloadService(1)
  Wend
  PokeI($E1C03008+i*64,st) : PokeI($E1C03010+i*64,cost)
  PokeI($E1C03018+i*64,webpTlsClose(h))
  PokeI($E1C03020+i*64,webpTlsState(h))
 Next
''')
    if cancel_preparation:
        assert not cancel_handshakes
        s=s.replace(' Define i.i,rc.i\n CaptureTable()', ' Define i.i,rc.i,h.i,st.i,began.i,cost.i\n CaptureTable()')
        s=s.replace(' MmuEnableCached()', ''' MmuEnableCached()
 PokeI($E1C00018,$43414E30)
 For i=0 To 1
  began=wireTime() : h=webpTlsOpen("httpbingo.org",443) : cost=wireTime()-began
  PokeI($E1C03000+i*64,h) : PokeI($E1C03028+i*64,cost)
  st=0 : cost=0
  If i=1
   began=wireTime() : st=webpTlsState(h) : cost=wireTime()-began
  EndIf
  PokeI($E1C03008+i*64,st) : PokeI($E1C03010+i*64,cost)
  PokeI($E1C03018+i*64,webpTlsClose(h))
  PokeI($E1C03020+i*64,webpTlsState(h))
 Next
''')
    if profile_root_file:
        assert cancel_preparation and not cancel_handshakes
        s=s.replace('Global wtable.i','Global *rootOpen,*rootSize,*rootRead,*rootClose\nGlobal Dim rootChunk.a[4096]\nGlobal wtable.i')
        s=s.replace(' PokeI($E1C00018,$43414E30)', ''' PokeI($E1C00020,$524F4F54)
 rootOpen=PeekI(wtable+16+49*8) : rootSize=PeekI(wtable+16+50*8)
 rootRead=PeekI(wtable+16+51*8) : rootClose=PeekI(wtable+16+52*8)
 For i=0 To 1
  began=wireTime() : rc=rootOpen("2:/tls/roots.pem") : cost=wireTime()-began
  PokeI($E1C03100+i*64,rc) : PokeI($E1C03108+i*64,cost)
  If rc=1
   PokeI($E1C03110+i*64,rootSize())
   began=wireTime() : rc=rootRead(0,@rootChunk[0],4096) : cost=wireTime()-began
   PokeI($E1C03118+i*64,rc) : PokeI($E1C03120+i*64,cost)
   rootClose()
  EndIf
 Next
 PokeI($E1C00018,$43414E30)''')
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names+['Anvil/Network/tcp_dial.pbi','Anvil/Network/ipv6_address.pbi']},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cancel-handshakes',action='store_true')
    ap.add_argument('--cancel-preparation',action='store_true')
    ap.add_argument('--profile-root-file',action='store_true')
    args=ap.parse_args();build(args.compiler,args.out.resolve(),args.cancel_handshakes,args.cancel_preparation,args.profile_root_file)
