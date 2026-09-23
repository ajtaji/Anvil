; ======================================================================
;  MODULES.TXT - DISCOVERY, AND ONE FILE INTO ONE RECORD
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Hal/module_format.pbi, Anvil/Hal/module_runtime.pbi
;    Anvil/Core/mod_registry.pbi, mod_container.pbi, mod_arena.pbi,
;    Anvil/Core/mod_lifecycle.pbi
;    the storage seam: HwFileOpen / HwFileSize / HwFileReadAt / HwFileClose
;
;  REQUIRED BOARD CONTRACT:
;    HwModStageAddr()   where a container is read to before it is judged
;    HwModStageBytes()  how big a container this board will accept
;
;  WHY A CONTAINER IS STAGED AND NOT READ STRAIGHT INTO THE ARENA. The
;  digest covers the header as well as the image, and the relocation
;  table and the compatible ids sit AFTER the image - so the whole file
;  has to be in one place before any of it can be believed. Reading it
;  into the arena first would mean writing unverified bytes into the
;  range live drivers occupy, and a refusal after that point would have
;  already done the damage it was refusing to allow. The staging window
;  is board-declared, inside the board's own reserved region, and is not
;  the arena, so a refused module never touches a loaded one.
;
;  THE MANIFEST IS IN THE ROOT, BESIDE SETTINGS.TXT. The design note's
;  reason stands: this board's FAT reader descends into no subdirectory,
;  so ANVIL\MODULES.TXT cannot be opened here at all, and one place for
;  Anvil's files is easier to explain than two. On a board whose storage
;  seam has directories the name is unchanged and the board decides where
;  it lands, exactly as SettingsFileName() already works.
;
;  THE SYNTAX, and every rule of it is SETTINGS.TXT's rule, because an
;  operator should not have to learn two text formats for one board:
;
;      # a comment, and ; is one too
;      THERMAL.MOD
;      TOUCH.MOD     touch      ; narrow this one to a single seam
;
;  A line is a file name and an OPTIONAL seam name. The seam name can
;  only ever NARROW a module to a subset of what its digest-covered
;  header declares; naming a seam the header does not carry is refused.
;  That is what makes the manifest useful when two modules claim one
;  group, and it keeps the digest the only thing deciding what a module
;  may do.
;
;  A PARTIAL READ STOPS THE WALK. The modules after a refused line are
;  NOT loaded and the console says which line stopped it, because acting
;  on half a file is the confident wrong answer this project refuses.
; ======================================================================

#MOD_TEXT_MAX = 4096          ; a manifest longer than this is not a manifest

