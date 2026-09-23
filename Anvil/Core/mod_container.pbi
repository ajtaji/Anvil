; ======================================================================
;  PMFMOD v1 CONTAINER PREFLIGHT AND RELOCATION ENGINE
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Hal/module_format.pbi
;    Anvil/Core/sha256.pbi
;
;  This is deliberately below loading policy. It parses one container in
;  memory, proves every length before pointer arithmetic, validates every
;  relocation before any destination byte is changed, and checks the digest
;  before allocation. It does not open files, select hardware, call probe or
;  init, fill service slots, or authenticate code. SHA-256 detects damage; a
;  trusted signing policy, if one is ever chosen, belongs above this engine.
;
;  The engine is intentionally non-reentrant, like the shared SHA-256 context.
;  A manifest walker must finish one ModPreflight() / ModArenaLoadPrepared()
;  transaction before starting another.
; ======================================================================

#MOD_I64_MAX = $7FFFFFFFFFFFFFFF

Global gModError.i
Global gModErrorIndex.i
Global gModErrorValue.i
Global gModPrepared.i
Global gModContainer.i
Global gModContainerBytes.i
Global gModAbiMajor.i
Global gModAbiMinor.i
Global gModSeamCount.i
Global gModFlags.i
Global gModImageBytes.i
Global gModBssOffset.i
Global gModBssBytes.i
Global gModInitOffset.i
Global gModRelocCount.i
Global gModRelocOffset.i
Global gModAlign.i
Global gModArchitecture.i
Global gModMatchCount.i
Global gModMatchOffset.i
Global gModProbeOffset.i
Global gModQuiesceOffset.i
Global gModObjectBytes.i
Global Dim gModSeam.i[#PMFMOD_SEAM_MAX]
Global Dim gModDigest.a[#PMFMOD_DIGEST_BYTES]
Global Dim gModDigestGot.a[#PMFMOD_DIGEST_BYTES]

Procedure.i ModFail(code.i, index.i, value.i)
  gModError = code
  gModErrorIndex = index
  gModErrorValue = value
  gModPrepared = 0
  ProcedureReturn code
EndProcedure

Procedure.i ModRd16(p.i)
  ProcedureReturn (PeekA(p) & 255) | ((PeekA(p + 1) & 255) << 8)
EndProcedure

Procedure.i ModRd32(p.i)
  ProcedureReturn (PeekA(p) & 255) | ((PeekA(p + 1) & 255) << 8) | ((PeekA(p + 2) & 255) << 16) | ((PeekA(p + 3) & 255) << 24)
EndProcedure

Procedure.i ModRd64(p.i)
  Define v.i
  Define i.i
  v = 0
  i = 0
  While i < 8
    v = v | ((PeekA(p + i) & 255) << (i * 8))
    i = i + 1
  Wend
  ProcedureReturn v
EndProcedure

Procedure.i ModAddOk(a.i, b.i)
  If a < 0 Or b < 0
    ProcedureReturn 0
  EndIf
  If a > #MOD_I64_MAX - b
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModMulOk(a.i, b.i)
  If a < 0 Or b < 0
    ProcedureReturn 0
  EndIf
  If a = 0 Or b = 0
    ProcedureReturn 1
  EndIf
  If a > #MOD_I64_MAX / b
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModAlignUp(v.i, a.i)
  If v < 0 Or a <= 0
    ProcedureReturn -1
  EndIf
  If ModAddOk(v, a - 1) = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn ((v + a - 1) / a) * a
EndProcedure

Procedure.i ModRangeEnd(start.i, bytes.i)
  If bytes <= 0 Or ModAddOk(start, bytes) = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn start + bytes
EndProcedure

Procedure.i ModEntryOffsetOk(offset.i, optional.i)
  If optional <> 0 And offset = 0
    ProcedureReturn 1
  EndIf
  If offset < 0 Or offset >= gModImageBytes Or (offset & 3) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModTargetOffsetOk(offset.i)
  Define bssEnd.i
  If offset < 0
    ProcedureReturn 0
  EndIf
  If offset < gModImageBytes
    ProcedureReturn 1
  EndIf
  If gModBssBytes <= 0 Or ModAddOk(gModBssOffset, gModBssBytes) = 0
    ProcedureReturn 0
  EndIf
  bssEnd = gModBssOffset + gModBssBytes
  If offset >= gModBssOffset And offset < bssEnd
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i ModMagicOk(p.i)
  If (PeekA(p) & 255) <> #PMFMOD_MAGIC_0 Or (PeekA(p + 1) & 255) <> #PMFMOD_MAGIC_1 Or (PeekA(p + 2) & 255) <> #PMFMOD_MAGIC_2 Or (PeekA(p + 3) & 255) <> #PMFMOD_MAGIC_3
    ProcedureReturn 0
  EndIf
  If (PeekA(p + 4) & 255) <> #PMFMOD_MAGIC_4 Or (PeekA(p + 5) & 255) <> #PMFMOD_MAGIC_5 Or (PeekA(p + 6) & 255) <> 0 Or (PeekA(p + 7) & 255) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModPadZero(p.i, first.i, last.i)
  Define i.i
  i = first
  While i < last
    If (PeekA(p + i) & 255) <> 0
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i ModMatchOk(p.i, index.i)
  Define base.i
  Define i.i
  Define n.i
  Define c.i
  base = p + gModMatchOffset + index * #PMFMOD_MATCH_BYTES
  n = -1
  i = 0
  While i < #PMFMOD_MATCH_BYTES
    c = PeekA(base + i) & 255
    If c = 0
      If n < 0
        n = i
      EndIf
    Else
      If n >= 0
        ProcedureReturn 0             ; non-zero tail after the terminator
      EndIf
      If c < 32 Or c > 126 Or c = 47 Or c = 92
        ProcedureReturn 0             ; printable identifier, never a path
      EndIf
    EndIf
    i = i + 1
  Wend
  If n <= 0 Or n >= #PMFMOD_MATCH_BYTES
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModMatchSame(p.i, a.i, b.i)
  Define pa.i
  Define pb.i
  Define i.i
  pa = p + gModMatchOffset + a * #PMFMOD_MATCH_BYTES
  pb = p + gModMatchOffset + b * #PMFMOD_MATCH_BYTES
  i = 0
  While i < #PMFMOD_MATCH_BYTES
    If (PeekA(pa + i) & 255) <> (PeekA(pb + i) & 255)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i ModRelocSiteOk(p.i, index.i)
  Define r.i
  Define site.i
  Define kind.i
  Define reserved.i
  Define addend.i
  Define width.i
  Define priorSite.i
  Define priorKind.i
  Define priorWidth.i
  Define word.i
  Define j.i
  Define delta.i
  Define pages.i
  r = p + gModRelocOffset + index * #PMFMOD_RELOC_BYTES
  site = ModRd32(r + #PMFMOD_REL_OFF_SITE)
  kind = ModRd16(r + #PMFMOD_REL_OFF_KIND)
  reserved = ModRd16(r + #PMFMOD_REL_OFF_RESERVED)
  addend = ModRd64(r + #PMFMOD_REL_OFF_ADDEND)

  If kind < #MREL_ADRP_PAGE Or kind > #MREL_CALL26
    ProcedureReturn ModFail(#MOD_ERR_RELKIND, index, kind)
  EndIf
  If reserved <> 0 Or ModTargetOffsetOk(addend) = 0
    ProcedureReturn ModFail(#MOD_ERR_RELOC, index, addend)
  EndIf
  ; Control transfer may only land on a complete instruction in the emitted
  ; image. BSS is valid storage for data relocations, never executable code.
  If kind = #MREL_CALL26
    If addend < 0 Or addend >= gModImageBytes Or (addend & 3) <> 0
      ProcedureReturn ModFail(#MOD_ERR_RELOC, index, addend)
    EndIf
  EndIf

  width = 4
  If kind = #MREL_ABS64
    width = 8
  EndIf
  If site < 0 Or ModAddOk(site, width) = 0 Or site + width > gModImageBytes
    ProcedureReturn ModFail(#MOD_ERR_RELOC, index, site)
  EndIf
  If kind = #MREL_ABS64
    If (site & 7) <> 0
      ProcedureReturn ModFail(#MOD_ERR_RELOC, index, site)
    EndIf
  ElseIf (site & 3) <> 0
    ProcedureReturn ModFail(#MOD_ERR_RELOC, index, site)
  EndIf

  ; Every destination byte has one owner. Compare spans, not only starts:
  ; an eight-byte ABS64 can overlap a four-byte instruction relocation.
  j = 0
  While j < index
    priorSite = ModRd32(p + gModRelocOffset + j * #PMFMOD_RELOC_BYTES)
    priorKind = ModRd16(p + gModRelocOffset + j * #PMFMOD_RELOC_BYTES + #PMFMOD_REL_OFF_KIND)
    priorWidth = 4
    If priorKind = #MREL_ABS64
      priorWidth = 8
    EndIf
    If site < priorSite + priorWidth And priorSite < site + width
      ProcedureReturn ModFail(#MOD_ERR_RELOC, index, site)
    EndIf
    j = j + 1
  Wend

  If kind <> #MREL_ABS64
    word = ModRd32(p + #PMFMOD_HEADER_BYTES + site)
  EndIf
  Select kind
    Case #MREL_ADRP_PAGE
      If (word & $9F000000) <> $90000000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      pages = (addend / 4096) - (site / 4096)
      If pages < -1048576 Or pages > 1048575
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, pages)
      EndIf
    Case #MREL_ADD_LO12
      If (word & $FFC00000) <> $91000000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
    Case #MREL_MOVW_G0
      If (word & $FF800000) <> $D2800000 And (word & $FF800000) <> $F2800000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      If ((word >> 21) & 3) <> kind - #MREL_MOVW_G0
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
    Case #MREL_MOVW_G1
      If (word & $FF800000) <> $D2800000 And (word & $FF800000) <> $F2800000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      If ((word >> 21) & 3) <> kind - #MREL_MOVW_G0
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
    Case #MREL_MOVW_G2
      If (word & $FF800000) <> $D2800000 And (word & $FF800000) <> $F2800000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      If ((word >> 21) & 3) <> kind - #MREL_MOVW_G0
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
    Case #MREL_MOVW_G3
      If (word & $FF800000) <> $D2800000 And (word & $FF800000) <> $F2800000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      If ((word >> 21) & 3) <> kind - #MREL_MOVW_G0
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
    Case #MREL_CALL26
      If (word & $FC000000) <> $94000000
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, word)
      EndIf
      delta = addend - site
      If (delta & 3) <> 0 Or delta < -134217728 Or delta > 134217724
        ProcedureReturn ModFail(#MOD_ERR_RELOC, index, delta)
      EndIf
  EndSelect
  ProcedureReturn #MOD_OK
EndProcedure

Procedure.i ModDigestOk(p.i, bytes.i)
  Define i.i
  Define bad.i
  Sha256Begin()
  Sha256Update(p, #PMFMOD_OFF_SHA256)
  Sha256Update(p + #PMFMOD_OFF_SHA256 + #PMFMOD_DIGEST_BYTES, bytes - (#PMFMOD_OFF_SHA256 + #PMFMOD_DIGEST_BYTES))
  Sha256End(@gModDigestGot[0])
  bad = 0
  i = 0
  While i < #PMFMOD_DIGEST_BYTES
    If (gModDigestGot[i] & 255) <> (PeekA(p + #PMFMOD_OFF_SHA256 + i) & 255)
      bad = 1
    EndIf
    i = i + 1
  Wend
  If bad <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ModPreflight(p.i, bytes.i, abiMajor.i, abiMinor.i)
  Define imageEnd.i
  Define wantReloc.i
  Define relocBytes.i
  Define relocEnd.i
  Define matchBytes.i
  Define matchEnd.i
  Define bssEnd.i
  Define objectEnd.i
  Define i.i
  Define j.i
  Define v.i

  gModPrepared = 0
  gModError = #MOD_OK
  gModErrorIndex = -1
  gModErrorValue = 0
  If p <= 0 Or bytes < #PMFMOD_HEADER_BYTES
    ProcedureReturn ModFail(#MOD_ERR_HEADER, -1, bytes)
  EndIf
  If ModMagicOk(p) = 0
    ProcedureReturn ModFail(#MOD_ERR_MAGIC, -1, 0)
  EndIf
  If ModRd32(p + #PMFMOD_OFF_VERSION) <> #PMFMOD_VERSION Or ModRd32(p + #PMFMOD_OFF_HEADER_BYTES) <> #PMFMOD_HEADER_BYTES
    ProcedureReturn ModFail(#MOD_ERR_VERSION, -1, ModRd32(p + #PMFMOD_OFF_VERSION))
  EndIf
  gModAbiMajor = ModRd32(p + #PMFMOD_OFF_ABI_MAJOR)
  gModAbiMinor = ModRd32(p + #PMFMOD_OFF_ABI_MINOR)
  If gModAbiMajor <> abiMajor
    ProcedureReturn ModFail(#MOD_ERR_ABI_MAJOR, -1, gModAbiMajor)
  EndIf
  If gModAbiMinor > abiMinor
    ProcedureReturn ModFail(#MOD_ERR_ABI_MINOR, -1, gModAbiMinor)
  EndIf

  gModFlags = ModRd32(p + #PMFMOD_OFF_FLAGS)
  If gModFlags <> #PMFMOD_FLAGS_V1 Or ModRd64(p + #PMFMOD_OFF_RESERVED1) <> 0
    ProcedureReturn ModFail(#MOD_ERR_HEADER, -1, gModFlags)
  EndIf
  gModArchitecture = ModRd32(p + #PMFMOD_OFF_ARCH)
  If gModArchitecture <> #PMFMOD_ARCH_AARCH64
    ProcedureReturn ModFail(#MOD_ERR_ARCH, -1, gModArchitecture)
  EndIf
  gModAlign = ModRd32(p + #PMFMOD_OFF_ALIGN)
  If gModAlign <> #PMFMOD_LOAD_ALIGN
    ProcedureReturn ModFail(#MOD_ERR_ALIGN, -1, gModAlign)
  EndIf

  gModSeamCount = ModRd32(p + #PMFMOD_OFF_SEAM_COUNT)
  If gModSeamCount < 1 Or gModSeamCount > #PMFMOD_SEAM_MAX
    ProcedureReturn ModFail(#MOD_ERR_HEADER, -1, gModSeamCount)
  EndIf
  i = 0
  While i < #PMFMOD_SEAM_MAX
    v = ModRd32(p + #PMFMOD_OFF_SEAMS + i * 4)
    gModSeam[i] = v
    If i < gModSeamCount
      If v = #PMFMOD_SEAM_UNUSED
        ProcedureReturn ModFail(#MOD_ERR_HEADER, i, v)
      EndIf
      j = 0
      While j < i
        If gModSeam[j] = v
          ProcedureReturn ModFail(#MOD_ERR_HEADER, i, v)
        EndIf
        j = j + 1
      Wend
    ElseIf v <> #PMFMOD_SEAM_UNUSED
      ProcedureReturn ModFail(#MOD_ERR_HEADER, i, v)
    EndIf
    i = i + 1
  Wend

  gModImageBytes = ModRd64(p + #PMFMOD_OFF_IMAGE_BYTES)
  gModBssOffset = ModRd64(p + #PMFMOD_OFF_BSS_OFFSET)
  gModBssBytes = ModRd64(p + #PMFMOD_OFF_BSS_BYTES)
  gModInitOffset = ModRd64(p + #PMFMOD_OFF_INIT_OFFSET)
  gModRelocCount = ModRd32(p + #PMFMOD_OFF_RELOC_COUNT)
  gModRelocOffset = ModRd32(p + #PMFMOD_OFF_RELOC_OFFSET)
  gModMatchCount = ModRd32(p + #PMFMOD_OFF_MATCH_COUNT)
  gModMatchOffset = ModRd32(p + #PMFMOD_OFF_MATCH_OFFSET)
  gModProbeOffset = ModRd64(p + #PMFMOD_OFF_PROBE_OFFSET)
  gModQuiesceOffset = ModRd64(p + #PMFMOD_OFF_QUIESCE)

  If gModImageBytes <= 0 Or ModAddOk(#PMFMOD_HEADER_BYTES, gModImageBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModImageBytes)
  EndIf
  imageEnd = #PMFMOD_HEADER_BYTES + gModImageBytes
  wantReloc = ModAlignUp(imageEnd, 8)
  ; Bound both endpoints against the supplied container before examining pad
  ; bytes. A forged image length must never turn validation into an OOB read.
  If wantReloc < 0 Or imageEnd > bytes Or wantReloc > bytes
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModRelocOffset)
  EndIf
  If gModRelocOffset <> wantReloc Or ModPadZero(p, imageEnd, wantReloc) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModRelocOffset)
  EndIf
  If ModMulOk(gModRelocCount, #PMFMOD_RELOC_BYTES) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModRelocCount)
  EndIf
  relocBytes = gModRelocCount * #PMFMOD_RELOC_BYTES
  If ModAddOk(gModRelocOffset, relocBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, relocBytes)
  EndIf
  relocEnd = gModRelocOffset + relocBytes
  If gModMatchOffset <> relocEnd Or gModMatchCount < 1 Or gModMatchCount > #PMFMOD_MATCH_MAX
    ProcedureReturn ModFail(#MOD_ERR_MATCH, -1, gModMatchCount)
  EndIf
  If ModMulOk(gModMatchCount, #PMFMOD_MATCH_BYTES) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModMatchCount)
  EndIf
  matchBytes = gModMatchCount * #PMFMOD_MATCH_BYTES
  If ModAddOk(gModMatchOffset, matchBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, matchBytes)
  EndIf
  matchEnd = gModMatchOffset + matchBytes
  If matchEnd <> bytes
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, matchEnd)
  EndIf

  If gModBssOffset < gModImageBytes Or (gModBssOffset & (#PMFMOD_BSS_ALIGN - 1)) <> 0 Or gModBssBytes < 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModBssOffset)
  EndIf
  If ModAddOk(gModBssOffset, gModBssBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModBssBytes)
  EndIf
  bssEnd = gModBssOffset + gModBssBytes
  objectEnd = gModImageBytes
  If bssEnd > objectEnd
    objectEnd = bssEnd
  EndIf
  gModObjectBytes = ModAlignUp(objectEnd, #PMFMOD_LOAD_ALIGN)
  If gModObjectBytes <= 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, objectEnd)
  EndIf
  If ModEntryOffsetOk(gModInitOffset, 0) = 0 Or ModEntryOffsetOk(gModProbeOffset, 1) = 0 Or ModEntryOffsetOk(gModQuiesceOffset, 1) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModInitOffset)
  EndIf

  i = 0
  While i < gModMatchCount
    If ModMatchOk(p, i) = 0
      ProcedureReturn ModFail(#MOD_ERR_MATCH, i, 0)
    EndIf
    j = 0
    While j < i
      If ModMatchSame(p, i, j) <> 0
        ProcedureReturn ModFail(#MOD_ERR_MATCH, i, j)
      EndIf
      j = j + 1
    Wend
    i = i + 1
  Wend

  i = 0
  While i < gModRelocCount
    If ModRelocSiteOk(p, i) <> #MOD_OK
      ProcedureReturn gModError
    EndIf
    i = i + 1
  Wend

  ; Hash before arena mutation. This is integrity against damage, not trust.
  If ModDigestOk(p, bytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_HASH, -1, 0)
  EndIf
  i = 0
  While i < #PMFMOD_DIGEST_BYTES
    gModDigest[i] = PeekA(p + #PMFMOD_OFF_SHA256 + i) & 255
    i = i + 1
  Wend

  gModContainer = p
  gModContainerBytes = bytes
  gModPrepared = 1
  gModError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

Procedure.i ModRelocateOne(base.i, index.i)
  Define r.i
  Define site.i
  Define kind.i
  Define addend.i
  Define at.i
  Define target.i
  Define word.i
  Define pages.i
  Define immlo.i
  Define immhi.i
  Define shift.i
  Define delta.i
  r = gModContainer + gModRelocOffset + index * #PMFMOD_RELOC_BYTES
  site = ModRd32(r + #PMFMOD_REL_OFF_SITE)
  kind = ModRd16(r + #PMFMOD_REL_OFF_KIND)
  addend = ModRd64(r + #PMFMOD_REL_OFF_ADDEND)
  at = base + site
  target = base + addend

  Select kind
    Case #MREL_ADRP_PAGE
      word = PeekN(at)
      pages = (target / 4096) - (at / 4096)
      immlo = pages & 3
      immhi = (pages >> 2) & $7FFFF
      word = (word & $9F00001F) | (immlo << 29) | (immhi << 5)
      PokeN(at, word)
    Case #MREL_ADD_LO12
      word = PeekN(at)
      word = (word & $FFC003FF) | ((target & $FFF) << 10)
      PokeN(at, word)
    Case #MREL_ABS64
      PokeI(at, target)
    Case #MREL_MOVW_G0
      shift = 0
      word = PeekN(at)
      word = (word & $FFE0001F) | (((target >> shift) & $FFFF) << 5)
      PokeN(at, word)
    Case #MREL_MOVW_G1
      shift = 16
      word = PeekN(at)
      word = (word & $FFE0001F) | (((target >> shift) & $FFFF) << 5)
      PokeN(at, word)
    Case #MREL_MOVW_G2
      shift = 32
      word = PeekN(at)
      word = (word & $FFE0001F) | (((target >> shift) & $FFFF) << 5)
      PokeN(at, word)
    Case #MREL_MOVW_G3
      shift = (kind - #MREL_MOVW_G0) * 16
      word = PeekN(at)
      word = (word & $FFE0001F) | (((target >> shift) & $FFFF) << 5)
      PokeN(at, word)
    Case #MREL_CALL26
      delta = target - at
      word = PeekN(at)
      word = (word & $FC000000) | ((delta >> 2) & $03FFFFFF)
      PokeN(at, word)
    Default
      ProcedureReturn #MOD_ERR_RELKIND
  EndSelect
  ProcedureReturn #MOD_OK
EndProcedure
