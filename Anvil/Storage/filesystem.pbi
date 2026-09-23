; Filesystem dispatch for block-backed Anvil boards. FAT32 and exFAT remain
; independent format owners; this is the only layer allowed to select one.
;
; ======================================================================
;  VOLUMES AND THE PATH FORM
; ======================================================================
;  A medium can carry up to four MBR partitions, and each FAT32 or exFAT
;  one is a volume a path can reach. A path names its partition with a
;  one-digit prefix and a colon:
;
;      2:/exfat test/random-1MiB.bin      partition 2
;      2:hello.txt                        the same as 2:/hello.txt
;      KERNEL8.IMG                        no prefix: partition 1
;
;  The digit is the MBR slot, 1 to 4, counted the way U-Boot's "usb 0:N"
;  counts it; on a GPT disk it is the Nth Microsoft Basic Data entry, which
;  the exFAT driver resolves. A path with no prefix ALWAYS means partition
;  1 - the boot partition - and never "whichever was used last". A stateful
;  default would let `ls 2:/` quietly redirect a later `save KERNEL8.IMG`
;  onto a data partition; a stateless one cannot. The colon cannot appear
;  in a FAT or exFAT name, so the prefix never collides with a real file.
;
;  ONE VOLUME IS MOUNTED AT A TIME, because each driver keeps one volume's
;  state. A path on another partition unmounts the current one cleanly and
;  mounts its own before the operation; a file left open refuses the switch
;  rather than having its volume taken away underneath it. Mounting reads
;  and never writes, so switching costs a few block reads and nothing else.
;
;  BOTH FORMATS TAKE THE SAME PATHS. Since 2026-09-17 a FAT32 volume has
;  folders at any depth, long names, mkdir, rmdir and rename exactly as an
;  exFAT volume does (forum 898); until then it was root-only and 8.3-only
;  and this layer refused the rest with volume errors 3 and 4. Those two
;  numbers stay defined, and their sentences stay, so a caller written
;  against the old refusal still reads a meaningful text - nothing raises
;  them any more.
;
;  TIMESTAMPS come from the caller through FsSetTimestamp, once per change;
;  this layer and both drivers have no clock of their own (forum 911).
; ======================================================================
#FS_NONE = 0
#FS_FAT = 1
#FS_EXFAT = 2
#FS_FACADE = 3                  ; error kind only: this layer refused

#FS_MAX_PARTITION = 4
#FS_DEFAULT_PARTITION = 1

; Errors this layer raises itself. Reported through FsLastError() only
; when FsErrorKind() says #FS_FACADE, so they never collide with a
; driver's numbering.
#FS_E_PARTITION = 1             ; N: names a partition outside 1..4
#FS_E_CROSS_VOLUME = 2          ; rename between two partitions
#FS_E_FAT_SUBDIR = 3            ; RETIRED 2026-09-17: FAT has folders now
#FS_E_FAT_UNSUPPORTED = 4       ; RETIRED 2026-09-17: FAT has mkdir/rename now
#FS_E_BUSY = 5                  ; a file is open on the mounted volume
#FS_E_NO_READER = 6             ; no block reader installed
#FS_E_ALLOCATION_UNSUPPORTED = 8 ; allocation ownership walk requires FAT32
#FS_E_TABLE_READ = 7            ; sector 0 would not read

Global fs_kind.i
Global fs_error.i
Global fs_errorKind.i
Global fs_partition.i           ; the partition fs_kind describes, 0 none
Global fs_pathPartition.i       ; set by fs_SplitPath
Global fs_rest.i                ; the path after its prefix and separators
Global *fs_reader
Global *fs_writer
Global *fs_flusher

; THE BLOCK-RANGE SEAM. Reader(lba, count, *buf) and Writer(lba, count,
; *buf) move count 512-byte blocks per call, at any buffer address, and
; answer 1 or 0. Until 2026-09-17 they moved one block per call, and that
; shape set the speed of both filesystems (forum 895). The setters were
; renamed with the contract: an indirect call's arity is not checked, so a
; one-block procedure left installed under the old name would have been
; called with its buffer where its count belongs.
Procedure FsSetRangeReader(address.i)
  *fs_reader = address
  FatSetRangeReader(address)
  ExFatSetRangeReader(address)
