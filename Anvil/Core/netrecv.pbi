; ======================================================================
;  netrecv.pi4 - THE RECEIVER. An image over the network, into a bounded
;  window of RAM.
;
;  CORE. Nothing here names a chip or touches a register: the wire is
;  reached through RaspberryPi4/Lib/tcp.pi4 and the link seam, the same
;  way `tcp` and `http get` reach it, so this works over the wired port
;  and over the radio without knowing that either exists.
;
;  ----------------------------------------------------------------------
;  THIS FILE IS THE STATE MACHINE AND NOTHING ELSE, AND THAT IS THE POINT
;  ----------------------------------------------------------------------
;  The console wiring - the argument parsing, the range refusals, every
;  printed sentence and the `net recv` command word - is in
;  Anvil/Core/netrecv_cmd.pbi. This file calls FOUR things it does not
;  define: the Tcp* family, millis(), Sha256Of() and PokeB/PeekA. It
;  prints nothing and parses nothing.
;
;  That split is not tidiness. tools/a64/a64_tcp_check.py drives the real
;  tcp.pi4 with byte-exact Ethernet frames and no device model at all,
;  and because this file's dependency list is those four names it can be
;  compiled into that harness and driven by the same scripted peer. So
;  the receiver's state machine is GRADED against real frames rather than
;  reasoned about - the listener, the streaming, the ceiling and the FIN
;  that ends the file - which would be impossible if it were tangled up
;  with a command parser and a console.
;
;      the state machine, against frames   tools/a64/a64_tcp_check.py
;      the refusals, in the built image    tools/a64/a64_anvil_check.py
;
;  ----------------------------------------------------------------------
;  WHY IT EXISTS, IN ONE MEASUREMENT
;  ----------------------------------------------------------------------
;  A 1.4 MB Anvil image over the serial console at 115200 is about two
;  minutes, every time anybody changes one line, and a long transfer down
;  that cable has started corrupting. The acknowledged datagram path
;  (`wb`) is stop-and-wait, one kilobyte at a time, and measures about
;  100 KB/s on this bench. This is the same bytes over a TCP connection,
;  which pipelines, and the numbers are in the note this landed with.
;
;  ----------------------------------------------------------------------
;  THE PROTOCOL IS "THE BYTES, THEN CLOSE", AND THAT IS DELIBERATE
;  ----------------------------------------------------------------------
;  There is no header, no length field and no per-chunk acknowledgement
;  on the wire. TCP already carries the framing, the ordering, the
;  retransmission and the end-of-stream marker; a second layer of all
;  four on top of it would be a second thing to get wrong, and `wb`
;  exists precisely because UDP has none of them.
;
;  So: the peer connects, sends the file, and closes. The board counts
;  what it stored, hashes THE MEMORY (not the wire), and prints the
;  length and the digest. The host compares that digest with the digest
;  of its own file. A transfer that is a byte short, a byte long, or a
;  byte wrong fails that comparison, and nothing is booted until it
;  passes - Anvil's hash-before-jump rule, one layer earlier.
;
;  THE HASH IS OVER MEMORY AND NOT OVER THE STREAM. Hashing the bytes as
;  they come off the ring would prove that the wire delivered them; it
;  would not prove that they are in the DRAM the payload is about to be
;  entered from. Those are different claims and the second one is the one
;  worth having. It costs a second pass over the range, and the cost is
;  printed rather than hidden - see THE HASH IS THE SLOW PART below.
;
;  ----------------------------------------------------------------------
;  THE LISTENER IS OFF UNLESS SOMEBODY ARMS IT, AND IT SERVES ONE CALLER
;  ----------------------------------------------------------------------
;  Nothing in this file runs unless `net recv` is typed. The socket is
;  put into LISTEN for exactly one connection and TAKEN BACK OUT again
;  when that connection ends, whatever way it ended - TcpUnlisten() in
;  tcp.pi4 exists for that and for nothing else, because a passive open
;  re-arms itself on close by design and a bootloader that is quietly
;  accepting images on a port for the rest of its uptime is a different
;  program from the one that was asked for.
;
;  ----------------------------------------------------------------------
;  THE CEILING IS DECIDED BEFORE A BYTE ARRIVES, AND ENFORCED PER BYTE
;  ----------------------------------------------------------------------
;  The length of the file is not known until the peer closes, so "check
;  the range, then receive" is not available. Instead the command settles
;  a LAST WRITABLE ADDRESS up front - the end of the payload window the
;  start address is in, or a smaller limit the operator gave - and the
;  receive loop never writes past it. When a peer sends more than that,
;  the transfer STOPS AT THE CEILING, the connection is reset, and the
;  refusal says how many bytes were stored and where the ceiling was.
;  Nothing outside the window is ever written, not even by one byte.
;
;  The three questions asked before arming are the same three the `b`
;  command asks, in the same order, with the same wording:
;    * does the range run over the monitor itself   (HitsMonitor)
;    * is it inside a payload window                (InPayload)
;    * does this board say the range can be written (AddrAllowed)
;
;  ----------------------------------------------------------------------
;  THE HASH IS THE SLOW PART, AND THE CACHES DECIDE BY HOW MUCH
;  ----------------------------------------------------------------------
;  SHA-256 in this tree measures 61 KB/s on this part with the caches OFF
;  and 4,041 KB/s with them ON - a factor of sixty-six, and it is
;  instruction fetch, not the algorithm. With the caches off the digest
;  of a 1.4 MB image takes longer than receiving it did. So the command
;  prints the two times separately and, when the caches are off, says so
;  in one sentence rather than letting the total look like a network
;  number. `cache on` is safe while the radio is carrying traffic - the
;  framebuffer and the GENET ring are mapped non-cacheable and the
;  mailbox and DMA engine clean their own buffers, which is what
;  CmdCache's own text says.
;
;  ----------------------------------------------------------------------
;  WHAT IS NOT HERE, AND WHY
;  ----------------------------------------------------------------------
;  THERE IS NO "STRAIGHT ONTO THE CARD" MODE. Writing a received image to
;  a named file is `save <name> <address> <length>`, which already owns
;  the create-or-resize decision, the write gate, the medium refusals and
;  seven exit paths' worth of wording. A second copy of that inside this
;  file would be the two-copies-that-drift shape this tree refuses, and
;  it would also make this receiver impossible to grade without a storage
;  model. tools/pi4_upload.py --to card is `net recv` followed by `save`,
;  which is one extra console line and no second implementation.
; ======================================================================

