; ======================================================================
;  DRIVER-MODULE RECORDS AND TRANSACTIONAL ARENA ALLOCATION
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Hal/module_format.pbi
;    Anvil/Core/sha256.pbi
;    Anvil/Core/mod_container.pbi
;
;  REQUIRED BOARD CONTRACT (not implemented here and not in a map):
;    HwModArenaBase()              4 KiB-aligned first byte
;    HwModArenaBytes()             byte count of a board-reserved range
;    HwModArenaRegion()            which HwMonRegion* index IS the arena,
;                                  or -1 if the board does not declare it
;    HwModCodeSync(base, bytes)    unconditional D-cache clean / I-cache
;                                  invalidate; returns 1 only on success
;    HwMonRegions() / HwMonRegionLo() / HwMonRegionHi()
;    HwPayWindows() / HwPayLo() / HwPayHi()
;
;  The board is responsible for proving that the supplied range is real and
;  disjoint from its live image, data, payload, DMA, display and firmware
;  reservations. In particular, the obsolete $08A00000..$091FFFFF proposal is
;  the Pi DSI framebuffer now and is forbidden. This engine contains no board
;  address and does not mutate a board memory map.
;
;  THAT PROOF IS NOW CHECKED RATHER THAN TRUSTED - ModArenaInit() walks the
;  board's OWN declared regions and payload windows and refuses an arena that
;  overlaps one. It is the same board answering both questions, which is the
;  point: a board that reserves a range in one procedure and hands the same
;  range out as arena in another is stating two contradictory facts, and the
;  contradiction is visible from here without this file knowing a single
;  address. The board's own arena region is skipped by index, because a range
;  necessarily overlaps itself.
;
;  READY below means only: header/hash/relocations passed, bytes were copied,
;  BSS/padding were zeroed, relocations applied, and code cache synchronised.
;  It does NOT mean matched, probed, initialised, bound or active.
; ======================================================================

#MOD_RECORD_MAX = 16

Global gModArenaReady.i
Global gModArenaBase.i
Global gModArenaBytes.i
Global gModArenaEnd.i                 ; one past the board-owned range
Global gModArenaNext.i
Global gModRecordCount.i
Global gModLastRecord.i

; Which map a #MOD_ERR_REGION refusal's index belongs to: 0 a region the
; board declares through HwMonRegion*(), 1 a payload window. One flag
; rather than a signed encoding, because a refusal sentence that decodes
; a negative index is a refusal nobody checks.
Global gModRegionKind.i

