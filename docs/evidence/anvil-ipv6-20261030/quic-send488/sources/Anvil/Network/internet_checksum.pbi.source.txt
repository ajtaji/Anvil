; Shared Internet checksum arithmetic, used by IPv4 and IPv6.
; RFC 1071 sections 1 and 2: ones-complement sum and byte-order independence.
; Caller supplies a valid nonnegative byte span and a nonnegative seed.
; Concatenated chunks must end on even boundaries except the final chunk.
; Uses native .i accumulation; the existing optimized 32-bit reads require
; the 64-bit integer ABI used by Anvil compositions. No device/state access.
Procedure.i InternetChecksumSum16(*p, n.i, seed.i)
  Protected sum.i
  Protected i.i
  Protected q.i
  Protected e.i
  Protected w.i
  Protected whole.i
  sum = seed
  i = 0

  If (*p & 1) = 0
    ; One pair, only if that is what it takes to reach a word boundary.
    If (*p & 2) <> 0
      If (i + 1) < n
        sum = sum + ((PeekA(*p + i) << 8) | PeekA(*p + i + 1))
        i = i + 2
      EndIf
    EndIf
    whole = (n - i) & (~3)
    If whole >= 4
      q = *p + i
      e = q + whole
      w = 0
      While q < e
        w = w + PeekN(q)
        q = q + 4
      Wend
      ; Fold to sixteen bits in the swapped domain, then swap once. Two
      ; separate steps on purpose: the fold is 1.2C and the swap is 1.2B,
      ; and a reader checking one should not have to untangle the other.
      While w > $FFFF
        w = (w & $FFFF) + (w >> 16)
      Wend
      sum = sum + (((w & $FF) << 8) | ((w >> 8) & $FF))
      i = i + whole
    EndIf
  EndIf

  ; i is EVEN here on every path, so the pairing below starts on the same
  ; parity it would have started on if this loop had run from zero. That
  ; is what makes the pieces add up to the same answer, and it is why the
  ; head above steps by two and the body by four.
  While (i + 1) < n
    sum = sum + ((PeekA(*p + i) << 8) | PeekA(*p + i + 1))
    i = i + 2
  Wend
  If i < n
    sum = sum + (PeekA(*p + i) << 8)
  EndIf
  ProcedureReturn sum
EndProcedure

; Fold the carries down into sixteen bits. Twice, because the first fold
; can itself carry: $1FFFE folds to $FFFF + 1 = $10000, and one more
; fold gives 1.
Procedure.i InternetChecksumFold(sum.i)
  Protected s.i
  s = sum
  While s > $FFFF
    s = (s & $FFFF) + (s >> 16)
  Wend
  ProcedureReturn s & $FFFF
EndProcedure

; The finished field: the ones' complement of the folded sum.
; $FFFF - s rather than (~s) & $FFFF. They are identical for
; 0 <= s <= $FFFF and the subtraction cannot be misread as a logical
; Not by somebody skimming.
Procedure.i InternetChecksumFinish(sum.i)
  ProcedureReturn ($FFFF - InternetChecksumFold(sum)) & $FFFF
EndProcedure
