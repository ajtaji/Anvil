; ======================================================================
;  Vulkan device memory and images -- the portable resource engine
; ======================================================================
; SPDX-License-Identifier: MIT
;
; Target-neutral. Nothing here knows a V3D register, a packet, a tiling or
; a display. Every physical fact it needs - where the device heap is, what
; a row pitch has to be, what alignment an image needs - is asked of the
; backend seam declared in vk_foundation.pbi.
;
; Semantics are the Vulkan specification's:
;   https://docs.vulkan.org/spec/latest/chapters/memory.html
;   https://docs.vulkan.org/spec/latest/chapters/resources.html
; read for the allocation, requirements, binding and layout rules. No
; implementation source was consulted or translated.
;
; WHAT THIS SLICE IMPLEMENTS is exactly one image shape:
;   VK_IMAGE_TYPE_2D, VK_FORMAT_B8G8R8A8_UNORM, VK_IMAGE_TILING_LINEAR,
;   one mip level, one array layer, VK_SAMPLE_COUNT_1_BIT,
;   VK_SHARING_MODE_EXCLUSIVE, usage within TRANSFER_SRC | TRANSFER_DST.
; Everything else is refused with a real error code and a whole sentence.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

; SIXTEEN ALLOCATIONS, raised from eight when the descriptor path and the
; split vertex layout arrived. This table holds the APPLICATION's
; VkDeviceMemory objects AND the internal allocation each compiled
; pipeline takes for its shaders, which no handle names - so a program
; with four pipelines and five allocations needs nine slots, and both
; instruments in this tree reached exactly that. A limit an instrument
; sits on refuses the next honest use of it, and the failure it produces
; is VK_ERROR_OUT_OF_DEVICE_MEMORY on a heap with almost all of itself
; still free, which reads as the wrong problem entirely.
#ANVIL_VK_MAX_MEMORY = 16
#ANVIL_VK_MAX_IMAGES = 8

; BGRA8 is four bytes per texel. This is the one format this slice knows,
; and the constant exists so the arithmetic below names it rather than
; scattering a 4 that could be anything.
#ANVIL_VK_BGRA8_TEXEL_BYTES = 4

