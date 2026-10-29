; SPDX-License-Identifier: MIT
; Actual V3D color-load proof. CPU stores seed an attachment, never render it.
Global Dim NalPacket.i[64]
Global NalCount.i,NalFailure.i
Procedure.i NalWord(address.i)
  ; Packet payload fields are byte-aligned. Word loads require alignment in
  ; the returning payload's cold memory mapping, so decode four byte loads.
  ProcedureReturn PeekA(address) | (PeekA(address+1)<<8) | (PeekA(address+2)<<16) | (PeekA(address+3)<<24)
EndProcedure
Procedure NalCheck(id.i,value.i,wanted.i)
  If NalCount>=200 : NalFailure=9999 : ProcedureReturn : EndIf
  PokeI($E1C02880+NalCount*24,id)
  PokeI($E1C02888+NalCount*24,value)
  PokeI($E1C02890+NalCount*24,wanted)
  NalCount=NalCount+1
  If value<>wanted And NalFailure=0 : NalFailure=id : EndIf
EndProcedure
Procedure.i NalPattern(x.i,y.i)
  ProcedureReturn ((x*13+y*7) & 255) | (((x*5+y*17) & 255)<<8) | (((x*19+y*3) & 255)<<16) | (((x+y*11) & 255)<<24)
EndProcedure
Procedure NalPixels(*c.NeonVkCanvas,id.i,kind.i)
  Protected mapped.i,x.i,y.i,wanted.i,bad.i,rc.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(id,rc,0)
  If rc<>0 : ProcedureReturn : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1
      wanted=NalPattern(x,y)
      If kind=1 And x>=10 And x<27 And y>=9 And y<22 : wanted=$80402010 : EndIf
      If kind=2 : wanted=$FF123456 : EndIf
      If PeekN(mapped+y* *c\pitch+x*4)<>wanted : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(id+1,bad,0)
