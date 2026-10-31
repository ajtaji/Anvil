"""Build an ABI-only IPv4/IPv6 echo proof for a controlled desktop peer."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out,ipv4,ipv6):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/udp_payload.pbi','Anvil/Network/udp_socket_types.pbi','Anvil/Hal/service_errors.pbi','Anvil/Network/ipv6_udp.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/internet_checksum.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[dict(name=f'IPv{family} echo {n} bytes',expected=0) for family,sizes in [(4,[0,17,1472]),(6,[0,17,1232])] for n in sizes]
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/udp_payload.pbi"
Global services.i,maxService.i
Global *pet,*clock
Global ep.UdpEndpoint,info.UdpDatagramInfo,status.UdpSocketStatus
Global Dim data.a[1472]
Global Dim received.a[1472]
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Probe(h.i,n.i,sequence.i)
 Define i.i,rc.i,t.i,started.i,elapsed.i,got.i
 For i=0 To n-1 : data[i]=(i*37+sequence)&255 : Next
 rc=UdpPayloadSendTo(h,@ep,@data[0],n)
 If rc<1 : ProcedureReturn rc : EndIf
 started=clock()
 While clock()-started<8000000
  pet()
  t=clock() : rc=UdpPayloadService() : elapsed=clock()-t
  If elapsed>maxService : maxService=elapsed : EndIf
  If rc<0 : ProcedureReturn rc : EndIf
  rc=UdpPayloadStatus(h,@status) : If rc<>0 : ProcedureReturn rc : EndIf
  If status\txState=#UDP_TX_FAILED : ProcedureReturn status\txError : EndIf
  If got=0
   rc=UdpPayloadReceive(h,@info,@received[0],1472)
   If rc<>#SVC_EAGAIN
    If rc<>n : ProcedureReturn -9101 : EndIf
    If info\family<>ep\family Or info\peerPort<>ep\port : ProcedureReturn -9102 : EndIf
    For i=0 To 15
     If PeekA(@info\peerAddress+i)<>PeekA(@ep\address+i) : ProcedureReturn -9103 : EndIf
    Next
    For i=0 To n-1
     If received[i]<>((i*37+sequence)&255) : ProcedureReturn -9104 : EndIf
    Next
    got=1
   EndIf
  EndIf
  If got=1 And status\txState=#UDP_TX_SENT : ProcedureReturn 0 : EndIf
 Wend
 ProcedureReturn -9105
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i,h.i,started.i
 rc=UdpPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8) : clock=PeekI(services+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 4095 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$55445331) : PokeI($E1C00008,6)
 started=clock()
 ep\family=4 : ep\kind=0 : ep\port=55440
 For i=0 To 15 : PokeA(@ep\address+i,PeekA(?Peer4+i)) : Next
 h=UdpPayloadOpen(4,0,55011)
 rc=Probe(h,0,0) : PokeI($E1C00100,rc)
 rc=Probe(h,17,1) : PokeI($E1C00108,rc)
 rc=Probe(h,1472,2) : PokeI($E1C00110,rc)
 UdpPayloadClose(h)
 ep\family=6 : ep\kind=0 : ep\port=55441
 For i=0 To 15 : PokeA(@ep\address+i,PeekA(?Peer6+i)) : Next
 h=UdpPayloadOpen(6,0,55012)
 rc=Probe(h,0,3) : PokeI($E1C00118,rc)
 rc=Probe(h,17,4) : PokeI($E1C00120,rc)
 rc=Probe(h,1232,5) : PokeI($E1C00128,rc)
 ; Leave this socket open deliberately: common payload return owns cleanup.
 PokeI($E1C00040,maxService) : PokeI($E1C00048,clock()-started)
 PokeI($E1C00050,PeekI(services+8)&$FFFFFFFF)
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
DataSection
'''
 for n,b in [('Peer4',ipaddress.IPv4Address(ipv4).packed+bytes(12)),('Peer6',ipaddress.IPv6Address(ipv6).packed)]:s+=n+':\n Data.a '+','.join(map(str,b))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c00fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases,peer4=ipv4,peer6=ipv6),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--ipv4',required=True);ap.add_argument('--ipv6',required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve(),a.ipv4,a.ipv6)
