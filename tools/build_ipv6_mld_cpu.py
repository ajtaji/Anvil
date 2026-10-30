"""Build independent MLD packet/query vectors for physical Pi execution."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_mld_policy.pbi','Anvil/Network/ipv6_mld.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda s:ipaddress.IPv6Address(s).packed
 ll=addr('fe80::1234');zero=bytes(16);group=addr('ff02::1:ff00:1234');allnodes=addr('ff02::1')
 def csum(b):
  if len(b)%2:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(body,src=ll,dst=allnodes,hop=1,hbh=b'\x3a\0\x05\x02\0\0\x01\0'):
  body=body[:2]+b'\0\0'+body[4:]
  v=csum(src+dst+struct.pack('>I3xB',len(body),58)+body)
  body=body[:2]+struct.pack('>H',v)+body[4:]
  return struct.pack('>IHBB',0x60000000,len(body)+len(hbh),0 if hbh else 58,hop)+src+dst+hbh+body
 cases=[];steps=[];vectors=[]
 def vector(b):
  vectors.append(b);return '?Vector'+str(len(vectors)-1)
 def add(name,code,rc,data=b'',query=None):
  cases.append(dict(name=name,rc=rc,output=(data+b'\xa5'*(128-len(data))).hex(),query=query or [0]*5));steps.append(code)
 for ver in [1,2]:
  for mode in [2,3,4]:
   for src in [zero,ll]:
    dst=addr('ff02::16') if ver==2 else addr('ff02::2') if mode==3 else group
    body=(bytes([143,0,0,0])+bytes(2)+b'\0\1'+bytes([mode,0,0,0])+group) if ver==2 else bytes([132 if mode==3 else 131,0,0,0])+bytes(4)+group
    expected=packet(body,src,dst)
    add(f'report v{ver} mode{mode} unspecified{src==zero}',f'rc=IPv6MldReport(@output[0],128,{vector(src)},{vector(group)},{ver},{mode})',len(expected),expected)
 for name,src,g,ver,mode,cap in [('short',ll,group,2,4,75),('bad source',addr('2001:db8::1'),group,2,4,128),('unicast group',ll,ll,2,4,128),('all nodes',ll,allnodes,2,4,128),('interface scope',ll,addr('ff01::123'),2,4,128),('bad version',ll,group,3,4,128),('bad mode',ll,group,2,6,128)]:
  add(name,f'rc=IPv6MldReport(@output[0],{cap},{vector(src)},{vector(g)},{ver},{mode})',-760)
 add('alias output',f'rc=IPv6MldReport(@output[0],128,@output[0],{vector(group)},2,4)',-760)
 def query(ver=2,g=zero,delay=10000,qrv=2,qqic=125,sources=(),extra=b'',code=0):
  body=bytes([130,code,0,0])+struct.pack('>H',delay)+bytes(2)+g
  if ver==2:body+=bytes([qrv,qqic])+struct.pack('>H',len(sources))+b''.join(sources)
  return body+extra
 def parse(name,b,expected=None):
  add(name,f'rc=IPv6MldQuery({vector(b)},{len(b)},@queryView)',0 if expected is not None else -760,query=expected)
 parse('v1 general',packet(query(1)),[1,10000,0,0,0])
 parse('v1 integer high delay',packet(query(1,delay=65535)),[1,65535,0,0,0])
 parse('v2 general',packet(query()),[2,10000,2,125,0])
 parse('v2 exponential limits',packet(query(delay=65535,qqic=255,qrv=7)),[2,8387584,7,31744,0])
 parse('v2 specific sources',packet(query(g=group,sources=(ll,addr('2001:db8::9'))),dst=group),[2,10000,2,125,2])
 parse('trailing checksum data',packet(query(extra=b'hello')),[2,10000,2,125,0])
 parse('code ignored',packet(query(code=17)),[2,10000,2,125,0])
 parse('unspecified router',packet(query(),src=zero))
 parse('global router',packet(query(),src=addr('2001:db8::1')))
 parse('noncanonical link local',packet(query(),src=addr('fe80:1::1')))
 parse('reserved link local prefix',packet(query(),src=addr('fe90::1')))
 parse('hop limit',packet(query(),hop=2))
 parse('missing router alert',packet(query(),hbh=b'\x3a\0\x01\x04\0\0\0\0'))
 parse('wrong router alert',packet(query(),hbh=b'\x3a\0\x05\x02\0\1\x01\0'))
 parse('no hop header',packet(query(),hbh=b''))
 parse('duplicate router alert',packet(query(),hbh=b'\x3a\1\x05\x02\0\0\x05\x02\0\0\x01\x04\0\0\0\0'))
 bad=bytearray(packet(query()));bad[-1]^=1;parse('bad checksum',bytes(bad))
 parse('ambiguous query length',packet(query(1,extra=b'x')))
 parse('truncated sources',packet(query(g=group)[:-2]+b'\0\x02'))
 parse('general with sources',packet(query(sources=(ll,))))
 parse('multicast source entry',packet(query(g=group,sources=(group,))))
 parse('unspecified source entry',packet(query(g=group,sources=(zero,))))
 parse('unicast query group',packet(query(g=ll)))
 parse('short IPv6',b'\x60'*20)
 def policy(name,code,rc,expected):
  add(name,code,rc);cases[-1]['policy']=expected
 policy('policy defaults','rc=IPv6MldInterfaceInit(@policyState,1,0)',0,[1,1,2,0,2,125000,10000,0])
 policy('policy stale init','rc=IPv6MldInterfaceInit(@policyState,1,1)',-771,[1,1,2,0,2,125000,10000,0])
 def observe(name,b,now,rc,expected,gen=1):
  policy(name,f'rc=IPv6MldInterfaceQuery(@policyState,{gen},{now},{vector(b)},{len(b)})',rc,expected)
 observe('specific v1 does not switch',packet(query(1,g=group)),10,2,[1,1,2,0,2,125000,10000,10])
 observe('learn v2 timing',packet(query(delay=65535,qrv=7,qqic=255)),20,2,[1,1,2,0,7,31744000,8387584,20])
 observe('enter v1',packet(query(1)),30,1,[1,2,1,222218030,7,31744000,10000,30])
 observe('v2 cannot exit compatibility',packet(query()),40,1,[1,2,1,222218030,2,125000,10000,40])
 observe('refresh v1 deadline',packet(query(1)),50,1,[1,2,1,260050,2,125000,10000,50])
 observe('specific query leaves response interval',packet(query(g=group,delay=100)),60,1,[1,2,1,260050,2,125000,10000,60])
 observe('invalid does not refresh timer',packet(query(1),src=zero),70,-760,[1,2,1,260050,2,125000,10000,60])
 observe('stale query',packet(query()),70,-771,[1,2,1,260050,2,125000,10000,60],gen=2)
 policy('before expiry','rc=IPv6MldInterfaceTick(@policyState,1,260049)',1,[1,2,1,260050,2,125000,10000,260049])
 policy('exact expiry','rc=IPv6MldInterfaceTick(@policyState,1,260050)',2,[1,3,2,0,2,125000,10000,260050])
 policy('tick does not repeat revision','rc=IPv6MldInterfaceTick(@policyState,1,260051)',2,[1,3,2,0,2,125000,10000,260051])
 policy('backwards time','rc=IPv6MldInterfaceTick(@policyState,1,260050)',-770,[1,3,2,0,2,125000,10000,260051])
 observe('backwards query',packet(query(1)),100,-770,[1,3,2,0,2,125000,10000,260051])
 observe('zero wire params use defaults',packet(query(qrv=0,qqic=0)),260052,2,[1,3,2,0,2,125000,10000,260052])
 observe('enter v1 again',packet(query(1)),260053,1,[1,4,1,520053,2,125000,10000,260053])
 policy('new interface generation','rc=IPv6MldInterfaceInit(@policyState,2,0)',0,[2,1,2,0,2,125000,10000,0])
 policy('old generation tick','rc=IPv6MldInterfaceTick(@policyState,1,1)',-771,[2,1,2,0,2,125000,10000,0])
 policy('null context','rc=IPv6MldInterfaceTick(0,2,1)',-770,[2,1,2,0,2,125000,10000,0])
 policy('overlap context packet','rc=IPv6MldInterfaceQuery(@policyState,2,1,@policyState,64)',-770,[2,1,2,0,2,125000,10000,0])

 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld_policy.pbi"\n'
 s+='Global Dim output.a[128]\nGlobal queryView.IPv6MldQueryView\nGlobal policyState.IPv6MldInterface\nProcedure Save(index.i,rc.i)\n Define p.i,i.i\n p=$E1C00100+index*256\n PokeI(p,rc) : PokeI(p+8,queryView\\version) : PokeI(p+16,queryView\\maxDelay)\n PokeI(p+24,queryView\\robustness) : PokeI(p+32,queryView\\interval) : PokeI(p+40,queryView\\sourceCount)\n For i=0 To 127 : PokeA(p+64+i,output[i]) : Next\n For i=0 To 7 : PokeI(p+192+i*8,PeekI(@policyState+i*8)) : Next\nEndProcedure\n'
 s+='Procedure.i Main()\n Define i.i,rc.i\n For i=0 To 131071 : PokeA($E1C00000+i,0) : Next\n PokeI($E1C00000,$4D4C4431)\n MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf\n MmuEnableCached()\n'
 for k,code in enumerate(steps):s+='For i=0 To 127 : output[i]=$A5 : Next\n For i=0 To SizeOf(IPv6MldQueryView)-1 : PokeA(@queryView+i,0) : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f'Vector{k}:\n'
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
