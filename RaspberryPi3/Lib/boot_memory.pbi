; Pi3 fixed A/B boot layout admission. Original DTSpec v0.4-format reader.
; No allocations or writes. Caller first validates DTB outer span in ARM RAM.
Procedure.i p3bmBe32(p.i)
  ProcedureReturn (PeekA(p) << 24) | (PeekA(p + 1) << 16) | (PeekA(p + 2) << 8) | PeekA(p + 3)
EndProcedure
Procedure.i p3bmBe64(p.i)
  ProcedureReturn (p3bmBe32(p) << 32) | p3bmBe32(p + 4)
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
Procedure.i Pi3BootRanges(dtb.i, total.i)
  Protected r.i
  Protected s.i
  Protected se.i
  Protected strings.i
  Protected stringsEnd.i
  Protected token.i
  Protected depth.i
  Protected name.i
  Protected bytes.i
  Protected value.i
  Protected n.i
  Protected rootAddress.i = 2
  Protected rootSize.i = 1
  Protected reserveAddress.i
  Protected reserveSize.i
  Protected reserveDepth.i
  Protected reserveSeen.i
  Protected rangesSeen.i
  Protected address.i
  Protected length.i
  Protected cells.i
  If total < 40 Or total > $100000 Or p3bmBe32(dtb) <> $D00DFEED : ProcedureReturn 0 : EndIf
  If p3bmBe32(dtb + 4) <> total Or p3bmBe32(dtb + 20) < 17 Or p3bmBe32(dtb + 24) > 17 : ProcedureReturn 0 : EndIf
  r = p3bmBe32(dtb + 16)
  s = p3bmBe32(dtb + 8)
  strings = p3bmBe32(dtb + 12)
  bytes = p3bmBe32(dtb + 36)
  length = p3bmBe32(dtb + 32)
  If r < 40 Or (r & 7) <> 0 Or r > total - 16 Or s < 40 Or (s & 3) <> 0 Or bytes < 12 Or s > total - bytes : ProcedureReturn 0 : EndIf
  If strings < 40 Or length < 1 Or strings > total - length : ProcedureReturn 0 : EndIf
  If s < strings + length And strings < s + bytes : ProcedureReturn 0 : EndIf
  ; Require ordered blocks as defined by the flattened format.
  If r >= s Or s + bytes > strings : ProcedureReturn 0 : EndIf
  se = dtb + s + bytes : s = dtb + s
  stringsEnd = dtb + strings + length : strings = dtb + strings
  r = dtb + r
  Repeat
    If r > s - 16 : ProcedureReturn 0 : EndIf
    address = p3bmBe64(r) : length = p3bmBe64(r + 8)
    If address = 0 And length = 0 : Break : EndIf
    If p3bmRange(address, length) = 0 : ProcedureReturn 0 : EndIf
    r = r + 16
  ForEver
  depth = 0
  While s <= se - 4
    token = p3bmBe32(s) : s = s + 4
    Select token
      Case 1
        depth = depth + 1
        If depth > 32 : ProcedureReturn 0 : EndIf
        If reserveDepth <> 0 And depth > 3 : ProcedureReturn 0 : EndIf
        If depth = 2 And p3bmName(s, se, "reserved-memory") <> 0
          If reserveSeen <> 0 : ProcedureReturn 0 : EndIf
          reserveSeen = 1 : reserveDepth = depth
          reserveAddress = 0 : reserveSize = 0 : rangesSeen = 0
        EndIf
        n = 0
        While s + n < se And n < 256
          If PeekA(s + n) = 0 : Break : EndIf
          n = n + 1
        Wend
        If n = 256 Or s + n >= se : ProcedureReturn 0 : EndIf
        s = (s + n + 4) & $FFFFFFFFFFFFFFFC
      Case 2
        If depth < 1 : ProcedureReturn 0 : EndIf
        If depth = reserveDepth
          If reserveAddress <> rootAddress Or reserveSize <> rootSize Or rangesSeen = 0 : ProcedureReturn 0 : EndIf
          reserveDepth = 0
        EndIf
        depth = depth - 1
      Case 3
        If depth < 1 Or s > se - 8 : ProcedureReturn 0 : EndIf
        bytes = p3bmBe32(s) : name = p3bmBe32(s + 4) : s = s + 8
        If bytes > se - s Or name >= stringsEnd - strings : ProcedureReturn 0 : EndIf
        name = strings + name
        ; Every property name must terminate inside the string block.
        n = 0
        While name + n < stringsEnd And n < 256
          If PeekA(name + n) = 0 : Break : EndIf
          n = n + 1
        Wend
        If n = 256 Or name + n >= stringsEnd : ProcedureReturn 0 : EndIf
        If depth = 1 Or depth = reserveDepth
          If p3bmName(name, stringsEnd, "#address-cells") <> 0 Or p3bmName(name, stringsEnd, "#size-cells") <> 0
            If bytes <> 4 : ProcedureReturn 0 : EndIf
            value = p3bmBe32(s)
            If value < 1 Or value > 2 : ProcedureReturn 0 : EndIf
            If p3bmName(name, stringsEnd, "#address-cells") <> 0
              If depth = 1 : rootAddress = value : Else : reserveAddress = value : EndIf
            Else
              If depth = 1 : rootSize = value : Else : reserveSize = value : EndIf
            EndIf
          ElseIf depth = reserveDepth And p3bmName(name, stringsEnd, "ranges") <> 0
            If bytes <> 0 : ProcedureReturn 0 : EndIf
            rangesSeen = 1
          EndIf
        ElseIf reserveDepth <> 0 And depth = 3 And p3bmName(name, stringsEnd, "reg") <> 0
          If reserveAddress <> rootAddress Or reserveSize <> rootSize Or rangesSeen = 0 : ProcedureReturn 0 : EndIf
          cells = (reserveAddress + reserveSize) * 4
          If bytes = 0 Or (bytes % cells) <> 0 : ProcedureReturn 0 : EndIf
          For n = 0 To bytes - 1 Step cells
            address = p3bmBe32(s + n)
            If reserveAddress = 2 : address = p3bmBe64(s + n) : EndIf
            length = p3bmBe32(s + n + reserveAddress * 4)
            If reserveSize = 2 : length = p3bmBe64(s + n + reserveAddress * 4) : EndIf
            If p3bmRange(address, length) = 0 : ProcedureReturn 0 : EndIf
          Next
        EndIf
        s = (s + bytes + 3) & $FFFFFFFFFFFFFFFC
      Case 4
        ; NOP
      Case 9
        ProcedureReturn depth = 0 And s = se
      Default
        ProcedureReturn 0
    EndSelect
  Wend
  ProcedureReturn 0
EndProcedure