Global Dim gModRecState.i[#MOD_RECORD_MAX]
Global Dim gModRecBase.i[#MOD_RECORD_MAX]
Global Dim gModRecBytes.i[#MOD_RECORD_MAX]
Global Dim gModRecImageBytes.i[#MOD_RECORD_MAX]
Global Dim gModRecBssOffset.i[#MOD_RECORD_MAX]
Global Dim gModRecBssBytes.i[#MOD_RECORD_MAX]
Global Dim gModRecInit.i[#MOD_RECORD_MAX]
Global Dim gModRecProbe.i[#MOD_RECORD_MAX]
Global Dim gModRecQuiesce.i[#MOD_RECORD_MAX]
Global Dim gModRecAbiMajor.i[#MOD_RECORD_MAX]
Global Dim gModRecAbiMinor.i[#MOD_RECORD_MAX]
Global Dim gModRecSeamCount.i[#MOD_RECORD_MAX]
Global Dim gModRecSeams.i[#MOD_RECORD_MAX * #PMFMOD_SEAM_MAX]
Global Dim gModRecMatchCount.i[#MOD_RECORD_MAX]
Global Dim gModRecMatches.a[#MOD_RECORD_MAX * #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES]
Global Dim gModRecDigest.a[#MOD_RECORD_MAX * #PMFMOD_DIGEST_BYTES]

Procedure ModRecordClear(index.i)
  Define i.i
  gModRecState[index] = #MOD_STATE_EMPTY
  gModRecBase[index] = 0
  gModRecBytes[index] = 0
  gModRecImageBytes[index] = 0
  gModRecBssOffset[index] = 0
  gModRecBssBytes[index] = 0
  gModRecInit[index] = 0
  gModRecProbe[index] = 0
  gModRecQuiesce[index] = 0
  gModRecAbiMajor[index] = 0
  gModRecAbiMinor[index] = 0
  gModRecSeamCount[index] = 0
  gModRecMatchCount[index] = 0
  i = 0
  While i < #PMFMOD_SEAM_MAX
    gModRecSeams[index * #PMFMOD_SEAM_MAX + i] = #PMFMOD_SEAM_UNUSED
    i = i + 1
  Wend
  i = 0
  While i < #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES
    gModRecMatches[index * #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES + i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #PMFMOD_DIGEST_BYTES
    gModRecDigest[index * #PMFMOD_DIGEST_BYTES + i] = 0
    i = i + 1
  Wend
EndProcedure

Procedure.i ModRangesOverlap(a0.i, a1.i, b0.i, b1.i)
  If a0 < b1 And b0 < a1
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  ModArenaRegionClash(base, endAt) - the arena against the board's own
;  declared map. Answers the clashing region index, or -1.
;
;  HwMonRegion*() is a CLOSED range (lo..hi inclusive) and the arena is
;  half-open here, which is why the comparison adds one to hi rather than
;  reusing the range as written. Getting that wrong would let an arena
;  start exactly on the last byte of the framebuffer and pass.
;
;  A region index the board does not have answers lo above hi, which
;  matches nothing - so an out-of-range index cannot invent a clash.
; ----------------------------------------------------------------------
Procedure.i ModArenaRegionClash(base.i, endAt.i)
  Define i.i
  Define n.i
  Define skip.i
  Define lo.i
  Define hi.i
  skip = HwModArenaRegion()
  n = HwMonRegions()
  i = 0
  While i < n
    If i <> skip
      lo = HwMonRegionLo(i)
      hi = HwMonRegionHi(i)
      If hi >= lo
        If ModRangesOverlap(base, endAt, lo, hi + 1) <> 0
          ProcedureReturn i
        EndIf
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

; The same question against the windows a payload may be loaded into. A
; module inside one of those would be overwritten by the next `boot`, and
; InPayload() would ALLOW it - the windows are the whole of what it calls
; allowed. Answers the window index, or -1.
Procedure.i ModArenaPayClash(base.i, endAt.i)
  Define i.i
  Define n.i
  Define lo.i
  Define hi.i
  n = HwPayWindows()
  i = 0
  While i < n
    lo = HwPayLo(i)
    hi = HwPayHi(i)
    If hi >= lo
      If ModRangesOverlap(base, endAt, lo, hi + 1) <> 0
        ProcedureReturn i
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i ModArenaInit()
  Define i.i
  Define base.i
  Define bytes.i
  Define clash.i
  ; Cold-start only. Reinitialising would forget READY records and make live
  ; module code available for overwrite, which would be an unsafe unload.
  If gModArenaReady <> 0
    ProcedureReturn ModFail(#MOD_ERR_INIT, -1, gModRecordCount)
  EndIf
  base = HwModArenaBase()
  bytes = HwModArenaBytes()
  ; A BOARD THAT OFFERS NO ARENA GETS ITS OWN CODE, not an alignment
  ; complaint about zero. "This board has nowhere to put a module yet" and
  ; "this board's arena is misaligned" send an operator to two completely
  ; different places, and answering the first with the second is the kind
  ; of nearly-right refusal that costs an afternoon.
  If base = 0 Or bytes = 0
    ProcedureReturn ModFail(#MOD_ERR_NOARENA, -1, 0)
  EndIf
  If base < 0 Or (base & (#PMFMOD_LOAD_ALIGN - 1)) <> 0 Or bytes < 0
    ProcedureReturn ModFail(#MOD_ERR_ALIGN, -1, base)
  EndIf
  If ModAddOk(base, bytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, bytes)
  EndIf
  ; Before one byte of it is believed. A refusal here names the region
  ; index, which HwMonRegionSay() turns into the board's own words.
  gModRegionKind = 0
  clash = ModArenaRegionClash(base, base + bytes)
  If clash >= 0
    ProcedureReturn ModFail(#MOD_ERR_REGION, clash, base)
  EndIf
  gModRegionKind = 1
  clash = ModArenaPayClash(base, base + bytes)
  If clash >= 0
    ProcedureReturn ModFail(#MOD_ERR_REGION, clash, base)
  EndIf
  gModRegionKind = 0
  ModSeamReset()
  gModArenaBase = base
  gModArenaBytes = bytes
  gModArenaEnd = base + bytes
  gModArenaNext = base
  gModRecordCount = 0
  gModLastRecord = -1
  i = 0
  While i < #MOD_RECORD_MAX
    ModRecordClear(i)
    i = i + 1
  Wend
  gModArenaReady = 1
  gModError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

Procedure ModZeroRange(base.i, bytes.i)
  Define i.i
  i = 0
  While i < bytes
    PokeB(base + i, 0)
    i = i + 1
  Wend
EndProcedure

Procedure ModCopyImage(dst.i)
  Define src.i
  Define i.i
  src = gModContainer + #PMFMOD_HEADER_BYTES
  i = 0
  While i < gModImageBytes
    PokeB(dst + i, PeekA(src + i) & 255)
    i = i + 1
  Wend
EndProcedure

Procedure ModRecordCommit(index.i, base.i)
  Define i.i
  gModRecBase[index] = base
  gModRecBytes[index] = gModObjectBytes
  gModRecImageBytes[index] = gModImageBytes
  gModRecBssOffset[index] = gModBssOffset
  gModRecBssBytes[index] = gModBssBytes
  gModRecInit[index] = base + gModInitOffset
  gModRecProbe[index] = 0
  If gModProbeOffset <> 0
    gModRecProbe[index] = base + gModProbeOffset
  EndIf
  gModRecQuiesce[index] = 0
  If gModQuiesceOffset <> 0
    gModRecQuiesce[index] = base + gModQuiesceOffset
  EndIf
  gModRecAbiMajor[index] = gModAbiMajor
  gModRecAbiMinor[index] = gModAbiMinor
  gModRecSeamCount[index] = gModSeamCount
  gModRecMatchCount[index] = gModMatchCount
  i = 0
  While i < #PMFMOD_SEAM_MAX
    gModRecSeams[index * #PMFMOD_SEAM_MAX + i] = gModSeam[i]
    i = i + 1
  Wend
  i = 0
  While i < #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES
    If i < gModMatchCount * #PMFMOD_MATCH_BYTES
      gModRecMatches[index * #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES + i] = PeekA(gModContainer + gModMatchOffset + i) & 255
    Else
      gModRecMatches[index * #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES + i] = 0
    EndIf
    i = i + 1
  Wend
  i = 0
  While i < #PMFMOD_DIGEST_BYTES
    gModRecDigest[index * #PMFMOD_DIGEST_BYTES + i] = gModDigest[i]
    i = i + 1
  Wend
  ; State is the last store. A reader never observes a half-filled READY row.
  gModRecState[index] = #MOD_STATE_READY
EndProcedure

Procedure.i ModRecordMatchAddr(index.i, match.i)
  If index < 0 Or index >= gModRecordCount Or match < 0 Or match >= gModRecMatchCount[index]
    ProcedureReturn 0
  EndIf
  ProcedureReturn @gModRecMatches[index * #PMFMOD_MATCH_MAX * #PMFMOD_MATCH_BYTES + match * #PMFMOD_MATCH_BYTES]
EndProcedure

Procedure.i ModArenaLoadPrepared()
  Define base.i
  Define endAt.i
  Define sourceEnd.i
  Define i.i
  Define rc.i
  Define index.i
  gModLastRecord = -1
  If gModArenaReady = 0 Or gModPrepared = 0
    ProcedureReturn ModFail(#MOD_ERR_HEADER, -1, 0)
  EndIf
  If gModRecordCount >= #MOD_RECORD_MAX
    ProcedureReturn ModFail(#MOD_ERR_RECORDS_FULL, -1, gModRecordCount)
  EndIf
  base = ModAlignUp(gModArenaNext, gModAlign)
  If base < 0 Or ModAddOk(base, gModObjectBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_ARENA_FULL, -1, gModObjectBytes)
  EndIf
  endAt = base + gModObjectBytes
  If base < gModArenaBase Or endAt > gModArenaEnd
    ProcedureReturn ModFail(#MOD_ERR_ARENA_FULL, -1, gModObjectBytes)
  EndIf
  If ModAddOk(gModContainer, gModContainerBytes) = 0
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, gModContainerBytes)
  EndIf
  sourceEnd = gModContainer + gModContainerBytes
  If ModRangesOverlap(gModContainer, sourceEnd, base, endAt) <> 0
    ProcedureReturn ModFail(#MOD_ERR_OVERLAP, -1, base)
  EndIf

  ; No allocator or record state changes before every possible refusal above.
  ; The uncommitted arena span is zeroed first, so padding and BSS are known.
  ModZeroRange(base, gModObjectBytes)
  ModCopyImage(base)
  i = 0
  While i < gModRelocCount
    rc = ModRelocateOne(base, i)
    If rc <> #MOD_OK
      ModZeroRange(base, gModObjectBytes)
      ProcedureReturn ModFail(rc, i, 0)
    EndIf
    i = i + 1
  Wend

  ; Required even when there were zero relocations: CPU stores created code.
  If HwModCodeSync(base, gModImageBytes) <> 1
    ModZeroRange(base, gModObjectBytes)
    ProcedureReturn ModFail(#MOD_ERR_SYNC, -1, base)
  EndIf

  index = gModRecordCount
  ModRecordCommit(index, base)
  gModArenaNext = endAt
  gModRecordCount = index + 1
  gModLastRecord = index
  gModPrepared = 0
  gModError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

; Half-open query used by future address-safety policy. It deliberately has a
; new name: HitsMonitor() keeps meaning the monitor's own board-declared ranges.
Procedure.i ModHitsRange(lo.i, hi.i)
  Define i.i
  Define endAt.i
  If hi < lo
    ProcedureReturn 0
  EndIf
  If hi = #MOD_I64_MAX
    ProcedureReturn 1
  EndIf
  endAt = hi + 1
  i = 0
  While i < gModRecordCount
    ; EVERY state at or above READY, not READY exactly. A record that has
    ; gone on to be probed, initialised, refused or unloaded still has the
    ; same bytes at the same base, and a FAILED or QUIESCED module's code
    ; is memory the allocator will never hand out again - so a `fill` over
    ; it is as wrong as a `fill` over a running driver and is refused the
    ; same way. Testing one state exactly protected only the narrow window
    ; between placement and activation.
    If gModRecState[i] >= #MOD_STATE_READY
      If ModRangesOverlap(lo, endAt, gModRecBase[i], gModRecBase[i] + gModRecBytes[i]) <> 0
        gModLastRecord = i
        ProcedureReturn 1
      EndIf
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure
