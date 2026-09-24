; ======================================================================
;  hwfile.pbi - THE FILE SEAM OVER THE SHARED FILESYSTEMS, for any board
;  with a block device.
;
;  It implements the HwFile* and HwDir* families of Anvil/Hal/hal.pbi on
;  top of Anvil/Storage/filesystem.pbi - open by name, size, read at an
;  offset, replace a whole file, remove, rename, make and remove folders,
;  and walk a directory. A board with a block medium supplies THREE
;  VALUES and nothing else:
;
;      gHwFileMounted    1 once something is mounted
;      gHwFileWritable   1 if a write can work at all right now
;      gHwFileWriter     the ranged block writer, armed here for the
;                        length of one write and disarmed on every path
;                        out - see HwFileWriteAll
;
;  IT WAS RaspberryPi4/Board/hw_file.pi4 UNTIL 2026-09-18, and it moved
;  because it never had a chip in it. Stripped of comments there is not
;  one reference in it to a controller, a register or a medium: every
;  call it makes is an Fs* call, a WallClock* call, or its own. The board
;  it lived in happened to be the only board with a block device, which
;  is a different thing from the file being that board's.
;
;  A BOARD WITH NO BLOCK DEVICE DOES NOT USE THIS. The Arduino UNO Q
;  answers the same seam from the firmware's own file service
;  (ArduinoQ/Board/hw_file_q.unoq) with completely different machinery,
;  which is the whole point of the seam being a seam.
;
;  WHAT FOLLOWS IS THE ORIGINAL HEADER, unchanged, because its reasoning
;  is the reasoning this file still runs on. Where it says "the Pi 4",
;  read "the first board that had one".
; ----------------------------------------------------------------------
;  The file-level storage seam, first implemented over that board's FAT
;  layer and the block medium its storage backend brings up.
;
;  WHY THIS FILE IS THIN AND WHY THAT IS THE POINT. Everything here is a
;  four-line wrapper. The Pi 4 already had every one of these operations -
;  StorageUp, FatOpen, FatSize, FatSeek, FatRead, FatClose, FatOverwrite -
;  and the monitor already called them directly. What it did NOT have was
;  a NAME for the operation that a second board could also answer to, and
;  the moment the Arduino UNO Q needed to read a file the direct calls
;  became a fork waiting to happen: the Q has no block device, no sector
;  reader and no FAT parser of ours, only the firmware's file service.
;
;  So the calls did not move to the Q. They moved BEHIND A NAME, and the
;  Q answers to the same name with completely different machinery. That
;  is Anvil/ARCHITECTURE.md's rule - "named backends, not chips" - applied
;  to the one group that had been left at block level because only one
;  board had ever needed it.
;
;  THE PI 4'S OFFSET BEHAVIOUR IS PRESERVED, deliberately and checkably.
;  Reads at repeated or random offsets still seek and every old guard is
;  retained. The one optimized case is a sequential read that begins at the
;  exact cursor left by the preceding successful seam read; avoiding a seek
;  there prevents a chunked multi-megabyte load from repeatedly walking the
;  FAT chain from its first cluster. See HwFileReadAt's validity contract.
;  The block writer is still armed only inside HwFileWriteAll.
;
;  IT DOES NOT BRING THE MEDIUM UP, AND THAT IS AN EXISTING CONTRACT
;  RATHER THAN A SHORTCUT. Anvil/Core/settings.pbi's SettingsLoad has
;  never brought a medium up - RaspberryPi4/Lib/wifi.pi4:342 says so in as
;  many words - because bringing one up on this board means enumerating
;  PCIe, xHCI and USB mass storage and printing a paragraph about it, and
;  a library that did that inside a getter would be unusable. The COMMAND
;  brings the medium up, once, and then reads files. HwStorageUp() is that
;  step, and it lives in RaspberryPi4/Board/storage.pi4 rather than here
;  for a mechanical reason worth writing down: StorageUp() calls
;  UsbEnumerate(), which lives in Board/cursor_input.pi4, which needs the
;  display - so the whole bring-up chain must be included LATE, while this
;  file must be included EARLY, before the settings store that calls it.
;  Splitting the two is what lets both sit in their right place.
;
;  INCLUDE ORDER: after Anvil/Core/wallclock.pbi (hwfile_Stamp dates each
;  change with it), after RaspberryPi4/Lib/fat.pi4 and after
;  RaspberryPi4/Lib/usbmsc.pi4 (for MscWriteBlock), and BEFORE
;  Anvil/Core/settings.pbi and every other core file that calls HwFile*.
;  Board/storage.pi4 comes much later and assigns gHwFileWritable as it
;  mounts; until it has, this seam correctly answers "not writable yet".
; ======================================================================

