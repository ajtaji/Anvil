; SPDX-License-Identifier: MIT
; Real GPU parent/child sections with actual shared presentation ownership.
; Provider image keys identify the offscreen parent; no physical WSI transfer.
Global NalWsiInstance.i
Global NalWsiExtra.NeonVkCanvas
Procedure NalWsiCreate(device.i,image.i,seed.i,*provider,*surface,*swapchain)
  Protected info.AnvilVkWsiProviderInfo,ci.AnvilVkWsiSwapchainInfo,fmt.AnvilVkWsiFormat
  Protected mode.i=#VK_PRESENT_MODE_FIFO_KHR
  fmt\format=#VK_FORMAT_B8G8R8A8_UNORM : fmt\colorSpace=#VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
  info\cookie=seed
  info\capabilities\minImageCount=1 : info\capabilities\maxImageCount=1
  info\capabilities\currentWidth=193 : info\capabilities\currentHeight=127
  info\capabilities\minWidth=1 : info\capabilities\minHeight=1
  info\capabilities\maxWidth=2048 : info\capabilities\maxHeight=2048
  info\capabilities\maxImageArrayLayers=1
  info\capabilities\supportedTransforms=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
  info\capabilities\currentTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR
  info\capabilities\supportedCompositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
  info\capabilities\supportedUsageFlags=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT
  info\formatCount=1 : info\formats=@fmt : info\presentModeCount=1 : info\presentModes=@mode
  NalCheck(seed,avkWsiProviderRegister(@info,*provider),0)
  NalCheck(seed+1,avkWsiSurfaceCreate(NalWsiInstance,PeekI(*provider),seed,*surface),0)
  ci\surface=PeekI(*surface) : ci\minImageCount=1
  ci\imageFormat=fmt\format : ci\imageColorSpace=fmt\colorSpace
  ci\imageWidth=193 : ci\imageHeight=127 : ci\imageArrayLayers=1
  ci\imageUsage=#VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : ci\imageSharingMode=#VK_SHARING_MODE_EXCLUSIVE
  ci\preTransform=#VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR : ci\compositeAlpha=#VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR
  ci\presentMode=mode : ci\clipped=1 : ci\providerImageCount=1 : ci\providerImages=@image
  NalCheck(seed+2,avkWsiSwapchainCreate(device,@ci,*swapchain),0)
