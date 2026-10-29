; Controlled present/WSI providers; builder inserts exact production guards.
; This proof does not submit GPU work or claim a hardware timeout.
Global nvcReady.i,nvcInFrame.i,nvcFramePending.i,nvcFrameAbortable.i
Global nvcExternalProducerQuarantined.i,nvcError.i
Global nvcFramebuffer.i,nvcLogicalW.i,nvcLogicalH.i,nvcPhysicalW.i,nvcPhysicalH.i
Global nvcPitch.i,nvcRotation.i,nvcWidth.i,nvcHeight.i
Global nvcTargetGeneration.i,nvcNextTargetGeneration.i
Global tofPresent.i,tofWsi.i,tofCalls.i,tofDevice.i,tofSwapchain.i,tofIndex.i,tofTarget.i
Global tofRecords.i,tofFailures.i
Global nvcDevice.i,nvcRenderPass.i
Global tofTargetRc.i,tofTargetCalls.i,tofTargetDevice.i,tofTargetPass.i
Global tofTargetFb.i,tofTargetW.i,tofTargetH.i,tofTargetPitch.i

Procedure.i TofPresentPending()
 ProcedureReturn tofPresent
EndProcedure
Procedure.i TofWsiEnabled()
 ProcedureReturn tofWsi
EndProcedure
Procedure.i TofAttach(device.i,swapchain.i,imageIndex.i,target.i)
 tofCalls=tofCalls+1 : tofDevice=device : tofSwapchain=swapchain
 tofIndex=imageIndex : tofTarget=target
 ProcedureReturn 23
EndProcedure

Procedure.i TofTargetCheck(device.i,renderPass.i,framebuffer.i,width.i,height.i,pitch.i)
 tofTargetCalls=tofTargetCalls+1
 tofTargetDevice=device : tofTargetPass=renderPass : tofTargetFb=framebuffer
 tofTargetW=width : tofTargetH=height : tofTargetPitch=pitch
 ProcedureReturn tofTargetRc
EndProcedure

; @TOF_PRODUCTION_PROCEDURES@