; The seam's error code for the last HwFile* call. Set on every failure
; path, cleared at the top of every entry point, so a caller reading it
; after a success can never be handed a stale reason for a call that
; worked.
Global gHwFileErr.i

; The FILESYSTEM's own sentence for that same failure, taken at the moment
; it failed. A pointer to a literal, or 0 when the last failure was one
; this seam decided itself. It exists because the reason and the code do
; not survive equally long: the settling flush that runs on a failure path
; resets the filesystem's error word, so a sentence fetched afterwards is
; about the flush and not about the failure. See hwfile_MapFat.
Global gHwFileFsText.i

; 1 while a file is open through this seam. fat.pi4 has FatIsOpen(), and
; this is not a second copy of it - it is this SEAM's notion of open, so
; that HwFileReadAt can refuse with #HW_FILE_NOTOPEN rather than let
; fat.pi4 answer a read against whatever file some other command left
; open. The two agree in normal operation and the disagreement is the
; interesting case.
Global gHwFileOpen.i

; 1 only when the FAT cursor left by the last successful seam operation is
; known to be the continuation point for this seam's open file. This is not
; inferred from FatTell() alone: FatRead may advance fat_pos and then fail
; while resolving the next cluster, leaving a position that looks current
; and a cursor that is not. Open establishes a valid position at zero;
; every seek/read attempt clears this first and restores it only after the
; operation has completed successfully.
Global gHwFileReadCont.i

; 1 when the medium that is currently mounted can be written to.
;
; DECLARED HERE AND ASSIGNED BY Board/storage.pi4, which is the file that
; knows which medium came up. On this board writing is implemented for the
; USB stick and not for the SD card, and it has been that way since `save`
; was written; storage.pi4 sets this to 1 when it mounts USB and 0 when it
; falls back to the card. Until anything is mounted it is 0, which is the
; truthful answer to "can this board write right now".
;
; IT IS NOT gMedium <> 1 TESTED FROM HERE, though that is what the two
; calling commands used to do. gMedium is declared in storage.pi4, which
; is included several hundred lines further down than this file has to be
; - see INCLUDE ORDER above - so reading it here would be reading a global
; that does not exist yet. One flag, declared where it is read and
; assigned where the fact is known, keeps both files in the only positions
; the dependency chain allows them to occupy.
Global gHwFileWritable.i

; 1 once a medium is mounted and files on it can be opened. Declared here
; and assigned by Board/storage.pi4 for exactly the reason gHwFileWritable
; is: storage.pi4's own gFatUp does not exist yet at this point in the
; include order, and this file has to be here. The two flags are set on
; the same lines, one mount apart in meaning: mounted says a file can be
; READ, writable says it can be written.
Global gHwFileMounted.i

; THE BLOCK WRITER HwFileWriteAll ARMS, as a pointer, nominated by
; whatever brought the medium up.
;
; It was @MscWriteBlock written inline, which was correct - writing is
; implemented for USB and not for the card - and it was correct by
; coincidence rather than by structure: the file that KNOWS which medium
; mounted is Board/storage.pi4, and it was not the file choosing. Now it
; is. storage.pi4 sets this on the mount path, and this file arms
; whatever it was handed.
;
; IT ALSO MAKES THE SEAM TESTABLE, which is not a side benefit worth
; hiding. RaspberryPi4/Examples/Diagnostics/pi4SettingsSelfTest.pi4 drives
; the settings store against a FABRICATED volume with its own block
; reader and writer, and proves the safety property that no sector is
; touched when writing is not available. With the writer hardcoded to one
; driver's procedure, that gate could only have tested a double of this
; file rather than this file.
;
; 0 means no writer: HwFileWriteAll refuses through the gate above it
; before it ever gets here, and fat.pi4 would refuse anyway with
; #FAT_ERR_NO_WRITER if it somehow did not.
Global gHwFileWriter.i

