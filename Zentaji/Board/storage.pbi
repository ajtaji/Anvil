; Zentaji storage lifecycle over the shared file services. Include after
; boot_context, console, disk, HAL and wallclock. No format policy lives here.
; Serialized owner/core, normal supervisor context and qualified idle timer.
; Select explicitly, or adopt the validated ROM disk choice with FromBoot.
XIncludeFile "Anvil/Storage/fat32.pbi"
XIncludeFile "Anvil/Storage/exfat.pbi"
#ANVIL_JOURNAL_FS=1
XIncludeFile "Anvil/Storage/filesystem.pbi"
XIncludeFile "Anvil/Storage/hwfile.pbi"
#ZEN_STORAGE_E_ARGUMENT=1
#ZEN_STORAGE_E_BUSY=2
#ZEN_STORAGE_E_UNCONFIGURED=3
#ZEN_STORAGE_E_DISK=4
#ZEN_STORAGE_E_VOLUME=5
#ZEN_STORAGE_E_BOOT=6
#ZEN_STORAGE_E_OWNER=7
#ZEN_STORAGE_E_CONTEXT=8
Global zenStorageAcquired.i
Global zenStorageConfigured.i
Global zenStorageDisk.i
Global zenStoragePartition.i
Global zenStorageError.i
Global zenStorageDetail.i

Procedure.i ZentajiStorageFail(error.i,detail.i)
 zenStorageError=error : zenStorageDetail=detail
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiStorageLastError() : ProcedureReturn zenStorageError : EndProcedure
Procedure.i ZentajiStorageErrorText()
 If zenStorageDetail<>0 : ProcedureReturn zenStorageDetail : EndIf
 Select zenStorageError
  Case #ZEN_STORAGE_E_ARGUMENT : ProcedureReturn "storage: disk must be 0..15 and partition 1..4"
  Case #ZEN_STORAGE_E_BUSY : ProcedureReturn "storage: an owner, file or mount operation is still active"
  Case #ZEN_STORAGE_E_UNCONFIGURED : ProcedureReturn "storage: no Zentaji disk and partition have been selected"
  Case #ZEN_STORAGE_E_OWNER : ProcedureReturn "storage: disk queue ownership changed; file services are disarmed"
  Case #ZEN_STORAGE_E_CONTEXT : ProcedureReturn "storage: normal supervisor context and a qualified idle timer are required"
  Case #ZEN_STORAGE_E_BOOT : ProcedureReturn "storage: the validated boot context does not identify a ROM disk boot"
 EndSelect
 ProcedureReturn "storage: no error"
EndProcedure

Procedure.i ZentajiStorageConfigure(disk.i,partition.i)
 If disk<0 Or disk>15 Or partition<1 Or partition>#FS_MAX_PARTITION
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_ARGUMENT,0)
 EndIf
 If zenStorageAcquired<>0 Or ZentajiDiskMode()<>0 Or gHwFileMounted<>0 Or gHwFileOpen<>0 Or FsIsOpen()<>0 Or FsMountPending()<>0 Or FsType()<>#FS_NONE
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BUSY,0)
 EndIf
 zenStorageConfigured=1 : zenStorageDisk=disk : zenStoragePartition=partition
 zenStorageError=0 : zenStorageDetail=0
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiStorageFromBoot(context.i,partition.i)
 If ZentajiBootContextValid(context)<>1
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BOOT,0)
 EndIf
 If PeekQ(context+#ZEN_BOOT_SOURCE)<>1
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BOOT,0)
 EndIf
 ProcedureReturn ZentajiStorageConfigure(PeekA(PeekQ(context+#ZEN_BOOT_TABLE)+36),partition)
EndProcedure

Procedure.i ZentajiStorageUp()
 Protected journalWriter.i
 zenStorageError=0 : zenStorageDetail=0
 If zenStorageConfigured=0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_UNCONFIGURED,0) : EndIf
 If ZenCpuStatus()<>0 Or HwPromptIdleReady()=0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_CONTEXT,0) : EndIf
 If zenStorageAcquired=0
  If ZentajiDiskMode()<>0 Or FsType()<>#FS_NONE Or FsMountPending()<>0
   ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BUSY,0)
  EndIf
  If ZentajiDiskOpen(zenStorageDisk)=0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_DISK,ZentajiDiskErrorText()) : EndIf
  zenStorageAcquired=1
 Else
  If ZentajiDiskOwned()=0 Or ZentajiDiskMode()<>1
   gHwFileMounted=0 : gHwFileWritable=0 : gHwFileWriter=0
   ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_OWNER,0)
  EndIf
 EndIf
 ; Do not reset a working file, mount job, current volume or driver caches.
 If gHwFileMounted<>0 And (FsType()<>#FS_NONE Or FsMountPending()<>0) : ProcedureReturn 1 : EndIf
 FsSetRangeReader(@ZentajiDiskRead) : FsSetRangeWriter(0) : FsSetBlockFlusher(@ZentajiDiskFlush)
 If (PeekQ(zenDisk\base+$58)&1)=0 : journalWriter=@ZentajiDiskWriteBuffered : EndIf
 FsSetJournalDevice(ZentajiDiskSectors(),journalWriter)
 If FsMount(zenStoragePartition)=0
  gHwFileMounted=0 : gHwFileWritable=0 : gHwFileWriter=0
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_VOLUME,FsErrorText())
 EndIf
 gHwFileMounted=1
 gHwFileWritable=Bool((PeekQ(zenDisk\base+$58)&1)=0)
 gHwFileWriter=0
 If gHwFileWritable<>0 : gHwFileWriter=@ZentajiDiskWrite : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i HwStorageUp()
 If ZentajiStorageUp()<>0 : ProcedureReturn 1 : EndIf
 UartWriteStr(ZentajiStorageErrorText()) : PrintNl()
 ProcedureReturn 0
