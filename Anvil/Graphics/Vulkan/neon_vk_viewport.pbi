; Fixed-canvas viewport math shared by Neon Vulkan hosts. This module owns no
; display, input device, Vulkan object, or board backend.

#NEON_VK_VIEWPORT_OK = 0
#NEON_VK_VIEWPORT_INSIDE = 1
#NEON_VK_VIEWPORT_BAR = 0
#NEON_VK_VIEWPORT_ERR_ARGS = -21320
#NEON_VK_VIEWPORT_ERR_STATE = -21321
#NEON_VK_VIEWPORT_Q16 = 65536
#NEON_VK_VIEWPORT_MAX_DIMENSION = 8192

Structure NeonVkPortViewport
  valid.i
  canvasW.i
  canvasH.i
  physicalW.i
  physicalH.i
  x.i
  y.i
  width.i
  height.i
EndStructure

; Preserve the desktop's order: fit width first, reduce to a height fit only
; when required, then center the resulting viewport. Its .f fields and
; intermediate operations matter: exact-rational rounding differs by a pixel
; at some dimensions. Inputs here are physical pixels at a 1:1 DPI scale.
Procedure.i NeonVkPortViewportPlan(canvasW.i, canvasH.i, physicalW.i, physicalH.i, *viewport.NeonVkPortViewport)
  Protected width.i, height.i, x.i, y.i
  Protected canvasWf.f, canvasHf.f, physicalWf.f, physicalHf.f
  Protected targetW.f, targetH.f, offsetX.f, offsetY.f
  If *viewport = 0 : ProcedureReturn #NEON_VK_VIEWPORT_ERR_ARGS : EndIf
  *viewport\valid = 0
  If canvasW < 1 Or canvasH < 1 Or physicalW < 1 Or physicalH < 1
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_ARGS
  EndIf
  If canvasW > #NEON_VK_VIEWPORT_MAX_DIMENSION Or canvasH > #NEON_VK_VIEWPORT_MAX_DIMENSION Or physicalW > #NEON_VK_VIEWPORT_MAX_DIMENSION Or physicalH > #NEON_VK_VIEWPORT_MAX_DIMENSION
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_ARGS
  EndIf
  canvasWf = canvasW : canvasHf = canvasH
  physicalWf = physicalW : physicalHf = physicalH
  targetW = physicalWf
  targetH = physicalWf * (canvasHf / canvasWf)
  If targetH > physicalHf
    targetH = physicalHf
    targetW = physicalHf * (canvasWf / canvasHf)
  EndIf
  offsetX = (physicalWf - targetW) / 2.0
  offsetY = (physicalHf - targetH) / 2.0
  x = offsetX + 0.5 : y = offsetY + 0.5
  width = targetW + 0.5 : height = targetH + 0.5
  If width < 1 Or height < 1 Or x < 0 Or y < 0 Or x > physicalW Or y > physicalH Or width > physicalW - x Or height > physicalH - y
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_STATE
  EndIf
  ; Convert offset and size independently after the float32 layout operation.
  *viewport\canvasW = canvasW : *viewport\canvasH = canvasH
  *viewport\physicalW = physicalW : *viewport\physicalH = physicalH
  *viewport\x = x : *viewport\y = y
  *viewport\width = width : *viewport\height = height
  *viewport\valid = 1
  ProcedureReturn #NEON_VK_VIEWPORT_OK
EndProcedure

Procedure.i nvvRoundSignedQ16(numerator.i, denominator.i)
  If numerator < 0
    ProcedureReturn -((-numerator * #NEON_VK_VIEWPORT_Q16 + denominator / 2) / denominator)
  EndIf
  ProcedureReturn (numerator * #NEON_VK_VIEWPORT_Q16 + denominator / 2) / denominator
EndProcedure

; Coordinates are signed Q16 canvas units. They are written for physical
; pixels inside the screen, including the bars; BAR tells the caller not to
; deliver that pointer to a canvas widget. No clamp or CRT warp is applied.
Procedure.i NeonVkPortViewportMapPointer(*viewport.NeonVkPortViewport, physicalX.i, physicalY.i, *canvasXQ16, *canvasYQ16)
  If *viewport = 0 Or *canvasXQ16 = 0 Or *canvasYQ16 = 0
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_ARGS
  EndIf
  If *viewport\valid <> 1 Or *viewport\width < 1 Or *viewport\height < 1 Or *viewport\canvasW < 1 Or *viewport\canvasH < 1 Or *viewport\physicalW < 1 Or *viewport\physicalH < 1
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_STATE
  EndIf
  If *viewport\canvasW > #NEON_VK_VIEWPORT_MAX_DIMENSION Or *viewport\canvasH > #NEON_VK_VIEWPORT_MAX_DIMENSION Or *viewport\physicalW > #NEON_VK_VIEWPORT_MAX_DIMENSION Or *viewport\physicalH > #NEON_VK_VIEWPORT_MAX_DIMENSION
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_STATE
  EndIf
  If *viewport\x < 0 Or *viewport\y < 0 Or *viewport\width > *viewport\physicalW - *viewport\x Or *viewport\height > *viewport\physicalH - *viewport\y
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_STATE
  EndIf
  If physicalX < 0 Or physicalY < 0 Or physicalX >= *viewport\physicalW Or physicalY >= *viewport\physicalH
    ProcedureReturn #NEON_VK_VIEWPORT_ERR_ARGS
  EndIf
  PokeI(*canvasXQ16, nvvRoundSignedQ16((physicalX - *viewport\x) * *viewport\canvasW, *viewport\width))
  PokeI(*canvasYQ16, nvvRoundSignedQ16((physicalY - *viewport\y) * *viewport\canvasH, *viewport\height))
  If physicalX < *viewport\x Or physicalX >= *viewport\x + *viewport\width Or physicalY < *viewport\y Or physicalY >= *viewport\y + *viewport\height
    ProcedureReturn #NEON_VK_VIEWPORT_BAR
  EndIf
  ProcedureReturn #NEON_VK_VIEWPORT_INSIDE
EndProcedure
