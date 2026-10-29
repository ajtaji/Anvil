; SPDX-License-Identifier: MIT
; Owned nearest/linear sampling, generation and resize on real GPU images.
Global NcfCanvas.NeonVkCanvas
Global NcfCount.i,NcfFailure.i
Global Dim NcfClear.l[4]
Procedure NcfCheck(value.i,wanted.i)
  If NcfCount>=60 : NcfFailure=999 : ProcedureReturn : EndIf
  PokeI($E1C036D0+NcfCount*24,NcfCount+1)
  PokeI($E1C036D8+NcfCount*24,value)
  PokeI($E1C036E0+NcfCount*24,wanted)
  NcfCount=NcfCount+1
  If value<>wanted And NcfFailure=0 : NcfFailure=NcfCount : EndIf
EndProcedure
Procedure NcfPixels(*primary.NeonVkCanvas,slot.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*primary\target\device,*primary\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NcfCheck(rc,0)
  If rc=0
    PokeI($E1C03CF0+slot*16,PeekN(mapped+4* *primary\pitch+3*4))
    PokeI($E1C03CF8+slot*16,PeekN(mapped+4* *primary\pitch+4*4))
    vkUnmapMemory(*primary\target\device,*primary\memory)
  EndIf
EndProcedure
Procedure.i NeonCanvasFilterProof(*primary.NeonVkCanvas)
  Protected generation.i
  PokeI($E1C036B0,$4E434631)
  NcfClear[3]=$3F800000
  NcfCheck(NeonVkCanvasInit(@NcfCanvas,SizeOf(NeonVkCanvas)),0)
  NcfCheck(NeonVkCanvasCreateBlank(@NcfCanvas,2,2,2),0)
  If NcfFailure<>0 : Goto NcfDone : EndIf
  NcfCheck(NcfCanvas\linear,1)
  generation=NcfCanvas\textureGeneration
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,2),#NEON_CANVAS_ERR_ARGS)
  NcfCheck(Bool(NcfCanvas\textureGeneration=generation),1)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,0),0)
  NcfCheck(NcfCanvas\linear,0)
  NcfCheck(Bool(NcfCanvas\textureGeneration=generation+1),1)
  NcfCheck(NeonVkCanvasBegin(@NcfCanvas,@NcfClear[0]),0)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,1),#NEON_CANVAS_ERR_STATE)
  NcfCheck(NeonVkChromeBox(0,0,1,2,$FFFF0000),0)
  NcfCheck(NeonVkChromeBox(1,0,1,2,$FF0000FF),0)
  NcfCheck(NeonVkCanvasEnd(@NcfCanvas),0)
  If NcfFailure<>0 : Goto NcfDone : EndIf
  NcfCheck(NeonVkCanvasBegin(*primary,@NcfClear[0]),0)
  NcfCheck(NeonVkChromeImageSpriteDrawId(2,0,0,0,0,2,2,8,8,$FFFFFFFF),0)
  NcfCheck(NeonVkCanvasEnd(*primary),0)
  NcfPixels(*primary,0)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,1),0)
  NcfCheck(NcfCanvas\linear,1)
  NcfCheck(NeonVkCanvasBegin(*primary,@NcfClear[0]),0)
  NcfCheck(NeonVkChromeImageSpriteDrawId(2,0,0,0,0,2,2,8,8,$FFFFFFFF),0)
  NcfCheck(NeonVkCanvasEnd(*primary),0)
  NcfPixels(*primary,1)
  NcfCheck(NeonVkCanvasResizeBlank(@NcfCanvas,16,8),0)
  NcfCheck(NcfCanvas\linear,1)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,0),0)
  NcfCheck(NeonVkCanvasResizeBlank(@NcfCanvas,8,8),0)
  NcfCheck(NcfCanvas\linear,0)
  NcfCheck(NeonVkCanvasBind(@NcfCanvas),0)
  NcfCheck(NeonVkCanvasSetLinear(*primary,0),#NEON_CANVAS_ERR_STATE)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,1),#NEON_CANVAS_ERR_STATE)
  NcfCheck(NeonVkCanvasUnbind(@NcfCanvas),0)
  NcfCheck(NeonVkCanvasResizeBlank(@NcfCanvas,1,1),0)
  NcfCheck(NeonVkCanvasBegin(@NcfCanvas,@NcfClear[0]),0)
  NcfCheck(NeonVkChromeBox(0,0,1,1,$FF00FF00),0)
  NcfCheck(NeonVkCanvasEnd(@NcfCanvas),0)
  NcfCheck(NeonVkCanvasBegin(*primary,@NcfClear[0]),0)
  NcfCheck(NeonVkChromeImageSpriteDrawId(2,0,0,0,0,1,1,8,8,$FFFFFFFF),0)
  NcfCheck(NeonVkCanvasEnd(*primary),0)
  NcfPixels(*primary,2)
  NcfCheck(NeonVkChromeImageSpriteLinearId(2,1),0)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,0),#NEON_CANVAS_ERR_STALE)
  NcfDone:
  NcfCheck(NeonVkCanvasClose(@NcfCanvas),0)
  NcfCheck(NeonVkChromeImageSpriteClearId(2),0)
  NcfCheck(NeonVkCanvasSetLinear(@NcfCanvas,0),#NEON_CANVAS_ERR_STATE)
  PokeI($E1C036B8,NcfFailure) : PokeI($E1C036C0,NcfCount) : PokeI($E1C036C8,1)
  ProcedureReturn NcfFailure
EndProcedure
