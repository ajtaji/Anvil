; ======================================================================
;  text_edit.pbi - ONE EDITABLE LINE, ONE CARET, ONE PATH IN
;
;  Every source of typing in this monitor edits THIS buffer through
;  THESE procedures: the serial line, a USB keyboard, a byte from the
;  network console, and the soft keyboard. There is no second editor and
;  no second buffer.
;
;  IT EDITS gLine ITSELF, and that is deliberate. gLine, gLineLen,
;  gLineTrunc and gLineCtrlC (Anvil/Core/state.pbi) are what the parser
;  and every command handler read; giving the editor a private buffer
;  and copying it out at the end would create a second place where the
;  command line lives, and the two would disagree the first time
;  something looked at the line mid-edit. The command ABI is therefore
;  byte for byte what it was.
;
; ======================================================================
;  WHAT USED TO BE HERE, AND WHY IT MOVED
; ======================================================================
;  Anvil/Core/parse.pbi's ReadLine() held the editor inline, and it was
;  APPEND-ONLY: a printable character went on the end, a backspace took
;  one off the end, Ctrl-C threw the line away, and that was the whole
;  of it. There was no caret, so there was nothing for Home, End, Delete
;  or the arrow keys to move - which is why the soft keyboard's design
;  says, of the line reader, "Extract real editing state for cursor
;  actions; do not fake navigation by injecting escape text."
;
;  Injecting escape text is the shape that had to be refused. It looks
;  cheap - send ESC [ D and let a terminal do the work - and it is wrong
;  in three ways at once: the board's own framebuffer console is not a
;  terminal and would print the bytes, the network console's peer might
;  be either, and the monitor would no longer know where its own caret
;  was. The editing state is the thing that has to exist.
;
; ======================================================================
;  THE ECHO IS PART OF THE EDITOR, AND IT USES NO ESCAPE SEQUENCES
; ======================================================================
;  Every insertion and deletion echoes itself, because otherwise each of
;  the four input sources would have to know how to redraw a line and
;  they would each do it slightly differently.
;
;  IT IS WRITTEN IN BACKSPACE, SPACE AND ORDINARY CHARACTERS - the three
;  things every consumer of this monitor's output can render: a dumb
;  serial terminal, the board's own text console, and the network
;  console's peer. ReadLine's original backspace was already exactly
;  this (8, 32, 8) and the reasoning simply extends: to move the caret
;  left, send a backspace; to move it right, re-send the character it
;  passes over; to delete inside the line, re-send the tail and one
;  space, then walk back over what was re-sent.
;
;  APPENDING AND BACKSPACING AT THE END EMIT EXACTLY THE BYTES THE OLD
;  EDITOR EMITTED. That is not a coincidence to be grateful for, it is
;  the acceptance test: no byte a transport can carry produces a caret
;  move (see InputFeedByte), so on the serial and Ethernet consoles the
;  caret is always at the end and every echoed byte is the same byte as
;  before this file existed. RaspberryPi4/Tests/input_editor_emitted_gate.pi4
;  compares the whole echo stream against a frozen model of the old
;  editor, character by character, and the mutants prove the comparison
;  is not vacuous.
;
;  IT NEVER RECONSTRUCTS THE LINE FROM THE SCREEN. The design says so in
;  as many words - "Never reconstruct command text from screen pixels" -
;  and the reason this file can honour it easily is that it is the
;  model: the screen is downstream of the buffer and never upstream.
; ======================================================================

Global gTeCaret.i = 0             ; 0..gLineLen, the insertion point
Global gTeDone.i = 0              ; 1 once the line is finished
Global gTeKeyUps.i = 0            ; key releases this editor was handed
Global gTeCancels.i = 0           ; #AIE_CANCEL events this editor saw
Global gTeLastCancel.i = 0        ; ... and the reason of the last one

; ----------------------------------------------------------------------
;  TextEditBegin - start a fresh line.
;
;  It clears exactly the four pieces of state ReadLine used to clear at
;  the top of its own loop, and no more. In particular it does NOT touch
;  gLastCR: a CRLF pair straddles the line boundary by definition, so
;  the de-duplicator has to survive the line it ended.
; ----------------------------------------------------------------------
Procedure TextEditBegin()
  gLineLen = 0
  gLineTrunc = 0
  gLineCtrlC = 0
  gTeCaret = 0
  gTeDone = 0
  gLine[0] = 0
EndProcedure

Procedure.i TextEditText()
  ProcedureReturn @gLine[0]
EndProcedure

Procedure.i TextEditLength()
  ProcedureReturn gLineLen
EndProcedure

Procedure.i TextEditCaret()
  ProcedureReturn gTeCaret
EndProcedure

Procedure.i TextEditDone()
  ProcedureReturn gTeDone
EndProcedure

Procedure.i TextEditCancelled()
  ProcedureReturn gLineCtrlC
EndProcedure

Procedure.i TextEditTruncated()
  ProcedureReturn gLineTrunc
EndProcedure

Procedure.i TextEditKeyUps()
  ProcedureReturn gTeKeyUps
EndProcedure

Procedure.i TextEditCancels()
  ProcedureReturn gTeCancels
EndProcedure

Procedure.i TextEditLastCancel()
  ProcedureReturn gTeLastCancel
EndProcedure

; te_EchoTail - re-send everything from the caret to the end of the
; line, then walk the caret back over it. `extra` is one more column to
; blank first, which is what a deletion needs and an insertion does not.
Procedure te_EchoTail(extra.i)
  Define i.i
  Define n.i
  n = 0
  i = gTeCaret
  While i < gLineLen
    UartWrite(gLine[i] & $FF)
    n = n + 1
    i = i + 1
  Wend
  If extra <> 0
    UartWrite(32)
    n = n + 1
  EndIf
  While n > 0
    UartWrite(8)
    n = n - 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  TextEditInsert - one printable character at the caret.
;  0 ok, #AIE_ERR_CODE for anything that is not printable ASCII,
;  #AIE_ERR_LINE_FULL when the line is already as long as it may be.
;
;  A FULL LINE IS REFUSED, RECORDED AND NOT ECHOED, exactly as before.
;  state.pbi's header explains at length what a silently amputated line
;  costs - an operator watching the last five characters of a Wi-Fi
;  passphrase not appear, and a stored passphrase quietly the wrong
;  length. The flag is what ReadLine's "that line was longer than"
;  sentence is built from, and it is set here because this is now the
;  only place that can know.
; ----------------------------------------------------------------------
Procedure.i TextEditInsert(char.i)
  Define c.i
  Define i.i

  c = char & $FF
  If c < 32 Or c > 126
    ProcedureReturn #AIE_ERR_CODE
  EndIf
  If gLineLen >= #LINE_MAX
    gLineTrunc = 1
    ProcedureReturn #AIE_ERR_LINE_FULL
  EndIf

  ; Open the gap. Walking DOWNWARDS from the end is what makes this an
  ; insertion rather than a smear: copying upwards would write each byte
  ; over the one it had not read yet.
  i = gLineLen
  While i > gTeCaret
    gLine[i] = gLine[i - 1]
    i = i - 1
  Wend
  gLine[gTeCaret] = c
  gLineLen = gLineLen + 1
  gTeCaret = gTeCaret + 1
  gLine[gLineLen] = 0

  UartWrite(c)
  ; At the end of the line there is no tail, so this emits nothing and
  ; the echo is the single character the old editor sent.
  te_EchoTail(0)
  ProcedureReturn #AIE_OK
EndProcedure

Procedure.i te_Backspace()
  Define i.i
  If gTeCaret <= 0
    ProcedureReturn #AIE_OK
  EndIf
  i = gTeCaret
  While i < gLineLen
    gLine[i - 1] = gLine[i]
    i = i + 1
  Wend
  gTeCaret = gTeCaret - 1
  gLineLen = gLineLen - 1
  gLine[gLineLen] = 0
  UartWrite(8)
  ; At the end of the line the tail is empty, so this is the space and
  ; the second backspace - the 8, 32, 8 the old editor sent.
  te_EchoTail(1)
  ProcedureReturn #AIE_OK
EndProcedure

Procedure.i te_Delete()
  Define i.i
  If gTeCaret >= gLineLen
    ProcedureReturn #AIE_OK
  EndIf
  i = gTeCaret + 1
  While i < gLineLen
    gLine[i - 1] = gLine[i]
    i = i + 1
  Wend
  gLineLen = gLineLen - 1
  gLine[gLineLen] = 0
  te_EchoTail(1)
  ProcedureReturn #AIE_OK
EndProcedure

; ----------------------------------------------------------------------
;  TextEditKey - one named key. 0 ok, nonzero an input error code whose
;  sentence InputErrText() holds.
;
;  TAB IS REFUSED AND NOT INVENTED. This monitor's command line has no
;  completion: the command table is matched on whole words, and prefix
;  matching was considered and rejected years ago because `s` would be
;  ambiguous between `screen` and `srecord` (see parse.pbi's COMMAND
;  WORDS block). So Tab returns #AIE_ERR_NO_TAB and the caller prints
;  the sentence. The design is explicit: "if none is implemented,
;  explicitly make it unavailable rather than invent completions."
;
;  ESC AND CTRL-C DO THE SAME THING HERE, and that is not a conflation.
;  They differ in WHO consumes them - a visible soft keyboard may take
;  Esc to hide itself and never pass it on, and the design says a
;  physical Esc "must not also cancel the command in the same event" -
;  but an Esc that does reach a single-line editor cancels the edit,
;  which is precisely what Ctrl-C does. Two keys, one editor action.
; ----------------------------------------------------------------------
Procedure.i TextEditKey(code.i)
  Select code
    Case #AIK_ENTER
      gTeDone = 1
      ProcedureReturn #AIE_OK
    Case #AIK_BACKSPACE
      ProcedureReturn te_Backspace()
    Case #AIK_DELETE
      ProcedureReturn te_Delete()
    Case #AIK_LEFT
      If gTeCaret > 0
        gTeCaret = gTeCaret - 1
        UartWrite(8)
      EndIf
      ProcedureReturn #AIE_OK
    Case #AIK_RIGHT
      If gTeCaret < gLineLen
        ; Re-send the character the caret steps over. A cursor-right
        ; escape would be the other way to do it and would print three
        ; visible characters on the board's own console.
        UartWrite(gLine[gTeCaret] & $FF)
        gTeCaret = gTeCaret + 1
      EndIf
      ProcedureReturn #AIE_OK
    Case #AIK_HOME
      While gTeCaret > 0
        gTeCaret = gTeCaret - 1
        UartWrite(8)
      Wend
      ProcedureReturn #AIE_OK
    Case #AIK_END
      While gTeCaret < gLineLen
        UartWrite(gLine[gTeCaret] & $FF)
        gTeCaret = gTeCaret + 1
      Wend
      ProcedureReturn #AIE_OK
    Case #AIK_TAB
      ProcedureReturn #AIE_ERR_NO_TAB
    Case #AIK_ESC
      gLineLen = 0
      gTeCaret = 0
      gLine[0] = 0
      gLineTrunc = 0
      gLineCtrlC = 1
      gTeDone = 1
      ProcedureReturn #AIE_OK
    Case #AIK_CANCEL_COMMAND
      ; WHAT CTRL-C ALWAYS DID, MOVED AND NOT CHANGED. The line is
      ; discarded, the truncation flag goes with it (complaining that a
      ; line was too long, about a line that has just been thrown away,
      ; would be a warning about nothing), and gLineCtrlC is set so the
      ; mm/nm sub-prompt in memcmd.pbi can tell a deliberate abort from
      ; a blank Enter. The echoed characters are deliberately NOT erased
      ; from the screen: the transcript should show what was abandoned.
      gLineLen = 0
      gTeCaret = 0
      gLine[0] = 0
      gLineTrunc = 0
      gLineCtrlC = 1
      gTeDone = 1
      ProcedureReturn #AIE_OK
    Default
      ProcedureReturn #AIE_ERR_CODE
  EndSelect
EndProcedure

; ----------------------------------------------------------------------
;  TextEditKeyRelease - a key came back up.
;
;  THE EDITOR HAS NOTHING TO DO WITH A RELEASE and says so by counting
;  it rather than by having no entry point at all. Repeat belongs to the
;  producer (the soft keyboard owns its own repeat timers); a line
;  editor has no held state to end.
;
;  The counter is the difference between "ignored" and "lost". The
;  design forbids ever silently dropping a key-UP, and the gate proves
;  it by pushing releases and reading this number back - which is only
;  possible because they arrive somewhere countable.
; ----------------------------------------------------------------------
Procedure.i TextEditKeyRelease(code.i)
  If code < 1 Or code > #AIK_MAX
    ProcedureReturn #AIE_ERR_CODE
  EndIf
  gTeKeyUps = gTeKeyUps + 1
  ProcedureReturn #AIE_OK
EndProcedure

; ----------------------------------------------------------------------
;  TextEditCancelNotice - everything was cancelled underneath us.
;
;  IT KEEPS THE TEXT. "Rotation, screen switch, resizing, renderer reset
;  or loss of focused client cancels all active contacts/modifiers/
;  repeat state before new hit geometry is installed. RETAIN TYPED
;  TEXT." A cancellation is about contacts and modifiers; the half-typed
;  command belongs to the person who typed it, and throwing it away
;  because a screen rotated would be the monitor losing work nobody
;  asked it to lose.
; ----------------------------------------------------------------------
Procedure TextEditCancelNotice(reason.i)
  gTeCancels = gTeCancels + 1
  gTeLastCancel = reason
EndProcedure
