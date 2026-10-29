; Bounded Neon-style TrueType handle for the Vulkan canvas port.
; Include after neon_vk_port.pbi and neon_vk_chrome.pbi. The caller owns the
; handle and must keep its selected TrueType slot loaded for its lifetime.

XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"

#NEON_VK_FONT_ERR_HANDLE = -21309
#NEON_VK_FONT_ERR_STALE = -21310
#NEON_VK_FONT_ERR_SEQUENCE = -21311
#NEON_VK_FONT_ERR_METRICS = -21312

Structure NeonVkPortFontRef
  slot.i
  generation.i
  face.i
  pixelHeight.i
  fixedAdvanceQ16.i
  snapToPixel.i
  controlMode.i
EndStructure

; Slots 0..3 hold loaded file faces; slot 4 is Anvil's embedded boot face.
; This binds existing bytes only. It does not load, replace or own a face.
Procedure.i NeonVkPortFontBind(*font.NeonVkPortFontRef, slot.i, face.i, pixelHeight.i)
  If *font = 0 Or slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS Or face < 0 Or face > 3 Or pixelHeight < 1 Or pixelHeight > 512
    ProcedureReturn #NEON_VK_FONT_ERR_HANDLE
  EndIf
  If AnvilTrueTypeSlotBytes(slot) < 1 Or AnvilTrueTypeSlotGeneration(slot) < 1
    ProcedureReturn #NEON_VK_FONT_ERR_HANDLE
  EndIf
  *font\slot = slot : *font\generation = AnvilTrueTypeSlotGeneration(slot)
  *font\face = face : *font\pixelHeight = pixelHeight : *font\fixedAdvanceQ16=0 : *font\snapToPixel=1 : *font\controlMode=0
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i nvpFontActivate(*font.NeonVkPortFontRef)
  If *font = 0 Or *font\slot < 0 Or *font\slot >= #ANVIL_TTS_MAX_SLOTS Or *font\face < 0 Or *font\face > 3 Or *font\pixelHeight < 1 Or *font\pixelHeight > 512 Or *font\fixedAdvanceQ16<0 Or *font\fixedAdvanceQ16>536870912 Or *font\snapToPixel<0 Or *font\snapToPixel>1 Or *font\controlMode<0 Or *font\controlMode>2
    ProcedureReturn #NEON_VK_FONT_ERR_HANDLE
  EndIf
  If *font\generation < 1 Or AnvilTrueTypeSlotGeneration(*font\slot) <> *font\generation Or AnvilTrueTypeSlotBytes(*font\slot) < 1
    ProcedureReturn #NEON_VK_FONT_ERR_STALE
  EndIf
  If NeonVkChromeFontSelect(*font\slot,*font\generation,*font\face,*font\pixelHeight) <> #NEON_VK_CHROME_OK
    ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE
  EndIf
  ProcedureReturn #NEON_OK
EndProcedure

; Derive another role/size from the same loaded generation, without another
; face load or ownership claim. Policies are copied; later setters are independent.
; Destination is separate caller-owned aligned storage, unchanged on refusal.
Procedure.i NeonVkPortFontDerive(*out.NeonVkPortFontRef,*source.NeonVkPortFontRef,face.i,pixelHeight.i)
  Protected candidate.NeonVkPortFontRef,rc.i,i.i
  If nvcInFrame<>0 : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  If NeonByteSpan(*out,SizeOf(NeonVkPortFontRef))=0 Or NeonByteSpan(*source,SizeOf(NeonVkPortFontRef))=0 Or (*out & 7)<>0 Or (*source & 7)<>0
    ProcedureReturn #NEON_VK_FONT_ERR_HANDLE
  EndIf
  If NeonByteOverlap(*out,SizeOf(NeonVkPortFontRef),*source,SizeOf(NeonVkPortFontRef)) : ProcedureReturn #NEON_VK_FONT_ERR_HANDLE : EndIf
  rc=nvpFontActivate(*source) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonVkPortFontBind(@candidate,*source\slot,face,pixelHeight) : If rc<>0 : ProcedureReturn rc : EndIf
  candidate\fixedAdvanceQ16=*source\fixedAdvanceQ16
  candidate\snapToPixel=*source\snapToPixel : candidate\controlMode=*source\controlMode
  For i=0 To SizeOf(NeonVkPortFontRef)-8 Step 8 : PokeI(*out+i,PeekI(@candidate+i)) : Next
  ProcedureReturn #NEON_OK