EndProcedure
Procedure NalWsiPixels(*c.NeonVkCanvas)
  Protected mapped.i,rc.i,x.i,y.i,wanted.i,bad.i
  rc=vkMapMemory(*c\target\device,*c\memory,0,#VK_WHOLE_SIZE,0,@mapped)
  NalCheck(890,rc,0)
  If rc<>0 : ProcedureReturn : EndIf
  For y=0 To 126
    For x=0 To 192
      wanted=$FF000000
      If x>=10 And x<30 And y>=10 And y<30 : wanted=$FFFF0000 : EndIf
      If x>=50 And x<70 And y>=10 And y<30 : wanted=$FF0000FF : EndIf
      If PeekN(mapped+y* *c\pitch+x*4)<>wanted : bad=bad+1 : EndIf
    Next
  Next
  vkUnmapMemory(*c\target\device,*c\memory)
  NalCheck(891,bad,0)
EndProcedure
Procedure NalWsiContinuationCase(*c.NeonVkCanvas,*child.NeonVkCanvas,*primary.NeonVkCanvas)
  Protected original.NeonVkTargetInfo,provider.i,surface.i,swapchain.i,mode.i,id.i,device.i,wanted.i
  Protected index.l
  Protected Dim clear.l[4]
  clear[3]=$3F800000 : device=*c\target\device
  NalCheck(700,NeonVkChromeTargetSnapshot(@original,SizeOf(NeonVkTargetInfo)),0)
  NalCheck(701,NeonVkChromeRebind(*c\framebuffer,193,127,193,127,*c\pitch,0),0)
  If NalFailure<>0 : Goto NwsDone : EndIf
  For mode=0 To 2
    id=710+mode*50
    NalWsiCreate(device,*c\image,id,@provider,@surface,@swapchain)
    NalCheck(id+3,NeonVkCanvasRetarget(*child),0)
    NalCheck(id+4,avkWsiAcquire(device,swapchain,0,@index),0)
    NalCheck(id+5,NeonVkChromeWsiAttach(device,swapchain,index),0)
    NalCheck(id+6,NeonVkChromeTargetRecordingAllowed(),1)
    If mode=0
      NalCheck(850,NeonVkCanvasInit(@NalWsiExtra,SizeOf(NeonVkCanvas)),0)
      NalCheck(851,NeonVkCanvasCreateBlank(@NalWsiExtra,8,8,4),0)
      NalCheck(852,nvdWsiState,1)
      NalCheck(853,NeonVkCanvasClose(@NalWsiExtra),0)
      NalCheck(854,nvdWsiState,1)
      NalCheck(855,avkWsiImageState(device,swapchain,index),1)
    EndIf
    NalCheck(id+7,NeonVkChromeBegin(@clear[0]),0)
    NalCheck(id+8,NeonVkChromeBox(10,10,20,20,$FFFF0000),0)
    NalCheck(id+9,NeonVkChromeSuspend(),0)
    NalCheck(id+10,nvdWsiSaved,1)
    NalCheck(id+11,avkWsiImageState(device,swapchain,index),1)
    NalCheck(id+12,nvdWsiEnabled(),0)
    NalCheck(id+13,NeonVkChromeWsiAttach(device,swapchain,index),#NEON_VK_CHROME_ERR_STATE)
    If NalFailure<>0 : Goto NwsDone : EndIf
    NalCheck(id+14,NeonVkCanvasBind(*child),0)
    NalCheck(id+15,NeonVkCanvasBegin(*child,@clear[0]),0)
    NalCheck(id+16,NeonVkChromeBox(0,0,20,20,$FF00FF00),0)
    NalCheck(id+17,NeonVkCanvasEnd(*child),0)
    NalCheck(id+18,avkWsiImageState(device,swapchain,index),1)
    NalCheck(id+19,nvdWsiSaved,1)
    NalCheck(id+20,NeonVkCanvasUnbind(*child),0)
    If NalFailure<>0 : Goto NwsDone : EndIf
    wanted=0
    Select mode
      Case 0
        NalCheck(id+21,avkWsiSwapchainRetire(device,swapchain),0)
        NalCheck(id+22,avkWsiProviderResize(provider,193,127),0)
      Case 1
        NalCheck(id+21,avkWsiProviderLose(provider),0)
        NalCheck(id+22,0,0) : wanted=#VK_ERROR_SURFACE_LOST_KHR
      Case 2
        NalCheck(id+21,avkWsiProviderResize(provider,200,127),0)
        NalCheck(id+22,0,0) : wanted=#VK_ERROR_OUT_OF_DATE_KHR
    EndSelect
    NalCheck(id+23,NeonVkChromeResume(),wanted)
    NalCheck(id+24,nvdWsiState,Bool(mode=0))
    NalCheck(id+25,nvdWsiSaved,Bool(mode<>0))
    If NalFailure<>0 : Goto NwsDone : EndIf
    If mode=0
      NalCheck(id+26,NeonVkChromeBox(50,10,20,20,$FF0000FF),0)
      NalCheck(id+27,NeonVkChromeEnd(),0)
      NalCheck(id+28,NeonVkChromePresentValidate(),1)
      NalCheck(id+29,NeonVkChromePresentConsume(),1)
      NalWsiPixels(*c)
    Else
      NalCheck(id+26,NeonVkChromeFrameAbortable(),0)
      NalCheck(id+27,NeonVkChromeCancelSuspended(),0)
      NalCheck(id+28,NeonVkChromePresentPending(),0)
      NalCheck(id+29,nvdWsiSaved,0)
    EndIf
    NalCheck(id+30,avkWsiImageState(device,swapchain,index),0)
    NalCheck(id+31,avkWsiSwapchainDestroy(device,swapchain),0)
    NalCheck(id+32,avkWsiSurfaceDestroy(NalWsiInstance,surface),0)
    NalCheck(id+33,avkWsiProviderDestroy(provider),0)
    provider=0 : surface=0 : swapchain=0
    If NalFailure<>0 : Goto NwsDone : EndIf
  Next

  NalWsiCreate(device,*c\image,910,@provider,@surface,@swapchain)
  NalCheck(913,avkWsiAcquire(device,swapchain,0,@index),0)
  NalCheck(914,NeonVkChromeWsiAttach(device,swapchain,index),0)
  NalCheck(915,avkWsiProviderLose(provider),0)
  NalCheck(916,NeonVkChromeTargetRecordingAllowed(),0)
  NalCheck(917,NeonVkChromeBegin(@clear[0]),#NEON_VK_CHROME_ERR_STATE)
  NalCheck(918,NeonVkChromeFrameAbortable(),0)
  NalCheck(919,nvdWsiState,1)
  NalCheck(920,nvdWsiRollback(),0)
  NalCheck(921,avkWsiImageState(device,swapchain,index),0)
  NalCheck(922,avkWsiSwapchainDestroy(device,swapchain),0)
  NalCheck(923,avkWsiSurfaceDestroy(NalWsiInstance,surface),0)
  NalCheck(924,avkWsiProviderDestroy(provider),0)
  provider=0 : surface=0 : swapchain=0
  NwsDone:
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  If ncvSelectedOwner=*child : NeonVkCanvasUnbind(*child) : EndIf
  NeonVkChromeCancelSuspended() : nvdWsiRollback() : nvdWsiCancelSuspended()
  If swapchain<>0 : avkWsiSwapchainDestroy(device,swapchain) : EndIf
  If surface<>0 : avkWsiSurfaceDestroy(NalWsiInstance,surface) : EndIf
  If provider<>0 : avkWsiProviderDestroy(provider) : EndIf
  NalCheck(900,NeonVkChromeRebind(original\framebuffer,original\logicalW,original\logicalH,original\physicalW,original\physicalH,original\pitch,original\rotation),0)
  NalCheck(901,NeonVkCanvasRetarget(*c),0)
  NalCheck(902,NeonVkCanvasRetarget(*child),0)
  NalCheck(903,NeonVkCanvasRetarget(*primary),0)
EndProcedure
