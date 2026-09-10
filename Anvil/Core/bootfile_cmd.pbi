; ======================================================================
;  bootfile_cmd.pi4 - the CONSOLE SIDE of the bootloader.
;
;  Anvil/Core/pmfboot.pbi holds the container engine: parse a header,
;  judge it, place an image, prove its hash, enter it. This file is
;  everything the OPERATOR touches, and everything that happens on its
;  own at start-up:
;
;    * the four settings - boot.file, boot.delay, boot.fails,
;      boot.maxfails - and the arithmetic for reading numbers out of a
;      store that holds strings;
;    * BootFileWait(), the countdown a board runs before its prompt;
;    * the `boot` command and its sub-commands.
;
;  WHY IT IS A SEPARATE FILE. Because the engine has to be buildable
;  without a line editor and without a settings store, so that the gate
;  (RaspberryPi4/Examples/Diagnostics/pi4BootContainerSelfTest.pi4) can
;  stage containers in memory and run the real verify-place-enter path
;  under the A64 oracle. The line editor reaches for a USB keyboard, a
;  mouse tick and a Wi-Fi console; none of those has anything to do with
;  whether a hash is checked before a jump, and all of them would have to
;  be faked to find out. The same boundary hash_cmd.pi4 draws over
;  sha256.pi4.
;
;  INCLUDE ORDER: after Anvil/Core/pmfboot.pbi, after the settings store,
;  after Anvil/Core/parse.pbi, and after the board's storage bring-up
;  (HwStorageUp).
; ======================================================================

; ======================================================================
;  THE SETTINGS SIDE - PmfDecOf AND PmfPutDec MOVED TO settings.pi4.
;
;  They read a number out of a store that holds strings, and write one
;  back into it. That is the settings store's job and not this command
;  file's, and it stopped being arguable the moment a second feature
;  needed the same two procedures: leaving them here would have meant
;  either a second copy or an include order in which the screen depends
;  on the boot-file command. They are unchanged, and every caller in this
;  file still calls them by the same names.
; ======================================================================

