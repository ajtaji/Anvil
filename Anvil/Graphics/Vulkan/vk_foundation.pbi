; ======================================================================
;  Native Vulkan object/lifecycle foundation for Anvil
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This is the executable ownership and command-buffer state engine beneath
; Anvil's public vk* entry points (vk_api.pbi). It owns handles, parents,
; generations and command-buffer states, and it contains no V3D register,
; packet, address or display assumption of any kind.
;
; THE BACKEND IS A SEAM AND IT IS STATIC. Exactly one backend file must be
; included by the program:
;
;   Anvil/Graphics/Vulkan/vk_backend_none.pbi   no device is enumerated
;   Anvil/Graphics/Vulkan/vk_backend_test.pbi   state only, owns no GPU
;   Anvil/Graphics/Vulkan/vk_v3d_backend.pi4    the real Pi 4 V3D backend
;
; The seam is Declared here and defined there, so a build that forgets a
; backend fails to link rather than quietly enumerating nothing. Including
; two backends declares the same procedures twice and fails as well: there
; is no run-time registration to get wrong.
;
; Semantics come from the Vulkan specification, read at
; https://docs.vulkan.org/spec/latest/chapters/fundamentals.html (object
; model, valid usage, return codes) and .../cmdbuffers.html (the command
; buffer lifecycle). Nothing is copied from any implementation.

XIncludeFile "Anvil/Graphics/Vulkan/vk_core_1_0.pbi"

; ----------------------------------------------------------------------
;  Anvil result codes.
;
;  Core Vulkan leaves most invalid usage UNDEFINED and gives a command no
;  result code for it. Anvil will not have undefined behaviour, so every
;  such case returns one of these instead. They are far outside VkResult's
;  core-1.0 range (-12 .. 5), so no caller can confuse one with a Vulkan
;  code and none of them can ever be mistaken for success.
; ----------------------------------------------------------------------
#ANVIL_VK_OK = 0
#ANVIL_VK_ERR_ARGS = -20001
#ANVIL_VK_ERR_HANDLE = -20002
#ANVIL_VK_ERR_OWNER = -20003
#ANVIL_VK_ERR_STATE = -20004
#ANVIL_VK_ERR_UNSUPPORTED = -20005

; Backend capability bits, reported by avkBackendCaps().
#ANVIL_VK_CAP_DEVICE = $0001        ; a physical device may be enumerated
#ANVIL_VK_CAP_CLEAR_COLOR = $0002   ; vkCmdClearColorImage can be executed
#ANVIL_VK_CAP_GPU = $0004           ; that execution is real GPU work

; avkBackendSubmitClear() answers.
#ANVIL_VK_JOB_DONE = 0
#ANVIL_VK_JOB_PENDING = 1

#ANVIL_VK_TYPE_INSTANCE = 1
#ANVIL_VK_TYPE_PHYSICAL_DEVICE = 2
#ANVIL_VK_TYPE_DEVICE = 3
#ANVIL_VK_TYPE_QUEUE = 4
#ANVIL_VK_TYPE_COMMAND_POOL = 5
#ANVIL_VK_TYPE_COMMAND_BUFFER = 6
#ANVIL_VK_TYPE_DEVICE_MEMORY = 7
#ANVIL_VK_TYPE_IMAGE = 8
#ANVIL_VK_TYPE_FENCE = 9

#ANVIL_VK_CB_INITIAL = 0
#ANVIL_VK_CB_RECORDING = 1
#ANVIL_VK_CB_EXECUTABLE = 2
#ANVIL_VK_CB_PENDING = 3
#ANVIL_VK_CB_INVALID = 4

#ANVIL_VK_MAX_INSTANCES = 4
#ANVIL_VK_MAX_PHYSICAL_DEVICES = 4
#ANVIL_VK_MAX_DEVICES = 4
#ANVIL_VK_MAX_QUEUES = 4
#ANVIL_VK_MAX_COMMAND_POOLS = 16
#ANVIL_VK_MAX_COMMAND_BUFFERS = 32

; The one queue family this slice exposes. It is transfer-capable and
; nothing else; a graphics or compute bit here would be a claim about
; draws and dispatches that no part of this tree implements.
#ANVIL_VK_QUEUE_FAMILY = 0

