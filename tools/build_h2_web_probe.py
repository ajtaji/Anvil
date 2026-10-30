"""Compile a verified HTTP/2 GET probe using shared transport, frames and HPACK.

This single-request qualification probe is not the reusable connection engine.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=['https://httpbin.org/uuid']
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_url.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/h2_frame.pbi','Anvil/Network/hpack_decode.pbi','Anvil/Network/hpack_tables.pbi']
 s='#WEB_KERNEL_BINDING=0\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global services.i
Global *pet,*clock
Global c.WebConnection
Global h.H2FrameHeader
Global decoder.HpackDecoder
Global Dim tx.a[16384]
Global Dim rx.a[16384]
Global Dim block.a[65536]
Global Dim dynamic.a[4096]
Global Dim field.a[8192]
Global headerWrite.i,headerCount.i,maxDecode.i
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure Progress()
 pet() : WebPayloadService(1)
EndProcedure
Procedure.i Send(source.i,bytes.i)
 Define pos.i,start.i,rc.i
 pos=0 : start=clock()
 While pos<bytes And clock()-start<10000000
  Progress() : rc=WebTransportSend(@c,source+pos,bytes-pos)
  If rc>0 : pos=pos+rc : EndIf
  If rc<0 And rc<>-110 : ProcedureReturn rc : EndIf
 Wend
 If pos<>bytes : ProcedureReturn -9001 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Receive(destination.i,bytes.i)
 Define pos.i,start.i,rc.i,st.i
 pos=0 : start=clock()
 While pos<bytes And clock()-start<10000000
  Progress() : st=WebTransportState(@c)
  If st<0 : ProcedureReturn st : EndIf
  rc=WebTransportRecv(@c,destination+pos,bytes-pos)
  If rc>0 : pos=pos+rc : EndIf
  If rc=0 And st=2 : ProcedureReturn -9002 : EndIf
  If rc<0 And rc<>-110 : ProcedureReturn rc : EndIf
 Wend
 If pos<>bytes : ProcedureReturn -9003 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i DecodeHeaders(bytes.i)
 Define rc.i,i.i,start.i,cost.i,p.i
 rc=HpackBegin(@decoder,@block[0],bytes,@field[0],8192,65536)
 If rc<>0 : ProcedureReturn rc : EndIf
 Repeat
  Progress() : start=clock() : rc=HpackNext(@decoder) : cost=clock()-start
  If cost>maxDecode : maxDecode=cost : EndIf
  If rc=1
   If headerWrite+24+decoder\nameLength+decoder\valueLength>8192 : ProcedureReturn -9004 : EndIf
   p=$E1C00000+headerWrite
   PokeI(p,decoder\nameLength) : PokeI(p+8,decoder\valueLength) : PokeI(p+16,decoder\sensitive)
   For i=0 To decoder\nameLength-1 : PokeA(p+24+i,PeekA(decoder\name+i)) : Next
   For i=0 To decoder\valueLength-1 : PokeA(p+24+decoder\nameLength+i,PeekA(decoder\value+i)) : Next
   headerWrite=headerWrite+24+decoder\nameLength+decoder\valueLength : headerCount=headerCount+1
  EndIf
 Until rc<=0
 ProcedureReturn rc
EndProcedure
Procedure.i Probe()
 Define rc.i,start.i,i.i,p.i,frames.i,first.i,sent.i,continuation.i,ended.i,used.i,offset.i,padding.i,n.i,body.i
 c\secure=1 : c\host="httpbin.org" : c\port=443
 tx[0]=2 : tx[1]=104 : tx[2]=50
 rc=WebTransportOpenAlpn(@c,@tx[0],3) : If rc<>0 : ProcedureReturn rc : EndIf
 start=clock()
 Repeat
  Progress() : rc=WebTransportState(@c)
 Until rc<>0 Or clock()-start>=30000000
 If rc<>1 : ProcedureReturn -9005 : EndIf
 rc=WebTransportAlpn(@c,@tx[0],16)
 If rc<>2 Or tx[0]<>104 Or tx[1]<>50 : ProcedureReturn -9006 : EndIf
 rc=HpackInit(@decoder,@dynamic[0],4096) : If rc<>0 : ProcedureReturn rc : EndIf
 H2ClientPreface(@tx[0],16384)
 H2FrameWrite(@tx[24],16360,6,4,0,0) : NetWriteBE16(@tx[33],2) : NetWriteBE32(@tx[35],0)
 rc=Send(@tx[0],39) : If rc<>0 : ProcedureReturn rc : EndIf
 first=1 : sent=0 : continuation=0 : ended=0 : used=0 : body=0 : frames=0
 headerWrite=512 : headerCount=0 : maxDecode=0 : start=clock()
 While (ended=0 Or continuation<>0) And frames<256 And clock()-start<30000000
  rc=Receive(@rx[0],9) : If rc<>0 : ProcedureReturn rc : EndIf
  H2FrameInit(@h,16384) : rc=H2FrameFeed(@h,@rx[0],9) : If rc<0 : ProcedureReturn rc : EndIf
  If first<>0
   If h\kind<>4 Or (h\flags & 1)<>0 : ProcedureReturn -9007 : EndIf
   first=0
  EndIf
  If continuation<>0 And (h\kind<>9 Or h\stream<>1) : ProcedureReturn -9008 : EndIf
  rc=Receive(@rx[0],h\length) : If rc<>0 : ProcedureReturn rc : EndIf
  frames=frames+1
  Select h\kind
   Case 4
    If (h\flags & 1)=0
     For i=0 To h\length-1 Step 6
      n=NetReadBE16(@rx[0]+i) : p=NetReadBE32(@rx[0]+i+2)
      If n=2 : ProcedureReturn -9009 : EndIf
      If n=4 And p>$7FFFFFFF : ProcedureReturn -9010 : EndIf
      If n=5 And (p<16384 Or p>16777215) : ProcedureReturn -9011 : EndIf
      If n=3 And p=0 : ProcedureReturn -9012 : EndIf
     Next
     H2FrameWrite(@tx[0],16384,0,4,1,0) : rc=Send(@tx[0],9) : If rc<>0 : ProcedureReturn rc : EndIf
     If sent=0
      ; Literal/static HPACK GET /uuid, with no request dynamic-table entries.
      tx[9]=$82 : tx[10]=$87 : tx[11]=4 : tx[12]=5 : p="/uuid"
      For i=0 To 4 : tx[13+i]=PeekA(p+i) : Next
      tx[18]=1 : tx[19]=11 : p="httpbin.org"
      For i=0 To 10 : tx[20+i]=PeekA(p+i) : Next
      H2FrameWrite(@tx[0],16384,22,1,5,1) : rc=Send(@tx[0],31) : If rc<>0 : ProcedureReturn rc : EndIf
      sent=1
     EndIf
    EndIf
   Case 1
    If h\stream<>1 Or sent=0 : ProcedureReturn -9013 : EndIf
    offset=0 : padding=0
    If (h\flags & 8)<>0 : padding=rx[0] : offset=1 : EndIf
    If (h\flags & 32)<>0 : offset=offset+5 : EndIf
    n=h\length-offset-padding : If n<0 Or used+n>65536 : ProcedureReturn -9014 : EndIf
    For i=0 To n-1 : block[used+i]=rx[offset+i] : Next
    used=used+n : If (h\flags & 1)<>0 : ended=1 : EndIf
    continuation=1
    If (h\flags & 4)<>0
     continuation=0 : rc=DecodeHeaders(used) : If rc<>0 : ProcedureReturn rc : EndIf
     used=0
    EndIf
   Case 9
    If continuation=0 Or h\stream<>1 Or used+h\length>65536 : ProcedureReturn -9015 : EndIf
    For i=0 To h\length-1 : block[used+i]=rx[i] : Next
    used=used+h\length
    If (h\flags & 4)<>0
     continuation=0 : rc=DecodeHeaders(used) : If rc<>0 : ProcedureReturn rc : EndIf
     used=0
    EndIf
   Case 0
    If h\stream<>1 Or headerCount=0 : ProcedureReturn -9016 : EndIf
    offset=0 : padding=0
    If (h\flags & 8)<>0 : offset=1 : padding=rx[0] : EndIf
    n=h\length-offset-padding : If n<0 Or body+n>4096 : ProcedureReturn -9017 : EndIf
    For i=0 To n-1 : PokeA($E1C02000+body+i,rx[offset+i]) : Next
    body=body+n : If (h\flags & 1)<>0 : ended=1 : EndIf
   Case 6
    If (h\flags & 1)=0
     H2FrameWrite(@tx[0],16384,8,6,1,0)
     For i=0 To 7 : tx[9+i]=rx[i] : Next
     rc=Send(@tx[0],17) : If rc<>0 : ProcedureReturn rc : EndIf
    EndIf
   Case 3
    ProcedureReturn -9018
   Case 7
    ProcedureReturn -9019
   Case 5
    ProcedureReturn -9020
  EndSelect
 Wend
 PokeI($E1C00010,body) : PokeI($E1C00018,headerCount) : PokeI($E1C00020,frames)
 PokeI($E1C00028,headerWrite) : PokeI($E1C00030,maxDecode)
 If ended=0 Or continuation<>0 : ProcedureReturn -9021 : EndIf
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
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$48324731)
 rc=Probe() : PokeI($E1C00008,rc)
 WebTransportClose(@c)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
