"""Physical TLS close and transport-failure proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile TLS closure qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Core/tls_client.pbi','Anvil/Hal/abi.pbi','Anvil/Crypto/tls13_hs.pbi']
owner=(r/names[0]).read_text(encoding='utf8')
# Compile the actual TLS service owner. Display-only diagnostics are outside
# this probe; crypto/TCP seams are deterministic doubles, not TLS wire tests.
owner=owner[:owner.index('; `tls status`')]
needed=set(re.findall(r'#[A-Z][A-Z_0-9]*',owner));defined=set(re.findall(r'(?m)^#([A-Z][A-Z_0-9]*)\s*=',owner))
needed.update(['#TLS13_ST_CONNECTED','#TLS13_ST_WAIT_SH'])
constants=[]
for name in names[1:]:
 for line in (r/name).read_text(encoding='utf8').splitlines():
  m=re.match(r'^#([A-Z][A-Z_0-9]*)\s*=',line)
  if m and '#'+m[1] in needed and m[1] not in defined:constants.append(line);defined.add(m[1])
s='\n'.join(constants)+r'''
Global Tls13Err.i,Tls13X509Err.i,Tls13PeerAlert.i,Tls13AppLen.i,Tls13AppAddr.i,Tls13State.i,gSvcDetail.i
Global mode.i,reads.i,feeds.i,closes.i,clockValue.i
Global Dim plain.a[16]
Procedure.i millis()
 ProcedureReturn clockValue
EndProcedure
Procedure str_print_at(p.i)
EndProcedure
Procedure.i PayNetTcpClose(h.i)
 closes=closes+1 : ProcedureReturn 0
EndProcedure
Procedure.i PayNetTcpSend(h.i,p.i,n.i)
 ProcedureReturn n
EndProcedure
Procedure.i PayNetTcpState(h.i)
 If mode=4 : ProcedureReturn #SVC_EIO : EndIf
 ProcedureReturn #SVC_TCP_PEER_CLOSED
EndProcedure
Procedure.i PayNetTcpRecv(h.i,p.i,n.i)
 reads=reads+1
 If mode=0 Or (mode=3 And reads>1) : ProcedureReturn #SVC_EIO : EndIf
 If mode=2
  If reads=1 : ProcedureReturn 4096 : EndIf
  If reads=2 : ProcedureReturn 8 : EndIf
 EndIf
 If mode=3 And reads=1 : ProcedureReturn 8 : EndIf
 If mode=6 And reads=1 : ProcedureReturn 3 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Tls13FeedBytesLimited(p.i,n.i,records.i)
 feeds=feeds+1
 If mode=3 Or (mode=2 And reads=2) : Tls13State=#TLS13_ST_CLOSED : EndIf
 If mode=2 And reads=1
  plain[0]=65 : plain[1]=66 : plain[2]=67
  Tls13AppLen=3 : Tls13AppAddr=@plain[0]
 EndIf
 ProcedureReturn n
EndProcedure
Procedure Tls13SetHsBuffer(p.i,n.i)
EndProcedure
Procedure Tls13SetRecvBuffer(p.i,n.i)
EndProcedure
Procedure Tls13SetGroup(group.i)
EndProcedure
Procedure.i WallClockNow()
 ProcedureReturn 0
EndProcedure
Procedure.i WallClockTrusted()
 ProcedureReturn 1
EndProcedure
Procedure.i TlsRootsEnsure()
 ProcedureReturn 1
EndProcedure
Procedure.i TlsRootsErrorText(code.i)
 ProcedureReturn 0
EndProcedure
Procedure.i DrbgAutoSeed()
 ProcedureReturn 0
EndProcedure
Procedure DrbgAutoReseed()
EndProcedure
Procedure.i Tls13Init(p.i,n.i,now.i)
 ProcedureReturn 1
EndProcedure
Procedure.i Tls13NewKeyShare()
 ProcedureReturn 1
EndProcedure
Procedure.i Tls13BuildClientHello(p.i,n.i)
 ProcedureReturn 1
EndProcedure
Procedure.i Tls13BuildClientFinished(p.i,n.i)
 ProcedureReturn 1
EndProcedure
Procedure.i Tls13Connected()
 ProcedureReturn Bool(Tls13State=#TLS13_ST_CONNECTED)
EndProcedure
Procedure.i Tls13BuildAppRecord(p.i,n.i,b.i,l.i)
 ProcedureReturn 1
EndProcedure
Procedure.i Tls13BuildAlert(p.i,n.i,level.i,description.i)
 ProcedureReturn 1
EndProcedure
Procedure.i PayNetDnsResolve(p.i)
 ProcedureReturn #SVC_EAGAIN
EndProcedure
Procedure.i PayNetTcpOpen(ip.i,port.i)
 ProcedureReturn 1
EndProcedure
'''+owner+r'''
Procedure Record(which.i)
 Define p.i,first.i,second.i,count.i,after.i,i.i
 mode=which : reads=0 : feeds=0 : closes=0 : clockValue=0
 tlsc_state=#TLSC_OPEN : tlsc_tcp=1 : tlsc_fail=0 : tlsc_why=0
 tlsc_txLen=0 : tlsc_txOff=0 : tlsc_inLen=0 : tlsc_inOff=0
 tlsc_ringHead=0 : tlsc_ringTail=0 : Tls13State=#TLS13_ST_CONNECTED : Tls13AppLen=0
 If mode=5 : tlsc_state=#TLSC_HS : Tls13State=#TLS13_ST_WAIT_SH : EndIf
 If mode=7 : tlsc_inLen=8 : EndIf
 first=TlsClientState(1)
 second=TlsClientState(1)
 count=TlsClientRecv(1,@plain[0],16)
 after=TlsClientState(1)
 p=$E1C00100+which*128
 For i=0 To 127 : PokeA(p+i,0) : Next
 PokeI(p,first) : PokeI(p+8,second) : PokeI(p+16,count) : PokeI(p+24,after)
 PokeI(p+32,reads) : PokeI(p+40,feeds) : PokeI(p+48,closes)
 For i=0 To 2 : PokeA(p+64+i,plain[i]) : Next
 tlsc_state=#TLSC_IDLE
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$54434C31) : PokeI($E1C00008,8)
 For i=0 To 7 : Record(i) : Next
 ProcedureReturn 0
EndProcedure
'''
cases=list(range(8))
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
