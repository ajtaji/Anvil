; SPDX-License-Identifier: MIT
; Returning list/tree and split-scroll ownership proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_list.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_list.pbi"
Global nltState.NeonChromeListState,nltOther.NeonChromeListState,nltConfig.NeonChromeListConfig
Global nltOffset.NeonChromeScrollOffset
Global nltScroll.NeonChromeScrollState
Global Dim nltArena.q[2048]
Global Dim nltOtherArena.q[2048]
Global Dim nltBuffer.a[128]
Global nltChecks.i,nltFailure.i,nltCapture.i,nltPackets.i,nltDrawing.i,nltMetrics.i,nltPrepares.i
Global nltMode.i,nltReenter.i,nltOtherBusy.i,nltClearFailure.i,nltPrepFailure.i
Procedure NltCheck(actual.i,expected.i)
  nltChecks=nltChecks+1
  PokeI(#NLT_REPORT+256+nltChecks*16,actual) : PokeI(#NLT_REPORT+264+nltChecks*16,expected)
  If actual<>expected And nltFailure=0 : nltFailure=nltChecks : EndIf
  PokeI(#NLT_REPORT+16,nltFailure) : PokeI(#NLT_REPORT+24,nltChecks)
EndProcedure
Procedure NltPacket(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
  Protected p.i,i.i,len.i
  If nltCapture=0 : ProcedureReturn : EndIf
  p=#NLT_REPORT+4096+nltPackets*128 : nltPackets=nltPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
  len=0 : If text<>0 : len=NeonUtf8Length(text,64) : EndIf
  PokeI(p+56,len)
  For i=0 To len-1
    PokeA(p+64+i,PeekA(text+i)) : If i<8 : PokeA(p+48+i,PeekA(text+i)) : EndIf
  Next
EndProcedure
Procedure.i NltBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NltPacket(1,0,x,y,w,h,r,g,b,a,0)
  If nltMode=1 : ProcedureReturn -22199 : EndIf
  If nltMode=2 : ProcedureReturn 1 : EndIf
  If nltMode=3
    nltReenter=NeonChromeListScrollTo(@nltState,0)
    nltOtherBusy=NeonChromeListBeginBuild(@nltOther)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NltText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NltPacket(2,font,x,y,0.0,0.0,r,g,b,a,text) : ProcedureReturn 0
EndProcedure
Procedure.f NltWidth(font.i,text.i)
  Protected bytes.i=NeonUtf8Length(text,512),i.i,count.i,width.i=8
  If nltDrawing<>0 : nltMetrics=nltMetrics+1 : EndIf
  If bytes<0 : ProcedureReturn -1.0 : EndIf
  While i<bytes : i=NeonUtf8Next(text,bytes,i) : count=count+1 : Wend
  If font=1 : width=7 : ElseIf font=2 : width=10 : EndIf
  ProcedureReturn MathFFromInt(count*width)
EndProcedure
Procedure.f NltHeight(font.i)
  If nltDrawing<>0 : nltMetrics=nltMetrics+1 : EndIf
  If font=1 : ProcedureReturn 14.0 : EndIf
  ProcedureReturn 16.0
EndProcedure
Procedure.i NltPrepare(font.i,text.i)
  If nltDrawing<>0 : nltPrepares=nltPrepares+1 : EndIf
  ProcedureReturn nltPrepFailure
EndProcedure
Procedure.i NltClip(x.f,y.f,w.f,h.f)
  NltPacket(3,0,x,y,w,h,0.0,0.0,0.0,0.0,0) : ProcedureReturn 0
EndProcedure
Procedure.i NltClear()
  NltPacket(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0)
  If nltClearFailure<>0 : ProcedureReturn -22198 : EndIf
  ProcedureReturn 0
EndProcedure


Procedure.i NltBuild(*s.NeonChromeListState,first.i)
  Protected rc.i
  rc=NeonChromeListAdd(*s,10,first,0,0,1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeListAdd(*s,20,"main.avr",1,1,0,"changed") : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeListAdd(*s,30,"an extremely long file name",2,0,0,"detail occupies") : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeListAdd(*s,40,"Footer",0,0,0,0) : If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonChromeListAdd(*s,50,"Last",1,0,0,0)
EndProcedure
Procedure.i NltInput(x.f,y.f,down.i,wheel.i,blocked.i,dt.f)
  Protected rc.i=NeonChromeScrollInput(@nltScroll,x,y,down)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonChromeListInput(@nltState,wheel,blocked,dt)
EndProcedure
Procedure NltReportString(dest.i,text.i)
  Protected n.i=NeonUtf8Length(text,128),i.i
  For i=0 To n : PokeA(dest+i,PeekA(text+i)) : Next
EndProcedure
Procedure.i NltReference(font.i,top.i)
  Protected i.i,rc.i,*row.NeonChromeListRow,y.f,x.f,r.f,g.f,b.f,thumbY.f,ty.f
  rc=NeonServiceBox(360.0,50.0,250.0,85.0,0.118,0.122,0.133,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceScissorSet(360.0,50.0,240.0,85.0) : If rc<>0 : ProcedureReturn rc : EndIf
  For i=top To 4
    y=50.0+MathFFromInt(i-top)*24.0 : If y>=135.0 : Break : EndIf
    *row=NeonChromeListGet(@nltState,(i+1)*10)
    If i=1
      rc=NeonServiceBox(360.0,y,240.0,24.0,0.353*0.30,0.741*0.30,0.816*0.34,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
      rc=NeonServiceBox(360.0,y,2.0,24.0,0.353,0.741,0.816,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
    EndIf
    r=0.863 : g=0.863 : b=0.863
    If i=0 : r=0.882 : g=0.647 : b=0.259 : ElseIf i=1 : r=0.353 : g=0.741 : b=0.816 : EndIf
    x=368.0 : If i=1 Or i=4 : x=x+14.0 : ElseIf i=2 : x=x+28.0 : EndIf
    ty=y+(24.0-nltState\lineH)/2.0
    rc=NeonServiceText(font,x,ty,*row\shownLabel,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
    If i=1 Or i=2
      rc=NeonServiceText(font,594.0-*row\detailW,ty,*row\shownDetail,0.435,0.459,0.498,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
    EndIf
  Next
  rc=NeonServiceScissorClear() : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceBox(600.0,50.0,10.0,85.0,0.129,0.133,0.145,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  thumbY=50.0+34.0*(MathFFromInt(top)/2.0)
  ProcedureReturn NeonServiceBox(602.0,thumbY,6.0,51.0,0.31,0.33,0.36,1.0)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,rc.i,font.i,*row.NeonChromeListRow,old.i
  For i=0 To 16383 Step 8 : PokeI(#NLT_REPORT+i,0) : Next
  PokeI(#NLT_REPORT,$4E4C5431) : PokeI(#NLT_REPORT+8,1) : PokeI(#NLT_REPORT+128,#NLT_SCENE)
  NltCheck(SizeOf(NeonChromeListRow),112) : NltCheck(SizeOf(NeonChromeListConfig),56)
  NltCheck(NeonChromeListRequiredBytes(0,128),0)
  NltCheck(NeonServiceChromeListInstall(),#NCL_ERR_RENDERER)
  NltCheck(NeonChromeScrollConfigure(@nltScroll,1.0),0)
  NltCheck(NeonChromeListRendererInstall(@NltBox,@NltText,@NltWidth,@NltHeight,@NltPrepare,@NltClip,@NltClear),0)
  nltConfig\id=1 : nltConfig\font=0 : nltConfig\scrollState=@nltScroll
  nltConfig\x=10.0 : nltConfig\y=20.0 : nltConfig\w=200.0 : nltConfig\h=65.0 : nltConfig\rowH=20.0 : nltConfig\scale=1.0
  NltCheck(NeonChromeListConfigure(@nltState,@nltArena[0],16384,16,128,@nltConfig),0)
  nltConfig\id=2 : NltCheck(NeonChromeListConfigure(@nltOther,@nltOtherArena[0],16384,16,128,@nltConfig),0)
  PokeL(@nltBuffer[0],$72756F53) : PokeL(@nltBuffer[0]+4,$00736563)
  NltCheck(NltBuild(@nltState,@nltBuffer[0]),0)
  For i=0 To 127 : PokeA(@nltBuffer[0]+i,0) : Next
  *row=NeonChromeListGet(@nltState,10) : NltCheck(PeekL(*row\label),$72756F53)
  PokeL(@nltBuffer[0],$000080C0)
  NltCheck(NeonChromeListAdd(@nltOther,60,@nltBuffer[0],0,0,0,0),#NCL_ERR_TEXT)
  NltCheck(NeonChromeListAdd(@nltState,10,"duplicate",0,0,0,0),#NCL_ERR_ARGS)
  NltCheck(NeonChromeListAdd(@nltState,60,"bad depth",-1,0,0,0),#NCL_ERR_ARGS)
  NltCheck(NeonChromeListSeal(@nltState),0) : NltCheck(nltState\visible,3) : NltCheck(nltState\maxTop,2)
  *row=NeonChromeListGet(@nltState,30)
  NltCheck(*row\shownLabelBytes,18) : NltCheck(*row\labelW,144) : NltCheck(*row\shownDetailBytes,0)
  NltReportString(#NLT_REPORT+3072,*row\shownLabel)
  NltCheck(NltInput(-100.0,-100.0,0,0,0,0.0),0)
  nltCapture=1 : nltDrawing=1 : NltCheck(NeonChromeListDraw(@nltState),0) : nltDrawing=0 : nltCapture=0
  NltCheck(nltPackets,15) : NltCheck(nltMetrics,0) : NltCheck(nltPrepares,0) : PokeI(#NLT_REPORT+32,nltPackets)
  NltCheck(NeonChromeListNeedsRedraw(@nltState),0)
  NltCheck(NltInput(20.0,30.0,0,0,0,0.05),0) : NltCheck(NeonChromeListDraw(@nltState),0)
  NltCheck(NeonChromeListNeedsRedraw(@nltState),1)
  For i=0 To 19 : rc=NltInput(20.0,30.0,0,0,0,0.05) : Next
  NltCheck(rc,0) : NltCheck(NeonChromeListDraw(@nltState),0)
  *row=NeonChromeListGet(@nltState,10) : NltCheck(*row\hover,1) : NltCheck(NeonChromeListNeedsRedraw(@nltState),0)
  NltCheck(NeonChromeListAt(@nltState,20.0,82.0),40) : NltCheck(NeonChromeListAt(@nltState,205.0,82.0),0)
  NltCheck(NltInput(20.0,30.0,1,0,0,0.0),0) : NltCheck(NeonChromeListEventGet(@nltState),10) : NltCheck(NeonChromeListEventGet(@nltState),0)
  NltCheck(NltInput(20.0,50.0,1,0,0,0.0),0) : NltCheck(NeonChromeListEventGet(@nltState),0)
  NltCheck(NltInput(20.0,50.0,0,0,0,0.0),0)
  NltCheck(NltInput(20.0,50.0,1,0,1,0.0),0) : NltCheck(NeonChromeListEventGet(@nltState),0)
  NltCheck(NltInput(20.0,30.0,0,-1,1,0.0),0) : NltCheck(nltState\top,0) : NltCheck(nltState\wheelRemaining,-1)
  NltCheck(NltInput(20.0,30.0,0,-1,0,0.0),0) : NltCheck(nltState\top,2) : NltCheck(nltState\wheelRemaining,0)
  NltCheck(NeonChromeListScrollTo(@nltState,0),0)
  nltCapture=1 : old=nltPackets
  NltCheck(NltInput(205.0,80.0,1,0,0,0.0),0) : NltCheck(nltState\top,2) : NltCheck(nltPackets,old)
  nltCapture=0
  NltCheck(NltInput(205.0,30.0,0,0,0,0.0),0) : NltCheck(NeonChromeListScrollTo(@nltState,0),0)
  NltCheck(NltInput(205.0,30.0,1,0,0,0.0),0) : NltCheck(NeonChromeScrollDragOwner(@nltScroll),900001)
  NltCheck(NltInput(205.0,85.0,1,0,0,0.0),0) : NltCheck(nltState\top,2)
  old=nltState\top
  NltCheck(NeonChromeListDraw(@nltState),0) : NltCheck(nltState\top,old) : NltCheck(NeonChromeScrollDragOwner(@nltScroll),900001)
  NltCheck(NltInput(205.0,85.0,0,0,0,0.0),0) : NltCheck(NeonChromeScrollDragOwner(@nltScroll),0)
  NltCheck(NeonChromeScrollInput(@nltScroll,90.0,125.0,1),0)
  nltMode=1
  NltCheck(NeonChromeScrollUpdateH(@nltScroll,99,10.0,120.0,100.0,10.0,100,20,@nltOffset),1)
  NltCheck(nltOffset\value,20)
  NltCheck(NeonChromeScrollPaintH(@nltScroll,99,10.0,120.0,100.0,10.0,100,20,@nltOffset),-22199)
  NltCheck(nltOffset\value,20) : NltCheck(NeonChromeScrollDragOwner(@nltScroll),0)
  nltMode=0 : NltCheck(NeonChromeScrollPaintH(@nltScroll,99,10.0,120.0,100.0,10.0,100,20,@nltOffset),0)
  NltCheck(nltOffset\value,20)
  nltMode=1 : NltCheck(NeonChromeListDraw(@nltState),-22199) : NltCheck(nltState\top,2)
  nltMode=2 : NltCheck(NeonChromeListDraw(@nltState),#NCL_ERR_RENDERER)
  nltMode=3 : NltCheck(NeonChromeListDraw(@nltState),0)
  NltCheck(nltReenter,#NCL_ERR_BUSY) : NltCheck(nltOtherBusy,#NCL_ERR_BUSY)
  nltMode=0 : nltClearFailure=1 : NltCheck(NeonChromeListDraw(@nltState),-22198) : NltCheck(nltState\cleanupError,-22198)
  nltClearFailure=0 : NltCheck(NeonChromeListDraw(@nltState),0)
  NltCheck(NeonChromeListItemState(@nltState,40,1,1),0) : *row=NeonChromeListGet(@nltState,40) : NltCheck(*row\selected,1) : NltCheck(*row\group,1)
  NltCheck(NeonChromeListBeginBuild(@nltState),0) : NltCheck(NeonChromeListAdd(@nltState,10,"One",0,0,0,0),0)
  nltPrepFailure=-22197 : NltCheck(NeonChromeListSeal(@nltState),-22197) : NltCheck(NeonChromeListDraw(@nltState),#NCL_ERR_STATE)
  nltPrepFailure=0 : NltCheck(NeonChromeListSeal(@nltState),0) : NltCheck(nltState\top,0)
  NltCheck(NeonServiceBind(services,35),0) : NltCheck(NeonServiceOpen(),0) : NltCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,1,14) : NltCheck(Bool(font>0),1) : NltCheck(NeonServiceChromeListInstall(),0)
  nltConfig\id=1 : nltConfig\font=font : nltConfig\x=20.0 : nltConfig\y=50.0 : nltConfig\w=250.0 : nltConfig\h=85.0 : nltConfig\rowH=24.0
  NltCheck(NeonChromeListConfigure(@nltState,@nltArena[0],16384,16,128,@nltConfig),0)
  NltCheck(NltBuild(@nltState,"Sources"),0) : NltCheck(NeonChromeListSeal(@nltState),0)
  NltCheck(NeonChromeListScrollTo(@nltState,(#NLT_SCENE-1)*2),0) : NltCheck(NltInput(-100.0,-100.0,0,0,0,0.0),0)
  PokeI(#NLT_REPORT+56,font) : PokeI(#NLT_REPORT+136,nltState\top) : PokeL(#NLT_REPORT+64,MathBitsOf(nltState\lineH))
  *row=NeonChromeListGet(@nltState,30) : NltReportString(#NLT_REPORT+3328,*row\shownLabel) : PokeL(#NLT_REPORT+68,MathBitsOf(*row\labelW))
  NltCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0) : NltCheck(NeonChromeListDraw(@nltState),0)
  NltCheck(NltReference(font,nltState\top),0) : NltCheck(NeonServiceEnd(),0)
  ProcedureReturn nltFailure
EndProcedure
