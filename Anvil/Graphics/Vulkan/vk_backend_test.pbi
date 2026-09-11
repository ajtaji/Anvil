; ======================================================================
;  The explicit test backend -- state and a call log, and NO PIXELS
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This backend owns no GPU and it DOES NOT WRITE ONE BYTE OF ANY IMAGE.
; It records what the engine asked it to do - the address, the extent,
; the pitch and the exact clear word - so a desk gate can check the call
; stream, the ordering and the state machine without a board, and can
; then check that the image memory is still exactly as the test left it.
;
; That last property is the point. A test backend that filled the image
; would make a green gate that proved the GATE writes pixels, not that
; the driver does. The only thing that may ever write an image here is
; real V3D, and that proof lives on the board.
;
; It can also HOLD a submission, so the fence state machine, the pending
; command-buffer state, the resource retention and the refusal to
; destroy in-flight objects are all reachable from a desk gate. Real
; asynchrony on the Pi is the V3D backend's own bounded wait; holding
; here models the observable contract, not the hardware.

XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

Global avkTbHeapBase.i = 0
Global avkTbHeapBytes.i = 0
Global avkTbMaxDim.i = 4096
Global avkTbRowAlign.i = 64
Global avkTbClearW.i = 0
Global avkTbClearH.i = 0
Global avkTbHold.i = 0
Global avkTbBusy.i = 0
Global avkTbFail.i = 0
Global avkTbTicks.i = 0
Global avkTbCalls.i = 0
Global avkTbPolls.i = 0
Global avkTbLastBase.i = 0
Global avkTbLastBytes.i = 0
Global avkTbLastW.i = 0
Global avkTbLastH.i = 0
Global avkTbLastPitch.i = 0
Global avkTbLastColor.i = 0
Global avkTbNative.i = 0

; Declare the window this backend suballocates. It is ordinary DRAM the
; caller owns; the backend never touches it.
Procedure AnvilVkTestBackendHeap(base.i, bytes.i)
  avkTbHeapBase = base
  avkTbHeapBytes = bytes
EndProcedure

Procedure AnvilVkTestBackendLimits(maxDim.i, rowAlign.i)
  If maxDim > 0 : avkTbMaxDim = maxDim : EndIf
  If rowAlign > 0 : avkTbRowAlign = rowAlign : EndIf
EndProcedure

; Restrict the extent this backend will clear, the way the Pi 4 backend
; is restricted to the render geometry Neon was initialised with. Zero
; means "any extent that fits".
Procedure AnvilVkTestBackendClearExtent(w.i, h.i)
  avkTbClearW = w
  avkTbClearH = h
EndProcedure

; While hold is 1 a submitted job stays outstanding until it is cleared.
Procedure AnvilVkTestBackendHold(on.i)
  If on <> 0 : avkTbHold = 1 : Else : avkTbHold = 0 : EndIf
EndProcedure

; Make the next submission fail with this native code, as a device fault.
Procedure AnvilVkTestBackendFailNext(code.i)
  avkTbFail = code
EndProcedure

Procedure.i AnvilVkTestBackendCalls()
  ProcedureReturn avkTbCalls
EndProcedure

Procedure.i AnvilVkTestBackendPolls()
  ProcedureReturn avkTbPolls
EndProcedure

Procedure.i AnvilVkTestBackendLastBase()
  ProcedureReturn avkTbLastBase
EndProcedure

Procedure.i AnvilVkTestBackendLastBytes()
  ProcedureReturn avkTbLastBytes
EndProcedure

Procedure.i AnvilVkTestBackendLastWidth()
  ProcedureReturn avkTbLastW
EndProcedure

Procedure.i AnvilVkTestBackendLastHeight()
  ProcedureReturn avkTbLastH
EndProcedure

Procedure.i AnvilVkTestBackendLastPitch()
  ProcedureReturn avkTbLastPitch
EndProcedure

Procedure.i AnvilVkTestBackendLastColor()
  ProcedureReturn avkTbLastColor
