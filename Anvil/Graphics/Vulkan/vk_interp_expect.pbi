; ======================================================================
;  What an interpolated varying MUST be, at a named pixel
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target neutral and INTEGER ONLY. Nothing here knows a QPU register, a
; VPM slot or a packet, and nothing here calls a floating-point
; instruction: every number below is an exact integer or an exact
; rational, so the same expectation comes out of this file, out of the
; desk gate's Python and out of a reader's pencil.
;
; ======================================================================
;  WHY IT EXISTS
; ======================================================================
;  vulkanTriangleProof's second pass gives all three vertices ONE colour,
;  on purpose: that makes the expected pixel exact whatever the
;  interpolator does, so it proves the varying PATH and says nothing
;  about interpolation. A gradient cannot be checked that way - the
;  answer at a pixel is a weighted average, and somebody has to say what
;  the weights are BEFORE the board runs.
;
;  This file is that somebody. It lives beside the front end rather than
;  inside the diagnostic for the reason vk_spirv_fixtures.pbi does: the
;  board must not be the first place anybody checks these numbers. The
;  desk gate calls exactly these procedures and compares every answer
;  against one its own Python computes from the same rule, written
;  separately.
;
; ======================================================================
;  THE CHAIN, IN FULL
; ======================================================================
;  1. CLIP TO SCREEN. A vertex's clip coordinate is an exact rational
;     num/den. The emitted coordinate shader computes
;         Xs = round(Xc * halfWidth256),  halfWidth256 = (W / 2) * 256
;     and the control list's VIEWPORT_OFFSET packet adds the same
;     halfWidth256 back (RaspberryPi4/Lib/neon.pi4, the frame prologue:
;     V3dClViewportOffset(cx * 256, 0, cy * 256, 0)). So a vertex lands
;     at, in units of 1/256 of a pixel,
;         Sx = round(xNum * halfWidth256 / den) + halfWidth256
;     Every value this diagnostic uses divides exactly; the rounding is
;     written out anyway, because a rule that only works for the numbers
;     in front of it is not a rule.
;
;  2. THE SAMPLE POINT. A fragment is shaded at the CENTRE of its pixel,
;     which in the same units is (px * 256 + 128, py * 256 + 128). There
;     is one sample per pixel - vkCreateGraphicsPipelines refuses more -
;     so there is no other point it could be.
;
;  3. THE WEIGHTS. The three edge functions of the triangle, evaluated at
;     the sample point, ARE the barycentric numerators:
;         w0 = edge(S1, S2, P),  w1 = edge(S2, S0, P),  w2 = edge(S0, S1, P)
;         D  = w0 + w1 + w2 = edge(S0, S1, S2)
;     each an exact integer in units of 1/65536 of a square pixel. The
;     sign of D is the winding; the weights are normalised against it so
;     either winding gives the same answer.
;
;  4. NO PERSPECTIVE DIVIDE. Every vertex this slice accepts has w = 1.0
;     exactly - vk_spirv.pbi refuses any other - and the draw sets the
;     non-perspective varying flags, so screen-space barycentrics ARE the
;     interpolation weights. That is the one assumption in this file that
;     is a statement about the hardware rather than about arithmetic, and
;     it is the assumption the board run is there to test.
;
;  5. THE COMPONENT. A per-vertex colour component is an integer 0..255
;     and the value the shader produces is the weighted average of the
;     three. The render target is VK_FORMAT_B8G8R8A8_UNORM, so the
;     expected byte is
;         round(255 * (w0*c0 + w1*c1 + w2*c2) / (255 * D))
;     written as one rounded integer division with no intermediate
;     rounding at all.
;
; ======================================================================
;  THE TOLERANCE, AND WHY IT IS NOT ZERO
; ======================================================================
;  Nothing above is approximate. The HARDWARE is: V3D delivers a varying
;  through LDVARY as a binary32 built from a per-primitive slope and a
;  per-fragment step, the emitted fragment shader packs two binary32
;  lanes into one 2 x f16 result, and the tile buffer converts that to an
;  8-bit UNORM. f16 carries eleven mantissa bits, so a value in [0, 1] is
;  held to about one part in 2048 - a fifth of one 8-bit step - and the
;  interpolator's own slope accumulation adds a little more.
;
;  So the gate is "within #ANVIL_VKI_TOL of the exact answer, per
;  channel", and the number is TWO. It is stated here rather than chosen
;  on the bench, and it is small enough that it cannot hide a real
;  defect: a varying wired to the wrong component, a missing W multiply,
;  a dropped interpolation or a flat-shaded triangle all miss by tens or
;  hundreds, not by two.
;
;  AN EXACT CHANNEL IS STILL CHECKED EXACTLY IN SPIRIT: alpha is 1.0 at
;  all three vertices of every probe below, so its weighted average is
;  1.0 whatever the weights are, and a run that returns anything but 255
;  for alpha has a defect the weights cannot explain. It is compared
;  through the same tolerance so one comparison covers the whole word,
;  and the diagnostic reports the raw pixel beside the expectation so a
;  reader can see which channel moved.

