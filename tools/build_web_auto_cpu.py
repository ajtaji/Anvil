"""Compile physical CPU qualification with a deliberately fragmented fake transport."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,cases=None,transform=None):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=json.loads((root/'tools/web_auto_cases.json').read_text()) if cases is None else cases
 names=['RaspberryPi4/Lib/mmu.pi4', 'Anvil/Network/web_url.pbi', 'Anvil/Network/web_transport.pbi', 'Anvil/Network/h2_frame.pbi', 'Anvil/Network/hpack_decode.pbi', 'Anvil/Network/hpack_tables.pbi', 'Anvil/Network/h2_client.pbi', 'Anvil/Network/h2_request.pbi', 'Anvil/Network/web_request.pbi', 'Anvil/Network/web_response.pbi', 'Anvil/Network/web_client.pbi', 'Anvil/Network/tcp_dial.pbi', 'Anvil/Network/ipv6_address.pbi']
 s=r'''#WEB_KERNEL_BINDING=0
XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
XIncludeFile "Anvil/Network/h2_frame.pbi"
XIncludeFile "Anvil/Network/hpack_decode.pbi"
XIncludeFile "Anvil/Network/hpack_tables.pbi"
XIncludeFile "Anvil/Network/h2_client.pbi"
XIncludeFile "Anvil/Network/h2_request.pbi"
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_client.pbi"
XIncludeFile "Anvil/Network/tcp_dial.pbi"
XIncludeFile "Anvil/Network/ipv6_address.pbi"
Global services.i
Global *pet
Global c.H2Client
Global client.WebClient
Global buffers.H2Buffers
Global url.WebUrl
Global request.WebRequest,request2.WebRequest
Global response.WebResponse,response2.WebResponse
Global Dim tx.a[16384]
Global Dim rx.a[16384]
Global Dim block.a[65536]
Global Dim controls.a[1024]
Global Dim requestBlock.a[65536]
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global Dim streams.a[2048]
Global Dim headers.a[2048]
Global Dim headers2.a[2048]
Global Dim line.a[8192]
Global Dim line2.a[8192]
Global Dim metadata.a[4096]
Global Dim metadata2.a[4096]
Global Dim result.a[512]
Global Dim lookup.a[32]
Global Dim body.a[70001]
Global Dim incoming.a[8192]
Global Dim outgoing.a[131072]
Global Dim gateAt.i[64]
Global Dim gateBytes.i[64]
Global Dim offer.a[32]
Global inBytes.i,inAt.i,outBytes.i,sendCalls.i,recvCalls.i,closeCalls.i,openCalls.i,offerBytes.i,mode.i,goal.i,unknown.i,gateCount.i,nowTick.i
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i FakeOpen(host.i,port.i,protocols.i,bytes.i)
 Define i.i
 openCalls=openCalls+1 : offerBytes=bytes
 For i=0 To bytes-1 : offer[i]=PeekA(protocols+i) : Next
 ProcedureReturn 1
EndProcedure
Procedure.i FakeLegacyOpen(host.i,port.i)
 ProcedureReturn FakeOpen(host,port,0,0)
EndProcedure
Procedure.i FakeDns(host.i)
 ProcedureReturn $04030201
EndProcedure
Procedure.i FakeTime()
 ProcedureReturn nowTick*1000
EndProcedure
Procedure.i FakeTcpState(handle.i)
 ProcedureReturn 2
EndProcedure
Procedure.i FakeState(handle.i)
 If mode=21 Or mode=22 : ProcedureReturn 0 : EndIf
 ProcedureReturn 4
EndProcedure
Procedure.i FakeAlpn(handle.i,destination.i,capacity.i)
 Define value.i,n.i,i.i
 If mode=16 : ProcedureReturn 0 : EndIf
 value="h2" : n=2
 If mode=15 : value="http/1.1" : n=8 : EndIf
 If mode=20 : value="spdy" : n=4 : EndIf
 For i=0 To n-1 : PokeA(destination+i,PeekA(value+i)) : Next
 ProcedureReturn n
EndProcedure
Procedure.i FakeClose(handle.i)
 closeCalls=closeCalls+1 : ProcedureReturn 0
EndProcedure
Procedure.i FakeSend(handle.i,source.i,bytes.i)
 Define i.i,n.i
 sendCalls=sendCalls+1 : If (sendCalls % 4)=0 : ProcedureReturn 0 : EndIf
 n=bytes : If n>97 : n=97 : EndIf
 If outBytes+n>131072 : ProcedureReturn -9601 : EndIf
 For i=0 To n-1 : outgoing[outBytes+i]=PeekA(source+i) : Next
 outBytes=outBytes+n : ProcedureReturn n
EndProcedure
Procedure.i FakeRecv(handle.i,destination.i,bytes.i)
 Define i.i,n.i,at.i,length.i,uploaded.i,ready.i,ended.i,required.i,kind.i,flags.i,highest.i,sid.i
 recvCalls=recvCalls+1 : If (recvCalls % 3)=0 : ProcedureReturn 0 : EndIf
 If mode>=15 And mode<=19
  If outBytes<request\length : ProcedureReturn 0 : EndIf
 Else
  at=24
  While at+9<=outBytes
   length=(outgoing[at]<<16)|(outgoing[at+1]<<8)|outgoing[at+2]
   If at+9+length>outBytes : Break : EndIf
   kind=outgoing[at+3] : flags=outgoing[at+4]
   sid=NetReadBE32(@outgoing[at+5])
   If (kind=1 Or kind=9) And (flags & 4)<>0 : ready=1 : If sid>highest : highest=sid : EndIf : EndIf
   If (kind=1 Or kind=0) And (flags & 1)<>0 : ended=1 : EndIf
   If kind=0 : uploaded=uploaded+length : EndIf
   at=at+9+length
  Wend
  required=-1
  For i=0 To gateCount-1 : If inAt>=gateAt[i] : required=gateBytes[i] : EndIf : Next
  If required<>-1
   If ready=0 : ProcedureReturn 0 : EndIf
   If required=-2
    If ended=0 : ProcedureReturn 0 : EndIf
   ElseIf required=-3
    If highest<3 : ProcedureReturn 0 : EndIf
   Else
    If uploaded<required : ProcedureReturn 0 : EndIf
   EndIf
  EndIf
 EndIf
 n=inBytes-inAt : If n>bytes : n=bytes : EndIf : If n>5 : n=5 : EndIf
 For i=0 To n-1 : PokeA(destination+i,incoming[inAt+i]) : Next
 inAt=inAt+n : ProcedureReturn n
EndProcedure
Procedure RunOne(index.i)
 Define i.i,rc.i,tick.i,base.i,timeout.i,position.i,received.i,capacity.i,method.i,methodBytes.i,length.i,head.i,limit.i,lineLimit.i,again.i,p.i,wireAt.i,*active.WebResponse,check.i
 inAt=0 : outBytes=0 : sendCalls=0 : recvCalls=0 : closeCalls=0 : openCalls=0 : offerBytes=0 : nowTick=0
 For i=0 To SizeOf(H2Client)-1 : PokeA(@c+i,0) : Next
 For i=0 To 70000 : body[i]=97 : Next
 If mode=2 : For i=0 To 16 : body[i]=i : Next : EndIf
 url\secure=1 : url\host="example.org" : url\hostLength=11 : url\port=443 : url\target="/upload" : url\targetLength=7
 If mode=19 : url\secure=0 : url\port=80 : EndIf
 buffers\tx=@tx[0] : buffers\rx=@rx[0] : buffers\requestBlock=@requestBlock[0] : buffers\controls=@controls[0] : buffers\block=@block[0] : buffers\dynamic=@dynamic[0] : buffers\field=@field[0] : buffers\streams=@streams[0] : buffers\streamCount=4
 webpTlsOpenAlpn=@FakeOpen : webpTlsOpen=@FakeLegacyOpen : webpTlsState=@FakeState : webpTlsAlpn=@FakeAlpn : webpTlsClose=@FakeClose : webpTlsSend=@FakeSend : webpTlsRecv=@FakeRecv
 webpDns=@FakeDns : webpTime=@FakeTime : webpOpen=@FakeLegacyOpen : webpState=@FakeTcpState : webpClose=@FakeClose : webpSend=@FakeSend : webpRecv=@FakeRecv : webpDns6=0 : webpOpen6=0
 If mode=17 : webpTlsOpenAlpn=0 : webpTlsAlpn=0 : EndIf
 method="GET" : methodBytes=3 : length=goal
 If mode=1 Or mode=2 Or mode=4 Or mode=23 : method="POST" : methodBytes=4 : EndIf
 If mode=3 : method="HEAD" : methodBytes=4 : head=1 : EndIf
 If unknown<>0 : length=-1 : EndIf
 rc=WebRequestInit(@request,@url,method,methodBytes,length,1,@headers[0],2048)
 If rc=0 : rc=WebRequestHeader(@request,"X-Test",6,"value",5) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@request) : EndIf
 limit=4096 : lineLimit=512
 If mode=5 : limit=128 : EndIf
 If mode=6 : lineLimit=128 : EndIf
 If rc=0 : rc=WebResponseInit(@response,@line[0],lineLimit,@metadata[0],limit,head) : EndIf
 If mode=18 And rc=0 : rc=WebResponseAllowUpgrade(@response) : EndIf
 *active=@response : timeout=10000
 If mode=13 : timeout=250 : EndIf
 If mode=21 : timeout=50 : EndIf
 If rc=0 : rc=WebClientStartAuto(@client,@url,@request,@response,@tx[0],16384,@rx[0],16384,@c,@buffers,0,timeout) : EndIf
 If rc=0
  For tick=1 To 30000
   pet() : nowTick=base+tick : capacity=1
   If (tick % 4)=0 Or mode=13 : capacity=0 : EndIf
   rc=WebClientStep(@client,@body[0]+position,goal-position,1,@result[0]+received,capacity,nowTick)
   position=position+client\consumed : received=received+client\written
   If position>goal Or received>511 : rc=-9602 : Break : EndIf
   If mode=12 And received=1 : rc=WebClientCancel(@client) : EndIf
   If mode=22 And tick=3 : rc=WebClientCancel(@client) : EndIf
   If rc<0 : Break : EndIf
   If rc=1
    If mode=14 And again=0
     url\target="/second" : url\targetLength=7
     rc=WebRequestInit(@request2,@url,"GET",3,0,1,@headers2[0],2048)
     If rc=0 : rc=WebRequestFinishHeaders(@request2) : EndIf
     If rc=0 : rc=WebResponseInit(@response2,@line2[0],512,@metadata2[0],4096,0) : EndIf
     If rc<>0 : Break : EndIf
     base=50000 : nowTick=base+tick
     If WebClientNext(@client,@request2,@response2,nowTick,0)<>#WEB_CLIENT_ARGUMENT : rc=-9603 : Break : EndIf
     rc=WebClientNext(@client,@request2,@response2,nowTick,10000)
     If rc<>0 : Break : EndIf
     *active=@response2 : again=1
    Else
     rc=0 : Break
    EndIf
   EndIf
  Next
  If tick>30000 : rc=-9604 : EndIf
 EndIf
 If rc=0 And mode=0
  If WebResponseHeaderCount(*active)<>5 : rc=-9605 : EndIf
  check=WebResponseHeader(*active,"x-trace",1,@lookup[0],32)
  If check<>3 Or lookup[0]<>116 Or lookup[1]<>119 Or lookup[2]<>111 : rc=-9606 : EndIf
  If WebResponseHeader(*active,"x-trailer",0,0,0)<>#WEB_RESPONSE_NOTFOUND : rc=-9607 : EndIf
  If WebResponseHeader(*active,"x-info",0,0,0)<>#WEB_RESPONSE_NOTFOUND : rc=-9608 : EndIf
 EndIf
 p=$E1C00100+index*32768
 PokeI(p,rc) : PokeI(p+8,position) : PokeI(p+16,received) : PokeI(p+24,*active\status)
 PokeI(p+32,outBytes) : PokeI(p+40,client\state) : PokeI(p+48,*active\state) : PokeI(p+56,*active\versionMajor)
 PokeI(p+64,client\protocol) : PokeI(p+72,openCalls) : PokeI(p+80,*active\headerLength)
 PokeI(p+88,*active\reusable) : PokeI(p+104,*active\interimCount) : PokeI(p+112,client\h2ResetCode)
 PokeI(p+120,*active\remaining) : PokeI(p+128,offerBytes) : PokeI(p+136,WebResponseHeaderCount(*active))
 PokeI(p+144,request\remaining) : PokeI(p+152,c\sent) : PokeI(p+160,c\received) : PokeI(p+168,inAt)
 PokeI(p+176,client\sent) : PokeI(p+184,client\received)
 For i=0 To offerBytes-1 : PokeA(p+208+i,offer[i]) : Next
 wireAt=p+512
 If outBytes>16384 : wireAt=$E1CE0000 : EndIf
 PokeI(p+96,wireAt-$E1C00000)
 For i=0 To outBytes-1 : PokeA(wireAt+i,outgoing[i]) : Next
 For i=0 To *active\headerLength-1 : PokeA(p+20000+i,PeekA(*active\headers+i)) : Next
 For i=0 To received-1 : PokeA(p+25000+i,result[i]) : Next
 WebClientClose(@client) : WebClientClose(@client)
 PokeI(p+192,closeCalls)
EndProcedure
Procedure RunCases()
 Define index.i,i.i,n.i,v.i
 Restore Cases : Read.i n : PokeI($E1C00008,n)
 For index=0 To n-1
  Read.i mode : Read.i goal : Read.i unknown : Read.i inBytes : Read.i gateCount
  For i=0 To gateCount-1 : Read.i v : gateAt[i]=v : Read.i v : gateBytes[i]=v : Next
  For i=0 To inBytes-1 : Read.i v : incoming[i]=v : Next
  RunOne(index)
 Next
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i
 rc=WebPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 1048575 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$48324155)
 RunCases()
 WebClientClose(@client)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 if transform is not None:s=transform(s)
 s+='\nDataSection\nCases:\n Data.i '+str(len(rows))+'\n'
 for row in rows:
  wire=bytes.fromhex(row['wire'])
  s+=' Data.i '+str(row['mode'])+','+str(row['goal'])+','+str(int(row['unknown']))+','+str(len(wire))+','+str(len(row['gates']))+'\n'
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
