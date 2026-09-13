; Filesystem dispatch for block-backed Anvil boards. FAT32 and exFAT remain
; independent format owners; this is the only layer allowed to select one.
#FS_NONE = 0
#FS_FAT = 1
#FS_EXFAT = 2

Global fs_kind.i
Global fs_error.i
Global fs_errorKind.i
Global *fs_reader
Global *fs_writer
Global *fs_flusher

Procedure FsSetBlockReader(address.i)
  *fs_reader = address
  FatSetBlockReader(address)
  ExFatSetBlockReader(address)
EndProcedure

Procedure FsSetBlockWriter(address.i)
  *fs_writer = address
  FatSetBlockWriter(address)
  ExFatSetBlockWriter(address)
EndProcedure

Procedure FsSetBlockFlusher(address.i)
  *fs_flusher = address
  ExFatSetBlockFlusher(address)
EndProcedure

Procedure.i FsMount(partition.i)
  fs_kind = #FS_NONE
  fs_errorKind = #FS_NONE
  If ExFatMount(partition) <> 0
    fs_kind = #FS_EXFAT
    fs_error = 0
    fs_errorKind = #FS_EXFAT
    ProcedureReturn 1
  EndIf
  ; Only a positive "not exFAT" classification may fall through. Corrupt
  ; exFAT metadata is never reinterpreted as another filesystem.
  If ExFatLastError() <> #EXFAT_E_NOT_EXFAT And ExFatLastError() <> #EXFAT_E_NO_MBR
    fs_error = ExFatLastError()
    fs_errorKind = #FS_EXFAT
    ProcedureReturn 0
  EndIf
  If FatMount(partition) <> 0
    fs_kind = #FS_FAT
    fs_error = 0
    fs_errorKind = #FS_FAT
    ProcedureReturn 1
  EndIf
  fs_error = FatLastError()
  fs_errorKind = #FS_FAT
  ProcedureReturn 0
EndProcedure

Procedure.i FsOpen(*path)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatOpen(*path)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatOpen(*path)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsCreate(*path)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatCreate(*path)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatCreate(*path)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsRead(*dst, count.i)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRead(*dst, count)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatRead(*dst, count)
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsWrite(*src, count.i)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatWrite(*src, count)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatWrite(*src, count)
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsSeek(position.i)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatSeek(position)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatSeek(position)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsTruncate(length.i)
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

Procedure.i FsLastError()
  If fs_kind = #FS_EXFAT Or (fs_kind = #FS_NONE And fs_errorKind = #FS_EXFAT)
    ProcedureReturn ExFatLastError()
  EndIf
  ProcedureReturn FatLastError()
EndProcedure

Procedure.i FsErrorText()
  If fs_kind = #FS_EXFAT Or (fs_kind = #FS_NONE And fs_errorKind = #FS_EXFAT)
    ProcedureReturn ExFatErrorText()
  EndIf
  ProcedureReturn FatErrorText()
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

Procedure.i FsDirOpen(*path)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirOpen(*path)
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatDirRewind()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsDirRewind()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirRewind()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatDirRewind()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsDirNext()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirNext()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatDirNext()
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i FsDirNameUtf8(*dst, capacity.i)
  Define raw.i
  Define i.i
  Define n.i
  Define base.i
  Define ext.i
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatDirNameUtf8(*dst, capacity)
  EndIf
  If fs_kind <> #FS_FAT Or *dst = 0 Or capacity < 13
    ProcedureReturn -1
  EndIf
  raw = @exfat_aux[0]
  FatDirName(raw)
  base = 8
  While base > 0 And PeekA(raw + base - 1) = 32
    base = base - 1
  Wend
  ext = 3
  While ext > 0 And PeekA(raw + 8 + ext - 1) = 32
    ext = ext - 1
  Wend
  n = 0
  i = 0
  While i < base
    PokeA(*dst + n, PeekA(raw + i))
    n = n + 1
    i = i + 1
  Wend
  If ext > 0
    PokeA(*dst + n, 46)
    n = n + 1
    i = 0
    While i < ext
      PokeA(*dst + n, PeekA(raw + 8 + i))
      n = n + 1
      i = i + 1
    Wend
  EndIf
  PokeA(*dst + n, 0)
  ProcedureReturn n
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
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatMkdir(*path)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsRemove(*path)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRemove(*path)
  EndIf
  ProcedureReturn FatDelete(*path)
EndProcedure

Procedure.i FsRename(*oldPath, *newPath)
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatRename(*oldPath, *newPath)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsFlush()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatFlush()
  EndIf
  If fs_kind = #FS_FAT
    ProcedureReturn FatSyncFsInfo()
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FsUnmount()
  If fs_kind = #FS_EXFAT
    If ExFatUnmount() = 0
      ProcedureReturn 0
    EndIf
  ElseIf fs_kind = #FS_FAT
    FatClose()
  EndIf
  fs_kind = #FS_NONE
  ProcedureReturn 1
EndProcedure

Procedure.i FsType()
  ProcedureReturn fs_kind
EndProcedure

Procedure.i FsBytesPerCluster()
  If fs_kind = #FS_EXFAT
    ProcedureReturn ExFatBytesPerCluster()
  EndIf
  ProcedureReturn FatBytesPerCluster()
EndProcedure
