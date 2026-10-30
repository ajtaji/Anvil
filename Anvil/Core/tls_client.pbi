; ======================================================================
;  tls_client.pbi - HTTPS FOR EVERYTHING ON THE BOARD. Bounded TLS 1.3 client
;  connections behind handles: the name is resolved, TCP opened, the
;  handshake run and the certificate chain verified against the root
;  store (Anvil/Core/tls_roots.pbi), and then application bytes go in and
;  out in the clear on this side, encrypted on the wire.
;
;  It serves the service table's TLS slots (80..83 and 87, Anvil/Hal/
;  abi.pbi) for payloads and the monitor's own `https` command, through
;  the SAME kernel service and shared protocol implementation.
;
;  THE RULE OF Anvil/Core/payload_net.pbi HOLDS: NOTHING WAITS. Open
;  returns a handle at once; DNS, TCP and the handshake advance from
;  TlsClientAdvance, which PayNetService (the payload's once-a-frame
;  slot) and every TLS slot call. The one stretch of pure computation is
;  the handshake's own arithmetic - an X25519 share at open and the chain
;  and CertificateVerify signatures when the server's flight lands - which
;  uses an optional cooperative driver. Without that driver it runs in the
;  call that has the bytes and is not bounded to one display frame.
;
;  FOUR SERIALIZED CONNECTIONS. Large buffers belong to fixed pool slots.
;  Explicit snapshots preserve TLS keys, sequences, transcript and certificate
;  key between calls. A cooperative worker serializes in-flight arithmetic
;  ownership while retaining the parser call stack across service calls.
;  Handles are monotonically allocated and stale handles are refused. The
;  service advances one allocated slot per call in round-robin order.
;
;  WHAT IS VERIFIED, ALWAYS: the chain to a root in the store, every
;  signature in it, the server's CertificateVerify, its Finished, the
;  validity dates against the wall clock, and the host name against the
;  certificate. There is no switch that turns any of it off. A clock that
;  is not trusted (no SNTP, not set by hand) refuses the open, because a
;  date check against a guessed time is a date check that lies.
;
;  States (TlsClientState / SvcTlsState):
;    #SVC_TLS_RESOLVING   the name is being looked up
;    #SVC_TLS_CONNECTING  TCP is being opened
;    #SVC_TLS_HANDSHAKE   TLS handshake in progress
;    #SVC_TLS_OPEN        verified and established; send and receive
;    #SVC_TLS_PEER_CLOSED authenticated close_notify was received;
;                         prior plaintext is still readable
;    negative             failed - the code, and SvcErrDetail's fragment
; ======================================================================

EnableExplicit
XIncludeFile "Anvil/Core/tcp_dial.pbi"

#SVC_TLS_RESOLVING   = 1
#SVC_TLS_CONNECTING  = 2
#SVC_TLS_HANDSHAKE   = 3
#SVC_TLS_OPEN        = 4
#SVC_TLS_PEER_CLOSED = 5

#TLSC_IDLE      = 0
#TLSC_RESOLVING = 1
#TLSC_TCP       = 2
#TLSC_HS        = 3
#TLSC_OPEN      = 4
#TLSC_CLOSED    = 5
#TLSC_FAILED    = 6
#TLSC_PREPARE   = 7

#TLSC_NAME_MAX  = 256
#TLSC_HS_BUF    = 24576     ; the largest handshake message: a certificate chain
#TLSC_RECV_BUF  = 16896     ; 5 + 16640, RFC 8446's largest record, and slack
#TLSC_TX_BUF    = 20480     ; ClientHello + Finished, or one app record
#TLSC_APP_CHUNK = 16384     ; plaintext per application record
#TLSC_IN_BUF    = 4096      ; TCP bytes read per pass
#TLSC_RING      = 65536     ; plaintext received, not yet read; a power of two
#TLSC_HS_MS     = 20000     ; DNS + TCP + handshake, all of it

