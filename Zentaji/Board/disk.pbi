; Zentaji block-device transport for Anvil's existing filesystem range seam.
; One serialized owner/core, one outstanding command, private two-entry queues.
; All DMA uses the private 4KB bounce buffer. A timeout quarantines that buffer
; and both rings until the actual completion retires; CTRL=0 is not DMA cancel.
; Caller buffers are never held by the device after a failed call returns.
; 512-byte writes use read/modify/write for partial 4KB blocks; exclusive medium
; ownership excludes other writers during that sequence. Acquisition requires a
; quiesced predecessor: disabled/empty registers alone cannot fence old DMA.
; Persistent emulator bindings sync FUA/FLUSH; explicit disk-memory bindings
; isolate writes for snapshots. A failed write can
; still complete later. This is not an atomic multi-sector transaction.
; Normal supervisor context with IE=0 and a qualified bounded idle source is
; required. The board owns INTC routing (line9 may wake early) and the idle timer.
XIncludeFile "Zentaji/Board/prompt_idle.pbi"
#ZEN_DISK_BASE=$FFFF000000200000
#ZEN_DISK_E_STATE=1
#ZEN_DISK_E_ARGUMENT=2
#ZEN_DISK_E_FOREIGN=3
#ZEN_DISK_E_CONTEXT=4
#ZEN_DISK_E_READONLY=5
#ZEN_DISK_E_TIMEOUT=6
#ZEN_DISK_E_COMPLETION=7
#ZEN_DISK_E_DEVICE=8
#ZEN_DISK_E_CLOCK=9
#ZEN_DISK_E_NO_DEVICE=10
#ZEN_DISK_POLLS=4096

Structure ZentajiDiskState
 base.i
 state.i
 owner.i
 pending.i
 error.i
 deviceStatus.i
 blocks.i
 ram.i
 sq.i
 cq.i
 bounce.i
 tail.i
 head.i
 phase.i
 tag.q
 waitTicks.q
 oldSq.i
 oldSqN.i
 oldCq.i
 oldCqN.i
 oldIrq.i
EndStructure
Global zenDisk.ZentajiDiskState
Global Dim zenDiskSq.a[128]
Global Dim zenDiskCq.a[128]
Global Dim zenDiskBounce.a[4160]

Procedure.i ZentajiDiskFail(code.i)
 zenDisk\error=code
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiDiskLastError() : ProcedureReturn zenDisk\error : EndProcedure
Procedure.i ZentajiDiskErrorText()
 Select zenDisk\error
  Case 0 : ProcedureReturn "disk: no error"
  Case #ZEN_DISK_E_STATE : ProcedureReturn "disk: not ready or an operation is still outstanding"
  Case #ZEN_DISK_E_ARGUMENT : ProcedureReturn "disk: invalid sector range or RAM buffer"
  Case #ZEN_DISK_E_FOREIGN : ProcedureReturn "disk: controller configuration is not owned by this driver"
  Case #ZEN_DISK_E_CONTEXT : ProcedureReturn "disk: requires the owning supervisor core, masked delivery and a qualified idle source"
  Case #ZEN_DISK_E_READONLY : ProcedureReturn "disk: the medium is read only"
  Case #ZEN_DISK_E_TIMEOUT : ProcedureReturn "disk: deadline expired; private DMA storage remains quarantined until completion"
  Case #ZEN_DISK_E_COMPLETION : ProcedureReturn "disk: completion tag, phase or queue position is not the expected request"
  Case #ZEN_DISK_E_DEVICE : ProcedureReturn "disk: device completed with an error; inspect ZentajiDiskDeviceStatus"
  Case #ZEN_DISK_E_CLOCK : ProcedureReturn "disk: deadline is invalid or cannot be represented by the hardware clock"
  Case #ZEN_DISK_E_NO_DEVICE : ProcedureReturn "disk: no configured version-1 block device at that instance"
 EndSelect
 ProcedureReturn "disk: unknown driver error"
EndProcedure
Procedure.i ZentajiDiskDeviceStatus() : ProcedureReturn zenDisk\deviceStatus : EndProcedure
Procedure.i ZentajiDiskMode() : ProcedureReturn zenDisk\state : EndProcedure
Procedure.i ZentajiDiskSectors()
 If zenDisk\state=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn zenDisk\blocks*8