EndProcedure

Procedure FsSetRangeWriter(address.i)
  *fs_writer = address
  FatSetRangeWriter(address)
  ExFatSetRangeWriter(address)
EndProcedure

Procedure FsSetBlockFlusher(address.i)
  *fs_flusher = address
  FatSetBlockFlusher(address)
  ExFatSetBlockFlusher(address)
EndProcedure

; ----------------------------------------------------------------------
;  FsSetTimestamp - the time every entry created or changed from now on
;  carries, on both formats.
;
;    date, time   the packed FAT words: date = ((year - 1980) << 9) |
;                 (month << 5) | day, time = (hour << 11) | (minute << 5)
;                 | (second / 2), in LOCAL time
;    hundredths   0..199: the 10-millisecond part, odd second included
;    utcOffset    seconds east of UTC that local time is at
;    valid        1 when the time really is known. 0 stores the format's
;                 first instant, 1980-01-01 00:00:00, and on exFAT marks
;                 the zone field not valid
;
;  WHICH FIELDS: FAT32 - DIR_CrtDate/Time/TimeTenth and the LstAccDate on
;  creation, DIR_WrtDate/Time and LstAccDate on every write. exFAT - the
;  Create, LastModified and LastAccessed timestamps, their 10 ms fields and
;  UtcOffset fields on creation; LastModified and LastAccessed on every
;  write. A rename keeps the times the entry had.
; ----------------------------------------------------------------------
Procedure FsSetTimestamp(date.i, time.i, hundredths.i, utcOffset.i, valid.i)
  Define quarter.i
  If valid = 0 Or FatSetTimestamp(date, time) = 0
    FatSetTimestamp($0021, 0)
    FatSetTimestampHundredths(0)
    ExFatSetTimestamp($0021, 0, 0, 0)
    ProcedureReturn
  EndIf
  If FatSetTimestampHundredths(hundredths) = 0
    FatSetTimestampHundredths(0)
    hundredths = 0
  EndIf
  ; exFAT 7.4.10: bit 7 OffsetValid, bits 6-0 a signed count of 15-minute
  ; steps, -48 to +56.
  quarter = utcOffset / 900
  If quarter < -48 Or quarter > 56
    ExFatSetTimestamp(date, time, hundredths, 0)
  Else
    ExFatSetTimestamp(date, time, hundredths, $80 | (quarter & $7F))
  EndIf
EndProcedure

Procedure.i fs_Fail(code.i)
  fs_error = code
  fs_errorKind = #FS_FACADE
  ProcedureReturn 0
EndProcedure

; Every public operation starts here, so a failure is always reported by
; whichever layer produced THIS failure and never by a stale earlier one.
Procedure fs_Begin()
  fs_error = 0
  fs_errorKind = #FS_NONE
EndProcedure

Procedure.i FsMount(partition.i)
  fs_Begin()
  fs_kind = #FS_NONE
  fs_partition = 0
  If ExFatMount(partition) <> 0
    fs_kind = #FS_EXFAT
    fs_partition = partition
    ProcedureReturn 1
  EndIf
  ; Only a positive "not exFAT" classification may fall through. Corrupt
  ; exFAT metadata is never reinterpreted as another filesystem.
  If ExFatLastError() <> #EXFAT_E_NOT_EXFAT And ExFatLastError() <> #EXFAT_E_NO_MBR
    fs_errorKind = #FS_EXFAT
    ProcedureReturn 0
  EndIf
  If FatMount(partition) <> 0
    fs_kind = #FS_FAT
    fs_partition = partition
    ProcedureReturn 1
  EndIf
  fs_errorKind = #FS_FAT
  ProcedureReturn 0
EndProcedure

Procedure.i FsIsOpen()
  If fs_kind = #FS_EXFAT
    ProcedureReturn exfat_open
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatIsOpen()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsUnmount()
  fs_Begin()
  If fs_kind = #FS_EXFAT
    If ExFatUnmount() = 0
      fs_errorKind = #FS_EXFAT
      ProcedureReturn 0
    EndIf
  ElseIf fs_kind = #FS_FAT
    FatClose()
    If FatFlush() = 0
      fs_errorKind = #FS_FAT
    EndIf
  EndIf
  fs_kind = #FS_NONE
  fs_partition = 0
  ProcedureReturn 1