EndProcedure

; Fixed advance is stored per reference and passed explicitly on every call.
; Changing it is idle-only; existing glyph rasters remain valid. Q16 rounding
; is nearest; a positive value below one Q16 unit refuses instead of becoming0.
Procedure.i NeonVkPortFontSetFixedAdvanceQ16(*font.NeonVkPortFontRef,q.i)
  Protected rc.i
  If nvcInFrame<>0 : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  If q<0 Or q>536870912 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  rc=nvpFontActivate(*font) : If rc<>0 : ProcedureReturn rc : EndIf
  *font\fixedAdvanceQ16=q : ProcedureReturn 0
EndProcedure
Procedure.i NeonVkPortFontSetFixedAdvance(*font.NeonVkPortFontRef,advance.f)
  Protected q.i
  If advance<0.0 Or (MathBitsOf(advance) & $7FFFFFFF)>$46000000 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  q=MathFToInt(advance*65536.0+0.5)
  If advance>0.0 And q=0 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn NeonVkPortFontSetFixedAdvanceQ16(*font,q)
EndProcedure
Procedure.f NeonVkPortFontFixedAdvance(*font.NeonVkPortFontRef)
  If nvpFontActivate(*font)<>0 : ProcedureReturn -1.0 : EndIf
  ProcedureReturn MathFFromInt(*font\fixedAdvanceQ16)/65536.0
EndProcedure

; The historical Anvil default is snapped. Disabling snap preserves Q16 ink
; origins through camera and canvas mapping. It does not change text metrics,
; layout-cache keys or atlas rasters, and never prepares work inside a frame.
Procedure.i NeonVkPortFontSetSnapToPixel(*font.NeonVkPortFontRef,enabled.i)
  Protected rc.i
  If nvcInFrame<>0 : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  If enabled<0 Or enabled>1 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  rc=nvpFontActivate(*font) : If rc<>0 : ProcedureReturn rc : EndIf
  *font\snapToPixel=enabled : ProcedureReturn 0
EndProcedure
Procedure.i NeonVkPortFontSnapToPixel(*font.NeonVkPortFontRef)
  If nvpFontActivate(*font)<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn *font\snapToPixel
EndProcedure

; Legacy0 preserves existing CR/LF wrapping; hide1 drops C0/DEL; show2
; emits one visible box per control, including CR/LF. All calls are explicit.
Procedure.i NeonVkPortFontSetControlMode(*font.NeonVkPortFontRef,mode.i)
  Protected rc.i
  If nvcInFrame<>0 : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  If mode<0 Or mode>2 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  rc=nvpFontActivate(*font) : If rc<>0 : ProcedureReturn rc : EndIf
  *font\controlMode=mode : ProcedureReturn 0
EndProcedure
Procedure.i NeonVkPortFontSetShowControls(*font.NeonVkPortFontRef,enabled.i)
  If enabled<0 Or enabled>1 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn NeonVkPortFontSetControlMode(*font,enabled+1)
EndProcedure
Procedure.i NeonVkPortFontControlMode(*font.NeonVkPortFontRef)
  If nvpFontActivate(*font)<>0 : ProcedureReturn -1 : EndIf
  ProcedureReturn *font\controlMode
EndProcedure

