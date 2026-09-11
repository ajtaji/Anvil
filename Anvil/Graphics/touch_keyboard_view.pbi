; ======================================================================
;  touch_keyboard_view.pbi - THE TOUCH KEYBOARD'S GEOMETRY AND DRAW LIST.
;
;  This file is PURE INTEGER ARITHMETIC. It touches no register, no
;  framebuffer, no GPU and no display library: every procedure here is a
;  function of its arguments and of one layout result. That is deliberate
;  and it is the same rule screen_geom.pi4 lives under - it is what lets
;  the emitted-code gate execute the shipped image of this file on a
;  machine that has no VideoCore, with an MMIO hard stop armed.
;
;  SO THE RULE FOR THIS FILE IS ONE LINE: if a procedure here ever needs a
;  register or a display primitive, it does not belong here.
;
;  WHAT IT OWNS
;    * ONE layout result - the keyboard band, every key's rectangle, the
;      down-chevron's rectangle and the keyboard button beside the prompt.
;      Hit testing and painting both read that one result, so a finger can
;      never land on geometry the picture was not drawn at.
;    * The density policy: a touch target is a PHYSICAL size. At least
;      0.32 inch, preferably 0.38 inch. When the screen can say how big it
;      is, those are computed from its pixels-to-the-inch. When it CANNOT,
;      this file is handed ppi = 0 and falls back to the existing explicit
;      display-scale policy - it never invents an inch measurement, and
;      TouchKeyboardDensityKnown() says which of the two happened.
;    * A DRAW LIST plus DIRTY RECTANGLES. Nothing here draws. The board
;      adapters walk the list through their own primitives - the CPU
;      renderer through display.pi4, the V3D renderer through NeonArcade -
;      so GPU and CPU drawing stay behind their rendering interfaces and
;      the keyboard never writes to a framebuffer a GPU frame owns.
;
;  WHAT IT DOES NOT OWN
;    Modifiers, repeat, pages, visibility transitions and emitted editor
;    events are Anvil/Core/touch_keyboard.pbi's. Touch routing, capture and
;    cancellation are the input dispatcher's. This file is asked what the
;    keys look like and where they are, and answers.
;
;  THE MODEL IS Anvil/Core/touch_keyboard.pbi AND THERE IS ONLY ONE OF IT.
;  A fenced placeholder model used to sit below, implementing the eight
;  accessors over a static table so that the monitor built before the
;  model existed. The model has landed, so the placeholder is gone: this
;  file now ASKS the real model for its keys and its labels, and the
;  character coverage contract is the model's alone. The accessors this
;  file calls are TouchKeyboardKeyCount, KeyRow, KeyColumn, KeyWidthUnits,
;  KeyKind, KeyLabel, KeyIsArmed, KeyIsLatched and KeyIsAccent.
;
;  THE HIDE CHEVRON IS THE MODEL'S HIDE KEY, laid out like every other
;  key and then published separately as TouchKeyboardHide{X,Y,W,H} so the
;  integration can ask "was this the chevron" without knowing what a key
;  kind is. It used to be a rectangle this file CARVED OUT of row 0 for
;  itself, which was right while the placeholder had no hide key and
;  became a second dismiss button the moment the real model - whose
;  utility row ends in one - arrived. One key, one rectangle, one label.
; ======================================================================

; ----------------------------------------------------------------------
;  Sizes. Fixed arrays, never an allocation: this runs on a monitor with
;  no allocator and a bounded frame budget.
; ----------------------------------------------------------------------
#TKB_MAX_KEYS   = 64
#TKB_MAX_ROWS   = 8
#TKB_MAX_DRAW   = 320
#TKB_MAX_DAMAGE = 72
#TKB_LABEL_MAX  = 12            ; bytes stored per label, NUL included
#TKB_ARENA      = 1024          ; sanitised label bytes for one paint

; One standard key is #TKB_UNIT width units, so a half-width key and a
; five-wide space bar are both whole numbers.
#TKB_UNIT = 4

; The touch target, in THOUSANDTHS OF AN INCH. 0.32 is the floor the
; design states and 0.38 is what it asks for where space permits.
#TKB_MIN_THOU  = 320
#TKB_PREF_THOU = 380

; The starting reservation, as a percentage of landscape screen height.
; It is a STARTING POINT and it loses to readability and to the minimum
; target: the band grows past it when six rows of 0.38 inch keys do not
; fit inside it, which on an 800 pixel tall console they do not.
#TKB_TARGET_PCT = 40

; The console viewport may never be reduced below this. The prompt row
; plus one line of what was above it.
#TKB_MIN_CONSOLE_ROWS = 2

; The built-in bitmap font, before magnification. Labels are rasterised
; at a WHOLE multiple of this and never by filtering an enlarged bitmap.
#TKB_FONT_W = 8
#TKB_FONT_H = 16
#TKB_SCALE_MAX = 8

; The fallback when the screen cannot say how big it is, expressed in the
; existing explicit display scale rather than in guessed inches: three
; text rows for the floor, three and a half for the preferred size.
#TKB_FALLBACK_MIN_PX  = 48
#TKB_FALLBACK_PREF_PX = 56

#TKB_GUTTER_MIN = 2
#TKB_PAD        = 2

; Draw item kinds.
#TKB_DRAW_RECT = 1
#TKB_DRAW_TEXT = 2

; Which adapter the list is being built for. The geometry is identical;
; the renderer id travels with the list so an adapter can assert it was
; handed its own list rather than the other one's.
#TKB_RENDER_CPU = 1
#TKB_RENDER_GPU = 2

; What a paint is allowed to touch.
#TKB_DAMAGE_ALL        = 0   ; the whole band - a first paint
#TKB_DAMAGE_CHANGED    = 1   ; the keys marked changed, and nothing else
#TKB_DAMAGE_TRANSITION = 2   ; the band rectangle - a show or a hide

; ----------------------------------------------------------------------
;  The palette, and every colour in it is one Anvil already draws.
;  $RRGGBB; the adapters pack it for their own surface (DisplayRGB on the
;  framebuffer, Neon_RGBA on the GPU), so this file states a colour and
;  never a pixel format.
;
;    ground   RGB(0,0,40)      - screen_cmd.pi4's gScreenBg
;    ink      RGB(226,232,240) - the console's text
;    dim ink  RGB(120,132,150) - the banner clock's
;    accent   $F09A32          - #CUR_COLOUR, the pointer's orange
; ----------------------------------------------------------------------
#TKB_C_BAND     = $000028
#TKB_C_FACE     = $16203C
#TKB_C_PRESS    = $32406E
#TKB_C_LATCH    = $6B4A16
#TKB_C_ACCENT   = $8A5A12
#TKB_C_EDGE     = $2E3A5C
#TKB_C_EDGEACC  = $F09A32
#TKB_C_INK      = $E2E8F0
#TKB_C_INKDIM   = $788496