Procedure.i HwFileLastError()
  ProcedureReturn gHwFileErr
EndProcedure

; ----------------------------------------------------------------------
;  hwfile_MapFat - fat.pi4's code translated into the portable
;  vocabulary. The board backend is the ONLY place that knows both, which
;  is the whole discipline hal.pi4 sets out for #HW_I2C_* and #HW_USB_*.
;
;  ANYTHING NOT NAMED HERE BECOMES #HW_FILE_IO, and that is honest rather
;  than lossy: the filesystem's own whole sentence still reaches the
;  caller, so the specific finding is never lost - only its numeric code
;  is generalised, and the core has no use for a number it cannot
;  interpret.
;
;  THE TWO DRIVERS NUMBER THEIR ERRORS INDEPENDENTLY, so the facade is
;  asked what KIND of failure it was rather than compared against both
;  numberings at once. That comparison was here until 2026-09-16 and it was
;  wrong: FAT's 29 ("that name is a directory") is exFAT's 29 ("no writer"),
;  so `load` of a FAT directory answered that nothing writable was mounted.
;
;  THE SENTENCE HAS TO BE TAKEN NOW, NOT LATER. This is called the instant
;  an operation fails - and the very next thing that happens on that path
;  is hwfile_SettleAfterFailure(), which flushes the volume to leave the
;  medium consistent. FsFlush() begins by clearing the filesystem's error,
;  and a flush that then succeeds sets it to OK. So by the time anybody
;  asked HwFileErrorText() for words, the layer that had refused was
;  reporting no error at all, and the console printed
;
;      !! mkdir did not complete.
;         The medium said: nothing went wrong
;
;  under a refusal that really had a reason. The code survived (it is
;  saved and put back around the settling flush); only the reason was
;  thrown away, which is the half a reader needs. Measured on build 174,
;  2026-09-17: gHwFileErr read 3 - #HW_FILE_IO, so the error WAS there
;  when it was mapped - while the sentence read "nothing went wrong".
;
;  IT IS ONLY EVER CALLED ON A FAILURE, so "no error" is also not an answer
;  it can pass on: a layer that returns 0 and names nothing has refused
;  without saying why, and that is a defect in the refusing layer rather
;  than an outcome. It gets a code of its own so it cannot be printed as
;  success.
; ----------------------------------------------------------------------
Procedure.i hwfile_MapFat()
  ; The pointer is to a literal, so keeping it costs nothing and cannot go
  ; stale the way the layer's error word does.
  gHwFileFsText = FsErrorText()
  If FsLastError() = 0
    gHwFileFsText = 0
    ProcedureReturn #HW_FILE_UNNAMED
  EndIf
  If FsErrorIsNotFound() <> 0
    ProcedureReturn #HW_FILE_NOTFOUND
  EndIf
  If FsErrorIsNoWriter() <> 0
    ProcedureReturn #HW_FILE_READONLY
  EndIf
  ProcedureReturn #HW_FILE_IO
EndProcedure

; ----------------------------------------------------------------------
;  HwFileOpen(*name) - open a file on the mounted medium for reading.
;
;  THE CALLER MUST HAVE BROUGHT THE MEDIUM UP with HwStorageUp() first.
;  See the note in the header for why that step is not folded in here. A
;  call with nothing mounted is not a silent zero: fat.pi4 answers
;  #FAT_ERR_NOT_MOUNTED, which maps to #HW_FILE_IO and carries fat.pi4's
;  own sentence out through HwFileErrorText.
; ----------------------------------------------------------------------
Procedure.i HwFileOpen(*name)
  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  gHwFileOpen = 0
  gHwFileReadCont = 0
  If *name = 0
    gHwFileErr = #HW_FILE_BADNAME
    ProcedureReturn 0
  EndIf
  If gHwFileMounted = 0
    gHwFileErr = #HW_FILE_NOMEDIUM
    ProcedureReturn 0
  EndIf
  If FsOpen(*name) = 0
    gHwFileErr = hwfile_MapFat()
    ProcedureReturn 0
  EndIf
  gHwFileOpen = 1
  gHwFileReadCont = 1
  ProcedureReturn 1
