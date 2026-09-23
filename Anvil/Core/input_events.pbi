; ======================================================================
;  input_events.pbi - THE NORMALIZED INPUT DISPATCHER
;
;  ONE PLACE WHERE A KEYSTROKE BECOMES A KEYSTROKE, whatever produced
;  it: the serial line, a USB keyboard, a byte from the network console,
;  or a finger on a soft key. Everything downstream - the line editor,
;  and later the touch keyboard - reads THIS queue and nothing else.
;
;  WHY IT EXISTS AT ALL. Before this file the monitor had two input
;  paths that did not know about each other:
;
;    1. Anvil/Core/parse.pbi's ReadLine() spun over three byte sources
;       and did its own editing inline - append a printable, drop the
;       last on a backspace, and nothing else. There was no cursor and
;       no way for anything but a byte to reach it.
;    2. RaspberryPi4/Board/cursor_input.pi4's TouchTick() drained the
;       HwTouch* event queue into a local buffer and THREW EVERY EVENT
;       AWAY, keeping only the contact count and the primary contact's
;       position for the mouse pointer.
;
;  A soft keyboard bolted onto that would have needed a SECOND drain of
;  the same hardware queue, and two drains of one queue is a coin toss
;  over which consumer sees each event. hal.pbi already says why the
;  queue is a queue: "a tap that begins and ends between two UI frames
;  must still be seen". Two consumers racing it is the same loss wearing
;  a different hat.
;
;  So the board drains the hardware queue ONCE, hands every event to
;  InputTouchDispatch() here, and this file decides who owns the
;  contact. An owner then reads ITS OWN routed lane. There is exactly
;  one drain of the hardware, and a consumer can never eat another
;  consumer's event.
;
; ======================================================================
;  THE NAMES, AS IMPLEMENTED
; ======================================================================
;  The shared contract this lane was given names these procedures, and
;  every one of them exists here with that exact spelling and meaning:
;
;    InputEventsPush(*event) -> 0 ok, nonzero error code
;    InputEventsPop(*event)  -> 1 got one, 0 empty
;    InputFocusGeneration()  -> the current generation
;    InputCancelAll(reason)
;    InputCaptureBegin(contactId, ownerId)
;    InputCaptureOwner(contactId)
;    InputCaptureEnd(contactId)
;
;  Nothing was renamed to suit the codebase. What follows are ADDITIONS
;  this implementation needs, named in the same family:
;
;    InputEventInit(*ev, kind, source, code, mods)  fill a record with
;                          the CURRENT generation and timestamp. A
;                          producer that does not use it is stamping the
;                          generation itself, which is how a stale event
;                          is written on purpose (the gate does exactly
;                          that).
;    InputEventsQueued()   how many are waiting, stale ones included
;    InputStaleDropped()   events Pop refused because their generation
;                          had been left behind
;    InputCancelReason() / InputCancelCount()
;                          why the last cancellation happened, and how
;                          many there have been. A cancellation that is
;                          not counted is a cancellation nobody can
;                          prove happened.
;    InputFocus() / InputFocusSet(client)
;                          which client owns typed input. Setting it to
;                          the client it already is changes NOTHING -
;                          see InputFocusSet.
;    InputFeedByte(source, byte)
;                          the one place a TRANSPORT byte becomes a UI
;                          event. The design is explicit that these are
;                          not the same thing.
;    InputTouchDispatch(x, y, contactId, state, ticks, pressure)
;                          route one contact event. Returns the owner.
;    InputTouchPop(ownerId, *ev) -> 1 got one, 0 empty
;    InputTouchQueued(ownerId)
;    InputRegionSet(ownerId, x, y, w, h) / InputRegionClear(ownerId)
;    InputRegionOwnerAt(x, y)
;                          WHO a DOWN belongs to, decided from ONE
;                          rectangle per owner. A soft keyboard installs
;                          its rectangle from the same layout result it
;                          draws from; nothing here knows what a key is.
;    InputCaptureReconcileBegin() / InputCaptureSeen(id) /
;    InputCaptureReconcileEnd(reason)
;                          mark and sweep against the contacts that are
;                          down NOW, for a stream that lost its UPs.
;    InputErrText(code) / InputCancelText(reason)
;                          a whole sentence for every code, as a
;                          POINTER, the way HwTouchErrText() does it.
;
; ======================================================================
;  THE EVENT RECORD - 32 BYTES, LAID OUT LIKE hal.pbi's TOUCH RECORD
; ======================================================================
;  Fields in the order the contract states them, with the 64-bit
;  timestamp eight-byte aligned - the same reasoning hal.pbi gives for
;  putting the controller's tick count at +16 of its own record, and the
;  same reason: PokeI writes eight bytes on this part and the tick
;  counter passes 2^32 about eighty seconds after a reset at 54 MHz, so
;  a 32-bit field here would wrap inside a working session.
;
;     +0  i32 Kind        #AIE_TEXT / _KEY_DOWN / _KEY_UP / _CANCEL
;     +4  i32 Source      #AIS_PHYSICAL / _NETWORK / _TOUCH_KEYBOARD
;     +8  i32 Code        printable ASCII 32..126 for TEXT, an #AIK_
;                         code for the KEY kinds, an #AIC_ reason for
;                         CANCEL
;     +12 i32 Modifiers   #AIM_ bits. INFORMATIONAL: the producer has
;                         already resolved case, so a consumer that
;                         ignores this field is still correct.
;     +16 i32 Generation  the focus generation the producer saw
;     +20 i32 reserved    0
;     +24 i64 Timestamp   monitor ticks. Push stamps it when it is 0, so
;                         a producer holding a CONTROLLER timestamp
;                         keeps it and one that has none cannot ship a
;                         zero.
; ======================================================================

#AIE_EVSZ = 32

#AIE_EV_KIND  = 0
#AIE_EV_SRC   = 4
#AIE_EV_CODE  = 8
#AIE_EV_MODS  = 12
#AIE_EV_GEN   = 16
#AIE_EV_RSVD  = 20
#AIE_EV_TIME  = 24

