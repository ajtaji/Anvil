; SPDX-License-Identifier: MIT
; A descriptor offset must change which texel the GPU actually samples.
Global NcuCanvas.NeonVkCanvas
Global NcuCount.i,NcuFailure.i
Global Dim NcuClear.l[4]
Procedure NcuCheck(value.i)
  If NcuCount>=80 : NcuFailure=999 : ProcedureReturn : EndIf
  PokeL($E1C03D80+NcuCount*4,value)
  NcuCount=NcuCount+1
  If value<>0 And NcuFailure=0 : NcuFailure=NcuCount : EndIf
EndProcedure
Procedure NcuOffset(trial.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(nvcDevice,nvcUniformMemory,0,16,0,@mapped) : NcuCheck(rc)
  If rc=0
    PokeL(mapped,0) : PokeL(mapped+4,0) : PokeL(mapped+8,0) : PokeL(mapped+12,0)
    Select trial
      Case 0
        PokeL(mapped+0,$3E800000)
        PokeL(mapped+4,$3E800000)
        PokeL(mapped+8,$3E800000)
        PokeL(mapped+12,$3E800000)
      Case 1
        PokeL(mapped+0,$0)
        PokeL(mapped+4,$0)
        PokeL(mapped+8,$0)
        PokeL(mapped+12,$0)
      Case 2
        PokeL(mapped+0,$3F0CCCCD)
        PokeL(mapped+4,$3F266666)
        PokeL(mapped+8,$3E800000)
        PokeL(mapped+12,$3E800000)
      Case 3
        PokeL(mapped+0,$3E800000)
        PokeL(mapped+4,$3E800000)
        PokeL(mapped+8,$3F0CCCCD)
        PokeL(mapped+12,$3F266666)
      Case 4
        PokeL(mapped+0,$BD4CCCCD)
        PokeL(mapped+4,$BE19999A)
        PokeL(mapped+8,$3E800000)
        PokeL(mapped+12,$3E800000)
      Case 5
        PokeL(mapped+0,$3DCCCCCD)
        PokeL(mapped+4,$3E4CCCCD)
        PokeL(mapped+8,$3E99999A)
        PokeL(mapped+12,$3ECCCCCD)
    EndSelect
    vkUnmapMemory(nvcDevice,nvcUniformMemory)
  EndIf
EndProcedure
Procedure NcuPixels(*primary.NeonVkCanvas,trial.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*primary\target\device,*primary\memory,0,#VK_WHOLE_SIZE,0,@mapped) : NcuCheck(rc)
  If rc=0
    PokeI($E1C03F00+trial*8,PeekN(mapped+4* *primary\pitch+3*4))
    vkUnmapMemory(*primary\target\device,*primary\memory)
  EndIf
EndProcedure
Procedure.i NeonCanvasComputedUvProof(*primary.NeonVkCanvas)
  Protected trial.i,bits.i
  PokeI($E1C03D60,$4E435531)
  NcuClear[3]=$3F800000
  NcuCheck(NeonVkCanvasInit(@NcuCanvas,SizeOf(NeonVkCanvas)))
  NcuCheck(NeonVkCanvasCreateBlank(@NcuCanvas,2,2,2))
  If NcuFailure<>0 : Goto NcuDone : EndIf
  NcuCheck(NeonVkCanvasSetLinear(@NcuCanvas,0))
  NcuCheck(NeonVkCanvasBegin(@NcuCanvas,@NcuClear[0]))
  NcuCheck(NeonVkChromeBox(0,0,1,2,$FF808080))
  NcuCheck(NeonVkChromeBox(1,0,1,2,$FF808080))
  NcuCheck(NeonVkCanvasEnd(@NcuCanvas))
  If NcuFailure<>0 : Goto NcuDone : EndIf
  For trial=0 To 5
    bits=0
    If trial=0 : bits=$3F000000 : EndIf
    If trial=1 : bits=$BF000000 : EndIf
    NcuOffset(trial)
    NcuCheck(NeonVkCanvasBegin(*primary,@NcuClear[0]))
    NcuCheck(NeonVkChromeImageSpriteDrawId(2,0,0,0,0,2,2,8,8,$FFFFFFFF))
    NcuCheck(NeonVkCanvasEnd(*primary))
    NcuPixels(*primary,trial)
    If NcuFailure<>0 : Goto NcuDone : EndIf
  Next
  NcuDone:
  NcuOffset(-1)
  NcuCheck(NeonVkCanvasClose(@NcuCanvas))
  NcuCheck(NeonVkChromeImageSpriteClearId(2))
  PokeI($E1C03D68,NcuFailure) : PokeI($E1C03D70,NcuCount)
  ProcedureReturn NcuFailure
EndProcedure