EndProcedure

Procedure.i HwFileSize()
  If gHwFileOpen = 0
    gHwFileErr = #HW_FILE_NOTOPEN
    ProcedureReturn 0
  EndIf
  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  ProcedureReturn FsSize()
EndProcedure

; ----------------------------------------------------------------------
;  HwFileReadAt(off, dst, n) - n bytes from byte offset `off`.
;
;  FatSeek unless the preceding successful operation left the FAT cursor at
;  exactly `off`, then FatRead. The seam still promises an OFFSET and not a
;  stream position: a repeated or random offset takes the seek path. The
;  narrow continuation case matters for a large sequential PMF load because
;  FatSeek rebuilds its cursor from the first cluster, making one seek per
;  fixed-size chunk a quadratic chain walk.
;
;  FatTell() equality is necessary but not sufficient. FatRead can copy data,
;  advance fat_pos to a cluster boundary, and then fail to resolve the next
;  cluster. The continuation bit is therefore cleared before either FatSeek
;  or FatRead and restored only after a nonnegative FatRead result.
; ----------------------------------------------------------------------
Procedure.i HwFileReadAt(off.i, dst.i, n.i)
  Define got.i
  Define canContinue.i
  If gHwFileOpen = 0
    gHwFileReadCont = 0
    gHwFileErr = #HW_FILE_NOTOPEN
    ProcedureReturn -1
  EndIf
  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  If n <= 0
    ProcedureReturn 0
  EndIf

  canContinue = 0
  If gHwFileReadCont <> 0
    If FsTell() = off
      canContinue = 1
    EndIf
  EndIf
  gHwFileReadCont = 0

  If canContinue = 0
    If FsSeek(off) = 0
      gHwFileErr = hwfile_MapFat()
      ProcedureReturn -1
    EndIf
  EndIf
  got = FsRead(dst, n)
  If got < 0
    gHwFileErr = hwfile_MapFat()
    ProcedureReturn -1
  EndIf
  gHwFileReadCont = 1
  ProcedureReturn got
EndProcedure

Procedure HwFileClose()
  gHwFileReadCont = 0
  If gHwFileOpen <> 0
    FsClose()
    gHwFileOpen = 0
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  HwFileWritable() - THE WRITE GATE.
;
;  On this board writing is implemented for the USB medium and not for the
;  SD card, and it has been that way since `save` was written. That fact
;  used to be tested by `If gMedium <> 1` at each of the two call sites
;  that write; it is tested here now, once, and both callers ask the seam
;  instead of asking the board directly.
;
;  IT DOES NOT BRING THE MEDIUM UP. A gate that enumerated USB to answer
;  a yes/no question would make "can I write" as slow and as loud as
;  writing, and the callers all bring the medium up anyway on the path
;  where the answer was yes. With nothing mounted this answers "not yet",
;  which is the truthful answer to the question actually asked.
; ----------------------------------------------------------------------
Procedure.i HwFileWritable()
  ProcedureReturn gHwFileWritable
EndProcedure

