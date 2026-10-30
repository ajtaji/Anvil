"""Build physical Ethernet IPv6 Neighbor Discovery codec proofs."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi']
 addr=lambda x:ipaddress.IPv6Address(x).packed
 src=addr('fe80::1234');target=addr('fe80::5678');zero=bytes(16);allnodes=addr('ff02::1');sol=addr('ff02::1:ff00:5678');mac=bytes.fromhex('020102030405');slla=b'\x01\x01'+mac;tlla=b'\x02\x01'+mac
 def checksum(b):
  if len(b)%2:b+=b'\0'
  n=sum(int.from_bytes(b[i:i+2],'big') for i in range(0,len(b),2))
  while n>65535:n=(n&65535)+(n>>16)
  return n^65535
 def packet(source,dest,body,hops=255,proto=58,fragment=False):
  body=body[:2]+b'\0\0'+body[4:]
  c=checksum(source+dest+len(body).to_bytes(4,'big')+bytes([0,0,0,proto])+body);body=body[:2]+c.to_bytes(2,'big')+body[4:]
  payload=(struct.pack('!BBHI',58,0,0,123)+body) if fragment else body
  return struct.pack('!IHBB',0x60000000,len(payload),44 if fragment else proto,hops)+source+dest+payload
 def ns(t=target,options=slla):return bytes([135,0,0,0])+bytes(4)+t+options
 def na(t=target,flags=0x60000000,options=tlla):return bytes([136,0,0,0])+flags.to_bytes(4,'big')+t+options
 cases=[];vectors=[]
 def add(name,source,dest,body,rc=0,**kwargs):
  p=packet(source,dest,body,**kwargs);c=dict(name=name,rc=rc)
  if rc==0:
   kind=body[0];c.update(kind=kind,flags=int.from_bytes(body[4:8],'big') if kind==136 else 0)
   if kind==133:c['built']=packet(source,addr('ff02::2'),bytes([133,0,0,0])+bytes(4)+(b'' if source==zero else slla)).hex()
   if kind in [135,136]:c['target']=body[8:24].hex()
   if kind==135:c['built']=packet(source,sol,ns(options=b'' if source==zero else slla)).hex()
   if kind==136:c['built']=packet(body[8:24],dest,na(body[8:24],int.from_bytes(body[4:8],'big'),tlla)).hex()
  cases.append(c);vectors.append(p)
 add('normal NS',src,sol,ns())
 add('DAD NS',zero,sol,ns(options=b''))
 add('solicited NA',target,src,na())
 add('unsolicited NA',target,allnodes,na(flags=0x20000000))
 add('RA',src,allnodes,bytes([134,0,0,0])+bytes(12)+slla)
 add('RS',src,addr('ff02::2'),bytes([133,0,0,0])+bytes(4)+slla)
 add('unspecified RS',zero,addr('ff02::2'),bytes([133,0,0,0])+bytes(4))
 add('bad hop',src,sol,ns(),-720,hops=254)
 add('bad code',src,sol,bytes([135,1])+ns()[2:],-720)
 add('corrupt checksum',src,sol,ns(),-721);vectors[-1]=vectors[-1][:-1]+bytes([vectors[-1][-1]^1])
 add('short NS',src,sol,ns()[:8],-720)
 add('redirect unsupported',src,allnodes,bytes([137,0,0,0])+bytes(36),-722)
 add('multicast target',src,sol,ns(allnodes),-720)
 add('zero target',src,sol,ns(zero),-720)
 add('DAD wrong destination',zero,allnodes,ns(options=b''),-720)
 add('DAD source option',zero,sol,ns(),-720)
 add('NA unspecified source',zero,src,na(),-720)
 add('NA multicast target',target,src,na(allnodes),-720)
 add('multicast solicited NA',target,allnodes,na(),-720)
 add('RA global source',addr('2001:db8::1'),allnodes,bytes([134,0,0,0])+bytes(12),-720)
 add('RA short',src,allnodes,bytes([134,0,0,0])+bytes(4),-720)
 add('zero length option',src,sol,ns(options=b'\x01\0'+bytes(6)),-720)
 add('truncated option',src,sol,ns(options=b'\x01\x02'+bytes(6)),-720)
 add('wrong Ethernet option length',src,sol,ns(options=b'\x01\x02'+bytes(14)),-720)
 add('multicast MAC',src,sol,ns(options=b'\x01\x01'+bytes([3,1,2,3,4,5])),-720)
 add('duplicate MAC',src,sol,ns(options=slla+slla),-720)
 add('unknown option ignored',src,allnodes,bytes([134,0,0,0])+bytes(12)+bytes([253,1,0,0,0,0,0,0]))
 add('atomic fragment ND',src,sol,ns(),-720,fragment=True)
 add('wrong protocol',src,sol,ns(),-720,proto=17)
 add('multicast source',allnodes,sol,ns(),-720)
 s='\n'.join('XIncludeFile "'+names[i]+'"' for i in [0,2])+'\n'+r'''
Global wtable.i
Global *pet
Global ip.IPv6PacketView
Global nd.IPv6NeighborView
Global Dim output.a[128]
Global Dim fallbackMac.a[6]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure NeighborFixture(index.i,data.i,n.i)
 Define p.i,i.i,rc.i,built.i,small.i,guard.i,mac.i
 p=$E1C00100+index*256
 rc=IPv6NeighborParse(data,n,@ip,@nd)
 PokeI(p,rc)
 If rc=0
  PokeI(p+8,nd\kind) : PokeI(p+16,nd\flags)
  If nd\target<>0
   For i=0 To 15 : PokeA(p+64+i,PeekA(nd\target+i)) : Next
  EndIf
  For i=0 To 127 : output[i]=$A5 : Next
  built=0 : small=0 : guard=1
  If nd\kind=133
   small=IPv6RouterSolicit(@output[0],47,ip\source,nd\sourceMac)
  ElseIf nd\kind=135
   small=IPv6NeighborSolicit(@output[0],63,ip\source,nd\target,nd\sourceMac)
  ElseIf nd\kind=136
   small=IPv6NeighborAdvertise(@output[0],63,nd\target,ip\destination,nd\targetMac,nd\flags)
  EndIf
  For i=0 To 127 : If output[i]<>$A5 : guard=0 : EndIf : Next
  If nd\kind=133
   built=IPv6RouterSolicit(@output[0],128,ip\source,nd\sourceMac)
  ElseIf nd\kind=135
   built=IPv6NeighborSolicit(@output[0],128,ip\source,nd\target,nd\sourceMac)
  ElseIf nd\kind=136
   built=IPv6NeighborAdvertise(@output[0],128,nd\target,ip\destination,nd\targetMac,nd\flags)
  EndIf
  If built>0
   For i=built To 127 : If output[i]<>$A5 : guard=0 : EndIf : Next
   For i=0 To built-1 : PokeA(p+96+i,output[i]) : Next
  EndIf
  PokeI(p+24,built) : PokeI(p+32,small) : PokeI(p+40,guard)
 EndIf
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$49503634)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,p in enumerate(vectors):s+=f' NeighborFixture({i},?IPv6NeighborVector{i},{len(p)})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,p in enumerate(vectors):
  s+=f'IPv6NeighborVector{i}:\n'
  for j in range(0,len(p),24):s+=' Data.a '+','.join(str(x) for x in p[j:j+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