XIncludeFile "Anvil/Crypto/tls13_context.pbi"
#TLSC_CONNECTIONS=4
Global Dim tlsc_dial.TcpDial[#TLSC_CONNECTIONS]
Global tlsc_state.i
Global tlsc_fail.i                 ; the latched #SVC_* code
Global tlsc_why.i                  ; and its fragment
Global tlsc_tcp.i                  ; the payload_net TCP handle
Global tlsc_port.i
Global tlsc_ip.i
Global tlsc_t0.i
Global tlsc_txLen.i
Global tlsc_txOff.i
Global tlsc_inLen.i
Global tlsc_inOff.i
Global tlsc_ringHead.i             ; next byte written
Global tlsc_ringTail.i             ; next byte read
Global tlsc_seeded.i
Global tlsc_tlsErr.i               ; Tls13Err / Tls13X509Err / Tls13PeerAlert at failure
Global tlsc_x509Err.i
Global tlsc_peerAlert.i
Global tlsc_nameLen.i
Global Dim tlsc_name.a[#TLSC_CONNECTIONS*#TLSC_NAME_MAX]
Global Dim tlsc_hs.a[#TLSC_CONNECTIONS*#TLSC_HS_BUF]
Global Dim tlsc_recv.a[#TLSC_CONNECTIONS*#TLSC_RECV_BUF]
Global Dim tlsc_tx.a[#TLSC_CONNECTIONS*#TLSC_TX_BUF]
; Accepted application bytes belong to the connection until protection ends.
Global Dim tlsc_plain.a[#TLSC_CONNECTIONS*#TLSC_APP_CHUNK]
Global Dim tlsc_appPending.i[#TLSC_CONNECTIONS]
Global Dim tlsc_in.a[#TLSC_CONNECTIONS*#TLSC_IN_BUF]
Global Dim tlsc_ring.a[#TLSC_CONNECTIONS*#TLSC_RING]

Global tlsc_slot.i
Global tlsc_cursor.i
Global tlsc_nextHandle.i
Global Dim tlsc_handles.i[#TLSC_CONNECTIONS]
Global Dim tlsc_saved.i[#TLSC_CONNECTIONS*17]
Global Dim tlsc_context.a[#TLSC_CONNECTIONS*#TLS13_CONTEXT_SIZE]

; Only one core enters the ABI. Switching happens between complete crypto
; calls, never in the middle of an AES/HMAC/X.509 operation.
Procedure tlsc_Select(slot.i)
 Define base.i,rc.i
 If slot=tlsc_slot : ProcedureReturn : EndIf
 base=tlsc_slot*17
 tlsc_saved[base+0]=tlsc_state
 tlsc_saved[base+1]=tlsc_fail
 tlsc_saved[base+2]=tlsc_why
 tlsc_saved[base+3]=tlsc_tcp
 tlsc_saved[base+4]=tlsc_port
 tlsc_saved[base+5]=tlsc_ip
 tlsc_saved[base+6]=tlsc_t0
 tlsc_saved[base+7]=tlsc_txLen
 tlsc_saved[base+8]=tlsc_txOff
 tlsc_saved[base+9]=tlsc_inLen
 tlsc_saved[base+10]=tlsc_inOff
 tlsc_saved[base+11]=tlsc_ringHead
 tlsc_saved[base+12]=tlsc_ringTail
 tlsc_saved[base+13]=tlsc_tlsErr
 tlsc_saved[base+14]=tlsc_x509Err
 tlsc_saved[base+15]=tlsc_peerAlert
 tlsc_saved[base+16]=tlsc_nameLen
 rc=Tls13ContextSave(@tlsc_context[tlsc_slot*#TLS13_CONTEXT_SIZE],#TLS13_CONTEXT_SIZE)
 tlsc_slot=slot
 base=slot*17
 tlsc_state=tlsc_saved[base+0]
 tlsc_fail=tlsc_saved[base+1]
 tlsc_why=tlsc_saved[base+2]
 tlsc_tcp=tlsc_saved[base+3]
 tlsc_port=tlsc_saved[base+4]
 tlsc_ip=tlsc_saved[base+5]
 tlsc_t0=tlsc_saved[base+6]
 tlsc_txLen=tlsc_saved[base+7]
 tlsc_txOff=tlsc_saved[base+8]
 tlsc_inLen=tlsc_saved[base+9]
 tlsc_inOff=tlsc_saved[base+10]
 tlsc_ringHead=tlsc_saved[base+11]
 tlsc_ringTail=tlsc_saved[base+12]
 tlsc_tlsErr=tlsc_saved[base+13]
 tlsc_x509Err=tlsc_saved[base+14]
 tlsc_peerAlert=tlsc_saved[base+15]
 tlsc_nameLen=tlsc_saved[base+16]
 rc=Tls13ContextRestore(@tlsc_context[slot*#TLS13_CONTEXT_SIZE],#TLS13_CONTEXT_SIZE)
EndProcedure

Procedure tlsc_Refuse(code.i, *why)
  If tlsc_state <> #TLSC_FAILED
    tlsc_fail = code
    tlsc_why = *why
    tlsc_tlsErr = Tls13Err
    tlsc_x509Err = Tls13X509Err
    tlsc_peerAlert = Tls13PeerAlert
  EndIf
  tlsc_state = #TLSC_FAILED
  TcpDialClose(@tlsc_dial[tlsc_slot])
  If tlsc_tcp > 0
    PayNetTcpClose(tlsc_tcp)
    tlsc_tcp = 0
  EndIf
EndProcedure

; Prints a sentence held by pointer; nothing for a null one.
Procedure tlsc_Say(p.i)
  If p <> 0
    str_print_at(p)
  EndIf
EndProcedure

Procedure.i tlsc_RingUsed()
  ProcedureReturn (tlsc_ringHead - tlsc_ringTail) & (#TLSC_RING - 1)
EndProcedure

Procedure.i tlsc_RingFree()
  ProcedureReturn #TLSC_RING - 1 - tlsc_RingUsed()
EndProcedure

; One send attempt per flush; partial progress stays queued for the next pass.
; 0, or -1 when TCP refused.
Procedure.i tlsc_Flush()
  Define k.i
  If tlsc_txOff < tlsc_txLen
    k = PayNetTcpSend(tlsc_tcp, @tlsc_tx[tlsc_slot*#TLSC_TX_BUF+tlsc_txOff], tlsc_txLen - tlsc_txOff)
    If k < 0
      tlsc_Refuse(k, "the TCP connection under TLS refused a send")
      ProcedureReturn -1
    EndIf
    If k > tlsc_txLen - tlsc_txOff
      tlsc_Refuse(#SVC_EIO, "TCP reported more sent bytes than TLS offered")
      ProcedureReturn -1
    EndIf
    tlsc_txOff = tlsc_txOff + k
  EndIf
  If tlsc_txOff >= tlsc_txLen
    tlsc_txOff = 0
    tlsc_txLen = 0
  EndIf
  ProcedureReturn 0
EndProcedure

; Appends a record of n bytes already built at tlsc_tx[tlsc_slot*#TLSC_TX_BUF+tlsc_txLen].
Procedure tlsc_Queued(n.i)
  tlsc_txLen = tlsc_txLen + n
EndProcedure

; Feeds at most one TLS record per pass when the plaintext ring can take a
; whole record. 0, or -1 when TLS refused.
Procedure.i tlsc_Feed()
  Define fed.i
  Define i.i
  Define n.i
  If tlsc_inOff < tlsc_inLen And tlsc_RingFree() >= #TLSC_APP_CHUNK + 256
    Tls13AppLen = 0
    fed = Tls13FeedBytesLimited(@tlsc_in[tlsc_slot*#TLSC_IN_BUF+tlsc_inOff], tlsc_inLen - tlsc_inOff, 1)
    If fed < 0
      tlsc_Refuse(#SVC_EIO, "the server's TLS was refused - certificate, signature, Finished or record (tls status for the codes)")
      ProcedureReturn -1
    EndIf
    tlsc_inOff = tlsc_inOff + fed
    n = Tls13AppLen
    If n > 0
      For i = 0 To n - 1
        tlsc_ring[tlsc_slot*#TLSC_RING+tlsc_ringHead] = PeekA(Tls13AppAddr + i)
        tlsc_ringHead = (tlsc_ringHead + 1) & (#TLSC_RING - 1)
      Next
      Tls13AppLen = 0
    EndIf
  EndIf
  If tlsc_inOff >= tlsc_inLen
    tlsc_inOff = 0
    tlsc_inLen = 0
  EndIf
  ProcedureReturn 0
EndProcedure

; The handshake begins once TCP is open: init, key share, ClientHello.
Procedure tlsc_Begin()
  Define n.i
  Tls13SetHsBuffer(@tlsc_hs[tlsc_slot*#TLSC_HS_BUF+0], #TLSC_HS_BUF)
  Tls13SetRecvBuffer(@tlsc_recv[tlsc_slot*#TLSC_RECV_BUF+0], #TLSC_RECV_BUF)
  Tls13SetGroup(#TLS_GROUP_X25519)
  If Tls13Init(@tlsc_name[tlsc_slot*#TLSC_NAME_MAX+0], tlsc_nameLen, WallClockNow()) = 0
    tlsc_Refuse(#SVC_ESTATE, "TLS would not start (no trusted time, no root store, or a key-schedule fault)")
    ProcedureReturn
  EndIf
  If Tls13NewKeyShare() = 0
    tlsc_Refuse(#SVC_EIO, "TLS could not make its key share (the random generator refused)")
    ProcedureReturn
  EndIf
  n = Tls13BuildClientHello(@tlsc_tx[tlsc_slot*#TLSC_TX_BUF+tlsc_txLen], #TLSC_TX_BUF - tlsc_txLen)
  If n <= 0
    tlsc_Refuse(#SVC_EIO, "TLS could not build its ClientHello")
    ProcedureReturn
  EndIf
  tlsc_Queued(n)
  tlsc_state = #TLSC_HS
EndProcedure

; ----------------------------------------------------------------------
;  TlsClientAdvance - move the connection on without waiting for I/O.
;  Signature/key-share arithmetic is synchronous; not a frame-time guarantee.
; ----------------------------------------------------------------------
Procedure tlsc_AdvanceWork()
  Define i.i
  Define r.i
  Define st.i
  Define n.i
  Define tcpEmpty.i

  If tlsc_state = #TLSC_IDLE Or tlsc_state = #TLSC_FAILED Or tlsc_state = #TLSC_CLOSED
    ProcedureReturn
  EndIf

  If tlsc_state = #TLSC_PREPARE Or tlsc_state = #TLSC_RESOLVING Or tlsc_state = #TLSC_TCP Or tlsc_state = #TLSC_HS
    If ((millis() - tlsc_t0) & $FFFFFFFF) > #TLSC_HS_MS
      tlsc_Refuse(#SVC_ETIMEOUT, "the HTTPS connection was not established within 20 seconds")
      ProcedureReturn
    EndIf
  EndIf

  If tlsc_state=#TLSC_PREPARE
  r = TlsRootsEnsure()
  If r <= 0
    tlsc_why = TlsRootsErrorText(r)
    tlsc_Refuse(#SVC_ESTATE,tlsc_why) : ProcedureReturn
  EndIf
  If tlsc_seeded = 0
    If DrbgAutoSeed() < 0
      tlsc_why = "the hardware random generator would not seed TLS's generator"
      tlsc_Refuse(#SVC_EIO,tlsc_why) : ProcedureReturn
    EndIf
    tlsc_seeded = 1
  Else
    DrbgAutoReseed()
  EndIf
    r=NetDialStart(@tlsc_dial[tlsc_slot],@tlsc_name[tlsc_slot*#TLSC_NAME_MAX],tlsc_port)
    If r<0 : tlsc_Refuse(r,"the connection selector could not start") : ProcedureReturn : EndIf
    tlsc_state=#TLSC_RESOLVING
  EndIf

  If tlsc_state = #TLSC_RESOLVING
    r=TcpDialPoll(@tlsc_dial[tlsc_slot])
    If r=0 : ProcedureReturn : EndIf
    If r<0 : tlsc_Refuse(r,"the server could not be reached over either address family") : ProcedureReturn : EndIf
    If r<>1 : tlsc_Refuse(#SVC_EIO,"the server closed TCP before TLS began") : ProcedureReturn : EndIf
    tlsc_ip=0
    If tlsc_dial[tlsc_slot]\family=4 : tlsc_ip=tlsc_dial[tlsc_slot]\address : EndIf
    tlsc_tcp=TcpDialTake(@tlsc_dial[tlsc_slot])
    tlsc_state = #TLSC_TCP
  EndIf

  If tlsc_state = #TLSC_TCP
    st = PayNetTcpState(tlsc_tcp)
    If st < 0
      tlsc_Refuse(st, "TCP to the server failed")
      ProcedureReturn
    EndIf
    If st = #SVC_TCP_CONNECTING
      ProcedureReturn
    EndIf
    If st <> #SVC_TCP_OPEN
      tlsc_Refuse(#SVC_EIO, "the server closed TCP before TLS began")
      ProcedureReturn
    EndIf
    tlsc_Begin()
    If tlsc_state = #TLSC_FAILED
      ProcedureReturn
    EndIf
  EndIf

  ; Only the progress worker protects accepted application data. Pending stays
  ; nonzero across yields, so another Send cannot overwrite its plaintext.
  If tlsc_state=#TLSC_OPEN And tlsc_appPending[tlsc_slot]>0 And tlsc_txLen=0
    n=Tls13BuildAppRecord(@tlsc_tx[tlsc_slot*#TLSC_TX_BUF],#TLSC_TX_BUF,@tlsc_plain[tlsc_slot*#TLSC_APP_CHUNK],tlsc_appPending[tlsc_slot])
    For i=0 To tlsc_appPending[tlsc_slot]-1 : tlsc_plain[tlsc_slot*#TLSC_APP_CHUNK+i]=0 : Next
    tlsc_appPending[tlsc_slot]=0
    If n<=0 : tlsc_Refuse(#SVC_EIO,"TLS could not protect the queued bytes") : ProcedureReturn : EndIf
    tlsc_txLen=n : tlsc_txOff=0
    tlsc_Flush()
    ProcedureReturn
  EndIf

  ; Send what is queued, then read and feed.
  If tlsc_Flush() < 0
    ProcedureReturn
  EndIf
  If tlsc_inLen = 0
    n = PayNetTcpRecv(tlsc_tcp, @tlsc_in[tlsc_slot*#TLSC_IN_BUF+0], #TLSC_IN_BUF)
    If n < 0
      ; A reset/error is never authenticated end-of-stream, even after data.
      tlsc_Refuse(n, "the TCP connection under TLS failed")
      ProcedureReturn
    EndIf
    tcpEmpty = Bool(n = 0)
    tlsc_inLen = n
    tlsc_inOff = 0
  EndIf
  If tlsc_inLen > 0
    If tlsc_Feed() < 0
      ProcedureReturn
    EndIf
  EndIf

  If Tls13State = #TLS13_ST_FAILED
    tlsc_Refuse(#SVC_EIO, "the server's TLS was refused - certificate, signature, Finished or record (tls status for the codes)")
    ProcedureReturn
  EndIf
  If tlsc_state = #TLSC_HS
    If Tls13State = #TLS13_ST_SEND_FINISHED
      n = Tls13BuildClientFinished(@tlsc_tx[tlsc_slot*#TLSC_TX_BUF+tlsc_txLen], #TLSC_TX_BUF - tlsc_txLen)
      If n <= 0
        tlsc_Refuse(#SVC_EIO, "TLS could not build its Finished")
        ProcedureReturn
      EndIf
      tlsc_Queued(n)
      tlsc_Flush()
    EndIf
    If Tls13Connected() = 1
      tlsc_state = #TLSC_OPEN
    EndIf
  EndIf
  If Tls13State = #TLS13_ST_CLOSED And tlsc_state = #TLSC_OPEN
    tlsc_state = #TLSC_CLOSED
  EndIf
  If tlsc_state = #TLSC_OPEN Or tlsc_state = #TLSC_HS
    st = PayNetTcpState(tlsc_tcp)
    If st < 0
      tlsc_Refuse(st, "the TCP connection under TLS failed")
    ElseIf st = #SVC_TCP_PEER_CLOSED And tcpEmpty And tlsc_inLen = 0
      ; FIN can coexist with unread TCP bytes. Drain them before deciding EOF.
      ; RFC 8446 section 6.1: absent close_notify, truncation is not excluded.
      ; The application must see failure, never successful close-delimited data.
      tlsc_Refuse(#SVC_EIO, "TCP ended without authenticated TLS close_notify")
    EndIf
  EndIf
EndProcedure

 ; Optional cooperative driver installed by the target composition. The
; arithmetic implementation remains independent of scheduler/target details.
Global *tlsc_advanceHook
Global *tlsc_profileHook
Global *tlsc_closeHook
Procedure tlsc_AdvanceCurrent()
 If tlsc_advanceHook<>0
  tlsc_advanceHook()
 Else
  tlsc_AdvanceWork()
 EndIf
EndProcedure

Procedure TlsClientAdvance()
 Define i.i,slot.i
 For i=0 To #TLSC_CONNECTIONS-1
  slot=(tlsc_cursor+i) % #TLSC_CONNECTIONS
  If tlsc_handles[slot]>0
   tlsc_cursor=(slot+1) % #TLSC_CONNECTIONS
   tlsc_Select(slot) : tlsc_AdvanceCurrent() : ProcedureReturn
  EndIf
 Next
EndProcedure

Procedure.i tlsc_Handle(h.i)
 Define slot.i
 If h>0
  For slot=0 To #TLSC_CONNECTIONS-1
   If tlsc_handles[slot]=h : tlsc_Select(slot) : ProcedureReturn 0 : EndIf
  Next
 EndIf
 gSvcDetail="that TLS handle is not open"
 ProcedureReturn #SVC_EARG
EndProcedure

; ----------------------------------------------------------------------
;  TlsClientOpen(*host, port) - a fresh handle at once, or negative.
; ----------------------------------------------------------------------
Procedure.i TlsClientOpen(*host, port.i)
  Define n.i
  Define r.i
  Define slot.i
  If *host = 0
    gSvcDetail = "the host name pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  If port < 1 Or port > 65535
    gSvcDetail = "a port must be 1 to 65535"
    ProcedureReturn #SVC_EARG
  EndIf
  n = 0
  While n < #TLSC_NAME_MAX - 1 And PeekA(*host + n) <> 0
    n = n + 1
  Wend
  If n = 0 Or n >= #TLSC_NAME_MAX - 1
    gSvcDetail = "the host name must be 1 to 253 characters"
    ProcedureReturn #SVC_EARG
  EndIf
  slot=-1
  For r=0 To #TLSC_CONNECTIONS-1
    If tlsc_handles[r]=0 : slot=r : Break : EndIf
  Next
  If slot<0 Or tlsc_nextHandle=$7FFFFFFF
    gSvcDetail="the bounded TLS connection pool is full"
    ProcedureReturn #SVC_EBUSY
  EndIf
  If WallClockTrusted() = 0
    gSvcDetail = "the clock is not trusted (no SNTP time yet, not set by hand), and certificate dates cannot be checked against a guess"
    ProcedureReturn #SVC_ESTATE
  EndIf
  tlsc_Select(slot)
  tlsc_nextHandle=tlsc_nextHandle+1 : tlsc_handles[slot]=tlsc_nextHandle
  For r = 0 To n - 1
    tlsc_name[tlsc_slot*#TLSC_NAME_MAX+r] = PeekA(*host + r)
  Next
  tlsc_name[tlsc_slot*#TLSC_NAME_MAX+n] = 0
  tlsc_nameLen = n
  tlsc_port = port
  tlsc_ip = 0
  tlsc_tcp = 0
  tlsc_fail = 0
  tlsc_why = 0
  tlsc_tlsErr = 0
  tlsc_x509Err = 0
  tlsc_peerAlert = -1
  tlsc_txLen = 0
  tlsc_txOff = 0
  tlsc_inLen = 0
  tlsc_inOff = 0
  tlsc_ringHead = 0
  tlsc_ringTail = 0
  tlsc_t0 = millis()
  tlsc_appPending[tlsc_slot]=0
  tlsc_state = #TLSC_PREPARE
  ; Opening reserves a handle only. Preparation belongs to the bounded
  ; progress path, not to a call promising a fresh handle at once.
  ProcedureReturn tlsc_handles[tlsc_slot]
EndProcedure

Procedure.i TlsClientState(h.i)
  Define r.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  tlsc_AdvanceCurrent()
  Select tlsc_state
    Case #TLSC_PREPARE
      ProcedureReturn #SVC_TLS_RESOLVING
    Case #TLSC_RESOLVING
      ProcedureReturn #SVC_TLS_RESOLVING
    Case #TLSC_TCP
      ProcedureReturn #SVC_TLS_CONNECTING
    Case #TLSC_HS
      ProcedureReturn #SVC_TLS_HANDSHAKE
    Case #TLSC_OPEN
      ProcedureReturn #SVC_TLS_OPEN
    Case #TLSC_CLOSED
      ProcedureReturn #SVC_TLS_PEER_CLOSED
  EndSelect
  gSvcDetail = tlsc_why
  ProcedureReturn tlsc_fail
EndProcedure

; Plaintext in; bytes taken, 0..n (0 while the handshake runs or the last
; record is still going out).
Procedure.i TlsClientSend(h.i, *b, n.i)
  Define i.i
  Define r.i
  Define take.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  If *b = 0 Or n < 0
    gSvcDetail = "a send needs a buffer and a byte count of zero or more"
    ProcedureReturn #SVC_EARG
  EndIf
  tlsc_AdvanceCurrent()
  If tlsc_state = #TLSC_FAILED
    gSvcDetail = tlsc_why
    ProcedureReturn tlsc_fail
  EndIf
  If tlsc_state <> #TLSC_OPEN Or tlsc_txLen > 0 Or tlsc_appPending[tlsc_slot]>0 Or n = 0
    ProcedureReturn 0
  EndIf
  take = n
  If take > #TLSC_APP_CHUNK
    take = #TLSC_APP_CHUNK
  EndIf
  For i=0 To take-1 : tlsc_plain[tlsc_slot*#TLSC_APP_CHUNK+i]=PeekA(*b+i) : Next
  tlsc_appPending[tlsc_slot]=take
  ProcedureReturn take
EndProcedure

; Plaintext out; bytes delivered, 0 = nothing yet.
Procedure.i TlsClientRecv(h.i, *b, n.i)
  Define r.i
  Define k.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  If *b = 0 Or n < 0
    gSvcDetail = "a receive needs a buffer and a byte count of zero or more"
    ProcedureReturn #SVC_EARG
  EndIf
  tlsc_AdvanceCurrent()
  k = 0
  While k < n And tlsc_ringTail <> tlsc_ringHead
    PokeA(*b + k, tlsc_ring[tlsc_slot*#TLSC_RING+tlsc_ringTail])
    tlsc_ringTail = (tlsc_ringTail + 1) & (#TLSC_RING - 1)
    k = k + 1
  Wend
  If k = 0 And tlsc_state = #TLSC_FAILED
    gSvcDetail = tlsc_why
    ProcedureReturn tlsc_fail
  EndIf
  ProcedureReturn k
EndProcedure

; Close: close_notify if established, then TCP; the handle is free at once.
Procedure.i TlsClientClose(h.i)
  If tlsc_closeHook<>0 : tlsc_closeHook(h) : EndIf
  Define r.i
  Define i.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  If tlsc_state = #TLSC_OPEN And tlsc_txLen = 0
    r = Tls13BuildAlert(@tlsc_tx[tlsc_slot*#TLSC_TX_BUF+0], #TLSC_TX_BUF, #TLS_ALERT_LEVEL_WARNING, #TLS_ALERT_CLOSE_NOTIFY)
    If r > 0
      tlsc_txLen = r
      tlsc_txOff = 0
      tlsc_Flush()
    EndIf
  EndIf
  TcpDialClose(@tlsc_dial[tlsc_slot])
  If tlsc_tcp > 0
    PayNetTcpClose(tlsc_tcp)
  EndIf
  tlsc_tcp = 0
  tlsc_state = #TLSC_IDLE
  tlsc_txLen = 0
  tlsc_inLen = 0
  tlsc_ringHead = 0
  tlsc_ringTail = 0
  tlsc_appPending[tlsc_slot]=0
  tlsc_handles[tlsc_slot]=0
  r=Tls13ContextWipe(@tlsc_context[tlsc_slot*#TLS13_CONTEXT_SIZE],#TLS13_CONTEXT_SIZE)
  r=Tls13ContextRestore(@tlsc_context[tlsc_slot*#TLS13_CONTEXT_SIZE],#TLS13_CONTEXT_SIZE)
  GcmWipe() : AesWipe()
  For i=0 To #TLSC_NAME_MAX-1 : tlsc_name[tlsc_slot*#TLSC_NAME_MAX+i]=0 : Next
  For i=0 To #TLSC_HS_BUF-1 : tlsc_hs[tlsc_slot*#TLSC_HS_BUF+i]=0 : Next
  For i=0 To #TLSC_RECV_BUF-1 : tlsc_recv[tlsc_slot*#TLSC_RECV_BUF+i]=0 : Next
  For i=0 To #TLSC_APP_CHUNK-1 : tlsc_plain[tlsc_slot*#TLSC_APP_CHUNK+i]=0 : Next
  For i=0 To #TLSC_TX_BUF-1 : tlsc_tx[tlsc_slot*#TLSC_TX_BUF+i]=0 : Next
  For i=0 To #TLSC_IN_BUF-1 : tlsc_in[tlsc_slot*#TLSC_IN_BUF+i]=0 : Next
  For i=0 To #TLSC_RING-1 : tlsc_ring[tlsc_slot*#TLSC_RING+i]=0 : Next
  ProcedureReturn #SVC_OK
EndProcedure

; A payload's connection ends with it (RunAt -> PayNetPayloadReturned).
Procedure TlsClientPayloadReturned()
 Define slot.i,rc.i
 For slot=0 To #TLSC_CONNECTIONS-1
  If tlsc_handles[slot]>0 : rc=TlsClientClose(tlsc_handles[slot]) : EndIf
 Next
EndProcedure

; `tls status` - the connection, and on a refusal the library's own codes.
Procedure tlsc_ShowCurrent()
  Print("TLS connection: ")
  Select tlsc_state
    Case #TLSC_IDLE
      PrintN("none")
    Case #TLSC_PREPARE
      PrintN("preparing trust and entropy")
    Case #TLSC_RESOLVING
      PrintN("resolving the name")
    Case #TLSC_TCP
      PrintN("opening TCP")
    Case #TLSC_HS
      PrintN("handshake in progress")
    Case #TLSC_OPEN
      PrintN("open and verified")
    Case #TLSC_CLOSED
      PrintN("closed by the server")
    Case #TLSC_FAILED
      PrintN("FAILED")
  EndSelect
  If tlsc_nameLen > 0
    Print("  host ")
    str_print_at(@tlsc_name[tlsc_slot*#TLSC_NAME_MAX+0])
    Print(":")
    PrintDec(tlsc_port)
    If tlsc_ip <> 0
      Print("  (")
      PutIp(tlsc_ip)
      Print(")")
    EndIf
    PrintNl()
  EndIf
  If tlsc_state = #TLSC_FAILED
    Print("  why ")
    tlsc_Say(tlsc_why) : PrintNl()
    Print("  tls13 refusal ")
    PrintDec(tlsc_tlsErr)
    Print("   x509 verdict ")
    PrintDec(tlsc_x509Err)
    Print("   peer alert ")
    PrintDec(tlsc_peerAlert)
    PrintNl()
  EndIf
EndProcedure

Procedure TlsClientShow()
  If tlsc_profileHook<>0 : tlsc_profileHook() : EndIf
  If tlsc_advanceHook<>0
    PrintN("TLS scheduling: cooperative arithmetic")
  Else
    PrintN("TLS scheduling: synchronous arithmetic")
  EndIf
  Define slot.i,previous.i,count.i
  previous=tlsc_slot
  For slot=0 To #TLSC_CONNECTIONS-1
    If tlsc_handles[slot]>0
      tlsc_Select(slot)
      Print("TLS handle ") : PrintDec(tlsc_handles[slot]) : PrintNl()
      tlsc_ShowCurrent() : count=count+1
    EndIf
  Next
  If count=0 : PrintN("TLS connections: none") : EndIf
  tlsc_Select(previous)
  PrintN("Network service timings since boot (microseconds):")
  PrintN("  phase: calls / total / maximum / in slowest whole call")
  For slot=0 To #NET_SERVICE_PHASES-1
    Select slot
      Case 0 : Print("  whole service")
      Case 1 : Print("  message begin")
      Case 2 : Print("  Wi-Fi maintenance")
      Case 3 : Print("  lease and protocols")
      Case 4 : Print("  NTP")
      Case 5 : Print("  console rearm")
      Case 6 : Print("  console receive")
      Case 7 : Print("  console link-local")
      Case 8 : Print("  HTTP server and TCP")
      Case 9 : Print("  DNS")
      Case 10 : Print("  TCP handles")
      Case 11 : Print("  TLS")
      Case 12 : Print("  receive drain")
      Case 13 : Print("  message end")
    EndSelect
    Print(": ") : PrintDec(netprof_count[slot]) : Print(" / ")
    PrintDec(netprof_total[slot]) : Print(" / ")
    PrintDec(netprof_max[slot]) : Print(" / ") : PrintDec(netprof_worst[slot]) : PrintNl()
  Next
EndProcedure
