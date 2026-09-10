; ======================================================================
;  tcp and http get - the two commands the TCP work is driven by.
; ======================================================================
;  CORE. They name no chip and touch no register: everything below goes
;  through RaspberryPi4/Lib/tcp.pi4 and RaspberryPi4/Lib/http.pi4, which
;  go through net.pi4 and the link seam, which is what lets the same
;  command work over the wired port and over the radio without knowing
;  that either exists. Gated on #CAP_NET like ping, dns and dhcp.
;
;  THAT WAS ALMOST TRUE UNTIL 2026-09-05. This file called LinkBringUp()
;  at three sites and LinkSay() at one, and both of those - despite the
;  portable-looking names - were DEFINED IN RaspberryPi4/Board/eth.pi4,
;  one board's network file. So a core command that named no chip still
;  could not be built without that board's Ethernet code underneath it,
;  and nothing in the spelling gave it away, which is the harder version
;  of the same problem. LinkBringUp is now HwLinkOpen, a name in
;  Anvil/Hal/hal.pbi's HwLink* seam that every board answers, and
;  LinkSay lives in Anvil/Core/net_cmd.pbi, where the wording it prints
;  is the same on every board.
;
;  WHY `http get` IS HERE AND NOT IN A DIAGNOSTIC
;  ----------------------------------------------------------------------
;  It is the smoke test for the whole stack and it has to be typed by a
;  person at a prompt for that to be worth anything. `tcp connect`
;  proves a handshake; `http get http://example.com/` proves the
;  handshake, the window, segmentation, reassembly of a reply that
;  arrives in several segments of the server's choosing, a clean FIN
;  close, DNS, and the routing decision to a host that is not on this
;  segment - in one line, against a machine nobody here controls, with
;  an answer nobody can misread.
;
;  THE COMMANDS ARE NON-BLOCKING WHERE THE LIBRARY IS
;  ----------------------------------------------------------------------
;  `tcp connect` sends the SYN and returns to the prompt; the connection
;  finishes in TcpTick(), which the prompt calls while it waits for a
;  key. That is the same shape the wireless console has and it is
;  deliberate: a blocking connect at the prompt is a board that looks
;  hung to the person who typed it, and on a board reached ONLY over the
;  network it is a board that cannot be rescued.
;
;  `http get` is the exception and blocks, because the operator typed a
;  fetch and is waiting for its answer. Every phase of it is bounded and
;  a keypress stops it.
; ======================================================================

#TCPCMD_RECV_DEFAULT = 256      ; bytes `tcp recv` prints when not told
#TCPCMD_BODY_MAX     = 4096     ; the body buffer `http get` fills
#TCPCMD_BODY_SHOW    = 512      ; and how much of it is printed by default
#TCPCMD_LINE_WRAP    = 72