; How long the listener waits for somebody to connect, and how long an
; open connection may stay silent before it is given up on. Both are
; interruptible by a keypress, so neither is a way to lose the prompt.
#NR_ARM_MS  = 60000
#NR_IDLE_MS = 15000

; The states. NetRecvStep() returns one of these every call and the
; command reads the terminal one; the numbers are stable because
; tools/a64/a64_tcp_check.py grades them.
#NR_IDLE = 0          ; nothing armed
#NR_WAIT = 1          ; listening, nobody has connected
#NR_RECV = 2          ; connected and streaming
#NR_DONE = 3          ; the peer closed and everything it sent is stored
#NR_OVER = 4          ; the peer sent past the ceiling; stopped at it
#NR_STOP = 5          ; a keypress
#NR_TIME = 6          ; nothing arrived inside the window
#NR_RST  = 7          ; the peer reset the connection
#NR_BUSY = 8          ; no socket was free
#NR_PORT = 9          ; the port was refused

Global gNrState.i
Global gNrPort.i
Global gNrSock.i
Global gNrBase.i               ; the first byte's address
Global gNrCeil.i               ; the LAST address this transfer may write
Global gNrNext.i               ; where the next byte goes
Global gNrCount.i              ; how many bytes are stored
Global gNrT0.i                 ; millis() when the connection opened
Global gNrT1.i                 ; millis() when it closed
Global gNrLast.i               ; millis() of the last byte, for the idle timer
Global gNrArm.i                ; millis() when the listener was armed
Global gNrHashMs.i
Global gNrPeer.i               ; the peer's address, kept for the report
Global Dim gNrDigest.a[32]

; ----------------------------------------------------------------------
;  The accessors. They exist so that a gate can read the outcome without
;  parsing printed text, and so that nothing outside this file has to
;  know the names of the globals above.
; ----------------------------------------------------------------------
Procedure.i NetRecvState()
  ProcedureReturn gNrState