Global Dim gModText.a[#MOD_TEXT_MAX]
Global gModTextLen.i

; 0 nothing read, 1 complete, 2 PARTIAL - the same tri-state the settings
; store uses, and for the same reason: "there is no manifest" and "the
; manifest stopped at line 4" are different facts with different first
; things to check.
Global gModManifestState.i
Global gModManifestLine.i     ; the line a partial walk stopped at
Global gModManifestLoaded.i   ; how many modules the walk activated

Procedure.i ModManifestFileName()
  ProcedureReturn "MODULES.TXT"
EndProcedure

; ----------------------------------------------------------------------
;  ModLoadFile(*name) - one container from the medium into one record.
;
;  The order is the design's order and every step is here because of what
;  the one before it proved:
;
;    open and size      before a byte is read, so a file too big for the
;                       staging window is refused with its size named
;    read to staging    outside the arena, always
;    preflight          magic, version, ABI, architecture, layout, every
;                       relocation, then the digest - all of it before
;                       one arena byte moves
;    place              zero, copy, relocate, synchronise the caches;
;                       the transaction commits no record if any of that
;                       refuses
;    name and enable    the record carries the name the operator used and
;                       every seam its header declared
;
;  It does NOT activate. Discovery and activation are separate states on
;  purpose: a READY record is bytes that are known good, and that is a
;  different claim from a driver that has looked at hardware.
; ----------------------------------------------------------------------
Procedure.i ModLoadFile(name.i)
  Define n.i
  Define got.i
  Define rc.i
  Define rec.i
  Define stage.i
  Define room.i

  rec = gModRecordCount
  gModErrorRecord = rec
  If rec < #MOD_RECORD_MAX
    ModRecSetName(rec, name)
  Else
    gModErrorRecord = -1
  EndIf

  If gModArenaReady = 0
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, 0)
  EndIf
  If rec >= #MOD_RECORD_MAX
    ProcedureReturn ModFail(#MOD_ERR_RECORDS_FULL, -1, #MOD_RECORD_MAX)
  EndIf

  stage = HwModStageAddr()
  room = HwModStageBytes()
  If stage <= 0 Or room < #PMFMOD_HEADER_BYTES
    ProcedureReturn ModFail(#MOD_ERR_REGION, -1, stage)
  EndIf

  If HwFileOpen(name) = 0
    ProcedureReturn ModFail(#MOD_ERR_FILE, -1, HwFileLastError())
  EndIf
  n = HwFileSize()
  If n < #PMFMOD_HEADER_BYTES Or n > room
    HwFileClose()
    ProcedureReturn ModFail(#MOD_ERR_RANGE, -1, n)
  EndIf
  got = HwFileReadAt(0, stage, n)
  HwFileClose()
  If got <> n
    ProcedureReturn ModFail(#MOD_ERR_FILE, -1, got)
  EndIf

  rc = ModPreflight(stage, n, #SVC_ABI_MAJOR, #SVC_ABI_MINOR)
  If rc <> #MOD_OK
    gModErrorRecord = rec
    ProcedureReturn rc
  EndIf
  rc = ModArenaLoadPrepared()
  If rc <> #MOD_OK
    gModErrorRecord = rec
    ProcedureReturn rc
  EndIf

  ; The record committed. ModArenaLoadPrepared chose the index; it is the
  ; one this procedure named above, but read it back rather than assume -
  ; the allocator owns that number.
  rec = gModLastRecord
  gModErrorRecord = rec
  ModRecSetName(rec, name)
  ModRecUseAllSeams(rec)
  gModRecDevice[rec] = -1
  gModRecToken[rec] = 0
  gModRecMatched[rec] = -1
  gModRecInitCalls[rec] = 0
  gModRecInitResult[rec] = 0
  ProcedureReturn #MOD_OK
EndProcedure

; ----------------------------------------------------------------------
;  ModLoadAndActivate(*name, seam) - the whole of one manifest line.
;
;  `seam` is a #SVCCAP_* id to narrow to, or -1 for "every seam the
;  header declares". A narrowing that names a seam the header does not
;  carry refuses BEFORE the device is matched, so a mistyped manifest
;  line never reaches hardware.
; ----------------------------------------------------------------------
Procedure.i ModLoadAndActivate(name.i, sid.i)
  Define rc.i
  Define rec.i
  rc = ModLoadFile(name)
  If rc <> #MOD_OK
    ProcedureReturn rc
  EndIf
  rec = gModLastRecord
  If sid >= 0
    rc = ModRecNarrowToSeam(rec, sid)
    If rc <> #MOD_OK
      gModErrorRecord = rec
      gModRecState[rec] = #MOD_STATE_FAILED
      ProcedureReturn rc
    EndIf
  EndIf
  ProcedureReturn ModActivate(rec)
EndProcedure

; ----------------------------------------------------------------------
;  The line scanner. One pass, no allocation, no copy.
;
;  CR LF COUNTS AS ONE ENDING so a line number in a refusal is the line
;  number an editor shows. A lone CR and a lone LF each end a line too,
;  because a manifest typed on three different machines is the normal
;  case and a format that only understands one of them is a format that
;  fails silently on the other two.
; ----------------------------------------------------------------------
Procedure.i ModTextLineEnd(at.i)
  Define i.i
  i = at
  While i < gModTextLen
    If gModText[i] = 10 Or gModText[i] = 13
      ProcedureReturn i
    EndIf
    i = i + 1
  Wend
  ProcedureReturn gModTextLen
EndProcedure

Procedure.i ModTextNextLine(endAt.i)
  Define i.i
  i = endAt
  If i < gModTextLen And gModText[i] = 13
    i = i + 1
    If i < gModTextLen And gModText[i] = 10
      i = i + 1
    EndIf
    ProcedureReturn i
  EndIf
  If i < gModTextLen And gModText[i] = 10
    ProcedureReturn i + 1
  EndIf
  ProcedureReturn i
EndProcedure

Procedure.i ModTextSkipSpace(at.i, limit.i)
  Define i.i
  i = at
  While i < limit And (gModText[i] = 32 Or gModText[i] = 9)
    i = i + 1
  Wend
  ProcedureReturn i
EndProcedure

Procedure.i ModTextTokenEnd(at.i, limit.i)
  Define i.i
  i = at
  While i < limit And gModText[i] <> 32 And gModText[i] <> 9
    i = i + 1
  Wend
  ProcedureReturn i
EndProcedure

; A NUL-terminated copy of one token, because the storage seam takes a
; name and the buffer holds a run. It is a fixed array rather than a
; pointer into gModText so the terminator cannot overwrite the byte that
; follows the name in the manifest.
Global Dim gModLineName.a[#MOD_NAME_MAX]

Procedure.i ModTextCopyName(at.i, endAt.i)
  Define i.i
  Define n.i
  n = endAt - at
  If n <= 0 Or n >= #MOD_NAME_MAX
    ProcedureReturn 0
  EndIf
  i = 0
  While i < n
    gModLineName[i] = gModText[at + i]
    i = i + 1
  Wend
  While i < #MOD_NAME_MAX
    gModLineName[i] = 0
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  ModManifestRead() - the file into the buffer, nothing more.
;
;  "NOT THERE" IS NOT A FAILURE OF THE MEDIUM and it is the normal case:
;  a board with no modules has no manifest and should not be told that
;  its card is faulty. It answers 0 with gModManifestState left at 0.
; ----------------------------------------------------------------------
Procedure.i ModManifestRead()
  Define n.i
  Define got.i
  gModTextLen = 0
  gModManifestState = 0
  gModManifestLine = 0
  If HwFileOpen(ModManifestFileName()) = 0
    ProcedureReturn 0
  EndIf
  n = HwFileSize()
  If n > #MOD_TEXT_MAX
    HwFileClose()
    gModManifestState = 2
    ProcedureReturn ModFail(#MOD_ERR_MANIFEST, 0, n)
  EndIf
  got = 0
  If n > 0
    got = HwFileReadAt(0, @gModText[0], n)
  EndIf
  HwFileClose()
  If got <> n
    gModManifestState = 2
    ProcedureReturn ModFail(#MOD_ERR_MANIFEST, 0, got)
  EndIf
  gModTextLen = n
  ; A UTF-8 BOM at offset 0 and nowhere else. An editor that writes one
  ; would otherwise make the first file name unopenable with no clue why.
  If gModTextLen >= 3 And gModText[0] = $EF And gModText[1] = $BB And gModText[2] = $BF
    gModText[0] = 32
    gModText[1] = 32
    gModText[2] = 32
  EndIf
  gModManifestState = 1
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  ModManifestWalk() - read it, then act on every line in order.
;
;  Answers the number of modules ACTIVATED. A refused line stops the walk
;  and leaves gModManifestState at 2 with gModManifestLine naming it;
;  the caller prints the refusal, which has already been composed by the
;  step that refused.
; ----------------------------------------------------------------------
Procedure.i ModManifestWalk()
  Define at.i
  Define lineNo.i
  Define endAt.i
  Define p.i
  Define q.i
  Define sid.i
  Define rc.i

  gModManifestLoaded = 0
  If ModManifestRead() <> 1
    ProcedureReturn 0
  EndIf

  at = 0
  lineNo = 0
  While at < gModTextLen
    lineNo = lineNo + 1
    endAt = ModTextLineEnd(at)
    p = ModTextSkipSpace(at, endAt)
    If p < endAt And gModText[p] <> 35 And gModText[p] <> 59
      q = ModTextTokenEnd(p, endAt)
      If ModTextCopyName(p, q) = 0
        gModManifestState = 2
        gModManifestLine = lineNo
        ProcedureReturn ModFail(#MOD_ERR_MANIFEST, lineNo, q - p)
      EndIf
      ; The optional seam column, and a trailing comment after it.
      sid = -1
      p = ModTextSkipSpace(q, endAt)
      If p < endAt And gModText[p] <> 35 And gModText[p] <> 59
        q = ModTextTokenEnd(p, endAt)
        sid = ModSeamIdOfName(@gModText[p], q - p)
        If sid < 0
          gModManifestState = 2
          gModManifestLine = lineNo
          ProcedureReturn ModFail(#MOD_ERR_MANIFEST, lineNo, 0)
        EndIf
      EndIf
      rc = ModLoadAndActivate(@gModLineName[0], sid)
      If rc <> #MOD_OK
        gModManifestState = 2
        gModManifestLine = lineNo
        ProcedureReturn rc
      EndIf
      gModManifestLoaded = gModManifestLoaded + 1
    EndIf
    at = ModTextNextLine(endAt)
  Wend
  gModManifestState = 1
  ProcedureReturn gModManifestLoaded
EndProcedure

; ----------------------------------------------------------------------
;  ModBoot() - the whole of module discovery at boot.
;
;  It runs AFTER the console is up and BEFORE anything capability-gated,
;  so a refusal is seen on whatever console this board came up on and a
;  driver is in place before autoboot can hand the board to a payload.
;
;  IT IS NEVER FATAL. A board with no modules, no manifest or a refused
;  module still reaches its prompt: every seam a module would have filled
;  has a core answer or an honest refusal behind it, which is the whole
;  reason the capability model distinguishes "no hardware", "the core
;  reaches it" and "present, but nothing fills it".
; ----------------------------------------------------------------------
Procedure ModBoot()
  Define rc.i
  ModLifecycleReset()
  rc = ModArenaInit()
  If rc = #MOD_ERR_NOARENA
    ; A BOARD WITH NO ARENA SAYS NOTHING AT BOOT. It is not a fault and it
    ; is not going to change between one power cycle and the next, so a
    ; refusal on every boot would be noise an operator learns to skip -
    ; and a refusal people learn to skip is worse than none. `mod` says it
    ; plainly the moment anybody asks.
    ProcedureReturn
  EndIf
  If rc <> #MOD_OK
    gModErrorRecord = -1
    ModSayRefusal()
    ProcedureReturn
  EndIf
  rc = ModManifestWalk()
  If gModManifestState = 2
    ModSayRefusal()
    Print("   MODULES.TXT line ")
    PrintDec(gModManifestLine)
    Print(" stopped the walk; the lines after it were not read.")
    PrintNl()
    ProcedureReturn
  EndIf
  If gModManifestLoaded > 0
    Print("modules: ")
    PrintDec(gModManifestLoaded)
    Print(" loaded from ")
    UartWriteStr(ModManifestFileName())
    PrintNl()
  EndIf
EndProcedure
