; ======================================================================
;  programs_cmd.pbi - WHAT CAN BE RUN FROM THE MEDIUM, AND RUNNING IT BY NAME.
;
;  `programs` lists every payload container (a file whose first eight bytes
;  are "PMFBOOT" and a zero) in the root of partition 2, in each folder of
;  that root, and in the root of partition 1. Typing one of the listed names
;  at the prompt - the file name without .pmf, in any case - runs it exactly
;  as `boot <path>` would: the container's own load address, its SHA-256
;  proved before the jump, the deadman if one is armed.
;
;  A NAME ONLY RUNS WHEN NO COMMAND HAS IT. The dispatcher asks this file
;  last, from its unknown-command arm, so a program called `ls` can never
;  take the place of the command.
;
;  NOTHING HERE STARTS ANYTHING BY ITSELF. Starting a program at power-up is
;  the boot.file setting's job and stays a separate decision.
;
;  INCLUDE ORDER: after Anvil/Core/pmfboot.pbi (PmfBootFile) and after the
;  storage seam (HwDir*, HwFile*).
; ======================================================================

#PRG_MAX      = 32           ; programs remembered from one listing
#PRG_PATH     = 256          ; bytes of a path, the NUL included
#PRG_NAME     = 64           ; bytes of a name, the NUL included
#PRG_DIRS     = 24           ; folders of partition 2's root that are looked in
#PRG_CAND     = 64           ; .pmf files seen before their first bytes are read

