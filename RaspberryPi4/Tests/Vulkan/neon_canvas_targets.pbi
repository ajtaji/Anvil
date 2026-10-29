; SPDX-License-Identifier: MIT
; Real multi-target/resize/lifetime proof; includes no CPU rendering.
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF
XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_attachment_load.pbi"
CompilerEndIf
Global NctB.NeonVkCanvas,NctC.NeonVkCanvas
Global Dim NctPool.NeonVkCanvas[15]
Global Dim NctClear.l[4]
Global NctCount.i,NctFailure.i
Global NctParticle.NeonParticleRecord
Procedure NctCheck(id.i,value.i,wanted.i)
  If NctCount>=400 : NctFailure=9999 : ProcedureReturn : EndIf
  PokeI($E1C017A0+NctCount*24,id)
  PokeI($E1C017A8+NctCount*24,value)
  PokeI($E1C017B0+NctCount*24,wanted)
  NctCount=NctCount+1
  If value<>wanted And NctFailure=0 : NctFailure=id : EndIf
EndProcedure
Procedure NctColour(*c.NeonVkCanvas,id.i,wanted.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NctCheck(id,rc,0)
  If rc=0
    NctCheck(id+1,PeekN(mapped+(*c\height/2)* *c\pitch+(*c\width/2)*4),wanted)
    vkUnmapMemory(*c\target\device,*c\memory)
  EndIf
EndProcedure
Procedure NctPixel(*c.NeonVkCanvas,id.i,x.i,y.i,wanted.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NctCheck(id,rc,0)
  If rc=0
    NctCheck(id+1,PeekN(mapped+y* *c\pitch+x*4),wanted)
    vkUnmapMemory(*c\target\device,*c\memory)
  EndIf
EndProcedure
Procedure.i NeonCanvasTargetsProof(*primary.NeonVkCanvas,scratch.i,bytes.i)
  Protected i.i,framebuffer.i,generation.i,rc.i
  PokeI($E1C01770,$4E435431)
  NctClear[3]=$3F800000
  NctCheck(1,NeonVkCanvasInit(@NctB,SizeOf(NeonVkCanvas)),0)
  NctCheck(2,NeonVkCanvasInit(@NctC,SizeOf(NeonVkCanvas)),0)
  NctCheck(3,NeonVkCanvasCreateBlank(@NctB,193,127,2),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(4,NeonVkCanvasCreate(@NctC,127,193,3,scratch,bytes),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  ; First and odd-tail texels must be transparent zero, preserving BLUE
  ; beneath them rather than painting an opaque black initialization.
  NctClear[2]=$3F800000
  NctCheck(200,NeonVkCanvasBegin(*primary,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(201,NeonVkChromeImageSpriteDrawId(2,0,0,192,126,1,1,160,120,$FFFFFFFF),0)
  NctCheck(202,NeonVkChromeImageSpriteDrawId(2,200,0,0,0,1,1,160,120,$FFFFFFFF),0)
  NctCheck(203,NeonVkCanvasEnd(*primary),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctPixel(*primary,204,80,60,4278190335)
  NctPixel(*primary,206,280,60,4278190335)
  NctClear[2]=0
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF
  NctCheck(400,NeonAttachmentLoadProof(@NctB,@NctC,*primary),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  CompilerEndIf
  NctCheck(5,Bool(NctB\image<>NctC\image And NctB\image<>*primary\image And NctB\framebuffer<>NctC\framebuffer),1)
  NctCheck(6,NeonVkCanvasCreate(@NctB,193,127,2,scratch,bytes),#NEON_CANVAS_ERR_STATE)
  NctCheck(7,NeonVkCanvasInit(@NctB,SizeOf(NeonVkCanvas)),#NEON_CANVAS_ERR_STATE)
  NctCheck(8,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(9,NeonVkCanvasBegin(@NctC,@NctClear[0]),#NEON_CANVAS_ERR_STATE)
  NctCheck(10,NeonVkCanvasEnd(@NctC),#NEON_CANVAS_ERR_STATE)
  NctCheck(11,NeonVkCanvasClose(@NctC),#NEON_CANVAS_ERR_STATE)
  NctCheck(12,NeonVkCanvasResize(@NctC,65,97,scratch,bytes),#NEON_CANVAS_ERR_STATE)
  NctCheck(13,NeonVkChromeBox(0,0,193,127,$FFFF0000),0)
  NctCheck(14,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(15,NctB\hasFrame,1)
  NctCheck(16,Bool(NctB\target\generation=NctC\target\generation And NctB\target\generation=*primary\target\generation),1)
  NctColour(@NctB,17,4294901760)
  NctCheck(19,NeonVkCanvasBegin(@NctC,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(20,NeonVkChromeBox(0,0,127,193,$FF00FF00),0)
  NctCheck(21,NeonVkCanvasEnd(@NctC),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctColour(@NctC,22,4278255360)
  NctCheck(300,NeonVkChromeDestroyChecked(),#NEON_VK_CHROME_ERR_STATE)
  NctCheck(301,NeonVkCanvasBind(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(302,NeonVkCanvasBind(@NctC),#NEON_CANVAS_ERR_STATE)
  NctCheck(303,NeonVkCanvasClose(@NctC),#NEON_CANVAS_ERR_STATE)
  NctCheck(304,NeonVkCanvasResizeBlank(@NctB,97,65),#NEON_CANVAS_ERR_STATE)
  NctParticle\x=50.0 : NctParticle\y=50.0 : NctParticle\size=20.0
  NctParticle\r=1.0 : NctParticle\g=1.0 : NctParticle\a=1.0
  NctCheck(305,NeonVkChromeParticlesPrepareFloat32(@NctParticle,1,0.0,0.0,1.0),0)
  NctCheck(306,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(307,NeonVkCanvasUnbind(@NctB),#NEON_CANVAS_ERR_STATE)
  NctCheck(308,NeonVkCanvasAbort(@NctC),#NEON_CANVAS_ERR_STATE)
  NctCheck(309,NeonVkChromeParticlesDrawPrepared(),0)
  NctCheck(310,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(311,NctB\phase,#NEON_VK_CANVAS_SELECTED)
  NctPixel(@NctB,312,50,50,4294967040)
  NctCheck(314,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(315,NeonVkChromeBox(0,0,193,127,$FFFF0000),0)
  NctCheck(316,NeonVkCanvasAbort(@NctB),0)
  NctCheck(317,NctB\phase,#NEON_VK_CANVAS_SELECTED)
  NctPixel(@NctB,318,50,50,4294967040)
  NctCheck(320,NeonVkCanvasUnbind(@NctB),0)
  NctCheck(321,NctB\phase,#NEON_VK_CANVAS_IDLE)
  NctCheck(322,NeonVkCanvasBind(@NctB),0)
  NctCheck(323,NeonVkCanvasClose(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(324,NctB\phase,#NEON_VK_CANVAS_CLOSED)
  NctCheck(325,NeonVkCanvasCreateBlank(@NctB,193,127,2),0)
  NctCheck(326,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(327,NeonVkChromeBox(0,0,193,127,$FFFF0000),0)
  NctCheck(328,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(330,NeonVkChromeResourceRetain(),0)
  NctCheck(331,NeonVkChromeResourceRelease(),0)
  NctCheck(332,NeonVkChromeDestroyChecked(),#NEON_VK_CHROME_ERR_STATE)
  ; A caller rebind must stale every prior capture. Retargeting B may
  ; not silently adopt the unrelated new epoch for C or the primary.
  NctCheck(60,NeonVkChromeRebind(*primary\target\framebuffer,*primary\target\logicalW,*primary\target\logicalH,*primary\target\physicalW,*primary\target\physicalH,*primary\target\pitch,*primary\target\rotation),0)
  NctCheck(61,NeonVkCanvasBegin(@NctB,@NctClear[0]),#NEON_CANVAS_ERR_STALE)
  NctCheck(62,NeonVkCanvasBegin(@NctC,@NctClear[0]),#NEON_CANVAS_ERR_STALE)
  NctCheck(63,NeonVkCanvasBegin(*primary,@NctClear[0]),#NEON_CANVAS_ERR_STALE)
  NctCheck(64,NeonVkCanvasRetarget(@NctB),0)
  NctCheck(65,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(66,NeonVkChromeBox(0,0,193,127,$FFFF0000),0)
  NctCheck(67,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(68,NeonVkCanvasBegin(@NctC,@NctClear[0]),#NEON_CANVAS_ERR_STALE)
  NctCheck(69,NeonVkCanvasBegin(*primary,@NctClear[0]),#NEON_CANVAS_ERR_STALE)
  NctCheck(70,NeonVkCanvasRetarget(@NctC),0)
  NctCheck(71,NeonVkCanvasRetarget(*primary),0)
  ; Sample BOTH independent optimal images into a third linear attachment,
  ; then read the real GPU output. This also checks descriptor isolation.
  NctCheck(50,NeonVkCanvasBegin(*primary,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(51,NeonVkChromeImageSpriteDrawId(2,0,0,0,0,193,127,160,120,$FFFFFFFF),0)
  NctCheck(52,NeonVkChromeImageSpriteDrawId(3,200,0,0,0,127,193,160,120,$FFFFFFFF),0)
  NctCheck(53,NeonVkCanvasEnd(*primary),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctPixel(*primary,54,80,60,4294901760)
  NctPixel(*primary,56,280,60,4278255360)
  framebuffer=NctB\framebuffer : generation=NctB\textureGeneration
  NctCheck(24,NeonVkCanvasResize(@NctB,0,65,scratch,bytes),#NEON_CANVAS_ERR_ARGS)
  NctCheck(25,Bool(NctB\framebuffer=framebuffer And NctB\width=193 And NctB\hasFrame=1),1)
  NctCheck(26,NeonVkCanvasResize(@NctB,1,1,@NctB,SizeOf(NeonVkCanvas)),#NEON_CANVAS_ERR_ARGS)
  NctCheck(27,NeonVkCanvasResizeBlank(@NctB,97,65),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(28,NctB\width,97) : NctCheck(29,NctB\height,65)
  NctCheck(30,NctB\hasFrame,0)
  NctCheck(31,Bool(NctB\textureGeneration>generation),1)
  NctCheck(32,NeonVkChromeBegin(@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(33,NeonVkCanvasDrawPassthrough(@NctB),#NEON_CANVAS_ERR_STATE)
  NctCheck(34,NeonVkChromeAbort(),0)
  NctCheck(35,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(36,NeonVkChromeBox(0,0,97,65,$FF00FF00),0)
  NctCheck(37,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctColour(@NctB,38,4278255360)
  ; The resized sampled image must contain the NEW green frame, not the
  ; preceding red texture or an old descriptor with the previous extent.
  NctCheck(80,NeonVkCanvasBegin(*primary,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(81,NeonVkChromeImageSpriteDrawId(2,0,0,0,0,97,65,160,120,$FFFFFFFF),0)
  NctCheck(82,NeonVkCanvasEnd(*primary),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctPixel(*primary,83,80,60,4278255360)
  NctCheck(40,NeonVkCanvasClose(@NctC),0)
  NctCheck(41,NeonVkChromeImageSpriteAllocatedId(3),0)
  NctCheck(42,NeonVkChromeImageSpriteAllocatedId(2),1)
  NctCheck(43,NeonVkCanvasBegin(@NctB,@NctClear[0]),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctCheck(44,NeonVkChromeBox(0,0,97,65,$FFFF0000),0)
  NctCheck(45,NeonVkCanvasEnd(@NctB),0)
  If NctFailure<>0 : Goto NctCleanup : EndIf
  NctColour(@NctB,46,4294901760)
  NctCheck(48,NeonVkCanvasClose(@NctB),0)
  NctCheck(49,NeonVkChromeImageSpriteAllocatedId(2),0)
  For i=0 To 14
    NctCheck(100+i*2,NeonVkCanvasInit(@NctPool[i],SizeOf(NeonVkCanvas)),0)
    If (i & 1)=0
      NctCheck(101+i*2,NeonVkCanvasCreateBlank(@NctPool[i],2,3,i+2),0)
    Else
      NctCheck(101+i*2,NeonVkCanvasCreate(@NctPool[i],2,3,i+2,scratch,bytes),0)
    EndIf
    If NctFailure<>0 : Goto NctCleanup : EndIf
  Next
  NctCheck(130,NeonVkCanvasInit(@NctB,SizeOf(NeonVkCanvas)),0)
  NctCheck(131,NeonVkCanvasCreate(@NctB,2,3,1,scratch,bytes),#NEON_CANVAS_ERR_STATE)
  For i=14 To 0 Step -1
    NctCheck(140+14-i,NeonVkCanvasClose(@NctPool[i]),0)
    If NctFailure<>0 : Goto NctCleanup : EndIf
  Next
  NctCheck(155,NeonVkCanvasCreate(@NctB,2,3,2,scratch,bytes),0)
  NctCheck(156,NeonVkCanvasClose(@NctB),0)
  NctCleanup:
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  If NctB\phase<>#NEON_VK_CANVAS_CLOSED
    rc=NeonVkCanvasClose(@NctB)
    If rc<>0 And NctFailure=0 : NctFailure=9002 : EndIf
  EndIf
  If NctC\phase<>#NEON_VK_CANVAS_CLOSED
    rc=NeonVkCanvasClose(@NctC)
    If rc<>0 And NctFailure=0 : NctFailure=9001 : EndIf
  EndIf
  For i=0 To 14
    If NctPool[i]\phase<>#NEON_VK_CANVAS_CLOSED
      rc=NeonVkCanvasClose(@NctPool[i])
      If rc<>0 And NctFailure=0 : NctFailure=9010+i : EndIf
    EndIf
  Next
  PokeI($E1C01778,NctFailure) : PokeI($E1C01780,NctCount)
  PokeI($E1C01788,1)
  ProcedureReturn NctFailure
EndProcedure
