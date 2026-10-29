; ======================================================================
;  COLOUR
;
;  Packed 0xAARRGGBB, each channel 0..255. This is a LOGICAL colour and
;  not the surface's word: the fragment shader is handed four separate
;  f32 components and the tile buffer packs them, so nothing here
;  depends on the framebuffer's channel order.
; ======================================================================
Procedure.i Neon_RGBA(r.i, g.i, b.i, a.i)
  If r < 0 : r = 0 : EndIf
  If r > 255 : r = 255 : EndIf
  If g < 0 : g = 0 : EndIf
  If g > 255 : g = 255 : EndIf
  If b < 0 : b = 0 : EndIf
  If b > 255 : b = 255 : EndIf
  If a < 0 : a = 0 : EndIf
  If a > 255 : a = 255 : EndIf
  ProcedureReturn ((a & $FF) << 24) | ((r & $FF) << 16) | ((g & $FF) << 8) | (b & $FF)
EndProcedure

Procedure.i Neon_RGB(r.i, g.i, b.i)
  ProcedureReturn Neon_RGBA(r, g, b, 255)
EndProcedure

Procedure.i Neon_R(c.i)
  ProcedureReturn (c >> 16) & $FF
EndProcedure

Procedure.i Neon_G(c.i)
  ProcedureReturn (c >> 8) & $FF
EndProcedure

Procedure.i Neon_B(c.i)
  ProcedureReturn c & $FF
EndProcedure

Procedure.i Neon_A(c.i)
  ProcedureReturn (c >> 24) & $FF
EndProcedure

; Replace the alpha, keeping the colour. `a` is 0..255.
Procedure.i Neon_WithAlpha(c.i, a.i)
  ProcedureReturn Neon_RGBA(Neon_R(c), Neon_G(c), Neon_B(c), a)
EndProcedure

; ----------------------------------------------------------------------
;  Neon_Mul - the palette's derived products, as an integer ratio.
;
;  The widgets multiply the palette rather than naming new entries: an
;  open menu tab is accent * 0.30/0.30/0.34 (GlUIChrome.pbi:725), a
;  drop-down frame accent * 0.55 (:774), a hot scrollbar thumb
;  accent * 0.8 (:485). Neon_Mul(cAcc, 55, 100) is that, and the
;  rounding is round-to-nearest so 0.353 * 0.55 * 255 comes out the
;  same integer the engine's float path would produce.
;
;  THE ALPHA IS NOT SCALED. Every one of those products in the engine
;  multiplies the colour and leaves the alpha at 1.0.
; ----------------------------------------------------------------------
Procedure.i Neon_Mul(c.i, num.i, den.i)
  Protected r.i
  Protected g.i
  Protected b.i
  If den <= 0
    ProcedureReturn c
  EndIf
  r = ((Neon_R(c) * num) + (den / 2)) / den
  g = ((Neon_G(c) * num) + (den / 2)) / den
  b = ((Neon_B(c) * num) + (den / 2)) / den
  ProcedureReturn Neon_RGBA(r, g, b, Neon_A(c))
EndProcedure

; The three-channel form, for accent * 0.30/0.30/0.34 and
; red * 0.5/0.35/0.35 which are not uniform.
Procedure.i Neon_Mul3(c.i, numR.i, numG.i, numB.i)
  Protected r.i
  Protected g.i
  Protected b.i
  r = ((Neon_R(c) * numR) + 50) / 100
  g = ((Neon_G(c) * numG) + 50) / 100
  b = ((Neon_B(c) * numB) + 50) / 100
  ProcedureReturn Neon_RGBA(r, g, b, Neon_A(c))
EndProcedure

; Add a constant to each channel, which is the button's hover lift:
; br + 0.06*hover, bg + 0.07*hover, bb + 0.08*hover (GlUIChrome.pbi:365).
; `hover` is 0..1000 here and the offsets are in 1/1000 of full scale.
Procedure.i Neon_Lift(c.i, hover1000.i)
  Protected r.i
  Protected g.i
  Protected b.i
  r = Neon_R(c) + ((255 * 60 * hover1000) / 1000000)
  g = Neon_G(c) + ((255 * 70 * hover1000) / 1000000)
  b = Neon_B(c) + ((255 * 80 * hover1000) / 1000000)
  ProcedureReturn Neon_RGBA(r, g, b, Neon_A(c))
EndProcedure
