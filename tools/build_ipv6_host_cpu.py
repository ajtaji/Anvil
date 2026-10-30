"""Physical composition proof for multicast membership and IPv6 DAD lifecycle."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_host.pbi','Anvil/Network/ipv6_endpoint.pbi','Anvil/Network/ipv6_mld.pbi','Anvil/Network/ipv6_mld_policy.pbi','Anvil/Network/ipv6_mld_group.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi']
 addr=lambda x:ipaddress.IPv6Address(x).packed
 local=addr('fe80::1234');peer=addr('fe80::5678');zero=bytes(16);group=addr('ff02::1:ff00:1234');allnodes=addr('ff02::1')
 mac=bytes.fromhex('020102030405');other=bytes.fromhex('020908070605')
 def checksum(b):
  if len(b)&1:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(src,dst,body,hop=255,hbh=b''):
  body=body[:2]+b'\0\0'+body[4:];c=checksum(src+dst+struct.pack('>I3xB',len(body),58)+body)
  return struct.pack('>IHBB',0x60000000,len(body)+len(hbh),0 if hbh else 58,hop)+src+dst+hbh+body[:2]+struct.pack('>H',c)+body[4:]
 def multi(ip):return b'\x33\x33'+ip[-4:]
 def ether(sm,dm,p):return dm+sm+b'\x86\xdd'+p
 hbh=b'\x3a\0\x05\x02\0\0\x01\0'
 def mld(mode,src=zero,ver=2):
  dst=addr('ff02::16') if ver==2 else group
  body=bytes([143,0,0,0])+bytes(2)+b'\0\1'+bytes([mode,0,0,0])+group if ver==2 else bytes([131,0,0,0])+bytes(4)+group
  return ether(mac,multi(dst),packet(src,dst,body,1,hbh))
 dad=ether(mac,multi(group),packet(zero,group,b'\x87\0\0\0'+bytes(4)+local))
 conflict=ether(other,multi(group),packet(zero,group,b'\x87\0\0\0'+bytes(4)+local))
 ns=ether(other,multi(group),packet(peer,group,b'\x87\0\0\0'+bytes(4)+local+b'\x01\x01'+other))
 na=ether(mac,other,packet(local,peer,b'\x88\0\0\0'+struct.pack('>I',0x60000000)+local+b'\x02\x01'+mac))
 body=b'\x80\0\0\0'+struct.pack('>HH',7,9)+b'host lifecycle'
 echo=ether(other,mac,packet(peer,local,body,64));reply=ether(mac,other,packet(local,peer,b'\x81'+body[1:],64))
 v1q=ether(other,multi(allnodes),packet(peer,allnodes,b'\x82\0\0\0'+struct.pack('>H',100)+bytes(2)+zero,1,hbh))
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(b);return '?V'+str(len(vectors)-1)
 def add(name,code,expected,wire=b''):
  cases.append(dict(name=name,expected=expected,wire=wire.hex()));steps.append(code)
 def init(g):return f'rc=IPv6HostInit(@host,{g},?Local,?Mac,@sources[0],1424,0,50)'
 def step(t,g=1,cap=1514):return f'rc=IPv6HostStep(@host,{g},{t},@output[0],{cap})'
 def sent(t,token,result=1,g=1):return f'rc=IPv6HostSent(@host,{g},{t},{token},{result},1000)'
 def inp(b,t,g=1,delay=1):return f'rc=IPv6HostInput(@host,{g},{t},{vec(b)},{len(b)},@output[0],1514,{delay})'
 def exp(rc,phase=1,ep=1,left=1,pending=0,ver=2,g=1):return [rc,phase,ep,left,pending,ver,g]
 add('initialize after filters',init(1),exp(0))
 add('initial multicast report',step(0),exp(90,pending=1),mld(4))
 add('pending report cannot start DAD',step(10000),exp(0,pending=1))
 add('wrong completion token',sent(10000,2),exp(-801,pending=1))
 add('definitely unsent report',sent(10000,1,0),exp(0))
 add('retry report',step(10001),exp(90,pending=2),mld(4))
 add('report confirmed starts DAD delay',sent(10002,2),exp(0,phase=2))
 add('DAD delay preserved',step(10051),exp(0,phase=2))
 add('DAD probe',step(10052),exp(78,phase=2,pending=3),dad)
 add('DAD probe confirmed',sent(10053,3),exp(0,phase=2,left=0))
 add('still tentative before repeat',step(11001),exp(0,phase=2,left=0))
 add('MLD repeat during DAD',step(11002),exp(90,phase=2,left=0,pending=4),mld(4))
 add('repeat completion',sent(11003,4),exp(0,phase=2,left=0))
 add('DAD full interval',step(11052),exp(0,phase=2,left=0))
 add('assigned address refresh report',step(11053),exp(90,phase=3,ep=2,left=0,pending=5),mld(2,local))
 add('refresh completion',sent(11054,5),exp(0,phase=3,ep=2,left=0))
 add('ready echo',inp(echo,11055),exp(len(reply),phase=3,ep=2,left=0),reply)
 add('ready neighbor response',inp(ns,11056),exp(len(na),phase=3,ep=2,left=0),na)
 add('backwards clock',step(11055),exp(-800,phase=3,ep=2,left=0))
 bad=bytearray(echo);bad[-1]^=1
 add('checksum refusal',inp(bytes(bad),11057),exp(-721,phase=3,ep=2,left=0))
 add('small output refused',step(11058,cap=89),exp(-800,phase=3,ep=2,left=0))
 add('generation restart',init(2),exp(0,g=2))
 add('new generation report',step(0,2),exp(90,pending=1,g=2),mld(4))
 add('duplicate before own DAD',inp(conflict,1,2),exp(0,phase=4,ep=3,pending=1,g=2))
 add('late report cannot revive duplicate',sent(2,1,g=2),exp(0,phase=4,ep=3,g=2))
 add('duplicate emits nothing',step(3,2),exp(0,phase=4,ep=3,g=2))
 add('restart third generation',init(3),exp(0,g=3))
 add('report before version change',step(0,3),exp(90,pending=1,g=3),mld(4))
 add('v1 query while report pending',inp(v1q,1,3,50),exp(0,pending=1,ver=1,g=3))
 add('old mode completion does not start DAD',sent(2,1,g=3),exp(0,ver=1,g=3))
 add('query response waits',step(50,3),exp(0,ver=1,g=3))
 add('v1 report',step(51,3),exp(86,pending=2,ver=1,g=3),mld(2,ver=1))
 add('v1 report confirmed',sent(52,2,g=3),exp(0,phase=2,ver=1,g=3))
 add('v1 DAD probe',step(102,3),exp(78,phase=2,pending=3,ver=1,g=3),dad)
 add('ambiguous DAD transmission fails host',sent(103,3,-9,3),exp(-9,phase=5,ver=1,g=3))
 add('failed host remains silent',step(5000,3),exp(0,phase=5,ver=1,g=3))
 add('stale generation',step(5001,2),exp(-801,phase=5,ver=1,g=3))
 add('reinitialize fourth generation',init(4),exp(0,g=4))
 add('context overlap rejected','rc=IPv6HostStep(@host,4,1,@host,1514)',exp(-800,g=4))
 add('owned source overlap rejected','rc=IPv6HostStep(@host,4,1,@sources[0],1514)',exp(-800,g=4))
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_endpoint.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld_policy.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld_group.pbi"\nXIncludeFile "Anvil/Network/ipv6_host.pbi"\n'+r'''
Global host.IPv6Host
Global Dim sources.a[1424]
Global Dim output.a[1514]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,host\phase) : PokeI(p+16,host\endpoint\state)
 PokeI(p+24,host\endpoint\remaining) : PokeI(p+32,host\awaiting)
 PokeI(p+40,host\policy\version) : PokeI(p+48,host\generation)
 For i=0 To 1513 : PokeA(p+64+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$484F5354)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=' For i=0 To 1513 : output[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
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