; Every run that may appear in a frame must be warmed before FrameBegin.
; Loaded faces/heights may be mixed in one frame after all runs are warmed.
Procedure.i NeonVkPortFontWarm(*font.NeonVkPortFontRef, *s)
  Protected rc.i
  If nvcInFrame <> 0 Or *s = 0 : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  rc = nvpFontActivate(*font)
  If rc <> #NEON_OK : ProcedureReturn rc : EndIf
  rc = NeonVkChromeWarmTrueTypeTextControls(*font\pixelHeight, *s,*font\controlMode)
  If rc < 0 : ProcedureReturn rc : EndIf
  ProcedureReturn #NEON_OK
EndProcedure

; Width and line height are the active Anvil TrueType layout metrics. They
; explicit fixed advance is Q16 source pixels, not desktop point/DPI sizing.
Procedure.f NeonVkPortFontTextWidth(*font.NeonVkPortFontRef, *s, scaled.i)
  Protected measured.i
  If nvpTextScaleSupported(scaled, 1) = 0 Or *s = 0 : ProcedureReturn -1.0 : EndIf
  If nvpFontActivate(*font) <> #NEON_OK : ProcedureReturn -1.0 : EndIf
  measured = NeonVkChromeMeasureWidthControls(*font\face, *s,*font\fixedAdvanceQ16,*font\controlMode)
  If measured < 0 : ProcedureReturn -1.0 : EndIf
  ProcedureReturn MathFFromInt(measured) / 65536.0
EndProcedure

Procedure.i NeonVkPortFontLineHeight(*font.NeonVkPortFontRef)
  If nvpFontActivate(*font) <> #NEON_OK : ProcedureReturn #NEON_VK_FONT_ERR_SEQUENCE : EndIf
  ProcedureReturn NeonVkChromeMeasureLineHeight(*font\face)
EndProcedure

; Caret positions are source pixels before camera/canvas mapping. Each query
; revalidates the font generation and uses the same spacing/control policies
; as drawing. Queries do not prepare glyph rasters or modify font policies.
Procedure.i NeonVkPortFontPrepareCarets(*font.NeonVkPortFontRef,*s)
  Protected rc.i=nvpFontActivate(*font)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonVkChromePrepareCarets(*font\face,*s,*font\fixedAdvanceQ16,*font\controlMode)
  If rc<1 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn rc
EndProcedure

; Exact scalar boundary, including multiline baseline Y and UTF8 byte offset.
Procedure.i NeonVkPortFontCaretPoint(*font.NeonVkPortFontRef,*s,column.i,xOut.i,yOut.i,byteOut.i)
  Protected rc.i=NeonVkPortFontPrepareCarets(*font,*s)
  If rc<0 : ProcedureReturn rc : EndIf
  If AnvilTrueTypeCaretPoint(column,xOut,yOut,byteOut)=0 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn 0
EndProcedure

; Explicit line, Q16 source X. Returns a scalar column or a named error.
Procedure.i NeonVkPortFontCaretColumnForX(*font.NeonVkPortFontRef,*s,line.i,xQ16.q)
  Protected rc.i=NeonVkPortFontPrepareCarets(*font,*s)
  If rc<0 : ProcedureReturn rc : EndIf
  rc=AnvilTrueTypeCaretColumnForX(line,xQ16)
  If rc<0 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn rc
EndProcedure

; Single-line compatibility query. Proportional text clamps at the end;
; fixed cells extrapolate beyond it using the final pen plus extra cells.
; Hidden controls within the text remain zero-width, matching actual drawing.
; Consume the current serialized caret snapshot before another layout call.
Procedure.f NeonVkPortCaretXPrepared(lines.i,advanceQ16.i,column.i)
  Protected last.i,extra.i,x.i,y.i,offset.i
  If lines<>1 Or column>#ANVIL_TTL_MAX_GLYPHS : ProcedureReturn -1.0 : EndIf
  If column<=0 : ProcedureReturn 0.0 : EndIf
  last=AnvilTrueTypeCaretCount()-1
  If column>last : extra=column-last : column=last : EndIf
  If AnvilTrueTypeCaretPoint(column,@x,@y,@offset)=0 : ProcedureReturn -1.0 : EndIf
  If advanceQ16>0 : x+extra*advanceQ16 : EndIf
  ProcedureReturn MathFFromInt(x)/65536.0
