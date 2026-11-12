; Owned native DMA channel7, coherent RAM, chained pitched copies and fills.
; Requires prompt_idle.pbi. Acquisition is serialized by the board; only the
; acquiring supervisor core with masked delivery may use this owner thereafter.
; Scratch and data remain pinned until retirement. A timeout never cancels DMA.
; This driver writes descriptors/registers, never destination data on the CPU.
#ZEN_DMA_BASE=$FFFF000000080000
#ZEN_DMA_CHANNEL=$FFFF000000080480
Structure ZentajiDmaTransfer
 owner.i : state.i : lost.i : error.i : ram.i : scratch.i : capacity.i
 source.i : destination.i : count.i : mode.i : status.i : launches.i : sleeps.i
 copyBase.i : copyBytes.i
EndStructure
Global zenDmaTransferOwner.i

Procedure.i ZentajiDmaFail(*q.ZentajiDmaTransfer,code.i)
 If *q\error=0 : *q\error=code : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiDmaContext(*q.ZentajiDmaTransfer)
 ProcedureReturn Bool(ZenCpuStatus()=0 And ZenCpuCoreId()=*q\owner)
EndProcedure
Procedure.i ZentajiDmaRange(*q.ZentajiDmaTransfer,base.i,bytes.i)
 If base<1 Or bytes<1 Or bytes>*q\ram Or base>*q\ram-bytes : ProcedureReturn 0 : EndIf
 If base<*q+SizeOf(ZentajiDmaTransfer) And *q<base+bytes : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(base>=*q\scratch+*q\capacity Or base+bytes<=*q\scratch)