; ----------------------------------------------------------------------
;  What the layout is asked about the surface. A structure and not eight
;  arguments, because the eight-argument ABI is exactly where a caller
;  starts dropping the one it thinks is obvious.
;
;    logicalW/H    the CONSOLE's own pixel geometry - already rotated and
;                  already scaled by the display/touch mapping. There is
;                  no second rotation here and there must never be one.
;    bannerH       the retained banner band's height; the console and the
;                  keyboard both live below it.
;    cellW/cellH   the console's character cell, magnification included.
;    ppi           pixels to the inch, or 0 for "the screen cannot say".
;                  Hand this 0 rather than an assumption; the caller is
;                  the only thing that knows whether it read or guessed.
;    displayScale  the magnification in force (>= 1).
; ----------------------------------------------------------------------
Structure TouchKeyboardMetrics
  logicalW.i
  logicalH.i
  bannerH.i
  cellW.i
  cellH.i
  ppi.i
  displayScale.i
EndStructure

; ---- the layout result ------------------------------------------------
Global gTkbOk.i = 0                   ; 1 when the result below is usable
Global gTkbGen.i = 0                  ; bumped by every install and reset
Global gTkbRefusal.i = 0              ; a whole sentence, or 0
Global gTkbVisible.i = 0              ; the band is on screen

Global gTkbLW.i = 0
Global gTkbLH.i = 0
Global gTkbBannerH.i = 0
Global gTkbCellW.i = 0
Global gTkbCellH.i = 0
Global gTkbPpi.i = 0
Global gTkbScale.i = 1
Global gTkbKnown.i = 0
Global gTkbSizeAdj.i = 100            ; per cent; the operator's adjustment

Global gTkbMinPx.i = 0
Global gTkbPrefPx.i = 0
Global gTkbGutter.i = 0

Global gTkbBandY.i = 0
Global gTkbBandH.i = 0
Global gTkbConsoleRows.i = 0
Global gTkbRows.i = 0
Global gTkbKeys.i = 0
Global gTkbSplit.i = 0                ; 1 when the utility row has to split