#ANVIL_VK_TOKEN_MAGIC = $564B000000000000
#ANVIL_VK_TOKEN_MAGIC_MASK = $FFFF000000000000
#ANVIL_VK_TOKEN_TYPE_MASK = $0000FF0000000000
#ANVIL_VK_TOKEN_GEN_MASK = $00000000FFFF0000
#ANVIL_VK_TOKEN_SLOT_MASK = $000000000000FFFF

; ----------------------------------------------------------------------
;  THE BACKEND SEAM.
; ----------------------------------------------------------------------
Declare.i avkBackendCaps()
Declare.i avkBackendName()
Declare.i avkBackendPrepare()
Declare.i avkBackendHeapBase()
Declare.i avkBackendHeapBytes()
Declare.i avkBackendMemoryTypeCount()
Declare.i avkBackendMemoryTypeFlags(index.i)
Declare.i avkBackendMemoryTypeHeap(index.i)
Declare.i avkBackendHeapCount()
Declare.i avkBackendHeapSizeOf(index.i)
Declare.i avkBackendHeapFlagsOf(index.i)
Declare.i avkBackendImageAlignment()
Declare.i avkBackendRowPitchFor(width.i)
Declare.i avkBackendMaxImageDimension2D()
Declare.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
Declare.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
Declare.i avkBackendPoll()
Declare.i avkBackendLastNativeError()
Declare.i avkBackendTicksUs()

