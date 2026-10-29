; SPDX-License-Identifier: MIT
; Palette atomicity, motion policy, nested callback guard and native chrome proof.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_menu.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_tabs.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_edit.pbi"
XIncludeFile "Anvil/Graphics/neon_chrome_list.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
Global nstDefault.NeonChromePalette,nstCustom.NeonChromePalette,nstCopy.NeonChromePalette
Global nstMenu.NeonChromeMenuState,nstTabs.NeonChromeTabState,nstEdit.NeonChromeEditState,nstList.NeonChromeListState,nstScroll.NeonChromeScrollState
Global nstTabConfig.NeonChromeTabConfig,nstEditConfig.NeonChromeEditConfig,nstListConfig.NeonChromeListConfig,nstEditInput.NeonChromeEditInput
Global Dim nstMenuArena.q[1024]
Global Dim nstTabArena.q[1024]
Global Dim nstEditArena.q[256]
Global Dim nstListArena.q[1024]
Global nstChecks.i,nstFailure.i,nstNative.i,nstCapture.i,nstPackets.i,nstReenter.i,nstBoxResult.i,nstReenterChecks.i
Procedure NstCheck(actual.i,expected.i)
  nstChecks=nstChecks+1
  If nstChecks<=220 : PokeI(#NST_REPORT+256+nstChecks*16,actual) : PokeI(#NST_REPORT+264+nstChecks*16,expected) : EndIf
  If actual<>expected And nstFailure=0 : nstFailure=nstChecks : EndIf
  PokeI(#NST_REPORT+16,nstFailure) : PokeI(#NST_REPORT+24,nstChecks)
EndProcedure
Procedure NstRecord(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected p.i
  If nstCapture=0 : ProcedureReturn : EndIf
  If nstPackets>=160 : nstFailure=9999 : ProcedureReturn : EndIf
  p=#NST_REPORT+4096+nstPackets*64 : nstPackets=nstPackets+1
  PokeI(p,op) : PokeI(p+8,font)
  PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
  PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
EndProcedure
Procedure.i NstBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  NstRecord(1,0,x,y,w,h,r,g,b,a)
  If nstReenter<>0
    NstCheck(NeonChromeStylePaletteSet(@nstCustom),#NSTY_ERR_BUSY)
    NstCheck(NeonChromeStylePaletteGet(@nstCopy),#NSTY_ERR_BUSY)
    NstCheck(NeonChromeStyleDefaults(@nstCopy),#NSTY_ERR_BUSY)
    NstCheck(NeonChromeStyleAnimationsSet(1),#NSTY_ERR_BUSY)
    nstReenterChecks=nstReenterChecks+1 : nstReenter=0
  EndIf
  If nstBoxResult<>0 : ProcedureReturn nstBoxResult : EndIf
  If nstNative<>0 : ProcedureReturn NeonServiceBox(x,y,w,h,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NstText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
  NstRecord(2,font,x,y,0.0,0.0,r,g,b,a)
  If nstNative<>0 : ProcedureReturn NeonServiceText(font,x,y,text,r,g,b,a) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.f NstWidth(font.i,text.i)
  Protected n.i=NeonUtf8Length(text,512)
  If nstNative<>0 : ProcedureReturn NeonServiceTextWidth(font,text) : EndIf
  ProcedureReturn MathFFromInt(n*7)
EndProcedure
Procedure.f NstHeight(font.i)
  If nstNative<>0 : ProcedureReturn NeonServiceLineHeight(font) : EndIf
  ProcedureReturn 14.0
EndProcedure
Procedure.i NstPrepare(font.i,text.i)
  If nstNative<>0 : ProcedureReturn NeonServicePrepare(font,text) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NstClip(x.f,y.f,w.f,h.f)
  NstRecord(3,0,x,y,w,h,0.0,0.0,0.0,0.0)
  If nstNative<>0 : ProcedureReturn NeonServiceScissorSet(x,y,w,h) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NstClear()
  NstRecord(4,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0)
  If nstNative<>0 : ProcedureReturn NeonServiceScissorClear() : EndIf
  ProcedureReturn 0
EndProcedure
Procedure NstInstall()
  NstCheck(NeonChromeMenuRendererInstall(@NstBox,@NstText,@NstWidth,@NstHeight,@NstPrepare,@NstClip,@NstClear),0)
  NstCheck(NeonChromeTabsRendererInstall(@NstBox,@NstText,@NstWidth,@NstHeight,@NstPrepare,@NstClip,@NstClear),0)
  NstCheck(NeonChromeEditRendererInstall(@NstBox,@NstText,@NstWidth,@NstHeight,@NstPrepare,@NstClip,@NstClear),0)
  NstCheck(NeonChromeListRendererInstall(@NstBox,@NstText,@NstWidth,@NstHeight,@NstPrepare,@NstClip,@NstClear),0)
EndProcedure
Procedure NstSetup(font.i,base.f)
  Protected i.i
  NstCheck(NeonChromeMenuConfigure(@nstMenu,@nstMenuArena[0],8192,8,64,640,400,1.0,font,font),0)
  NstCheck(NeonChromeMenuBarRect(@nstMenu,base,20.0,290.0,26.0),0)
  NstCheck(NeonChromeMenuAddRoot(@nstMenu,10,"File"),0)
  NstCheck(NeonChromeMenuAddItem(@nstMenu,11,10,"Open","Ctrl+O",1,1),0)
  NstCheck(NeonChromeMenuAddItem(@nstMenu,12,10,"Unavailable","",0,0),0)
  NstCheck(NeonChromeMenuSeal(@nstMenu),0)
  nstTabConfig\x=base : nstTabConfig\y=55.0 : nstTabConfig\w=290.0 : nstTabConfig\h=30.0 : nstTabConfig\scale=1.0
  nstTabConfig\font=font : nstTabConfig\smallFont=font : nstTabConfig\italicFont=-1 : nstTabConfig\activeId=1
  NstCheck(NeonChromeTabsConfigure(@nstTabs,@nstTabArena[0],8192,8,64,@nstTabConfig),0)
  NstCheck(NeonChromeTabsAdd(@nstTabs,1,"Sources",#NCT_NORMAL),0)
  NstCheck(NeonChromeTabsAdd(@nstTabs,2,"Preview",#NCT_PINNED),0)
  NstCheck(NeonChromeTabsSeal(@nstTabs),0)
  nstEditConfig\id=1 : nstEditConfig\font=font : nstEditConfig\text="Road names" : nstEditConfig\placeholder="Find"
  nstEditConfig\x=base : nstEditConfig\y=100.0 : nstEditConfig\w=290.0 : nstEditConfig\h=30.0 : nstEditConfig\scale=1.0
  NstCheck(NeonChromeEditConfigure(@nstEdit,@nstEditArena[0],2048,128,@nstEditConfig),0)
  NstCheck(NeonChromeEditSeal(@nstEdit),0)
  NstCheck(NeonChromeScrollConfigure(@nstScroll,1.0),0)
  nstListConfig\id=10 : nstListConfig\font=font : nstListConfig\scrollState=@nstScroll
  nstListConfig\x=base : nstListConfig\y=145.0 : nstListConfig\w=290.0 : nstListConfig\h=100.0 : nstListConfig\rowH=24.0 : nstListConfig\scale=1.0
  NstCheck(NeonChromeListConfigure(@nstList,@nstListArena[0],8192,8,64,@nstListConfig),0)
  NstCheck(NeonChromeListAdd(@nstList,1,"Assets",0,0,1,"group"),0)
  NstCheck(NeonChromeListAdd(@nstList,2,"Road names",1,1,0,"UTF8"),0)
  For i=3 To 6 : NstCheck(NeonChromeListAdd(@nstList,i,"Route",1,0,0,0),0) : Next
  NstCheck(NeonChromeListSeal(@nstList),0)
  NstCheck(NeonChromeScrollInput(@nstScroll,-10.0,-10.0,0),0)
  NstCheck(NeonChromeListInput(@nstList,0,0,0.0),0)
EndProcedure
Procedure NstDraw()
  NstCheck(NeonChromeTabsDraw(@nstTabs),0)
  NstCheck(NeonChromeEditDraw(@nstEdit),0)
  NstCheck(NeonChromeListDraw(@nstList),0)
  NstCheck(NeonChromeMenuDraw(@nstMenu),0)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,j.i,rev.i,old.i,font.i,*row.NeonChromeListRow,*tab.NeonChromeTab,rc.i
  For i=0 To 16383 : PokeA(#NST_REPORT+i,0) : Next
  PokeI(#NST_REPORT,$4E535431) : PokeI(#NST_REPORT+8,1)
  NstCheck(SizeOf(NeonChromePalette),180)
  NstCheck(NeonChromeStyleDefaults(@nstDefault),0)
  NstCheck(NeonChromeStylePaletteGet(@nstCopy),0)
  old=0 : For i=0 To 176 Step 4 : If PeekL(@nstCopy+i)<>PeekL(@nstDefault+i) : old=1 : EndIf : Next
  NstCheck(old,0)
  rev=NeonChromeStyleRevision()
  NstCheck(NeonChromeStylePaletteSet(@nstDefault),0) : NstCheck(NeonChromeStyleRevision(),rev)
  NstCheck(NeonChromeStyleDefaults(0),#NSTY_ERR_ARGS) : NstCheck(NeonChromeStylePaletteGet(@nstCopy+1),#NSTY_ERR_ARGS)
  NstCheck(NeonChromeStylePaletteSet(@nstyPalette),#NSTY_ERR_ARGS) : NstCheck(NeonChromeStyleDefaults(@nstyPalette+4),#NSTY_ERR_ARGS)
  ; Validate every field, including the final field, before publication.
  For i=0 To 176 Step 4
    old=PeekL(@nstDefault+i) : PokeL(@nstDefault+i,$7FC00000)
    rc=NeonChromeStylePaletteSet(@nstDefault) : PokeL(@nstDefault+i,old)
    NstCheck(rc,#NSTY_ERR_ARGS)
  Next
  NstCheck(NeonChromeStyleRevision(),rev) : NstCheck(NeonChromeStylePaletteGet(@nstCopy),0)
  For i=0 To 179 : If PeekA(@nstCopy+i)<>PeekA(@nstDefault+i) : nstFailure=9001 : EndIf : Next
  For i=0 To 176 Step 4 : PokeL(@nstCustom+i,MathBitsOf(0.1+MathFFromInt(i/4)*0.01)) : Next
  nstCustom\text\r=0.9 : nstCustom\text\g=0.95 : nstCustom\text\b=1.0
  nstCustom\accent\r=0.8 : nstCustom\accent\g=0.45 : nstCustom\accent\b=0.95
  NstCheck(NeonChromeStylePaletteSet(@nstCustom),0) : NstCheck(NeonChromeStyleRevision(),rev+1)
  old=MathBitsOf(nstCustom\bg\r) : nstCustom\bg\r=0.99
  NstCheck(NeonChromeStylePaletteGet(@nstCopy),0) : NstCheck(MathBitsOf(nstCopy\bg\r),old)
  nstCustom\bg\r=MathFromBits(old)
  NstCheck(NeonChromeStyleAnimationsSet(2),#NSTY_ERR_ARGS)
  NstCheck(NeonChromeStyleAnimationsSet(0),0) : NstCheck(NeonChromeStyleAnimationsGet(),0)
  NstCheck(NeonChromeStyleRevision(),rev+2) : NstCheck(NeonChromeStyleAnimationsSet(0),0) : NstCheck(NeonChromeStyleRevision(),rev+2)
  NstInstall() : NstSetup(1,20.0)
  ; Reduced motion snaps even at dt=0; normal motion retains its initial value.
  NstCheck(NeonChromeTabsInput(@nstTabs,130.0,65.0,1,0,0,0.0),0)
  *tab=nctNode(@nstTabs,1) : NstCheck(MathBitsOf(*tab\hover),MathBitsOf(1.0))
  NstCheck(NeonChromeScrollInput(@nstScroll,30.0,155.0,0),0) : NstCheck(NeonChromeListInput(@nstList,0,0,0.0),0)
  *row=NeonChromeListGet(@nstList,1) : NstCheck(MathBitsOf(*row\hover),MathBitsOf(1.0))
  NstCheck(NeonChromeStyleAnimationsSet(1),0)
  NstCheck(NeonChromeListInput(@nstList,0,1,0.0),0) : NstCheck(MathBitsOf(*row\hover),MathBitsOf(1.0))
  nstReenter=1 : NstCheck(NeonChromeListDraw(@nstList),0) : NstCheck(nstReenterChecks,1) : NstCheck(nstyBusy,0)
  nstBoxResult=-22499 : NstCheck(NeonChromeTabsDraw(@nstTabs),-22499) : NstCheck(nstyBusy,0)
  nstBoxResult=1 : NstCheck(NeonChromeEditDraw(@nstEdit),#NCE_ERR_RENDERER) : NstCheck(nstyBusy,0)
  nstBoxResult=0 : NstCheck(NeonChromeStylePaletteSet(@nstDefault),0)
  NstCheck(NeonChromeStyleAnimationsSet(0),0)
  NstCheck(NeonChromeListInput(@nstList,0,1,0.0),0)
  NstCheck(NeonChromeListDraw(@nstList),0) : NstCheck(NeonChromeListNeedsRedraw(@nstList),0)
  NstCheck(NeonChromeStylePaletteSet(@nstCustom),0) : NstCheck(NeonChromeListNeedsRedraw(@nstList),1)
  NstCheck(NeonChromeListDraw(@nstList),0) : NstCheck(NeonChromeListNeedsRedraw(@nstList),0)
  NstCheck(NeonChromeStylePaletteSet(@nstDefault),0)
  NstCheck(NeonServiceBind(services,35),0) : NstCheck(NeonServiceOpen(),0) : NstCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,1,14) : NstCheck(Bool(font>0),1) : nstNative=1
  NstSetup(font,20.0)
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  nstCapture=1 : NstDraw() : nstCapture=0
  PokeI(#NST_REPORT+40,nstPackets)
  NstCheck(NeonServiceEnd(),0)
  ; Publish outside the frame; no metrics or text are retained from caller palette storage.
  NstCheck(NeonChromeStylePaletteSet(@nstCustom),0) : NstSetup(font,330.0)
  NstCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  ; Native scene uses the changed palette; a small reference row shows the default.
  NeonServiceBox(20.0,20.0,40.0,40.0,nstDefault\head\r,nstDefault\head\g,nstDefault\head\b,1.0)
  NeonServiceBox(70.0,20.0,40.0,40.0,nstDefault\accent\r,nstDefault\accent\g,nstDefault\accent\b,1.0)
  nstCapture=1 : NstDraw() : nstCapture=0
  NstCheck(NeonServiceEnd(),0)
  PokeI(#NST_REPORT+32,nstPackets) : PokeI(#NST_REPORT+48,nstyBusy) : PokeI(#NST_REPORT+56,font)
  PokeI(#NST_REPORT+64,NeonChromeStyleRevision())
  For i=0 To 179 : PokeA(#NST_REPORT+14400+i,PeekA(@nstDefault+i)) : PokeA(#NST_REPORT+14592+i,PeekA(@nstCustom+i)) : Next
  NstCheck(NeonChromeStylePaletteSet(@nstDefault),0) : NstCheck(NeonChromeStyleAnimationsSet(1),0)
  ProcedureReturn nstFailure
EndProcedure
