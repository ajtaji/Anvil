; Serialized native 3D/blitter command transport, not a pixel renderer.
; Requires prompt_idle.pbi, included explicitly before this file by the owner.
; Context, private list/fence and all resources named by commands must remain
; protected and pinned until retirement or a confirmed abort. A deadline is
; not completion. Foreign configuration permanently quarantines this lease.
; The board serializes acquisition across cores. Thereafter only the owning
; supervisor core with masked delivery may use this driver.
; The future Vulkan backend validates command resource extents and lifetimes;
; this internal transport is never an application-facing raw-command service.
#ZEN_GFX_BLIT=$FFFF0000000D0000
#ZEN_GFX_3D=$FFFF0000000E0000
#ZEN_GFX_E_ARGUMENT=1
#ZEN_GFX_E_STATE=2
#ZEN_GFX_E_CONTEXT=3
#ZEN_GFX_E_FOREIGN=4
#ZEN_GFX_E_DEVICE=5
#ZEN_GFX_E_FENCE=6
#ZEN_GFX_E_TIMEOUT=7
#ZEN_GFX_E_CLOCK=8

Structure ZentajiGraphicsQueue
 base.i : kind.i : owner.i : state.i : lost.i : error.i
 ram.i : list.i : capacity.i : fence.i : count.i : submittedBytes.i
 sequence.q : deviceStatus.q : faultPc.q : faultInfo.q
EndStructure
Global zenGraphicsBlitOwner.i,zenGraphics3dOwner.i

Procedure.i ZentajiGraphicsFail(*q.ZentajiGraphicsQueue,code.i)
 If *q\lost=0 Or *q\error=0 : *q\error=code : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiGraphicsContext(*q.ZentajiGraphicsQueue)
 ProcedureReturn Bool(ZenCpuStatus()=0 And ZenCpuCoreId()=*q\owner)
EndProcedure

