"""Compile multicast group scheduling for physical CPU qualification."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_mld_group.pbi','Anvil/Network/ipv6_mld_policy.pbi','Anvil/Network/ipv6_mld.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda s:ipaddress.IPv6Address(s).packed
 group=addr('ff02::1:ff00:1234');ll=addr('fe80::1234');sources=[addr('2001:db8::'+str(i)) for i in [1,2,3]]
 def checksum(b):
  if len(b)%2:b+=bytes(1)
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def report(mode,version=2,srcs=()):
  if version==2:
   dst=addr('ff02::16');body=bytes([143,0,0,0])+bytes(2)+b'\0\1'+bytes([mode,0])+struct.pack('>H',len(srcs))+group+b''.join(srcs)
  else:
   dst=addr('ff02::2') if mode==3 else group;body=bytes([132 if mode==3 else 131,0,0,0])+bytes(4)+group
  c=checksum(ll+dst+struct.pack('>I3xB',len(body),58)+body);body=body[:2]+struct.pack('>H',c)+body[4:]
  return struct.pack('>IHBB',0x60000000,len(body)+8,0,1)+ll+dst+b'\x3a\0\5\2\0\0\1\0'+body
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(b);return '?Vector'+str(len(vectors)-1)
 gp=vec(group);lp=vec(ll);zp=vec(bytes(16));sp=vec(b''.join(sources))
 fields=['joined','changeCount','changeDue','queryDue','queryCount','lastReporter','awaiting','failed','revision','version']
 state=dict(zip(fields,[0,0,0,-1,0,0,0,0,1,2]));stored=[]
 def add(name,code,rc=0,packet=b'',changes=None,store=None):
  nonlocal stored
  state.update(changes or {})
  if store is not None:stored=store
  cases.append(dict(name=name,expected=[rc]+[state[k] for k in fields],packet=(packet+bytes([165])*(1500-len(packet))).hex(),sources=(b''.join(stored)+bytes(1424-len(stored)*16)).hex()));steps.append(code)
 def step(name,now,mode=None,version=2,srcs=(),rc=None):
  packet=report(mode,version,srcs) if mode is not None else b''
  add(name,f'rc=IPv6MldGroupStep(@g,1,g\\revision,{now},{lp},@output[0],1500) : token=g\\awaiting',len(packet) if rc is None else rc,packet,{'awaiting':1} if packet else None)
 def sent(name,now,retry=100,result=1,changes=None,store=None):
  add(name,f'rc=IPv6MldGroupSent(@g,1,g\\revision,{now},token,{result},{retry})',-782 if result<0 else 0,changes=dict(awaiting=0,**(changes or {})),store=store)
 def query(name,now,delay,values=(),general=False,changes=None,store=None,rc=0):
  qp=zp if general else gp;src=vec(b''.join(values)) if values else '0'
  code=f'q\\group={qp} : q\\sourceCount={len(values)} : q\\sources={src} : q\\maxDelay=1000 : rc=IPv6MldGroupQuery(@g,1,g\\revision,{now},@q,{delay})'
  add(name,code,rc,changes=changes,store=store)
 add('init',f'rc=IPv6MldGroupInit(@g,1,1,2,{gp},@owned[0],1424,0)')
 add('join','rc=IPv6MldGroupChange(@g,1,1,0,1,2)',changes={'joined':1,'changeCount':2})
 step('prepare first join',0,4)
 sent('definitely unsent keeps repeats',1,result=0)
 step('prepare retry',2,4)
 add('stale token','rc=IPv6MldGroupSent(@g,1,1,3,token-1,1,100)',-781)
 step('pending prevents second output',3)
 sent('first confirmed',4,changes={'changeCount':1,'changeDue':104,'lastReporter':1})
 add('duplicate completion','rc=IPv6MldGroupSent(@g,1,1,5,token,1,100)',-781)
 step('before repeat',103)
 step('repeat due',104,4)
 add('leave while join pending','rc=IPv6MldGroupChange(@g,1,1,105,0,2)',changes={'joined':0,'changeCount':2,'changeDue':105})
 sent('old join cannot consume leave',106)
 step('leave report',107,3)
 sent('leave complete',108,changes={'changeCount':1,'changeDue':208})
 add('rejoin before second leave','rc=IPv6MldGroupChange(@g,1,1,109,1,2)',changes={'joined':1,'changeCount':2,'changeDue':109})
 step('new join',110,4)
 sent('new first confirmed',111,changes={'changeCount':1,'changeDue':211})
 step('new repeat due',211,4)
 sent('repeats finished',212,changes={'changeCount':0,'changeDue':312})
 query('source query',220,10,sources[:2],changes={'queryDue':230,'queryCount':2},store=sources[:2])
 step('query waits',229)
 step('source response',230,1,srcs=sources[:2])
 query('more sources while pending',231,20,sources[1:],changes={'queryCount':3},store=sources)
 sent('old response keeps newer query',232)
 step('merged source response',233,1,srcs=sources)
 sent('new response clears query',234,changes={'queryDue':-1,'queryCount':0},store=[])
 query('general query',240,50,general=True,changes={'queryDue':290})
 query('specific shortens full response',241,10,sources[:1],changes={'queryDue':251},store=[])
 step('full response waits',250)
 step('full response',251,2)
 sent('full response complete',252,changes={'queryDue':-1},store=[])
 query('zero random delay refused',260,0,rc=-780)
 add('v1 revision cancels','rc=IPv6MldGroupSync(@g,1,2,1,270)',changes={'revision':2,'version':1,'lastReporter':0})
 add('v1 nonreporter leave','rc=IPv6MldGroupChange(@g,1,2,271,0,2)',changes={'joined':0,'changeCount':1,'changeDue':271})
 step('v1 leave always announces Done',271,3,version=1)
 sent('v1 Done once',271,retry=1000,changes={'changeCount':0,'changeDue':1271})
 add('v1 join','rc=IPv6MldGroupChange(@g,1,2,272,1,2)',changes={'joined':1,'changeCount':2,'changeDue':272})
 step('v1 report',273,4,version=1)
 sent('v1 repeat scheduled',274,retry=1000,changes={'changeCount':1,'changeDue':1274,'lastReporter':1})
 add('other v1 report suppresses','rc=IPv6MldGroupHeardV1(@g,1,2,275)',changes={'changeCount':0,'lastReporter':0})
 query('v1 ignores source filtering',276,5,sources[:2],changes={'queryDue':281},store=[])
 step('v1 query report',281,2,version=1)
 add('mode switch cancels flight','rc=IPv6MldGroupSync(@g,1,3,2,282)',changes={'revision':3,'version':2,'awaiting':0,'queryDue':-1})
 add('old revision completion refused','rc=IPv6MldGroupSent(@g,1,2,283,token,1,100)',-781)
 add('leave v2','rc=IPv6MldGroupChange(@g,1,3,284,0,2)',changes={'joined':0,'changeCount':2,'changeDue':284})
 step('prepare leave',285,3)
 sent('ambiguous outcome fails membership',286,result=-1,changes={'failed':1})
 step('failed membership cannot emit',287,rc=-782)
 add('new generation resets',f'rc=IPv6MldGroupInit(@g,2,1,2,{gp},@owned[0],32,0)',changes=dict(zip(fields,[0,0,0,-1,0,0,0,0,1,2])),store=[])
 add('join new generation','rc=IPv6MldGroupChange(@g,2,1,0,1,2)',changes={'joined':1,'changeCount':2})
 add('output context overlap',f'rc=IPv6MldGroupStep(@g,2,1,1,{lp},@g,100)',-780)
 add('query view overlaps context','rc=IPv6MldGroupQuery(@g,2,1,1,@g,1)',-780)
 add('two sources fit owned capacity',f'q\\group={gp} : q\\maxDelay=1000 : q\\sourceCount=2 : q\\sources={sp} : rc=IPv6MldGroupQuery(@g,2,1,1,@q,10)',changes={'queryDue':11,'queryCount':2},store=sources[:2])
 add('union overflow leaves timer and list',f'q\\sourceCount=1 : q\\sources={sp}+32 : rc=IPv6MldGroupQuery(@g,2,1,2,@q,1)',-760)
 add('backwards time','rc=IPv6MldGroupChange(@g,2,1,0,0,2)',-780)
 add('stale interface generation','rc=IPv6MldGroupChange(@g,1,1,2,0,2)',-781)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld_policy.pbi"\nXIncludeFile "Anvil/Network/ipv6_mld_group.pbi"\n'
 s+='Global g.IPv6MldGroupState\nGlobal q.IPv6MldQueryView\nGlobal Dim owned.a[1424]\nGlobal Dim output.a[1500]\nProcedure Save(index.i,rc.i)\n Define p.i,i.i,busy.i\n p=$E1C00100+index*4096\n PokeI(p,rc)\n busy=0 : If g\\awaiting<>0 : busy=1 : EndIf\n'
 for k,field in enumerate(fields):s+=f' PokeI(p+{8+k*8},'+('busy' if field=='awaiting' else 'g\\'+field)+')\n'
 s+=' For i=0 To 1499 : PokeA(p+128+i,output[i]) : Next\n For i=0 To 1423 : PokeA(p+1728+i,owned[i]) : Next\nEndProcedure\nProcedure.i Main()\n Define i.i,rc.i,token.i\n For i=0 To 524287 : PokeA($E1C00000+i,0) : Next\n PokeI($E1C00000,$4D475231)\n MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf\n MmuEnableCached()\n'
 for k,code in enumerate(steps):s+='For i=0 To 1499 : output[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f'Vector{k}:\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c7ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