; ======================================================================
;  PROVENANCE
; ======================================================================
;  Two facts here are the Khronos Vulkan specification's and are cited
;  as such: that a fragment with one rasterisation sample is shaded at
;  the pixel's centre (chapter `primsrast`, the sample-position rule),
;  and that VK_FORMAT_B8G8R8A8_UNORM stores blue, green, red and alpha
;  in ascending byte order (chapter `formats`). Both were CONSULTED in
;  the sense docs/PROVENANCE_INVENTORY.md defines: read for what the
;  interface means, with no code read or translated. Everything else -
;  the edge functions, the rounding rule, the tolerance and its argument
;  - is this tree's own arithmetic.

; Three vertices. Not a limit worth raising: a triangle has three.
#ANVIL_VKI_V = 3

; The per-channel tolerance, in 8-bit UNORM steps. See the note above.
#ANVIL_VKI_TOL = 2

Global Dim avkiSx.i[#ANVIL_VKI_V]        ; screen x, units of 1/256 pixel
Global Dim avkiSy.i[#ANVIL_VKI_V]
Global Dim avkiC.i[#ANVIL_VKI_V * 4]     ; r, g, b, a per vertex, 0..255
Global avkiHalfW.i = 0
Global avkiHalfH.i = 0
Global avkiBegun.i = 0

; Round a signed rational to the nearest integer, halves away from zero.
; Written out rather than done with a shift because `num` is signed and a
; shift of a negative number rounds the wrong way at exactly the point
; this procedure exists to get right.
Procedure.i avkiRound(num.i, den.i)
  If den = 0 : ProcedureReturn 0 : EndIf
  If den < 0
    num = -num
    den = -den
  EndIf
  If num >= 0
    ProcedureReturn (num + (den / 2)) / den
  EndIf
  ProcedureReturn -(((-num) + (den / 2)) / den)
EndProcedure

; The viewport this triangle is rasterised into, in whole pixels. Both
; must be positive and even; vkCreateGraphicsPipelines has already
; refused a viewport that is not a positive whole number of pixels, and
; an odd one would put the viewport centre on a half pixel, which the
; VIEWPORT_OFFSET packet's fine field cannot carry.
;
; A REFUSAL CLEARS EVERYTHING, and that is deliberate: the previous
; triangle's screen coordinates are still in these tables, so a Begin
; that refused and left them would answer the next probe with the last
; triangle's gradient. A module that keeps answering after it has said
; no is the one shape of this defect nobody notices.
Procedure.i AnvilVkInterpBegin(viewW.i, viewH.i)
  Define k.i
  avkiBegun = 0
  avkiHalfW = 0
  avkiHalfH = 0
  k = 0
  While k < #ANVIL_VKI_V
    avkiSx[k] = 0
    avkiSy[k] = 0
    avkiC[(k * 4) + 0] = 0
    avkiC[(k * 4) + 1] = 0
    avkiC[(k * 4) + 2] = 0
    avkiC[(k * 4) + 3] = 0
    k = k + 1
  Wend
  If viewW < 2 Or viewH < 2 : ProcedureReturn 0 : EndIf
  If (viewW % 2) <> 0 Or (viewH % 2) <> 0 : ProcedureReturn 0 : EndIf
  avkiHalfW = (viewW / 2) * 256
  avkiHalfH = (viewH / 2) * 256
  avkiBegun = 1
  ProcedureReturn 1
EndProcedure

; Vertex k at clip position (xNum/den, yNum/den). Step 1 of the chain.
Procedure.i AnvilVkInterpVertex(k.i, xNum.i, yNum.i, den.i)
  If avkiBegun = 0 : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_VKI_V : ProcedureReturn 0 : EndIf
  If den = 0 : ProcedureReturn 0 : EndIf
  avkiSx[k] = avkiRound(xNum * avkiHalfW, den) + avkiHalfW
  avkiSy[k] = avkiRound(yNum * avkiHalfH, den) + avkiHalfH
  ProcedureReturn 1
EndProcedure

; Vertex k's colour, each channel an integer 0..255. Only 0 and 255 are
; used by the diagnostic, because those two are the only 8-bit values
; whose binary32 form - 0.0 and 1.0 - is exact in an f16 as well, so the
; VERTEX data cannot itself be the thing that moved.
Procedure.i AnvilVkInterpColour(k.i, r.i, g.i, b.i, a.i)
  If avkiBegun = 0 : ProcedureReturn 0 : EndIf
  If k < 0 Or k >= #ANVIL_VKI_V : ProcedureReturn 0 : EndIf
  If r < 0 Or r > 255 Or g < 0 Or g > 255 Or b < 0 Or b > 255 Or a < 0 Or a > 255
    ProcedureReturn 0
  EndIf
  avkiC[(k * 4) + 0] = r
  avkiC[(k * 4) + 1] = g
  avkiC[(k * 4) + 2] = b
  avkiC[(k * 4) + 3] = a

  ProcedureReturn 1
EndProcedure

Procedure.i AnvilVkInterpScreenX(k.i)
  If k < 0 Or k >= #ANVIL_VKI_V : ProcedureReturn 0 : EndIf
  ProcedureReturn avkiSx[k]
EndProcedure

Procedure.i AnvilVkInterpScreenY(k.i)
  If k < 0 Or k >= #ANVIL_VKI_V : ProcedureReturn 0 : EndIf
  ProcedureReturn avkiSy[k]
EndProcedure

; The edge function of the directed line AB evaluated at P, in units of
; 1/65536 of a square pixel. Positive on one side, negative on the other,
; zero exactly on the line.
Procedure.i avkiEdge(ax.i, ay.i, bx.i, by.i, px.i, py.i)
  ProcedureReturn ((bx - ax) * (py - ay)) - ((by - ay) * (px - ax))
EndProcedure

; Twice the signed area. Its sign is the winding.
Procedure.i AnvilVkInterpArea()
  ProcedureReturn avkiEdge(avkiSx[0], avkiSy[0], avkiSx[1], avkiSy[1], avkiSx[2], avkiSy[2])
EndProcedure

; The barycentric numerator of vertex k at the centre of pixel (px, py),
; already signed the same way as AnvilVkInterpArea().
Procedure.i AnvilVkInterpWeight(px.i, py.i, k.i)
  Define cx.i
  Define cy.i
  cx = (px * 256) + 128
  cy = (py * 256) + 128
  If k = 0
    ProcedureReturn avkiEdge(avkiSx[1], avkiSy[1], avkiSx[2], avkiSy[2], cx, cy)
  EndIf
  If k = 1
    ProcedureReturn avkiEdge(avkiSx[2], avkiSy[2], avkiSx[0], avkiSy[0], cx, cy)
  EndIf
  If k = 2
    ProcedureReturn avkiEdge(avkiSx[0], avkiSy[0], avkiSx[1], avkiSy[1], cx, cy)
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 when the centre of pixel (px, py) is strictly inside the triangle.
; STRICTLY, and that is the point: a probe on an edge is decided by the
; rasteriser's fill rule rather than by arithmetic, and a diagnostic
; whose expected pixel depends on a tie-break rule is a diagnostic that
; argues with the bench instead of measuring it.
Procedure.i AnvilVkInterpInside(px.i, py.i)
  Define d.i
  Define w.i
  Define k.i
  d = AnvilVkInterpArea()
  If d = 0 : ProcedureReturn 0 : EndIf
  k = 0
  While k < #ANVIL_VKI_V
    w = AnvilVkInterpWeight(px, py, k)
    If d > 0
      If w <= 0 : ProcedureReturn 0 : EndIf
    Else
      If w >= 0 : ProcedureReturn 0 : EndIf
    EndIf
    k = k + 1
  Wend
  ProcedureReturn 1
EndProcedure

; One channel of the interpolated colour at pixel (px, py), 0..255.
; `ch` is 0 red, 1 green, 2 blue, 3 alpha.
Procedure.i AnvilVkInterpChannel(px.i, py.i, ch.i)
  Define d.i
  Define acc.i
  Define k.i
  Define v.i
  If ch < 0 Or ch > 3 : ProcedureReturn 0 : EndIf
  d = AnvilVkInterpArea()
  If d = 0 : ProcedureReturn 0 : EndIf
  acc = 0
  k = 0
  While k < #ANVIL_VKI_V
    acc = acc + (AnvilVkInterpWeight(px, py, k) * avkiC[(k * 4) + ch])
    k = k + 1
  Wend
  v = avkiRound(acc, d)
  If v < 0 : v = 0 : EndIf
  If v > 255 : v = 255 : EndIf
  ProcedureReturn v
EndProcedure

; The whole expected pixel, packed the way VK_FORMAT_B8G8R8A8_UNORM
; stores it and a 32-bit load on this little-endian part reads it back:
; (A << 24) | (R << 16) | (G << 8) | B.
Procedure.i AnvilVkInterpExpect(px.i, py.i)
  Define r.i
  Define g.i
  Define b.i
  Define a.i
  r = AnvilVkInterpChannel(px, py, 0)
  g = AnvilVkInterpChannel(px, py, 1)
  b = AnvilVkInterpChannel(px, py, 2)
  a = AnvilVkInterpChannel(px, py, 3)
  ProcedureReturn ((a << 24) | (r << 16) | (g << 8) | b) & $FFFFFFFF
EndProcedure

Procedure.i AnvilVkInterpTolerance()
  ProcedureReturn #ANVIL_VKI_TOL
EndProcedure

; How far one packed pixel is from another, as the LARGEST per-channel
; difference. A caller compares that against the tolerance; returning the
; distance rather than a yes or no means a report can carry how far out a
; failing pixel was, which is the difference between "the gradient is
; slightly off" and "the triangle is the wrong colour".
Procedure.i AnvilVkInterpDistance(got.i, want.i)
  Define k.i
  Define d.i
  Define worst.i
  worst = 0
  k = 0
  While k < 4
    d = ((got >> (k * 8)) & $FF) - ((want >> (k * 8)) & $FF)
    If d < 0 : d = -d : EndIf
    If d > worst : worst = d : EndIf
    k = k + 1
  Wend
  ProcedureReturn worst
EndProcedure