Global Dim gHttpBody.a[#TCPCMD_BODY_MAX]

Procedure tcp_PutState(s.i)
  UartWriteStr(TcpStateName(s))
EndProcedure

; Print n bytes, showing anything unprintable as a dot and wrapping. A
; monitor that prints raw bytes to a terminal can be made to redraw the
; screen, change the character set or ring the bell by whatever is on
; the other end of the connection, and "the far end can drive my
; terminal" is not a property a diagnostic should have.
Procedure tcp_PutBytes(p.i, n.i)
  Define i.i
  Define c.i
  Define col.i
  col = 0
  i = 0
  While i < n
    c = PeekA(p + i) & $FF
    If c = 10
      PrintNl()
      col = 0
    ElseIf c = 13
      ; swallowed; the LF beside it ends the line
    ElseIf c < 32 Or c > 126
      UartWrite(46)                    ; 46 is a full stop
      col = col + 1
    Else
      UartWrite(c)
      col = col + 1
    EndIf
    If col >= #TCPCMD_LINE_WRAP
      PrintNl()
      col = 0
    EndIf
    i = i + 1
  Wend
  If col > 0
    PrintNl()
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  tcp status - the socket table, and the numbers a bench asks for.
; ----------------------------------------------------------------------
Procedure tcp_Status()
  Define i.i
  Define keep.i
  Define any.i
  keep = TcpCurrent()
  any = 0
  PrintN("  #  state         local  peer                    port  rx    tx")
  i = 0
  While i < #TCP_SOCKETS
    TcpUse(i)
    Print("  ")
    PrintDec(i)
    Print("  ")
    PutPadded(TcpStateName(TcpState()), 13)
    Print(" ")
    PrintDec(TcpLocalPort())
    Print("  ")
    If TcpPeerIp() = 0
      Print("-                      ")
    Else
      PutIp(TcpPeerIp())
      Print("            ")
    EndIf
    PrintDec(TcpPeerPort())
    Print("   ")
    PrintDec(TcpAvailable())
    Print("     ")
    PrintDec(TcpSendSpace())
    PrintNl()
    If TcpState() = #TCP_LISTEN
      PrintN("     wildcard: every usable addressed interface")
    ElseIf TcpLocalIp() <> 0
      Print("     bound to ")
      UartWriteStr(HwLinkName(TcpLinkKind()))
      Print(" at ")
      PutIp(TcpLocalIp())
      PrintNl()
    EndIf
    If TcpState() <> #TCP_CLOSED
      any = 1
    EndIf
    i = i + 1
  Wend
  TcpUse(keep)
  If any = 0
    PrintN("  Nothing is open. tcp connect <host> <port> opens one.")
  EndIf

  PrintNl()
  PrintN("Since the last reset, over every socket:")
  Print("  segments in ")
  PrintDec(tcp_seg_rx)
  Print(", out ")
  PrintDec(tcp_seg_tx)
  Print(", RETRANSMITTED ")
  PrintDec(tcp_retrans)
  Print(", deliberately dropped ")
  PrintDec(tcp_dropped)
  PrintN(".")
  Print("  duplicate ACKs sent ")
  PrintDec(tcp_dupacks)
  Print(", out of order queued ")
  PrintDec(tcp_ooo_queued)
  Print(", delivered ")
  PrintDec(tcp_ooo_deliver)
  Print(", dropped ")
  PrintDec(tcp_ooo_drop)
  PrintN(".")
  Print("  unacceptable ")
  PrintDec(tcp_unacceptable)
  Print(", resets in ")
  PrintDec(tcp_rst_rx)
  Print(", out ")
  PrintDec(tcp_rst_tx)
  Print(", to a closed port ")
  PrintDec(tcp_norst)
  PrintN(".")
  Print("  zero windows seen ")
  PrintDec(tcp_zerowin)
  Print(", probes sent ")
  PrintDec(tcp_probes)
  Print(", keepalives ")
  PrintDec(tcp_keeps)
  Print(", link refusals ")
  PrintDec(tcp_txfail)
  PrintN(".")
  ; WINDOW UPDATES SENT BECAUSE THE APPLICATION READ. This is on its own
  ; line rather than tucked into the one above because it is the number
  ; that tells a slow transfer apart from a stalled one: a receive that
  ; crawls in five-second steps with this at ZERO is a peer waiting out
  ; its persist timer, which is a fault at THIS end and reads like a
  ; slow network from the other. See TcpRead in RaspberryPi4/Lib/tcp.pi4.
  Print("  window updates sent when the application read ")
  PrintDec(tcp_wndup)
  PrintN(".")
  Print("  bytes acknowledged by peers ")
  PrintDec(tcp_bytes_tx)
  Print(", delivered to a ring ")
  PrintDec(tcp_bytes_rx)
  PrintN(".")
  Print("  retransmit timeout now ")
  PrintDec(tcp_rto)
  Print(" ms, smoothed round trip ")
  PrintDec(tcp_srtt8 / 8)
  Print(" ms, last ")
  PrintDec(tcp_rtt_last)
  PrintN(" ms.")
  Print("  send MSS ")
  PrintDec(tcp_snd_mss)
  Print(", the peer's window ")
  PrintDec(tcp_snd_wnd)
  Print(", the one we advertise ")
  PrintDec(tcp_rcv_wnd)
  PrintN(".")
  If tcp_drop_every > 0
    Print("  !! THE LOSS INJECTOR IS ARMED, TABLE-WIDE: every ")
    PrintDec(tcp_drop_every)
    PrintN("th data segment on")
    PrintN("     ANY socket is built, checksummed and then thrown away on purpose.")
    PrintN("     A retransmission is never itself dropped. This is a bench")
    PrintN("     instrument and it must be off in anything shipped. Type")
    PrintN("     tcp drop 0 to turn it off.")
  EndIf
  PrintNl()
  If LinkUp() = 0
    PrintN("No interface is carrying traffic. Type net to see why.")
  Else
    LinkSay()
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  tcp connect <host|a.b.c.d> <port>
; ----------------------------------------------------------------------
Procedure tcp_Connect()
  Define host.i
  Define portStr.i
  Define ip.i
  Define port.i
  Define s.i
  Define rc.i
  Define t0.i
  Define k.i

  host = ArgWord()
  portStr = ArgWord()
  If host = 0 Or portStr = 0
    PrintN("!! tcp connect needs a host and a port, so nothing was done.")
    PrintN("   tcp connect 192.168.1.10 80   or   tcp connect example.com 80")
    ProcedureReturn
  EndIf
  port = 0
  ip = 0
  ; A port is read here rather than through ParseDec, which reads from
  ; the line and the line has already been walked past by ArgWord.
  s = 0
  While PeekA(portStr + s) <> 0
    If PeekA(portStr + s) < 48 Or PeekA(portStr + s) > 57
      PrintN("!! that port is not a number, so nothing was done. A port is 1 to")
      PrintN("   65535 in plain decimal.")
      ProcedureReturn
    EndIf
    port = port * 10 + (PeekA(portStr + s) - 48)
    If port > 65535
      PrintN("!! that port is above 65535, so nothing was done.")
      ProcedureReturn
    EndIf
    s = s + 1
  Wend
  If port < 1
    PrintN("!! a port must be at least 1, so nothing was done.")
    ProcedureReturn
  EndIf

  If HwLinkOpen(1) = 0
    ProcedureReturn
  EndIf

  ip = ParseDotted(host)
  If ip <= 0
    ip = ResolveName(host)
    If ip <= 0
      ProcedureReturn                  ; ResolveName has already said why
    EndIf
  EndIf

  s = TcpAlloc()
  If s < 0
    Print("!! ")
    UartWriteStr(TcpErrorText(#NET_TCP_E_BUSY))
    PrintNl()
    ProcedureReturn
  EndIf
  TcpUse(s)

  ; TcpConnect is non-blocking and answers #NET_TCP_E_ARP until the next
  ; hop has been resolved, which is not a failure - it is the ARP
  ; exchange happening. Pump for it here rather than making the operator
  ; type the command twice.
  ; WHICH INTERFACE CAN REACH IT. TCP latches the interface with the
  ; rest of the peer, so the route is resolved once, here, and handed
  ; down; a board with a cable and a radio has a different source
  ; address and a different hardware address on each.
  k = NetIfForDest(ip)
  If k = #HW_LINK_NONE
    Print("!! ")
    UartWriteStr(TcpErrorText(#NET_TCP_E_ROUTE))
    PrintNl()
    ProcedureReturn
  EndIf
  t0 = millis()
  While 1 = 1
    rc = TcpConnect(k, ip, port)
    If rc = #NET_TCP_OK
      Break
    EndIf
    If rc <> #NET_TCP_E_ARP
      Print("!! ")
      UartWriteStr(TcpErrorText(rc))
      PrintNl()
      ProcedureReturn
    EndIf
    TcpPoll(20)
    If OutBreak() <> 0
      PrintN("  Stopped before any SYN went out, so nothing was opened.")
      ProcedureReturn
    EndIf
    If (millis() - t0) > 4000
      Print("!! ")
      UartWriteStr(TcpErrorText(#NET_TCP_E_ARP))
      PrintNl()
      PrintN("   Four seconds of address requests went unanswered, so NO SYN WAS")
      PrintN("   EVER SENT and this is not a TCP result at all. The machine at that")
      PrintN("   address is not on this segment, or the gateway is wrong.")
      ProcedureReturn
    EndIf
  Wend

  Print("Socket ")
  PrintDec(s)
  Print(": SYN sent to ")
  PutIp(ip)
  Print(" port ")
  PrintDec(port)
  Print(" from port ")
  PrintDec(TcpLocalPort())
  PrintN(".")
  Print("  It goes out over ")
  UartWriteStr(LinkName())
  PrintN("; the handshake finishes in the background.")
  PrintN("  tcp status says when it is ESTABLISHED, or why it is not.")
EndProcedure

; ----------------------------------------------------------------------
;  tcp listen <port> - the minimal listening socket.
; ----------------------------------------------------------------------
Procedure tcp_Listen()
  Define portStr.i
  Define port.i
  Define s.i
  Define i.i
  Define rc.i
  portStr = ArgWord()
  If portStr = 0
    PrintN("!! tcp listen needs a port, so nothing was done. tcp listen 7")
    ProcedureReturn
  EndIf
  port = 0
  i = 0
  While PeekA(portStr + i) <> 0
    If PeekA(portStr + i) < 48 Or PeekA(portStr + i) > 57
      PrintN("!! that port is not a number, so nothing was done.")
      ProcedureReturn
    EndIf
    port = port * 10 + (PeekA(portStr + i) - 48)
    i = i + 1
  Wend
  If HwLinkOpen(1) = 0
    ProcedureReturn
  EndIf
  s = TcpAlloc()
  If s < 0
    Print("!! ")
    UartWriteStr(TcpErrorText(#NET_TCP_E_BUSY))
    PrintNl()
    ProcedureReturn
  EndIf
  TcpUse(s)
  rc = TcpListen(port)
  If rc <> #NET_TCP_OK
    Print("!! ")
    UartWriteStr(TcpErrorText(rc))
    PrintNl()
    ProcedureReturn
  EndIf
  Print("Socket ")
  PrintDec(s)
  Print(" is listening on port ")
  PrintDec(port)
  Print(" over ")
  UartWriteStr(LinkName())
  PrintN(".")
  PrintN("  One connection at a time. A SYN for any other port is answered with a")
  PrintN("  reset, which is what makes a closed port say so instantly instead of")
  PrintN("  timing out.")
EndProcedure

; ----------------------------------------------------------------------
;  tcp send <text> - the text, then CRLF.
;
;  THE CRLF IS ADDED AND THAT IS SAID OUT LOUD, because the first thing
;  anybody types is a request line and every line-based protocol on the
;  internet ends its lines that way. A raw-bytes mode would be a
;  different command.
; ----------------------------------------------------------------------
Procedure tcp_Send()
  Define text.i
  Define n.i
  Define k.i
  Define sent.i
  Define t0.i
  Define crlf.i
  text = ArgRest()
  If text = 0
    PrintN("!! tcp send needs something to send, so nothing was sent.")
    PrintN("   Everything after the word send goes out, followed by a carriage")
    PrintN("   return and a line feed.")
    ProcedureReturn
  EndIf
  If TcpState() <> #TCP_ESTABLISHED And TcpState() <> #TCP_CLOSE_WAIT
    Print("!! this socket is ")
    tcp_PutState(TcpState())
    PrintN(", not ESTABLISHED, so nothing was sent.")
    PrintN("   tcp status shows every socket; tcp connect opens one.")
    ProcedureReturn
  EndIf
  n = StrLenZ(text)
  sent = 0
  t0 = millis()
  While sent < n
    k = TcpSend(text + sent, n - sent)
    If k > 0
      sent = sent + k
      t0 = millis()
    EndIf
    TcpPoll(5)
    If TcpState() = #TCP_CLOSED
      PrintN("!! the connection closed while the text was being sent, so only part")
      PrintN("   of it went. tcp status says whether that was a reset or a close.")
      ProcedureReturn
    EndIf
    If OutBreak() <> 0
      PrintN("  Stopped part way; part of the text has already gone.")
      ProcedureReturn
    EndIf
    If (millis() - t0) > 5000
      PrintN("!! five seconds with no room in the window and no progress, so the")
      PrintN("   rest was not sent. The peer has stopped reading.")
      ProcedureReturn
    EndIf
  Wend
  ; The two bytes that end a line, sent from a two-byte buffer rather
  ; than appended to the caller's text, which is the command line and is
  ; not ours to write past.
  crlf = @gHttpBody[0]
  PokeB(crlf + 0, 13)
  PokeB(crlf + 1, 10)
  k = 0
  t0 = millis()
  While k < 2
    k = k + TcpSend(crlf + k, 2 - k)
    TcpPoll(5)
    If (millis() - t0) > 2000
      Break
    EndIf
  Wend
  Print("Sent ")
  PrintDec(n + 2)
  PrintN(" bytes, the carriage return and line feed included.")
EndProcedure

; ----------------------------------------------------------------------
;  tcp recv [n] - take up to n bytes out of the receive ring and print.
; ----------------------------------------------------------------------
Procedure tcp_Recv()
  Define nStr.i
  Define want.i
  Define got.i
  Define i.i
  nStr = ArgWord()
  want = #TCPCMD_RECV_DEFAULT
  If nStr <> 0
    want = 0
    i = 0
    While PeekA(nStr + i) <> 0
      If PeekA(nStr + i) < 48 Or PeekA(nStr + i) > 57
        PrintN("!! tcp recv takes a count in plain decimal, so nothing was read.")
        ProcedureReturn
      EndIf
      want = want * 10 + (PeekA(nStr + i) - 48)
      i = i + 1
    Wend
  EndIf
  If want > #TCPCMD_BODY_MAX
    want = #TCPCMD_BODY_MAX
  EndIf
  If want < 1
    PrintN("!! a count of zero reads nothing, so nothing was read.")
    ProcedureReturn
  EndIf
  ; Pump once first: bytes may be sitting in a segment that has arrived
  ; and not yet been processed, and "there is nothing here" would be a
  ; wrong answer given a moment too early.
  TcpPoll(20)
  got = TcpRead(@gHttpBody[0], want)
  If got <= 0
    If TcpAvailable() = 0
      Print("Nothing has arrived. The socket is ")
      tcp_PutState(TcpState())
      PrintN(".")
    EndIf
    ProcedureReturn
  EndIf
  Print("--- ")
  PrintDec(got)
  Print(" bytes, ")
  PrintDec(TcpAvailable())
  PrintN(" still waiting ---")
  tcp_PutBytes(@gHttpBody[0], got)
  PrintN("--- end ---")
EndProcedure

Procedure tcp_Close()
  Define rc.i
  Define t0.i
  If TcpState() = #TCP_CLOSED
    PrintN("This socket is already closed, so nothing was done.")
    ProcedureReturn
  EndIf
  rc = TcpClose()
  If rc <> #NET_TCP_OK
    Print("!! ")
    UartWriteStr(TcpErrorText(rc))
    PrintNl()
    ProcedureReturn
  EndIf
  ; Let the FIN and its acknowledgment happen while the operator is
  ; still looking, rather than reporting a state that is about to change.
  t0 = millis()
  While (millis() - t0) < 1000
    TcpPoll(10)
    If TcpState() = #TCP_CLOSED Or TcpState() = #TCP_TIME_WAIT
      Break
    EndIf
  Wend
  Print("Closed. The socket is ")
  tcp_PutState(TcpState())
  PrintN(".")
  If TcpState() = #TCP_TIME_WAIT
    PrintN("  TIME-WAIT is not a fault: the connection is over and the socket is")
    PrintN("  held for four minutes so that a late duplicate from it cannot be")
    PrintN("  mistaken for the next connection. Another socket is used meanwhile.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  tcp drop <n> - arm the deliberate loss injector, for the bench.
; ----------------------------------------------------------------------
Procedure tcp_Drop()
  Define nStr.i
  Define n.i
  Define i.i
  nStr = ArgWord()
  If nStr = 0
    Print("The loss injector is ")
    If tcp_drop_every = 0
      PrintN("OFF.")
    Else
      Print("ON, every ")
      PrintDec(tcp_drop_every)
      PrintN("th data segment.")
    EndIf
    PrintN("  tcp drop <n> throws away every nth DATA segment after it has been")
    PrintN("  built and checksummed, so the retransmission path is exercised for")
    PrintN("  real. A retransmission is never itself dropped. tcp drop 0 is off.")
    PrintN("  IT IS TABLE-WIDE, not per socket: it counts data segments on every")
    PrintN("  socket together.")
    ProcedureReturn
  EndIf
  n = 0
  i = 0
  While PeekA(nStr + i) <> 0
    If PeekA(nStr + i) < 48 Or PeekA(nStr + i) > 57
      PrintN("!! tcp drop takes a count in plain decimal, so nothing was changed.")
      ProcedureReturn
    EndIf
    n = n * 10 + (PeekA(nStr + i) - 48)
    i = i + 1
  Wend
  TcpDropEvery(n)
  If n = 0
    PrintN("The loss injector is OFF. Every segment now goes out.")
  Else
    Print("!! THE LOSS INJECTOR IS ARMED, TABLE-WIDE: every ")
    PrintDec(n)
    PrintN("th data")
    PrintN("   segment on ANY socket will be built, checksummed and then thrown")
    PrintN("   away on purpose.")
    PrintN("   This is a bench instrument. Nothing shipped may leave it on, and")
    PrintN("   tcp status prints this warning for as long as it is.")
  EndIf
EndProcedure

Procedure tcp_Keep()
  Define nStr.i
  Define n.i
  Define i.i
  nStr = ArgWord()
  If nStr = 0
    Print("Keepalive on socket ")
    PrintDec(TcpCurrent())
    Print(" is ")
    If TcpKeepaliveMs() = 0
      PrintN("OFF, which is the default and what the RFC requires.")
    Else
      PrintDec(TcpKeepaliveMs() / 1000)
      PrintN(" seconds of idle time.")
    EndIf
    PrintN("  tcp keepalive <seconds> arms it; 0 turns it off. It only runs when")
    PrintN("  nothing is in flight - the retransmission timer already proves the")
    PrintN("  peer is alive whenever something is.")
    ProcedureReturn
  EndIf
  n = 0
  i = 0
  While PeekA(nStr + i) <> 0
    If PeekA(nStr + i) < 48 Or PeekA(nStr + i) > 57
      PrintN("!! tcp keepalive takes seconds in plain decimal, so nothing changed.")
      ProcedureReturn
    EndIf
    n = n * 10 + (PeekA(nStr + i) - 48)
    i = i + 1
  Wend
  TcpKeepalive(n)
  If n = 0
    PrintN("Keepalive is off on this socket.")
  Else
    Print("Keepalive armed at ")
    PrintDec(n)
    PrintN(" seconds of idle time, three probes.")
  EndIf
EndProcedure

Procedure tcp_Use()
  Define nStr.i
  Define n.i
  Define i.i
  nStr = ArgWord()
  If nStr = 0
    Print("Socket ")
    PrintDec(TcpCurrent())
    PrintN(" is the one tcp send, tcp recv and tcp close act on.")
    PrintN("  tcp use <n> picks another; tcp status lists them all.")
    ProcedureReturn
  EndIf
  n = 0
  i = 0
  While PeekA(nStr + i) <> 0
    If PeekA(nStr + i) < 48 Or PeekA(nStr + i) > 57
      PrintN("!! tcp use takes a socket number in plain decimal.")
      ProcedureReturn
    EndIf
    n = n * 10 + (PeekA(nStr + i) - 48)
    i = i + 1
  Wend
  If TcpUse(n) <> #NET_TCP_OK
    Print("!! ")
    UartWriteStr(TcpErrorText(#NET_TCP_E_SOCKET))
    PrintNl()
    ProcedureReturn
  EndIf
  Print("Socket ")
  PrintDec(n)
  Print(" selected. It is ")
  tcp_PutState(TcpState())
  PrintN(".")
EndProcedure

; ======================================================================
;  CmdTcp
; ======================================================================
Procedure CmdTcp()
  If RequireCap(#CAP_NET, "tcp", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If gWordLen = 0 Or WordIs("status") <> 0 Or WordIs("show") <> 0
    tcp_Status()
    ProcedureReturn
  EndIf
  If WordIs("connect") <> 0 Or WordIs("open") <> 0
    tcp_Connect()
    ProcedureReturn
  EndIf
  If WordIs("listen") <> 0
    tcp_Listen()
    ProcedureReturn
  EndIf
  If WordIs("send") <> 0
    tcp_Send()
    ProcedureReturn
  EndIf
  If WordIs("recv") <> 0 Or WordIs("read") <> 0
    tcp_Recv()
    ProcedureReturn
  EndIf
  If WordIs("close") <> 0
    tcp_Close()
    ProcedureReturn
  EndIf
  If WordIs("abort") <> 0 Or WordIs("reset") <> 0
    TcpAbort()
    PrintN("A reset was sent and the socket is closed. That is the hard exit -")
    PrintN("the peer is told the connection is gone rather than being asked.")
    ProcedureReturn
  EndIf
  If WordIs("use") <> 0
    tcp_Use()
    ProcedureReturn
  EndIf
  If WordIs("drop") <> 0
    tcp_Drop()
    ProcedureReturn
  EndIf
  If WordIs("keepalive") <> 0 Or WordIs("keep") <> 0
    tcp_Keep()
    ProcedureReturn
  EndIf
  PrintN("!! tcp does not know that word, so nothing was done. It takes:")
  PrintN("   tcp connect <host|a.b.c.d> <port>    open one")
  PrintN("   tcp listen <port>                    wait for one")
  PrintN("   tcp send <text>                      the text, then CR LF")
  PrintN("   tcp recv [n]                         print what has arrived")
  PrintN("   tcp close                            the polite close")
  PrintN("   tcp abort                            a reset, the hard one")
  PrintN("   tcp status                           every socket and the counters")
  PrintN("   tcp use <n>                          pick which socket the rest act on")
  PrintN("   tcp drop <n>                         the bench loss injector")
  PrintN("   tcp keepalive <seconds>              0 is off, and off is the default")
EndProcedure

; ======================================================================
;  CmdHttp - http get <url>
; ======================================================================
Procedure http_Get()
  Define url.i
  Define ip.i
  Define rc.i
  Define t0.i
  Define ms.i
  Define show.i

  url = ArgRest()
  If url = 0
    PrintN("!! http get needs a URL, so nothing was fetched.")
    PrintN("   http get http://example.com/")
    ProcedureReturn
  EndIf

  rc = HttpParseUrl(url)
  If rc <> #HTTP_OK
    Print("!! ")
    UartWriteStr(HttpErrorText(rc))
    PrintNl()
    ProcedureReturn
  EndIf

  If HwLinkOpen(1) = 0
    ProcedureReturn
  EndIf

  ip = ParseDotted(HttpHost())
  If ip <= 0
    ip = ResolveName(HttpHost())
    If ip <= 0
      ProcedureReturn                  ; ResolveName has already said why
    EndIf
  EndIf

  Print("GET ")
  UartWriteStr(HttpPath())
  Print(" from ")
  UartWriteStr(HttpHost())
  Print(" at ")
  PutIp(ip)
  Print(" port ")
  PrintDec(HttpUrlPort())
  PrintN(",")
  Print("  over ")
  UartWriteStr(LinkName())
  PrintN(". Press a key to stop.")
  UartDrain()

  t0 = millis()
  rc = HttpGet(ip, @gHttpBody[0], #TCPCMD_BODY_MAX)
  ms = millis() - t0

  If rc <> #HTTP_OK And rc <> #HTTP_E_TRUNC
    Print("!! ")
    UartWriteStr(HttpErrorText(rc))
    PrintNl()
    If HttpTcpError() <> 0
      Print("   Underneath it: ")
      UartWriteStr(TcpErrorText(HttpTcpError()))
      PrintNl()
    EndIf
    ProcedureReturn
  EndIf

  Print("HTTP/1.1 ")
  PrintDec(HttpStatus())
  Print("  -  ")
  PrintDec(HttpHeaderCount())
  Print(" header lines, framed by ")
  UartWriteStr(HttpFramingName(HttpFraming()))
  PrintN(",")
  Print("  ")
  PrintDec(HttpBodySeen())
  Print(" body bytes in ")
  PrintDec(ms)
  Print(" ms over ")
  PrintDec(HttpRxBytes())
  PrintN(" bytes of response.")
  If HttpContentLength() >= 0
    Print("  Content-Length said ")
    PrintDec(HttpContentLength())
    PrintN(".")
  EndIf
  If HttpHeadersDropped() > 0
    Print("  ")
    PrintDec(HttpHeadersDropped())
    PrintN(" header lines were longer than the buffer and were NOT parsed.")
    PrintN("  They are counted rather than truncated, because half a header read")
    PrintN("  as a whole one is worse than a header nobody read.")
  EndIf
  If HttpIsRedirect() <> 0
    Print("  This is a redirect and it was NOT followed. Location: ")
    UartWriteStr(HttpLocation())
    PrintNl()
    PrintN("  Fetch that URL yourself if you want it.")
  EndIf
  If rc = #HTTP_E_TRUNC
    Print("  ")
    UartWriteStr(HttpErrorText(rc))
    PrintNl()
  EndIf

  show = HttpBodyLen()
  If show > #TCPCMD_BODY_SHOW
    show = #TCPCMD_BODY_SHOW
  EndIf
  If show > 0
    Print("--- the first ")
    PrintDec(show)
    Print(" of ")
    PrintDec(HttpBodyLen())
    PrintN(" body bytes ---")
    tcp_PutBytes(@gHttpBody[0], show)
    PrintN("--- end ---")
  Else
    PrintN("The response carried no body.")
  EndIf
EndProcedure

Procedure CmdHttp()
  If RequireCap(#CAP_NET, "http", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("get") <> 0
    http_Get()
    ProcedureReturn
  EndIf
  PrintN("!! http takes one word and it is get, so nothing was fetched.")
  PrintN("   http get http://example.com/")
  PrintN("   This is PLAIN HTTP over port 80 and there is no TLS here at all, so")
  PrintN("   an https URL is refused by name rather than fetched in clear.")
EndProcedure