; ----------------------------------------------------------------------
;  HwFileWriteAll(*name, src, n) - replace a whole file, creating it if
;  it is not there and resizing it to match.
;
;  THIS IS THE ONE PLACE ON THIS BOARD THAT ARMS THE BLOCK WRITER, and
;  that is a tightening of an existing rule rather than a new one.
;  settings_cmd.pi4 and fs_cmd.pi4 each used to do
;
;      FatSetBlockWriter(@MscWriteBlock)  ...  FatSetBlockWriter(0)
;
;  around their own write, with a disarm on every path out, because
;  leaving it installed would mean any later bug anywhere in the monitor
;  could reach the boot medium. Two call sites each remembering to disarm
;  on four exits is eight chances to forget. One call site with three
;  exits is three, and they are all on this screen.
;
;  THE ORDERING IS fat.pi4's AND IT IS NOT ARBITRARY: create only when the
;  failure was specifically "not there", never on a read error or a
;  looping directory, because creating a file on top of a damaged volume
;  is how a filesystem gets wrecked by a program trying to be helpful.
;  FatCreate leaves the new file OPEN, so there is no second FatOpen after
;  it and there must not be one.
; ----------------------------------------------------------------------
; ----------------------------------------------------------------------
;  hwfile_Stamp - hand the filesystem the time the change about to be made
;  carries (forum 911). The wall clock gives it only when it holds a
;  TRUSTED time - set by hand or by SNTP - and then as LOCAL time with the
;  zone's offset from UTC, which both formats expect. Otherwise the entry
;  gets the formats' first instant, 1980-01-01 00:00:00, and on exFAT a zone
;  field marked not valid: a time restored from the medium at boot is a
;  lower bound, not a time (Anvil/Core/wallclock.pbi, THE FLOOR).
; ----------------------------------------------------------------------
Procedure hwfile_Stamp()
  Define date.i
  Define time.i
  Define hundredths.i
  Define now.i
  If WallClockTrusted() = 0
    FsSetTimestamp($0021, 0, 0, 0, 0)
    ProcedureReturn
  EndIf
  now = WallClockNow()
  date = WallClockFatDate()
  time = WallClockFatTime()
  If date = 0 Or now < 0
    FsSetTimestamp($0021, 0, 0, 0, 0)
    ProcedureReturn
  EndIf
  ; WallClockFatTime just filled the broken-down fields, so the second is
  ; the one in `time`: the 10 ms field carries the odd second and the
  ; hundredths of this one.
  hundredths = (WallClockSecond() % 2) * 100 + (WallClockMicros() / 10000)
  FsSetTimestamp(date, time, hundredths, WallClockOffsetAt(now), 1)
EndProcedure

; A change that failed still puts the volume away: each driver keeps its
; dirty mark when a block read or write failed part way, and clears it when
; the refusal came before anything was written or was rolled back.
Procedure hwfile_SettleAfterFailure()
  Define keep.i
  keep = gHwFileErr
  FsFlush()
  gHwFileErr = keep
EndProcedure

Procedure.i HwFileWriteAll(*name, src.i, n.i)
  Define opened.i

  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  ; FatOpen/FatCreate below replace fat.pi4's single live file and FatClose
  ; releases it. No read continuation can survive this operation, including
  ; any refusal before the writer is armed.
  gHwFileReadCont = 0
  If *name = 0
    gHwFileErr = #HW_FILE_BADNAME
    ProcedureReturn 0
  EndIf
  If n < 0
    gHwFileErr = #HW_FILE_TOOBIG
    ProcedureReturn 0
  EndIf
  If gHwFileWritable = 0
    ; Either nothing is mounted, or what is mounted is the SD card and
    ; writing is implemented for USB only. Refused BEFORE anything is
    ; armed; the caller says so in its own words, and the seam's job here
    ; is to make sure no writer was ever installed.
    gHwFileErr = #HW_FILE_READONLY
    ProcedureReturn 0
  EndIf

  FsSetRangeWriter(gHwFileWriter)
  hwfile_Stamp()

  opened = FsOpen(*name)
  If opened = 0
    If FsErrorIsNotFound() = 0
      gHwFileErr = hwfile_MapFat()
      FsSetRangeWriter(0)                     ; DISARM - open failed
      ProcedureReturn 0
    EndIf
    If FsCreate(*name) = 0
      gHwFileErr = hwfile_MapFat()
      hwfile_SettleAfterFailure()
      FsSetRangeWriter(0)                     ; DISARM - create failed
      ProcedureReturn 0
    EndIf
    ; FatCreate leaves it open. No second FatOpen.
  EndIf

  If FsOverwrite(src, n) = 0
    gHwFileErr = hwfile_MapFat()
    FsClose()
    hwfile_SettleAfterFailure()
    FsSetRangeWriter(0)                       ; DISARM - write failed
    ProcedureReturn 0
  EndIf

  FsClose()
  If FsFlush() = 0
    gHwFileErr = hwfile_MapFat()
    FsSetRangeWriter(0)
    ProcedureReturn 0
  EndIf
  FsSetRangeWriter(0)                         ; DISARM - success
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  HwFileRemove / HwFileRename / HwDirCreate - the three directory-level
;  changes, each one exactly the shape of HwFileWriteAll: refused before
;  anything is armed when the medium is not writable, the block writer
;  armed around the one operation, the volume flushed (exFAT clears its
;  dirty mark there) and the writer disarmed on every path out.
;
;  THE PATHS CARRY THEIR PARTITION (2:/folder/name - see
;  Anvil/Storage/filesystem.pbi). A rename is refused across partitions.
;  FAT32 and exFAT take the same folder paths and long names. Each refusal
;  is the facade's or the driver's own sentence.
; ----------------------------------------------------------------------
Procedure.i hwfile_ArmForChange(*path)
  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  gHwFileReadCont = 0
  If *path = 0
    gHwFileErr = #HW_FILE_BADNAME
    ProcedureReturn 0
  EndIf
  If gHwFileWritable = 0
    gHwFileErr = #HW_FILE_READONLY
    ProcedureReturn 0
  EndIf
  If gHwFileOpen <> 0
    FsClose()
    gHwFileOpen = 0
  EndIf
  FsSetRangeWriter(gHwFileWriter)
  hwfile_Stamp()
  ProcedureReturn 1
