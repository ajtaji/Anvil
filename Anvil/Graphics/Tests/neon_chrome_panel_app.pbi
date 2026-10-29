; SPDX-License-Identifier: MIT
; Prepared panel model, ordered callbacks and independent native composition.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_panel.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_panel.pbi"
Global Dim nppStates.NeonChromePanelState[5]
Global Dim nppTitles.q[72]
Global Dim nppScratch.q[18]
Global Dim nppInput.a[128]
Global Dim nppBefore.q[32]
Global nppConfig.NeonChromePanelConfig,nppPalette.NeonChromePalette
Global nppChecks.i,nppFailure.i,nppPackets.i,nppCapture.i,nppMode.i,nppTextFailure.i,nppPrepFailure.i
Global nppBoxes.i,nppTexts.i,nppPrepares.i,nppDrawing.i,nppPreparedInside.i
Procedure NppCheck(actual.i,expected.i)
 PokeI(#NPP_REPORT+256+nppChecks*16,actual) : PokeI(#NPP_REPORT+264+nppChecks*16,expected)
 nppChecks=nppChecks+1
 If actual<>expected And nppFailure=0 : nppFailure=nppChecks : EndIf
EndProcedure
Procedure NppRecord(op.i,font.i,x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f,text.i)
 Protected p.i,n.i,i.i
 If nppCapture=0 : ProcedureReturn : EndIf
 If nppPackets>=30 : nppFailure=9998 : ProcedureReturn : EndIf
 p=#NPP_REPORT+16384+nppPackets*128 : nppPackets=nppPackets+1
 PokeI(p,op) : PokeI(p+8,font)
 PokeL(p+16,MathBitsOf(x)) : PokeL(p+20,MathBitsOf(y)) : PokeL(p+24,MathBitsOf(w)) : PokeL(p+28,MathBitsOf(h))
 PokeL(p+32,MathBitsOf(r)) : PokeL(p+36,MathBitsOf(g)) : PokeL(p+40,MathBitsOf(b)) : PokeL(p+44,MathBitsOf(a))
 If text<>0
  n=NeonUtf8Length(text,64) : If n<0 : nppFailure=9999 : ProcedureReturn : EndIf
  PokeI(p+48,n) : For i=0 To n : PokeA(p+64+i,PeekA(text+i)) : Next
 EndIf
EndProcedure
Procedure.i NppBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
 nppBoxes=nppBoxes+1 : NppRecord(1,0,x,y,w,h,r,g,b,a,0)
 If nppMode=1 : ProcedureReturn 1 : EndIf
 If nppMode=2 : ProcedureReturn -23399 : EndIf
 If nppMode=3
  nppMode=0
  NppCheck(NeonChromePanelTitleSet(@nppStates[4],"changed",8),#NCP_ERR_BUSY)
  NppCheck(NeonChromePanelGeometrySet(@nppStates[4],0.0,0.0,10.0,10.0,0.0),#NCP_ERR_BUSY)
  NppCheck(NeonChromePanelAccentSet(@nppStates[4],0.0,0.0,0.0),#NCP_ERR_BUSY)
  NppCheck(NeonChromePanelConfigure(0,0,0,0),#NCP_ERR_BUSY)
  NppCheck(NeonChromePanelRendererInstall(@NppBox,@NppText,@NppPrepare),#NCP_ERR_BUSY)
  NppCheck(NeonChromeStylePaletteSet(@nppPalette),#NSTY_ERR_BUSY)
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i NppText(font.i,x.f,y.f,text.i,r.f,g.f,b.f,a.f)
 nppTexts=nppTexts+1 : NppRecord(2,font,x,y,0.0,0.0,r,g,b,a,text)
 ProcedureReturn nppTextFailure
EndProcedure
Procedure.i NppPrepare(font.i,text.i)
 nppPrepares=nppPrepares+1
 If nppDrawing<>0 : nppPreparedInside=nppPreparedInside+1 : EndIf
 ProcedureReturn nppPrepFailure
EndProcedure
Procedure NppSetupConfig(font.i,title.i,bytes.i,y.f,h.f,header.f,ar.f,ag.f,ab.f)
 nppConfig\font=font : nppConfig\title=title : nppConfig\titleBudget=bytes
 nppConfig\x=20.0 : nppConfig\y=y : nppConfig\w=280.0 : nppConfig\h=h
 nppConfig\headerH=header : nppConfig\ar=ar : nppConfig\ag=ag : nppConfig\ab=ab
EndProcedure
Procedure NppSave()
 Protected i.i
 For i=0 To SizeOf(NeonChromePanelState)-1 : PokeA(@nppBefore[0]+i,PeekA(@nppStates[4]+i)) : Next
 For i=0 To 143 : PokeA(@nppBefore[0]+104+i,PeekA(@nppScratch[0]+i)) : Next
EndProcedure
Procedure.i NppSame(state.i)
 Protected i.i,bad.i
 If state<>0
  For i=0 To 103 : If PeekA(@nppBefore[0]+i)<>PeekA(@nppStates[4]+i) : bad=bad+1 : EndIf : Next
 EndIf
 For i=0 To 143 : If PeekA(@nppBefore[0]+104+i)<>PeekA(@nppScratch[0]+i) : bad=bad+1 : EndIf : Next
 ProcedureReturn bad
EndProcedure
Procedure NppCustom()
 nppPalette\panel\r=0.08 : nppPalette\panel\g=0.13 : nppPalette\panel\b=0.19
 nppPalette\head\r=0.12 : nppPalette\head\g=0.2 : nppPalette\head\b=0.29
 nppPalette\line\r=0.3 : nppPalette\line\g=0.4 : nppPalette\line\b=0.5
EndProcedure
Procedure.i NppRef(index.i,font.i)
 Protected y.f,h.f,hh.f,ar.f,ag.f,ab.f,pr.f,pg.f,pb.f,hr.f,hg.f,hb.f,lr.f,lg.f,lb.f,title.i,rc.i
 If index=0 : y=40.0 : h=72.0 : hh=26.0 : ar=0.2 : ag=0.7 : ab=0.9 : title=?nppReference0 : EndIf
 If index=1 : y=130.0 : h=72.0 : hh=32.0 : ar=0.9 : ag=0.5 : ab=0.2 : title=?nppReference1 : EndIf
 If index=2 : y=220.0 : h=64.0 : hh=26.0 : ar=0.5 : ag=0.5 : ab=0.5 : title=?nppReference2 : EndIf
 If index=3 : y=300.0 : h=60.0 : hh=0.0 : ar=0.8 : ag=0.6 : ab=0.2 : title=?nppReference3 : EndIf
 pr=0.145 : pg=0.149 : pb=0.161 : hr=0.169 : hg=0.173 : hb=0.184 : lr=0.196 : lg=0.2 : lb=0.212
 If index>0 : pr=0.08 : pg=0.13 : pb=0.19 : hr=0.12 : hg=0.2 : hb=0.29 : lr=0.3 : lg=0.4 : lb=0.5 : EndIf
 rc=NeonServiceBox(340.0,y,280.0,h,pr,pg,pb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
 If index<>2
  If hh>0.0
   rc=NeonServiceBox(340.0,y,280.0,hh,hr,hg,hb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
   rc=NeonServiceBox(340.0,y,3.0,hh,ar,ag,ab,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  rc=NeonServiceBox(340.0,y+hh,280.0,1.0,lr,lg,lb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonServiceText(font,352.0,y+5.0,title,ar,ag,ab,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
 EndIf
 rc=NeonServiceBox(340.0,y,280.0,1.0,lr,lg,lb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=NeonServiceBox(340.0,y+h-1.0,280.0,1.0,lr,lg,lb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=NeonServiceBox(340.0,y,1.0,h,lr,lg,lb,1.0) : If rc<>0 : ProcedureReturn rc : EndIf
 ProcedureReturn NeonServiceBox(619.0,y,1.0,h,lr,lg,lb,1.0)
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,j.i,before.i,font.i
 For i=0 To #NPP_REPORT_BYTES-1 : PokeA(#NPP_REPORT+i,0) : Next
 PokeI(#NPP_REPORT,$4E505031) : PokeI(#NPP_REPORT+8,1)
 NppCheck(SizeOf(NeonChromePanelConfig),56)
 NppCheck(SizeOf(NeonChromePanelState),104)
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23301)
 NppCheck(NeonServiceChromePanelInstall(),-23304)
 NppCheck(NeonChromePanelTitleBytes(?nppTitle0,20),20)
 For i=0 To 143 : PokeA(@nppScratch[0]+i,165) : Next
 NppSetupConfig(0,?nppTitle0,20,10.0,80.0,26.0,0.2,0.7,0.9)
 NppCheck(NeonChromePanelConfigure(@nppStates[4],@nppScratch[1],128,@nppConfig),0)
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23301)
 NppCheck(NeonChromePanelSeal(@nppStates[4]),-23304)
 NppCheck(NeonChromePanelRendererInstall(0,@NppText,@NppPrepare),-23300)
 NppCheck(NeonChromePanelRendererInstall(@NppBox,@NppText,@NppPrepare),0)
 NppCheck(NeonChromePanelSeal(@nppStates[4]),0)
 NppSave()
 nppConfig\w=-1.0
 NppCheck(NeonChromePanelConfigure(@nppStates[4],@nppScratch[1],128,@nppConfig),-23300)
 NppCheck(NppSame(1),0)
 nppConfig\w=280.0
 NppCheck(NeonChromePanelConfigure(@nppStates[4],@nppStates[4],128,@nppConfig),-23300)
 NppCheck(NppSame(1),0)
 NppCheck(NeonChromePanelConfigure(@nppStates[4],@nppScratch[1],19,@nppConfig),-23303)
 NppCheck(NppSame(1),0)
 nppConfig\title=?nppBad : nppConfig\titleBudget=2
 NppCheck(NeonChromePanelConfigure(@nppStates[4],@nppScratch[1],128,@nppConfig),-23305)
 NppCheck(NppSame(1),0)
 nppConfig\title=?nppTitle0 : nppConfig\titleBudget=20
 NppCheck(NeonChromePanelTitleSet(@nppStates[4],?nppBad,2),-23305)
 NppCheck(NeonChromePanelError(@nppStates[4]),-23305)
 NppCheck(NppSame(0),0)
 NppCheck(nppStates[4]\ready,1)
 NppCheck(NeonChromePanelTitleSet(@nppStates[4],?nppLong,130),-23303)
 NppCheck(NppSame(0),0)
 NppCheck(NeonChromePanelTitleSet(@nppStates[4],NeonChromePanelTitle(@nppStates[4]),20),-23300)
 NppCheck(NppSame(0),0)
 NppCheck(NeonChromePanelGeometrySet(@nppStates[4],0.0,0.0,-1.0,1.0,0.0),-23300)
 NppCheck(NeonChromePanelGeometrySet(@nppStates[4],11.0,12.0,120.0,90.0,120.0),0)
 NppCheck(MathBitsOf(nppStates[4]\x),1093664768)
 NppCheck(MathBitsOf(nppStates[4]\y),1094713344)
 NppCheck(MathBitsOf(nppStates[4]\w),1123024896)
 NppCheck(MathBitsOf(nppStates[4]\h),1119092736)
 NppCheck(MathBitsOf(nppStates[4]\headerH),1123024896)
 NppCheck(NeonChromePanelAccentSet(@nppStates[4],1.1,0.0,0.0),-23300)
 NppCheck(NeonChromePanelAccentSet(@nppStates[4],0.3,0.4,0.5),0)
 NppCheck(MathBitsOf(nppStates[4]\ar),1050253722)
 NppCheck(MathBitsOf(nppStates[4]\ag),1053609165)
 NppCheck(MathBitsOf(nppStates[4]\ab),1056964608)
 NppCheck(nppStates[4]\ready,1)
 NppCheck(nppPrepares,1)
 nppDrawing=1 : nppMode=1 : before=nppBoxes
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23304)
 NppCheck(nppBoxes-before,1)
 nppMode=2 : before=nppBoxes
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23399)
 NppCheck(nppBoxes-before,1)
 nppMode=0 : nppTextFailure=1 : before=nppBoxes
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23304)
 NppCheck(nppBoxes-before,4)
 nppTextFailure=0
 NppCheck(NeonChromePanelDraw(@nppStates[4]),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[4]),0)
 NppCheck(NeonChromePanelError(@nppStates[4]),0)
 NppCheck(NeonChromeStylePaletteGet(@nppPalette),0)
 NppCustom()
 NppCheck(NeonChromeStylePaletteSet(@nppPalette),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[4]),1)
 nppMode=3
 NppCheck(NeonChromePanelDraw(@nppStates[4]),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[4]),0)
 nppDrawing=0
 NppCheck(NeonChromePanelTitleSet(@nppStates[4],"last",5),0)
 nppPrepFailure=1
 NppCheck(NeonChromePanelSeal(@nppStates[4]),-23304)
 NppCheck(NeonChromePanelDraw(@nppStates[4]),-23301)
 nppPrepFailure=-23398
 NppCheck(NeonChromePanelSeal(@nppStates[4]),-23398)
 nppPrepFailure=0
 NppCheck(NeonChromePanelSeal(@nppStates[4]),0)
 NppCheck(NeonChromePanelTitleSet(@nppStates[4],"",1),0)
 before=nppPrepares
 NppCheck(NeonChromePanelSeal(@nppStates[4]),0)
 NppCheck(nppPrepares-before,0)
 before=nppBoxes
 NppCheck(NeonChromePanelDraw(@nppStates[4]),0)
 NppCheck(nppBoxes-before,5)
 For i=0 To 575 : PokeA(@nppTitles[0]+i,165) : Next
 For j=0 To 19 : PokeA(@nppInput[0]+j,PeekA(?nppTitle0+j)) : Next
 NppSetupConfig(0,@nppInput[0],20,40.0,72.0,26.0,0.2,0.7,0.9)
 NppCheck(NeonChromePanelConfigure(@nppStates[0],@nppTitles[1],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[0]),0)
 For j=0 To 12 : PokeA(@nppInput[0]+j,PeekA(?nppTitle1+j)) : Next
 NppSetupConfig(0,@nppInput[0],13,130.0,72.0,32.0,0.9,0.5,0.2)
 NppCheck(NeonChromePanelConfigure(@nppStates[1],@nppTitles[19],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[1]),0)
 For j=0 To 0 : PokeA(@nppInput[0]+j,PeekA(?nppTitle2+j)) : Next
 NppSetupConfig(0,@nppInput[0],1,220.0,64.0,26.0,0.5,0.5,0.5)
 NppCheck(NeonChromePanelConfigure(@nppStates[2],@nppTitles[37],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[2]),0)
 For j=0 To 11 : PokeA(@nppInput[0]+j,PeekA(?nppTitle3+j)) : Next
 NppSetupConfig(0,@nppInput[0],12,300.0,60.0,0.0,0.8,0.6,0.2)
 NppCheck(NeonChromePanelConfigure(@nppStates[3],@nppTitles[55],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[3]),0)
 NppCheck(NeonChromeStyleDefaults(@nppPalette),0)
 NppCheck(NeonChromeStylePaletteSet(@nppPalette),0)
 nppCapture=1 : nppDrawing=1
 NppCheck(NeonChromePanelDraw(@nppStates[0]),0)
 NppCustom()
 NppCheck(NeonChromeStylePaletteSet(@nppPalette),0)
 NppCheck(NeonChromePanelDraw(@nppStates[1]),0)
 NppCheck(NeonChromePanelDraw(@nppStates[2]),0)
 NppCheck(NeonChromePanelDraw(@nppStates[3]),0)
 nppCapture=0 : nppDrawing=0
 NppCheck(nppPackets,30)
 NppCheck(nppPreparedInside,0)
 NppCheck(NeonServiceBind(services,35),0)
 NppCheck(NeonServiceOpen(),0)
 NppCheck(NeonServiceCanvas(640,400),0)
 font=NeonServiceFontRegister(0,1,14)
 NppCheck(Bool(font>3),1)
 NppCheck(NeonServiceChromePanelInstall(),0)
 For i=0 To 575 : PokeA(@nppTitles[0]+i,165) : Next
 For j=0 To 19 : PokeA(@nppInput[0]+j,PeekA(?nppTitle0+j)) : Next
 NppSetupConfig(font,@nppInput[0],20,40.0,72.0,26.0,0.2,0.7,0.9)
 NppCheck(NeonChromePanelConfigure(@nppStates[0],@nppTitles[1],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[0]),0)
 For j=0 To 12 : PokeA(@nppInput[0]+j,PeekA(?nppTitle1+j)) : Next
 NppSetupConfig(font,@nppInput[0],13,130.0,72.0,32.0,0.9,0.5,0.2)
 NppCheck(NeonChromePanelConfigure(@nppStates[1],@nppTitles[19],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[1]),0)
 For j=0 To 0 : PokeA(@nppInput[0]+j,PeekA(?nppTitle2+j)) : Next
 NppSetupConfig(font,@nppInput[0],1,220.0,64.0,26.0,0.5,0.5,0.5)
 NppCheck(NeonChromePanelConfigure(@nppStates[2],@nppTitles[37],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[2]),0)
 For j=0 To 11 : PokeA(@nppInput[0]+j,PeekA(?nppTitle3+j)) : Next
 NppSetupConfig(font,@nppInput[0],12,300.0,60.0,0.0,0.8,0.6,0.2)
 NppCheck(NeonChromePanelConfigure(@nppStates[3],@nppTitles[55],128,@nppConfig),0)
 For j=0 To 127 : PokeA(@nppInput[0]+j,0) : Next
 NppCheck(NeonChromePanelSeal(@nppStates[3]),0)
 NppCheck(NeonServicePrepare(font,?nppReference0),0)
 NppCheck(NeonServicePrepare(font,?nppReference1),0)
 NppCheck(NeonServicePrepare(font,?nppReference3),0)
 NppCheck(NeonChromeStyleDefaults(@nppPalette),0)
 NppCheck(NeonChromeStylePaletteSet(@nppPalette),0)
 NppCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NppCheck(NeonServiceScissorSet(20.0,40.0,250.0,62.0),0)
 NppCheck(NeonChromePanelDraw(@nppStates[0]),0)
 NppCheck(NeonServiceFrameOpen(),1)
 NppCheck(NeonServiceBox(20.0,105.0,10.0,3.0,1.0,0.0,0.0,1.0),0)
 NppCheck(NeonServiceScissorClear(),0)
 NppCheck(NeonServiceScissorSet(340.0,40.0,250.0,62.0),0)
 NppCheck(NppRef(0,font),0)
 NppCheck(NeonServiceBox(340.0,105.0,10.0,3.0,1.0,0.0,0.0,1.0),0)
 NppCheck(NeonServiceScissorClear(),0)
 NppCustom()
 NppCheck(NeonChromeStylePaletteSet(@nppPalette),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[0]),1)
 NppCheck(NeonChromePanelDraw(@nppStates[1]),0)
 NppCheck(NppRef(1,font),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[1]),0)
 NppCheck(NeonChromePanelDraw(@nppStates[2]),0)
 NppCheck(NppRef(2,font),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[2]),0)
 NppCheck(NeonChromePanelDraw(@nppStates[3]),0)
 NppCheck(NppRef(3,font),0)
 NppCheck(NeonChromePanelNeedsRedraw(@nppStates[3]),0)
 NppCheck(NeonServiceFrameOpen(),1)
 NppCheck(NeonServiceEnd(),0)
 NppCheck(NeonServiceFrameOpen(),0)
 NppCheck(nppPreparedInside,0)
 PokeI(#NPP_REPORT+16,nppFailure) : PokeI(#NPP_REPORT+24,nppChecks)
 PokeI(#NPP_REPORT+32,nppPackets) : PokeI(#NPP_REPORT+40,nppPreparedInside)
 PokeI(#NPP_REPORT+48,font)
 For i=0 To 575 : PokeA(#NPP_REPORT+32768+i,PeekA(@nppTitles[0]+i)) : Next
 ProcedureReturn nppFailure
EndProcedure
DataSection
nppTitle0:
 Data.a 112,97,110,101,108,32,115,116,114,97,195,159,101,32,99,97,102,195,169,0
nppReference0:
 Data.a 80,65,78,69,76,32,83,84,82,65,83,83,69,32,67,65,70,195,137,0
nppTitle1:
 Data.a 99,117,115,116,111,109,32,112,97,110,101,108,0
nppReference1:
 Data.a 67,85,83,84,79,77,32,80,65,78,69,76,0
nppTitle2:
 Data.a 0
nppReference2:
 Data.a 0
nppTitle3:
 Data.a 122,101,114,111,32,104,101,105,103,104,116,0
nppReference3:
 Data.a 90,69,82,79,32,72,69,73,71,72,84,0
nppBad:
 Data.a 128,0
nppLong:
 Data.a 88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,88,0
EndDataSection
