; Complete logical banner composition for a Neon/Vulkan frame.
; The caller owns the frame and supplies stable text and logo dimensions.

Structure NeonVkBannerRect
  x.i : y.i : w.i : h.i
EndStructure

Structure NeonVkBannerArgs
  width.i
  height.i
  logoWidth.i
  logoHeight.i
  platformText.i
  buildText.i
  clockText.i
  glintActive.i
  glintX.i
  glintY.i
  clockRect.NeonVkBannerRect ; logical damage bounds, computed by clock layout/render
EndStructure

; Counter ticks spent in the banner's text and in its logo, summed since vkstat last read them.
Global gVkBanTicksText.i, gVkBanTicksLogo.i

; Share the established clock layout with boards that preserve completed pixels.
; The returned rectangle excludes the build label, logo and orange rule.
Procedure.i NeonVkBannerClockLayout(*args.NeonVkBannerArgs)
  Protected buildWidth.i,right.i
  If *args=0 : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  If *args\width<128 Or *args\height<120 Or *args\logoWidth<1 Or *args\buildText=0 : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  buildWidth=Neon_TextWidth(#NEON_FONT_SMALL,*args\buildText)
  If buildWidth<0 : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  right=*args\width-*args\logoWidth-12-16
  *args\clockRect\x=28+buildWidth+24 : *args\clockRect\y=94
  *args\clockRect\w=right-*args\clockRect\x : *args\clockRect\h=16
  If *args\clockRect\w<0 : *args\clockRect\w=0 : EndIf
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

; Clear only this rectangle when updating a loaded frame. A full banner has
; already painted its background and passes clear=0, preserving its composition.
Procedure.i NeonVkBannerClockRender(*args.NeonVkBannerArgs,clear.i)
  Protected rc.i
  If *args=0 Or (clear<>0 And clear<>1) : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  If *args\clockText=0 : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  rc=NeonVkBannerClockLayout(*args)
  If rc<>#NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  If *args\clockRect\w=0 : ProcedureReturn #NEON_VK_CHROME_OK : EndIf
  If clear<>0
    rc=NeonVkChromeBox(*args\clockRect\x,*args\clockRect\y,*args\clockRect\w,*args\clockRect\h,Neon_RGB(0,0,40))
    If rc<>#NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  EndIf
  If PeekA(*args\clockText)=0 : ProcedureReturn #NEON_VK_CHROME_OK : EndIf
  NeonVkChromeScissorSet(*args\clockRect\x,*args\clockRect\y,*args\clockRect\w,*args\clockRect\h)
  If NeonVkChromeError()<>#NEON_VK_CHROME_OK : ProcedureReturn NeonVkChromeError() : EndIf
  rc=Neon_Text(#NEON_FONT_SMALL,*args\clockRect\x,*args\clockRect\y,*args\clockText,Neon_RGB(120,132,150))
  NeonVkChromeScissorClear()
  If rc<>#NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  ProcedureReturn NeonVkChromeError()
EndProcedure

; Repaint the immutable logo beneath a moving glint in a LOAD frame.
; The title, clock, label and console remain untouched.
Procedure.i NeonVkBannerGlintRender(*args.NeonVkBannerArgs,restoreLogo.i)
  Protected rc.i,logoX.i,logoY.i=12,steel.i=Neon_RGB(226,232,240),warm.i=Neon_RGB(255,176,64)
  If *args=0 : ProcedureReturn #NEON_VK_CHROME_ERR_ARGS : EndIf
  logoX=*args\width-*args\logoWidth-12
  If logoX<0 : logoX=0 : EndIf
  If restoreLogo<>0
    rc=NeonVkChromeLogo(logoX,logoY)
    If rc<>#NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  EndIf
  If *args\glintActive <> 0
    rc = NeonVkChromeBox(logoX + *args\glintX, logoY + *args\glintY, 1, 1, warm)
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
    rc = NeonVkChromeBox(logoX + *args\glintX - 1, logoY + *args\glintY, 1, 1, steel)
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
    rc = NeonVkChromeBox(logoX + *args\glintX + 1, logoY + *args\glintY, 1, 1, steel)
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
    rc = NeonVkChromeBox(logoX + *args\glintX, logoY + *args\glintY - 1, 1, 1, steel)
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
    rc = NeonVkChromeBox(logoX + *args\glintX, logoY + *args\glintY + 1, 1, 1, steel)
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  EndIf
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

Procedure.i NeonVkBannerRender(*args.NeonVkBannerArgs)
  Define tb0.i, tb1.i
  Define rc.i, logoX.i, logoY.i, labelX.i, titleX.i
  Define titleWidth.i, labelWidth.i
  Define steel.i, warm.i, faint.i
  If *args = 0 Or *args\width < 128 Or *args\height < 120 Or *args\logoWidth < 1 Or *args\logoHeight < 1
    ProcedureReturn #NEON_VK_CHROME_ERR_ARGS
  EndIf
  If *args\platformText = 0 Or *args\buildText = 0 Or *args\clockText = 0
    ProcedureReturn #NEON_VK_CHROME_ERR_ARGS
  EndIf
  steel = Neon_RGB(226, 232, 240)
  warm = Neon_RGB(255, 176, 64)
  faint = Neon_RGB(120, 132, 150)
  rc = NeonVkChromeBox(0, 0, *args\width, 120, Neon_RGB(0, 0, 40))
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  tb0 = Ticks()
  rc = Neon_Text(#NEON_FONT_BOLD, 26, 12, "PureMetal", steel)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  titleWidth = Neon_TextWidth(#NEON_FONT_BOLD, "PureMetal ")
  labelWidth = Neon_TextWidth(#NEON_FONT_SMALL, "A N V I L")
  If titleWidth < 0 Or labelWidth < 0
    ProcedureReturn #NEON_VK_CHROME_ERR_ARGS
  EndIf
  titleX = 26 + titleWidth
  rc = Neon_Text(#NEON_FONT_BOLD, titleX, 12, "Forge", Neon_RGB(255, 148, 48))
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  rc = Neon_Text(#NEON_FONT_SMALL, 28, 70, *args\platformText, faint)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  rc = Neon_Text(#NEON_FONT_SMALL, 28, 94, *args\buildText, steel)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  rc = NeonVkBannerClockRender(*args,0)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  rc = NeonVkChromeBox(24, 114, *args\width - 48, 1, Neon_RGB(255, 148, 48))
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  rc = NeonVkChromeBox(24, 115, *args\width - 48, 1, Neon_RGB(60, 40, 20))
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  logoX = *args\width - *args\logoWidth - 12
  If logoX < 0 : logoX = 0 : EndIf
  logoY = 12
  tb1 = Ticks() : gVkBanTicksText = gVkBanTicksText + (tb1 - tb0)
  rc = NeonVkChromeLogo(logoX, logoY)
  gVkBanTicksLogo = gVkBanTicksLogo + (Ticks() - tb1)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  labelX = logoX + (*args\logoWidth - labelWidth) / 2
  rc = Neon_Text(#NEON_FONT_SMALL, labelX, logoY + *args\logoHeight + 6, "A N V I L", warm)
  If rc <> #NEON_VK_CHROME_OK : ProcedureReturn rc : EndIf
  ProcedureReturn NeonVkBannerGlintRender(*args,0)
EndProcedure

