"""Physical IPv6 neighbor owner: wire packets, receipt timing and cache transitions."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_neighbor_owner.pbi','Anvil/Network/ipv6_reachability.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda s:ipaddress.IPv6Address(s).packed
 local=addr('fe80::1234');target=addr('fe80::5678');group=addr('ff02::1:ff00:5678');allnodes=addr('ff02::1');wrong=addr('fe80::9999')
 mac=bytes.fromhex('020102030405');peer=bytes.fromhex('020908070605');changed=bytes.fromhex('020a0b0c0d0e');m=int.from_bytes(peer,'little');m2=int.from_bytes(changed,'little')
 def packet(src,dst,body):
  pseudo=src+dst+struct.pack('>I3xB',len(body),58)+body
  if len(pseudo)&1:pseudo+=b'\0'
  n=sum(struct.unpack('>'+str(len(pseudo)//2)+'H',pseudo))
  while n>>16:n=(n&65535)+(n>>16)
  body=body[:2]+struct.pack('>H',(~n)&65535)+body[4:]
  return struct.pack('>IHBB',0x60000000,len(body),58,255)+src+dst+body
 def ether(sm,dm,p):return dm+sm+b'\x86\xdd'+p
 body=b'\x87\0\0\0'+bytes(4)+target+b'\x01\x01'+mac
 multicast=ether(mac,b'\x33\x33'+group[-4:],packet(local,group,body))
 def probe(dm):return ether(mac,dm,packet(local,target,body))
 def advert(flags,tm=peer,dst=local,tgt=target,dm=None):
  option=b'' if tm is None else b'\x02\x01'+tm
  b=b'\x88\0\0\0'+struct.pack('>I',flags)+tgt+option
  return ether(peer,dm if dm is not None else (b'\x33\x33'+dst[-4:] if dst[0]==255 else mac),packet(target,dst,b))
 cases=[];steps=[];vectors=[]
 state=dict(g=1,s=0,a=0,state=1,router=0,d=0,p=0,m=0,t=0)
 def add(name,code,rc,wire=b'',**changes):
  state.update(changes);cases.append(dict(name=name,expected=[rc]+list(state.values()),wire=wire.hex()));steps.append(code)
 def init(g,target_name='Target'):return f'rc=IPv6NeighborOwnerInit(@owner,{g},?{target_name},?Mac,0,1000)'
 def use(t,g=1):return f'rc=IPv6NeighborOwnerUse(@owner,{g},{t})'
 def step(t,g=1):return f'rc=IPv6NeighborOwnerStep(@owner,{g},{t},?Local,@output[0],1514)'
 def sent(t,tok,result=1,g=1):return f'rc=IPv6NeighborOwnerSent(@owner,{g},{t},{tok},{result})'
 def inp(b,t,g=2):vectors.append(b);return f'rc=IPv6NeighborOwnerInput(@owner,{g},{t},?Local,?V{len(vectors)-1},{len(b)},30000)'
 add('initial incomplete',init(1),0)
 add('data must wait for resolution',use(1),0,t=1)
 add('multicast solicitation exact bytes',step(1),86,multicast,s=1,a=1,p=1,d=1001)
 add('pending receipt suppresses further attempts',step(5000),0,t=5000)
 add('interval begins at confirmed completion',sent(5001,1),0,a=0,d=6001,t=5001)
 add('full retransmit interval',step(6000),0,t=6000)
 add('second solicitation',step(6001),86,multicast,s=2,a=2,p=2,d=7001,t=6001)
 add('queue refusal preserves wire-attempt budget',sent(6002,2,0),0,a=0,p=1,d=7002,t=6002)
 add('second wire attempt after queue backpressure',step(7002),86,multicast,s=3,a=3,p=2,d=8002,t=7002)
 add('ambiguous link failure consumes attempt',sent(7003,3,-1),0,a=0,d=8003,t=7003)
 add('wait before final attempt',step(8002),0,t=8002)
 add('third wire attempt',step(8003),86,multicast,s=4,a=4,p=3,d=9003,t=8003)
 add('invalid receipt outcome refused',sent(8004,4,2),-870)
 add('last wire attempt completion',sent(8004,4),0,a=0,d=9004,t=8004)
 add('three wire attempts fail queued data',step(9004),-872,state=6,d=0,t=9004)
 add('failed neighbor unusable',use(9005),-2,t=9005)
 add('new link generation clears old owner',init(2),0,g=2,s=0,a=0,state=1,router=0,d=0,p=0,m=0,t=0)
 add('RA learned router is stale','rc=IPv6NeighborOwnerLearn(@owner,2,100,?PeerMac,1)',1,state=3,router=1,m=m,t=100)
 add('traffic starts delayed probing',use(100,2),1,state=4,d=5100)
 add('no early probe',step(5099,2),0,t=5099)
 add('unicast probe exact bytes',step(5100,2),86,probe(peer),s=1,a=1,state=5,p=1,d=6100,t=5100)
 add('queued probe does not time out',step(9000,2),0,t=9000)
 add('solicited NA resolves pending probe',inp(advert(0xe0000000),9001),1,a=0,state=2,p=0,d=39001,t=9001)
 add('late send receipt cannot overwrite reachable state',sent(9002,1,g=2),-871)
 add('reachability expires on use',use(39001,2),1,state=4,d=44001,t=39001)
 add('probe after stale delay',step(44001,2),86,probe(peer),s=2,a=2,state=5,p=1,d=45001,t=44001)
 add('upper-layer forward confirmation','rc=IPv6NeighborOwnerConfirm(@owner,2,44002,30000)',1,a=0,state=2,p=0,d=74002,t=44002)
 add('old completion cannot clear upper confirmation',sent(44003,2,g=2),-871)
 add('changed unsolicited NA demotes router',inp(advert(0x20000000,changed,allnodes),44004),2,state=3,router=0,d=0,m=m2,t=44004)
 add('changed hardware address usable but stale',use(44005,2),1,state=4,d=49005,t=44005)
 add('probe goes to changed MAC',step(49005,2),86,probe(changed),s=3,a=3,state=5,p=1,d=50005,t=49005)
 add('nonoverride conflict ignored during probe',inp(advert(0x40000000,peer),49006),0,t=49006)
 add('ignored advertisement preserves pending receipt',sent(49007,3,g=2),0,a=0,d=50007,t=49007)
 add('solicited matching NA confirms',inp(advert(0x60000000,changed),49008),1,state=2,p=0,d=79008,t=49008)
 bad=bytearray(advert(0x60000000,changed));bad[-1]^=1
 add('checksum refusal preserves state',inp(bytes(bad),49009),-721)
 add('different target ignored',inp(advert(0x60000000,changed,tgt=wrong),49010),0)
 add('wrong Ethernet destination ignored',inp(advert(0x60000000,changed,dm=peer),49011),0)
 add('unassigned IPv6 destination ignored',inp(advert(0x60000000,changed,dst=wrong),49012),0)
 add('zero learned MAC refused','rc=IPv6NeighborOwnerLearn(@owner,2,49013,?ZeroMac,1)',-870)
 add('multicast target init refused',init(3,'Group'),-870)
 add('stale generation refused',use(49013,1),-871)
 add('backward clock refused',use(49007,2),-870)
 add('whole owner output alias','rc=IPv6NeighborOwnerStep(@owner,2,49013,?Local,@owner,1514)',-870)
 add('unspecified source cannot probe','rc=IPv6NeighborOwnerStep(@owner,2,49013,?ZeroAddress,@output[0],1514)',-870)
 add('clock ceiling refused',use(0x7fffffff00000000,2),-870)
 add('fresh incomplete entry',init(3),0,g=3,s=0,a=0,state=1,router=0,d=0,p=0,m=0,t=0)
 add('NA without link option cannot resolve incomplete',inp(advert(0x60000000,None),1,3),0,t=1)
 add('unsolicited advertisement resolves only to stale',inp(advert(0x20000000,changed,allnodes),2,3),1,state=3,m=m2,t=2)
 add('new generation for stale token proof',init(4),0,g=4,s=0,a=0,state=1,d=0,p=0,m=0,t=0)
 add('outstanding old generation solicitation',step(0,4),86,multicast,s=1,a=1,p=1,d=1000)
 add('replacement invalidates pending token',init(5),0,g=5,s=0,a=0,state=1,d=0,p=0,m=0,t=0)
 add('old generation completion refused',sent(1,1,g=4),-871)
 add('existing DAD codec remains exact','rc=IPv6NeighborSolicit(@output[0],1514,?ZeroAddress,?Target,?Mac)',64,packet(bytes(16),group,b'\x87\0\0\0'+bytes(4)+target))
 add('unicast DAD is refused','rc=IPv6NeighborProbe(@output[0],1514,?ZeroAddress,?Target,?Mac)',-720)
 add('short unicast probe capacity refused','rc=IPv6NeighborProbe(@output[0],64,?Local,?Target,?Mac)',-720)
 assert len(cases)<=63
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_reachability.pbi"\nXIncludeFile "Anvil/Network/ipv6_neighbor_owner.pbi"\n'+r"""
Global owner.IPv6NeighborOwner
Global Dim output.a[1514]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,owner\generation) : PokeI(p+16,owner\serial) : PokeI(p+24,owner\awaiting)
 PokeI(p+32,owner\policy\state) : PokeI(p+40,owner\policy\router) : PokeI(p+48,owner\policy\deadline)
 PokeI(p+56,owner\policy\probes) : PokeI(p+64,owner\policy\mac) : PokeI(p+72,owner\lastNow)
 For i=0 To 1513 : PokeA(p+80+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$4E4F574E)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 for k,code in enumerate(steps):s+=' For i=0 To 1513 : output[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Target',target),('Local',local),('Group',group),('Mac',mac),('PeerMac',peer),('ZeroMac',bytes(6)),('ZeroAddress',bytes(16))]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
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