EndProcedure
Procedure.i ZentajiDmaOwned(*q.ZentajiDmaTransfer)
 If *q\state=0 Or *q\lost<>0 Or zenDmaTransferOwner<>*q : ProcedureReturn 0 : EndIf
 If ZentajiDmaContext(*q)=0 : ProcedureReturn ZentajiDmaFail(*q,3) : EndIf
 If PeekQ(#ZEN_DMA_BASE)<>$10009 Or PeekQ(#ZEN_DMA_BASE+$40)<>8 Or (PeekQ(#ZEN_DMA_BASE+$10)&$80)<>0 Or (PeekQ(#ZEN_DMA_BASE+$18)&$80)<>0
  *q\lost=1 : ProcedureReturn ZentajiDmaFail(*q,4)
 EndIf
 If *q\state=1
  If PeekQ(#ZEN_DMA_CHANNEL)<>*q\source Or PeekQ(#ZEN_DMA_CHANNEL+8)<>*q\destination Or PeekQ(#ZEN_DMA_CHANNEL+$10)<>*q\count Or PeekQ(#ZEN_DMA_CHANNEL+$18)<>*q\mode Or PeekQ(#ZEN_DMA_CHANNEL+$20)<>0 Or PeekQ(#ZEN_DMA_CHANNEL+$30)<>0 Or PeekQ(#ZEN_DMA_CHANNEL+$38)<>0
   *q\lost=1 : ProcedureReturn ZentajiDmaFail(*q,4)
  EndIf
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiDmaBind(*q.ZentajiDmaTransfer,scratch.i,capacity.i)
 Protected ram.i=PeekQ($FFFF000000010018),n.i
 If *q<1 Or *q>ram-SizeOf(ZentajiDmaTransfer) : ProcedureReturn 0 : EndIf
 If *q\state<>0 Or zenDmaTransferOwner<>0 Or ZenCpuStatus()<>0 : ProcedureReturn ZentajiDmaFail(*q,2) : EndIf
 If scratch<1 Or (scratch&7)<>0 Or capacity<48 Or capacity>4096 Or scratch>ram-capacity : ProcedureReturn ZentajiDmaFail(*q,1) : EndIf
 If scratch<*q+SizeOf(ZentajiDmaTransfer) And *q<scratch+capacity : ProcedureReturn ZentajiDmaFail(*q,1) : EndIf
 If PeekQ(#ZEN_DMA_BASE)<>$10009 Or PeekQ(#ZEN_DMA_BASE+$40)<>8 Or ((PeekQ(#ZEN_DMA_BASE+$10)|PeekQ(#ZEN_DMA_BASE+$18))&$80)<>0 : ProcedureReturn ZentajiDmaFail(*q,4) : EndIf
 For n=0 To $20 Step 8
  If PeekQ(#ZEN_DMA_CHANNEL+n)<>0 : ProcedureReturn ZentajiDmaFail(*q,4) : EndIf
 Next
 If PeekQ(#ZEN_DMA_CHANNEL+$30)<>0 Or PeekQ(#ZEN_DMA_CHANNEL+$38)<>0 : ProcedureReturn ZentajiDmaFail(*q,4) : EndIf
 *q\owner=ZenCpuCoreId() : *q\ram=ram : *q\scratch=scratch : *q\capacity=capacity
 *q\source=0 : *q\destination=0 : *q\count=0 : *q\mode=0 : *q\error=0 : *q\copyBytes=0
 *q\state=1 : zenDmaTransferOwner=*q
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiDmaRowsValid(*q.ZentajiDmaTransfer,source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i,fill.i)
 Protected sourceSpan.i,destinationSpan.i,sourceRow.i,destinationRow.i,a.i,b.i
 If rowBytes<1 Or rows<1 Or destinationPitch<rowBytes Or destinationPitch>*q\ram Or rowBytes>*q\ram : ProcedureReturn 0 : EndIf
 If rows-1>(*q\ram-rowBytes)/destinationPitch : ProcedureReturn 0 : EndIf
 destinationSpan=(rows-1)*destinationPitch+rowBytes
 If ZentajiDmaRange(*q,destination,destinationSpan)=0 : ProcedureReturn 0 : EndIf
 If fill<>0
  ProcedureReturn Bool((rowBytes&3)=0 And (destination&3)=0 And (destinationPitch&3)=0)
 EndIf
 If sourcePitch<rowBytes Or sourcePitch>*q\ram Or rows-1>(*q\ram-rowBytes)/sourcePitch : ProcedureReturn 0 : EndIf
 sourceSpan=(rows-1)*sourcePitch+rowBytes
 If ZentajiDmaRange(*q,source,sourceSpan)=0 : ProcedureReturn 0 : EndIf
 If source>=destination+destinationSpan Or destination>=source+sourceSpan : ProcedureReturn 1 : EndIf
 ; Compare exact sorted row intervals, including cross-row hazards. Padding
 ; may share an allocation; bytes read by any row may never be overwritten.
 While sourceRow<rows And destinationRow<rows
  a=source+sourceRow*sourcePitch : b=destination+destinationRow*destinationPitch
  If a<b+rowBytes And b<a+rowBytes : ProcedureReturn 0 : EndIf
  If a+rowBytes<=b : sourceRow=sourceRow+1 : Else : destinationRow=destinationRow+1 : EndIf
 Wend
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiDmaStartRows(*q.ZentajiDmaTransfer,source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i,fill.i)
 Protected n.i,at.i,link.i,mode.i=0,alignment.i
 If *q\state<>1 Or ZentajiDmaOwned(*q)=0 : ProcedureReturn 0 : EndIf
 If rows>*q\capacity/48 Or ZentajiDmaRowsValid(*q,source,sourcePitch,destination,destinationPitch,rowBytes,rows,fill)=0 : ProcedureReturn ZentajiDmaFail(*q,1) : EndIf
 If HwPromptIdleReady()=0 : ProcedureReturn ZentajiDmaFail(*q,3) : EndIf
 If fill<>0
  mode=$201
 Else
  ; A wide element covers the same bytes within each native DMA burst.
  alignment=source|destination|rowBytes
  If rows>1 : alignment=alignment|sourcePitch|destinationPitch : EndIf
  If (alignment&7)=0
   mode=$300
  ElseIf (alignment&3)=0
   mode=$200
  ElseIf (alignment&1)=0
   mode=$100
  EndIf
 EndIf
 For n=0 To rows-1
  at=*q\scratch+n*48 : link=0
  If n+1<rows : link=at+48 : EndIf
  If fill<>0 : PokeQ(at,source&$FFFFFFFF) : Else : PokeQ(at,source+n*sourcePitch) : EndIf
  PokeQ(at+8,destination+n*destinationPitch) : PokeQ(at+16,rowBytes)
  PokeQ(at+24,mode) : PokeQ(at+32,link) : PokeQ(at+40,0)
 Next
 *q\source=source+(rows-1)*sourcePitch+rowBytes
 If fill<>0 : *q\source=source&$FFFFFFFF : EndIf
 *q\destination=destination+(rows-1)*destinationPitch+rowBytes : *q\count=rowBytes : *q\mode=mode
 PokeQ(#ZEN_DMA_CHANNEL,PeekQ(*q\scratch)) : PokeQ(#ZEN_DMA_CHANNEL+8,destination)
 PokeQ(#ZEN_DMA_CHANNEL+$10,rowBytes) : PokeQ(#ZEN_DMA_CHANNEL+$18,mode)
 PokeQ(#ZEN_DMA_CHANNEL+$20,PeekQ(*q\scratch+32))
 *q\copyBytes=0
 *q\state=3 : *q\error=0 : *q\launches=*q\launches+1
 PokeQ(#ZEN_DMA_CHANNEL+$28,1)
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiDmaPoll(*q.ZentajiDmaTransfer)
 If *q\state<>3 Or ZentajiDmaOwned(*q)=0 : ProcedureReturn -1 : EndIf
 *q\status=PeekQ(#ZEN_DMA_CHANNEL+$30)
 If (*q\status&1)<>0 : ProcedureReturn 0 : EndIf
 If *q\status<>2 Or PeekQ(#ZEN_DMA_CHANNEL+$38)<>0 Or PeekQ(#ZEN_DMA_CHANNEL)<>*q\source Or PeekQ(#ZEN_DMA_CHANNEL+8)<>*q\destination Or PeekQ(#ZEN_DMA_CHANNEL+$10)<>*q\count Or PeekQ(#ZEN_DMA_CHANNEL+$18)<>*q\mode Or PeekQ(#ZEN_DMA_CHANNEL+$20)<>0
  *q\lost=1 : ZentajiDmaFail(*q,5) : ProcedureReturn -1
 EndIf
 PokeQ(#ZEN_DMA_CHANNEL+$30,2) : *q\state=1
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiDmaWait(*q.ZentajiDmaTransfer,deadline.i)
 Protected rc.i,now.i
 Repeat
  rc=ZentajiDmaPoll(*q)
  If rc<>0 : ProcedureReturn rc : EndIf
  now=HwMicros()
  If now<0 Or now>=deadline Or HwPromptIdleReady()=0
   *q\lost=1 : ZentajiDmaFail(*q,7) : ProcedureReturn -1
  EndIf
  HwPromptIdleWait() : *q\sleeps=*q\sleeps+1
 ForEver
EndProcedure
Procedure.i ZentajiDmaRows(*q.ZentajiDmaTransfer,source.i,sourcePitch.i,destination.i,destinationPitch.i,rowBytes.i,rows.i,fill.i,timeoutUs.i)
 Protected done.i,batch.i,src.i,start.i=HwMicros(),deadline.i,now.i
 If timeoutUs<1 Or timeoutUs>1000000 Or start<0 Or start>$7FFFFFFFFFFFFFFF-timeoutUs : ProcedureReturn ZentajiDmaFail(*q,8) : EndIf
 If ZentajiDmaRowsValid(*q,source,sourcePitch,destination,destinationPitch,rowBytes,rows,fill)=0 : ProcedureReturn ZentajiDmaFail(*q,1) : EndIf
 ; Packed rows already passed full-span range and overlap checks.
 ; One descriptor avoids a timer wake and resubmission at every batch boundary.
 If rows>1 And destinationPitch=rowBytes And (fill<>0 Or sourcePitch=rowBytes)
  rowBytes=rowBytes*rows : rows=1
  sourcePitch=rowBytes : destinationPitch=rowBytes
 EndIf
 deadline=start+timeoutUs
 While done<rows
  now=HwMicros()
  If now<start Or now>=deadline
   If done<>0 : *q\lost=1 : EndIf
   ProcedureReturn ZentajiDmaFail(*q,7)
  EndIf
  batch=rows-done : If batch>*q\capacity/48 : batch=*q\capacity/48 : EndIf
  src=source : If fill=0 : src=source+done*sourcePitch : EndIf
  If ZentajiDmaStartRows(*q,src,sourcePitch,destination+done*destinationPitch,destinationPitch,rowBytes,batch,fill)=0 : ProcedureReturn 0 : EndIf
  If ZentajiDmaWait(*q,deadline)<>1 : ProcedureReturn 0 : EndIf
  done=done+batch
 Wend
 ; Record the contiguous destination only after the complete copy retires.
 ; The next native launch invalidates this proof, even if that launch fails.
 If fill=0 And destinationPitch=rowBytes
  *q\copyBase=destination : *q\copyBytes=rowBytes*rows
 EndIf
 ProcedureReturn 1
EndProcedure
