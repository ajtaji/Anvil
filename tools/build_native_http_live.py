"""Build the native HTTP command procedure over resident network services."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out,url):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 assert url.startswith('http://') and len(url)<200 and '"' not in url
 names=['Anvil/Network/web_client.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_response.pbi','Anvil/Network/ipv6_address.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='#WEB_KERNEL_BINDING=0\nXIncludeFile "Anvil/Network/web_client.pbi"\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+r'''
Global url.WebUrl,request.WebRequest,response.WebResponse,client.WebClient
Global Dim host.a[256]
Global Dim target.a[3072]
Global Dim headers.a[1024]
Global Dim metadata.a[4096]
Global Dim line.a[1024]
Global Dim tx.a[512]
Global Dim rx.a[512]
Global Dim output.a[512]
Global table.i
Global *livePet,*liveTime
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Main()
 Define i.i,n.i,rc.i,start.i,step.i,total.i,text.i
 CaptureTable()
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$48545436)
 rc=WebPayloadBind(table) : If rc<>0 : PokeI($E1C00008,rc) : ProcedureReturn 0 : EndIf
 livePet=PeekI(table+16+6*8) : liveTime=PeekI(table+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 url\host=@host[0] : url\hostCapacity=256 : url\target=@target[0] : url\targetCapacity=3072
'''
 s+=' text="'+url+'"\n'
 s+=r'''
 n=0 : While PeekA(text+n)<>0 : n=n+1 : Wend
 rc=WebUrlParse(text,n,0,@url)
 If rc=0 : rc=WebRequestInit(@request,@url,"GET",3,0,0,@headers[0],1024) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@request) : EndIf
 If rc=0 : rc=WebResponseInit(@response,@line[0],1024,@metadata[0],4096,0) : EndIf
 start=liveTime()/1000
 If rc=0 : rc=WebClientStart(@client,@url,@request,@response,@tx[0],512,@rx[0],512,start,10000) : EndIf
 While rc=0
  livePet() : WebPayloadService(1)
  step=WebClientStep(@client,0,0,1,@output[0],512,liveTime()/1000)
  If step<0 : rc=step : Break : EndIf
  If total+client\written>65536 : rc=-999 : Break : EndIf
  For i=0 To client\written-1 : PokeA($E1C00100+total+i,output[i]) : Next
  total=total+client\written
  If step=1 : Break : EndIf
 Wend
 PokeI($E1C00008,rc) : PokeI($E1C00010,response\status) : PokeI($E1C00018,total)
 PokeI($E1C00020,liveTime()/1000-start) : PokeI($E1C00028,client\sent) : PokeI($E1C00030,client\received)
 WebClientClose(@client)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''

 core=(root/'Anvil/Core/tcp_cmd.pbi').read_text(encoding='utf8')
 core=core[core.index('Global httpc_url.'):core.index('\nProcedure CmdHttp()')]
 wrappers=r"""
#TCPCMD_BODY_SHOW=600
Global Dim gHttpBody.a[600]
Global nativeUrl.i
Procedure.i millis()
 ProcedureReturn liveTime()/1000
EndProcedure
Procedure.i ArgRest()
 ProcedureReturn nativeUrl
EndProcedure
Procedure.i HwLinkOpen(kind.i)
 ProcedureReturn 1
EndProcedure
Procedure.i NetBreakCheck()
 ProcedureReturn 0
EndProcedure
Procedure PayNetCommandPump(ms.i)
 livePet() : WebPayloadService(ms)
EndProcedure
Procedure UartDrain()
EndProcedure
Procedure UartWriteStr(p.i)
EndProcedure
Procedure tcp_PutBytes(p.i,n.i)
EndProcedure
Procedure str_print_at(p.i)
EndProcedure
Procedure PrintNl()
EndProcedure
Procedure PrintDec(n.i)
EndProcedure
"""
 s=s[:s.index('Procedure.i Main()')]+wrappers+core+r"""
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 rc=WebPayloadBind(table)
 If rc<>0 : ProcedureReturn 1 : EndIf
 livePet=PeekI(table+16+6*8) : liveTime=PeekI(table+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 nativeUrl="""+'"'+url+'"'+r"""
 http_Get()
 PokeI($E1C00000,httpc_response\status)
 PokeI($E1C00008,httpc_response\bodyBytes)
 PokeI($E1C00010,httpc_client\received)
 PokeI($E1C00018,httpc_client\error)
 For i=0 To 599 : PokeA($E1C00100+i,gHttpBody[i]) : Next
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
"""
 names.append('Anvil/Core/tcp_cmd.pbi')

 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 body=bytes(32+i%95 for i in range(20000))
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=dict(url=url,body_sha256=hashlib.sha256(body).hexdigest(),body_bytes=len(body))),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--url',required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve(),args.url)
