; SPDX-License-Identifier: MIT
; Palette atomicity, motion policy, nested callback guard and native chrome proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_animation.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_menu.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_tabs.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_list.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
Global nmrDefault.NeonChromePalette,nmrCustom.NeonChromePalette,nmrCopy.NeonChromePalette
Global nmrMenu.NeonChromeMenuState,nmrTabs.NeonChromeTabState,nmrEdit.NeonChromeEditState,nmrList.NeonChromeListState,nmrScroll.NeonChromeScrollState
Global nmrTabConfig.NeonChromeTabConfig,nmrEditConfig.NeonChromeEditConfig,nmrListConfig.NeonChromeListConfig,nmrEditInput.NeonChromeEditInput
Global Dim nmrMenuArena.q[1024]
Global Dim nmrTabArena.q[1024]
Global Dim nmrEditArena.q[256]
Global Dim nmrListArena.q[1024]
Global nmrChecks.i,nmrFailure.i,nmrNative.i,nmrCapture.i,nmrPackets.i,nmrReenter.i,nmrBoxResult.i,nmrReenterChecks.i
CompilerIf #NMR_SCENE=3
Global nmrHoffset.NeonChromeScrollOffset
CompilerEndIf
Global nmrHot.NeonChromeHotState
Procedure NmrCheck(actual.i,expected.i)
  nmrChecks=nmrChecks+1
  If nmrChecks<=420 : PokeI(#NMR_REPORT+256+nmrChecks*16,actual) : PokeI(#NMR_REPORT+264+nmrChecks*16,expected) : EndIf
  If actual<>expected And nmrFailure=0 : nmrFailure=nmrChecks : EndIf
  PokeI(#NMR_REPORT+16,nmrFailure) : PokeI(#NMR_REPORT+24,nmrChecks)
EndProcedure
Procedure NmrRecord(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected p.i
  If nmrCapture=0 : ProcedureReturn : EndIf
  If nmrPackets>=76 : nmrFailure=9999 : ProcedureReturn : EndIf
  p=#NMR_REPORT+7168+nmrPackets*64 : nmrPackets=nmrPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
EndProcedure
Procedure.i NmrBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NmrRecord(1,0,x,y,w,h,r,g,b,a)
  If nmrReenter<>0
    NmrCheck(NeonChromeStylePaletteSet(@nmrCustom),#NSTY_ERR_BUSY)
    NmrCheck(NeonChromeStylePaletteGet(@nmrCopy),#NSTY_ERR_BUSY)
    NmrCheck(NeonChromeStyleDefaults(@nmrCopy),#NSTY_ERR_BUSY)
    NmrCheck(NeonChromeStyleAnimationsSet(1),#NSTY_ERR_BUSY)
    If nmrReenter=2
      NmrCheck(NeonChromeHotBind(0),#NHZ_ERR_BUSY)
      NmrCheck(NeonChromeHotCommit(@nmrHot),#NHZ_ERR_BUSY)
      NmrCheck(NeonChromeHotAbort(@nmrHot),#NHZ_ERR_BUSY)
    EndIf
    nmrReenterChecks=nmrReenterChecks+1 : nmrReenter=0
  EndIf
  If nmrBoxResult<>0 : ProcedureReturn nmrBoxResult : EndIf
  If nmrNative<>0 : ProcedureReturn NeonServiceBox(x,y,w,h,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmrText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NmrRecord(2,font,x,y,0.0,0.0,r,g,b,a)
  If nmrNative<>0 : ProcedureReturn NeonServiceText(font,x,y,text,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.f NmrWidth(font.i,text.i)
  Protected n.i=NeonUtf8Length(text,512)
  If nmrNative<>0 : ProcedureReturn NeonServiceTextWidth(font,text) : EndIf
  ProcedureReturn MathFFromInt(n*7)
EndProcedure
Procedure.f NmrHeight(font.i)
  If nmrNative<>0 : ProcedureReturn NeonServiceLineHeight(font) : EndIf
  ProcedureReturn 14.0
EndProcedure
Procedure.i NmrPrepare(font.i,text.i)
  If nmrNative<>0 : ProcedureReturn NeonServicePrepare(font,text) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmrClip(x.f,y.f,w.f,h.f)
  NmrRecord(3,0,x,y,w,h,0.0,0.0,0.0,0.0)
  If nmrNative<>0 : ProcedureReturn NeonServiceScissorSet(x,y,w,h) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NmrClear()
  NmrRecord(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0)
  If nmrNative<>0 : ProcedureReturn NeonServiceScissorClear() : EndIf
  ProcedureReturn 0
EndProcedure
Procedure NmrInstall()
  NmrCheck(NeonChromeMenuRendererInstall(@NmrBox,@NmrText,@NmrWidth,@NmrHeight,@NmrPrepare,@NmrClip,@NmrClear),0)
  NmrCheck(NeonChromeTabsRendererInstall(@NmrBox,@NmrText,@NmrWidth,@NmrHeight,@NmrPrepare,@NmrClip,@NmrClear),0)
  NmrCheck(NeonChromeEditRendererInstall(@NmrBox,@NmrText,@NmrWidth,@NmrHeight,@NmrPrepare,@NmrClip,@NmrClear),0)
  NmrCheck(NeonChromeListRendererInstall(@NmrBox,@NmrText,@NmrWidth,@NmrHeight,@NmrPrepare,@NmrClip,@NmrClear),0)
EndProcedure
Procedure NmrSetup(font.i,base.f)
  Protected i.i
  NmrCheck(NeonChromeMenuConfigure(@nmrMenu,@nmrMenuArena[0],8192,8,64,640,400,1.0,font,font),0)
  NmrCheck(NeonChromeMenuBarRect(@nmrMenu,base,20.0,290.0,26.0),0)
  NmrCheck(NeonChromeMenuAddRoot(@nmrMenu,10,"File"),0)
  NmrCheck(NeonChromeMenuAddItem(@nmrMenu,11,10,"Open","Ctrl+O",1,1),0)
  NmrCheck(NeonChromeMenuAddItem(@nmrMenu,12,10,"Unavailable","",0,0),0)
  NmrCheck(NeonChromeMenuSeal(@nmrMenu),0)
  nmrTabConfig\x=base : nmrTabConfig\y=55.0 : nmrTabConfig\w=290.0 : nmrTabConfig\h=30.0 : nmrTabConfig\scale=1.0
  nmrTabConfig\font=font : nmrTabConfig\smallFont=font : nmrTabConfig\italicFont=-1 : nmrTabConfig\activeId=1
  CompilerIf #NMR_SCENE=3
    If nmrNative<>0 : nmrTabConfig\withClose=1 : nmrTabConfig\flags=#NCT_SCROLL : nmrTabConfig\w=140.0 : EndIf
  CompilerEndIf
  NmrCheck(NeonChromeTabsConfigure(@nmrTabs,@nmrTabArena[0],8192,8,64,@nmrTabConfig),0)
  NmrCheck(NeonChromeTabsAdd(@nmrTabs,1,"Sources",#NCT_NORMAL),0)
  NmrCheck(NeonChromeTabsAdd(@nmrTabs,2,"Preview",#NCT_PINNED),0)
  NmrCheck(NeonChromeTabsSeal(@nmrTabs),0)
  nmrEditConfig\id=1 : nmrEditConfig\font=font : nmrEditConfig\text="Road names" : nmrEditConfig\placeholder="Find"
  nmrEditConfig\x=base : nmrEditConfig\y=100.0 : nmrEditConfig\w=290.0 : nmrEditConfig\h=30.0 : nmrEditConfig\scale=1.0
  NmrCheck(NeonChromeEditConfigure(@nmrEdit,@nmrEditArena[0],2048,128,@nmrEditConfig),0)
  NmrCheck(NeonChromeEditSeal(@nmrEdit),0)
  NmrCheck(NeonChromeScrollConfigure(@nmrScroll,1.0),0)
  nmrListConfig\id=10 : nmrListConfig\font=font : nmrListConfig\scrollState=@nmrScroll
  nmrListConfig\x=base : nmrListConfig\y=145.0 : nmrListConfig\w=290.0 : nmrListConfig\h=100.0 : nmrListConfig\rowH=24.0 : nmrListConfig\scale=1.0
  NmrCheck(NeonChromeListConfigure(@nmrList,@nmrListArena[0],8192,8,64,@nmrListConfig),0)
  NmrCheck(NeonChromeListAdd(@nmrList,1,"Assets",0,0,1,"group"),0)
  NmrCheck(NeonChromeListAdd(@nmrList,2,"Road names",1,1,0,"UTF8"),0)
  For i=3 To 6 : NmrCheck(NeonChromeListAdd(@nmrList,i,"Route",1,0,0,0),0) : Next
  NmrCheck(NeonChromeListSeal(@nmrList),0)
  NmrCheck(NeonChromeScrollInput(@nmrScroll,-10.0,-10.0,0),0)
  NmrCheck(NeonChromeListInput(@nmrList,0,0,0.0),0)
EndProcedure
Procedure NmrDraw()
  NmrCheck(NeonChromeTabsDraw(@nmrTabs),0)
  NmrCheck(NeonChromeEditDraw(@nmrEdit),0)
  NmrCheck(NeonChromeListDraw(@nmrList),0)
  CompilerIf #NMR_SCENE=3
    NmrStage(NeonChromeScrollPaintH(@nmrScroll,99,20.0,260.0,290.0,12.0,100,20,@nmrHoffset))
  CompilerEndIf
  NmrCheck(NeonChromeMenuDraw(@nmrMenu),0)
EndProcedure
Global nmrAnimation.NeonChromeAnimationState,nmrValue.NeonChromeAnimationValue,nmrIdentity.NeonChromeHotIdentity
Global Dim nmrAnimArena.q[128]
Global Dim nmrHotArena.q[1024]
Global Dim nmrKey.a[20]
Global nmrStages.i
Procedure.i NmrNoClock()
  ProcedureReturn -1
EndProcedure
Global nmrClock.i=@NmrNoClock
Procedure.i NmrStage(rc.i)
  nmrStages=nmrStages+1
  If rc<>0 And nmrFailure=0 : nmrFailure=10000+nmrStages : PokeI(#NMR_REPORT+16,nmrFailure) : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,j.i,font.i,rc.i,old.i,started.i,now.i,frameStart.i,target.f,p.i
  For i=0 To 16383 : PokeA(#NMR_REPORT+i,0) : Next
  PokeI(#NMR_REPORT,$4E4D5231) : PokeI(#NMR_REPORT+8,#NMR_SCENE)
  NmrCheck(SizeOf(NeonChromeAnimationSlot),32)
  NmrCheck(SizeOf(NeonChromeHotRegion),40)
  NmrCheck(NeonChromeAnimationConfigure(@nmrAnimation,@nmrAnimArena[0],1024,3,16),0)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"x",1.0,16.0,0.0,1,@nmrValue),-22601)
  NmrCheck(NeonChromeAnimationBegin(@nmrAnimation,-1.0),0)
  NmrCheck(NeonChromeAnimationBegin(@nmrAnimation,0.0),-22601)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"snap",7.0,16.0,0.0,0,@nmrValue),0)
  NmrCheck(MathBitsOf(nmrValue\value),1088421888)
  NmrCheck(NeonChromeAnimationForget(@nmrAnimation,"snap"),-22601)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"hover",1.0,16.0,0.0,1,@nmrValue),0)
  NmrCheck(MathBitsOf(nmrValue\value),0)
  NmrCheck(nmrValue\moving,1)
  NmrCheck(NeonChromeAnimationActive(@nmrAnimation),1)
  NmrCheck(NeonChromeAnimationEnd(@nmrAnimation),0)
  NmrCheck(NeonChromeAnimationBegin(@nmrAnimation,1.0),0)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"hover",1.0,16.0,0.0,1,@nmrValue),0)
  NmrCheck(Bool(nmrValue\value>0.55 And nmrValue\value<0.551),1)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"",-10.0,16.0,0.0,0,@nmrValue),0)
  NmrCheck(Bool(nmrValue\value=-10.0),1)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"fourth",1.0,16.0,0.0,0,@nmrValue),-22602)
  NmrCheck(Bool(nmrValue\value=-10.0),1)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"hover",1.0,-1.0,0.0,0,@nmrValue),-22600)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"hover",MathFromBits($7FC00000),1.0,0.0,0,@nmrValue),-22600)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"hover",1.0,1.0,0.0,0,@nmrAnimation),-22600)
  nmrKey[0]=$C0 : nmrKey[1]=$AF : nmrKey[2]=0
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,@nmrKey[0],1.0,1.0,0.0,0,@nmrValue),-22603)
  NmrCheck(NeonChromeAnimationEnd(@nmrAnimation),0)
  NmrCheck(NeonChromeAnimationForget(@nmrAnimation,""),0)
  NmrCheck(nmrAnimation\count,2)
  NmrCheck(NeonChromeAnimationForget(@nmrAnimation,"missing"),0)
  NmrCheck(NeonChromeAnimationConfigure(@nmrAnimation,@nmrAnimArena[0],1024,3,16),0)
  nmrKey[0]=99 : nmrKey[1]=111 : nmrKey[2]=112 : nmrKey[3]=121 : nmrKey[4]=0
  NmrCheck(NeonChromeAnimationBegin(@nmrAnimation,0.0),0)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,@nmrKey[0],4.0,16.0,0.0,0,@nmrValue),0)
  For i=0 To 19 : nmrKey[i]=0 : Next
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"copy",5.0,16.0,0.0,0,@nmrValue),0)
  NmrCheck(nmrAnimation\count,1)
  NmrCheck(MathBitsOf(nmrValue\value),1082130432)
  NmrCheck(NeonChromeStyleAnimationsSet(0),0)
  NmrCheck(NeonChromeAnimationStep(@nmrAnimation,"copy",8.0,16.0,0.0,0,@nmrValue),0)
  NmrCheck(MathBitsOf(nmrValue\value),1090519040)
  NmrCheck(nmrValue\moving,0)
  NmrCheck(NeonChromeAnimationEnd(@nmrAnimation),0)
  NmrCheck(NeonChromeAnimationBegin(@nmrAnimation,MathFromBits($7FC00000)),-22600)
  NmrCheck(nmrAnimation\open,0)
  NmrCheck(NeonChromeStyleAnimationsSet(1),0)
  NmrCheck(NeonChromeHotConfigure(@nmrHot,@nmrHotArena[0],8192,3),0)
  NmrCheck(NeonChromeHotAt(@nmrHot,0.0,0.0,@nmrIdentity),0)
  NmrCheck(nmrIdentity\family,0)
  NmrCheck(NeonChromeHotBegin(@nmrHot),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,1,0.0,0.0,10.0,10.0),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,2,5.0,5.0,10.0,10.0),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,3,0.0,0.0,0.0,1.0),0)
  NmrCheck(nmrHot\count,2)
  NmrCheck(NeonChromeHotCommit(@nmrHot),0)
  NmrCheck(NeonChromeHotAt(@nmrHot,6.0,6.0,@nmrIdentity),1)
  NmrCheck(nmrIdentity\item,2)
  NmrCheck(NeonChromeHotAt(@nmrHot,15.0,15.0,@nmrIdentity),0)
  NmrCheck(NeonChromeHotChanged(@nmrHot,1.0,1.0,2.0,2.0),0)
  NmrCheck(NeonChromeHotChanged(@nmrHot,1.0,1.0,6.0,6.0),1)
  NmrCheck(NeonChromeHotBegin(@nmrHot),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,3,20.0,20.0,10.0,10.0),0)
  NmrCheck(NeonChromeHotAt(@nmrHot,6.0,6.0,@nmrIdentity),1)
  NmrCheck(nmrIdentity\item,2)
  NmrCheck(NeonChromeHotAbort(@nmrHot),0)
  NmrCheck(NeonChromeHotAt(@nmrHot,6.0,6.0,@nmrIdentity),1)
  NmrCheck(NeonChromeHotBegin(@nmrHot),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,0,0.0,0.0,1.0,1.0),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,1,0.0,0.0,1.0,1.0),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,2,0.0,0.0,1.0,1.0),0)
  NmrCheck(NeonChromeHotAdd(@nmrHot,1,100,4,0.0,0.0,1.0,1.0),-22702)
  NmrCheck(nmrHot\count,3)
  NmrCheck(NeonChromeHotCommit(@nmrHot),-22702)
  NmrCheck(NeonChromeHotAbort(@nmrHot),0)
  NmrCheck(NeonChromeHotAt(@nmrHot,6.0,6.0,@nmrIdentity),1)
  NmrInstall() : NmrSetup(1,20.0)
  NmrCheck(NeonChromeHotBind(@nmrHot),0)
  NmrCheck(NeonChromeTabsDraw(@nmrTabs),-22701)
  NmrCheck(NeonChromeHotBegin(@nmrHot),0)
  NmrCheck(NeonChromeListDraw(@nmrList),-22702)
  NmrCheck(NeonChromeHotCommit(@nmrHot),-22702)
  NmrCheck(NeonChromeHotAbort(@nmrHot),0)
  NmrCheck(NeonChromeHotBind(0),0)
  NmrCheck(NeonChromeHotConfigure(@nmrHot,@nmrHotArena[0],8192,64),0)
  NmrCheck(NeonChromeHotBind(@nmrHot),0) : NmrCheck(NeonChromeHotBegin(@nmrHot),0)
  nmrReenter=2 : NmrCheck(NeonChromeTabsDraw(@nmrTabs),0) : NmrCheck(nmrReenterChecks,1)
  NmrCheck(NeonChromeHotAbort(@nmrHot),0) : NmrCheck(NeonChromeHotBind(0),0)
  NmrCheck(NeonChromeAnimationConfigure(@nmrAnimation,@nmrAnimArena[0],1024,3,16),0)
  NmrCheck(NeonServiceBind(services,35),0)
  nmrClock=PeekI(services+16+11*8)
  NmrCheck(NeonServiceOpen(),0)
  NmrCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,1,14)
  NmrCheck(Bool(font>0),1)
  nmrNative=1 : NmrSetup(font,20.0)
  NmrCheck(NeonChromeHotBind(@nmrHot),0)
  CompilerIf #NMR_SCENE=2
    NmrCheck(NeonChromeMenuInput(@nmrMenu,30.0,30.0,1,0,0),0)
  CompilerEndIf
  PokeI(#NMR_REPORT+64,@nmrMenu) : PokeI(#NMR_REPORT+72,@nmrTabs) : PokeI(#NMR_REPORT+80,@nmrEdit) : PokeI(#NMR_REPORT+88,@nmrList) : PokeI(#NMR_REPORT+96,@nmrScroll)
  started=nmrClock()
  For i=0 To 59
    frameStart=nmrClock() : target=100.0 : If i>=20 : target=300.0 : EndIf : If i>=40 : target=180.0 : EndIf
    If NmrStage(NeonChromeAnimationBegin(@nmrAnimation,1.0/30.0))<>0 : Break : EndIf
    If NmrStage(NeonChromeAnimationStep(@nmrAnimation,"position",target,8.0,20.0,1,@nmrValue))<>0 : Break : EndIf
    If NmrStage(NeonChromeAnimationEnd(@nmrAnimation))<>0 : Break : EndIf
    If NmrStage(NeonChromeHotBegin(@nmrHot))<>0 : Break : EndIf
    If NmrStage(NeonServiceBegin(0.0,0.0,0.0,1.0))<>0 : Break : EndIf
    If i=59 : nmrCapture=1 : EndIf
    NmrDraw() : nmrCapture=0
    If NmrStage(NeonServiceBox(nmrValue\value,300.0,30.0,20.0,0.2,0.8,1.0,1.0))<>0 : Break : EndIf
    If NmrStage(NeonServiceEnd())<>0 : Break : EndIf
    If NmrStage(NeonChromeHotCommit(@nmrHot))<>0 : Break : EndIf
    p=#NMR_REPORT+12032+i*24 : PokeL(p,MathBitsOf(nmrValue\value)) : PokeL(p+4,MathBitsOf(target)) : PokeI(p+8,nmrValue\moving) : PokeI(p+16,nmrHot\previousCount)
    PokeI(#NMR_REPORT+13600+i*8,nmrClock()-frameStart)
    Repeat : now=nmrClock() : Until now-frameStart>=33333 Or now<frameStart
    If now<frameStart Or now-started>6000000 : NmrStage(-1) : Break : EndIf
  Next
  PokeI(#NMR_REPORT+32,i) : PokeI(#NMR_REPORT+40,nmrPackets) : PokeI(#NMR_REPORT+48,nmrHot\previousCount) : PokeI(#NMR_REPORT+56,nmrStages)
  PokeI(#NMR_REPORT+104,font) : PokeI(#NMR_REPORT+112,nmrClock()-started)
  For j=0 To nmrHot\previousCount*40-1 : PokeA(#NMR_REPORT+14592+j,PeekA(nmrHot\previous+j)) : Next
  NmrCheck(NeonChromeHotAt(@nmrHot,30.0,110.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,9)
  NmrCheck(NeonChromeHotAt(@nmrHot,30.0,244.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,10) : NmrCheck(nmrIdentity\item,5)
  NmrCheck(NeonChromeHotAt(@nmrHot,30.0,245.0,@nmrIdentity),0)
  CompilerIf #NMR_SCENE=2
    NmrCheck(NeonChromeHotAt(@nmrHot,30.0,80.0,@nmrIdentity),0)
    NmrCheck(NeonChromeHotAt(@nmrHot,30.0,60.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,3) : NmrCheck(nmrIdentity\item,11)
    NmrCheck(NeonChromeHotAt(@nmrHot,29.0,47.0,@nmrIdentity),0)
  CompilerEndIf
  CompilerIf #NMR_SCENE=3
    NmrCheck(NeonChromeHotAt(@nmrHot,150.0,65.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,11) : NmrCheck(nmrIdentity\item,1)
    NmrCheck(NeonChromeHotAt(@nmrHot,105.0,65.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,6) : NmrCheck(nmrIdentity\item,1)
    NmrCheck(NeonChromeHotAt(@nmrHot,30.0,266.0,@nmrIdentity),1) : NmrCheck(nmrIdentity\family,8) : NmrCheck(nmrIdentity\item,99)
  CompilerEndIf
  NmrCheck(NeonChromeHotBind(0),0)
  ProcedureReturn nmrFailure
EndProcedure
