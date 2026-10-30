"""Compile physical CPU qualification with a deliberately fragmented fake transport."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=json.loads((root/'tools/h2_client_cases.json').read_text())
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_url.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/h2_frame.pbi','Anvil/Network/hpack_decode.pbi','Anvil/Network/hpack_tables.pbi','Anvil/Network/h2_client.pbi']
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

Global Dim incoming.a[131072]
Global Dim outgoing.a[16384]
Global inBytes.i,inAt.i,outBytes.i,sendCalls.i,recvCalls.i,wanted.i,closeCalls.i,mode.i,forceClosed.i
Procedure.i FakeOpen(host.i,port.i,offer.i,bytes.i)
 ProcedureReturn 1
EndProcedure
Procedure.i FakeState(handle.i)
 If forceClosed<>0 : ProcedureReturn 5 : EndIf
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
 n=bytes : If n>3 : n=3 : EndIf
 If outBytes+n>16384 : ProcedureReturn -9201 : EndIf
 For i=0 To n-1 : outgoing[outBytes+i]=PeekA(source+i) : Next
 outBytes=outBytes+n : ProcedureReturn n
EndProcedure
Procedure.i FakeRecv(handle.i,destination.i,bytes.i)
 Define i.i,n.i,at.i,requests.i,length.i,needed.i
 recvCalls=recvCalls+1 : If (recvCalls % 3)=0 And forceClosed=0 : ProcedureReturn 0 : EndIf
 at=24 : requests=0
 While at+9<=outBytes
  length=(outgoing[at]<<16)|(outgoing[at+1]<<8)|outgoing[at+2]
  If at+9+length>outBytes : Break : EndIf
  If outgoing[at+3]=1 : requests=requests+1 : EndIf
  at=at+9+length
 Wend
 needed=wanted : If mode=7 : needed=2 : EndIf
 If inAt>=9 And requests<needed : ProcedureReturn 0 : EndIf
 n=inBytes-inAt : If n>bytes : n=bytes : EndIf : If n>5 : n=5 : EndIf
 If inAt<9 And inAt+n>9 : n=9-inAt : EndIf
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
 Define rc.i,tick.i,sent.i,ended.i,bodyBytes.i,bodySum.i,i.i,p.i,at.i,st.i,busy.i,cancelled.i,shouldCancel.i,eventKind.i
 inAt=0 : outBytes=0 : sendCalls=0 : recvCalls=0 : closeCalls=0 : forceClosed=0
 url\secure=1 : url\host="example.org" : url\hostLength=11 : url\port=443
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 rc=H2ClientStart(@c,@url,@buffers,0,200000)
 If rc<>0 : ProcedureReturn rc : EndIf
 For tick=1 To 100000
  pet()
  If sent=wanted And c\txLength=0
   If mode=1 : rc=H2ClientCancel(@c) : Break : EndIf
   If mode=2 : rc=H2ClientStep(@c,200001) : Break : EndIf
   If mode=3 : forceClosed=1 : EndIf
  EndIf
  shouldCancel=0
  If cancelled=0 And sent>=2 And c\txLength=0 And c\event=0
   If mode=4 : shouldCancel=1 : EndIf
   If (mode=5 Or mode=7) And c\continuation=1 : shouldCancel=1 : EndIf
   If mode=6 And c\decoding<>0 And c\decoder\fields>0 : shouldCancel=1 : EndIf
  EndIf
  If shouldCancel<>0
   rc=H2ClientCancelStream(@c,1) : If rc<>0 : Break : EndIf
   cancelled=1
  EndIf
  rc=H2ClientStep(@c,tick)
  If rc<0 : Break : EndIf
  If rc>0
   eventKind=rc : at=inAt : st=rc
   If H2ClientStep(@c,tick)<>st Or inAt<>at : rc=-9202 : Break : EndIf
   busy=H2ClientGet(@c,"/forbidden",10)
   If busy<>#H2_BUSY And c\goaway=0 : rc=-9203 : Break : EndIf
   If rc=#H2_DATA Or rc=#H2_FIELD
    If H2ClientCancelStream(@c,c\eventStream)<>#H2_BUSY : rc=-9206 : Break : EndIf
   EndIf
   If rc=#H2_DATA
    bodyBytes=bodyBytes+c\dataBytes
    For i=0 To c\dataBytes-1 : bodySum=bodySum+PeekA(c\data+i) : Next
   EndIf
   If rc=#H2_END : ended=ended+1 : EndIf
   If rc=#H2_GOAWAY : Break : EndIf
   If rc=#H2_RESET
    If mode<4 : Break : EndIf
    ended=ended+1
   EndIf
   at=c\eventStream
   rc=H2ClientConsume(@c) : If rc<>0 : Break : EndIf
   If mode>=4 And (eventKind=#H2_RESET Or eventKind=#H2_END)
    rc=H2ClientRelease(@c,at) : If rc<>0 : Break : EndIf
   EndIf
  EndIf
  If ended=wanted And c\txLength=0 : rc=0 : Break : EndIf
  If c\state=3 And c\txLength=0 And c\event=0 And sent<wanted And (mode<>7 Or sent<2 Or cancelled<>0)
   rc=H2ClientGet(@c,"/test?x=1",9)
   If rc>0
    sent=sent+1
    If H2ClientCancelStream(@c,rc)<>#H2_BUSY : rc=-9207 : Break : EndIf
   Else
    If rc<>#H2_BUSY : Break : EndIf
   EndIf
  EndIf
 Next
 If tick>100000 : rc=-9204 : EndIf
 p=$E1C00100+index*8192
 PokeI(p,rc) : PokeI(p+8,bodyBytes) : PokeI(p+16,bodySum) : PokeI(p+24,ended) : PokeI(p+32,outBytes) : PokeI(p+40,sendCalls) : PokeI(p+48,recvCalls) : PokeI(p+56,tick)
 If outBytes>7000 : ProcedureReturn -9205 : EndIf
 For i=0 To outBytes-1 : PokeA(p+256+i,outgoing[i]) : Next
 H2ClientClose(@c) : PokeI(p+64,closeCalls)
 ProcedureReturn 0
EndProcedure
Procedure RunCases()
 Define index.i,i.i,n.i,v.i
 webpTlsOpenAlpn=@FakeOpen : webpTlsState=@FakeState : webpTlsAlpn=@FakeAlpn : webpTlsClose=@FakeClose : webpTlsSend=@FakeSend : webpTlsRecv=@FakeRecv
 Restore Cases : Read.i n : PokeI($E1C00008,n)
 For index=0 To n-1
  Read.i wanted : Read.i inBytes : Read.i mode
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
 PokeI($E1C00000,$48324843)
 RunCases()
 H2ClientClose(@c)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 s+='\nDataSection\nCases:\n Data.i '+str(len(rows))+'\n'
 for row in rows:
  wire=bytes.fromhex(row['wire'])
  s+=' Data.i '+str(row['requests'])+','+str(len(wire))+','+str(row.get('mode',0))+'\n'
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
