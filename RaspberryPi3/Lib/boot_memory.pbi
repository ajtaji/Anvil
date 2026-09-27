; Pi3 fixed A/B boot layout admission, read through the ONE shared device-tree
; reader, Anvil/Core/fdt.pbi (Rule 30; vault "The shared FDT reader - fdt.pbi
; and its migration 2026-09-26", row 2). No allocations or writes. The caller
; first validates the DTB's outer span in ARM RAM. fdt.pbi must be included
; before this file.
;
; FdtCheck proves the tree well formed. What stays here is Pi 3 LOADER POLICY,
; checked after it, exactly as the private walker this replaces enforced it:
;   * the tree is at most 1 MiB and its header totalsize is exactly `total`;
;   * last_comp_version <= 17;
;   * an 8-byte-aligned reserve map, a 4-byte-aligned structure block of at
;     least 12 bytes, a non-empty strings block, and the blocks in the
;     flattened-format order reserve < structure < strings;
;   * the root's #address-cells / #size-cells, when present, are one cell
;     holding 1 or 2;
;   * every reserve-map entry, and every reg of every child of the one root
;     child named exactly "reserved-memory", keeps out of the two fixed
;     boot bands (p3bmRange);
;   * that node carries its own #address-cells and #size-cells equal to the
;     root's, and an empty ranges; its children have no children.
Procedure.i p3bmBe32(p.i)
  ProcedureReturn (PeekA(p) << 24) | (PeekA(p + 1) << 16) | (PeekA(p + 2) << 8) | PeekA(p + 3)
EndProcedure
Procedure.i p3bmName(p.i, limit.i, expected.i)
  Protected n.i
  For n = 0 To 255
    If p + n >= limit : ProcedureReturn 0 : EndIf
    If PeekA(p + n) <> PeekA(expected + n) : ProcedureReturn 0 : EndIf
    If PeekA(p + n) = 0 : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.i p3bmRange(address.i, bytes.i)
  If address < 0 Or bytes < 0 Or bytes > $7FFFFFFFFFFFFFFF - address : ProcedureReturn 0 : EndIf
  If bytes = 0 : ProcedureReturn 1 : EndIf
  ; Code/loader/stack, then BSS/stack/handoff/staging. DTB interval between
  ; these bands remains reserved and may itself appear in the reserve map.
  If address < $1000000 And address + bytes > $80000 : ProcedureReturn 0 : EndIf
  If address < $2E00000 And address + bytes > $1100000 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
; A one-cell property of `node` that must hold 1 or 2 when present: its value,
; `absent` when it is not there, or 0 when it is malformed.
Procedure.i p3bmCells(node.i, *name, absent.i)
  Protected p.i
  p = FdtGetProp(node, *name)
  If p = 0 : ProcedureReturn absent : EndIf
  If FdtPropLen() <> 4 : ProcedureReturn 0 : EndIf
  p = p3bmBe32(p)
  If p < 1 Or p > 2 : ProcedureReturn 0 : EndIf
  ProcedureReturn p
EndProcedure
Procedure.i Pi3BootRanges(dtb.i, total.i)
  Protected r.i
  Protected s.i
  Protected strings.i
  Protected bytes.i
  Protected length.i
  Protected i.i
  Protected n.i
  Protected root.i
  Protected rootAddress.i
  Protected rootSize.i
  Protected rm.i
  Protected child.i
  Protected p.i
  If total < 40 Or total > $100000 : ProcedureReturn 0 : EndIf
  If FdtCheck(dtb, total) <> #FDT_OK : ProcedureReturn 0 : EndIf
  If p3bmBe32(dtb + 4) <> total Or p3bmBe32(dtb + 24) > 17 : ProcedureReturn 0 : EndIf
  r = p3bmBe32(dtb + 16)
  s = p3bmBe32(dtb + 8)
  strings = p3bmBe32(dtb + 12)
  bytes = p3bmBe32(dtb + 36)
  length = p3bmBe32(dtb + 32)
  If (r & 7) <> 0 Or (s & 3) <> 0 Or bytes < 12 Or length < 1 : ProcedureReturn 0 : EndIf
  ; Require ordered blocks as defined by the flattened format.
  If r >= s Or s + bytes > strings : ProcedureReturn 0 : EndIf
  n = FdtReserveCount()
  For i = 0 To n - 1
    If FdtReserve(i) <> #FDT_OK : ProcedureReturn 0 : EndIf
    If p3bmRange(FdtRegBase(), FdtRegLength()) = 0 : ProcedureReturn 0 : EndIf
  Next
  root = FdtRoot()
  rootAddress = p3bmCells(root, "#address-cells", 2)
  rootSize = p3bmCells(root, "#size-cells", 1)
  If rootAddress = 0 Or rootSize = 0 : ProcedureReturn 0 : EndIf
  ; At most one root child named exactly "reserved-memory".
  rm = 0
  child = FdtFirstChild(root)
  While child <> 0
    If p3bmName(FdtNodeName(child), FdtNodeName(child) + 256, "reserved-memory") <> 0
      If rm <> 0 : ProcedureReturn 0 : EndIf
      rm = child
    EndIf
    child = FdtNextSibling(child)
  Wend
  If rm = 0 : ProcedureReturn 1 : EndIf
  If p3bmCells(rm, "#address-cells", 0) <> rootAddress : ProcedureReturn 0 : EndIf
  If p3bmCells(rm, "#size-cells", 0) <> rootSize : ProcedureReturn 0 : EndIf
  If FdtGetProp(rm, "ranges") = 0 Or FdtPropLen() <> 0 : ProcedureReturn 0 : EndIf
  child = FdtFirstChild(rm)
  While child <> 0
    If FdtFirstChild(child) <> 0 : ProcedureReturn 0 : EndIf
    p = FdtGetProp(child, "reg")
    If p <> 0
      n = (rootAddress + rootSize) * 4
      If FdtPropLen() = 0 Or (FdtPropLen() % n) <> 0 : ProcedureReturn 0 : EndIf
      n = FdtPropLen() / n
      For i = 0 To n - 1
        If FdtReg(child, i) <> #FDT_OK : ProcedureReturn 0 : EndIf
        If p3bmRange(FdtRegBase(), FdtRegLength()) = 0 : ProcedureReturn 0 : EndIf
      Next
    EndIf
    child = FdtNextSibling(child)
  Wend
  ProcedureReturn 1
EndProcedure
