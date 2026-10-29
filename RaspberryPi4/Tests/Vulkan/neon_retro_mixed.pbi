XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retro.pbi"
; SPDX-License-Identifier: MIT
; The original curved-screen effect requires opaque black outside warped UV [0,1].
Global NcuCanvas.NeonVkCanvas
Global NcuCount.i,NcuFailure.i
Global Dim NcuClear.l[4]
Procedure NcuCheck(value.i)
  If NcuCount>=30 : NcuFailure=999 : ProcedureReturn : EndIf
  PokeI($E1C03D80+NcuCount*16,value) : PokeI($E1C03D88+NcuCount*16,0)
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
    PokeI($E1C03F10+0,PeekN(mapped+0* *primary\pitch+0))
    PokeI($E1C03F10+8,PeekN(mapped+0* *primary\pitch+1020))
    PokeI($E1C03F10+16,PeekN(mapped+255* *primary\pitch+0))
    PokeI($E1C03F10+24,PeekN(mapped+255* *primary\pitch+1020))
    PokeI($E1C03F10+32,PeekN(mapped+127* *primary\pitch+508))
    PokeI($E1C03F10+40,PeekN(mapped+127* *primary\pitch+40))
    PokeI($E1C03F10+48,PeekN(mapped+0* *primary\pitch+1024))
    PokeI($E1C03F10+56,PeekN(mapped+0* *primary\pitch+2044))
    PokeI($E1C03F10+64,PeekN(mapped+255* *primary\pitch+1024))
    PokeI($E1C03F10+72,PeekN(mapped+255* *primary\pitch+2044))
    PokeI($E1C03F10+80,PeekN(mapped+127* *primary\pitch+1532))
    PokeI($E1C03F10+88,PeekN(mapped+127* *primary\pitch+1064))
    PokeI($E1C03F10+96,PeekN(mapped+1* *primary\pitch+2048))
    PokeI($E1C03F10+104,PeekN(mapped+1* *primary\pitch+2052))
    PokeI($E1C03F10+112,PeekN(mapped+3* *primary\pitch+2332))
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
  NcuOffset(0)
  NcuCheck(NeonVkCanvasBegin(*primary,@NcuClear[0]))
  NcuCheck(NeonVkChromeRetroDrawId(2,0,0,256,256,0))
  NcuCheck(NeonVkChromeRetroDrawId(2,256,0,256,256,$3E000000))
  NcuCheck(NeonVkChromeImageSpriteDrawId(2,512,0,0,0,64,64,64,64,$FFFFFFFF))
  NcuCheck(NeonVkChromeBox(580,0,8,8,$FFFF0000))
  NcuCheck(NeonVkCanvasEnd(*primary))
  NcuPixels(*primary,0)
  NcuDone:
  NcuOffset(-1)
  NcuCheck(NeonVkCanvasClose(@NcuCanvas))
  NcuCheck(NeonVkChromeImageSpriteClearId(2))
  PokeI($E1C03D68,NcuFailure) : PokeI($E1C03D70,NcuCount)
  ProcedureReturn NcuFailure
EndProcedure