Procedure.i ZentajiGraphicsPresent(kind.i)
 Protected table.i=$FFFF000000010000,total.i,entries.i,n.i,p.i,base.i
 If kind<>14 And kind<>15 : ProcedureReturn 0 : EndIf
 base=#ZEN_GFX_BLIT : If kind=15 : base=#ZEN_GFX_3D : EndIf
 If PeekQ(table)<>$00494A41544E455A Or PeekU(table+8)<>1 Or PeekU(table+10)<>64 Or PeekL(table+20)<>64 : ProcedureReturn 0 : EndIf
 total=PeekL(table+12)&$FFFFFFFF : entries=PeekL(table+16)&$FFFFFFFF
 If total<64 Or total>65536 Or entries<1 Or entries>(total-64)/64 : ProcedureReturn 0 : EndIf
 For n=0 To entries-1
  p=table+64+n*64
  If PeekU(p)=kind And PeekA(p+2)=0 And PeekA(p+3)=1 And (PeekA(p+5)&1)<>0
   If PeekQ(p+8)=base And PeekQ(p+16)=65536 And PeekQ(base)=kind+$10000 : ProcedureReturn 1 : EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiGraphicsOwned(*q.ZentajiGraphicsQueue)
 Protected lease.i,status.q
 If *q\state=0 Or *q\lost<>0 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsContext(*q)=0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CONTEXT) : EndIf
 lease=zenGraphicsBlitOwner : If *q\kind=15 : lease=zenGraphics3dOwner : EndIf
 If lease<>*q : ProcedureReturn 0 : EndIf
 If PeekQ(*q\base)<>*q\kind+$10000 Or PeekQ(*q\base+$10)<>0 Or PeekQ(*q\base+$20)<>0 Or PeekQ(*q\base+$40)<>*q\list Or PeekQ(*q\base+$48)<>*q\submittedBytes
  *q\lost=1 : *q\error=#ZEN_GFX_E_FOREIGN : ProcedureReturn 0
 EndIf
 status=PeekQ(*q\base+8)
 If *q\state<>3 And ((status&$FFFFFFF7)<>0 Or PeekQ(*q\base+$18)<>0)
  *q\lost=1 : *q\error=#ZEN_GFX_E_FOREIGN : ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsBind(*q.ZentajiGraphicsQueue,kind.i,privateBase.i,privateBytes.i,list.i,capacity.i,fence.i)
 Protected ram.i=PeekQ($FFFF000000010018),base.i,last.i,lease.i
 If *q\state<>0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZenCpuStatus()<>0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CONTEXT) : EndIf
 If kind<>14 And kind<>15 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 lease=zenGraphicsBlitOwner : base=#ZEN_GFX_BLIT
 If kind=15 : lease=zenGraphics3dOwner : base=#ZEN_GFX_3D : EndIf
 If lease<>0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If privateBase<1 Or privateBytes<200 Or privateBase>ram Or privateBytes>ram-privateBase : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If *q<1 Or *q>ram-SizeOf(ZentajiGraphicsQueue) : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 last=privateBase+privateBytes
 If list<privateBase Or list>last Or capacity<192 Or capacity>$100000000 Or (list&7)<>0 Or (capacity&63)<>0 Or capacity>last-list : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If fence<privateBase Or fence>last-8 Or (fence&7)<>0 Or (fence<list+capacity And fence+8>list) : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If (list<*q+SizeOf(ZentajiGraphicsQueue) And list+capacity>*q) Or (fence<*q+SizeOf(ZentajiGraphicsQueue) And fence+8>*q) : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If ZentajiGraphicsPresent(kind)=0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 ; A fresh boot or separately quiesced predecessor is required. Do not reset
 ; a controller merely because its interrupts or enable bit are clear.
 If (PeekQ(base+8)&$FFFFFFF7)<>0 Or PeekQ(base+$10)<>0 Or PeekQ(base+$18)<>0 Or PeekQ(base+$20)<>0 Or PeekQ(base+$40)<>0 Or PeekQ(base+$48)<>0
  ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_FOREIGN)
 EndIf
 *q\base=base : *q\kind=kind : *q\owner=ZenCpuCoreId() : *q\ram=ram
 *q\list=list : *q\capacity=capacity : *q\fence=fence
 *q\count=0 : *q\submittedBytes=0 : *q\sequence=0 : *q\lost=0
 *q\deviceStatus=0 : *q\faultPc=0 : *q\faultInfo=0 : *q\error=0
 PokeQ(base+$40,list)
 *q\state=1
 If kind=14 : zenGraphicsBlitOwner=*q : Else : zenGraphics3dOwner=*q : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsBegin(*q.ZentajiGraphicsQueue)
 If *q\state<>1 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn 0 : EndIf
 *q\count=0 : *q\error=0 : *q\state=2
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsAppend(*q.ZentajiGraphicsQueue,command.i)
 Protected n.i,op.i,to.i
 If *q\state<>2 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn 0 : EndIf
 If command<1 Or command>*q\ram-64 Or *q\count>=*q\capacity/64-2 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 op=PeekA(command)
 ; Only the transport emits END and its final FENCE. All ordinary commands
 ; are copied before launch, so a caller's staging record can be reused.
 If op<1 Or op>8+Bool(*q\kind=15) : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If command<*q\list+*q\capacity And command+64>*q\list : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 to=*q\list+*q\count*64
 For n=0 To 56 Step 8 : PokeQ(to+n,PeekQ(command+n)) : Next
 *q\count=*q\count+1
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsSubmit(*q.ZentajiGraphicsQueue)
 Protected at.i,n.i
 If *q\state<>2 Or *q\count<1 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn 0 : EndIf
 If *q\sequence=$7FFFFFFFFFFFFFFF : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 at=*q\list+*q\count*64
 For n=0 To 120 Step 8 : PokeQ(at+n,0) : Next
 *q\sequence=*q\sequence+1
 PokeA(at,9+Bool(*q\kind=15)) : PokeQ(at+8,*q\fence) : PokeQ(at+16,*q\sequence)
 PokeQ(*q\fence,0)
 *q\submittedBytes=(*q\count+2)*64 : *q\state=3 : *q\error=0
 PokeQ(*q\base+$48,*q\submittedBytes)
 PokeQ(*q\base+$50,1)
 ProcedureReturn 1
