; ============================================================================
; exfat.pbi - target-neutral native exFAT 1.x filesystem for Anvil
;
; This driver owns filesystem policy only.  A board supplies block-RANGE
; callbacks - (lba, count, *buf), 512-byte blocks - through
; ExFatSetRangeReader/Writer; no USB, SD, firmware or target register appears
; here.  All media
; arithmetic is checked before a callback is made.  The implementation follows
; Microsoft's published exFAT specification and deliberately refuses TexFAT,
; unknown critical entries, invalid checksums, invalid UTF-16, and geometries
; which cannot be represented by Anvil's signed native integer.  Dual-FAT
; volumes are accepted and the VolumeFlags ActiveFat bit selects the live FAT;
; VolumeDirty is tracked independently and is never mistaken for TexFAT.
;
; Public API mirrors the existing FAT driver where practical and adds paths,
; directories, rename, flush and unmount.  One file and one directory cursor
; may be live at once; callers needing concurrency serialize at the VFS seam.
; ============================================================================

#EXFAT_OK = 0
#EXFAT_E_NO_READER = 1
#EXFAT_E_READ = 2
#EXFAT_E_NO_MBR = 3
#EXFAT_E_PARTITION = 4
#EXFAT_E_NOT_EXFAT = 5
#EXFAT_E_BOOT = 6
#EXFAT_E_BOOT_CHECKSUM = 7
#EXFAT_E_REVISION = 8
#EXFAT_E_GEOMETRY = 9
#EXFAT_E_DIRTY = 10
#EXFAT_E_ROOT = 11
#EXFAT_E_BITMAP = 12
#EXFAT_E_UPCASE = 13
#EXFAT_E_UPCASE_CHECKSUM = 14
#EXFAT_E_NOT_MOUNTED = 15
#EXFAT_E_PATH = 16
#EXFAT_E_UTF8 = 17
#EXFAT_E_UTF16 = 18
#EXFAT_E_NOT_FOUND = 19
#EXFAT_E_NOT_DIR = 20
#EXFAT_E_IS_DIR = 21
#EXFAT_E_SET_CHECKSUM = 22
#EXFAT_E_NAME_HASH = 23
#EXFAT_E_CHAIN = 24
#EXFAT_E_BOUNDS = 25
#EXFAT_E_NO_FILE = 26
#EXFAT_E_NULL = 27
#EXFAT_E_LENGTH = 28
#EXFAT_E_NO_WRITER = 29
#EXFAT_E_WRITE = 30
#EXFAT_E_NO_SPACE = 31
#EXFAT_E_EXISTS = 32
#EXFAT_E_NOT_EMPTY = 33
#EXFAT_E_READ_ONLY = 34
#EXFAT_E_DIR_FULL = 35
#EXFAT_E_FLUSH = 36
#EXFAT_E_BUSY = 37
#EXFAT_E_CRITICAL = 38
#EXFAT_E_TEXFAT = 39
#EXFAT_E_BITMAP_CHECK = 40
#EXFAT_E_MEDIA_FAILURE = 41
#EXFAT_E_RESERVED_NAME = 42
; ExFatExtentOf was asked for a file whose data is not one unbroken run
; of clusters. Not a fault in the volume - it means only that a caller
; which needs a single extent cannot be served from this file.
#EXFAT_E_FRAGMENTED = 43

#EXFAT_ENTRY_BITMAP = $81
#EXFAT_ENTRY_UPCASE = $82
#EXFAT_ENTRY_LABEL = $83
#EXFAT_ENTRY_FILE = $85
#EXFAT_ENTRY_STREAM = $C0
#EXFAT_ENTRY_NAME = $C1
#EXFAT_ATTR_READ_ONLY = 1
#EXFAT_ATTR_DIRECTORY = $10
#EXFAT_ATTR_ARCHIVE = $20
#EXFAT_STREAM_ALLOC_POSSIBLE = 1
#EXFAT_STREAM_NO_FAT_CHAIN = 2
#EXFAT_EOC = $FFFFFFFF
#EXFAT_MAX_NAME = 255
#EXFAT_MAX_PATH = 1023
#EXFAT_MAX_SECTOR = 4096
#EXFAT_BLOCK_SIZE = 512

