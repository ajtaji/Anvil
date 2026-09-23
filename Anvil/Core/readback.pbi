
; ======================================================================
;  readback <address> <length>  -  GETTING BYTES OFF THIS BOARD
; ======================================================================
;  Written 2026-09-16, from a measurement rather than from a suspicion.
;  Forum topic 839.
;
;  WHAT WAS MEASURED, AND WHAT THE NUMBERS SAID
;  --------------------------------------------
;  Reading 1,812,000 bytes back over the UDP console with `memory` took
;  1,048.04 seconds - 443 chunks of 4096 bytes, 2.365 s each, 1,729
;  bytes a second, over a gigabit cable that carries a TFTP transfer at
;  965 KB/s. Two terms account for 99.7% of it and NEITHER of them is
;  the network:
;
;    1.762 s  the PL011. `memory` spends 78 bytes of hex and ASCII on
;             every 16 bytes of memory - 4.875 times - and every one of
;             those characters goes through UartWrite, which spins on
;             the serial transmit FIFO and only THEN copies the byte
;             into the screen mirror and the network console's tap. At
;             115200 baud that is 11,520 bytes a second for the whole
;             machine. 20,300 characters a chunk / 11,520 = 1.762 s.
;    0.600 s  the host tool settling the console for 0.6 s of quiet
;             before each of the 443 commands, so that a reply can be
;             attributed to the command that produced it.
;    0.003 s  everything else, the 261 datagrams per chunk included.
;
;  So the console's bulk rate is the SERIAL PORT'S BAUD RATE DIVIDED BY
;  THE FORMATTER'S EXPANSION, and no change to the formatter or to the
;  number of datagrams can take it past 11.5 KB/s while the payload goes
;  through the PL011 one byte at a time. Packed hex would have bought
;  2.4x. Base64 through the same pipe would have bought 3.5x. The target
;  was 60x.
;
;  THE RULE THIS COMMAND IS AN INSTANCE OF
;  ---------------------------------------
;  A TRANSFER'S BYTES BELONG TO THE CONSOLE THAT ASKED FOR THEM. A
;  DISPLAY'S BYTES BELONG TO EVERY CONSOLE.
;
;  `memory` is a display: it renders bytes as text for a person, and it
;  goes to the serial port, the screen and the network at once, at the
;  slowest of the three's rate, so that all three agree character for
;  character about what was printed. That is what a terminal is for and
;  it is left EXACTLY as it was - same format, same clamp, same ASCII
;  gutter, same stop-on-any-keystroke, same closing sentence.
;
;  `readback` is a transfer: it moves bytes to a machine, and that
;  machine named itself by sending the command. The payload goes to that
;  machine, at its own wire's rate, and nowhere else. A person at the
;  serial port or the screen sees the command and its verdict line -
;  which is the part a person can read - and not a megabyte of base64
;  they could do nothing with anyway.
;
;  Typed on the serial port, a readback goes out the serial port, at
;  what a serial port can do. Nothing is special-cased: ConsoleWriteBulk
;  below asks who is asking, once, before the first byte, and that is the
;  entire decision.
;
;  THE FORM ON THE WIRE
;  --------------------
;    readback 57400000 1812000 bytes base64
;    <64 base64 characters>            48 bytes of memory a line
;    ... 37,750 more lines ...
;    readback end 1812000 bytes crc32 A1B2C3D4
;
;  48 bytes is chosen because it is a multiple of three, so a full line
;  is 64 characters with NO padding and a host can join every line and
;  decode the lot in one call; only the final short line can carry '='.
;  Fifteen lines is 990 bytes, which fits one console datagram
;  (#NETCON_OUT_MAX is 1024) and carries 720 bytes of memory - so 1.8 MB
;  is 2,517 datagrams instead of the 115,000 the hex dump sent.
;
;  THE LENGTH AND THE CRC-32 ARE THE PROOF, and they are on the LAST
;  line on purpose: a host reads until it sees that line, so it never
;  sleeps waiting for a reply to end, and a lost datagram - which takes
;  whole lines with it and leaves a stream that still looks orderly -
;  fails the length immediately and the checksum after it. The
;  polynomial is #CRC_POLY, the same one `crc32`, tools/anvil.py and
;  Python's zlib.crc32 use, so the host's answer is independent and not
;  a restatement of the board's.
;
;  NO gBase. `readback` is in the crc32/load/save family - a whole-range
;  operation over an address a tool worked out - and U-Boot's crc32 does
;  not add base_address either. `memory`, `write`, `fill`, `copy` and
;  `compare` do add it, and each says so when it happens.
;
;  Ctrl-C ONLY, not any byte. A readback is driven by a host that is
;  sending nothing while it listens, so the any-byte rule would be
;  harmless - but the screenshot stream took the same decision for the
;  same reason (see OutBreakCtrlC) and one rule for bulk streams is
;  better than two. A stopped readback says `readback stopped`, with the
;  count and the checksum OF WHAT REALLY WENT, so a host cannot mistake
;  a partial stream for a whole one.
; ======================================================================

; 48 source bytes -> 64 base64 characters, no padding. The only line
; that can be shorter is the last one.
#RB_LINE_SRC   = 48
; 15 lines a datagram: 15 * (64 + 2) = 990 <= #NETCON_OUT_MAX.
#RB_BLOCK_SRC  = 720
; The staging buffer for the encoded block. 1024 rather than the 990 the
; arithmetic above gives, because a bound that is only just large enough
; is a bound that goes wrong the first time somebody changes a constant.
#RB_OUT_MAX    = 1024

Global Dim rbSrc.a[#RB_BLOCK_SRC]
Global Dim rbOut.a[#RB_OUT_MAX]
; The alphabet as a table, filled from rb_Sixbit on first use. Measured
; under tools/a64: calling rb_Sixbit four times per three bytes cost 45
; instructions a byte on its own, and a lookup is a load. The mapping is
; still written once, in rb_Sixbit, and read from there.
Global Dim rbAlpha.a[64]
Global rbAlphaReady.i = 0
Global gRbDatagrams.i          ; blocks handed to the console
Global gRbFails.i              ; blocks the console could not send

; ----------------------------------------------------------------------
;  ConsoleWriteBulk - where a transfer's payload goes.
;
;  toPeer is decided ONCE by the emitter, before the first block, and
;  passed in. It is not re-derived per block, because a block that fell
;  back to the other console halfway through a stream would arrive in
;  two places, in two formats, and neither copy would be whole.
;
;  1 if the block went, 0 if it did not. A refusal is counted and named
;  in the closing line rather than silently retried: the length and the
;  checksum there are what say whether the stream is usable, and a host
;  that gets a short one asks for the range again - `readback` reads and
;  changes nothing, so asking twice cannot cost anything but time.
; ----------------------------------------------------------------------
Procedure.i ConsoleWriteBulk(toPeer.i, *p, n.i)
  Define i.i
  If n <= 0
    ProcedureReturn 0
  EndIf
  If toPeer <> 0
    ProcedureReturn NetConsoleWriteBulk(*p, n)
  EndIf
  ; The local console. UartWrite is the right call here and its cost is
  ; not a defect: this IS the serial port, and the bytes are going to the
  ; person who typed the command on it.
  i = 0
  While i < n
    UartWrite(PeekA(*p + i))
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  rb_Sixbit - one base64 digit. RFC 4648 table 1, the standard
;  alphabet, so Python's base64.b64decode and every other decoder on
;  earth reads it with no arguments about it.
; ----------------------------------------------------------------------
Procedure.i rb_Sixbit(v.i)
  If v < 26
    ProcedureReturn 65 + v                 ; A..Z
  EndIf
  If v < 52
    ProcedureReturn 97 + (v - 26)          ; a..z
  EndIf
  If v < 62
    ProcedureReturn 48 + (v - 52)          ; 0..9
  EndIf
  If v = 62
    ProcedureReturn 43                     ; +
  EndIf
  ProcedureReturn 47                       ; /
EndProcedure

; ----------------------------------------------------------------------
;  rb_EncodeBlock - rbSrc[0..n-1] into rbOut as base64 lines.
;
;  Returns how many bytes of rbOut are in use. Every line but a final
;  short one is #RB_LINE_SRC bytes, and each line ends CR LF because the
;  reader on the other end is a terminal.
; ----------------------------------------------------------------------
Procedure.i rb_EncodeBlock(n.i)
  Define i.i
  Define v.i
  Define j.i
  Define o.i
  Define run.i
  Define left.i
  Define b0.i
  Define b1.i
  Define b2.i
  If rbAlphaReady = 0
    v = 0
    While v < 64
      rbAlpha[v] = rb_Sixbit(v)
      v = v + 1
    Wend
    rbAlphaReady = 1
  EndIf
  o = 0
  i = 0
  While i < n
    run = n - i
    If run > #RB_LINE_SRC
      run = #RB_LINE_SRC
    EndIf
    j = 0
    While j < run
      left = run - j
      b0 = rbSrc[i + j]
      rbOut[o] = rbAlpha[b0 >> 2]
      o = o + 1
      If left = 1
        rbOut[o] = rbAlpha[(b0 & 3) << 4]
        o = o + 1
        rbOut[o] = 61                      ; =
        o = o + 1
        rbOut[o] = 61                      ; =
        o = o + 1
      Else
        b1 = rbSrc[i + j + 1]
        rbOut[o] = rbAlpha[((b0 & 3) << 4) | (b1 >> 4)]
        o = o + 1
        If left = 2
          rbOut[o] = rbAlpha[(b1 & 15) << 2]
          o = o + 1
          rbOut[o] = 61                    ; =
          o = o + 1
        Else
          b2 = rbSrc[i + j + 2]
          rbOut[o] = rbAlpha[((b1 & 15) << 2) | (b2 >> 6)]
          o = o + 1
          rbOut[o] = rbAlpha[b2 & 63]
          o = o + 1
        EndIf
      EndIf
      j = j + 3
    Wend
    rbOut[o] = 13
    o = o + 1
    rbOut[o] = 10
    o = o + 1
    i = i + run
  Wend
  ProcedureReturn o
EndProcedure

; ----------------------------------------------------------------------
;  ReadbackStream - the whole payload. Returns the bytes that went.
;
;  The CRC is computed over the STAGED COPY rather than over the target
;  range a second time, so every byte of the range is read from the
;  board EXACTLY ONCE. That is the same rule DumpMem states for its row
;  snapshot and it matters for the same reason: a range that turns out
;  to hold a device register must not be asked twice and get two
;  different answers, one of which then goes on the wire while the other
;  goes into the checksum.
;
;  gRbCrcOut is the finished checksum of what actually went, not of what
;  was asked for, so a stopped stream carries a checksum a host can
;  still verify against the part it received.
; ----------------------------------------------------------------------
Global gRbCrcOut.i

Procedure.i ReadbackStream(a.i, n.i)
  Define i.i
  Define k.i
  Define take.i
  Define nOut.i
  Define crc.i
  Define toPeer.i
  ; ONE decision, before the first byte. See the header.
  toPeer = NetConsoleOwnsCommand()
  gRbDatagrams = 0
  gRbFails = 0
  crc = $FFFFFFFF
  i = 0
  While i < n
    ; ONE CHECK PER BLOCK - 720 bytes of memory, one datagram. Fine
    ; enough that a stop is felt at once, coarse enough that the check
    ; is not the cost.
    If OutBreakCtrlC() <> 0
      Break
    EndIf
    take = n - i
    If take > #RB_BLOCK_SRC
      take = #RB_BLOCK_SRC
    EndIf
    k = 0
    While k < take
      rbSrc[k] = PeekA(a + i + k)
      k = k + 1
    Wend
    crc = Crc32Part(crc, @rbSrc[0], take)
    nOut = rb_EncodeBlock(take)
    If ConsoleWriteBulk(toPeer, @rbOut[0], nOut) = 0
      gRbFails = gRbFails + 1
    EndIf
    gRbDatagrams = gRbDatagrams + 1
    i = i + take
  Wend
  gRbCrcOut = crc ! $FFFFFFFF
  ProcedureReturn i
EndProcedure

; ----------------------------------------------------------------------
;  ReadbackRun - the header, the payload and the verdict, for a range
;  that has already been parsed and allowed.
;
;  Split from CmdReadback so that the part that decides what goes on the
;  wire can be driven by tools/a64/a64_wificon_check.py through the REAL
;  console output path, without a command parser or an address guard in
;  that image. The command below is argument handling and refusals and
;  nothing else, so there is no second copy of anything that reaches a
;  console.
; ----------------------------------------------------------------------
Procedure.i ReadbackRun(a.i, n.i)
  Define sent.i

  ; THE HEADER, then the payload, then the verdict. The header goes
  ; through the ordinary console path so every console sees it; the
  ; payload does not. NetConsoleWriteBulk flushes the ordinary path
  ; before its first datagram, so the header cannot end up behind the
  ; stream it introduces.
  Print("readback ")
  PutAddr(a)
  Print(" ")
  PrintDec(n)
  PrintN(" bytes base64")
  UartDrain()

  sent = ReadbackStream(a, n)

  ; THE CLOSING LINE IS THE PROOF AND IT IS SENT ONCE.
  ;
  ; The screenshot stream prints its terminator THREE times, because
  ; losing the one datagram that carried it wastes a seven-minute
  ; capture that cannot be resumed. That reasoning does not carry here
  ; and the difference is worth stating rather than copying: a readback
  ; is chunked by the host and is READ-ONLY, so a lost terminator costs
  ; one re-read of one chunk and nothing else. Three identical verdict
  ; lines in a transcript a person reads would be the larger harm.
  ;
  ; A BLOCK THE LINK REFUSED IS SAID BEFORE THE VERDICT, not after it. A
  ; host stops reading at the verdict line, so anything printed below it
  ; lands in the next command's settle and is never seen by the tool that
  ; needed it.
  If gRbFails > 0
    Print("!! ")
    PrintDec(gRbFails)
    Print(" of ")
    PrintDec(gRbDatagrams)
    PrintN(" blocks could not be put on the wire, so the stream above is")
    PrintN("   INCOMPLETE and the checksum below is of the whole range rather than")
    PrintN("   of what arrived. Check the link with net and ask again.")
  EndIf
  If sent < n
    Print("readback stopped after ")
    PrintDec(sent)
    Print(" of ")
    PrintDec(n)
    Print(" bytes crc32 ")
    PutHexN(gRbCrcOut, 8)
    PrintNl()
    PrintN("  Ctrl-C ended it. The count and the checksum above are of what really")
    PrintN("  went, so they can still be checked - but this is PART of the range.")
  Else
    Print("readback end ")
    PrintDec(sent)
    Print(" bytes crc32 ")
    PutHexN(gRbCrcOut, 8)
    PrintNl()
  EndIf
  ProcedureReturn sent
EndProcedure

; ----------------------------------------------------------------------
;  CmdReadback - the command: arguments, refusals, the board's say, and
;  then ReadbackRun.
; ----------------------------------------------------------------------
Procedure CmdReadback()
  Define a.i
  Define n.i
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was read.")
      ProcedureReturn
    EndIf
    PrintN("readback <address> <length>")
    PrintN("  send a block of memory to whoever typed this, as base64, and end")
    PrintN("  with the byte count and a crc32 over it. Both numbers are hex and")
    PrintN("  the length is in bytes. This is how a tool gets bytes OFF the board;")
    PrintN("  memory is how a person LOOKS at them, and it is unchanged.")
    PrintN("  There is no length limit and no default: a bulk read with a guessed")
    PrintN("  length is not a bulk read. Ctrl-C stops it and says how far it got.")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    PrintN("!! readback needs a length as well as an address, in hexadecimal bytes,")
    PrintN("   and it is missing or is not a hex number. Nothing was read.")
    PrintN("   readback <address> <length>, both hex. There is no default length -")
    PrintN("   type memory <address> if what you wanted was to look at 64 bytes.")
    ProcedureReturn
  EndIf
  If n <= 0
    PrintN("!! a length of zero bytes sends nothing, so nothing was read. Give a")
    PrintN("   length in hexadecimal bytes - readback 500000 1000 sends 4096 of")
    PrintN("   them from 00500000.")
    ProcedureReturn
  EndIf
  If n > #LEN_MAX
    PrintN("!! that is more than a gigabyte, and the range check below cannot be")
    PrintN("   trusted for a length that large. Nothing was read. Read it in")
    PrintN("   pieces - see the note on #LEN_MAX in the source.")
    ProcedureReturn
  EndIf
  ; The board is asked, exactly as `memory` asks it, and for the same
  ; reason: a range with nothing behind it stalls the processor on the
  ; bus rather than faulting, and it has happened to somebody twice.
  ; The range is NOT window-checked - reading is the whole point.
  If AddrAllowed(a, a + n - 1, 0, "readback", "read") = 0
    ProcedureReturn
  EndIf
  ReadbackRun(a, n)
EndProcedure
