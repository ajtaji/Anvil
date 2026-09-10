
; ======================================================================
;  Receive with a deadline.
;
;  uart.pi4 gives us UartReadReady() and UartRead(); timer.pi4 gives us
;  the counter. This is the ten lines that join them, and it is all that
;  is left of the old GetC/GetCT pair - the blocking read IS UartRead().
;
;  WHY NOT UartReadWait(). It bounds a SPIN COUNT, which is the right
;  shape for a library that refuses to depend on a clock, and the wrong
;  shape here: `c 1500000000` changes the CPU speed by 2.5x and would
;  change a spin-count timeout with it, silently. A tick deadline means
;  the same wall-clock time whatever the core is doing. See the note on
;  c in the header.
;
;  A DIVIDE PER PASS WOULD ALSO BE WRONG, which is why this compares
;  raw Ticks() rather than calling millis(). This is the loop with the
;  deadline in the b protocol; the arithmetic in it is one subtract.
; ======================================================================

; RxByte() IS THE PROTOCOL READER, NOT THE INTERACTIVE ONE. CmdBlock()
; reads every byte of an image through here, one at a time, in the
; tightest loop the monitor has - the PL011's RX FIFO is 32 bytes and
; there is no hardware flow control, so any work done between two reads
; is time the FIFO can overrun. The mouse and keyboard are polled in
; ReadLine() instead, which is where the human is; putting them here made
; a 584 KB transfer lose ~40 KB every time and, once the lazy attach was
; added, would have run a multi-second PcieInit() in the middle of a
; receive. Nothing HID belongs in this loop.
Procedure.i RxByte()
  Define t0.i
  t0 = Ticks()
  Repeat
    If UartReadReady() <> 0
      ProcedureReturn UartRead()
    EndIf
    ; A plain 64-bit subtract of two full counter reads. Ticks() is the
    ; whole of CNTPCT_EL0, so there is no wrap to reason about.
    If (Ticks() - t0) > gToTicks
      ProcedureReturn -1
    EndIf
  ForEver
EndProcedure

; ======================================================================
;  STOPPING A LONG PRINT
; ======================================================================
;  WHY THIS EXISTS. 2026-08-26, on the bench: `memory 700000 82A` - about
;  130 lines of hex - made the board unresponsive for MINUTES while the
;  HDMI console painted. It did not answer a carriage return. It did not
;  answer anything. It had in fact already accepted a `reset` and carried
;  it out, but from the host side that was indistinguishable from a dead
;  board, and the operator polled for 76 seconds before concluding it had
;  crashed.
;
;  The verdict, and it is the right one: "unresponsive bootloader because
;  its printing, design flaw". This is not a performance complaint. The
;  boot stick no longer carries U-Boot and nothing can be chainloaded, so
;  the only recovery from a genuinely hung monitor is pulling the power.
;  A monitor that an ORDINARY `memory` command can make look dead is a
;  hazard, and making the print faster does not fix it - a fast console
;  still blocks for long enough, and somebody will always dump something
;  bigger.
;
;  SO OUTPUT IS INTERRUPTIBLE. Every long-output loop asks OutBreak()
;  once per line; if a byte has arrived on the wire, the print stops and
;  says so.
;
;  ONCE PER LINE, NOT ONCE PER CHARACTER, and that is a measurement not a
;  guess. The check is one MMIO read of the PL011 flag register. Per
;  character it would sit inside the tightest loop in the monitor; per
;  line it is one read against seventy-eight characters of output, which
;  at 115200 baud have already cost 6.8 ms of wire time. The worst case
;  it leaves is one line of latency, and one line is not what made the
;  board look dead.
;
;  THE ABORTING BYTE IS EATEN. It has to be: leaving it in the FIFO
;  means the very next ReadLine() picks it up as the first character of a
;  command nobody typed. One byte is consumed, and one only - a host that
;  pipelines a whole command behind the abort will find the rest of that
;  command arriving as a normal line, which is the same thing that would
;  happen if it had typed it a moment later.
;
;  WHAT THIS COSTS A SCRIPT, said plainly rather than discovered later: a
;  host that sends the next command WITHOUT waiting for the prompt will
;  now truncate its own output. That is how `more` and `less` have always
;  behaved, it is what makes the board recoverable from a keyboard, and
;  the fix on the host side is to wait for "pmf> ". It is a deliberate
;  trade and the screenshot path below is the one place it is refused.
; ======================================================================

Global gAbort.i                ; set when output was cut short; cleared
                               ; by OutBreakArm() at the top of every
                               ; command, so it can never leak from one
                               ; command into the next
Global gBreakNetPump.i         ; re-entry guard: OutBreak can be reached
                               ; from network-backed command callbacks

; Called before dispatching a command. NOT at the end of one: a byte that
; arrives after the last line of output is the operator typing the next
; command, and eating it here rather than there is what keeps the two
; apart.
Procedure OutBreakArm()
  gAbort = 0
EndProcedure

Procedure.i OutBroke()
  ProcedureReturn gAbort
EndProcedure

