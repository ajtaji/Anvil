; SPDX-License-Identifier: MIT
; Returning prepared menu model and resident renderer qualification.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_menu.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_menu.pbi"
Global nmaState.NeonChromeMenuState,nmaOther.NeonChromeMenuState
Global Dim nmaArena.q[4096]
Global Dim nmaSmall.q[128]
Global Dim nmaCopied.a[16]
Global nmaChecks.i,nmaFailure.i,nmaCapture.i,nmaPackets.i,nmaDrawing.i,nmaMetrics.i,nmaPrepares.i
Global nmaMode.i,nmaReenter.i,nmaOtherBusy.i,nmaClearFailure.i
Procedure NmaCheck(actual.i,expected.i)
  nmaChecks=nmaChecks+1
  PokeI(#NMA_REPORT+256+nmaChecks*16,actual) : PokeI(#NMA_REPORT+264+nmaChecks*16,expected)
  If actual<>expected And nmaFailure=0 : nmaFailure=nmaChecks : EndIf
  PokeI(#NMA_REPORT+16,nmaFailure) : PokeI(#NMA_REPORT+24,nmaChecks)
EndProcedure
Procedure.i NmaLength(text.i)
  Protected i.i
  If text=0 : ProcedureReturn 0 : EndIf
  While (PeekA(text+i) & 255)<>0 And i<512 : i=i+1 : Wend
  ProcedureReturn i
EndProcedure
Procedure NmaPacket(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
  Protected p.i,i.i,length.i
  If nmaCapture=0 : ProcedureReturn : EndIf
  If nmaPackets>=100 : nmaFailure=999 : ProcedureReturn : EndIf
  p=#NMA_REPORT+4096+nmaPackets*80 : nmaPackets=nmaPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
  length=NmaLength(text) : PokeI(p+56,length)
  For i=0 To 7 : If i<length : PokeA(p+48+i,PeekA(text+i)) : EndIf : Next
EndProcedure
Procedure.i NmaBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NmaPacket(1,0,x,y,w,h,r,g,b,a,0)
  If nmaMode=1 : ProcedureReturn -21900 : EndIf
  If nmaMode=2 : ProcedureReturn 1 : EndIf
  If nmaMode=3
    nmaReenter=NeonChromeMenuInput(@nmaState,0.0,0.0,0,0,0)
    nmaOtherBusy=NeonChromeMenuConfigure(@nmaOther,@nmaSmall[0],1024,2,16,640,400,1.0,0,1)
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmaText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NmaPacket(2,font,x,y,0.0,0.0,r,g,b,a,text) : ProcedureReturn 0
EndProcedure
Procedure.f NmaWidth(font.i,text.i)
  If nmaDrawing<>0 : nmaMetrics=nmaMetrics+1 : EndIf
  ProcedureReturn MathFFromInt(NmaLength(text)*8)
EndProcedure
Procedure.f NmaHeight(font.i)
  If nmaDrawing<>0 : nmaMetrics=nmaMetrics+1 : EndIf
  ProcedureReturn 16.0
EndProcedure
Procedure.i NmaPrepare(font.i,text.i)
  If nmaDrawing<>0 : nmaPrepares=nmaPrepares+1 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmaClip(x.f,y.f,w.f,h.f)
  NmaPacket(3,0,x,y,w,h,0.0,0.0,0.0,0.0,0) : ProcedureReturn 0
EndProcedure
Procedure.i NmaClear()
  NmaPacket(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0)
  If nmaClearFailure<>0 : ProcedureReturn -21901 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmaBuild(*s.NeonChromeMenuState,label.i)
  Protected rc.i,i.i
  rc=NeonChromeMenuAddRoot(*s,1,label) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,10,1,"Open","Ctrl+O",1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,11,1,"Show grid","",1,1) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,12,1,"Disabled","",0,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddSeparator(*s,1) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddSubmenu(*s,20,1,"More") : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,21,20,"First","",1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,22,20,"Last","",1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddItem(*s,13,1,"Exit","",1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonChromeMenuAddRoot(*s,2,"Tools") : If rc<>0 : ProcedureReturn rc : EndIf
  For i=0 To 39
    rc=NeonChromeMenuAddItem(*s,1000+i,2,"Tool","",1,0) : If rc<>0 : ProcedureReturn rc : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,ui.i,small.i,before.i,*node.NeonChromeMenuNode,x.f,refX.f,rowY.f,ty.f
  For i=0 To 16383 Step 8 : PokeI(#NMA_REPORT+i,0) : Next
  PokeI(#NMA_REPORT,$4E4D4131) : PokeI(#NMA_REPORT+8,1) : PokeI(#NMA_REPORT+128,#NMA_SCENE)
  NmaCheck(SizeOf(NeonChromeMenuNode),88)
  NmaCheck(NeonServiceChromeMenuInstall(),#NCM_ERR_RENDERER)
  NmaCheck(NeonChromeMenuRendererInstall(@NmaBox,@NmaText,@NmaWidth,@NmaHeight,@NmaPrepare,@NmaClip,@NmaClear),0)
  NmaCheck(NeonChromeMenuRequiredBytes(0,64),0)
  NmaCheck(NeonChromeMenuConfigure(@nmaOther,@nmaSmall[0],1024,2,16,640,400,1.0,0,1),0)
  NmaCheck(NeonChromeMenuAddRoot(@nmaOther,1,"One"),0)
  NmaCheck(NeonChromeMenuAddRoot(@nmaOther,1,"Duplicate"),#NCM_ERR_ARGS)
  NmaCheck(NeonChromeMenuAddRoot(@nmaOther,2,"Two"),0)
  NmaCheck(NeonChromeMenuAddRoot(@nmaOther,3,"Three"),#NCM_ERR_CAPACITY)
  NmaCheck(NeonChromeMenuConfigure(@nmaState,@nmaArena[0],32768,128,64,640,400,1.0,0,1),0)
  NmaCheck(NeonChromeMenuDraw(@nmaState),#NCM_ERR_STATE)
  PokeL(@nmaCopied[0],$656C6946) : PokeA(@nmaCopied[0]+4,0)
  NmaCheck(NmaBuild(@nmaState,@nmaCopied[0]),0)
  For i=0 To 15 : PokeA(@nmaCopied[0]+i,0) : Next
  *node=NeonChromeMenuGet(@nmaState,1) : NmaCheck(PeekL(*node\label),$656C6946)
  NmaCheck(NeonChromeMenuAddSubmenu(@nmaState,30,20,"Too deep"),#NCM_ERR_ARGS)
  NmaCheck(NeonChromeMenuSeal(@nmaState),0)
  NmaCheck(NeonChromeMenuAddItem(@nmaState,40,1,"Late","",1,0),#NCM_ERR_STATE)
  NmaCheck(NeonChromeMenuInput(@nmaState,20.0,15.0,1,0,0),0)
  NmaCheck(NeonChromeMenuIsOpen(@nmaState),1) : NmaCheck(NeonChromeMenuBlocksMouse(@nmaState),1)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,90.0,0,0,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,90.0,1,0,0),0)
  NmaCheck(NeonChromeMenuEventGet(@nmaState),0) : NmaCheck(NeonChromeMenuIsOpen(@nmaState),1)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,127.0,0,0,0),0)
  NmaCheck(nmaState\subPanel\x,178) : NmaCheck(nmaState\subPanel\y,111)
  nmaCapture=1 : nmaDrawing=1
  NmaCheck(NeonChromeMenuDraw(@nmaState),0)
  nmaDrawing=0 : nmaCapture=0
  NmaCheck(nmaPackets,49) : NmaCheck(nmaMetrics,0) : NmaCheck(nmaPrepares,0)
  PokeI(#NMA_REPORT+32,nmaPackets)
  NmaCheck(NeonChromeMenuInput(@nmaState,200.0,120.0,1,0,0),0)
  NmaCheck(NeonChromeMenuEventGet(@nmaState),21) : NmaCheck(NeonChromeMenuEventGet(@nmaState),0)
  NmaCheck(NeonChromeMenuIsOpen(@nmaState),0) : NmaCheck(NeonChromeMenuBlocksMouse(@nmaState),1)
  NmaCheck(NeonChromeMenuInput(@nmaState,500.0,300.0,0,0,0),0)
  NmaCheck(NeonChromeMenuBlocksMouse(@nmaState),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,20.0,15.0,1,0,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,80.0,15.0,0,0,0),0)
  *node=NeonChromeMenuGet(@nmaState,2) : NmaCheck(nmaState\rootPanel\x,64)
  NmaCheck(nmaState\rootPanel\viewH,322)
  NmaCheck(NeonChromeMenuInput(@nmaState,100.0,100.0,0,-1,0),0) : NmaCheck(*node\scroll,48)
  NmaCheck(NeonChromeMenuInput(@nmaState,100.0,100.0,0,-128,0),0) : NmaCheck(*node\scroll,638)
  NmaCheck(NeonChromeMenuInput(@nmaState,100.0,40.0,0,0,0),0) : NmaCheck(*node\scroll,632)
  NmaCheck(NeonChromeMenuInput(@nmaState,600.0,300.0,1,0,0),0)
  NmaCheck(NeonChromeMenuIsOpen(@nmaState),0) : NmaCheck(NeonChromeMenuBlocksMouse(@nmaState),1)
  NmaCheck(NeonChromeMenuInput(@nmaState,20.0,15.0,0,0,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,20.0,15.0,1,0,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,127.0,0,0,0),0)
  nmaMode=1 : NmaCheck(NeonChromeMenuDraw(@nmaState),-21900)
  NmaCheck(NeonChromeMenuIsOpen(@nmaState),1)
  nmaMode=2 : NmaCheck(NeonChromeMenuDraw(@nmaState),#NCM_ERR_RENDERER)
  nmaMode=3 : NmaCheck(NeonChromeMenuDraw(@nmaState),0)
  NmaCheck(nmaReenter,#NCM_ERR_BUSY) : NmaCheck(nmaOtherBusy,#NCM_ERR_BUSY)
  nmaMode=0 : nmaClearFailure=1
  NmaCheck(NeonChromeMenuDraw(@nmaState),-21901) : NmaCheck(nmaState\cleanupError,-21901)
  nmaClearFailure=0 : NmaCheck(NeonChromeMenuDraw(@nmaState),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,0.0,0.0,0,0,1),0) : NmaCheck(NeonChromeMenuIsOpen(@nmaState),0)
  NmaCheck(NeonChromeMenuBeginBuild(@nmaState),0)
  NmaCheck(NeonChromeMenuBarRect(@nmaState,520.0,0.0,120.0,30.0),0)
  NmaCheck(NmaBuild(@nmaState,"File"),0) : NmaCheck(NeonChromeMenuSeal(@nmaState),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,530.0,15.0,1,0,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,490.0,127.0,0,0,0),0)
  NmaCheck(nmaState\rootPanel\x,464) : NmaCheck(nmaState\subPanel\x,286)
  NmaCheck(NeonChromeMenuBeginBuild(@nmaState),0) : NmaCheck(NmaBuild(@nmaState,"File"),0)
  NmaCheck(NeonChromeMenuBarRect(@nmaState,0.0,270.0,640.0,30.0),0) : NmaCheck(NeonChromeMenuSeal(@nmaState),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,330.0,0,-1,0),0)
  NmaCheck(NeonChromeMenuInput(@nmaState,26.0,360.0,0,0,0),0)
  NmaCheck(nmaState\subPanel\y,336)
  NmaCheck(NeonChromeMenuInput(@nmaState,MathFromBits($7FC00001),0.0,0,0,0),#NCM_ERR_ARGS)
  NmaCheck(NeonServiceBind(services,35),0) : NmaCheck(NeonServiceOpen(),0)
  NmaCheck(NeonServiceCanvas(640,400),0)
  ui=NeonServiceFontRegister(0,0,16) : small=NeonServiceFontRegister(0,1,14)
  NmaCheck(Bool(ui>0 And small>0),1) : NmaCheck(NeonServiceChromeMenuInstall(),0)
  NmaCheck(NeonChromeMenuConfigure(@nmaState,@nmaArena[0],32768,128,64,640,400,1.0,ui,small),0)
  CompilerIf #NMA_SCENE=3
    NmaCheck(NeonChromeMenuBarRect(@nmaState,520.0,0.0,120.0,30.0),0)
  CompilerEndIf
  NmaCheck(NmaBuild(@nmaState,"File"),0) : NmaCheck(NeonChromeMenuSeal(@nmaState),0)
  CompilerIf #NMA_SCENE=2
    *node=NeonChromeMenuGet(@nmaState,2) : x=*node\tabX+2.0
    NmaCheck(NeonChromeMenuInput(@nmaState,x,15.0,1,0,0),0)
    NmaCheck(NeonChromeMenuInput(@nmaState,nmaState\rootPanel\x+30.0,100.0,0,-4,0),0)
    refX=400.0 : rowY=nmaState\rootPanel\viewY
  CompilerElse
    *node=NeonChromeMenuGet(@nmaState,1) : x=*node\tabX+2.0
    NmaCheck(NeonChromeMenuInput(@nmaState,x,15.0,1,0,0),0)
    NmaCheck(NeonChromeMenuInput(@nmaState,nmaState\rootPanel\x+18.0,127.0,0,0,0),0)
    refX=400.0 : If #NMA_SCENE=3 : refX=20.0 : EndIf
    rowY=nmaState\rootPanel\viewY
  CompilerEndIf
  PokeI(#NMA_REPORT+56,ui)
  PokeL(#NMA_REPORT+64,MathBitsOf(nmaState\uiH))
  PokeL(#NMA_REPORT+72,MathBitsOf(NeonServiceTextWidth(ui,"Open")))
  PokeL(#NMA_REPORT+76,MathBitsOf(NeonServiceTextWidth(small,"Ctrl+O")))
  PokeL(#NMA_REPORT+80,MathBitsOf(nmaState\rootPanel\x)) : PokeL(#NMA_REPORT+84,MathBitsOf(nmaState\rootPanel\y))
  PokeL(#NMA_REPORT+88,MathBitsOf(nmaState\rootPanel\w)) : PokeL(#NMA_REPORT+92,MathBitsOf(nmaState\rootPanel\h))
  PokeL(#NMA_REPORT+96,MathBitsOf(nmaState\rootPanel\viewY)) : PokeL(#NMA_REPORT+100,MathBitsOf(nmaState\rootPanel\viewH))
  PokeL(#NMA_REPORT+104,MathBitsOf(nmaState\subPanel\x)) : PokeL(#NMA_REPORT+108,MathBitsOf(nmaState\subPanel\y))
  PokeL(#NMA_REPORT+112,MathBitsOf(nmaState\subPanel\w)) : PokeL(#NMA_REPORT+116,MathBitsOf(nmaState\subPanel\h))
  *node=NeonChromeMenuGet(@nmaState,1) : PokeL(#NMA_REPORT+136,MathBitsOf(*node\labelW))
  PokeL(#NMA_REPORT+140,MathBitsOf(NeonServiceTextWidth(ui,"File")))
  x=nmaState\rootPanel\x+18.0
  refX=refX+(x-MathFFromInt(MathFToI32(x)))
  PokeL(#NMA_REPORT+148,MathBitsOf(refX)) : PokeL(#NMA_REPORT+152,MathBitsOf(x)) : PokeL(#NMA_REPORT+156,MathBitsOf(rowY))
  ty=rowY+(24.0-nmaState\uiH)/2.0
  NmaCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NmaCheck(NeonChromeMenuDraw(@nmaState),0)
  NmaCheck(NeonServiceBox(MathFFromInt(MathFToI32(refX))-1.0,rowY,72.0,24.0,0.169,0.173,0.184,1.0),0)
  CompilerIf #NMA_SCENE=2
    NmaCheck(NeonServiceText(ui,refX,ty,"Tool",0.863,0.863,0.863,1.0),0)
  CompilerElse
    NmaCheck(NeonServiceText(ui,refX,ty,"Open",0.863,0.863,0.863,1.0),0)
  CompilerEndIf
  NmaCheck(NeonServiceEnd(),0)
  ProcedureReturn nmaFailure
EndProcedure