EndProcedure

Procedure.f NeonVkPortFontTextXForColumn(*font.NeonVkPortFontRef,*s,column.i)
  Protected lines.i=NeonVkPortFontPrepareCarets(*font,*s)
  If lines<0 : ProcedureReturn -1.0 : EndIf
  ProcedureReturn NeonVkPortCaretXPrepared(lines,*font\fixedAdvanceQ16,column)
EndProcedure

; Single-line nearest-column query, clamped to the source scalar count.
; Nonfinite or out-of-range input refuses; x<=0 retains the column-zero rule.
Procedure.i NeonVkPortCaretColumnPrepared(lines.i,x.f)
  Protected q.i
  If lines<0 : ProcedureReturn lines : EndIf
  If lines<>1 Or (MathBitsOf(x)&$7FFFFFFF)>$49742400 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  If x<=0.0 : ProcedureReturn 0 : EndIf
  q=MathFToInt(x*65536.0+0.5)
  ProcedureReturn AnvilTrueTypeCaretColumnForX(0,q)
EndProcedure

Procedure.i NeonVkPortFontTextColumnForX(*font.NeonVkPortFontRef,*s,x.f)
  Protected lines.i=NeonVkPortFontPrepareCarets(*font,*s)
  ProcedureReturn NeonVkPortCaretColumnPrepared(lines,x)
EndProcedure

Procedure.i NeonVkPortFontText(*font.NeonVkPortFontRef, x.f, y.f, *s, r.f, g.f, b.f, a.f, scaled.i, ignoreCamera.i)
  Protected rc.i = nvpFontActivate(*font)
  If rc <> #NEON_OK : ProcedureReturn rc : EndIf
  ProcedureReturn NeonVkPortTextControls(*font\face, x, y, *s, r, g, b, a, scaled, ignoreCamera,*font\fixedAdvanceQ16,*font\snapToPixel,*font\controlMode)
EndProcedure

Procedure.i NeonVkPortFontTextRight(*font.NeonVkPortFontRef, xRight.f, y.f, *s, r.f, g.f, b.f, a.f, scaled.i, ignoreCamera.i)
  Protected rc.i = nvpFontActivate(*font)
  Protected width.f
  If rc <> #NEON_OK : ProcedureReturn rc : EndIf
  If nvpTextScaleSupported(scaled, 1) = 0 : ProcedureReturn #NEON_VK_PORT_ERR_TEXT_SCALE : EndIf
  width = NeonVkPortFontTextWidth(*font, *s, scaled)
  If width < 0.0 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn NeonVkPortFontText(*font, xRight - width, y, *s, r, g, b, a, scaled, ignoreCamera)
EndProcedure

Procedure.i NeonVkPortFontTextCentre(*font.NeonVkPortFontRef, x.f, w.f, y.f, *s, r.f, g.f, b.f, a.f, scaled.i, ignoreCamera.i)
  Protected rc.i = nvpFontActivate(*font)
  Protected width.f
  If rc <> #NEON_OK : ProcedureReturn rc : EndIf
  If nvpTextScaleSupported(scaled, 1) = 0 : ProcedureReturn #NEON_VK_PORT_ERR_TEXT_SCALE : EndIf
  width = NeonVkPortFontTextWidth(*font, *s, scaled)
  If width < 0.0 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  ProcedureReturn NeonVkPortFontText(*font, x + (w - width) / 2.0, y, *s, r, g, b, a, scaled, ignoreCamera)
EndProcedure
