; Renderer-neutral Neon lifecycle binder for the resident Vulkan chrome.
; Include after the shared Neon lifecycle and the concrete Chrome provider. This file
; owns only selection/configuration and callback translation; Vulkan resource
; ownership remains in neon_vk_chrome.pbi.

Structure NeonVkLifecycleConfig
  physicalDevice.i
  device.i
  queue.i
  commandPool.i
  renderPass.i
  framebuffer.i
  width.i
  height.i
  maxQuads.i
EndStructure

Declare.i NeonVkChromeCreate(physicalDevice.i, device.i, queue.i, commandPool.i, renderPass.i, framebuffer.i, width.i, height.i, maxQuads.i)
Declare.i NeonVkChromeBegin(*clearValue)
Declare.i NeonVkChromeEnd()
Declare NeonVkChromeDestroy()
Declare.i NeonVkChromeDestroyChecked()

Global nvlConfigured.i
Global nvlPhysical.i
Global nvlDevice.i
Global nvlQueue.i
Global nvlCommandPool.i
Global nvlRenderPass.i
Global nvlFramebuffer.i
Global nvlWidth.i
Global nvlHeight.i
Global nvlMaxQuads.i
Global Dim nvlClear.l[4]

Procedure.i nvlInit()
  Protected r.i
  If nvlConfigured = 0 : ProcedureReturn #NEON_ERR_BACKEND : EndIf
  r = NeonVkChromeCreate(nvlPhysical, nvlDevice, nvlQueue, nvlCommandPool, nvlRenderPass, nvlFramebuffer, nvlWidth, nvlHeight, nvlMaxQuads)
  If r <> 0
    ; Shared lifecycle retains the failed init's cleanup obligation. The
    ; caller must use NeonShutdown(), which reaches checked destruction even
    ; while readiness is zero; configuration is released only on success.
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i nvlBegin(colour.i)
  nvlClear[0] = GraphicsF32ByteBits(Neon_R(colour))
  nvlClear[1] = GraphicsF32ByteBits(Neon_G(colour))
  nvlClear[2] = GraphicsF32ByteBits(Neon_B(colour))
  nvlClear[3] = GraphicsF32ByteBits(Neon_A(colour))
  If NeonVkChromeBegin(@nvlClear[0]) <> 0
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i nvlEnd()
  If NeonVkChromeEnd() <> 0 : ProcedureReturn #NEON_ERR_BACKEND : EndIf
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i nvlShutdown()
  If NeonVkChromeDestroyChecked() <> #NEON_OK
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  nvlConfigured = 0
  ProcedureReturn #NEON_OK
EndProcedure

; Configuration is complete before lifecycle selection. No partial config is
; published if validation or callback installation refuses.
Procedure.i NeonVkLifecycleConfigure(*cfg.NeonVkLifecycleConfig)
  Protected r.i
  If *cfg = 0 Or nvlConfigured <> 0 Or Neon_Ready() <> 0
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  If *cfg\physicalDevice = 0 Or *cfg\device = 0 Or *cfg\queue = 0 Or *cfg\commandPool = 0 Or *cfg\renderPass = 0 Or *cfg\framebuffer = 0
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  If *cfg\width < 1 Or *cfg\height < 1 Or *cfg\maxQuads < 1
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  nvlPhysical = *cfg\physicalDevice : nvlDevice = *cfg\device : nvlQueue = *cfg\queue
  nvlCommandPool = *cfg\commandPool : nvlRenderPass = *cfg\renderPass : nvlFramebuffer = *cfg\framebuffer
  nvlWidth = *cfg\width : nvlHeight = *cfg\height : nvlMaxQuads = *cfg\maxQuads
  r = NeonLifecycleInstall(@nvlInit, @nvlBegin, @nvlEnd, @nvlShutdown)
  If r <> #NEON_OK
    nvlPhysical = 0 : nvlDevice = 0 : nvlQueue = 0 : nvlCommandPool = 0
    nvlRenderPass = 0 : nvlFramebuffer = 0 : nvlWidth = 0 : nvlHeight = 0 : nvlMaxQuads = 0
    ProcedureReturn r
  EndIf
  nvlConfigured = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonVkLifecycleConfigured()
  ProcedureReturn nvlConfigured
EndProcedure

; Prepared-native-context users explicitly include neon_vk_prepared_lifecycle.pbi.
; This ordinary binder keeps its independent public-provider contract.
