; ======================================================================
;  tls_client.pbi - HTTPS FOR EVERYTHING ON THE BOARD. One TLS 1.3 client
;  connection behind a handle: the name is resolved, TCP opened, the
;  handshake run and the certificate chain verified against the root
;  store (Anvil/Core/tls_roots.pbi), and then application bytes go in and
;  out in the clear on this side, encrypted on the wire.
;
;  It serves the service table's TLS slots (80..83 and 87, Anvil/Hal/
;  abi.pbi) for payloads and the monitor's own `https` command, through
;  the SAME code: a kernel service, not a payload's private stack (Ron,
;  2026-10-14: "anvil is to be a full service kernel").
;
;  THE RULE OF Anvil/Core/payload_net.pbi HOLDS: NOTHING WAITS. Open
;  returns a handle at once; DNS, TCP and the handshake advance from
;  TlsClientAdvance, which PayNetService (the payload's once-a-frame
;  slot) and every TLS slot call. The one stretch of pure computation is
;  the handshake's own arithmetic - an X25519 share at open and the chain
;  and CertificateVerify signatures when the server's flight lands - which
;  is done in the call that has the bytes. Its cost depends on cache state
;  and the certificate algorithms; it is not bounded to one display frame.
;
;  ONE CONNECTION AT A TIME. tls13_hs keeps its state in globals (it is
;  the Pico core's design), so there is one handle, 1; a second open while
;  it is in use is #SVC_EBUSY. That is the honest limit of the library,
;  stated where a caller meets it.
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

#TLSC_NAME_MAX  = 256
#TLSC_HS_BUF    = 24576     ; the largest handshake message: a certificate chain
#TLSC_RECV_BUF  = 16896     ; 5 + 16640, RFC 8446's largest record, and slack
#TLSC_TX_BUF    = 20480     ; ClientHello + Finished, or one app record
#TLSC_APP_CHUNK = 16384     ; plaintext per application record
#TLSC_IN_BUF    = 4096      ; TCP bytes read per pass
#TLSC_RING      = 65536     ; plaintext received, not yet read; a power of two
#TLSC_HS_MS     = 20000     ; DNS + TCP + handshake, all of it

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
Global Dim tlsc_name.a[#TLSC_NAME_MAX]
Global Dim tlsc_hs.a[#TLSC_HS_BUF]
Global Dim tlsc_recv.a[#TLSC_RECV_BUF]
Global Dim tlsc_tx.a[#TLSC_TX_BUF]
Global Dim tlsc_in.a[#TLSC_IN_BUF]
Global Dim tlsc_ring.a[#TLSC_RING]

Procedure tlsc_Refuse(code.i, *why)
  If tlsc_state <> #TLSC_FAILED
    tlsc_fail = code
    tlsc_why = *why
    tlsc_tlsErr = Tls13Err
    tlsc_x509Err = Tls13X509Err
    tlsc_peerAlert = Tls13PeerAlert
  EndIf
  tlsc_state = #TLSC_FAILED
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

; Pushes queued record bytes into TCP. 0, or -1 when TCP refused.
Procedure.i tlsc_Flush()
  Define k.i
  While tlsc_txOff < tlsc_txLen
    k = PayNetTcpSend(tlsc_tcp, @tlsc_tx[tlsc_txOff], tlsc_txLen - tlsc_txOff)
    If k < 0
      tlsc_Refuse(k, "the TCP connection under TLS refused a send")
      ProcedureReturn -1
    EndIf
    If k = 0
      Break
    EndIf
    tlsc_txOff = tlsc_txOff + k
  Wend
  If tlsc_txOff >= tlsc_txLen
    tlsc_txOff = 0
    tlsc_txLen = 0
  EndIf
  ProcedureReturn 0
EndProcedure

; Appends a record of n bytes already built at tlsc_tx[tlsc_txLen].
Procedure tlsc_Queued(n.i)
  tlsc_txLen = tlsc_txLen + n
EndProcedure

; Feeds received TCP bytes to TLS while the plaintext ring can take a
; whole record. 0, or -1 when TLS refused.
Procedure.i tlsc_Feed()
  Define fed.i
  Define i.i
  Define n.i
  While tlsc_inOff < tlsc_inLen And tlsc_RingFree() >= #TLSC_APP_CHUNK + 256
    Tls13AppLen = 0
    fed = Tls13FeedBytes(@tlsc_in[tlsc_inOff], tlsc_inLen - tlsc_inOff)
    If fed < 0
      tlsc_Refuse(#SVC_EIO, "the server's TLS was refused - certificate, signature, Finished or record (tls status for the codes)")
      ProcedureReturn -1
    EndIf
    tlsc_inOff = tlsc_inOff + fed
    n = Tls13AppLen
    If n > 0
      For i = 0 To n - 1
        tlsc_ring[tlsc_ringHead] = PeekA(Tls13AppAddr + i)
        tlsc_ringHead = (tlsc_ringHead + 1) & (#TLSC_RING - 1)
      Next
      Tls13AppLen = 0
    EndIf
    If fed = 0
      Break
    EndIf
  Wend
  If tlsc_inOff >= tlsc_inLen
    tlsc_inOff = 0
    tlsc_inLen = 0
  EndIf
  ProcedureReturn 0
EndProcedure

; The handshake begins once TCP is open: init, key share, ClientHello.
Procedure tlsc_Begin()
  Define n.i
  Tls13SetHsBuffer(@tlsc_hs[0], #TLSC_HS_BUF)
  Tls13SetRecvBuffer(@tlsc_recv[0], #TLSC_RECV_BUF)
  Tls13SetGroup(#TLS_GROUP_X25519)
  If Tls13Init(@tlsc_name[0], tlsc_nameLen, WallClockNow()) = 0
    tlsc_Refuse(#SVC_ESTATE, "TLS would not start (no trusted time, no root store, or a key-schedule fault)")
    ProcedureReturn
  EndIf
  If Tls13NewKeyShare() = 0
    tlsc_Refuse(#SVC_EIO, "TLS could not make its key share (the random generator refused)")
    ProcedureReturn
  EndIf
  n = Tls13BuildClientHello(@tlsc_tx[tlsc_txLen], #TLSC_TX_BUF - tlsc_txLen)
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
Procedure TlsClientAdvance()
  Define r.i
  Define st.i
  Define n.i
  Define tcpEmpty.i

  If tlsc_state = #TLSC_IDLE Or tlsc_state = #TLSC_FAILED Or tlsc_state = #TLSC_CLOSED
    ProcedureReturn
  EndIf

  If tlsc_state = #TLSC_RESOLVING Or tlsc_state = #TLSC_TCP Or tlsc_state = #TLSC_HS
    If ((millis() - tlsc_t0) & $FFFFFFFF) > #TLSC_HS_MS
      tlsc_Refuse(#SVC_ETIMEOUT, "the HTTPS connection was not established within 20 seconds")
      ProcedureReturn
    EndIf
  EndIf

  If tlsc_state = #TLSC_RESOLVING
    r = PayNetDnsResolve(@tlsc_name[0])
    If r = #SVC_EAGAIN Or r = #SVC_EBUSY
      ProcedureReturn
    EndIf
    If r < 0
      tlsc_Refuse(r, "the server's name did not resolve")
      ProcedureReturn
    EndIf
    tlsc_ip = r
    r = PayNetTcpOpen(tlsc_ip, tlsc_port)
    If r < 0
      tlsc_Refuse(r, "TCP to the server could not be opened")
      ProcedureReturn
    EndIf
    tlsc_tcp = r
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

  ; Send what is queued, then read and feed.
  If tlsc_Flush() < 0
    ProcedureReturn
  EndIf
  If tlsc_inLen = 0
    n = PayNetTcpRecv(tlsc_tcp, @tlsc_in[0], #TLSC_IN_BUF)
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
      n = Tls13BuildClientFinished(@tlsc_tx[tlsc_txLen], #TLSC_TX_BUF - tlsc_txLen)
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

Procedure.i tlsc_Handle(h.i)
  If h <> 1 Or tlsc_state = #TLSC_IDLE
    gSvcDetail = "that is not an open TLS handle: there is one, 1, and only the TLS open service hands it out"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  TlsClientOpen(*host, port) - handle 1 at once, or negative.
; ----------------------------------------------------------------------
Procedure.i TlsClientOpen(*host, port.i)
  Define n.i
  Define r.i
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
  If tlsc_state <> #TLSC_IDLE
    gSvcDetail = "the one TLS connection is in use - close it first"
    ProcedureReturn #SVC_EBUSY
  EndIf
  If WallClockTrusted() = 0
    gSvcDetail = "the clock is not trusted (no SNTP time yet, not set by hand), and certificate dates cannot be checked against a guess"
    ProcedureReturn #SVC_ESTATE
  EndIf
  r = TlsRootsEnsure()
  If r <= 0
    gSvcDetail = TlsRootsErrorText(r)
    ProcedureReturn #SVC_ESTATE
  EndIf
  If tlsc_seeded = 0
    If DrbgAutoSeed() < 0
      gSvcDetail = "the hardware random generator would not seed TLS's generator"
      ProcedureReturn #SVC_EIO
    EndIf
    tlsc_seeded = 1
  Else
    DrbgAutoReseed()
  EndIf
  For r = 0 To n - 1
    tlsc_name[r] = PeekA(*host + r)
  Next
  tlsc_name[n] = 0
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
  tlsc_state = #TLSC_RESOLVING
  TlsClientAdvance()
  ProcedureReturn 1
EndProcedure

Procedure.i TlsClientState(h.i)
  Define r.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  TlsClientAdvance()
  Select tlsc_state
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
  TlsClientAdvance()
  If tlsc_state = #TLSC_FAILED
    gSvcDetail = tlsc_why
    ProcedureReturn tlsc_fail
  EndIf
  If tlsc_state <> #TLSC_OPEN Or tlsc_txLen > 0 Or n = 0
    ProcedureReturn 0
  EndIf
  take = n
  If take > #TLSC_APP_CHUNK
    take = #TLSC_APP_CHUNK
  EndIf
  r = Tls13BuildAppRecord(@tlsc_tx[0], #TLSC_TX_BUF, *b, take)
  If r <= 0
    tlsc_Refuse(#SVC_EIO, "TLS could not protect the bytes to send")
    gSvcDetail = tlsc_why
    ProcedureReturn tlsc_fail
  EndIf
  tlsc_txLen = r
  tlsc_txOff = 0
  tlsc_Flush()
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
  TlsClientAdvance()
  k = 0
  While k < n And tlsc_ringTail <> tlsc_ringHead
    PokeA(*b + k, tlsc_ring[tlsc_ringTail])
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
  Define r.i
  r = tlsc_Handle(h)
  If r < 0
    ProcedureReturn r
  EndIf
  If tlsc_state = #TLSC_OPEN And tlsc_txLen = 0
    r = Tls13BuildAlert(@tlsc_tx[0], #TLSC_TX_BUF, #TLS_ALERT_LEVEL_WARNING, #TLS_ALERT_CLOSE_NOTIFY)
    If r > 0
      tlsc_txLen = r
      tlsc_txOff = 0
      tlsc_Flush()
    EndIf
  EndIf
  If tlsc_tcp > 0
    PayNetTcpClose(tlsc_tcp)
  EndIf
  tlsc_tcp = 0
  tlsc_state = #TLSC_IDLE
  tlsc_txLen = 0
  tlsc_inLen = 0
  tlsc_ringHead = 0
  tlsc_ringTail = 0
  ProcedureReturn #SVC_OK
EndProcedure

; A payload's connection ends with it (RunAt -> PayNetPayloadReturned).
Procedure TlsClientPayloadReturned()
  If tlsc_state <> #TLSC_IDLE
    TlsClientClose(1)
  EndIf
EndProcedure

; `tls status` - the connection, and on a refusal the library's own codes.
Procedure TlsClientShow()
  Print("TLS connection: ")
  Select tlsc_state
    Case #TLSC_IDLE
      PrintN("none")
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
    str_print_at(@tlsc_name[0])
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
