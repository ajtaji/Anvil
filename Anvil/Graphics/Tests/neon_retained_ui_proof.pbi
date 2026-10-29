; SPDX-License-Identifier: MIT
; Controlled renderer/state proof. No GPU or display provider.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_retained_ui.pbi"
Global Dim nrtArena.q[1024]
Global Dim nrtString.a[64]
Global nrtChecks.i,nrtFailure.i,nrtBoxes.i,nrtTexts.i,nrtPolys.i,nrtPrepared.i
Global nrtCallback.i,nrtReentrant.i,nrtProviderError.i,nrtFirstX.f,nrtFirstY.f
Global nrtFontProbe.i,nrtFontDrawResult.i,nrtFontDrawAllowed.i
Procedure NrtCheck(actual.i,expected.i)
  nrtChecks=nrtChecks+1
  If actual<>expected And nrtFailure=0 : nrtFailure=nrtChecks : EndIf
EndProcedure
Global nrtEvents.i,nrtWideMetric.i
Procedure NrtLog(op.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,extra.i)
  Protected p.i
  If nrtEvents>=60 : nrtFailure=9999 : ProcedureReturn : EndIf
  p=#NRT_REPORT+256+nrtEvents*56
  PokeI(p,op)
  PokeL(p+8,MathBitsOf(x)) : PokeL(p+12,MathBitsOf(y))
  PokeL(p+16,MathBitsOf(w)) : PokeL(p+20,MathBitsOf(h))
  PokeL(p+24,MathBitsOf(r)) : PokeL(p+28,MathBitsOf(g))
  PokeL(p+32,MathBitsOf(b)) : PokeL(p+36,MathBitsOf(a))
  PokeI(p+40,extra) : nrtEvents=nrtEvents+1
EndProcedure
Procedure.i NrtBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  If nrtBoxes=0 : nrtFirstX=x : nrtFirstY=y : EndIf
  NrtLog(1,x,y,w,h,r,g,b,a,0)
  nrtBoxes=nrtBoxes+1
  ProcedureReturn nrtProviderError
EndProcedure
Procedure.i NrtText(font.i,x.f,y.f,*text,r.f,g.f,b.f,a.f)
  If nrtFontProbe<>0
    nrtFontDrawResult=NeonRetainedGadgetFontSet(nrtFontProbe,3)
    nrtFontDrawAllowed=NeonRetainedMutationAllowed()
    nrtFontProbe=0
  EndIf
  NrtLog(2,x,y,0.0,0.0,r,g,b,a,PeekA(*text))
  nrtTexts=nrtTexts+1 : ProcedureReturn nrtProviderError
EndProcedure
Procedure.f NrtWidth(font.i,*text)
  Protected n.i=0
  If nrtWideMetric<>0 : ProcedureReturn MathFromBits($7F7FFFFF) : EndIf
  If *text<>0
    While PeekA(*text+n)<>0 And n<64 : n=n+1 : Wend
  EndIf
  ProcedureReturn MathFFromInt(n)*8.0
EndProcedure
Procedure.f NrtHeight(font.i)
  ProcedureReturn 16.0
EndProcedure
Procedure.i NrtPoly(x.f,y.f,rx.f,ry.f,sides.i,r.f,g.f,b.f,a.f,solid.i)
  NrtLog(3,x,y,rx,ry,r,g,b,a,sides)
  nrtPolys=nrtPolys+1 : ProcedureReturn nrtProviderError
EndProcedure
Procedure.i NrtPrepare(font.i,*text)
  nrtPrepared=nrtPrepared+1 : ProcedureReturn nrtProviderError
