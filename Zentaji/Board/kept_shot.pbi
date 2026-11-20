; One immutable captured native scanout. Allocate protected Vulkan heap memory
; only on an explicit capture. The ordinary console and payload share no frame
; storage with this allocation. Native DMA completes before the header publishes.
Global zkMemory.i,zkPixels.i,zkSequence.i,zkWidth.i,zkHeight.i,zkWho.i,zkResult.q
Procedure ZentajiKeptRelease()
 If zkMemory<>0
  vkUnmapMemory(znsDev,zkMemory) : vkFreeMemory(znsDev,zkMemory,0)
 EndIf
 zkMemory=0 : zkPixels=0 : zkSequence=0
EndProcedure
Procedure.i ZentajiKeptCopy(source.i,who.i,result.q)
 Protected bytes.i,pitch.i=zgdWidth*4,memory.i,mapped.i
 Protected alloc.VkMemoryAllocateInfo,rc.i
 If source=0 Or zgdWidth<1 Or zgdWidth>4096 Or zgdHeight<1 Or zgdHeight>4096 : ProcedureReturn 0 : EndIf
 If zgdPitch<pitch Or zgdWidth*zgdHeight>4194304 Or ShotSeq()>=$FFFFFFFF : ProcedureReturn 0 : EndIf
 bytes=pitch*zgdHeight
 ; Keep the old picture readable until the complete replacement is ready.
 alloc\sType=#VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO : alloc\allocationSize=bytes : alloc\memoryTypeIndex=0
 If vkAllocateMemory(znsDev,@alloc,0,@memory)<>#VK_SUCCESS : ProcedureReturn 0 : EndIf
 If vkMapMemory(znsDev,memory,0,bytes,0,@mapped)<>#VK_SUCCESS
  vkFreeMemory(znsDev,memory,0) : ProcedureReturn 0
 EndIf
 rc=ZentajiDmaRows(@avkZenDma,source,zgdPitch,mapped,pitch,pitch,zgdHeight,0,1000000)
 If rc<>1
  If avkZenDma\state<>1 Or avkZenDma\lost<>0
   ZentajiPayloadRecoveryFailed($5C02,"Frame capture failed (0x5C02): native DMA did not retire.")
  EndIf
  vkUnmapMemory(znsDev,memory) : vkFreeMemory(znsDev,memory,0)
  ProcedureReturn 0
 EndIf
 ZentajiKeptRelease() : zkMemory=memory : zkPixels=mapped
 zkWidth=zgdWidth : zkHeight=zgdHeight : zkWho=who : zkResult=result
 zkSequence=ShotNextSeq()
 ProcedureReturn 1
EndProcedure
Procedure ZentajiKeptBegin()
 zkPresented=0 : zkWatch=ShotTakeArm()
EndProcedure
Procedure.i ZentajiKeptReturn(entered.i,result.q)
 If zkWatch=0 : ProcedureReturn 1 : EndIf
 zkWatch=0
 If entered<>0 And zkPresented<>0 And zngSuspended=2 And zgdPending=0 And zgdEnabled<>0
  If ZentajiGraphicsDisplayOwned()<>0
   If ZentajiKeptCopy(zgdBase+zgdShown*zgdSpan,1,result)<>0 : ProcedureReturn 1 : EndIf
  EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i ScrShotValid()
 ProcedureReturn Bool(zkMemory<>0 And zkSequence<>0)
EndProcedure
Procedure.i ScrShotField(field.i)
 Select field
  Case #MON_SHOT_OFF_SEQ : ProcedureReturn zkSequence
  Case #MON_SHOT_OFF_W,#MON_SHOT_OFF_PANELW : ProcedureReturn zkWidth
  Case #MON_SHOT_OFF_H,#MON_SHOT_OFF_PANELH : ProcedureReturn zkHeight
  Case #MON_SHOT_OFF_PITCH : ProcedureReturn zkWidth*4
  Case #MON_SHOT_OFF_ROT : ProcedureReturn 0
  Case #MON_SHOT_OFF_TIER,#MON_SHOT_OFF_SRC : ProcedureReturn 3
  Case #MON_SHOT_OFF_X0 : ProcedureReturn zkResult
  Case #MON_SHOT_OFF_BPP : ProcedureReturn 4
  Case #MON_SHOT_OFF_WHO : ProcedureReturn zkWho
  Case #MON_SHOT_OFF_BYTES : ProcedureReturn zkWidth*zkHeight*4
 EndSelect
 ProcedureReturn 0
EndProcedure
Procedure.i ScrShotNow(who.i,result.q)
 Protected source.i=ZentajiScreenshotFront(),rc.i
 If source=0 : ProcedureReturn 0 : EndIf
 rc=ZentajiKeptCopy(source,who,result) : zngPainting=0 : ProcedureReturn rc
EndProcedure
Procedure ShotDump()
 Protected mirror.i
 If ScrShotValid()=0 : ShotSayNothing() : ProcedureReturn : EndIf
 mirror=UartMirrorOn() : UartMirror(0) : ShotPutHeader()
 AnvilScreenshotStream(zkPixels,zkWidth,zkHeight,zkWidth*4,0,zkWidth,zkHeight,4)
 If mirror<>0 : UartMirror(1) : EndIf
EndProcedure
Procedure ShotStatus()
 If ShotArmed()<>0 : PrintN("A capture on the next payload return is ARMED.") : Else : PrintN("A capture on the next payload return is not armed.") : EndIf
 If ScrShotValid()=0 : PrintN("The capture area holds no picture yet.") : ProcedureReturn : EndIf
 Print("The capture area holds picture number ") : PrintDec(zkSequence) : Print(", ") : PrintDec(zkWidth) : Print(" by ") : PrintDec(zkHeight) : PrintNl()
 Print("Native Vulkan scanout, return register r1 = $") : PutHex16(zkResult) : PrintNl()
 ShotPutHeader()
EndProcedure
Procedure ZentajiCmdShotR()
 Protected Dim meta.l[14]
 If ScrShotValid()=0 : ShotSayNothing() : ProcedureReturn : EndIf
 If NetConsoleOn()=0 Or NetConsolePeerOk()=0 : PrintN("!! sr needs an active UDP console peer.") : ProcedureReturn : EndIf
 meta[0]=#PICR_SHOT_MAGIC : meta[1]=#PICR_SHOT_VERSION : meta[2]=zkSequence
 meta[3]=zkWidth*4 : meta[4]=0 : meta[5]=3
 meta[6]=zkResult&$FFFFFFFF : meta[7]=(zkResult >> 32)&$FFFFFFFF
 meta[8]=zkWidth : meta[9]=zkHeight : meta[10]=4 : meta[11]=3
 meta[12]=zkWho : meta[13]=zkWidth*zkHeight*4
 AnvilScreenshotReliableSend(zkPixels,zkWidth,zkHeight,zkWidth*4,0,zkWidth,zkHeight,@meta[0])
EndProcedure