EndProcedure

; Make `partition` the mounted volume. 1, or 0 with the reason recorded.
;
; A VOLUME THAT WILL NOT UNMOUNT CLEANLY IS STILL LEFT. ExFatUnmount fails
; only when a failed write left the volume marked dirty and it cannot be
; flushed - the writer is disarmed by then. The dirty mark is already on
; the medium, which is the truthful state: the next mount of that volume
; sees it and refuses to change anything. Refusing the switch instead
; would strand every other partition behind one failed write.
Procedure.i FsSelectPartition(partition.i)
  If partition < 1 Or partition > #FS_MAX_PARTITION
    ProcedureReturn fs_Fail(#FS_E_PARTITION)
  EndIf
  If fs_kind <> #FS_NONE And fs_partition = partition
    fs_Begin()
    ProcedureReturn 1
  EndIf
  If FsIsOpen() <> 0
    ProcedureReturn fs_Fail(#FS_E_BUSY)
  EndIf
  If *fs_reader = 0
    ProcedureReturn fs_Fail(#FS_E_NO_READER)
  EndIf
  If fs_kind <> #FS_NONE
    FsUnmount()
    fs_kind = #FS_NONE
    fs_partition = 0
  EndIf
  ProcedureReturn FsMount(partition)
EndProcedure

; Split a path into its partition and the rest. Sets fs_pathPartition and
; fs_rest. A null path is the default partition's root. 0 for a prefix
; naming a partition that cannot exist.
Procedure.i fs_SplitPath(*path)
  Define c.i
  fs_pathPartition = #FS_DEFAULT_PARTITION
  fs_rest = *path
  If *path = 0
    ProcedureReturn 1
  EndIf
  c = PeekA(*path)
  If c >= 48 And c <= 57 And PeekA(*path + 1) = 58
    If c < 49 Or c > 48 + #FS_MAX_PARTITION
      ProcedureReturn fs_Fail(#FS_E_PARTITION)
    EndIf
    fs_pathPartition = c - 48
    fs_rest = *path + 2
  EndIf
  While PeekA(fs_rest) = 47 Or PeekA(fs_rest) = 92
    fs_rest = fs_rest + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Split and mount. On success fs_rest is the in-volume path.
Procedure.i fs_Volume(*path)
  fs_Begin()
  If fs_SplitPath(*path) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn FsSelectPartition(fs_pathPartition)
EndProcedure


Procedure.i FsOpen(*path)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatOpen(fs_rest)
  EndIf
  ProcedureReturn FatOpen(fs_rest)
EndProcedure

Procedure.i FsCreate(*path)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatCreate(fs_rest)
  EndIf
  ProcedureReturn FatCreate(fs_rest)
EndProcedure

Procedure.i FsRead(*dst, count.i)
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRead(*dst, count)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatRead(*dst, count)
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsWrite(*src, count.i)
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatWrite(*src, count)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatWrite(*src, count)
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsSeek(position.i)
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatSeek(position)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatSeek(position)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsTruncate(length.i)
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatTruncate(length)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatTruncate(length)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsOverwrite(*src, length.i)
  If FsTruncate(0) = 0
    ProcedureReturn 0
  EndIf
  If FsSeek(0) = 0
    ProcedureReturn 0
  EndIf
  If length = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn FsWrite(*src, length) = length
EndProcedure

; Replace the contents of an existing, contiguous FAT32 file without leaving
; a file cursor open and without touching its FAT or directory entry. This is the
; only overwrite primitive suitable for boot control records: the caller
; supplies an exact 512-byte record (or another sector-aligned size), and the
; installed range writer receives precisely the file's extent. exFAT remains
; refused until it has the same fixed extent proof.
Procedure.i FsOverwriteFixed(*path, *src, length.i)
  Protected first.i
  Protected blocks.i
  Protected bytes.i
  Protected ok.i
  If *path = 0 Or *src = 0 Or length < 1 Or (length & 511) <> 0
    ProcedureReturn fs_Fail(#FS_E_ALLOCATION_UNSUPPORTED)
  EndIf
  If FsExtentOf(*path, @first, @blocks, @bytes) = 0
    ProcedureReturn 0
  EndIf
  ; FsExtentOf selects the filesystem named by the explicit path. Check the
  ; resulting kind after that selection so a prior FAT mount cannot authorize
  ; an exFAT path.
  If fs_kind <> #FS_FAT Or *fs_writer = 0
    ProcedureReturn fs_Fail(#FS_E_ALLOCATION_UNSUPPORTED)
  EndIf
  If bytes <> length Or blocks < (length / 512) Or blocks < 1
    ProcedureReturn fs_Fail(#FS_E_ALLOCATION_UNSUPPORTED)
  EndIf
  ; Only the logical file bytes are written. The final allocated cluster may
  ; be larger than the directory size and is deliberately left untouched.
  ok = fs_writer(first, length / 512, *src)
  ProcedureReturn Bool(ok = 1)
EndProcedure

Procedure FsClose()
  If fs_kind = #FS_EXFAT
    ExFatClose()
  ElseIf fs_kind = #FS_FAT
    FatClose()
  EndIf
EndProcedure

Procedure.i FsSize()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatSize()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatSize()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsTell()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatTell()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatTell()
  EndIf
  ProcedureReturn 0
EndProcedure

; Which layer owns the last failure: #FS_FACADE, #FS_EXFAT or #FS_FAT.
Procedure.i FsErrorKind()
  If fs_errorKind <> #FS_NONE
    ProcedureReturn fs_errorKind
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn #FS_EXFAT
  EndIf
  ProcedureReturn #FS_FAT
EndProcedure

; The numeric code, meaningful only together with FsErrorKind(). The two
; drivers number independently - FAT's 29 is "a directory" where exFAT's 29
; is "no writer" - so a caller asks the predicates below, never a number.
Procedure.i FsLastError()
  Define k.i
  k = FsErrorKind()
  If k = #FS_FACADE
    ProcedureReturn fs_error
  EndIf
  If k = #FS_EXFAT
    ProcedureReturn ExFatLastError()
  EndIf
  ProcedureReturn FatLastError()
EndProcedure

Procedure.i FsErrorIsNotFound()
  Define k.i
  k = FsErrorKind()
  If k = #FS_EXFAT
    ProcedureReturn Bool(ExFatLastError() = #EXFAT_E_NOT_FOUND)
  EndIf
  If k = #FS_FAT
    ProcedureReturn Bool(FatLastError() = #FAT_ERR_NOTFOUND)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsErrorIsNoWriter()
  Define k.i
  k = FsErrorKind()
  If k = #FS_EXFAT
    ProcedureReturn Bool(ExFatLastError() = #EXFAT_E_NO_WRITER)
  EndIf
  If k = #FS_FAT
    ProcedureReturn Bool(FatLastError() = #FAT_ERR_NO_WRITER)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsErrorText()
  Define k.i
  k = FsErrorKind()
  If k = #FS_FACADE
    Select fs_error
      Case #FS_E_PARTITION : ProcedureReturn "volume error 1: a path may name partition 1, 2, 3 or 4 only, as 2:/name; check the digit before the colon"
      Case #FS_E_CROSS_VOLUME : ProcedureReturn "volume error 2: a rename cannot move an entry to another partition; give both paths the same N: prefix, and remember a path with no prefix means partition 1"
      Case #FS_E_FAT_SUBDIR : ProcedureReturn "volume error 3: retired - FAT partitions have folders since 2026-09-17; if this appears, the monitor is older than its documentation"
      Case #FS_E_FAT_UNSUPPORTED : ProcedureReturn "volume error 4: retired - FAT partitions have mkdir and rename since 2026-09-17; if this appears, the monitor is older than its documentation"
      Case #FS_E_BUSY : ProcedureReturn "volume error 5: a file is still open on the mounted partition, so another partition was not mounted; close it first"
      Case #FS_E_NO_READER : ProcedureReturn "volume error 6: no block reader is installed, so no partition can be mounted; bring the storage medium up first"
      Case #FS_E_ALLOCATION_UNSUPPORTED : ProcedureReturn "volume error 8: bounded allocation ownership checks require a FAT32 volume; this format has no verified allocation walker"
      Case #FS_E_TABLE_READ : ProcedureReturn "volume error 7: sector 0, which holds the partition table, would not read; check that the medium is still connected"
    EndSelect
    ProcedureReturn "volume error: an unknown internal refusal; record the number and stop using the medium"
  EndIf
  If k = #FS_EXFAT
    ProcedureReturn ExFatErrorText()
  EndIf
  ProcedureReturn FatErrorText()
EndProcedure

Procedure.i FsDirOpen(*path)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirOpen(fs_rest)
  EndIf
  ProcedureReturn FatDirOpen(fs_rest)
EndProcedure

Procedure.i FsDirRewind()
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirRewind()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatDirRewind()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsDirNext()
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirNext()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatDirNext()
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsDirNameUtf8(*dst, capacity.i)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirNameUtf8(*dst, capacity)
  EndIf
  If fs_kind <> #FS_FAT
    ProcedureReturn -1
  EndIf
  ProcedureReturn FatDirNameUtf8(*dst, capacity)
EndProcedure

Procedure.i FsDirIsDir()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirIsDir()
  EndIf
  ProcedureReturn FatDirIsDir()
EndProcedure

Procedure.i FsDirSize()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirSize()
  EndIf
  ProcedureReturn FatDirSize()
EndProcedure

Procedure.i FsMkdir(*path)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatMkdir(fs_rest)
  EndIf
  ProcedureReturn FatMkdir(fs_rest)
EndProcedure

Procedure.i FsRemove(*path)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRemove(fs_rest)
  EndIf
  ProcedureReturn FatDelete(fs_rest)
EndProcedure

; Remove a FOLDER, and only a folder: a file of that name is refused with
; the driver's "not a directory" sentence and nothing is written. The folder
; must be empty; both drivers check that before anything changes.
Procedure.i FsRmdir(*path)
  If FsDirOpen(*path) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn FsRemove(*path)
EndProcedure

Procedure.i FsRename(*oldPath, *newPath)
  Define oldPartition.i
  Define oldRest.i
  fs_Begin()
  If fs_SplitPath(*newPath) = 0
    ProcedureReturn 0
  EndIf
  If fs_SplitPath(*oldPath) = 0
    ProcedureReturn 0
  EndIf
  oldPartition = fs_pathPartition
  oldRest = fs_rest
  fs_SplitPath(*newPath)
  If fs_pathPartition <> oldPartition
    ProcedureReturn fs_Fail(#FS_E_CROSS_VOLUME)
  EndIf
  If FsSelectPartition(oldPartition) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRename(oldRest, fs_rest)
  EndIf
  ProcedureReturn FatRename(oldRest, fs_rest)
EndProcedure

Procedure.i FsFlush()
  fs_Begin()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatFlush()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatFlush()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsType()
  ProcedureReturn fs_kind
EndProcedure

; The partition the mounted volume lives on, 0 when nothing is mounted.
Procedure.i FsPartition()
  ProcedureReturn fs_partition
EndProcedure

Procedure.i FsBytesPerCluster()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatBytesPerCluster()
  EndIf
  ProcedureReturn FatBytesPerCluster()
EndProcedure

; Where a file's data starts, how many 512-byte blocks it occupies, and how
; long it really is - but ONLY when that data is one unbroken run of clusters.
;
; This exists for callers that must hand a file to something which speaks in
; block ranges and cannot follow a chain: a boot loader copying a slot, a DMA
; engine, a verifier that hashes an extent. Working it out from outside means
; reaching into a driver's private cluster arithmetic and re-deciding what a
; directory entry means, which is how a second reader of this format ends up
; in a boot chain.
;
; It REFUSES rather than half-answering. Fragmented, missing, a directory or
; empty all return 0 with the reason in FsLastError(); the out parameters are
; not touched. A fragmented file is not a fault - most files are fragmented -
; it means only that this caller cannot be served from it.
;
; Read-only. Nothing here writes, and it leaves no file open behind it.
Procedure.i FsExtentOf(*path, *firstLba, *blocks, *bytes)
  If fs_Volume(*path) = 0
    ProcedureReturn 0
  EndIf
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatExtentOf(fs_rest, *firstLba, *blocks, *bytes)
  EndIf
  ProcedureReturn FatExtentOf(fs_rest, *firstLba, *blocks, *bytes)
EndProcedure

; Walk every allocated run in the mounted volume. The FAT32 owner supplies
; the bounded tree walk; exFAT remains deliberately unsupported here until a
; format-specific walker has the same corruption checks.
Procedure.i FsWalkAllocations(*entryVisitor, *rangeVisitor, context.i)
  fs_Begin()
  If fs_kind <> #FS_FAT
    ProcedureReturn fs_Fail(#FS_E_ALLOCATION_UNSUPPORTED)
  EndIf
  ProcedureReturn FatWalkAllocations(*entryVisitor, *rangeVisitor, context)
EndProcedure

Procedure.i FsWalkRoot(*rangeVisitor, context.i)
  fs_Begin()
  If fs_kind <> #FS_FAT : ProcedureReturn fs_Fail(#FS_E_ALLOCATION_UNSUPPORTED) : EndIf
  ProcedureReturn FatWalkRoot(*rangeVisitor, context)
EndProcedure

Procedure.i FsDataLba()
  If fs_kind = #FS_FAT : ProcedureReturn FatDataLba() : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsDataEnd()
  If fs_kind = #FS_FAT : ProcedureReturn FatDataEnd() : EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  THE PARTITION TABLE, as the storage report needs it.
;
;  FsTableRead() reads sector 0 once through the installed reader. The
;  slot accessors then answer from that copy: the MBR type byte, the start
;  and the length in 512-byte blocks. A GPT disk (a protective $EE entry)
;  or a volume written straight onto the medium with no table answers
;  FsTableIsMbr() = 0, and the report falls back to trying each ordinal.
; ----------------------------------------------------------------------
Global Dim fs_table.a[512]
Global fs_tableMbr.i

Procedure.i FsTableRead()
  Define i.i
  fs_Begin()
  fs_tableMbr = 0
  If *fs_reader = 0
    ProcedureReturn fs_Fail(#FS_E_NO_READER)
  EndIf
  If FsIsOpen() <> 0
    ProcedureReturn fs_Fail(#FS_E_BUSY)
  EndIf
  ; Straight through the reader, not through a driver: a driver bounds its
  ; reads to the partition it has mounted, and sector 0 is outside all of
  ; them.
  If fs_reader(0, 1, @fs_table[0]) = 0
    ProcedureReturn fs_Fail(#FS_E_TABLE_READ)
  EndIf
  If fs_table[510] <> $55 Or fs_table[511] <> $AA
    ProcedureReturn 1
  EndIf
  i = 0
  While i < 4
    If fs_table[$1BE + i * 16 + 4] = $EE
      ProcedureReturn 1
    EndIf
    If fs_table[$1BE + i * 16] <> 0 And fs_table[$1BE + i * 16] <> $80
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  fs_tableMbr = 1
  ProcedureReturn 1
EndProcedure

Procedure.i FsTableIsMbr()
  ProcedureReturn fs_tableMbr
EndProcedure

Procedure.i FsTableType(partition.i)
  If fs_tableMbr = 0 Or partition < 1 Or partition > 4
    ProcedureReturn -1
  EndIf
  ProcedureReturn fs_table[$1BE + (partition - 1) * 16 + 4]
EndProcedure

Procedure.i FsTableBlocks(partition.i)
  If fs_tableMbr = 0 Or partition < 1 Or partition > 4
    ProcedureReturn 0
  EndIf
  ProcedureReturn exfat_U32(@fs_table[0], $1BE + (partition - 1) * 16 + 12) & $FFFFFFFF
EndProcedure

Procedure.i FsTableStart(partition.i)
  If fs_tableMbr = 0 Or partition < 1 Or partition > 4
    ProcedureReturn 0
  EndIf
  ProcedureReturn exfat_U32(@fs_table[0], $1BE + (partition - 1) * 16 + 8) & $FFFFFFFF
EndProcedure
