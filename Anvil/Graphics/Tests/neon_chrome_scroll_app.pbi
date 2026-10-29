; SPDX-License-Identifier: MIT
; Pure returning state and resident GPU scrollbar application.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_chrome_scroll.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_chrome_scroll.pbi"
Global nsaState.NeonChromeScrollState,nsaUnset.NeonChromeScrollState
Global nsaChecks.i,nsaFailure.i,nsaCalls.i,nsaFailAt.i,nsaPositive.i,nsaReenter.i,nsaReentered.i,nsaCapture.i,nsaRecorded.i,nsaOtherBusy.i,nsaInstallBusy.i
Procedure NsaCheck(actual.i,expected.i)
  nsaChecks=nsaChecks+1
  PokeI(#NSA_REPORT+256+nsaChecks*16,actual) : PokeI(#NSA_REPORT+264+nsaChecks*16,expected)
  If actual<>expected And nsaFailure=0 : nsaFailure=nsaChecks : EndIf
  PokeI(#NSA_REPORT+16,nsaFailure) : PokeI(#NSA_REPORT+24,nsaChecks)
EndProcedure
Procedure.i NsaBox(x.f,y.f,w.f,h.f,r.f,g.f,b.f,a.f)
  Protected p.i
  nsaCalls=nsaCalls+1
  If nsaCapture<>0
    p=#NSA_REPORT+3072+nsaRecorded*32
    PokeL(p,MathBitsOf(x)) : PokeL(p+4,MathBitsOf(y)) : PokeL(p+8,MathBitsOf(w)) : PokeL(p+12,MathBitsOf(h))
    PokeL(p+16,MathBitsOf(r)) : PokeL(p+20,MathBitsOf(g)) : PokeL(p+24,MathBitsOf(b)) : PokeL(p+28,MathBitsOf(a))
    nsaRecorded=nsaRecorded+1
  EndIf
  If nsaReenter<>0
    nsaReentered=NeonChromeScrollInput(@nsaState,0.0,0.0,0)
    nsaOtherBusy=NeonChromeScrollConfigure(@nsaUnset,1.0)
    nsaInstallBusy=NeonChromeScrollRendererInstall(0)
  EndIf
  If nsaCalls=nsaFailAt : ProcedureReturn -21777 : EndIf
  ProcedureReturn nsaPositive
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,top.i,left.i,inert.i,before.i
  For i=0 To 4095 Step 8 : PokeI(#NSA_REPORT+i,0) : Next
  PokeI(#NSA_REPORT,$4E534131) : PokeI(#NSA_REPORT+8,1)
  NsaCheck(SizeOf(NeonChromeScrollState),80)
  NsaCheck(NeonChromeScrollRendererInstall(@NsaBox),0)
  NsaCheck(NeonChromeScrollInput(@nsaUnset,0.0,0.0,0),#NCS_ERR_STATE)
  NsaCheck(NeonChromeScrollConfigure(@nsaState,0.0),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollConfigure(@nsaState,1.0),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),#NCS_ERR_STATE)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,130.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),0)
  NsaCheck(NeonChromeScrollDragOwner(@nsaState),7)
  inert=5
  NsaCheck(NeonChromeScrollBarV(@nsaState,8,500.0,100.0,20.0,200.0,10,20,@inert),0)
  NsaCheck(inert,0) : NsaCheck(NeonChromeScrollDragOwner(@nsaState),7)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,210.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,40)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,900.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,80)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,-100.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,0)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,-100.0,0),0)
  NsaCheck(NeonChromeScrollDragOwner(@nsaState),0)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,280.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,20)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,280.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),0) : NsaCheck(top,20)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,110.0,0),0)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,110.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,0)
  NsaCheck(NeonChromeScrollInput(@nsaState,-100.0,-100.0,0),0)
  left=999
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,100.0,100.0,200.0,20.0,100,20,@left),1) : NsaCheck(left,80)
  left=-3
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,100.0,100.0,200.0,20.0,100,20,@left),1) : NsaCheck(left,0)
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,110.0,1),0)
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,100.0,100.0,200.0,20.0,100,20,@left),0)
  NsaCheck(NeonChromeScrollDragOwner(@nsaState),9)
  NsaCheck(NeonChromeScrollInput(@nsaState,190.0,110.0,1),0)
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,100.0,100.0,200.0,20.0,100,20,@left),1) : NsaCheck(left,40)
  NsaCheck(NeonChromeScrollBarH(@nsaState,10,500.0,100.0,200.0,20.0,10,20,@inert),0)
  NsaCheck(NeonChromeScrollDragOwner(@nsaState),9)
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,100.0,100.0,200.0,20.0,10,20,@left),0)
  NsaCheck(NeonChromeScrollDragOwner(@nsaState),0) : NsaCheck(left,0)
  NsaCheck(NeonChromeScrollInput(@nsaState,-100.0,-100.0,0),0)
  top=50
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,10.0,10.0,100,20,@top),0) : NsaCheck(top,50)
  NsaCheck(NeonChromeScrollBarV(@nsaState,0,100.0,100.0,20.0,200.0,100,20,@top),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,-1,20,@top),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,2147483648,20,@top),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,0),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@nsaState),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollInput(@nsaState,MathFromBits($7FC00001),0.0,1),#NCS_ERR_ARGS)
  NsaCheck(NeonChromeScrollInput(@nsaState,MathFromBits($7F800000),0.0,1),#NCS_ERR_ARGS)
  top=10 : nsaFailAt=nsaCalls+2
  NsaCheck(NeonChromeScrollInput(@nsaState,110.0,280.0,1),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),-21777)
  NsaCheck(top,10) : NsaCheck(NeonChromeScrollDragOwner(@nsaState),0)
  NsaCheck(NeonChromeScrollError(@nsaState),-21777)
  nsaFailAt=0
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),1) : NsaCheck(top,30)
  nsaPositive=1
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),#NCS_ERR_RENDERER) : NsaCheck(top,30)
  nsaPositive=0 : nsaReenter=1
  NsaCheck(NeonChromeScrollInput(@nsaState,-100.0,-100.0,0),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,7,100.0,100.0,20.0,200.0,100,20,@top),0)
  NsaCheck(nsaReentered,#NCS_ERR_BUSY) : NsaCheck(NeonChromeScrollError(@nsaState),0)
  NsaCheck(nsaOtherBusy,#NCS_ERR_BUSY) : NsaCheck(nsaInstallBusy,#NCS_ERR_BUSY)
  nsaReenter=0 : nsaCapture=1 : left=40
  NsaCheck(NeonChromeScrollBarH(@nsaState,9,500.0,100.0,200.0,20.0,100,20,@left),0)
  nsaCapture=0 : NsaCheck(nsaRecorded,2)
  PokeI(#NSA_REPORT+32,nsaRecorded)
  NsaCheck(NeonServiceBind(services,33),0) : NsaCheck(NeonServiceOpen(),0)
  NsaCheck(NeonServiceCanvas(640,400),0)
  NsaCheck(NeonServiceChromeScrollInstall(@nsaState,1.0),0)
  NsaCheck(NeonChromeScrollInput(@nsaState,-100.0,-100.0,0),0)
  top=40 : left=50 : inert=17
  NsaCheck(NeonServiceBegin(0.0,0.0,0.0,1.0),0)
  NsaCheck(NeonServiceScissorSet(50.0,60.0,10.0,160.0),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,1,50.0,50.0,10.0,200.0,100,20,@top),0)
  NsaCheck(NeonServiceScissorClear(),0)
  NsaCheck(NeonChromeScrollBarH(@nsaState,2,100.0,300.0,200.0,10.0,100,25,@left),0)
  NsaCheck(NeonChromeScrollBarV(@nsaState,3,400.0,50.0,20.0,200.0,10,20,@inert),0)
  NsaCheck(inert,0)
  top=50
  NsaCheck(NeonChromeScrollBarV(@nsaState,4,500.0,300.0,10.0,10.0,100,20,@top),0)
  NsaCheck(NeonServiceEnd(),0)
  ProcedureReturn nsaFailure
EndProcedure
