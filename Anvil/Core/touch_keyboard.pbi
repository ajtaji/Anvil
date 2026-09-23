; ======================================================================
;  Anvil/Core/touch_keyboard.pbi - THE TOUCH KEYBOARD WITHOUT PIXELS
; ======================================================================
;  This file is the whole keyboard except where it is on the glass. It
;  owns the key tables, the modifiers, the pages, the repeat clock, the
;  visibility state machine, the contacts and the events that come out
;  of it. It owns NO coordinates, NO colours and NO rectangles.
;
;  WHY THE SPLIT IS HERE AND NOT SOMEWHERE ELSE. A keyboard has two
;  entirely different kinds of knowledge in it: what the keys MEAN, and
;  where they ARE. The first is the same on a 7-inch panel, a 1080p
;  HDMI screen and a future board nobody has wired yet; the second
;  changes with every one of them. Put them in one file and every
;  rotation, every text-scale change and every new panel reopens the
;  question of what Shift does - which is a question that was answered
;  on a US keyboard forty years ago and does not need answering again.
;
;  So this file asks the view exactly ONE question, TouchKeyboardHitKey,
;  and never asks it anything else.
;
;  ====================================================================
;   THE VIEW'S SIDE OF THAT ONE QUESTION - READ THIS BEFORE IMPLEMENTING IT
;  ====================================================================
;  TouchKeyboardHitKey(x, y) takes SCREEN LOGICAL pixels - the same
;  numbers the HAL touch event already carries, mapped once by the
;  board's display layer and never rotated or scaled a second time -
;  and returns an index into the CURRENT PAGE, 0..TouchKeyboardKeyCount()-1,
;  or -1 for a point that is not on this keyboard at all.
;
;  ITS HIT RECTANGLES MUST TILE THE KEYBOARD SURFACE. A point anywhere
;  inside the keyboard - including the gap a designer sees between two
;  key faces, including the chrome around the hide chevron - must come
;  back as some key, never as -1. That is not a convenience: -1 is how
;  this file knows a contact does not belong to the keyboard and must be
;  left for whatever is underneath, so a -1 returned from a pixel that
;  is visibly inside the keyboard is a tap that clicks through onto the
;  console. Draw the faces with gaps; make the rectangles touch.
;
;  ====================================================================
;   WHAT COMES OUT: A BOUNDED QUEUE, DRAINED BY THE INTEGRATION
;  ====================================================================
;  Nothing in here calls the input dispatcher directly, because the
;  dispatcher is another lane's file and a keyboard that cannot be
;  compiled or tested without it is a keyboard that gets tested with it
;  and never alone. Instead every emission lands in a bounded 64-event
;  ring that the service loop drains:
;
;      While TouchKeyboardPop() <> 0
;        ; fill the dispatcher's record from the six accessors
;        InputEventsPush(...)
;      Wend
;
;  The six accessors carry exactly the shared contract's six fields, in
;  its order and with its numbers. The constants below are the contract's
;  own names at the contract's own values, so the integration writes
;  #AIE_TEXT and this file means #AIE_TEXT; the gate asserts every one of
;  those numbers so a lane that changes one is caught by an assertion
;  instead of by a keyboard that types the wrong thing.
;
;  THE RING RESERVES ITS LAST SLOT FOR A CANCEL. An ordinary event is
;  refused at 63 so the cancellation that a full queue forces can always
;  be delivered. The design's rule is that a key-UP is never silently
;  dropped, and this is how that is kept: the drop is loud - an error
;  code with a whole sentence behind it - and everything in flight is
;  cancelled rather than half-applied.
;
;  ====================================================================
;   THE CLOCK IS INJECTED. NOTHING IN HERE BLOCKS.
;  ====================================================================
;  TouchKeyboardTick(now) takes MILLISECONDS from the monitor's own
;  clock and is the only thing that moves time forward in this file.
;  Every timing rule - the 450 ms before a repeat starts, the 50 ms
;  between repeats, the 350 ms double-tap that latches Caps Lock, the
;  slide - is arithmetic on that number. There is no delay, no spin and
;  no sleep anywhere below, which is what makes the whole of it provable
;  at a desk with scripted clock values instead of a stopwatch.
;
;  TouchKeyboardRouteTouch() uses the last value tick was given, so the
;  service loop must tick at least once per pass before it drains touch.
;  That is one ordering rule, written here, rather than a second clock.
; ======================================================================


; ----------------------------------------------------------------------
;  THE SHARED INPUT-EVENT CONTRACT
;
;  The dispatcher lane owns the definitive file. These are its names at
;  its values; a duplicate definition of the same value is accepted, and
;  the gate asserts every number so a divergence is a failed assertion
;  rather than a silent disagreement about what Enter is.
; ----------------------------------------------------------------------
#AIE_TEXT     = 1
#AIE_KEY_DOWN = 2
#AIE_KEY_UP   = 3
#AIE_CANCEL   = 4

#AIK_ENTER          = 1
#AIK_BACKSPACE      = 2
#AIK_DELETE         = 3
#AIK_LEFT           = 4
#AIK_RIGHT          = 5
#AIK_HOME           = 6
#AIK_END            = 7
#AIK_TAB            = 8
#AIK_ESC            = 9
#AIK_CANCEL_COMMAND = 10

#AIS_PHYSICAL       = 1
#AIS_NETWORK        = 2
#AIS_TOUCH_KEYBOARD = 3

#AIM_SHIFT = 1
#AIM_CTRL  = 2

; ----------------------------------------------------------------------
;  THE HAL TOUCH RECORD
;
;  32 bytes, laid out by Anvil/Hal/hal.pbi as part of the portable
;  vocabulary. Only the first four fields are read here: x and y are
;  already screen pixels, the id is stable for one contact, and the
;  state is the four-valued phase. The controller's own tick stamp is
;  deliberately NOT used as this file's clock - see the clock note above.
;  The names are re-stated rather than depended on so this file compiles
;  with no board beneath it.
; ----------------------------------------------------------------------
#TK_EV_X  = 0
#TK_EV_Y  = 4
#TK_EV_ID = 8
#TK_EV_ST = 12

#TK_TOUCH_DOWN   = 0
#TK_TOUCH_MOVE   = 1
#TK_TOUCH_UP     = 2
#TK_TOUCH_CANCEL = 3

; ----------------------------------------------------------------------
;  SIZES. Every one of them is a fixed array; nothing here allocates.
; ----------------------------------------------------------------------
#TK_MAX_KEYS     = 128     ; the two pages use 97
#TK_PAGES        = 2
#TK_MAX_CONTACTS = 10      ; what the controller supports
#TK_QUEUE_MAX    = 64      ; the design's bounded keyboard queue

