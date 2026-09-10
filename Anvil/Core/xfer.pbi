
; ======================================================================
;  b - receive a raw block. THE FAST PATH.
;
;      b <addr-hex> <len-hex> <crc32-hex>
;
;  The contract this procedure has to honour, restated where the code
;  is:
;
;    * "rdy" is a PROMISE. Nothing is printed between it and the first
;      "+" except the acks themselves, because everything after "rdy" on
;      this wire is the host's binary, and a stray banner byte would be
;      read as an ack that had not happened.
;    * Every refusal happens BEFORE "rdy". If the header is bad the host
;      never starts sending, and the monitor is back at a prompt with
;      nothing in flight.
;    * The verdict is the LAST line, and is exactly "ok" or "crc". Any
;      human detail is printed before it, and is worded to contain
;      neither token, so a host can scan for the verdict without a
;      parser.
;
;  ------------------------------------------------------------------
;  PROTOCOL STRINGS IN THIS PROCEDURE. DO NOT REWORD THEM.
;  Audited against tools/ on 2026-08-26 during the plain-English sweep.
;
;    "rdy"       tools/ubsend.py send_raw()  - compares the whole line
;                with == , and tools/anvil.py block() greps for it.
;                Three letters, no punctuation, on a line of its own.
;    "ok"        tools/ubsend.py send_raw()  - line == "ok" is the
;                success verdict; tools/anvil.py block() and
;                tools/anvil_update.py both grep the WHOLE transcript
;                for the SUBSTRING "ok". That is why no other line on
;                this path may contain the letters o-k in that order -
;                "look", "took" and "broken" are all banned words here,
;                and an innocent rewording of the success detail below
;                would make a failed transfer report success.
;    "crc"       tools/ubsend.py send_raw()  - line == "crc" is the
;                failure verdict, and tools/anvil_update.py treats the
;                SUBSTRING "crc" anywhere in the transcript as failure.
;                Same rule in reverse: the success path must never print
;                the letters c-r-c, which is why the mismatch line says
;                "checksum" and the success line does not name the
;                algorithm at all.
;    "+"         tools/ubsend.py send_raw()  - one byte per chunk, and
;                the host waits for each one before sending the next.
;    "!! "       tools/ubsend.py send_raw()  - a line starting "!!" (or
;                "usage") is how the host knows the header was REFUSED
;                and that it must not start sending the binary. Every
;                refusal below therefore keeps "!!" as its first two
;                characters, however English the rest of it gets.
;    "timed out" tools/anvil.py block()      - one of the substrings it
;                breaks its read loop on, so the timeout line keeps
;                those two words verbatim.
;  ------------------------------------------------------------------
; ======================================================================

