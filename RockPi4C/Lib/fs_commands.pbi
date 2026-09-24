; Rock Pi 4C serial adapter for Anvil's shared HwFile/Fs command operations.
; Keep the block format and file semantics in Anvil/Storage; this layer only
; parses bounded recovery lines and reports their result over UART.

#ROCK_FS_PATH_BYTES = 512
#ROCK_FS_LIST_CAP = 256
#ROCK_FS_CAT_CAP = 65536
#ROCK_FS_CAT_CHUNK = 256

Global Dim rock_fs_path.a[#ROCK_FS_PATH_BYTES]
Global Dim rock_fs_second.a[#ROCK_FS_PATH_BYTES]
Global Dim rock_fs_name.a[#ROCK_FS_PATH_BYTES]
Global Dim rock_fs_cat.a[#ROCK_FS_CAT_CHUNK]
Global Dim rock_fs_word.a[32]
Global rock_fs_stage_valid.i
Global rock_fs_stage_length.i
Global rock_fs_stage_crc.i

Procedure RockFsHex64(value.i)
  Protected index.i
  Protected digit.i
  For index=0 To 15
    digit=(value >> (60-index*4)) & 15
    If digit<10
      RockUartByte(48+digit)
    Else
      RockUartByte(55+digit)
    EndIf
  Next
EndProcedure

; 0 means missing, -1 means malformed, otherwise returns the byte length.
; Quotes permit spaces in FAT32/exFAT names, just as shared Anvil does.
Procedure.i RockFsNextPath(*line, lineLength.i, *position, *dst, capacity.i)
  Protected pos.i = PeekI(*position)
  Protected n.i
  Protected quoted.i
  Protected c.i
  While pos < lineLength And (PeekA(*line+pos)=32 Or PeekA(*line+pos)=9)
    pos=pos+1
  Wend
  If pos>=lineLength : ProcedureReturn 0 : EndIf
  quoted=Bool(PeekA(*line+pos)=34)
  If quoted<>0 : pos=pos+1 : EndIf
  While pos<lineLength
    c=PeekA(*line+pos) & 255
    If quoted<>0
      If c=34 : Break : EndIf
    ElseIf c=32 Or c=9
      Break
    EndIf
    If n>=capacity-1 : ProcedureReturn -1 : EndIf
    PokeA(*dst+n,c)
    n=n+1
    pos=pos+1
  Wend
  If quoted<>0
    If pos>=lineLength Or PeekA(*line+pos)<>34 : ProcedureReturn -1 : EndIf
    pos=pos+1
    If pos<lineLength And PeekA(*line+pos)<>32 And PeekA(*line+pos)<>9
      ProcedureReturn -1
    EndIf
  EndIf
  PokeA(*dst+n,0)
  PokeI(*position,pos)
  If n=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn n
EndProcedure

Procedure.i RockFsReady()
  If HwStorageUp()<>0 : ProcedureReturn 1 : EndIf
  RockUartLine("FILESYSTEM MOUNT FAILED")
  RockUartLine(RockStorageErrorText())
  RockStorageDiagnostics()
  ProcedureReturn 0
EndProcedure

Procedure RockFsList(*path)
  Protected result.i
  Protected count.i
  Protected length.i
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If HwDirOpen(*path)=0
    RockUartText("LS FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  RockUartText("DIRECTORY ") : RockUartLine(*path)
  Repeat
    result=HwDirNext()
    If result<=0 : Break : EndIf
    If count>=#ROCK_FS_LIST_CAP
      RockUartLine("LS TRUNCATED: 256 ENTRIES; MORE REMAIN")
      ProcedureReturn
    EndIf
    length=HwDirNameUtf8(@rock_fs_name[0],#ROCK_FS_PATH_BYTES)
    If length<=0
      RockUartText("LS FAILED: ") : RockUartLine(HwFileErrorText())
      ProcedureReturn
    EndIf
    If HwDirIsDir()<>0
      RockUartText("DIR  ")
    Else
      RockUartText("FILE ")
      RockFsHex64(HwDirSize())
      RockUartByte(32)
    EndIf
    RockUartLine(@rock_fs_name[0])
    count=count+1
    RockWatchdogPet()
  ForEver
  If result<0
    RockUartText("LS INCOMPLETE: ") : RockUartLine(HwFileErrorText())
  Else
    RockUartText("LS DONE COUNT ") : RockStorageHex8(count) : RockUartLine("")
  EndIf
EndProcedure

Procedure RockFsStat(*path)
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If HwFileOpen(*path)=0
    RockUartText("STAT FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  RockUartText("FILE ") : RockUartText(*path)
  RockUartText(" BYTES ") : RockFsHex64(HwFileSize()) : RockUartLine("")
  HwFileClose()
EndProcedure

Procedure RockFsCat(*path)
  Protected size.i
  Protected offset.i
  Protected want.i
  Protected got.i
  Protected index.i
  Protected c.i
  Protected odd.i
  Protected afterCr.i
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If HwFileOpen(*path)=0
    RockUartText("CAT FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  size=HwFileSize()
  If size>#ROCK_FS_CAT_CAP
    HwFileClose()
    RockUartLine("CAT REFUSED: FILE EXCEEDS 64 KIB TEXT LIMIT; USE get")
    ProcedureReturn
  EndIf
  While offset<size
    want=size-offset
    If want>#ROCK_FS_CAT_CHUNK : want=#ROCK_FS_CAT_CHUNK : EndIf
    got=HwFileReadAt(offset,@rock_fs_cat[0],want)
    If got<>want
      HwFileClose()
      RockUartText("CAT INCOMPLETE: ") : RockUartLine(HwFileErrorText())
      ProcedureReturn
    EndIf
    For index=0 To got-1
      c=PeekA(@rock_fs_cat[0]+index) & 255
      If c=10
        If afterCr=0 : RockUartByte(13) : RockUartByte(10) : EndIf
        afterCr=0
      ElseIf c=13
        RockUartByte(13) : RockUartByte(10)
        afterCr=1
      ElseIf c>=32 And c<=126
        RockUartByte(c)
        afterCr=0
      Else
        RockUartByte(46)
        odd=odd+1
        afterCr=0
      EndIf
    Next
    offset=offset+got
    RockWatchdogPet()
  Wend
  HwFileClose()
  RockUartLine("")
  RockUartText("CAT DONE BYTES ") : RockStorageHex8(size)
  RockUartText(" NONPRINTABLE ") : RockStorageHex8(odd) : RockUartLine("")
EndProcedure

; `receive` fills Anvil's owned stage without executing the bytes. `load`
; fills the same stage from a file. Only a fully checked stage may be saved.
Procedure RockFsReceive(length.i,checksum.i)
  rock_fs_stage_valid=0
  If length<=0 Or length>#ROCK_STORAGE_STAGE_BYTES
    RockUartLine("RECEIVE REFUSED: STAGE LIMIT IS 4 MIB")
    ProcedureReturn
  EndIf
  If RockWatchdogArm()=0
    RockUartLine("RECEIVE REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn
  EndIf
  If RockStorageReceive(length,checksum)=0
    ProcedureReturn
  EndIf
  rock_fs_stage_length=length
  rock_fs_stage_crc=checksum
  rock_fs_stage_valid=1
  RockUartLine("STAGE READY; NO CODE EXECUTED")
EndProcedure

Procedure RockFsLoad(*path)
  Protected length.i
  Protected got.i
  rock_fs_stage_valid=0
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If HwFileOpen(*path)=0
    RockUartText("LOAD FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  length=HwFileSize()
  If length<=0 Or length>#ROCK_STORAGE_STAGE_BYTES
    HwFileClose()
    RockUartLine("LOAD REFUSED: FILE IS EMPTY OR EXCEEDS 4 MIB STAGE")
    ProcedureReturn
  EndIf
  If RockWatchdogArm()=0
    HwFileClose()
    RockUartLine("LOAD REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn
  EndIf
  got=HwFileReadAt(0,@rock_storage_stage[0],length)
  HwFileClose()
  If got<>length
    RockUartText("LOAD INCOMPLETE: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  rock_fs_stage_length=length
  rock_fs_stage_crc=RockStorageCrc32Pet(@rock_storage_stage[0],length)
  rock_fs_stage_valid=1
  RockUartText("STAGE ") : RockFsHex64(@rock_storage_stage[0])
  RockUartText(" BYTES ") : RockStorageHex8(length)
  RockUartText(" CRC ") : RockStorageHex8(rock_fs_stage_crc)
  RockUartLine("; NO CODE EXECUTED")
EndProcedure

; The selected medium's writer is armed only for one checked file operation.
; eMMC also checks the live hardware partition selector before accepting it.
Procedure.i RockFsArmWriter()
  If RockStorageIsEmmc()<>0
    If RockEmmcArmWrites()=0
      RockUartText("EMMC WRITE REFUSED: ") : RockUartLine(RockEmmcErrorText())
      ProcedureReturn 0
    EndIf
    gHwFileWriter=@RockEmmcWriteBlocks
  Else
    gHwFileWriter=@RockSdWriteBlocks
  EndIf
  gHwFileWritable=1
  ProcedureReturn 1
EndProcedure

Procedure RockFsDisarmWriter()
  gHwFileWriter=0
  gHwFileWritable=0
  FsSetRangeWriter(0)
  RockEmmcDisarmWrites()
EndProcedure

Procedure RockFsSave(*path)
  Protected partition.i
  Protected got.i
  If rock_fs_stage_valid=0
    RockUartLine("SAVE REFUSED: NO VERIFIED STAGE; USE receive OR load")
    ProcedureReturn
  EndIf
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If RockWatchdogArm()=0
    RockUartLine("SAVE REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn
  EndIf
  If RockStorageCrc32Pet(@rock_storage_stage[0],rock_fs_stage_length)<>rock_fs_stage_crc
    rock_fs_stage_valid=0
    RockUartLine("SAVE REFUSED: STAGE CHECKSUM CHANGED")
    ProcedureReturn
  EndIf
  If RockFsArmWriter()=0
    ProcedureReturn
  EndIf
  got=HwFileWriteAll(*path,@rock_storage_stage[0],rock_fs_stage_length)
  RockFsDisarmWriter()
  If got=0
    RockUartText("SAVE FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  partition=FsPartition()
  If FsUnmount()=0
    RockUartText("SAVE FLUSHED; REMOUNT FAILED: ") : RockUartLine(FsErrorText())
    rock_storage_up=0 : gHwFileMounted=0
    ProcedureReturn
  EndIf
  rock_storage_up=0 : gHwFileMounted=0
  If FsSelectPartition(partition)=0
    RockUartText("SAVE FLUSHED; REMOUNT FAILED: ") : RockUartLine(FsErrorText())
    ProcedureReturn
  EndIf
  rock_storage_up=1 : rock_storage_partition=partition : gHwFileMounted=1
  If HwFileOpen(*path)=0
    RockUartText("SAVE FLUSHED; READBACK OPEN FAILED: ") : RockUartLine(HwFileErrorText())
    ProcedureReturn
  EndIf
  If HwFileSize()<>rock_fs_stage_length
    HwFileClose()
    RockUartLine("SAVE FLUSHED; READBACK SIZE MISMATCH")
    ProcedureReturn
  EndIf
  got=HwFileReadAt(0,@rock_storage_stage[0],rock_fs_stage_length)
  HwFileClose()
  If got<>rock_fs_stage_length Or RockStorageCrc32Pet(@rock_storage_stage[0],rock_fs_stage_length)<>rock_fs_stage_crc
    rock_fs_stage_valid=0
    RockUartLine("SAVE FLUSHED; REMOUNTED READBACK CHECKSUM FAILED")
    ProcedureReturn
  EndIf
  RockUartLine("SAVE FLUSHED; REMOUNTED READBACK CHECKSUM PASS")
EndProcedure

; The shared HwFile mutation path flushes and disarms Fs after each call.
; The board additionally disarms its SD writer on every return path.
Procedure RockFsChange(command.i,*first,*second)
  Protected done.i
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If RockWatchdogArm()=0
    RockUartLine("FILESYSTEM CHANGE REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn
  EndIf
  RockWatchdogPet()
  If RockFsArmWriter()=0
    ProcedureReturn
  EndIf
  Select command
    Case 1 : done=HwDirCreate(*first)
    Case 2 : done=HwFileRemove(*first)
    Case 3 : done=HwDirRemove(*first)
    Case 4 : done=HwFileRename(*first,*second)
  EndSelect
  RockFsDisarmWriter()
  RockWatchdogPet()
  If done=0
    RockUartText("FILESYSTEM CHANGE FAILED: ") : RockUartLine(HwFileErrorText())
  Else
    RockUartLine("FILESYSTEM CHANGE FLUSHED")
  EndIf
EndProcedure

Procedure RockFsStatus()
  If RockFsReady()=0
    ProcedureReturn
  EndIf
  If RockStorageIsEmmc()<>0
    RockUartText("FILESYSTEM EMMC ")
  Else
    RockUartText("FILESYSTEM SD ")
  EndIf
  If FsType()=#FS_EXFAT
    RockUartText("EXFAT")
  ElseIf FsType()=#FS_FAT
    RockUartText("FAT32")
  Else
    RockUartText("UNMOUNTED")
  EndIf
  RockUartText(" PARTITION ") : RockStorageHex8(FsPartition())
  RockUartText(" BLOCKS ") : RockFsHex64(RockStorageBlockCount())
  RockUartLine("")
EndProcedure

Procedure RockFsSelectMedium(emmc.i)
  Protected selected.i
  If RockWatchdogArm()=0
    RockUartLine("STORAGE SELECT REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn
  EndIf
  If emmc<>0
    selected=RockStorageUseEmmc()
  Else
    selected=RockStorageUseSd()
  EndIf
  If selected=0
    RockUartText("STORAGE SELECT FAILED: ") : RockUartLine(RockStorageErrorText())
    ProcedureReturn
  EndIf
  If HwStorageUp()=0
    RockUartText("MEDIUM SELECTED; FILESYSTEM UNAVAILABLE: ")
    RockUartLine(RockStorageErrorText())
    ProcedureReturn
  EndIf
  RockFsStatus()
EndProcedure

; Return 0 only when the command belongs to another subsystem.
Procedure.i RockFsCommand(*line,lineLength.i)
  Protected pos.i
  Protected n.i
  Protected command.i
  Protected length.i
  Protected checksum.i
  n=rock_storage_nextToken(*line,lineLength,@pos,@rock_fs_word[0],32)
  If n<=0 : ProcedureReturn 0 : EndIf
  If rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_ls,2)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_dir,3)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_fatls,5)<>0
    command=1
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_stat,4)<>0
    command=2
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_cat,3)<>0
    command=3
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_load,4)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_fatload,7)<>0
    command=8
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_save,4)<>0
    command=9
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_receive,7)<>0
    command=10
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_f,1)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_fs,2)<>0
    command=11
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_emmc,4)<>0
    command=12
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_sd,2)<>0
    command=13
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_mkdir,5)<>0
    command=4
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_rm,2)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_del,3)<>0
    command=5
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_rmdir,5)<>0
    command=6
  ElseIf rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_mv,2)<>0 Or rock_storage_tokenIs(@rock_fs_word[0],?rock_fs_rename,6)<>0
    command=7
  Else
    ProcedureReturn 0
  EndIf
  If command=11 Or command=12 Or command=13
    If rock_storage_onlySpace(*line,lineLength,pos)=0
      RockUartLine("USAGE: fs | emmc | sd")
    ElseIf command=12
      RockFsSelectMedium(1)
    ElseIf command=13
      RockFsSelectMedium(0)
    Else
      RockFsStatus()
    EndIf
    ProcedureReturn 1
  EndIf
  If command=10
    If rock_storage_parseHexToken(*line,lineLength,@pos,@length)=0 Or rock_storage_parseHexToken(*line,lineLength,@pos,@checksum)=0 Or rock_storage_onlySpace(*line,lineLength,pos)=0
      RockUartLine("USAGE: receive <length-hex> <crc32-hex>")
    Else
      RockFsReceive(length,checksum)
    EndIf
    ProcedureReturn 1
  EndIf
  n=RockFsNextPath(*line,lineLength,@pos,@rock_fs_path[0],#ROCK_FS_PATH_BYTES)
  If command=1 And n=0
    PokeA(@rock_fs_path[0],47) : PokeA(@rock_fs_path[1],0)
    n=1
  EndIf
  If n<=0
    RockUartLine("FILESYSTEM PATH MISSING OR MALFORMED")
    ProcedureReturn 1
  EndIf
  If command=7
    n=RockFsNextPath(*line,lineLength,@pos,@rock_fs_second[0],#ROCK_FS_PATH_BYTES)
    If n<=0
      RockUartLine("MV DESTINATION PATH MISSING OR MALFORMED")
      ProcedureReturn 1
    EndIf
  EndIf
  If rock_storage_onlySpace(*line,lineLength,pos)=0
    RockUartLine("FILESYSTEM COMMAND HAS EXTRA ARGUMENTS")
    ProcedureReturn 1
  EndIf
  Select command
    Case 1 : RockFsList(@rock_fs_path[0])
    Case 2 : RockFsStat(@rock_fs_path[0])
    Case 3 : RockFsCat(@rock_fs_path[0])
    Case 8 : RockFsLoad(@rock_fs_path[0])
    Case 9 : RockFsSave(@rock_fs_path[0])
    Case 4 : RockFsChange(1,@rock_fs_path[0],0)
    Case 5 : RockFsChange(2,@rock_fs_path[0],0)
    Case 6 : RockFsChange(3,@rock_fs_path[0],0)
    Case 7 : RockFsChange(4,@rock_fs_path[0],@rock_fs_second[0])
  EndSelect
  ProcedureReturn 1
EndProcedure

DataSection
rock_fs_ls: Data.s "ls"
rock_fs_dir: Data.s "dir"
rock_fs_fatls: Data.s "fatls"
rock_fs_stat: Data.s "stat"
rock_fs_cat: Data.s "cat"
rock_fs_load: Data.s "load"
rock_fs_fatload: Data.s "fatload"
rock_fs_save: Data.s "save"
rock_fs_receive: Data.s "receive"
rock_fs_f: Data.s "f"
rock_fs_fs: Data.s "fs"
rock_fs_emmc: Data.s "emmc"
rock_fs_sd: Data.s "sd"
rock_fs_mkdir: Data.s "mkdir"
rock_fs_rm: Data.s "rm"
rock_fs_del: Data.s "del"
rock_fs_rmdir: Data.s "rmdir"
rock_fs_mv: Data.s "mv"
rock_fs_rename: Data.s "rename"
EndDataSection