EndProcedure

Procedure HwStorageReport()
 If gHwFileMounted=0
  PrintN("No Zentaji volume is mounted.") : ProcedureReturn
 EndIf
 Print("Zentaji disk ") : PrintDec(zenStorageDisk)
 Print(" holds ") : PrintDec(ZentajiDiskSectors()) : PrintN(" blocks of 512 bytes.")
 If FsMountPending()<>0
  PrintN("A filesystem mount is in progress.") : ProcedureReturn
 EndIf
 If FsType()=#FS_NONE
  PrintN("No filesystem partition is currently mounted.") : ProcedureReturn
 EndIf
 Print("Mounted partition ") : PrintDec(FsPartition())
 Select FsType()
  Case #FS_EXFAT : Print(" uses exFAT")
  Case #FS_JOURNAL : Print(" uses AnvilFS")
  Case #FS_FAT : Print(" uses FAT32")
 EndSelect
 If gHwFileWritable<>0 : PrintN("; writes are available.") : Else : PrintN("; the medium is read-only.") : EndIf
EndProcedure

Procedure.i ZentajiStorageDown()
 zenStorageError=0 : zenStorageDetail=0
 If zenStorageAcquired=0
  If ZentajiDiskMode()<>0 Or FsType()<>#FS_NONE Or FsMountPending()<>0
   ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BUSY,0)
  EndIf
  ProcedureReturn 1
 EndIf
 If ZenCpuStatus()<>0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_CONTEXT,0) : EndIf
 If ZentajiDiskOwned()=0
  gHwFileMounted=0 : gHwFileWritable=0 : gHwFileWriter=0
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_OWNER,0)
 EndIf
 If gHwFileOpen<>0 Or FsIsOpen()<>0 Or FsMountPending()<>0
  ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_BUSY,0)
 EndIf
 If FsType()<>#FS_NONE
  ; Explicitly flush before unmount: a failed flush must retain the owner.
  FsSetRangeWriter(gHwFileWriter)
  If FsFlush()=0
   zenStorageDetail=FsErrorText() : FsSetRangeWriter(0)
   ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_VOLUME,zenStorageDetail)
  EndIf
  FsSetRangeWriter(0)
  If FsUnmount()=0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_VOLUME,FsErrorText()) : EndIf
 EndIf
 gHwFileMounted=0 : gHwFileWritable=0 : gHwFileWriter=0
 If ZentajiDiskClose()=0 : ProcedureReturn ZentajiStorageFail(#ZEN_STORAGE_E_DISK,ZentajiDiskErrorText()) : EndIf
 zenStorageAcquired=0
 FsSetJournalDevice(0,0)
 FsSetRangeReader(0) : FsSetRangeWriter(0) : FsSetBlockFlusher(0)
 ProcedureReturn 1
EndProcedure
