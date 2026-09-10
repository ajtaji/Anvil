; ======================================================================
;  Native Vulkan object/lifecycle foundation for Anvil
; ======================================================================
; This is the executable ownership and command-buffer state engine beneath a
; future Vulkan entry surface. Public create-info records now have checked
; AArch64 C layout, but vk* entry procedures remain outside this bounded slice.
;
; The including program must define #ANVIL_VK_TEST_BACKEND as 0 for production
; or 1 for the explicit test backend. That backend owns no GPU and accepts
; only empty command buffers, completing them synchronously.

XIncludeFile "Anvil/Graphics/Vulkan/vk_core_1_0.pbi"

#ANVIL_VK_OK = 0
#ANVIL_VK_ERR_ARGS = -20001
#ANVIL_VK_ERR_HANDLE = -20002
#ANVIL_VK_ERR_OWNER = -20003
#ANVIL_VK_ERR_STATE = -20004
#ANVIL_VK_ERR_UNSUPPORTED = -20005

#ANVIL_VK_BACKEND_NONE = 0
#ANVIL_VK_BACKEND_TEST = 1
#ANVIL_VK_BACKEND_V3D_DEVELOPMENT = 2

#ANVIL_VK_TYPE_INSTANCE = 1
#ANVIL_VK_TYPE_PHYSICAL_DEVICE = 2
#ANVIL_VK_TYPE_DEVICE = 3
#ANVIL_VK_TYPE_QUEUE = 4
#ANVIL_VK_TYPE_COMMAND_POOL = 5
#ANVIL_VK_TYPE_COMMAND_BUFFER = 6

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
#ANVIL_VK_MAX_COMMAND_BUFFERS = 128

#ANVIL_VK_TOKEN_MAGIC = $564B000000000000
#ANVIL_VK_TOKEN_MAGIC_MASK = $FFFF000000000000
#ANVIL_VK_TOKEN_TYPE_MASK = $0000FF0000000000
#ANVIL_VK_TOKEN_GEN_MASK = $00000000FFFF0000
#ANVIL_VK_TOKEN_SLOT_MASK = $000000000000FFFF