EndProcedure

Procedure.i ZentajiDiskOwned()
 If zenDisk\state=0 Or ZenCpuCoreId()<>zenDisk\owner : ProcedureReturn 0 : EndIf
 If PeekQ(zenDisk\base+$70)<>zenDisk\tail Or PeekQ(zenDisk\base+$78)<>zenDisk\tail Or PeekQ(zenDisk\base+$90)<>zenDisk\head : ProcedureReturn 0 : EndIf
 If zenDisk\pending=0 And PeekQ(zenDisk\base+$98)<>zenDisk\head : ProcedureReturn 0 : EndIf
 If PeekQ(zenDisk\base+$10)<>3 Or PeekQ(zenDisk\base+$60)<>zenDisk\sq Or PeekQ(zenDisk\base+$68)<>2 Or PeekQ(zenDisk\base+$80)<>zenDisk\cq Or PeekQ(zenDisk\base+$88)<>2 Or PeekQ(zenDisk\base+$20)<>1 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskTimeoutUs(us.i)
 Protected hz.i,ticks.q
 If zenDisk\state<>1 Or zenDisk\pending<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_STATE) : EndIf
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>zenDisk\owner : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 hz=TickHz()
 If us<1 Or us>2000000 Or hz<1 Or hz>$7FFFFFFFFFFFFFFF/us : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CLOCK) : EndIf
 ticks=(hz*us)/1000000
 If ticks<1 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CLOCK) : EndIf
 zenDisk\waitTicks=ticks : zenDisk\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskPresent(disk.i)
 Protected table.i=$FFFF000000010000,entries.i,i.i,at.i
 If PeekQ(table)<>$00494A41544E455A Or PeekU(table+8)<>1 Or PeekU(table+10)<>64 Or PeekL(table+20)<>64 : ProcedureReturn 0 : EndIf
 entries=PeekL(table+16)
 If entries<1 Or entries>1023 Or PeekL(table+12)<64+entries*64 : ProcedureReturn 0 : EndIf
 For i=0 To entries-1
  at=table+64+i*64
  If PeekU(at)=18 And PeekA(at+2)=disk And (PeekA(at+5)&1)<>0
   If PeekQ(at+8)=#ZEN_DISK_BASE+disk*65536 And PeekQ(at+16)>=160 : ProcedureReturn 1 : EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiDiskOpen(disk.i)
 Protected base.i,n.i,hz.i
 If zenDisk\state<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_STATE) : EndIf
 If disk<0 Or disk>15 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 If ZenCpuStatus()<>0 Or HwPromptIdleReady()=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 If ZentajiDiskPresent(disk)=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_NO_DEVICE) : EndIf
 base=#ZEN_DISK_BASE+disk*65536
 If (PeekQ(base)&65535)<>18 Or ((PeekQ(base)>>16)&255)<>1 Or PeekQ(base+$48)<>4096 Or PeekQ(base+$40)<1 Or PeekQ(base+$40)>$7FFFFFFFFFFFFFFF/8 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 ; A disabled but dirty queue is not an idle device we may acquire.
 If PeekQ(base+$10)<>0 Or PeekQ(base+$08)<>0 Or PeekQ(base+$18)<>0 Or PeekQ(base+$70)<>0 Or PeekQ(base+$78)<>0 Or PeekQ(base+$90)<>0 Or PeekQ(base+$98)<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN) : EndIf
 zenDisk\base=base : zenDisk\owner=ZenCpuCoreId() : zenDisk\ram=PeekQ($FFFF000000010018)
 zenDisk\sq=(@zenDiskSq[0]+63)&-64 : zenDisk\cq=(@zenDiskCq[0]+63)&-64 : zenDisk\bounce=(@zenDiskBounce[0]+63)&-64
 If zenDisk\sq<0 Or zenDisk\sq>zenDisk\ram-64 Or zenDisk\cq<0 Or zenDisk\cq>zenDisk\ram-32 Or zenDisk\bounce<0 Or zenDisk\bounce>zenDisk\ram-4096 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 hz=TickHz()
 If hz<1 Or hz>$7FFFFFFFFFFFFFFF/2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CLOCK) : EndIf
 zenDisk\oldSq=PeekQ(base+$60) : zenDisk\oldSqN=PeekQ(base+$68)
 zenDisk\oldCq=PeekQ(base+$80) : zenDisk\oldCqN=PeekQ(base+$88) : zenDisk\oldIrq=PeekQ(base+$20)
 For n=0 To 63 : PokeA(zenDisk\sq+n,0) : Next
 For n=0 To 31 : PokeA(zenDisk\cq+n,0) : Next
 zenDisk\blocks=PeekQ(base+$40) : zenDisk\tail=0 : zenDisk\head=0 : zenDisk\phase=1 : zenDisk\tag=0 : zenDisk\pending=0
 zenDisk\waitTicks=hz*2 : zenDisk\deviceStatus=0
 PokeQ(base+$60,zenDisk\sq) : PokeQ(base+$68,2)
 PokeQ(base+$80,zenDisk\cq) : PokeQ(base+$88,2)
 PokeQ(base+$20,1) : PokeQ(base+$10,3)
 zenDisk\state=1 : zenDisk\error=0
 If ZentajiDiskOwned()=0 Or PeekQ(base+$08)<>0
  zenDisk\state=2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN)
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskPoll()
 Protected tail.i,at.i,status.i,nextHead.i
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>zenDisk\owner : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 If ZentajiDiskOwned()=0 : zenDisk\state=2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN) : EndIf
 If zenDisk\pending=0 : ProcedureReturn 1 : EndIf
 tail=PeekQ(zenDisk\base+$98)
 If tail=zenDisk\head : ProcedureReturn 0 : EndIf
 at=zenDisk\cq+zenDisk\head*16 : nextHead=(zenDisk\head+1)&1
 If tail<>nextHead Or PeekQ(at)<>zenDisk\tag Or PeekU(at+14)<>zenDisk\phase Or PeekU(at+12)<>zenDisk\tail
  zenDisk\state=2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_COMPLETION)
 EndIf
 status=PeekL(at+8)
 PokeQ(zenDisk\base+$90,nextHead) : PokeQ(zenDisk\base+$18,1)
 zenDisk\head=nextHead
 If nextHead=0 : zenDisk\phase=1-zenDisk\phase : EndIf
 zenDisk\deviceStatus=status : zenDisk\pending=0
 If status<>0 : ZentajiDiskFail(#ZEN_DISK_E_DEVICE) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskCommand(op.i,lba.i)
 Protected at.i,n.i,start.q
 If zenDisk\state<>1 Or zenDisk\pending<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_STATE) : EndIf
 If ZenCpuStatus()<>0 Or HwPromptIdleReady()=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 If ZentajiDiskOwned()=0 : zenDisk\state=2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN) : EndIf
 If op<>3 And (lba<0 Or lba>=zenDisk\blocks) : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 If (op=2 Or op=4) And (PeekQ(zenDisk\base+$58)&1)<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_READONLY) : EndIf
 zenDisk\error=0 : zenDisk\deviceStatus=0 : zenDisk\tag=zenDisk\tag+1
 If zenDisk\tag=0 : zenDisk\tag=1 : EndIf
 at=zenDisk\sq+zenDisk\tail*32
 PokeQ(at,0) : PokeA(at,op)
 If op=2 : PokeA(at+1,1) : EndIf
 If op<>3 : PokeL(at+4,1) : EndIf
 PokeQ(at+8,lba) : PokeQ(at+16,zenDisk\bounce) : PokeQ(at+24,zenDisk\tag)
 zenDisk\tail=(zenDisk\tail+1)&1 : zenDisk\pending=1
 start=Ticks() : PokeQ(zenDisk\base+$70,zenDisk\tail)
 For n=1 To #ZEN_DISK_POLLS
  If ZentajiDiskPoll()<>0 : ProcedureReturn Bool(zenDisk\deviceStatus=0) : EndIf
  If zenDisk\state<>1 : ProcedureReturn 0 : EndIf
  If Ticks()-start>=zenDisk\waitTicks : Break : EndIf
  If HwPromptIdleReady()=0 : Break : EndIf
  HwPromptIdleWait()
 Next
 ; The device has no cancel command. Keep the private DMA storage pinned.
 zenDisk\state=2
 ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_TIMEOUT)
