'''Physical SLAAC address owner lifecycle and exact frame qualification.'''
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_address_owner.pbi','Anvil/Network/ipv6_slaac.pbi','Anvil/Network/ipv6_endpoint.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda s:ipaddress.IPv6Address(s).packed
 local=addr('2001:db8:1:2::1234');ll=addr('fe80::1234');peer=addr('fe80::5678');group=addr('ff02::1:ff00:1234');mac=bytes.fromhex('020102030405');other=bytes.fromhex('020908070605')
 def packet(src,dst,body,hop):
  pseudo=src+dst+struct.pack('>I3xB',len(body),58)+body
  if len(pseudo)&1:pseudo+=b'\0'
  n=sum(struct.unpack('>'+str(len(pseudo)//2)+'H',pseudo))
  while n>>16:n=(n&65535)+(n>>16)
  body=body[:2]+struct.pack('>H',(~n)&65535)+body[4:]
  return struct.pack('>IHBB',0x60000000,len(body),58,hop)+src+dst+body
 def ether(sm,dm,p):return dm+sm+b'\x86\xdd'+p
 dadbody=b'\x87\0\0\0'+bytes(4)+local
 dad=ether(mac,b'\x33\x33'+group[-4:],packet(bytes(16),group,dadbody,255))
 conflict=ether(other,b'\x33\x33'+group[-4:],packet(bytes(16),group,dadbody,255))
 body=b'\x80\0\0\0'+struct.pack('>HH',7,9)+b'owned address'
 echo=ether(other,mac,packet(peer,local,body,64));reply=ether(mac,other,packet(local,peer,b'\x81'+body[1:],64))
 cases=[];steps=[];vectors=[];state=[1,0,0,0,0,0,0]
 def add(name,code,rc,new=None,wire=b''):
  nonlocal state
  if new is not None:state=new
  cases.append(dict(name=name,expected=[rc]+state,wire=wire.hex()));steps.append(code)
 def init(g):return f'rc=IPv6AddressOwnerInit(@owner,{g},?Prefix,?LinkLocal,?Group,?Mac,0)'
 def app(t,v,p,g=1,delay=0):return f'rc=IPv6AddressOwnerApply(@owner,{g},{t},{v},{p},0,{delay},1000)'
 def step(t,g=1):return f'rc=IPv6AddressOwnerStep(@owner,{g},{t},@output[0],1514)'
 def sent(t,tok,result=1,g=1):return f'rc=IPv6AddressOwnerSent(@owner,{g},{t},{tok},{result})'
 def status(t,g=1):return f'rc=IPv6AddressOwnerStatus(@owner,{g},{t})'
 def inp(b,t,g=1):vectors.append(b);return f'rc=IPv6AddressOwnerInput(@owner,{g},{t},?V{len(vectors)-1},{len(b)},@output[0],1514)'
 add('initialize with confirmed shared group',init(1),0)
 add('new address starts tentative',app(0,4,2,delay=50),1,[1,0,0,1,1,4000,2000])
 add('random delay',step(49),0)
 add('DAD frame',step(50),78,[1,1,1,1,1,4000,2000],dad)
 add('pending receipt does not assign',step(1000),0)
 add('confirmed DAD starts full interval',sent(1000,1),0,[1,1,0,1,1,4000,2000])
 add('interval not elapsed',step(1999),0)
 add('DAD complete',step(2000),0,[1,1,0,1,2,4000,2000])
 add('preferred expiry yields deprecated',status(2000),3)
 add('deprecated address still receives echo',inp(echo,2001),len(reply),wire=reply)
 add('valid expiry removes address',status(4000),0,[1,1,0,1,0,4000,2000])
 add('late receipt cannot revive',sent(4001,1),-861)
 add('recreated address needs new DAD',app(4002,10,10),1,[1,1,0,2,1,14002,14002])
 add('new DAD token',step(4002),78,[1,2,2,2,1,14002,14002],dad)
 add('old token refused',sent(4003,1),-861)
 add('conflict cancels pending assignment',inp(conflict,4004),0,[1,2,0,2,3,14002,14002])
 add('late conflict receipt refused',sent(4005,2),-861)
 add('refresh cannot clear duplicate',app(4006,100,50),0,[1,2,0,2,3,104006,54006])
 add('duplicate status',status(4006),4)
 add('new link generation resets',init(2),0,[2,0,0,0,0,0,0])
 add('short lifetime',app(0,1,1,2),1,[2,0,0,1,1,1000,1000])
 add('short lifetime pending DAD',step(0,2),78,[2,1,1,1,1,1000,1000],dad)
 add('expiry while DAD pending',status(1000,2),0,[2,1,0,1,0,1000,1000])
 add('expired receipt refused',sent(1001,1,g=2),-861)
 add('another DAD generation',app(1002,10,10,2),1,[2,1,0,2,1,11002,11002])
 add('second token',step(1002,2),78,[2,2,2,2,1,11002,11002],dad)
 add('definitely unsent retry allowed',sent(1003,2,0,2),0,[2,2,0,2,1,11002,11002])
 add('retry gets unique token',step(1004,2),78,[2,3,3,2,1,11002,11002],dad)
 add('ambiguous transmission fails address',sent(1005,3,-9,2),0,[2,3,0,2,4,11002,11002])
 add('failed status',status(1006,2),5)
 add('stale link generation refused',status(1006,1),-861)
 add('wrong joined group refused','rc=IPv6AddressOwnerInit(@owner,3,?Prefix,?LinkLocal,?WrongGroup,?Mac,0)',-860)
 add('whole owner output alias refused','rc=IPv6AddressOwnerStep(@owner,2,1007,@owner,1514)',-860)
 add('backwards clock refused',status(999,2),-860)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_endpoint.pbi"\nXIncludeFile "Anvil/Network/ipv6_slaac.pbi"\nXIncludeFile "Anvil/Network/ipv6_address_owner.pbi"\n'+r'''
Global owner.IPv6AddressOwner
Global Dim output.a[1514]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,owner\generation) : PokeI(p+16,owner\serial) : PokeI(p+24,owner\awaiting)
 PokeI(p+32,owner\endpointGeneration) : PokeI(p+40,owner\endpoint\state)
 PokeI(p+48,owner\lifetime\validUntil) : PokeI(p+56,owner\lifetime\preferredUntil)
 For i=0 To 1513 : PokeA(p+64+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$4F574E52)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=' For i=0 To 1513 : output[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Prefix',addr('2001:db8:1:2::')),('LinkLocal',ll),('Group',group),('Mac',mac),('WrongGroup',addr('ff02::1:ff00:5555'))]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
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
