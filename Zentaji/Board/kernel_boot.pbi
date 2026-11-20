; booti stages a host-file ZEX; bootm stages an image in the ROM's 4 KiB
; boot-disk format. Only supervisor kernels are admitted. The original ROM
; boot source and the firmware device table remain the kernel's handoff.
Global zenKernelPending.i
Global Dim zenKernelPlan.q[6]
Procedure.i ZentajiKernelAbsent(plan.i,scratch.i) : ProcedureReturn 0 : EndProcedure
Global *zenKernelEnter=@ZentajiKernelAbsent

Procedure.i ZentajiKernelOwnsMachine()
 Protected count.i=ZentajiCoreCount(),id.i,base.i
 If count<1 Or ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 Or ZentajiPayloadProtection()<>0 Or HwPromptIdleReady()=0
  PrintN("!! kernel boot needs the primary supervisor and its idle timer.") : ProcedureReturn 0
 EndIf
 If ZentajiCoreRelease()=0 : PrintN("!! a secondary core changed ownership.") : ProcedureReturn 0 : EndIf
 For id=1 To count-1
  base=ZentajiCoreWindow(id)
  If PeekQ(base)<>0 Or PeekQ(base+8)<>0 Or PeekQ(base+$10)<>0 Or PeekQ(base+$18)<>0 Or PeekQ(base+$20)<>0
   PrintN("!! a secondary core belongs to another caller.") : ProcedureReturn 0
  EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure ZentajiCmdKernelBoot(diskImage.i)
 Protected addr.i,body.i,bytes.i,bss.i,load.i,entry.i,stack.i,crc.i,offset.i,stageHi.i,gate.i
 If BootDirty()<>0 : ProcedureReturn : EndIf
 addr=BootDefaultAddr() : If gBootAddrOk=0 : ProcedureReturn : EndIf
 SkipSpace()
 If gLine[gPos]<>0 : PrintN("? kernel boot takes one optional hexadecimal staging address.") : ProcedureReturn : EndIf
 offset=64 : If diskImage<>0 : offset=4096 : EndIf
 stageHi=HwPayHi(0)
 If addr<0 Or addr>stageHi-offset Or InPayload(addr,addr+offset-1)=0
  PrintN("!! the kernel header is outside staging RAM.") : ProcedureReturn
 EndIf
 If PeekQ(addr)<>$31494A41544E455A : PrintN("!! the staged header has no ZENTAJI1 signature.") : ProcedureReturn : EndIf
 entry=PeekQ(addr+8) : load=PeekQ(addr+16) : bytes=PeekQ(addr+24) : bss=PeekQ(addr+32)
 stack=PeekQ(addr+40) : body=addr+offset
 If PeekQ(addr+48)<>0 Or PeekL(addr+60)<>0
  PrintN("!! the image must have supervisor flags and a zero reserved field.") : ProcedureReturn
 EndIf
 If bytes<8 Or bytes>stageHi-body+1
  PrintN("!! the kernel body extends outside staging RAM.") : ProcedureReturn
 EndIf
 If gHaveEntry<>0 And gLoLo=addr And gHiHi<body+bytes-1
  PrintN("!! the most recent load did not contain the complete kernel body.") : ProcedureReturn
 EndIf
 If InPayload(body,body+bytes-1)=0 : PrintN("!! the kernel body crosses a protected staging range.") : ProcedureReturn : EndIf
 ; All code, graphics storage and the staging area can be reclaimed after
 ; shutdown. The old stack and the ROM work area stay intact during the copy.
 If load<0 Or (load&7)<>0 Or bss<0 Or load>zenMemoryStackBottom-bytes
  PrintN("!! the kernel load range overlaps the handoff stack or exceeds RAM.") : ProcedureReturn
 EndIf
 If bss>zenMemoryStackBottom-load-bytes Or entry<load Or entry>load+bytes-8 Or (entry&7)<>0
  PrintN("!! the kernel entry or BSS is outside the valid image extent.") : ProcedureReturn
 EndIf
 If stack=0 : stack=zenMemoryRam&-16 : EndIf
 If stack<16 Or stack>zenMemoryRam Or (stack&15)<>0 Or (stack>load And stack<=load+bytes+bss)
  PrintN("!! the kernel stack is unaligned, outside RAM or starts in the image.") : ProcedureReturn
 EndIf
 crc=Crc32(body,bytes)&$FFFFFFFF
 If crc<>(PeekL(addr+56)&$FFFFFFFF) : PrintN("!! kernel CRC-32 mismatch. Nothing was booted.") : ProcedureReturn : EndIf
 If zenMemoryContext<HwMonLo()+32 Or PeekQ(zenMemoryContext-32)<>$31544F4F424E455A
  PrintN("!! this monitor startup has no kernel handoff.") : ProcedureReturn
 EndIf
 gate=PeekQ(zenMemoryContext-24)
 If gate<ZentajiPayloadVectors()+4096 Or gate>=zenMemoryContext-32 Or (gate&7)<>0
  PrintN("!! the kernel handoff address is outside the supervisor startup.") : ProcedureReturn
 EndIf
 If ZentajiKernelOwnsMachine()=0 : ProcedureReturn : EndIf
 If ZentajiStorageDown()=0 : UartWriteStr(ZentajiStorageErrorText()) : PrintNl() : ProcedureReturn : EndIf
 zenKernelPlan[0]=body : zenKernelPlan[1]=load : zenKernelPlan[2]=bytes
 zenKernelPlan[3]=bss : zenKernelPlan[4]=entry : zenKernelPlan[5]=stack
 *zenKernelEnter=gate : zenKernelPending=1 : zenShellStop=1
 Print("Validated Zentaji supervisor kernel. Entry $") : PutHex16(entry) : Print(" CRC32 ") : PutHex8(crc) : PrintNl()
EndProcedure

Procedure ZentajiKernelHandoff()
 ; Timer and Ethernet interrupt admission were owned by this board. All its
 ; other devices have already been released by the ordinary monitor exit.
 PokeQ(#ZEN_IDLE_INTC+$F008,0)
 PokeQ(#ZEN_IDLE_INTC+$120,0) : PokeQ(#ZEN_IDLE_INTC+$220,0) : PokeQ(#ZEN_IDLE_INTC+$228,0)
 CallFunctionFast(zenKernelEnter,@zenKernelPlan[0],zenMemoryStackBottom)
 ZentajiPayloadRecoveryFailed($5B0C,"The one-way kernel handoff unexpectedly returned.")
EndProcedure