; ----------------------------------------------------------------------
;  TIMING, IN MILLISECONDS. Proposed interaction defaults, not measured
;  hardware figures, and not blocking waits.
; ----------------------------------------------------------------------
#TK_REPEAT_DELAY_MS    = 450
#TK_REPEAT_INTERVAL_MS = 50
#TK_CAPS_DOUBLE_MS     = 350
#TK_SLIDE_MS           = 110

; ----------------------------------------------------------------------
;  PAGES
; ----------------------------------------------------------------------
#TK_PAGE_ABC = 0
#TK_PAGE_SYM = 1

; ----------------------------------------------------------------------
;  WHAT A KEY IS
; ----------------------------------------------------------------------
#TK_KIND_CHAR  = 1     ; base/shift characters, emits #AIE_TEXT
#TK_KIND_KEY   = 2     ; a named key, emits #AIE_KEY_DOWN + #AIE_KEY_UP
#TK_KIND_SHIFT = 3     ; the Shift modifier
#TK_KIND_CTRL  = 4     ; the Ctrl modifier
#TK_KIND_PAGE  = 5     ; switch to the page in the key's base field
#TK_KIND_HIDE  = 6     ; the hide chevron - hides, and nothing else

; ----------------------------------------------------------------------
;  VISIBILITY
; ----------------------------------------------------------------------
#TK_STATE_HIDDEN  = 0
#TK_STATE_OPENING = 1
#TK_STATE_VISIBLE = 2
#TK_STATE_CLOSING = 3

; ----------------------------------------------------------------------
;  MODIFIER LATCHES. "Held" is a separate fact - a finger is physically
;  on the key right now - and is reported separately, because the design
;  requires one-shot, held and Caps Lock to look different on the glass.
; ----------------------------------------------------------------------
#TK_SHIFT_OFF     = 0
#TK_SHIFT_ONESHOT = 1
#TK_SHIFT_CAPS    = 2

#TK_CTRL_OFF     = 0
#TK_CTRL_ONESHOT = 1

; ----------------------------------------------------------------------
;  WHY EVERYTHING WAS CANCELLED. Carried in the Code field of the
;  #AIE_CANCEL event, so a consumer can say which of these happened.
;  NONE of them means "clear the command line" - they mean "drop the
;  capture and the in-flight contacts this source owns".
; ----------------------------------------------------------------------
#TK_CANCEL_TOUCH      = 1   ; the controller sent CANCEL
#TK_CANCEL_HIDDEN     = 2   ; the keyboard started closing
#TK_CANCEL_GENERATION = 3   ; the focus generation changed underneath us
#TK_CANCEL_OVERFLOW   = 4   ; the event queue filled
#TK_CANCEL_CONTACTS   = 5   ; more than ten contacts were routed here
#TK_CANCEL_CLIENT     = 6   ; the integration asked
#TK_CANCEL_VIEW       = 7   ; the view returned a key that does not exist

; ----------------------------------------------------------------------
;  ERRORS. Each one is a whole sentence with its number in it and the
;  first thing to check, because a bare code sends somebody to grep.
; ----------------------------------------------------------------------
#TK_ERR_NONE          = 0
#TK_ERR_QUEUE_FULL    = 1
#TK_ERR_CONTACTS_FULL = 2
#TK_ERR_BAD_KEY       = 3
#TK_ERR_TABLE_FULL    = 4
#TK_ERR_BAD_KIND      = 5
#TK_ERR_BAD_CHAR      = 6


; ----------------------------------------------------------------------
;  The one question this file asks the view. The whole file is read
;  before any code is generated, so the forward reference resolves
;  wherever the view is included; this line is here for the reader.
; ----------------------------------------------------------------------
Declare.i TouchKeyboardHitKey(x.i, y.i)


; ======================================================================
;  STATE
; ======================================================================

