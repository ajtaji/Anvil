"""Physical IPv6 endpoint state and wire-image proof builder."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_endpoint.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi']
 addr=lambda x:ipaddress.IPv6Address(x).packed
 local=addr('fe80::1234');peer=addr('fe80::5678');zero=bytes(16);allnodes=addr('ff02::1');sol=addr('ff02::1:ff00:1234')
 mac=bytes.fromhex('020102030405');other=bytes.fromhex('020908070605')
 def checksum(b):
  if len(b)&1:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(src,dst,body,hop=255):
  body=body[:2]+b'\0\0'+body[4:]
  check=checksum(src+dst+struct.pack('>I3xB',len(body),58)+body)
  body=body[:2]+struct.pack('>H',check)+body[4:]
  return struct.pack('>IHBB',0x60000000,len(body),58,hop)+src+dst+body
 def ether(sm,dm,p):return dm+sm+b'\x86\xdd'+p
 def multi(ip):return b'\x33\x33'+ip[-4:]
 def ns(src=peer,sm=other):
  body=b'\x87\0\0\0'+bytes(4)+local
  if src!=zero:body+=b'\x01\x01'+sm
  return ether(sm,multi(sol),packet(src,sol,body))
 def na(dst,flags,sm=mac,dm=None):
  body=b'\x88\0\0\0'+struct.pack('>I',flags)+local+b'\x02\x01'+sm
  if dm is None:dm=multi(dst) if dst[0]==255 else other
  return ether(sm,dm,packet(local,dst,body))
 body=b'\x80\0\0\0'+struct.pack('>HH',123,456)+b'endpoint odd payload!'
 echo=ether(other,mac,packet(peer,local,body,64));reply=ether(mac,other,packet(local,peer,b'\x81'+body[1:],64))
 dad=ns(zero,mac)
 vectors=[ns(),echo,echo[:56]+bytes([echo[56]^1])+echo[57:],b'\x02\x99\x99\x99\x99\x99'+echo[6:],ns(zero,other),na(allnodes,0x20000000,other),ns(peer,mac),na(local,0x60000000,other,mac)]
 cases=[];steps=[]
 def add(name,code,scalars,wire=b''):
  cases.append(dict(name=name,expected=scalars,wire=wire.hex()));steps.append(code)
 init=lambda g,delay=100,probes=1:f'rc=IPv6EndpointInit(@ep,{g},?Local,?Mac,0,{delay},1000,{probes})'
 step=lambda time,gen=1:f'rc=IPv6EndpointStep(@ep,{gen},{time},@output[0],1514)'
 sent=lambda time,result,gen=1:f'rc=IPv6EndpointSent(@ep,{gen},{time},{result})'
 inp=lambda k,gen=1:f'rc=IPv6EndpointInput(@ep,{gen},?Vector{k},{len(vectors[k])},@output[0],1514)'
 add('initialize',init(1),[0,1,1,0,100,1])
 add('random delay',step(99),[0,1,1,0,100,1])
 add('DAD emitted',step(100),[78,1,1,1,100,1],dad)
 add('not inferred complete',step(2000),[0,1,1,1,100,1])
 add('not sent retry',sent(200,0),[0,1,1,0,100,1])
 add('retry emits DAD',step(201),[78,1,1,1,100,1],dad)
 add('stale result refused',sent(202,1,2),[-741,1,1,1,100,1])
 add('confirmed sent',sent(202,1),[0,1,0,0,1202,1])
 add('double completion refused',sent(203,1),[-740,1,0,0,1202,1])
 add('full interval',step(1201),[0,1,0,0,1202,1])
 add('preferred',step(1202),[0,2,0,0,1202,1])
 add('neighbor resolution',inp(0),[86,2,0,0,1202,1],na(peer,0x60000000))
 add('echo byte exact',inp(1),[len(reply),2,0,0,1202,1],reply)
 add('checksum refused',inp(2),[-721,2,0,0,1202,1])
 add('wrong MAC ignored',inp(3),[0,2,0,0,1202,1])
 add('defend assigned address',inp(4),[86,2,0,0,1202,1],na(allnodes,0x20000000))
 add('assigned NA ignored',inp(5),[0,2,0,0,1202,1])
 add('generation two',init(2),[0,1,1,0,100,2])
 add('duplicate before first probe',inp(4,2),[0,3,1,0,100,2])
 add('duplicate never promotes',step(2000,2),[0,3,1,0,100,2])
 add('generation three',init(3),[0,1,1,0,100,3])
 add('tentative ignores unicast',inp(1,3),[0,1,1,0,100,3])
 add('tentative ignores resolution',inp(0,3),[0,1,1,0,100,3])
 add('tentative ignores unicast NA',inp(7,3),[0,1,1,0,100,3])
 add('multicast NA detects duplicate',inp(5,3),[0,3,1,0,100,3])
 add('generation four',init(4),[0,1,1,0,100,4])
 add('local loopback ignored',inp(6,4),[0,1,1,0,100,4])
 add('probe before failed send',step(100,4),[78,1,1,1,100,4],dad)
 add('ambiguous send fails',sent(100,-1,4),[0,4,1,0,100,4])
 add('failed never promotes',step(2000,4),[0,4,1,0,100,4])
 add('stale init preserves',init(4),[-741,4,1,0,100,4])
 add('two probes',init(5,0,2),[0,1,2,0,0,5])
 add('first of two',step(0,5),[78,1,2,1,0,5],dad)
 add('first sent',sent(0,1,5),[0,1,1,0,1000,5])
 add('interval not elapsed',step(999,5),[0,1,1,0,1000,5])
 add('second of two',step(1000,5),[78,1,1,1,1000,5],dad)
 add('second sent',sent(1000,1,5),[0,1,0,0,2000,5])
 add('second interval',step(1999,5),[0,1,0,0,2000,5])
 add('two probes preferred',step(2000,5),[0,2,0,0,2000,5])
 add('short output','rc=IPv6EndpointInput(@ep,5,?Vector1,'+str(len(echo))+',@output[0],85)',[-740,2,0,0,2000,5])
 add('alias output','rc=IPv6EndpointInput(@ep,5,?Vector1,'+str(len(echo))+',?Vector1,1514)',[-740,2,0,0,2000,5])
 add('null context','rc=IPv6EndpointStep(0,5,3000,@output[0],1514)',[-740,2,0,0,2000,5])
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_endpoint.pbi"\n'+r'''
Global ep.IPv6Endpoint
Global Dim output.a[1514]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,ep\state) : PokeI(p+16,ep\remaining)
 PokeI(p+24,ep\awaiting) : PokeI(p+32,ep\deadline) : PokeI(p+40,ep\generation)
 For i=0 To 1513 : PokeA(p+64+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 131071 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$45503631)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,code in enumerate(steps):s+=' For i=0 To 1513 : output[i]=$A5 : Next\n '+code+f'\n Save({i},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Local',local),('Mac',mac)]+[(f'Vector{i}',b) for i,b in enumerate(vectors)]:
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
