"""Physical shared UDP6 stack and dispatcher proof; routes/owners are controlled seams."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/net.pbi','Anvil/Network/ipv6_udp.pbi','Anvil/Network/ipv6_tcp.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','Anvil/Core/netconsole.pbi','Anvil/Core/ipv6_service.pbi','RaspberryPi4/Lib/mmu.pi4']
 local=ipaddress.IPv6Address('fe80::1234').packed;peer=ipaddress.IPv6Address('fe80::5678').packed
 mac=bytes.fromhex('020102030405');remote=bytes.fromhex('020908070605')
 def checksum(b):
  b+=bytes(len(b)%2);n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def udp6(data=b'abc',sport=443,dport=49152,src=peer,dst=local,dm=mac,sm=remote):
  u=struct.pack('>4H',sport,dport,len(data)+8,0)+data
  c=checksum(src+dst+struct.pack('>I3xB',len(u),17)+u) or 65535
  return dm+sm+b'\x86\xdd'+struct.pack('>IHBB',0x60000000,len(u),17,64)+src+dst+u[:6]+struct.pack('>H',c)+u[8:]
 def udp4(data=b'v4',sport=443,dport=49152):
  a=bytes([192,0,2,2]);b=bytes([192,0,2,1]);u=struct.pack('>4H',sport,dport,len(data)+8,0)+data
  h=struct.pack('>BBHHHBBH4s4s',0x45,0,len(u)+20,1,0,64,17,0,a,b)
  return mac+remote+b'\x08\0'+h[:10]+struct.pack('>H',checksum(h))+h[12:]+u
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(bytes(b));return f'?V{len(vectors)-1}'
 def add(name,code,rc,wire=b'',err=0,dis=-1,owner=0,legacy=0,resolve=0,meta=None,addresses=b'',data=b''):
  cases.append(dict(name=name,expected=[rc,len(wire),err,dis,owner,legacy,resolve]+(meta or [-1]*4),wire=wire.hex(),addresses=addresses.hex(),data=data[:256].hex()));steps.append(code)
 def inp(b):return f'rc=NetInput(1,{vec(b)},{len(b)})\nIf rc=#NET_IN_UDP : dis=NetServiceInput(1,0,rc) : EndIf'
 def receive(name,b=None,**kw):
  if b is None:b=udp6()
  sport,dport,n=struct.unpack_from('>3H',b,54)
  add(name,inp(b),2,dis=1,owner=1,meta=[6,sport,dport,n-8],addresses=b[22:54],data=b[62:62+n-8],**kw)
 receive('IPv6 UDP delivered with correct tuple')
 receive('empty datagram delivered',udp6(b''))
 receive('full minimum MTU datagram',udp6(bytes(1232)))
 for sp,dp,label in [(67,68,'DHCP'),(123,123,'NTP'),(53,5555,'DNS console')]:receive('IPv6 does not enter '+label+' owner',udp6(sport=sp,dport=dp))
 add('unowned IPv6 stays unconsumed','NetServiceSetUdp6Hook(0)\n'+inp(udp6()),2,dis=0,meta=[6,443,49152,3],addresses=peer+local,data=b'abc')
 add('IPv6 owner may decline','consume=0\n'+inp(udp6()),2,dis=0,owner=1,meta=[6,443,49152,3],addresses=peer+local,data=b'abc')
 b=bytearray(udp6());b[-1]^=1;add('checksum refusal before dispatch',inp(b),-3503,err=-3503)
 add('foreign local IPv6 refused',inp(udp6(dst=ipaddress.IPv6Address('fe80::9999').packed)),0)
 add('multicast source refused',inp(udp6(src=ipaddress.IPv6Address('ff02::1').packed)),0)
 add('unspecified source refused',inp(udp6(src=bytes(16))),0)
 add('foreign destination MAC refused',inp(udp6(dm=bytes.fromhex('020000000099'))),0)
 add('bound port filters unrelated packet','NetUdpBind(1,40000)\n'+inp(udp6()),0)
 add('persistent listener survives command binding','NetUdpBind(1,40000)\nNetUdpListen(1,49152,1)\n'+inp(udp6()),2,dis=1,owner=1,meta=[6,443,49152,3],addresses=peer+local,data=b'abc')
 add('legacy IPv4 remains isolated',inp(udp4()),2,dis=1,legacy=2,meta=[4,443,49152,2],data=b'v4')
 add('legacy IPv4 DHCP remains owned',inp(udp4(sport=67,dport=68)),2,dis=1,legacy=2,meta=[4,67,68,2],data=b'v4')
 p=vec(udp6())
 add('IPv4 clears IPv6 addresses',f'rc=NetInput(1,{p},65)\n'+inp(udp4()),2,dis=1,legacy=2,meta=[4,443,49152,2],data=b'v4')
 add('stale UDP result cannot pass hook contract',f'rc=NetInput(1,{p},65)\nmode=1\n'+inp(udp6()),-108,err=-108)
 def emit(name,data=b'abc',args=None,rc=None,err=0,resolve=1,setup=''):
  ptr=vec(data or b'\0');args=args or f'1,?Local,?Peer,443,49152,{ptr},{len(data)}'
  good=udp6(data,49152,443,local,peer,remote,mac)
  add(name,setup+f'\nrc=NetUdp6BuildFrom({args})',1 if rc is None else rc,wire=good if rc is None else b'',err=err,resolve=resolve)
 emit('UDP6 emission reuses route and neighbor seam')
 emit('empty UDP6 emission',b'')
 emit('minimum MTU UDP6 emission',bytes(1232))
 emit('pending neighbor does not build or wait',rc=0,resolve=1,setup='resolution=0')
 emit('neighbor failure propagates',rc=0,err=-888,resolve=1,setup='resolution=-888')
 emit('unassigned source refused',args='1,?Peer,?Peer,443,49152,0,0',rc=0,err=-881,resolve=0)
 emit('multicast destination refused',args='1,?Local,?Group,443,49152,0,0',rc=0,err=-100,resolve=0)
 emit('oversize datagram refused',args='1,?Local,?Peer,443,49152,?Local,1233',rc=0,err=-100,resolve=0)
 emit('payload aliases staging refused',args='1,?Local,?Peer,443,49152,NetOutBuf(),1',rc=0,err=-100,resolve=0)
 emit('address aliases staging refused',args='1,NetOutBuf(),?Peer,443,49152,0,0',rc=0,err=-100,resolve=0)
 emit('invalid port refused',args='1,?Local,?Peer,0,49152,0,0',rc=0,err=-100,resolve=0)
 emit('invalid interface refused',args='0,?Local,?Peer,443,49152,0,0',rc=0,err=-100,resolve=0)
 core=(root/'Anvil/Core/netconsole.pbi').read_text()
 def proc(name):
  m=re.search(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',core,re.M|re.S);assert m,name;return m[0]+'\n'
 dispatcher='Global *gNetUdpSvcHook,*gNetUdp6SvcHook\n'+''.join(proc(n) for n in ['NetServiceSetUdpHook','NetServiceSetUdp6Hook','NetServiceInput'])
 s='#HW_LINK_NONE=0\n#HW_LINK_WIRED=1\n#HW_LINK_FILE=5\n#DHCP_PORT_SERVER=67\n#DHCP_PORT_CLIENT=68\n#DHCPC_INIT=0\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/net.pbi"\n'+r'''
Global legacy.i,owner.i,resolves.i,resolution.i,consume.i,mode.i
Procedure.i millis()
 ProcedureReturn 0
EndProcedure
Procedure netcon_SendStaged(kind.i)
 legacy=legacy+1
EndProcedure
Procedure TcpInput()
 legacy=legacy+1
EndProcedure
Procedure.i DhcpClientState(kind.i)
 legacy=legacy+1 : ProcedureReturn 1
EndProcedure
Procedure DhcpClientInput(kind.i,p.i,n.i,t.i)
 legacy=legacy+1
EndProcedure
Procedure.i NtpServiceInput(kind.i)
 legacy=legacy+1 : ProcedureReturn 0
EndProcedure
Procedure.i NetConsoleOfferUdp(frame.i,kind.i)
 legacy=legacy+1 : ProcedureReturn 0
EndProcedure
Procedure.i LegacyOwner(kind.i)
 legacy=legacy+1 : ProcedureReturn 1
EndProcedure
Procedure.i UdpOwner(kind.i)
 owner=owner+1 : ProcedureReturn consume
EndProcedure
Procedure.i Assigned(kind.i,source.i)
 If kind<>1 : ProcedureReturn 0 : EndIf
 ProcedureReturn net_Same(source,?Local,16)
EndProcedure
Procedure.i Resolve(kind.i,source.i,destination.i,mac.i)
 Define i.i
 resolves=resolves+1
 If resolution=1
  For i=0 To 5 : PokeA(mac+i,PeekA(?RemoteMac+i)) : Next
 EndIf
 ProcedureReturn resolution
EndProcedure
Procedure.i Receive(kind.i,frame.i,n.i,out.i,capacity.i)
 If mode=1 : ProcedureReturn #NET_IN_UDP : EndIf
 ProcedureReturn NetUdp6Input(kind,frame,n)
EndProcedure
'''+dispatcher+r'''
Procedure Save(index.i,rc.i,dis.i)
 Define p.i,i.i,n.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,NetOutLen()) : PokeI(p+16,NetError()) : PokeI(p+24,dis)
 PokeI(p+32,owner) : PokeI(p+40,legacy) : PokeI(p+48,resolves)
 For i=0 To 3 : PokeI(p+56+i*8,-1) : Next
 If rc=#NET_IN_UDP
  PokeI(p+56,NetUdpRxFamily()) : PokeI(p+64,NetUdpRxPort())
  PokeI(p+72,NetUdpRxDstPort()) : PokeI(p+80,NetUdpRxLen())
  If NetUdpRxFamily()=6
   For i=0 To 15
    PokeA(p+1648+i,PeekA(NetUdpRxFrom6()+i)) : PokeA(p+1664+i,PeekA(NetUdpRxTo6()+i))
   Next
  EndIf
  n=NetUdpRxLen() : If n>256 : n=256 : EndIf
  If n>0
   For i=0 To n-1 : PokeA(p+1680+i,PeekA(NetUdpRxData()+i)) : Next
  EndIf
 EndIf
 n=NetOutLen()
 If n>0
  For i=0 To n-1 : PokeA(p+128+i,PeekA(NetOutBuf()+i)) : Next
 EndIf
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,dis.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$55444936)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):
  s+='NetInit() : NetSetMac(1,?Mac) : NetSetIPv4(1,$C0000201,$FFFFFF00,0)\nNetSetTcp6Hooks(@Assigned,@Resolve) : NetSetIPv6InputHook(@Receive)\nNetServiceSetUdpHook(@LegacyOwner) : NetServiceSetUdp6Hook(@UdpOwner)\nlegacy=0 : owner=0 : resolves=0 : consume=1 : resolution=1 : mode=0 : dis=-1\n'+code+f'\nSave({k},rc,dis)\n'
 s+=f'PokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Local',local),('Peer',peer),('Mac',mac),('RemoteMac',remote),('Group',ipaddress.IPv6Address('ff02::1').packed)]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
  s+=name+':\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
