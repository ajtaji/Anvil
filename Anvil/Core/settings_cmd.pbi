
; ----------------------------------------------------------------------
;  Why the last call into settings.pi4 refused. One place, so no caller
;  has to remember that #SET_ERR_FAT has a second line to it.
; ----------------------------------------------------------------------
Procedure SettingsSayWhyNot()
  Print("!! ")
  ; UartWriteStr, NOT PrintN. SettingsErrorText returns an .i POINTER -
  ; see the note on SdErrorText, and trap 1 at the top of this section.
  UartWriteStr(SettingsErrorText())
  PrintNl()
  If SettingsLastError() = #SET_ERR_FAT
    ; The medium's own words, through the storage seam. settings.pi4
    ; deliberately does not restate them; it says "the next line says
    ; what it found". On the Pi 4 this is still fat.pi4's sentence, but
    ; it is handed back by Anvil/Storage/hwfile.pbi rather than
    ; fetched from fat.pi4 here, so this file names no filesystem and
    ; reads correctly on a board that has none of ours.
    Print("   ")
    UartWriteStr(HwFileErrorText())   ; a POINTER
    PrintNl()
  EndIf
  If SettingsErrorLine() > 0
    Print("   The trouble is on line ")
    PrintDec(SettingsErrorLine())
    PrintN(" of SETTINGS.TXT, counting from 1.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  THE PLAIN-TEXT SENTENCE. Printed EVERY time a secret is set, never
;  once per session and never only in the help.
;
;  settings.pi4's header spends two pages on this and its conclusion is
;  that the warning has to be attached to the moment of the decision.
;  The key name carries it into the file ("wifi.password.plaintext"),
;  every save rewrites a banner comment at the top of SETTINGS.TXT that
;  carries it to whoever opens the file - and this is the third place,
;  the one that reaches the person actually choosing.
;
;  THE ADVICE AT THE END IS THE PART THAT IS WORTH ANYTHING. No on-board
;  scheme defends against somebody holding the stick. A guest network
;  does, it is free, and it is the only real mitigation there is.
; ----------------------------------------------------------------------
Procedure SettingsSayPlainText()
  PrintN("   THIS IS STORED IN PLAIN TEXT. It goes into SETTINGS.TXT on the boot")
  PrintN("   medium as ordinary readable characters. Anybody who plugs that stick")
  PrintN("   into any computer can read it. It is not encrypted, it is not")
  PrintN("   scrambled, and it is not hidden anywhere but on this screen.")
  PrintN("   That is a decision, not an oversight. The radio needs the passphrase")
  PrintN("   itself: WPA2 derives its key with PBKDF2-HMAC-SHA1, there is no SHA-1")
  PrintN("   implementation anywhere in this project, and the CYW43 firmware runs")
  PrintN("   that derivation from the plain passphrase in any case - so a stored")
  PrintN("   form we could not compute would feed an interface that will not take")
  PrintN("   it. Obscuring it with a key that is in the image on the same stick")
  PrintN("   would be theatre and was refused by name.")
  PrintN("   Give this board a guest network or an IoT VLAN rather than the")
  PrintN("   household one. That costs nothing and it is worth more than anything")
  PrintN("   this monitor could do to the file.")
EndProcedure

; ----------------------------------------------------------------------
;  The table, as the operator sees it. Secrets masked.
; ----------------------------------------------------------------------
Procedure SettingsShowTable()
  Define i.i
  Define c.i
  Define k.i
  Define v.i

  c = SettingsCount()
  Print("Settings held in memory: ")
  PrintDec(c)
  Print(" of ")
  PrintDec(#SET_MAX_KEYS)
  PrintN(".")

  i = 0
  While i < c
    ; One check per row. Thirty-two rows is not a long print, but the
    ; rule in STOPPING A LONG PRINT is that every output loop has one.
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    k = SettingsKeyAt(i)
    v = SettingsValueAt(i)
    Print("  ")
    PutPadded(k, 26)
    Print("  ")
    If SettingsIsSecret(k) <> 0
      ; The mask is a FIXED eight asterisks and the true length is
      ; printed as a number beside it (settings.pi4:1201-1206). Eight
      ; stars for a twenty-character password is on purpose - the stars
      ; must not leak the length - and the number is there anyway
      ; because "did it take all twenty characters" is a real question
      ; and this is the operator's own console.
      UartWriteStr(SettingsMaskText())
      Print("   (")
      PrintDec(StrLenZ(v))
      PrintN(" characters, hidden)")
    Else
      UartWriteStr(v)
      PrintNl()
    EndIf
    i = i + 1
  Wend

  If c > 0
    PrintN("Anything whose name contains password, passphrase or secret is hidden")
    PrintN("here, because this output also goes to the HDMI console and into the")
    PrintN("next screenshot. settings reveal <name> prints one in full.")
  EndIf

  ; WHERE data:/ PATHS GO, said whether or not the key exists, because an
  ; absent data.path is a meaningful answer (partition 1's root) and not an
  ; empty table row. See Anvil/Core/datapath.pbi.
  If SettingsHas("data.path") <> 0
    Print("data:/ paths resolve under ")
    UartWriteStr(SettingsGet("data.path"))
    PrintN(" (the data.path setting).")
  Else
    PrintN("data.path is not set, so data:/ paths mean the root of partition 1.")
    PrintN("  On a medium with a data partition: settings set data.path 2:/")
  EndIf

  Select SettingsLoadState()
    Case 0
      PrintN("Nothing has been read off the boot medium in this session.")
      PrintN("  Type settings load to read SETTINGS.TXT. Bringing the medium up")
      PrintN("  is slow and noisy, which is why it is not done for you.")
    Case 2
      PrintN("!! the last load stopped at a bad line, so this is only the part of")
      PrintN("   SETTINGS.TXT above it. Saving is REFUSED until you type settings")
      PrintN("   discard, because a save would delete every line it never read.")
  EndSelect

  If SettingsDirty() <> 0
    PrintN("There are changes here that are not in the file. Type settings save.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  settings load - read SETTINGS.TXT. READ ONLY: no writer is armed
;  anywhere on this path and none is needed.
;
;  IT NO LONGER BRINGS THE MEDIUM UP ITSELF. This used to open with
;  StorageUp(), which is a Pi 4 procedure that enumerates USB and mounts
;  a FAT volume - in a core file that also compiles for a board with
;  neither. Bringing a medium up is now the storage backend's job, done
;  inside HwFileOpen on the board that needs it and skipped entirely on
;  the board whose firmware already has the volume open. The "no medium"
;  case has not gone quiet: it comes back as #HW_FILE_NOMEDIUM and lands
;  in SettingsSayWhyNot below with the backend's own sentence.
; ----------------------------------------------------------------------
Procedure CmdSettingsLoad()
  If SettingsLoad() = 0
    If SettingsLastError() = #SET_ERR_NO_FILE
      PrintN("There is no SETTINGS.TXT on this medium yet. That is normal until the")
      PrintN("first save and it is not a fault.")
      PrintN("  The table in memory has been EMPTIED even so, so it cannot sit there")
      PrintN("  showing you another medium's settings. Set what you want and type")
      PrintN("  settings save to create the file.")
      ProcedureReturn
    EndIf
    SettingsSayWhyNot()
    If SettingsLoadState() = 2
      PrintN("   Everything BEFORE that line did load and settings will show it.")
      PrintN("   Saving is refused until you type settings discard.")
      PrintN("   The file itself has not been changed and will not be.")
    EndIf
    ProcedureReturn
  EndIf

  Print("Read ")
  PrintDec(SettingsCount())
  PrintN(" settings from SETTINGS.TXT on the boot medium.")
  If SettingsDuplicates() > 0
    Print("  ")
    PrintDec(SettingsDuplicates())
    PrintN(" names appeared more than once in the file. The last one of each won,")
    PrintN("  and a save from here will write each of them only once.")
  EndIf
  SettingsShowTable()
EndProcedure

; ----------------------------------------------------------------------
;  settings save - THE ONE COMMAND HERE THAT CAN TOUCH THE MEDIUM.
;
;  THE BLOCK WRITER IS ARMED AROUND EXACTLY ONE CALL AND DISARMED ON
;  EVERY PATH OUT OF THIS PROCEDURE. That is CmdSave's pattern
;  (anvil.pi4's save command, and settings.pi4:305-314 names it as the
;  expected one) and the reason is stated there: leaving it set all the
;  time would mean any later bug anywhere in this monitor could reach
;  the boot medium. There are three exits below and all three disarm.
;
;  WHAT THIS CAN AND CANNOT DAMAGE, from settings.pi4's SAFETY section
;  and worth restating where the arming actually happens:
;    * it cannot reach a raw sector. Every write goes through fat.pi4's
;      fat_WriteRaw, which refuses any LBA outside the FSInfo sector,
;      the FAT and the data region (fat.pi4:1612-1642).
;    * it cannot touch ANVIL.IMG or any other file. The only name
;      settings.pi4 ever passes to fat.pi4 is SETTINGS.TXT, from one
;      place, and no call takes a name from here.
;    * it CAN destroy SETTINGS.TXT, and it rewrites the whole of it.
;      Hand-written comments in that file are lost. Said out loud below
;      every time, because settings.pi4's header asks the monitor to.
; ----------------------------------------------------------------------
Procedure CmdSettingsSave()
  ; REFUSED BEFORE THE MEDIUM IS EVEN BROUGHT UP. SettingsSave would
  ; refuse this too (#SET_ERR_UNSAFE_SAVE), but making the operator wait
  ; through a USB enumeration to be told no is rude, and the writer is
  ; never armed on this path at all.
  If SettingsLoadState() = 2
    PrintN("!! refusing to save. The last load stopped at a bad line, so the table")
    PrintN("   in memory holds only the part of SETTINGS.TXT above it, and a save")
    PrintN("   rewrites the whole file from the table - it would delete every line")
    PrintN("   after the bad one, silently and permanently.")
    PrintN("   Fix the file by hand on a PC, or type settings discard to accept")
    PrintN("   losing the unread rest, and then save again.")
    PrintN("   Nothing was written. The block writer was never armed.")
    ProcedureReturn
  EndIf

  If SettingsCount() = 0
    ; Not refused - an empty file is a legitimate thing to want, and
    ; "remove the last setting then save" has to work. Just said.
    PrintN("Note: there are no settings in memory, so this writes an empty file.")
  EndIf

  ; THE MEDIUM AND THE WRITER ARE THE BACKEND'S BUSINESS NOW. This
  ; procedure used to call StorageUp() itself, test gMedium against 1 for
  ; the USB-only write rule, and bracket the save with
  ; FatSetRangeWriter(@MscWriteBlocks) ... FatSetRangeWriter(0) on all
  ; three paths out. Every one of those is a Pi 4 fact, and this is a core
  ; file that also compiles for a board with no blocks and no FAT.
  ;
  ; The guarantees did not weaken; they moved down one layer, into
  ; HwFileWriteAll, which is now the single place on this board that arms
  ; the writer and disarms it on every exit. What is left here is the
  ; question a command should be asking: may I write at all? - and the
  ; refusal in this monitor's own words when the answer is no.
  If HwFileWritable() = 0
    PrintN("!! nothing was written, because this board cannot write to its boot")
    PrintN("   medium right now. The settings in memory are unchanged and still")
    PrintN("   there; nothing was opened, created or truncated, and no writer was")
    PrintN("   ever armed.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())   ; a POINTER
    PrintNl()
    ProcedureReturn
  EndIf

  Print("Writing SETTINGS.TXT ...")
  PrintNl()
  UartDrain()

  If SettingsSave() = 0
    SettingsSayWhyNot()
    PrintN("   Either nothing was written at all, or SETTINGS.TXT is now part old")
    PrintN("   and part new - the line above says which. No other file on the")
    PrintN("   medium can have been touched: SETTINGS.TXT is the only name this")
    PrintN("   library ever gives to the medium.")
    PrintN("   The writer has been disarmed on the way out of the failure.")
    ProcedureReturn
  EndIf

  Print("Saved ")
  PrintDec(SettingsCount())
  PrintN(" settings to SETTINGS.TXT on the boot medium.")
  PrintN("  The whole file was rewritten from the table, so any comments you had")
  PrintN("  typed into it by hand are gone. The banner at the top is rewritten")
  PrintN("  every save and explains the file to whoever opens it next.")
  PrintN("  The writer has been disarmed again, so nothing else in this monitor")
  PrintN("  can reach the medium until the next save.")
EndProcedure

Procedure CmdSettingsDiscard()
  If SettingsLoadState() <> 2
    PrintN("There is nothing to discard, and nothing was changed.")
    PrintN("  This command exists for one situation only: a load that stopped at a")
    PrintN("  bad line, where the table holds part of the file and saving would")
    PrintN("  delete the rest. The last load did not do that.")
    ProcedureReturn
  EndIf
  SettingsDiscardLoad()
  PrintN("Accepted. The part of SETTINGS.TXT after the bad line is being thrown")
  PrintN("away, and settings save will now write the table as it stands.")
  PrintN("  Nothing has been written to the medium yet, so the file on the stick")
  PrintN("  is still complete. Type settings to see what would be written, and")
  PrintN("  settings load to read the file again if you have fixed it instead.")
EndProcedure

; ----------------------------------------------------------------------
;  settings - the whole family.
; ----------------------------------------------------------------------
Procedure CmdSettings()
  Define k.i
  Define v.i
  Define n.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  ; Bare `settings` is `settings show`. WordIs returns 0 for a
  ; zero-length word, so the two tests cannot both be needed and both
  ; are harmless.
  If gWordLen = 0 Or WordIs("show") <> 0
    SettingsShowTable()
    ProcedureReturn
  EndIf

  If WordIs("set") <> 0
    k = ArgWord()
    If k = 0
      PrintN("!! settings set needs the name of the setting to change, and none was")
      PrintN("   given, so nothing was changed.")
      PrintN("   settings set <name> <value>")
      PrintN("   The name is one word - letters, digits, a dot, a dash or an")
      PrintN("   underscore, up to thirty-one characters, and case does not matter.")
      PrintN("   The value is the WHOLE REST OF THE LINE, so it may contain spaces.")
      ProcedureReturn
    EndIf
    v = ArgRest()
    If v = 0
      Print("!! a value is required. Nothing was changed and ")
      UartWriteStr(k)
      PrintN(" is as it was.")
      PrintN("   settings set <name> <value>, where the value is the rest of the line.")
      PrintN("   To take a setting away entirely, type settings remove <name>.")
      ProcedureReturn
    EndIf
    If SettingsSet(k, v) = 0
      SettingsSayWhyNot()
      PrintN("   Nothing was changed.")
      ProcedureReturn
    EndIf
    Print("Set ")
    UartWriteStr(k)
    Print(" to ")
    ; The value is echoed back even for a secret, because the operator
    ; typed it a second ago and it is already on this screen. What must
    ; not happen is a secret appearing in the output of a command that
    ; did not involve typing it, which is what `settings show` masks.
    UartWriteStr(v)
    Print("   (")
    PrintDec(StrLenZ(v))
    PrintN(" characters)")
    If SettingsIsSecret(k) <> 0
      SettingsSayPlainText()
    EndIf
    PrintN("  This is in memory only. Type settings save to write it to the medium.")
    ProcedureReturn
  EndIf

  If WordIs("remove") <> 0
    k = ArgWord()
    If k = 0
      PrintN("!! settings remove needs the name of the setting to take out, and none")
      PrintN("   was given, so nothing was changed and nothing was removed.")
      PrintN("   settings remove <name>")
      PrintN("   Type settings on its own to see what names there are.")
      ProcedureReturn
    EndIf
    If SettingsRemove(k) = 0
      SettingsSayWhyNot()
      If SettingsLastError() = #SET_ERR_NOTFOUND
        PrintN("   Type settings on its own to see what names there are.")
      EndIf
      PrintN("   Nothing was changed.")
      ProcedureReturn
    EndIf
    Print("Removed ")
    UartWriteStr(k)
    PrintN(".")
    PrintN("  Its bytes are cleared out of the table in memory, values included -")
    PrintN("  one of these may have been a password. It is STILL IN SETTINGS.TXT")
    PrintN("  on the medium until you type settings save.")
    ProcedureReturn
  EndIf

  If WordIs("reveal") <> 0
    k = ArgWord()
    If k = 0
      PrintN("!! settings reveal needs the name of the setting to print, and none")
      PrintN("   was given, so nothing was printed.")
      PrintN("   settings reveal <name>")
      PrintN("   It prints one setting in full, including a hidden one. This is the")
      PrintN("   deliberate keystroke that puts a password on the screen, which is")
      PrintN("   why it will not do it for a name you did not type.")
      ProcedureReturn
    EndIf
    v = SettingsGet(k)
    If v = 0
      SettingsSayWhyNot()
      PrintN("   Type settings on its own to see what names there are.")
      ProcedureReturn
    EndIf
    If SettingsIsSecret(k) <> 0
      PrintN("!! about to print a secret in full. It goes to the HDMI console as")
      PrintN("   well as to this wire, and into the next screenshot anybody takes.")
    EndIf
    Print("  ")
    UartWriteStr(k)
    Print(" = ")
    UartWriteStr(v)
    PrintNl()
    Print("  ")
    PrintDec(StrLenZ(v))
    PrintN(" characters.")
    If SettingsIsSecret(k) = 0
      PrintN("  That one was never hidden - settings on its own prints it too.")
    EndIf
    ProcedureReturn
  EndIf

  If WordIs("save") <> 0
    CmdSettingsSave()
    ProcedureReturn
  EndIf

  If WordIs("load") <> 0
    CmdSettingsLoad()
    ProcedureReturn
  EndIf

  If WordIs("discard") <> 0
    CmdSettingsDiscard()
    ProcedureReturn
  EndIf

  Print("? settings does not know the word ")
  n = 0
  While n < gWordLen And n < 24
    UartWrite(gLine[gWordAt + n] & $FF)
    n = n + 1
  Wend
  PrintN(", so nothing was done and nothing was changed.")
  PrintN("  settings                   list everything, passwords hidden")
  PrintN("  settings show              the same thing, spelled out")
  PrintN("  settings set <name> <value>")
  PrintN("                             the value is the whole rest of the line")
  PrintN("  settings remove <name>     take one out of the table")
  PrintN("  settings reveal <name>     print one in full, hidden or not")
  PrintN("  settings save              write SETTINGS.TXT to the boot medium")
  PrintN("  settings load              read it back")
  PrintN("  settings discard           accept a part-read file, so a save is")
  PrintN("                             allowed again")
EndProcedure

; ======================================================================
;  U-BOOT ENV ALIASES  -  printenv, setenv, saveenv, env
; ======================================================================
;  The settings store IS what U-Boot's environment was for, and the help
;  has said so for as long as the store existed. What was missing was the
;  three command NAMES a U-Boot user's fingers already know, so a line
;  pasted out of a U-Boot session, or typed from muscle memory, landed on
;  "unknown command" instead of the store that does exactly this job.
;  These are those names, mapped onto the settings model:
;
;    printenv        -> settings show           (v2025.01_cmd_nvedit.c
;    printenv <name> -> one setting, masked      do_env_print, :89)
;    setenv <n> <v>  -> settings set             (do_env_set, :188)
;    saveenv         -> settings save            (do_env_save, :463)
;    env <sub>       -> the sub-command router    (do_env, table :1059)
;
;  TWO PLACES WHERE U-BOOT AND ANVIL GENUINELY DIFFER, and both are
;  handled by SAYING SO rather than by silently doing U-Boot's thing:
;
;    * setenv <name> WITH NO VALUE deletes the variable in U-Boot
;      (do_env_set falls through to _do_env_set which unsets when
;      argc < 3). Anvil does NOT delete on this - a command whose short
;      form quietly destroys a setting is exactly the trap this monitor
;      avoids - it points at `settings remove`, which is the deliberate
;      keystroke for taking one out.
;    * the masking rule still applies. U-Boot's printenv prints a
;      password in the clear; this monitor's output also lands on an HDMI
;      console and in the next screenshot, so a secret is masked here too
;      and `settings reveal` is the keystroke that prints it in full.
;      This is settings.pi4's rule, not one invented for the alias.
; ======================================================================

; printenv, and printenv <name> <name>...
Procedure CmdEnvPrint()
  Define k.i
  Define v.i
  Define any.i

  ; No names: the whole table, exactly `settings show`.
  SkipSpace()
  If gLine[gPos] = 0
    SettingsShowTable()
    ProcedureReturn
  EndIf

  ; One or more names, each printed on its own. Secrets masked, with the
  ; pointer to reveal - same as the table.
  any = 0
  Repeat
    k = ArgWord()
    If k = 0
      Break
    EndIf
    any = 1
    v = SettingsGet(k)
    If v = 0
      Print("!! ")
      UartWriteStr(k)
      PrintN(" is not set. Type settings on its own to see what names there are.")
    ElseIf SettingsIsSecret(k) <> 0
      UartWriteStr(k)
      Print("=")
      UartWriteStr(SettingsMaskText())
      Print("   (")
      PrintDec(StrLenZ(v))
      PrintN(" characters, hidden - settings reveal prints it in full)")
    Else
      UartWriteStr(k)
      Print("=")
      UartWriteStr(v)
      PrintNl()
    EndIf
  ForEver
  If any = 0
    SettingsShowTable()
  EndIf
EndProcedure

; setenv <name> <value...>
Procedure CmdEnvSet()
  Define k.i
  Define v.i

  k = ArgWord()
  If k = 0
    PrintN("!! setenv needs the name of the setting to change, and none was given,")
    PrintN("   so nothing was changed.")
    PrintN("   setenv <name> <value>   the value is the whole rest of the line.")
    PrintN("   This is U-Boot's setenv, mapped onto this monitor's settings store.")
    ProcedureReturn
  EndIf
  v = ArgRest()
  If v = 0
    ; U-Boot deletes here. Anvil will not delete on a short form - said
    ; out loud, with the command that does delete on purpose.
    Print("!! setenv with no value would DELETE ")
    UartWriteStr(k)
    PrintN(" in U-Boot. This monitor")
    PrintN("   does not delete on a short command, because a keystroke that quietly")
    PrintN("   destroys a setting is a trap. Nothing was changed.")
    Print("   To take it out on purpose, type: settings remove ")
    UartWriteStr(k)
    PrintNl()
    PrintN("   To set it to an empty value, that is not something the store keeps.")
    ProcedureReturn
  EndIf
  If SettingsSet(k, v) = 0
    SettingsSayWhyNot()
    PrintN("   Nothing was changed.")
    ProcedureReturn
  EndIf
  Print("Set ")
  UartWriteStr(k)
  Print(" to ")
  UartWriteStr(v)
  Print("   (")
  PrintDec(StrLenZ(v))
  PrintN(" characters)")
  If SettingsIsSecret(k) <> 0
    SettingsSayPlainText()
  EndIf
  PrintN("  This is in memory only. Type saveenv - or settings save - to write it")
  PrintN("  to the medium.")
EndProcedure

; env <sub-command> - the router. Maps U-Boot's `env print/set/save/...`
; onto the same settings model as the standalone aliases above.
Procedure CmdEnv()
  Define k.i
  Define n.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  ; Bare `env` is `env print`, which is `settings show`.
  If gWordLen = 0 Or WordIs("print") <> 0
    CmdEnvPrint()
    ProcedureReturn
  EndIf
  If WordIs("set") <> 0
    CmdEnvSet()
    ProcedureReturn
  EndIf
  If WordIs("save") <> 0
    CmdSettingsSave()
    ProcedureReturn
  EndIf
  If WordIs("load") <> 0
    CmdSettingsLoad()
    ProcedureReturn
  EndIf
  If WordIs("delete") <> 0 Or WordIs("rm") <> 0
    ; `settings remove`, reached through the word env delete expects.
    k = ArgWord()
    If k = 0
      PrintN("!! env delete needs the name of the setting to take out, and none was")
      PrintN("   given, so nothing was changed.")
      PrintN("   env delete <name>")
      ProcedureReturn
    EndIf
    If SettingsRemove(k) = 0
      SettingsSayWhyNot()
      PrintN("   Nothing was changed.")
      ProcedureReturn
    EndIf
    Print("Removed ")
    UartWriteStr(k)
    PrintN(".")
    PrintN("  It is still in SETTINGS.TXT on the medium until you type saveenv.")
    ProcedureReturn
  EndIf

  If WordIs("exists") <> 0
    ; do_env_exists returns a shell rc; with no shell here the useful
    ; form is to SAY whether it is set, on this operator's own console.
    k = ArgWord()
    If k = 0
      PrintN("!! env exists needs the name of a setting to look for.")
      PrintN("   env exists <name>")
      ProcedureReturn
    EndIf
    If SettingsGet(k) <> 0
      UartWriteStr(k)
      PrintN(" is set.")
    Else
      UartWriteStr(k)
      PrintN(" is not set.")
    EndIf
    ProcedureReturn
  EndIf

  If WordIs("grep") <> 0
    ; do_env_grep prints the settings whose NAME or VALUE contains the
    ; text. A secret is matched on its NAME ONLY and printed masked - the
    ; same rule the rest of this file follows, because grep output also
    ; reaches the HDMI console and the next screenshot.
    Define pat.i
    Define i.i
    Define hits.i
    Define kk.i
    Define vv.i
    Define show.i
    pat = ArgWord()
    If pat = 0
      PrintN("!! env grep needs something to search for.")
      PrintN("   env grep <text>   prints the settings whose name or value has it")
      ProcedureReturn
    EndIf
    hits = 0
    i = 0
    While i < SettingsCount()
      If OutBreak() <> 0
        ProcedureReturn
      EndIf
      kk = SettingsKeyAt(i)
      vv = SettingsValueAt(i)
      show = 0
      If SubstrFound(kk, pat) <> 0
        show = 1
      ElseIf SettingsIsSecret(kk) = 0 And SubstrFound(vv, pat) <> 0
        show = 1
      EndIf
      If show <> 0
        Print("  ")
        PutPadded(kk, 26)
        Print("  ")
        If SettingsIsSecret(kk) <> 0
          UartWriteStr(SettingsMaskText())
          PrintNl()
        Else
          UartWriteStr(vv)
          PrintNl()
        EndIf
        hits = hits + 1
      EndIf
      i = i + 1
    Wend
    If hits = 0
      Print("Nothing in the settings store matches ")
      UartWriteStr(pat)
      PrintN(".")
    EndIf
    ProcedureReturn
  EndIf

  If WordIs("default") <> 0
    PrintN("!! env default resets U-Boot's environment to the values compiled into")
    PrintN("   its image. This monitor has no compiled-in defaults - a setting it")
    PrintN("   does not hold simply is not there - so there is nothing to reset to")
    PrintN("   and nothing was changed. To empty the store, remove the settings you")
    PrintN("   do not want and type saveenv.")
    ProcedureReturn
  EndIf
  If WordIs("import") <> 0 Or WordIs("export") <> 0
    PrintN("!! env import and env export move the environment to and from a blob in")
    PrintN("   memory. This monitor keeps its settings as plain text in SETTINGS.TXT")
    PrintN("   on the boot medium instead, which any editor on any computer opens -")
    PrintN("   so the import/export step is pulling the stick. Nothing was done.")
    ProcedureReturn
  EndIf

  Print("? env does not know the word ")
  n = 0
  While n < gWordLen And n < 24
    UartWrite(gLine[gWordAt + n] & $FF)
    n = n + 1
  Wend
  PrintN(", so nothing was done and nothing was changed.")
  PrintN("  env print                  list everything, passwords hidden")
  PrintN("  env set <name> <value>     the value is the whole rest of the line")
  PrintN("  env delete <name>          take one out of the table")
  PrintN("  env exists <name>          say whether one is set")
  PrintN("  env grep <text>            list the ones whose name or value has it")
  PrintN("  env save                   write SETTINGS.TXT to the boot medium")
  PrintN("  env load                   read it back")
  PrintN("  printenv, setenv and saveenv are the same commands without the env word.")
EndProcedure
