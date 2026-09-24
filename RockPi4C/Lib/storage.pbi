; Rock Pi 4C block-device adapter for Anvil's shared filesystem and HwFile seam.
; Include after Anvil/Storage/filesystem.pbi and Anvil/Storage/hwfile.pbi,
; and after RockPi4C/Lib/sdmmc.pbi and RockPi4C/Lib/emmc.pbi. Board composition and command wiring are
; intentionally left to the board integrator.

Global rock_storage_up.i
Global rock_storage_partition.i
Global rock_storage_error.i
Global rock_storage_fs_text.i
Global rock_storage_blocks.i
Global rock_storage_medium.i ; 0 removable SD, 1 on-board eMMC

#ROCK_STORAGE_ERR_OK = 0
#ROCK_STORAGE_ERR_SD = 1
#ROCK_STORAGE_ERR_CAPACITY = 2
#ROCK_STORAGE_ERR_FILESYSTEM = 3
#ROCK_STORAGE_ERR_EMMC = 4
#ROCK_STORAGE_ERR_BUSY = 5

Procedure.i rock_storage_selectMedium(medium.i)
  If medium=rock_storage_medium
    ProcedureReturn 1
  EndIf
  If FsIsOpen()<>0
    rock_storage_error=#ROCK_STORAGE_ERR_BUSY
    ProcedureReturn 0
  EndIf
  If FsUnmount()=0
    rock_storage_error=#ROCK_STORAGE_ERR_BUSY
    ProcedureReturn 0
  EndIf
  RockEmmcDisarmWrites()
  FsSetRangeWriter(0)
  FsSetRangeReader(0)
  FsSetBlockFlusher(0)
  gHwFileMounted=0
  gHwFileWritable=0
  gHwFileWriter=0
  rock_storage_up=0
  rock_storage_partition=0
  rock_storage_blocks=0
  rock_storage_medium=medium
  rock_storage_error=#ROCK_STORAGE_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure.i RockStorageUseEmmc()
  ProcedureReturn rock_storage_selectMedium(1)
EndProcedure

Procedure.i RockStorageUseSd()
  ProcedureReturn rock_storage_selectMedium(0)
EndProcedure

Procedure.i RockStorageIsEmmc()
  ProcedureReturn rock_storage_medium
EndProcedure

; Bring up the SD reader and mount a supported partition through the shared
; filesystem dispatcher (GPT Microsoft Basic Data entries are interpreted by
; exFAT's existing mount path). The first successful partition remains mounted.
; Writes stay disarmed until the SD write path has been validated separately.
Procedure.i HwStorageUp()
  Define partition.i

  If rock_storage_up <> 0
    ProcedureReturn 1
  EndIf

  rock_storage_error = #ROCK_STORAGE_ERR_OK
  rock_storage_fs_text = 0
  rock_storage_partition = 0
  rock_storage_blocks = 0
  gHwFileMounted = 0
  gHwFileWritable = 0
  gHwFileWriter = 0
  FsSetRangeWriter(0)
  If rock_storage_medium=1
    FsSetRangeReader(@RockEmmcReadBlocks)
    FsSetBlockFlusher(@RockEmmcFlush)
    If RockEmmcInit()=0
      rock_storage_error=#ROCK_STORAGE_ERR_EMMC
      ProcedureReturn 0
    EndIf
    rock_storage_blocks=RockEmmcBlockCount()
  Else
    FsSetRangeReader(@RockSdReadBlocks)
    FsSetBlockFlusher(@RockSdFlush)
    If RockSdInit()=0
      rock_storage_error=#ROCK_STORAGE_ERR_SD
      ProcedureReturn 0
    EndIf
    rock_storage_blocks=RockSdBlockCount()
  EndIf
  If rock_storage_blocks <= 0
    rock_storage_error = #ROCK_STORAGE_ERR_CAPACITY
    ProcedureReturn 0
  EndIf

  For partition = 1 To #FS_MAX_PARTITION
    If FsSelectPartition(partition) <> 0
      rock_storage_partition = partition
      rock_storage_up = 1
      gHwFileMounted = 1
      gHwFileWritable = 0
      gHwFileWriter = 0
      FsSetRangeWriter(0)
      ProcedureReturn 1
    EndIf
    ; A recognized exFAT volume that fails its integrity checks must remain
    ; the reported failure. Continuing through empty GPT ordinals replaces
    ; the useful reason with FAT's "partition slot is empty" message.
    If FsErrorKind() = #FS_EXFAT And ExFatLastError() <> #EXFAT_E_NOT_EXFAT And ExFatLastError() <> #EXFAT_E_NO_MBR
      rock_storage_fs_text = FsErrorText()
      rock_storage_error = #ROCK_STORAGE_ERR_FILESYSTEM
      ProcedureReturn 0
    EndIf
  Next

  rock_storage_fs_text = FsErrorText()
  rock_storage_error = #ROCK_STORAGE_ERR_FILESYSTEM
  ProcedureReturn 0
EndProcedure

Procedure.i RockStorageIsUp()
  ProcedureReturn rock_storage_up
EndProcedure

Procedure.i RockStoragePartition()
  ProcedureReturn rock_storage_partition
EndProcedure

Procedure.i RockStorageBlockCount()
  ProcedureReturn rock_storage_blocks
EndProcedure

Procedure.i RockStorageError()
  ProcedureReturn rock_storage_error
EndProcedure

; Return the lower-level driver's reason for transport failures and preserve
; the filesystem's mount diagnostic for filesystem failures.
Procedure.i RockStorageErrorText()
  If rock_storage_error = #ROCK_STORAGE_ERR_SD
    ProcedureReturn RockSdErrorText()
  EndIf
  If rock_storage_error = #ROCK_STORAGE_ERR_EMMC
    ProcedureReturn RockEmmcErrorText()
  EndIf
  If rock_storage_error = #ROCK_STORAGE_ERR_BUSY
    ProcedureReturn ?rock_storage_busy
  EndIf
  If rock_storage_error = #ROCK_STORAGE_ERR_FILESYSTEM And rock_storage_fs_text <> 0
    ProcedureReturn rock_storage_fs_text
  EndIf
  If rock_storage_error = #ROCK_STORAGE_ERR_CAPACITY
    ProcedureReturn ?rock_storage_no_capacity
  EndIf
  If rock_storage_error = #ROCK_STORAGE_ERR_FILESYSTEM
    ProcedureReturn ?rock_storage_no_filesystem
  EndIf
  ProcedureReturn ?rock_storage_ok
EndProcedure

DataSection
rock_storage_ok:
  Data.s "storage ready"
rock_storage_no_capacity:
  Data.s "no usable storage sectors"
rock_storage_no_filesystem:
  Data.s "no supported filesystem mounted"
rock_storage_busy:
  Data.s "filesystem has an open file"
EndDataSection
