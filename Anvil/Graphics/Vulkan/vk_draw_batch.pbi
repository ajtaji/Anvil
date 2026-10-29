; Backend-local execution compaction, after whole-list semantic admission.
; Caller keeps the original draw list and resource ledger alive. Only use for
; triangle pipelines without draw/primitive-ID shader inputs or side effects.
; This helper never edits source records, referenced bindings or push bytes.
XIncludeFile "Anvil/Graphics/Vulkan/vk_foundation.pbi"

Procedure.i avkBatchBytesEqual(a.i, b.i, bytes.i)
  Define offset.i
  If bytes < 0 : ProcedureReturn 0 : EndIf
  If bytes = 0 : ProcedureReturn 1 : EndIf
  If a = 0 Or b = 0 : ProcedureReturn 0 : EndIf
  If a = b : ProcedureReturn 1 : EndIf
  While offset + 8 <= bytes
    If PeekI(a + offset) <> PeekI(b + offset) : ProcedureReturn 0 : EndIf
    offset = offset + 8
  Wend
  While offset < bytes
    If PeekA(a + offset) <> PeekA(b + offset) : ProcedureReturn 0 : EndIf
    offset = offset + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilVkDrawCanMerge(*a.AnvilVkBackendDraw, *b.AnvilVkBackendDraw, topology.i)
  Define offset.i
  If *a = 0 Or *b = 0 Or topology <> #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST : ProcedureReturn 0 : EndIf
  If *a\kind <> #ANVIL_VK_RENDER_OP_DRAW Or *b\kind <> #ANVIL_VK_RENDER_OP_DRAW Or *a\sampleMask = 0 Or *b\sampleMask = 0 : ProcedureReturn 0 : EndIf
  If *a\indexBase <> 0 Or *b\indexBase <> 0 Or *a\instanceCount <> 1 Or *b\instanceCount <> 1 Or *a\firstInstance <> 0 Or *b\firstInstance <> 0 : ProcedureReturn 0 : EndIf
  If *a\vertexCount < 1 Or *b\vertexCount < 1 Or *a\vertexCount > $7FFFFFFF Or *b\vertexCount > $7FFFFFFF : ProcedureReturn 0 : EndIf
  If (*a\vertexCount % 3) <> 0 Or (*b\vertexCount % 3) <> 0 Or *a\vertexCount > $7FFFFFFF - *b\vertexCount : ProcedureReturn 0 : EndIf
  If *a\firstVertex < 0 Or *a\firstVertex > $FFFFFFFF - *a\vertexCount Or *b\firstVertex <> *a\firstVertex + *a\vertexCount : ProcedureReturn 0 : EndIf
  ; All scalar state must match. Exclude only the concatenated range and the
  ; three owned snapshots whose addresses differ even when values are equal.
  While offset < SizeOf(AnvilVkBackendDraw)
    If offset <> OffsetOf(AnvilVkBackendDraw\bindings) And offset <> OffsetOf(AnvilVkBackendDraw\vertexCount) And offset <> OffsetOf(AnvilVkBackendDraw\firstVertex) And offset <> OffsetOf(AnvilVkBackendDraw\maxVertex) And offset <> OffsetOf(AnvilVkBackendDraw\pushBase) And offset <> OffsetOf(AnvilVkBackendDraw\sampledImage)
      If PeekI(*a + offset) <> PeekI(*b + offset) : ProcedureReturn 0 : EndIf
    EndIf
    offset = offset + 8
  Wend
  If avkBatchBytesEqual(*a\bindings, *b\bindings, *a\bindingCount * SizeOf(AnvilVkBackendBinding)) = 0 : ProcedureReturn 0 : EndIf
  If avkBatchBytesEqual(*a\pushBase, *b\pushBase, *a\pushBytes) = 0 : ProcedureReturn 0 : EndIf
  If *a\sampledImage <> *b\sampledImage
    If avkBatchBytesEqual(*a\sampledImage, *b\sampledImage, SizeOf(AnvilVkBackendSampledImage)) = 0 : ProcedureReturn 0 : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure
