; Controlled fence responses around the exact production Async/Pending/Finish
; procedures inserted by build_neon_async_wait_proof.py. No GPU code is linked.
Global acfRecords.i,acfFailures.i,acfWaits.i,acfPublishes.i,acfWaitRc.i,acfPublishRc.i
Global acfDevice.i,acfFence.i,acfCount.i,acfAll.i,acfTimeout.i
Global nvcAsync.i,nvcInFrame.i,nvcFramePending.i,nvcSubmitStage.i,nvcSubmitRc.i
Global nvcDevice.i,nvcFence.i,nvcError.i

Procedure.i AcfFenceWait(device.i,count.i,*fences,all.i,timeout.i)
 acfWaits=acfWaits+1 : acfDevice=device : acfCount=count
 acfFence=PeekI(*fences) : acfAll=all : acfTimeout=timeout
 ProcedureReturn acfWaitRc
EndProcedure
Procedure.i AcfPublish()
 acfPublishes=acfPublishes+1
 ProcedureReturn acfPublishRc
EndProcedure

; @ACF_PRODUCTION_PROCEDURES@

Procedure AcfCheck(tag.i,value.i,wanted.i)
 PokeI(#ACF_REPORT+64+acfRecords*16,tag)
 PokeI(#ACF_REPORT+72+acfRecords*16,value)
 acfRecords=acfRecords+1
 If value<>wanted : acfFailures=acfFailures+1 : EndIf
EndProcedure

Procedure.i AsyncWaitProof()
 Define rc.i
 ; No pending frame must never touch a fence or publish.
 nvcDevice=$1234 : nvcFence=$5678 : nvcAsync=1
 rc=NeonVkChromeFinish()
 AcfCheck(100,rc,0) : AcfCheck(101,acfWaits,0) : AcfCheck(102,acfPublishes,0)
 ; Timeout, a repeated timeout, and device loss all retain the same frame.
 nvcFramePending=1 : acfWaitRc=2
 rc=NeonVkChromeFinish()
 AcfCheck(110,rc,2) : AcfCheck(111,NeonVkChromeFramePending(),1)
 AcfCheck(112,acfWaits,1) : AcfCheck(113,acfPublishes,0)
 AcfCheck(114,nvcSubmitStage,4) : AcfCheck(115,nvcSubmitRc,2) : AcfCheck(116,nvcError,2)
 AcfCheck(117,acfDevice,$1234) : AcfCheck(118,acfFence,$5678) : AcfCheck(119,acfCount,1)
 AcfCheck(120,acfAll,1) : AcfCheck(121,acfTimeout,#NEON_VK_CHROME_WAIT_NS)
 rc=NeonVkChromeAsync(0)
 AcfCheck(122,rc,#NEON_VK_CHROME_ERR_STATE) : AcfCheck(123,nvcAsync,1)
 rc=NeonVkChromeFinish()
 AcfCheck(130,rc,2) : AcfCheck(131,NeonVkChromeFramePending(),1)
 AcfCheck(132,acfWaits,2) : AcfCheck(133,acfPublishes,0)
 acfWaitRc=-4 : rc=NeonVkChromeFinish()
 AcfCheck(140,rc,-4) : AcfCheck(141,NeonVkChromeFramePending(),1)
 AcfCheck(142,acfWaits,3) : AcfCheck(143,acfPublishes,0)
 AcfCheck(144,nvcSubmitRc,-4) : AcfCheck(145,nvcError,-4)
 ; Only successful completion releases pending and publishes, exactly once.
 acfWaitRc=0 : rc=NeonVkChromeFinish()
 AcfCheck(150,rc,0) : AcfCheck(151,NeonVkChromeFramePending(),0)
 AcfCheck(152,acfWaits,4) : AcfCheck(153,acfPublishes,1) : AcfCheck(154,nvcSubmitRc,0)
 rc=NeonVkChromeFinish()
 AcfCheck(160,rc,0) : AcfCheck(161,acfWaits,4) : AcfCheck(162,acfPublishes,1)
 rc=NeonVkChromeAsync(0)
 AcfCheck(163,rc,0) : AcfCheck(164,nvcAsync,0)
 ; A publication refusal occurs after GPU completion and must not re-wait or
 ; publish twice on the next Finish. It is distinct from a failed fence wait.
 nvcFramePending=1 : acfPublishRc=-21301
 rc=NeonVkChromeFinish()
 AcfCheck(170,rc,-21301) : AcfCheck(171,NeonVkChromeFramePending(),0)
 AcfCheck(172,acfWaits,5) : AcfCheck(173,acfPublishes,2)
 rc=NeonVkChromeFinish()
 AcfCheck(174,rc,0) : AcfCheck(175,acfWaits,5) : AcfCheck(176,acfPublishes,2)
 ; Recording frame also refuses Async mode change independently of pending.
 nvcInFrame=1 : rc=NeonVkChromeAsync(1)
 AcfCheck(180,rc,#NEON_VK_CHROME_ERR_STATE) : AcfCheck(181,nvcAsync,0)
 nvcInFrame=0 : rc=NeonVkChromeAsync(1)
 AcfCheck(182,rc,0) : AcfCheck(183,nvcAsync,1)
 ProcedureReturn acfFailures
EndProcedure
