; ======================================================================
;  net recv - the console wiring over Anvil/Core/netrecv.pbi.
;
;      net recv <port> <address> [max-length]
;
;  CORE. It names no chip. Everything about the wire, the ceiling and the
;  digest is in netrecv.pi4, which is included ahead of this file and has
;  no console in it at all - read that file's header for the protocol and
;  for why the split exists. What is here is the argument parsing, the
;  three range refusals, the loop that runs the transfer with a keypress
;  able to stop it, and every printed sentence.
;
;  THE REFUSALS ARE A PROCEDURE OF THEIR OWN, NetRecvPlaceRefused, so
;  that tools/a64/a64_anvil_check.py can execute them in the real built
;  image and read the sentences back. A refusal with an empty sentence
;  refuses just as correctly and tells nobody anything, and this monitor
;  has been caught printing one before.
;
;  Gated on #CAP_NET through RequireCap, like ping, dns, dhcp and tcp, so
;  this same line compiles and dispatches on a board with no network and
;  degrades there to the honest "not available" refusal.
; ======================================================================

; ----------------------------------------------------------------------
;  NetRecvPutDigest - the digest, lowercase, the way sha256sum prints it.
; ----------------------------------------------------------------------
Procedure NetRecvPutDigest()
  Define i.i
  i = 0
  While i < 32
    PutHexLower2(gNrDigest[i] & $FF)
    i = i + 1
  Wend
EndProcedure