Global *exfat_reader
Global *exfat_writer
Global *exfat_flusher
Global exfat_error.i
Global exfat_lastLba.i = -1
Global exfat_mounted.i
Global exfat_dirty.i
Global exfat_inheritedDirty.i
Global exfat_partLba.i
Global exfat_partBlocks.i
Global exfat_volumeBlocks.i
Global exfat_bytesPerSector.i
Global exfat_blocksPerSector.i
Global exfat_sectorsPerCluster.i
Global exfat_blocksPerCluster.i
Global exfat_bytesPerCluster.i
Global exfat_fatOffset.i
Global exfat_fatLength.i
Global exfat_heapOffset.i
Global exfat_clusterCount.i
Global exfat_rootCluster.i
Global exfat_numFats.i
Global exfat_activeFat.i
Global exfat_texfat.i
Global exfat_mediaFailure.i
Global exfat_volumeFlags.i
Global exfat_percentInUse.i
Global exfat_bitmapCluster.i
Global exfat_bitmapLength.i
Global exfat_upcaseCluster.i
Global exfat_upcaseLength.i
Global exfat_upcaseChecksum.i
Global exfat_freeClusters.i = -1
Global exfat_allocHint.i = 2
Global Dim exfat_sector.a[#EXFAT_MAX_SECTOR]
Global Dim exfat_aux.a[#EXFAT_MAX_SECTOR]
; THE FAT'S OWN SECTOR. Only exfat_FatEntry and exfat_SetFatEntry touch it.
; They are called while a stream's clusters are resolved - in the middle of
; a directory read or write whose caller's 32-byte entry is often sitting in
; exfat_aux - so they must never borrow exfat_aux. Until 2026-09-16 they did,
; and every entry written past a directory's first cluster had the FAT
; sector's bytes copied over it before it reached the medium.
Global Dim exfat_fatSector.a[#EXFAT_MAX_SECTOR]
Global Dim exfat_entry.a[32]
Global Dim exfat_gptEntry.a[48]
Global Dim exfat_name.w[#EXFAT_MAX_NAME + 1]
Global Dim exfat_want.w[#EXFAT_MAX_NAME + 1]
Global exfat_wantLength.i
Global Dim exfat_upcaseFast.w[255]
Global exfat_upcaseFastReady.i

; Current open object.
Global exfat_open.i
Global exfat_fileFirst.i
Global exfat_fileLength.i
Global exfat_fileValid.i
Global exfat_filePos.i
Global exfat_fileFlags.i
Global exfat_fileAttr.i
Global exfat_fileParent.i
Global exfat_fileParentFlags.i
Global exfat_fileParentLength.i
Global exfat_fileSetIndex.i
Global exfat_fileSecondaries.i
Global exfat_fileNameLength.i

; Current directory iterator.
Global exfat_dirFirst.i
Global exfat_dirFlags.i
Global exfat_dirLength.i
Global exfat_dirIndex.i
Global exfat_dirEnd.i
Global exfat_dirLimit.i
Global exfat_dirCurrentAttr.i
Global exfat_dirCurrentLength.i
Global exfat_dirCurrentFirst.i
Global exfat_dirCurrentNameLength.i

; Timestamps supplied by the wall-clock owner.  exFAT uses the same packed
; calendar/time bit layout as FAT, with separate 10 ms and UTC-offset fields.
Global exfat_date.i = $0021
Global exfat_time.i
Global exfat_time10ms.i
; UtcOffset: bit 7 OffsetValid, bits 6-0 the offset in 15-minute steps
; (exFAT specification 7.4.10). 0 means "not valid", which is what a date
; nobody set must carry (forum 911).
Global exfat_utcOffset.i = 0
; A block read or write failed while the volume was marked dirty: the dirty
; mark then stays on the medium for a repair tool to see.
Global exfat_ioFailed.i

; ============================================================================
; THE THREE SECTOR CACHES, since 2026-09-17 (forum 893, 897).
;
; exfat_rcache - the last sector a byte-at-a-time metadata read touched. The
;   up-case table checksum at mount, entry-set scans and directory walks read
;   one byte or one 32-byte entry per call, and every call used to read its
;   whole sector off the medium again: a partition switch cost about two
;   seconds of USB reads. ANY write through this driver throws it away
;   (exfat_WriteBlocks), and so do a mount and a new reader.
;
; exfat_fatSector / exfat_fatTag / exfat_fatDirty - the FAT sector last read
;   or changed. exfat_bmpSector / exfat_bmpTag / exfat_bmpDirty - the same for
;   the allocation bitmap. A cluster allocation changed a FAT entry and a
;   bitmap bit and wrote each sector back AT ONCE, reading between writes -
;   and on the boot stick a read between two single-block writes costs about
;   4 ms per write. Changes now wait in these buffers and reach the medium in
;   exfat_FlushMeta, FAT first and bitmap second, before ANY other sector is
;   written: a metadata or partial sector (exfat_WriteSector), a run of file
;   data (exfat_StreamWriteFixed), and the volume's clean mark and the
;   device's own flush (ExFatFlush). A failed write drops them, and so does
;   disarming the writer: after a failure nobody knows what the medium holds,
;   and the volume's dirty mark stays for a repair tool.
; ============================================================================
Global Dim exfat_rcache.a[#EXFAT_MAX_SECTOR]
Global exfat_rcacheSector.i = -1
Global exfat_fatTag.i = -1
Global exfat_fatDirty.i
Global Dim exfat_bmpSector.a[#EXFAT_MAX_SECTOR]
Global exfat_bmpTag.i = -1
Global exfat_bmpDirty.i
Declare.i exfat_FlushMeta()

Procedure exfat_DropCaches()
  exfat_rcacheSector = -1
  exfat_fatTag = -1
  exfat_fatDirty = 0
  exfat_bmpTag = -1
  exfat_bmpDirty = 0
EndProcedure
; The allocation changed since mount, so PercentInUse must be refreshed.
Global exfat_allocChanged.i

Procedure.i exfat_Fail(code.i)
  exfat_error = code
  ProcedureReturn 0
EndProcedure

Procedure.i exfat_U16(*p, off.i)
  ProcedureReturn PeekA(*p + off) | (PeekA(*p + off + 1) << 8)
EndProcedure

Procedure.i exfat_U32(*p, off.i)
  ProcedureReturn PeekA(*p + off) | (PeekA(*p + off + 1) << 8) | (PeekA(*p + off + 2) << 16) | (PeekA(*p + off + 3) << 24)
EndProcedure

Procedure.i exfat_U64(*p, off.i)
  Define lo.i
  Define hi.i
  lo = exfat_U32(*p, off) & $FFFFFFFF
  hi = exfat_U32(*p, off + 4) & $FFFFFFFF
  If hi > $7FFFFFFF
    exfat_Fail(#EXFAT_E_BOUNDS)
    ProcedureReturn -1
  EndIf
  ProcedureReturn lo | (hi << 32)
EndProcedure

Procedure exfat_Put16(*p, off.i, value.i)
  PokeA(*p + off, value & $FF)
  PokeA(*p + off + 1, (value >> 8) & $FF)
EndProcedure

Procedure exfat_Put32(*p, off.i, value.i)
  PokeA(*p + off, value & $FF)
  PokeA(*p + off + 1, (value >> 8) & $FF)
  PokeA(*p + off + 2, (value >> 16) & $FF)
  PokeA(*p + off + 3, (value >> 24) & $FF)
EndProcedure

Procedure exfat_Put64(*p, off.i, value.i)
  exfat_Put32(*p, off, value)
  exfat_Put32(*p, off + 4, value >> 32)
EndProcedure

Procedure exfat_Copy(*dst, *src, count.i)
  Define i.i
  i = 0
  While i < count
    PokeA(*dst + i, PeekA(*src + i))
    i = i + 1
  Wend
EndProcedure

Procedure exfat_Zero(*dst, count.i)
  Define i.i
  i = 0
  While i < count
    PokeA(*dst + i, 0)
    i = i + 1
  Wend
EndProcedure

; THE RANGE SEAM: Reader(lba, count, *buf) / Writer(lba, count, *buf), count
; 512-byte blocks per call, 1 or 0. It was one block per call until
; 2026-09-17; the names changed with the contract so that a one-block
; procedure left installed anywhere is a compile error, not a call with its
; arguments shifted.
Procedure ExFatSetRangeReader(address.i)
  *exfat_reader = address
  exfat_DropCaches()
EndProcedure

Procedure ExFatSetRangeWriter(address.i)
  If address = 0
    ; Unwritten FAT and bitmap changes can only exist after a failure, and
    ; with no writer they could never reach the medium.
    exfat_fatDirty = 0
    exfat_bmpDirty = 0
    exfat_fatTag = -1
    exfat_bmpTag = -1
  EndIf
  *exfat_writer = address
EndProcedure

Procedure ExFatSetBlockFlusher(address.i)
  *exfat_flusher = address
EndProcedure

Procedure.i exfat_BlockInPartition(lba.i)
  If lba < exfat_partLba
    ProcedureReturn 0
  EndIf
  If lba >= exfat_partLba + exfat_partBlocks
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ReadBlocks(lba.i, count.i, *dst)
  If *exfat_reader = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_READER)
  EndIf
  If count < 1
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  If exfat_partBlocks <> 0
    If exfat_BlockInPartition(lba) = 0 Or exfat_BlockInPartition(lba + count - 1) = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
    EndIf
  EndIf
  exfat_lastLba = lba
  If exfat_reader(lba, count, *dst) = 0
    If exfat_dirty <> 0
      exfat_ioFailed = 1
    EndIf
    ProcedureReturn exfat_Fail(#EXFAT_E_READ)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ReadBlock(lba.i, *dst)
  ProcedureReturn exfat_ReadBlocks(lba, 1, *dst)
EndProcedure

Procedure.i exfat_WriteBlocks(lba.i, count.i, *src)
  If *exfat_writer = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_WRITER)
  EndIf
  If count < 1 Or exfat_BlockInPartition(lba) = 0 Or exfat_BlockInPartition(lba + count - 1) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  exfat_lastLba = lba
  ; The read cache cannot describe a sector once anything has been written.
  exfat_rcacheSector = -1
  If exfat_writer(lba, count, *src) = 0
    exfat_ioFailed = 1
    exfat_DropCaches()
    ProcedureReturn exfat_Fail(#EXFAT_E_WRITE)
  EndIf
  ProcedureReturn 1
EndProcedure

; `count` whole sectors in ONE call to the reader or writer.
Procedure.i exfat_ReadSectors(sector.i, count.i, *dst)
  If count < 1 Or sector < 0 Or sector + count > exfat_volumeBlocks / exfat_blocksPerSector
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  ProcedureReturn exfat_ReadBlocks(exfat_partLba + sector * exfat_blocksPerSector, count * exfat_blocksPerSector, *dst)
EndProcedure

Procedure.i exfat_WriteSectors(sector.i, count.i, *src)
  If count < 1 Or sector < 0 Or sector + count > exfat_volumeBlocks / exfat_blocksPerSector
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  ProcedureReturn exfat_WriteBlocks(exfat_partLba + sector * exfat_blocksPerSector, count * exfat_blocksPerSector, *src)
EndProcedure

Procedure.i exfat_ReadSector(sector.i, *dst)
  ProcedureReturn exfat_ReadSectors(sector, 1, *dst)
EndProcedure

; ONE SECTOR OF METADATA OR PARTIAL DATA. Waiting FAT and bitmap changes go
; out first, so no directory entry, boot sector or other structure reaches
; the medium ahead of the allocation it may depend on. Whole-sector file
; data does not come through here (exfat_StreamWriteFixed).
Procedure.i exfat_WriteSector(sector.i, *src)
  If exfat_FlushMeta() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn exfat_WriteSectors(sector, 1, *src)
EndProcedure

Procedure.i exfat_ClusterValid(cluster.i)
  If cluster < 2 Or cluster > exfat_clusterCount + 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ClusterSector(cluster.i, sectorInCluster.i)
  If exfat_ClusterValid(cluster) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  If sectorInCluster < 0 Or sectorInCluster >= exfat_sectorsPerCluster
    exfat_Fail(#EXFAT_E_BOUNDS)
    ProcedureReturn -1
  EndIf
  ProcedureReturn exfat_heapOffset + (cluster - 2) * exfat_sectorsPerCluster + sectorInCluster
EndProcedure

; Put a changed FAT sector on the medium. Only exfat_FlushMeta and a sector
; switch call this; a write failure drops the buffer.
Procedure.i exfat_FlushFat()
  If exfat_fatDirty = 0
    ProcedureReturn 1
  EndIf
  exfat_fatDirty = 0
  If exfat_WriteSectors(exfat_fatTag, 1, @exfat_fatSector[0]) = 0
    exfat_fatTag = -1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Make exfat_fatSector hold `sector`, writing back a changed one first.
Procedure.i exfat_FatLoad(sector.i)
  If exfat_fatTag = sector
    ProcedureReturn 1
  EndIf
  If exfat_FlushFat() = 0
    ProcedureReturn 0
  EndIf
  exfat_fatTag = -1
  If exfat_ReadSectors(sector, 1, @exfat_fatSector[0]) = 0
    ProcedureReturn 0
  EndIf
  exfat_fatTag = sector
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_FatEntry(cluster.i)
  Define byteOff.i
  Define sector.i
  Define off.i
  If exfat_ClusterValid(cluster) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  byteOff = cluster * 4
  sector = exfat_fatOffset + exfat_activeFat * exfat_fatLength + byteOff / exfat_bytesPerSector
  off = byteOff % exfat_bytesPerSector
  If exfat_FatLoad(sector) = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn exfat_U32(@exfat_fatSector[0], off) & $FFFFFFFF
EndProcedure

Procedure.i exfat_SetFatEntry(cluster.i, value.i)
  Define byteOff.i
  Define sector.i
  Define off.i
  If exfat_ClusterValid(cluster) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  byteOff = cluster * 4
  sector = exfat_fatOffset + exfat_activeFat * exfat_fatLength + byteOff / exfat_bytesPerSector
  off = byteOff % exfat_bytesPerSector
  If exfat_FatLoad(sector) = 0
    ProcedureReturn 0
  EndIf
  exfat_Put32(@exfat_fatSector[0], off, value)
  exfat_fatDirty = 1
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_NextCluster(first.i, current.i, flags.i, index.i)
  Define n.i
  If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
    n = first + index + 1
    If exfat_ClusterValid(n) = 0
      exfat_Fail(#EXFAT_E_CHAIN)
      ProcedureReturn -1
    EndIf
    ProcedureReturn n
  EndIf
  n = exfat_FatEntry(current)
  If n < 0
    ProcedureReturn -1
  EndIf
  If n >= $FFFFFFF8
    ProcedureReturn 0
  EndIf
  If exfat_ClusterValid(n) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  ProcedureReturn n
EndProcedure

Procedure.i exfat_StreamCluster(first.i, flags.i, clusterIndex.i)
  Define current.i
  Define i.i
  Define n.i
  If clusterIndex < 0 Or exfat_ClusterValid(first) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  ; A contiguous stream is arithmetic: its Nth cluster is first + N, and
  ; the run is valid when both of its ends are.
  If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
    n = first + clusterIndex
    If clusterIndex >= exfat_clusterCount Or exfat_ClusterValid(n) = 0
      exfat_Fail(#EXFAT_E_CHAIN)
      ProcedureReturn -1
    EndIf
    ProcedureReturn n
  EndIf
  current = first
  i = 0
  While i < clusterIndex
    If i >= exfat_clusterCount
      exfat_Fail(#EXFAT_E_CHAIN)
      ProcedureReturn -1
    EndIf
    n = exfat_NextCluster(first, current, flags, i)
    If n <= 0
      exfat_Fail(#EXFAT_E_CHAIN)
      ProcedureReturn -1
    EndIf
    current = n
    i = i + 1
  Wend
  ProcedureReturn current
EndProcedure

;  THE STREAM CURSOR. A read or write crosses the clusters of one stream in
;  order, so the cluster for the next sector is either the one already in
;  hand or the link after it. Resolving each sector from the first cluster
;  instead walks the chain again every time - one FAT sector read per link,
;  over USB - which makes a large fragmented file cost the square of its
;  length. exfat_CursorCluster keeps the last (index, cluster) pair and
;  walks from the start only when a caller moves backwards or jumps.
;
;  THE CURSOR LIVES FOR ONE CALL. exfat_StreamRead and exfat_StreamWriteFixed
;  reset it on entry, and neither changes a FAT entry inside its loop, so the
;  chain it caches cannot change under it. Kept across calls it would outlive
;  a truncate, a free or a reallocation of the same first cluster, and hand
;  back a cluster that now belongs to another file.
Global exfat_curFirst.i
Global exfat_curFlags.i
Global exfat_curIndex.i = -1
Global exfat_curCluster.i

Procedure.i exfat_CursorCluster(first.i, flags.i, clusterIndex.i)
  Define n.i
  If exfat_curIndex >= 0 And exfat_curFirst = first And exfat_curFlags = flags
    If clusterIndex = exfat_curIndex
      ProcedureReturn exfat_curCluster
    EndIf
    If clusterIndex = exfat_curIndex + 1
      n = exfat_NextCluster(first, exfat_curCluster, flags, exfat_curIndex)
      If n <= 0
        exfat_curIndex = -1
        exfat_Fail(#EXFAT_E_CHAIN)
        ProcedureReturn -1
      EndIf
      exfat_curIndex = clusterIndex
      exfat_curCluster = n
      ProcedureReturn n
    EndIf
  EndIf
  exfat_curIndex = -1
  n = exfat_StreamCluster(first, flags, clusterIndex)
  If n < 0
    ProcedureReturn -1
  EndIf
  exfat_curFirst = first
  exfat_curFlags = flags
  exfat_curIndex = clusterIndex
  exfat_curCluster = n
  ProcedureReturn n
EndProcedure

; How many whole sectors, at most `want`, run on from sector `sectorIn` of
; `cluster` (the stream's cluster number `clusterIndex`) through clusters
; whose successor is the next cluster number. At least the rest of this
; cluster; -1 if the chain would not resolve. The stream cursor is left on
; the last cluster looked at, which the caller's next step asks for again.
Procedure.i exfat_RunSectors(first.i, flags.i, clusterIndex.i, cluster.i, sectorIn.i, want.i)
  Define run.i
  Define nxt.i
  run = exfat_sectorsPerCluster - sectorIn
  While run < want
    nxt = exfat_CursorCluster(first, flags, clusterIndex + 1)
    If nxt < 0
      ProcedureReturn -1
    EndIf
    If nxt <> cluster + 1
      Break
    EndIf
    clusterIndex = clusterIndex + 1
    cluster = nxt
    run = run + exfat_sectorsPerCluster
  Wend
  If run > want
    run = want
  EndIf
  ProcedureReturn run
EndProcedure

Procedure.i exfat_StreamRead(first.i, flags.i, length.i, offset.i, *dst, count.i)
  Define run.i
  Define done.i
  Define clusterIndex.i
  Define inCluster.i
  Define sectorIn.i
  Define inSector.i
  Define take.i
  Define cluster.i
  Define sector.i
  If count < 0 Or offset < 0 Or offset > length
    exfat_Fail(#EXFAT_E_BOUNDS)
    ProcedureReturn -1
  EndIf
  If count = 0 Or offset = length
    ProcedureReturn 0
  EndIf
  If *dst = 0
    exfat_Fail(#EXFAT_E_NULL)
    ProcedureReturn -1
  EndIf
  If count > length - offset
    count = length - offset
  EndIf
  exfat_curIndex = -1
  done = 0
  While done < count
    clusterIndex = (offset + done) / exfat_bytesPerCluster
    inCluster = (offset + done) % exfat_bytesPerCluster
    sectorIn = inCluster / exfat_bytesPerSector
    inSector = inCluster % exfat_bytesPerSector
    cluster = exfat_CursorCluster(first, flags, clusterIndex)
    If cluster < 0
      ProcedureReturn -1
    EndIf
    sector = exfat_ClusterSector(cluster, sectorIn)
    If sector < 0
      ProcedureReturn -1
    EndIf
    If inSector = 0 And count - done >= exfat_bytesPerSector
      ; WHOLE SECTORS go straight into the caller's memory, a run through
      ; every cluster that follows its predecessor, in one read.
      run = exfat_RunSectors(first, flags, clusterIndex, cluster, sectorIn, (count - done) / exfat_bytesPerSector)
      If run < 1 Or exfat_ReadSectors(sector, run, *dst + done) = 0
        ProcedureReturn -1
      EndIf
      done = done + run * exfat_bytesPerSector
    Else
      ; A PIECE OF A SECTOR comes out of the read cache - see exfat_rcache.
      If exfat_rcacheSector <> sector
        exfat_rcacheSector = -1
        If exfat_ReadSectors(sector, 1, @exfat_rcache[0]) = 0
          ProcedureReturn -1
        EndIf
        exfat_rcacheSector = sector
      EndIf
      take = exfat_bytesPerSector - inSector
      If take > count - done
        take = count - done
      EndIf
      exfat_Copy(*dst + done, @exfat_rcache[0] + inSector, take)
      done = done + take
    EndIf
  Wend
  ProcedureReturn done
EndProcedure

Procedure.i exfat_Ror32(value.i)
  ProcedureReturn ((value & $FFFFFFFF) >> 1) | ((value & 1) << 31)
EndProcedure

Procedure.i exfat_Ror16(value.i)
  ProcedureReturn ((value & $FFFF) >> 1) | ((value & 1) << 15)
EndProcedure

Procedure.i exfat_BootChecksum(base.i)
  Define checksum.i
  Define sector.i
  Define i.i
  Define b.i
  checksum = 0
  sector = 0
  While sector < 11
    If exfat_ReadSector(base + sector, @exfat_sector[0]) = 0
      ProcedureReturn -1
    EndIf
    i = 0
    While i < exfat_bytesPerSector
      If sector <> 0 Or (i <> 106 And i <> 107 And i <> 112)
        b = PeekA(@exfat_sector[0] + i)
        checksum = (exfat_Ror32(checksum) + b) & $FFFFFFFF
      EndIf
      i = i + 1
    Wend
    sector = sector + 1
  Wend
  ProcedureReturn checksum
EndProcedure

Procedure.i exfat_CheckBootRegion(base.i)
  Define checksum.i
  Define i.i
  checksum = exfat_BootChecksum(base)
  If checksum < 0
    ProcedureReturn 0
  EndIf
  If exfat_ReadSector(base + 11, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < exfat_bytesPerSector
    If exfat_U32(@exfat_sector[0], i) <> checksum
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT_CHECKSUM)
    EndIf
    i = i + 4
  Wend
  ; The boot and every extended boot sector carry mandatory signatures.
  If exfat_ReadSector(base, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  If PeekA(@exfat_sector[0]) <> $EB Or PeekA(@exfat_sector[0] + 1) <> $76 Or PeekA(@exfat_sector[0] + 2) <> $90
    ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
  EndIf
  i = 0
  While i < 8
    If PeekA(@exfat_sector[0] + 3 + i) <> PeekA(?exfat_signature + i)
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
    EndIf
    i = i + 1
  Wend
  i = 11
  While i <= 63
    If PeekA(@exfat_sector[0] + i) <> 0
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
    EndIf
    i = i + 1
  Wend
  If exfat_U16(@exfat_sector[0], 510) <> $AA55
    ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
  EndIf
  i = 1
  While i <= 8
    If exfat_ReadSector(base + i, @exfat_sector[0]) = 0
      ProcedureReturn 0
    EndIf
    If exfat_U32(@exfat_sector[0], exfat_bytesPerSector - 4) <> $AA550000
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Both boot regions describe the same geometry. VolumeFlags and PercentInUse
; are explicitly allowed to be stale in the backup and are not compared.
Procedure.i exfat_CheckBackupGeometry()
  Define i.i
  If exfat_ReadSector(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  If exfat_ReadSector(12, @exfat_aux[0]) = 0
    ProcedureReturn 0
  EndIf
  i = 64
  While i <= 105
    If PeekA(@exfat_sector[0] + i) <> PeekA(@exfat_aux[0] + i)
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
    EndIf
    i = i + 1
  Wend
  i = 108
  While i <= 111
    If PeekA(@exfat_sector[0] + i) <> PeekA(@exfat_aux[0] + i)
      ProcedureReturn exfat_Fail(#EXFAT_E_BOOT)
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_Crc32Update(crc.i, value.i)
  Define bit.i
  crc = crc ! (value & $FF)
  bit = 0
  While bit < 8
    If (crc & 1) <> 0
      crc = (crc >> 1) ! $EDB88320
    Else
      crc = crc >> 1
    EndIf
    bit = bit + 1
  Wend
  ProcedureReturn crc & $FFFFFFFF
EndProcedure

Procedure.i exfat_GptTypeIsBasic(*entry)
  Define i.i
  i = 0
  While i < 16
    If PeekA(*entry + i) <> PeekA(?exfat_gptBasicData + i)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; GPT is a 512-byte block structure regardless of the exFAT logical sector
; size declared later by the selected volume. `partition` is the one-based
; ordinal among Microsoft Basic Data partitions, matching what a user sees as
; usable data volumes instead of exposing protective and vendor entries.
Procedure.i exfat_FindGptPartition(partition.i)
  Define headerSize.i
  Define storedHeaderCrc.i
  Define headerCrc.i
  Define entryLba.i
  Define entryCount.i
  Define entrySize.i
  Define storedArrayCrc.i
  Define arrayCrc.i
  Define total.i
  Define done.i
  Define take.i
  Define i.i
  Define e.i
  Define ordinal.i
  Define first.i
  Define last.i
  Define firstUsable.i
  Define lastUsable.i
  Define backupLba.i
  If partition < 1
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  If exfat_ReadBlock(1, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  If exfat_U32(@exfat_sector[0], 0) <> $20494645 Or exfat_U32(@exfat_sector[0], 4) <> $54524150
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  headerSize = exfat_U32(@exfat_sector[0], 12) & $FFFFFFFF
  If headerSize < 92 Or headerSize > 512
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  storedHeaderCrc = exfat_U32(@exfat_sector[0], 16) & $FFFFFFFF
  exfat_Put32(@exfat_sector[0], 16, 0)
  headerCrc = $FFFFFFFF
  i = 0
  While i < headerSize
    headerCrc = exfat_Crc32Update(headerCrc, PeekA(@exfat_sector[0] + i))
    i = i + 1
  Wend
  headerCrc = (~headerCrc) & $FFFFFFFF
  exfat_Put32(@exfat_sector[0], 16, storedHeaderCrc)
  If headerCrc <> storedHeaderCrc Or exfat_U64(@exfat_sector[0], 24) <> 1
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  firstUsable = exfat_U64(@exfat_sector[0], 40)
  lastUsable = exfat_U64(@exfat_sector[0], 48)
  backupLba = exfat_U64(@exfat_sector[0], 32)
  entryLba = exfat_U64(@exfat_sector[0], 72)
  entryCount = exfat_U32(@exfat_sector[0], 80) & $FFFFFFFF
  entrySize = exfat_U32(@exfat_sector[0], 84) & $FFFFFFFF
  storedArrayCrc = exfat_U32(@exfat_sector[0], 88) & $FFFFFFFF
  If backupLba <= lastUsable Or firstUsable < 2 Or lastUsable < firstUsable Or entryLba < 2 Or entryCount < 1 Or entryCount > 131072 Or entrySize < 128 Or entrySize > 4096 Or (entrySize & 7) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  If entryCount > 16777216 / entrySize
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  total = entryCount * entrySize
  If entryLba + (total + 511) / 512 > firstUsable
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  arrayCrc = $FFFFFFFF
  done = 0
  While done < total
    If exfat_ReadBlock(entryLba + done / 512, @exfat_aux[0]) = 0
      ProcedureReturn 0
    EndIf
    take = 512
    If take > total - done
      take = total - done
    EndIf
    i = 0
    While i < take
      arrayCrc = exfat_Crc32Update(arrayCrc, PeekA(@exfat_aux[0] + i))
      i = i + 1
    Wend
    done = done + take
  Wend
  arrayCrc = (~arrayCrc) & $FFFFFFFF
  If arrayCrc <> storedArrayCrc
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  ordinal = 0
  e = 0
  While e < entryCount
    done = e * entrySize
    ; GPT entry sizes may exceed a block, but every legal entry begins on an
    ; eight-byte boundary. Copy its first 48 bytes explicitly across a block
    ; edge before interpreting its type and LBA range.
    i = 0
    While i < 48
      If i = 0 Or ((done + i) / 512) <> ((done + i - 1) / 512)
        If exfat_ReadBlock(entryLba + (done + i) / 512, @exfat_aux[0]) = 0
          ProcedureReturn 0
        EndIf
      EndIf
      PokeA(@exfat_gptEntry[0] + i, PeekA(@exfat_aux[0] + ((done + i) % 512)))
      i = i + 1
    Wend
    If exfat_GptTypeIsBasic(@exfat_gptEntry[0]) <> 0
      ordinal = ordinal + 1
      If ordinal = partition
        first = exfat_U64(@exfat_gptEntry[0], 32)
        last = exfat_U64(@exfat_gptEntry[0], 40)
        If first < firstUsable Or last < first Or last > lastUsable
          ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
        EndIf
        exfat_partLba = first
        exfat_partBlocks = last - first + 1
        ProcedureReturn 1
      EndIf
    EndIf
    e = e + 1
  Wend
  ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EXFAT)
EndProcedure

Procedure.i exfat_FindPartition(partition.i)
  Define status.i
  Define typ.i
  Define off.i
  Define start.i
  Define count.i
  Define entry.i
  Define shift.i
  Define logicalSectors.i
  exfat_partLba = 0
  exfat_partBlocks = $7FFFFFFF
  If exfat_ReadBlock(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  ; A raw exFAT volume is valid removable-media layout.
  If PeekA(@exfat_sector[0] + 3) = 69 And PeekA(@exfat_sector[0] + 4) = 88 And PeekA(@exfat_sector[0] + 5) = 70 And PeekA(@exfat_sector[0] + 6) = 65 And PeekA(@exfat_sector[0] + 7) = 84 And PeekA(@exfat_sector[0] + 8) = 32 And PeekA(@exfat_sector[0] + 9) = 32 And PeekA(@exfat_sector[0] + 10) = 32
    exfat_partLba = 0
    shift = PeekA(@exfat_sector[0] + 108)
    logicalSectors = exfat_U64(@exfat_sector[0], 72)
    If shift < 9 Or shift > 12 Or logicalSectors <= 0 Or logicalSectors > $7FFFFFFFFFFFFFFF / (1 << (shift - 9))
      ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
    EndIf
    exfat_partBlocks = logicalSectors * (1 << (shift - 9))
    ProcedureReturn exfat_partBlocks > 0
  EndIf
  If PeekA(@exfat_sector[0] + 510) <> $55 Or PeekA(@exfat_sector[0] + 511) <> $AA
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_MBR)
  EndIf
  ; A protective MBR delegates the data-volume ordinal to GPT.
  entry = 0
  While entry < 4
    If PeekA(@exfat_sector[0] + $1BE + entry * 16 + 4) = $EE
      ProcedureReturn exfat_FindGptPartition(partition)
    EndIf
    entry = entry + 1
  Wend
  If partition < 1 Or partition > 4
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  off = $1BE + (partition - 1) * 16
  status = PeekA(@exfat_sector[0] + off)
  typ = PeekA(@exfat_sector[0] + off + 4)
  If status <> 0 And status <> $80
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  If typ <> 7
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EXFAT)
  EndIf
  start = exfat_U32(@exfat_sector[0], off + 8) & $FFFFFFFF
  count = exfat_U32(@exfat_sector[0], off + 12) & $FFFFFFFF
  If start <= 0 Or count <= 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PARTITION)
  EndIf
  exfat_partLba = start
  exfat_partBlocks = count
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ReadBoot()
  Define volume.i
  Define heapEnd.i
  Define shift.i
  Define i.i
  ; Bootstrap with 512-byte sectors, then re-read using declared geometry.
  exfat_bytesPerSector = 512
  exfat_blocksPerSector = 1
  exfat_volumeBlocks = exfat_partBlocks
  If exfat_ReadSector(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < 8
    If PeekA(@exfat_sector[0] + 3 + i) <> PeekA(?exfat_signature + i)
      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EXFAT)
    EndIf
    i = i + 1
  Wend
  shift = PeekA(@exfat_sector[0] + 108)
  If shift < 9 Or shift > 12
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  exfat_bytesPerSector = 1 << shift
  exfat_blocksPerSector = exfat_bytesPerSector / #EXFAT_BLOCK_SIZE
  shift = PeekA(@exfat_sector[0] + 109)
  If shift < 0 Or shift > 16
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  exfat_sectorsPerCluster = 1 << shift
  exfat_blocksPerCluster = exfat_blocksPerSector * exfat_sectorsPerCluster
  exfat_bytesPerCluster = exfat_bytesPerSector * exfat_sectorsPerCluster
  If exfat_bytesPerCluster <= 0 Or exfat_bytesPerCluster > 33554432
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  If exfat_ReadSector(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  volume = exfat_U64(@exfat_sector[0], 72)
  If volume <= 0 Or volume > exfat_partBlocks / exfat_blocksPerSector
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  exfat_volumeBlocks = volume * exfat_blocksPerSector
  exfat_fatOffset = exfat_U32(@exfat_sector[0], 80) & $FFFFFFFF
  exfat_fatLength = exfat_U32(@exfat_sector[0], 84) & $FFFFFFFF
  exfat_heapOffset = exfat_U32(@exfat_sector[0], 88) & $FFFFFFFF
  exfat_clusterCount = exfat_U32(@exfat_sector[0], 92) & $FFFFFFFF
  exfat_rootCluster = exfat_U32(@exfat_sector[0], 96) & $FFFFFFFF
  exfat_volumeFlags = exfat_U16(@exfat_sector[0], 106)
  exfat_numFats = PeekA(@exfat_sector[0] + 110)
  exfat_percentInUse = PeekA(@exfat_sector[0] + 112)
  If (exfat_U16(@exfat_sector[0], 104) >> 8) <> 1
    ProcedureReturn exfat_Fail(#EXFAT_E_REVISION)
  EndIf
  If exfat_numFats < 1 Or exfat_numFats > 2
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  If exfat_numFats = 1 And (exfat_volumeFlags & 1) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  If exfat_percentInUse > 100 And exfat_percentInUse <> $FF
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  If exfat_numFats = 2
    exfat_activeFat = exfat_volumeFlags & 1
    exfat_texfat = 1
  Else
    exfat_activeFat = 0
    exfat_texfat = 0
  EndIf
  exfat_inheritedDirty = Bool((exfat_volumeFlags & 2) <> 0)
  exfat_mediaFailure = Bool((exfat_volumeFlags & 4) <> 0)
  If volume < (1048576 + exfat_bytesPerSector - 1) / exfat_bytesPerSector Or exfat_fatOffset < 24 Or exfat_fatLength < ((exfat_clusterCount + 2) * 4 + exfat_bytesPerSector - 1) / exfat_bytesPerSector Or exfat_clusterCount < 1
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  heapEnd = exfat_heapOffset + exfat_clusterCount * exfat_sectorsPerCluster
  If exfat_fatOffset + exfat_fatLength * exfat_numFats > exfat_heapOffset Or heapEnd > volume
    ProcedureReturn exfat_Fail(#EXFAT_E_GEOMETRY)
  EndIf
  If exfat_ClusterValid(exfat_rootCluster) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_ROOT)
  EndIf
  If exfat_CheckBootRegion(0) = 0 Or exfat_CheckBootRegion(12) = 0 Or exfat_CheckBackupGeometry() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

DataSection
  exfat_signature: Data.a 69,88,70,65,84,32,32,32
  ; {EBD0A0A2-B9E5-4433-87C0-68B6B72699C7}, byte order on disk.
  exfat_gptBasicData: Data.a $A2,$A0,$D0,$EB,$E5,$B9,$33,$44,$87,$C0,$68,$B6,$B7,$26,$99,$C7
EndDataSection

Procedure.i exfat_StreamByte(first.i, flags.i, length.i, offset.i)
  Define b.i
  If exfat_StreamRead(first, flags, length, offset, @b, 1) <> 1
    ProcedureReturn -1
  EndIf
  ProcedureReturn b & $FF
EndProcedure

Procedure.i exfat_DirRead(first.i, flags.i, length.i, index.i, *dst)
  Define maxBytes.i
  Define got.i
  If index < 0 Or index >= 8388608
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  If length = 0
    maxBytes = exfat_clusterCount * exfat_bytesPerCluster
  Else
    maxBytes = length
  EndIf
  If index * 32 >= maxBytes
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  got = exfat_StreamRead(first, flags, maxBytes, index * 32, *dst, 32)
  If got <> 32
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_SetChecksum(first.i, flags.i, length.i, index.i, secondaryCount.i)
  Define sum.i
  Define e.i
  Define b.i
  Define v.i
  sum = 0
  e = 0
  While e <= secondaryCount
    If exfat_DirRead(first, flags, length, index + e, @exfat_aux[0]) = 0
      ProcedureReturn -1
    EndIf
    b = 0
    While b < 32
      If e <> 0 Or (b <> 2 And b <> 3)
        v = PeekA(@exfat_aux[0] + b)
        sum = (exfat_Ror16(sum) + v) & $FFFF
      EndIf
      b = b + 1
    Wend
    e = e + 1
  Wend
  ProcedureReturn sum
EndProcedure

Procedure.i exfat_UpcaseTableChecksum()
  Define sum.i
  Define off.i
  Define b.i
  sum = 0
  off = 0
  While off < exfat_upcaseLength
    b = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    If b < 0
      ProcedureReturn -1
    EndIf
    sum = (exfat_Ror32(sum) + b) & $FFFFFFFF
    off = off + 1
  Wend
  ProcedureReturn sum
EndProcedure

; Decode one compressed up-case-table mapping. 0xFFFF followed by a count
; means that many identity mappings. The last word of a complete table is the
; literal mapping U+FFFF -> U+FFFF and therefore has no count after it.
Procedure.i exfat_Upper(code.i)
  Define cp.i
  Define off.i
  Define word.i
  Define skip.i
  Define lo.i
  Define hi.i
  If code < 0 Or code > $FFFF
    exfat_Fail(#EXFAT_E_UTF16)
    ProcedureReturn -1
  EndIf
  If exfat_upcaseFastReady <> 0 And code < 256
    ProcedureReturn exfat_upcaseFast[code] & $FFFF
  EndIf
  cp = 0
  off = 0
  While off + 1 < exfat_upcaseLength And cp <= code
    lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
    If lo < 0 Or hi < 0
      ProcedureReturn -1
    EndIf
    word = lo | (hi << 8)
    off = off + 2
    If word = $FFFF
      If off + 1 >= exfat_upcaseLength
        If cp = $FFFF And code = $FFFF
          ProcedureReturn $FFFF
        EndIf
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
      hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
      If lo < 0 Or hi < 0
        ProcedureReturn -1
      EndIf
      skip = lo | (hi << 8)
      off = off + 2
      If skip = 0 Or cp + skip > 65536
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      If code < cp + skip
        ProcedureReturn code
      EndIf
      cp = cp + skip
    Else
      If cp = code
        ProcedureReturn word
      EndIf
      cp = cp + 1
    EndIf
  Wend
  ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
EndProcedure

Procedure.i exfat_NameHash(*name, count.i)
  Define sum.i
  Define i.i
  Define c.i
  If count < 1 Or count > #EXFAT_MAX_NAME
    ProcedureReturn -1
  EndIf
  sum = 0
  i = 0
  While i < count
    c = exfat_Upper(PeekW(*name + i * 2) & $FFFF)
    If c < 0
      ProcedureReturn -1
    EndIf
    sum = (exfat_Ror16(sum) + (c & $FF)) & $FFFF
    sum = (exfat_Ror16(sum) + ((c >> 8) & $FF)) & $FFFF
    i = i + 1
  Wend
  ProcedureReturn sum
EndProcedure

Procedure.i exfat_BuildFastUpcase()
  Define cp.i
  Define off.i
  Define word.i
  Define skip.i
  Define lo.i
  Define hi.i
  Define endCp.i
  cp = 0
  off = 0
  While cp < 256 And off + 1 < exfat_upcaseLength
    lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
    If lo < 0 Or hi < 0
      ProcedureReturn 0
    EndIf
    word = lo | (hi << 8)
    off = off + 2
    If word = $FFFF
      If off + 1 >= exfat_upcaseLength
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
      hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
      If lo < 0 Or hi < 0
        ProcedureReturn 0
      EndIf
      skip = lo | (hi << 8)
      off = off + 2
      If skip = 0 Or cp + skip > 65536
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      endCp = cp + skip
      If endCp > 256
        endCp = 256
      EndIf
      While cp < endCp
        exfat_upcaseFast[cp] = cp
        cp = cp + 1
      Wend
    Else
      exfat_upcaseFast[cp] = word
      cp = cp + 1
    EndIf
  Wend
  If cp <> 256
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
  EndIf
  ; Microsoft defines mandatory mappings for the first 128 code points.
  cp = 0
  While cp < 128
    If cp >= 97 And cp <= 122
      If exfat_upcaseFast[cp] <> cp - 32
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
    ElseIf exfat_upcaseFast[cp] <> cp
      ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
    EndIf
    cp = cp + 1
  Wend
  exfat_upcaseFastReady = 1
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ValidateUpcase()
  Define cp.i
  Define off.i
  Define lo.i
  Define hi.i
  Define word.i
  Define skip.i
  cp = 0
  off = 0
  While off + 1 < exfat_upcaseLength And cp < 65536
    lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
    hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
    If lo < 0 Or hi < 0
      ProcedureReturn 0
    EndIf
    word = lo | (hi << 8)
    off = off + 2
    If word = $FFFF
      If off + 1 >= exfat_upcaseLength
        If cp = $FFFF
          cp = cp + 1
          Break
        EndIf
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      lo = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off)
      hi = exfat_StreamByte(exfat_upcaseCluster, 0, exfat_upcaseLength, off + 1)
      If lo < 0 Or hi < 0
        ProcedureReturn 0
      EndIf
      skip = lo | (hi << 8)
      off = off + 2
      If skip = 0 Or cp + skip > 65536
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      cp = cp + skip
    Else
      cp = cp + 1
    EndIf
  Wend
  If cp <> 65536 Or off <> exfat_upcaseLength
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_NameEqual(*a, *b, count.i)
  Define i.i
  Define ca.i
  Define cb.i
  i = 0
  While i < count
    ca = exfat_Upper(PeekW(*a + i * 2) & $FFFF)
    cb = exfat_Upper(PeekW(*b + i * 2) & $FFFF)
    If ca < 0 Or cb < 0 Or ca <> cb
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_Utf8Name(*text, *out, maxChars.i)
  Define p.i
  Define n.i
  Define c.i
  Define c2.i
  Define c3.i
  Define c4.i
  Define cp.i
  If *text = 0 Or *out = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  p = 0
  n = 0
  While PeekA(*text + p) <> 0
    c = PeekA(*text + p)
    If c = 47 Or c = 92
      Break
    EndIf
    If c < $80
      cp = c
      p = p + 1
    ElseIf c >= $C2 And c <= $DF
      c2 = PeekA(*text + p + 1)
      If (c2 & $C0) <> $80
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
      EndIf
      cp = ((c & $1F) << 6) | (c2 & $3F)
      p = p + 2
    ElseIf c >= $E0 And c <= $EF
      c2 = PeekA(*text + p + 1)
      c3 = PeekA(*text + p + 2)
      If (c2 & $C0) <> $80 Or (c3 & $C0) <> $80
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
      EndIf
      cp = ((c & $0F) << 12) | ((c2 & $3F) << 6) | (c3 & $3F)
      If cp < $800 Or (cp >= $D800 And cp <= $DFFF)
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
      EndIf
      p = p + 3
    ElseIf c >= $F0 And c <= $F4
      c2 = PeekA(*text + p + 1)
      c3 = PeekA(*text + p + 2)
      c4 = PeekA(*text + p + 3)
      If (c2 & $C0) <> $80 Or (c3 & $C0) <> $80 Or (c4 & $C0) <> $80
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
      EndIf
      cp = ((c & 7) << 18) | ((c2 & $3F) << 12) | ((c3 & $3F) << 6) | (c4 & $3F)
      If cp < $10000 Or cp > $10FFFF Or n + 2 > maxChars
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
      EndIf
      cp = cp - $10000
      PokeW(*out + n * 2, $D800 | (cp >> 10))
      n = n + 1
      PokeW(*out + n * 2, $DC00 | (cp & $3FF))
      n = n + 1
      p = p + 4
      Continue
    Else
      ProcedureReturn exfat_Fail(#EXFAT_E_UTF8)
    EndIf
    If cp < $20 Or cp = 34 Or cp = 42 Or cp = 47 Or cp = 58 Or cp = 60 Or cp = 62 Or cp = 63 Or cp = 92 Or cp = 124
      ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
    EndIf
    If n >= maxChars
      ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
    EndIf
    PokeW(*out + n * 2, cp)
    n = n + 1
  Wend
  If n = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  ; exFAT specification 7.7.3: "." and ".." are reserved (forum 905).
  If PeekW(*out) = 46 And (n = 1 Or (n = 2 And PeekW(*out + 2) = 46))
    ProcedureReturn exfat_Fail(#EXFAT_E_RESERVED_NAME)
  EndIf
  PokeW(*out + n * 2, 0)
  ProcedureReturn n
EndProcedure

Procedure.i exfat_ReadName(first.i, flags.i, length.i, setIndex.i, secondaryCount.i, nameLength.i, *out)
  Define needed.i
  Define e.i
  Define j.i
  Define n.i
  Define c.i
  needed = (nameLength + 14) / 15
  If secondaryCount < 1 + needed Or nameLength < 1 Or nameLength > #EXFAT_MAX_NAME
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  n = 0
  e = 0
  While e < needed
    If exfat_DirRead(first, flags, length, setIndex + 2 + e, @exfat_aux[0]) = 0
      ProcedureReturn 0
    EndIf
    If PeekA(@exfat_aux[0]) <> #EXFAT_ENTRY_NAME
      ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
    EndIf
    j = 0
    While j < 15 And n < nameLength
      c = exfat_U16(@exfat_aux[0], 2 + j * 2)
      If c >= $D800 And c <= $DBFF
        If n + 1 >= nameLength
          ProcedureReturn exfat_Fail(#EXFAT_E_UTF16)
        EndIf
      ElseIf c >= $DC00 And c <= $DFFF
        If n = 0 Or (PeekW(*out + (n - 1) * 2) & $FFFF) < $D800 Or (PeekW(*out + (n - 1) * 2) & $FFFF) > $DBFF
          ProcedureReturn exfat_Fail(#EXFAT_E_UTF16)
        EndIf
      EndIf
      PokeW(*out + n * 2, c)
      n = n + 1
      j = j + 1
    Wend
    e = e + 1
  Wend
  PokeW(*out + n * 2, 0)
  ProcedureReturn 1
EndProcedure

; THE NUMBER OF 32-BYTE ENTRIES A DIRECTORY STREAM HOLDS. A directory ends at
; its first type-0 entry OR at the end of its clusters, whichever comes
; first; one whose entries fill its clusters exactly has no type-0 entry at
; all. Every scan stops here as well (forum 913 - until 2026-09-17 a scan of
; an exactly full folder read past its last cluster and failed with error 25).
; The root and any stream recorded with length 0 are measured along their FAT
; chain; -1 on a broken chain.
Procedure.i exfat_DirEntryLimit(first.i, flags.i, length.i)
  Define count.i
  Define current.i
  Define nxt.i
  If length > 0
    ProcedureReturn length / 32
  EndIf
  If exfat_ClusterValid(first) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  current = first
  count = 1
  While count <= exfat_clusterCount
    nxt = exfat_NextCluster(first, current, flags, count - 1)
    If nxt = 0
      ProcedureReturn (count * exfat_bytesPerCluster) / 32
    EndIf
    If nxt < 0
      ProcedureReturn -1
    EndIf
    current = nxt
    count = count + 1
  Wend
  exfat_Fail(#EXFAT_E_CHAIN)
  ProcedureReturn -1
EndProcedure

; Result is placed in the exfat_file* globals.  A malformed in-use file set is
; never skipped: it makes the directory unusable, preventing a later write
; from treating damaged metadata as free space.
Procedure.i exfat_FindInDir(dirFirst.i, dirFlags.i, dirLength.i, *name, nameLength.i)
  Define index.i
  Define typ.i
  Define secondary.i
  Define sum.i
  Define stored.i
  Define streamFlags.i
  Define streamNameLength.i
  Define streamHash.i
  Define streamFirst.i
  Define streamValid.i
  Define streamLength.i
  Define wantHash.i
  Define found.i
  Define limit.i
  wantHash = exfat_NameHash(*name, nameLength)
  If wantHash < 0
    ProcedureReturn 0
  EndIf
  limit = exfat_DirEntryLimit(dirFirst, dirFlags, dirLength)
  If limit < 0
    ProcedureReturn 0
  EndIf
  index = 0
  While index < limit
    If exfat_DirRead(dirFirst, dirFlags, dirLength, index, @exfat_entry[0]) = 0
      ProcedureReturn 0
    EndIf
    typ = PeekA(@exfat_entry[0])
    If typ = 0
      exfat_error = #EXFAT_E_NOT_FOUND
      ProcedureReturn 0
    EndIf
    If typ = #EXFAT_ENTRY_FILE
      secondary = PeekA(@exfat_entry[0] + 1)
      If secondary < 2 Or secondary > 18
        ProcedureReturn exfat_Fail(#EXFAT_E_SET_CHECKSUM)
      EndIf
      stored = exfat_U16(@exfat_entry[0], 2)
      sum = exfat_SetChecksum(dirFirst, dirFlags, dirLength, index, secondary)
      If sum < 0 Or sum <> stored
        ProcedureReturn exfat_Fail(#EXFAT_E_SET_CHECKSUM)
      EndIf
      If exfat_DirRead(dirFirst, dirFlags, dirLength, index + 1, @exfat_aux[0]) = 0
        ProcedureReturn 0
      EndIf
      If PeekA(@exfat_aux[0]) <> #EXFAT_ENTRY_STREAM
        ProcedureReturn exfat_Fail(#EXFAT_E_SET_CHECKSUM)
      EndIf
      streamFlags = PeekA(@exfat_aux[0] + 1)
      streamNameLength = PeekA(@exfat_aux[0] + 3)
      streamHash = exfat_U16(@exfat_aux[0], 4)
      streamValid = exfat_U64(@exfat_aux[0], 8)
      streamFirst = exfat_U32(@exfat_aux[0], 20) & $FFFFFFFF
      streamLength = exfat_U64(@exfat_aux[0], 24)
      If streamValid < 0 Or streamLength < 0
        ProcedureReturn 0
      EndIf
      If (streamFlags & #EXFAT_STREAM_ALLOC_POSSIBLE) = 0 Or (streamFlags & ~$03) <> 0
        ProcedureReturn exfat_Fail(#EXFAT_E_SET_CHECKSUM)
      EndIf
      If streamFirst = 0 And (streamLength <> 0 Or (streamFlags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0)
        ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
      EndIf
      If exfat_ReadName(dirFirst, dirFlags, dirLength, index, secondary, streamNameLength, @exfat_name[0]) = 0
        ProcedureReturn 0
      EndIf
      If exfat_NameHash(@exfat_name[0], streamNameLength) <> streamHash
        ProcedureReturn exfat_Fail(#EXFAT_E_NAME_HASH)
      EndIf
      If streamNameLength = nameLength And streamHash = wantHash
        found = exfat_NameEqual(@exfat_name[0], *name, nameLength)
        If found <> 0
          exfat_fileFirst = streamFirst
          exfat_fileValid = streamValid
          exfat_fileLength = streamLength
          If exfat_fileValid < 0 Or exfat_fileLength < 0 Or exfat_fileValid > exfat_fileLength
            ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
          EndIf
          If exfat_fileLength > 0 And exfat_ClusterValid(exfat_fileFirst) = 0
            ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
          EndIf
          exfat_fileFlags = streamFlags
          exfat_fileAttr = exfat_U16(@exfat_entry[0], 4)
          exfat_fileParent = dirFirst
          exfat_fileParentFlags = dirFlags
          exfat_fileParentLength = dirLength
          exfat_fileSetIndex = index
          exfat_fileSecondaries = secondary
          exfat_fileNameLength = streamNameLength
          exfat_error = #EXFAT_OK
          ProcedureReturn 1
        EndIf
      EndIf
      index = index + secondary + 1
    Else
      ; Unknown critical primaries are invalid. Known metadata is valid only
      ; in root and is consumed during mount.
      If (typ & $80) <> 0 And (typ & $40) = 0 And typ <> #EXFAT_ENTRY_BITMAP And typ <> #EXFAT_ENTRY_UPCASE And typ <> #EXFAT_ENTRY_LABEL
        ProcedureReturn exfat_Fail(#EXFAT_E_CRITICAL)
      EndIf
      index = index + 1
    EndIf
  Wend
  exfat_error = #EXFAT_E_NOT_FOUND
  ProcedureReturn 0
EndProcedure

Procedure.i exfat_FindSystemEntries()
  Define index.i
  Define typ.i
  Define bitmapSeen.i
  Define upcaseSeen.i
  Define flags.i
  Define checksum.i
  Define limit.i
  limit = exfat_DirEntryLimit(exfat_rootCluster, 0, 0)
  If limit < 0
    ProcedureReturn 0
  EndIf
  index = 0
  While index < limit
    If exfat_DirRead(exfat_rootCluster, 0, 0, index, @exfat_entry[0]) = 0
      ProcedureReturn 0
    EndIf
    typ = PeekA(@exfat_entry[0])
    If typ = 0
      Break
    EndIf
    If typ = #EXFAT_ENTRY_BITMAP
      flags = PeekA(@exfat_entry[0] + 1)
      If (flags & 1) = exfat_activeFat
        If bitmapSeen <> 0
          ProcedureReturn exfat_Fail(#EXFAT_E_BITMAP)
        EndIf
        exfat_bitmapCluster = exfat_U32(@exfat_entry[0], 20) & $FFFFFFFF
        exfat_bitmapLength = exfat_U64(@exfat_entry[0], 24)
        bitmapSeen = 1
      EndIf
    ElseIf typ = #EXFAT_ENTRY_UPCASE
      If upcaseSeen <> 0
        ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
      EndIf
      exfat_upcaseChecksum = exfat_U32(@exfat_entry[0], 4) & $FFFFFFFF
      exfat_upcaseCluster = exfat_U32(@exfat_entry[0], 20) & $FFFFFFFF
      exfat_upcaseLength = exfat_U64(@exfat_entry[0], 24)
      upcaseSeen = 1
    ElseIf (typ & $80) <> 0 And (typ & $40) = 0 And typ <> #EXFAT_ENTRY_LABEL And typ <> #EXFAT_ENTRY_FILE
      ProcedureReturn exfat_Fail(#EXFAT_E_CRITICAL)
    EndIf
    index = index + 1
  Wend
  If bitmapSeen = 0 Or exfat_ClusterValid(exfat_bitmapCluster) = 0 Or exfat_bitmapLength < (exfat_clusterCount + 7) / 8
    ProcedureReturn exfat_Fail(#EXFAT_E_BITMAP)
  EndIf
  If upcaseSeen = 0 Or exfat_ClusterValid(exfat_upcaseCluster) = 0 Or exfat_upcaseLength < 2 Or (exfat_upcaseLength & 1) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE)
  EndIf
  checksum = exfat_UpcaseTableChecksum()
  If checksum < 0 Or checksum <> exfat_upcaseChecksum
    ProcedureReturn exfat_Fail(#EXFAT_E_UPCASE_CHECKSUM)
  EndIf
  If exfat_ValidateUpcase() = 0
    ProcedureReturn 0
  EndIf
  exfat_upcaseFastReady = 0
  If exfat_BuildFastUpcase() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatMount(partition.i)
  exfat_error = #EXFAT_OK
  exfat_DropCaches()
  exfat_mounted = 0
  exfat_upcaseFastReady = 0
  exfat_open = 0
  exfat_partBlocks = 0
  If exfat_FindPartition(partition) = 0
    ProcedureReturn 0
  EndIf
  If exfat_ReadBoot() = 0
    ProcedureReturn 0
  EndIf
  If exfat_FindSystemEntries() = 0
    ProcedureReturn 0
  EndIf
  exfat_mounted = 1
  exfat_dirty = 0
  exfat_ioFailed = 0
  exfat_allocChanged = 0
  exfat_freeClusters = -1
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_PathNext(*path, offset.i)
  While PeekA(*path + offset) = 47 Or PeekA(*path + offset) = 92
    offset = offset + 1
  Wend
  ProcedureReturn offset
EndProcedure

Procedure.i exfat_PathAfterSegment(*path, offset.i)
  While PeekA(*path + offset) <> 0 And PeekA(*path + offset) <> 47 And PeekA(*path + offset) <> 92
    offset = offset + 1
  Wend
  ProcedureReturn exfat_PathNext(*path, offset)
EndProcedure

; Resolves every parent component.  Result globals name the final object.
Procedure.i exfat_Resolve(*path)
  Define off.i
  Define nxt.i
  Define len.i
  Define dirFirst.i
  Define dirFlags.i
  Define dirLength.i
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  If *path = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  off = exfat_PathNext(*path, 0)
  ; An empty path, or one of separators only, names the root directory,
  ; which has no entry set of its own. Answering "resolved" here would leave
  ; the PREVIOUS lookup's entry in the result globals, and a remove or rename
  ; would then act on that entry under the root's name.
  If PeekA(*path + off) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  dirFirst = exfat_rootCluster
  dirFlags = 0
  dirLength = 0
  While PeekA(*path + off) <> 0
    len = exfat_Utf8Name(*path + off, @exfat_want[0], #EXFAT_MAX_NAME)
    If len <= 0
      ProcedureReturn 0
    EndIf
    nxt = exfat_PathAfterSegment(*path, off)
    If exfat_FindInDir(dirFirst, dirFlags, dirLength, @exfat_want[0], len) = 0
      ProcedureReturn 0
    EndIf
    If PeekA(*path + nxt) <> 0
      If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) = 0
        ProcedureReturn exfat_Fail(#EXFAT_E_NOT_DIR)
      EndIf
      dirFirst = exfat_fileFirst
      dirFlags = exfat_fileFlags
      dirLength = exfat_fileLength
    EndIf
    off = nxt
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatOpen(*path)
  exfat_open = 0
  If exfat_Resolve(*path) = 0
    ProcedureReturn 0
  EndIf
  If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_IS_DIR)
  EndIf
  exfat_filePos = 0
  exfat_open = 1
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatRead(*dst, count.i)
  Define got.i
  If exfat_open = 0
    exfat_error = #EXFAT_E_NO_FILE
    ProcedureReturn -1
  EndIf
  If count < 0
    exfat_error = #EXFAT_E_LENGTH
    ProcedureReturn -1
  EndIf
  If *dst = 0 And count > 0
    exfat_error = #EXFAT_E_NULL
    ProcedureReturn -1
  EndIf
  If count > exfat_fileLength - exfat_filePos
    count = exfat_fileLength - exfat_filePos
  EndIf
  If count <= 0
    ProcedureReturn 0
  EndIf
  ; THE FILE IS DataLength LONG. Bytes past ValidDataLength have never been
  ; written and read as zeros (exFAT specification 7.6.4; forum 906) -
  ; they were cut off here until 2026-09-17.
  got = 0
  If exfat_filePos < exfat_fileValid
    got = exfat_StreamRead(exfat_fileFirst, exfat_fileFlags, exfat_fileValid, exfat_filePos, *dst, count)
    If got < 0
      ProcedureReturn -1
    EndIf
  EndIf
  If got < count
    exfat_Zero(*dst + got, count - got)
    got = count
  EndIf
  exfat_filePos = exfat_filePos + got
  ProcedureReturn got
EndProcedure

Procedure.i ExFatSeek(position.i)
  If exfat_open = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_FILE)
  EndIf
  If position < 0 Or position > exfat_fileLength
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  exfat_filePos = position
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure ExFatClose()
  exfat_open = 0
  exfat_filePos = 0
EndProcedure

; One unbroken run, or nothing. The shared query behind FsExtentOf; see the
; long note on FatExtentOf for why this is answered inside the drivers rather
; than worked out by a caller from their private cluster arithmetic.
;
; exFAT makes the common case free: a stream with the no-FAT-chain flag IS
; contiguous by definition, and its Nth cluster is first + N with no table to
; walk. A stream without that flag is walked like any chain and refused the
; moment it breaks.
Procedure.i ExFatExtentOf(*name, *firstLba, *blocks, *bytes)
  Define cluster.i
  Define following.i
  Define size.i
  Define count.i
  Define n.i
  Define first.i
  Define flags.i
  If ExFatOpen(*name) = 0
    ProcedureReturn 0
  EndIf
  size = exfat_fileLength
  first = exfat_fileFirst
  flags = exfat_fileFlags
  If size < 1 Or exfat_ClusterValid(first) = 0
    ExFatClose()
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  count = (size + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
  If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) = 0
    cluster = first
    For n = 1 To count - 1
      following = exfat_NextCluster(first, cluster, flags, n - 1)
      If following <> cluster + 1 Or exfat_ClusterValid(following) = 0
        ExFatClose()
        ProcedureReturn exfat_Fail(#EXFAT_E_FRAGMENTED)
      EndIf
      cluster = following
    Next
  EndIf
  ; Either way the run must fit inside the cluster heap.
  If exfat_ClusterValid(first + count - 1) = 0
    ExFatClose()
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  ; The public extent uses absolute 512-byte device blocks, just like the
  ; range-reader seam. ClusterSector itself is partition-relative and uses
  ; the volume's logical sector size, which may be larger than 512 bytes.
  If *firstLba <> 0 : PokeI(*firstLba, exfat_partLba + exfat_ClusterSector(first, 0) * exfat_blocksPerSector) : EndIf
  If *blocks <> 0 : PokeI(*blocks, count * exfat_sectorsPerCluster * exfat_blocksPerSector) : EndIf
  If *bytes <> 0 : PokeI(*bytes, size) : EndIf
  ExFatClose()
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatSize()
  If exfat_open = 0
    exfat_Fail(#EXFAT_E_NO_FILE)
    ProcedureReturn 0
  EndIf
  ProcedureReturn exfat_fileLength
EndProcedure

Procedure.i ExFatTell()
  ProcedureReturn exfat_filePos
EndProcedure

Procedure.i ExFatDirOpen(*path)
  Define root.i
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  root = 1
  If *path <> 0
    If PeekA(*path + exfat_PathNext(*path, 0)) <> 0
      root = 0
    EndIf
  EndIf
  If root <> 0
    exfat_dirFirst = exfat_rootCluster
    exfat_dirFlags = 0
    exfat_dirLength = 0
  Else
    If exfat_Resolve(*path) = 0
      ProcedureReturn 0
    EndIf
    If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_DIR)
    EndIf
    exfat_dirFirst = exfat_fileFirst
    exfat_dirFlags = exfat_fileFlags
    exfat_dirLength = exfat_fileLength
  EndIf
  exfat_dirLimit = exfat_DirEntryLimit(exfat_dirFirst, exfat_dirFlags, exfat_dirLength)
  If exfat_dirLimit < 0
    ProcedureReturn 0
  EndIf
  exfat_dirIndex = 0
  exfat_dirEnd = 0
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatDirRewind()
  exfat_dirIndex = 0
  exfat_dirEnd = 0
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatDirNext()
  Define typ.i
  Define secondary.i
  Define checksum.i
  Define expectedHash.i
  Define streamFirst.i
  Define streamLength.i
  If exfat_dirEnd <> 0
    ProcedureReturn 0
  EndIf
  While exfat_dirIndex < exfat_dirLimit
    If exfat_DirRead(exfat_dirFirst, exfat_dirFlags, exfat_dirLength, exfat_dirIndex, @exfat_entry[0]) = 0
      ProcedureReturn -1
    EndIf
    typ = PeekA(@exfat_entry[0])
    If typ = 0
      exfat_dirEnd = 1
      ProcedureReturn 0
    EndIf
    If typ = #EXFAT_ENTRY_FILE
      secondary = PeekA(@exfat_entry[0] + 1)
      If secondary < 2 Or secondary > 18
        exfat_Fail(#EXFAT_E_SET_CHECKSUM)
        ProcedureReturn -1
      EndIf
      checksum = exfat_SetChecksum(exfat_dirFirst, exfat_dirFlags, exfat_dirLength, exfat_dirIndex, secondary)
      If checksum < 0 Or checksum <> exfat_U16(@exfat_entry[0], 2)
        exfat_Fail(#EXFAT_E_SET_CHECKSUM)
        ProcedureReturn -1
      EndIf
      If exfat_DirRead(exfat_dirFirst, exfat_dirFlags, exfat_dirLength, exfat_dirIndex + 1, @exfat_aux[0]) = 0 Or PeekA(@exfat_aux[0]) <> #EXFAT_ENTRY_STREAM
        exfat_Fail(#EXFAT_E_SET_CHECKSUM)
        ProcedureReturn -1
      EndIf
      exfat_dirCurrentNameLength = PeekA(@exfat_aux[0] + 3)
      expectedHash = exfat_U16(@exfat_aux[0], 4)
      streamFirst = exfat_U32(@exfat_aux[0], 20) & $FFFFFFFF
      streamLength = exfat_U64(@exfat_aux[0], 24)
      If streamLength < 0
        ProcedureReturn -1
      EndIf
      If exfat_ReadName(exfat_dirFirst, exfat_dirFlags, exfat_dirLength, exfat_dirIndex, secondary, exfat_dirCurrentNameLength, @exfat_name[0]) = 0
        ProcedureReturn -1
      EndIf
      If exfat_NameHash(@exfat_name[0], exfat_dirCurrentNameLength) <> expectedHash
        exfat_Fail(#EXFAT_E_NAME_HASH)
        ProcedureReturn -1
      EndIf
      exfat_dirCurrentAttr = exfat_U16(@exfat_entry[0], 4)
      exfat_dirCurrentFirst = streamFirst
      exfat_dirCurrentLength = streamLength
      exfat_dirIndex = exfat_dirIndex + secondary + 1
      ProcedureReturn 1
    EndIf
    exfat_dirIndex = exfat_dirIndex + 1
  Wend
  exfat_dirEnd = 1
  ProcedureReturn 0
EndProcedure

Procedure.i ExFatDirNameUtf8(*dst, capacity.i)
  Define i.i
  Define out.i
  Define c.i
  Define cp.i
  Define hi.i
  If *dst = 0 Or capacity <= 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NULL)
  EndIf
  i = 0
  out = 0
  While i < exfat_dirCurrentNameLength
    c = PeekW(@exfat_name[0] + i * 2) & $FFFF
    If c >= $D800 And c <= $DBFF
      If i + 1 >= exfat_dirCurrentNameLength
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF16)
      EndIf
      hi = PeekW(@exfat_name[0] + (i + 1) * 2) & $FFFF
      If hi < $DC00 Or hi > $DFFF
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF16)
      EndIf
      cp = $10000 + ((c & $3FF) << 10) + (hi & $3FF)
      If out + 4 >= capacity
        ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
      EndIf
      PokeA(*dst + out, $F0 | (cp >> 18))
      PokeA(*dst + out + 1, $80 | ((cp >> 12) & $3F))
      PokeA(*dst + out + 2, $80 | ((cp >> 6) & $3F))
      PokeA(*dst + out + 3, $80 | (cp & $3F))
      out = out + 4
      i = i + 2
    ElseIf c < $80
      If out + 1 >= capacity
        ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
      EndIf
      PokeA(*dst + out, c)
      out = out + 1
      i = i + 1
    ElseIf c < $800
      If out + 2 >= capacity
        ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
      EndIf
      PokeA(*dst + out, $C0 | (c >> 6))
      PokeA(*dst + out + 1, $80 | (c & $3F))
      out = out + 2
      i = i + 1
    Else
      If c >= $DC00 And c <= $DFFF
        ProcedureReturn exfat_Fail(#EXFAT_E_UTF16)
      EndIf
      If out + 3 >= capacity
        ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
      EndIf
      PokeA(*dst + out, $E0 | (c >> 12))
      PokeA(*dst + out + 1, $80 | ((c >> 6) & $3F))
      PokeA(*dst + out + 2, $80 | (c & $3F))
      out = out + 3
      i = i + 1
    EndIf
  Wend
  PokeA(*dst + out, 0)
  ProcedureReturn out
EndProcedure

Procedure.i ExFatDirIsDir()
  ProcedureReturn (exfat_dirCurrentAttr & #EXFAT_ATTR_DIRECTORY) <> 0
EndProcedure

Procedure.i ExFatDirSize()
  ProcedureReturn exfat_dirCurrentLength
EndProcedure

Global exfat_parentFirst.i
Global exfat_parentFlags.i
Global exfat_parentLength.i
Global exfat_parentOwnerFirst.i
Global exfat_parentOwnerFlags.i
Global exfat_parentOwnerLength.i
Global exfat_parentSetIndex.i = -1
Global exfat_parentSecondaries.i
Global exfat_parentNameLength.i
Global exfat_parentAttr.i
Global exfat_growFirst.i
Global exfat_growFlags.i

Procedure.i exfat_StreamWriteFixed(first.i, flags.i, allocationLength.i, offset.i, *src, count.i)
  Define run.i
  Define done.i
  Define clusterIndex.i
  Define inCluster.i
  Define sectorIn.i
  Define inSector.i
  Define take.i
  Define cluster.i
  Define sector.i
  If *src = 0 Or count < 0 Or offset < 0 Or offset + count > allocationLength
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  exfat_curIndex = -1
  done = 0
  While done < count
    clusterIndex = (offset + done) / exfat_bytesPerCluster
    inCluster = (offset + done) % exfat_bytesPerCluster
    sectorIn = inCluster / exfat_bytesPerSector
    inSector = inCluster % exfat_bytesPerSector
    cluster = exfat_CursorCluster(first, flags, clusterIndex)
    If cluster < 0
      ProcedureReturn 0
    EndIf
    sector = exfat_ClusterSector(cluster, sectorIn)
    If sector < 0
      ProcedureReturn 0
    EndIf
    If inSector = 0 And count - done >= exfat_bytesPerSector
      ; WHOLE SECTORS are replaced whole: NO READ FIRST, and a run through
      ; clusters that follow one another goes out in one write. The read
      ; before every sector was what made a 16 MiB save take three minutes
      ; (forum 893). Waiting metadata goes first, as for every write.
      run = exfat_RunSectors(first, flags, clusterIndex, cluster, sectorIn, (count - done) / exfat_bytesPerSector)
      If run < 1 Or exfat_FlushMeta() = 0
        ProcedureReturn 0
      EndIf
      If exfat_WriteSectors(sector, run, *src + done) = 0
        ProcedureReturn 0
      EndIf
      done = done + run * exfat_bytesPerSector
    Else
      If exfat_ReadSector(sector, @exfat_sector[0]) = 0
        ProcedureReturn 0
      EndIf
      take = exfat_bytesPerSector - inSector
      If take > count - done
        take = count - done
      EndIf
      exfat_Copy(@exfat_sector[0] + inSector, *src + done, take)
      If exfat_WriteSector(sector, @exfat_sector[0]) = 0
        ProcedureReturn 0
      EndIf
      done = done + take
    EndIf
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_FlushBitmap()
  If exfat_bmpDirty = 0
    ProcedureReturn 1
  EndIf
  exfat_bmpDirty = 0
  If exfat_WriteSectors(exfat_bmpTag, 1, @exfat_bmpSector[0]) = 0
    exfat_bmpTag = -1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; FAT FIRST, BITMAP SECOND: a cluster is owned once its bitmap bit is set, so
; the chain that bit protects must already be on the medium.
Procedure.i exfat_FlushMeta()
  If exfat_FlushFat() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn exfat_FlushBitmap()
EndProcedure

; The bitmap byte for `cluster`: loads its sector into exfat_bmpSector and
; returns the byte's offset in it, or -1. A different sector is loaded only
; after every waiting change has been written (exfat_FlushMeta).
Procedure.i exfat_BitmapByte(cluster.i)
  Define byteOff.i
  Define bc.i
  Define sector.i
  If exfat_ClusterValid(cluster) = 0
    exfat_Fail(#EXFAT_E_CHAIN)
    ProcedureReturn -1
  EndIf
  byteOff = (cluster - 2) >> 3
  If byteOff >= exfat_bitmapLength
    exfat_Fail(#EXFAT_E_BITMAP)
    ProcedureReturn -1
  EndIf
  bc = exfat_StreamCluster(exfat_bitmapCluster, 0, byteOff / exfat_bytesPerCluster)
  If bc < 0
    ProcedureReturn -1
  EndIf
  sector = exfat_ClusterSector(bc, (byteOff % exfat_bytesPerCluster) / exfat_bytesPerSector)
  If sector < 0
    ProcedureReturn -1
  EndIf
  If exfat_bmpTag <> sector
    If exfat_FlushMeta() = 0
      ProcedureReturn -1
    EndIf
    exfat_bmpTag = -1
    If exfat_ReadSectors(sector, 1, @exfat_bmpSector[0]) = 0
      ProcedureReturn -1
    EndIf
    exfat_bmpTag = sector
  EndIf
  ProcedureReturn (byteOff % exfat_bytesPerCluster) % exfat_bytesPerSector
EndProcedure

Procedure.i exfat_BitmapGet(cluster.i)
  Define at.i
  at = exfat_BitmapByte(cluster)
  If at < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn (exfat_bmpSector[at] >> ((cluster - 2) & 7)) & 1
EndProcedure

Procedure.i exfat_BitmapSet(cluster.i, used.i)
  Define bit.i
  Define byteOff.i
  Define b.i
  If exfat_ClusterValid(cluster) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  bit = cluster - 2
  byteOff = exfat_BitmapByte(cluster)
  If byteOff < 0
    ProcedureReturn 0
  EndIf
  b = exfat_bmpSector[byteOff]
  If used <> 0
    b = b | (1 << (bit & 7))
  Else
    b = b & ~(1 << (bit & 7))
  EndIf
  exfat_bmpSector[byteOff] = b & $FF
  exfat_bmpDirty = 1
  exfat_allocChanged = 1
  If exfat_freeClusters >= 0
    If used <> 0
      exfat_freeClusters = exfat_freeClusters - 1
    Else
      exfat_freeClusters = exfat_freeClusters + 1
    EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

; THE MAIN BOOT SECTOR ONLY. The Backup Boot Region exists to rescue a
; volume whose main region is damaged, and the specification says
; implementations should not modify it (section 3) and must treat its
; VolumeFlags and PercentInUse as stale (3.1.13, 3.1.18). Until 2026-09-17
; every dirty mark was written into both regions (forum 903).
;
; PERCENTINUSE (3.1.18) must follow the allocation or read FFh. It is set
; when the volume is marked clean after the allocation changed: the true
; percentage when the free count is known, FFh when it is not (forum 904).
Procedure.i exfat_SetVolumeDirty(dirty.i)
  Define flags.i
  Define used.i
  If *exfat_writer = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_WRITER)
  EndIf
  flags = exfat_volumeFlags
  If dirty <> 0
    flags = flags | 2
  Else
    flags = flags & ~$0002
  EndIf
  ; ClearToZero is mandatory before any filesystem modification.
  flags = flags & ~$0008
  If exfat_ReadSector(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  exfat_Put16(@exfat_sector[0], 106, flags)
  If dirty = 0 And exfat_allocChanged <> 0
    If exfat_freeClusters >= 0 And exfat_clusterCount > 0
      used = exfat_clusterCount - exfat_freeClusters
      PokeA(@exfat_sector[0] + 112, (used * 100) / exfat_clusterCount)
    Else
      PokeA(@exfat_sector[0] + 112, $FF)
    EndIf
  EndIf
  If exfat_WriteSector(0, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  exfat_volumeFlags = flags
  exfat_dirty = dirty
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_BeginMutation()
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  If *exfat_writer = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_WRITER)
  EndIf
  ; NumberOfFats=2 denotes TexFAT. Reading the selected active copy is safe,
  ; but changing it without the transaction descriptors is not.
  If exfat_texfat <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_TEXFAT)
  EndIf
  If exfat_mediaFailure <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_MEDIA_FAILURE)
  EndIf
  If exfat_inheritedDirty <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_DIRTY)
  EndIf
  If exfat_dirty = 0
    ProcedureReturn exfat_SetVolumeDirty(1)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_ZeroCluster(cluster.i)
  Define sec.i
  Define sector.i
  exfat_Zero(@exfat_sector[0], exfat_bytesPerSector)
  sec = 0
  While sec < exfat_sectorsPerCluster
    sector = exfat_ClusterSector(cluster, sec)
    If sector < 0 Or exfat_WriteSector(sector, @exfat_sector[0]) = 0
      ProcedureReturn 0
    EndIf
    sec = sec + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ZERO IS 1 ONLY FOR A DIRECTORY CLUSTER. A directory is read until an
; end-of-directory entry, so a new one must not hold a deleted file's bytes.
; A FILE's new clusters are not zeroed: a write covers every byte it makes
; valid, a grow leaves ValidDataLength where it is so the new bytes read as
; zeros (7.6.4), and a write that starts past ValidDataLength zeros the gap
; itself. Until 2026-09-17 every file cluster was zeroed a sector at a time
; and then overwritten - 256 wasted writes per cluster on the boot stick
; (forum 893).
Procedure.i exfat_AllocateOne(zero.i)
  Define pass.i
  Define cluster.i
  Define used.i
  pass = 0
  cluster = exfat_allocHint
  If cluster < 2 Or cluster > exfat_clusterCount + 1
    cluster = 2
  EndIf
  While pass < exfat_clusterCount
    used = exfat_BitmapGet(cluster)
    If used < 0
      ProcedureReturn 0
    EndIf
    If used = 0
      ; FAT and initialized data precede the allocation bitmap. Until the
      ; bitmap bit is set the cluster remains unowned after a power loss.
      If exfat_SetFatEntry(cluster, #EXFAT_EOC) = 0
        ProcedureReturn 0
      EndIf
      If zero <> 0
        If exfat_ZeroCluster(cluster) = 0
          exfat_SetFatEntry(cluster, 0)
          ProcedureReturn 0
        EndIf
      EndIf
      If exfat_BitmapSet(cluster, 1) = 0
        exfat_SetFatEntry(cluster, 0)
        ProcedureReturn 0
      EndIf
      exfat_allocHint = cluster + 1
      If exfat_allocHint > exfat_clusterCount + 1
        exfat_allocHint = 2
      EndIf
      ProcedureReturn cluster
    EndIf
    cluster = cluster + 1
    If cluster > exfat_clusterCount + 1
      cluster = 2
    EndIf
    pass = pass + 1
  Wend
  ProcedureReturn exfat_Fail(#EXFAT_E_NO_SPACE)
EndProcedure

Procedure.i exfat_MaterializeContiguous(first.i, count.i)
  Define i.i
  Define value.i
  If count <= 0
    ProcedureReturn 1
  EndIf
  i = 0
  While i < count
    If i + 1 < count
      value = first + i + 1
    Else
      value = #EXFAT_EOC
    EndIf
    If exfat_SetFatEntry(first + i, value) = 0
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Validate the complete allocation before any mutation uses it. A declared
; length and a shorter, longer, looping, or bitmap-free chain is corruption;
; discovering that only after clusters were released would damage neighbors.
Procedure.i exfat_ValidateAllocation(first.i, flags.i, length.i)
  Define count.i
  Define i.i
  Define current.i
  Define nxt.i
  Define used.i
  If length = 0
    If first <> 0
      ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
    EndIf
    ProcedureReturn 1
  EndIf
  count = (length + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
  If count < 1 Or count > exfat_clusterCount Or exfat_ClusterValid(first) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  current = first
  i = 0
  While i < count
    If exfat_ClusterValid(current) = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
    EndIf
    used = exfat_BitmapGet(current)
    If used < 0
      ProcedureReturn 0
    EndIf
    If used = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_BITMAP)
    EndIf
    If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
      current = current + 1
    Else
      nxt = exfat_FatEntry(current)
      If nxt < 0
        ProcedureReturn 0
      EndIf
      If i + 1 = count
        If nxt < $FFFFFFF8
          ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
        EndIf
      ElseIf exfat_ClusterValid(nxt) = 0
        ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
      EndIf
      current = nxt
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; Give back `count` clusters of a FAT chain starting at `start` that an
; extension claimed and never published, keeping the reported failure.
Procedure exfat_ReleaseClaimed(start.i, count.i)
  Define keep.i
  keep = exfat_error
  exfat_error = #EXFAT_OK
  If start <> 0 And count > 0
    exfat_FreeAllocation(start, #EXFAT_STREAM_ALLOC_POSSIBLE, count * exfat_bytesPerCluster)
  EndIf
  exfat_error = keep
EndProcedure

; Make the stream hold enough clusters for newLength. A failure part way -
; the volume filling up is the usual one - gives back every cluster this
; call claimed and restores the old end of chain, so the entry set's
; DataLength and the allocation still agree and the file can still be
; removed (forum 907). Nothing is published here; the caller writes the
; entry set once the data is in place.
; zero: 1 for a directory stream, 0 for a file - see exfat_AllocateOne.
; What was claimed waits in the FAT and bitmap buffers; the first data run or
; sector written into it puts them on the medium first (exfat_FlushMeta).
Procedure.i exfat_EnsureClusters(first.i, flags.i, oldLength.i, newLength.i, zero.i)
  Define have.i
  Define need.i
  Define last.i
  Define oldLast.i
  Define nxt.i
  Define i.i
  Define newStart.i
  Define keep.i
  Define claimed.i
  Define count.i
  exfat_growFirst = first
  exfat_growFlags = flags
  have = (oldLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
  need = (newLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
  If need <= have
    ProcedureReturn 1
  EndIf
  If have > 0 And exfat_ValidateAllocation(first, flags, oldLength) = 0
    ProcedureReturn 0
  EndIf
  If exfat_BeginMutation() = 0
    ProcedureReturn 0
  EndIf
  oldLast = 0
  newStart = 0
  claimed = 0
  count = have
  If have = 0
    first = exfat_AllocateOne(zero)
    If first = 0
      ProcedureReturn 0
    EndIf
    exfat_growFirst = first
    exfat_growFlags = #EXFAT_STREAM_ALLOC_POSSIBLE
    newStart = first
    claimed = 1
    count = 1
  Else
    If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
      If exfat_MaterializeContiguous(first, have) = 0
        ProcedureReturn 0
      EndIf
      exfat_growFlags = flags & ~#EXFAT_STREAM_NO_FAT_CHAIN
    EndIf
  EndIf
  last = exfat_StreamCluster(exfat_growFirst, exfat_growFlags, count - 1)
  If last < 0
    exfat_ReleaseClaimed(newStart, claimed)
    ProcedureReturn 0
  EndIf
  If have > 0
    oldLast = last
  EndIf
  While count < need
    nxt = exfat_AllocateOne(zero)
    If nxt = 0
      Break
    EndIf
    If exfat_SetFatEntry(last, nxt) = 0
      keep = exfat_error
      exfat_error = #EXFAT_OK
      exfat_SetFatEntry(nxt, 0)
      exfat_BitmapSet(nxt, 0)
      exfat_error = keep
      Break
    EndIf
    If newStart = 0
      newStart = nxt
    EndIf
    last = nxt
    count = count + 1
    claimed = claimed + 1
  Wend
  If count < need
    ; Roll back: cut the old chain where it ended, then free the claim.
    If oldLast <> 0
      keep = exfat_error
      exfat_error = #EXFAT_OK
      exfat_SetFatEntry(oldLast, #EXFAT_EOC)
      exfat_error = keep
    EndIf
    exfat_ReleaseClaimed(newStart, claimed)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_FreeAllocation(first.i, flags.i, length.i)
  Define count.i
  Define current.i
  Define nxt.i
  Define i.i
  If length = 0 Or first = 0
    ProcedureReturn 1
  EndIf
  If exfat_ValidateAllocation(first, flags, length) = 0
    ProcedureReturn 0
  EndIf
  count = (length + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
  current = first
  i = 0
  While i < count
    If exfat_ClusterValid(current) = 0 Or i >= exfat_clusterCount
      ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
    EndIf
    If (flags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
      nxt = current + 1
    Else
      nxt = exfat_FatEntry(current)
      If nxt < 0
        ProcedureReturn 0
      EndIf
    EndIf
    If exfat_SetFatEntry(current, 0) = 0 Or exfat_BitmapSet(current, 0) = 0
      ProcedureReturn 0
    EndIf
    current = nxt
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_DirWrite(first.i, flags.i, length.i, index.i, *src)
  Define allocation.i
  If length = 0
    allocation = exfat_clusterCount * exfat_bytesPerCluster
  Else
    allocation = length
  EndIf
  ProcedureReturn exfat_StreamWriteFixed(first, flags, allocation, index * 32, *src, 32)
EndProcedure

; The sector and offset of directory entry `index` of a directory stream.
; Sets exfat_entSector / exfat_entOffset; 0 on failure.
Global exfat_entSector.i
Global exfat_entOffset.i
Procedure.i exfat_EntryLocation(first.i, flags.i, index.i)
  Define byteOff.i
  Define cluster.i
  byteOff = index * 32
  cluster = exfat_StreamCluster(first, flags, byteOff / exfat_bytesPerCluster)
  If cluster < 0
    ProcedureReturn 0
  EndIf
  exfat_entSector = exfat_ClusterSector(cluster, (byteOff % exfat_bytesPerCluster) / exfat_bytesPerSector)
  If exfat_entSector < 0
    ProcedureReturn 0
  EndIf
  exfat_entOffset = (byteOff % exfat_bytesPerCluster) % exfat_bytesPerSector
  ProcedureReturn 1
EndProcedure

; THE SET IS REWRITTEN IN MEMORY AND EACH SECTOR IS WRITTEN ONCE (forum 909).
; The file and stream entries are almost always in the same sector, and then
; the new size, cluster, time and checksum reach the medium in ONE write: a
; power cut leaves the old set or the new one, never a set whose checksum
; disagrees with its entries. When the two straddle a sector boundary the
; stream sector goes first and the file entry, carrying the checksum, last.
Global Dim exfat_setBuf.a[19 * 32]
Procedure.i exfat_UpdateEntrySet(parentFirst.i, parentFlags.i, parentLength.i, setIndex.i, secondary.i, newFirst.i, newFlags.i, validLength.i, dataLength.i, attr.i)
  Define checksum.i
  Define e.i
  Define b.i
  Define primarySector.i
  Define primaryOffset.i
  If secondary < 1 Or secondary > 18
    ProcedureReturn exfat_Fail(#EXFAT_E_SET_CHECKSUM)
  EndIf
  e = 0
  While e <= secondary
    If exfat_DirRead(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_setBuf[0] + e * 32) = 0
      ProcedureReturn 0
    EndIf
    e = e + 1
  Wend
  exfat_Put16(@exfat_setBuf[0], 4, attr)
  exfat_Put16(@exfat_setBuf[0], 12, exfat_time)
  exfat_Put16(@exfat_setBuf[0], 14, exfat_date)
  exfat_Put16(@exfat_setBuf[0], 16, exfat_time)
  exfat_Put16(@exfat_setBuf[0], 18, exfat_date)
  PokeA(@exfat_setBuf[0] + 21, exfat_time10ms)
  PokeA(@exfat_setBuf[0] + 23, exfat_utcOffset)
  PokeA(@exfat_setBuf[0] + 24, exfat_utcOffset)
  PokeA(@exfat_setBuf[0] + 32 + 1, newFlags)
  exfat_Put64(@exfat_setBuf[0] + 32, 8, validLength)
  exfat_Put32(@exfat_setBuf[0] + 32, 20, newFirst)
  exfat_Put64(@exfat_setBuf[0] + 32, 24, dataLength)
  checksum = 0
  e = 0
  While e <= secondary
    b = 0
    While b < 32
      If e <> 0 Or (b <> 2 And b <> 3)
        checksum = (exfat_Ror16(checksum) + PeekA(@exfat_setBuf[0] + e * 32 + b)) & $FFFF
      EndIf
      b = b + 1
    Wend
    e = e + 1
  Wend
  exfat_Put16(@exfat_setBuf[0], 2, checksum)
  If exfat_EntryLocation(parentFirst, parentFlags, setIndex) = 0
    ProcedureReturn 0
  EndIf
  primarySector = exfat_entSector
  primaryOffset = exfat_entOffset
  If exfat_EntryLocation(parentFirst, parentFlags, setIndex + 1) = 0
    ProcedureReturn 0
  EndIf
  If exfat_entSector <> primarySector
    If exfat_ReadSector(exfat_entSector, @exfat_sector[0]) = 0
      ProcedureReturn 0
    EndIf
    exfat_Copy(@exfat_sector[0] + exfat_entOffset, @exfat_setBuf[0] + 32, 32)
    If exfat_WriteSector(exfat_entSector, @exfat_sector[0]) = 0
      ProcedureReturn 0
    EndIf
  EndIf
  If exfat_ReadSector(primarySector, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  exfat_Copy(@exfat_sector[0] + primaryOffset, @exfat_setBuf[0], 32)
  If exfat_entSector = primarySector
    exfat_Copy(@exfat_sector[0] + exfat_entOffset, @exfat_setBuf[0] + 32, 32)
  EndIf
  ProcedureReturn exfat_WriteSector(primarySector, @exfat_sector[0])
EndProcedure

Procedure.i exfat_UpdateOpen()
  If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) = 0
    exfat_fileAttr = exfat_fileAttr | #EXFAT_ATTR_ARCHIVE
  EndIf
  ProcedureReturn exfat_UpdateEntrySet(exfat_fileParent, exfat_fileParentFlags, exfat_fileParentLength, exfat_fileSetIndex, exfat_fileSecondaries, exfat_fileFirst, exfat_fileFlags, exfat_fileValid, exfat_fileLength, exfat_fileAttr)
EndProcedure

; EVERY WRITE MARKS THE VOLUME DIRTY FIRST, including one that needs no new
; cluster (forum 902: an overwrite, or an append inside the last cluster,
; used to skip both the dirty mark and the refusal of a volume that was
; already dirty). A write that starts beyond ValidDataLength zeros the gap
; first, so the bytes it makes valid were really written (forum 906).
Procedure.i ExFatWrite(*src, count.i)
  Define endPos.i
  Define oldLength.i
  Define gap.i
  Define take.i
  Define allocation.i
  If exfat_open = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_FILE)
  EndIf
  If (exfat_fileAttr & #EXFAT_ATTR_READ_ONLY) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_READ_ONLY)
  EndIf
  If count < 0 Or *src = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_LENGTH)
  EndIf
  If count = 0
    ProcedureReturn 0
  EndIf
  endPos = exfat_filePos + count
  If endPos < exfat_filePos
    ProcedureReturn exfat_Fail(#EXFAT_E_BOUNDS)
  EndIf
  If exfat_BeginMutation() = 0
    ProcedureReturn -1
  EndIf
  oldLength = exfat_fileLength
  If exfat_EnsureClusters(exfat_fileFirst, exfat_fileFlags, oldLength, endPos, 0) = 0
    ProcedureReturn -1
  EndIf
  exfat_fileFirst = exfat_growFirst
  exfat_fileFlags = exfat_growFlags
  allocation = ((endPos + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster) * exfat_bytesPerCluster
  If allocation < ((oldLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster) * exfat_bytesPerCluster
    allocation = ((oldLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster) * exfat_bytesPerCluster
  EndIf
  If exfat_filePos > exfat_fileValid
    exfat_Zero(@exfat_aux[0], exfat_bytesPerSector)
    gap = exfat_fileValid
    While gap < exfat_filePos
      take = exfat_filePos - gap
      If take > exfat_bytesPerSector
        take = exfat_bytesPerSector
      EndIf
      If exfat_StreamWriteFixed(exfat_fileFirst, exfat_fileFlags, allocation, gap, @exfat_aux[0], take) = 0
        ProcedureReturn -1
      EndIf
      gap = gap + take
    Wend
  EndIf
  If exfat_StreamWriteFixed(exfat_fileFirst, exfat_fileFlags, allocation, exfat_filePos, *src, count) = 0
    ProcedureReturn -1
  EndIf
  exfat_filePos = endPos
  If endPos > exfat_fileLength
    exfat_fileLength = endPos
  EndIf
  If endPos > exfat_fileValid
    exfat_fileValid = endPos
  EndIf
  If exfat_UpdateOpen() = 0
    ProcedureReturn -1
  EndIf
  exfat_error = #EXFAT_OK
  ProcedureReturn count
EndProcedure

Procedure.i ExFatTruncate(newLength.i)
  Define oldClusters.i
  Define newClusters.i
  Define keep.i
  Define cut.i
  Define tail.i
  Define tailLength.i
  Define oldFirst.i
  Define oldFlags.i
  Define oldLength.i
  Define oldValid.i
  If exfat_open = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NO_FILE)
  EndIf
  If newLength < 0
    ProcedureReturn exfat_Fail(#EXFAT_E_LENGTH)
  EndIf
  If (exfat_fileAttr & #EXFAT_ATTR_READ_ONLY) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_READ_ONLY)
  EndIf
  oldFirst = exfat_fileFirst
  oldFlags = exfat_fileFlags
  oldLength = exfat_fileLength
  oldValid = exfat_fileValid
  If newLength = oldLength
    exfat_error = #EXFAT_OK
    ProcedureReturn 1
  EndIf
  ; Every length change marks the volume dirty first, whether or not it
  ; allocates (forum 902).
  If exfat_BeginMutation() = 0
    ProcedureReturn 0
  EndIf
  If newLength > exfat_fileLength
    If exfat_EnsureClusters(exfat_fileFirst, exfat_fileFlags, exfat_fileLength, newLength, 0) = 0
      ProcedureReturn 0
    EndIf
    exfat_fileFirst = exfat_growFirst
    exfat_fileFlags = exfat_growFlags
    ; GROWING LEAVES ValidDataLength WHERE IT IS. The new bytes lie past it,
    ; so they read as zeros (7.6.4) without a single data sector written;
    ; a later write past them zeros the gap it makes valid.
    exfat_fileLength = newLength
    If exfat_filePos > newLength
      exfat_filePos = newLength
    EndIf
    ProcedureReturn exfat_UpdateOpen()
  ElseIf newLength < exfat_fileLength
    oldClusters = (exfat_fileLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
    newClusters = (newLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster
    If newClusters = 0
      If exfat_ValidateAllocation(oldFirst, oldFlags, oldLength) = 0
        ProcedureReturn 0
      EndIf
      exfat_fileFirst = 0
      exfat_fileFlags = #EXFAT_STREAM_ALLOC_POSSIBLE
      exfat_fileLength = 0
      exfat_fileValid = 0
      exfat_filePos = 0
      ; Publish the shorter object first. A power loss after this point may
      ; leak allocation, but can never leave the file pointing into freed
      ; clusters.
      If exfat_UpdateOpen() = 0
        exfat_fileFirst = oldFirst
        exfat_fileFlags = oldFlags
        exfat_fileLength = oldLength
        exfat_fileValid = oldValid
        ProcedureReturn 0
      EndIf
      If exfat_FreeAllocation(oldFirst, oldFlags, oldLength) = 0
        ProcedureReturn 0
      EndIf
      exfat_error = #EXFAT_OK
      ProcedureReturn 1
    ElseIf newClusters < oldClusters
      If exfat_ValidateAllocation(oldFirst, oldFlags, oldLength) = 0
        ProcedureReturn 0
      EndIf
      keep = exfat_StreamCluster(oldFirst, oldFlags, newClusters - 1)
      If keep < 0
        ProcedureReturn 0
      EndIf
      If (oldFlags & #EXFAT_STREAM_NO_FAT_CHAIN) <> 0
        tail = oldFirst + newClusters
      Else
        tail = exfat_FatEntry(keep)
        If tail < 0
          ProcedureReturn 0
        EndIf
      EndIf
      exfat_fileLength = newLength
      exfat_fileValid = oldValid
      If exfat_fileValid > newLength
        exfat_fileValid = newLength
      EndIf
      If exfat_filePos > newLength
        exfat_filePos = newLength
      EndIf
      ; As with full truncation, shorten the directory entry before making
      ; any cluster free. This is the deletion ordering required by exFAT.
      If exfat_UpdateOpen() = 0
        exfat_fileLength = oldLength
        exfat_fileValid = oldValid
        ProcedureReturn 0
      EndIf
      If (oldFlags & #EXFAT_STREAM_NO_FAT_CHAIN) = 0
        If exfat_SetFatEntry(keep, #EXFAT_EOC) = 0
          ProcedureReturn 0
        EndIf
      EndIf
      If exfat_FreeAllocation(tail, oldFlags, (oldClusters - newClusters) * exfat_bytesPerCluster) = 0
        ProcedureReturn 0
      EndIf
      exfat_error = #EXFAT_OK
      ProcedureReturn 1
    EndIf
  EndIf
  ; Shorter within the same cluster count: nothing is freed.
  exfat_fileLength = newLength
  If exfat_fileValid > newLength
    exfat_fileValid = newLength
  EndIf
  If exfat_filePos > newLength
    exfat_filePos = newLength
  EndIf
  ProcedureReturn exfat_UpdateOpen()
EndProcedure

Procedure.i exfat_AllocationBytes(first.i, flags.i, declaredLength.i)
  Define count.i
  Define current.i
  Define nxt.i
  If declaredLength > 0
    ProcedureReturn ((declaredLength + exfat_bytesPerCluster - 1) / exfat_bytesPerCluster) * exfat_bytesPerCluster
  EndIf
  If exfat_ClusterValid(first) = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
  EndIf
  current = first
  count = 1
  While count <= exfat_clusterCount
    nxt = exfat_NextCluster(first, current, flags, count - 1)
    If nxt = 0
      ProcedureReturn count * exfat_bytesPerCluster
    EndIf
    If nxt < 0
      ProcedureReturn 0
    EndIf
    current = nxt
    count = count + 1
  Wend
  ProcedureReturn exfat_Fail(#EXFAT_E_CHAIN)
EndProcedure

Procedure.i exfat_ResolveParent(*path, forbiddenAncestor.i)
  Define off.i
  Define nxt.i
  Define len.i
  Define dirFirst.i
  Define dirFlags.i
  Define dirLength.i
  Define ownerFirst.i
  Define ownerFlags.i
  Define ownerLength.i
  Define ownerSet.i
  Define ownerSecondaries.i
  Define ownerNameLength.i
  Define ownerAttr.i
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  If *path = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  off = exfat_PathNext(*path, 0)
  dirFirst = exfat_rootCluster
  dirFlags = 0
  dirLength = 0
  ownerFirst = 0
  ownerSet = -1
  If forbiddenAncestor <> 0 And dirFirst = forbiddenAncestor
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  While PeekA(*path + off) <> 0
    len = exfat_Utf8Name(*path + off, @exfat_want[0], #EXFAT_MAX_NAME)
    If len <= 0
      ProcedureReturn 0
    EndIf
    nxt = exfat_PathAfterSegment(*path, off)
    If PeekA(*path + nxt) = 0
      exfat_wantLength = len
      exfat_parentFirst = dirFirst
      exfat_parentFlags = dirFlags
      exfat_parentLength = dirLength
      exfat_parentOwnerFirst = ownerFirst
      exfat_parentOwnerFlags = ownerFlags
      exfat_parentOwnerLength = ownerLength
      exfat_parentSetIndex = ownerSet
      exfat_parentSecondaries = ownerSecondaries
      exfat_parentNameLength = ownerNameLength
      exfat_parentAttr = ownerAttr
      ProcedureReturn 1
    EndIf
    If exfat_FindInDir(dirFirst, dirFlags, dirLength, @exfat_want[0], len) = 0
      ProcedureReturn 0
    EndIf
    If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_DIR)
    EndIf
    ownerFirst = exfat_fileParent
    ownerFlags = exfat_fileParentFlags
    ownerLength = exfat_fileParentLength
    ownerSet = exfat_fileSetIndex
    ownerSecondaries = exfat_fileSecondaries
    ownerNameLength = exfat_fileNameLength
    ownerAttr = exfat_fileAttr
    dirFirst = exfat_fileFirst
    dirFlags = exfat_fileFlags
    dirLength = exfat_fileLength
    If forbiddenAncestor <> 0 And dirFirst = forbiddenAncestor
      ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
    EndIf
    off = nxt
  Wend
  ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
EndProcedure

Procedure.i exfat_FindFreeRun(first.i, flags.i, length.i, needed.i)
  Define allocation.i
  Define entries.i
  Define index.i
  Define run.i
  Define start.i
  Define typ.i
  allocation = exfat_AllocationBytes(first, flags, length)
  If allocation <= 0
    ProcedureReturn -1
  EndIf
  entries = allocation / 32
  index = 0
  run = 0
  start = 0
  While index < entries
    If exfat_DirRead(first, flags, allocation, index, @exfat_aux[0]) = 0
      ProcedureReturn -1
    EndIf
    typ = PeekA(@exfat_aux[0])
    If typ = 0 Or (typ & $80) = 0
      If run = 0
        start = index
      EndIf
      run = run + 1
      If run >= needed
        ProcedureReturn start
      EndIf
    Else
      run = 0
    EndIf
    index = index + 1
  Wend
  ProcedureReturn -1
EndProcedure

Procedure.i exfat_GrowParentDirectory()
  Define oldAllocation.i
  Define newAllocation.i
  oldAllocation = exfat_AllocationBytes(exfat_parentFirst, exfat_parentFlags, exfat_parentLength)
  If oldAllocation <= 0
    ProcedureReturn 0
  EndIf
  newAllocation = oldAllocation + exfat_bytesPerCluster
  If exfat_EnsureClusters(exfat_parentFirst, exfat_parentFlags, oldAllocation, newAllocation, 1) = 0
    ProcedureReturn 0
  EndIf
  exfat_parentFirst = exfat_growFirst
  exfat_parentFlags = exfat_growFlags
  If exfat_parentSetIndex >= 0
    If exfat_UpdateEntrySet(exfat_parentOwnerFirst, exfat_parentOwnerFlags, exfat_parentOwnerLength, exfat_parentSetIndex, exfat_parentSecondaries, exfat_parentFirst, exfat_parentFlags, newAllocation, newAllocation, exfat_parentAttr) = 0
      ProcedureReturn 0
    EndIf
    exfat_parentLength = newAllocation
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i exfat_PrimaryChecksum(*primary, parentFirst.i, parentFlags.i, parentLength.i, setIndex.i, secondary.i)
  Define sum.i
  Define b.i
  Define e.i
  sum = 0
  b = 0
  While b < 32
    If b <> 2 And b <> 3
      sum = (exfat_Ror16(sum) + PeekA(*primary + b)) & $FFFF
    EndIf
    b = b + 1
  Wend
  e = 1
  While e <= secondary
    If exfat_DirRead(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_aux[0]) = 0
      ProcedureReturn -1
    EndIf
    b = 0
    While b < 32
      sum = (exfat_Ror16(sum) + PeekA(@exfat_aux[0] + b)) & $FFFF
      b = b + 1
    Wend
    e = e + 1
  Wend
  ProcedureReturn sum
EndProcedure

; A NEW ENTRY SET IS ASSEMBLED IN MEMORY AND PLACED SECTOR BY SECTOR (forum
; 914). The file entry carries the checksum of the whole set, so it must
; reach the medium no earlier than the entries it covers; and nothing in use
; may ever sit after an end-of-directory marker (specification 6.2.1.1),
; which is what the file entry's slot often still is.
;
;   * a set that fits one sector - nearly every set - is ONE write: the old
;     slots or the complete new set, nothing in between
;   * a set that spans sectors first marks the file entry's slot unused-but-
;     not-end (type 05h), then writes the other sectors, then writes the
;     real file entry. Every state in between is at worst stream and name
;     entries with no file entry before them, which every reader skips and a
;     repair tool clears.
Procedure.i exfat_WriteNewSet(parentFirst.i, parentFlags.i, parentLength.i, setIndex.i, *name, nameLength.i, attr.i, first.i, streamFlags.i, validLength.i, dataLength.i, *primaryTemplate)
  Define nameEntries.i
  Define secondary.i
  Define hash.i
  Define e.i
  Define j.i
  Define n.i
  Define b.i
  Define checksum.i
  Define *d
  Define primarySector.i
  Define primaryOffset.i
  Define multi.i
  Define cur.i
  nameEntries = (nameLength + 14) / 15
  secondary = 1 + nameEntries
  If secondary > 18
    ProcedureReturn exfat_Fail(#EXFAT_E_PATH)
  EndIf
  hash = exfat_NameHash(*name, nameLength)
  If hash < 0
    ProcedureReturn 0
  EndIf
  exfat_Zero(@exfat_setBuf[0], (secondary + 1) * 32)
  ; the file entry
  *d = @exfat_setBuf[0]
  If *primaryTemplate <> 0
    exfat_Copy(*d, *primaryTemplate, 32)
  EndIf
  PokeA(*d, #EXFAT_ENTRY_FILE)
  PokeA(*d + 1, secondary)
  exfat_Put16(*d, 4, attr)
  If *primaryTemplate = 0
    exfat_Put16(*d, 8, exfat_time)
    exfat_Put16(*d, 10, exfat_date)
    exfat_Put16(*d, 12, exfat_time)
    exfat_Put16(*d, 14, exfat_date)
    exfat_Put16(*d, 16, exfat_time)
    exfat_Put16(*d, 18, exfat_date)
    PokeA(*d + 20, exfat_time10ms)
    PokeA(*d + 21, exfat_time10ms)
    PokeA(*d + 22, exfat_utcOffset)
    PokeA(*d + 23, exfat_utcOffset)
    PokeA(*d + 24, exfat_utcOffset)
  EndIf
  ; the stream extension
  *d = @exfat_setBuf[0] + 32
  PokeA(*d, #EXFAT_ENTRY_STREAM)
  PokeA(*d + 1, streamFlags | #EXFAT_STREAM_ALLOC_POSSIBLE)
  PokeA(*d + 3, nameLength)
  exfat_Put16(*d, 4, hash)
  exfat_Put64(*d, 8, validLength)
  exfat_Put32(*d, 20, first)
  exfat_Put64(*d, 24, dataLength)
  ; the file name entries
  n = 0
  e = 0
  While e < nameEntries
    *d = @exfat_setBuf[0] + (2 + e) * 32
    PokeA(*d, #EXFAT_ENTRY_NAME)
    j = 0
    While j < 15
      If n < nameLength
        exfat_Put16(*d, 2 + j * 2, PeekW(*name + n * 2) & $FFFF)
        n = n + 1
      EndIf
      j = j + 1
    Wend
    e = e + 1
  Wend
  checksum = 0
  e = 0
  While e <= secondary
    b = 0
    While b < 32
      If e <> 0 Or (b <> 2 And b <> 3)
        checksum = (exfat_Ror16(checksum) + PeekA(@exfat_setBuf[0] + e * 32 + b)) & $FFFF
      EndIf
      b = b + 1
    Wend
    e = e + 1
  Wend
  exfat_Put16(@exfat_setBuf[0], 2, checksum)

  If exfat_EntryLocation(parentFirst, parentFlags, setIndex) = 0
    ProcedureReturn 0
  EndIf
  primarySector = exfat_entSector
  primaryOffset = exfat_entOffset
  If exfat_EntryLocation(parentFirst, parentFlags, setIndex + secondary) = 0
    ProcedureReturn 0
  EndIf
  multi = Bool(exfat_entSector <> primarySector)

  ; 1. the file entry's own sector: every set entry that shares it, and the
  ;    file entry itself only when the whole set is in this sector
  If exfat_ReadSector(primarySector, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  e = 0
  While e <= secondary
    If exfat_EntryLocation(parentFirst, parentFlags, setIndex + e) = 0
      ProcedureReturn 0
    EndIf
    If exfat_entSector = primarySector
      exfat_Copy(@exfat_sector[0] + exfat_entOffset, @exfat_setBuf[0] + e * 32, 32)
    EndIf
    e = e + 1
  Wend
  If multi <> 0
    PokeA(@exfat_sector[0] + primaryOffset, $05)
  EndIf
  If exfat_WriteSector(primarySector, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  If multi = 0
    ProcedureReturn 1
  EndIf
  ; 2. the other sectors, in order
  cur = -1
  e = 1
  While e <= secondary
    If exfat_EntryLocation(parentFirst, parentFlags, setIndex + e) = 0
      ProcedureReturn 0
    EndIf
    If exfat_entSector <> primarySector
      If exfat_entSector <> cur
        If cur >= 0
          If exfat_WriteSector(cur, @exfat_aux[0]) = 0
            ProcedureReturn 0
          EndIf
        EndIf
        cur = exfat_entSector
        If exfat_ReadSector(cur, @exfat_aux[0]) = 0
          ProcedureReturn 0
        EndIf
      EndIf
      exfat_Copy(@exfat_aux[0] + exfat_entOffset, @exfat_setBuf[0] + e * 32, 32)
    EndIf
    e = e + 1
  Wend
  If cur >= 0
    If exfat_WriteSector(cur, @exfat_aux[0]) = 0
      ProcedureReturn 0
    EndIf
  EndIf
  ; 3. the real file entry, last
  If exfat_ReadSector(primarySector, @exfat_sector[0]) = 0
    ProcedureReturn 0
  EndIf
  exfat_Copy(@exfat_sector[0] + primaryOffset, @exfat_setBuf[0], 32)
  ProcedureReturn exfat_WriteSector(primarySector, @exfat_sector[0])
EndProcedure

Procedure.i exfat_CreateCommon(*path, attr.i)
  Define slot.i
  Define first.i
  Define length.i
  Define needed.i
  If exfat_ResolveParent(*path, 0) = 0
    ProcedureReturn 0
  EndIf
  If exfat_FindInDir(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, @exfat_want[0], exfat_wantLength) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_EXISTS)
  EndIf
  If exfat_error <> #EXFAT_E_NOT_FOUND
    ProcedureReturn 0
  EndIf
  needed = 2 + (exfat_wantLength + 14) / 15
  slot = exfat_FindFreeRun(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, needed)
  If slot < 0
    If exfat_error <> #EXFAT_OK And exfat_error <> #EXFAT_E_NOT_FOUND
      ProcedureReturn 0
    EndIf
    If exfat_GrowParentDirectory() = 0
      ProcedureReturn 0
    EndIf
    slot = exfat_FindFreeRun(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, needed)
    If slot < 0
      ProcedureReturn exfat_Fail(#EXFAT_E_DIR_FULL)
    EndIf
  EndIf
  If exfat_BeginMutation() = 0
    ProcedureReturn 0
  EndIf
  first = 0
  length = 0
  If (attr & #EXFAT_ATTR_DIRECTORY) <> 0
    first = exfat_AllocateOne(1)
    If first = 0
      ProcedureReturn 0
    EndIf
    length = exfat_bytesPerCluster
  EndIf
  If exfat_WriteNewSet(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, slot, @exfat_want[0], exfat_wantLength, attr, first, #EXFAT_STREAM_ALLOC_POSSIBLE, length, length, 0) = 0
    If first <> 0
      exfat_FreeAllocation(first, 0, length)
    EndIf
    ProcedureReturn 0
  EndIf
  exfat_fileFirst = first
  exfat_fileLength = length
  exfat_fileValid = length
  exfat_fileFlags = #EXFAT_STREAM_ALLOC_POSSIBLE
  exfat_fileAttr = attr
  exfat_fileParent = exfat_parentFirst
  exfat_fileParentFlags = exfat_parentFlags
  exfat_fileParentLength = exfat_parentLength
  exfat_fileSetIndex = slot
  exfat_fileSecondaries = needed - 1
  exfat_fileNameLength = exfat_wantLength
  exfat_filePos = 0
  exfat_open = 0
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatCreate(*path)
  If exfat_CreateCommon(*path, #EXFAT_ATTR_ARCHIVE) = 0
    ProcedureReturn 0
  EndIf
  exfat_fileLength = 0
  exfat_fileValid = 0
  exfat_open = 1
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatMkdir(*path)
  ProcedureReturn exfat_CreateCommon(*path, #EXFAT_ATTR_DIRECTORY)
EndProcedure

Procedure.i exfat_DirectoryEmpty(first.i, flags.i, length.i)
  Define index.i
  Define typ.i
  Define limit.i
  limit = exfat_DirEntryLimit(first, flags, length)
  If limit < 0
    ProcedureReturn -1
  EndIf
  index = 0
  While index < limit
    If exfat_DirRead(first, flags, length, index, @exfat_aux[0]) = 0
      ProcedureReturn -1
    EndIf
    typ = PeekA(@exfat_aux[0])
    If typ = 0
      ProcedureReturn 1
    EndIf
    If (typ & $80) <> 0
      ProcedureReturn 0
    EndIf
    index = index + 1
  Wend
  ProcedureReturn 1
EndProcedure

; THE FILE ENTRY IS CLEARED FIRST (forum 908). Clearing InUse on the file
; entry removes the whole set in one write: what is left behind are
; secondary entries with no file entry before them, which every reader
; skips and a repair tool clears. Clearing a secondary first changes bytes
; the set checksum covers while the file entry is still in use, and a power
; cut then leaves a damaged set that makes the whole folder unreadable.
Procedure.i exfat_ClearSet(parentFirst.i, parentFlags.i, parentLength.i, setIndex.i, secondary.i)
  Define e.i
  e = 0
  While e <= secondary
    If exfat_DirRead(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_aux[0]) = 0
      ProcedureReturn 0
    EndIf
    PokeA(@exfat_aux[0], PeekA(@exfat_aux[0]) & $7F)
    If exfat_DirWrite(parentFirst, parentFlags, parentLength, setIndex + e, @exfat_aux[0]) = 0
      ProcedureReturn 0
    EndIf
    e = e + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatRemove(*path)
  Define empty.i
  If exfat_Resolve(*path) = 0
    ProcedureReturn 0
  EndIf
  If (exfat_fileAttr & #EXFAT_ATTR_READ_ONLY) <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_READ_ONLY)
  EndIf
  If (exfat_fileAttr & #EXFAT_ATTR_DIRECTORY) <> 0
    empty = exfat_DirectoryEmpty(exfat_fileFirst, exfat_fileFlags, exfat_fileLength)
    If empty < 0
      ProcedureReturn 0
    EndIf
    If empty = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_NOT_EMPTY)
    EndIf
  EndIf
  If exfat_fileLength > 0 And exfat_ValidateAllocation(exfat_fileFirst, exfat_fileFlags, exfat_fileLength) = 0
    ProcedureReturn 0
  EndIf
  If exfat_BeginMutation() = 0
    ProcedureReturn 0
  EndIf
  ; Delete the name first, then release allocation, per the exFAT ordering.
  If exfat_ClearSet(exfat_fileParent, exfat_fileParentFlags, exfat_fileParentLength, exfat_fileSetIndex, exfat_fileSecondaries) = 0
    ProcedureReturn 0
  EndIf
  If exfat_FreeAllocation(exfat_fileFirst, exfat_fileFlags, exfat_fileLength) = 0
    ProcedureReturn 0
  EndIf
  exfat_open = 0
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatRename(*oldPath, *newPath)
  Dim oldPrimary.a[32]
  Define oldFirst.i
  Define oldLength.i
  Define oldValid.i
  Define oldFlags.i
  Define oldAttr.i
  Define oldParent.i
  Define oldParentFlags.i
  Define oldParentLength.i
  Define oldIndex.i
  Define oldSecondary.i
  Define slot.i
  Define needed.i
  Define forbidden.i
  If exfat_Resolve(*oldPath) = 0
    ProcedureReturn 0
  EndIf
  oldFirst = exfat_fileFirst
  oldLength = exfat_fileLength
  oldValid = exfat_fileValid
  oldFlags = exfat_fileFlags
  oldAttr = exfat_fileAttr
  oldParent = exfat_fileParent
  oldParentFlags = exfat_fileParentFlags
  oldParentLength = exfat_fileParentLength
  oldIndex = exfat_fileSetIndex
  oldSecondary = exfat_fileSecondaries
  exfat_Copy(@oldPrimary[0], @exfat_entry[0], 32)
  forbidden = 0
  If (oldAttr & #EXFAT_ATTR_DIRECTORY) <> 0
    forbidden = oldFirst
  EndIf
  If exfat_ResolveParent(*newPath, forbidden) = 0
    ProcedureReturn 0
  EndIf
  If exfat_FindInDir(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, @exfat_want[0], exfat_wantLength) <> 0
    ; The name found may be this very entry in another case - the one way to
    ; change a name's case (forum 910). Anything else is taken.
    If exfat_fileParent <> oldParent Or exfat_fileSetIndex <> oldIndex
      ProcedureReturn exfat_Fail(#EXFAT_E_EXISTS)
    EndIf
  ElseIf exfat_error <> #EXFAT_E_NOT_FOUND
    ProcedureReturn 0
  EndIf
  needed = 2 + (exfat_wantLength + 14) / 15
  slot = exfat_FindFreeRun(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, needed)
  If slot < 0
    If exfat_GrowParentDirectory() = 0
      ProcedureReturn 0
    EndIf
    slot = exfat_FindFreeRun(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, needed)
    If slot < 0
      ProcedureReturn exfat_Fail(#EXFAT_E_DIR_FULL)
    EndIf
  EndIf
  If exfat_BeginMutation() = 0
    ProcedureReturn 0
  EndIf
  If (oldAttr & #EXFAT_ATTR_DIRECTORY) = 0
    oldAttr = oldAttr | #EXFAT_ATTR_ARCHIVE
  EndIf
  exfat_open = 0
  If exfat_WriteNewSet(exfat_parentFirst, exfat_parentFlags, exfat_parentLength, slot, @exfat_want[0], exfat_wantLength, oldAttr, oldFirst, oldFlags, oldValid, oldLength, @oldPrimary[0]) = 0
    ProcedureReturn 0
  EndIf
  If exfat_ClearSet(oldParent, oldParentFlags, oldParentLength, oldIndex, oldSecondary) = 0
    ProcedureReturn 0
  EndIf
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatRescanFree()
  Define cluster.i
  Define used.i
  Define free.i
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  free = 0
  cluster = 2
  While cluster <= exfat_clusterCount + 1
    used = exfat_BitmapGet(cluster)
    If used < 0
      ProcedureReturn 0
    EndIf
    If used = 0
      free = free + 1
    EndIf
    cluster = cluster + 1
  Wend
  exfat_freeClusters = free
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatFreeClusters()
  If exfat_freeClusters < 0
    If ExFatRescanFree() = 0
      ProcedureReturn -1
    EndIf
  EndIf
  ProcedureReturn exfat_freeClusters
EndProcedure

Procedure.i ExFatFlush()
  If exfat_mounted = 0
    ProcedureReturn exfat_Fail(#EXFAT_E_NOT_MOUNTED)
  EndIf
  ; The device is asked to commit only after the metadata it must commit.
  If exfat_FlushMeta() = 0
    ProcedureReturn 0
  EndIf
  If *exfat_flusher <> 0
    If exfat_flusher() = 0
      ProcedureReturn exfat_Fail(#EXFAT_E_FLUSH)
    EndIf
  EndIf
  ; After a failed block read or write in the middle of a change the volume
  ; may really be inconsistent, so its dirty mark stays for a repair tool.
  If exfat_dirty <> 0 And exfat_ioFailed = 0
    If exfat_SetVolumeDirty(0) = 0
      ProcedureReturn 0
    EndIf
    If *exfat_flusher <> 0
      If exfat_flusher() = 0
        ProcedureReturn exfat_Fail(#EXFAT_E_FLUSH)
      EndIf
    EndIf
  EndIf
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure.i ExFatUnmount()
  If exfat_open <> 0
    ProcedureReturn exfat_Fail(#EXFAT_E_BUSY)
  EndIf
  If exfat_mounted <> 0 And exfat_dirty <> 0 And exfat_ioFailed = 0
    If ExFatFlush() = 0
      ProcedureReturn 0
    EndIf
  EndIf
  exfat_mounted = 0
  exfat_inheritedDirty = 0
  exfat_bitmapCluster = 0
  exfat_upcaseCluster = 0
  exfat_error = #EXFAT_OK
  ProcedureReturn 1
EndProcedure

Procedure ExFatSetTimestamp(date.i, time.i, time10ms.i, utcOffset.i)
  exfat_date = date
  exfat_time = time
  exfat_time10ms = time10ms
  exfat_utcOffset = utcOffset
EndProcedure

Procedure.i ExFatMounted()
  ProcedureReturn exfat_mounted
EndProcedure

Procedure.i ExFatLastError()
  ProcedureReturn exfat_error
EndProcedure

Procedure.i ExFatLastLba()
  ProcedureReturn exfat_lastLba
EndProcedure

Procedure.i ExFatBytesPerCluster()
  ProcedureReturn exfat_bytesPerCluster
EndProcedure

Procedure.i ExFatErrorText()
  Select exfat_error
    Case #EXFAT_OK : ProcedureReturn "nothing went wrong"
    Case #EXFAT_E_NO_READER : ProcedureReturn "exFAT error 1: no block reader is installed; bring up a storage device first"
    Case #EXFAT_E_READ : ProcedureReturn "exFAT error 2: a block read failed; check the medium and connection"
    Case #EXFAT_E_NO_MBR : ProcedureReturn "exFAT error 3: sector zero is neither an exFAT boot sector nor a valid MBR"
    Case #EXFAT_E_PARTITION : ProcedureReturn "exFAT error 4: the requested partition entry is invalid; check the partition table"
    Case #EXFAT_E_NOT_EXFAT : ProcedureReturn "exFAT error 5: the selected volume is not exFAT; select the correct partition"
    Case #EXFAT_E_BOOT : ProcedureReturn "exFAT error 6: the boot region is malformed; check the volume with a filesystem repair tool"
    Case #EXFAT_E_BOOT_CHECKSUM : ProcedureReturn "exFAT error 7: the boot-region checksum is wrong; use a verified copy of the medium"
    Case #EXFAT_E_REVISION : ProcedureReturn "exFAT error 8: this exFAT major revision is unsupported; use an exFAT 1.x volume"
    Case #EXFAT_E_GEOMETRY : ProcedureReturn "exFAT error 9: volume geometry is inconsistent or out of range; check the partition"
    Case #EXFAT_E_DIRTY : ProcedureReturn "exFAT error 10: the volume was not cleanly unmounted; repair it before writing"
    Case #EXFAT_E_ROOT : ProcedureReturn "exFAT error 11: the root directory cluster is invalid; check the filesystem"
    Case #EXFAT_E_BITMAP : ProcedureReturn "exFAT error 12: the required allocation bitmap is missing or invalid; check the filesystem"
    Case #EXFAT_E_UPCASE : ProcedureReturn "exFAT error 13: the required Unicode up-case table is missing or invalid; check the filesystem"
    Case #EXFAT_E_UPCASE_CHECKSUM : ProcedureReturn "exFAT error 14: the Unicode up-case table checksum is wrong; check the filesystem"
    Case #EXFAT_E_NOT_MOUNTED : ProcedureReturn "exFAT error 15: no exFAT volume is mounted; bring up storage first"
    Case #EXFAT_E_PATH : ProcedureReturn "exFAT error 16: the path or filename is invalid; check its separators and characters"
    Case #EXFAT_E_UTF8 : ProcedureReturn "exFAT error 17: the input name is not valid UTF-8; correct the filename encoding"
    Case #EXFAT_E_UTF16 : ProcedureReturn "exFAT error 18: the on-disk filename is not valid UTF-16; check the filesystem"
    Case #EXFAT_E_NOT_FOUND : ProcedureReturn "exFAT error 19: no entry has that path; check the filename and directory"
    Case #EXFAT_E_NOT_DIR : ProcedureReturn "exFAT error 20: a path component is a file rather than a directory; check the path"
    Case #EXFAT_E_IS_DIR : ProcedureReturn "exFAT error 21: the requested object is a directory rather than a file"
    Case #EXFAT_E_SET_CHECKSUM : ProcedureReturn "exFAT error 22: a directory entry-set checksum is wrong; check the filesystem"
    Case #EXFAT_E_NAME_HASH : ProcedureReturn "exFAT error 23: a filename hash is inconsistent; check the filesystem"
    Case #EXFAT_E_CHAIN : ProcedureReturn "exFAT error 24: a cluster chain is invalid or loops; check the filesystem"
    Case #EXFAT_E_BOUNDS : ProcedureReturn "exFAT error 25: metadata points outside the selected volume; do not use this copy"
    Case #EXFAT_E_NO_FILE : ProcedureReturn "exFAT error 26: no file is open; open a file before reading or writing"
    Case #EXFAT_E_NULL : ProcedureReturn "exFAT error 27: a null data buffer was supplied; check the caller"
    Case #EXFAT_E_LENGTH : ProcedureReturn "exFAT error 28: a length or offset is invalid; check the requested range"
    Case #EXFAT_E_NO_WRITER : ProcedureReturn "exFAT error 29: no block writer is installed; this medium is read-only"
    Case #EXFAT_E_WRITE : ProcedureReturn "exFAT error 30: a block write failed; keep the medium connected and run a filesystem check"
    Case #EXFAT_E_NO_SPACE : ProcedureReturn "exFAT error 31: the volume has no free cluster; remove files or use a larger medium"
    Case #EXFAT_E_EXISTS : ProcedureReturn "exFAT error 32: an entry with that name already exists; choose another name"
    Case #EXFAT_E_NOT_EMPTY : ProcedureReturn "exFAT error 33: the directory is not empty; remove its contents first"
    Case #EXFAT_E_READ_ONLY : ProcedureReturn "exFAT error 34: the entry is read-only; clear the attribute before changing it"
    Case #EXFAT_E_DIR_FULL : ProcedureReturn "exFAT error 35: the directory has no contiguous entry slots; remove entries or repair it"
    Case #EXFAT_E_FLUSH : ProcedureReturn "exFAT error 36: the device did not flush writes; do not remove power"
    Case #EXFAT_E_BUSY : ProcedureReturn "exFAT error 37: a file is still open; close it before unmounting"
    Case #EXFAT_E_CRITICAL : ProcedureReturn "exFAT error 38: an unknown critical directory entry is present; this implementation cannot mount it safely"
    Case #EXFAT_E_TEXFAT : ProcedureReturn "exFAT error 39: TexFAT transactional mode is unsupported; use ordinary exFAT"
    Case #EXFAT_E_RESERVED_NAME : ProcedureReturn "exFAT error 42: . and .. are reserved names for a folder and its parent and cannot name a file or folder"
    Case #EXFAT_E_MEDIA_FAILURE : ProcedureReturn "exFAT error 41: the volume records an unresolved media failure; repair or replace the medium before writing"
  EndSelect
  ProcedureReturn "exFAT error: an unknown internal failure occurred; record the numeric code and stop using the medium"
EndProcedure