; The four event kinds. TEXT and KEY are separate because a printable
; character and a named key are different things: 'a' is text, Home is
; not, and a consumer that had to tell them apart by inspecting the code
; would be guessing about codes 1..10.
#AIE_TEXT     = 1
#AIE_KEY_DOWN = 2
#AIE_KEY_UP   = 3
#AIE_CANCEL   = 4

; The named keys. These numbers are the shared vocabulary of all three
; lanes of this feature and they are not renumbered.
#AIK_ENTER          = 1
#AIK_BACKSPACE      = 2
#AIK_DELETE         = 3
#AIK_LEFT           = 4
#AIK_RIGHT          = 5
#AIK_HOME           = 6
#AIK_END            = 7
#AIK_TAB            = 8
#AIK_ESC            = 9
#AIK_CANCEL_COMMAND = 10          ; Ctrl+C semantics
#AIK_MAX            = 10

; Where an event came from. IT IS NOT DECORATION: the network console's
; ownership rules key off it - a soft keystroke is LOCAL input and
; claims the console the way a serial byte does, a byte that arrived
; from the peer does not, and merely DRAWING a keyboard claims nothing.
#AIS_PHYSICAL       = 1
#AIS_NETWORK        = 2
#AIS_TOUCH_KEYBOARD = 3
#AIS_MAX            = 3

; Modifier bits, informational. The producer resolved the case already.
#AIM_SHIFT = 1
#AIM_CTRL  = 2

; ----------------------------------------------------------------------
;  THE RETURN CODES. Every one of them has a whole sentence in
;  InputErrText() below, because rule of 2026-09-03: an error a program
;  prints is a complete sentence that keeps the numeric code, says what
;  it means and names the first thing to check.
; ----------------------------------------------------------------------
#AIE_OK            = 0
#AIE_ERR_ARG       = 1            ; a null record pointer
#AIE_ERR_KIND      = 2            ; no such event kind
#AIE_ERR_CODE      = 3            ; the code is not legal for the kind
#AIE_ERR_SOURCE    = 4            ; no such producer
#AIE_ERR_FULL      = 5            ; the queue saturated; all cancelled
#AIE_ERR_LINE_FULL = 6            ; the edited line is at its limit
#AIE_ERR_NO_TAB    = 7            ; this editor has no completion
#AIE_ERR_CAPTURED  = 8            ; another owner holds that contact
#AIE_ERR_CAPFULL   = 9            ; no contact slot left
#AIE_ERR_OWNER     = 10           ; no such owner

; ----------------------------------------------------------------------
;  WHY EVERYTHING WAS CANCELLED. The design lists the causes; each one
;  gets a number so the sentence the operator reads names the actual
;  event rather than "input was reset".
; ----------------------------------------------------------------------
#AIC_NONE          = 0
#AIC_FOCUS_CHANGE  = 1
#AIC_QUEUE_FULL    = 2
#AIC_TOUCH_LOST    = 3
#AIC_SCREEN_CHANGE = 4
#AIC_LAYOUT_CHANGE = 5
#AIC_CONTACT_LOST  = 6
#AIC_PAYLOAD       = 7
#AIC_MAX           = 7

; ----------------------------------------------------------------------
;  WHO CAN OWN A CONTACT. Zero is nobody, and it is not an owner id: a
;  capture table whose empty slots read as a real owner is a table that
;  hands every stray finger to whoever drew slot 0.
;
;  #AIO_KEYBOARD is declared HERE, in the file that owns the vocabulary,
;  even though the touch keyboard is another lane's file. An owner id
;  invented by the consumer would be an id this dispatcher could not
;  range check.
; ----------------------------------------------------------------------
#AIO_NONE     = 0
#AIO_POINTER  = 1                 ; the mouse/finger arrow, cursor_input.pi4
#AIO_KEYBOARD = 2                 ; the soft keyboard
#AIO_UI       = 3                 ; a payload or diagnostic surface
#AIO_MAX      = 3

; ----------------------------------------------------------------------
;  WHICH CLIENT TYPED INPUT GOES TO. One today. It is a number and not a
;  flag because "no client" and "the command line" must be tellable
;  apart: a monitor that is running a payload has no editor to type at,
;  and events queued against one would run as a command when it
;  returned - which the design names as a thing that must not happen.
; ----------------------------------------------------------------------
#AIF_NONE         = 0
#AIF_COMMAND_LINE = 1

; ======================================================================
;  THE ROUTED CONTACT RECORD - 40 BYTES
; ======================================================================
;  hal.pbi's 32-byte touch record is the BOARD's vocabulary and it stops
;  at the board. What crosses into portable code is this: the same
;  fields, plus the two the dispatcher adds - who owns the contact, and
;  which focus generation it was routed in.
;
;     +0  i32 x        screen pixels, already rotated and scaled BY THE
;                      BOARD. Nothing here transforms a coordinate; a
;                      second opinion about which way up the panel is
;                      is exactly the defect hal.pbi warns about.
;     +4  i32 y
;     +8  i32 id       the controller's stable contact id
;     +12 i32 state    #AIT_DOWN / _MOVE / _UP / _CANCEL
;     +16 i64 ticks    when the CONTROLLER reported it
;     +24 i32 pressure 0..255, or -1. Carried rather than dropped: a
;                      normalization seam that quietly loses a field is
;                      a seam the next consumer has to route around.
;     +28 i32 owner    #AIO_*
;     +32 i32 gen      the generation this was routed in
;     +36 i32 reserved 0
;
;  THE FOUR STATES ARE DELIBERATELY THE SAME NUMBERS as hal.pbi's
;  #HW_TOUCH_DOWN / _MOVE / _UP / _CANCEL, so the board's hand-over is a
;  copy and not a translation table that can rot. They are re-declared
;  rather than reached for because hal.pbi is a HAL header a board
;  includes and this file compiles on a board with no touch surface at
;  all. tools/input_editor_emitted_check.py reads both files and goes
;  red if the two sets ever stop agreeing.
;
;  AND _CANCEL IS NOT _UP. hal.pbi: a UI that treats a lost contact as a
;  release "will fire a button the driver did not press".
; ======================================================================

