; SPDX-License-Identifier: MIT
; Explicit and implicit idle child scopes retain an acquired parent image.
XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_wsi_continuation.pbi"
Procedure NalIdleWsiCase(*c.NeonVkCanvas,*child.NeonVkCanvas,*primary.NeonVkCanvas)
  Protected original.NeonVkTargetInfo,provider.i,surface.i,swapchain.i,device.i,mode.i,id.i
  Protected index.l
  Protected Dim clear.l[4]
  clear[3]=$3F800000 : device=*c\target\device
  NalCheck(950,NeonVkChromeTargetSnapshot(@original,SizeOf(NeonVkTargetInfo)),0)
  NalCheck(951,NeonVkChromeRebind(*c\framebuffer,193,127,193,127,*c\pitch,0),0)
  If NalFailure<>0 : Goto NisDone : EndIf
  For mode=0 To 3
    id=1000+mode*50
    NalWsiCreate(device,*c\image,id,@provider,@surface,@swapchain)
    NalCheck(id+3,avkWsiAcquire(device,swapchain,0,@index),0)
    NalCheck(id+4,NeonVkChromeWsiAttach(device,swapchain,index),0)
    NalCheck(id+5,NeonVkCanvasRetarget(*child),0)
    NalCheck(id+6,NeonVkChromeFrameAbortable(),0)
    If mode=1
      NalCheck(id+7,NeonVkCanvasBegin(*child,@clear[0]),0)
    Else
      NalCheck(id+7,NeonVkCanvasBind(*child),0)
    EndIf
    NalCheck(id+8,NeonVkChromeSuspended(),2)
    NalCheck(id+9,avkWsiImageState(device,swapchain,index),1)
    NalCheck(id+10,NeonVkChromeFrameAbortable(),Bool(mode=1))
    NalCheck(id+11,NeonVkChromeResumeIdle(),#NEON_VK_CHROME_ERR_STATE)
    If NalFailure<>0 : Goto NisDone : EndIf
    If mode=1 : NalCheck(id+12,0,0)
    Else : NalCheck(id+12,NeonVkCanvasBegin(*child,@clear[0]),0) : EndIf
    NalCheck(id+13,NeonVkChromeBox(0,0,20,20,$FF00FF00),0)
    NalCheck(id+14,NeonVkCanvasEnd(*child),0)
    NalCheck(id+15,nvdWsiSaved,Bool(mode<>1))
    NalCheck(id+16,avkWsiImageState(device,swapchain,index),1)
    If mode>=2 : NalCheck(id+17,avkWsiProviderLose(provider),0)
    Else : NalCheck(id+17,0,0) : EndIf
    If mode=1
      NalCheck(id+18,0,0)
    ElseIf mode>=2
      NalCheck(id+18,NeonVkCanvasUnbind(*child),#VK_ERROR_SURFACE_LOST_KHR)
    Else
      NalCheck(id+18,NeonVkCanvasUnbind(*child),0)
    EndIf
    NalCheck(id+19,NeonVkChromeFrameAbortable(),0)
    NalCheck(id+20,NeonVkChromeSuspended(),2*Bool(mode>=2))
    NalCheck(id+21,nvdWsiSaved,Bool(mode>=2))
    NalCheck(id+22,nvdWsiState,Bool(mode<2))
    If NalFailure<>0 : Goto NisDone : EndIf
    If mode>=2
      NalCheck(id+23,NeonVkCanvasClose(*child),#VK_ERROR_SURFACE_LOST_KHR)
      NalCheck(id+24,Bool(*child\framebuffer<>0),1)
      If mode=3
        NalCheck(1183,NeonVkChromeCancelSuspended(),0)
        NalCheck(1184,NeonVkChromeSuspended(),0)
      EndIf
      NalCheck(id+25,NeonVkCanvasCloseContextScope(*child),0)
      NalCheck(id+26,avkWsiImageState(device,swapchain,index),0)
      NalCheck(id+27,NeonVkChromeSuspended(),0)
      NalCheck(id+28,NeonVkCanvasCreateBlank(*child,127,193,3),0)
    Else
      NalCheck(id+23,NeonVkChromeBegin(@clear[0]),0)
      NalCheck(id+24,NeonVkChromeBox(10,10,20,20,$FFFF0000),0)
      NalCheck(id+25,NeonVkChromeBox(50,10,20,20,$FF0000FF),0)
      NalCheck(id+26,NeonVkChromeEnd(),0)
      NalCheck(id+27,NeonVkChromePresentConsume(),1)
      NalCheck(id+28,0,0)
      If mode=0 : NalWsiPixels(*c) : EndIf
    EndIf
    NalCheck(id+29,avkWsiImageState(device,swapchain,index),0)
    NalCheck(id+30,avkWsiSwapchainDestroy(device,swapchain),0)
    NalCheck(id+31,avkWsiSurfaceDestroy(NalWsiInstance,surface),0)
    NalCheck(id+32,avkWsiProviderDestroy(provider),0)
    provider=0 : surface=0 : swapchain=0
    If NalFailure<>0 : Goto NisDone : EndIf
  Next
  NisDone:
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  If ncvSelectedOwner=*child : NeonVkCanvasUnbind(*child) : EndIf
  NeonVkChromeCancelSuspended() : nvdWsiRollback() : nvdWsiCancelSuspended()
  If swapchain<>0 : avkWsiSwapchainDestroy(device,swapchain) : EndIf
  If surface<>0 : avkWsiSurfaceDestroy(NalWsiInstance,surface) : EndIf
  If provider<>0 : avkWsiProviderDestroy(provider) : EndIf
  NalCheck(1200,NeonVkChromeRebind(original\framebuffer,original\logicalW,original\logicalH,original\physicalW,original\physicalH,original\pitch,original\rotation),0)
  NalCheck(1201,NeonVkCanvasRetarget(*c),0)
  NalCheck(1202,NeonVkCanvasRetarget(*child),0)
  NalCheck(1203,NeonVkCanvasRetarget(*primary),0)
EndProcedure