Global Dim gTkbKeyX.i[#TKB_MAX_KEYS]
Global Dim gTkbKeyY.i[#TKB_MAX_KEYS]
Global Dim gTkbKeyW.i[#TKB_MAX_KEYS]
Global Dim gTkbKeyH.i[#TKB_MAX_KEYS]
Global Dim gTkbKeyScale.i[#TKB_MAX_KEYS]
Global Dim gTkbKeyDirty.a[#TKB_MAX_KEYS]

Global Dim gTkbRowCount.i[#TKB_MAX_ROWS]
Global Dim gTkbRowUnits.i[#TKB_MAX_ROWS]
Global Dim gTkbRowY.i[#TKB_MAX_ROWS]
Global Dim gTkbRowH.i[#TKB_MAX_ROWS]

Global gTkbHideX.i = 0
Global gTkbHideY.i = 0
Global gTkbHideW.i = 0
Global gTkbHideH.i = 0
Global gTkbHideAt.i = -1              ; which key the chevron IS, or -1

; The prompt row, and the rectangle that owns touch while the band is
; down. THE DISPATCHER HOLDS ONE RECTANGLE PER OWNER, so the keyboard's
; rectangle is the band while it is up and this one while it is not:
; that is how a tap on the editable prompt line reaches the keyboard
; through the one dispatcher instead of through a second poll.
Global gTkbPromptY.i = 0
Global gTkbPromptH.i = 0
Global gTkbIdleY.i = 0
Global gTkbIdleH.i = 0

Global gTkbBtnX.i = 0
Global gTkbBtnY.i = 0
Global gTkbBtnYHidden.i = 0
Global gTkbBtnW.i = 0
Global gTkbBtnH.i = 0
Global gTkbBtnDirty.i = 0

; ---- the draw list ----------------------------------------------------
Global gTkbDrawN.i = 0
Global gTkbDrawFor.i = 0
Global Dim gTkbDrawKind.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawX.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawY.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawW.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawH.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawFg.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawBg.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawAux.i[#TKB_MAX_DRAW]
Global Dim gTkbDrawScale.i[#TKB_MAX_DRAW]

Global gTkbDamageN.i = 0
Global Dim gTkbDamX.i[#TKB_MAX_DAMAGE]
Global Dim gTkbDamY.i[#TKB_MAX_DAMAGE]
Global Dim gTkbDamW.i[#TKB_MAX_DAMAGE]
Global Dim gTkbDamH.i[#TKB_MAX_DAMAGE]

Global gTkbArenaAt.i = 0
Global Dim gTkbArena.a[#TKB_ARENA + 4]
Global gTkbOverflow.i = 0             ; a list or arena ran out - loud, never silent



; ----------------------------------------------------------------------
;  The size adjustment. It exists because a screen that cannot say how
;  big it is leaves the preferred target a policy rather than a
;  measurement, and the design asks for a way to correct that by hand.
;  It moves the PREFERRED size only: the 0.32 inch floor is a statement
;  about fingers and a typed number does not shrink one.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardSizeAdjust(pct.i)
  If pct < 50 Or pct > 200
    ProcedureReturn 0
  EndIf
  gTkbSizeAdj = pct
  ProcedureReturn 1
EndProcedure

Procedure.i TouchKeyboardSizeAdjustment()
  ProcedureReturn gTkbSizeAdj
EndProcedure

; ----------------------------------------------------------------------
;  TouchKeyboardLayoutInvalidate - the surface this geometry describes has
;  gone away (a rotation, a screen switch, a renderer reset, a console
;  geometry change). Everything derived from it is refused from here until
;  a new layout is installed, and the generation moves so a contact armed
;  against the old geometry can be recognised as stale rather than
;  delivered against the new one.
; ----------------------------------------------------------------------
Procedure TouchKeyboardLayoutInvalidate()
  gTkbOk = 0
  gTkbVisible = 0
  gTkbDrawN = 0
  gTkbDamageN = 0
  gTkbGen = gTkbGen + 1
EndProcedure

Procedure.i TouchKeyboardLayoutGeneration()
  ProcedureReturn gTkbGen
EndProcedure

Procedure.i TouchKeyboardLayoutOk()
  ProcedureReturn gTkbOk
EndProcedure

Procedure.i TouchKeyboardRefusal()
  ProcedureReturn gTkbRefusal
EndProcedure

Procedure TouchKeyboardViewSetVisible(v.i)
  gTkbVisible = Bool(v <> 0)
EndProcedure

Procedure.i TouchKeyboardViewVisible()
  ProcedureReturn gTkbVisible
EndProcedure

Procedure.i TouchKeyboardDensityKnown()
  ProcedureReturn gTkbKnown
EndProcedure
Procedure.i TouchKeyboardTargetMinPx()
  ProcedureReturn gTkbMinPx
EndProcedure
Procedure.i TouchKeyboardTargetPrefPx()
  ProcedureReturn gTkbPrefPx
EndProcedure
Procedure.i TouchKeyboardGutter()
  ProcedureReturn gTkbGutter
EndProcedure
Procedure.i TouchKeyboardBandX()
  ProcedureReturn 0
EndProcedure
Procedure.i TouchKeyboardBandY()
  ProcedureReturn gTkbBandY
EndProcedure
Procedure.i TouchKeyboardBandW()
  ProcedureReturn gTkbLW
EndProcedure
Procedure.i TouchKeyboardBandH()
  ProcedureReturn gTkbBandH
EndProcedure
Procedure.i TouchKeyboardConsoleRows()
  ProcedureReturn gTkbConsoleRows
EndProcedure
Procedure.i TouchKeyboardRows()
  ProcedureReturn gTkbRows
EndProcedure
Procedure.i TouchKeyboardKeys()
  ProcedureReturn gTkbKeys
EndProcedure
Procedure.i TouchKeyboardSplitUtilityRow()
  ProcedureReturn gTkbSplit
EndProcedure

Procedure.i TouchKeyboardKeyX(i.i)
  If i < 0 Or i >= gTkbKeys : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbKeyX[i]
EndProcedure
Procedure.i TouchKeyboardKeyY(i.i)
  If i < 0 Or i >= gTkbKeys : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbKeyY[i]
EndProcedure
Procedure.i TouchKeyboardKeyW(i.i)
  If i < 0 Or i >= gTkbKeys : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbKeyW[i]
EndProcedure
Procedure.i TouchKeyboardKeyH(i.i)
  If i < 0 Or i >= gTkbKeys : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbKeyH[i]
EndProcedure
Procedure.i TouchKeyboardKeyLabelScale(i.i)
  If i < 0 Or i >= gTkbKeys : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbKeyScale[i]
EndProcedure

Procedure.i TouchKeyboardHideX()
  ProcedureReturn gTkbHideX
EndProcedure
Procedure.i TouchKeyboardHideY()
  ProcedureReturn gTkbHideY
EndProcedure
Procedure.i TouchKeyboardHideW()
  ProcedureReturn gTkbHideW
EndProcedure
Procedure.i TouchKeyboardHideH()
  ProcedureReturn gTkbHideH
EndProcedure

; Which key the chevron is, so a caller that wants to know can ask rather
; than re-derive it from the kinds. -1 before anything is laid out.
Procedure.i TouchKeyboardHideKey()
  ProcedureReturn gTkbHideAt
EndProcedure

; The editable prompt line, and the rectangle that owns touch while the
; band is down. Both are full width: a finger aimed at a command line is
; aimed at a LINE, and asking it to find an eight pixel tall cell is the
; kind of target the density policy exists to refuse.
Procedure.i TouchKeyboardPromptX()
  ProcedureReturn 0
EndProcedure
Procedure.i TouchKeyboardPromptY()
  ProcedureReturn gTkbPromptY
EndProcedure
Procedure.i TouchKeyboardPromptW()
  ProcedureReturn gTkbLW
EndProcedure
Procedure.i TouchKeyboardPromptH()
  ProcedureReturn gTkbPromptH
EndProcedure
Procedure.i TouchKeyboardIdleX()
  ProcedureReturn 0
EndProcedure
Procedure.i TouchKeyboardIdleY()
  ProcedureReturn gTkbIdleY
EndProcedure
Procedure.i TouchKeyboardIdleW()
  ProcedureReturn gTkbLW
EndProcedure
Procedure.i TouchKeyboardIdleH()
  ProcedureReturn gTkbIdleH
EndProcedure

Procedure.i TouchKeyboardButtonX()
  ProcedureReturn gTkbBtnX
EndProcedure
Procedure.i TouchKeyboardButtonY()
  If gTkbVisible <> 0
    ProcedureReturn gTkbBtnY
  EndIf
  ProcedureReturn gTkbBtnYHidden
EndProcedure
Procedure.i TouchKeyboardButtonW()
  ProcedureReturn gTkbBtnW
EndProcedure
Procedure.i TouchKeyboardButtonH()
  ProcedureReturn gTkbBtnH
EndProcedure

; The largest number of minimum-size targets one row of this screen can
; hold. The MODEL consults this before it emits an arrangement, which is
; how a narrow screen gets a split utility row instead of a refusal.
Procedure.i TouchKeyboardMaxKeysPerRow()
  If gTkbLW < 1 Or gTkbMinPx < 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn (gTkbLW - gTkbGutter) / (gTkbMinPx + gTkbGutter)
EndProcedure

; ----------------------------------------------------------------------
;  THE LAYOUT. One result, computed once, read by the hit test and by the
;  paint. Returns 1, or 0 having set a whole-sentence refusal.
;
;  THE ORDER MATTERS AND EACH STEP IS WHERE IT IS FOR A REASON:
;
;   1. the surface, because nothing below means anything without it
;   2. the model's shape, because a malformed arrangement must be named
;      as one rather than laid out into overlapping rectangles
;   3. the TARGET SIZES, from the density or from the explicit display
;      scale - never from a guessed inch
;   4. the band's height: the 40 per cent starting point, raised to what
;      six rows of preferred-size keys need, capped by what still leaves
;      a usable prompt row, and refused outright if the FLOOR does not fit
;   5. the band snapped DOWN to a whole console cell, so the console
;      viewport is a whole number of rows and the framebuffer renderer's
;      per-row repaint can never reach into the band
;   6. the rows, then the keys inside them, by cumulative units so the
;      rounding remainder lands inside the row instead of accumulating
;      into an overlap or a one pixel seam
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardLayout(*m.TouchKeyboardMetrics)
  Define n.i
  Define i.i
  Define r.i
  Define lw.i
  Define lh.i
  Define bh.i
  Define cw.i
  Define ch.i
  Define ds.i
  Define need.i
  Define want.i
  Define maxKb.i
  Define floorH.i
  Define kbH.i
  Define kbY.i
  Define rows.i
  Define slots.i
  Define usable.i
  Define acc.i
  Define left.i
  Define right.i
  Define gridTop.i
  Define gridH.i
  Define at.i
  Define k.i
  Define lab.i
  Define len.i
  Define c.i

  gTkbOk = 0
  gTkbRefusal = 0
  gTkbSplit = 0
  gTkbOverflow = 0
  gTkbGen = gTkbGen + 1

  ; ---- 1. the surface -------------------------------------------------
  If *m = 0
    gTkbRefusal = "the touch keyboard was asked to lay itself out with no surface measurements at all, so there is nothing to compute a key size from; the caller must fill a TouchKeyboardMetrics before calling TouchKeyboardLayout."
    ProcedureReturn 0
  EndIf
  lw = *m\logicalW
  lh = *m\logicalH
  bh = *m\bannerH
  cw = *m\cellW
  ch = *m\cellH
  ds = *m\displayScale
  If ds < 1
    ds = 1
  EndIf
  If cw < 1 Or ch < 1
    gTkbRefusal = "the touch keyboard was given a console character cell of zero pixels, so it cannot work out how many console rows the keyboard would cost; bring the screen up before showing the keyboard."
    ProcedureReturn 0
  EndIf
  If lw < 64 Or lh < 64 Or bh < 0 Or bh >= lh
    gTkbRefusal = "the touch keyboard was given a screen size it cannot use - the surface must be at least 64 by 64 pixels and the retained banner must be shorter than the screen; check the screen is up and that screen_geom reported a logical size."
    ProcedureReturn 0
  EndIf

  gTkbLW = lw
  gTkbLH = lh
  gTkbBannerH = bh
  gTkbCellW = cw
  gTkbCellH = ch
  gTkbPpi = *m\ppi
  gTkbScale = ds

  ; ---- 2. the model's shape ------------------------------------------
  n = TouchKeyboardKeyCount()
  If n < 1
    gTkbRefusal = "the touch keyboard layout was asked for by a key model that reports no keys at all, so there is no arrangement to draw; select a keyboard page before showing it."
    ProcedureReturn 0
  EndIf
  If n > #TKB_MAX_KEYS
    gTkbRefusal = "the touch keyboard key model reports more keys than this view can lay out, so no arrangement was installed; the fixed key table holds 64 and an arrangement that needs more has to be split across pages."
    ProcedureReturn 0
  EndIf
  For r = 0 To #TKB_MAX_ROWS - 1
    gTkbRowCount[r] = 0
    gTkbRowUnits[r] = 0
  Next
  rows = 0
  i = 0
  While i < n
    r = TouchKeyboardKeyRow(i)
    If r < 0 Or r >= #TKB_MAX_ROWS
      gTkbRefusal = "the touch keyboard key model placed a key on a row this view cannot lay out, so no arrangement was installed; rows are numbered 0 to 7 and must be given in order."
      ProcedureReturn 0
    EndIf
    If TouchKeyboardKeyColumn(i) <> gTkbRowCount[r]
      gTkbRefusal = "the touch keyboard key model gave its keys out of order, so laying them out would have produced overlapping hit rectangles; every key must arrive with the column it will occupy, counting from zero across its own row."
      ProcedureReturn 0
    EndIf
    k = TouchKeyboardKeyWidthUnits(i)
    If k < 1
      gTkbRefusal = "the touch keyboard key model gave a key a width of zero units, which would be a key with no rectangle and no way to touch it; a standard key is 4 units wide."
      ProcedureReturn 0
    EndIf
    gTkbRowCount[r] = gTkbRowCount[r] + 1
    gTkbRowUnits[r] = gTkbRowUnits[r] + k
    If (r + 1) > rows
      rows = r + 1
    EndIf
    i = i + 1
  Wend
  r = 0
  While r < rows
    If gTkbRowCount[r] < 1
      gTkbRefusal = "the touch keyboard key model left a row empty in the middle of its arrangement, so the keyboard would have drawn a blank stripe with no keys on it; rows must be numbered without gaps."
      ProcedureReturn 0
    EndIf
    r = r + 1
  Wend
  gTkbRows = rows
  gTkbKeys = n

  ; ---- 3. the target sizes -------------------------------------------
  ; A TOUCH TARGET IS A PHYSICAL SIZE. When the screen said how big it is,
  ; these are inches. When it did not, ppi arrives as 0 and these are the
  ; existing explicit display scale - stated as such, never dressed up as
  ; a measurement.
  If gTkbPpi >= 1
    gTkbKnown = 1
    gTkbMinPx  = (gTkbPpi * #TKB_MIN_THOU) / 1000
    gTkbPrefPx = (gTkbPpi * #TKB_PREF_THOU) / 1000
  Else
    gTkbKnown = 0
    gTkbMinPx  = #TKB_FALLBACK_MIN_PX * ds
    gTkbPrefPx = #TKB_FALLBACK_PREF_PX * ds
  EndIf
  ; A bench that asked for bigger type asked for bigger everything: the
  ; floor is never below one and a half console lines and the preferred
  ; size never below two.
  If gTkbMinPx < (ch * 3) / 2
    gTkbMinPx = (ch * 3) / 2
  EndIf
  If gTkbPrefPx < ch * 2
    gTkbPrefPx = ch * 2
  EndIf
  gTkbPrefPx = (gTkbPrefPx * gTkbSizeAdj) / 100
  If gTkbPrefPx < gTkbMinPx
    gTkbPrefPx = gTkbMinPx
  EndIf
  gTkbGutter = gTkbMinPx / 10
  If gTkbGutter < #TKB_GUTTER_MIN
    gTkbGutter = #TKB_GUTTER_MIN
  EndIf

  ; ---- 4. the band's height ------------------------------------------
  need    = rows * gTkbPrefPx + (rows + 1) * gTkbGutter
  floorH  = rows * gTkbMinPx  + (rows + 1) * gTkbGutter
  want    = (lh * #TKB_TARGET_PCT) / 100
  If want < need
    want = need
  EndIf
  maxKb = lh - bh - #TKB_MIN_CONSOLE_ROWS * ch
  If floorH > maxKb
    gTkbRefusal = "this screen is not tall enough for a touch keyboard: the smallest keys that are still safe to hit would leave no room for the prompt line above them, so no keyboard was shown. Use a taller screen, a smaller text size with screen scale, or the physical keyboard."
    ProcedureReturn 0
  EndIf
  If want > maxKb
    want = maxKb
  EndIf
  ; Snap the CONSOLE side to whole cells. The framebuffer renderer repaints
  ; the console one whole text row at a time, so a band that began part way
  ; down a row would be painted over by the next console line.
  gTkbConsoleRows = (lh - bh - want) / ch
  If gTkbConsoleRows < #TKB_MIN_CONSOLE_ROWS
    gTkbConsoleRows = #TKB_MIN_CONSOLE_ROWS
  EndIf
  kbY = bh + gTkbConsoleRows * ch
  kbH = lh - kbY
  If kbH < floorH
    gTkbRefusal = "this screen is not tall enough for a touch keyboard once the console is left a whole prompt row, so no keyboard was shown. Use a taller screen, a smaller text size with screen scale, or the physical keyboard."
    ProcedureReturn 0
  EndIf
  gTkbBandY = kbY
  gTkbBandH = kbH

  ; ---- 5. the rows ----------------------------------------------------
  gridTop = kbY
  gridH   = kbH - (rows + 1) * gTkbGutter
  r = 0
  While r < rows
    gTkbRowY[r] = gridTop + (r + 1) * gTkbGutter + (gridH * r) / rows
    gTkbRowH[r] = (gridH * (r + 1)) / rows - (gridH * r) / rows
    If gTkbRowH[r] < gTkbMinPx
      gTkbRefusal = "the touch keyboard could not give every key row the smallest height that is still safe to hit, so no keyboard was shown; reduce the number of rows on the page or use a taller screen."
      ProcedureReturn 0
    EndIf
    r = r + 1
  Wend

  ; ---- 6. the keys ----------------------------------------------------
  ; EVERY ROW IS LAID OUT THE SAME WAY, including row 0. There used to be
  ; a chevron carved out of row 0 before the keys, because the placeholder
  ; model had no hide key; the real model's utility row ends in one, so
  ; carving a second rectangle here would have drawn two dismiss buttons
  ; side by side. The chevron is found among the keys below instead.
  at = 0
  r = 0
  While r < rows
    slots = gTkbRowCount[r]
    usable = lw - (slots + 1) * gTkbGutter
    ; THERE IS ONE WIDTH GUARD AND IT IS PER KEY, below. A second one on
    ; the row's total would be a weaker statement of the same thing - a
    ; row whose total fits can still hold a key that does not - and a
    ; redundant guard is a guard nothing can ever be shown to need.
    acc = 0
    k = 0
    While k < gTkbRowCount[r]
      i = at + k
      left  = (usable * acc) / gTkbRowUnits[r]
      acc   = acc + TouchKeyboardKeyWidthUnits(i)
      right = (usable * acc) / gTkbRowUnits[r]
      gTkbKeyX[i] = (k + 1) * gTkbGutter + left
      gTkbKeyY[i] = gTkbRowY[r]
      gTkbKeyW[i] = right - left
      gTkbKeyH[i] = gTkbRowH[r]
      If gTkbKeyW[i] < gTkbMinPx
        gTkbSplit = Bool(r = 0)
        gTkbRefusal = "this screen is not wide enough for the keyboard arrangement it was given: at least one key would be narrower than is safe to hit. Ask the key model for a split utility row or the symbol page - TouchKeyboardMaxKeysPerRow says how many keys one row of this screen holds - or use the physical keyboard."
        ProcedureReturn 0
      EndIf
      k = k + 1
    Wend
    at = at + gTkbRowCount[r]
    r = r + 1
  Wend

  ; ---- 7. the chevron IS one of those keys ----------------------------
  ; The model says which - it is the key whose KIND is the hide kind - and
  ; this file republishes its rectangle under the chevron's own name. The
  ; integration can then ask "was this DOWN the chevron" without knowing
  ; what a key kind is, and the rectangle it is asking about is provably
  ; the same one the picture was drawn at, because it is a key's.
  ;
  ; AN ARRANGEMENT WITH NO WAY OUT IS REFUSED. A page whose model forgot
  ; its hide key would be a keyboard that covers the prompt and cannot be
  ; put away, so it is named as the defect it is rather than shown.
  gTkbHideAt = -1
  i = 0
  While i < n
    If TouchKeyboardKeyKind(i) = #TK_KIND_HIDE
      gTkbHideAt = i
      Break
    EndIf
    i = i + 1
  Wend
  If gTkbHideAt < 0
    gTkbRefusal = "the touch keyboard key model offered a page with no hide key on it, so the keyboard would have covered the prompt with no way to put it away again; every page's utility row must end in the hide chevron."
    ProcedureReturn 0
  EndIf
  gTkbHideX = gTkbKeyX[gTkbHideAt]
  gTkbHideY = gTkbKeyY[gTkbHideAt]
  gTkbHideW = gTkbKeyW[gTkbHideAt]
  gTkbHideH = gTkbKeyH[gTkbHideAt]

  ; ---- 8. the label sizes --------------------------------------------
  ; The largest WHOLE magnification of the 8 x 16 bitmap that still fits
  ; the key with its padding. Never a fraction, so a glyph is never
  ; enlarged by filtering; never below 1, so a label is never absent.
  i = 0
  While i < n
    lab = TouchKeyboardKeyLabel(i)
    len = 0
    If lab <> 0
      While len < (#TKB_LABEL_MAX - 1)
        c = PeekA(lab + len) & $FF
        If c = 0
          Break
        EndIf
        len = len + 1
      Wend
    EndIf
    If len < 1
      len = 1
    EndIf
    k = #TKB_SCALE_MAX
    While k > 1
      If (len * #TKB_FONT_W * k) <= (gTkbKeyW[i] - 2 * #TKB_PAD) And (#TKB_FONT_H * k) <= (gTkbKeyH[i] - 2 * #TKB_PAD)
        Break
      EndIf
      k = k - 1
    Wend
    gTkbKeyScale[i] = k
    gTkbKeyDirty[i] = 1
    i = i + 1
  Wend

  ; ---- 9. the keyboard button beside the prompt ----------------------
  ; Bottom right of the CONSOLE viewport, which is a different rectangle
  ; depending on whether the band is up; both are computed here so the
  ; button never has to be laid out again on a show or a hide.
  gTkbBtnW = gTkbMinPx
  gTkbBtnH = gTkbMinPx
  If gTkbBtnH > gTkbConsoleRows * ch
    gTkbBtnH = gTkbConsoleRows * ch
  EndIf
  If gTkbBtnW > lw / 4
    gTkbBtnW = lw / 4
  EndIf
  gTkbBtnX = lw - gTkbGutter - gTkbBtnW
  gTkbBtnY = kbY - gTkbBtnH
  gTkbBtnYHidden = lh - gTkbBtnH
  gTkbBtnDirty = 1

  ; ---- 10. the prompt row, and what owns touch while the band is down -
  ; The console paints whole rows from the bottom of the banner, so with
  ; nothing reserved the editable prompt line is the LAST whole row on the
  ; screen. The idle rectangle is that row together with the keyboard
  ; button, which is taller than a row and reaches further up; the union
  ; is what the dispatcher is given as the keyboard's region while the
  ; band is down, so a deliberate tap on either lands on this layer and
  ; on nothing underneath it.
  gTkbPromptH = ch
  gTkbPromptY = bh + ((lh - bh) / ch - 1) * ch
  gTkbIdleY = gTkbPromptY
  If gTkbBtnYHidden < gTkbIdleY
    gTkbIdleY = gTkbBtnYHidden
  EndIf
  gTkbIdleH = lh - gTkbIdleY

  gTkbOk = 1
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  THE HIT TEST. The SAME rectangles the paint used, because there is one
;  layout result and both read it. Coordinates are the screen's logical
;  ones, already produced by the display/touch mapping - nothing here
;  rotates or scales a second time.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardHitKey(x.i, y.i)
  Define i.i
  If gTkbOk = 0 Or gTkbVisible = 0
    ProcedureReturn -1
  EndIf
  i = 0
  While i < gTkbKeys
    If x >= gTkbKeyX[i] And x < (gTkbKeyX[i] + gTkbKeyW[i])
      If y >= gTkbKeyY[i] And y < (gTkbKeyY[i] + gTkbKeyH[i])
        ProcedureReturn i
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i TouchKeyboardHideHit(x.i, y.i)
  If gTkbOk = 0 Or gTkbVisible = 0
    ProcedureReturn 0
  EndIf
  If x < gTkbHideX Or x >= (gTkbHideX + gTkbHideW)
    ProcedureReturn 0
  EndIf
  If y < gTkbHideY Or y >= (gTkbHideY + gTkbHideH)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; THE BUTTON IS NOT THERE WHILE THE BAND IS UP. It is not drawn then -
; the chevron is the affordance once the keyboard is open - and a hit
; test that still answered for it would be a hit on a picture that is not
; on the glass.
Procedure.i TouchKeyboardButtonHit(x.i, y.i)
  Define by.i
  If gTkbOk = 0 Or gTkbVisible <> 0
    ProcedureReturn 0
  EndIf
  by = TouchKeyboardButtonY()
  If x < gTkbBtnX Or x >= (gTkbBtnX + gTkbBtnW)
    ProcedureReturn 0
  EndIf
  If y < by Or y >= (by + gTkbBtnH)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; The editable prompt line, while the band is down. A DELIBERATE TOUCH IN
; A FOCUSED EDITABLE LOCAL FIELD is the design's one auto-open trigger,
; and this is that field's rectangle.
Procedure.i TouchKeyboardPromptHit(x.i, y.i)
  If gTkbOk = 0 Or gTkbVisible <> 0
    ProcedureReturn 0
  EndIf
  If x < 0 Or x >= gTkbLW
    ProcedureReturn 0
  EndIf
  If y < gTkbPromptY Or y >= (gTkbPromptY + gTkbPromptH)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Anywhere in the band, keys and gutters alike. A DOWN here belongs to the
; keyboard until the contact ends, so it cannot click or scroll the
; console underneath - which is the dispatcher's rule, stated here as the
; one geometric question it has to ask.
Procedure.i TouchKeyboardHitChrome(x.i, y.i)
  If gTkbOk = 0 Or gTkbVisible = 0
    ProcedureReturn 0
  EndIf
  If x < 0 Or x >= gTkbLW
    ProcedureReturn 0
  EndIf
  If y < gTkbBandY Or y >= (gTkbBandY + gTkbBandH)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  DAMAGE. A key changes colour far more often than the band changes size,
;  so the common case is a handful of key rectangles and the whole-band
;  rectangle is reserved for a show or a hide.
; ----------------------------------------------------------------------
Procedure TouchKeyboardMarkKey(i.i)
  If i < 0 Or i >= gTkbKeys
    ProcedureReturn
  EndIf
  gTkbKeyDirty[i] = 1
EndProcedure

; The chevron is a key, so marking it changed is marking that key changed.
; One flag, so the two can never disagree about whether it needs redrawing.
Procedure TouchKeyboardMarkHide()
  TouchKeyboardMarkKey(gTkbHideAt)
EndProcedure

Procedure TouchKeyboardMarkButton()
  gTkbBtnDirty = 1
EndProcedure

Procedure TouchKeyboardMarkAll()
  Define i.i
  i = 0
  While i < gTkbKeys
    gTkbKeyDirty[i] = 1
    i = i + 1
  Wend
  gTkbBtnDirty = 1
EndProcedure

Procedure.i TouchKeyboardDamageCount()
  ProcedureReturn gTkbDamageN
EndProcedure
Procedure.i TouchKeyboardDamageX(i.i)
  If i < 0 Or i >= gTkbDamageN : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbDamX[i]
EndProcedure
Procedure.i TouchKeyboardDamageY(i.i)
  If i < 0 Or i >= gTkbDamageN : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbDamY[i]
EndProcedure
Procedure.i TouchKeyboardDamageW(i.i)
  If i < 0 Or i >= gTkbDamageN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDamW[i]
EndProcedure
Procedure.i TouchKeyboardDamageH(i.i)
  If i < 0 Or i >= gTkbDamageN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDamH[i]
EndProcedure

Procedure TkbDamage(x.i, y.i, w.i, h.i)
  If gTkbDamageN >= #TKB_MAX_DAMAGE
    gTkbOverflow = 1
    ProcedureReturn
  EndIf
  gTkbDamX[gTkbDamageN] = x
  gTkbDamY[gTkbDamageN] = y
  gTkbDamW[gTkbDamageN] = w
  gTkbDamH[gTkbDamageN] = h
  gTkbDamageN = gTkbDamageN + 1
EndProcedure

; ----------------------------------------------------------------------
;  THE DRAW LIST. Rectangles and text, in paint order, in the screen's
;  logical coordinates. Nothing here draws: the adapters walk it.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardDrawCount()
  ProcedureReturn gTkbDrawN
EndProcedure
Procedure.i TouchKeyboardDrawKind(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawKind[i]
EndProcedure
Procedure.i TouchKeyboardDrawX(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbDrawX[i]
EndProcedure
Procedure.i TouchKeyboardDrawY(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn -1 : EndIf
  ProcedureReturn gTkbDrawY[i]
EndProcedure
Procedure.i TouchKeyboardDrawW(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawW[i]
EndProcedure
Procedure.i TouchKeyboardDrawH(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawH[i]
EndProcedure
Procedure.i TouchKeyboardDrawFg(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawFg[i]
EndProcedure
Procedure.i TouchKeyboardDrawBg(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawBg[i]
EndProcedure
Procedure.i TouchKeyboardDrawText(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawAux[i]
EndProcedure
Procedure.i TouchKeyboardDrawScale(i.i)
  If i < 0 Or i >= gTkbDrawN : ProcedureReturn 0 : EndIf
  ProcedureReturn gTkbDrawScale[i]
EndProcedure
Procedure.i TouchKeyboardDrawRenderer()
  ProcedureReturn gTkbDrawFor
EndProcedure
Procedure.i TouchKeyboardDrawOverflowed()
  ProcedureReturn gTkbOverflow
EndProcedure

Procedure TkbRect(x.i, y.i, w.i, h.i, colour.i)
  If w < 1 Or h < 1
    ProcedureReturn
  EndIf
  If gTkbDrawN >= #TKB_MAX_DRAW
    gTkbOverflow = 1
    ProcedureReturn
  EndIf
  gTkbDrawKind[gTkbDrawN]  = #TKB_DRAW_RECT
  gTkbDrawX[gTkbDrawN]     = x
  gTkbDrawY[gTkbDrawN]     = y
  gTkbDrawW[gTkbDrawN]     = w
  gTkbDrawH[gTkbDrawN]     = h
  gTkbDrawFg[gTkbDrawN]    = colour
  gTkbDrawBg[gTkbDrawN]    = colour
  gTkbDrawAux[gTkbDrawN]   = 0
  gTkbDrawScale[gTkbDrawN] = 0
  gTkbDrawN = gTkbDrawN + 1
EndProcedure

; Copy a label into this paint's arena, replacing every byte the bitmap
; font cannot draw with a question mark. A GLYPH THAT IS NOT IN THE FONT
; BECOMES A VISIBLE CHARACTER AND NEVER AN EMPTY BOX - an empty key is
; indistinguishable from a broken keyboard, and the design says so.
; Returns the arena pointer, or 0 if the arena is full (which is loud).
Procedure.i TkbArenaLabel(*src, maxChars.i)
  Define at.i
  Define n.i
  Define c.i
  If maxChars < 1
    maxChars = 1
  EndIf
  at = gTkbArenaAt
  If (at + maxChars + 1) > #TKB_ARENA
    gTkbOverflow = 1
    ProcedureReturn 0
  EndIf
  n = 0
  If *src <> 0
    While n < maxChars
      c = PeekA(*src + n) & $FF
      If c = 0
        Break
      EndIf
      If c < 32 Or c > 126
        c = 63                        ; '?'
      EndIf
      gTkbArena[at + n] = c
      n = n + 1
    Wend
  EndIf
  If n = 0
    gTkbArena[at] = 63
    n = 1
  EndIf
  gTkbArena[at + n] = 0
  gTkbArenaAt = at + n + 1
  ProcedureReturn @gTkbArena[at]
EndProcedure

Procedure TkbText(x.i, y.i, w.i, h.i, fg.i, bg.i, *label, scale.i)
  If gTkbDrawN >= #TKB_MAX_DRAW
    gTkbOverflow = 1
    ProcedureReturn
  EndIf
  gTkbDrawKind[gTkbDrawN]  = #TKB_DRAW_TEXT
  gTkbDrawX[gTkbDrawN]     = x
  gTkbDrawY[gTkbDrawN]     = y
  gTkbDrawW[gTkbDrawN]     = w
  gTkbDrawH[gTkbDrawN]     = h
  gTkbDrawFg[gTkbDrawN]    = fg
  gTkbDrawBg[gTkbDrawN]    = bg
  gTkbDrawAux[gTkbDrawN]   = *label
  gTkbDrawScale[gTkbDrawN] = scale
  gTkbDrawN = gTkbDrawN + 1
EndProcedure

; A key: its edge, its face, and its label centred in it.
Procedure TkbKeyItems(i.i)
  Define face.i
  Define edge.i
  Define ink.i
  Define s.i
  Define lab.i
  Define maxChars.i
  Define len.i
  Define tw.i
  Define th.i
  Define c.i

  face = #TKB_C_FACE
  edge = #TKB_C_EDGE
  ink  = #TKB_C_INK
  If TouchKeyboardKeyIsAccent(i) <> 0
    face = #TKB_C_ACCENT
    edge = #TKB_C_EDGEACC
  EndIf
  If TouchKeyboardKeyIsLatched(i) <> 0
    face = #TKB_C_LATCH
    edge = #TKB_C_EDGEACC
  EndIf
  If TouchKeyboardKeyIsArmed(i) <> 0
    face = #TKB_C_PRESS
    edge = #TKB_C_EDGEACC
  EndIf

  TkbRect(gTkbKeyX[i], gTkbKeyY[i], gTkbKeyW[i], gTkbKeyH[i], edge)
  TkbRect(gTkbKeyX[i] + 1, gTkbKeyY[i] + 1, gTkbKeyW[i] - 2, gTkbKeyH[i] - 2, face)

  s = gTkbKeyScale[i]
  If s < 1
    s = 1
  EndIf
  maxChars = (gTkbKeyW[i] - 2 * #TKB_PAD) / (#TKB_FONT_W * s)
  If maxChars < 1
    maxChars = 1
  EndIf
  lab = TkbArenaLabel(TouchKeyboardKeyLabel(i), maxChars)
  If lab = 0
    ProcedureReturn
  EndIf
  len = 0
  While len < maxChars
    c = PeekA(lab + len) & $FF
    If c = 0
      Break
    EndIf
    len = len + 1
  Wend
  tw = len * #TKB_FONT_W * s
  th = #TKB_FONT_H * s
  TkbText(gTkbKeyX[i] + (gTkbKeyW[i] - tw) / 2, gTkbKeyY[i] + (gTkbKeyH[i] - th) / 2, tw, th, ink, face, lab, s)
EndProcedure

; The down-chevron. It is DRAWN FROM RECTANGLES and not looked up in the
; bitmap font, because the font has no chevron and a font that has no
; glyph draws nothing at all - which is the empty box the design forbids.
; A rectangle too small for a legible arrow falls back to the letter v.
Procedure TkbHideItems()
  Define cx.i
  Define cy.i
  Define half.i
  Define step.i
  Define i.i
  Define w.i
  Define lab.i

  TkbRect(gTkbHideX, gTkbHideY, gTkbHideW, gTkbHideH, #TKB_C_EDGE)
  TkbRect(gTkbHideX + 1, gTkbHideY + 1, gTkbHideW - 2, gTkbHideH - 2, #TKB_C_FACE)

  half = gTkbHideW / 4
  If half > gTkbHideH / 4
    half = gTkbHideH / 4
  EndIf
  If half < 6
    lab = TkbArenaLabel("v", 1)
    If lab <> 0
      TkbText(gTkbHideX + (gTkbHideW - #TKB_FONT_W) / 2, gTkbHideY + (gTkbHideH - #TKB_FONT_H) / 2, #TKB_FONT_W, #TKB_FONT_H, #TKB_C_INK, #TKB_C_FACE, lab, 1)
    EndIf
    ProcedureReturn
  EndIf
  ; A solid downward triangle in eight horizontal slices: unmistakably
  ; "put this away", and eight rectangles rather than a glyph.
  cx = gTkbHideX + gTkbHideW / 2
  cy = gTkbHideY + (gTkbHideH - half) / 2
  step = half / 8
  If step < 1
    step = 1
  EndIf
  i = 0
  While i < 8
    w = (half * 2 * (8 - i)) / 8
    If w < 2
      w = 2
    EndIf
    TkbRect(cx - w / 2, cy + i * step, w, step, #TKB_C_EDGEACC)
    i = i + 1
  Wend
EndProcedure

; The keyboard button beside the prompt. Also rectangles - a key outline
; with three rows of caps and a space bar - falling back to the letters
; KB when there is no room to draw one.
Procedure TkbButtonItems()
  Define x.i
  Define y.i
  Define w.i
  Define h.i
  Define lab.i
  Define capW.i
  Define capH.i
  Define gapX.i
  Define gapY.i
  Define r.i
  Define c.i

  x = gTkbBtnX
  y = TouchKeyboardButtonY()
  w = gTkbBtnW
  h = gTkbBtnH
  If w < 4 Or h < 4
    ProcedureReturn
  EndIf
  TkbRect(x, y, w, h, #TKB_C_EDGEACC)
  TkbRect(x + 1, y + 1, w - 2, h - 2, #TKB_C_FACE)

  capW = (w - 10) / 4
  capH = (h - 12) / 4
  If capW < 2 Or capH < 2
    lab = TkbArenaLabel("KB", 2)
    If lab <> 0
      TkbText(x + (w - 2 * #TKB_FONT_W) / 2, y + (h - #TKB_FONT_H) / 2, 2 * #TKB_FONT_W, #TKB_FONT_H, #TKB_C_INK, #TKB_C_FACE, lab, 1)
    EndIf
    ProcedureReturn
  EndIf
  gapX = (w - 4 * capW) / 5
  gapY = (h - 4 * capH) / 5
  r = 0
  While r < 3
    c = 0
    While c < 4
      TkbRect(x + gapX + c * (capW + gapX), y + gapY + r * (capH + gapY), capW, capH, #TKB_C_INKDIM)
      c = c + 1
    Wend
    r = r + 1
  Wend
  TkbRect(x + gapX, y + gapY + 3 * (capH + gapY), w - 2 * gapX, capH, #TKB_C_INKDIM)
EndProcedure

; ----------------------------------------------------------------------
;  TouchKeyboardPaint - build the draw list and the dirty rectangles for
;  one pass. It DRAWS NOTHING; the board adapter walks the list.
;
;  renderer is #TKB_RENDER_CPU or #TKB_RENDER_GPU and travels with the
;  list so an adapter can assert it was handed its own.
;
;  damage says what this pass is allowed to touch:
;    ALL          the band, on a first paint after a layout
;    CHANGED      the keys marked changed, and NOTHING else. This is the
;                 common case - a press, a release, a modifier latching -
;                 and it is why a keystroke is a few small rectangles
;                 rather than a screen.
;    TRANSITION   the band rectangle, for a show or a hide.
;
;  Returns the number of draw items.
; ----------------------------------------------------------------------
Procedure.i TouchKeyboardPaint(renderer.i, damage.i)
  Define i.i
  Define whole.i

  gTkbDrawN = 0
  gTkbDamageN = 0
  gTkbArenaAt = 0
  gTkbOverflow = 0
  gTkbDrawFor = renderer
  If gTkbOk = 0
    ProcedureReturn 0
  EndIf

  ; The button beside the prompt lives OUTSIDE the band and is drawn
  ; whether or not the keyboard is up - it is how the keyboard is asked
  ; for in the first place.
  If gTkbVisible = 0
    If damage = #TKB_DAMAGE_CHANGED And gTkbBtnDirty = 0
      ProcedureReturn 0
    EndIf
    TkbButtonItems()
    TkbDamage(gTkbBtnX, TouchKeyboardButtonY(), gTkbBtnW, gTkbBtnH)
    gTkbBtnDirty = 0
    ProcedureReturn gTkbDrawN
  EndIf

  whole = Bool(damage <> #TKB_DAMAGE_CHANGED)
  If whole <> 0
    TkbRect(0, gTkbBandY, gTkbLW, gTkbBandH, #TKB_C_BAND)
    TkbDamage(0, gTkbBandY, gTkbLW, gTkbBandH)
  EndIf

  ; ONE DRAW PATH PER KEY. The chevron is a key like the others - the
  ; model's hide key - so it is drawn in this loop, at its own rectangle,
  ; from its own dirty flag. It gets a triangle instead of a label
  ; because the bitmap font has no chevron in it, and that is the whole
  ; of the difference between it and every other key.
  i = 0
  While i < gTkbKeys
    If whole <> 0 Or gTkbKeyDirty[i] <> 0
      If i = gTkbHideAt
        TkbHideItems()
      Else
        TkbKeyItems(i)
      EndIf
      If whole = 0
        TkbDamage(gTkbKeyX[i], gTkbKeyY[i], gTkbKeyW[i], gTkbKeyH[i])
      EndIf
      gTkbKeyDirty[i] = 0
    EndIf
    i = i + 1
  Wend

  ; THE BUTTON BESIDE THE PROMPT IS NOT DRAWN WHILE THE BAND IS UP. It is
  ; how the keyboard is ASKED FOR, and once it is open the chevron is how
  ; it is put away; drawing both would leave a button on the glass that
  ; does nothing when it is tapped, which the design forbids in as many
  ; words. Its flag is cleared rather than left set, so the hidden pass
  ; that follows a hide is not told the button is stale for ever.
  gTkbBtnDirty = 0

  ProcedureReturn gTkbDrawN
EndProcedure

; The band's damage, as one pair of scan lines, for the presentation seam
; (ScrPresent takes a logical row range). -1 when nothing was damaged.
Procedure.i TouchKeyboardDamageTop()
  Define i.i
  Define v.i
  If gTkbDamageN < 1
    ProcedureReturn -1
  EndIf
  v = gTkbDamY[0]
  i = 1
  While i < gTkbDamageN
    If gTkbDamY[i] < v
      v = gTkbDamY[i]
    EndIf
    i = i + 1
  Wend
  ProcedureReturn v
EndProcedure

Procedure.i TouchKeyboardDamageBottom()
  Define i.i
  Define v.i
  Define b.i
  If gTkbDamageN < 1
    ProcedureReturn -1
  EndIf
  v = gTkbDamY[0] + gTkbDamH[0] - 1
  i = 1
  While i < gTkbDamageN
    b = gTkbDamY[i] + gTkbDamH[i] - 1
    If b > v
      v = b
    EndIf
    i = i + 1
  Wend
  ProcedureReturn v
EndProcedure