#AIT_EVSZ = 40

#AIT_EV_X     = 0
#AIT_EV_Y     = 4
#AIT_EV_ID    = 8
#AIT_EV_ST    = 12
#AIT_EV_TICK  = 16
#AIT_EV_PRES  = 24
#AIT_EV_OWNER = 28
#AIT_EV_GEN   = 32
#AIT_EV_RSVD  = 36

#AIT_DOWN   = 0
#AIT_MOVE   = 1
#AIT_UP     = 2
#AIT_CANCEL = 3

; ----------------------------------------------------------------------
;  THE BOUNDS, AND THEY ARE BOUNDS AND NOT GUESSES.
;
;  #AIE_QMAX is 64 because the design says 64: "Start with a bounded
;  64-event keyboard queue and fixed contact/layout arrays; on
;  saturation cancel safely and report an error, never silently drop a
;  key-UP."
;
;  #AIT_QMAX is 64 to MATCH THE HARDWARE RING IT IS FED FROM.
;  RaspberryPi4/Board/hw_touch.pi4 holds 64 records and TouchTick()
;  drains it completely, dispatches each event and then lets each owner
;  drain its own lane inside the same tick - so the most a lane can be
;  handed between two drains is one full hardware ring. Equal capacity
;  is the arithmetic answer, not a round number.
;
;  #AIT_MAXCONTACTS is 10 because that is what the fitted controller
;  reports and what the ten-point visual test confirmed on the glass on
;  2026-09-10.
; ----------------------------------------------------------------------
#AIE_QMAX        = 64
#AIT_QMAX        = 64
#AIT_MAXCONTACTS = 10