Procedure.i PmfDelay()
  Define d.i
  d = PmfDecOf(SettingsGet(PmfKeyDelay()), #PMF_DELAY_DEFAULT)
  If d < 0
    d = 0
  EndIf
  If d > #PMF_DELAY_MAX
    d = #PMF_DELAY_MAX
  EndIf
  ProcedureReturn d
EndProcedure

Procedure.i PmfMaxFails()
  Define m.i
  m = PmfDecOf(SettingsGet(PmfKeyMaxFails()), #PMF_MAXFAILS_DEFAULT)
  If m < 1
    m = 1
  EndIf
  ProcedureReturn m
EndProcedure

Procedure.i PmfFails()
  ProcedureReturn PmfDecOf(SettingsGet(PmfKeyFails()), 0)
EndProcedure

; PmfSetFails(n) - write the counter and PUT IT ON THE MEDIUM.
;
; THE SAVE IS THE POINT, not an afterthought. A counter that lives only in
; the table in memory is gone the instant the payload hangs and the board
; is power-cycled, which is exactly and only the case it exists to catch.
; Returns 1 if it reached the medium.
Procedure.i PmfSetFails(n.i)
  PmfPutDec(n, @gNumBuf[0])
  If SettingsSet(PmfKeyFails(), @gNumBuf[0]) = 0
    ProcedureReturn 0
  EndIf
  If SettingsSave() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  BootFileWait() - THE AUTOMATIC BOOT, called once from Main().
;
;  ORDER OF PRECEDENCE, and it is deliberate. The board's Main() calls
;  BootWait() first - the DRAM autoboot record, `autoboot <addr>`, which
;  survives a reset but not a power cycle - and then this. So:
;
;    * `autoboot <addr>` WINS while it is armed. It is the more recent and
;      more deliberate act: somebody typed an address at this prompt in
;      this power cycle and asked for it to be taken on the next reset.
;    * `boot.file` is what happens on a COLD start, when the DRAM record
;      is whatever DRAM happened to hold and correctly fails its magic.
;
;  That is the right way round. The quick path is for the person sitting
;  at the board; the persisted path is for the board running on its own.
;
;  IT LOADS THE SETTINGS ITSELF, and on this board that means bringing the
;  boot medium up on every start. That is a real cost - a USB enumeration
;  before the prompt - and it is the price of a boot target that survives
;  a power cycle. There is no cheaper place to keep one: the DRAM record
;  does not survive power, and this board has no NVRAM of its own that
;  Anvil reaches.
;
;  NOTHING SET MEANS NO DELAY AT ALL. The same ruling BootWait makes, for
;  the same reason: a countdown whose only possible outcome is "carry on
;  to the prompt" costs two seconds on every start and teaches people to
;  ignore it, which is how a real countdown gets missed later.
; ======================================================================
Procedure BootFileWait()
  Define nm.i
  Define i.i
  Define c.i
  Define fails.i
  Define maxf.i
  Define secs.i
  Define hz.i
  Define t0.i
  Define quarter.i
  Define dots.i

  ; The gate first. A board with no storage has no persisted boot target
  ; and there is nothing here to do - silently, because this runs on every
  ; start and a refusal printed at every boot of a board that simply has
  ; no medium is noise, not honesty. `boot` typed at the prompt DOES
  ; refuse out loud, which is where the operator is actually asking.
  CompilerIf #CAP_STORAGE = 0
    ProcedureReturn
  CompilerEndIf

  ; THE SETTINGS ARE READ ONLY IF NOBODY HAS READ THEM YET, and that test
  ; is what keeps this procedure free on the board it matters most on. The
  ; Pi 4's BootBringUp() already enumerates USB, mounts the medium and
  ; calls SettingsLoad() before this runs, so re-reading here would be a
  ; second trip to the medium for a file already in memory, on every boot,
  ; for nothing. The Arduino UNO Q has no such bring-up, so it lands in
  ; the branch below and reads them itself.
  ;
  ; SettingsLoadState() answers 1 only after a load that completed. A
  ; part-read file answers 2 and is deliberately NOT treated as loaded:
  ; boot.file might be one of the lines that was never reached, and
  ; booting a target read out of half a file is exactly the confident
  ; wrong answer this whole command refuses.
  If SettingsLoadState() <> 1
    ; Reading the settings needs the medium. If it will not come up there
    ; is no boot target to read and the prompt follows - HwStorageUp has
    ; already said why, so nothing is added here.
    If HwStorageUp() = 0
      ProcedureReturn
    EndIf
    If SettingsLoad() = 0
      If SettingsLastError() <> #SET_ERR_NO_FILE
        PrintN("!! the settings could not be read, so any persisted boot target on this")
        PrintN("   medium was not acted on and the prompt follows as usual.")
        SettingsSayWhyNot()
        ScreenServiceTick()
      EndIf
      ProcedureReturn
    EndIf
  EndIf

  nm = SettingsGet(PmfKeyFile())
  If nm = 0
    ProcedureReturn                ; nothing armed, no delay, no noise
  EndIf

  ; COPIED OUT OF THE STORE IMMEDIATELY. SettingsGet hands back a pointer
  ; into the settings table, and PmfSetFails below calls SettingsSet,
  ; which rewrites that table - so the name would move, or be overwritten,
  ; between here and the load that uses it.
  i = 0
  While i < 30
    c = PeekA(nm + i)
    gPmfName[i] = c
    If c = 0
      Break
    EndIf
    i = i + 1
  Wend
  gPmfName[30] = 0

  ; --- THE REBOOT-LOOP GUARD, before anything is attempted -------------
  fails = PmfFails()
  maxf  = PmfMaxFails()
  If fails >= maxf
    PrintNl()
    Print("!! NOT booting ")
    UartWriteStr(@gPmfName[0])
    PrintN(" automatically, and this is the reboot-loop")
    Print("   guard rather than a fault with the file. It has been attempted ")
    PrintDec(fails)
    PrintNl()
    Print("   times in a row without anything ever confirming that the payload")
    PrintNl()
    Print("   reached a working state, and boot.maxfails is ")
    PrintDec(maxf)
    PrintN(".")
    PrintN("   A payload that hangs or resets gets re-entered on every start, and")
    PrintN("   there is then never a prompt long enough to type the fix at. This is")
    PrintN("   that prompt.")
    PrintN("   Type boot ok to clear the counter once the payload is known good, or")
    PrintN("   boot clear to stop booting this file at all. boot status shows all")
    PrintN("   four settings.")
    PrintNl()
    ScreenServiceTick()
    ProcedureReturn
  EndIf

  ; --- the countdown ---------------------------------------------------
  secs = PmfDelay()
  PrintNl()
  Print("Booting ")
  UartWriteStr(@gPmfName[0])
  Print(" in ")
  PrintDec(secs)
  If secs = 1
    PrintN(" second.")
  Else
    PrintN(" seconds.")
  EndIf
  If fails > 0
    Print("  (attempt ")
    PrintDec(fails + 1)
    Print(" of ")
    PrintDec(maxf)
    PrintN(" - nothing has confirmed a good boot yet)")
  EndIf
  Print("Press any key now to stop it and get a prompt instead ")
  ; Put the complete announcement on any attached display before entering
  ; the wait it describes. The target's service seam is a no-op when absent.
  ScreenServiceTick()

  If secs > 0
    hz = TickHz()
    If hz <= 0
      hz = 54000000
    EndIf
    t0 = Ticks()
    quarter = (hz * #BOOT_DOT) / 1000
    dots = 0
    While (Ticks() - t0) < (hz * secs)
      If UartReadReady() <> 0
        ; CONSUMED, deliberately - left in the FIFO it would become the
        ; first character of the first command. auto.pi4 does the same.
        c = UartRead()
        PrintNl()
        Print("Stopped by a keypress. ")
        UartWriteStr(@gPmfName[0])
        PrintN(" is still the boot target -")
        PrintN("type boot status to see it, or boot clear to stop booting it.")
        PrintN("The failure counter was NOT touched: nothing was attempted.")
        ScreenServiceTick()
        ProcedureReturn
      EndIf
      If (Ticks() - t0) > (quarter * (dots + 1))
        UartWrite(46)
        dots = dots + 1
        ScreenServiceTick()
      EndIf
    Wend
  EndIf
  PrintNl()

  ; --- THE COUNTER GOES TO THE MEDIUM BEFORE THE ATTEMPT ---------------
  ; This ordering IS the guard. Written after a successful boot it would
  ; never be written at all in the case it exists to detect, because that
  ; case is a payload that never comes back.
  If PmfSetFails(fails + 1) = 0
    PrintN("!! the boot-attempt counter could not be written to the medium, so the")
    PrintN("   reboot-loop guard cannot count this attempt and would never stop a")
    PrintN("   loop. NOTHING WAS BOOTED - going ahead would arm exactly the trap")
    PrintN("   the counter exists to prevent, on a board with no way out of it.")
    SettingsSayWhyNot()
    PrintN("   The prompt follows. boot <name> still works by hand, because you are")
    PrintN("   here to stop it.")
    ScreenServiceTick()
    ProcedureReturn
  EndIf
  Print("  attempt ")
  PrintDec(fails + 1)
  Print(" of ")
  PrintDec(maxf)
  PrintN(" recorded on the medium, so a payload that never comes")
  PrintN("  back cannot be retried for ever. Type boot ok once it is up.")

  ; PmfBootFile may transfer control permanently. Flush the final monitor
  ; state before it opens/validates/enters the payload, not after a return
  ; which a healthy payload is not required to make.
  ScreenServiceTick()
  PmfBootFile(@gPmfName[0])

  ; Reached when the boot was refused, or when the payload returned. Both
  ; are ordinary outcomes and both end at the prompt.
  PrintNl()
EndProcedure

; ======================================================================
;  boot - the command.
;
;    boot <name>        load, verify and enter that container now
;    boot mem <addr>    the same, for a container already in memory
;    boot ok            clear the failure counter - the payload is good
;    boot clear         stop booting a file at start-up
;    boot status        show the four settings and what they mean
;    boot               with nothing armed, the same as boot status
;
;  THERE IS NO SCRIPTING AND THERE IS NOT GOING TO BE. U-Boot's answer to
;  "load then run" is a command string in an environment variable, and
;  that needs a command separator, quoting, and a `run` verb that already
;  means something else in this monitor. `boot <name>` IS load-then-run,
;  as one built-in flow, because that is the only flow anybody wanted.
;  The inventory notes the name collision (S2.5) and this avoids it by not
;  creating the feature that would need it.
; ======================================================================

Procedure PmfPutStatus()
  Define v.i
  Define fails.i
  Define maxf.i

  PrintN("The persisted boot target, as this board would act on it at its next")
  PrintN("start:")
  v = SettingsGet(PmfKeyFile())
  Print("  boot.file      ")
  If v = 0
    PrintN("(not set)")
  Else
    UartWriteStr(v)
    PrintNl()
  EndIf
  Print("  boot.delay     ")
  PrintDec(PmfDelay())
  Print(" seconds")
  If SettingsGet(PmfKeyDelay()) = 0
    Print("   (not set, so the default of ")
    PrintDec(#PMF_DELAY_DEFAULT)
    PrintN(")")
  Else
    PrintNl()
  EndIf
  fails = PmfFails()
  maxf  = PmfMaxFails()
  Print("  boot.fails     ")
  PrintDec(fails)
  Print("   attempts since anything last confirmed a good boot")
  PrintNl()
  Print("  boot.maxfails  ")
  PrintDec(maxf)
  If SettingsGet(PmfKeyMaxFails()) = 0
    Print("   (not set, so the default of ")
    PrintDec(#PMF_MAXFAILS_DEFAULT)
    PrintN(")")
  Else
    PrintNl()
  EndIf

  If v = 0
    PrintN("Nothing is armed, so this board goes straight to its prompt when it")
    PrintN("starts and runs nothing by itself.")
    PrintN("  setenv boot.file APP.PMF")
    PrintN("  saveenv")
    PrintN("arms it. The name is a container - the .pmf file the compiler writes")
    PrintN("beside the flat image - and it carries its own load address, entry")
    PrintN("point and hash, so no address is ever typed.")
    ProcedureReturn
  EndIf

  If fails >= maxf
    PrintN("THE REBOOT-LOOP GUARD IS TRIPPED. This board will NOT boot that file")
    PrintN("automatically until the counter is cleared, because it has been tried")
    PrintN("that many times without anything confirming the payload came up.")
    PrintN("  boot ok      clears the counter")
    PrintN("  boot clear   stops booting this file at all")
  Else
    PrintN("At the next start this board will count that many seconds, printing")
    PrintN("dots, and any keystroke stops it and gives a prompt instead. If nothing")
    PrintN("stops it, the container is loaded, its hash is checked, and only then")
    PrintN("is it entered.")
  EndIf
  PrintN("A payload marks itself good by getting boot.fails back to zero: either")
  PrintN("the operator types boot ok, or the payload returns to this monitor and")
  PrintN("something here does. A payload that keeps the board can do it before it")
  PrintN("takes over, by writing the setting through this same store.")
EndProcedure

Procedure CmdBoot()
  Define nm.i
  Define a.i
  Define i.i
  Define c.i
  Define n.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  ; --- bare `boot`, and `boot status` ---------------------------------
  If gWordLen = 0 Or WordIs("status") <> 0
    If RequireCap(#CAP_STORAGE, "boot", "it has no storage medium Anvil can keep a boot target on") = 0
      ProcedureReturn
    EndIf
    ; The table in memory may be stale or empty on a board where nobody
    ; has typed `settings load` this session, and a status command that
    ; reported "(not set)" for a setting that is sitting in the file would
    ; be a confident wrong answer. So it reads the medium first.
    If HwStorageUp() <> 0
      If SettingsLoad() = 0
        If SettingsLastError() <> #SET_ERR_NO_FILE
          SettingsSayWhyNot()
        EndIf
      EndIf
    EndIf
    PmfPutStatus()
    ProcedureReturn
  EndIf

  ; --- boot ok --------------------------------------------------------
  If WordIs("ok") <> 0
    If RequireCap(#CAP_STORAGE, "boot", "it has no storage medium Anvil can keep a boot target on") = 0
      ProcedureReturn
    EndIf
    If HwStorageUp() = 0
      PrintN("!! the counter was not cleared, because no medium came up.")
      ProcedureReturn
    EndIf
    If SettingsLoad() = 0
      If SettingsLastError() <> #SET_ERR_NO_FILE
        PrintN("!! the counter was not cleared, because the settings could not be read")
        PrintN("   and a save would then rewrite the file from an incomplete table.")
        SettingsSayWhyNot()
        ProcedureReturn
      EndIf
    EndIf
    If PmfSetFails(0) = 0
      PrintN("!! the counter could not be written back to the medium, so it still")
      PrintN("   stands at whatever it was and this board may still stop autobooting.")
      SettingsSayWhyNot()
      ProcedureReturn
    EndIf
    PrintN("boot.fails is now 0. This board will boot its target automatically")
    PrintN("again at the next start, and the reboot-loop guard starts counting from")
    PrintN("nothing.")
    PrintN("  This is the acknowledgement that a payload came up. Say it when the")
    PrintN("  payload is actually working - saying it on every boot regardless")
    PrintN("  turns the guard off, which is a decision, not a habit worth falling")
    PrintN("  into.")
    ProcedureReturn
  EndIf

  ; --- boot clear -----------------------------------------------------
  If WordIs("clear") <> 0
    If RequireCap(#CAP_STORAGE, "boot", "it has no storage medium Anvil can keep a boot target on") = 0
      ProcedureReturn
    EndIf
    If HwStorageUp() = 0
      PrintN("!! nothing was changed, because no medium came up.")
      ProcedureReturn
    EndIf
    If SettingsLoad() = 0
      If SettingsLastError() <> #SET_ERR_NO_FILE
        PrintN("!! nothing was changed, because the settings could not be read and a")
        PrintN("   save would then rewrite the file from an incomplete table.")
        SettingsSayWhyNot()
        ProcedureReturn
      EndIf
    EndIf
    If SettingsRemove(PmfKeyFile()) = 0
      PrintN("There was no boot target set, so nothing was changed. This board")
      PrintN("already goes straight to its prompt when it starts.")
      ProcedureReturn
    EndIf
    If SettingsSave() = 0
      PrintN("!! boot.file was taken out of the table in memory but the file on the")
      PrintN("   medium was NOT rewritten, so this board will still boot that target")
      PrintN("   at its next start. Nothing has actually changed yet.")
      SettingsSayWhyNot()
      ProcedureReturn
    EndIf
    PrintN("The boot target is cleared. This board will go straight to its prompt")
    PrintN("when it starts and run nothing by itself.")
    PrintN("  boot.delay, boot.fails and boot.maxfails are left as they are; they")
    PrintN("  do nothing with no target set, and they are what you had chosen.")
    ProcedureReturn
  EndIf

  ; --- boot mem <addr> ------------------------------------------------
  If WordIs("mem") <> 0
    ; NO CAPABILITY GATE, and that is right rather than an oversight: this
    ; path never touches a medium. A container that arrived over `receive`
    ; or over the air is already in DRAM, and a board with no storage can
    ; boot one perfectly well.
    a = ParseHex()
    If gParseOk = 0
      If gParseOver <> 0
        PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
        PrintN("   a 64-bit address can have. Nothing was booted.")
        ProcedureReturn
      EndIf
      PrintN("!! boot mem needs the address of a container already in memory, in")
      PrintN("   hex, and none was given, so nothing was booted.")
      PrintN("   boot mem <address>")
      PrintN("   It reads the container header there, checks it, places the image at")
      PrintN("   the address the payload was built for, verifies its SHA-256, and")
      PrintN("   only then enters it. Use it for a container that arrived over")
      PrintN("   receive or over the air, with no medium involved at any point.")
      ProcedureReturn
    EndIf
    If gBad > 0 Or gFail <> 0
      PrintN("!! the last transfer did not arrive cleanly, so nothing was booted.")
      PrintN("   What is in memory is part of an image and part of whatever was")
      PrintN("   there before. The hash below would have caught it, and catching it")
      PrintN("   here says something more useful about why. Send it again.")
      ProcedureReturn
    EndIf
    ; THE ADDRESS CAME FROM THE OPERATOR, so the board is asked before
    ; the container header is read. The range asked about is the header
    ; alone - 96 bytes - because that is the first thing touched, and the
    ; image placement the header goes on to describe is checked by the
    ; loader's own window guards afterwards. Asking about a length the
    ; header has not been read yet to supply would be asking about a
    ; number nobody has.
    If AddrAllowed(a, a + 95, 0, "boot mem", "booted") = 0
      ProcedureReturn
    EndIf
    PmfBootAt(a)
    ProcedureReturn
  EndIf

  ; --- boot <name> ----------------------------------------------------
  If RequireCap(#CAP_STORAGE, "boot", "it has no storage medium Anvil can read a payload container from") = 0
    ProcedureReturn
  EndIf

  ; The name, copied out of the line editor's buffer. gLine is overwritten
  ; by the next ReadLine and the load below prints, so it is copied rather
  ; than pointed at - the same reason CmdSave copies into gName.
  n = gWordLen
  If n > 30
    n = 30
  EndIf
  i = 0
  While i < n
    gPmfName[i] = gLine[gWordAt + i]
    i = i + 1
  Wend
  gPmfName[n] = 0

  PmfBootFile(@gPmfName[0])
EndProcedure