EndProcedure

Procedure.i hwfile_FinishChange(done.i)
  If done = 0
    gHwFileErr = hwfile_MapFat()
    hwfile_SettleAfterFailure()
    FsSetRangeWriter(0)                       ; DISARM - the change failed
    ProcedureReturn 0
  EndIf
  If FsFlush() = 0
    gHwFileErr = hwfile_MapFat()
    FsSetRangeWriter(0)                       ; DISARM - the flush failed
    ProcedureReturn 0
  EndIf
  FsSetRangeWriter(0)                         ; DISARM - success
  ProcedureReturn 1
EndProcedure

Procedure.i HwFileRemove(*path)
  If hwfile_ArmForChange(*path) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn hwfile_FinishChange(FsRemove(*path))
EndProcedure

Procedure.i HwFileRename(*oldPath, *newPath)
  If *newPath = 0
    gHwFileErr = #HW_FILE_BADNAME
    ProcedureReturn 0
  EndIf
  If hwfile_ArmForChange(*oldPath) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn hwfile_FinishChange(FsRename(*oldPath, *newPath))
EndProcedure

Procedure.i HwDirCreate(*path)
  If hwfile_ArmForChange(*path) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn hwfile_FinishChange(FsMkdir(*path))
EndProcedure

; Remove an EMPTY folder, and refuse a file: `rmdir` cannot take a file by
; mistake the way `rm` of a mistyped folder name could.
Procedure.i HwDirRemove(*path)
  If hwfile_ArmForChange(*path) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn hwfile_FinishChange(FsRmdir(*path))
EndProcedure

; ----------------------------------------------------------------------
;  HwFileErrorText() - the last failure as a whole English sentence, as a
;  POINTER for UartWriteStr.
;
;  WHERE THE SENTENCE COMES FROM. For the codes this seam decided itself
;  (no medium, no file open, a bad name) it is written here. For anything
;  that came out of fat.pi4 it is FatErrorText() - the filesystem's own
;  words, which name what was actually found on the volume and are far
;  more use than a generalisation of them. That is why hwfile_MapFat is
;  allowed to be lossy about the CODE: the TEXT is not.
;
;  It returns a pointer, and the trap that costs a board run if it is
;  forgotten is documented at the foot of Anvil/Hal/hal.pbi: print it with
;  UartWriteStr, never with Print or PrintN, which pick their formatter
;  from the argument type and would print the address in decimal.
; ----------------------------------------------------------------------
Procedure.i HwFileErrorText()
  If gHwFileErr = #HW_FILE_OK
    ProcedureReturn "nothing went wrong"
  EndIf
  If gHwFileErr = #HW_FILE_NOMEDIUM
    ProcedureReturn "no storage medium came up at all, so there is nowhere for a file of any name to be"
  EndIf
  If gHwFileErr = #HW_FILE_NOTOPEN
    ProcedureReturn "no file was open when one was read from, which is a fault in this monitor and not in the medium"
  EndIf
  If gHwFileErr = #HW_FILE_BADNAME
    ProcedureReturn "that name is not one this medium can express - a path is at most 1023 UTF-8 bytes of folder and file names, each at most 255 characters"
  EndIf
  If gHwFileErr = #HW_FILE_READONLY
    ProcedureReturn "no writable storage medium is mounted or this board has not enabled its writer for this operation"
  EndIf
  If gHwFileErr = #HW_FILE_UNNAMED
    ProcedureReturn "file error 9: the filesystem refused and named no reason, which is a defect in this monitor and not an answer from the medium. Nothing was reported as wrong because nothing was recorded; check the last storage command's own error and sense with usb storage, and treat the medium as untouched by this operation."
  EndIf
  ; Everything else came out of the filesystem, which has better words for
  ; it than a generalisation would - and they are the words IT HAD WHEN IT
  ; REFUSED, captured by hwfile_MapFat, not whatever it would say now. See
  ; the header there: the settling flush on the failure path resets the
  ; layer's error, so asking it again answers about the flush.
  If gHwFileFsText <> 0
    ProcedureReturn gHwFileFsText
  EndIf
  ProcedureReturn FsErrorText()
