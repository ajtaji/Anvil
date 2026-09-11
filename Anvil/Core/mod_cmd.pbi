; ======================================================================
;  `mod` - THE CONSOLE OVER THE DRIVER-MODULE LOADER
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Core/mod_registry.pbi, mod_container.pbi, mod_arena.pbi,
;    Anvil/Core/mod_lifecycle.pbi, Anvil/Core/mod_manifest.pbi
;    Anvil/Core/parse.pbi, argfmt.pbi, format.pbi
;
;  NO SINGLE-LETTER ALIAS. `m` is memory and `d` is deadman; a monitor
;  that guesses which of three commands a letter meant is not a monitor
;  anyone should trust, and the design note said so before this file
;  existed.
;
;  THIS FILE HOLDS NO POLICY. Every refusal it prints was composed by the
;  layer that refused - ModSayRefusal() in mod_lifecycle.pbi - and every
;  decision it reports was made below it. What is here is argument
;  parsing and the layout of a table, which is the whole job of a console
;  file in this tree.
;
;  NO SENTENCE HERE NAMES A PIECE OF HARDWARE. The shared-core finding
;  (forum 575) is that one board's facts written as literal prose in a
;  shared file is how that file comes to lie on the second board. `mod`
;  prints the module's FILE name, the seam's PORTABLE name, and asks the
;  BOARD to name its own devices through HwDevSay().
; ======================================================================

Procedure.i ModArgIs(a.i, name.i)
  If a = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn ModTokenIs(a, StrLenZ(a), name)
EndProcedure

; A record by the file name the operator typed, or -1. The policy - the
; live record of that name before a stranded one - is the lifecycle's,
; in ModRecFindByName, where the states it reads are defined and where
; the module pipeline gate can reach it.
Procedure.i ModFindByName(a.i)
  ProcedureReturn ModRecFindByName(a)
EndProcedure