Procedure CmdBlock()
  Define addr.i
  Define len.i
  Define want.i
  Define hi.i
  Define i.i
  Define n.i
  Define c.i
  Define crc.i
  Define aborted.i

  addr = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was received.")
    Else
      PrintN("!! receive needs three things and the first of them, the address to")
      PrintN("   write to, is missing or is not hexadecimal. Nothing was received.")
      PrintN("   receive <address> <length> <checksum>, and all three are hex.")
    EndIf
    ProcedureReturn
  EndIf
  len = ParseHex()
  If gParseOk = 0
    PrintN("!! the length is missing or is not hexadecimal, so there is no way to")
    PrintN("   know how many bytes to wait for. Nothing was received.")
    PrintN("   receive <address> <length> <checksum>, and all three are hex.")
    ProcedureReturn
  EndIf
  want = ParseHex()
  If gParseOk = 0
    PrintN("!! the checksum is missing, and it is not optional. The whole reason")
    PrintN("   to use this command instead of srecord is that the board can tell")
    PrintN("   you whether the bytes arrived intact, and it cannot do that without")
    PrintN("   knowing what they should add up to. Nothing was received.")
    PrintN("   receive <address> <length> <checksum>, and all three are hex.")
    ; The algorithm is deliberately NOT named on this line. It is the
    ; IEEE reflected one, polynomial EDB88320, and the host gets it from
    ; Python's zlib - but spelling those three letters here would put
    ; them in a transcript that tools/anvil_update.py greps for them as
    ; its failure verdict. See the protocol note above this procedure.
    ProcedureReturn
  EndIf

  If len <= 0
    PrintN("!! a length of zero bytes would receive nothing, so nothing was")
    PrintN("   received. Give the length of the image in hexadecimal bytes.")
    ProcedureReturn
  EndIf

  ; hi is the last byte written. Computing it BEFORE the window test and
  ; checking it did not go backwards catches a length that wraps a
  ; 64-bit add - which InPayload() alone would then wave through,
  ; because a wrapped hi is a small number and small numbers look like
  ; they are inside the low window.
  hi = addr + len - 1
  If hi < addr
    PrintN("!! the address plus the length runs off the end of a 64-bit number,")
    PrintN("   so the last byte would land at a lower address than the first one.")
    PrintN("   One of the two is wrong. Nothing was received.")
    ProcedureReturn
  EndIf

  If HitsMonitor(addr, hi) <> 0
    Print("!! that range runs over the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". Writing there would overwrite the running monitor and")
    PrintN("   take this prompt with it, so nothing was received.")
    ; DELIBERATELY NOT "rather than 0x200000" ANY MORE. That is what this
    ; said until the monitor's variables moved out of the image window on
    ; 2026-08-28, when there stopped being one address the mistake could
    ; have been. A range at $08200000 hits the DATA window and has
    ; nothing to do with 0x200000, so naming that number would have sent
    ; the reader looking at a build line that was already correct. The
    ; two addresses above name the region actually hit; this line names
    ; where payloads go, which is the same answer for both.
    Print("   Build the payload with --load-addr 0x")
    PutAddr(HwStageAddr())
    PrintN(" for the low window,")
    Print("   or send it to the high window at 0x")
    PutAddr(HwPayLo(1))
    PrintN(".")
    ProcedureReturn
  EndIf

  If InPayload(addr, hi) = 0
    Print("!! the range ")
    PutAddr(addr)
    Print(" to ")
    PutAddr(hi)
    PrintN(" is not inside either payload")
    PrintN("   window, so nothing was received. There is DRAM the monitor will")
    PrintN("   not hand out - U-Boot and the three parked cores are in some of")
    PrintN("   it - and a gap in the middle where there is no DRAM at all. A")
    PrintN("   range may not straddle that gap. These are the two you may use:")
    PutWindows()
    ProcedureReturn
  EndIf

  ; Everything that can be refused has been. From here the host is
  ; entitled to start sending, and the counters describe THIS transfer.
  gRecs = 0
  gBytes = 0
  gBad = 0
  gFail = 0
  gLoLo = addr
  gHiHi = hi
  gEntry = addr
  gHaveEntry = 1

  PrintN("rdy")

  i = 0
  n = 0
  aborted = 0
  While i < len
    c = RxByte()
    If c < 0
      aborted = 1
      Break
    EndIf
    PokeB(addr + i, c)
    i = i + 1
    n = n + 1
    ; Ack a full chunk, and also the short final one, so the host reads
    ; exactly ceil(len / #BLK) acks and does not have to special-case
    ; the tail.
    If n = #BLK Or i = len
      UartWrite(43)             ; "+"
      n = 0
    EndIf
  Wend

  PrintNl()

  If aborted <> 0
    ; A dead wire mid-transfer. Same contract as the S-record loader:
    ; report honestly, leave a live prompt, and block g. The bytes that
    ; DID arrive are still in memory - deliberately, because dumping
    ; them with m is often how you find out where the host stopped.
    ; "timed out" IS PARSED. tools/anvil.py block() breaks its read loop
    ; on that exact pair of words, so they stay verbatim and stay early
    ; in the line. Everything after them is free prose.
    Print("!! timed out after ")
    PrintDec(i)
    Print(" of ")
    PrintDec(len)
    PrintN(" bytes. The host stopped sending and the")
    PrintN("   image in memory is only part of a file. The bytes that did arrive")
    PrintN("   have been left where they are, because dumping them with memory is")
    PrintN("   often how you find out where the host gave up.")
    gFail = 1
    gBytes = i
    gHaveEntry = 0
    PrintN("!! run is blocked until an image loads cleanly. Send it again.")
    ProcedureReturn
  EndIf

  gBytes = len
  gRecs = 1

  crc = Crc32(addr, len)
  If crc <> want
    ; Detail first, verdict last, and this line deliberately says
    ; "checksum" rather than naming the algorithm, so that a host
    ; scanning the stream for the verdict token cannot match it here.
    Print("!! all ")
    PrintDec(len)
    PrintN(" bytes arrived, but they are not the right bytes. The")
    Print("   board added them up to ")
    PutHex8(crc)
    Print(" and the header said they would come")
    PrintNl()
    Print("   to ")
    PutHex8(want)
    PrintN(". Something on the wire changed them in flight.")
    PrintN("!! what is in memory is NOT what the host sent, so run is blocked")
    PrintN("   until an image loads cleanly. Send it again; if it fails a second")
    PrintN("   time, drop the baud rate back to 115200 and try once more.")
    gBad = 1
    gHaveEntry = 0
    PrintN("crc")
    ProcedureReturn
  EndIf

  CacheFlushRange(gLoLo, gHiHi)

  ; THE SUCCESS DETAIL. Every word here was chosen to avoid the letters
  ; o-k and c-r-c, because two host tools grep the whole transcript for
  ; those as substrings. See the protocol note above this procedure
  ; before rewording a single line of it.
  Print("Received all ")
  PrintDec(len)
  PrintN(" bytes and the checksum agreed, so what is in")
  PrintN("memory is exactly what the host sent.")
  Print("  The image lies at ")
  PutAddr(gLoLo)
  Print(" through ")
  PutAddr(gHiHi)
  PrintN(",")
  Print("  and its entry point is ")
  PutAddr(gEntry)
  PrintN(", which is where run will jump")
  PrintN("  if you type run with no address of your own.")
  PrintN("ok")
EndProcedure

; ======================================================================
;  wb - RECEIVE AN IMAGE OVER WI-FI. The wireless twin of b.
; ======================================================================
;
;  #ANVIL_WIFI_OTA compiles in the `wb` command, which takes a new image
;  over the air instead of down the serial line - so the FTDI cable is
;  free for something else and a board with no serial attached can still
;  be reflashed. It rides the wireless console's own port and peer, so it
;  needs the radio: a target that drops wifi.pi4 sets this to 0 and the
;  command, with its use of NetConsolePollUdp / NetConsoleSendPeer, compiles out.
;
;      pmf> wb <addr-hex> <len-hex> <crc32-hex>
;      board:  rdy
;      host:   datagrams, each [4-byte LE offset][payload], to port 5555
;      board:  a 4-byte LE echo of the offset after each one it stored
;      host:   one datagram whose offset field is four $FF bytes - the end
;      board:  4 bytes - $F0F0F0F0 if the whole-image CRC agreed,
;              $E1E1E1E1 if it did not
;
;  SAME CONTRACT AS b, A DIFFERENT WIRE. The bytes land in the same DRAM
;  window, the CRC is read back out of memory the same way, and gEntry is
;  set the same way - so save, run and crc32 cannot tell a wireless image
;  from a serial one. Only the transport is new, which is why the file it
;  writes (save) and the reset into it stay the plain existing commands.
;
;  STOP-AND-WAIT, DELIBERATELY. The board echoes each datagram's offset
;  before the host sends the next, so the host cannot outrun the SDIO
;  receive path and drop frames, and a lost datagram is just an ack the
;  host waited for and did not get - it resends, and the offset makes the
;  rewrite land in the same place. It is not fast, and does not need to
;  be: it replaces a sixty-second serial save, and correctness is the
;  point of a thing that overwrites the file the board boots from.
;
;  THE RESULT WORDS ARE NOT o-k / c-r-c. The host reads a 4-byte code,
;  not text, so those letters are free in the human line that follows -
;  but they stay off the wire, the same care CmdBlock takes.
#ANVIL_WIFI_OTA = 1

CompilerIf #ANVIL_WIFI_OTA = 1

#OTA_OK  = $F0F0F0F0          ; board -> host: received and verified
#OTA_BAD = $E1E1E1E1          ; board -> host: received but CRC disagreed

Global Dim gOtaMsg.a[4]       ; the 4-byte reply is built here

; Put a 4-byte little-endian word on the wire to the current peer. The
; byte masks make the constant's 32-vs-64-bit sign irrelevant: only the
; low four bytes are ever sent.
Procedure ota_Reply(word.i)
  PokeB(@gOtaMsg[0], word & $FF)
  PokeB(@gOtaMsg[1], (word >> 8) & $FF)
  PokeB(@gOtaMsg[2], (word >> 16) & $FF)
  PokeB(@gOtaMsg[3], (word >> 24) & $FF)
  NetConsoleSendPeer(@gOtaMsg[0], 4)
EndProcedure
CompilerEndIf

Procedure CmdWirelessBlock()
  CompilerIf #ANVIL_WIFI_OTA = 1
  Define addr.i
  Define len.i
  Define want.i
  Define hi.i
  Define plen.i
  Define off.i
  Define dlen.i
  Define pd.i
  Define i.i
  Define crc.i
  Define aborted.i

  addr = ParseHex()
  If gParseOk = 0
    PrintN("!! wb needs an address, a length and a checksum, all hex, and the")
    PrintN("   address is missing. wb <address> <length> <checksum>. Nothing was received.")
    ProcedureReturn
  EndIf
  len = ParseHex()
  If gParseOk = 0
    PrintN("!! the length is missing or is not hexadecimal, so there is no way to")
    PrintN("   know how big the image is. Nothing was received.")
    ProcedureReturn
  EndIf
  want = ParseHex()
  If gParseOk = 0
    PrintN("!! the checksum is missing, and the board needs it to tell you whether")
    PrintN("   the image arrived intact. Nothing was received.")
    ProcedureReturn
  EndIf

  If len <= 0
    PrintN("!! a length of zero would receive nothing. Give the image length in")
    PrintN("   hexadecimal bytes.")
    ProcedureReturn
  EndIf

  hi = addr + len - 1
  If hi < addr
    PrintN("!! the address plus the length runs off the end of a 64-bit number.")
    PrintN("   One of the two is wrong. Nothing was received.")
    ProcedureReturn
  EndIf

  If HitsMonitor(addr, hi) <> 0
    Print("!! that range runs over the monitor itself, at ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(".")
    PrintN("   Writing there would take this prompt with it. Nothing was received.")
    Print("   Send it to the payload window at 0x")
    PutAddr(HwStageAddr())
    PrintN(" instead.")
    ProcedureReturn
  EndIf

  If InPayload(addr, hi) = 0
    Print("!! the range ")
    PutAddr(addr)
    Print(" to ")
    PutAddr(hi)
    PrintN(" is not inside a payload window,")
    PrintN("   so nothing was received. These are the two you may use:")
    PutWindows()
    ProcedureReturn
  EndIf

  ; The link must be up with a peer, or there is no one to receive from.
  ; wb only ever arrives over the air, so the peer is whoever sent it.
  If NetConsoleOn() = 0 Or NetConsolePeerOk() = 0
    PrintN("!! the wireless console has no peer, so wb has nowhere to receive")
    PrintN("   from. This command is meant to arrive over the air itself.")
    ProcedureReturn
  EndIf

  ; Everything refusable has been refused. The counters describe THIS one.
  gRecs = 0
  gBytes = 0
  gBad = 0
  gFail = 0
  gLoLo = addr
  gHiHi = hi
  gEntry = addr
  gHaveEntry = 1

  ; "rdy" is the promise, exactly as b makes it. Push it to the peer now,
  ; before the wait, so the host knows to start sending.
  PrintN("rdy")
  NetConsoleFlush()

  aborted = 0
  Repeat
    plen = NetConsolePollUdp(4000)
    If plen < 0
      aborted = 1                     ; the host went quiet mid-transfer
      Break
    EndIf
    If plen < 4
      Continue                        ; too short to carry an offset; ignore
    EndIf
    pd = NetUdpRxData()
    ; The end marker is four $FF bytes in the offset field - tested byte by
    ; byte so no 32-vs-64-bit sign question can turn a real end into a miss.
    If PeekA(pd) = $FF And PeekA(pd + 1) = $FF And PeekA(pd + 2) = $FF And PeekA(pd + 3) = $FF
      Break
    EndIf
    off = PeekA(pd) | (PeekA(pd + 1) << 8) | (PeekA(pd + 2) << 16) | (PeekA(pd + 3) << 24)
    dlen = plen - 4
    ; A chunk that would land outside the declared image is a protocol
    ; fault, not something to clamp and carry on from - stop and report.
    If off + dlen > len
      aborted = 1
      Break
    EndIf
    i = 0
    While i < dlen
      PokeB(addr + off + i, PeekA(pd + 4 + i))
      i = i + 1
    Wend
    ota_Reply(off)                    ; ack: the offset just stored
  ForEver

  PrintNl()

  If aborted <> 0
    PrintN("!! the over-the-air transfer stopped before the end marker. What")
    PrintN("   arrived is only part of an image, so run is blocked until one")
    PrintN("   loads cleanly. Send it again.")
    gFail = 1
    gHaveEntry = 0
    ProcedureReturn
  EndIf

  gBytes = len
  gRecs = 1

  crc = Crc32(addr, len)
  If crc <> want
    ota_Reply(#OTA_BAD)
    Print("!! all ")
    PrintDec(len)
    PrintN(" bytes arrived but the checksum disagreed - the")
    Print("   board made them ")
    PutHex8(crc)
    Print(" and the header said ")
    PutHex8(want)
    PrintN(".")
    PrintN("   What is in memory is not what the host sent, so run is blocked.")
    gBad = 1
    gHaveEntry = 0
    ProcedureReturn
  EndIf

  CacheFlushRange(gLoLo, gHiHi)
  ota_Reply(#OTA_OK)

  Print("Received all ")
  PrintDec(len)
  PrintN(" bytes over the air and the checksum agreed.")
  Print("  The image lies at ")
  PutAddr(gLoLo)
  Print(" through ")
  PutAddr(gHiHi)
  PrintN(".")
  PrintN("  save it to the boot file and reset, or run it where it sits.")
  CompilerElse
  PrintN("!! this build has the over-the-air update compiled out (#ANVIL_WIFI_OTA = 0).")
  PrintN("   Reflash over the serial line with b, or rebuild with the radio included.")
  CompilerEndIf
EndProcedure

; ======================================================================
;  l - receive S-records. THE PROVEN PATH, kept.
; ======================================================================

Procedure.i SrecByte()
  ; Two hex digits, or -1 for a timeout or a non-hex character.
  Define a.i
  Define b.i
  a = RxByte()
  If a < 0
    ProcedureReturn -1
  EndIf
  b = RxByte()
  If b < 0
    ProcedureReturn -1
  EndIf
  a = HexVal(a)
  b = HexVal(b)
  If a < 0 Or b < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn (a << 4) | b
EndProcedure

Procedure SrecLoad()
  Define c.i
  Define t.i
  Define cnt.i
  Define sum.i
  Define chk.i
  Define i.i
  Define b.i
  Define addr.i
  Define dlen.i
  Define done.i
  Define aborted.i
  Define ignored.i
  Define inmon.i

  gRecs = 0
  gBytes = 0
  gBad = 0
  gFail = 0
  gLoLo = 0
  gHiHi = 0
  gEntry = 0
  gHaveEntry = 0
  done = 0
  aborted = 0
  ignored = 0
  inmon = 0

  ; This used to be U-Boot's own "## Ready for S-Record download ..." on
  ; the theory that a matching vocabulary helped. Nothing in tools/ parses
  ; it - checked on 2026-08-26 - and a person reading the log is better
  ; served by being told what to do next and when it will give up.
  PrintN("Ready for the S-record stream. Send it now. Two seconds of silence")
  PrintN("ends the transfer, and Escape or Ctrl-C abandons it.")

  Repeat
    ; --- resynchronise on the next record ---------------------------
    c = RxByte()
    If c < 0
      aborted = 1
      Break
    EndIf
    If c = 27 Or c = 3
      aborted = 2
      Break
    EndIf

    If c = 83 Or c = 115                    ; S or s
      t = RxByte()
      cnt = SrecByte()
      If t < 0 Or cnt < 0
        gBad = gBad + 1
      Else
        t = t - 48                          ; the record type digit
        sum = cnt
        chk = 0
        b = 0
        i = 0
        ; cnt counts the address bytes, the data AND the checksum, so
        ; the body is cnt-1 bytes. Nothing is written to memory here -
        ; the record is held in gRec until its checksum proves it.
        While i < cnt - 1
          b = SrecByte()
          If b < 0
            Break
          EndIf
          If i < #REC_MAX
            gRec[i] = b
          EndIf
          sum = sum + b
          i = i + 1
        Wend
        If b < 0
          gBad = gBad + 1
        Else
          chk = SrecByte()
          If chk < 0
            gBad = gBad + 1
          ElseIf ((sum + chk) & $FF) <> $FF
            ; ones complement: count + address + data + checksum must
            ; sum to $FF in the low byte.
            gBad = gBad + 1
          ElseIf (t = 3 Or t = 7) And cnt >= 5
            ; Both carry a 32-bit big-endian address. THIRTY-TWO BITS IS
            ; THE FORMAT'S LIMIT, NOT OURS - an S3 record has a four-byte
            ; address field and that is what S3 means. It is also not a
            ; limit that bites on this board: all 4 GiB of a Pi 4's DRAM
            ; is below $100000000, high window included. It bites on an
            ; 8 GiB Pi 4. Use b there.
            addr = ((gRec[0] & $FF) << 24) | ((gRec[1] & $FF) << 16)
            addr = addr | ((gRec[2] & $FF) << 8) | (gRec[3] & $FF)
            ; That reassembly is unsigned without anyone arranging it:
            ; each masked byte is a small positive .i, the shifts happen
            ; in a 64-bit register, and $FFFFFFFF is the largest value
            ; it can produce. So an S3 record aimed at the high window
            ; is accepted rather than arriving negative and failing the
            ; range test for the wrong reason.
            dlen = cnt - 5
            If t = 7
              gEntry = addr
              gHaveEntry = 1
              done = 1
            ElseIf dlen <= 0
              ignored = ignored + 1
            ElseIf HitsMonitor(addr, addr + dlen - 1) <> 0
              ; Counted separately so the report can say WHICH mistake
              ; it was. This is the case that was proven on silicon: a
              ; record aimed at $00200400 was refused and the monitor's
              ; own instructions were left intact.
              inmon = inmon + 1
              gBad = gBad + 1
            ElseIf InPayload(addr, addr + dlen - 1) = 0
              gBad = gBad + 1
            Else
              For i = 0 To dlen - 1
                PokeB(addr + i, gRec[4 + i] & $FF)
              Next
              If gRecs = 0 Or addr < gLoLo
                gLoLo = addr
              EndIf
              If (addr + dlen - 1) > gHiHi
                gHiHi = addr + dlen - 1
              EndIf
              gRecs = gRecs + 1
              gBytes = gBytes + dlen
            EndIf
          Else
            ; S0 headers, S5/S6 counts, S8/S9 terminators. The checksum
            ; was still verified; the content is not ours to act on.
            ignored = ignored + 1
          EndIf
        EndIf
      EndIf
    EndIf
  Until done <> 0

  ; --- the report ---------------------------------------------------
  If aborted = 1
    PrintN("!! nothing arrived for two seconds, so the transfer was given up on")
    PrintN("   part way through. Whatever the host had sent by then is in memory")
    PrintN("   and the rest of the image is not.")
    gFail = 1
  ElseIf aborted = 2
    PrintN("!! abandoned, because Escape or Ctrl-C was pressed. The records that")
    PrintN("   had already arrived are in memory and the rest of the image is not.")
    gFail = 1
  ElseIf gHaveEntry = 0
    PrintN("!! the stream stopped without an S7 record on the end of it. S7 is")
    PrintN("   what says the image is complete and where its entry point is, so")
    PrintN("   without one there is no way to tell a finished transfer from one")
    PrintN("   that was cut off. Treating this as incomplete.")
    gFail = 1
  EndIf

  Print("Accepted ")
  PrintDec(gRecs)
  Print(" data records, ")
  PrintDec(gBytes)
  Print(" bytes in all")
  If gRecs > 0
    Print(", written to ")
    PutAddr(gLoLo)
    Print(" through ")
    PutAddr(gHiHi)
  EndIf
  PrintN(".")

  If ignored > 0
    Print("  ")
    PrintDec(ignored)
    PrintN(" records carried no data for us - S0 headers, S5 and S6 counts,")
    PrintN("  S8 and S9 terminators. Their checksums were still verified; there")
    PrintN("  was simply nothing in them to write. This is normal and not a fault.")
  EndIf

  If gHaveEntry <> 0
    Print("  The entry point is ")
    PutAddr(gEntry)
    PrintN(", which is where run will jump if you")
    PrintN("  type run with no address of your own.")
  EndIf

  If inmon > 0
    Print("!! ")
    PrintDec(inmon)
    PrintN(" of those records were aimed inside the monitor itself, and")
    ; BOTH REGIONS ARE NAMED HERE, AND ONLY HERE, BECAUSE THIS MESSAGE IS
    ; A SUMMARY. gMonHitLo/gMonHitHi describe the LAST call to
    ; HitsMonitor(), and this line is printed after a whole S-record file
    ; has been walked - the last call in that walk very probably returned
    ; zero, and even if it did not, `inmon` may be counting records that
    ; hit the other region. Reading the pair here would print a region
    ; picked by whichever record happened to come last, which is a number
    ; that looks authoritative and is not. The nine other refusals in
    ; this file each report a single range and are on the instruction
    ; after their own call, which is the contract those globals have.
    PrintN("   were refused. Nothing was written for them. Writing into any of")
    PrintN("   this would overwrite the running monitor and take the prompt with")
    PrintN("   it:")
    ; THE WHOLE REGION LIST, ASKED FOR - 2026-09-08. This used to name
    ; four constants: the image window and the data window. There are
    ; three regions on this board now (the autoboot record left the image
    ; window when the image stopped having a fixed top) and the number is
    ; the board's business, not this file's.
    PutMonitorMap()
    Print("   Build the payload with --load-addr 0x")
    PutAddr(HwStageAddr())
    PrintN(" for the low window.")
  EndIf

  If gBad > 0
    Print("!! ")
    PrintDec(gBad)
    PrintN(" records were rejected. A record is rejected for one of two")
    PrintN("   reasons: its own checksum did not add up, which means the wire")
    PrintN("   changed it in flight, or it was aimed at an address outside both")
    PrintN("   payload windows. Nothing was written for a rejected record.")
    PutWindows()
  EndIf

  If gBad > 0 Or gFail <> 0
    PrintN("!! run is blocked until an image loads cleanly, because a part-loaded")
    PrintN("   image is not a program. Send the whole of it again.")
  ElseIf gRecs > 0
    CacheFlushRange(gLoLo, gHiHi)
    PrintN("The image is complete and its caches have been flushed, so it can be")
    PrintN("run. Type run to start it.")
    PrintN("ok")
  Else
    ; NOT SILENT. A stream that is well formed and carries an S7 but no
    ; data at all used to fall off the end of this If with no verdict
    ; printed - a host waiting for "ok" or "!!" waited for ever, and a
    ; person saw a records line and nothing else. Every path through this
    ; procedure now ends in a sentence.
    PrintN("!! no data records arrived at all, so nothing was written anywhere.")
    PrintN("   The stream was well formed - it ended properly - it simply had no")
    PrintN("   S3 records in it. Check that the host sent the image and not an")
    PrintN("   empty file.")
  EndIf
EndProcedure
