; ======================================================================
;  messages.pbi - THE MESSAGE LOG. What background services have to say,
;  kept off the command line and shown where it was asked for.
; ======================================================================
;  THE RULE (2026-09-16): a message for the user is not written to the
;  command line at all. The command line carries the prompt, the typed
;  input and the output of the command that was run. Everything else -
;  a lease renewing, the radio rekeying or recovering, the network console
;  arming on a new address, a mouse being looked for, a renderer refusing
;  unsafe memory - is a MESSAGE, and a message goes here.
;
;  HOW A BYTE BECOMES A MESSAGE is decided once, at the byte layer every
;  console shares: the board's console write (RaspberryPi4/Lib/uart.pi4 on
;  the Pi 4, ArduinoQ/Board/qcon_q.unoq on the UNO Q) diverts every byte
;  written between UartMessageBegin() and UartMessageEnd() into a ring,
;  and never to the serial line, the screen console or the network tap.
;  This file registers the drain that turns that ring into lines.
;
;  WHO OPENS THE BRACKET. Not the sentences - the CONTEXTS that run on
;  behalf of nobody at the keyboard:
;
;    Anvil/Core/parse.pbi    ReadLine's idle services, all of them, so a
;                            service added later is covered unnamed; the
;                            mouse search that runs as the prompt opens;
;                            and the editor's own refusal of a key.
;    Anvil/Core/rxbreak.pbi  the network poll a long command makes while
;                            it prints, to notice Ctrl-C.
;    the Pi 4 payload return the lease and console re-derivation that runs
;                            after a payload comes back, before its result.
;    the Pi 4 Wi-Fi library  a mid-session EAPOL-Key frame, whichever pump
;                            happened to deliver it.
;
;  WHERE IT IS SHOWN. `messages` prints the log on any console, and on the
;  serial line and the network console that is the way to see them. On a
;  board with a screen, the banner's status caption carries the newest
;  unread one (RaspberryPi4/Board/banner_status.pi4). Reading the log
;  clears the banner.
;
;  A MESSAGE IS ONE BRACKET. Every line written inside one outermost
;  UartMessageBegin/UartMessageEnd shares a number, so a sentence and the
;  address list that follows it read back as one message.
;
;  BOUNDED, AND IT SAYS WHAT IT LOST. #MSG_SLOTS lines are kept; the oldest
;  line goes when a new one needs its slot, and the count of lines lost that
;  way is printed. A line longer than #MSG_LINE continues in the next slot.
; ======================================================================

#MSG_SLOTS = 64
#MSG_LINE = 159

