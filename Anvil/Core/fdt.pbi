; ======================================================================
;  fdt.pbi - THE flattened device-tree reader. One, for every board.
; ======================================================================
;
;  Rule 30: every library exists once. Before this file Anvil carried
;  seven private DTB walkers (boot_cmd.pbi, the Pi 3's boot_memory,
;  v3d.pi3, wifi_bringup.pi3 and update_boot_support, the Pi 4's hw_boot,
;  the Rock Pi's boot_contract). This is the shared one; the migration list
;  per caller is in the vault ("Anvil/One library, many boards - layering
;  plan 2026-09-18.md", section "The shared FDT reader").
;
;  DEPENDENCIES: none. It reads memory it is handed and allocates nothing.
;  NO RECURSION (rule 31): every walk is one iterative loop over the token
;  stream with a depth counter; the one place that needs ancestry
;  (FdtParent) keeps an explicit bounded stack.
;
;  THE FORMAT is the Devicetree Specification v0.4, chapter 5 (flattened
;  format): a 40-byte big-endian header, a memory-reservation block of
;  (address, size) 64-bit pairs ended by a zero pair, a structure block of
;  32-bit tokens (FDT_BEGIN_NODE 1, FDT_END_NODE 2, FDT_PROP 3, FDT_NOP 4,
;  FDT_END 9), and a strings block of NUL-terminated property names.
;
;  VALIDATION IS THE SAME AS RaspberryPi5/Boot/dtb_contract.py's parse(),
;  which is this file's desk oracle (tools/a64/fdt_check.py): magic
;  $D00DFEED, 40 <= totalsize <= 16 MiB and inside the caller's bound,
;  version >= 17 and last_comp_version <= version, both blocks inside the
;  tree and not overlapping, a terminated reserve map, and one full token
;  walk - names terminated and ASCII, properties inside their node and
;  their block, balanced nodes, a single empty-named root, and FDT_END
;  exactly at the end of the structure block. Anything else is REFUSED
;  with a distinct code; nothing is guessed.
;
;  Two deliberate differences from the oracle, both from the spec:
;    * an EMPTY `ranges` property is an identity mapping (DTSpec 2.3.8);
;      an ABSENT one means the bus is not translatable and is refused;
;    * a missing #address-cells / #size-cells takes the spec default,
;      2 and 1 (DTSpec 2.3.5).
;  And one known gap: duplicate node or property names are not detected;
;  a lookup returns the first.
;
;  ADDRESSES WITH THREE CELLS (a PCI bus). Values are carried as a 64-bit
;  low part plus the top cell (fdt_regHi / the ranges entry's top cell).
;  A translation step matches a ranges entry only when the top cells are
;  EQUAL - for PCI that is the phys.hi space code, compared exactly - and
;  then compares and offsets the low 64 bits. That is enough for the Pi 5's
;  RP1 window (rp1 ranges -> PCI space 2 -> pcie ranges -> $1F_0000_0000);
;  a bus whose top cells differ is refused rather than approximated.
;
;  HANDLES are the absolute address of a node's FDT_BEGIN_NODE token.
;  Zero means "none".
;
;  ---- A QUICK EXAMPLE -------------------------------------------------
;
;    If FdtCheck(HwFirmwareDtb(), $200000) = #FDT_OK
;      ram = FdtMemoryEndFromZero()             ; /memory, the entry at 0
;      uart = FdtStdoutNode()                    ; /chosen stdout-path
;      base = FdtRegAddress(uart, 0)             ; through every ranges
;      pin = FdtFindCompatible("brcm,bcm2712c0-pinctrl", 0)
;    EndIf
; ======================================================================

#FDT_MAGIC       = $D00DFEED
#FDT_HEADER      = 40
#FDT_MAX_BYTES   = $1000000      ; 16 MiB, dtb_contract.py MAX_DTB
#FDT_MAX_DEPTH   = 32
#FDT_BEGIN_NODE  = 1
#FDT_END_NODE    = 2
#FDT_PROP        = 3
#FDT_NOP         = 4
#FDT_END         = 9
#FDT_CH_SLASH    = 47          ; '/'
#FDT_CH_COLON    = 58          ; ':'
#FDT_CH_AT       = 64          ; '@'

#FDT_OK             = 0
#FDT_ERR_NULL       = -1         ; no tree address, or FdtCheck not passed
#FDT_ERR_MAGIC      = -2
#FDT_ERR_SIZE       = -3         ; totalsize outside 40..16 MiB or the bound
#FDT_ERR_VERSION    = -4
#FDT_ERR_BLOCK      = -5         ; structure or strings block outside the tree
#FDT_ERR_RESERVE    = -6         ; reserve map outside or unterminated
#FDT_ERR_OVERLAP    = -7
#FDT_ERR_TOKEN      = -8         ; unknown token, or a token past the block
#FDT_ERR_NAME       = -9         ; unterminated or non-ASCII name
#FDT_ERR_NESTING    = -10        ; unbalanced nodes, second root, too deep
#FDT_ERR_PROP       = -11        ; property outside a node or its block
#FDT_ERR_END        = -12        ; FDT_END missing or not final
#FDT_ERR_NOTFOUND   = -13
#FDT_ERR_CELLS      = -14        ; a cell layout this reader does not take
#FDT_ERR_REG        = -15        ; reg missing, malformed, zero-length
#FDT_ERR_RANGES     = -16        ; no ranges, malformed, or not covered
#FDT_ERR_VALUE      = -17        ; a value with bit 63 set, or overflow

Global fdt_base.i
Global fdt_total.i
Global fdt_struct.i
Global fdt_structEnd.i
Global fdt_strings.i
Global fdt_stringsEnd.i
Global fdt_root.i
Global fdt_ready.i
Global fdt_err.i
Global fdt_propLen.i
Global fdt_regHi.i
Global fdt_regAddr.i
Global fdt_regSize.i
Global fdt_cellHi.i
Global Dim fdt_stack.i(#FDT_MAX_DEPTH)

; ---------------------------------------------------------------- results
; The public way to read what the last call left behind. Callers use these,
; never the fdt_ globals, which are this file's private namespace (the
; layering gate's rule 4).
Procedure.i FdtError()
  ProcedureReturn fdt_err
EndProcedure

Procedure.i FdtPropLen()
  ProcedureReturn fdt_propLen
EndProcedure

Procedure.i FdtRegBase()
  ProcedureReturn fdt_regAddr
EndProcedure

Procedure.i FdtRegBaseHigh()
  ProcedureReturn fdt_regHi
EndProcedure

Procedure.i FdtRegLength()
  ProcedureReturn fdt_regSize
EndProcedure

; ---------------------------------------------------------------- bytes
; Big-endian, byte by byte: alignment-safe with the MMU off, and the tree
; is big-endian whatever the CPU is.
Procedure.i fdt_Be32(p.i)
  ProcedureReturn (PeekA(p) << 24) | (PeekA(p + 1) << 16) | (PeekA(p + 2) << 8) | PeekA(p + 3)
EndProcedure

Procedure.i fdt_Align4(x.i)
  ProcedureReturn ((x + 3) >> 2) << 2
EndProcedure

; The address of the NUL ending the name at p, or 0 if there is none
; before limit or a byte is not ASCII (dtb_contract.py _cstring).
Procedure.i fdt_NameEnd(p.i, limit.i)
  Protected c.i
  While p < limit
    c = PeekA(p)
    If c = 0
      ProcedureReturn p
    EndIf
    If c > 127
      ProcedureReturn 0
    EndIf
    p = p + 1
  Wend
  ProcedureReturn 0
EndProcedure

; 1 if the NUL-terminated DTB string at p equals the NUL-terminated s.
Procedure.i fdt_StrEq(p.i, *s)
  Protected i.i
  Protected a.i
  i = 0
  Repeat
    a = PeekA(p + i)
    If a <> PeekA(*s + i)
      ProcedureReturn 0
    EndIf
    If a = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  ForEver
EndProcedure

; ---------------------------------------------------------------- check
; FdtCheck(base, limit) - validate the whole tree at base. limit is the
; most bytes the caller knows are the tree's (the firmware's region, the
; loaded file); totalsize must not exceed it. Returns #FDT_OK or a
; negative #FDT_ERR_*; every other Fdt* call refuses until this passes.
Procedure.i FdtCheck(base.i, limit.i)
  Protected total.i, offStruct.i, offStrings.i, offReserve.i
  Protected version.i, lastComp.i, sizeStrings.i, sizeStruct.i
  Protected cur.i, at.i, token.i, depth.i, rootSeen.i, e.i
  Protected plen.i, noff.i

  fdt_ready = 0
  fdt_err = #FDT_ERR_NULL
  If base <= 0 Or limit < #FDT_HEADER
    ProcedureReturn #FDT_ERR_NULL
  EndIf
  If fdt_Be32(base) <> #FDT_MAGIC
    fdt_err = #FDT_ERR_MAGIC : ProcedureReturn fdt_err
  EndIf
  total = fdt_Be32(base + 4)
  If total < #FDT_HEADER Or total > #FDT_MAX_BYTES Or total > limit
    fdt_err = #FDT_ERR_SIZE : ProcedureReturn fdt_err
  EndIf
  offStruct   = fdt_Be32(base + 8)
  offStrings  = fdt_Be32(base + 12)
  offReserve  = fdt_Be32(base + 16)
  version     = fdt_Be32(base + 20)
  lastComp    = fdt_Be32(base + 24)
  sizeStrings = fdt_Be32(base + 32)
  sizeStruct  = fdt_Be32(base + 36)
  If version < 17 Or lastComp > version
    fdt_err = #FDT_ERR_VERSION : ProcedureReturn fdt_err
  EndIf
  If offStruct < #FDT_HEADER Or sizeStruct > total - offStruct
    fdt_err = #FDT_ERR_BLOCK : ProcedureReturn fdt_err
  EndIf
  If offStrings < #FDT_HEADER Or sizeStrings > total - offStrings
    fdt_err = #FDT_ERR_BLOCK : ProcedureReturn fdt_err
  EndIf
  ; The reserve map: 16-byte pairs ending in a zero pair, before the
  ; structure block (dtb_contract.py:53-62).
  If offReserve < #FDT_HEADER Or offReserve + 16 > offStruct
    fdt_err = #FDT_ERR_RESERVE : ProcedureReturn fdt_err
  EndIf
  cur = offReserve
  e = 0
  While cur + 16 <= offStruct And e = 0
    If fdt_Be32(base + cur) = 0 And fdt_Be32(base + cur + 4) = 0 And fdt_Be32(base + cur + 8) = 0 And fdt_Be32(base + cur + 12) = 0
      e = 1
    EndIf
    cur = cur + 16
  Wend
  If e = 0
    fdt_err = #FDT_ERR_RESERVE : ProcedureReturn fdt_err
  EndIf
  If offStruct + sizeStruct > offStrings And offStrings + sizeStrings > offStruct
    fdt_err = #FDT_ERR_OVERLAP : ProcedureReturn fdt_err
  EndIf

  fdt_base = base
  fdt_total = total
  fdt_struct = base + offStruct
  fdt_structEnd = fdt_struct + sizeStruct
  fdt_strings = base + offStrings
  fdt_stringsEnd = fdt_strings + sizeStrings
  fdt_root = 0

  ; ---- one full token walk (dtb_contract.py:66-113) --------------------
  at = fdt_struct
  depth = 0
  rootSeen = 0
  e = 0
  While at < fdt_structEnd
    If at + 4 > fdt_structEnd
      fdt_err = #FDT_ERR_TOKEN : ProcedureReturn fdt_err
    EndIf
    token = fdt_Be32(at)
    at = at + 4
    Select token
      Case #FDT_BEGIN_NODE
        cur = fdt_NameEnd(at, fdt_structEnd)
        If cur = 0
          fdt_err = #FDT_ERR_NAME : ProcedureReturn fdt_err
        EndIf
        If depth = 0
          If rootSeen <> 0 Or cur <> at
            fdt_err = #FDT_ERR_NESTING : ProcedureReturn fdt_err
          EndIf
          rootSeen = 1
          fdt_root = at - 4
        EndIf
        depth = depth + 1
        If depth > #FDT_MAX_DEPTH
          fdt_err = #FDT_ERR_NESTING : ProcedureReturn fdt_err
        EndIf
        at = fdt_Align4(cur + 1)
      Case #FDT_END_NODE
        If depth = 0
          fdt_err = #FDT_ERR_NESTING : ProcedureReturn fdt_err
        EndIf
        depth = depth - 1
      Case #FDT_PROP
        If depth = 0 Or at + 8 > fdt_structEnd
          fdt_err = #FDT_ERR_PROP : ProcedureReturn fdt_err
        EndIf
        plen = fdt_Be32(at)
        noff = fdt_Be32(at + 4)
        at = at + 8
        If noff >= sizeStrings Or plen > fdt_structEnd - at
          fdt_err = #FDT_ERR_PROP : ProcedureReturn fdt_err
        EndIf
        If fdt_NameEnd(fdt_strings + noff, fdt_stringsEnd) = 0
          fdt_err = #FDT_ERR_NAME : ProcedureReturn fdt_err
        EndIf
        at = fdt_Align4(at + plen)
      Case #FDT_NOP
        ; nothing
      Case #FDT_END
        If depth <> 0 Or at <> fdt_structEnd
          fdt_err = #FDT_ERR_END : ProcedureReturn fdt_err
        EndIf
        e = 1
        Break
      Default
        fdt_err = #FDT_ERR_TOKEN : ProcedureReturn fdt_err
    EndSelect
    If at > fdt_structEnd
      fdt_err = #FDT_ERR_TOKEN : ProcedureReturn fdt_err
    EndIf
  Wend
  If e = 0 Or fdt_root = 0
    fdt_err = #FDT_ERR_END : ProcedureReturn fdt_err
  EndIf
  fdt_ready = 1
  fdt_err = #FDT_OK
  ProcedureReturn #FDT_OK
EndProcedure

; ---------------------------------------------------------------- tokens
; fdt_Next(at) - the token after the one at `at`. The tree is validated,
; so no bound check is repeated here beyond the block end.
Procedure.i fdt_Next(at.i)
  Protected token.i
  token = fdt_Be32(at)
  Select token
    Case #FDT_BEGIN_NODE
      ProcedureReturn fdt_Align4(fdt_NameEnd(at + 4, fdt_structEnd) + 1)
    Case #FDT_PROP
      ProcedureReturn fdt_Align4(at + 12 + fdt_Be32(at + 4))
  EndSelect
  ProcedureReturn at + 4
EndProcedure

Procedure.i FdtRoot()
  If fdt_ready = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn fdt_root
EndProcedure

; The node's name (a NUL-terminated string inside the tree).
Procedure.i FdtNodeName(node.i)
  If fdt_ready = 0 Or node = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn node + 4
EndProcedure

; 1 if the node name at p matches the path component [c, cEnd): exactly,
; or - when the component has no unit address - the name up to its #FDT_CH_AT.
Procedure.i fdt_CompMatch(p.i, c.i, cEnd.i)
  Protected n.i
  Protected hasAt.i
  Protected k.i
  n = cEnd - c
  hasAt = 0
  For k = 0 To n - 1
    If PeekA(c + k) = #FDT_CH_AT : hasAt = 1 : EndIf
  Next
  For k = 0 To n - 1
    If PeekA(p + k) <> PeekA(c + k)
      ProcedureReturn 0
    EndIf
  Next
  If PeekA(p + n) = 0
    ProcedureReturn 1
  EndIf
  If hasAt = 0 And PeekA(p + n) = #FDT_CH_AT
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; FdtFindNode(*path) - "/", "/soc@107c000000/serial@7d001000", "/soc/serial"
; ... A path ends at its NUL or at #FDT_CH_COLON (the stdout-path options separator,
; never legal in a node name). Returns the node handle or 0.
Procedure.i FdtFindNode(*path)
  Protected at.i, token.i, depth.i, matched.i, cp.i, ce.i, c.i
  If fdt_ready = 0 Or *path = 0 : ProcedureReturn 0 : EndIf
  If PeekA(*path) <> #FDT_CH_SLASH : ProcedureReturn 0 : EndIf
  cp = *path + 1
  c = PeekA(cp)
  If c = 0 Or c = #FDT_CH_COLON
    ProcedureReturn fdt_root
  EndIf
  ce = cp
  While PeekA(ce) <> 0 And PeekA(ce) <> #FDT_CH_SLASH And PeekA(ce) <> #FDT_CH_COLON
    ce = ce + 1
  Wend
  at = fdt_root
  depth = 0
  matched = 1                       ; the root is matched at depth 1
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE
      depth = depth + 1
      If depth = matched + 1
        If fdt_CompMatch(at + 4, cp, ce) <> 0
          matched = depth
          If PeekA(ce) = 0 Or PeekA(ce) = #FDT_CH_COLON
            ProcedureReturn at
          EndIf
          cp = ce + 1
          ce = cp
          While PeekA(ce) <> 0 And PeekA(ce) <> #FDT_CH_SLASH And PeekA(ce) <> #FDT_CH_COLON
            ce = ce + 1
          Wend
          If ce = cp                  ; "//" or a trailing #FDT_CH_SLASH
            ProcedureReturn at
          EndIf
        EndIf
      EndIf
    ElseIf token = #FDT_END_NODE
      If depth = matched
        ProcedureReturn 0             ; left the matched node: not there
      EndIf
      depth = depth - 1
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; FdtParent(node) - the enclosing node, 0 for the root. An explicit stack.
Procedure.i FdtParent(node.i)
  Protected at.i, token.i, depth.i
  If fdt_ready = 0 Or node = 0 : ProcedureReturn 0 : EndIf
  at = fdt_root
  depth = 0
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE
      If at = node
        If depth = 0 : ProcedureReturn 0 : EndIf
        ProcedureReturn fdt_stack(depth - 1)
      EndIf
      fdt_stack(depth) = at
      depth = depth + 1
    ElseIf token = #FDT_END_NODE
      depth = depth - 1
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; FdtGetProp(node, *name) - the property's data address, or 0 if the node
; has no such property. FdtPropLen() gives its length. Properties of
; SUB-nodes are skipped, whatever order the tree writes them in.
Procedure.i FdtGetProp(node.i, *name)
  Protected at.i, token.i, depth.i
  fdt_propLen = 0
  If fdt_ready = 0 Or node = 0 : ProcedureReturn 0 : EndIf
  at = fdt_Next(node)
  depth = 0
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_PROP
      If depth = 0
        If fdt_StrEq(fdt_strings + fdt_Be32(at + 8), *name) <> 0
          fdt_propLen = fdt_Be32(at + 4)
          ProcedureReturn at + 12
        EndIf
      EndIf
    ElseIf token = #FDT_BEGIN_NODE
      depth = depth + 1
    ElseIf token = #FDT_END_NODE
      If depth = 0 : ProcedureReturn 0 : EndIf
      depth = depth - 1
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; FdtFirstChild(node) - the node's first subnode, or 0.
Procedure.i FdtFirstChild(node.i)
  Protected at.i, token.i
  If fdt_ready = 0 Or node = 0 : ProcedureReturn 0 : EndIf
  at = fdt_Next(node)
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE : ProcedureReturn at : EndIf
    If token = #FDT_END_NODE Or token = #FDT_END : ProcedureReturn 0 : EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; FdtNextSibling(node) - the next subnode of node's parent, or 0. Skips
; node's own subtree with a depth counter, not by recursion.
Procedure.i FdtNextSibling(node.i)
  Protected at.i, token.i, depth.i
  If fdt_ready = 0 Or node = 0 : ProcedureReturn 0 : EndIf
  at = fdt_Next(node)
  depth = 1
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE
      If depth = 0 : ProcedureReturn at : EndIf
      depth = depth + 1
    ElseIf token = #FDT_END_NODE
      If depth = 0 : ProcedureReturn 0 : EndIf
      depth = depth - 1
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; The memory-reservation block (/memreserve/): how many entries before the
; zero terminator, and one entry into FdtRegBase() / FdtRegLength().
Procedure.i FdtReserveCount()
  Protected p.i, n.i
  If fdt_ready = 0 : ProcedureReturn 0 : EndIf
  p = fdt_base + fdt_Be32(fdt_base + 16)
  n = 0
  While fdt_Be32(p) <> 0 Or fdt_Be32(p + 4) <> 0 Or fdt_Be32(p + 8) <> 0 Or fdt_Be32(p + 12) <> 0
    n = n + 1
    p = p + 16
  Wend
  ProcedureReturn n
EndProcedure

Procedure.i FdtReserve(index.i)
  Protected p.i
  If fdt_ready = 0 Or index < 0 Or index >= FdtReserveCount() : ProcedureReturn #FDT_ERR_NOTFOUND : EndIf
  p = fdt_base + fdt_Be32(fdt_base + 16) + index * 16
  fdt_regAddr = fdt_Cells(p, 2)
  fdt_regSize = fdt_Cells(p + 8, 2)
  fdt_regHi = 0
  If fdt_regAddr < 0 Or fdt_regSize < 0 : ProcedureReturn #FDT_ERR_VALUE : EndIf
  ProcedureReturn #FDT_OK
EndProcedure

; A one-cell property, or dflt if absent; -1 if present but not one cell.
Procedure.i fdt_Cell(node.i, *name, dflt.i)
  Protected p.i
  p = FdtGetProp(node, *name)
  If p = 0 : ProcedureReturn dflt : EndIf
  If fdt_propLen <> 4 : ProcedureReturn -1 : EndIf
  ProcedureReturn fdt_Be32(p)
EndProcedure

Procedure.i FdtAddressCells(node.i)
  ProcedureReturn fdt_Cell(node, "#address-cells", 2)
EndProcedure

Procedure.i FdtSizeCells(node.i)
  ProcedureReturn fdt_Cell(node, "#size-cells", 1)
EndProcedure

; n cells at p: the low 64 bits returned, the top cell of a three-cell
; value in fdt_cellHi (0 otherwise). -1 if the low part has bit 63 set,
; because nothing this reader serves can hold such an address.
Procedure.i fdt_Cells(p.i, n.i)
  Protected v.i
  fdt_cellHi = 0
  If n = 1
    ProcedureReturn fdt_Be32(p)
  EndIf
  If n = 3
    fdt_cellHi = fdt_Be32(p)
    p = p + 4
  EndIf
  v = fdt_Be32(p)
  If v & $80000000
    ProcedureReturn -1
  EndIf
  ProcedureReturn (v << 32) | fdt_Be32(p + 4)
EndProcedure

; FdtRegCount(node) - how many (address, size) entries `reg` has.
Procedure.i FdtRegCount(node.i)
  Protected parent.i, ac.i, sc.i, p.i
  parent = FdtParent(node)
  If parent = 0 : ProcedureReturn 0 : EndIf
  ac = FdtAddressCells(parent)
  sc = FdtSizeCells(parent)
  If ac < 1 Or ac > 3 Or sc < 0 Or sc > 2 : ProcedureReturn 0 : EndIf
  p = FdtGetProp(node, "reg")
  If p = 0 Or fdt_propLen = 0 Or fdt_propLen % (4 * (ac + sc)) <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn fdt_propLen / (4 * (ac + sc))
EndProcedure

; FdtReg(node, index) - one raw reg entry, in the PARENT's address space:
; FdtRegBaseHigh() (top cell of a three-cell address), FdtRegBase(),
; FdtRegLength().
Procedure.i FdtReg(node.i, index.i)
  Protected parent.i, ac.i, sc.i, p.i, w.i
  If fdt_ready = 0 Or node = 0 : ProcedureReturn #FDT_ERR_NULL : EndIf
  parent = FdtParent(node)
  If parent = 0 : ProcedureReturn #FDT_ERR_REG : EndIf
  ac = FdtAddressCells(parent)
  sc = FdtSizeCells(parent)
  If ac < 1 Or ac > 3 Or sc < 0 Or sc > 2 : ProcedureReturn #FDT_ERR_CELLS : EndIf
  w = 4 * (ac + sc)
  p = FdtGetProp(node, "reg")
  If p = 0 Or fdt_propLen < w Or fdt_propLen % w <> 0 : ProcedureReturn #FDT_ERR_REG : EndIf
  If index < 0 Or index >= fdt_propLen / w : ProcedureReturn #FDT_ERR_REG : EndIf
  p = p + index * w
  fdt_regAddr = fdt_Cells(p, ac)
  fdt_regHi = fdt_cellHi
  If fdt_regAddr < 0 : ProcedureReturn #FDT_ERR_VALUE : EndIf
  fdt_regSize = 0
  If sc > 0
    fdt_regSize = fdt_Cells(p + 4 * ac, sc)
    If fdt_regSize < 0 : ProcedureReturn #FDT_ERR_VALUE : EndIf
  EndIf
  ProcedureReturn #FDT_OK
EndProcedure

; FdtRegAddress(node, index) - reg entry `index` translated through every
; ancestor's `ranges` to a CPU physical address (dtb_contract.py
; mapped_reg, widened to three-cell buses). -1 on any refusal, with the
; reason in FdtError().
Procedure.i FdtRegAddress(node.i, index.i)
  Protected r.i, hi.i, addr.i, span.i, bus.i, grand.i
  Protected cc.i, pc.i, sc.i, ranges.i, n.i, w.i, k.i, e.i
  Protected chHi.i, ch.i, cpuHi.i, cpu.i, length.i
  r = FdtReg(node, index)
  If r <> #FDT_OK : fdt_err = r : ProcedureReturn -1 : EndIf
  hi = fdt_regHi
  addr = fdt_regAddr
  span = fdt_regSize
  If span <= 0 : fdt_err = #FDT_ERR_REG : ProcedureReturn -1 : EndIf
  bus = FdtParent(node)
  While bus <> fdt_root
    grand = FdtParent(bus)
    cc = FdtAddressCells(bus)
    sc = FdtSizeCells(bus)
    pc = FdtAddressCells(grand)
    If cc < 1 Or cc > 3 Or pc < 1 Or pc > 3 Or sc < 1 Or sc > 2
      fdt_err = #FDT_ERR_CELLS : ProcedureReturn -1
    EndIf
    ranges = FdtGetProp(bus, "ranges")
    If ranges = 0
      fdt_err = #FDT_ERR_RANGES : ProcedureReturn -1
    EndIf
    n = fdt_propLen
    If n > 0
      w = 4 * (cc + pc + sc)
      If n % w <> 0
        fdt_err = #FDT_ERR_RANGES : ProcedureReturn -1
      EndIf
      e = 0
      k = 0
      While k < n And e = 0
        ch = fdt_Cells(ranges + k, cc) : chHi = fdt_cellHi
        cpu = fdt_Cells(ranges + k + 4 * cc, pc) : cpuHi = fdt_cellHi
        length = fdt_Cells(ranges + k + 4 * (cc + pc), sc)
        If ch < 0 Or cpu < 0 Or length < 0
          fdt_err = #FDT_ERR_VALUE : ProcedureReturn -1
        EndIf
        If chHi = hi And addr >= ch And span <= length And addr - ch <= length - span
          addr = cpu + (addr - ch)
          hi = cpuHi
          e = 1
        EndIf
        k = k + w
      Wend
      If e = 0
        fdt_err = #FDT_ERR_RANGES : ProcedureReturn -1
      EndIf
    EndIf
    ; An empty `ranges` is the identity map (DTSpec 2.3.8): nothing moves.
    bus = grand
  Wend
  If hi <> 0 Or addr < 0
    fdt_err = #FDT_ERR_VALUE : ProcedureReturn -1
  EndIf
  fdt_err = #FDT_OK
  ProcedureReturn addr
EndProcedure

; 1 if `compatible` of node lists s (an exact entry, not a prefix).
Procedure.i FdtCompatible(node.i, *s)
  Protected p.i, e.i, q.i
  p = FdtGetProp(node, "compatible")
  If p = 0 Or fdt_propLen = 0 : ProcedureReturn 0 : EndIf
  e = p + fdt_propLen
  If PeekA(e - 1) <> 0 : ProcedureReturn 0 : EndIf
  q = p
  While q < e
    If fdt_StrEq(q, *s) <> 0 : ProcedureReturn 1 : EndIf
    While PeekA(q) <> 0
      q = q + 1
    Wend
    q = q + 1
  Wend
  ProcedureReturn 0
EndProcedure

; The first node after `after` (0 = from the start) whose compatible
; lists s, or 0. Call again with the result to find the next one.
Procedure.i FdtFindCompatible(*s, after.i)
  Protected at.i, token.i
  If fdt_ready = 0 : ProcedureReturn 0 : EndIf
  at = fdt_root
  If after <> 0 : at = fdt_Next(after) : EndIf
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE
      If FdtCompatible(at, *s) <> 0
        ProcedureReturn at
      EndIf
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; A string property of a fixed node: the pointer if it is NUL-terminated.
Procedure.i fdt_StringProp(node.i, *name)
  Protected p.i
  If node = 0 : ProcedureReturn 0 : EndIf
  p = FdtGetProp(node, *name)
  If p = 0 Or fdt_propLen = 0 : ProcedureReturn 0 : EndIf
  If PeekA(p + fdt_propLen - 1) <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn p
EndProcedure

; /aliases: the path an alias names (a string inside the tree), or 0.
Procedure.i FdtAlias(*name)
  ProcedureReturn fdt_StringProp(FdtFindNode("/aliases"), *name)
EndProcedure

; /chosen: a property's data pointer (FdtPropLen()), or 0.
Procedure.i FdtChosen(*name)
  Protected node.i
  node = FdtFindNode("/chosen")
  If node = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn FdtGetProp(node, *name)
EndProcedure

; The node /chosen stdout-path names, through /aliases when it is an
; alias, options after #FDT_CH_COLON ignored (dtb_contract.py early_uart). 0 if none.
Procedure.i FdtStdoutNode()
  Protected p.i, q.i, e.i, k.i, match.i, al.i, ae.i
  p = fdt_StringProp(FdtFindNode("/chosen"), "stdout-path")
  If p = 0 : ProcedureReturn 0 : EndIf
  If PeekA(p) = #FDT_CH_SLASH
    ProcedureReturn FdtFindNode(p)
  EndIf
  ; an alias name, up to #FDT_CH_COLON or NUL: find it among /aliases' properties
  e = p
  While PeekA(e) <> 0 And PeekA(e) <> #FDT_CH_COLON
    e = e + 1
  Wend
  If e = p : ProcedureReturn 0 : EndIf
  q = FdtFindNode("/aliases")
  If q = 0 : ProcedureReturn 0 : EndIf
  q = fdt_Next(q)
  While q < fdt_structEnd And fdt_Be32(q) <> #FDT_BEGIN_NODE And fdt_Be32(q) <> #FDT_END_NODE
    If fdt_Be32(q) = #FDT_PROP
      al = fdt_strings + fdt_Be32(q + 8)
      match = 1
      For k = 0 To (e - p) - 1
        If PeekA(al + k) <> PeekA(p + k) : match = 0 : Break : EndIf
      Next
      If match <> 0 And PeekA(al + (e - p)) = 0
        ae = q + 12
        If fdt_Be32(q + 4) > 0 And PeekA(ae + fdt_Be32(q + 4) - 1) = 0 And PeekA(ae) = #FDT_CH_SLASH
          ProcedureReturn FdtFindNode(ae)
        EndIf
        ProcedureReturn 0
      EndIf
    EndIf
    q = fdt_Next(q)
  Wend
  ProcedureReturn 0
EndProcedure

; The index-th node whose device_type is "memory" (0 = the first), or 0.
Procedure.i FdtMemoryNode(index.i)
  Protected at.i, token.i, p.i
  If fdt_ready = 0 : ProcedureReturn 0 : EndIf
  at = fdt_root
  While at < fdt_structEnd
    token = fdt_Be32(at)
    If token = #FDT_BEGIN_NODE
      p = fdt_StringProp(at, "device_type")
      If p <> 0
        If fdt_StrEq(p, "memory") <> 0
          If index = 0 : ProcedureReturn at : EndIf
          index = index - 1
        EndIf
      EndIf
    ElseIf token = #FDT_END
      ProcedureReturn 0
    EndIf
    at = fdt_Next(at)
  Wend
  ProcedureReturn 0
EndProcedure

; The end of the RAM bank that starts at address 0 - the contiguous RAM an
; identity-mapped monitor can rely on - from every memory node's every reg
; entry. 0 if no entry starts at 0.
Procedure.i FdtMemoryEndFromZero()
  Protected i.i, node.i, n.i, k.i
  i = 0
  node = FdtMemoryNode(0)
  While node <> 0
    n = FdtRegCount(node)
    For k = 0 To n - 1
      If FdtRegAddress(node, k) = 0
        ProcedureReturn fdt_regSize
      EndIf
    Next
    i = i + 1
    node = FdtMemoryNode(i)
  Wend
  ProcedureReturn 0
EndProcedure
