Procedure CmdFat()
  Define nm.i
  Define a.i
  Define n.i
  Define got.i
  Define i.i
  Define ch.i

  ; --- the name, copied out of the command line ----------------------
  ; gLine is the line editor's buffer and ReadLine will overwrite it the
  ; moment this returns, so the name is copied rather than pointed at.
  SkipSpace()
  nm = gPos
  SkipWord()

  If gPos = nm
    ; Bare f - a status report, and the one command worth having when
    ; there is no medium, because it names WHICH step failed.
    ;
    ; THE FACTS IT PRINTS ARE THE BOARD'S, so the board prints them. This
    ; used to read MscBlockCount(), SdBlockCount(), FatType() and
    ; FatBytesPerCluster() inline - four Pi 4 names, in a core file. There
    ; is no FAT and no block count on the Arduino UNO Q; there is a
    ; firmware file service on an EFI System Partition, and the true
    ; sentences about it are completely different ones. HwStorageReport()
    ; is the seam: each board says what its own medium is, in its own
    ; words, and this command supplies the paragraph about `load` that is
    ; the same everywhere.
    If HwStorageUp() = 0
      ProcedureReturn
    EndIf
    HwStorageReport()
    PrintN("  Type load <name> to read a file off it into memory, and load <name>")
    ; THE DEFAULT IS PRINTED, NOT SPELT - 2026-09-08. It used to be the
    ; literal "00400000" in this sentence, and that number is now
    ; arithmetic on the size of the running monitor. A help line naming
    ; an address the command would not actually use is worse than none.
    Print("  <address> to read it somewhere other than the default ")
    PutAddr(HwStageAddr())
    PrintN(".")
    PrintN("  Type boot <name> for a payload container, which carries its own load")
    PrintN("  address and needs none typed.")
    ProcedureReturn
  EndIf

  ; NUL-terminate in place. Safe: everything after the name is either
  ; the address, which is parsed BELOW from gPos, or nothing - and the
  ; byte overwritten is the separating space.
  gLine[gPos] = 0
  Define after.i = gPos + 1

  ; --- the destination ------------------------------------------------
  gPos = after
  a = ParseHex()
  If gParseOk = 0
    a = HwStageAddr()
  EndIf

  If HwStorageUp() = 0
    ProcedureReturn
  EndIf

  If HwFileOpen(@gLine[nm]) = 0
    Print("!! the file ")
    UartWriteStr(@gLine[nm])
    PrintN(" could not be opened, so nothing was loaded")
    PrintN("   and memory is untouched. The name has to be a short 8.3 name in the")
    PrintN("   root directory of the boot medium - case does not matter.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())   ; a POINTER - see the note on SdErrorText
    PrintNl()
    ProcedureReturn
  EndIf
  n = HwFileSize()

  ; The window check, before a single byte lands. See the header.
  If InPayload(a, a + n - 1) = 0
    If HitsMonitor(a, a + n - 1) <> 0
      Print("!! that file is ")
      PrintDec(n)
      PrintN(" bytes long, so loading it there would run over")
      Print("   the monitor itself, which lives at ")
      PutAddr(gMonHitLo)
      Print(" to ")
      PutAddr(gMonHitHi)
      PrintN(".")
      PrintN("   Nothing was loaded. Give load an address in one of the payload")
      PrintN("   windows - type help to see them - or leave the address out and it")
      Print("   goes to ")
      PutAddr(HwStageAddr())
      PrintN(".")
    Else
      Print("!! that file is ")
      PrintDec(n)
      PrintN(" bytes long, and loading it there would run")
      PrintN("   outside both payload windows. Nothing was loaded. The length is")
      PrintN("   the file's, not yours, which is why an address that looks fine can")
      PrintN("   still be refused. These are the windows you may load into:")
      PutWindows()
    EndIf
    HwFileClose()
    ProcedureReturn
  EndIf

  ; AND THE BOARD, on top of the window check. The windows say whether
  ; the destination is memory the operator owns; they say nothing about
  ; whether it can take a bus access at all. The file is closed on the
  ; refusal path so a refused load leaves no handle open on the medium.
  If AddrAllowed(a, a + n - 1, 1, "load", "loaded") = 0
    HwFileClose()
    ProcedureReturn
  EndIf

  got = HwFileReadAt(0, a, n)
  HwFileClose()

  If got < 0
    PrintN("!! reading the file stopped part way through, AFTER some of it had")
    PrintN("   already been written into memory. What is at that address now is")
    PrintN("   the beginning of a file and whatever was there before underneath")
    PrintN("   it. Do not run it. Load it again, or load something else over it.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())   ; a POINTER - see the note on SdErrorText
    PrintNl()
    ProcedureReturn
  EndIf

  Print("Loaded ")
  PrintDec(got)
  Print(" bytes into memory, filling ")
  PutAddr(a)
  Print(" through ")
  PutAddr(a + got - 1)
  PrintN(".")
  If got <> n
    Print("!! that is short. The directory says the file is ")
    PrintDec(n)
    PrintN(" bytes, and")
    Print("   only ")
    PrintDec(got)
    PrintN(" of them arrived, so what is in memory is part of a")
    PrintN("   file. The entry point has deliberately NOT been armed, so a bare")
    PrintN("   run will not jump into it by accident.")
    ProcedureReturn
  EndIf
  gEntry = a
  gHaveEntry = 1
  Print("  Its entry point is ")
  PutAddr(a)
  PrintN(", which is where run will jump if you")
  PrintN("  type run with no address of your own.")
EndProcedure

; ======================================================================
;  save - write memory back to a file on the boot medium
; ======================================================================
;  THIS IS WHAT MAKES ANVIL SELF-HOSTING. Until it existed, updating the
;  monitor meant getting U-Boot back, and U-Boot is no longer what the
;  firmware boots - so it meant pulling the stick and using another
;  machine. Now:
;
;      map                            it prints `stage a file at <s>`
;      receive <s> <len> <crc>        the new build, over the wire
;      save ANVIL.IMG <s>             onto the stick it boots from
;      reset                          and it comes up running it
;
;  Anvil builds Anvil.
;
;  THE SIZE NO LONGER HAS TO MATCH. This header used to say the opposite
;  at length: that fat.pi4 would not allocate clusters, extend a file or
;  touch a directory entry, so the file was a fixed-size slot and the
;  host padded up to it. That was true and it is not any more - fat.pi4
;  now allocates, extends, truncates, creates and deletes, with a gate
;  that models a writable volume and thirteen mutations that go red.
;
;  So a length may be given: save <name> <addr> [len]. Left out, the
;  file's current size is used, which is what the fixed-slot era did and
;  keeps every existing caller working.
;
;  The practical difference is that an update sends the image and not a
;  slot. Anvil is about 224 KB in a 692 KB slot, so padding meant
;  shipping three times the bytes over the wire every single time.
;
;  IT REFUSES RATHER THAN GUESSING. A length that does not match, a file
;  that is not there, a medium that will not mount - each says which,
;  because "save failed" over a boot image is the least helpful sentence
;  available.
; ----------------------------------------------------------------------
Procedure CmdSave()
  Define nm.i
  Define a.i
  Define n.i
  Define i.i
  Define ch.i

  ; --- the name, copied out of the line editor's buffer ---------------
  SkipSpace()
  nm = gPos
  i = 0
  While gLine[gPos] <> 0 And gLine[gPos] <> 32 And i < 12
    gName[i] = gLine[gPos]
    gPos = gPos + 1
    i = i + 1
  Wend
  gName[i] = 0
  If i = 0
    PrintN("!! save needs the name of a file to write, and none was given, so")
    PrintN("   nothing was written.")
    PrintN("   save <name> <address> [length]")
    PrintN("   It writes that many bytes out of memory onto the boot medium,")
    PrintN("   replacing what is in that file and resizing the file to match.")
    PrintN("   Leave the length out and the file keeps the size it already has.")
    PrintN("   The address and the length are both hexadecimal.")
    ; THE ADDRESS IN THE EXAMPLE IS THE ONE THIS BOARD WOULD ACTUALLY
    ; USE. It was the literal 400000, which stopped being right the day
    ; the staging address started following the monitor's size. A worked
    ; example naming an address the board refuses is a worked example of
    ; a refusal. The length stays illustrative - it is the image's, and
    ; the image being saved is not the one running.
    Print("   save KERNEL8.IMG ")
    PutAddr(HwStageAddr())
    PrintN(" 36A0C is how Anvil replaces itself.")
    ProcedureReturn
  EndIf

  a = ParseHex()
  If gParseOk = 0
    PrintN("!! save needs to know where in memory to take the bytes from, and no")
    PrintN("   address was given, so nothing was written and the file on the")
    PrintN("   medium is untouched.")
    PrintN("   save <name> <address> [length], with both numbers in hexadecimal.")
    ProcedureReturn
  EndIf

  If HwStorageUp() = 0
    ProcedureReturn
  EndIf

  ; THE WRITE GATE, ASKED BEFORE ANYTHING IS OPENED OR ARMED. This used to
  ; be `If gMedium <> 1` followed by FatSetBlockWriter(@MscWriteBlock)
  ; here, with a matching disarm on each of the seven paths out below.
  ; Both are Pi 4 facts in a core file, and both moved into the board's
  ; HwFileWriteAll, which arms the writer around its own single write and
  ; disarms it on every exit. The GUARANTEE is unchanged and stronger for
  ; being in one place: seven disarms that must each be remembered is
  ; seven chances to leave the boot medium reachable by the next bug.
  If HwFileWritable() = 0
    PrintN("!! nothing was written and the file is untouched, because this board")
    PrintN("   cannot write to its boot medium right now. Nothing was opened,")
    PrintN("   created or resized, and no writer was ever armed.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())      ; a POINTER
    PrintNl()
    ProcedureReturn
  EndIf

  ; A length, if one was given. Hex like every other address argument
  ; here - mixing bases inside one command line is how a boot image ends
  ; up the wrong length.
  Define want.i
  want = ParseHex()
  Define haveLen.i
  haveLen = gParseOk

  ; THE CURRENT SIZE, WHICH IS ALSO THE TEST FOR "IS IT THERE".
  ;
  ; save keeps the size the file already has when no length is given, so
  ; it has to ask. Opening it read-only is how, and it is also how the
  ; not-there case is detected - the same two facts the FatOpen here used
  ; to establish, now asked through the seam so the Q can answer them.
  ;
  ; SAVE CREATES THE FILE WHEN IT IS NOT THERE, BUT ONLY WITH A LENGTH.
  ; A file that does not exist has no size of its own to keep, and
  ; guessing one from the transfer would be worse than refusing: a boot
  ; image saved one byte short does not fail loudly, it produces a board
  ; that almost works. What forced creation to exist at all: the CYW43455
  ; needs three files on the stick and not one of them is there to be
  ; replaced, and there is no way to put a first copy of a file on a
  ; medium from a board that only boots from that medium.
  Define exists.i
  exists = HwFileOpen(@gName[0])
  If exists <> 0
    n = HwFileSize()
    HwFileClose()
    Print("The file ")
    UartWriteStr(@gName[0])
    Print(" on the boot medium is ")
    PrintDec(n)
    PrintN(" bytes long at the moment.")
  Else
    If HwFileLastError() <> #HW_FILE_NOTFOUND
      ; ONLY "not there" IS TREATED AS "make it". An unreadable directory
      ; or a medium that dropped off the bus also fails to open, and
      ; creating a file on top of either is how a filesystem gets damaged
      ; by a program trying to be helpful.
      Print("!! the file ")
      UartWriteStr(@gName[0])
      PrintN(" could not be opened, so nothing was written")
      PrintN("   and nothing on the medium has changed.")
      Print("   The medium said: ")
      UartWriteStr(HwFileErrorText())
      PrintNl()
      ProcedureReturn
    EndIf
    If haveLen = 0
      Print("!! the file ")
      UartWriteStr(@gName[0])
      PrintN(" is not on the medium, and no length was given.")
      PrintN("   Nothing was written. save will create a file that is not there")
      PrintN("   yet, but only when it is told how many bytes to put in it -")
      PrintN("   a file that does not exist has no size of its own to keep.")
      PrintN("   save <name> <address> <length>, both numbers in hexadecimal.")
      ProcedureReturn
    EndIf
    Print("The file ")
    UartWriteStr(@gName[0])
    PrintN(" is not on the medium yet, so it is being created.")
    n = 0
  EndIf

  If haveLen <> 0
    If want < 0
      PrintN("!! a length cannot be negative, so nothing was written and the file")
      PrintN("   is untouched. Give the length in hexadecimal bytes, or leave it")
      PrintN("   out entirely and the file keeps the size it already has.")
      ProcedureReturn
    EndIf
    If want <> n And exists <> 0
      Print("It is being resized from ")
      PrintDec(n)
      Print(" bytes to ")
      PrintDec(want)
      PrintN(" bytes to match what")
      PrintN("you asked to write.")
    EndIf
    n = want
  EndIf

  If n <= 0
    PrintN("!! there is nothing to write: the length works out as zero bytes, and")
    PrintN("   the file is untouched. Give a length in hexadecimal bytes.")
    ProcedureReturn
  EndIf

  ; The source has to be somewhere sane. Same windows the loaders use -
  ; reading from inside the monitor and writing it to the boot image
  ; would produce a file that boots into whatever this monitor's BSS
  ; happened to contain.
  If HitsMonitor(a, a + n - 1) <> 0
    Print("!! the bytes would be taken from inside the monitor itself, which")
    PrintNl()
    Print("   lives at ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(". Nothing was written. Writing")
    PrintN("   the running monitor's own memory into a boot image would produce a")
    PrintN("   file that boots into whatever this monitor's working storage")
    PrintN("   happened to contain at the moment you typed the command. Receive")
    PrintN("   the image into a payload window first, then save from there.")
    ProcedureReturn
  EndIf
  ; The source is READ, byte by byte, to build the file. A source in a
  ; block that cannot answer stalls the board part way through writing
  ; the boot image, which is the worst moment there is for it.
  If AddrAllowed(a, a + n - 1, 0, "save", "written") = 0
    ProcedureReturn
  EndIf

  Print("Writing ")
  PrintDec(n)
  Print(" bytes out of memory, starting at ")
  PutAddr(a)
  PrintN(". This")
  PrintN("takes a moment and must not be interrupted.")
  UartDrain()

  If HwFileWriteAll(@gName[0], a, n) = 0
    PrintN("!! the write did not finish. THE FILE MAY NOW BE PART OLD AND PART NEW.")
    PrintN("   Write it again before resetting the board, or it will try to boot")
    PrintN("   half of one image and half of another. No other file on the medium")
    PrintN("   can have been touched: this command gives the medium one name.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
    ProcedureReturn
  EndIf

  ; "written." IS A PROTOCOL STRING, full stop included.
  ; tools/anvil_update.py checks  if "written." not in out  and refuses
  ; to reset the board when it is missing, precisely so a half-written
  ; boot image is never reset into. That word cannot change, and it must
  ; stay on the success path only. The sentences below it are free prose
  ; and the script ignores them.
  PrintN("written.")
  Print("  Saved ") : UartWriteStr(@gName[0]) : PrintN(" on the boot medium.")
  PrintN("  That file now holds what was in memory, and the")
  PrintN("  block writer has been disarmed again so nothing else in this monitor")
  PrintN("  can reach the medium. Saving does not change the boot-file selection;")
  PrintN("  reset still loads the configured boot image, not an arbitrary saved file.")
EndProcedure

; ======================================================================
;  fatls / ls - list the root directory of the boot medium
; ======================================================================
;  THE SINGLE MOST-MISSED EVERYDAY COMMAND (the U-Boot inventory, S2.2):
;  `load` needs a name you already know, and there was no way to ask the
;  medium what is on it. This is that - one line per entry, its 8.3 name,
;  its size in bytes or a <DIR> marker, and a summary line underneath.
;
;  IT IS CORE LOGIC RIDING THE STORAGE SEAM. It names no chip: it asks the
;  board whether it has storage at all (RequireCap over #CAP_STORAGE,
;  exactly as gpio_cmd.pi4 gates on #CAP_GPIO), then whether that storage
;  can be ENUMERATED (HwFileCanList - a separate question, see below),
;  brings the medium up through HwStorageUp() the same as load and save,
;  and walks the directory through the HwDir* iterator the board supplies.
;  On the Pi 4 that iterator is fat.pi4's FatDirRewind / FatDirNext, the
;  SAME root-directory walk fat_FindEntry does, exposed rather than copied.
;  No FAT parsing lives in this file and no chip is named in it.
;
;  HONEST ABOUT THE LIBRARY'S LIMITS, because a listing that hides them is
;  worse than none: it lists the ROOT directory only (the reader reads no
;  subdirectory), names are the 8.3 short form (a long name shows under its
;  short alias), and matching is case-insensitive. A subdirectory or path
;  argument is refused in a whole sentence rather than silently ignored.
;
;  IT NEVER SILENTLY TRUNCATES. Any byte on the wire stops it through
;  OutBreak(), and it says it stopped; and if the directory holds more
;  than #FATLS_CAP entries it stops at the cap and says how many it lists
;  at once and that the rest are still there. A short answer that looked
;  complete is the failure this monitor refuses everywhere.
; ----------------------------------------------------------------------
#FATLS_CAP = 1024              ; entries listed in one fatls, then it says
                              ; the rest were not shown rather than scroll
                              ; a directory without end

Global Dim gLsName.a[#HW_DIR_NAME_LEN]   ; the 11 raw 8.3 bytes of one row

; PutName83 - the 11 raw name bytes at *e printed as NAME.EXT: the base
; and extension each have their space padding trimmed, and the dot appears
; only when there is an extension. Returns how many characters it printed,
; so the caller can pad the name to a fixed column.
Procedure.i PutName83(*e)
  Define i.i
  Define baseLen.i
  Define extLen.i
  Define printed.i

  printed = 0
  baseLen = #HW_DIR_BASE_MAX
  While baseLen > 0 And PeekA(*e + baseLen - 1) = 32
    baseLen = baseLen - 1
  Wend
  extLen = #HW_DIR_EXT_MAX
  While extLen > 0 And PeekA(*e + #HW_DIR_BASE_MAX + extLen - 1) = 32
    extLen = extLen - 1
  Wend

  i = 0
  While i < baseLen
    UartWrite(PeekA(*e + i))
    printed = printed + 1
    i = i + 1
  Wend
  If extLen > 0
    UartWrite(46)                       ; 46 = '.'
    printed = printed + 1
    i = 0
    While i < extLen
      UartWrite(PeekA(*e + #HW_DIR_BASE_MAX + i))
      printed = printed + 1
      i = i + 1
    Wend
  EndIf
  ProcedureReturn printed
EndProcedure

; PutDecRight - a non-negative decimal right-justified in a field w wide,
; so the size column lines up down the listing. A value too wide for the
; field is printed in full rather than clipped - the number is the point.
Procedure PutDecRight(v.i, w.i)
  Define digits.i
  Define t.i
  Define pad.i

  digits = 1
  t = v
  While t >= 10
    t = t / 10
    digits = digits + 1
  Wend
  pad = w - digits
  While pad > 0
    UartWrite(32)                       ; 32 = a space
    pad = pad - 1
  Wend
  PrintDec(v)
EndProcedure

Procedure CmdFatls()
  Define argAt.i
  Define n.i
  Define files.i
  Define dirs.i
  Define total.i
  Define shown.i
  Define more.i
  Define namelen.i
  Define c.i

  ; THE GATE, FIRST - as gpio_cmd does. On a board with no block storage
  ; this prints the honest "not available on this board" sentence and
  ; returns cleanly, having touched no storage seam.
  If RequireCap(#CAP_STORAGE, "fatls", "this board has no block storage medium Anvil can read") = 0
    ProcedureReturn
  EndIf

  ; ROOT ONLY, AND SAY SO. fat.pi4 reads no subdirectory, so a path or a
  ; subdirectory name is refused in a whole sentence rather than ignored.
  ; A lone "/" or "." is the root itself and is allowed through.
  SkipSpace()
  argAt = gPos
  SkipWord()
  If gPos > argAt
    c = gLine[argAt] & $FF
    If (gPos - argAt) = 1 And (c = 47 Or c = 46)   ; 47 = '/', 46 = '.'
      ; the root, spelled out - fall through
    Else
      PrintN("!! this monitor lists the ROOT directory of the boot medium only, so")
      PrintN("   a subdirectory or a path cannot be listed and nothing was shown.")
      PrintN("   The FAT reader underneath reads no subdirectory - the same reason")
      PrintN("   load takes a bare 8.3 name and not a path. Type fatls on its own,")
      PrintN("   or ls, for the root, which is where the files it can reach live.")
      ProcedureReturn
    EndIf
  EndIf

  ; THE SECOND GATE, and it is a different question from #CAP_STORAGE.
  ;
  ; A board can be perfectly able to open a file BY NAME and completely
  ; unable to list a directory, and the Arduino UNO Q is exactly that
  ; board: UEFI's file protocol opens what you name, and walking a
  ; directory means reading EFI_FILE_INFO records back off a directory
  ; handle, which is a second piece of work nobody has written. Folding
  ; that into #CAP_STORAGE would have meant either declaring the Q as
  ; having no storage - untrue, `load` and `boot` work there - or letting
  ; `fatls` print an empty directory, which is the silent wrong answer.
  ; So the listing has its own question and its own honest refusal.
  If HwFileCanList() = 0
    PrintN("!! this board cannot list a directory, so nothing was shown - though it")
    PrintN("   can read and write files perfectly well by name. Its medium is")
    PrintN("   reached through a file service that opens what it is given rather")
    PrintN("   than through a filesystem this monitor walks itself, and enumerating")
    PrintN("   a directory over that service is not implemented here.")
    PrintN("   load <name> and boot <name> both work; you have to know the name.")
    ProcedureReturn
  EndIf

  If HwStorageUp() = 0
    ProcedureReturn
  EndIf

  If HwDirRewind() = 0
    ; HwStorageUp() reported a mounted volume, so this should not arise;
    ; if it does, be honest rather than return in silence.
    PrintN("!! the boot medium is mounted but its root directory could not be")
    PrintN("   opened for listing, so nothing was shown.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
    ProcedureReturn
  EndIf

  PrintN("The root directory of the boot medium:")

  files = 0
  dirs  = 0
  total = 0
  shown = 0
  more  = 0

  n = HwDirNext()
  While n = 1
    ; ONE BREAK CHECK PER LINE, at the top, so a stopped listing never
    ; leaves half a row on the wire - the discipline DumpMem and gpio use.
    If OutBreak() <> 0
      PrintN("   stopped - the rest of the directory was not listed.")
      ProcedureReturn
    EndIf
    If shown >= #FATLS_CAP
      ; NEVER SILENTLY TRUNCATE. n is still 1, so there is at least one
      ; more entry; stop at the cap and say so under the summary.
      more = 1
      Break
    EndIf

    HwDirName(@gLsName[0])
    Print("  ")
    namelen = PutName83(@gLsName[0])
    ; Pad the 8.3 name to a 12-column field (8 + '.' + 3) so the size and
    ; the <DIR> marker line up down the page.
    While namelen < 12
      UartWrite(32)
      namelen = namelen + 1
    Wend
    Print("  ")
    If HwDirIsDir() <> 0
      PrintN("<DIR>")
      dirs = dirs + 1
    Else
      PutDecRight(HwDirSize(), 10)
      PrintN(" bytes")
      files = files + 1
      total = total + HwDirSize()
    EndIf
    shown = shown + 1

    n = HwDirNext()
  Wend

  If n = -1
    ; The walk hit a read error or a corrupt chain. Say so; the totals
    ; below stay honest - they count only what was listed before it broke.
    PrintN("!! the listing stopped part way through because the directory could")
    PrintN("   not be read to the end, so what is above is only part of it and the")
    PrintN("   totals below count only that part.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
  EndIf

  ; THE SUMMARY LINE - files, bytes, directories, each singular or plural.
  Print("  ")
  PrintDec(files)
  If files = 1
    Print(" file, ")
  Else
    Print(" files, ")
  EndIf
  PrintDec(total)
  Print(" bytes, ")
  PrintDec(dirs)
  If dirs = 1
    PrintN(" directory.")
  Else
    PrintN(" directories.")
  EndIf

  If more <> 0
    Print("!! there are more entries in this directory than the ")
    PrintDec(#FATLS_CAP)
    PrintN(" this")
    PrintN("   command lists at once, so the rest were not shown and the totals")
    PrintN("   above count only what was. They are still on the medium; this")
    PrintN("   command stops here rather than scrolling a directory without end.")
  EndIf

  PrintN("  These are 8.3 short names in the root directory; a file saved under a")
  PrintN("  long name shows under its short form, and a subdirectory is marked")
  PrintN("  <DIR> but not listed into. Case is not significant.")
EndProcedure


; ======================================================================
;  cat - print a text file off the boot medium, without loading it
; ----------------------------------------------------------------------
;  WHY THIS EXISTS. Reading a small text file on the card used to mean
;  `load` into a payload window and then `memory` over it, which prints
;  hex with the characters in a side column - a fine way to read a boot
;  image and a poor way to read four lines of configuration. It also
;  overwrites a payload window to look at a file.
;
;  The immediate need is CONFIG.TXT: an experiment is about to add a line
;  to it, and the file has to be recorded verbatim BEFORE anything is
;  written, on a board whose only console is a radio link. Reading it by
;  eye out of a hex dump is how a character gets transcribed wrongly into
;  a file the firmware then has to boot.
;
;  IT READS AND NEVER WRITES, and it goes through the same Hw file seam
;  every other reader here uses, so it is honest on a board with no
;  block storage and works on one whose medium is a firmware file
;  service rather than a filesystem this monitor walks.
;
;  ROOT ONLY AND 8.3, because the FAT reader underneath reads no
;  subdirectory. Same rule as `load`, refused in the same words.
;
;  WHAT IT DOES TO THE BYTES. It prints printable ASCII as itself, turns
;  a lone LF into the CR-LF a terminal wants, and prints anything else -
;  a control byte, a high byte, a NUL - as a dot with a running count
;  reported at the end. A file that is not text says so in that count
;  rather than by scrambling the terminal, and a config file with a
;  stray byte in it is exactly the thing worth noticing.
; ======================================================================
#CAT_CHUNK   = 256
#CAT_MAX     = 65536

Global Dim gCatBuf.b[#CAT_CHUNK]

Procedure CmdCat()
  Define nm.i
  Define n.i
  Define off.i
  Define want.i
  Define got.i
  Define i.i
  Define c.i
  Define odd.i
  Define shown.i
  Define stopped.i

  If RequireCap(#CAP_STORAGE, "cat", "this board has no block storage medium Anvil can read") = 0
    ProcedureReturn
  EndIf

  SkipSpace()
  nm = gPos
  SkipWord()
  If gPos = nm
    PrintN("!! cat needs the name of a file to print, and none was given, so")
    PrintN("   nothing was read.")
    PrintN("   cat CONFIG.TXT")
    PrintN("   The name is a short 8.3 name in the root directory of the boot")
    PrintN("   medium - case does not matter, and a path cannot be used because")
    PrintN("   the reader underneath reads no subdirectory.")
    ProcedureReturn
  EndIf
  ; NUL-terminate in place. gLine is the line editor's buffer and everything
  ; after the name on this line is already consumed.
  gLine[gPos] = 0

  If HwStorageUp() = 0
    ProcedureReturn
  EndIf

  If HwFileOpen(@gLine[nm]) = 0
    Print("!! the file ")
    UartWriteStr(@gLine[nm])
    PrintN(" could not be opened, so nothing was printed.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
    ProcedureReturn
  EndIf
  n = HwFileSize()

  Print("---- ")
  UartWriteStr(@gLine[nm])
  Print(", ")
  PrintDec(n)
  PrintN(" bytes ----")

  If n <= 0
    HwFileClose()
    PrintN("---- the file is empty. Nothing was printed because there is nothing")
    PrintN("     in it, which is a different thing from a file that would not read.")
    ProcedureReturn
  EndIf

  odd = 0
  shown = 0
  stopped = 0
  off = 0
  While off < n
    If OutBreak() <> 0
      stopped = 1
      Break
    EndIf
    If off >= #CAT_MAX
      stopped = 2
      Break
    EndIf
    want = n - off
    If want > #CAT_CHUNK
      want = #CAT_CHUNK
    EndIf
    got = HwFileReadAt(off, @gCatBuf[0], want)
    If got <= 0
      stopped = 3
      Break
    EndIf
    i = 0
    While i < got
      c = gCatBuf[i] & $FF
      If c = 10
        UartWriteNl()
      ElseIf c = 13
        ; A CR is swallowed: the LF beside it already produced CR-LF, and
        ; a bare CR on its own would put the terminal back at column zero
        ; over text it has just written.
      ElseIf c = 9
        UartWrite(32)
        UartWrite(32)
      ElseIf c >= 32 And c <= 126
        UartWrite(c)
      Else
        UartWrite(46)                   ; 46 = a full stop
        odd = odd + 1
      EndIf
      shown = shown + 1
      i = i + 1
    Wend
    off = off + got
  Wend
  HwFileClose()
  PrintNl()

  Print("---- ")
  PrintDec(shown)
  Print(" of ")
  PrintDec(n)
  PrintN(" bytes printed.")
  If odd > 0
    Print("!! ")
    PrintDec(odd)
    PrintN(" of those bytes were not printable text and were shown as a")
    PrintN("   full stop each. In a configuration file that is worth looking at:")
    PrintN("   the file is either not text or has something in it nobody typed.")
  EndIf
  If stopped = 1
    PrintN("!! stopped early because a key was pressed. The rest of the file was")
    PrintN("   not printed and nothing on the medium was changed.")
  ElseIf stopped = 2
    Print("!! stopped at ")
    PrintDec(#CAT_MAX)
    PrintN(" bytes. This command prints small text files and")
    PrintN("   refuses to scroll a large one without end; the file is intact and")
    PrintN("   load will read all of it into memory.")
  ElseIf stopped = 3
    PrintN("!! the read stopped part way through, so what is above is the")
    PrintN("   beginning of the file and not all of it.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
  EndIf
EndProcedure