Global Dim gInQ.a[#AIE_QMAX * #AIE_EVSZ + 8]
Global gInHead.i = 0
Global gInTail.i = 0
Global gInCount.i = 0
Global gInStale.i = 0             ; popped, refused, counted
Global gInPushed.i = 0            ; accepted by Push, ever
Global gInPopped.i = 0            ; delivered by Pop, ever

Global gInGen.i = 1               ; the focus generation. STARTS AT ONE so
                                  ; that a record left zeroed in BSS is
                                  ; never mistaken for a current event.
Global gInFocus.i = #AIF_NONE
Global gInCancelReason.i = #AIC_NONE
Global gInCancelCount.i = 0

; The routed lanes, one per owner. Slot 0 (#AIO_NONE) exists so the
; arithmetic is ownerId * #AIT_QMAX and not (ownerId - 1) * #AIT_QMAX,
; which is one subtraction and one off-by-one waiting to happen.
Global Dim gItQ.a[(#AIO_MAX + 1) * #AIT_QMAX * #AIT_EVSZ + 8]
Global Dim gItHead.i[#AIO_MAX + 1]
Global Dim gItTail.i[#AIO_MAX + 1]
Global Dim gItCount.i[#AIO_MAX + 1]
Global Dim gItLost.i[#AIO_MAX + 1]

; The capture table. A contact belongs to one owner for its whole life.
Global Dim gIcId.i[#AIT_MAXCONTACTS + 1]
Global Dim gIcOwner.i[#AIT_MAXCONTACTS + 1]
Global Dim gIcMark.i[#AIT_MAXCONTACTS + 1]
Global gIcUsed.i = 0

; One hit rectangle per owner, installed from that owner's own layout.
Global Dim gIrOn.i[#AIO_MAX + 1]
Global Dim gIrX.i[#AIO_MAX + 1]
Global Dim gIrY.i[#AIO_MAX + 1]
Global Dim gIrW.i[#AIO_MAX + 1]
Global Dim gIrH.i[#AIO_MAX + 1]

; ======================================================================
;  SENTENCES
; ======================================================================

Procedure.i InputErrText(code.i)
  Select code
    Case #AIE_OK
      ProcedureReturn "input error 0: nothing went wrong; this code means success and should not have been printed."
    Case #AIE_ERR_ARG
      ProcedureReturn "input error 1: an input event record was passed as a null pointer, so there was nowhere to read or write the 32 bytes; the caller passed the address of its event buffer incorrectly."
    Case #AIE_ERR_KIND
      ProcedureReturn "input error 2: an input event named a kind that does not exist; it must be text, key-down, key-up or cancel, and the producer filled the kind field with something else."
    Case #AIE_ERR_CODE
      ProcedureReturn "input error 3: an input event carried a code its kind does not allow - text must be printable ASCII 32 to 126 and a key must be one of the ten named keys; check what the producer put in the code field."
    Case #AIE_ERR_SOURCE
      ProcedureReturn "input error 4: an input event named a producer that does not exist; it must be the physical console, the network console or the touch keyboard."
    Case #AIE_ERR_FULL
      ProcedureReturn "input error 5: the input queue filled up, so every contact, modifier and pending key was cancelled rather than a key release being thrown away silently; the consumer stopped draining input - check whether a command is running without servicing the prompt."
    Case #AIE_ERR_LINE_FULL
      ProcedureReturn "input error 6: the command line is already at its maximum length, so that character was not inserted; shorten the line or press Enter to run it."
    Case #AIE_ERR_NO_TAB
      ProcedureReturn "input error 7: this monitor's command line has no Tab completion, so the Tab key does nothing here rather than inserting an invented completion; type the command word in full."
    Case #AIE_ERR_CAPTURED
      ProcedureReturn "input error 8: that touch contact is already owned by a different part of the screen and keeps that owner until the finger lifts; nothing else may take it mid-gesture."
    Case #AIE_ERR_CAPFULL
      ProcedureReturn "input error 9: every tracked touch contact slot is in use, so this contact could not be given an owner; ten simultaneous contacts is the controller's reported maximum."
    Case #AIE_ERR_OWNER
      ProcedureReturn "input error 10: an input owner id outside the known set was used; the owners are the pointer, the touch keyboard and a payload surface."
    Default
      ProcedureReturn "input error: an input return code outside the documented set was produced, which means this file and its caller disagree about the contract; that is a defect in the monitor, not in anything you typed."
  EndSelect
EndProcedure

Procedure.i InputCancelText(reason.i)
  Select reason
    Case #AIC_NONE
      ProcedureReturn "input cancel 0: no cancellation has happened since this board started."
    Case #AIC_FOCUS_CHANGE
      ProcedureReturn "input cancel 1: the part of the screen that receives typing changed, so held contacts and modifiers were released; anything already typed is kept."
    Case #AIC_QUEUE_FULL
      ProcedureReturn "input cancel 2: the input queue saturated, so held contacts and modifiers were released rather than a key release being lost; anything already typed is kept."
    Case #AIC_TOUCH_LOST
      ProcedureReturn "input cancel 3: the panel's touch controller stopped answering, so held contacts and modifiers were released; anything already typed is kept."
    Case #AIC_SCREEN_CHANGE
      ProcedureReturn "input cancel 4: the screen or its source changed, so held contacts and modifiers were released before the new hit geometry was installed; anything already typed is kept."
    Case #AIC_LAYOUT_CHANGE
      ProcedureReturn "input cancel 5: the on-screen layout was rebuilt, so held contacts and modifiers were released before the new hit rectangles were installed; anything already typed is kept."
    Case #AIC_CONTACT_LOST
      ProcedureReturn "input cancel 6: a touch contact disappeared without a release event, so it was released against the contacts the controller reports now; anything already typed is kept."
    Case #AIC_PAYLOAD
      ProcedureReturn "input cancel 7: the monitor handed the processor to a payload, so held contacts and modifiers were released before the hand-over; anything already typed is kept."
    Default
      ProcedureReturn "input cancel: a cancellation reason outside the documented set was recorded, which is a defect in the monitor rather than anything you did."
  EndSelect
EndProcedure

; ======================================================================
;  FOCUS AND GENERATION
; ======================================================================

Procedure.i InputFocusGeneration()
  ProcedureReturn gInGen
EndProcedure

Procedure.i InputFocus()
  ProcedureReturn gInFocus
EndProcedure

Procedure.i InputCancelReason()
  ProcedureReturn gInCancelReason
EndProcedure

Procedure.i InputCancelCount()
  ProcedureReturn gInCancelCount
EndProcedure

Procedure.i InputStaleDropped()
  ProcedureReturn gInStale
EndProcedure

Procedure.i InputEventsQueued()
  ProcedureReturn gInCount
EndProcedure

Procedure.i InputTouchQueued(ownerId.i)
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn 0
  EndIf
  ProcedureReturn gItCount[ownerId]
EndProcedure

Procedure.i InputTouchLost(ownerId.i)
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn 0
  EndIf
  ProcedureReturn gItLost[ownerId]
EndProcedure

; ----------------------------------------------------------------------
;  InputCancelAll - release EVERYTHING and say why.
;
;  The design lists the causes in one breath: "On CANCEL, queue
;  overflow, touch loss, focus loss or layout generation change, release
;  every capture and repeat timer. Never leave a stuck Shift/Backspace."
;  So there is one procedure and the reason is an argument, rather than
;  five places that each remember four of the five things to clear.
;
;  IT LEAVES EXACTLY ONE EVENT IN THE QUEUE - a #AIE_CANCEL carrying the
;  reason, at the NEW generation. A consumer therefore learns that its
;  world was reset by reading its normal input, at the point in the
;  stream where it happened, instead of having to poll a flag it might
;  check on the wrong side of the reset.
;
;  IT DOES NOT TOUCH TYPED TEXT, and that is a requirement and not an
;  omission: "Rotation, screen switch, resizing, renderer reset or loss
;  of focused client cancels all active contacts/modifiers/repeat state
;  before new hit geometry is installed. RETAIN TYPED TEXT."
;
;  IT DOES NOT FLUSH THE HARDWARE QUEUE EITHER. "Do not flush unrelated
;  consumers' events to clear keyboard state" - HwTouchFlush() belongs
;  to screen changes and to the board, and reaching for it from here
;  would throw away a payload's touch stream to tidy up the monitor's.
; ----------------------------------------------------------------------
Procedure InputCancelAll(reason.l)
  Define i.i
  Define o.i
  Define *e

  ; Every queued event was produced against the generation that is being
  ; left behind, so they are all stale by definition. They are counted
  ; where a stale event is always counted rather than being quietly
  ; overwritten by the ring reset.
  gInStale = gInStale + gInCount
  gInHead = 0
  gInTail = 0
  gInCount = 0

  o = 1
  While o <= #AIO_MAX
    gItHead[o] = 0
    gItTail[o] = 0
    gItCount[o] = 0
    o = o + 1
  Wend

  i = 0
  While i < #AIT_MAXCONTACTS
    gIcId[i] = 0
    gIcOwner[i] = #AIO_NONE
    gIcMark[i] = 0
    i = i + 1
  Wend
  gIcUsed = 0

  gInGen = gInGen + 1
  gInCancelReason = reason
  gInCancelCount = gInCancelCount + 1

  ; The announcement, written straight into the ring rather than through
  ; InputEventsPush, because Push validates against the generation and
  ; the reason codes are not #AIK_ codes.
  *e = @gInQ[0] + gInHead * #AIE_EVSZ
  PokeL(*e + #AIE_EV_KIND, #AIE_CANCEL)
  PokeL(*e + #AIE_EV_SRC, #AIS_PHYSICAL)
  PokeL(*e + #AIE_EV_CODE, reason)
  PokeL(*e + #AIE_EV_MODS, 0)
  PokeL(*e + #AIE_EV_GEN, gInGen)
  PokeL(*e + #AIE_EV_RSVD, 0)
  PokeI(*e + #AIE_EV_TIME, Ticks())
  gInHead = (gInHead + 1) % #AIE_QMAX
  gInCount = gInCount + 1
EndProcedure

; ----------------------------------------------------------------------
;  InputPayloadSuspend - the machine is about to change hands.
;
;  ONE NAME FOR "A PAYLOAD IS BEING ENTERED", SO THAT NO BOARD HAS TO
;  SPELL THE REASON ITSELF. A payload takes the whole machine; anything
;  this dispatcher is still holding when it goes - a queued byte, a
;  routed contact, a capture whose UP will never arrive - would
;  otherwise be delivered to an editor that is not running, or worse,
;  executed as a command after the payload returns. That is the same
;  hazard on every board, so the cancellation belongs here and not in
;  each board's jump.
;
;  IT CANCELS AND NOTHING ELSE. There is no suspended flag to clear
;  afterwards and therefore no Resume twin: InputCancelAll bumps the
;  generation and leaves one #AIE_CANCEL in the ring, so a consumer
;  learns its world was reset by reading its normal input, and the next
;  producer stamps the new generation without being told to. A board
;  with a UI layer on top - the Pi 4's touch keyboard - needs more than
;  this and has its own suspend/resume pair for the parts of that layer
;  this file knows nothing about; that pair's suspend half ends in the
;  very same InputCancelAll(#AIC_PAYLOAD) call. It still writes the call
;  itself rather than coming through here, which is one spelling too
;  many and is owed - the Pi 4 image is deliberately unchanged by the
;  commit that added this seam, so that the Q's fix could be proven to
;  have moved nothing on the board that was already correct.
;
;  WHY A PROCEDURE AND NOT THE BARE InputCancelAll(#AIC_PAYLOAD) CALL.
;  Not style: the compiler settles it. A board file may call a procedure
;  this file defines later in the include order, because procedure names
;  are resolved across the whole build - but it may NOT name a constant
;  that has not been declared yet, and a constant cannot be forward
;  declared. ArduinoQ/Board/qstubs_q.unoq is included ahead of this file
;  (it declares gLastCR, which InputFeedByte below reads, so it has to
;  be), and its RunAt was therefore unable to write the #AIC_PAYLOAD
;  spelling at all. A seam that takes no argument keeps the #AIC_
;  vocabulary inside the layer that defines it, which is where it should
;  have been anyway: the board says WHAT HAPPENED, and this file decides
;  what that means.
; ----------------------------------------------------------------------
Procedure InputPayloadSuspend()
  InputCancelAll(#AIC_PAYLOAD)
EndProcedure

; ----------------------------------------------------------------------
;  InputFocusSet - point typed input at a client.
;
;  SETTING IT TO WHAT IT ALREADY IS DOES NOTHING AT ALL, and that is the
;  whole reason this is a procedure rather than an assignment. ReadLine
;  calls it on every line; if it bumped the generation each time, every
;  Enter would cancel a held Shift, an in-flight contact and the
;  keyboard's repeat state - so typing two commands in a row with a
;  finger held on Shift would behave differently from typing one.
; ----------------------------------------------------------------------
Procedure.i InputFocusSet(client.i)
  If client = gInFocus
    ProcedureReturn gInGen
  EndIf
  gInFocus = client
  InputCancelAll(#AIC_FOCUS_CHANGE)
  ProcedureReturn gInGen
EndProcedure

; ======================================================================
;  THE EVENT QUEUE
; ======================================================================

; InputEventInit - fill a record with the current generation and time.
; A producer that wants a stale or a hand-stamped event writes the
; fields itself; this is the ordinary path and it cannot produce one.
Procedure.i InputEventInit(*ev, kind.l, source.l, code.l, mods.l)
  If *ev = 0
    ProcedureReturn #AIE_ERR_ARG
  EndIf
  PokeL(*ev + #AIE_EV_KIND, kind)
  PokeL(*ev + #AIE_EV_SRC, source)
  PokeL(*ev + #AIE_EV_CODE, code)
  PokeL(*ev + #AIE_EV_MODS, mods)
  PokeL(*ev + #AIE_EV_GEN, gInGen)
  PokeL(*ev + #AIE_EV_RSVD, 0)
  PokeI(*ev + #AIE_EV_TIME, Ticks())
  ProcedureReturn #AIE_OK
EndProcedure

; ----------------------------------------------------------------------
;  InputEventsPush - one event into the queue. 0 ok, nonzero code.
;
;  IT VALIDATES THE SHAPE AND REFUSES, rather than storing something no
;  consumer can act on. A text event carrying 7, or a key event carrying
;  99, is a producer defect and this monitor's whole philosophy is that
;  a loud refusal beats a plausible wrong answer.
;
;  IT DOES NOT REFUSE A STALE GENERATION. A producer legitimately reads
;  the generation, builds an event, and loses a race with a cancellation
;  in between; that is not an error, it is exactly what the generation
;  exists to catch. It is caught at the OTHER end, in Pop, so the event
;  dies once, in one place, and is counted there.
;
;  ON SATURATION IT CANCELS EVERYTHING AND SAYS SO. The alternative -
;  dropping the oldest, which is what the hardware ring does - is right
;  for positions and wrong for keys: the oldest event in a full keyboard
;  queue is as likely as not the key-UP that stops a repeat, and losing
;  it leaves a key held down forever. The design names this outcome
;  directly: "on saturation cancel safely and report an error, never
;  silently drop a key-UP".
; ----------------------------------------------------------------------
Procedure.i InputEventsPush(*event)
  Define kind.i
  Define code.i
  Define src.i
  Define *e

  If *event = 0
    ProcedureReturn #AIE_ERR_ARG
  EndIf
  kind = PeekL(*event + #AIE_EV_KIND)
  code = PeekL(*event + #AIE_EV_CODE)
  src = PeekL(*event + #AIE_EV_SRC)

  If src < 1 Or src > #AIS_MAX
    ProcedureReturn #AIE_ERR_SOURCE
  EndIf
  Select kind
    Case #AIE_TEXT
      If code < 32 Or code > 126
        ProcedureReturn #AIE_ERR_CODE
      EndIf
    Case #AIE_KEY_DOWN
      If code < 1 Or code > #AIK_MAX
        ProcedureReturn #AIE_ERR_CODE
      EndIf
    Case #AIE_KEY_UP
      If code < 1 Or code > #AIK_MAX
        ProcedureReturn #AIE_ERR_CODE
      EndIf
    Case #AIE_CANCEL
      If code < 0 Or code > #AIC_MAX
        ProcedureReturn #AIE_ERR_CODE
      EndIf
    Default
      ProcedureReturn #AIE_ERR_KIND
  EndSelect

  If gInCount >= #AIE_QMAX
    InputCancelAll(#AIC_QUEUE_FULL)
    ProcedureReturn #AIE_ERR_FULL
  EndIf

  *e = @gInQ[0] + gInHead * #AIE_EVSZ
  PokeL(*e + #AIE_EV_KIND, kind)
  PokeL(*e + #AIE_EV_SRC, src)
  PokeL(*e + #AIE_EV_CODE, code)
  PokeL(*e + #AIE_EV_MODS, PeekL(*event + #AIE_EV_MODS))
  PokeL(*e + #AIE_EV_GEN, PeekL(*event + #AIE_EV_GEN))
  PokeL(*e + #AIE_EV_RSVD, 0)
  If PeekI(*event + #AIE_EV_TIME) = 0
    PokeI(*e + #AIE_EV_TIME, Ticks())
  Else
    PokeI(*e + #AIE_EV_TIME, PeekI(*event + #AIE_EV_TIME))
  EndIf
  gInHead = (gInHead + 1) % #AIE_QMAX
  gInCount = gInCount + 1
  gInPushed = gInPushed + 1
  ProcedureReturn #AIE_OK
EndProcedure

; ----------------------------------------------------------------------
;  InputEventsPop - the next event this generation still owns.
;  1 filled the caller's record, 0 nothing to deliver.
;
;  A STALE EVENT IS SKIPPED AND COUNTED, not delivered. It is skipped
;  here rather than refused at Push so that the decision is made once,
;  at the moment of delivery, against the generation that is current
;  THEN - which is the only moment at which "stale" has a meaning.
; ----------------------------------------------------------------------
Procedure.i InputEventsPop(*event)
  Define *e
  Define i.i

  If *event = 0
    ProcedureReturn 0
  EndIf
  While gInCount > 0
    *e = @gInQ[0] + gInTail * #AIE_EVSZ
    gInTail = (gInTail + 1) % #AIE_QMAX
    gInCount = gInCount - 1
    If PeekL(*e + #AIE_EV_GEN) <> gInGen
      gInStale = gInStale + 1
    Else
      i = 0
      While i < #AIE_EVSZ
        PokeA(*event + i, PeekA(*e + i))
        i = i + 1
      Wend
      gInPopped = gInPopped + 1
      ProcedureReturn 1
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i InputEventsPushed()
  ProcedureReturn gInPushed
EndProcedure

Procedure.i InputEventsDelivered()
  ProcedureReturn gInPopped
EndProcedure

; ======================================================================
;  A TRANSPORT BYTE IS NOT A KEYSTROKE
; ======================================================================
;  "do not conflate raw binary transport bytes with UI keystrokes."
;
;  This is the ONE place the conversion happens, and it reproduces
;  exactly what Anvil/Core/parse.pbi's ReadLine() used to do inline,
;  byte for byte, because the physical and Ethernet consoles must behave
;  the same after this refactor as before it:
;
;    13            Enter, and arm the CRLF de-duplicator
;    10            Enter, UNLESS a CR came immediately before it
;    8 or 127      Backspace
;    3             the cancel action (Ctrl-C)
;    32..126       text
;    anything else NOTHING, silently, exactly as before
;
;  THE LAST LINE IS THE IMPORTANT ONE. Byte 9 is Tab and byte 27 is Esc,
;  and it is tempting to map them onto #AIK_TAB and #AIK_ESC now that
;  those exist. Both would CHANGE the serial console: today a Tab does
;  nothing at all, and mapping it would start printing a "no completion
;  here" sentence at people who press it by habit, while Esc would begin
;  discarding half-typed lines - and an escape SEQUENCE from a terminal
;  arrow key starts with exactly that byte, so every arrow press would
;  throw the line away and then type "[A". Those two keys reach the
;  editor from the soft keyboard, which sends the key and not the byte.
;
;  gLastCR IS A BOARD GLOBAL AND IT SURVIVES BETWEEN LINES on purpose: a
;  CRLF terminal sends the CR that ends one line and the LF that arrives
;  at the start of the next, so the de-duplication cannot be per-line
;  state. Getting this wrong draws two prompts for every Enter, which
;  looks like a fault and is not one.
; ----------------------------------------------------------------------
Procedure.i InputFeedByte(source.l, byte.l)
  Define c.i
  Define rc.i
  Dim ev.a[#AIE_EVSZ]

  c = byte & $FF
  If c = 10 And gLastCR <> 0
    gLastCR = 0
    ProcedureReturn #AIE_OK
  EndIf
  gLastCR = 0

  If c = 13 Or c = 10
    If c = 13
      gLastCR = 1
    EndIf
    rc = InputEventInit(@ev[0], #AIE_KEY_DOWN, source, #AIK_ENTER, 0)
    If rc <> #AIE_OK
      ProcedureReturn rc
    EndIf
    ProcedureReturn InputEventsPush(@ev[0])
  EndIf
  If c = 8 Or c = 127
    rc = InputEventInit(@ev[0], #AIE_KEY_DOWN, source, #AIK_BACKSPACE, 0)
    If rc <> #AIE_OK
      ProcedureReturn rc
    EndIf
    ProcedureReturn InputEventsPush(@ev[0])
  EndIf
  If c = 3
    rc = InputEventInit(@ev[0], #AIE_KEY_DOWN, source, #AIK_CANCEL_COMMAND, #AIM_CTRL)
    If rc <> #AIE_OK
      ProcedureReturn rc
    EndIf
    ProcedureReturn InputEventsPush(@ev[0])
  EndIf
  If c >= 32 And c < 127
    rc = InputEventInit(@ev[0], #AIE_TEXT, source, c, 0)
    If rc <> #AIE_OK
      ProcedureReturn rc
    EndIf
    ProcedureReturn InputEventsPush(@ev[0])
  EndIf
  ProcedureReturn #AIE_OK
EndProcedure

; ======================================================================
;  CAPTURE - A CONTACT BELONGS TO ONE OWNER FOR ITS WHOLE LIFE
; ======================================================================
;  "A DOWN inside keyboard chrome or a key belongs to the keyboard until
;  that contact ends - even if dragged outside. It must not click or
;  scroll underneath." And the other half: "Starting outside and sliding
;  inside does not manufacture a keypress."
;
;  Both fall out of one rule - ownership is decided ONCE, at the DOWN,
;  and never revisited - so neither is a special case anywhere.
; ======================================================================

Procedure.i InputCaptureSlot(contactId.i)
  Define i.i
  i = 0
  While i < #AIT_MAXCONTACTS
    If gIcOwner[i] <> #AIO_NONE And gIcId[i] = contactId
      ProcedureReturn i
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i InputCaptureOwner(contactId.i)
  Define s.i
  s = InputCaptureSlot(contactId)
  If s < 0
    ProcedureReturn #AIO_NONE
  EndIf
  ProcedureReturn gIcOwner[s]
EndProcedure

Procedure.i InputCaptureBegin(contactId.i, ownerId.i)
  Define i.i
  Define s.i
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn #AIE_ERR_OWNER
  EndIf
  s = InputCaptureSlot(contactId)
  If s >= 0
    ; ALREADY OWNED. Re-claiming by the SAME owner is idempotent, which
    ; is what a DOWN repeated by a controller that re-reported a frame
    ; looks like; a claim by a different owner is the mid-gesture steal
    ; the design forbids, and it is refused rather than honoured.
    If gIcOwner[s] = ownerId
      ProcedureReturn #AIE_OK
    EndIf
    ProcedureReturn #AIE_ERR_CAPTURED
  EndIf
  i = 0
  While i < #AIT_MAXCONTACTS
    If gIcOwner[i] = #AIO_NONE
      gIcId[i] = contactId
      gIcOwner[i] = ownerId
      gIcMark[i] = 0
      gIcUsed = gIcUsed + 1
      ProcedureReturn #AIE_OK
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #AIE_ERR_CAPFULL
EndProcedure

Procedure.i InputCaptureEnd(contactId.i)
  Define s.i
  s = InputCaptureSlot(contactId)
  If s < 0
    ProcedureReturn #AIE_OK
  EndIf
  gIcOwner[s] = #AIO_NONE
  gIcId[s] = 0
  gIcMark[s] = 0
  gIcUsed = gIcUsed - 1
  ProcedureReturn #AIE_OK
EndProcedure

Procedure.i InputCaptureCount()
  ProcedureReturn gIcUsed
EndProcedure

; ----------------------------------------------------------------------
;  MARK AND SWEEP AGAINST THE CONTACTS THAT ARE DOWN NOW.
;
;  "Reconcile against available current-contact state when a stream
;  loses events." A queue that overflows, or a HwTouchFlush() on a
;  screen change, can swallow an UP - and a capture whose UP never
;  arrives is a finger the keyboard believes is still on a key.
;
;  This is the same argument hw_touch.pi4 makes for deriving the button
;  from HwTouchContacts() rather than from the event stream: the frame
;  is the truth about NOW, the queue is the record of what happened, and
;  a consumer that uses each for the thing it is good at cannot get
;  stuck in either direction.
;
;  THE SWEEP SYNTHESISES A CANCEL, NOT AN UP, for every contact the
;  controller no longer reports - hal.pbi is emphatic that a lost
;  contact is not a release, and a release would commit whatever key the
;  finger was resting on.
; ----------------------------------------------------------------------
Procedure InputCaptureReconcileBegin()
  Define i.i
  i = 0
  While i < #AIT_MAXCONTACTS
    gIcMark[i] = 0
    i = i + 1
  Wend
EndProcedure

Procedure InputCaptureSeen(contactId.i)
  Define s.i
  s = InputCaptureSlot(contactId)
  If s >= 0
    gIcMark[s] = 1
  EndIf
EndProcedure

Procedure.i InputTouchRoutePush(ownerId.i, x.i, y.i, contactId.i, state.i, ticks.i, pressure.i)
  Define *e
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn #AIE_ERR_OWNER
  EndIf
  If gItCount[ownerId] >= #AIT_QMAX
    ; The lane is full, which means its owner stopped draining. Counting
    ; it and cancelling is the loud answer; overwriting the oldest would
    ; be the silent one, and the oldest in a keyboard's lane is exactly
    ; the release that stops a repeat.
    gItLost[ownerId] = gItLost[ownerId] + 1
    InputCancelAll(#AIC_QUEUE_FULL)
    ProcedureReturn #AIE_ERR_FULL
  EndIf
  *e = @gItQ[0] + (ownerId * #AIT_QMAX + gItHead[ownerId]) * #AIT_EVSZ
  PokeL(*e + #AIT_EV_X, x)
  PokeL(*e + #AIT_EV_Y, y)
  PokeL(*e + #AIT_EV_ID, contactId)
  PokeL(*e + #AIT_EV_ST, state)
  PokeI(*e + #AIT_EV_TICK, ticks)
  PokeL(*e + #AIT_EV_PRES, pressure)
  PokeL(*e + #AIT_EV_OWNER, ownerId)
  PokeL(*e + #AIT_EV_GEN, gInGen)
  PokeL(*e + #AIT_EV_RSVD, 0)
  gItHead[ownerId] = (gItHead[ownerId] + 1) % #AIT_QMAX
  gItCount[ownerId] = gItCount[ownerId] + 1
  ProcedureReturn #AIE_OK
EndProcedure

Procedure InputCaptureReconcileEnd(reason.l)
  Define i.i
  Define id.i
  Define owner.i
  i = 0
  While i < #AIT_MAXCONTACTS
    If gIcOwner[i] <> #AIO_NONE And gIcMark[i] = 0
      id = gIcId[i]
      owner = gIcOwner[i]
      InputTouchRoutePush(owner, -1, -1, id, #AIT_CANCEL, Ticks(), -1)
      InputCaptureEnd(id)
      gInCancelReason = reason
      gInCancelCount = gInCancelCount + 1
      ; The table was walked from 0 and InputCaptureEnd only clears the
      ; slot it was given, so the walk position is still valid.
    EndIf
    i = i + 1
  Wend
EndProcedure

; ======================================================================
;  HIT REGIONS - ONE RECTANGLE PER OWNER, FROM THAT OWNER'S LAYOUT
; ======================================================================
;  "Derive key geometry and hit rectangles from one layout result. Use
;  screen logical coordinates already produced by the display/touch
;  mapping; do not rotate or scale touch a second time."
;
;  So the dispatcher holds ONE rectangle per owner and knows nothing
;  about keys, chrome or rows. A soft keyboard installs the rectangle it
;  just laid out; the dispatcher answers "is this DOWN yours"; the
;  keyboard decides which key inside it was hit. Neither half can
;  disagree with the other about where the keyboard is, because there is
;  only one number.
; ======================================================================

Procedure.i InputRegionSet(ownerId.i, x.i, y.i, w.i, h.i)
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn #AIE_ERR_OWNER
  EndIf
  If w <= 0 Or h <= 0
    ProcedureReturn #AIE_ERR_ARG
  EndIf
  gIrOn[ownerId] = 1
  gIrX[ownerId] = x
  gIrY[ownerId] = y
  gIrW[ownerId] = w
  gIrH[ownerId] = h
  ProcedureReturn #AIE_OK
EndProcedure

Procedure.i InputRegionClear(ownerId.i)
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn #AIE_ERR_OWNER
  EndIf
  gIrOn[ownerId] = 0
  ProcedureReturn #AIE_OK
EndProcedure

; InputRegionOwnerAt - who owns this pixel, or #AIO_POINTER.
;
; THE HIGHEST OWNER ID WINS because the owners are declared in layer
; order: the pointer is underneath everything, the keyboard sits over
; the console, and a payload surface sits over that. Searching downwards
; makes the topmost installed rectangle the answer with no separate
; z-order table to keep in step with this one.
Procedure.i InputRegionOwnerAt(x.i, y.i)
  Define o.i
  o = #AIO_MAX
  While o >= 2
    If gIrOn[o] <> 0
      If x >= gIrX[o] And x < gIrX[o] + gIrW[o] And y >= gIrY[o] And y < gIrY[o] + gIrH[o]
        ProcedureReturn o
      EndIf
    EndIf
    o = o - 1
  Wend
  ProcedureReturn #AIO_POINTER
EndProcedure

; ======================================================================
;  THE ONE ROUTE
; ======================================================================
;  InputTouchDispatch - one contact event, routed once.
;
;  The board hands over the FIELDS and not its record, because
;  hal.pbi's 32-byte layout is the board's vocabulary and this file
;  compiles on a board with no touch surface at all. The coordinates
;  arrive already rotated and scaled; nothing here transforms them.
;
;  Returns the owner the event was routed to, or #AIO_NONE if it could
;  not be routed at all.
; ----------------------------------------------------------------------
Procedure.i InputTouchDispatch(x.i, y.i, contactId.i, state.i, ticks.i, pressure.i)
  Define owner.i

  Select state
    Case #AIT_DOWN
      ; OWNERSHIP IS DECIDED HERE AND NOWHERE ELSE.
      owner = InputRegionOwnerAt(x, y)
      If InputCaptureBegin(contactId, owner) <> #AIE_OK
        ; Either another owner holds this id mid-gesture, or all ten
        ; slots are in use. Both mean this DOWN has no owner that can be
        ; trusted, so it is not delivered to anybody.
        ProcedureReturn #AIO_NONE
      EndIf
    Case #AIT_MOVE
      owner = InputCaptureOwner(contactId)
      If owner = #AIO_NONE
        ; A MOVE for a contact whose DOWN was never seen - the stream
        ; started mid-gesture, or its DOWN was refused above. It does
        ; NOT get an owner here: "Starting outside and sliding inside
        ; does not manufacture a keypress", and manufacturing a capture
        ; from a MOVE is the same mistake with the same result.
        ProcedureReturn #AIO_NONE
      EndIf
    Case #AIT_UP
      owner = InputCaptureOwner(contactId)
    Case #AIT_CANCEL
      owner = InputCaptureOwner(contactId)
    Default
      ; hal.pbi has four contact states. A fifth means this file and the
      ; board disagree about the vocabulary, and guessing which of the
      ; four was meant would put a keypress somewhere nobody pressed.
      ProcedureReturn #AIO_NONE
  EndSelect

  If owner = #AIO_NONE
    ProcedureReturn #AIO_NONE
  EndIf

  InputTouchRoutePush(owner, x, y, contactId, state, ticks, pressure)

  ; The release ends the capture AFTER the event has been routed, so the
  ; owner receives its own UP. Ending it first would deliver the last
  ; event of a gesture to nobody, which is the stuck-key shape again.
  If state = #AIT_UP Or state = #AIT_CANCEL
    InputCaptureEnd(contactId)
  EndIf
  ProcedureReturn owner
EndProcedure

; InputTouchPop - the next routed contact event for one owner.
; 1 filled the caller's 40 bytes, 0 the lane is empty.
Procedure.i InputTouchPop(ownerId.i, *ev)
  Define *e
  Define i.i
  If *ev = 0
    ProcedureReturn 0
  EndIf
  If ownerId < 1 Or ownerId > #AIO_MAX
    ProcedureReturn 0
  EndIf
  If gItCount[ownerId] = 0
    ProcedureReturn 0
  EndIf
  *e = @gItQ[0] + (ownerId * #AIT_QMAX + gItTail[ownerId]) * #AIT_EVSZ
  i = 0
  While i < #AIT_EVSZ
    PokeA(*ev + i, PeekA(*e + i))
    i = i + 1
  Wend
  gItTail[ownerId] = (gItTail[ownerId] + 1) % #AIT_QMAX
  gItCount[ownerId] = gItCount[ownerId] - 1
  ProcedureReturn 1
EndProcedure
