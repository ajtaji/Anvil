"""Physical learned-DNS lease and scoped-route tests with hardware-state doubles."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Core/ipv6_service.pbi','Anvil/Core/dns_policy.pbi','Anvil/Network/net.pbi','Anvil/Network/ipv6_source.pbi','Anvil/Network/ipv6_rdnss_list.pbi','Anvil/Network/ipv6_rdnss.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 texts={n:(root/n).read_text(encoding='utf8') for n in names}
 def proc(file,name):return re.search(r'^Procedure(?:\.\w+)? '+re.escape(name)+r'\(.*?^EndProcedure',texts[file],re.M|re.S).group(0)+'\n'
 policy=texts['Anvil/Core/dns_policy.pbi'];policy=policy[policy.index('Structure NetDns6Lease'):]
 s=r'''
XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/ipv6_rdnss_list.pbi"
XIncludeFile "Anvil/Network/ipv6_source.pbi"
#NET_IF_KINDS=3
#IPV6_SERVICE_DNS=8
#IPV6_SERVICE_ADDRESSES=4
#IPV6_HOST_READY=3
#IPV6_NC_FAILED=5
Structure FixtureHost
 phase.i
EndStructure
Structure FixtureLifetime
 address.IPv6AddressStorage
EndStructure
Structure FixtureOwner
 generation.i
 lifetime.FixtureLifetime
EndStructure
Structure FixturePolicy
 state.i
EndStructure
Structure FixtureNeighbor
 policy.FixturePolicy
EndStructure
Structure IPv6DefaultRouter
 address.IPv6AddressStorage
EndStructure
Global Dim ipv6svcHost.FixtureHost[3]
Global Dim ipv6svcEpoch.i[3] : Global Dim ipv6svcState.i[3] : Global Dim ready.i[3]
Global Dim ipv6svcDns.IPv6RdnssList[3]
Global Dim ipv6svcDnsRows.IPv6RdnssEntry[24]
Global Dim ipv6svcOnLink.i[3] : Global Dim ipv6svcRouters.i[3]
Global Dim ipv6svcRouterRows.a[384] : Global Dim ipv6svcAddresses.a[48]
Global Dim ipv6svcOwner.FixtureOwner[12] : Global Dim ipv6svcOwnerUsed.i[12]
Global Dim ipv6svcNeighbor.FixtureNeighbor[24]
Global *net_tcp6ScopedSelectHook
Global now.i,preferred.i=2
Procedure.i ipv6svc_Now()
 ProcedureReturn now
EndProcedure
Procedure.i HwLinkReady(kind.i)
 ProcedureReturn ready[kind]
EndProcedure
Procedure.i LinkKind()
 ProcedureReturn preferred
EndProcedure
Procedure.i IPv6PrefixListMatch(s.i,gen.i,t.i,dest.i)
 ProcedureReturn 0
EndProcedure
Procedure.i ipv6svc_NeighborFind(kind.i,addr.i)
 ProcedureReturn -1
EndProcedure
Procedure.i IPv6DefaultRoutersSelect(s.i,gen.i,t.i,failed.i)
 ProcedureReturn 0
EndProcedure
Procedure.i IPv6AddressOwnerStatus(s.i,gen.i,t.i)
 ProcedureReturn 2
EndProcedure
Procedure.i WrongLink(kind.i,dest.i,source.i)
 ProcedureReturn 3-kind
EndProcedure
'''+policy
 for name in ['ipv6svc_Select','IPv6ServiceSelect','IPv6ServiceSelectOn','IPv6ServiceDnsSelect','IPv6ServiceDnsValid']:s+=proc('Anvil/Core/ipv6_service.pbi',name)
 for name in ['NetSetTcp6ScopedSelectHook','NetTcp6SelectOn']:s+=proc('Anvil/Network/net.pbi',name)
 s+=r'''
Global lease.NetDns6Lease,learned.IPv6RdnssAdvertisement,dest.IPv6AddressStorage,result.IPv6AddressStorage
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*64 : PokeI(p,rc) : PokeI(p+8,lease\kind) : PokeI(p+16,lease\generation)
 For i=0 To 15 : PokeA(p+24+i,PeekA(@lease\address+i)) : PokeA(p+40+i,PeekA(@result+i)) : Next
EndProcedure
Procedure.i Main()
 Define i.i,kind.i,rc.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$52445343)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 For kind=1 To 2
  ready[kind]=1 : ipv6svcState[kind]=2 : ipv6svcHost[kind]\phase=#IPV6_HOST_READY : ipv6svcEpoch[kind]=1
  ipv6svcAddresses[kind*16]=$FE : ipv6svcAddresses[kind*16+1]=$80 : ipv6svcAddresses[kind*16+15]=kind
  IPv6RdnssListInit(@ipv6svcDns[kind],kind,1,@ipv6svcDnsRows[kind*8],8,0)
 Next
 PokeA(@dest,$FE) : PokeA(@dest+1,$80) : PokeA(@dest+15,53)
 For i=0 To 15 : PokeA(@learned\address+i,PeekA(@dest+i)) : Next
 learned\seconds=1
'''
 cases=[]
 def add(label,code,expected,source=None):
  i=len(cases);cases.append(dict(name=label,rc=expected,source=source));return ' For i=0 To 15 : PokeA(@result+i,$A5) : Next\n'+code+f'\n Save({i},rc)\n'
 s+=add('unbound provider','rc=NetDnsLearned6Select(@lease)',0)
 s+=' NetDnsLearned6Bind(@IPv6ServiceDnsSelect,@IPv6ServiceDnsValid)\n NetSetTcp6ScopedSelectHook(@IPv6ServiceSelectOn)\n'
 s+=add('empty repositories','rc=NetDnsLearned6Select(@lease)',0)
 s+=add('unscoped selects preferred link','rc=IPv6ServiceSelect(@dest,@result)',2,2)
 s+=add('scope overrides preferred link','rc=NetTcp6SelectOn(1,@dest,@result)',1,1)
 s+=add('unavailable scoped link cannot migrate','ready[1]=0 : rc=NetTcp6SelectOn(1,@dest,@result)',-883)
 s+=add('other link remains reachable','rc=NetTcp6SelectOn(2,@dest,@result)',2,2)
 s+=add('zero scope refused','rc=NetTcp6SelectOn(0,@dest,@result)',-881)
 s+=add('overlapping addresses refused','rc=NetTcp6SelectOn(1,@dest,@dest)',-881)
 s+=add('wrong-link hook result refused','NetSetTcp6ScopedSelectHook(@WrongLink) : rc=NetTcp6SelectOn(1,@dest,@result)',-883)
 s+=' NetSetTcp6ScopedSelectHook(@IPv6ServiceSelectOn) : ready[1]=1\n'
 s+=' IPv6RdnssListApply(@ipv6svcDns[1],1,1,0,@learned,1)\n'
 s+=add('first link learned','rc=NetDnsLearned6Select(@lease)',1)
 s+=add('current lease valid','rc=NetDnsLearned6Valid(@lease)',1)
 s+=add('link loss invalidates lease','ready[1]=0 : rc=NetDnsLearned6Valid(@lease)',0)
 s+=' ready[1]=1 : now=1000\n'
 s+=add('exact expiry invalidates lease','rc=NetDnsLearned6Valid(@lease)',0)
 s+=' learned\\seconds=$FFFFFFFF : IPv6RdnssListApply(@ipv6svcDns[1],1,1,now,@learned,1)\n IPv6RdnssListApply(@ipv6svcDns[2],2,1,now,@learned,1)\n'
 s+=add('renewed lease valid','rc=NetDnsLearned6Valid(@lease)',1)
 s+=' ipv6svcEpoch[1]=2 : IPv6RdnssListInit(@ipv6svcDns[1],1,2,@ipv6svcDnsRows[8],8,now)\n'
 s+=add('generation change invalidates lease','rc=NetDnsLearned6Valid(@lease)',0)
 s+=add('same server on second link independent','rc=NetDnsLearned6Select(@lease)',2)
 s+=add('second lease valid','rc=NetDnsLearned6Valid(@lease)',1)
 s+=' learned\\seconds=0 : IPv6RdnssListApply(@ipv6svcDns[2],2,1,now,@learned,1)\n'
 s+=add('withdrawal invalidates lease','rc=NetDnsLearned6Valid(@lease)',0)
 s+=add('withdrawn server not selected','rc=NetDnsLearned6Select(@lease)',0)
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
