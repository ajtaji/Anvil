"""Compile shared exFAT regression and buffered-checksum timing for physical Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=[0,1,2,3,4,5,7,8,9,15,16,17,31,32,33,127,128,129,255,256,511,512,513,4095,4096,4097,8192,32768]
    names=['Anvil/Storage/exfat.pbi','Anvil/Storage/fat32.pbi','Anvil/Storage/filesystem.pbi','RaspberryPi4/Tests/exfat_emitted_gate.pi4','Anvil/Hal/aarch64_counter.pbi','RaspberryPi4/Lib/mmu.pi4']
    names.append('Anvil/Storage/exfat_profile.pbi')
    s=(root/names[3]).read_text(encoding='utf8').replace('Procedure.i Main()','Procedure.i GateMain()')
    s=s.replace('Global gateFlushes.i','Global gateFailLba.i=-1\nGlobal gateFlushes.i').replace('  gateReads = gateReads + 1','  If gateFailLba>=lba And gateFailLba<lba+count : ProcedureReturn 0 : EndIf\n  gateReads = gateReads + 1')
    # Legacy fixture buffers expressed inclusive maxima; provide their intended counts.
    for before,after in [('[#GATE_BYTES - 1]','[#GATE_BYTES]'),('[1399]','[1400]'),('[1023]','[1024]'),('[4607]','[4608]')]:s=s.replace(before,after)
    s='XIncludeFile "Anvil/Hal/aarch64_counter.pbi"\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+s
    s+=r'''
Procedure.i OldChecksum()
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


Procedure.i OldValidate()
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
Procedure.i OldBuildFast()
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
Procedure PrepareTable(prefix.i)
 Define i.i,v.i
 For i=0 To prefix-1
  v=i : If i>=97 And i<=122 : v=i-32 : EndIf
  exfat_Put16(@gateDisk[0]+35*512,i*2,v)
 Next
 exfat_Put16(@gateDisk[0]+35*512,prefix*2,$FFFF)
 exfat_Put16(@gateDisk[0]+35*512,prefix*2+2,65535-prefix)
 exfat_Put16(@gateDisk[0]+35*512,prefix*2+4,$FFFF)
 exfat_upcaseLength=prefix*2+6 : exfat_DropCaches()
EndProcedure
Procedure ValidationRow(index.i)
 Define p.i,t.i,rc.i
 p=$E1C01000+index*64
 exfat_DropCaches() : t=A64CounterReadOrdered() : rc=OldValidate()
 PokeI(p,rc) : PokeI(p+16,A64CounterReadOrdered()-t)
 exfat_DropCaches() : t=A64CounterReadOrdered() : rc=exfat_ValidateUpcase()
 PokeI(p+8,rc) : PokeI(p+24,A64CounterReadOrdered()-t)
EndProcedure
Procedure.i ProofPartialDirectoryWrite(lba.i,count.i,dst.i)
 PokeA(@gateDisk[0]+lba*512,166) : ProcedureReturn 0
EndProcedure
Procedure.i ProofDirectoryCache()
 Define i.i,base.i,before.i,rc.i
 GateFormat() : ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(@GateWriter)
 If ExFatMount(1)=0 : ProcedureReturn 1 : EndIf
 exfat_sectorsPerCluster=8 : exfat_blocksPerCluster=8 : exfat_bytesPerCluster=4096 : exfat_clusterCount=128
 base=exfat_partLba+exfat_heapOffset
 For i=0 To 12287 : PokeA(@gateDisk[0]+base*512+i,(i/512) & 255) : Next
 exfat_DropCaches()
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>0 : ProcedureReturn 2 : EndIf
 If exfat_DirRead(3,2,4096,0,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 3 : EndIf
 If exfat_StreamRead(4,2,4096,0,@gateBig[0],512)<>512 : ProcedureReturn 4 : EndIf
 before=gateReads
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>0 : ProcedureReturn 5 : EndIf
 If exfat_DirRead(3,2,4096,0,@gateRead[0])=0 Or gateRead[0]<>8 Or gateReads<>before : ProcedureReturn 6 : EndIf
 If exfat_DirRead(2,0,8192,0,@gateRead[0])=0 Or gateReads<=before : ProcedureReturn 7 : EndIf
 before=gateReads
 If exfat_DirRead(2,2,512,0,@gateRead[0])=0 Or gateReads<=before : ProcedureReturn 8 : EndIf
 If exfat_DirRead(2,2,512,16,@gateRead[0])<>0 Or ExFatLastError()<>#EXFAT_E_BOUNDS : ProcedureReturn 9 : EndIf
 If exfat_DirRead(2,2,8192,255,@gateRead[0])=0 Or gateRead[0]<>15 : ProcedureReturn 10 : EndIf
 If exfat_DirRead(2,2,8192,0,0)<>0 : ProcedureReturn 11 : EndIf
 If exfat_SetFatEntry(2,3)=0 Or exfat_FlushFat()=0 : ProcedureReturn 20 : EndIf
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 21 : EndIf
 before=gateWrites
 If exfat_SetFatEntry(2,4)=0 Or gateWrites<>before : ProcedureReturn 22 : EndIf
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>16 : ProcedureReturn 23 : EndIf
 ExFatSetRangeWriter(0)
 If exfat_DirRead(2,0,8192,128,@gateRead[0])=0 Or gateRead[0]<>8 : ProcedureReturn 24 : EndIf
 ExFatSetRangeWriter(@GateWriter)
 PokeA(@gateDisk[0]+base*512,88) : ExFatSetRangeReader(@GateReader)
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>88 : ProcedureReturn 12 : EndIf
 exfat_Copy(@gateBig[0],@gateDisk[0]+base*512,512) : gateBig[0]=123
 If exfat_WriteBlocks(base,1,@gateBig[0])=0 : ProcedureReturn 13 : EndIf
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or gateRead[0]<>123 : ProcedureReturn 14 : EndIf
 ExFatSetRangeWriter(@ProofPartialDirectoryWrite)
 If exfat_WriteBlocks(base,1,@gateBig[0])<>0 : ProcedureReturn 15 : EndIf
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or (gateRead[0] & 255)<>166 : ProcedureReturn 16 : EndIf
 exfat_DropCaches() : exfat_error=0 : exfat_dirty=1 : exfat_ioFailed=0 : gateFailLba=base+1
 If exfat_DirRead(2,2,8192,0,@gateRead[0])=0 Or (gateRead[0] & 255)<>166 : ProcedureReturn 17 : EndIf
 If exfat_error<>0 Or exfat_ioFailed<>0 : ProcedureReturn 18 : EndIf
 If exfat_DirRead(2,2,8192,16,@gateRead[0])<>0 Or exfat_ioFailed<>1 : ProcedureReturn 19 : EndIf
 gateFailLba=-1 : exfat_dirty=0 : exfat_ioFailed=0 : ExFatSetRangeWriter(0)
 ProcedureReturn 0
EndProcedure
Global profileTestClock.i
Procedure.i ProofProfileClock()
 profileTestClock=profileTestClock+10 : ProcedureReturn profileTestClock
EndProcedure
Procedure ProofRepairBoot(base.i)
 Define i.i,sum.i
 sum=GateBootChecksum(base)
 For i=0 To 508 Step 4 : exfat_Put32(@gateDisk[0]+(base+11)*512,i,sum) : Next
EndProcedure
Procedure.i ProofDriftingBootReader(lba.i,count.i,dst.i)
 If lba=1 And count=12
  exfat_Put32(@gateDisk[0]+512,96,3)
  exfat_Put32(@gateDisk[0]+13*512,96,3)
  ProofRepairBoot(1) : ProofRepairBoot(13)
 EndIf
 ProcedureReturn GateReader(lba,count,dst)
EndProcedure
Procedure ProofPrepareBoot()
 GateFormat() : gateFailLba=-1
 ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(0)
 exfat_partLba=1 : exfat_partBlocks=2048 : exfat_error=0 : exfat_ioFailed=0
 gateReads=0
EndProcedure
Procedure.i ProofBootSnapshots()
 Define i.i,rc.i
 ProofPrepareBoot()
 If exfat_ReadBoot()=0 Or gateReads<>4 : ProcedureReturn 1 : EndIf
 PokeI($E1C00090,gateReads)
 ; Every immutable byte must still match, even with a valid backup checksum.
 For i=64 To 111
  If i<>106 And i<>107
   ProofPrepareBoot()
   gateDisk[13*512+i]=gateDisk[13*512+i] ! 1 : ProofRepairBoot(13)
   If exfat_ReadBoot()<>0 Or exfat_error<>#EXFAT_E_BOOT : ProcedureReturn 100+i : EndIf
  EndIf
 Next
 ProofPrepareBoot()
 gateDisk[13*512+106]=255 : gateDisk[13*512+107]=255 : gateDisk[13*512+112]=100
 If exfat_ReadBoot()=0 : ProcedureReturn 2 : EndIf
 For i=0 To 1
  ProofPrepareBoot() : gateDisk[(1+i*12)*512+200]=1
  If exfat_ReadBoot()<>0 Or exfat_error<>#EXFAT_E_BOOT_CHECKSUM : ProcedureReturn 3+i : EndIf
  ProofPrepareBoot() : gateFailLba=5+i*12
  rc=exfat_ReadBoot() : gateFailLba=-1
  If rc<>0 Or exfat_error<>#EXFAT_E_READ : ProcedureReturn 5+i : EndIf
 Next
 ProofPrepareBoot() : ExFatSetRangeReader(@ProofDriftingBootReader)
 If exfat_ReadBoot()<>0 Or exfat_error<>#EXFAT_E_BOOT : ProcedureReturn 7 : EndIf
 ProofPrepareBoot()
 ProcedureReturn 0
EndProcedure
Procedure.i ProofMountStages()
 Define stage.i,reads.i
 ProofPrepareBoot() : exfat_MountReset()
 For stage=0 To 5
  If exfat_mounted<>0 : ProcedureReturn 1 : EndIf
  If exfat_MountStage(1,stage)=0 : ProcedureReturn 10+stage : EndIf
  If exfat_mounted<>0 : ProcedureReturn 2 : EndIf
 Next
 exfat_MountFinish()
 If exfat_mounted<>1 Or exfat_upcaseFastReady<>1 : ProcedureReturn 3 : EndIf
 ProofPrepareBoot() : exfat_MountReset()
 reads=gateReads
 If exfat_MountStage(1,-1)<>0 Or exfat_error<>#EXFAT_E_BOUNDS : ProcedureReturn 4 : EndIf
 If exfat_MountStage(1,6)<>0 Or exfat_error<>#EXFAT_E_BOUNDS : ProcedureReturn 5 : EndIf
 If gateReads<>reads Or exfat_mounted<>0 : ProcedureReturn 6 : EndIf
 ; A later validation failure cannot publish the partial volume.
 For stage=0 To 2
  If exfat_MountStage(1,stage)=0 : ProcedureReturn 20+stage : EndIf
 Next
 exfat_upcaseChecksum=exfat_upcaseChecksum ! 1
 If exfat_MountStage(1,3)<>0 Or exfat_error<>#EXFAT_E_UPCASE_CHECKSUM Or exfat_mounted<>0 : ProcedureReturn 7 : EndIf
 ; The ordinary entry point still resets and completes the same stages.
 If ExFatMount(1)=0 Or exfat_mounted<>1 : ProcedureReturn 8 : EndIf
 ProcedureReturn 0
EndProcedure
Global proofMountCallbackFault.i
Procedure.i ProofReplacingReader(lba.i,count.i,dst.i)
 ExFatSetRangeReader(@GateReader)
 If ExFatMountBegin(1)<>0 : proofMountCallbackFault=1 : EndIf
 If ExFatMountPending()<>1 : proofMountCallbackFault=2 : EndIf
 ProcedureReturn GateReader(lba,count,dst)
EndProcedure
Procedure.i ProofMountJobs()
 Define h.i,nextHandle.i,stage.i,stopAt.i,rc.i,reads.i,saved.i
 ProofPrepareBoot() : exfat_MountReset() : reads=gateReads
 h=ExFatMountBegin(1)
 If h<=0 Or gateReads<>reads Or ExFatMountPending()<>1 : ProcedureReturn 1 : EndIf
 If ExFatMountBegin(1)<>0 Or ExFatLastError()<>#EXFAT_E_BUSY : ProcedureReturn 2 : EndIf
 If ExFatMount(1)<>0 Or ExFatLastError()<>#EXFAT_E_BUSY : ProcedureReturn 3 : EndIf
 If ExFatMountStep(h+1)<>-1 Or ExFatMountCancel(h+1)<>0 Or ExFatMountPending()<>1 : ProcedureReturn 4 : EndIf
 exfat_mountRunning=1 : rc=ExFatMountStep(h) : exfat_mountRunning=0
 If rc<>-1 Or ExFatLastError()<>#EXFAT_E_BUSY Or gateReads<>reads : ProcedureReturn 69 : EndIf
 If ExFatProbePartition(1,0,0)<>0 Or ExFatUnmount()<>0 Or ExFatDirRewind()<>0 : ProcedureReturn 5 : EndIf
 If ExFatDirNext()<>-1 Or ExFatOpen(0)<>0 Or ExFatBytesPerCluster()<>0 Or gateReads<>reads : ProcedureReturn 6 : EndIf
 For stage=0 To 5
  rc=ExFatMountStep(h)
  If rc<>Bool(stage=5) Or ExFatMounted()<>Bool(stage=5) : ProcedureReturn 10+stage : EndIf
 Next
 If ExFatMountPending()<>0 Or ExFatMountStep(h)<>-1 Or ExFatMounted()<>1 : ProcedureReturn 7 : EndIf
 For stopAt=0 To 5
  ProofPrepareBoot() : exfat_MountReset() : h=ExFatMountBegin(1)
  For stage=0 To stopAt-1
   If ExFatMountStep(h)<>0 : ProcedureReturn 20+stage : EndIf
  Next
  reads=gateReads
  If ExFatMountCancel(h)<>1 Or ExFatMountPending()<>0 Or ExFatMounted()<>0 Or gateReads<>reads : ProcedureReturn 30+stopAt : EndIf
  nextHandle=ExFatMountBegin(1)
  If nextHandle<=h Or ExFatMountCancel(h)<>0 Or ExFatMountPending()<>1 : ProcedureReturn 40+stopAt : EndIf
  If ExFatMountCancel(nextHandle)<>1 : ProcedureReturn 50+stopAt : EndIf
 Next
 ProofPrepareBoot() : exfat_MountReset() : h=ExFatMountBegin(1)
 If ExFatMountStep(h)<>0 : ProcedureReturn 8 : EndIf
 ExFatSetRangeReader(@GateReader) : reads=gateReads
 If ExFatMountStep(h)<>-1 Or ExFatMountPending()<>0 Or ExFatMounted()<>0 Or gateReads<>reads : ProcedureReturn 9 : EndIf
 ProofPrepareBoot() : exfat_MountReset() : h=ExFatMountBegin(1)
 If ExFatMountStep(h)<>0 : ProcedureReturn 60 : EndIf
 gateFailLba=1 : rc=ExFatMountStep(h) : gateFailLba=-1
 If rc<>-1 Or ExFatLastError()<>#EXFAT_E_READ Or ExFatMountPending()<>0 Or ExFatMounted()<>0 : ProcedureReturn 61 : EndIf
 ProofPrepareBoot() : exfat_MountReset() : ExFatSetRangeReader(@ProofReplacingReader)
 proofMountCallbackFault=0 : h=ExFatMountBegin(1)
 If ExFatMountStep(h)<>-1 Or ExFatLastError()<>#EXFAT_E_MOUNT_HANDLE : ProcedureReturn 66 : EndIf
 If ExFatMountPending()<>0 Or ExFatMounted()<>0 Or proofMountCallbackFault<>0 : ProcedureReturn 67 : EndIf
 If ExFatMount(1)=0 : ProcedureReturn 68 : EndIf
 ProofPrepareBoot() : exfat_MountReset() : ExFatSetRangeReader(@ProofReplacingReader)
 h=ExFatMountBegin(1) : exfat_mountRunning=1
 rc=exfat_ReadBlocks(0,1,@gateRead[0]) : exfat_mountRunning=0
 If rc<>0 Or ExFatLastError()<>#EXFAT_E_MOUNT_HANDLE Or ExFatMountPending()<>0 : ProcedureReturn 70 : EndIf
 reads=gateReads : exfat_mountRunning=1
 rc=exfat_ReadBlocks(0,1,@gateRead[0]) : exfat_mountRunning=0
 If rc<>0 Or gateReads<>reads Or ExFatLastError()<>#EXFAT_E_MOUNT_HANDLE : ProcedureReturn 71 : EndIf
 saved=exfat_mountNext : exfat_mountNext=$7FFFFFFF : reads=gateReads
 rc=ExFatMountBegin(1) : exfat_mountNext=saved
 If rc<>0 Or ExFatLastError()<>#EXFAT_E_BUSY Or gateReads<>reads : ProcedureReturn 62 : EndIf
 ProofPrepareBoot() : exfat_MountReset()
 If ExFatMount(1)=0 : ProcedureReturn 63 : EndIf
 exfat_open=1 : rc=ExFatMountBegin(1) : exfat_open=0
 If rc<>0 Or ExFatMounted()<>1 : ProcedureReturn 64 : EndIf
 exfat_dirty=1 : rc=ExFatMountBegin(1) : exfat_dirty=0
 If rc<>0 Or ExFatMounted()<>1 : ProcedureReturn 65 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure ProofPrepareFacade()
 ProofPrepareBoot() : exfat_MountReset()
 fs_kind=#FS_NONE : fs_partition=0
 FsSetRangeReader(@GateReader) : FsSetRangeWriter(0) : FsSetBlockFlusher(0)
EndProcedure
Global proofFsCallbackFault.i
Procedure.i ProofFsReplacingReader(lba.i,count.i,dst.i)
 FsSetRangeReader(@GateReader)
 If FsMountBegin(1)<>0 Or FsMountPending()<>1 : proofFsCallbackFault=1 : EndIf
 ProcedureReturn GateReader(lba,count,dst)
EndProcedure
Procedure.i ProofFsCancelFlusher()
 FsSetRangeReader(@GateReader)
 ProcedureReturn 0
EndProcedure
Procedure.i ProofFsFailedFlusher()
 ProcedureReturn 0
EndProcedure
Procedure.i ProofFacadeJobs()
 Define h.i,nextHandle.i,i.i,stopAt.i,rc.i,reads.i
 ProofPrepareFacade()
 If FsMount(1)=0 : ProcedureReturn 1 : EndIf
 reads=gateReads : fs_rest=123 : h=FsMountBegin(2)
 If h<=0 Or gateReads<>reads : ProcedureReturn 2 : EndIf
 If FsMount(1)<>0 Or FsUnmount()<>0 Or FsSelectPartition(1)<>0 : ProcedureReturn 3 : EndIf
 If FsOpen(0)<>0 Or FsRename(0,0)<>0 Or fs_rest<>123 : ProcedureReturn 4 : EndIf
 If FsRead(@gateRead[0],1)<>-1 Or FsWrite(@gateRead[0],1)<>-1 Or FsTableRead()<>0 : ProcedureReturn 5 : EndIf
 FsClose()
 If gateReads<>reads Or fs_kind<>#FS_EXFAT Or fs_partition<>1 : ProcedureReturn 6 : EndIf
 If FsMountStep(h+1)<>-1 Or FsMountCancel(h+1)<>0 Or FsMountPending()<>1 : ProcedureReturn 7 : EndIf
 If FsMountCancel(h)<>1 Or FsType()<>#FS_EXFAT Or FsPartition()<>1 : ProcedureReturn 8 : EndIf
 h=FsMountBegin(1) : reads=gateReads
 If FsMountStep(h)<>1 Or gateReads<>reads Or FsMountPending()<>0 : ProcedureReturn 9 : EndIf
 For stopAt=0 To 6
  ProofPrepareFacade() : h=FsMountBegin(1)
  For i=0 To stopAt-1
   If FsMountStep(h)<>0 : ProcedureReturn 20+i : EndIf
  Next
  If FsMountCancel(h)<>1 Or FsMountPending()<>0 Or ExFatMountPending()<>0 : ProcedureReturn 30+stopAt : EndIf
  nextHandle=FsMountBegin(1)
  If nextHandle<=h Or FsMountCancel(h)<>0 Or FsMountPending()<>1 : ProcedureReturn 40+stopAt : EndIf
  If FsMountCancel(nextHandle)<>1 : ProcedureReturn 50+stopAt : EndIf
 Next
 ProofPrepareFacade() : h=FsMountBegin(1)
 For i=0 To 6
  rc=FsMountStep(h)
  If rc<>Bool(i=6) : ProcedureReturn 60+i : EndIf
 Next
 If FsType()<>#FS_EXFAT Or FsPartition()<>1 Or FsMountStep(h)<>-1 : ProcedureReturn 10 : EndIf
 ProofPrepareFacade() : h=FsMountBegin(1)
 If FsMountStep(h)<>0 : ProcedureReturn 11 : EndIf
 FsSetRangeReader(@GateReader)
 If FsMountPending()<>0 Or FsMountStep(h)<>-1 Or FsType()<>#FS_NONE : ProcedureReturn 12 : EndIf
 ProofPrepareFacade() : FsSetRangeReader(@ProofFsReplacingReader) : proofFsCallbackFault=0
 h=FsMountBegin(1)
 If FsMountStep(h)<>0 Or FsMountStep(h)<>-1 : ProcedureReturn 13 : EndIf
 If FsMountPending()<>0 Or FsErrorKind()<>#FS_FACADE Or FsLastError()<>#FS_E_MOUNT_HANDLE Or proofFsCallbackFault<>0 : ProcedureReturn 14 : EndIf
 ; Cancellation during unmount must not start a new driver job afterward.
 ProofPrepareFacade() : If FsMount(1)=0 : ProcedureReturn 15 : EndIf
 exfat_dirty=1 : FsSetBlockFlusher(@ProofFsCancelFlusher)
 h=FsMountBegin(2)
 If FsMountStep(h)<>-1 Or FsMountPending()<>0 Or ExFatMountPending()<>0 : ProcedureReturn 16 : EndIf
 ; Two MBR names alias this virtual volume for recovery-path testing.
 ProofPrepareFacade() : If FsMount(1)=0 : ProcedureReturn 17 : EndIf
 gateDisk[$1CE+4]=7 : exfat_Put32(@gateDisk[0],$1CE+8,1) : exfat_Put32(@gateDisk[0],$1CE+12,2048)
 exfat_Put16(@gateDisk[0]+512,106,2) : exfat_Put16(@gateDisk[0]+13*512,106,2)
 exfat_dirty=1 : FsSetBlockFlusher(@ProofFsFailedFlusher) : gateWrites=0
 h=FsMountBegin(2)
 If FsMountStep(h)<>1 Or FsPartition()<>2 Or gateWrites<>0 Or exfat_inheritedDirty<>1 : ProcedureReturn 18 : EndIf
 FsSetBlockFlusher(0)
 ; Corrupt exFAT must not be reinterpreted as FAT32.
 ProofPrepareFacade() : gateDisk[512+200]=1 : h=FsMountBegin(1)
 Repeat : rc=FsMountStep(h) : Until rc<>0
 If rc<>-1 Or FsErrorKind()<>#FS_EXFAT Or ExFatLastError()<>#EXFAT_E_BOOT_CHECKSUM : ProcedureReturn 19 : EndIf
 ; Sparse FAT32 metadata fixture: only the mount's metadata reads are backed.
 ProofPrepareFacade() : exfat_Zero(@gateDisk[0],#GATE_BYTES)
 gateDisk[510]=$55 : gateDisk[511]=$AA : gateDisk[$1BE+4]=$0C
 exfat_Put32(@gateDisk[0],$1BE+8,1) : exfat_Put32(@gateDisk[0],$1BE+12,70000)
 exfat_Put16(@gateDisk[0]+512,11,512) : gateDisk[512+13]=1
 exfat_Put16(@gateDisk[0]+512,14,32) : gateDisk[512+16]=1
 exfat_Put32(@gateDisk[0]+512,32,70000) : exfat_Put32(@gateDisk[0]+512,36,600)
 exfat_Put32(@gateDisk[0]+512,44,2) : exfat_Put16(@gateDisk[0]+512,48,1)
 gateDisk[512+510]=$55 : gateDisk[512+511]=$AA
 exfat_Put32(@gateDisk[0]+1024,0,$41615252) : exfat_Put32(@gateDisk[0]+1024,484,$61417272)
 exfat_Put32(@gateDisk[0]+1024,488,$FFFFFFFF) : exfat_Put32(@gateDisk[0]+1024,492,$FFFFFFFF)
 exfat_Put32(@gateDisk[0]+1024,508,$AA550000)
 h=FsMountBegin(1) : i=0
 Repeat : rc=FsMountStep(h) : i=i+1 : Until rc<>0 Or i>8
 If rc<>1 Or FsType()<>#FS_FAT Or FsPartition()<>1 : ProcedureReturn 70 : EndIf
 ProofPrepareFacade()
 ProcedureReturn 0
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,j.i,n.i,start.i,slow.i,fast.i,old.i,new.i,p.i,reads.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 9999 : EndIf
 MmuEnableCached()
 PokeI($E1C00000,$58464337)
 PokeI($E1C00040,ExFatProfileBegin())
 ExFatProfileSetClock(@ProofProfileClock)
 start=ExFatProfileBegin() : ExFatProfileEnd(0,start)
 start=ExFatProfileBegin() : ExFatProfileEnd(0,start)
 ExFatProfileEnd(-1,0) : ExFatProfileEnd(7,0) : ExFatProfileEnd(0,-1) : ExFatProfileEnd(0,999)
 PokeI($E1C00048,ExFatProfileValue(0,0))
 PokeI($E1C00050,ExFatProfileValue(0,1))
 PokeI($E1C00058,ExFatProfileValue(0,2))
 ExFatProfileSetClock(0) : PokeI($E1C00060,ExFatProfileValue(0,0))
 PokeI($E1C00068,ExFatProfileValue(7,0))
 rc=GateMain() : PokeI($E1C00008,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn rc : EndIf
 rc=ProofBootSnapshots() : PokeI($E1C00088,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 9800+rc : EndIf
 rc=ProofMountStages() : PokeI($E1C00098,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 9900+rc : EndIf
 rc=ProofMountJobs() : PokeI($E1C000A0,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 10000+rc : EndIf
 rc=ProofFacadeJobs() : PokeI($E1C000A8,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 11000+rc : EndIf
 rc=ProofDirectoryCache() : PokeI($E1C00080,rc)
 If rc<>0 : MmuDisableCachedFlushed() : ProcedureReturn 9500+rc : EndIf
 GateFormat() : ExFatSetRangeReader(@GateReader) : ExFatSetRangeWriter(0) : exfat_MountReset()
 rc=ExFatMount(1) : If rc=0 : MmuDisableCachedFlushed() : ProcedureReturn 9000+ExFatLastError() : EndIf
 For i=10 To 73 : exfat_Put32(@gateDisk[0]+25*512,i*4,i+1) : Next
 exfat_Put32(@gateDisk[0]+25*512,73*4,$FFFFFFFF)
 For i=0 To 32767 : gateDisk[35*512+i]=(i*37+19) & 255 : Next
 exfat_upcaseCluster=10
__CHECKSUM_ROWS__
 exfat_upcaseLength=1024 : gateFailLba=36 : exfat_DropCaches()
 PokeI($E1C00018,exfat_UpcaseTableChecksum()) : gateFailLba=-1
 PrepareTable(255) : ValidationRow(0)
 PokeI($E1C01020,exfat_BuildFastUpcase()) : PokeI($E1C01028,exfat_upcaseFast[255] & $FFFF)
 PrepareTable(4095) : ValidationRow(1)
 PrepareTable(4095) : exfat_upcaseLength=8194 : ValidationRow(2)
 PrepareTable(4095) : exfat_Put16(@gateDisk[0]+35*512,8192,0) : ValidationRow(3)
 PrepareTable(4095) : exfat_Put16(@gateDisk[0]+35*512,8192,65535) : ValidationRow(4)
 PrepareTable(4095) : exfat_upcaseLength=8198 : ValidationRow(5)
 PrepareTable(4095) : gateFailLba=36 : ValidationRow(6) : gateFailLba=-1
 PrepareTable(255) : exfat_Put16(@gateDisk[0]+35*512,194,97) : exfat_DropCaches()
 PokeI($E1C00020,OldBuildFast()) : exfat_DropCaches() : PokeI($E1C00028,exfat_BuildFastUpcase())
 PokeI($E1C00010,A64CounterFrequency())
 MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
'''
    rows=[]
    for i,n in enumerate(cases):
        rows.append(f" exfat_upcaseLength={n} : p=$E1C00100+{i}*64\n"
            " exfat_DropCaches() : start=A64CounterReadOrdered() : old=OldChecksum() : slow=A64CounterReadOrdered()-start\n"
            " exfat_DropCaches() : reads=gateReads : start=A64CounterReadOrdered() : new=exfat_UpcaseTableChecksum() : fast=A64CounterReadOrdered()-start\n"
            " PokeI(p,old) : PokeI(p+8,new) : PokeI(p+16,slow) : PokeI(p+24,fast) : PokeI(p+32,gateReads-reads)\n")
    s=s.replace('__CHECKSUM_ROWS__', ''.join(rows))
    names.append('tools/build_exfat_checksum_cpu.py')
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
