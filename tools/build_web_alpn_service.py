"""Compile opt-in web transport ALPN and legacy-binding checks."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/web_transport.pbi','Anvil/Network/web_url.pbi','Anvil/Network/tcp_dial.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi'];cases=['h2','http/1.1','legacy']
 s='#WEB_KERNEL_BINDING=0\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/web_url.pbi"\nXIncludeFile "Anvil/Network/web_transport.pbi"\n'+r'''
Global table.i
Global *openAlpn,*selected,*openLegacy,*state,*close,*service,*pet,*clock
Global Dim offer.a[256]
Global Dim answer.a[256]
Global Dim handles.i[3]
Global Dim connections.a[3*SizeOf(WebConnection)]
Global Dim oldTable.a[1616]
Procedure.i Connection(index.i)
 ProcedureReturn @connections[0]+index*SizeOf(WebConnection)
EndProcedure
Procedure.i OpenConnection(index.i,protocols.i,bytes.i)
 Define *c.WebConnection,rc.i
 *c=Connection(index) : *c\secure=1 : *c\host="httpbin.org" : *c\port=443
 If bytes=0
  rc=WebTransportOpen(*c)
 Else
  rc=WebTransportOpenAlpn(*c,protocols,bytes)
 EndIf
 If rc<>0 : ProcedureReturn rc : EndIf
 ProcedureReturn *c\handle
EndProcedure
Procedure.i CloseConnection(index.i)
 WebTransportClose(Connection(index)) : ProcedureReturn 0
EndProcedure
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Word(p.i)
 ProcedureReturn PeekA(p)|(PeekA(p+1)<<8)|(PeekA(p+2)<<16)|(PeekA(p+3)<<24)
EndProcedure
Procedure.i Main(services.i)
 CaptureTable()
 Define i.i,k.i,rc.i,n.i,start.i,p.i,done.i,maxcall.i,began.i,elapsed.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$414C5331)
 PokeI($E1C00008,Word(table+8)) : PokeI($E1C00010,Word(table+12))
 If Word(table)<>$53564E41 Or Word(table+4)<>1 Or Word(table+8)<13 Or Word(table+12)<92 : ProcedureReturn 71 : EndIf
 openAlpn=PeekI(table+16+90*8) : selected=PeekI(table+16+91*8)
 openLegacy=PeekI(table+16+80*8) : state=PeekI(table+16+87*8) : close=PeekI(table+16+83*8)
 service=PeekI(table+16+85*8) : pet=PeekI(table+16+6*8) : clock=PeekI(table+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 PokeI($E1C00500,WebPayloadBind(table))
 offer[0]=2 : offer[1]=104 : offer[2]=50
 handles[0]=OpenConnection(0,@offer[0],3)
 PokeI($E1C00100,handles[0]) : PokeI($E1C00108,WebTransportAlpn(Connection(0),@answer[0],256))
 offer[0]=8 : p="http/1.1"
 For i=0 To 7 : offer[i+1]=PeekA(p+i) : Next
 handles[1]=OpenConnection(1,@offer[0],9)
 PokeI($E1C00200,handles[1]) : PokeI($E1C00208,selected(handles[1],@answer[0],256))
 For i=0 To 255 : offer[i]=$FF : Next
 start=clock() : done=0
 While done<>3 And clock()-start<30000000
  pet() : began=clock() : service(1) : elapsed=clock()-began
  If elapsed>maxcall : maxcall=elapsed : EndIf
  For k=0 To 1
   If (done & (1<<k))=0
    rc=WebTransportState(Connection(k))
    If rc=1 Or rc<0
     p=$E1C00100+k*256 : PokeI(p+16,rc)
     For i=0 To 255 : answer[i]=$A5 : Next
     PokeI(p+24,WebTransportAlpn(Connection(k),@answer[0],1))
     PokeI(p+56,answer[0])
     n=WebTransportAlpn(Connection(k),@answer[0],256) : PokeI(p+32,n)
     For i=0 To 15 : PokeA(p+64+i,answer[i]) : Next
     PokeI(p+40,CloseConnection(k)) : PokeI(p+48,WebTransportAlpn(Connection(k),@answer[0],256))
     done=done | (1<<k)
    EndIf
   EndIf
  Next
 Wend
 PokeI($E1C00018,done) : PokeI($E1C00020,maxcall)
 For k=0 To 1 : If (done & (1<<k))=0 : rc=CloseConnection(k) : EndIf : Next
 handles[2]=OpenConnection(2,0,0) : PokeI($E1C00300,handles[2])
 start=clock() : rc=0
 While rc<>1 And rc>=0 And clock()-start<30000000
  pet() : service(1) : rc=WebTransportState(Connection(2))
 Wend
 PokeI($E1C00310,rc) : PokeI($E1C00320,WebTransportAlpn(Connection(2),@answer[0],256)) : PokeI($E1C00328,CloseConnection(2))
 offer[0]=0
 PokeI($E1C00400,openAlpn("httpbin.org",443,@offer[0],1))
 PokeI($E1C00408,openAlpn("httpbin.org",443,0,3))
 PokeI($E1C00410,openAlpn("httpbin.org",443,$200000,3))
 PokeI($E1C00418,openAlpn($200000,443,0,0))
 PokeI($E1C00420,openAlpn("httpbin.org",443,@offer[0],257))
 PokeI($E1C00428,WebTransportAlpn(Connection(0),$200000,256))
 For i=0 To 1615 : oldTable[i]=PeekA(table+i) : Next
 PokeL(@oldTable[8],12) : PokeL(@oldTable[12],90)
 PokeI($E1C00508,WebPayloadBind(@oldTable[0]))
 PokeI($E1C00510,OpenConnection(0,@offer[0],3))
 PokeI($E1C00518,WebTransportAlpn(Connection(0),@answer[0],256))
 PokeI($E1C00520,WebPayloadBind(table))
 PokeI($E1C00528,WebTransportOpenAlpn(0,@offer[0],3))
 PokeI($E1C00530,WebTransportOpenAlpn(Connection(0),0,3))
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 assert s.index('MmuBuildTables(')<s.index('MmuEnableCached()')<s.index('MmuDisableCachedFlushed()')
 assert 'ProcedureReturn' not in s.split('MmuEnableCached()',1)[1].split('MmuDisableCachedFlushed()',1)[0]
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
