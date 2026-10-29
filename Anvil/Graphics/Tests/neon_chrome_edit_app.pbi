; SPDX-License-Identifier: MIT
; Returning editor interaction/callback and resident raster proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_edit.pbi"
Global netState.NeonChromeEditState,netOther.NeonChromeEditState,netClipState.NeonChromeEditState
Global netConfig.NeonChromeEditConfig,netEvent.NeonChromeEditInput
Global Dim netArena.q[320]
Global Dim netOtherArena.q[320]
Global Dim netClipArena.q[320]
Global Dim netBuffer.a[256]
Global netChecks.i,netFailure.i,netCapture.i,netPackets.i,netDrawing.i,netMetrics.i,netPrepares.i
Global netMode.i,netReenter.i,netOtherBusy.i,netClearFailure.i,netPrepFailure.i
Procedure NetCheck(actual.i,expected.i)
  netChecks=netChecks+1
  PokeI(#NET_REPORT+256+netChecks*16,actual) : PokeI(#NET_REPORT+264+netChecks*16,expected)
  If actual<>expected And netFailure=0 : netFailure=netChecks : EndIf
  PokeI(#NET_REPORT+16,netFailure) : PokeI(#NET_REPORT+24,netChecks)
EndProcedure
Procedure NetPacket(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
  Protected p.i,i.i,len.i
  If netCapture=0 : ProcedureReturn : EndIf
  p=#NET_REPORT+4096+netPackets*128 : netPackets=netPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
  len=0 : If text<>0 : len=NeonUtf8Length(text,64) : EndIf
  PokeI(p+56,len)
  For i=0 To len-1
    PokeA(p+64+i,PeekA(text+i)) : If i<8 : PokeA(p+48+i,PeekA(text+i)) : EndIf
  Next
EndProcedure
Procedure.i NetBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NetPacket(1,0,x,y,w,h,r,g,b,a,0)
  If netMode=1 : ProcedureReturn -22199 : EndIf
  If netMode=2 : ProcedureReturn 1 : EndIf
  If netMode=3
    netReenter=NeonChromeEditFocus(@netState,1)
    netOtherBusy=NeonChromeEditSeal(@netOther)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NetText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NetPacket(2,font,x,y,0.0,0.0,r,g,b,a,text) : ProcedureReturn 0
EndProcedure
Procedure.f NetWidth(font.i,text.i)
  Protected bytes.i=NeonUtf8Length(text,512),i.i,count.i,width.i=8
  If netDrawing<>0 : netMetrics=netMetrics+1 : EndIf
  If bytes<0 : ProcedureReturn -1.0 : EndIf
  While i<bytes : i=NeonUtf8Next(text,bytes,i) : count=count+1 : Wend
  If font=1 : width=7 : ElseIf font=2 : width=10 : EndIf
  ProcedureReturn MathFFromInt(count*width)
EndProcedure
Procedure.f NetHeight(font.i)
  If netDrawing<>0 : netMetrics=netMetrics+1 : EndIf
  If font=1 : ProcedureReturn 14.0 : EndIf
  ProcedureReturn 16.0
EndProcedure
Procedure.i NetPrepare(font.i,text.i)
  If netDrawing<>0 : netPrepares=netPrepares+1 : EndIf
  ProcedureReturn netPrepFailure
EndProcedure
Procedure.i NetClip(x.f,y.f,w.f,h.f)
  NetPacket(3,0,x,y,w,h,0.0,0.0,0.0,0.0,0) : ProcedureReturn 0
EndProcedure
Procedure.i NetClear()
  NetPacket(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0)
  If netClearFailure<>0 : ProcedureReturn -22198 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i NetInput(key.i,cp.i,ctrl.i)
  netEvent\key=key : netEvent\scalar=cp : netEvent\ctrl=ctrl
  ProcedureReturn NeonChromeEditInput(@netState,@netEvent)
EndProcedure
Procedure NetCopyReport(dest.i,src.i)
  Protected n.i=NeonUtf8Length(src,256),i.i
  For i=0 To n : PokeA(dest+i,PeekA(src+i)) : Next
EndProcedure
Procedure.i NetReference(font.i,x.f,y.f,w.f,h.f,lineH.f,text.i,focused.i,placeholder.i,textW.f,selected.i)
  Protected rc.i,r.f=0.196,g.f=0.200,b.f=0.212,ty.f=y+(h-lineH)/2.0
  rc=NeonServiceBox(x,y,w,h,0.09,0.093,0.102,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  If focused<>0 : r=0.353 : g=0.741 : b=0.816 : EndIf
  rc=NeonServiceBox(x,y,w,1.0,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceBox(x,y+h-1.0,w,1.0,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceBox(x,y+1.0,1.0,h-2.0,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceBox(x+w-1.0,y+1.0,1.0,h-2.0,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceScissorSet(x+1.0,y+1.0,w-2.0,h-2.0) : If rc<>0 : ProcedureReturn rc : EndIf
  r=0.863 : g=0.863 : b=0.863 : If placeholder<>0 : r=0.435 : g=0.459 : b=0.498 : EndIf
  If selected<>0
    rc=NeonServiceBox(x+6.0,ty,textW+4.0,lineH,0.353,0.741,0.816,0.35) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  rc=NeonServiceText(font,x+8.0,ty,text,r,g,b,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  If focused<>0
    rc=NeonServiceBox(x+8.0+textW,ty,1.5,lineH,0.353,0.741,0.816,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  ProcedureReturn NeonServiceScissorClear()
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,rc.i,font.i
  For i=0 To 16383 Step 8 : PokeI(#NET_REPORT+i,0) : Next
  PokeI(#NET_REPORT,$4E455431) : PokeI(#NET_REPORT+8,1) : PokeI(#NET_REPORT+128,#NET_SCENE)
  NetCheck(SizeOf(NeonChromeEditConfig),56) : NetCheck(SizeOf(NeonChromeEditInput),72)
  NetCheck(NeonChromeEditRequiredBytes(4),20) : NetCheck(NeonChromeEditRequiredBytes(4097),0)
  NetCheck(NeonServiceChromeEditInstall(),#NCE_ERR_RENDERER)
  NetCheck(NeonChromeEditRendererInstall(@NetBox,@NetText,@NetWidth,@NetHeight,@NetPrepare,@NetClip,@NetClear),0)
  netConfig\id=1 : netConfig\font=0 : netConfig\x=10.0 : netConfig\y=20.0 : netConfig\w=200.0 : netConfig\h=30.0 : netConfig\scale=1.0
  PokeL(@netBuffer[0],$64616F52) : PokeA(@netBuffer[0]+4,0)
  netConfig\text=@netBuffer[0] : netConfig\placeholder="Find a road"
  NetCheck(NeonChromeEditConfigure(@netState,@netArena[0],2560,256,@netConfig),0)
  For i=0 To 255 : PokeA(@netBuffer[0]+i,0) : Next
  NetCheck(PeekL(NeonChromeEditText(@netState)),$64616F52)
  netConfig\id=2 : netConfig\text=""
  NetCheck(NeonChromeEditConfigure(@netOther,@netOtherArena[0],2560,256,@netConfig),0)
  NetCheck(NeonChromeEditFocus(@netState,1),0) : NetCheck(NeonChromeEditFocused(@netOther),0)
  NetCheck(NetInput(#NCE_A,1,1),0) : NetCheck(netState\all,1) : NetCheck(netState\charUsed,1)
  NetCheck(NeonChromeEditSeal(@netState),0)
  netCapture=1 : netDrawing=1 : NetCheck(NeonChromeEditDraw(@netState),0) : netDrawing=0 : netCapture=0
  NetCheck(netPackets,11) : NetCheck(netMetrics,0) : NetCheck(netPrepares,0) : PokeI(#NET_REPORT+32,netPackets)
  netMode=1 : NetCheck(NeonChromeEditDraw(@netState),-22199)
  netMode=2 : NetCheck(NeonChromeEditDraw(@netState),#NCE_ERR_RENDERER)
  netMode=3 : NetCheck(NeonChromeEditDraw(@netState),0)
  NetCheck(netReenter,#NCE_ERR_BUSY) : NetCheck(netOtherBusy,#NCE_ERR_BUSY)
  netMode=0 : netClearFailure=1
  NetCheck(NeonChromeEditDraw(@netState),-22198) : NetCheck(netState\cleanupError,-22198)
  netClearFailure=0 : NetCheck(NeonChromeEditDraw(@netState),0)
  NetCheck(NetInput(#NCE_C,3,1),0) : NetCheck(netState\clipboardEvent,1)
  NetCopyReport(#NET_REPORT+3072,NeonChromeEditClipboard(@netState))
  NetCheck(NetInput(#NCE_X,0,1),0) : NetCheck(netState\length,0) : NetCheck(netState\clipboardEvent,2)
  NetCheck(NeonChromeEditDraw(@netState),#NCE_ERR_STATE)
  NetCheck(NetInput(0,$1F69A,0),0) : NetCheck(netState\length,4) : NetCheck(netState\caret,4)
  NetCheck(NeonChromeEditCaret(@netState,1),#NCE_ERR_ARGS)
  NetCheck(NetInput(0,233,0),0) : NetCheck(netState\length,6)
  NetCheck(NetInput(#NCE_LEFT,0,0),0) : NetCheck(netState\caret,4)
  NetCheck(NetInput(#NCE_BACK,0,0),0) : NetCheck(netState\length,2) : NetCheck(netState\caret,0)
  NetCheck(NetInput(#NCE_RIGHT,0,0),0) : NetCheck(netState\caret,2)
  NetCopyReport(#NET_REPORT+3328,NeonChromeEditText(@netState))
  NetCheck(NetInput(#NCE_HOME,0,0),0) : NetCheck(NetInput(#NCE_DELETE,0,0),0) : NetCheck(netState\length,0)
  PokeL(@netBuffer[0],$090A4209) : PokeA(@netBuffer[0]+4,0)
  netEvent\paste=@netBuffer[0] : netEvent\pasteBudget=256
  NetCheck(NetInput(#NCE_V,22,1),0) : NetCheck(netState\length,2)
  NetCopyReport(#NET_REPORT+3584,NeonChromeEditText(@netState))
  NetCheck(NetInput(#NCE_RETURN,0,0),0) : NetCheck(netState\submitted,1)
  NetCheck(NetInput(#NCE_ESCAPE,0,0),0) : NetCheck(NeonChromeEditFocused(@netState),0)
  NetCheck(NetInput(0,65,0),0) : NetCheck(netState\length,2)
  NetCheck(NeonChromeEditFocus(@netState,1),0)
  netEvent\blocked=1 : NetCheck(NetInput(0,65,0),0) : NetCheck(netState\length,2) : netEvent\blocked=0
  NetCheck(NetInput(0,$D800,0),#NCE_ERR_TEXT)
  NetCheck(NeonChromeEditSetText(@netState,"Road",5),0)
  NetCheck(NetInput(#NCE_C,0,1),0) : NetCheck(netState\clipboardEvent,1)
  NetCheck(NetInput(#NCE_X,0,1),0) : NetCheck(netState\length,4) : NetCheck(netState\clipboardEvent,0)
  NetCheck(NetInput(#NCE_A,0,1),0) : NetCheck(NetInput(0,90,0),0) : NetCheck(netState\length,1)
  NetCheck(NetInput(#NCE_END,0,0),0) : NetCheck(netState\caret,1)
  NetCheck(NeonChromeEditSetText(@netState,"Road",5),0)
  netPrepFailure=-22197 : NetCheck(NeonChromeEditSeal(@netState),-22197) : NetCheck(NeonChromeEditDraw(@netState),#NCE_ERR_STATE)
  netPrepFailure=0 : NetCheck(NeonChromeEditSeal(@netState),0)
  netConfig\id=3 : netConfig\text="abc" : netConfig\placeholder=""
  NetCheck(NeonChromeEditConfigure(@netClipState,@netClipArena[0],2560,4,@netConfig),0)
  NetCheck(NeonChromeEditFocus(@netClipState,1),0)
  netEvent\key=0 : netEvent\ctrl=0 : netEvent\scalar=$1F69A
  NetCheck(NeonChromeEditInput(@netClipState,@netEvent),#NCE_ERR_CAPACITY) : NetCheck(netClipState\length,3)
  NetCheck(PeekA(netClipState\clipboard),0)
  netEvent\ctrl=1 : netEvent\key=#NCE_A : netEvent\scalar=0
  NetCheck(NeonChromeEditInput(@netClipState,@netEvent),0)
  netEvent\key=#NCE_V : netEvent\paste="abcd" : netEvent\pasteBudget=5
  NetCheck(NeonChromeEditInput(@netClipState,@netEvent),#NCE_ERR_CAPACITY)
  NetCheck(netClipState\length,3) : NetCheck(netClipState\caret,3) : NetCheck(netClipState\all,1)
  netEvent\key=#NCE_BACK : netEvent\ctrl=0
  NetCheck(NeonChromeEditInput(@netClipState,@netEvent),0) : NetCheck(netClipState\length,0)
  PokeL(@netBuffer[0],$000080C0)
  NetCheck(NeonChromeEditSetText(@netState,@netBuffer[0],4),#NCE_ERR_TEXT)
  NetCheck(netState\length,4)
  NetCheck(NeonChromeEditFocus(@netState,1),0)
  netEvent\down=1 : netEvent\x=20.0 : netEvent\y=30.0
  NetCheck(NetInput(0,0,0),0) : NetCheck(NeonChromeEditFocused(@netState),1)
  netEvent\x=500.0 : NetCheck(NetInput(0,0,0),0) : NetCheck(NeonChromeEditFocused(@netState),1)
  netEvent\down=0 : NetCheck(NetInput(0,0,0),0) : netEvent\down=1
  NetCheck(NetInput(0,0,0),0) : NetCheck(NeonChromeEditFocused(@netState),0)
  NetCheck(NeonServiceBind(services,35),0) : NetCheck(NeonServiceOpen(),0) : NetCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,0,16) : NetCheck(Bool(font>0),1)
  NetCheck(NeonServiceChromeEditInstall(),0)
  netConfig\id=1 : netConfig\font=font : netConfig\x=20.0 : netConfig\y=50.0 : netConfig\w=250.0 : netConfig\h=34.0 : netConfig\text="Jefferson Street" : netConfig\placeholder="Find a road"
  NetCheck(NeonChromeEditConfigure(@netState,@netArena[0],2560,256,@netConfig),0)
  netConfig\id=2 : netConfig\y=110.0 : netConfig\text=""
  NetCheck(NeonChromeEditConfigure(@netOther,@netOtherArena[0],2560,256,@netConfig),0)
  netConfig\id=3 : netConfig\y=170.0 : netConfig\w=90.0 : netConfig\text="Turn left on Jefferson Street"
  NetCheck(NeonChromeEditConfigure(@netClipState,@netClipArena[0],2560,256,@netConfig),0)
  NetCheck(NeonChromeEditFocus(@netState,1),0)
  netEvent\down=0
  CompilerIf #NET_SCENE=2
    NetCheck(NetInput(#NCE_A,0,1),0)
  CompilerElse
    NetCheck(0,0)
  CompilerEndIf
  NetCheck(NeonChromeEditSeal(@netState),0) : NetCheck(NeonChromeEditSeal(@netOther),0) : NetCheck(NeonChromeEditSeal(@netClipState),0)
  PokeI(#NET_REPORT+56,font) : PokeL(#NET_REPORT+64,MathBitsOf(netState\lineH)) : PokeL(#NET_REPORT+68,MathBitsOf(netState\textW)) : PokeL(#NET_REPORT+72,MathBitsOf(netState\caretW))
  NetCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NetCheck(NeonChromeEditDraw(@netState),0) : NetCheck(NeonChromeEditDraw(@netOther),0) : NetCheck(NeonChromeEditDraw(@netClipState),0)
  NetCheck(NetReference(font,360.0,50.0,250.0,34.0,netState\lineH,"Jefferson Street",1,0,netState\textW,#NET_SCENE-1),0)
  NetCheck(NetReference(font,360.0,110.0,250.0,34.0,netState\lineH,"Find a road",0,1,0.0,0),0)
  NetCheck(NetReference(font,360.0,170.0,90.0,34.0,netState\lineH,"Turn left on Jefferson Street",0,0,0.0,0),0)
  NetCheck(NeonServiceEnd(),0)
  ProcedureReturn netFailure
EndProcedure