EndProcedure

Procedure.i NetRecvCount()
  ProcedureReturn gNrCount
EndProcedure

Procedure.i NetRecvBase()
  ProcedureReturn gNrBase
EndProcedure

Procedure.i NetRecvCeil()
  ProcedureReturn gNrCeil
EndProcedure

Procedure.i NetRecvDigest()
  ProcedureReturn @gNrDigest[0]
EndProcedure

Procedure.i NetRecvMs()
  ProcedureReturn gNrT1 - gNrT0
EndProcedure

Procedure.i NetRecvHashMs()
  ProcedureReturn gNrHashMs
EndProcedure

Procedure.i NetRecvPeer()
  ProcedureReturn gNrPeer
EndProcedure

; WHICH SOCKET THIS TRANSFER IS ON, or -1 between transfers. Nothing in
; the monitor needs it; tools/a64/a64_tcp_check.py does, because the
; frames its scripted peer sends have to carry the port and the
; acknowledgment THIS socket chose, and the harness has to select it to
; read those two out. -1 rather than 0 so "no socket" cannot be mistaken
; for socket zero.
Procedure.i NetRecvSock()
  ProcedureReturn gNrSock
EndProcedure

; ----------------------------------------------------------------------
;  NetRecvRelease - put the socket back and take the passive open away.
;
;  Called on EVERY exit, including the refusals, because a listener left
;  armed after a refused transfer is the one thing this command must
;  never leave behind.
; ----------------------------------------------------------------------
Procedure NetRecvRelease()
  Define keep.i
  Define orderly.i
  If gNrSock < 0
    ProcedureReturn
  EndIf
  keep = TcpCurrent()
  TcpUse(gNrSock)
  TcpUnlisten()
  ; A successful receive has already answered the peer's FIN with our own
  ; orderly FIN. LAST_ACK remains owned by the ordinary multi-socket TCP
  ; service until the peer ACKs it or the existing retransmission bound
  ; expires. Only that exact successful terminal is exempt from abort.
  orderly = Bool(gNrState = #NR_DONE And TcpState() = #TCP_LAST_ACK)
  If orderly = 0
    If TcpState() <> #TCP_CLOSED And TcpState() <> #TCP_TIME_WAIT
      TcpAbort()
      TcpUnlisten()
    EndIf
  EndIf
  TcpUse(keep)
  gNrSock = -1
EndProcedure

; ----------------------------------------------------------------------
;  NetRecvArm(port, addr, ceil) - take a socket and listen on it.
;
;  `ceil` is the LAST address this transfer may write, inclusive. The
;  caller has already decided it and has already had every refusal about
;  it; this procedure trusts it and only enforces it.
; ----------------------------------------------------------------------
Procedure.i NetRecvArm(port.i, addr.i, ceil.i)
  Define s.i
  Define rc.i

  gNrState = #NR_IDLE
  gNrSock = -1
  gNrPort = port
  gNrBase = addr
  gNrCeil = ceil
  gNrNext = addr
  gNrCount = 0
  gNrT0 = 0
  gNrT1 = 0
  gNrHashMs = 0
  gNrPeer = 0

  s = TcpAlloc()
  If s < 0
    gNrState = #NR_BUSY
    ProcedureReturn gNrState
  EndIf
  TcpUse(s)
  rc = TcpListen(port)
  If rc <> #NET_TCP_OK
    TcpUnlisten()
    gNrState = #NR_PORT
    ProcedureReturn gNrState
  EndIf
  gNrSock = s
  gNrArm = millis()
  gNrLast = gNrArm
  gNrState = #NR_WAIT
  ProcedureReturn gNrState
EndProcedure

; ----------------------------------------------------------------------
;  NetRecvDrain - move whatever is in the receive ring into the window.
;
;  Returns how many bytes it stored. Sets #NR_OVER and returns -1 when
;  the peer has sent past the ceiling; in that case everything up to and
;  including the ceiling HAS been stored and nothing beyond it has.
;
;  TcpRead writes straight into the destination, so there is one copy
;  from the socket ring into DRAM and not two. On a board with the caches
;  off that difference is worth having.
; ----------------------------------------------------------------------
Procedure.i NetRecvDrain()
  Define avail.i
  Define room.i
  Define want.i
  Define got.i

  avail = TcpAvailable()
  If avail <= 0
    ProcedureReturn 0
  EndIf

  room = gNrCeil - gNrNext + 1
  If room <= 0
    gNrState = #NR_OVER
    ProcedureReturn -1
  EndIf

  want = avail
  If want > room
    want = room
  EndIf
  got = TcpRead(gNrNext, want)
  If got > 0
    gNrNext = gNrNext + got
    gNrCount = gNrCount + got
    gNrLast = millis()
  EndIf

  ; MORE WAS WAITING THAN THE WINDOW HAD ROOM FOR. Everything that fits
  ; is now stored and the rest is still in the ring, unread; the caller
  ; stops here rather than reading it, so the ceiling is the last byte
  ; this transfer ever touched.
  If avail > got
    gNrState = #NR_OVER
    ProcedureReturn -1
  EndIf
  ProcedureReturn got
EndProcedure

; ----------------------------------------------------------------------
;  NetRecvStep - one pump. Returns the state.
;
;  TcpPoll may process a bounded batch before returning. The peer can
;  therefore finish its handshake, data and FIN before this consumer ever
;  observes ESTABLISHED. CLOSE_WAIT still owns that accepted byte stream.
;  The slice is zero because this caller has no reason to wait deliberately.
; ----------------------------------------------------------------------
Procedure.i NetRecvStep()
  Define st.i
  Define keep.i

  If gNrState <> #NR_WAIT
    If gNrState <> #NR_RECV
      ProcedureReturn gNrState
    EndIf
  EndIf

  keep = TcpCurrent()
  TcpUse(gNrSock)
  st = TcpPoll(0)

  If gNrState = #NR_WAIT
    If st = #TCP_ESTABLISHED Or st = #TCP_CLOSE_WAIT
      gNrState = #NR_RECV
      gNrT0 = millis()
      gNrLast = gNrT0
      gNrPeer = TcpPeerIp()
    ElseIf (millis() - gNrArm) > #NR_ARM_MS
      gNrState = #NR_TIME
      TcpUse(keep)
      ProcedureReturn gNrState
    Else
      TcpUse(keep)
      ProcedureReturn gNrState
    EndIf
  EndIf

  ; From here the connection is, or has been, open.
  If NetRecvDrain() < 0
    TcpUse(keep)
    ProcedureReturn gNrState                ; #NR_OVER
  EndIf

  If TcpWasReset() <> 0
    gNrT1 = millis()
    gNrState = #NR_RST
    TcpUse(keep)
    ProcedureReturn gNrState
  EndIf

  ; THE PEER'S FIN IS THE END-OF-FILE MARKER. CLOSE-WAIT means it has
  ; sent everything it means to send; the ring is drained above, so when
  ; nothing is left the transfer is complete. CLOSED can also be reached
  ; directly if the whole exchange fitted in one poll.
  st = TcpState()
  If st = #TCP_CLOSE_WAIT Or st = #TCP_CLOSED Or st = #TCP_LAST_ACK
    If TcpAvailable() = 0
      ; The peer FIN is the file delimiter, but it does not make an abortive
      ; local close correct. Revoke the one-shot listener before queueing our
      ; FIN so the later LAST_ACK completion frees rather than re-listens.
      If st = #TCP_CLOSE_WAIT
        TcpUnlisten()
        TcpClose()
      EndIf
      gNrT1 = millis()
      gNrState = #NR_DONE
      TcpUse(keep)
      ProcedureReturn gNrState
    EndIf
  EndIf

  If (millis() - gNrLast) > #NR_IDLE_MS
    gNrT1 = millis()
    gNrState = #NR_TIME
  EndIf

  TcpUse(keep)
  ProcedureReturn gNrState
EndProcedure

; ----------------------------------------------------------------------
;  NetRecvHash - SHA-256 over what is in the window, and how long it took.
;
;  Separate from the receive so the two times can be reported separately
;  and so a gate can grade one without paying for the other.
; ----------------------------------------------------------------------
Procedure NetRecvHash()
  Define t.i
  t = millis()
  Sha256Of(gNrBase, gNrCount, @gNrDigest[0])
  gNrHashMs = millis() - t
EndProcedure
