; SPDX-License-Identifier: MIT
; Returning tab-strip interaction/renderer and resident application proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_tabs.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_tabs.pbi"
Global nttState.NeonChromeTabState,nttOther.NeonChromeTabState,nttConfig.NeonChromeTabConfig
Global Dim nttArena.q[1024]
Global Dim nttSmall.q[128]
Global Dim nttBuffer.a[64]
Global nttChecks.i,nttFailure.i,nttCapture.i,nttPackets.i,nttDrawing.i,nttMetrics.i,nttPrepares.i
Global nttMode.i,nttReenter.i,nttOtherBusy.i,nttClearFailure.i
Procedure NttCheck(actual.i,expected.i)
  nttChecks=nttChecks+1
  PokeI(#NTT_REPORT+256+nttChecks*16,actual) : PokeI(#NTT_REPORT+264+nttChecks*16,expected)
  If actual<>expected And nttFailure=0 : nttFailure=nttChecks : EndIf
  PokeI(#NTT_REPORT+16,nttFailure) : PokeI(#NTT_REPORT+24,nttChecks)
EndProcedure
Procedure NttPacket(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
  Protected p.i,i.i,len.i
  If nttCapture=0 : ProcedureReturn : EndIf
  p=#NTT_REPORT+4096+nttPackets*128 : nttPackets=nttPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
  len=0 : If text<>0 : len=NeonUtf8Length(text,64) : EndIf
  PokeI(p+56,len)
  For i=0 To len-1
    PokeA(p+64+i,PeekA(text+i)) : If i<8 : PokeA(p+48+i,PeekA(text+i)) : EndIf
  Next
EndProcedure
Procedure.i NttBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NttPacket(1,0,x,y,w,h,r,g,b,a,0)
  If nttMode=1 : ProcedureReturn -22099 : EndIf
  If nttMode=2 : ProcedureReturn 1 : EndIf
  If nttMode=3
    nttReenter=NeonChromeTabsInput(@nttState,0.0,0.0,0,0,0,0.0)
    nttOtherBusy=NeonChromeTabsBeginBuild(@nttOther)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NttText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NttPacket(2,font,x,y,0.0,0.0,r,g,b,a,text) : ProcedureReturn 0
EndProcedure
Procedure.f NttWidth(font.i,text.i)
  Protected bytes.i=NeonUtf8Length(text,512),i.i,count.i,width.i=8
  If nttDrawing<>0 : nttMetrics=nttMetrics+1 : EndIf
  If bytes<0 : ProcedureReturn -1.0 : EndIf
  While i<bytes : i=NeonUtf8Next(text,bytes,i) : count=count+1 : Wend
  If font=1 : width=7 : ElseIf font=2 : width=10 : EndIf
  ProcedureReturn MathFFromInt(count*width)
EndProcedure
Procedure.f NttHeight(font.i)
  If nttDrawing<>0 : nttMetrics=nttMetrics+1 : EndIf
  If font=1 : ProcedureReturn 14.0 : EndIf
  ProcedureReturn 16.0
EndProcedure
Procedure.i NttPrepare(font.i,text.i)
  If nttDrawing<>0 : nttPrepares=nttPrepares+1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NttClip(x.f,y.f,w.f,h.f)
  NttPacket(3,0,x,y,w,h,0.0,0.0,0.0,0.0,0) : ProcedureReturn 0
EndProcedure
Procedure.i NttClear()
  NttPacket(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0)
  If nttClearFailure<>0 : ProcedureReturn -22098 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NttBuild(*s.NeonChromeTabState,longName.i,first.i)
  Protected rc.i
  rc=NeonChromeTabsAdd(*s,10,first,#NCT_NORMAL) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeTabsAdd(*s,20,"pipe|name",#NCT_PINNED) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeTabsAdd(*s,30,"Preview",#NCT_ITALIC) : If rc<>0 : ProcedureReturn rc : EndIf
  If longName<>0 : rc=NeonChromeTabsAdd(*s,40,"an extremely long document name which needs shortening",#NCT_NORMAL) : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,rc.i,ui.i,small.i,alternate.i,*n.NeonChromeTab,refx.f,labelx.f,ty.f,cellW.f
  For i=0 To 16383 Step 8 : PokeI(#NTT_REPORT+i,0) : Next
  PokeI(#NTT_REPORT,$4E545431) : PokeI(#NTT_REPORT+8,1) : PokeI(#NTT_REPORT+128,#NTT_SCENE)
  NttCheck(SizeOf(NeonChromeTab),88) : NttCheck(SizeOf(NeonChromeTabConfig),80)
  NttCheck(NeonServiceChromeTabsInstall(),#NCT_ERR_RENDERER)
  NttCheck(NeonChromeTabsRendererInstall(@NttBox,@NttText,@NttWidth,@NttHeight,@NttPrepare,@NttClip,@NttClear),0)
  nttConfig\x=10.0 : nttConfig\y=20.0 : nttConfig\w=600.0 : nttConfig\h=30.0 : nttConfig\scale=1.0
  nttConfig\font=0 : nttConfig\smallFont=1 : nttConfig\italicFont=2 : nttConfig\withClose=1 : nttConfig\flags=#NCT_SCROLL : nttConfig\activeId=10
  NttCheck(NeonChromeTabsConfigure(@nttOther,@nttSmall[0],1024,2,128,@nttConfig),0)
  NttCheck(NeonChromeTabsConfigure(@nttState,@nttArena[0],8192,12,128,@nttConfig),0)
  PokeL(@nttBuffer[0],$00656E4F)
  NttCheck(NttBuild(@nttState,0,@nttBuffer[0]),0)
  For i=0 To 63 : PokeA(@nttBuffer[0]+i,0) : Next
  *n=NeonChromeTabsGet(@nttState,10) : NttCheck(PeekL(*n\label),$00656E4F)
  NttCheck(NeonChromeTabsSeal(@nttState),0)
  *n=NeonChromeTabsGet(@nttState,30) : NttCheck(*n\font,2) : NttCheck(*n\width,114)
  NttCheck(NeonChromeTabAt(@nttState,90.0,30.0),20)
  NttCheck(NeonChromeTabAt(@nttState,20.0,49.0),0)
  NttCheck(NeonChromeTabsInput(@nttState,188.0,34.0,1,0,0,0.0),0)
  NttCheck(NeonChromeTabsPinGet(@nttState),20) : NttCheck(NeonChromeTabsCloseGet(@nttState),0) : NttCheck(nttState\activeId,10)
  NttCheck(NeonChromeTabsInput(@nttState,-100.0,-100.0,0,0,0,0.0),0)
  NttCheck(NeonChromeTabsInput(@nttState,72.0,34.0,1,0,0,0.0),0)
  NttCheck(NeonChromeTabsCloseGet(@nttState),10) : NttCheck(NeonChromeTabsPinGet(@nttState),0)
  NttCheck(NeonChromeTabsInput(@nttState,-100.0,-100.0,0,0,0,0.0),0)
  NttCheck(NeonChromeTabsInput(@nttState,210.0,30.0,1,0,0,0.05),0)
  NttCheck(nttState\activeId,30)
  NttCheck(Bool(nttState\indicatorX>14.0 And nttState\indicatorX<198.0),1)
  For i=0 To 14 : rc=NeonChromeTabsInput(@nttState,210.0,30.0,0,0,0,0.05) : Next
  NttCheck(rc,0) : NttCheck(nttState\indicatorX,198) : NttCheck(nttState\indicatorW,114)
  NttCheck(NeonChromeTabsNeedsRedraw(@nttState),0)
  NttCheck(NeonChromeTabsSelect(@nttState,10,0),0)
  For i=0 To 14 : rc=NeonChromeTabsInput(@nttState,-100.0,-100.0,0,0,0,0.05) : Next
  NttCheck(rc,0)
  nttCapture=1 : nttDrawing=1 : NttCheck(NeonChromeTabsDraw(@nttState),0) : nttDrawing=0 : nttCapture=0
  NttCheck(nttPackets,17) : NttCheck(nttMetrics,0) : NttCheck(nttPrepares,0) : PokeI(#NTT_REPORT+32,nttPackets)
  nttMode=1 : NttCheck(NeonChromeTabsDraw(@nttState),-22099)
  nttMode=2 : NttCheck(NeonChromeTabsDraw(@nttState),#NCT_ERR_RENDERER)
  nttMode=3 : NttCheck(NeonChromeTabsDraw(@nttState),0)
  NttCheck(nttReenter,#NCT_ERR_BUSY) : NttCheck(nttOtherBusy,#NCT_ERR_BUSY)
  nttMode=0 : nttClearFailure=1
  NttCheck(NeonChromeTabsDraw(@nttState),-22098) : NttCheck(nttState\cleanupError,-22098)
  nttClearFailure=0 : NttCheck(NeonChromeTabsDraw(@nttState),0)
  nttConfig\w=200.0 : nttConfig\activeId=40
  NttCheck(NeonChromeTabsConfigure(@nttState,@nttArena[0],8192,12,128,@nttConfig),0)
  NttCheck(NttBuild(@nttState,1,"One"),0) : NttCheck(NeonChromeTabsSeal(@nttState),0)
  *n=NeonChromeTabsGet(@nttState,40)
  NttCheck(*n\width,148) : NttCheck(*n\shownBytes,13)
  NttCheck(*n\shownW,104)
  For i=0 To *n\shownBytes : PokeA(#NTT_REPORT+3072+i,PeekA(*n\shown+i)) : Next
  NttCheck(nttState\scroll,250)
  NttCheck(NeonChromeTabAt(@nttState,20.0,30.0),0)
  NttCheck(NeonChromeTabsSelect(@nttState,10,1),0) : NttCheck(nttState\scroll,0)
  NttCheck(NeonChromeTabsInput(@nttState,100.0,30.0,0,-1,1,0.0),0) : NttCheck(nttState\scroll,0)
  NttCheck(NeonChromeTabsInput(@nttState,100.0,30.0,0,-1,0,0.0),0) : NttCheck(nttState\scroll,10)
  NttCheck(NeonChromeTabsInput(@nttState,20.0,30.0,1,0,0,0.0),0)
  NttCheck(nttState\activeId,10) : NttCheck(NeonChromeTabsCloseGet(@nttState),0)
  NttCheck(NeonChromeTabsInput(@nttState,100.0,30.0,0,-128,0,0.0),0) : NttCheck(nttState\scroll,250)
  NttCheck(NeonChromeTabsSelect(@nttState,0,0),0) : NttCheck(nttState\activeId,0)
  NttCheck(NeonChromeTabsBeginBuild(@nttState),0) : NttCheck(NeonChromeTabsAdd(@nttState,10,"One",0),0)
  NttCheck(NeonChromeTabsSeal(@nttState),0) : NttCheck(nttState\scroll,0)
  PokeL(@nttBuffer[0],$007881C3)
  NttCheck(NeonUtf8Length(@nttBuffer[0],64),3)
  NttCheck(NeonUtf8Prefix(@nttBuffer[0],3,1),0)
  PokeL(@nttBuffer[0],$7881CC65) : PokeA(@nttBuffer[0]+4,0)
  NttCheck(NeonUtf8Length(@nttBuffer[0],64),4) : NttCheck(NeonUtf8Prefix(@nttBuffer[0],4,1),0)
  NttCheck(NeonUtf8Prefix(@nttBuffer[0],4,3),3)
  PokeL(@nttBuffer[0],$000080C0)
  NttCheck(NeonUtf8Length(@nttBuffer[0],64),#NEON_UTF8_ERR)
  NttCheck(NeonChromeTabsBeginBuild(@nttState),0)
  NttCheck(NeonChromeTabsAdd(@nttState,10,@nttBuffer[0],0),#NCT_ERR_TEXT)
  NttCheck(NeonChromeTabsAdd(@nttState,10,"One",0),0)
  NttCheck(NeonChromeTabsAdd(@nttState,10,"Dup",0),#NCT_ERR_ARGS)
  NttCheck(NeonChromeTabsInput(@nttState,MathFromBits($7FC00001),0.0,0,0,0,0.0),#NCT_ERR_STATE)
  NttCheck(NeonServiceBind(services,35),0) : NttCheck(NeonServiceOpen(),0) : NttCheck(NeonServiceCanvas(640,400),0)
  ui=NeonServiceFontRegister(0,0,16) : small=NeonServiceFontRegister(0,1,14) : alternate=NeonServiceFontRegister(0,2,16)
  NttCheck(Bool(ui>0 And small>0 And alternate>0),1)
  NttCheck(NeonServiceChromeTabsInstall(),0)
  nttConfig\x=20.0 : nttConfig\y=50.0 : nttConfig\w=600.0 : nttConfig\font=ui : nttConfig\smallFont=small : nttConfig\italicFont=alternate : nttConfig\activeId=10
  CompilerIf #NTT_SCENE=2
    nttConfig\w=200.0 : nttConfig\activeId=40
  CompilerEndIf
  NttCheck(NeonChromeTabsConfigure(@nttState,@nttArena[0],8192,12,128,@nttConfig),0)
  NttCheck(NttBuild(@nttState,#NTT_SCENE-1,"One"),0) : NttCheck(NeonChromeTabsSeal(@nttState),0)
  NttCheck(NeonChromeTabsInput(@nttState,-100.0,-100.0,0,0,0,0.05),0)
  *n=NeonChromeTabsGet(@nttState,nttState\activeId)
  labelx=nttState\x+4.0+*n\pos-nttState\scroll+12.0
  refx=400.0+(labelx-MathFFromInt(Int(labelx))) : ty=nttState\y+(nttState\h-nttState\uiH)/2.0
  cellW=*n\shownW+2.0
  PokeI(#NTT_REPORT+56,ui)
  PokeL(#NTT_REPORT+64,MathBitsOf(nttState\side)) : PokeL(#NTT_REPORT+68,MathBitsOf(nttState\scroll))
  PokeL(#NTT_REPORT+72,MathBitsOf(nttState\viewL)) : PokeL(#NTT_REPORT+76,MathBitsOf(nttState\viewR))
  PokeL(#NTT_REPORT+80,MathBitsOf(labelx)) : PokeL(#NTT_REPORT+84,MathBitsOf(refx)) : PokeL(#NTT_REPORT+88,MathBitsOf(cellW))
  PokeL(#NTT_REPORT+92,MathBitsOf(ty)) : PokeL(#NTT_REPORT+96,MathBitsOf(*n\width)) : PokeL(#NTT_REPORT+100,MathBitsOf(nttState\h))
  PokeL(#NTT_REPORT+104,MathBitsOf(*n\shownW)) : PokeL(#NTT_REPORT+108,MathBitsOf(nttState\uiH))
  PokeI(#NTT_REPORT+136,nttState\activeId) : PokeI(#NTT_REPORT+144,*n\shownBytes)
  *n=NeonChromeTabsGet(@nttState,20)
  PokeL(#NTT_REPORT+112,MathBitsOf(nttState\x+4.0+*n\pos-nttState\scroll+*n\width-nttState\side-1.0))
  PokeL(#NTT_REPORT+116,MathBitsOf(nttState\y+(nttState\h-1.0-nttState\side)/2.0))
  PokeL(#NTT_REPORT+120,MathBitsOf(nttState\side/9.0))
  *n=NeonChromeTabsGet(@nttState,nttState\activeId)
  For i=0 To *n\shownBytes : PokeA(#NTT_REPORT+3200+i,PeekA(*n\shown+i)) : Next
  NttCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NttCheck(NeonChromeTabsDraw(@nttState),0)
  NttCheck(NeonServiceBox(MathFFromInt(Int(refx))-1.0,52.0,cellW+3.0,26.0,0.145,0.149,0.161,1.0),0)
  NttCheck(NeonServiceText(ui,refx,ty,*n\shown,0.863,0.863,0.863,1.0),0)
  NttCheck(NeonServiceEnd(),0)
  ProcedureReturn nttFailure
EndProcedure