Global Dim avkMemLive.a[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemGen.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemDev.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemType.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemOffset.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemSize.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemBinds.i[#ANVIL_VK_MAX_MEMORY + 1]
Global Dim avkMemInFlight.i[#ANVIL_VK_MAX_MEMORY + 1]
; 1 for an allocation this implementation made for itself - a compiled
; pipeline's shaders and records. No handle names one; see INTERNAL
; ALLOCATIONS below.
Global Dim avkMemInternal.a[#ANVIL_VK_MAX_MEMORY + 1]

Global Dim avkImgLive.a[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgGen.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgDev.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgW.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgH.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgUsage.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgPitch.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgSize.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgAlign.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgMemory.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgMemSlot.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgMemOffset.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgBound.a[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgLayout.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgOwnerQf.i[#ANVIL_VK_MAX_IMAGES + 1]
Global Dim avkImgInFlight.i[#ANVIL_VK_MAX_IMAGES + 1]

Global avkHeapReady.i = 0
Global avkHeapBase.i = 0
Global avkHeapBytes.i = 0

Procedure.i avkMemSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_DEVICE_MEMORY, #ANVIL_VK_MAX_MEMORY)
  If s = 0 Or avkMemLive[s] = 0 Or avkMemGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ; An internal allocation has no handle, so a token that reaches one is
  ; a forgery or a slot reused after a pipeline took it. Either way it is
  ; not this caller's memory and it is refused here rather than in every
  ; entry point that takes a VkDeviceMemory.
  If avkMemInternal[s] <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkImgSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_IMAGE, #ANVIL_VK_MAX_IMAGES)
  If s = 0 Or avkImgLive[s] = 0 Or avkImgGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

; ----------------------------------------------------------------------
;  THE DEVICE HEAP.
;
;  One heap, taken whole from the backend, suballocated here. The search
;  is first fit over the LIVE allocations rather than a bump pointer, so
;  a freed allocation is reusable immediately and in any order - which is
;  the property "resource reuse" actually means, and a bump allocator
;  does not have it.
; ----------------------------------------------------------------------
Procedure.i avkHeapBind()
  If avkHeapReady <> 0 : ProcedureReturn #VK_SUCCESS : EndIf
  avkHeapBase = avkBackendHeapBase()
  avkHeapBytes = avkBackendHeapBytes()
  If avkHeapBase <= 0 Or avkHeapBytes <= 0
    avkHeapBase = 0
    avkHeapBytes = 0
    ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED
  EndIf
  avkHeapReady = 1
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Returns a byte offset into the heap, or -1 when no run of `bytes` at
; `align` is free. The loop restarts whenever it is pushed past a live
; allocation, so the answer does not depend on table order.
Procedure.i avkHeapAlloc(bytes.i, align.i)
  Define off.i
  Define moved.i
  Define i.i
  Define guard.i
  If bytes <= 0 : ProcedureReturn -1 : EndIf
  If align < 1 : align = 1 : EndIf
  off = 0
  moved = 1
  guard = 0
  While moved <> 0
    moved = 0
    guard = guard + 1
    If guard > (#ANVIL_VK_MAX_MEMORY + 2) : ProcedureReturn -1 : EndIf
    off = ((off + align - 1) / align) * align
    If off < 0 Or off > avkHeapBytes : ProcedureReturn -1 : EndIf
    If (avkHeapBytes - off) < bytes : ProcedureReturn -1 : EndIf
    i = 1
    While i <= #ANVIL_VK_MAX_MEMORY
      If avkMemLive[i] <> 0
        If off < (avkMemOffset[i] + avkMemSize[i]) And (off + bytes) > avkMemOffset[i]
          off = avkMemOffset[i] + avkMemSize[i]
          moved = 1
        EndIf
      EndIf
      i = i + 1
    Wend
  Wend
  ProcedureReturn off
EndProcedure

; ----------------------------------------------------------------------
;  MEMORY TYPES.
;
;  The backend enumerates them; this layer only checks indices and the
;  memoryTypeBits an image asks for. Every type this slice can expose is
;  host visible, because the whole point of the first slice is that a
;  person can read the pixels back and compare them.
; ----------------------------------------------------------------------
Procedure.i AnvilVkMemoryTypeCount()
  ProcedureReturn avkBackendMemoryTypeCount()
EndProcedure

Procedure.i AnvilVkMemoryTypeFlags(index.i)
  If index < 0 Or index >= avkBackendMemoryTypeCount() : ProcedureReturn 0 : EndIf
  ProcedureReturn avkBackendMemoryTypeFlags(index)
EndProcedure

; Every memory type is acceptable for this slice's one linear image, so
; the mask is simply "all the types that exist". It is computed rather
; than written down, so adding a type to a backend cannot leave a stale
; literal behind.
Procedure.i avkImageMemoryTypeBits()
  Define n.i
  Define bits.i
  Define i.i
  n = avkBackendMemoryTypeCount()
  bits = 0
  i = 0
  While i < n
    bits = bits | (1 << i)
    i = i + 1
  Wend
  ProcedureReturn bits
EndProcedure

Procedure.i AnvilVkMemoryAllocate(device.i, size.i, typeIndex.i, *out)
  Define d.i
  Define s.i
  Define off.i
  Define rc.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If size <= 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateMemory was asked for an allocation of zero or negative bytes (Anvil code -20001, invalid argument); VkMemoryAllocateInfo.allocationSize must be greater than zero, so check the size the caller computed from vkGetImageMemoryRequirements.")
  EndIf
  If typeIndex < 0 Or typeIndex >= avkBackendMemoryTypeCount()
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkAllocateMemory was given a memory type index this device does not have (Anvil code -20001, invalid argument); call vkGetPhysicalDeviceMemoryProperties and choose an index below memoryTypeCount before allocating.")
  EndIf
  rc = avkHeapBind()
  If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_MEMORY And avkMemLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_MEMORY : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  off = avkHeapAlloc(size, avkBackendImageAlignment())
  If off < 0 : ProcedureReturn #VK_ERROR_OUT_OF_DEVICE_MEMORY : EndIf
  avkMemGen[s] = avkNextGen(avkMemGen[s])
  avkMemLive[s] = 1
  avkMemDev[s] = d
  avkMemType[s] = typeIndex
  avkMemOffset[s] = off
  avkMemSize[s] = size
  avkMemBinds[s] = 0
  avkMemInFlight[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_DEVICE_MEMORY, s, avkMemGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

; ----------------------------------------------------------------------
;  INTERNAL ALLOCATIONS.
;
;  A pipeline's compiled shaders, its shader record and its uniform
;  blocks have to live in memory the GPU can reach, which on this device
;  is the same heap the application allocates from. They are NOT a
;  VkDeviceMemory: no handle names one, vkFreeMemory cannot reach one and
;  vkGetPhysicalDeviceMemoryProperties does not hide one - the heap size
;  it reports is the whole window, and an internal allocation is simply
;  part of it that is in use, the way a driver's own objects always are.
;
;  They take ordinary slots in the same table so that avkHeapAlloc's
;  overlap search sees them. That is the whole reason they are here and
;  not in a table of their own: two allocators over one heap is a bug
;  waiting for the day the two ranges meet.
; ----------------------------------------------------------------------
; Returns a memory slot, or 0. The caller has already called avkHeapBind.
Procedure.i avkInternalAlloc(bytes.i)
  Define s.i
  Define off.i
  If bytes <= 0 : ProcedureReturn 0 : EndIf
  If avkHeapReady = 0 : ProcedureReturn 0 : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_MEMORY And avkMemLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_MEMORY : ProcedureReturn 0 : EndIf
  off = avkHeapAlloc(bytes, avkBackendImageAlignment())
  If off < 0 : ProcedureReturn 0 : EndIf
  avkMemGen[s] = avkNextGen(avkMemGen[s])
  avkMemLive[s] = 1
  avkMemDev[s] = 0
  avkMemType[s] = 0
  avkMemOffset[s] = off
  avkMemSize[s] = bytes
  avkMemBinds[s] = 0
  avkMemInFlight[s] = 0
  avkMemInternal[s] = 1
  ProcedureReturn s
EndProcedure

Procedure avkInternalFree(s.i)
  If s < 1 Or s > #ANVIL_VK_MAX_MEMORY
    ProcedureReturn
  EndIf
  If avkMemInternal[s] = 0
    ProcedureReturn
  EndIf
  avkMemLive[s] = 0
  avkMemInternal[s] = 0
EndProcedure

Procedure.i avkInternalBase(s.i)
  If s < 1 Or s > #ANVIL_VK_MAX_MEMORY : ProcedureReturn 0 : EndIf
  If avkMemInternal[s] = 0 Or avkHeapReady = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkHeapBase + avkMemOffset[s]
EndProcedure

; The ARM address of an allocation's first byte. This is an Anvil answer,
; not a Vulkan one: core 1.0's way to reach memory is vkMapMemory, which
; this slice does not implement. It is here because the heap is already
; identity mapped and a diagnostic has to be able to read the pixels back
; without pretending a mapping happened.
Procedure.i AnvilVkMemoryAddress(memory.i)
  Define s.i
  s = avkMemSlot(memory)
  If s = 0 : ProcedureReturn 0 : EndIf
  If avkHeapReady = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkHeapBase + avkMemOffset[s]
EndProcedure

Procedure.i AnvilVkMemorySize(memory.i)
  Define s.i
  s = avkMemSlot(memory)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkMemSize[s]
EndProcedure

; vkFreeMemory returns void, so a refusal cannot be a return value. It is
; recorded as a fault and the allocation is LEFT ALONE - the one thing
; that must never happen is releasing memory an image still points at.
Procedure AnvilVkMemoryFree(device.i, memory.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkMemSlot(memory)
  If s = 0
    If memory <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkFreeMemory was given a VkDeviceMemory handle that is not live on this device (Anvil code -20002, stale or foreign handle); the allocation was left untouched. A handle that has already been freed does not come back, so check for a double free.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkMemDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkFreeMemory was called with a device that does not own this allocation (Anvil code -20003, wrong parent); the allocation was left untouched. Free memory through the same VkDevice that vkAllocateMemory returned it from.")
    ProcedureReturn
  EndIf
  If avkMemInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkFreeMemory was called while a submitted command buffer still reads or writes this allocation (Anvil code -20004, resource in use); the allocation was left untouched. Wait on the submission's fence with vkWaitForFences, or call vkDeviceWaitIdle, before freeing.")
    ProcedureReturn
  EndIf
  If avkMemBinds[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkFreeMemory was called while a VkImage is still bound to this allocation (Anvil code -20004, resource still bound); the allocation was left untouched. Destroy every image bound to an allocation with vkDestroyImage before freeing it.")
    ProcedureReturn
  EndIf
  avkMemLive[s] = 0
EndProcedure

; ----------------------------------------------------------------------
;  IMAGES.
; ----------------------------------------------------------------------
Procedure.i AnvilVkImageCreate(device.i, width.i, height.i, format.i, tiling.i, usage.i, initialLayout.i, *out)
  Define d.i
  Define s.i
  Define pitch.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If format <> #VK_FORMAT_B8G8R8A8_UNORM
    avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED, "vkCreateImage was asked for a format this implementation does not support (VkResult -11, VK_ERROR_FORMAT_NOT_SUPPORTED); the only image format Anvil implements today is VK_FORMAT_B8G8R8A8_UNORM, so ask vkGetPhysicalDeviceFormatProperties before choosing one.")
    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
  EndIf
  If tiling <> #VK_IMAGE_TILING_LINEAR
    avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED, "vkCreateImage was asked for VK_IMAGE_TILING_OPTIMAL (VkResult -11, VK_ERROR_FORMAT_NOT_SUPPORTED); Anvil implements only VK_IMAGE_TILING_LINEAR, because the tiled layouts this GPU uses are not written yet and a linear image is the one whose bytes a reader can check.")
    ProcedureReturn #VK_ERROR_FORMAT_NOT_SUPPORTED
  EndIf
  If width < 1 Or height < 1 Or width > avkBackendMaxImageDimension2D() Or height > avkBackendMaxImageDimension2D()
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImage was given an extent outside this device's limits (Anvil code -20001, invalid argument); width and height must be at least one and no more than maxImageDimension2D, which vkGetPhysicalDeviceProperties reports.")
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT))) <> 0 Or usage = 0
    avkFault(#ANVIL_VK_ERR_UNSUPPORTED, "vkCreateImage was asked for an image usage Anvil does not implement (Anvil code -20005, unsupported); only VK_IMAGE_USAGE_TRANSFER_SRC_BIT and VK_IMAGE_USAGE_TRANSFER_DST_BIT exist here, because there is no sampler, no storage image and no attachment path yet.")
    ProcedureReturn #ANVIL_VK_ERR_UNSUPPORTED
  EndIf
  If initialLayout <> #VK_IMAGE_LAYOUT_UNDEFINED And initialLayout <> #VK_IMAGE_LAYOUT_PREINITIALIZED
    avkFault(#ANVIL_VK_ERR_ARGS, "vkCreateImage was given an initialLayout that the specification does not permit (Anvil code -20001, invalid argument); VkImageCreateInfo.initialLayout must be VK_IMAGE_LAYOUT_UNDEFINED or VK_IMAGE_LAYOUT_PREINITIALIZED.")
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_IMAGES And avkImgLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_IMAGES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  pitch = avkBackendRowPitchFor(width)
  If pitch < (width * #ANVIL_VK_BGRA8_TEXEL_BYTES)
    avkFault(#VK_ERROR_INITIALIZATION_FAILED, "the graphics backend answered vkCreateImage with a row pitch narrower than one row of the image (VkResult -3, VK_ERROR_INITIALIZATION_FAILED); no image was created. This is a backend defect, not a caller error - check avkBackendRowPitchFor for the linked backend.")
    ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED
  EndIf
  avkImgGen[s] = avkNextGen(avkImgGen[s])
  avkImgLive[s] = 1
  avkImgDev[s] = d
  avkImgW[s] = width
  avkImgH[s] = height
  avkImgUsage[s] = usage
  avkImgPitch[s] = pitch
  avkImgSize[s] = pitch * height
  avkImgAlign[s] = avkBackendImageAlignment()
  avkImgMemory[s] = #VK_NULL_HANDLE
  avkImgMemSlot[s] = 0
  avkImgMemOffset[s] = 0
  avkImgBound[s] = 0
  avkImgLayout[s] = initialLayout
  avkImgOwnerQf[s] = #ANVIL_VK_QUEUE_FAMILY
  avkImgInFlight[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_IMAGE, s, avkImgGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i AnvilVkImageSize(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkImgSize[s]
EndProcedure

Procedure.i AnvilVkImageAlignment(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkImgAlign[s]
EndProcedure

Procedure.i AnvilVkImageRowPitch(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkImgPitch[s]
EndProcedure

Procedure.i AnvilVkImageLayout(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ProcedureReturn avkImgLayout[s]
EndProcedure

Procedure.i AnvilVkImageQueueFamily(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ProcedureReturn avkImgOwnerQf[s]
EndProcedure

; The ARM address of the image's first texel, or 0 while it is unbound.
Procedure.i AnvilVkImageAddress(image.i)
  Define s.i
  s = avkImgSlot(image)
  If s = 0 Or avkImgBound[s] = 0 : ProcedureReturn 0 : EndIf
  If avkHeapReady = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkHeapBase + avkMemOffset[avkImgMemSlot[s]] + avkImgMemOffset[s]
EndProcedure

Procedure.i AnvilVkImageBindMemory(device.i, image.i, memory.i, memoryOffset.i)
  Define d.i
  Define s.i
  Define m.i
  d = avkDevSlot(device)
  s = avkImgSlot(image)
  m = avkMemSlot(memory)
  If d = 0 Or s = 0 Or m = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkImgDev[s] <> d Or avkMemDev[m] <> d
    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, "vkBindImageMemory was given an image and an allocation that do not both belong to the VkDevice it was called on (Anvil code -20003, wrong parent); bind an image to memory allocated from the same device.")
  EndIf
  If avkImgBound[s] <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "vkBindImageMemory was called on an image that is already bound (Anvil code -20004, already bound); a non-sparse image may be bound exactly once, and rebinding is not a way to move it. Create a second image if a second allocation is wanted.")
  EndIf
  If (avkImgAlign[s] < 1) Or ((memoryOffset % avkImgAlign[s]) <> 0)
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindImageMemory was given a memoryOffset that is not a multiple of the alignment vkGetImageMemoryRequirements reported (Anvil code -20001, misaligned bind); round the offset up to VkMemoryRequirements.alignment before binding.")
  EndIf
  If memoryOffset < 0 Or memoryOffset > avkMemSize[m]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindImageMemory was given a memoryOffset outside the allocation (Anvil code -20001, offset out of range); the offset must be inside the VkDeviceMemory it names.")
  EndIf
  ; Written as a difference so an offset plus size that wraps cannot pass.
  If (avkMemSize[m] - memoryOffset) < avkImgSize[s]
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindImageMemory was asked to place an image past the end of its allocation (Anvil code -20001, allocation too small); VkMemoryRequirements.size bytes must fit between memoryOffset and the end of the VkDeviceMemory.")
  EndIf
  If (avkImageMemoryTypeBits() & (1 << avkMemType[m])) = 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "vkBindImageMemory was given memory of a type this image cannot use (Anvil code -20001, incompatible memory type); the allowed indices are the set bits of VkMemoryRequirements.memoryTypeBits.")
  EndIf
  avkImgMemory[s] = memory
  avkImgMemSlot[s] = m
  avkImgMemOffset[s] = memoryOffset
  avkImgBound[s] = 1
  avkMemBinds[m] = avkMemBinds[m] + 1
  ProcedureReturn #VK_SUCCESS
EndProcedure

; vkDestroyImage returns void; a refusal is recorded and the image stays.
Procedure AnvilVkImageDestroy(device.i, image.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkImgSlot(image)
  If s = 0
    If image <> #VK_NULL_HANDLE
      avkFault(#ANVIL_VK_ERR_HANDLE, "vkDestroyImage was given a VkImage handle that is not live on this device (Anvil code -20002, stale or foreign handle); nothing was destroyed. An image handle does not come back after it is destroyed, so check for a double destroy.")
    EndIf
    ProcedureReturn
  EndIf
  If d = 0 Or avkImgDev[s] <> d
    avkFault(#ANVIL_VK_ERR_OWNER, "vkDestroyImage was called with a device that does not own this image (Anvil code -20003, wrong parent); nothing was destroyed. Destroy an image through the VkDevice that created it.")
    ProcedureReturn
  EndIf
  If avkImgInFlight[s] <> 0
    avkFault(#ANVIL_VK_ERR_STATE, "vkDestroyImage was called while a submitted command buffer still references this image (Anvil code -20004, resource in use); nothing was destroyed. Wait on the submission's fence with vkWaitForFences, or call vkDeviceWaitIdle, before destroying it.")
    ProcedureReturn
  EndIf
  If avkImgBound[s] <> 0
    avkMemBinds[avkImgMemSlot[s]] = avkMemBinds[avkImgMemSlot[s]] - 1
  EndIf
  avkImgLive[s] = 0
  avkImgBound[s] = 0
EndProcedure
