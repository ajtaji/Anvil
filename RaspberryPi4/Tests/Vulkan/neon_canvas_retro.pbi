XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas_retro.pbi"
; SPDX-License-Identifier: MIT
; The original curved-screen effect requires opaque black outside warped UV [0,1].
Global NcuCanvas.NeonVkCanvas
Global NcuCount.i,NcuFailure.i
Global Dim NcuClear.l[4]
Procedure NcuCheck(value.i)
  If NcuCount>=30 : NcuFailure=999 : ProcedureReturn : EndIf
  PokeL($E1C03D80+NcuCount*4,value)
  NcuCount=NcuCount+1
  If value<>0 And NcuFailure=0 : NcuFailure=NcuCount : EndIf
EndProcedure
Global NcuTime.i
Procedure NcuOffset(bits.i)
  Protected rc.i,text.i,k.i
  NcuTime=bits
  If bits=-1 : NcuCheck(0) : ProcedureReturn : EndIf
  rc=NeonVkChromeRetroPrepare()
  If rc<>0
    PokeI($E1C04000,rc)
    PokeI($E1C04008,AnvilVkIrV3d42Error())
    PokeI($E1C04010,AnvilVkIrV3d42SourceId())
    PokeI($E1C04018,AnvilVkIrV3d42SourceOpcode())
    PokeI($E1C04020,AnvilVkIrV3d42Stage())
    text=AnvilVkFaultText()
    If text<>0
      For k=0 To 1022
        PokeA($E1C04100+k,PeekA(text+k))
        If PeekA(text+k)=0 : Break : EndIf
      Next
    EndIf
  EndIf
  NcuCheck(rc)
EndProcedure
Procedure NcuPixels(*primary.NeonVkCanvas,trial.i)
  Protected mapped.i,rc.i
  rc=vkMapMemory(*primary\target\device,*primary\memory,0,#VK_WHOLE_SIZE,0,@mapped) : NcuCheck(rc)
  If rc=0
    PokeI($E1C03F10+trial*48+0,PeekN(mapped+0* *primary\pitch+400))
    PokeI($E1C03F10+trial*48+8,PeekN(mapped+0* *primary\pitch+2796))
    PokeI($E1C03F10+trial*48+16,PeekN(mapped+599* *primary\pitch+400))
    PokeI($E1C03F10+trial*48+24,PeekN(mapped+599* *primary\pitch+2796))
    PokeI($E1C03F10+trial*48+32,PeekN(mapped+299* *primary\pitch+1596))
    PokeI($E1C03F10+trial*48+40,PeekN(mapped+299* *primary\pitch+500))
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
  NcuCheck(NeonVkCanvasRetroPrepare(@NcuCanvas))
  NcuCheck(ncvSelect(*primary))
  NcuCheck(NeonVkCanvasRetarget(@NcuCanvas))
  For trial=0 To 2
    bits=0
    If trial=0 : bits=0 : EndIf
    If trial=1 : bits=$3E000000 : EndIf
    If trial=2 : bits=$41480000 : EndIf
    NcuCheck(NeonVkChromeBegin(@NcuClear[0]))
    NcuCheck(NeonVkCanvasDrawRetro(@NcuCanvas,bits))
    NcuCheck(NeonVkChromeEnd())
    NcuCheck(NeonVkChromePresentConsume()-1)
    NcuPixels(*primary,trial)
    If NcuFailure<>0 : Goto NcuDone : EndIf
  Next
  NcuDone:
  NcuCheck(ncvRestore(*primary))
  NcuCheck(NeonVkCanvasRetarget(@NcuCanvas))
  NcuCheck(NeonVkCanvasClose(@NcuCanvas))
  NcuCheck(NeonVkChromeImageSpriteClearId(2))
  PokeI($E1C03D68,NcuFailure) : PokeI($E1C03D70,NcuCount)
  ProcedureReturn NcuFailure
EndProcedure
