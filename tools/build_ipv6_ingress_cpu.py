"""Exercise shared NetInput with the real IPv6 endpoint on physical Pi."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Hal/hal.pbi','Anvil/Network/net.pbi','Anvil/Network/ipv6_endpoint.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi']
 addr=lambda x:ipaddress.IPv6Address(x).packed
 local=addr('fe80::1234');peer=addr('fe80::5678');group=addr('ff02::1:ff00:1234')
 mac=bytes.fromhex('020102030405');other=bytes.fromhex('020908070605')
 def checksum(b):
  if len(b)&1:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(src,dst,body,hop=255):
  body=body[:2]+b'\0\0'+body[4:];c=checksum(src+dst+struct.pack('>I3xB',len(body),58)+body)
  return struct.pack('>IHBB',0x60000000,len(body),58,hop)+src+dst+body[:2]+struct.pack('>H',c)+body[4:]
 def ether(dm,p):return dm+other+b'\x86\xdd'+p
 body=b'\x80\0\0\0'+struct.pack('>HH',123,456)+b'actual ingress payload!'
 echo=ether(mac,packet(peer,local,body,64));reply=other+mac+b'\x86\xdd'+packet(local,peer,b'\x81'+body[1:],64)
 ns=ether(b'\x33\x33'+group[-4:],packet(peer,group,b'\x87\0\0\0'+bytes(4)+local+b'\x01\x01'+other))
 na=other+mac+b'\x86\xdd'+packet(local,peer,b'\x88\0\0\0'+struct.pack('>I',0x60000000)+local+b'\x02\x01'+mac)
 # A real IPv4 ICMP echo proves the original path still constructs replies.
 def v4(src,dst,icmp):
  icmp=icmp[:2]+struct.pack('>H',checksum(icmp[:2]+bytes(2)+icmp[4:]))+icmp[4:]
  h=struct.pack('>BBHHHBBH4s4s',0x45,0,20+len(icmp),7,0,64,1,0,src,dst)
  h=h[:10]+struct.pack('>H',checksum(h))+h[12:]
  return h+icmp
 ip4=bytes([192,0,2,1]);peer4=bytes([192,0,2,2]);icmp=b'\x08\0\0\0'+struct.pack('>HH',1,2)+b'legacy'
 ipv4=mac+other+b'\x08\0'+v4(peer4,ip4,icmp)
 arp=bytes.fromhex('0001080006040001')+other+peer4+bytes(6)+ip4
 arpframe=bytes([255])*6+other+b'\x08\x06'+arp
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(b);return '?V'+str(len(vectors)-1)
 def add(name,code,rc,wire=None,called=0,proto=0,length=None):
  cases.append(dict(name=name,rc=rc,wire=None if wire is None else wire.hex(),called=called,proto=proto,length=len(wire) if wire is not None else (length or 0)));steps.append(code)
 def inp(b,kind=1):return f'rc=NetInput({kind},{vec(b)},{len(b)})'
 add('disabled handler',inp(echo),0,proto=0x86dd)
 add('install real endpoint','old=NetSetIPv6InputHook(@Receive)\n '+inp(echo),1,reply,1,0x86dd)
 add('multicast neighbor solicitation',inp(ns),1,na,1,0x86dd)
 add('wrong Ethernet multicast mapping',inp(ns[:5]+bytes([ns[5]^1])+ns[6:]),0,proto=0x86dd)
 add('foreign unicast MAC',inp(bytes.fromhex('020000000099')+echo[6:]),0,proto=0x86dd)
 add('IPv6 broadcast refused',inp(bytes([255])*6+echo[6:]),0,proto=0x86dd)
 add('unjoined IPv6 group',inp(ether(b'\x33\x33\0\0\0\x99',packet(peer,addr('ff02::99'),body))),0,called=1,proto=0x86dd)
 broken=bytearray(echo);broken[-1]^=1
 add('real checksum failure',inp(bytes(broken)),-721,called=1,proto=0x86dd)
 add('interface identity is preserved',inp(echo,2),0,called=1,proto=0x86dd)
 add('short IPv6 frame',inp(echo[:53]),-108,proto=0x86dd)
 add('oversize IPv6 frame',inp(echo+bytes(1515-len(echo))),-108,proto=0x86dd)
 add('missing interface MAC',inp(echo,3),-101)
 add('IPv4 echo bypasses IPv6 handler',inp(ipv4),1,called=0,proto=1,length=max(60,14+20+len(icmp)))
 arpreply=other+mac+b'\x08\x06'+bytes.fromhex('0001080006040002')+mac+ip4+other+peer4
 add('ARP broadcast bypasses IPv6 handler',inp(arpframe),1,arpreply+bytes(60-len(arpreply)),0,0x806)
 for mode,rc in [(1,-108),(2,-108),(3,-100),(4,-100),(5,-888),(6,0)]:
  add('handler output contract '+str(mode),f'mode={mode}\n '+inp(echo),rc,called=1,proto=0x86dd)
 add('handler replacement refused during delivery','mode=7\n '+inp(echo),1,reply,1,0x86dd)
 add('uninstall handler','old=NetSetIPv6InputHook(0)\n mode=0\n '+inp(ns),0,proto=0x86dd)
 add('IPv4 still works after uninstall',inp(ipv4),1,called=0,proto=1,length=max(60,14+20+len(icmp)))
 s='#HW_LINK_NONE=0\n#HW_LINK_WIRED=1\n#HW_LINK_FILE=5\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/net.pbi"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_endpoint.pbi"\n'+r'''
Global ep.IPv6Endpoint
Global called.i,mode.i,nested.i,replaced.i
Procedure.i Receive(kind.i,frame.i,bytes.i,out.i,capacity.i)
 Define rc.i
 called=called+1
 If kind<>1 : ProcedureReturn 0 : EndIf
 If mode=1 : ProcedureReturn 1 : EndIf
 If mode=2 : ProcedureReturn 1515 : EndIf
 If mode=5 : ProcedureReturn -888 : EndIf
 If mode=6 : ProcedureReturn 0 : EndIf
 If mode=7
  replaced=NetSetIPv6InputHook(0)
 EndIf
 rc=IPv6EndpointInput(@ep,1,frame,bytes,out,capacity)
 If mode=3 : NetWriteBE16(out+12,$800) : EndIf
 If mode=4 : PokeA(out+6,99) : EndIf
 ProcedureReturn rc
EndProcedure
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,NetOutLen()) : PokeI(p+16,called)
 PokeI(p+24,NetLastProto()) : PokeI(p+32,nested) : PokeI(p+40,replaced)
 For i=0 To 1513 : PokeA(p+64+i,PeekA(NetOutBuf()+i)) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,old.i
 For i=0 To 131071 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$494E4736)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 NetDefaults() : NetSetMac(1,?Mac) : NetSetMac(2,?Mac)
 NetSetIPv4(1,$C0000201,$FFFFFF00,0)
 rc=IPv6EndpointInit(@ep,1,?Local,?Mac,0,0,1000,1)
 rc=IPv6EndpointStep(@ep,1,0,NetOutBuf(),1514)
 rc=IPv6EndpointSent(@ep,1,0,1)
 rc=IPv6EndpointStep(@ep,1,1000,NetOutBuf(),1514)
'''
 for k,code in enumerate(steps):s+=' called=0 : nested=0 : replaced=0\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Local',local),('Mac',mac)]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
  s+=name+':\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