; The key tables, flat across both pages, built once by TouchKeyboardInit.
Global Dim gTkKeyPage.i[#TK_MAX_KEYS]
Global Dim gTkKeyRow.i[#TK_MAX_KEYS]
Global Dim gTkKeyCol.i[#TK_MAX_KEYS]
Global Dim gTkKeyUnits.i[#TK_MAX_KEYS]
Global Dim gTkKeyKind.i[#TK_MAX_KEYS]
Global Dim gTkKeyBase.i[#TK_MAX_KEYS]     ; char, key code, or target page
Global Dim gTkKeyShift.i[#TK_MAX_KEYS]    ; the shifted character, or 0
Global Dim gTkKeyLabel.i[#TK_MAX_KEYS]    ; a literal for named keys, 0 for characters
Global Dim gTkPageStart.i[#TK_PAGES + 1]
Global gTkKeyCount.i = 0
Global gTkBuilt.i = 0

; One two-byte label slot per key, so a character key's label is a
; stable pointer the view may hold while it draws the rest of the row.
Global Dim gTkLabelBuf.a[#TK_MAX_KEYS * 2]

; Column bookkeeping while the table is being built.
Global gTkBuildPage.i = -1
Global gTkBuildRow.i = -1
Global gTkBuildCol.i = 0

; Visibility. gTkDesired is the DESIRED FINAL STATE and it is the whole
; defence against a toggle race: Show and Hide write nothing but this,
; and the tick is the only writer of gTkState. Ten alternating taps
; between two ticks collapse to the last one instead of queueing ten
; transitions that then play out in order.
Global gTkState.i = #TK_STATE_HIDDEN
Global gTkDesired.i = #TK_STATE_HIDDEN
Global gTkTransitionMs.i = 0
Global gTkClient.i = 0
Global gTkSurface.i = 0

; Time, in milliseconds, as last given to TouchKeyboardTick.
Global gTkNow.i = 0
Global gTkTicked.i = 0

; Modifiers.
Global gTkShift.i = #TK_SHIFT_OFF
Global gTkCtrl.i = #TK_CTRL_OFF
Global gTkShiftHeld.i = 0          ; contacts physically on a Shift key
Global gTkCtrlHeld.i = 0
Global gTkShiftChord.i = 0         ; a held Shift has already modified a key
Global gTkCtrlChord.i = 0
Global gTkShiftTapMs.i = 0
Global gTkShiftTapSeen.i = 0

Global gTkPage.i = #TK_PAGE_ABC
Global gTkGeneration.i = 0

; Contacts, by stable id.
Global Dim gTkCtId.i[#TK_MAX_CONTACTS]
Global Dim gTkCtActive.i[#TK_MAX_CONTACTS]
Global Dim gTkCtKey.i[#TK_MAX_CONTACTS]      ; flat key index, or -1
Global Dim gTkCtPage.i[#TK_MAX_CONTACTS]
Global Dim gTkCtArmMs.i[#TK_MAX_CONTACTS]
Global Dim gTkCtShift.i[#TK_MAX_CONTACTS]    ; the chord snapshot
Global Dim gTkCtCtrl.i[#TK_MAX_CONTACTS]
Global Dim gTkCtCaps.i[#TK_MAX_CONTACTS]
Global Dim gTkCtReps.i[#TK_MAX_CONTACTS]     ; repeats emitted for this press
Global Dim gTkCtNextMs.i[#TK_MAX_CONTACTS]

; The emitted-event ring.
Global Dim gTkQKind.i[#TK_QUEUE_MAX]
Global Dim gTkQSource.i[#TK_QUEUE_MAX]
Global Dim gTkQCode.i[#TK_QUEUE_MAX]
Global Dim gTkQMods.i[#TK_QUEUE_MAX]
Global Dim gTkQGen.i[#TK_QUEUE_MAX]
Global Dim gTkQStamp.i[#TK_QUEUE_MAX]
Global gTkQHead.i = 0
Global gTkQTail.i = 0
Global gTkQCount.i = 0

; The event most recently popped.
Global gTkEvKind.i = 0
Global gTkEvSource.i = 0
Global gTkEvCode.i = 0
Global gTkEvMods.i = 0
Global gTkEvGen.i = 0
Global gTkEvStamp.i = 0

Global gTkErr.i = #TK_ERR_NONE
Global gTkDropped.i = 0            ; events the full ring refused


; ======================================================================
;  ERRORS - WHOLE SENTENCES
; ======================================================================
Procedure.i TouchKeyboardErr()
  ProcedureReturn gTkErr
EndProcedure

Procedure TouchKeyboardClearErr()
  gTkErr = #TK_ERR_NONE
EndProcedure

Procedure.i TouchKeyboardDropped()
  ProcedureReturn gTkDropped
EndProcedure

Procedure.i TouchKeyboardErrText()
  Select gTkErr
    Case #TK_ERR_NONE
      ProcedureReturn "The touch keyboard has reported no error."
    Case #TK_ERR_QUEUE_FULL
      ProcedureReturn "Touch keyboard error 1: the 64-event keyboard queue was already full when a key committed, so that key was refused rather than dropped in silence, and every contact, modifier and repeat has been cancelled; check that the service loop drains TouchKeyboardPop on every pass."
    Case #TK_ERR_CONTACTS_FULL
      ProcedureReturn "Touch keyboard error 2: an eleventh simultaneous contact was routed to the keyboard, which is one more than the controller supports, so it was refused and every contact, modifier and repeat has been cancelled; check that the dispatcher delivers an UP or a CANCEL for every contact it starts."
    Case #TK_ERR_BAD_KEY
      ProcedureReturn "Touch keyboard error 3: the view's hit test returned a key index that does not exist on the current page, so the touch was refused and everything in flight was cancelled; check that TouchKeyboardHitKey returns an index below TouchKeyboardKeyCount for the page the model is on."
    Case #TK_ERR_TABLE_FULL
      ProcedureReturn "Touch keyboard error 4: the key tables did not fit in the fixed 128-key array, so the keyboard is incomplete and must not be shown; raise TK_MAX_KEYS to match the layout that was added."
    Case #TK_ERR_BAD_KIND
      ProcedureReturn "Touch keyboard error 5: a key in the table has a kind this file does not implement, so it was refused instead of guessed at; every key must be one of the six TK_KIND values."
    Case #TK_ERR_BAD_CHAR
      ProcedureReturn "Touch keyboard error 6: a character key resolved to a code outside printable ASCII 32..126, which this keyboard never emits, so the keystroke was refused; check the page tables for a base or shifted character that is not printable."
  EndSelect
  ProcedureReturn "The touch keyboard reported an error number this build has no sentence for, which is itself a defect; check TouchKeyboardErrText against the TK_ERR list."
EndProcedure


; ======================================================================
;  BUILDING THE PAGES
; ======================================================================
;  The tables are written as data, in the wireframe's order, and the
;  only thing the code below knows about a key is its kind. There is no
;  branch anywhere in this file on "is this the Enter key".
;
;  EVERY CHARACTER KEY CARRIES BOTH ITS CHARACTERS. Where the pair is a
;  US keyboard's pair - 2 and @, [ and {, ; and : - the pair IS the US
;  keyboard's, so Shift means on this glass what it means on a desk. The
;  symbol page also carries a row of characters that are their own
;  shifted form, which is not an exception in the code: it is a table
;  entry whose two characters happen to be the same one, and it exists
;  because a command line types < > | & * ? ~ constantly and a symbol
;  page that still demanded Shift for them would be a worse keyboard.
; ----------------------------------------------------------------------

Procedure TkAddKey(page.i, row.i, units.i, kind.i, base.i, shifted.i, *label)
  Define i.i
  If gTkKeyCount >= #TK_MAX_KEYS
    gTkErr = #TK_ERR_TABLE_FULL
    ProcedureReturn
  EndIf
  If page <> gTkBuildPage Or row <> gTkBuildRow
    gTkBuildPage = page
    gTkBuildRow = row
    gTkBuildCol = 0
  EndIf
  i = gTkKeyCount
  gTkKeyPage[i] = page
  gTkKeyRow[i] = row
  gTkKeyCol[i] = gTkBuildCol
  gTkKeyUnits[i] = units
  gTkKeyKind[i] = kind
  gTkKeyBase[i] = base
  gTkKeyShift[i] = shifted
  gTkKeyLabel[i] = *label
  gTkBuildCol = gTkBuildCol + 1
  gTkKeyCount = gTkKeyCount + 1
EndProcedure

; One unit-wide character keys, taken from two equal-length strings.
; The pair of strings IS the page table for that run of keys, which is
; why the rows below read like the wireframe they came from.
Procedure TkAddChars(page.i, row.i, *bases, *shifts)
  Define n.i
  Define b.i
  Define s.i
  n = 0
  While PeekA(*bases + n) <> 0
    b = PeekA(*bases + n)
    s = PeekA(*shifts + n)
    If s = 0
      s = b
    EndIf
    TkAddKey(page, row, 1, #TK_KIND_CHAR, b, s, 0)
    n = n + 1
  Wend
EndProcedure

; The utility row is identical on every page - same keys, same order,
; same widths - because a row that moves between pages is a row whose
; Backspace is somewhere else every time the user switches.
Procedure TkAddUtilityRow(page.i)
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_ESC,    0, "Esc")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_TAB,    0, "Tab")
  TkAddKey(page, 0, 1, #TK_KIND_CTRL, 0,           0, "Ctrl")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_HOME,   0, "Home")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_LEFT,   0, "<-")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_RIGHT,  0, "->")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_END,    0, "End")
  TkAddKey(page, 0, 1, #TK_KIND_KEY,  #AIK_DELETE, 0, "Del")
  TkAddKey(page, 0, 2, #TK_KIND_HIDE, 0,           0, "hide v")
EndProcedure

Procedure TouchKeyboardInit()
  Define p.i
  If gTkBuilt <> 0
    ProcedureReturn
  EndIf
  gTkBuilt = 1
  gTkKeyCount = 0
  gTkBuildPage = -1
  gTkBuildRow = -1
  gTkBuildCol = 0

  ; ---------------- page 0: ABC ----------------
  gTkPageStart[#TK_PAGE_ABC] = gTkKeyCount
  TkAddUtilityRow(#TK_PAGE_ABC)
  TkAddChars(#TK_PAGE_ABC, 1, "1234567890", "!@#$%^&*()")
  TkAddChars(#TK_PAGE_ABC, 2, "qwertyuiop", "QWERTYUIOP")
  TkAddChars(#TK_PAGE_ABC, 3, "asdfghjkl",  "ASDFGHJKL")
  TkAddKey(#TK_PAGE_ABC, 4, 1, #TK_KIND_SHIFT, 0, 0, "Shift")
  TkAddChars(#TK_PAGE_ABC, 4, "zxcvbnm", "ZXCVBNM")
  TkAddKey(#TK_PAGE_ABC, 4, 2, #TK_KIND_KEY, #AIK_BACKSPACE, 0, "Backspace")
  TkAddKey(#TK_PAGE_ABC, 5, 2, #TK_KIND_PAGE, #TK_PAGE_SYM, 0, "?123")
  TkAddKey(#TK_PAGE_ABC, 5, 1, #TK_KIND_CHAR, 47, 63, 0)      ; /  ?
  TkAddKey(#TK_PAGE_ABC, 5, 1, #TK_KIND_CHAR, 46, 62, 0)      ; .  >
  TkAddKey(#TK_PAGE_ABC, 5, 3, #TK_KIND_CHAR, 32, 32, "Space")
  TkAddKey(#TK_PAGE_ABC, 5, 1, #TK_KIND_CHAR, 45, 95, 0)      ; -  _
  TkAddKey(#TK_PAGE_ABC, 5, 2, #TK_KIND_KEY, #AIK_ENTER, 0, "Enter")

  ; ---------------- page 1: ?123 ----------------
  gTkPageStart[#TK_PAGE_SYM] = gTkKeyCount
  TkAddUtilityRow(#TK_PAGE_SYM)
  TkAddChars(#TK_PAGE_SYM, 1, "1234567890", "!@#$%^&*()")
  ; The eight US punctuation keys the letter page has no room for, in
  ; their US pairs. These eight are what make all 95 printable
  ; characters reachable; the gate proves that rather than asserting it.
  TkAddChars(#TK_PAGE_SYM, 2, "`-=[]", "~_+{}")
  TkAddKey(#TK_PAGE_SYM, 2, 1, #TK_KIND_CHAR, 92, 124, 0)     ; \  |
  TkAddChars(#TK_PAGE_SYM, 2, ";", ":")
  TkAddKey(#TK_PAGE_SYM, 2, 1, #TK_KIND_CHAR, 39, 34, 0)      ; '  "
  TkAddChars(#TK_PAGE_SYM, 2, ",.", "<>")
  TkAddKey(#TK_PAGE_SYM, 3, 1, #TK_KIND_SHIFT, 0, 0, "Shift")
  TkAddChars(#TK_PAGE_SYM, 3, "<>|&*?~", "<>|&*?~")
  TkAddKey(#TK_PAGE_SYM, 3, 2, #TK_KIND_KEY, #AIK_BACKSPACE, 0, "Backspace")
  TkAddKey(#TK_PAGE_SYM, 4, 2, #TK_KIND_PAGE, #TK_PAGE_ABC, 0, "ABC")
  TkAddKey(#TK_PAGE_SYM, 4, 1, #TK_KIND_CHAR, 47, 63, 0)      ; /  ?
  TkAddKey(#TK_PAGE_SYM, 4, 1, #TK_KIND_CHAR, 58, 58, 0)      ; :
  TkAddKey(#TK_PAGE_SYM, 4, 3, #TK_KIND_CHAR, 32, 32, "Space")
  TkAddKey(#TK_PAGE_SYM, 4, 1, #TK_KIND_CHAR, 36, 36, 0)      ; $
  TkAddKey(#TK_PAGE_SYM, 4, 2, #TK_KIND_KEY, #AIK_ENTER, 0, "Enter")

  gTkPageStart[#TK_PAGES] = gTkKeyCount
EndProcedure

Procedure TkEnsure()
  If gTkBuilt = 0
    TouchKeyboardInit()
  EndIf
EndProcedure


; ======================================================================
;  THE MODEL, AS THE VIEW READS IT
; ======================================================================

Procedure.i TouchKeyboardPage()
  ProcedureReturn gTkPage
EndProcedure

Procedure.i TouchKeyboardKeyCount()
  TkEnsure()
  ProcedureReturn gTkPageStart[gTkPage + 1] - gTkPageStart[gTkPage]
EndProcedure

; Page-relative index to flat index. -1 for anything out of range, so a
; caller that is confused gets a refusal rather than another page's key.
Procedure.i TkFlat(index.i)
  TkEnsure()
  If index < 0
    ProcedureReturn -1
  EndIf
  If index >= (gTkPageStart[gTkPage + 1] - gTkPageStart[gTkPage])
    ProcedureReturn -1
  EndIf
  ProcedureReturn gTkPageStart[gTkPage] + index
EndProcedure

Procedure.i TouchKeyboardKeyKind(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn gTkKeyKind[f]
EndProcedure

Procedure.i TouchKeyboardKeyRow(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn gTkKeyRow[f]
EndProcedure

Procedure.i TouchKeyboardKeyColumn(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn gTkKeyCol[f]
EndProcedure

Procedure.i TouchKeyboardKeyWidthUnits(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn gTkKeyUnits[f]
EndProcedure

Procedure.i TouchKeyboardRowCount()
  Define i.i
  Define n.i
  TkEnsure()
  n = 0
  For i = gTkPageStart[gTkPage] To gTkPageStart[gTkPage + 1] - 1
    If gTkKeyRow[i] >= n
      n = gTkKeyRow[i] + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; The character a key would produce under a given modifier snapshot.
; THE US RULE, WRITTEN ONCE: Shift picks the key's other character;
; Caps Lock is letters only, and a letter under both is lower case
; again, exactly as it is on a desk.
Procedure.i TkEffChar(f.i, shift.i, caps.i)
  Define b.i
  Define up.i
  b = gTkKeyBase[f]
  If b >= 97 And b <= 122
    up = 0
    If shift <> 0
      up = 1
    EndIf
    If caps <> 0
      If up <> 0
        up = 0
      Else
        up = 1
      EndIf
    EndIf
    If up <> 0
      ProcedureReturn gTkKeyShift[f]
    EndIf
    ProcedureReturn b
  EndIf
  If shift <> 0
    ProcedureReturn gTkKeyShift[f]
  EndIf
  ProcedureReturn b
EndProcedure

Procedure.i TkShiftNow()
  If gTkShiftHeld > 0
    ProcedureReturn 1
  EndIf
  If gTkShift = #TK_SHIFT_ONESHOT
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i TkCtrlNow()
  If gTkCtrlHeld > 0
    ProcedureReturn 1
  EndIf
  If gTkCtrl = #TK_CTRL_ONESHOT
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i TkCapsNow()
  If gTkShift = #TK_SHIFT_CAPS
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; The label the view draws. A character key's label is the character it
; would produce RIGHT NOW, so a latched Shift is visible on every key
; and not only on the Shift key itself. The buffer is per key, so the
; view may collect a whole row of pointers before it draws any of them.
Procedure.i TouchKeyboardKeyLabel(index.i)
  Define f.i
  Define p.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn "?"
  EndIf
  If gTkKeyLabel[f] <> 0
    ProcedureReturn gTkKeyLabel[f]
  EndIf
  p = @gTkLabelBuf[0] + f * 2
  PokeA(p, TkEffChar(f, TkShiftNow(), TkCapsNow()))
  PokeA(p + 1, 0)
  ProcedureReturn p
EndProcedure


; ======================================================================
;  THE EVENT RING
; ======================================================================

Procedure.i TkPush(kind.i, code.i, mods.i)
  Define slot.i
  Define room.i
  ; The last slot belongs to the cancellation a full queue forces. An
  ; ordinary event is refused one short of the end so that cancellation
  ; can always be delivered - the design's rule is that a key-UP is
  ; never silently dropped, and a refusal that is reported is not a drop.
  room = #TK_QUEUE_MAX - 1
  If kind = #AIE_CANCEL
    room = #TK_QUEUE_MAX
  EndIf
  If gTkQCount >= room
    gTkDropped = gTkDropped + 1
    ProcedureReturn 0
  EndIf
  slot = gTkQHead
  gTkQKind[slot] = kind
  gTkQSource[slot] = #AIS_TOUCH_KEYBOARD
  gTkQCode[slot] = code
  gTkQMods[slot] = mods
  gTkQGen[slot] = gTkGeneration
  gTkQStamp[slot] = gTkNow
  gTkQHead = slot + 1
  If gTkQHead >= #TK_QUEUE_MAX
    gTkQHead = 0
  EndIf
  gTkQCount = gTkQCount + 1
  ProcedureReturn 1
EndProcedure

Procedure.i TouchKeyboardQueued()
  ProcedureReturn gTkQCount
EndProcedure

Procedure.i TouchKeyboardPop()
  Define slot.i
  If gTkQCount <= 0
    ProcedureReturn 0
  EndIf
  slot = gTkQTail
  gTkEvKind = gTkQKind[slot]
  gTkEvSource = gTkQSource[slot]
  gTkEvCode = gTkQCode[slot]
  gTkEvMods = gTkQMods[slot]
  gTkEvGen = gTkQGen[slot]
  gTkEvStamp = gTkQStamp[slot]
  gTkQTail = slot + 1
  If gTkQTail >= #TK_QUEUE_MAX
    gTkQTail = 0
  EndIf
  gTkQCount = gTkQCount - 1
  ProcedureReturn 1
EndProcedure

Procedure.i TouchKeyboardEventKind()
  ProcedureReturn gTkEvKind
EndProcedure
Procedure.i TouchKeyboardEventSource()
  ProcedureReturn gTkEvSource
EndProcedure
Procedure.i TouchKeyboardEventCode()
  ProcedureReturn gTkEvCode
EndProcedure
Procedure.i TouchKeyboardEventModifiers()
  ProcedureReturn gTkEvMods
EndProcedure
Procedure.i TouchKeyboardEventGeneration()
  ProcedureReturn gTkEvGen
EndProcedure
Procedure.i TouchKeyboardEventTimestamp()
  ProcedureReturn gTkEvStamp
EndProcedure


; ======================================================================
;  CONTACTS
; ======================================================================

Procedure.i TkFindContact(id.i)
  Define i.i
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0 And gTkCtId[i] = id
      ProcedureReturn i
    EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i TkAllocContact(id.i)
  Define i.i
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] = 0
      gTkCtActive[i] = 1
      gTkCtId[i] = id
      gTkCtKey[i] = -1
      gTkCtPage[i] = gTkPage
      gTkCtArmMs[i] = gTkNow
      gTkCtShift[i] = 0
      gTkCtCtrl[i] = 0
      gTkCtCaps[i] = 0
      gTkCtReps[i] = 0
      gTkCtNextMs[i] = 0
      ProcedureReturn i
    EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i TouchKeyboardContactCount()
  Define i.i
  Define n.i
  n = 0
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0
      n = n + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; Is this key already under another finger? A key is a key: a second
; contact on the same face is not a second press. This is the whole of
; why two fingers cannot submit two commands, and it is a rule about
; every key rather than a special case for Enter.
Procedure.i TkKeyHeldByOther(f.i, except.i)
  Define i.i
  For i = 0 To #TK_MAX_CONTACTS - 1
    If i <> except And gTkCtActive[i] <> 0 And gTkCtKey[i] = f
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure TkDisarm(c.i)
  Define f.i
  f = gTkCtKey[c]
  If f < 0
    ProcedureReturn
  EndIf
  If gTkKeyKind[f] = #TK_KIND_SHIFT And gTkShiftHeld > 0
    gTkShiftHeld = gTkShiftHeld - 1
  EndIf
  If gTkKeyKind[f] = #TK_KIND_CTRL And gTkCtrlHeld > 0
    gTkCtrlHeld = gTkCtrlHeld - 1
  EndIf
  gTkCtKey[c] = -1
  gTkCtReps[c] = 0
  gTkCtNextMs[c] = 0
EndProcedure

Procedure TkClearContact(c.i)
  TkDisarm(c)
  gTkCtActive[c] = 0
  gTkCtId[c] = 0
EndProcedure

; Arm a key under a contact and SNAPSHOT THE CHORD. The snapshot is the
; point: a user who presses Shift, presses A, then lifts Shift before A
; meant an upper-case A, and the order two fingers happen to leave the
; glass in is not a thing anybody types on purpose.
Procedure TkArm(c.i, f.i)
  Define kind.i
  If f < 0
    ProcedureReturn
  EndIf
  If TkKeyHeldByOther(f, c) <> 0
    gTkCtKey[c] = -1
    ProcedureReturn
  EndIf
  kind = gTkKeyKind[f]
  gTkCtKey[c] = f
  gTkCtPage[c] = gTkPage
  gTkCtArmMs[c] = gTkNow
  gTkCtReps[c] = 0
  gTkCtNextMs[c] = 0
  gTkCtShift[c] = TkShiftNow()
  gTkCtCtrl[c] = TkCtrlNow()
  gTkCtCaps[c] = TkCapsNow()
  If kind = #TK_KIND_SHIFT
    gTkShiftHeld = gTkShiftHeld + 1
    ProcedureReturn
  EndIf
  If kind = #TK_KIND_CTRL
    gTkCtrlHeld = gTkCtrlHeld + 1
    ProcedureReturn
  EndIf
  If kind = #TK_KIND_CHAR Or kind = #TK_KIND_KEY
    ; A held modifier that has now modified something is SPENT: lifting
    ; it must not leave a one-shot armed behind it, or every chord would
    ; capitalise the letter after it too.
    If gTkShiftHeld > 0
      gTkShiftChord = 1
    EndIf
    If gTkCtrlHeld > 0
      gTkCtrlChord = 1
    EndIf
    ; A one-shot is consumed by the key it arms, not by the key that
    ; commits: two fingers landing while one Shift is armed must not
    ; both come out upper case.
    If gTkShift = #TK_SHIFT_ONESHOT
      gTkShift = #TK_SHIFT_OFF
      gTkShiftTapSeen = 0
    EndIf
    If gTkCtrl = #TK_CTRL_ONESHOT
      gTkCtrl = #TK_CTRL_OFF
    EndIf
  EndIf
EndProcedure


; ======================================================================
;  CANCELLATION - THE ONE PLACE NOTHING IS LEFT STUCK
; ======================================================================
Procedure TouchKeyboardCancelAll(reason.i)
  Define i.i
  Define had.i
  had = 0
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0
      had = 1
      TkClearContact(i)
    EndIf
  Next
  gTkShift = #TK_SHIFT_OFF
  gTkCtrl = #TK_CTRL_OFF
  gTkShiftHeld = 0
  gTkCtrlHeld = 0
  gTkShiftChord = 0
  gTkCtrlChord = 0
  gTkShiftTapSeen = 0
  ; ONLY a real capture produces a cancellation event. Hiding a keyboard
  ; nobody is touching must not send the focused editor anything at all:
  ; opening and closing this keyboard never clears the command, and an
  ; event that a consumer might read as "drop what you were doing" is
  ; exactly how that promise gets broken by accident.
  If had <> 0
    TkPush(#AIE_CANCEL, reason, 0)
  EndIf
EndProcedure


; ======================================================================
;  EMISSION
; ======================================================================

Procedure TkOverflow()
  gTkErr = #TK_ERR_QUEUE_FULL
  TouchKeyboardCancelAll(#TK_CANCEL_OVERFLOW)
EndProcedure

; TEXT carries the CHARACTER and not the Shift that made it. The shift
; is already inside the character; reporting it as well invites an
; editor to apply it twice. Ctrl is different - it is not folded into
; any character - so it is reported.
Procedure TkEmitText(code.i, mods.i)
  If code < 32 Or code > 126
    gTkErr = #TK_ERR_BAD_CHAR
    ProcedureReturn
  EndIf
  If TkPush(#AIE_TEXT, code, mods) = 0
    TkOverflow()
  EndIf
EndProcedure

; A named key is a DOWN and an UP, always as a pair and always in the
; same call. A repeat is another pair. Nothing in this file can leave a
; key down, because nothing in this file ever sends a DOWN on its own.
Procedure TkEmitKey(code.i, mods.i)
  If TkPush(#AIE_KEY_DOWN, code, mods) = 0
    TkOverflow()
    ProcedureReturn
  EndIf
  If TkPush(#AIE_KEY_UP, code, mods) = 0
    TkOverflow()
  EndIf
EndProcedure


; ======================================================================
;  MODIFIER TAPS
; ======================================================================

Procedure TkShiftTapped()
  ; A Shift that has already modified another finger's key is spent.
  If gTkShiftChord <> 0
    gTkShiftChord = 0
    gTkShift = #TK_SHIFT_OFF
    gTkShiftTapSeen = 0
    ProcedureReturn
  EndIf
  If gTkShift = #TK_SHIFT_CAPS
    gTkShift = #TK_SHIFT_OFF
    gTkShiftTapSeen = 0
    ProcedureReturn
  EndIf
  If gTkShift = #TK_SHIFT_ONESHOT
    If gTkShiftTapSeen <> 0 And (gTkNow - gTkShiftTapMs) <= #TK_CAPS_DOUBLE_MS
      gTkShift = #TK_SHIFT_CAPS
    Else
      gTkShift = #TK_SHIFT_OFF
    EndIf
    gTkShiftTapMs = gTkNow
    gTkShiftTapSeen = 1
    ProcedureReturn
  EndIf
  gTkShift = #TK_SHIFT_ONESHOT
  gTkShiftTapMs = gTkNow
  gTkShiftTapSeen = 1
EndProcedure

Procedure TkCtrlTapped()
  If gTkCtrlChord <> 0
    gTkCtrlChord = 0
    gTkCtrl = #TK_CTRL_OFF
    ProcedureReturn
  EndIf
  If gTkCtrl = #TK_CTRL_ONESHOT
    gTkCtrl = #TK_CTRL_OFF
    ProcedureReturn
  EndIf
  gTkCtrl = #TK_CTRL_ONESHOT
EndProcedure


; ======================================================================
;  PAGES
; ======================================================================
;  Switching a page invalidates every armed key, because an index is an
;  index into the page it was taken from. Disarming rather than
;  cancelling keeps a latched Shift alive across the switch, which is
;  what a user who pressed Shift and then went looking for a brace meant.
Procedure TkSetPage(page.i)
  Define i.i
  If page < 0 Or page >= #TK_PAGES
    gTkErr = #TK_ERR_BAD_KEY
    ProcedureReturn
  EndIf
  If page = gTkPage
    ProcedureReturn
  EndIf
  gTkPage = page
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0
      TkDisarm(i)
    EndIf
  Next
EndProcedure


; ======================================================================
;  VISIBILITY
; ======================================================================

Procedure TouchKeyboardShow(clientId.i, surfaceId.i)
  TkEnsure()
  gTkClient = clientId
  gTkSurface = surfaceId
  gTkDesired = #TK_STATE_VISIBLE
EndProcedure

Procedure TouchKeyboardHide()
  gTkDesired = #TK_STATE_HIDDEN
EndProcedure

Procedure.i TouchKeyboardState()
  ProcedureReturn gTkState
EndProcedure

Procedure.i TouchKeyboardDesiredState()
  ProcedureReturn gTkDesired
EndProcedure

Procedure.i TouchKeyboardClient()
  ProcedureReturn gTkClient
EndProcedure

Procedure.i TouchKeyboardSurface()
  ProcedureReturn gTkSurface
EndProcedure

; How far through the slide, in parts per thousand, so the view can
; interpolate without owning a second clock. 1000 whenever the keyboard
; is fully visible, 0 whenever it is fully hidden.
Procedure.i TouchKeyboardSlidePermille()
  Define e.i
  Select gTkState
    Case #TK_STATE_VISIBLE
      ProcedureReturn 1000
    Case #TK_STATE_HIDDEN
      ProcedureReturn 0
  EndSelect
  e = gTkNow - gTkTransitionMs
  If e < 0
    e = 0
  EndIf
  If e > #TK_SLIDE_MS
    e = #TK_SLIDE_MS
  EndIf
  If gTkState = #TK_STATE_OPENING
    ProcedureReturn (e * 1000) / #TK_SLIDE_MS
  EndIf
  ProcedureReturn 1000 - (e * 1000) / #TK_SLIDE_MS
EndProcedure


; ======================================================================
;  FOCUS GENERATION
; ======================================================================
;  The dispatcher owns the generation; the integration hands this file
;  the current value beside the tick. A change means the focused client
;  went away underneath us, and everything in flight belongs to a client
;  that is not there any more.
Procedure TouchKeyboardSetGeneration(gen.i)
  If gen = gTkGeneration
    ProcedureReturn
  EndIf
  TouchKeyboardCancelAll(#TK_CANCEL_GENERATION)
  gTkGeneration = gen
EndProcedure

Procedure.i TouchKeyboardGeneration()
  ProcedureReturn gTkGeneration
EndProcedure


; ======================================================================
;  COMMITTING A KEY
; ======================================================================
Procedure TkCommit(c.i)
  Define f.i
  Define kind.i
  Define mods.i
  Define ch.i
  f = gTkCtKey[c]
  If f < 0
    ProcedureReturn
  EndIf
  kind = gTkKeyKind[f]
  mods = 0
  If gTkCtCtrl[c] <> 0
    mods = mods | #AIM_CTRL
  EndIf
  Select kind
    Case #TK_KIND_CHAR
      ch = TkEffChar(f, gTkCtShift[c], gTkCtCaps[c])
      If gTkCtCtrl[c] <> 0 And (ch = 99 Or ch = 67)
        ; Ctrl+C is the cancel the whole monitor already understands, not
        ; the letter C with a bit set beside it. It is named, so nothing
        ; downstream has to recognise a letter to know what happened.
        If gTkCtShift[c] <> 0
          mods = mods | #AIM_SHIFT
        EndIf
        TkEmitKey(#AIK_CANCEL_COMMAND, mods)
        ProcedureReturn
      EndIf
      TkEmitText(ch, mods)
    Case #TK_KIND_KEY
      If gTkCtShift[c] <> 0
        mods = mods | #AIM_SHIFT
      EndIf
      TkEmitKey(gTkKeyBase[f], mods)
    Case #TK_KIND_SHIFT
      TkShiftTapped()
    Case #TK_KIND_CTRL
      TkCtrlTapped()
    Case #TK_KIND_PAGE
      TkSetPage(gTkKeyBase[f])
    Case #TK_KIND_HIDE
      TouchKeyboardHide()
    Default
      gTkErr = #TK_ERR_BAD_KIND
  EndSelect
EndProcedure

; Only four keys repeat, and they are the four where holding means
; "keep going": the two deletions and the two arrows. A letter that
; repeated would turn a slow finger into a stutter, and an Enter that
; repeated would submit a command twice.
Procedure.i TkRepeatable(f.i)
  If f < 0
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] <> #TK_KIND_KEY
    ProcedureReturn 0
  EndIf
  Select gTkKeyBase[f]
    Case #AIK_BACKSPACE
      ProcedureReturn 1
    Case #AIK_DELETE
      ProcedureReturn 1
    Case #AIK_LEFT
      ProcedureReturn 1
    Case #AIK_RIGHT
      ProcedureReturn 1
  EndSelect
  ProcedureReturn 0
EndProcedure


; ======================================================================
;  ARMED AND LATCHED, FOR THE VIEW
; ======================================================================
Procedure.i TouchKeyboardKeyIsArmed(index.i)
  Define f.i
  Define i.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn 0
  EndIf
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0 And gTkCtKey[i] = f
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; Latched is what the user must be able to SEE: 1 for a one-shot, 2 for
; Caps Lock, 3 for a modifier a finger is physically holding. Three
; different numbers because the design requires three different looks.
Procedure.i TouchKeyboardKeyIsLatched(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] = #TK_KIND_SHIFT
    If gTkShiftHeld > 0
      ProcedureReturn 3
    EndIf
    If gTkShift = #TK_SHIFT_CAPS
      ProcedureReturn 2
    EndIf
    If gTkShift = #TK_SHIFT_ONESHOT
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] = #TK_KIND_CTRL
    If gTkCtrlHeld > 0
      ProcedureReturn 3
    EndIf
    If gTkCtrl = #TK_CTRL_ONESHOT
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] = #TK_KIND_PAGE
    If gTkKeyBase[f] = gTkPage
      ProcedureReturn 1
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  TouchKeyboardKeyIsAccent - is this key drawn in the accent colour?
;
;  THE EIGHTH ACCESSOR THE VIEW ASKS FOR, and it is the MODEL's answer
;  because the accent is a statement about what a key MEANS and not
;  about where it is. The design names exactly two things that get it:
;  "an accent for Enter and active modifiers".
;
;  ENTER IS ALWAYS ACCENTED because Enter is always the key that ends
;  the command, whatever the keyboard is doing. A MODIFIER IS ACCENTED
;  ONLY WHILE IT IS ACTUALLY DOING SOMETHING - a one-shot Shift, Caps
;  Lock, a physically held Shift, an armed Ctrl - so the accent is a
;  reading of the state and never decoration. A modifier that is off
;  looks like every other key, which is what makes the ones that are on
;  worth looking at.
;
;  IT IS COMPUTED FROM THE SAME THREE GLOBALS TouchKeyboardKeyIsLatched
;  reads, not from a parallel flag, so the two can never disagree about
;  whether Shift is on.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardKeyIsAccent(index.i)
  Define f.i
  f = TkFlat(index)
  If f < 0
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] = #TK_KIND_KEY And gTkKeyBase[f] = #AIK_ENTER
    ProcedureReturn 1
  EndIf
  If gTkKeyKind[f] = #TK_KIND_SHIFT
    If TkShiftNow() <> 0 Or TkCapsNow() <> 0
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  If gTkKeyKind[f] = #TK_KIND_CTRL
    If TkCtrlNow() <> 0
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i TouchKeyboardShiftState()
  ProcedureReturn gTkShift
EndProcedure

Procedure.i TouchKeyboardShiftHeld()
  ProcedureReturn gTkShiftHeld
EndProcedure

Procedure.i TouchKeyboardCtrlState()
  ProcedureReturn gTkCtrl
EndProcedure

Procedure.i TouchKeyboardCtrlHeld()
  ProcedureReturn gTkCtrlHeld
EndProcedure


; ======================================================================
;  THE TICK
; ======================================================================
;  One writer of gTkState, one writer of gTkNow, and no loop in here
;  whose length depends on anything but the fixed contact array. At most
;  ONE repeat is emitted per contact per tick: a service loop that
;  stalled for two seconds must not then delete forty characters in one
;  pass, and bounding it here is what keeps a held Backspace from
;  starving the network the monitor is also servicing.
; ----------------------------------------------------------------------
Procedure TouchKeyboardTick(now.i)
  Define i.i
  Define e.i
  Define left.i
  TkEnsure()
  gTkNow = now
  gTkTicked = 1

  ; --- the visibility machine, reconciled against the desired state ---
  If gTkState = #TK_STATE_OPENING
    If gTkDesired = #TK_STATE_HIDDEN
      e = now - gTkTransitionMs
      If e < 0
        e = 0
      EndIf
      If e > #TK_SLIDE_MS
        e = #TK_SLIDE_MS
      EndIf
      left = #TK_SLIDE_MS - e
      gTkState = #TK_STATE_CLOSING
      gTkTransitionMs = now - left
      TouchKeyboardCancelAll(#TK_CANCEL_HIDDEN)
    ElseIf (now - gTkTransitionMs) >= #TK_SLIDE_MS
      gTkState = #TK_STATE_VISIBLE
    EndIf
  ElseIf gTkState = #TK_STATE_CLOSING
    If gTkDesired = #TK_STATE_VISIBLE
      e = now - gTkTransitionMs
      If e < 0
        e = 0
      EndIf
      If e > #TK_SLIDE_MS
        e = #TK_SLIDE_MS
      EndIf
      left = #TK_SLIDE_MS - e
      gTkState = #TK_STATE_OPENING
      gTkTransitionMs = now - left
    ElseIf (now - gTkTransitionMs) >= #TK_SLIDE_MS
      gTkState = #TK_STATE_HIDDEN
    EndIf
  ElseIf gTkState = #TK_STATE_VISIBLE
    If gTkDesired = #TK_STATE_HIDDEN
      gTkState = #TK_STATE_CLOSING
      gTkTransitionMs = now
      TouchKeyboardCancelAll(#TK_CANCEL_HIDDEN)
    EndIf
  ElseIf gTkState = #TK_STATE_HIDDEN
    If gTkDesired = #TK_STATE_VISIBLE
      gTkState = #TK_STATE_OPENING
      gTkTransitionMs = now
    EndIf
  EndIf

  If gTkState <> #TK_STATE_VISIBLE
    ProcedureReturn
  EndIf

  ; --- repeat ---
  For i = 0 To #TK_MAX_CONTACTS - 1
    If gTkCtActive[i] <> 0 And TkRepeatable(gTkCtKey[i]) <> 0
      If gTkCtReps[i] = 0
        If (now - gTkCtArmMs[i]) >= #TK_REPEAT_DELAY_MS
          TkCommit(i)
          gTkCtReps[i] = 1
          gTkCtNextMs[i] = now + #TK_REPEAT_INTERVAL_MS
        EndIf
      ElseIf now >= gTkCtNextMs[i]
        TkCommit(i)
        gTkCtReps[i] = gTkCtReps[i] + 1
        gTkCtNextMs[i] = now + #TK_REPEAT_INTERVAL_MS
      EndIf
    EndIf
  Next
EndProcedure


; ======================================================================
;  ROUTING TOUCH
; ======================================================================
;  Returns 1 when the keyboard owned the event and 0 when it did not, so
;  the dispatcher knows whether to keep looking for a consumer. A DOWN
;  that hits no key is not ours and is not tracked, which is the whole
;  of "starting outside and sliding inside does not manufacture a
;  keypress": there is nothing to slide, because nothing was recorded.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardRouteTouch(*ev)
  Define x.i
  Define y.i
  Define id.i
  Define st.i
  Define hit.i
  Define c.i
  Define f.i

  TkEnsure()
  If *ev = 0
    ProcedureReturn 0
  EndIf
  x = PeekL(*ev + #TK_EV_X)
  y = PeekL(*ev + #TK_EV_Y)
  id = PeekL(*ev + #TK_EV_ID)
  st = PeekL(*ev + #TK_EV_ST)

  ; A CANCEL is the controller saying the stream is not trustworthy any
  ; more. Everything goes - contacts, modifiers, repeats - because the
  ; one thing that must never survive it is a Shift or a Backspace that
  ; nobody is holding.
  If st = #TK_TOUCH_CANCEL
    TouchKeyboardCancelAll(#TK_CANCEL_TOUCH)
    ProcedureReturn 1
  EndIf

  If gTkState <> #TK_STATE_VISIBLE
    ProcedureReturn 0
  EndIf

  c = TkFindContact(id)

  If st = #TK_TOUCH_DOWN
    If c >= 0
      ; A DOWN for an id already down means an UP was lost. Reconcile
      ; against what is true now rather than committing a key whose
      ; release was never seen.
      TkClearContact(c)
    EndIf
    hit = TouchKeyboardHitKey(x, y)
    If hit < 0
      ProcedureReturn 0
    EndIf
    If hit >= TouchKeyboardKeyCount()
      gTkErr = #TK_ERR_BAD_KEY
      TouchKeyboardCancelAll(#TK_CANCEL_VIEW)
      ProcedureReturn 1
    EndIf
    c = TkAllocContact(id)
    If c < 0
      gTkErr = #TK_ERR_CONTACTS_FULL
      TouchKeyboardCancelAll(#TK_CANCEL_CONTACTS)
      ProcedureReturn 1
    EndIf
    TkArm(c, gTkPageStart[gTkPage] + hit)
    ProcedureReturn 1
  EndIf

  If c < 0
    ProcedureReturn 0
  EndIf

  If st = #TK_TOUCH_MOVE
    hit = TouchKeyboardHitKey(x, y)
    If hit < 0
      TkDisarm(c)
      ProcedureReturn 1
    EndIf
    If hit >= TouchKeyboardKeyCount()
      gTkErr = #TK_ERR_BAD_KEY
      TouchKeyboardCancelAll(#TK_CANCEL_VIEW)
      ProcedureReturn 1
    EndIf
    f = gTkPageStart[gTkPage] + hit
    If f <> gTkCtKey[c]
      TkDisarm(c)
      TkArm(c, f)
    EndIf
    ProcedureReturn 1
  EndIf

  If st = #TK_TOUCH_UP
    ; A press that has already begun repeating has said what it had to
    ; say. Committing again on the release would delete one character
    ; more than the finger asked for, every time.
    If gTkCtKey[c] >= 0 And gTkCtReps[c] = 0
      TkCommit(c)
    EndIf
    TkClearContact(c)
    ProcedureReturn 1
  EndIf

  ProcedureReturn 0
EndProcedure
