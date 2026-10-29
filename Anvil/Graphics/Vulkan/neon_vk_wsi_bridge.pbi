;
; Opt-in bridge from the resident adapter's completed attachment to vk_wsi.
; It owns no display, DMA, HDMI or DSI operation.
;

XIncludeFile "Anvil/Graphics/Vulkan/vk_wsi.pbi"

#NVD_WSI_FREE = 0
#NVD_WSI_ACQUIRED = 1
#NVD_WSI_READY = 2
#NVD_WSI_RESERVED = 3
#NVD_WSI_COMMITTED = 4

Global nvdWsiState.i
Global nvdWsiDevice.i
Global nvdWsiSwapchain.i
Global nvdWsiImageIndex.i
Global nvdWsiImageKey.i
Global nvdWsiTargetGeneration.i
Global nvdWsiTicket.i
; One suspended parent keeps its core image ACQUIRED while a child is active.
Global nvdWsiSaved.i,nvdWsiSavedDevice.i,nvdWsiSavedSwapchain.i
Global nvdWsiSavedImageIndex.i,nvdWsiSavedImageKey.i

Procedure.i nvdWsiEnabled()
  ProcedureReturn Bool(nvdWsiState <> #NVD_WSI_FREE)
EndProcedure

; Read-only recording preflight. Failed publication/rollback can retain an
; attached image without leaving it writable. The bridge and core must both
; still identify this adapter's acquired image before recording touches it.
Procedure.i nvdWsiRecordingAllowed(device.i, targetGeneration.i)
  Define imageKey.i
  If nvdWsiState = #NVD_WSI_FREE : ProcedureReturn 1 : EndIf
  If nvdWsiState <> #NVD_WSI_ACQUIRED Or nvdWsiDevice <> device Or nvdWsiTargetGeneration <> targetGeneration
    ProcedureReturn 0
  EndIf
  imageKey = avkWsiImageKey(device, nvdWsiSwapchain, nvdWsiImageIndex)
  If imageKey = 0 Or imageKey <> nvdWsiImageKey : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(avkWsiAcquiredValidate(device,nvdWsiSwapchain,nvdWsiImageIndex,imageKey)=#VK_SUCCESS)
EndProcedure

Procedure nvdWsiClear()
  nvdWsiState = #NVD_WSI_FREE : nvdWsiDevice = 0 : nvdWsiSwapchain = 0
  nvdWsiImageIndex = -1 : nvdWsiImageKey = 0 : nvdWsiTargetGeneration = 0 : nvdWsiTicket = 0
EndProcedure

Procedure.i nvdWsiSuspendAllowed(device.i,targetGeneration.i)
  If nvdWsiSaved<>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn nvdWsiRecordingAllowed(device,targetGeneration)
EndProcedure
Procedure.i nvdWsiSuspend(device.i,targetGeneration.i)
  If nvdWsiSuspendAllowed(device,targetGeneration)=0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If nvdWsiState=#NVD_WSI_FREE : ProcedureReturn #VK_SUCCESS : EndIf
  nvdWsiSavedDevice=nvdWsiDevice : nvdWsiSavedSwapchain=nvdWsiSwapchain
  nvdWsiSavedImageIndex=nvdWsiImageIndex : nvdWsiSavedImageKey=nvdWsiImageKey
  nvdWsiSaved=1 : nvdWsiClear()
  ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure nvdWsiSavedClear()
  nvdWsiSaved=0 : nvdWsiSavedDevice=0 : nvdWsiSavedSwapchain=0
  nvdWsiSavedImageIndex=-1 : nvdWsiSavedImageKey=0
EndProcedure
Procedure.i nvdWsiResume(device.i,targetGeneration.i)
  Define rc.i
  If nvdWsiSaved=0 : ProcedureReturn #VK_SUCCESS : EndIf
  If nvdWsiState<>#NVD_WSI_FREE Or device<>nvdWsiSavedDevice Or targetGeneration<1 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  rc=avkWsiAcquiredValidate(device,nvdWsiSavedSwapchain,nvdWsiSavedImageIndex,nvdWsiSavedImageKey)
  If rc<>#VK_SUCCESS : ProcedureReturn rc : EndIf
  nvdWsiDevice=device : nvdWsiSwapchain=nvdWsiSavedSwapchain
  nvdWsiImageIndex=nvdWsiSavedImageIndex : nvdWsiImageKey=nvdWsiSavedImageKey
  nvdWsiTargetGeneration=targetGeneration : nvdWsiTicket=0 : nvdWsiState=#NVD_WSI_ACQUIRED
  nvdWsiSavedClear()
  ProcedureReturn #VK_SUCCESS
EndProcedure
Procedure.i nvdWsiCancelSuspended()
  Define rc.i
  If nvdWsiSaved=0 : ProcedureReturn #VK_SUCCESS : EndIf
  If nvdWsiState<>#NVD_WSI_FREE : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiImageKey(nvdWsiSavedDevice,nvdWsiSavedSwapchain,nvdWsiSavedImageIndex)<>nvdWsiSavedImageKey : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  rc=avkWsiReleaseImage(nvdWsiSavedDevice,nvdWsiSavedSwapchain,nvdWsiSavedImageIndex)
  If rc<>#VK_SUCCESS : ProcedureReturn rc : EndIf
  nvdWsiSavedClear()
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Match the captured completed-frame identity without consuming any ownership.
; A lost/resized surface can still be rolled back, but cannot be presented.
Procedure.i nvdWsiPresentCurrent(targetGeneration.i, ticket.i, swapchain.i, imageIndex.i, imageKey.i)
  If nvdWsiState = #NVD_WSI_FREE
    ProcedureReturn Bool(ticket = 0 And swapchain = 0 And imageKey = 0)
  EndIf
  If nvdWsiState <> #NVD_WSI_COMMITTED Or nvdWsiTargetGeneration <> targetGeneration
    ProcedureReturn 0
  EndIf
  If ticket = 0 Or ticket <> nvdWsiTicket Or swapchain <> nvdWsiSwapchain Or imageIndex <> nvdWsiImageIndex Or imageKey = 0 Or imageKey <> nvdWsiImageKey
    ProcedureReturn 0
  EndIf
  If avkWsiPresentValidate(ticket) <> #VK_SUCCESS : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(avkWsiImageKey(nvdWsiDevice, swapchain, imageIndex) = imageKey)
EndProcedure

Procedure.i nvdWsiAttach(device.i, swapchain.i, imageIndex.i, targetGeneration.i)
  If nvdWsiSaved<>0 Or nvdWsiState <> #NVD_WSI_FREE Or device = 0 Or swapchain = 0 Or imageIndex < 0 Or targetGeneration < 1
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  nvdWsiImageKey = avkWsiImageKey(device, swapchain, imageIndex)
  If nvdWsiImageKey = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkWsiAcquiredValidate(device,swapchain,imageIndex,nvdWsiImageKey)<>#VK_SUCCESS
    nvdWsiImageKey=0 : ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  nvdWsiDevice = device : nvdWsiSwapchain = swapchain : nvdWsiImageIndex = imageIndex
  nvdWsiTargetGeneration = targetGeneration : nvdWsiState = #NVD_WSI_ACQUIRED
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i nvdWsiMarkReady()
  If nvdWsiState <> #NVD_WSI_ACQUIRED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiMarkRenderReady(nvdWsiDevice, nvdWsiSwapchain, nvdWsiImageIndex) <> #VK_SUCCESS
    ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  nvdWsiState = #NVD_WSI_READY
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i nvdWsiReserve()
  Define item.AnvilVkWsiPresentItem
  If nvdWsiState <> #NVD_WSI_READY : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  item\swapchain = nvdWsiSwapchain : item\imageIndex = nvdWsiImageIndex
  If avkWsiPresentReserve(nvdWsiDevice, 1, @item, @nvdWsiTicket) <> #VK_SUCCESS
    ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  nvdWsiState = #NVD_WSI_RESERVED
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i nvdWsiCommit()
  If nvdWsiState <> #NVD_WSI_RESERVED Or nvdWsiTicket = 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiPresentCommit(nvdWsiTicket) <> #VK_SUCCESS : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  nvdWsiState = #NVD_WSI_COMMITTED
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i nvdWsiComplete(success.i)
  If nvdWsiState <> #NVD_WSI_COMMITTED Or nvdWsiTicket = 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkWsiPresentComplete(nvdWsiTicket, success) <> #VK_SUCCESS : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  nvdWsiClear()
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i nvdWsiRollback()
  Define result.i
  If nvdWsiState = #NVD_WSI_FREE : ProcedureReturn #VK_SUCCESS : EndIf
  If nvdWsiState = #NVD_WSI_READY
    result = avkWsiReleaseImage(nvdWsiDevice, nvdWsiSwapchain, nvdWsiImageIndex)
    If result <> #VK_SUCCESS : ProcedureReturn result : EndIf
    nvdWsiClear() : ProcedureReturn #VK_SUCCESS
  EndIf
  If nvdWsiState = #NVD_WSI_ACQUIRED
    result = avkWsiReleaseImage(nvdWsiDevice, nvdWsiSwapchain, nvdWsiImageIndex)
    If result <> #VK_SUCCESS : ProcedureReturn result : EndIf
    nvdWsiClear() : ProcedureReturn #VK_SUCCESS
  EndIf
  result = avkWsiPresentRollback(nvdWsiTicket)
  If result <> #VK_SUCCESS : ProcedureReturn result : EndIf
  nvdWsiTicket = 0
  nvdWsiState = #NVD_WSI_READY
  result = avkWsiReleaseImage(nvdWsiDevice, nvdWsiSwapchain, nvdWsiImageIndex)
  If result <> #VK_SUCCESS : ProcedureReturn result : EndIf
  nvdWsiClear()
  ProcedureReturn #VK_SUCCESS
EndProcedure