Procedure ModPutDigest(rec.i)
  Define i.i
  i = 0
  While i < #PMFMOD_DIGEST_BYTES
    PutHexLower2(gModRecDigest[rec * #PMFMOD_DIGEST_BYTES + i] & 255)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  `mod` / `mod list` - one line per record.
;
;  THE STATE COLUMN IS THE POINT OF THE TABLE. READY means the bytes are
;  good and nothing has looked at hardware; ACTIVE means a driver is
;  answering; FAILED means it was refused and every service it had
;  published was withdrawn; STRANDED means it was unloaded and its arena
;  is not reusable until a reset. Those are four different things and a
;  loader that printed "loaded" for all of them would be useless exactly
;  when it was needed.
; ----------------------------------------------------------------------
Procedure ModCmdList()
  Define i.i
  Define s.i
  Define sid.i
  If gModArenaReady = 0
    If HwModArenaBase() = 0
      PrintN("this board declares no module arena, so no driver module can be")
      PrintN("  loaded on it yet. Everything else of the loader is here and")
      PrintN("  answering; what is missing is a range of memory this board can")
      PrintN("  prove belongs to nothing else. [mod 30]")
      ProcedureReturn
    EndIf
    PrintN("!! the module arena was never brought up, so nothing can be loaded.")
    PrintN("   `map` shows the ranges this board reserves; the refusal printed at")
    PrintN("   boot says which one the arena collided with. [mod 26]")
    ProcedureReturn
  EndIf
  If gModRecordCount = 0
    Print("no modules are loaded. The arena is ")
    PrintDec(gModArenaBytes / 1024)
    PrintN(" KiB, all of it free.")
    PrintN("  a module is loaded by a line in MODULES.TXT in the root of the boot")
    PrintN("  medium, or by `mod load <file>`. `mod devices` lists what is here to")
    PrintN("  drive and `mod seams` lists what is published.")
    ProcedureReturn
  EndIf
  PrintN("  #  file          base      size    state     seams filled");
  i = 0
  While i < gModRecordCount
    Print("  ")
    PrintDec(i)
    Print("  ")
    PutPadded(ModRecNameAddr(i), 14)
    Print("$")
    PutHex8(gModRecBase[i])
    Print("  ")
    PrintDec(gModRecBytes[i] / 1024)
    Print("K    ")
    ModSayState(i)
    Print("    ")
    s = 0
    sid = 0
    While sid <= #MOD_SEAM_MAX
      If ModSeamOwner(sid) = i
        If s > 0
          Print(",")
        EndIf
        ModSaySeam(sid)
        s = s + 1
      EndIf
      sid = sid + 1
    Wend
    If s = 0
      Print("-")
    EndIf
    PrintNl()
    i = i + 1
  Wend
  Print("  arena $")
  PutHex8(gModArenaBase)
  Print("..$")
  PutHex8(gModArenaEnd - 1)
  Print(", ")
  PrintDec((gModArenaEnd - gModArenaNext) / 1024)
  PrintN(" KiB free. Unloaded modules stay put until a reset.")
EndProcedure

; ----------------------------------------------------------------------
;  `mod info <file>` - everything the header claimed and everything that
;  happened to it since.
; ----------------------------------------------------------------------
Procedure ModCmdInfo(a.i)
  Define rec.i
  Define i.i
  Define sid.i
  rec = ModFindByName(a)
  If rec < 0
    Print("!! no module called ")
    UartWriteStr(a)
    PrintN(" has been loaded in this power cycle.")
    PrintN("   `mod` lists what has. Nothing was done. [mod 24]")
    ProcedureReturn
  EndIf
  Print("  file      ")
  ModSayName(rec)
  PrintNl()
  Print("  state     ")
  ModSayState(rec)
  PrintNl()
  Print("  built for ABI ")
  PrintDec(gModRecAbiMajor[rec])
  Print(".")
  PrintDec(gModRecAbiMinor[rec])
  Print(", this Anvil publishes ")
  PrintDec(#SVC_ABI_MAJOR)
  Print(".")
  PrintDec(#SVC_ABI_MINOR)
  PrintNl()
  Print("  placed at $")
  PutHex8(gModRecBase[rec])
  Print(", image ")
  PrintDec(gModRecImageBytes[rec])
  Print(" bytes, BSS ")
  PrintDec(gModRecBssBytes[rec])
  Print(" at +$")
  PutHex8(gModRecBssOffset[rec])
  PrintNl()
  Print("  entries   init +$")
  PutHex8(gModRecInit[rec] - gModRecBase[rec])
  If gModRecProbe[rec] <> 0
    Print("  probe +$")
    PutHex8(gModRecProbe[rec] - gModRecBase[rec])
  EndIf
  If gModRecQuiesce[rec] <> 0
    Print("  quiesce +$")
    PutHex8(gModRecQuiesce[rec] - gModRecBase[rec])
  EndIf
  PrintNl()
  Print("  sha256    ")
  ModPutDigest(rec)
  PrintNl()
  Print("  declares  ")
  i = 0
  While i < gModRecSeamCount[rec]
    If i > 0
      Print(", ")
    EndIf
    ModSaySeam(gModRecSeams[rec * #PMFMOD_SEAM_MAX + i])
    If gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] = 0
      Print(" (narrowed out by MODULES.TXT)")
    EndIf
    i = i + 1
  Wend
  PrintNl()
  Print("  fills     ")
  i = 0
  sid = 0
  While sid <= #MOD_SEAM_MAX
    If ModSeamOwner(sid) = rec
      If i > 0
        Print(", ")
      EndIf
      ModSaySeam(sid)
      Print(" (")
      PrintDec(ModSeamFilledCount(sid))
      Print(" function(s), ")
      PrintDec(ModSeamBindCount(sid))
      Print(" binding(s))")
      i = i + 1
    EndIf
    sid = sid + 1
  Wend
  If i = 0
    Print("nothing")
  EndIf
  PrintNl()
  Print("  matches   ")
  i = 0
  While i < gModRecMatchCount[rec]
    If i > 0
      Print(", ")
    EndIf
    UartWriteStr(ModRecordMatchAddr(rec, i))
    If i = gModRecMatched[rec]
      Print(" <- bound")
    EndIf
    i = i + 1
  Wend
  PrintNl()
  Print("  device    ")
  If gModRecDevice[rec] < 0
    Print("none matched")
  Else
    HwDevSay(gModRecDevice[rec])
    Print(", handle $")
    PutHex8(gModRecToken[rec])
  EndIf
  PrintNl()
  Print("  init ran  ")
  PrintDec(gModRecInitCalls[rec])
  Print(" time(s), last answered ")
  PrintDec(gModRecInitResult[rec])
  PrintNl()
  Print("  relocations applied: ")
  PrintDec(gModRelocCount)
  PrintN(" for the last container parsed")
EndProcedure

; ----------------------------------------------------------------------
;  `mod devices` - what this board is willing to hand to a driver.
;
;  IT IS THE OTHER HALF OF `mod info`'s match list, and printing the two
;  the same way is deliberate: the whole of device matching is a string
;  in a container meeting a string in this table, and an operator holding
;  a module that will not bind should be able to see both lists and spot
;  the difference without a tool.
; ----------------------------------------------------------------------
Procedure ModCmdDevices()
  Define i.i
  Define n.i
  n = HwDevCount()
  If n = 0
    PrintN("this board declares no devices a driver module could bind to.")
    ProcedureReturn
  EndIf
  PrintN("  #  compatible id             seam      handle     what it is")
  i = 0
  While i < n
    Print("  ")
    PrintDec(i)
    Print("  ")
    PutPadded(HwDevIdAddr(i), 25)
    ModSaySeam(HwDevSeam(i))
    Print("       $")
    PutHex8(HwDevToken(i))
    Print("  ")
    HwDevSay(i)
    PrintNl()
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  `mod seams` - the published vocabulary and who answers each entry.
;
;  THREE STATES AND THEY HAVE THREE DIFFERENT FIRST THINGS TO CHECK, which
;  is the whole reason the capability model kept a compile-time answer
;  beside a run-time one:
;
;    no hardware here          nothing to do; this board has none
;    the core reaches it       no module is needed
;    here, nothing fills it    load a module - this is the state a
;                              refusal has to be able to name
; ----------------------------------------------------------------------
Procedure ModCmdSeams()
  Define sid.i
  PrintN("  seam      source                              bindings")
  sid = 0
  While sid <= #MOD_SEAM_MAX
    If HwSeamPossible(sid) <> 0 Or ModSeamHas(sid) <> 0 Or HwSeamCore(sid) <> 0
      Print("  ")
      ModSaySeam(sid)
      Print("        ")
      If ModSeamHas(sid) <> 0
        Print("a loaded module (")
        ModSayName(ModSeamOwner(sid))
        Print(")")
        If ModSeamClosed(sid) <> 0
          Print(", closed to new use until it is unloaded")
        EndIf
      ElseIf HwSeamCore(sid) <> 0
        Print("the core, with no module")
      Else
        Print("the hardware is here and nothing fills it")
      EndIf
      Print("   ")
      PrintDec(ModSeamBindCount(sid))
      PrintNl()
    EndIf
    sid = sid + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  `mod load <file> [seam]` - one module, now.
;
;  The optional seam NARROWS it to a subset of what its header declares,
;  exactly as a manifest line does, and can never widen one.
; ----------------------------------------------------------------------
Procedure ModCmdLoad(a.i)
  Define b.i
  Define sid.i
  Define rc.i
  sid = -1
  b = ArgWord()
  If b <> 0
    sid = ModSeamIdOfName(b, StrLenZ(b))
    If sid < 0
      Print("!! `")
      UartWriteStr(b)
      PrintN("` is not a seam this Anvil publishes. Nothing was loaded.")
      PrintN("   `mod seams` lists the names. [mod 27]")
      ProcedureReturn
    EndIf
  EndIf
  rc = ModLoadAndActivate(a, sid)
  If rc <> #MOD_OK
    ModSayRefusal()
    ProcedureReturn
  EndIf
  Print("loaded ")
  ModSayName(gModLastRecord)
  Print(" at $")
  PutHex8(gModRecBase[gModLastRecord])
  Print(", bound to ")
  HwDevSay(gModRecDevice[gModLastRecord])
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  `mod unload <file>` - refused while anything holds it.
; ----------------------------------------------------------------------
Procedure ModCmdUnload(a.i)
  Define rec.i
  Define rc.i
  rec = ModFindByName(a)
  If rec < 0
    Print("!! no module called ")
    UartWriteStr(a)
    PrintN(" has been loaded in this power cycle.")
    PrintN("   `mod` lists what has. Nothing was done. [mod 24]")
    ProcedureReturn
  EndIf
  rc = ModUnload(rec)
  If rc <> #MOD_OK
    ModSayRefusal()
    ProcedureReturn
  EndIf
  Print("unloaded ")
  ModSayName(rec)
  Print(". Its ")
  PrintDec(gModRecBytes[rec] / 1024)
  PrintN(" KiB of arena stay reserved until a reset -")
  PrintN("  the allocator has no free list, and handing that memory to a later")
  PrintN("  module would put it where a stale pointer still names.")
EndProcedure

; ----------------------------------------------------------------------
;  `mod detach <seam>` - ask every consumer holding a seam to let go.
;
;  IT IS NOT AN UNLOAD AND DOES NOT PRETEND TO BE. It asks each binding's
;  owner to release the service and go back to whatever it used before;
;  the module stays loaded and working. What it buys is that the unload
;  which was refused a moment ago can now be reissued honestly, rather
;  than the operator being offered a "force" that strands live callers.
; ----------------------------------------------------------------------
Procedure ModCmdDetach(a.i)
  Define sid.i
  Define left.i
  Define before.i
  sid = ModSeamIdOfName(a, StrLenZ(a))
  If sid < 0
    Print("!! `")
    UartWriteStr(a)
    PrintN("` is not a seam this Anvil publishes. Nothing was done.")
    PrintN("   `mod seams` lists the names. [mod 27]")
    ProcedureReturn
  EndIf
  before = ModSeamBindCount(sid)
  If before = 0
    Print("nothing is bound to the ")
    ModSaySeam(sid)
    PrintN(" seam; there was nothing to release.")
    ; Close it anyway when a module fills it, for the consumer that has
    ; not read yet: without this the first read after the operator's
    ; detach binds, and the unload is refused by a consumer that was
    ; never asked. See gSeamClosed in Anvil/Core/mod_registry.pbi.
    If ModSeamHas(sid) <> 0
      ModSeamDetachAll(sid)
      PrintN("  The seam is closed to new use until its module is unloaded, so")
      PrintN("  nothing can bind between now and `mod unload`.")
    EndIf
    ProcedureReturn
  EndIf
  left = ModSeamDetachAll(sid)
  If left > 0
    Print("!! ")
    PrintDec(left)
    Print(" of ")
    PrintDec(before)
    Print(" binding(s) on the ")
    ModSaySeam(sid)
    PrintN(" seam did not release.")
    PrintN("   That is a defect in the consumer holding it, not in the module.")
    PrintN("   The unload stays refused, which is the safe half. [mod 23]")
    ProcedureReturn
  EndIf
  PrintDec(before)
  Print(" binding(s) on the ")
  ModSaySeam(sid)
  PrintN(" seam released.")
  PrintN("  Everything that used it has fallen back to whatever it used before")
  PrintN("  the module was loaded, and the seam is closed to new use until its")
  PrintN("  module is unloaded, so nothing can bind again in the meantime.")
  PrintN("  `mod unload` can act now.")
EndProcedure

Procedure ModCmdHelp()
  PrintN("mod [list]              what is loaded, where, and in what state")
  PrintN("mod info <file>         the header, the digest, the seams, the device")
  PrintN("mod devices             what this board offers a driver to bind to")
  PrintN("mod seams               the published seams and who answers each")
  PrintN("mod load <file> [seam]  read, verify, place and activate one module")
  PrintN("mod unload <file>       refused while a consumer still holds a seam")
  PrintN("mod detach <seam>       ask those consumers to let go first")
  PrintN("  MODULES.TXT in the root of the boot medium loads modules at boot,")
  PrintN("  one file name per line, with an optional seam name to narrow it.")
EndProcedure

Procedure CmdMod()
  Define a.i
  a = ArgWord()
  If a = 0 Or ModArgIs(a, "list") <> 0
    ModCmdList()
    ProcedureReturn
  EndIf
  If ModArgIs(a, "help")
    ModCmdHelp()
    ProcedureReturn
  EndIf
  If ModArgIs(a, "devices")
    ModCmdDevices()
    ProcedureReturn
  EndIf
  If ModArgIs(a, "seams")
    ModCmdSeams()
    ProcedureReturn
  EndIf
  If ModArgIs(a, "info")
    a = ArgWord()
    If a = 0
      PrintN("mod info <file> - which module? `mod` lists them.")
      ProcedureReturn
    EndIf
    ModCmdInfo(a)
    ProcedureReturn
  EndIf
  If ModArgIs(a, "load")
    a = ArgWord()
    If a = 0
      PrintN("mod load <file> [seam] - which file? It is a name in the root of the")
      PrintN("  boot medium, like THERMAL.MOD.")
      ProcedureReturn
    EndIf
    ModCmdLoad(a)
    ProcedureReturn
  EndIf
  If ModArgIs(a, "unload")
    a = ArgWord()
    If a = 0
      PrintN("mod unload <file> - which module? `mod` lists them.")
      ProcedureReturn
    EndIf
    ModCmdUnload(a)
    ProcedureReturn
  EndIf
  If ModArgIs(a, "detach")
    a = ArgWord()
    If a = 0
      PrintN("mod detach <seam> - which seam? `mod seams` lists them.")
      ProcedureReturn
    EndIf
    ModCmdDetach(a)
    ProcedureReturn
  EndIf
  Print("!! `mod ")
  UartWriteStr(a)
  PrintN("` is not one of this command's words. Nothing was done.")
  ModCmdHelp()
EndProcedure
