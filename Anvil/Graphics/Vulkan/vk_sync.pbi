; ======================================================================
;  Vulkan fences -- the host/device completion contract
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. Read from
; https://docs.vulkan.org/spec/latest/chapters/synchronization.html
; (fences: the two states, the submit-time requirement that a fence be
; unsignalled and unused, host waiting, and the reset rule). No
; implementation source was consulted or translated.
;
; A fence has exactly two states, signalled and unsignalled, and exactly
; one owner while it is in use: the submission it was given to. That
; ownership is what lets vkDestroyFence refuse instead of dangling.
;
; NOT IMPLEMENTED HERE, and refused out loud elsewhere: semaphores,
; events, timeline semaphores, and any wait that could be satisfied by
; another host thread while this one blocks.

XIncludeFile "Anvil/Graphics/Vulkan/vk_memory.pbi"

#ANVIL_VK_MAX_FENCES = 8

; vkWaitForFences takes a nanosecond timeout; the backend's clock is in
; microseconds, which is the finest unit either the V3D counter or a test
; backend can honestly offer. A timeout is therefore rounded UP to the
; next microsecond, never down: waiting slightly too long is invisible,
; and returning VK_TIMEOUT early is a fault that shows up once in ten.
#ANVIL_VK_NS_PER_US = 1000

; The wait loop is bounded twice - by the caller's timeout and by this
; poll count - so a backend whose clock never advances cannot turn
; vkWaitForFences into a hang. Hitting the bound is reported as a fault
; with its own sentence, not silently as a timeout.
#ANVIL_VK_WAIT_MAX_POLLS = 2000000

Global Dim avkFenceLive.a[#ANVIL_VK_MAX_FENCES + 1]
Global Dim avkFenceGen.i[#ANVIL_VK_MAX_FENCES + 1]
Global Dim avkFenceDev.i[#ANVIL_VK_MAX_FENCES + 1]
Global Dim avkFenceSignaled.i[#ANVIL_VK_MAX_FENCES + 1]
Global Dim avkFenceInUse.i[#ANVIL_VK_MAX_FENCES + 1]

Procedure.i avkFenceSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_FENCE, #ANVIL_VK_MAX_FENCES)
  If s = 0 Or avkFenceLive[s] = 0 Or avkFenceGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i AnvilVkFenceCreate(device.i, flags.i, *out)
  Define d.i
  Define s.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If (flags & (~#VK_FENCE_CREATE_SIGNALED_BIT)) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateFence was given a flag bit that core Vulkan 1.0 does not define (Anvil code -20001, invalid argument); the only bit in VkFenceCreateFlags is VK_FENCE_CREATE_SIGNALED_BIT.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_FENCES And avkFenceLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_FENCES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkFenceGen[s] = avkNextGen(avkFenceGen[s])
  avkFenceLive[s] = 1
  avkFenceDev[s] = d
  avkFenceInUse[s] = 0
  If (flags & #VK_FENCE_CREATE_SIGNALED_BIT) <> 0
    avkFenceSignaled[s] = 1
  Else
    avkFenceSignaled[s] = 0
  EndIf
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_FENCE, s, avkFenceGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkFenceStatus(device.i, fence.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkFenceSlot(fence)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkFenceDev[s] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkFenceSignaled[s] <> 0 : ProcedureReturn #VK_SUCCESS : EndIf
  ProcedureReturn #VK_NOT_READY
EndProcedure

; vkResetFences returns a VkResult and takes an array of handles. A fence
; that is still owned by an unfinished submission may not be reset, so
; the whole array is CHECKED BEFORE ANY OF IT IS APPLIED - a partially
; applied reset would leave the caller with no way to know how far it got.
Procedure.i AnvilVkFencesReset(device.i, count.i, *handles)
  Define d.i
  Define s.i
  Define i.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If count < 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If count = 0 : ProcedureReturn #VK_SUCCESS : EndIf
  If *handles = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  i = 0
  While i < count
    s = avkFenceSlot(PeekI(*handles + (i * 8)))
    If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
    If avkFenceDev[s] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
    If avkFenceInUse[s] <> 0
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkResetFences was given a fence that a submitted command buffer has not finished with (Anvil code -20004, fence in use); no fence in the array was reset. Wait for the fence with vkWaitForFences before resetting it.")
    EndIf
    i = i + 1
  Wend
  i = 0
  While i < count
    s = avkFenceSlot(PeekI(*handles + (i * 8)))
    avkFenceSignaled[s] = 0
    i = i + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Claim a fence for a submission. Called by the command engine only.
Procedure.i avkFenceAcquire(d.i, fence.i)
  Define s.i
  s = avkFenceSlot(fence)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkFenceDev[s] <> d : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkFenceSignaled[s] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a fence that is already signalled (Anvil code -20004, fence already signalled); nothing was submitted. A fence handed to a submission must be unsignalled, so call vkResetFences on it first.")
  EndIf
  If avkFenceInUse[s] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkQueueSubmit was given a fence that another submission has not finished with (Anvil code -20004, fence in use); nothing was submitted. One fence belongs to one outstanding submission at a time.")
  EndIf
  avkFenceInUse[s] = 1
  ProcedureReturn s
EndProcedure

Procedure avkFenceSignal(s.i)
  If s < 1 Or s > #ANVIL_VK_MAX_FENCES
    ProcedureReturn
  EndIf
  avkFenceInUse[s] = 0
  avkFenceSignaled[s] = 1
EndProcedure

; Release a fence WITHOUT signalling it: the submission it was claimed
; for never reached the hardware, so the caller's world is unchanged.
Procedure avkFenceRelease(s.i)
  If s < 1 Or s > #ANVIL_VK_MAX_FENCES
    ProcedureReturn
  EndIf
  avkFenceInUse[s] = 0
EndProcedure

; vkDestroyFence returns void; a refusal is recorded and the fence stays.
Procedure AnvilVkFenceDestroy(device.i, fence.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkFenceSlot(fence)
  If s = 0
    If fence <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyFence was given a VkFence handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed. Check for a double destroy.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkFenceDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyFence was called with a device that does not own this fence (Anvil code -20003, wrong parent); nothing was destroyed. Destroy a fence through the VkDevice that created it.")
    ProcedureReturn
  EndIf
  If avkFenceInUse[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyFence was called while a submitted command buffer has not finished with this fence (Anvil code -20004, fence in use); nothing was destroyed. Wait for the fence with vkWaitForFences before destroying it.")
    ProcedureReturn
  EndIf
  avkFenceLive[s] = 0
EndProcedure
