"""Physical datagram-owner contract proof with controlled clock/link seams."""
from pathlib import Path
import argparse, hashlib, ipaddress, json, os, re, struct, subprocess
from pmf_compiler import resolve_compiler

def build(compiler, out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Hal/service_errors.pbi','Anvil/Core/udp_service.pbi','Anvil/Core/netconsole.pbi','Anvil/Network/udp_socket_types.pbi','Anvil/Network/net.pbi','Anvil/Network/ipv6_udp.pbi','Anvil/Network/ipv6_tcp.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 local=ipaddress.IPv6Address('fe80::1234').packed;peer=ipaddress.IPv6Address('fe80::5678').packed
 mac=bytes.fromhex('020102030405');remote=bytes.fromhex('020908070605')
 def checksum(b):
  b+=bytes(len(b)%2);n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(data):
  u=struct.pack('>4H',443,50001,len(data)+8,0)+data
  c=checksum(peer+local+struct.pack('>I3xB',len(u),17)+u) or 65535
  return mac+remote+b'\x86\xdd'+struct.pack('>IHBB',0x60000000,len(u),17,64)+peer+local+u[:6]+struct.pack('>H',c)+u[8:]
 cases=[];steps=[]
 def add(name,code,checks):
  steps.append(code)
  for expression,expected in checks:
   steps.append(f'PokeI($E1C00100+{len(cases)}*8,{expression})')
   cases.append(dict(name=name+' / '+expression,expected=expected))
 open6='h=UdpServiceOpen(6,1,50001)\n'
 receive='rc=NetInput(1,?Packet,65) : rc=NetServiceInput(1,0,rc)\n'
 advance='For j=0 To 3 : UdpServiceAdvance() : Next\n'
 send='rc=UdpServiceSendTo(h,@ep,@data[0],3)\n'
 reset='UdpServiceCloseAll() : NetInit() : NetSetMac(1,?Mac) : NetSetIPv4(1,$C0000201,$FFFFFF00,0)\nNetSetTcp6Hooks(@Assigned,@Resolve) : NetSetTcp6ScopedSelectHook(@SelectSource) : NetSetIPv6InputHook(@Receive)\nNetServiceSetUdpHook(0) : NetServiceSetUdp6Hook(0)\nticks=1000 : ready=1 : submit=77 : receipt=0 : submissions=0 : resolution=1\nudpControl\\cursor=0\nep\\family=6 : ep\\kind=1 : ep\\port=443\nFor j=0 To 15 : ep\\address[j]=PeekA(?Peer+j) : Next\ndata[0]=97 : data[1]=98 : data[2]=99\n'
 def case(name,code,checks):add(name,reset+code,checks)
 case('record layout','', [('SizeOf(UdpEndpoint)',40),('SizeOf(UdpDatagramInfo)',80),('SizeOf(UdpSocketStatus)',112)])
 case('legacy listener ownership','rc=NetUdpListen(1,51000,1)\na=NetUdpClaim(1,51000,99)\nb=NetUdpRelease(1,51000,99)', [('rc',1),('a',0),('b',0),('NetUdpPortOwner(1,51000)',1)])
 case('owner release and command isolation','NetUdpClaim(1,51000,99)\nrc=NetUdpBind(0,51000)\na=NetUdpBoundPort(2)\nb=NetUdpListen(1,51000,0)', [('rc',0),('a',0),('b',0),('NetUdpPortOwner(1,51000)',99)])
 case('all-interface refusal atomic','NetUdpBind(2,52000)\nNetUdpClaim(1,51000,99)\nrc=NetUdpBind(0,51000)', [('rc',0),('NetUdpBoundPort(2)',52000)])
 case('claim idempotence and exact release','rc=NetUdpClaim(1,51000,99)\na=NetUdpClaim(1,51000,99)\nb=NetUdpRelease(1,51000,99)', [('rc',1),('a',1),('b',1),('NetUdpPortOwner(1,51000)',0)])
 case('listener capacity','For j=0 To 15 : NetUdpClaim(1,51000+j,99+j) : Next\nrc=NetUdpClaim(1,52000,999)', [('rc',0),('NetError()',-126)])
 case('bound port cannot be stolen','NetUdpBind(1,51000)\nrc=NetUdpClaim(1,51000,99)', [('rc',0),('NetError()',-127)])
 for port in [67,68,5555,49200,49240,49263]:case(f'reserved port {port}',f'rc=UdpServiceOpen(6,1,{port})',[('rc',-106)])
 case('socket allocation',open6+'rc=UdpServiceStatus(h,@status)', [('rc',0),('status\\family',6),('status\\kind',1),('status\\port',50001),('status\\maxSend',1232)])
 case('duplicate port',open6+'rc=UdpServiceOpen(4,1,50001)', [('rc',-103)])
 case('socket pool capacity','For j=0 To 3 : h=UdpServiceOpen(6,1,50001+j) : Next\nrc=UdpServiceOpen(6,1,50009)', [('rc',-103)])
 case('stale handle after reuse',open6+'UdpServiceClose(h)\nh2=UdpServiceOpen(6,1,50001)\nrc=UdpServiceClose(h)\na=UdpServiceStatus(h2,@status)', [('rc',-108),('a',0),('h=h2',0)])
 case('cleanup releases ownership',open6+'UdpServiceCloseAll()\nrc=UdpServiceStatus(h,@status)', [('rc',-108),('NetUdpPortOwner(1,50001)',0)])
 case('whole receive and tuple',open6+receive+'rc=UdpServiceReceive(h,@info,@data[0],16)', [('rc',3),('info\\family',6),('info\\kind',1),('info\\localPort',50001),('info\\peerPort',443),('info\\receivedUs',1000),('data[0]',97),('data[2]',99)])
 case('short buffer preserves head',open6+receive+'data[0]=88\nrc=UdpServiceReceive(h,@info,@data[0],2)\na=UdpServicePeek(h,@info)\nUdpServiceStatus(h,@status)', [('rc',-102),('a',0),('info\\bytes',3),('data[0]',88),('status\\rxQueued',1)])
 case('empty receive is distinct',open6+'rc=UdpServiceReceive(h,@info,@data[0],16)', [('rc',-110)])
 case('zero datagram is valid',open6+'rc=NetInput(1,?Empty,62) : rc=NetServiceInput(1,0,rc)\nrc=UdpServiceReceive(h,@info,0,0)', [('rc',0),('info\\bytes',0)])
 case('queue overflow retains FIFO',open6+'For j=0 To 9\n'+receive+'Next\nUdpServiceStatus(h,@status)\nrc=UdpServiceDiscard(h)\nUdpServicePeek(h,@info)', [('rc',3),('status\\rxQueued',8),('status\\rxDropped',2),('info\\bytes',3)])
 case('metadata data alias refusal',open6+receive+'rc=UdpServiceReceive(h,@info,@info,80)\nUdpServiceStatus(h,@status)', [('rc',-102),('status\\rxQueued',1)])
 case('resident state alias refusal',open6+'rc=UdpServiceStatus(h,@udpControl)', [('rc',-102)])
 case('send queues copied payload',open6+send+'data[0]=88\nep\\port=444\n'+advance+'UdpServiceStatus(h,@status)', [('rc',1),('submissions',1),('status\\txState',2),('status\\txTicket',1),('PeekA(@sent[62])',97),('PeekA(@sent[57])',187)])
 case('busy send refuses replacement',open6+send+'rc=UdpServiceSendTo(h,@ep,@data[0],3)', [('rc',-110)])
 case('receipt completion does not resubmit',open6+send+advance+'receipt=1\n'+advance+'UdpServiceStatus(h,@status)', [('submissions',1),('status\\txState',3),('status\\txError',0)])
 case('expired receipt never replays',open6+send+advance+'receipt=-2\n'+advance+advance+'UdpServiceStatus(h,@status)', [('submissions',1),('status\\txState',4),('status\\txError',-105)])
 case('accepted packet deadline',open6+send+advance+'ticks=6001000\n'+advance+'UdpServiceStatus(h,@status)', [('submissions',1),('status\\txState',4),('status\\txError',-104)])
 case('queue refusal permits retry',open6+'submit=0\n'+send+advance+'submit=78\n'+advance+'UdpServiceStatus(h,@status)', [('submissions',2),('status\\txState',2)])
 case('unavailable tracked transport',open6+'submit=-2\n'+send+advance+'UdpServiceStatus(h,@status)', [('submissions',1),('status\\txState',4),('status\\txError',-100)])
 case('neighbor pending is nonblocking',open6+'resolution=0\n'+send+advance+'UdpServiceStatus(h,@status)', [('submissions',0),('status\\txState',1)])
 case('lost link fails pending send',open6+send+'ready=0\n'+advance+'UdpServiceStatus(h,@status)', [('submissions',0),('status\\txState',4),('status\\txError',-108)])
 case('close cancels unsubmitted send',open6+send+'UdpServiceClose(h)\n'+advance, [('submissions',0),('NetUdpPortOwner(1,50001)',0)])
 case('endpoint scope mismatch',open6+'ep\\kind=2\n'+send, [('rc',-102)])
 case('oversize refused',open6+'rc=UdpServiceSendTo(h,@ep,@data[0],1233)', [('rc',-102)])
 case('IPv4 ARP uses tracked submission','h=UdpServiceOpen(4,1,50001)\nep\\family=4\nFor j=0 To 15 : ep\\address[j]=0 : Next\nNetWriteBE32(@ep\\address,$C0000202)\n'+send+advance+'UdpServiceStatus(h,@status)', [('rc',1),('UdpEndpointValid(@ep)',1),('ep\\family',4),('ep\\kind',1),('ep\\port',443),('NetReadBE32(@ep\\address)',3221225986),('PeekA(@ep\\address)',192),('PeekA(@ep\\address+4)',0),('PeekA(@ep\\address+14)',0),('PeekA(@ep\\address+15)',0),('submissions',1),('status\\txState',1),('PeekA(@sent[12])',8),('PeekA(@sent[13])',6)])
 v4='h=UdpServiceOpen(4,1,50001)\nep\\family=4\nFor j=0 To 15 : PokeA(@ep\\address+j,0) : Next\nNetWriteBE32(@ep\\address,$C0000202)\n'
 case('IPv4 multicast refused',v4+'PokeA(@ep\\address,224)\n'+send,[('rc',-102),('submissions',0)])
 case('IPv4 unspecified prefix refused',v4+'PokeA(@ep\\address,0)\n'+send,[('rc',-102)])
 case('IPv4 nonzero tail refused',v4+'PokeA(@ep\\address+15,1)\n'+send,[('rc',-102)])
 case('FIFO preserves differing contents',open6+receive+'rc=NetInput(1,?Second,65) : rc=NetServiceInput(1,0,rc)\nrc=UdpServiceReceive(h,@info,@data[0],16)\na=data[0]\nrc=UdpServiceReceive(h,@info,@data[0],16)', [('a',97),('data[0]',88),('rc',3)])
 case('ARP receipt blocks duplicate request',v4+send+advance+'ticks=1101000\n'+advance+'UdpServiceStatus(h,@status)', [('submissions',1),('status\\txState',1)])
 core=(root/'Anvil/Core/netconsole.pbi').read_text()
 def proc(n):return re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',core,re.M|re.S)[0]+'\n'
 dispatcher='Global *gNetUdpSvcHook,*gNetUdp6SvcHook,*gNetDatagramHook\n'+''.join(proc(n) for n in ['NetServiceSetUdpHook','NetServiceSetUdp6Hook','NetServiceSetDatagramHook','NetServiceInput'])
 s='#HW_LINK_NONE=0\n#HW_LINK_WIRED=1\n#HW_LINK_FILE=5\n#DHCP_PORT_SERVER=67\n#DHCP_PORT_CLIENT=68\n#DHCPC_INIT=0\n'
 s+='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/net.pbi"\nXIncludeFile "Anvil/Core/udp_service.pbi"\n'+dispatcher+r'''
Global ticks.i,ready.i,submit.i,receipt.i,submissions.i,resolution.i
Global Dim sent.a[1514]
Procedure.i millis()
 ProcedureReturn 0
EndProcedure
Procedure.i HwMicros()
 ProcedureReturn ticks
EndProcedure
Procedure.i LinkKind()
 ProcedureReturn 1
EndProcedure
Procedure.i HwLinkHas(kind.i)
 ProcedureReturn kind=1
EndProcedure
Procedure.i HwLinkReady(kind.i)
 ProcedureReturn ready
EndProcedure
Procedure.i LinkSendTracked(kind.i,p.i,n.i)
 Define i.i
 submissions=submissions+1
 For i=0 To n-1 : sent[i]=PeekA(p+i) : Next
 ProcedureReturn submit
EndProcedure
Procedure.i LinkTxReceipt(kind.i,ticket.i)
 ProcedureReturn receipt
EndProcedure
Procedure netcon_SendStaged(kind.i)
EndProcedure
Procedure TcpInput()
EndProcedure
Procedure.i DhcpClientState(kind.i)
 ProcedureReturn 1
EndProcedure
Procedure DhcpClientInput(kind.i,p.i,n.i,t.i)
EndProcedure
Procedure.i NtpServiceInput(kind.i)
 ProcedureReturn 0
EndProcedure
Procedure.i NetConsoleOfferUdp(frame.i,kind.i)
 ProcedureReturn 0
EndProcedure
Procedure.i ProbeFirst(*p.UdpEndpoint)
 ProcedureReturn *p\address[0]
EndProcedure
Procedure.i ProbeTail(*p.UdpEndpoint)
 Define i.i,n.i
 For i=4 To 15 : n=n|*p\address[i] : Next
 ProcedureReturn n
EndProcedure
Procedure.i Assigned(kind.i,source.i)
 Define j.i
 For j=0 To 15
  If PeekA(source+j)<>PeekA(?Local+j) : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure
Procedure.i SelectSource(kind.i,destination.i,source.i)
 Define i.i
 For i=0 To 15 : PokeA(source+i,PeekA(?Local+i)) : Next
 ProcedureReturn kind
EndProcedure
Procedure.i Resolve(kind.i,source.i,destination.i,mac.i)
 Define i.i
 For i=0 To 5 : PokeA(mac+i,PeekA(?RemoteMac+i)) : Next
 ProcedureReturn resolution
EndProcedure
Procedure.i Receive(kind.i,frame.i,n.i,out.i,capacity.i)
 ProcedureReturn NetUdp6Input(kind,frame,n)
EndProcedure
Procedure.i Main()
 Define rc.i,a.i,b.i,h.i,h2.i,j.i
 Define ep.UdpEndpoint,info.UdpDatagramInfo,status.UdpSocketStatus
 Dim data.a[16]
 For j=0 To 131071 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Local',local),('Peer',peer),('Mac',mac),('RemoteMac',remote),('Packet',packet(b'abc')),('Second',packet(b'XYZ')),('Empty',packet(b''))]:
  s+=name+':\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