EndProcedure

; 1 successful retirement, 0 still pending, -1 failed. Inspect state/lost:
; only state=1 proves the transport's private DMA storage may be reused.
Procedure.i ZentajiGraphicsPoll(*q.ZentajiGraphicsQueue)
 Protected status.q,ok.i
 If *q\state<>3 : *q\error=#ZEN_GFX_E_STATE : ProcedureReturn -1 : EndIf
 If ZentajiGraphicsContext(*q)=0 : *q\error=#ZEN_GFX_E_CONTEXT : ProcedureReturn -1 : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn -1 : EndIf
 status=PeekQ(*q\base+8)
 If (status&1)<>0 : ProcedureReturn 0 : EndIf
 *q\deviceStatus=status
 If *q\kind=15 : *q\faultPc=PeekQ(*q\base+$60) : *q\faultInfo=PeekQ(*q\base+$68) : EndIf
 If (status&6)=0 Or ((status&4)=0 And PeekQ(*q\fence)<>*q\sequence)
  *q\lost=1 : *q\error=#ZEN_GFX_E_FENCE : ProcedureReturn -1
 EndIf
 ok=Bool((status&4)=0)
 ; Idle plus the expected completion/error retires this lease's command list.
 ; A controller error does not roll back already completed earlier commands.
 PokeQ(*q\base+$18,7) : PokeQ(*q\base+8,6)
 *q\state=1 : *q\error=0
 If ok=0 : *q\error=#ZEN_GFX_E_DEVICE : ProcedureReturn -1 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsWait(*q.ZentajiGraphicsQueue,microseconds.i)
 Protected start.q,now.q,result.i,n.i
 If *q\state<>3 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If microseconds<1 Or microseconds>250000 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_ARGUMENT) : EndIf
 If ZentajiGraphicsContext(*q)=0 Or HwPromptIdleReady()=0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CONTEXT) : EndIf
 start=HwMicros()
 If start<0 Or start>$7FFFFFFFFFFFFFFF-microseconds : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CLOCK) : EndIf
 For n=1 To 4096
  result=ZentajiGraphicsPoll(*q)
  If result<>0 : ProcedureReturn Bool(result=1) : EndIf
  now=HwMicros()
  If now<start : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CLOCK) : EndIf
  If now-start>=microseconds : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_TIMEOUT) : EndIf
  If HwPromptIdleReady()=0 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_CONTEXT) : EndIf
  HwPromptIdleWait()
 Next
 ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_TIMEOUT)
EndProcedure

Procedure.i ZentajiGraphicsAbort(*q.ZentajiGraphicsQueue)
 Protected result.i
 If *q\state<>3 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn 0 : EndIf
 PokeQ(*q\base+$50,2)
 result=ZentajiGraphicsPoll(*q)
 ProcedureReturn Bool(*q\state=1 And *q\lost=0)
EndProcedure

Procedure.i ZentajiGraphicsRelease(*q.ZentajiGraphicsQueue)
 If *q\state<>1 And *q\state<>2 : ProcedureReturn ZentajiGraphicsFail(*q,#ZEN_GFX_E_STATE) : EndIf
 If ZentajiGraphicsOwned(*q)=0 : ProcedureReturn 0 : EndIf
 PokeQ(*q\base+$48,0) : PokeQ(*q\base+$40,0)
 If *q\kind=14 : zenGraphicsBlitOwner=0 : Else : zenGraphics3dOwner=0 : EndIf
 *q\state=0 : *q\error=0
 ProcedureReturn 1
EndProcedure
