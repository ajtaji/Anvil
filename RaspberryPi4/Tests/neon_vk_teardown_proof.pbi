; Exact production teardown/callback bodies with controlled Vulkan providers.
; Generated state reset seeds independent cases; it is not runtime recovery.
Global acdRecords.i,acdFailures.i,acdIdleCalls.i,acdFirstRc.i,acdLaterRc.i
Global acdReleases.i,acdPresentClears.i,acdDrawClears.i,acdBannerReleases.i
Global acdRollbackCalls.i,acdRollbackRc.i,acdUnmaps.i

; @ACD_CONTROLLED_COMPOSITION@

Procedure AcdObserve(tag.i,rc.i,*want)
 Define i.i
 Dim seen.i[20]
 seen[0]=rc : seen[1]=nvcDevice : seen[2]=nvcCommand : seen[3]=nvcFramePending
 seen[4]=nvcReady : seen[5]=nvcHooksInstalled : seen[6]=nvlConfigured
 seen[7]=acdIdleCalls : seen[8]=acdRollbackCalls : seen[9]=Bool(acdReleases>0)
 seen[10]=acdPresentClears : seen[11]=acdDrawClears
 seen[12]=nvcMapped : seen[13]=acdUnmaps
 seen[14]=avcDevice : seen[15]=avcPool : seen[16]=avcFramebuffer
 seen[17]=avcReady : seen[18]=avcDeviceUnsafe : seen[19]=acdBannerReleases
 For i=0 To 19
  PokeI(#ACD_REPORT+64+acdRecords*16,tag+i)
  PokeI(#ACD_REPORT+72+acdRecords*16,seen[i])
  acdRecords=acdRecords+1
  If seen[i]<>PeekI(*want+i*8) : acdFailures=acdFailures+1 : EndIf
 Next
EndProcedure

Procedure.i TeardownProof()
 Define rc.i
 ; Expected rows are supplied independently by the builder's explicit case
 ; contract, also consumed by the separate host report oracle.
 AcdReset() : nvcExternalProducerAttached=1
 rc=NeonVkChromeDestroyChecked() : AcdObserve(100,rc,?acdWant1)
 AcdReset() : nvcExternalProducerQuarantined=1
 rc=NeonVkChromeDestroyChecked() : AcdObserve(200,rc,?acdWant2)
 AcdReset() : acdFirstRc=2 : acdLaterRc=-4
 rc=NeonVkChromeDestroyChecked() : AcdObserve(300,rc,?acdWant3)
 rc=NeonVkChromeDestroyChecked() : AcdObserve(400,rc,?acdWant4)
 acdLaterRc=0
 rc=NeonVkChromeDestroyChecked() : AcdObserve(500,rc,?acdWant5)
 AcdReset() : NeonVkChromeDestroy() : AcdObserve(600,0,?acdWant6)
 AcdReset() : acdFirstRc=2
 rc=nvlShutdown() : AcdObserve(700,rc,?acdWant7)
 rc=nvlShutdown() : AcdObserve(800,rc,?acdWant8)
 AcdReset() : nvcInFrame=1
 rc=nvcLifecycleShutdown() : AcdObserve(900,rc,?acdWant9)
 AcdReset() : acdFirstRc=2
 rc=nvcLifecycleShutdown() : AcdObserve(1000,rc,?acdWant10)
 AcdReset()
 rc=nvcLifecycleShutdown() : AcdObserve(1100,rc,?acdWant11)
 AcdReset() : acdFirstRc=2
 rc=VulkanConsoleDestroy() : AcdObserve(1200,rc,?acdWant12)
 AcdReset() : acdLaterRc=2
 rc=VulkanConsoleDestroy() : AcdObserve(1300,rc,?acdWant13)
 AcdReset()
 rc=VulkanConsoleDestroy() : AcdObserve(1400,rc,?acdWant14)
 ; A completed device does not permit release when WSI rollback refuses.
 AcdReset() : acdRollbackRc=-20004
 rc=NeonVkChromeDestroyChecked() : AcdObserve(1500,rc,?acdWant15)
 acdRollbackRc=0
 rc=NeonVkChromeDestroyChecked() : AcdObserve(1600,rc,?acdWant16)
 ; A separate, unsubmitted mapped frame preserves its mapping on idle refusal.
 AcdReset() : nvcFramePending=0 : nvcMapped=301 : nvcInFrame=1 : acdFirstRc=2
 rc=NeonVkChromeDestroyChecked() : AcdObserve(1700,rc,?acdWant17)
 rc=NeonVkChromeDestroyChecked() : AcdObserve(1800,rc,?acdWant18)
 ProcedureReturn acdFailures
EndProcedure
