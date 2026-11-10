; Native pixel-display owner. Requires memory.pbi, graphics_queue.pbi and the
; prompt timer owner. Images are permanently pinned inside the boot arena;
; page zero remains private to commands/fences. No pixel copy or CPU renderer.
; The producer must retire its GPU queue before presenting an image. A pending
; scanout is not reusable until Poll/Wait confirms the actual display latch.
; Foreign configuration quarantines this owner; never reset it to fake recovery.
#ZEN_GFX_DISPLAY=$FFFF0000000C0000
Global zgdUp.i,zgdLost.i,zgdBase.i,zgdSpan.i,zgdPitch.i,zgdWidth.i,zgdHeight.i,zgdMode.i,zgdBuffers.i
Global zgdPending.i,zgdRequested.i,zgdShown.i,zgdEnabled.i,zgdSequence.q

Procedure.i ZentajiGraphicsDisplayOwned()
 Protected n.i,status.i
 If zgdUp=0 Or zgdLost<>0 : ProcedureReturn 0 : EndIf
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_GFX_DISPLAY+$10)<>zgdEnabled Or PeekQ(#ZEN_GFX_DISPLAY+$20)<>0 Or PeekQ(#ZEN_GFX_DISPLAY+$40)<>zgdMode Or PeekQ(#ZEN_GFX_DISPLAY+$50)<>zgdWidth Or PeekQ(#ZEN_GFX_DISPLAY+$58)<>zgdHeight Or PeekQ(#ZEN_GFX_DISPLAY+$68)<>0 Or PeekQ(#ZEN_GFX_DISPLAY+$70)<>zgdPitch Or PeekQ($FFFF0000001A0040)<>0
  zgdLost=1 : ProcedureReturn 0
 EndIf
 For n=0 To zgdBuffers-1
  If PeekQ(#ZEN_GFX_DISPLAY+$78+n*8)<>zgdBase+n*zgdSpan : zgdLost=1 : ProcedureReturn 0 : EndIf
 Next
 status=PeekQ(#ZEN_GFX_DISPLAY+8)
 If (status&$FF00)<>0 Or (zgdPending=0 And ((status&1)<>0 Or PeekQ(#ZEN_GFX_DISPLAY+$90)<>zgdShown))
  zgdLost=1 : ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsDisplayStart(base.i)
 Protected w.i,h.i,pitch.i,span.i,n.i,last.i,table.i=$FFFF000000010000,total.i,entries.i,p.i,buffers.i
 If zgdUp<>0 Or zgdLost<>0 Or zenMemoryGraphicsBase=0 Or ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_GFX_DISPLAY)<>$1000D Or PeekQ(#ZEN_GFX_DISPLAY+$10)<>0 Or PeekQ(#ZEN_GFX_DISPLAY+$20)<>0 Or PeekQ($FFFF0000001A0040)<>0 Or (PeekQ(#ZEN_GFX_DISPLAY+8)&$FF01)<>0 : ProcedureReturn 0 : EndIf
 ; Buffer count comes from the validated device descriptor, not a guessed
 ; triple-buffer profile. No display register is changed before admission.
 If PeekQ(table)<>$00494A41544E455A Or PeekU(table+8)<>1 Or PeekU(table+10)<>64 Or PeekL(table+20)<>64 : ProcedureReturn 0 : EndIf
 total=PeekL(table+12)&$FFFFFFFF : entries=PeekL(table+16)&$FFFFFFFF
 If total<64 Or total>65536 Or entries<1 Or entries>(total-64)/64 : ProcedureReturn 0 : EndIf
 For n=0 To entries-1
  p=table+64+n*64
  If PeekU(p)=13 And PeekA(p+2)=0 And PeekA(p+3)=1 And (PeekA(p+5)&1)<>0 And PeekQ(p+8)=#ZEN_GFX_DISPLAY And PeekQ(p+16)=65536
   buffers=PeekQ(p+56)
  EndIf
 Next
 If buffers<2 Or buffers>3 : ProcedureReturn 0 : EndIf
 w=PeekQ(#ZEN_GFX_DISPLAY+$50) : h=PeekQ(#ZEN_GFX_DISPLAY+$58)
 If w<1 Or w>16384 Or h<1 Or h>16384 : ProcedureReturn 0 : EndIf
 pitch=w*4 : span=(pitch*h+4095)&-4096
 last=zenMemoryGraphicsBase+zenMemoryGraphicsBytes
 If base<zenMemoryGraphicsBase+4096 Or (base&4095)<>0 Or base>last Or span>(last-base)/buffers : ProcedureReturn 0 : EndIf
 zgdBuffers=buffers
 zgdBase=base : zgdSpan=span : zgdPitch=pitch : zgdWidth=w : zgdHeight=h
 zgdMode=PeekQ(#ZEN_GFX_DISPLAY+$40) : zgdShown=PeekQ(#ZEN_GFX_DISPLAY+$90)
 zgdEnabled=0 : zgdPending=0 : zgdSequence=0
 PokeQ(#ZEN_GFX_DISPLAY+$68,0) : PokeQ(#ZEN_GFX_DISPLAY+$70,pitch)
 For n=0 To zgdBuffers-1 : PokeQ(#ZEN_GFX_DISPLAY+$78+n*8,base+n*span) : Next
 zgdUp=1
 ProcedureReturn ZentajiGraphicsDisplayOwned()
EndProcedure

Procedure.i ZentajiGraphicsDisplayPresent(*queue.ZentajiGraphicsQueue,index.i)
 If index<0 Or index>=zgdBuffers Or zgdPending<>0 Or ZentajiGraphicsDisplayOwned()=0 : ProcedureReturn 0 : EndIf
 If *queue=0 : ProcedureReturn 0 : EndIf
 If *queue\state<>1 Or *queue\error<>0 Or *queue\sequence<1 : ProcedureReturn 0 : EndIf
 If ZentajiGraphicsOwned(*queue)=0 Or PeekQ(*queue\fence)<>*queue\sequence : ProcedureReturn 0 : EndIf
 If zgdSequence=$7FFFFFFFFFFFFFFF : ProcedureReturn 0 : EndIf
 zgdRequested=index : zgdPending=1
 PokeQ(#ZEN_GFX_DISPLAY+$90,index)
 PokeQ(#ZEN_GFX_DISPLAY+$10,1) : zgdEnabled=1
 ProcedureReturn 1
EndProcedure

; 1 means the selected image has actually reached scanout, 0 still pending,
; -1 means ownership/error failure. A deadline never retires a pending image.
Procedure.i ZentajiGraphicsDisplayPoll()
 If ZentajiGraphicsDisplayOwned()=0 : ProcedureReturn -1 : EndIf
 If zgdPending=0 : ProcedureReturn 1 : EndIf
 If (PeekQ(#ZEN_GFX_DISPLAY+8)&1)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_GFX_DISPLAY+$90)<>zgdRequested : zgdLost=1 : ProcedureReturn -1 : EndIf
 zgdShown=zgdRequested : zgdPending=0 : zgdSequence=zgdSequence+1
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiGraphicsDisplayWait(microseconds.i)
 Protected start.q,now.q,result.i,n.i
 If microseconds<1 Or microseconds>250000 Or HwPromptIdleReady()=0 : ProcedureReturn 0 : EndIf
 start=HwMicros()
 If start<0 Or start>$7FFFFFFFFFFFFFFF-microseconds : ProcedureReturn 0 : EndIf
 For n=1 To 4096
  result=ZentajiGraphicsDisplayPoll()
  If result<>0 : ProcedureReturn Bool(result=1) : EndIf
  now=HwMicros()
  If now<start Or now-start>=microseconds Or HwPromptIdleReady()=0 : ProcedureReturn 0 : EndIf
  HwPromptIdleWait()
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiGraphicsDisplayRelease()
 Protected n.i
 If zgdPending<>0 Or ZentajiGraphicsDisplayOwned()=0 : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_GFX_DISPLAY+$10,0)
 For n=0 To zgdBuffers-1 : PokeQ(#ZEN_GFX_DISPLAY+$78+n*8,0) : Next
 PokeQ(#ZEN_GFX_DISPLAY+$70,0)
 zgdUp=0 : zgdEnabled=0
 ProcedureReturn 1
EndProcedure