; One cancellation byte from either console source. UART wins when both
; are ready and explicitly takes local ownership, applying the same safe
; cancellation policy as ReadLine. The network pump's exact endpoint
; filter admits only the command owner; another peer gets BUSY and leaves
; no byte here. Guard the pump because a driver/transfer callback may ask
; OutBreak while servicing a network turn of its own.
Procedure.i OutBreakByte()
  Define c.i
  If UartReadReady() <> 0
    c = UartRead()
    NetConsoleClaimLocal()
    ProcedureReturn c
  EndIf
  If gBreakNetPump = 0
    gBreakNetPump = 1
    NetConsolePump()
    gBreakNetPump = 0
  EndIf
  ; Even a re-entrant caller may consume a byte already admitted to the
  ; exact-owner ring; only recursively driving the hardware pump is barred.
  ProcedureReturn NetConsoleGetc()
EndProcedure

; ----------------------------------------------------------------------
;  OutBreak() - 1 if the print should stop now.
;
;  Sticky. Once it has said stop it keeps saying stop for the rest of the
;  command, so a producer with more than one output loop in it does not
;  restart at the second one.
;
;  It PRINTS the reason, once, and the message goes out the normal way -
;  so it reaches the screen console too and the operator sees on the
;  glass that what is in front of him is not the whole answer. A truncated
;  dump that looks complete is exactly the silent-wrong-answer failure
;  this project refuses everywhere else.
; ----------------------------------------------------------------------
Procedure.i OutBreak()
  Define c.i
  If gAbort <> 0
    ProcedureReturn 1
  EndIf
  c = OutBreakByte()
  If c < 0
    ProcedureReturn 0
  EndIf
  gAbort = 1
  ; SAY THAT IT WAS CUT SHORT, IN WORDS. This used to read "-- stopped",
  ; which is four characters that leave the one question a reader has
  ; unanswered: is what is above this line the whole answer? It is not,
  ; and saying so is the entire job of this message. No host tool matches
  ; on it - checked across tools/ on 2026-08-26 - so it is free prose.
  PrintN("Stopped, because a key was pressed. What is printed above this line is")
  PrintN("only part of the answer, not all of it. Run the command again to see")
  PrintN("the whole of it.")
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  OutBreakCtrlC() - the same, but ONLY Ctrl-C stops it.
;
;  THIS IS THE SCREENSHOT'S CHECK AND THE REASON IT IS SEPARATE IS
;  tools/pmfshot.py. That script drives `p` and parses the reply as a
;  machine-readable stream - a PIC header, tens of thousands of run
;  lines, then "END <count>" - and it takes SEVEN MINUTES at 115200
;  baud. Under the any-byte rule a single stray byte from the host, a
;  line-noise glitch or an impatient keypress would end a seven-minute
;  capture, and the operator would have to start again.
;
;  Worse than the waste: it must not be able to end one QUIETLY. pmfshot
;  checks two things - that "END" arrived at all, and that the run count
;  in it matches the number of run lines it parsed (tools/pmfshot.py:
;  the decode() function) - so a stream that simply stops is already
;  caught. The trap would be ending a stream in a way that still looks
;  finished. So an aborted screenshot emits "ABORT <count>" and NEVER
;  "END <count>": pmfshot's END regex does not match it, and the script
;  reports that the stream stopped early instead of writing a truncated
;  PNG. No change to the script is needed and none has been made.
;
;  A BYTE THAT IS NOT Ctrl-C IS READ AND DISCARDED, and there is no way
;  round that: the PL011 has no peek, so the only way to find out what a
;  byte is, is to take it out of the FIFO. It cannot be put back.
;
;  Discarding is nevertheless the right of the two bad options. The
;  alternative is to leave the byte queued, which means not looking at
;  it, which means no Ctrl-C either. And a stray byte arriving DURING a
;  screenshot is not a command the operator meant to run: `p` takes
;  seven minutes and anything typed into it is noise or impatience.
;  Letting it survive to be executed as the first character of the next
;  command line is worse than losing it.
; ----------------------------------------------------------------------
Procedure.i OutBreakCtrlC()
  Define c.i
  If gAbort <> 0
    ProcedureReturn 1
  EndIf
  c = OutBreakByte()
  If c < 0
    ProcedureReturn 0
  EndIf
  If c <> 3                    ; 3 = Ctrl-C
    ProcedureReturn 0
  EndIf
  gAbort = 1
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetBreakCheck - the one name the network libraries ask the monitor
;  for, so that a long fetch can be stopped by a keypress.
;
;  IT IS A NAME AND NOT A PROCEDURE POINTER, for the reason net.pi4's
;  header gives about the same choice: a pointer buys nothing over one
;  line here, and it turns a missing implementation from a compile-time
;  "undefined procedure" into a run-time call through null. A gate that
;  compiles RaspberryPi4/Lib/http.pi4 with no monitor under it supplies
;  its own one-line version and the seam is the whole contract.
; ----------------------------------------------------------------------
Procedure.i NetBreakCheck()
  ProcedureReturn OutBreak()
EndProcedure