Procedure TofCheck(tag.i,value.i,wanted.i)
 PokeI(#TOF_REPORT+64+tofRecords*16,tag)
 PokeI(#TOF_REPORT+72+tofRecords*16,value)
 tofRecords=tofRecords+1
 If value<>wanted : tofFailures=tofFailures+1 : EndIf
EndProcedure

Procedure TofReset(kind.i)
 nvcReady=1 : nvcInFrame=0 : nvcFramePending=0 : nvcFrameAbortable=0
 nvcExternalProducerQuarantined=0 : tofPresent=0 : tofWsi=0 : tofCalls=0
 tofDevice=0 : tofSwapchain=0 : tofIndex=0 : tofTarget=0
 nvcFramebuffer=111 : nvcLogicalW=64 : nvcLogicalH=32
 nvcPhysicalW=64 : nvcPhysicalH=32 : nvcPitch=256 : nvcRotation=0
 nvcWidth=64 : nvcHeight=32 : nvcTargetGeneration=41 : nvcNextTargetGeneration=41
 nvcError=99
 nvcDevice=1001 : nvcRenderPass=1002 : tofTargetRc=0 : tofTargetCalls=0
 tofTargetDevice=0 : tofTargetPass=0 : tofTargetFb=0
 tofTargetW=0 : tofTargetH=0 : tofTargetPitch=0
 Select kind
  Case 1 : nvcReady=0
  Case 2 : nvcInFrame=1
  Case 3 : nvcFramePending=1
  Case 4 : nvcFrameAbortable=1
  Case 5 : nvcExternalProducerQuarantined=1
  Case 6 : tofPresent=1
  Case 7 : tofWsi=1
 EndSelect
EndProcedure

Procedure TofSnapshot(tag.i,changed.i)
 If changed=0
  TofCheck(tag,nvcFramebuffer,111)
  TofCheck(tag+1,nvcLogicalW,64) : TofCheck(tag+2,nvcLogicalH,32)
  TofCheck(tag+3,nvcPhysicalW,64) : TofCheck(tag+4,nvcPhysicalH,32)
  TofCheck(tag+5,nvcPitch,256) : TofCheck(tag+6,nvcRotation,0)
  TofCheck(tag+7,nvcWidth,64) : TofCheck(tag+8,nvcHeight,32)
  TofCheck(tag+9,nvcTargetGeneration,41) : TofCheck(tag+10,nvcNextTargetGeneration,41)
 Else
  TofCheck(tag,nvcFramebuffer,222)
  TofCheck(tag+1,nvcLogicalW,96) : TofCheck(tag+2,nvcLogicalH,48)
  TofCheck(tag+3,nvcPhysicalW,48) : TofCheck(tag+4,nvcPhysicalH,96)
  TofCheck(tag+5,nvcPitch,192) : TofCheck(tag+6,nvcRotation,90)
  TofCheck(tag+7,nvcWidth,96) : TofCheck(tag+8,nvcHeight,48)
  TofCheck(tag+9,nvcTargetGeneration,42) : TofCheck(tag+10,nvcNextTargetGeneration,42)
 EndIf
EndProcedure

Procedure.i TargetOwnershipProof()
 Define kind.i,tag.i,rc.i
 ; Each busy state independently refuses with every target field retained.
 For kind=1 To 7
  TofReset(kind) : tag=100+kind*20
  rc=NeonVkChromeRebind(222,96,48,48,96,192,90)
  TofCheck(tag,rc,#NEON_VK_CHROME_ERR_STATE)
  TofSnapshot(tag+1,0)
  TofCheck(tag+12,nvcError,#NEON_VK_CHROME_ERR_STATE)
  TofCheck(tag+13,tofCalls,0)
 Next
 ; Quiescent retry publishes all target fields once, including generation.
 TofReset(0) : rc=NeonVkChromeRebind(222,96,48,48,96,192,90)
 TofCheck(260,rc,0) : TofSnapshot(261,1)
 TofCheck(272,nvcError,0) : TofCheck(273,tofCalls,0)
 TofCheck(274,tofTargetCalls,1) : TofCheck(275,tofTargetDevice,1001)
 TofCheck(276,tofTargetPass,1002) : TofCheck(277,tofTargetFb,222)
 TofCheck(278,tofTargetW,48) : TofCheck(279,tofTargetH,96) : TofCheck(280,tofTargetPitch,192)
 ; A target-owner refusal precedes publication of every adapter field.
 TofReset(0) : tofTargetRc=-20004
 rc=NeonVkChromeRebind(222,96,48,48,96,192,90)
 TofCheck(290,rc,-20004) : TofSnapshot(291,0)
 TofCheck(302,nvcError,-20004) : TofCheck(303,tofTargetCalls,1)

 ; Attachment must not call its provider during an open/submitted/abortable
 ; frame. Its legacy refusal leaves the frontend error unchanged.
 For kind=1 To 6
  TofReset(kind) : tag=300+kind*20
  rc=NeonVkChromeWsiAttach(11,22,3)
  TofCheck(tag,rc,#NEON_VK_CHROME_ERR_STATE)
  TofSnapshot(tag+1,0)
  TofCheck(tag+12,nvcError,99) : TofCheck(tag+13,tofCalls,0)
 Next
 TofReset(0) : rc=NeonVkChromeWsiAttach(11,22,3)
 TofCheck(440,rc,23) : TofSnapshot(441,0)
 TofCheck(452,nvcError,99) : TofCheck(453,tofCalls,1)
 TofCheck(454,tofDevice,11) : TofCheck(455,tofSwapchain,22)
 TofCheck(456,tofIndex,3) : TofCheck(457,tofTarget,41)
 ProcedureReturn tofFailures
EndProcedure