EndProcedure

Procedure.i avkBackendCaps()
  If avkTbHeapBase <= 0 Or avkTbHeapBytes <= 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR
EndProcedure

Procedure.i avkBackendName()
  ProcedureReturn "the explicit Anvil test backend: it models Vulkan object and submission state, owns no GPU, and never writes a pixel of any image"
EndProcedure

Procedure.i avkBackendPrepare()
  If avkTbHeapBase <= 0 Or avkTbHeapBytes <= 0 : ProcedureReturn #VK_ERROR_INITIALIZATION_FAILED : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendHeapBase()
  ProcedureReturn avkTbHeapBase
EndProcedure

Procedure.i avkBackendHeapBytes()
  ProcedureReturn avkTbHeapBytes
EndProcedure

; Two types over one heap: the plain device-local one, and a host-visible
; host-coherent view of the same memory. That is the truth on a part
; where the GPU and the processor share DRAM, and it lets a test choose
; an index and be refused for a wrong one.
Procedure.i avkBackendMemoryTypeCount()
  ProcedureReturn 2
EndProcedure

Procedure.i avkBackendMemoryTypeFlags(index.i)
  If index = 0 : ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT : EndIf
  If index = 1
    ProcedureReturn #VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | #VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendMemoryTypeHeap(index.i)
  ProcedureReturn 0
EndProcedure

Procedure.i avkBackendHeapCount()
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendHeapSizeOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn avkTbHeapBytes
EndProcedure

Procedure.i avkBackendHeapFlagsOf(index.i)
  If index <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn #VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
EndProcedure

Procedure.i avkBackendImageAlignment()
  ProcedureReturn 4096
EndProcedure

Procedure.i avkBackendRowPitchFor(width.i)
  ProcedureReturn (((width * 4) + avkTbRowAlign - 1) / avkTbRowAlign) * avkTbRowAlign
EndProcedure

Procedure.i avkBackendMaxImageDimension2D()
  ProcedureReturn avkTbMaxDim
EndProcedure

Procedure.i avkBackendClearSupported(base.i, bytes.i, w.i, h.i, pitch.i)
  If base <= 0 Or bytes <= 0 : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If pitch < (w * 4) Or (pitch * h) > bytes : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkTbClearW <> 0 And w <> avkTbClearW : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  If avkTbClearH <> 0 And h <> avkTbClearH : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkBackendSubmitClear(base.i, bytes.i, w.i, h.i, pitch.i, bgra.i)
  avkTbCalls = avkTbCalls + 1
  avkTbLastBase = base
  avkTbLastBytes = bytes
  avkTbLastW = w
  avkTbLastH = h
  avkTbLastPitch = pitch
  avkTbLastColor = bgra
  avkTbTicks = avkTbTicks + 1
  If avkTbFail <> 0
    avkTbNative = avkTbFail
    avkTbFail = 0
    ProcedureReturn -1
  EndIf
  avkTbNative = 0
  ; NOTHING IS WRITTEN TO `base`. See the header.
  If avkTbHold <> 0
    avkTbBusy = 1
    ProcedureReturn #ANVIL_VK_JOB_PENDING
  EndIf
  avkTbBusy = 0
  ProcedureReturn #ANVIL_VK_JOB_DONE
EndProcedure

Procedure.i avkBackendPoll()
  avkTbPolls = avkTbPolls + 1
  avkTbTicks = avkTbTicks + 1
  If avkTbBusy <> 0 And avkTbHold <> 0 : ProcedureReturn 0 : EndIf
  avkTbBusy = 0
  ProcedureReturn 1
EndProcedure

Procedure.i avkBackendLastNativeError()
  ProcedureReturn avkTbNative
EndProcedure

; A counter, not a clock. It advances one microsecond per backend call,
; so a gate's timeouts are deterministic and a wait cannot spin forever.
Procedure.i avkBackendTicksUs()
  avkTbTicks = avkTbTicks + 1
  ProcedureReturn avkTbTicks
EndProcedure