EndProcedure

; ======================================================================
;  THE DIRECTORY ITERATOR, and the medium's own status report.
;
;  These are the two parts of the storage seam that could not be answered
;  by "open a file by name". A directory walk needs the filesystem, and
;  the status line needs to know what the medium physically IS - both are
;  board knowledge by nature, which is why the core asks rather than
;  reads.
;
;  THEY ARE AT THE BOTTOM OF THIS FILE AND NOT IN A SEPARATE ONE because
;  they have exactly the same dependencies as everything above: fat.pi4
;  and nothing later. HwStorageReport does print two numbers that come
;  from the medium drivers (MscBlockCount / SdBlockCount) and one flag
;  from storage.pi4 (gMedium), so it is the single procedure here that
;  cannot be included this early - and it therefore lives at the bottom of
;  Board/storage.pi4 beside HwStorageUp, which is exactly where its facts
;  are known.
; ======================================================================

; HwFileCanList() - can this board enumerate a directory at all?
;
; 1 here, unconditionally, and it is a compile-time truth rather than a
; runtime one: this board reads its filesystem itself, so if a volume
; mounts at all its root directory can be walked. HwDirRewind still
; reports a failure honestly if the walk cannot start.
Procedure.i HwFileCanList()
  ProcedureReturn 1
EndProcedure

Procedure.i HwDirOpen(*path)
  If gHwFileMounted = 0
    gHwFileErr = #HW_FILE_NOMEDIUM
    ProcedureReturn 0
  EndIf
  If FsDirOpen(*path) = 0
    gHwFileErr = hwfile_MapFat()
    ProcedureReturn 0
  EndIf
  gHwFileErr = #HW_FILE_OK
  gHwFileFsText = 0
  ProcedureReturn 1
EndProcedure

Procedure.i HwDirRewind()
  ProcedureReturn HwDirOpen(0)
EndProcedure

; 1 an entry was read, 0 the end of the directory, -1 the walk broke.
; The three-way answer is fat.pi4's and the core renders all three.
Procedure.i HwDirNext()
  Define r.i
  r = FsDirNext()
  If r = -1
    gHwFileErr = hwfile_MapFat()
  EndIf
  ProcedureReturn r
EndProcedure

; The 11 raw 8.3 name bytes of the current entry into *d. The core formats
; them; the shape of a name on the medium is the medium's business.
Procedure HwDirName(*d)
  ; Compatibility ABI: an exFAT long name cannot fit in this legacy 11-byte
  ; slot, so callers which need names use HwDirNameUtf8 below.
  If FsType() = #FS_FAT
    FatDirName(*d)
  Else
    exfat_Zero(*d, 11)
  EndIf
EndProcedure

Procedure.i HwDirNameUtf8(*d, capacity.i)
  ProcedureReturn FsDirNameUtf8(*d, capacity)
EndProcedure

Procedure.i HwDirIsDir()
  ProcedureReturn FsDirIsDir()
EndProcedure

Procedure.i HwDirSize()
  ProcedureReturn FsDirSize()
EndProcedure
