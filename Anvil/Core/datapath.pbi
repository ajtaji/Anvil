; ======================================================================
;  datapath.pbi - the `data:/` path form and the `data.path` setting.
; ----------------------------------------------------------------------
;  WHY IT EXISTS. Weights, model packs, kept monitor images and diagnostic
;  payloads are data, and where data lives depends on the medium. A stick
;  with one partition keeps it beside the boot files; a stick with a big
;  exFAT data partition keeps it on partition 2. A recipe, a host tool or a
;  run manifest that wrote `2:/models/MODEL.PMW` would break on the first
;  medium that has one partition, and one that wrote `MODEL.PMW` would
;  break on the second. So there is ONE editable location:
;
;      settings set data.path 2:/          this bench: the exFAT partition
;      settings save
;      load data:/models/MODEL.PMW 40000000
;
;  and `data:/models/MODEL.PMW` means `<data.path>/models/MODEL.PMW`. With
;  data.path absent or empty it means `/models/MODEL.PMW` - the root of
;  partition 1 - so a stock one-partition card works with no setting.
;
;  THE PREFIX IS `data:` (any case) and it is resolved before a path reaches
;  the board's storage seam, so it works for every command that takes a
;  storage path and the seam never has to know settings exist. A colon cannot
;  occur in a FAT or exFAT name, so `data:` never collides with a real file.
;
;  THE JOIN is exact and says what it refuses:
;    - one separator between the location and the rest, however many the
;      two sides carry ("2:/" + "/models" and "2:" + "models" both give
;      "2:/models"); a location that names a partition keeps its colon;
;    - a location that itself begins `data:` is refused - it would name
;      itself;
;    - a result longer than the buffer is refused, never truncated.
;
;  THIS FILE IS PURE: no settings, no storage, no printing. DataPathJoin is
;  gated in tools/datapath_emitted_check.py; the lookup of the setting is in
;  Anvil/Core/fs_cmd.pbi's ParseStoragePath.
; ======================================================================

; 1 if *path begins with `data:` in any case.
Procedure.i DataPathIs(*path)
  Define i.i
  Define c.i
  If *path = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < 5
    c = PeekA(*path + i)
    If c >= 65 And c <= 90
      c = c + 32
    EndIf
    If c <> PeekA(?datapath_prefix + i)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Resolve *path into *dst (capacity bytes including the terminator).
; *base is the data.path value, or 0 / "" for the default (partition 1 root).
; A path that does not begin `data:` is copied unchanged.
; Returns the resulting length, or -1 when the result would not fit, and
; -2 when the location itself begins `data:`.
Procedure.i DataPathJoin(*base, *path, *dst, capacity.i)
  Define n.i
  Define i.i
  Define baseLen.i
  Define restAt.i
  Define c.i
  If *dst = 0 Or capacity < 1
    ProcedureReturn -1
  EndIf
  n = 0
  If DataPathIs(*path) = 0
    i = 0
    c = PeekA(*path)
    While c <> 0
      If n >= capacity - 1
        PokeA(*dst, 0)
        ProcedureReturn -1
      EndIf
      PokeA(*dst + n, c)
      n = n + 1
      i = i + 1
      c = PeekA(*path + i)
    Wend
    PokeA(*dst + n, 0)
    ProcedureReturn n
  EndIf
  ; The location, without its trailing separators.
  baseLen = 0
  If *base <> 0
    If DataPathIs(*base) <> 0
      PokeA(*dst, 0)
      ProcedureReturn -2
    EndIf
    While PeekA(*base + baseLen) <> 0
      baseLen = baseLen + 1
    Wend
    While baseLen > 0
      c = PeekA(*base + baseLen - 1)
      If c <> 47 And c <> 92
        Break
      EndIf
      baseLen = baseLen - 1
    Wend
  EndIf
  i = 0
  While i < baseLen
    If n >= capacity - 1
      PokeA(*dst, 0)
      ProcedureReturn -1
    EndIf
    PokeA(*dst + n, PeekA(*base + i))
    n = n + 1
    i = i + 1
  Wend
  ; Exactly one separator, then the rest without its leading separators.
  If n >= capacity - 1
    PokeA(*dst, 0)
    ProcedureReturn -1
  EndIf
  PokeA(*dst + n, 47)
  n = n + 1
  restAt = 5
  c = PeekA(*path + restAt)
  While c = 47 Or c = 92
    restAt = restAt + 1
    c = PeekA(*path + restAt)
  Wend
  While c <> 0
    If n >= capacity - 1
      PokeA(*dst, 0)
      ProcedureReturn -1
    EndIf
    PokeA(*dst + n, c)
    n = n + 1
    restAt = restAt + 1
    c = PeekA(*path + restAt)
  Wend
  PokeA(*dst + n, 0)
  ProcedureReturn n
EndProcedure

DataSection
  datapath_prefix: Data.a 100,97,116,97,58
EndDataSection
