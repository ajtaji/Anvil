"""Compile physical CPU qualification with a deliberately fragmented fake transport."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=json.loads((root/'tools/h2_upload_cases.json').read_text())
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_url.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/h2_frame.pbi','Anvil/Network/hpack_decode.pbi','Anvil/Network/hpack_tables.pbi','Anvil/Network/h2_client.pbi','Anvil/Network/h2_request.pbi','Anvil/Network/web_request.pbi']
 s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''

Global services.i
Global *pet,*clock
Global c.H2Client
Global buffers.H2Buffers
Global url.WebUrl
Global request.WebRequest
Global Dim tx.a[16384]
Global Dim rx.a[16384]
Global Dim block.a[65536]
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global Dim streams.a[2048]
Global Dim headers.a[32768]
Global Dim body.a[70001]
Global Dim large.a[1000]
Global Dim incoming.a[8192]
Global Dim outgoing.a[131072]
Global Dim gateAt.i[64]
Global Dim gateBytes.i[64]
Global inBytes.i,inAt.i,outBytes.i,sendCalls.i,recvCalls.i,closeCalls.i,mode.i,goal.i,gateCount.i
Procedure.i FakeOpen(host.i,port.i,offer.i,bytes.i)
 ProcedureReturn 1
EndProcedure
Procedure.i FakeState(handle.i)
 ProcedureReturn 4
EndProcedure
Procedure.i FakeAlpn(handle.i,destination.i,capacity.i)
 PokeA(destination,104) : PokeA(destination+1,50) : ProcedureReturn 2
EndProcedure
Procedure.i FakeClose(handle.i)
 closeCalls=closeCalls+1 : ProcedureReturn 0
EndProcedure
Procedure.i FakeSend(handle.i,source.i,bytes.i)
 Define i.i,n.i
 sendCalls=sendCalls+1 : If (sendCalls % 4)=0 : ProcedureReturn 0 : EndIf
 n=bytes : If n>97 : n=97 : EndIf
 If outBytes+n>131072 : ProcedureReturn -9301 : EndIf
 For i=0 To n-1 : outgoing[outBytes+i]=PeekA(source+i) : Next
 outBytes=outBytes+n : ProcedureReturn n
EndProcedure
Procedure.i FakeRecv(handle.i,destination.i,bytes.i)
 Define i.i,n.i,at.i,length.i,uploaded.i,ready.i,ended.i,required.i,kind.i,flags.i
 recvCalls=recvCalls+1 : If (recvCalls % 3)=0 : ProcedureReturn 0 : EndIf
 at=24 : uploaded=0 : ready=0 : ended=0
 While at+9<=outBytes
  length=(outgoing[at]<<16)|(outgoing[at+1]<<8)|outgoing[at+2]
  If at+9+length>outBytes : Break : EndIf
  kind=outgoing[at+3] : flags=outgoing[at+4]
  If (kind=1 Or kind=9) And (flags & 4)<>0 : ready=1 : EndIf
  If (kind=1 Or kind=0) And (flags & 1)<>0 : ended=1 : EndIf
  If kind=0 : uploaded=uploaded+length : EndIf
  at=at+9+length
 Wend
 required=-1
 For i=0 To gateCount-1
  If inAt>=gateAt[i] : required=gateBytes[i] : EndIf
 Next
 If required<>-1
  If ready=0 : ProcedureReturn 0 : EndIf
  If required=-2
   If ended=0 : ProcedureReturn 0 : EndIf
  Else
   If uploaded<required : ProcedureReturn 0 : EndIf
  EndIf
 EndIf
 n=inBytes-inAt : If n>bytes : n=bytes : EndIf : If n>5 : n=5 : EndIf
 For i=0 To n-1 : PokeA(destination+i,incoming[inAt+i]) : Next
 inAt=inAt+n : ProcedureReturn n
EndProcedure
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure



Procedure.i RunOne(index.i)
 Define rc.i,tick.i,submitted.i,ended.i,position.i,i.i,p.i,n.i,method.i,methodBytes.i,length.i,bodyBytes.i,status.i,busy.i
 inAt=0 : outBytes=0 : sendCalls=0 : recvCalls=0 : closeCalls=0
 For i=0 To 70000 : body[i]=97 : Next
 For i=0 To 999 : large[i]=76 : Next
 If mode=2 : For i=0 To 16 : body[i]=i : Next : EndIf
 url\secure=1 : url\host="example.org" : url\hostLength=11 : url\port=443 : url\target="/upload" : url\targetLength=7
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 method="POST" : methodBytes=4 : length=goal
 If mode=2 Or mode=3 : length=-1 : EndIf
 If mode=4 : method="HEAD" : EndIf
 If mode=5 : method="GET" : methodBytes=3 : EndIf
 If mode=7 : url\host="foreign.org" : EndIf
 rc=WebRequestInit(@request,@url,method,methodBytes,length,0,@headers[0],32768) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestHeader(@request,"X-Test",6,"  value  ",9) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WebRequestHeader(@request,"Cookie",6,"a=b; c=d",8) : If rc<>0 : ProcedureReturn rc : EndIf
 If mode=5
  For i=0 To 30
   rc=WebRequestHeader(@request,"X-Large",7,@large[0],1000) : If rc<>0 : ProcedureReturn rc : EndIf
  Next
 EndIf
 If mode=8 : rc=WebRequestHeader(@request,"TE",2,"gzip",4) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
 rc=WebRequestFinishHeaders(@request) : If rc<>0 : ProcedureReturn rc : EndIf
 url\host="example.org"
 rc=H2ClientStart(@c,@url,@buffers,0,200000) : If rc<>0 : ProcedureReturn rc : EndIf
 For tick=1 To 100000
  pet() : rc=H2ClientStep(@c,tick)
  If rc<0 : Break : EndIf
  If rc>0
   If rc=#H2_FIELD And h2cEqual(c\name,c\nameLength,":status")
    status=(PeekA(c\value)-48)*100+(PeekA(c\value+1)-48)*10+PeekA(c\value+2)-48
   EndIf
   If rc=#H2_DATA : bodyBytes=bodyBytes+c\dataBytes : EndIf
   If rc=#H2_END : ended=1 : EndIf
   If rc=#H2_RESET Or rc=#H2_GOAWAY : rc=-9302 : Break : EndIf
   rc=H2ClientConsume(@c) : If rc<>0 : Break : EndIf
  EndIf
  If ended<>0 And c\txLength=0 : rc=0 : Break : EndIf
  If submitted=0 And c\state=3 And c\txLength=0
   rc=H2ClientRequest(@c,@request)
   If rc<0 : Break : EndIf
   If rc<>1 : rc=-9303 : Break : EndIf
   submitted=1
  EndIf
  If submitted<>0 And request\state<>2 And ended=0
   rc=H2ClientData(@c,1,@body[0]+position,goal-position,1)
   If rc=#H2_BUSY
    busy=busy+1
   Else
    If rc<0 : Break : EndIf
    position=position+rc
   EndIf
  EndIf
 Next
 If tick>100000 : rc=-9304 : EndIf
 p=$E1C00100+index*120000
 PokeI(p,rc) : PokeI(p+8,position) : PokeI(p+16,bodyBytes) : PokeI(p+24,status)
 PokeI(p+32,outBytes) : PokeI(p+40,request\state) : PokeI(p+48,request\offset) : PokeI(p+56,busy)
 PokeI(p+72,c\nextStream) : PokeI(p+80,c\activeStreams)
 If outBytes>100000 : ProcedureReturn -9305 : EndIf
 For i=0 To outBytes-1 : PokeA(p+256+i,outgoing[i]) : Next
 H2ClientClose(@c) : PokeI(p+64,closeCalls)
 ProcedureReturn 0
EndProcedure
Procedure RunCases()
 Define index.i,i.i,n.i,v.i
 webpTlsOpenAlpn=@FakeOpen : webpTlsState=@FakeState : webpTlsAlpn=@FakeAlpn : webpTlsClose=@FakeClose : webpTlsSend=@FakeSend : webpTlsRecv=@FakeRecv
 Restore Cases : Read.i n : PokeI($E1C00008,n)
 For index=0 To n-1
  Read.i mode : Read.i goal : Read.i inBytes : Read.i gateCount
  For i=0 To gateCount-1 : Read.i v : gateAt[i]=v : Read.i v : gateBytes[i]=v : Next
  For i=0 To inBytes-1 : Read.i v : incoming[i]=v : Next
  RunOne(index)
 Next
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
 PokeI($E1C00000,$48325550)
 RunCases()
 H2ClientClose(@c)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 s+='\nDataSection\nCases:\n Data.i '+str(len(rows))+'\n'
 for row in rows:
  wire=bytes.fromhex(row['wire'])
  s+=' Data.i '+str(row['mode'])+','+str(row['goal'])+','+str(len(wire))+','+str(len(row['gates']))+'\n'
  for at,gate in row['gates']:s+=' Data.i '+str(at)+','+str(gate)+'\n'
  for first in range(0,len(wire),24):s+=' Data.i '+','.join(map(str,wire[first:first+24]))+'\n'
 s+='EndDataSection\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1cfffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