Global Dim avkInstLive.a[#ANVIL_VK_MAX_INSTANCES]
Global Dim avkInstGen.i[#ANVIL_VK_MAX_INSTANCES]
Global Dim avkPhysLive.a[#ANVIL_VK_MAX_PHYSICAL_DEVICES]
Global Dim avkPhysGen.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES]
Global Dim avkPhysInst.i[#ANVIL_VK_MAX_PHYSICAL_DEVICES]
Global Dim avkDevLive.a[#ANVIL_VK_MAX_DEVICES]
Global Dim avkDevGen.i[#ANVIL_VK_MAX_DEVICES]
Global Dim avkDevPhys.i[#ANVIL_VK_MAX_DEVICES]
Global Dim avkQueueLive.a[#ANVIL_VK_MAX_QUEUES]
Global Dim avkQueueGen.i[#ANVIL_VK_MAX_QUEUES]
Global Dim avkQueueDev.i[#ANVIL_VK_MAX_QUEUES]
Global Dim avkPoolLive.a[#ANVIL_VK_MAX_COMMAND_POOLS]
Global Dim avkPoolGen.i[#ANVIL_VK_MAX_COMMAND_POOLS]
Global Dim avkPoolDev.i[#ANVIL_VK_MAX_COMMAND_POOLS]
Global Dim avkPoolFlags.i[#ANVIL_VK_MAX_COMMAND_POOLS]
Global Dim avkCmdLive.a[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdGen.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdPool.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdLevel.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdState.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdBeginFlags.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global Dim avkCmdOps.i[#ANVIL_VK_MAX_COMMAND_BUFFERS]
Global avkBackendKind.i = #ANVIL_VK_BACKEND_NONE

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

Procedure.i AnvilVkBackendAvailable()
  ; Production registration is deliberately absent. Development and test
  ; backends never turn this capability answer into a production claim.
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendEnable(kind.i)
  If kind <> #ANVIL_VK_BACKEND_TEST And kind <> #ANVIL_VK_BACKEND_V3D_DEVELOPMENT
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If avkBackendKind <> #ANVIL_VK_BACKEND_NONE And avkBackendKind <> kind
    ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  avkBackendKind = kind
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

Procedure.i AnvilVkBackendKind()
  ProcedureReturn avkBackendKind
EndProcedure

Procedure.i AnvilVkTestBackendEnable()
  CompilerIf #ANVIL_VK_TEST_BACKEND = 1
  ProcedureReturn avkBackendEnable(#ANVIL_VK_BACKEND_TEST)
  CompilerElse
  ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
  CompilerEndIf
EndProcedure

Procedure.i AnvilVkInstanceCreate(*out)
  Define s.i
  Define p.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  If avkBackendKind = #ANVIL_VK_BACKEND_NONE : ProcedureReturn #VK_ERROR_INCOMPATIBLE_DRIVER : EndIf
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
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, 0)
  p = avkPhysSlot(physical)
  If p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
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

Procedure.i AnvilVkCommandBufferBegin(commandBuffer.i, flags.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_INITIAL : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If (flags & (~(#VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT | #VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT | #VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT))) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If avkCmdLevel[c] = #VK_COMMAND_BUFFER_LEVEL_PRIMARY And (flags & #VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT) <> 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  avkCmdBeginFlags[c] = flags
  avkCmdOps[c] = 0
  avkCmdState[c] = #ANVIL_VK_CB_RECORDING
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkTestRecordUnsupported(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkCmdOps[c] = avkCmdOps[c] + 1
  ProcedureReturn #ANVIL_VK_OK
EndProcedure

Procedure.i AnvilVkCommandBufferEnd(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_RECORDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkCmdState[c] = #ANVIL_VK_CB_EXECUTABLE
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferReset(commandBuffer.i, flags.i)
  Define c.i
  Define p.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~#VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  p = avkCmdPool[c]
  If (avkPoolFlags[p] & #VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT) = 0
    ProcedureReturn #ANVIL_VK_ERR_STATE
  EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_PENDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkCmdState[c] = #ANVIL_VK_CB_INITIAL
  avkCmdBeginFlags[c] = 0
  avkCmdOps[c] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandPoolReset(device.i, pool.i, flags.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~#VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT)) <> 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCmdState[c] = #ANVIL_VK_CB_PENDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
    EndIf
    c = c + 1
  Wend
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      avkCmdState[c] = #ANVIL_VK_CB_INITIAL
      avkCmdBeginFlags[c] = 0
      avkCmdOps[c] = 0
    EndIf
    c = c + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkQueueSubmitEmpty(queue.i, commandBuffer.i)
  Define q.i
  Define c.i
  Define p.i
  q = avkQueueSlot(queue)
  c = avkCmdSlot(commandBuffer)
  If q = 0 Or c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  p = avkCmdPool[c]
  If avkQueueDev[q] <> avkPoolDev[p] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkCmdLevel[c] <> #VK_COMMAND_BUFFER_LEVEL_PRIMARY : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkCmdState[c] <> #ANVIL_VK_CB_EXECUTABLE : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkCmdOps[c] <> 0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  avkCmdState[c] = #ANVIL_VK_CB_PENDING
  ; The test backend has no asynchronous work. Completion is immediate.
  If (avkCmdBeginFlags[c] & #VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT) <> 0
    avkCmdState[c] = #ANVIL_VK_CB_INVALID
  Else
    avkCmdState[c] = #ANVIL_VK_CB_EXECUTABLE
  EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandBufferState(commandBuffer.i)
  Define c.i
  c = avkCmdSlot(commandBuffer)
  If c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ProcedureReturn avkCmdState[c]
EndProcedure

Procedure.i AnvilVkCommandBufferFree(device.i, pool.i, commandBuffer.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  c = avkCmdSlot(commandBuffer)
  If d = 0 Or p = 0 Or c = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d Or avkCmdPool[c] <> p : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkCmdState[c] = #ANVIL_VK_CB_PENDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  avkCmdLive[c] = 0
  avkCmdState[c] = #ANVIL_VK_CB_INVALID
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkCommandPoolDestroy(device.i, pool.i)
  Define d.i
  Define p.i
  Define c.i
  d = avkDevSlot(device)
  p = avkPoolSlot(pool)
  If d = 0 Or p = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkPoolDev[p] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  c = 1
  While c <= #ANVIL_VK_MAX_COMMAND_BUFFERS
    If avkCmdLive[c] <> 0 And avkCmdPool[c] = p
      If avkCmdState[c] = #ANVIL_VK_CB_PENDING : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
      avkCmdLive[c] = 0
      avkCmdState[c] = #ANVIL_VK_CB_INVALID
    EndIf
    c = c + 1
  Wend
  avkPoolLive[p] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkDeviceDestroy(device.i)
  Define d.i
  Define p.i
  Define q.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  p = 1
  While p <= #ANVIL_VK_MAX_COMMAND_POOLS
    If avkPoolLive[p] <> 0 And avkPoolDev[p] = d
      AnvilVkCommandPoolDestroy(device, avkToken(#ANVIL_VK_TYPE_COMMAND_POOL, p, avkPoolGen[p]))
    EndIf
    p = p + 1
  Wend
  q = 1
  While q <= #ANVIL_VK_MAX_QUEUES
    If avkQueueLive[q] <> 0 And avkQueueDev[q] = d : avkQueueLive[q] = 0 : EndIf
    q = q + 1
  Wend
  avkDevLive[d] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkInstanceDestroy(instance.i)
  Define s.i
  Define p.i
  Define d.i
  s = avkInstSlot(instance)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  d = 1
  While d <= #ANVIL_VK_MAX_DEVICES
    If avkDevLive[d] <> 0
      p = avkDevPhys[d]
      If avkPhysLive[p] <> 0 And avkPhysInst[p] = s
        AnvilVkDeviceDestroy(avkToken(#ANVIL_VK_TYPE_DEVICE, d, avkDevGen[d]))
      EndIf
    EndIf
    d = d + 1
  Wend
  p = 1
  While p <= #ANVIL_VK_MAX_PHYSICAL_DEVICES
    If avkPhysLive[p] <> 0 And avkPhysInst[p] = s : avkPhysLive[p] = 0 : EndIf
    p = p + 1
  Wend
  avkInstLive[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure
