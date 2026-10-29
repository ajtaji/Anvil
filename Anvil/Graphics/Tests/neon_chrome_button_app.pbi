; SPDX-License-Identifier: MIT
; Chrome button press/model/renderer and independent native reference proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_button.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_button.pbi"
Global Dim nbtStates.NeonChromeButtonState[4]
Global Dim nbtLabels.a[512]
Global Dim nbtSource.a[160]
Global Dim nbtHotArena.q[128]
Global nbtConfig.NeonChromeButtonConfig,nbtHot.NeonChromeHotState,nbtIdentity.NeonChromeHotIdentity
Global nbtPalette.NeonChromePalette
Global nbtChecks.i,nbtFailure.i,nbtPackets.i,nbtBase.i=8192,nbtCapture.i,nbtNative.i,nbtDrawing.i,nbtMetrics.i,nbtPrepares.i,nbtMode.i,nbtPrepFail.i,nbtMetricFail.i,nbtReentries.i
Global nbtReferenceError.i
Global nbtBodyR.f
Procedure NbtCheck(actual.i,expected.i)
  nbtChecks=nbtChecks+1
  If nbtChecks<=400 : PokeI(#NBT_REPORT+256+nbtChecks*16,actual) : PokeI(#NBT_REPORT+264+nbtChecks*16,expected) : EndIf
  If actual<>expected And nbtFailure=0 : nbtFailure=nbtChecks : EndIf
  PokeI(#NBT_REPORT+16,nbtFailure) : PokeI(#NBT_REPORT+24,nbtChecks)
EndProcedure
Procedure NbtRecord(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
  Protected p.i,n.i,i.i
  If nbtCapture=0 : ProcedureReturn : EndIf
  If nbtPackets>=28 : nbtFailure=9998 : ProcedureReturn : EndIf
  p=#NBT_REPORT+nbtBase+nbtPackets*128 : nbtPackets=nbtPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
  If text<>0
    n=NeonUtf8Length(text,64) : If n<0 : nbtFailure=9999 : ProcedureReturn : EndIf
    PokeI(p+48,n) : For i=0 To n : PokeA(p+64+i,PeekA(text+i)) : Next
  EndIf
EndProcedure
Procedure.i NbtBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NbtRecord(1,0,x,y,w,h,r,g,b,a,0)
  If h=36.0 : nbtBodyR=r : EndIf
  If nbtMode=1 : ProcedureReturn 1 : EndIf
  If nbtMode=2 : ProcedureReturn -22899 : EndIf
  If nbtMode=3
    nbtMode=0
    NbtCheck(NeonChromeButtonFlagsSet(@nbtStates[0],1,0),#NCB_ERR_BUSY)
    NbtCheck(NeonChromeButtonLabelSet(@nbtStates[0],"changed"),#NCB_ERR_BUSY)
    NbtCheck(NeonChromeButtonConfigure(@nbtStates[1],@nbtLabels[128],128,@nbtConfig),#NCB_ERR_BUSY)
    nbtReentries=nbtReentries+1
  EndIf
  If nbtNative<>0 : ProcedureReturn NeonServiceBox(x,y,w,h,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NbtText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NbtRecord(2,font,x,y,0.0,0.0,r,g,b,a,text)
  If nbtNative<>0 : ProcedureReturn NeonServiceText(font,x,y,text,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.f NbtWidth(font.i,text.i)
  Protected bytes.i=NeonUtf8Length(text,512),i.i,count.i
  If nbtDrawing<>0 : nbtMetrics=nbtMetrics+1 : EndIf
  If nbtMetricFail<>0 : ProcedureReturn -1.0 : EndIf
  If nbtNative<>0 : ProcedureReturn NeonServiceTextWidth(font,text) : EndIf
  While i<bytes : i=NeonUtf8Next(text,bytes,i) : count=count+1 : Wend
  ProcedureReturn MathFFromInt(count*7)
EndProcedure
Procedure.f NbtHeight(font.i)
  If nbtDrawing<>0 : nbtMetrics=nbtMetrics+1 : EndIf
  If nbtNative<>0 : ProcedureReturn NeonServiceLineHeight(font) : EndIf
  ProcedureReturn 16.0
EndProcedure
Procedure.i NbtPrepare(font.i,text.i)
  If nbtDrawing<>0 : nbtPrepares=nbtPrepares+1 : EndIf
  If nbtPrepFail<>0 : ProcedureReturn nbtPrepFail : EndIf
  If nbtNative<>0 : ProcedureReturn NeonServicePrepare(font,text) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure NbtSetup(index.i,font.i,label.i,lit.i,enabled.i)
  nbtConfig\id=index+1 : nbtConfig\font=font : nbtConfig\label=label : nbtConfig\lit=lit : nbtConfig\enabled=enabled
  nbtConfig\x=20.0 : nbtConfig\y=50.0+MathFFromInt(index)*70.0 : nbtConfig\w=280.0 : nbtConfig\h=36.0
  NbtCheck(NeonChromeButtonConfigure(@nbtStates[index],@nbtLabels[index*128],128,@nbtConfig),0)
  NbtCheck(NeonChromeButtonSeal(@nbtStates[index]),0)
EndProcedure
Procedure.i NbtRefStatus(rc.i)
  If rc<>0 And nbtReferenceError=0 : nbtReferenceError=rc : EndIf
  ProcedureReturn rc
EndProcedure
Procedure NbtReference(index.i,font.i)
  Protected x.f=340.0,y.f=50.0+MathFFromInt(index)*70.0,h.f=nbtStates[index]\hover,i.i,br.f=0.196,bg.f=0.200,bb.f=0.212,tr.f=0.863,tg.f=0.863,tb.f=0.863,text.i
  text="Drive" : If index=1 : text="Route" : br=0.157 : bg=0.365 : bb=0.408 : tr=0.588 : tg=0.816 : tb=0.867 : EndIf
  If index=2 : text="Unavailable" : tr=0.435 : tg=0.459 : tb=0.498 : EndIf
  If index=3 : text="Confirm" : EndIf
  If h>0.0
    For i=1 To 4
      NbtRefStatus(NeonServiceBox(x-MathFFromInt(i),y-MathFFromInt(i),280.0+MathFFromInt(2*i),36.0+MathFFromInt(2*i),0.353,0.741,0.816,(0.16*h)*(2.0/MathFFromInt(3*i))))
    Next
    br=br+0.06*h : bg=bg+0.07*h : bb=bb+0.08*h
  EndIf
  NbtRefStatus(NeonServiceBox(x,y,280.0,36.0,br,bg,bb,1.0))
  NbtRefStatus(NeonServiceBox(x,y,280.0,1.0,0.216,0.259,0.325,1.0))
  NbtRefStatus(NeonServiceBox(x,y+35.0,280.0,1.0,0.129,0.133,0.145,1.0))
  NbtRefStatus(NeonServiceText(font,x+(280.0-nbtStates[index]\textW)/2.0,y+(36.0-nbtStates[index]\lineH)/2.0,text,tr,tg,tb,1.0))
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,font.i,p.i,rc.i
  For i=0 To 16383 : PokeA(#NBT_REPORT+i,0) : Next
  PokeI(#NBT_REPORT,$4E425431) : PokeI(#NBT_REPORT+8,#NBT_SCENE)
  NbtCheck(SizeOf(NeonChromeButtonState),144)
  NbtCheck(SizeOf(NeonChromeButtonConfig),56)
  NbtCheck(NeonServiceChromeButtonInstall(),-22804)
  NbtCheck(NeonChromeGlow(0.0,0.0,10.0,10.0,1.0,1.0,1.0,0.1),-22804)
  nbtConfig\id=1 : nbtConfig\font=1 : nbtConfig\label=@nbtSource[0] : nbtConfig\enabled=1 : nbtConfig\w=280.0 : nbtConfig\h=36.0 : nbtConfig\x=20.0 : nbtConfig\y=50.0
  nbtSource[0]=$C3 : nbtSource[1]=$A9 : nbtSource[2]=0
  NbtCheck(NeonChromeButtonConfigure(@nbtStates[0],@nbtLabels[0],128,@nbtConfig),0)
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),-22804)
  nbtSource[0]=0
  NbtCheck(PeekA(NeonChromeButtonLabel(@nbtStates[0])),195)
  NbtCheck(PeekA(NeonChromeButtonLabel(@nbtStates[0])+1),169)
  NbtCheck(NeonChromeButtonRendererInstall(@NbtBox,@NbtText,@NbtWidth,@NbtHeight,@NbtPrepare),0)
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),0)
  NbtCheck(MathBitsOf(nbtStates[0]\textW),1088421888)
  NbtCheck(NeonChromeButtonLabelSet(@nbtStates[0],"Drive"),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),-22801)
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,1,0,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),1)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],300.0,60.0,1,0,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,1,1,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonFlagsSet(@nbtStates[0],0,0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,1,0,0.0),0)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonFlagsSet(@nbtStates[0],0,1),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,1,0,0.0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,2,0,0.0),-22800)
  NbtCheck(NeonChromeButtonEventGet(@nbtStates[0]),1)
  NbtCheck(NeonChromeButtonFlagsSet(@nbtStates[0],2,1),-22800)
  NbtCheck(nbtStates[0]\lit,0)
  For i=0 To 159 : nbtSource[i]=88 : Next
  NbtCheck(NeonChromeButtonLabelSet(@nbtStates[0],@nbtSource[0]),-22806)
  NbtCheck(nbtStates[0]\length,5)
  nbtSource[0]=$C0 : nbtSource[1]=$AF : nbtSource[2]=0
  NbtCheck(NeonChromeButtonLabelSet(@nbtStates[0],@nbtSource[0]),-22806)
  NbtCheck(NeonChromeButtonLabelSet(@nbtStates[0],NeonChromeButtonLabel(@nbtStates[0])+1),-22800)
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),0)
  nbtPrepFail=-22898
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),-22898)
  NbtCheck(nbtStates[0]\ready,0)
  nbtPrepFail=0 : nbtMetricFail=1
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),-22805)
  nbtMetricFail=0
  NbtCheck(NeonChromeButtonSeal(@nbtStates[0]),0)
  nbtMode=1
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),-22804)
  nbtMode=2
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),-22899)
  nbtMode=3
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(nbtReentries,1)
  NbtCheck(nbtStates[0]\enabled,1)
  NbtCheck(NeonChromeButtonNeedsRedraw(@nbtStates[0]),1)
  NbtCheck(NeonChromeStyleAnimationsSet(0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],-100.0,-100.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonNeedsRedraw(@nbtStates[0]),0)
  NbtCheck(NeonChromeStylePaletteGet(@nbtPalette),0)
  nbtPalette\line\r=1.0 : nbtPalette\line\g=1.0 : nbtPalette\line\b=1.0
  NbtCheck(NeonChromeStylePaletteSet(@nbtPalette),0)
  NbtCheck(NeonChromeButtonNeedsRedraw(@nbtStates[0]),1)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],30.0,60.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(MathBitsOf(nbtBodyR),1065353216)
  NbtCheck(NeonChromeStyleDefaults(@nbtPalette),0)
  NbtCheck(NeonChromeStylePaletteSet(@nbtPalette),0)
  NbtSetup(0,1,"Drive",0,1) : NbtSetup(1,1,"Route",1,1) : NbtSetup(2,1,"Unavailable",0,0) : NbtSetup(3,1,"Confirm",0,1)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],-100.0,-100.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[1],-100.0,-100.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[2],-100.0,-100.0,0,0,0.0),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[3],30.0,270.0,0,0,0.0),0)
  NbtCheck(NeonChromeHotConfigure(@nbtHot,@nbtHotArena[0],1024,1),0)
  NbtCheck(NeonChromeHotBind(@nbtHot),0)
  NbtCheck(NeonChromeHotBegin(@nbtHot),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[1]),-22702)
  NbtCheck(NeonChromeHotCommit(@nbtHot),-22702)
  NbtCheck(NeonChromeHotAbort(@nbtHot),0)
  NbtCheck(NeonChromeHotBegin(@nbtHot),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[2]),0)
  NbtCheck(nbtHot\count,0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(NeonChromeHotCommit(@nbtHot),0)
  NbtCheck(NeonChromeHotAt(@nbtHot,30.0,60.0,@nbtIdentity),1)
  NbtCheck(nbtIdentity\family,1)
  NbtCheck(nbtIdentity\item,1)
  NbtCheck(NeonChromeHotBind(0),0)
  NbtCheck(NeonChromeFrame(0.0,0.0,10.0,10.0,2.0,1.0,1.0,1.0),-22800)
  NbtCheck(NeonChromeGlow(0.0,0.0,10.0,10.0,1.0,1.0,1.0,MathFromBits($7FC00000)),-22800)
  nbtCapture=1 : nbtDrawing=1
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[1]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[2]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[3]),0)
  NbtCheck(NeonChromeGlow(20.0,335.0,280.0,32.0,0.7,0.5,0.2,0.12),0)
  NbtCheck(NeonChromeFrame(20.0,335.0,280.0,32.0,0.7,0.5,0.2,1.0),0)
  nbtCapture=0 : nbtDrawing=0 : PokeI(#NBT_REPORT+32,nbtPackets)
  NbtCheck(nbtPackets,28)
  NbtCheck(nbtMetrics,0)
  NbtCheck(nbtPrepares,0)
  NbtCheck(NeonServiceBind(services,35),0)
  NbtCheck(NeonServiceOpen(),0)
  NbtCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,1,14)
  NbtCheck(Bool(font>0),1)
  nbtNative=1 : nbtPackets=0 : nbtBase=12288
  NbtSetup(0,font,"Drive",0,1) : NbtSetup(1,font,"Route",1,1) : NbtSetup(2,font,"Unavailable",0,0) : NbtSetup(3,font,"Confirm",0,1)
  NbtCheck(NeonServiceChromeButtonInstall(),0)
  NbtCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  NbtCheck(NeonServiceEnd(),0)
  NbtCheck(NeonChromeButtonRendererInstall(@NbtBox,@NbtText,@NbtWidth,@NbtHeight,@NbtPrepare),0)
  NbtCheck(NeonChromeStyleAnimationsSet(#NBT_SCENE-1),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[0],-100.0,-100.0,0,0,0.05),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[1],-100.0,-100.0,0,0,0.05),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[2],-100.0,-100.0,0,0,0.05),0)
  NbtCheck(NeonChromeButtonInput(@nbtStates[3],30.0,270.0,0,0,0.05),0)
  For i=0 To 3
    p=#NBT_REPORT+128+i*24 : PokeL(p,MathBitsOf(nbtStates[i]\textW)) : PokeL(p+4,MathBitsOf(nbtStates[i]\lineH)) : PokeL(p+8,MathBitsOf(nbtStates[i]\hover)) : PokeI(p+16,nbtStates[i]\id)
  Next
  NbtCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
  NbtCheck(NeonServiceScissorSet(20.0,50.0,270.0,30.0),0)
  nbtCapture=1 : nbtDrawing=1
  NbtCheck(NeonChromeButtonDraw(@nbtStates[0]),0)
  nbtCapture=0
  NbtCheck(NeonServiceBox(20.0,82.0,10.0,3.0,1.0,0.0,0.0,1.0),0)
  NbtCheck(NeonServiceScissorClear(),0)
  nbtCapture=1
  NbtCheck(NeonChromeButtonDraw(@nbtStates[1]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[2]),0)
  NbtCheck(NeonChromeButtonDraw(@nbtStates[3]),0)
  NbtCheck(NeonChromeGlow(20.0,335.0,280.0,32.0,0.7,0.5,0.2,0.12),0)
  NbtCheck(NeonChromeFrame(20.0,335.0,280.0,32.0,0.7,0.5,0.2,1.0),0)
  nbtCapture=0 : nbtDrawing=0
  NbtCheck(NeonServiceScissorSet(340.0,50.0,270.0,30.0),0)
  NbtReference(0,font)
  NbtCheck(NeonServiceBox(340.0,82.0,10.0,3.0,1.0,0.0,0.0,1.0),0)
  NbtCheck(NeonServiceScissorClear(),0)
  For i=1 To 3 : NbtReference(i,font) : Next
  For i=1 To 4
    NbtRefStatus(NeonServiceBox(340.0-MathFFromInt(i),335.0-MathFFromInt(i),280.0+MathFFromInt(i*2),32.0+MathFFromInt(i*2),0.7,0.5,0.2,0.12*(2.0/MathFFromInt(i*3))))
  Next
  NbtRefStatus(NeonServiceBox(340.0,335.0,280.0,1.0,0.7,0.5,0.2,1.0))
  NbtRefStatus(NeonServiceBox(340.0,366.0,280.0,1.0,0.7,0.5,0.2,1.0))
  NbtRefStatus(NeonServiceBox(340.0,335.0,1.0,32.0,0.7,0.5,0.2,1.0))
  NbtRefStatus(NeonServiceBox(619.0,335.0,1.0,32.0,0.7,0.5,0.2,1.0))
  NbtCheck(nbtReferenceError,0)
  NbtCheck(NeonServiceEnd(),0)
  NbtCheck(nbtMetrics,0)
  NbtCheck(nbtPrepares,0)
  PokeI(#NBT_REPORT+40,nbtPackets) : PokeI(#NBT_REPORT+48,font) : PokeI(#NBT_REPORT+56,NeonServiceFrameOpen())
  PokeI(#NBT_REPORT+64,@nbtStates[0]) : PokeI(#NBT_REPORT+72,nbtMetrics) : PokeI(#NBT_REPORT+80,nbtPrepares) : PokeI(#NBT_REPORT+88,nbtReentries)
  NbtCheck(NeonChromeStyleAnimationsSet(1),0)
  ProcedureReturn nbtFailure
EndProcedure
