; SPDX-License-Identifier: MIT
; Pixel snapping through actual native and retained Vulkan paths.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retained_ui.pbi"
#NFP_REPORT=$E1C00200
#NFP_PIXELS=$E2400000
#NFP_PIXEL_BYTES=368640
Global nfpChecks.i,nfpFailure.i
Global nfpSnap.NeonVkPortFontRef,nfpFree.NeonVkPortFontRef,nfpStale.NeonVkPortFontRef
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
 Protected i.i,j.i,row.i,part.i,src.i,dst.i,copied.i,poisoned.i,old.i
 Protected Dim clear.l[4]
 PokeI(#NFP_REPORT,$4E465031) : PokeI(#NFP_REPORT+8,2) : PokeI(#NFP_REPORT+32,6)
 NfpCheck(NeonVkPortCanvas(400,640,800,1280),0)
 NfpCheck(SizeOf(NeonVkPortFontRef),56)
 NfpCheck(NeonVkPortFontBind(@nfpSnap,0,1,12),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpSnap,16.0),0)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpSnap),1)
 NfpCheck(NeonVkPortFontBind(@nfpFree,0,1,12),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFree,16.0),0)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpFree),1)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFree,0),0)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpFree),0)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFree,-1),-21312)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFree,2),-21312)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFree,9223372036854775807),-21312)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpFree),0)
 NfpCheck(NeonVkPortFontSnapToPixel(0),-1)
 NfpCheck(NeonVkPortFontSetSnapToPixel(0,1),-21309)
 For i=0 To SizeOf(NeonVkPortFontRef)-1 : PokeA(@nfpStale+i,PeekA(@nfpFree+i)) : Next
 nfpStale\generation=nfpStale\generation+1
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpStale,1),-21310)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpStale),-1)
 nfpStale\generation=nfpFree\generation : nfpStale\snapToPixel=2
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpStale,1),-21309)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpStale),-1)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpSnap,?nfpText,1)),1119879168)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpFree,?nfpText,1)),1119879168)
 NfpCheck(NeonVkRetainedFontBytes(3),168)
 NfpCheck(NeonVkRetainedFontsConfigure(@nfpFonts[0],168,3),0)
 nfpRetained=NeonVkRetainedFontRegister(0,1,12)
 NfpCheck(Bool(nfpRetained>3),1)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(nfpRetained,16.0),0)
 NfpCheck(NeonVkRetainedFontSetSnapToPixel(nfpRetained,0),0)
 NfpCheck(NeonVkRetainedFontSetSnapToPixel(nfpRetained,2),-21312)
 NfpCheck(NeonVkRetainedFontSetSnapToPixel(1,0),-21309)
 NfpCheck(NeonVkRetainedInstall(),0)
 NfpCheck(NeonRetainedConfigure(@nfpArena[0],2048,2,128),0)
 NfpCheck(NeonRetainedViewport(0.0,0.0,400.0,640.0,400.0,640.0),0)
 NfpCheck(NeonRetainedFontSet(nfpRetained),0)
 old=NeonRetainedAddLabel(1,10.375,110.375,?nfpText)
 NfpCheck(Bool(old>0),1)
 NfpCheck(NeonVkPortFontWarm(@nfpSnap,?nfpText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpFree,?nfpText),0)
 NfpCheck(NeonRetainedUpdateInput(1000.0,1500.0,0,0,0,0,0),0)
 NfpCheck(NeonRetainedPrepare(),0)
 NfpCheck(NeonVkChromeRebind(framebuffer,800,1280,800,1280,pitch,0),0)
 clear[0]=$3D23D70A : clear[1]=$3D4CCCCD : clear[2]=$3D8F5C29 : clear[3]=$3F800000
 NfpCheck(NeonVkChromeBegin(@clear[0]),0)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpFree,1),-21311)
 NfpCheck(NeonVkRetainedFontSetSnapToPixel(nfpRetained,1),-21311)
 NfpCheck(NeonVkPortFontSnapToPixel(@nfpFree),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,10.375,20.375,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,200.0,20.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,216.0,20.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,232.0,20.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,248.0,20.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,264.0,20.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,280.0,20.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,10.375,50.375,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,200.375,50.375,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,216.375,50.375,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,232.375,50.375,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,248.375,50.375,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,264.375,50.375,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,280.375,50.375,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,10.0,80.0,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,200.0,80.0,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,216.0,80.0,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,232.0,80.0,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,248.0,80.0,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,264.0,80.0,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpSnap,280.0,80.0,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonRetainedDrawUI(0.0),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,200.375,110.375,?nfpChar0,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,216.375,110.375,?nfpChar1,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,232.375,110.375,?nfpChar2,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,248.375,110.375,?nfpChar3,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,264.375,110.375,?nfpChar4,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,280.375,110.375,?nfpChar5,1.0,0.8,0.2,1.0,1,1),0)
 NfpCheck(NeonVkPortFontTextRight(@nfpFree,106.375,140.375,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,200.375,140.375,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,216.375,140.375,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,232.375,140.375,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,248.375,140.375,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,264.375,140.375,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,280.375,140.375,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontTextCentre(@nfpFree,10.375,116.0,170.375,?nfpText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,210.375,170.375,?nfpChar0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,226.375,170.375,?nfpChar1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,242.375,170.375,?nfpChar2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,258.375,170.375,?nfpChar3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,274.375,170.375,?nfpChar4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFree,290.375,170.375,?nfpChar5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkChromeEnd(),0)
 NfpCheck(NeonVkChromeFrameRasterDelta(),0)
 NfpCheck(NeonVkChromeFrameUploadDelta(),0)
 NfpCheck(NeonVkChromeDrawCount(),43)
 NfpCheck(NeonVkChromeVertexCount(),450)
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
 Data.a 65,86,65,84,65,82,0
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
EndDataSection