EndProcedure
Procedure NrtEvent(id.i,kind.i,tag.i)
  nrtCallback=nrtCallback+1
  NrtCheck(id,77) : NrtCheck(kind,1) : NrtCheck(tag,999)
  NrtCheck(NeonRetainedReset(),0)
  NrtCheck(Bool(NeonRetainedAddLabel(90,0.0,0.0,@nrtString[0])<>0),1)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,h.i,old.i,id.i,kind.i,tag.i
  Protected phase.f
  Protected *g.NeonRetainedGadget
  For i=0 To 4095 : PokeA(#NRT_REPORT+i,0) : Next
  phase=nruPhaseAdvance(6.0,0.25)
  NrtCheck(Bool(MathFAbs(phase-0.7168145)<0.0001),1)
  phase=0.0
  For i=0 To 4999 : phase=nruPhaseAdvance(phase,1.0) : Next
  NrtCheck(nruFinite(phase),1) : NrtCheck(Bool(phase>=0.0 And phase<6.28318530718),1)
  phase=nruPhaseAdvance(0.0,MathFromBits($7F7FFFFF))
  NrtCheck(nruFinite(phase),1) : NrtCheck(Bool(phase>=0.0 And phase<6.28318530718),1)
  nrtString[0]=65 : nrtString[1]=66 : nrtString[2]=0
  NrtCheck(NeonRetainedConfigure(@nrtArena[0],8192,8,64),0)
  NrtCheck(NeonRetainedMutationAllowed(),1)
  NrtCheck(NeonRetainedViewport(10.0,20.0,400.0,200.0,800.0,400.0),0)
  NrtCheck(NeonRetainedFontSet(0),0)
  NrtCheck(NeonRetainedRendererInstall(@NrtBox,@NrtText,@NrtWidth,@NrtHeight,@NrtPoly,0),#NRU_ERR_ARGS)
  NrtCheck(NeonRetainedPrepare(),#NRU_ERR_RENDERER)
  NrtCheck(NeonRetainedRendererInstall(@NrtBox,@NrtText,@NrtWidth,@NrtHeight,@NrtPoly,@NrtPrepare),0)
  nrtWideMetric=1
  NrtCheck(NeonRetainedAddButton(0,-MathFromBits($7F7FFFFF),0.0,20.0,30.0,@nrtString[0],0,0),0)
  NrtCheck(NeonRetainedError(),#NRU_ERR_ARGS) : NrtCheck(NeonRetainedCount(),0)
  nrtWideMetric=0
  NrtCheck(NeonRetainedUpdateInput(MathFromBits($7F7FFFFF),MathFromBits($7F7FFFFF),0,0,0,0,0),#NRU_ERR_ARGS)
  NrtCheck(nruInputBusy,0)
  h=NeonRetainedAddButton(77,100.0,100.0,20.0,30.0,@nrtString[0],0,999)
  NrtCheck(Bool(h<>0),1) : old=h : *g=NeonRetainedGet(h)
  NrtCheck(MathBitsOf(*g\w),MathBitsOf(56.0))
  NrtCheck(MathBitsOf(*g\x),MathBitsOf(82.0))
  NrtCheck(NeonRetainedGadgetFontSet(h,2),0) : NrtCheck(*g\font,2)
  NrtCheck(NeonRetainedGadgetFontSet(h,-2),#NRU_ERR_ARGS) : NrtCheck(*g\font,2)
  NrtCheck(NeonRetainedGadgetFontSet(h,-1),0) : NrtCheck(*g\font,-1)
  NrtCheck(NeonRetainedGadgetFontSet(h,0),0)
  nrtString[0]=90 : NrtCheck(PeekA(*g\text),65)
  NrtCheck(NeonRetainedUpdateInput(60.0,75.0,0,1,0,0,0),0)
  NrtCheck(NeonRetainedEventGet(@id,@kind,@tag),1)
  NrtCheck(id,77) : NrtCheck(kind,1) : NrtCheck(tag,999)
  NrtCheck(NeonRetainedEventGet(@id,@kind,@tag),0)
  NrtCheck(NeonRetainedEventHandlerInstall(@NrtEvent),0)
  NrtCheck(NeonRetainedUpdateInput(60.0,75.0,0,1,0,0,0),0)
  NrtCheck(nrtCallback,1)
  nruInputBusy=1 : NrtCheck(NeonRetainedUpdateInput(0.0,0.0,0,0,0,0,0),#NRU_ERR_BUSY) : nruInputBusy=0
  NrtCheck(NeonRetainedCount(),1)
  NrtCheck(NeonRetainedGet(old),0) : NrtCheck(NeonRetainedError(),#NRU_ERR_STALE)
  NrtCheck(NeonRetainedGadgetFontSet(old,1),#NRU_ERR_STALE)
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,0,1,0),0)
  NrtCheck(NeonRetainedReset(),0)
  NrtCheck(NeonRetainedEventHandlerInstall(0),0)
  nrtString[0]=65 : nrtString[1]=124 : nrtString[2]=66 : nrtString[3]=0
  NrtCheck(Bool(NeonRetainedAddLabel(1,10.0,10.0,@nrtString[0])<>0),1)
  NrtCheck(Bool(NeonRetainedAddBreadcrumb(2,10.0,30.0,@nrtString[0])<>0),1)
  NrtCheck(Bool(NeonRetainedAddButton(3,20.0,70.0,100.0,30.0,@nrtString[0],1,0)<>0),1)
  h=NeonRetainedAddSlider(4,20.0,140.0,200.0,30.0,0.5,@nrtString[0],0)
  NrtCheck(Bool(h<>0),1)
  NrtCheck(NeonRetainedValueSet(h,1.1),#NRU_ERR_ARGS)
  NrtCheck(NeonRetainedUpdateInput(70.0,95.0,1,0,0,0,0),0)
  *g=NeonRetainedGet(h) : NrtCheck(MathBitsOf(*g\value),MathBitsOf(0.5))
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,1,0,0),0)
  NrtCheck(MathBitsOf(*g\value),MathBitsOf(0.55))
  h=NeonRetainedAddToggle(5,300.0,70.0,180.0,30.0,@nrtString[0],0,0)
  NrtCheck(Bool(h<>0),1)
  NrtCheck(NeonRetainedUpdateInput(170.0,60.0,0,1,0,0,0),0)
  *g=NeonRetainedGet(h) : NrtCheck(*g\isActive,1)
  NrtCheck(Bool(NeonRetainedAddMeter(6,300.0,140.0,200.0,30.0,0.5,@nrtString[0])<>0),1)
  h=NeonRetainedAddDipBank(7,20.0,240.0,2,1,@nrtString[0],0)
  NrtCheck(Bool(h<>0),1)
  NrtCheck(NeonRetainedUpdateInput(50.0,150.0,1,0,0,0,0),0)
  *g=NeonRetainedGet(h) : NrtCheck(*g\isActive,3)
  NrtCheck(NeonRetainedUpdateInput(50.0,150.0,1,0,0,0,0),0)
  NrtCheck(*g\isActive,3)
  ; A new press is distinct from dragging a held pointer to another control.
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,0,0,0),0)
  h=NeonRetainedAddCarousel(8,300.0,240.0,200.0,30.0,@nrtString[0],0,0)
  NrtCheck(Bool(h<>0),1)
  NrtCheck(NeonRetainedUpdateInput(200.0,150.0,1,0,0,0,0),0)
  *g=NeonRetainedGet(h) : NrtCheck(MathBitsOf(*g\value),MathBitsOf(1.0))
  NrtCheck(NeonRetainedUpdateInput(200.0,150.0,1,0,0,0,0),0)
  NrtCheck(MathBitsOf(*g\value),MathBitsOf(1.0))
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,1,0,0),0)
  NrtCheck(MathBitsOf(*g\value),MathBitsOf(0.0))
  NrtCheck(NeonRetainedCount(),8)
  NrtCheck(NeonRetainedAddLabel(9,0.0,0.0,0),0)
  NrtCheck(NeonRetainedError(),#NRU_ERR_CAPACITY)
  NrtCheck(NeonRetainedPrepare(),0) : NrtCheck(nrtPrepared,13)
  nrtFontProbe=h
  NrtCheck(NeonRetainedDrawUI(0.0),0)
  NrtCheck(nrtFontDrawResult,#NRU_ERR_BUSY) : NrtCheck(nrtFontDrawAllowed,0)
  *g=NeonRetainedGet(h) : NrtCheck(*g\font,0)
  NrtCheck(nrtBoxes,41) : NrtCheck(nrtTexts,12) : NrtCheck(nrtPolys,3)
  NrtCheck(MathBitsOf(nrtFirstX),MathBitsOf(10.0))
  NrtCheck(MathBitsOf(nrtFirstY),MathBitsOf(50.0))
  nrtProviderError=-1234
  NrtCheck(NeonRetainedDrawUI(0.0),-1234)
  NrtCheck(NeonRetainedPrepare(),-1234)
  nrtProviderError=0 : NrtCheck(NeonRetainedReset(),0)
  NrtCheck(NeonRetainedDrawUI(-0.1),#NRU_ERR_ARGS)
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,0,1,0),0)
  NrtCheck(NeonRetainedConfigure(@nrtArena[0]+1,8191,8,64),#NRU_ERR_ARGS)
  NrtCheck(NeonRetainedFontSet(-1),0)
  h=NeonRetainedAddDipBank(10,0.0,0.0,64,0,0,0)
  NrtCheck(Bool(h<>0),1)
  NrtCheck(NeonRetainedUpdateInput(-10.0,-10.0,0,0,-1,0,1),0)
  *g=NeonRetainedGet(h)
  NrtCheck(*g\subFocus,63) : NrtCheck(*g\isActive,$8000000000000000)
  NrtCheck(NeonRetainedReset(),0)
  NrtCheck(NeonRetainedGet(h),0)
  For i=0 To 63 : nrtString[i]=65 : Next
  NrtCheck(NeonRetainedAddLabel(0,0.0,0.0,@nrtString[0]),0)
  NrtCheck(NeonRetainedError(),#NRU_ERR_TEXT)
  NrtCheck(NeonRetainedCount(),0)
  NrtCheck(NeonRetainedReset(),0)
  NrtCheck(NeonRetainedViewport(0.0,0.0,1000.0,600.0,1000.0,600.0),0)
  NrtCheck(Bool(NeonRetainedAddButton(101,10.0,10.0,100.0,100.0,0,0,0)>0),1)
  h=NeonRetainedAddButton(102,20.0,20.0,100.0,100.0,0,0,0)
  NrtCheck(Bool(h>0),1)
  NrtCheck(NeonRetainedHit(25.0,25.0),h)
  NrtCheck(NeonRetainedUpdateInput(25.0,25.0,0,1,0,0,0),0)
  NrtCheck(NeonRetainedEventGet(@id,@kind,@tag),1)
  NrtCheck(id,102) : NrtCheck(kind,1)
  PokeI(#NRT_REPORT,$4E525431) : PokeI(#NRT_REPORT+8,nrtFailure)
  PokeI(#NRT_REPORT+16,nrtChecks) : PokeI(#NRT_REPORT+24,#PMF_CHIP)
  PokeI(#NRT_REPORT+32,nrtBoxes) : PokeI(#NRT_REPORT+40,nrtTexts)
  PokeI(#NRT_REPORT+48,nrtPolys) : PokeI(#NRT_REPORT+56,nrtPrepared)
  PokeI(#NRT_REPORT+80,nrtEvents)
  PokeI(#NRT_REPORT+64,nrtCallback) : PokeI(#NRT_REPORT+72,$3154524E)
  ProcedureReturn nrtFailure
EndProcedure
