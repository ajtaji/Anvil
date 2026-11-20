; Raw block sessions use the same serialized disk queue as the filesystem.
; Flush and unmount a live volume before bypassing its sector cache.
Procedure.i HwMmcInfo() : ProcedureReturn ZentajiDiskOwned() : EndProcedure
Procedure.i HwMmcType() : ProcedureReturn #HW_MMC_VIRTUAL : EndProcedure
Procedure.i HwMmcBlockSize() : ProcedureReturn 512 : EndProcedure
Procedure.i HwMmcBlockCount() : ProcedureReturn ZentajiDiskSectors() : EndProcedure
Procedure.i HwMmcCanWrite()
 If ZentajiDiskOwned()=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool((PeekQ(zenDisk\base+$58)&1)=0)
EndProcedure
Procedure.i HwMmcReadBlock(lba.i,*buf) : ProcedureReturn ZentajiDiskRead(lba,1,*buf) : EndProcedure
Procedure.i HwMmcWriteBlock(lba.i,*buf) : ProcedureReturn ZentajiDiskWrite(lba,1,*buf) : EndProcedure
Procedure.i HwMmcErrorText() : ProcedureReturn ZentajiDiskErrorText() : EndProcedure

XIncludeFile "Anvil/Core/mmc_cmd.pbi"

Procedure ZentajiCmdBlocks()
 Protected mounted.i,acquired.i,partition.i,configured.i
 If zenStorageConfigured=0 : PrintN("!! No Zentaji disk selected.") : ProcedureReturn : EndIf
 If gHwFileOpen<>0 Or FsIsOpen()<>0 Or FsMountPending()<>0
  PrintN("!! The filesystem is busy. Finish the open operation before raw block access.") : ProcedureReturn
 EndIf
 acquired=zenStorageAcquired : mounted=gHwFileMounted
 partition=FsPartition() : configured=zenStoragePartition
 If mounted<>0
  If ZentajiStorageDown()<>1 : UartWriteStr(ZentajiStorageErrorText()) : PrintNl() : ProcedureReturn : EndIf
 EndIf
 If zenStorageAcquired=0
  If ZentajiDiskOpen(zenStorageDisk)<>1 : UartWriteStr(ZentajiDiskErrorText()) : PrintNl() : ProcedureReturn : EndIf
 EndIf
 CmdMmc()
 If zenStorageAcquired=0
  If ZentajiDiskClose()<>1 : UartWriteStr(ZentajiDiskErrorText()) : PrintNl() : ProcedureReturn : EndIf
 EndIf
 If acquired<>0 And mounted<>0
  zenStoragePartition=partition
  If ZentajiStorageUp()<>1 : Print("Filesystem remount failed. ") : UartWriteStr(ZentajiStorageErrorText()) : PrintNl() : EndIf
  zenStoragePartition=configured
 EndIf
EndProcedure