Global Dim gMsgText.a[#MSG_SLOTS * (#MSG_LINE + 1)]
Global Dim gMsgNoOf.i[#MSG_SLOTS]      ; message number the line belongs to
Global Dim gMsgSecsOf.i[#MSG_SLOTS]    ; seconds since start when it was kept
Global gMsgNext.i = 0                  ; the slot the next line takes
Global gMsgKept.i = 0                  ; slots in use, 0..#MSG_SLOTS
Global gMsgLines.i = 0                 ; lines ever kept
Global gMsgEvicted.i = 0               ; lines dropped to make room
Global gMsgNo.i = 0                    ; messages ever started
Global gMsgReadNo.i = 0                ; the newest message `messages` has shown
Global gMsgOpen.i = 0                  ; 1 while the current bracket has a line
Global gMsgNewestSlot.i = -1           ; first line of the newest message
Global Dim gMsgCur.a[#MSG_LINE + 1]
Global gMsgCurLen.i = 0
Global Dim gMsgNone.a[1]               ; the empty string MessagesNewest returns

Procedure.i msg_Secs()
  Define hz.i
  Define now.i
  hz = TickHz()
  now = Ticks()
  If hz <= 0 Or now < gBootTicks
    ProcedureReturn 0
  EndIf
  ProcedureReturn (now - gBootTicks) / hz
EndProcedure

; Keep the line being built. Blank lines are not messages - a PrintN("")
; that only ended a line has already been accounted for.
Procedure msg_Commit()
  Define base.i
  Define i.i
  Define seen.i
  If gMsgCurLen <= 0
    ProcedureReturn
  EndIf
  ; A LINE WITH NOTHING VISIBLE IN IT IS NOT A MESSAGE - forum 892. Build 164
  ; kept one: nine spaces, all that was left of a line once the bytes the log
  ; could not show had been dropped. It says something happened and not what,
  ; so it is neither kept nor allowed to start a message number of its own.
  seen = 0
  For i = 0 To gMsgCurLen - 1
    If gMsgCur[i] <> 32
      seen = 1
      Break
    EndIf
  Next
  If seen = 0
    gMsgCurLen = 0
    ProcedureReturn
  EndIf
  If gMsgKept >= #MSG_SLOTS
    gMsgEvicted = gMsgEvicted + 1
    ; The slot being reused holds the newest message's first line only
    ; when that one message is longer than the whole log; then there is no
    ; first line left to show, and the banner says nothing rather than
    ; showing a line from the middle.
    If gMsgNewestSlot = gMsgNext
      gMsgNewestSlot = -1
    EndIf
  Else
    gMsgKept = gMsgKept + 1
  EndIf
  If gMsgOpen = 0
    gMsgNo = gMsgNo + 1
    gMsgOpen = 1
    gMsgNewestSlot = gMsgNext
  EndIf
  base = gMsgNext * (#MSG_LINE + 1)
  For i = 0 To gMsgCurLen - 1
    gMsgText[base + i] = gMsgCur[i]
  Next
  gMsgText[base + gMsgCurLen] = 0
  gMsgNoOf[gMsgNext] = gMsgNo
  gMsgSecsOf[gMsgNext] = msg_Secs()
  gMsgLines = gMsgLines + 1
  gMsgNext = gMsgNext + 1
  If gMsgNext >= #MSG_SLOTS
    gMsgNext = 0
  EndIf
  gMsgCurLen = 0
EndProcedure

; ----------------------------------------------------------------------
;  MessagesDrain - the byte ring's drain. Registered by MessagesStart().
;
;  IT MUST NOT PRINT: it runs inside the console write. It only moves
;  bytes into lines. A carriage return is dropped (the newline ends the
;  line), a tab is a space, and any other control byte or non-ASCII byte
;  is stored as the four visible characters \xNN: the log is read back on a
;  terminal and on the banner and neither should be steered by it, and a
;  byte that is simply dropped is how a message came to say nothing (892).
;
;  CALLED WITH NO BRACKET OPEN, it also finishes the message: a partial
;  line is kept as it stands and the next line starts a new message.
; ----------------------------------------------------------------------
Procedure msg_Put(c.i)
  If gMsgCurLen >= #MSG_LINE
    msg_Commit()
  EndIf
  gMsgCur[gMsgCurLen] = c
  gMsgCurLen = gMsgCurLen + 1
EndProcedure

; A byte the log cannot show as itself, kept as the four characters \xNN -
; never dropped, so a message made of such bytes still says what it held.
Procedure msg_PutEscaped(c.i)
  Define d.i
  If gMsgCurLen > #MSG_LINE - 4
    msg_Commit()
  EndIf
  msg_Put(92)
  msg_Put(120)
  d = (c >> 4) & 15
  If d < 10
    msg_Put(48 + d)
  Else
    msg_Put(55 + d)
  EndIf
  d = c & 15
  If d < 10
    msg_Put(48 + d)
  Else
    msg_Put(55 + d)
  EndIf
EndProcedure

Procedure MessagesDrain()
  Define c.i
  Repeat
    c = UartMessageGet()
    If c < 0
      Break
    EndIf
    If c = 10
      msg_Commit()
    ElseIf c = 13
      ; the newline that follows ends the line
    ElseIf c = 9
      msg_Put(32)
    ElseIf c >= 32 And c <= 126
      msg_Put(c)
    Else
      msg_PutEscaped(c & $FF)
    EndIf
  ForEver
  If UartMessageDepth() = 0
    msg_Commit()
    gMsgOpen = 0
  EndIf
EndProcedure

; Start diverting. Called once, by the board, before its first prompt.
; Everything printed before this - the boot log - stays on the consoles.
Procedure MessagesStart()
  UartMessageSetDrain(@MessagesDrain)
EndProcedure

; Messages nobody has run `messages` to see yet.
Procedure.i MessagesUnread()
  If gMsgNo > gMsgReadNo
    ProcedureReturn gMsgNo - gMsgReadNo
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i MessagesTotal()
  ProcedureReturn gMsgNo
EndProcedure

; The first line of the newest message, or an empty string. For a caption:
; the address is into this log and must be copied at once.
Procedure.i MessagesNewest()
  If gMsgNewestSlot < 0 Or gMsgNo = 0
    ProcedureReturn @gMsgNone[0]
  EndIf
  ProcedureReturn @gMsgText[gMsgNewestSlot * (#MSG_LINE + 1)]
EndProcedure

; ----------------------------------------------------------------------
;  messages - print the log, oldest first, and mark it read.
;
;  THE FIRST LINE IS FOR A SCRIPT:  messages <total> kept <lines> lost <n>
;  where lost counts lines pushed out of the log and bytes the ring could
;  not take. Then each message: its number and the seconds since start on
;  its first line, continuation lines indented under it.
; ----------------------------------------------------------------------
Procedure CmdMessages()
  Define i.i
  Define s.i
  Define no.i
  Define lastNo.i
  Define lost.i

  SkipSpace()
  If gLine[gPos] <> 0
    PrintN("!! messages takes no arguments. Type messages on its own to see what")
    PrintN("   background services have reported; nothing was changed.")
    ProcedureReturn
  EndIf

  ; Anything still being collected belongs in this listing.
  If UartMessageDepth() = 0
    MessagesDrain()
  EndIf

  lost = gMsgEvicted + UartMessageLost()
  Print("messages ")
  PrintDec(gMsgNo)
  Print(" kept ")
  PrintDec(gMsgKept)
  Print(" lost ")
  PrintDec(lost)
  PrintNl()

  If gMsgKept = 0
    PrintN("No background service has reported anything since this monitor started.")
    gMsgReadNo = gMsgNo
    ProcedureReturn
  EndIf

  PrintN("Messages from background services, oldest first. These are never")
  PrintN("printed on the command line; this is where they are read.")
  If gMsgEvicted > 0
    Print("The oldest ")
    PrintDec(gMsgEvicted)
    PrintN(" lines were dropped to make room for newer ones.")
  EndIf
  If UartMessageLost() > 0
    Print("A burst of ")
    PrintDec(UartMessageLost())
    PrintN(" bytes arrived faster than it could be kept and was dropped.")
  EndIf

  s = gMsgNext - gMsgKept
  If s < 0
    s = s + #MSG_SLOTS
  EndIf
  lastNo = -1
  For i = 0 To gMsgKept - 1
    If OutBreak() <> 0
      Break
    EndIf
    no = gMsgNoOf[s]
    If no <> lastNo
      Print("  #")
      PrintDec(no)
      Print("  at ")
      PrintDec(gMsgSecsOf[s])
      Print(" s")
      PrintNl()
      lastNo = no
    EndIf
    Print("      ")
    UartWriteStr(@gMsgText[s * (#MSG_LINE + 1)])
    PrintNl()
    s = s + 1
    If s >= #MSG_SLOTS
      s = 0
    EndIf
  Next
  gMsgReadNo = gMsgNo
EndProcedure
