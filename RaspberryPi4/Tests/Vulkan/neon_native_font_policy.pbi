; SPDX-License-Identifier: MIT
; Actual font owner, native Vulkan adapter and retained font registry.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retained_ui.pbi"
#NFP_REPORT=$E1C00200
#NFP_PIXELS=$E2400000
#NFP_PIXEL_BYTES=368640
Global nfpChecks.i,nfpFailure.i
Global nfpProportional.NeonVkPortFontRef,nfpFixed.NeonVkPortFontRef,nfpFraction.NeonVkPortFontRef,nfpStale.NeonVkPortFontRef
Global nfpDerived.NeonVkPortFontRef,nfpDeriveStale.NeonVkPortFontRef
Global Dim nfpDeriveGuard.q[7]
Global Dim nfpFonts.q[21]
Global Dim nfpArena.q[256]
Global nfpRetained.i
Procedure NfpCheck(actual.i,expected.i)
 PokeI(#NFP_REPORT+512+nfpChecks*16,actual) : PokeI(#NFP_REPORT+520+nfpChecks*16,expected)
 nfpChecks=nfpChecks+1
 If actual<>expected And nfpFailure=0 : nfpFailure=nfpChecks : EndIf
 PokeI(#NFP_REPORT+16,nfpFailure) : PokeI(#NFP_REPORT+24,nfpChecks)
EndProcedure
Procedure.i NfpFrame(imageBase.i,pitch.i,framebuffer.i)
 Protected i.i,j.i,row.i,part.i,src.i,dst.i,copied.i,poisoned.i,width.f,old.i
 Protected Dim clear.l[4]
 PokeI(#NFP_REPORT,$4E465031) : PokeI(#NFP_REPORT+8,1) : PokeI(#NFP_REPORT+32,6)
 NfpCheck(NeonVkPortCanvas(800,1280,800,1280),0)
 NfpCheck(SizeOf(NeonVkPortFontRef),56)
 NfpCheck(NeonVkPortFontBind(@nfpProportional,0,1,20),0)
 NfpCheck(NeonVkPortFontBind(@nfpFixed,0,1,20),0)
 NfpCheck(NeonVkPortFontBind(@nfpFraction,0,1,20),0)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpProportional)),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,16.0),0)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpFixed)),1098907648)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,-1.0),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,MathFromBits($7FC00000)),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,MathFromBits($7F800000)),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,0.00000001),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,8193.0),-21312)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpFixed)),1098907648)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,8192.0),0)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpFixed)),1174405120)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,16.0),0)
 NfpCheck(NeonVkPortFontSetFixedAdvanceQ16(@nfpFixed,-1),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvanceQ16(@nfpFixed,536870913),-21312)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFraction,7.5),0)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpFraction)),1089470464)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpFraction,2),0)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFraction,0),0)
 NfpCheck(NeonVkPortFontDerive(@nfpDerived,@nfpFraction,2,24),0)
 NfpCheck(nfpDerived\slot-nfpFraction\slot,0)
 NfpCheck(nfpDerived\generation-nfpFraction\generation,0)
 NfpCheck(nfpDerived\face,2)
 NfpCheck(nfpDerived\pixelHeight,24)
 NfpCheck(nfpDerived\fixedAdvanceQ16,491520)
 NfpCheck(nfpDerived\snapToPixel,0)
 NfpCheck(nfpDerived\controlMode,2)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFraction,7.0),0)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpFraction,1),0)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFraction,1),0)
 NfpCheck(nfpDerived\fixedAdvanceQ16,491520)
 NfpCheck(nfpDerived\controlMode,2)
 NfpCheck(nfpDerived\snapToPixel,0)
 For i=0 To 6 : nfpDeriveGuard[i]=$A5A5A5A5A5A5A5A5 : Next
 For i=0 To SizeOf(NeonVkPortFontRef)-1 : PokeA(@nfpDeriveStale+i,PeekA(@nfpFraction+i)) : Next
 nfpDeriveStale\generation=nfpDeriveStale\generation+1
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],@nfpDeriveStale,1,20),-21310)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],@nfpFraction,4,20),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],@nfpFraction,1,0),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],@nfpFraction,1,513),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],0,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0],$7FFFFFFFFFFFFFE0,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpDeriveGuard[0]+1,@nfpFraction,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive(0,@nfpFraction,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive($7FFFFFFFFFFFFFE0,@nfpFraction,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpFraction,@nfpFraction,1,20),-21309)
 NfpCheck(NeonVkPortFontDerive(@nfpFraction+8,@nfpFraction,1,20),-21309)
 NfpCheck(nfpDeriveGuard[0],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[1],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[2],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[3],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[4],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[5],-6510615555426900571)
 NfpCheck(nfpDeriveGuard[6],-6510615555426900571)
 NfpCheck(nfpFraction\pixelHeight,20)
 NfpCheck(nfpFraction\face,1)
 NfpCheck(nfpFraction\fixedAdvanceQ16,458752)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFraction,7.5),0)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpFraction,0),0)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpFixed,?nfpText,1)),1127219200)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpFraction,?nfpText,1)),1118109696)
 width=NeonVkPortFontTextWidth(@nfpProportional,?nfpText,1) : PokeL(#NFP_REPORT+128,MathBitsOf(width))
 NfpCheck(Bool(width>0.0),1)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,0.0),0)
 PokeL(#NFP_REPORT+132,MathBitsOf(NeonVkPortFontTextWidth(@nfpFixed,?nfpText,1)))
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,16.0),0)
 For i=0 To SizeOf(NeonVkPortFontRef)-1 : PokeA(@nfpStale+i,PeekA(@nfpFixed+i)) : Next
 nfpStale\generation=nfpStale\generation+1
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpStale,16.0),-21310)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpStale)),3212836864)
 NfpCheck(NeonVkRetainedFontBytes(3),168)
 NfpCheck(NeonVkRetainedFontsConfigure(@nfpFonts[0],168,3),0)
 nfpRetained=NeonVkRetainedFontRegister(0,1,20)
 NfpCheck(Bool(nfpRetained>3),1)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(nfpRetained,12.5),0)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(nfpRetained,-1.0),-21312)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(1,12.5),-21309)
 NfpCheck(MathBitsOf(NeonVkRetainedFontTextWidth(nfpRetained,?nfpText)),1124696064)
 NfpCheck(NeonVkRetainedInstall(),0)
 NfpCheck(NeonRetainedConfigure(@nfpArena[0],2048,2,128),0)
 NfpCheck(NeonRetainedViewport(0.0,0.0,800.0,1280.0,800.0,1280.0),0)
 NfpCheck(NeonRetainedFontSet(nfpRetained),0)
 old=NeonRetainedAddLabel(1,20.0,220.0,?nfpText)
 NfpCheck(Bool(old>0),1)
 NfpCheck(NeonVkPortFontWarm(@nfpProportional,?nfpText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpFixed,?nfpText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpFraction,?nfpText),0)
 NfpCheck(NeonRetainedUpdateInput(1000.0,1500.0,0,0,0,0,0),0)
 NfpCheck(NeonRetainedPrepare(),0)
 NfpCheck(NeonVkChromeRebind(framebuffer,800,1280,800,1280,pitch,0),0)
 clear[0]=$3D23D70A : clear[1]=$3D4CCCCD : clear[2]=$3D8F5C29 : clear[3]=$3F800000
 NfpCheck(NeonVkChromeBegin(@clear[0]),0)
 NfpCheck(NeonVkPortFontDerive(@nfpDerived,@nfpFraction,1,20),-21311)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFixed,20.0),-21311)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(nfpRetained,15.0),-21311)
 NfpCheck(MathBitsOf(NeonVkPortFontFixedAdvance(@nfpFixed)),1098907648)
 NfpCheck(NeonVkPortFontText(@nfpProportional,20.0,40.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortText(1,400.0,40.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFixed,20.0,100.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,400.0,100.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,416.0,100.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,432.0,100.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,448.0,100.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,464.0,100.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,480.0,100.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,496.0,100.0,?nfpChar6,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,512.0,100.0,?nfpChar7,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,528.0,100.0,?nfpChar8,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,544.0,100.0,?nfpChar9,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,560.0,100.0,?nfpChar10,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFraction,20.25,160.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,400.25,160.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,407.75,160.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,415.25,160.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,422.75,160.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,430.25,160.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,437.75,160.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,445.25,160.0,?nfpChar6,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,452.75,160.0,?nfpChar7,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,460.25,160.0,?nfpChar8,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,467.75,160.0,?nfpChar9,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,475.25,160.0,?nfpChar10,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonRetainedDrawUI(0.0),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,400.0,220.0,?nfpChar0,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,412.5,220.0,?nfpChar1,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,425.0,220.0,?nfpChar2,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,437.5,220.0,?nfpChar3,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,450.0,220.0,?nfpChar4,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,462.5,220.0,?nfpChar5,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,475.0,220.0,?nfpChar6,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,487.5,220.0,?nfpChar7,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,500.0,220.0,?nfpChar8,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,512.5,220.0,?nfpChar9,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,525.0,220.0,?nfpChar10,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontTextRight(@nfpFixed,240.0,280.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,444.0,280.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,460.0,280.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,476.0,280.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,492.0,280.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,508.0,280.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,524.0,280.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,540.0,280.0,?nfpChar6,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,556.0,280.0,?nfpChar7,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,572.0,280.0,?nfpChar8,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,588.0,280.0,?nfpChar9,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,604.0,280.0,?nfpChar10,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontTextCentre(@nfpFixed,20.0,220.0,340.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,422.0,340.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,438.0,340.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,454.0,340.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,470.0,340.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,486.0,340.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,502.0,340.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,518.0,340.0,?nfpChar6,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,534.0,340.0,?nfpChar7,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,550.0,340.0,?nfpChar8,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,566.0,340.0,?nfpChar9,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProportional,582.0,340.0,?nfpChar10,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkChromeEnd(),0)
 NfpCheck(NeonVkChromeFrameRasterDelta(),0)
 NfpCheck(NeonVkChromeFrameUploadDelta(),0)
 ; Retained DrawUI always submits its16-side pointer, even off-screen.
 ; Public fan path records centre+16rim+closure=18 input vertices in one draw.
 NfpCheck(NeonVkChromeDrawCount(),58)
 NfpCheck(NeonVkChromeVertexCount(),738)
 NfpCheck(NeonVkChromePresentConsume(),1)
 For i=0 To #NFP_PIXEL_BYTES+24 Step 8 : PokeI(#NFP_PIXELS+i,$A5A5A5A5A5A5A5A5) : poisoned=poisoned+8 : Next
 For row=0 To 5
  For part=0 To 1
   src=imageBase+(40+row*60)*pitch+(20+part*380)*4
   dst=#NFP_PIXELS+16+(row*2+part)*30720
   For i=0 To 31
    For j=0 To 952 Step 8
     PokeI(dst+i*960+j,PeekI(src+i*pitch+j)) : copied=copied+8
    Next
   Next
  Next
 Next
 PokeI(#NFP_REPORT+40,copied) : PokeI(#NFP_REPORT+48,poisoned)
 PokeI(#NFP_REPORT+112,NeonVkChromeDrawCount()) : PokeI(#NFP_REPORT+120,NeonVkChromeVertexCount())
 ProcedureReturn nfpFailure
EndProcedure
Procedure NfpRetired(report.i)
 Protected count.l=12345,rc.i
 PokeI(#NFP_REPORT+80,AnvilVkFaultCount())
 NfpCheck(NeonVkChromeReady(),0)
 NfpCheck(NeonDrawBackendActive(),0)
 NfpCheck(Neon_Ready(),0)
 rc=vkDeviceWaitIdle(PeekL(report+24))
 NfpCheck(rc,-20002)
 rc=vkEnumeratePhysicalDevices(PeekL(report+16),@count,0)
 NfpCheck(rc,-20002)
 NfpCheck(count,12345)
 PokeI(#NFP_REPORT+88,AnvilVkFaultCount())
EndProcedure
DataSection
nfpText:
 Data.a 65,86,65,84,65,82,32,99,97,102,195,169,0
nfpChar0:
 Data.a 65,0
nfpChar1:
 Data.a 86,0
nfpChar2:
 Data.a 65,0
nfpChar3:
 Data.a 84,0
nfpChar4:
 Data.a 65,0
nfpChar5:
 Data.a 82,0
nfpChar6:
 Data.a 32,0
nfpChar7:
 Data.a 99,0
nfpChar8:
 Data.a 97,0
nfpChar9:
 Data.a 102,0
nfpChar10:
 Data.a 195,169,0
EndDataSection