; ======================================================================
;  NetRecvPlaceRefused(addr, len) - the three range questions, asked and
;  answered out loud. 1 means refused and nothing was armed.
;
;  IT IS A PROCEDURE OF ITS OWN so that tools/a64/a64_anvil_check.py can
;  execute it in the real built image and read the sentence back, which
;  is the only way to prove that a refusal actually NAMES the thing it
;  refused. A refusal with an empty sentence refuses just as correctly
;  and tells nobody anything.
; ======================================================================
Procedure.i NetRecvPlaceRefused(addr.i, len.i)
  Define hi.i

  If len <= 0
    PrintN("!! a window of zero bytes could not hold anything, so nothing was")
    PrintN("   armed and no port was opened.")
    ProcedureReturn 1
  EndIf

  ; hi is the last byte that could be written. Computed BEFORE the window
  ; test and checked for going backwards, because a length that wraps a
  ; 64-bit add produces a small hi that looks like it is inside the low
  ; window. Same guard, same reason, as the b command.
  hi = addr + len - 1
  If hi < addr
    PrintN("!! the address plus the length runs off the end of a 64-bit number, so")
    PrintN("   the last byte would land at a lower address than the first one. One")
    PrintN("   of the two is wrong. Nothing was armed and no port was opened.")
    ProcedureReturn 1
  EndIf

  If HitsMonitor(addr, hi) <> 0
    Print("!! that range runs over the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". Receiving there would overwrite the running")
    PrintN("   monitor and take this prompt and this connection with it, so nothing")
    PrintN("   was armed and no port was opened.")
    Print("   Send the image to ")
    PutAddr(HwStageAddr())
    PrintN(" for the low window, or to")
    Print("   ")
    PutAddr(HwPayLo(1))
    PrintN(" for the high one.")
    ProcedureReturn 1
  EndIf

  If InPayload(addr, hi) = 0
    Print("!! the range ")
    PutAddr(addr)
    Print(" to ")
    PutAddr(hi)
    PrintN(" is not inside either payload")
    PrintN("   window, so nothing was armed and no port was opened. There is DRAM")
    PrintN("   the monitor will not hand out, and a gap in the middle where there")
    PrintN("   is no DRAM at all; a range may not straddle that gap. These are the")
    PrintN("   two you may use:")
    PutWindows()
    ProcedureReturn 1
  EndIf

  If AddrAllowed(addr, hi, 1, "net recv", "nothing was armed and no port was opened") = 0
    ProcedureReturn 1
  EndIf

  ProcedureReturn 0
EndProcedure

; ======================================================================
;  CmdNetRecv - the console wiring. `net recv` has already been eaten.
; ======================================================================
Procedure CmdNetRecv()
  Define portStr.i
  Define port.i
  Define addr.i
  Define want.i
  Define ceil.i
  Define top.i
  Define i.i
  Define st.i
  Define ms.i
  Define rate.i
  Define kind.i

  If RequireCap(#CAP_NET, "net recv", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf

  ; ---- the port -------------------------------------------------------
  portStr = ArgWord()
  If portStr = 0
    PrintN("!! net recv needs a port to listen on and an address to write to, and")
    PrintN("   neither was given, so nothing was armed and no port was opened.")
    PrintN("   net recv <port> <address> [max-length]")
    PrintN("   The port is decimal; the address and the length are hexadecimal.")
    Print("   net recv 5001 ")
    PutAddr(HwStageAddr())
    PrintN(" receives an image into the low payload")
    PrintN("   window, which is where a new Anvil goes before save writes it to")
    PrintN("   the card.")
    ProcedureReturn
  EndIf
  port = 0
  i = 0
  While PeekA(portStr + i) <> 0
    If PeekA(portStr + i) < 48 Or PeekA(portStr + i) > 57
      PrintN("!! that port is not a number, so nothing was armed and no port was")
      PrintN("   opened. A port is 1 to 65535 in plain decimal.")
      ProcedureReturn
    EndIf
    port = port * 10 + (PeekA(portStr + i) - 48)
    If port > 65535
      PrintN("!! that port is above 65535, so nothing was armed and no port was")
      PrintN("   opened.")
      ProcedureReturn
    EndIf
    i = i + 1
  Wend
  If port < 1
    PrintN("!! a port must be at least 1, so nothing was armed and no port was")
    PrintN("   opened.")
    ProcedureReturn
  EndIf

  ; ---- the address, and an optional smaller ceiling -------------------
  addr = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was armed and no port was")
      PrintN("   opened.")
      ProcedureReturn
    EndIf
    PrintN("!! net recv needs the address to write the image to, in hexadecimal,")
    PrintN("   and none was given, so nothing was armed and no port was opened.")
    PrintN("   net recv <port> <address> [max-length]")
    ProcedureReturn
  EndIf

  ; PayloadTop() answers the last address of the window `addr` is in, and
  ; it is the same procedure the loaders use, so this ceiling and their
  ; refusals can never disagree. A start address in neither window gets 0
  ; back and is caught by NetRecvPlaceRefused a few lines below, which is
  ; where that refusal is worded.
  top = PayloadTop(addr)
  want = ParseHex()
  If gParseOk = 0
    If top = 0
      want = 1                       ; refused below, on the real question
    Else
      want = top - addr + 1
    EndIf
  EndIf
  If want > 0 And top <> 0
    If (addr + want - 1) > top
      Print("!! ")
      PrintDec(want)
      PrintN(" bytes from that address would run past the end of the")
      Print("   payload window it is in, which ends at ")
      PutAddr(top)
      PrintN(". Nothing was")
      PrintN("   armed and no port was opened. Leave the length out and the whole")
      PrintN("   rest of the window is used, which is the usual thing to want.")
      ProcedureReturn
    EndIf
  EndIf

  If NetRecvPlaceRefused(addr, want) <> 0
    ProcedureReturn
  EndIf
  ceil = addr + want - 1

  ; A listener is not an outbound-route decision. It is wildcard across
  ; every addressed, live interface; the SYN chooses the endpoint and TCP
  ; pins that exact interface and local destination for the connection.
  If NetIfUsableCount() = 0
    PrintN("!! no addressed network interface can carry a frame, so nothing was")
    PrintN("   armed and no port was opened. The net report shows each interface")
    PrintN("   and its DHCP/link state.")
    ProcedureReturn
  EndIf

  ; ---- arm ------------------------------------------------------------
  st = NetRecvArm(port, addr, ceil)
  If st = #NR_BUSY
    PrintN("!! every socket is in use, so nothing was armed and no port was")
    PrintN("   opened. tcp status lists them; tcp close frees one, and a socket in")
    PrintN("   TIME-WAIT frees itself after four minutes.")
    ProcedureReturn
  EndIf
  If st <> #NR_WAIT
    Print("!! port ")
    PrintDec(port)
    PrintN(" was refused, so nothing was armed. Another socket is")
    PrintN("   already listening on it, or it is outside 1 to 65535.")
    NetRecvRelease()
    ProcedureReturn
  EndIf

  Print("Listening on port ")
  PrintDec(port)
  PrintN(" on every usable addressed interface for ONE connection:")
  kind = NetIfNext(#HW_LINK_NONE)
  While kind <> #HW_LINK_NONE
    Print("    ")
    UartWriteStr(HwLinkName(kind))
    Print(" at ")
    PutIp(NetIPv4(kind))
    If NetIPv4Alt(kind) <> 0
      Print(" (also ")
      PutIp(NetIPv4Alt(kind))
      Print(")")
    EndIf
    PrintNl()
    kind = NetIfNext(kind)
  Wend
  Print("  Everything it sends goes to ")
  PutAddr(addr)
  Print(" and the last byte it may")
  PrintNl()
  Print("  write is ")
  PutAddr(ceil)
  Print(", which is ")
  PrintDec(want)
  PrintN(" bytes.")
  PrintN("  Send the file and close the connection; the length and the SHA-256 of")
  PrintN("  what actually landed are printed here when you do. Any key stops it.")
  UartDrain()

  ; ---- run ------------------------------------------------------------
  While 1 = 1
    st = NetRecvStep()
    If st <> #NR_WAIT
      If st <> #NR_RECV
        Break
      EndIf
    EndIf
    If OutBreak() <> 0
      gNrState = #NR_STOP
      st = #NR_STOP
      Break
    EndIf
  Wend

  NetRecvRelease()

  ; ---- the verdict ----------------------------------------------------
  If st = #NR_TIME And gNrCount = 0
    Print("!! nobody connected to port ")
    PrintDec(port)
    PrintN(" inside the waiting window, so nothing")
    PrintN("   was received and nothing in memory was changed. The listener is")
    PrintN("   closed again. Check that the host can reach this board - ping it")
    PrintN("   from there - and that nothing between the two is filtering the port.")
    ProcedureReturn
  EndIf

  If st = #NR_STOP
    Print("  Stopped by a keypress after ")
    PrintDec(gNrCount)
    PrintN(" bytes. The connection was reset")
    PrintN("  and the listener is closed. What did arrive is in memory and is")
    PrintN("  PART OF AN IMAGE, so nothing may be booted from it.")
    ProcedureReturn
  EndIf

  If st = #NR_RST
    Print("!! the peer reset the connection after ")
    PrintDec(gNrCount)
    PrintN(" bytes, so this transfer is")
    PrintN("   INCOMPLETE and what is in memory is part of an image. Nothing may be")
    PrintN("   booted from it. Send it again.")
    ProcedureReturn
  EndIf

  If st = #NR_TIME
    Print("!! the connection went silent after ")
    PrintDec(gNrCount)
    PrintN(" bytes and never closed, so this")
    PrintN("   transfer is INCOMPLETE and what is in memory is part of an image.")
    PrintN("   Nothing may be booted from it. A close is how the end of the file is")
    PrintN("   announced; a host that stops sending without closing looks exactly")
    PrintN("   like a host that has crashed, and this board cannot tell them apart.")
    ProcedureReturn
  EndIf

  If st = #NR_OVER
    Print("!! the peer sent more than ")
    PrintDec(want)
    PrintN(" bytes, which is all the room there is")
    Print("   between ")
    PutAddr(addr)
    Print(" and the end of its payload window at ")
    PutAddr(gNrCeil)
    PrintN(".")
    PrintN("   The transfer STOPPED AT THAT ADDRESS and the connection was reset:")
    PrintN("   not one byte was written past it. What is in memory is the first")
    Print("   ")
    PrintDec(gNrCount)
    PrintN(" bytes of a longer file and nothing may be booted from it.")
    Print("   Send it to the high window at ")
    PutAddr(HwPayLo(1))
    PrintN(" if it really is that big.")
    ProcedureReturn
  EndIf

  ; ---- #NR_DONE -------------------------------------------------------
  ms = NetRecvMs()
  Print("Received ")
  PrintDec(gNrCount)
  Print(" bytes from ")
  PutIp(gNrPeer)
  Print(" to ")
  PutAddr(gNrBase)
  Print(" in ")
  PrintDec(ms)
  PrintN(" ms.")
  If ms > 0
    ; Bytes a second, worked out in whole numbers with the multiply
    ; first, so a 1.4 MB transfer in 4000 ms reads as 350 KB/s and not as
    ; the 0 an integer divide of kilobytes by seconds would produce. That
    ; exact truncation printed "0 KB/s" for a real measurement on this
    ; board on 2026-09-05 and it is not going to do it twice.
    rate = (gNrCount / 1024) * 1000 / ms
    If rate > 0
      Print("  That is ")
      PrintDec(rate)
      PrintN(" KB/s.")
    Else
      rate = gNrCount * 1000 / ms
      Print("  That is ")
      PrintDec(rate)
      PrintN(" bytes a second.")
    EndIf
  EndIf

  NetRecvHash()
  Print("  sha256 ")
  NetRecvPutDigest()
  PrintNl()
  Print("  The digest is of THE MEMORY, taken after the transfer, and it took ")
  PrintDec(gNrHashMs)
  PrintNl()
  PrintN("  ms. Compare it with sha256sum of the file on the host: equal means")
  PrintN("  the bytes in this board's DRAM are the bytes in that file.")
  If gNrHashMs > ms
    PrintN("  THE DIGEST TOOK LONGER THAN THE TRANSFER, and that is instruction")
    PrintN("  fetch rather than the hashing: on a board whose caches are off, every")
    PrintN("  instruction of the inner loop is read from DRAM. If this board has a")
    PrintN("  runtime cache switch, turning it on before the next upload is worth")
    PrintN("  a factor of about sixty here. Type help to see whether it has one.")
  EndIf
  PrintN("  Nothing has been booted and nothing has been written to the medium.")
  Print("  boot mem ")
  PutAddr(gNrBase)
  PrintN(" enters it if it is a container; save <name>")
  Print("  ")
  PutAddr(gNrBase)
  Print(" ")
  PutHexN(gNrCount, 8)
  PrintN(" writes it to the boot medium.")
EndProcedure