EndProcedure
Procedure NalCase(*c.NeonVkCanvas,id.i)
  Protected mapped.i,x.i,y.i,rc.i
  Protected oldBase.i,oldW.i,oldH.i,oldPitch.i,oldBytes.i,oldFormat.i,oldRotation.i
  oldBase=Neon_SurfaceBase() : oldW=Neon_SurfaceW() : oldH=Neon_SurfaceH()
  oldPitch=Neon_SurfacePitch() : oldBytes=Neon_SurfaceBytes()
  oldFormat=Neon_SurfaceFormat() : oldRotation=Neon_SurfaceRotation()
  NalCheck(id,NeonRebindSurface(AnvilVkImageAddress(*c\image),*c\width,*c\height,*c\pitch,*c\pitch* *c\height,#V3D_OFMT_RGBA8,0),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(id+1,rc,0)
  If rc<>0 : Goto NalCaseDone : EndIf
  For y=0 To *c\height-1
    For x=0 To *c\width-1 : PokeL(mapped+y* *c\pitch+x*4,NalPattern(x,y)) : Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(id+2,NeonHardwareFrameBeginLoad(0,2),#NEON_ERR_ARGS)
  NalCheck(id+3,NeonHardwareFrameBeginLoad($FF00FF00,1),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalCheck(id+4,NeonHardwareFrameEnd(),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalPixels(*c,id+5,0)
  NalCheck(id+7,NeonHardwareFrameBeginLoad($FFFF0000,1),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalCheck(id+8,NeonHardwareClearRect(10,9,17,13,$80402010),0)
  NalCheck(id+9,NeonHardwareFrameEnd(),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalPixels(*c,id+10,1)
  NalCheck(id+12,NeonHardwareFrameBegin($FF123456),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalCheck(id+13,NeonHardwareFrameEnd(),0)
  If NalFailure<>0 : Goto NalCaseDone : EndIf
  NalPixels(*c,id+14,2)
  NalCaseDone:
  ; Return borrowed renderer ownership before a canvas resize can retire the
  ; temporary attachment, and before the next Vulkan submission preflight.
  NalCheck(id+16,NeonRebindSurface(oldBase,oldW,oldH,oldPitch,oldBytes,oldFormat,oldRotation),0)
  NalCheck(id+17,Bool(Neon_SurfaceBase()=oldBase And Neon_SurfaceW()=oldW And Neon_SurfaceH()=oldH And Neon_SurfacePitch()=oldPitch And Neon_SurfaceBytes()=oldBytes And Neon_SurfaceFormat()=oldFormat And Neon_SurfaceRotation()=oldRotation),1)
EndProcedure
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=2
XIncludeFile "RaspberryPi4/Tests/Vulkan/vulkan_attachment_load.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=3
XIncludeFile "RaspberryPi4/Tests/Vulkan/vulkan_renderpass_compatibility.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=4
XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_chrome_continuation.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=5
XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_wsi_continuation.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=6
XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_idle_wsi_scope.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=7
XIncludeFile "RaspberryPi4/Tests/Vulkan/vulkan_clear_value_count.pbi"
CompilerEndIf
CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=8
XIncludeFile "RaspberryPi4/Tests/Vulkan/vulkan_clear_initial_layout.pbi"
CompilerEndIf
Procedure.i NeonAttachmentLoadProof(*c.NeonVkCanvas,*child.NeonVkCanvas,*primary.NeonVkCanvas)
  PokeI($E1C02840,$4E414C31)
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=6
  NalIdleWsiCase(*c,*child,*primary)
  Goto NalDone
  CompilerEndIf
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=5
  NalWsiContinuationCase(*c,*child,*primary)
  Goto NalDone
  CompilerEndIf
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=4
  NalContinuationCase(*c,*child,*primary)
  Goto NalDone
  CompilerEndIf
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=3
  NalCompatibilityCase(*c)
  Goto NalDone
  CompilerEndIf
  NalCheck(1,V3dClBegin(@NalPacket[0],512),0)
  V3dClLoadTileBufferGeneral(0,$12345678,21,0,$ABCDE,1)
  NalCheck(2,V3dClFinish(),0)
  NalCheck(3,V3dClEndAddr()-V3dClAddr(),13)
  NalCheck(4,PeekA(@NalPacket[0]),30)
  NalCheck(5,NalWord(@NalPacket[0]+1),$E0115000)
  NalCheck(6,NalWord(@NalPacket[0]+5),$ABCD)
  NalCheck(7,NalWord(@NalPacket[0]+9),$12345678)
  NalCheck(8,V3dClBegin(@NalPacket[0],512),0)
  V3dClLoadTileBufferGeneral(0,$12345678,21,0,$100000,0)
  NalCheck(9,V3dClError(),#V3D_ERR_CL_ARGS)
  NalCheck(10,V3dClEndAddr()-V3dClAddr(),0)
  If NalFailure<>0 : Goto NalDone : EndIf
  NalCase(*c,100)
  If NalFailure<>0 : Goto NalDone : EndIf
  NalCheck(20,NeonVkCanvasResizeBlank(*c,65,33),0)
  If NalFailure<>0 : Goto NalDone : EndIf
  NalCase(*c,200)
  If NalFailure<>0 : Goto NalDone : EndIf
  NalCheck(21,NeonVkCanvasResizeBlank(*c,193,127),0)
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=2
  If NalFailure=0 : NalPublicCase(*c) : EndIf
  CompilerEndIf
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=7
  If NalFailure=0 : NalClearValueCountCase(*c) : EndIf
  CompilerEndIf
  CompilerIf #NCT_ATTACHMENT_LOAD_PROOF=8
  If NalFailure=0 : NalClearInitialLayoutCase(*c) : EndIf
  CompilerEndIf
  NalDone:
  PokeI($E1C02848,NalFailure) : PokeI($E1C02850,NalCount)
  PokeI($E1C02858,1)
  ProcedureReturn NalFailure
EndProcedure