EndProcedure

Procedure.i ZentajiDiskClose()
 If zenDisk\state=0 : zenDisk\error=0 : ProcedureReturn 1 : EndIf
 If ZenCpuStatus()<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 If ZentajiDiskOwned()=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN) : EndIf
 If zenDisk\pending<>0
  If ZentajiDiskPoll()=0 : ProcedureReturn 0 : EndIf
 EndIf
 ; Re-enable the empty private queues once to reset their indices/phase, then
 ; restore the acquired disabled configuration. No request is submitted here.
 PokeQ(zenDisk\base+$10,0) : PokeQ(zenDisk\base+$10,3) : PokeQ(zenDisk\base+$10,0)
 PokeQ(zenDisk\base+$60,zenDisk\oldSq) : PokeQ(zenDisk\base+$68,zenDisk\oldSqN)
 PokeQ(zenDisk\base+$80,zenDisk\oldCq) : PokeQ(zenDisk\base+$88,zenDisk\oldCqN) : PokeQ(zenDisk\base+$20,zenDisk\oldIrq)
 zenDisk\state=0 : zenDisk\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskBuffer(address.i,bytes.i)
 If address<0 Or bytes<0 Or bytes>zenDisk\ram Or address>zenDisk\ram-bytes : ProcedureReturn 0 : EndIf
 If bytes=0 : ProcedureReturn 1 : EndIf
 If address<@zenDisk+SizeOf(ZentajiDiskState) And address+bytes>@zenDisk : ProcedureReturn 0 : EndIf
 If address<@zenDiskSq[0]+128 And address+bytes>@zenDiskSq[0] : ProcedureReturn 0 : EndIf
 If address<@zenDiskCq[0]+128 And address+bytes>@zenDiskCq[0] : ProcedureReturn 0 : EndIf
 If address<@zenDiskBounce[0]+4160 And address+bytes>@zenDiskBounce[0] : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskRange(lba.i,count.i,buffer.i,write.i)
 Protected offset.i,n.i,i.i,block.i,bytes.i
 If zenDisk\state<>1 Or zenDisk\pending<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_STATE) : EndIf
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>zenDisk\owner Or HwPromptIdleReady()=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_CONTEXT) : EndIf
 If ZentajiDiskOwned()=0 : zenDisk\state=2 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_FOREIGN) : EndIf
 If lba<0 Or count<0 Or lba>zenDisk\blocks*8 Or count>zenDisk\blocks*8-lba Or count>zenDisk\ram/512 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 bytes=count*512
 If ZentajiDiskBuffer(buffer,bytes)=0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_ARGUMENT) : EndIf
 If count=0 : zenDisk\error=0 : ProcedureReturn 1 : EndIf
 If write And (PeekQ(zenDisk\base+$58)&1)<>0 : ProcedureReturn ZentajiDiskFail(#ZEN_DISK_E_READONLY) : EndIf
 While count>0
  offset=(lba&7)*512 : n=8-(lba&7)
  If n>count : n=count : EndIf
  block=lba/8
  If write=0 Or offset<>0 Or n<>8
   If ZentajiDiskCommand(1,block)=0 : ProcedureReturn 0 : EndIf
  EndIf
  For i=0 To n*512-1
   If write : PokeA(zenDisk\bounce+offset+i,PeekA(buffer+i)) : Else : PokeA(buffer+i,PeekA(zenDisk\bounce+offset+i)) : EndIf
  Next
  If write
   If ZentajiDiskCommand(2,block)=0 : ProcedureReturn 0 : EndIf
  EndIf
  lba=lba+n : count=count-n : buffer=buffer+n*512
 Wend
 zenDisk\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiDiskRead(lba.i,count.i,*buffer)
 ProcedureReturn ZentajiDiskRange(lba,count,*buffer,0)
EndProcedure
Procedure.i ZentajiDiskWrite(lba.i,count.i,*buffer)
 ProcedureReturn ZentajiDiskRange(lba,count,*buffer,1)
EndProcedure
Procedure.i ZentajiDiskFlush() : ProcedureReturn ZentajiDiskCommand(3,0) : EndProcedure
