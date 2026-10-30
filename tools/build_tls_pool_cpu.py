"""Physical bounded TLS pool lifecycle proof; deterministic transport/handshake doubles."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile TLS pool lifecycle qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Core/tls_client.pbi','Anvil/Hal/abi.pbi','Anvil/Crypto/tls13_hs.pbi','Anvil/Crypto/tls13_record.pbi','Anvil/Crypto/x509.pbi','Anvil/Crypto/tls13_context.pbi']
names+=['Anvil/Core/tcp_dial.pbi','Anvil/Network/tcp_dial.pbi','Anvil/Network/ipv6_address.pbi']
owner=(r/names[0]).read_text(encoding='utf8')
# Compile the actual TLS service owner. Display-only diagnostics are outside
# this probe; crypto/TCP seams are deterministic doubles, not TLS wire tests.
owner=owner[:owner.index('; `tls status`')]
needed=set(re.findall(r'#[A-Z][A-Z_0-9]*',owner));defined=set(re.findall(r'(?m)^#([A-Z][A-Z_0-9]*)\s*=',owner))
needed.update(['#SVC_EAGAIN','#TLS13_ST_CONNECTED','#TLS13_ST_WAIT_SH','#SVC_TCP_OPEN'])
constants=[]
for name in names[1:3]:
 for line in (r/name).read_text(encoding='utf8').splitlines():
  m=re.match(r'^#([A-Z][A-Z_0-9]*)\s*=',line)
  if m and '#'+m[1] in needed and m[1] not in defined:constants.append(line);defined.add(m[1])
s='\n'.join(constants)+'\n#TLS13_MAX_OFFERED=8\n#TLS13_MAX_CERTS=6\n#X_EEPKEY_SIZE=520\n'+r'''Global Dim secTlsWKey.a[16]          ; write traffic key            (secret)
Global Dim secTlsWIv.a[12]           ; write traffic iv             (secret)
Global TlsWSeqLo.i                   ; write sequence number, low 32
Global TlsWSeqHi.i                   ; write sequence number, high 32
Global TlsWKeyed.i                   ; 0 until a write key is installed
Global Dim secTlsRKey.a[16]          ; read traffic key             (secret)
Global Dim secTlsRIv.a[12]           ; read traffic iv              (secret)
Global TlsRSeqLo.i                   ; read sequence number, low 32
Global TlsRSeqHi.i                   ; read sequence number, high 32
Global TlsRKeyed.i                   ; 0 until a read key is installed
Global Dim TlsNonce.a[12]            ; the per-record AEAD nonce   (public)
Global Dim TlsAad.a[5]               ; the 5-byte additional data  (public)
Global Dim TlsTag.a[16]              ; tag scratch                 (public)
Global TlsRecInnerType.i             ; recovered content type of the last record
Global Tls13RecErr.i                 ; named reason for the last refusal
Global TlsCipherInstalled.i          ; 0 none, 1 write key loaded, 2 read key
Global Tls13State.i
Global Tls13Err.i                    ; a #TLS13_REFUSE_* name
Global Tls13Alert.i                  ; the alert that refusal would send
Global Tls13X509Err.i                ; the x509 verdict, on a chain refusal
Global Tls13PeerAlert.i              ; the description the peer sent
Global Tls13TicketsDiscarded.i
Global Tls13KeyUpdatePending.i
Global Tls13AppAddr.i
Global Tls13AppLen.i
Global TlsGroup.i                    ; the group offered in key_share
Global TlsUnixTime.i
Global TlsNameAddr.i
Global TlsNameLen.i
Global Dim secTlsEarly.a[32]
Global Dim secTlsDerived.a[32]
Global Dim secTlsHsSec.a[32]
Global Dim secTlsMaster.a[32]
Global Dim secTlsCHs.a[32]           ; client_handshake_traffic_secret
Global Dim secTlsSHs.a[32]           ; server_handshake_traffic_secret
Global Dim secTlsCAp.a[32]           ; client_application_traffic_secret_N
Global Dim secTlsSAp.a[32]           ; server_application_traffic_secret_N
Global Dim secTlsEcdhe.a[32]         ; the (EC)DHE shared secret
Global Dim secTlsPriv.a[32]          ; our ephemeral private key
Global Dim secTlsFinKey.a[32]        ; a Finished key, transiently
Global Dim secTlsKeyBuf.a[16]        ; a traffic key, transiently
Global Dim secTlsIvBuf.a[12]         ; a traffic iv, transiently
Global Dim secTlsZeros.a[32]         ; 32 zero bytes: the absent PSK
Global Dim TlsClientRandom.a[32]
Global Dim TlsSessionId.a[32]
Global TlsSessionIdLen.i
Global Dim TlsKeyShare.a[65]         ; our public share (32 or 65 bytes)
Global TlsKeyShareLen.i
Global Dim TlsPeerShare.a[65]        ; the server's share, as received
Global TlsPeerShareLen.i
Global Dim TlsOfferedExt.i[#TLS13_MAX_OFFERED]
Global TlsOfferedCount.i
Global Dim TlsTrSnap.a[104]          ; the running transcript hash state
Global Dim TlsThBuf.a[32]            ; a computed transcript hash
Global Dim TlsThCert.a[32]           ; Transcript-Hash(CH..Certificate)
Global Dim TlsThSf.a[32]             ; Transcript-Hash(CH..server Finished)
Global Dim TlsEmptyHash.a[32]        ; SHA-256("") - the "derived" context
Global TlsHsAddr.i
Global TlsHsSize.i
Global TlsHsLen.i
Global TlsRecvAddr.i
Global TlsRecvSize.i
Global TlsRecvLen.i
Global Dim TlsCertAddr.i[#TLS13_MAX_CERTS]
Global Dim TlsCertLen.i[#TLS13_MAX_CERTS]
Global TlsCertCount.i
Global Dim TlsScratch.a[72]          ; basepoint / P-256 point / small message work
Global Dim TlsMsgHash.a[64]          ; the CertificateVerify message hash
Global Dim TlsVerifyData.a[32]
Global Dim TlsHrrRandom.a[32]        ; the RFC 8446 4.1.3 HRR sentinel
Global Dim TlsP256Order.a[32]        ; the P-256 group order n
Global Dim TlsLbl.a[80]              ; the HKDF label texts, back to back
Global Dim TlsCvCtx.a[98]            ; 64 spaces + the context string + NUL
Global TlsLabelsReady.i
Global TlsKdfFault.i                 ; 1 once an hkdf call came back short
Global X509EePkeyType.i        ; 1=RSA, 2=EC, 0=none
Global X509EeNAddr.i
Global X509EeNLen.i
Global X509EeEAddr.i
Global X509EeELen.i
Global X509EeCurve.i
Global X509EeQAddr.i
Global X509EeQLen.i
Global Dim xEePkey.a[#X_EEPKEY_SIZE]   ; permanent EE key bytes

Global gSvcDetail.i
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
 If h>=100 And h<104 : PokeI($E1C00800+(h-100)*8,PeekA(p) & 255) : EndIf
 ProcedureReturn n
EndProcedure
Procedure.i PayNetTcpState(h.i)
 ProcedureReturn #SVC_TCP_OPEN
EndProcedure
Procedure.i PayNetTcpRecv(h.i,p.i,n.i)
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
 PokeI($E1C00900+(secTlsWKey[0]-31)*8,PeekA(b) & 255)
 PokeA(p,secTlsWKey[0]) : ProcedureReturn 1
EndProcedure
Procedure.i Tls13BuildAlert(p.i,n.i,level.i,description.i)
 ProcedureReturn 1
EndProcedure
Procedure.i PayNetDnsResolve(p.i)
 ProcedureReturn #SVC_EAGAIN
EndProcedure
Procedure.i PayNetDnsResolve6(p.i,out.i)
 ProcedureReturn #SVC_EAGAIN
EndProcedure
Procedure.i PayNetTcpOpen6(ip.i,port.i)
 ProcedureReturn 2
EndProcedure
Procedure.i PayNetTcpOpen(ip.i,port.i)
 ProcedureReturn 1
EndProcedure

Procedure TlsCopy(dst.i,src.i,n.i)
 Define i.i
 For i=0 To n-1 : PokeA(dst+i,PeekA(src+i)) : Next
EndProcedure
Procedure Tls13RecInvalidateCipher()
 TlsCipherInstalled=0
EndProcedure
Procedure GcmWipe()
EndProcedure
Procedure AesWipe()
EndProcedure
'''+owner+r'''
Global Dim handles.i[4]
Global Dim result.a[8]
Procedure.i Main(services.i)
 Define i.i,h.i,rc.i,p.i,first.i,old.i,ok.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$54504C31)
 For i=0 To 3
  h=TlsClientOpen("example.com",443) : handles[i]=h
  PokeI($E1C00100+i*64,h)
  tlsc_state=#TLSC_OPEN : tlsc_tcp=100+i : Tls13State=#TLS13_ST_CONNECTED
  secTlsWKey[0]=31+i : TlsWSeqLo=500+i : TlsTrSnap[0]=71+i
  tlsc_ring[tlsc_slot*#TLSC_RING]=91+i : tlsc_ringHead=1 : tlsc_ringTail=0
 Next
 PokeI($E1C00008,TlsClientOpen("example.com",443))
 For i=0 To 3
  p=$E1C00100+i*64 : h=handles[i]
  PokeI(p+8,TlsClientState(h)) : PokeI(p+16,TlsWSeqLo) : PokeI(p+24,TlsTrSnap[0])
  result[0]=111+i
  PokeI(p+32,TlsClientSend(h,@result[0],1))
  PokeI(p+56,tlsc_appPending[tlsc_slot])
  result[0]=0
  PokeI(p+40,TlsClientRecv(h,@result[0],1)) : PokeI(p+48,result[0])
 Next
 old=handles[1] : rc=TlsClientClose(old)
 PokeI($E1C00010,TlsClientState(old))
 h=TlsClientOpen("example.com",443) : PokeI($E1C00018,h)
 PokeI($E1C00020,TlsClientState(old))
 TlsClientPayloadReturned()
 ok=1
 For i=0 To #TLSC_CONNECTIONS-1 : If tlsc_handles[i]<>0 : ok=0 : EndIf : Next
 PokeI($E1C00028,ok)
 ok=1
 For i=0 To #TLSC_CONNECTIONS*#TLS13_CONTEXT_SIZE-1 : If tlsc_context[i]<>0 : ok=0 : EndIf : Next
 PokeI($E1C00030,ok)
 ok=1
 For i=0 To #TLSC_CONNECTIONS*#TLSC_APP_CHUNK-1 : If tlsc_plain[i]<>0 : ok=0 : EndIf : Next
 For i=0 To #TLSC_CONNECTIONS-1 : If tlsc_appPending[i]<>0 : ok=0 : EndIf : Next
 PokeI($E1C00038,ok)
 ProcedureReturn 0
EndProcedure
'''
cases=list(range(4))
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