; EVERY SLOT TABLE IS ONE ELEMENT LONGER THAN ITS MAXIMUM. Slot 0 means
; "no object", so live slots run 1..MAX and a table dimensioned to MAX
; would have its last slot land one element past the end. That is exactly
; what the first version of this file did, on every object type at once,
; and it is invisible until the table is full - the allocator only ever
; reaches the last slot when everything before it is taken.
Global Dim avkInstLive.a[#ANVIL_VK_MAX_INSTANCES + 1]
Global Dim avkInstGen.i[#ANVIL_VK_MAX_INSTANCES + 1]
Global Dim avkPhysLive.a[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkPhysGen.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkPhysInst.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES + 1]
Global Dim avkDevLive.a[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkDevGen.i[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkDevPhys.i[#ANVIL_VK_MAX_DEVICES + 1]
Global Dim avkQueueLive.a[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkQueueGen.i[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkQueueDev.i[#ANVIL_VK_MAX_QUEUES + 1]
Global Dim avkPoolLive.a[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolGen.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolDev.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkPoolFlags.i[#ANVIL_VK_MAX_COMMAND_POOLS + 1]
Global Dim avkCmdLive.a[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdGen.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdPool.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdLevel.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdState.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdBeginFlags.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]
Global Dim avkCmdOps.i[#ANVIL_VK_MAX_COMMAND_BUFFERS + 1]

; ----------------------------------------------------------------------
;  THE VALIDATION FAULT RECORD.
;
;  Vulkan's void commands - vkCmdPipelineBarrier, vkCmdClearColorImage,
;  vkFreeMemory, vkDestroyImage, vkDestroyFence - have no return value,
;  and the specification's answer to misuse is undefined behaviour. Anvil
;  records a numeric code and a WHOLE SENTENCE here instead, and where the
;  specification allows it (a recording error) the command buffer is moved
;  to the invalid state so vkEndCommandBuffer reports the failure. Nothing
;  in this engine ever proceeds as though a refused call had succeeded.
; ----------------------------------------------------------------------
Global avkFaultCode.i = #ANVIL_VK_OK
Global avkFaultText.i = 0
Global avkFaultCount.i = 0

Procedure.i avkFault(code.i, text.i)
  avkFaultCode = code
  avkFaultText = text
  avkFaultCount = avkFaultCount + 1
  ProcedureReturn code
EndProcedure

Procedure AnvilVkFaultClear()
  avkFaultCode = #ANVIL_VK_OK
  avkFaultText = 0
EndProcedure

Procedure.i AnvilVkFaultCode()
  ProcedureReturn avkFaultCode
EndProcedure

; A whole sentence naming the numeric code, what it means and the first
; thing to check, or 0 if no call has been refused.
Procedure.i AnvilVkFaultText()
  ProcedureReturn avkFaultText
EndProcedure

Procedure.i AnvilVkFaultCount()
  ProcedureReturn avkFaultCount
EndProcedure

Procedure.i avkNextGen(v.i)
  v = (v + 1) & $FFFF
  If v = 0 : v = 1 : EndIf
  ProcedureReturn v
EndProcedure

Procedure.i avkToken(kind.i, slot.i, gen.i)
  ProcedureReturn #ANVIL_VK_TOKEN_MAGIC | ((kind & $FF) << 40) | ((gen & $FFFF) << 16) | (slot & $FFFF)
EndProcedure

Procedure.i avkTokenKind(h.i)
  ProcedureReturn (h >> 40) & $FF
EndProcedure

Procedure.i avkTokenSlot(h.i)
  ProcedureReturn h & $FFFF
EndProcedure

Procedure.i avkTokenGen(h.i)
  ProcedureReturn (h >> 16) & $FFFF
EndProcedure

Procedure.i avkTokenShape(h.i, kind.i, cap.i)
  Define s.i
  If (h & #ANVIL_VK_TOKEN_MAGIC_MASK) <> #ANVIL_VK_TOKEN_MAGIC
    ProcedureReturn 0
  EndIf
  If avkTokenKind(h) <> kind
    ProcedureReturn 0
  EndIf
  s = avkTokenSlot(h)
  If s < 1 Or s > cap
    ProcedureReturn 0
  EndIf
  ProcedureReturn s
EndProcedure

; Read a uint32_t member without the sign of PeekL's signed 32-bit load
; leaking into a 64-bit comparison. VK_QUEUE_FAMILY_IGNORED is $FFFFFFFF
; and must compare equal to the constant of the same name.
Procedure.i avkU32(*p)
  ProcedureReturn PeekL(*p) & $FFFFFFFF
EndProcedure

Procedure.i avkInstSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_INSTANCE, #ANVIL_VK_MAX_INSTANCES)
  If s = 0 Or avkInstLive[s] = 0 Or avkInstGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkPhysSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_PHYSICAL_DEVICE, #ANVIL_VK_MAX_PHYSICAL_DEVICES)
  If s = 0 Or avkPhysLive[s] = 0 Or avkPhysGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkDevSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DEVICE, #ANVIL_VK_MAX_DEVICES)
  If s = 0 Or avkDevLive[s] = 0 Or avkDevGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkQueueSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_QUEUE, #ANVIL_VK_MAX_QUEUES)
  If s = 0 Or avkQueueLive[s] = 0 Or avkQueueGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkPoolSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_COMMAND_POOL, #ANVIL_VK_MAX_COMMAND_POOLS)
  If s = 0 Or avkPoolLive[s] = 0 Or avkPoolGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkCmdSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_COMMAND_BUFFER, #ANVIL_VK_MAX_COMMAND_BUFFERS)
  If s = 0 Or avkCmdLive[s] = 0 Or avkCmdGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; ----------------------------------------------------------------------
;  Capability answers.
;
;  AnvilVkBackendAvailable() is the production question and it is answered
;  by the linked backend, not by a flag any caller can set. A build that
;  links vk_backend_none.pbi answers 0 here and refuses instance creation
;  with VK_ERROR_INCOMPATIBLE_DRIVER, exactly as a loader does when no ICD
;  is installed.
; ----------------------------------------------------------------------
Procedure.i AnvilVkBackendAvailable()
  If (avkBackendCaps() & #ANVIL_VK_CAP_DEVICE) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 when the linked backend executes clears on a GPU, 0 when it models
; state only. A gate uses this to refuse to call a state-only backend's
; result silicon.
Procedure.i AnvilVkBackendIsGpu()
  If (avkBackendCaps() & #ANVIL_VK_CAP_GPU) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilVkBackendName()
  ProcedureReturn avkBackendName()
EndProcedure

Procedure.i AnvilVkInstanceCreate(*out)
  Define s.i
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  If AnvilVkBackendAvailable() = 0 : ProcedureReturn #VK_ERROR_INCOMPATIBLE_DRIVER : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_INSTANCES And avkInstLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_INSTANCES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES And avkPhysLive[p] <> 0 : p = p + 1 : Wend
  If p > #ANVIL_VK_MAX_PHYSICAL_DEVICES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkInstGen[s] = avkNextGen(avkInstGen[s])
  avkInstLive[s] = 1
  avkPhysGen[p] = avkNextGen(avkPhysGen[p])
  avkPhysLive[p] = 1
  avkPhysInst[p] = s
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_INSTANCE, s, avkInstGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkPhysicalEnumerate(instance.i, *count, *out)
  Define s.i
  Define p.i
  Define cap.i
  s = avkInstSlot(instance)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If *count = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES
    If avkPhysLive[p] <> 0 And avkPhysInst[p] = s : Break : EndIf
    p = p + 1
  Wend
  If *out = 0
    If p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES : PokeL(*count, 1) : Else : PokeL(*count, 0) : EndIf
    ProcedureReturn #VK_SUCCESS
  EndIf
  cap = PeekL(*count)
  If cap < 1
    PokeL(*count, 0)
    ProcedureReturn #VK_INCOMPLETE
  EndIf
  If p > #ANVIL_VK_MAX_PHYSICAL_DEVICES
    PokeL(*count, 0)
    ProcedureReturn #VK_SUCCESS
  EndIf
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_PHYSICAL_DEVICE, p, avkPhysGen[p]))
  PokeL(*count, 1)
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceCreate(physical.i, *out)
  Define p.i
  Define s.i
  Define q.i
  Define rc.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  p = avkPhysSlot(physical)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ; The backend gets its one chance to refuse before any object exists.
  rc = avkBackendPrepare()
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_DEVICES And avkDevLive[s] <> 0 : s = s + 1 : Wend
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES And avkQueueLive[q] <> 0 : q = q + 1 : Wend
  If s > #ANVIL_VK_MAX_DEVICES Or q > #ANVIL_VK_MAX_QUEUES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkDevGen[s] = avkNextGen(avkDevGen[s])
  avkDevLive[s] = 1
  avkDevPhys[s] = p
  avkQueueGen[q] = avkNextGen(avkQueueGen[q])
  avkQueueLive[q] = 1
  avkQueueDev[q] = s
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DEVICE, s, avkDevGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceQueue(device.i, *out)
  Define d.i
  Define q.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES
    If avkQueueLive[q] <> 0 And avkQueueDev[q] = d
      PokeI(*out, avkToken(#ANVIL_VK_TYPE_QUEUE, q, avkQueueGen[q]))
      ProcedureReturn #VK_SUCCESS
    EndIf
    q = q + 1
  Wend
  ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED
EndProcedure

Procedure.i AnvilVkCommandPoolCreate(device.i, flags.i, *out)
  Define d.i
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~(#VK_COMMAND_POOL_CREATE_TRANSIENT_BIT | #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT))) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_COMMAND_POOLS And avkPoolLive[p] <> 0 : p = p + 1 : Wend
  If p > #ANVIL_VK_MAX_COMMAND_POOLS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkPoolGen[p] = avkNextGen(avkPoolGen[p])
  avkPoolLive[p] = 1
  avkPoolDev[p] = d
  avkPoolFlags[p] = flags
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_COMMAND_POOL, p, avkPoolGen[p]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferAllocate(device.i, pool.i, level.i, *out)
  Define d.i
  Define p.i
  Define c.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If level <> #VK_COMMAND_BUFFER_LEVEL_PRIMARY And level <> #VK_COMMAND_BUFFER_LEVEL_SECONDARY
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS And avkCmdLive[c] <> 0 : c = c + 1 : Wend
  If c > #ANVIL_VK_MAX_COMMAND_BUFFERS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkCmdGen[c] = avkNextGen(avkCmdGen[c])
  avkCmdLive[c] = 1
  avkCmdPool[c] = p
  avkCmdLevel[c] = level
  avkCmdState[c] = #ANVIL_VK_CB_INITIAL
  avkCmdBeginFlags[c] = 0
  avkCmdOps[c] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_COMMAND_BUFFER, c, avkCmdGen[c]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferState(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ProcedureReturn avkCmdState[c]
EndProcedure