Global Dim gPrgPath.a[#PRG_MAX * #PRG_PATH]
Global Dim gPrgName.a[#PRG_MAX * #PRG_NAME]
Global Dim gPrgSize.i[#PRG_MAX]
Global gPrgCount.i
Global gPrgListed.i           ; 1 once a listing has been made this session
Global Dim gPrgCand.a[#PRG_CAND * #PRG_PATH]
Global Dim gPrgCandSize.i[#PRG_CAND]
Global gPrgCandN.i
Global Dim gPrgDir.a[#PRG_DIRS * #PRG_NAME]
Global gPrgDirN.i
Global gPrgDirsSkipped.i
Global Dim gPrgEnt.a[#PRG_PATH]
Global Dim gPrgHead.a[16]

; Copies the NUL-terminated text at *src onto dst + at; answers the new end, or -1 when it would not fit.
Procedure.i prg_Put(dst.i, at.i, cap.i, *src)
  Define i.i, c.i
  i = 0
  c = PeekA(*src)
  While c <> 0
    If at + i >= cap - 1
      ProcedureReturn -1
    EndIf
    PokeA(dst + at + i, c)
    i = i + 1
    c = PeekA(*src + i)
  Wend
  PokeA(dst + at + i, 0)
  ProcedureReturn at + i
EndProcedure

Procedure.i prg_Len(*s)
  Define i.i
  i = 0
  While PeekA(*s + i) <> 0
    i = i + 1
  Wend
  ProcedureReturn i
EndProcedure

Procedure.i prg_Lower(c.i)
  If c >= 65 And c <= 90
    ProcedureReturn c + 32
  EndIf
  ProcedureReturn c
EndProcedure

; 1 when the name ends in .pmf, in any case.
Procedure.i prg_EndsPmf(*s)
  Define n.i
  n = prg_Len(*s)
  If n < 5
    ProcedureReturn 0
  EndIf
  If PeekA(*s + n - 4) <> 46 : ProcedureReturn 0 : EndIf                  ; .
  If prg_Lower(PeekA(*s + n - 3)) <> 112 : ProcedureReturn 0 : EndIf      ; p
  If prg_Lower(PeekA(*s + n - 2)) <> 109 : ProcedureReturn 0 : EndIf      ; m
  If prg_Lower(PeekA(*s + n - 1)) <> 102 : ProcedureReturn 0 : EndIf      ; f
  ProcedureReturn 1
EndProcedure

; 1 when the file at *path begins "PMFBOOT" and a zero byte.
Procedure.i prg_IsContainer(*path)
  Define got.i, ok.i
  If HwFileOpen(*path) = 0
    ProcedureReturn 0
  EndIf
  got = HwFileReadAt(0, @gPrgHead[0], 8)
  HwFileClose()
  If got <> 8
    ProcedureReturn 0
  EndIf
  ok = Bool(gPrgHead[0] = 80 And gPrgHead[1] = 77 And gPrgHead[2] = 70 And gPrgHead[3] = 66)   ; PMFB
  ok = ok & Bool(gPrgHead[4] = 79 And gPrgHead[5] = 79 And gPrgHead[6] = 84 And gPrgHead[7] = 0) ; OOT, 0
  ProcedureReturn ok
EndProcedure

; One folder: every .pmf file becomes a candidate; with keepDirs, every folder of it is remembered too.
Procedure prg_ScanDir(*dir, keepDirs.i)
  Define r.i, n.i, at.i
  If HwDirOpen(*dir) = 0
    ProcedureReturn
  EndIf
  Repeat
    r = HwDirNext()
    If r <> 1
      Break
    EndIf
    n = HwDirNameUtf8(@gPrgEnt[0], #PRG_PATH - 1)
    If n <= 0
      Continue
    EndIf
    gPrgEnt[n] = 0
    If gPrgEnt[0] = 46                                ; . and ..
      Continue
    EndIf
    If HwDirIsDir() <> 0
      If keepDirs <> 0
        If gPrgDirN < #PRG_DIRS And n < #PRG_NAME - 1
          prg_Put(@gPrgDir[gPrgDirN * #PRG_NAME], 0, #PRG_NAME, @gPrgEnt[0])
          gPrgDirN = gPrgDirN + 1
        Else
          gPrgDirsSkipped = gPrgDirsSkipped + 1
        EndIf
      EndIf
    ElseIf prg_EndsPmf(@gPrgEnt[0]) <> 0 And gPrgCandN < #PRG_CAND
      at = prg_Put(@gPrgCand[gPrgCandN * #PRG_PATH], 0, #PRG_PATH, *dir)
      If at >= 0
        at = prg_Put(@gPrgCand[gPrgCandN * #PRG_PATH], at, #PRG_PATH, @gPrgEnt[0])
      EndIf
      If at >= 0
        gPrgCandSize[gPrgCandN] = HwDirSize()
        gPrgCandN = gPrgCandN + 1
      EndIf
    EndIf
  ForEver
EndProcedure

; Builds the list: candidates first (a folder walk and a file read cannot share the one engine), then each proved.
Procedure.i prg_Scan()
  Define i.i, k.i, at.i, n.i, c.i
  Define Dim folder.a[#PRG_PATH]
  gPrgCount = 0 : gPrgCandN = 0 : gPrgDirN = 0 : gPrgDirsSkipped = 0
  If HwStorageUp() = 0
    ProcedureReturn 0
  EndIf
  prg_ScanDir("2:/", 1)
  For i = 0 To gPrgDirN - 1
    at = prg_Put(@folder[0], 0, #PRG_PATH, "2:/")
    at = prg_Put(@folder[0], at, #PRG_PATH, @gPrgDir[i * #PRG_NAME])
    If at >= 0
      at = prg_Put(@folder[0], at, #PRG_PATH, "/")
    EndIf
    If at >= 0
      prg_ScanDir(@folder[0], 0)
    EndIf
  Next
  prg_ScanDir("1:/", 0)
  For i = 0 To gPrgCandN - 1
    If gPrgCount >= #PRG_MAX
      Break
    EndIf
    If prg_IsContainer(@gPrgCand[i * #PRG_PATH]) = 0
      Continue
    EndIf
    prg_Put(@gPrgPath[gPrgCount * #PRG_PATH], 0, #PRG_PATH, @gPrgCand[i * #PRG_PATH])
    ; the name: the part after the last '/', without .pmf
    n = prg_Len(@gPrgCand[i * #PRG_PATH])
    k = n
    While k > 0 And PeekA(@gPrgCand[i * #PRG_PATH] + k - 1) <> 47
      k = k - 1
    Wend
    at = 0
    While k < n - 4 And at < #PRG_NAME - 1
      c = PeekA(@gPrgCand[i * #PRG_PATH] + k)
      gPrgName[gPrgCount * #PRG_NAME + at] = c
      at = at + 1 : k = k + 1
    Wend
    gPrgName[gPrgCount * #PRG_NAME + at] = 0
    gPrgSize[gPrgCount] = gPrgCandSize[i]
    gPrgCount = gPrgCount + 1
  Next
  gPrgListed = 1
  ProcedureReturn gPrgCount
EndProcedure

Procedure CmdPrograms()
  Define i.i, n.i
  If RequireCap(#CAP_STORAGE, "programs", "this board has no block storage medium Anvil can read") = 0
    ProcedureReturn
  EndIf
  prg_Scan()
  If gPrgCount = 0
    PrintN("No programs were found. A program is a payload container (.pmf) in the root")
    PrintN("of partition 2, in a folder of that root, or in the root of partition 1.")
    ProcedureReturn
  EndIf
  PrintN("Programs on the boot medium - type a name to run it:")
  For i = 0 To gPrgCount - 1
    Print("  ")
    UartWriteStr(@gPrgName[i * #PRG_NAME])
    n = prg_Len(@gPrgName[i * #PRG_NAME])
    While n < 18
      Print(" ") : n = n + 1
    Wend
    PrintDec(gPrgSize[i])
    Print(" bytes   ")
    UartWriteStr(@gPrgPath[i * #PRG_PATH])
    PrintNl()
  Next
  If gPrgCandN >= #PRG_CAND Or gPrgCount >= #PRG_MAX Or gPrgDirsSkipped > 0
    PrintN("  (the list is cut short: more files or folders than this listing holds)")
  EndIf
  PrintN("  Typing a name is the same as boot <its path>. A command of the same name wins.")
EndProcedure

; Called from the unknown-command arm with the typed word. 1 when the word named a program and it was run.
Procedure.i ProgramsTryRun()
  Define i.i, k.i, same.i, c.i
  If #CAP_STORAGE = 0
    ProcedureReturn 0
  EndIf
  If gWordLen < 1 Or gWordLen >= #PRG_NAME
    ProcedureReturn 0
  EndIf
  If gPrgListed = 0
    prg_Scan()                                      ; the first name typed this session builds the list quietly
  EndIf
  For i = 0 To gPrgCount - 1
    If prg_Len(@gPrgName[i * #PRG_NAME]) <> gWordLen
      Continue
    EndIf
    same = 1
    For k = 0 To gWordLen - 1
      c = gLine[gWordAt + k] & $FF
      If prg_Lower(c) <> prg_Lower(gPrgName[i * #PRG_NAME + k])
        same = 0
        Break
      EndIf
    Next
    If same <> 0
      Print("Running ")
      UartWriteStr(@gPrgPath[i * #PRG_PATH])
      PrintNl()
      PmfBootFile(@gPrgPath[i * #PRG_PATH])
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure
