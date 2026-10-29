; SPDX-License-Identifier: MIT
; Parent draw, independent child draw, preserving parent continuation.
Procedure NalContinuationPixels(*c.NeonVkCanvas,id.i)
  Protected mapped.i,x.i,y.i,wanted.i,bad.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(id,rc,0)
  If rc<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      wanted=$FF000000
      If x>=20 And x<40 And y>=18 And y<38 : wanted=$FFFF0000 : EndIf
      If x>=50 And x<70 And y>=28 And y<48 : wanted=$FF0000FF : EndIf
      If PeekN(mapped+y* *c\pitch+x*4)<>wanted : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(id+1,bad,0)
EndProcedure
Procedure NalContinuationCase(*c.NeonVkCanvas,*child.NeonVkCanvas,*primary.NeonVkCanvas)
  Protected original.NeonVkTargetInfo,seq.i
  Protected Dim clear.l[4]
  clear[3]=$3F800000
  NalCheck(600,NeonVkCanvasResizeBlank(*c,194,128),0)
  NalCheck(601,NeonVkChromeTargetSnapshot(@original,SizeOf(NeonVkTargetInfo)),0)
  If NalFailure<>0 : ProcedureReturn : EndIf
  NalCheck(602,NeonVkChromeRebind(*c\framebuffer,194,128,194,128,*c\pitch,0),0)
  NalCheck(603,NeonVkChromeResume(),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(604,NeonVkChromeBegin(@clear[0]),0)
  NalCheck(605,NeonVkChromeViewportSet(10,8,97,64),0)
  NeonVkChromeScissorSet(0,0,194,128)
  NalCheck(606,NeonVkChromeBox(20,20,40,40,$FFFF0000),0)
  seq=nvcNextFrameSequence
  NalCheck(607,NeonVkChromeSuspend(),0)
  NalCheck(608,nvcNextFrameSequence-seq,0)
  NalCheck(609,NeonVkChromePresentPending(),0)
  NalCheck(610,NeonVkChromeSuspended(),1)
  NalCheck(611,NeonVkChromeBegin(@clear[0]),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(612,NeonVkChromeSuspend(),#NEON_VK_CHROME_ERR_STATE)
  If NalFailure<>0 : Goto NalContinuationDone : EndIf
  NalCheck(613,NeonVkChromeRebind(*child\framebuffer,*child\width,*child\height,*child\width,*child\height,*child\pitch,0),0)
  NalCheck(614,NeonVkChromeResume(),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(615,NeonVkChromeBegin(@clear[0]),0)
  NalCheck(616,NeonVkChromeBox(0,0,*child\width,*child\height,$FF00FF00),0)
  NalCheck(617,NeonVkChromeSuspend(),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(618,NeonVkChromeCancelSuspended(),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(619,NeonVkChromeEnd(),0)
  NalCheck(620,NeonVkChromePresentConsume(),1)
  NalCheck(621,nvcNextFrameSequence-seq,1)
  NalCheck(622,NeonVkChromeRebind(*c\framebuffer,194,128,194,128,*c\pitch,0),0)
  NalCheck(623,NeonVkChromeResume(),0)
  NalCheck(624,NeonVkChromeSuspended(),0)
  NalCheck(625,Bool(nvcViewportX=10 And nvcViewportY=8 And nvcViewportW=97 And nvcViewportH=64),1)
  NalCheck(626,Bool(nvcClipOn=1 And nvcClipX=0 And nvcClipY=0 And nvcClipW=194 And nvcClipH=128),1)
  NalCheck(627,NeonVkChromeDrawCount(),1)
  NalCheck(628,nvcFlatDraws,1)
  NalCheck(629,NeonVkChromeBox(80,40,40,40,$FF0000FF),0)
  NalCheck(630,NeonVkChromeEnd(),0)
  NalCheck(631,NeonVkChromePresentConsume(),1)
  NalCheck(632,nvcNextFrameSequence-seq,2)
  If NalFailure<>0 : Goto NalContinuationDone : EndIf
  NalContinuationPixels(*c,633)
  ; Repeated continuation with no new geometry must neither clear nor invent
  ; a transparent draw, and must preserve the logical draw budgets.
  NalCheck(635,NeonVkChromeBegin(@clear[0]),0)
  NalCheck(636,NeonVkChromeViewportSet(10,8,97,64),0)
  NalCheck(637,NeonVkChromeBox(20,20,40,40,$FFFF0000),0)
  NalCheck(638,NeonVkChromeBox(80,40,40,40,$FF0000FF),0)
  NalCheck(639,NeonVkChromeSuspend(),0)
  NalCheck(640,NeonVkChromeResume(),0)
  NalCheck(641,NeonVkChromeSuspend(),0)
  NalCheck(642,NeonVkChromeResume(),0)
  NalCheck(643,NeonVkChromeDrawCount(),2)
  NalCheck(644,NeonVkChromeEnd(),0)
  NalCheck(645,NeonVkChromePresentConsume(),1)
  NalContinuationPixels(*c,646)
  NalCheck(648,NeonVkChromeBegin(@clear[0]),0)
  NalCheck(649,NeonVkChromeSuspend(),0)
  NalCheck(650,NeonVkChromeCancelSuspended(),0)
  NalCheck(651,NeonVkChromeSuspended(),0)
  NalCheck(652,NeonVkChromePresentPending(),0)
  NalContinuationDone:
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  NeonVkChromeCancelSuspended()
  NalCheck(653,NeonVkChromeRebind(original\framebuffer,original\logicalW,original\logicalH,original\physicalW,original\physicalH,original\pitch,original\rotation),0)
  NalCheck(654,NeonVkCanvasRetarget(*c),0)
  NalCheck(655,NeonVkCanvasRetarget(*child),0)
  NalCheck(656,NeonVkCanvasRetarget(*primary),0)
  NalCheck(657,NeonVkCanvasResizeBlank(*c,193,127),0)
EndProcedure
