"""Build deterministic physical checks of Anvil's DNS TCP fallback owner."""
from pathlib import Path
import argparse, hashlib, json, os, re, struct, subprocess
from pmf_compiler import resolve_compiler
from build_dns_reply_cpu import packet, answer


def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Core/payload_net.pbi','Anvil/Hal/abi.pbi','Anvil/Network/dns_codec.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Core/dns_policy.pbi']
    owner=(root/names[0]).read_text(encoding='utf8')
    def proc(name):
        m=re.search(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',owner,re.M|re.S);assert m,name;return m[0]
    shared='\n'.join(proc(n) for n in ['paynet_DnsCloseListener','paynet_DnsCloseTcp','paynet_DnsFail','paynet_DnsCaptureAnswer','PayNetDnsInput','paynet_DnsTcpStep','paynet_DnsCancel','paynet_DnsStep','paynet_DnsResolveType','PayNetDnsResolve','PayNetDnsResolve6'])
    start=owner.index('Procedure.i paynet_Lower(')
    end=owner.index('; ======================================================================',owner.index('Procedure paynet_CachePut(',start))
    shared=owner[start:end]+'\n'+shared
    constants='\n'.join(line for line in owner.splitlines() if line.startswith('#PAYNET_'))
    needed=set(re.findall(r'#[A-Z][A-Z_0-9]*',shared))|{'#SVC_EIO','#SVC_TCP_CONNECTING','#SVC_TCP_OPEN','#SVC_TCP_PEER_CLOSED'}
    constants+='\n'+'\n'.join(line for line in (root/names[1]).read_text(encoding='utf8').splitlines() if re.match(r'^#[A-Z][A-Z_0-9]*\s*=',line) and line.split('=')[0].strip() in needed)
    lease=re.search(r'^Structure NetDns6Lease.*?^EndStructure',(root/'Anvil/Core/dns_policy.pbi').read_text(encoding='utf8'),re.M|re.S).group(0)
    globals_=lease+'\n'+owner[owner.index('Global paynet_dnsTcp.i'):owner.index('; ---- TCP ----')]
    s='XIncludeFile "Anvil/Network/ipv6_address.pbi"\nXIncludeFile "Anvil/Network/dns_codec.pbi"\n#HW_LINK_NONE=0\n'+constants+'\n'+globals_+r'''
Global gSvcDetail.i
Global chosenFamily.i,openedFamily.i,resolverResult.i,routeResult.i,v4Checks.i
Global learnedKind.i,learnedValid.i=1,static4.i,openedScope.i
Procedure.i SettingsGet(key.i)
 ProcedureReturn static4
EndProcedure
Procedure.i EthKeyDns()
 ProcedureReturn "net.dns"
EndProcedure
Procedure.i NetDnsLearned6Select(*lease.NetDns6Lease)
 Define i.i
 If learnedKind>0
  *lease\kind=learnedKind : *lease\generation=1
  For i=0 To 15 : PokeA(@*lease\address+i,32+i) : Next
 EndIf
 ProcedureReturn learnedKind
EndProcedure
Procedure.i NetDnsLearned6Valid(*lease.NetDns6Lease)
 ProcedureReturn learnedValid
EndProcedure
Procedure.i PayNetTcpOpen6On(kind.i,destination.i,port.i)
 openedScope=kind
 ProcedureReturn PayNetTcpOpen6(destination,port)
EndProcedure
Procedure.i NetDnsResolver6(out.i)
 Define i.i
 If resolverResult=16
  For i=0 To 15 : PokeA(out+i,i+32) : Next
 EndIf
 ProcedureReturn resolverResult
EndProcedure
Procedure.i NetTcp6Select(destination.i,source.i)
 ProcedureReturn routeResult
EndProcedure
Procedure.i PayNetTcpOpen6(destination.i,port.i)
 openedFamily=6
 ProcedureReturn PayNetTcpOpen(0,port)
EndProcedure
Global Dim pendingOut.a[16]
Global mode.i,opens.i,closes.i,listeners.i,sends.i,received.i,sent.i,replyLen.i
Global Dim mockWire.a[4096]
Global Dim mockSent.a[512]
Global Dim udp.a[1024]
Global udpLen.i
Procedure.i NetIfUsable(kind.i)
 ProcedureReturn 1
EndProcedure
Procedure.i NetIfUsableCount()
 v4Checks=v4Checks+1
 ProcedureReturn 0
EndProcedure
Procedure.i NetIfNext(kind.i)
 ProcedureReturn 0
EndProcedure
Procedure.i NetNextHop(kind.i,ip.i)
 ProcedureReturn 0
EndProcedure
Procedure.i paynet_DnsFor(kind.i)
 ProcedureReturn 0
EndProcedure
Procedure.i ParseDotted(name.i)
 ProcedureReturn -1
EndProcedure
Procedure NetServiceSetUdpHook(callback.i)
EndProcedure
Procedure paynet_DnsSend(now.i)
EndProcedure
Procedure.i millis()
 ProcedureReturn 100
EndProcedure
Procedure.i NetUdpRxData()
 ProcedureReturn @udp[0]
EndProcedure
Procedure.i NetUdpRxLen()
 ProcedureReturn udpLen
EndProcedure
Procedure.i NetUdpRxDstPort()
 ProcedureReturn 5300
EndProcedure
Procedure.i NetUdpRxPort()
 ProcedureReturn 53
EndProcedure
Procedure.i NetUdpRxFrom()
 If mode=102 : ProcedureReturn $02020202 : EndIf
 ProcedureReturn $01010101
EndProcedure
Procedure.i NetRxTo()
 ProcedureReturn $C0000202
EndProcedure
Procedure.i NetUdpListen(kind.i,port.i,enabled.i)
 listeners=listeners+1 : ProcedureReturn 1
EndProcedure
Procedure.i PayNetTcpOpen(ip.i,port.i)
 If openedFamily=0 : openedFamily=4 : EndIf
 opens=opens+1
 If mode=8 And opens<3 : ProcedureReturn #SVC_EBUSY : EndIf
 If mode=9 : ProcedureReturn #SVC_EIO : EndIf
 ProcedureReturn 7
EndProcedure
Procedure.i PayNetTcpClose(h.i)
 closes=closes+1 : ProcedureReturn 0
EndProcedure
Procedure.i PayNetTcpState(h.i)
 If mode=3 Or mode=14 Or mode=15 : ProcedureReturn #SVC_TCP_CONNECTING : EndIf
 If (mode=1 Or mode=2) And sent=paynet_dnsTcpTxLen : ProcedureReturn #SVC_TCP_PEER_CLOSED : EndIf
 ProcedureReturn #SVC_TCP_OPEN
EndProcedure
Procedure.i PayNetTcpSend(h.i,p.i,n.i)
 Define i.i
 sends=sends+1
 If mode=4 : ProcedureReturn #SVC_EIO : EndIf
 If mode=12 : ProcedureReturn n+1 : EndIf
 If n>3 : n=3 : EndIf
 For i=0 To n-1 : mockSent[sent+i]=PeekA(p+i) : Next
 sent=sent+n : ProcedureReturn n
EndProcedure
Procedure.i PayNetTcpRecv(h.i,p.i,n.i)
 Define i.i,remaining.i
 If sent<paynet_dnsTcpTxLen : ProcedureReturn 0 : EndIf
 If mode=5 : ProcedureReturn #SVC_EIO : EndIf
 If mode=11 : ProcedureReturn n+1 : EndIf
 remaining=replyLen-received
 If mode=2 : remaining=6-received : EndIf
 If remaining<=0 : ProcedureReturn 0 : EndIf
 If n>remaining : n=remaining : EndIf
 If received<2 : n=1 : ElseIf n>7 : n=7 : EndIf
 For i=0 To n-1 : PokeA(p+i,mockWire[received+i]) : Next
 received=received+n : ProcedureReturn n
EndProcedure
'''+shared+r'''
Procedure Run(index.i,bytes.i,qtype.i)
 Define i.i,now.i,p.i,wrong.i,host.i,transition.i
 openedScope=0 : paynet_dnsLearned=0
 openedFamily=0 : paynet_dnsFamily=chosenFamily
 mode=index % 16 : paynet_dnsType=qtype : opens=0 : closes=0 : listeners=0 : sends=0 : received=0 : sent=0
 replyLen=bytes
 For i=0 To bytes-1 : Read.a mockWire[i] : Next
 paynet_dnsState=#PAYNET_DNS_WAIT : paynet_dnsTcp=0 : paynet_dnsPort=5300
 paynet_dnsKind=1 : paynet_dnsServer=$01010101 : paynet_dnsQid=$1234
 For i=0 To 15 : paynet_dnsAnswer6[i]=0 : Next
 paynet_dnsAnswer=0 : paynet_dnsTtl=0 : paynet_dnsErr=0 : paynet_dnsStart=100
 If mode=14 : paynet_dnsStart=$FFFFFF00 : EndIf
 host="example.test"
 For i=0 To 11 : paynet_dnsName[i]=PeekA(host+i) : Next
 paynet_dnsName[12]=0 : paynet_dnsLocalIp=$C0000202
 transition=PayNetDnsInput(1)
 If paynet_dnsState<>#PAYNET_DNS_TCP : transition=-1 : EndIf
 now=paynet_dnsStart
 For i=0 To 99
  paynet_DnsTcpStep(now)
  If mode=15 : paynet_DnsCancel() : Break : EndIf
  If paynet_dnsState<>#PAYNET_DNS_TCP : Break : EndIf
  now=(now+100) & $FFFFFFFF
 Next
 If sent>0 And sent=paynet_dnsTcpTxLen
  If NetReadBE16(@mockSent[0])<>DnsQueryLen() : wrong=1 : EndIf
  For i=0 To DnsQueryLen()-1
   If mockSent[i+2]<>PeekA(DnsQueryBuf()+i) : wrong=1 : EndIf
  Next
 EndIf
 p=$E1C00100+index*96
 PokeI(p,paynet_dnsState) : PokeI(p+8,paynet_dnsErr)
 PokeI(p+16,paynet_dnsAnswer) : PokeI(p+24,paynet_dnsTtl)
 PokeI(p+32,opens) : PokeI(p+40,closes) : PokeI(p+48,listeners)
 For i=0 To 15 : PokeA($E1C02800+index*16+i,paynet_dnsAnswer6[i]) : Next
 PokeI(p+56,sent) : PokeI(p+64,wrong) : PokeI(p+72,paynet_dnsTcp) : PokeI(p+80,transition) : PokeI(p+88,openedFamily)
EndProcedure
Procedure ProofDnsDispatch(which.i)
 Define host.i,i.i,p.i,rc.i
 paynet_dnsType=#DNS_QTYPE_A
 mode=100+which : paynet_dnsState=#PAYNET_DNS_WAIT : paynet_dnsRejects=0
 paynet_dnsPort=5300 : paynet_dnsLocalIp=$C0000202 : paynet_dnsKind=1
 paynet_dnsServer=$01010101 : paynet_dnsQid=$1234
 host="example.test"
 For i=0 To 11 : paynet_dnsName[i]=PeekA(host+i) : Next
 paynet_dnsName[12]=0
 If which=0 : paynet_dnsName[0]=122 : EndIf
 If which=1 : paynet_dnsQid=$4321 : EndIf
 rc=PayNetDnsInput(1)
 p=$E1C02000+which*24
 PokeI(p,rc) : PokeI(p+8,paynet_dnsState) : PokeI(p+16,paynet_dnsRejects)
EndProcedure
Procedure PendingType()
 Define i.i,name.i,p.i
 name="example.test" : p=$E1C03000
 For i=0 To 3 : paynet_cacheUsed[i]=0 : Next
 paynet_CopyName(@paynet_dnsName[0],name)
 paynet_dnsType=#DNS_QTYPE_AAAA : paynet_dnsState=#PAYNET_DNS_WAIT
 paynet_dnsStart=100 : paynet_dnsDeadline=1000 : paynet_dnsKind=1
 For i=0 To 15 : pendingOut[i]=$A5 : Next
 PokeI(p,PayNetDnsResolve(name))
 PokeI(p+8,PayNetDnsResolve6(name,@pendingOut[0]))
 PokeI(p+16,PayNetDnsResolve6("other.test",@pendingOut[0]))
 PokeI(p+24,paynet_dnsType) : PokeI(p+32,paynet_dnsState)
 paynet_dnsState=#PAYNET_DNS_FAIL : paynet_dnsErr=#SVC_EIO
 PokeI(p+40,PayNetDnsResolve6(name,@pendingOut[0]))
 PokeI(p+48,paynet_dnsState)
 PokeI(p+56,PayNetDnsResolve6(name,0))
 For i=0 To 15 : PokeA(p+64+i,pendingOut[i]) : Next
EndProcedure
Procedure Start6(index.i)
 Define p.i,rc.i,i.i,name.i,qtype.i
 p=$E1C03400+index*128
 For i=0 To 3 : paynet_cacheUsed[i]=0 : Next
 paynet_DnsCancel()
 learnedKind=0 : learnedValid=1 : static4=0 : openedScope=0
 resolverResult=16 : routeResult=2 : mode=3 : v4Checks=0
 opens=0 : closes=0 : listeners=0 : openedFamily=0
 paynet_dnsErr=0 : paynet_dnsFamily=4
 name="example.test" : qtype=#DNS_QTYPE_A
 If index=1 : qtype=#DNS_QTYPE_AAAA : EndIf
 If index=2 : resolverResult=-1 : EndIf
 If index=3 : routeResult=0 : EndIf
 If index=4 : name="bad..test" : EndIf
 If index=5 : resolverResult=0 : EndIf
 If index=6 : mode=8 : EndIf
 If index=7 : mode=9 : EndIf
 If index>=8 : resolverResult=0 : learnedKind=2 : EndIf
 If index=9 : learnedValid=0 : EndIf
 If index=10 : static4=1 : EndIf
 If index=11 : resolverResult=-1 : EndIf
 rc=paynet_DnsResolveType(name,qtype,@pendingOut[0])
 PokeI(p,rc) : PokeI(p+8,paynet_dnsState) : PokeI(p+16,paynet_dnsFamily)
 PokeI(p+24,opens) : PokeI(p+32,listeners) : PokeI(p+40,v4Checks)
 PokeI(p+48,paynet_dnsPort) : PokeI(p+56,openedFamily)
 For i=0 To 15 : PokeA(p+64+i,paynet_dnsServer6[i]) : Next
 If index=12
  learnedValid=0 : paynet_DnsTcpStep(101)
  PokeI(p+112,paynet_dnsState) : PokeI(p+120,paynet_dnsErr)
 EndIf
 paynet_DnsCancel()
 PokeI(p+104,openedScope)
 PokeI(p+80,paynet_dnsState) : PokeI(p+88,paynet_dnsTcp) : PokeI(p+96,closes)
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$444E5431) : PokeI($E1C00008,64)
'''
    cases=[];packets=[];udps=[]
    for family,qtype in [(4,1),(4,28),(6,1),(6,28)]:
        s+=f' chosenFamily={family}\n'
        addr=b'\x01\x02\x03\x04' if qtype==1 else bytes.fromhex('20010db800000000123456789abcdef0')
        udp=packet([answer(b'\xc0\x0c',qtype,addr,45)],flags=0x8380,qtype=qtype);udps.append(udp)
        s+=f' Restore UdpPacket{qtype}\n udpLen={len(udp)}\n For i=0 To udpLen-1 : Read.a udp[i] : Next\n'
        for i in range(16):
            raw=packet([answer(b'\xc0\x0c',qtype,addr,45)],question='another.test' if i==6 else 'example.test',flags=0x8380 if i==10 else 0x8180,qtype=qtype)
            if i==13:raw=packet([],qtype=qtype)
            raw=struct.pack('>H',11 if i==7 else len(raw))+raw
            index=len(cases);packets.append(raw);cases.append(index);s+=f' Restore Packet{index}\n Run({index},{len(raw)},{qtype})\n'
    s+=f' Restore UdpPacket1\n udpLen={len(udps[0])}\n For i=0 To udpLen-1 : Read.a udp[i] : Next\n'
    s+=' ProofDnsDispatch(0) : ProofDnsDispatch(1) : ProofDnsDispatch(2)\n PendingType()\n For i=0 To 12 : Start6(i) : Next\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for kind,raw in zip([1,28],udps):s+=f' UdpPacket{kind}:\n Data.a '+','.join(map(str,raw))+'\n'
    for i,raw in enumerate(packets):
        s+=f'Packet{i}:\n'
        for j in range(0,len(raw),24):s+=' Data.a '+','.join(map(str,raw[j:j+24]))+'\n'
    s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
