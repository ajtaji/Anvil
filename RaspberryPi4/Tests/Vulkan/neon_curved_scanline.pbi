; SPDX-License-Identifier: MIT
; A descriptor offset must change which texel the GPU actually samples.
Global NcuCanvas.NeonVkCanvas
Global NcuCount.i,NcuFailure.i
Global Dim NcuClear.l[4]
Procedure NcuCheck(value.i)
  If NcuCount>=30 : NcuFailure=999 : ProcedureReturn : EndIf
  PokeI($E1C03D80+NcuCount*16,value) : PokeI($E1C03D88+NcuCount*16,0)
  NcuCount=NcuCount+1
  If value<>0 And NcuFailure=0 : NcuFailure=NcuCount : EndIf
EndProcedure
Procedure NcuOffset(bits.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(nvcDevice,nvcUniformMemory,0,16,0,@mapped) : NcuCheck(rc)
  If rc=0
    PokeL(mapped+4,0) : PokeL(mapped+8,0)
    If bits=-1 : bits=0 : Else : PokeL(mapped+4,$3F800000) : PokeL(mapped+8,$3C75C28F) : EndIf
    PokeL(mapped,bits) : PokeL(mapped+12,0)
    vkUnmapMemory(nvcDevice,nvcUniformMemory)
  EndIf
EndProcedure
Procedure NcuPixels(*primary.NeonVkCanvas,trial.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*primary\target\device,*primary\memory,0,#VK_WHOLE_SIZE,0,@mapped) : NcuCheck(rc)
  If rc=0
    PokeI($E1C03F10+trial*48+0,PeekN(mapped+7* *primary\pitch+40))
    PokeI($E1C03F10+trial*48+8,PeekN(mapped+127* *primary\pitch+40))
    PokeI($E1C03F10+trial*48+16,PeekN(mapped+7* *primary\pitch+132))
    PokeI($E1C03F10+trial*48+24,PeekN(mapped+127* *primary\pitch+132))
    PokeI($E1C03F10+trial*48+32,PeekN(mapped+7* *primary\pitch+920))
    PokeI($E1C03F10+trial*48+40,PeekN(mapped+127* *primary\pitch+920))
    vkUnmapMemory(*primary\target\device,*primary\memory)
  EndIf
EndProcedure
Procedure.i NeonCanvasComputedUvProof(*primary.NeonVkCanvas)
  Protected trial.i,bits.i,i.i,rc.i,colour.i
  PokeI($E1C03D60,$4E435531)
  NcuClear[3]=$3F800000
  NcuCheck(NeonVkCanvasInit(@NcuCanvas,SizeOf(NeonVkCanvas)))
  NcuCheck(NeonVkCanvasCreateBlank(@NcuCanvas,64,64,2))
  If NcuFailure<>0 : Goto NcuDone : EndIf
  NcuCheck(NeonVkCanvasSetLinear(@NcuCanvas,0))
  NcuCheck(NeonVkCanvasBegin(@NcuCanvas,@NcuClear[0]))
  rc=0
  For i=0 To 63
    colour=$FF606060 : If (i & 1)<>0 : colour=$FFA0A0A0 : EndIf
    If rc=0 : rc=NeonVkChromeBox(i,0,1,64,colour) : EndIf
    If i=31 : NcuCheck(rc) : EndIf
  Next
  NcuCheck(rc)
  NcuCheck(NeonVkCanvasEnd(@NcuCanvas))
  If NcuFailure<>0 : Goto NcuDone : EndIf
  For trial=0 To 2
    bits=0
    If trial=0 : bits=0 : EndIf
    If trial=1 : bits=$3E000000 : EndIf
    If trial=2 : bits=$41480000 : EndIf
    NcuOffset(bits)
    NcuCheck(NeonVkCanvasBegin(*primary,@NcuClear[0]))
    NcuCheck(NeonVkChromeImageSpriteDrawId(2,0,0,0,0,64,64,256,256,$FFFFFFFF))
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
