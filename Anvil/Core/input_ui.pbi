; SPDX-License-Identifier: MIT
; One payload focus owner over existing normalized typed events plus a bounded
; device lane (pointer/wheel/raw key). Hardware producers call Push; they never own a second
; typed-event drain. Include input_events.pbi first.
XIncludeFile "Anvil/Hal/input_service_api.pbi"
#NUI_QUEUE=64
Global Dim nuiPointerQueue.q[384]
Global nuiHead.i,nuiTail.i,nuiCount.i,nuiActive.i,nuiGeneration.i,nuiPreferPointer.i
Global nuiDiscarded.i,nuiOverflows.i
Procedure.i InputUiActive()
  ProcedureReturn nuiActive
EndProcedure
Procedure.i InputUiDiscarded()
  ProcedureReturn nuiDiscarded
EndProcedure
Procedure.i InputUiOverflowCount()
  ProcedureReturn nuiOverflows
EndProcedure
Procedure.i InputUiBegin()
  If nuiActive<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
  If InputFocusGeneration()>=2147483646 : ProcedureReturn #NUI_ERR_STATE : EndIf
  InputFocusSet(#AIF_PAYLOAD)
  nuiGeneration=InputFocusGeneration()
  nuiHead=0 : nuiTail=0 : nuiCount=0 : nuiPreferPointer=0 : nuiActive=1
  ProcedureReturn 0
EndProcedure
Procedure.i InputUiEnd()
  If nuiActive=0 : ProcedureReturn 0 : EndIf
  nuiDiscarded=nuiDiscarded+nuiCount : nuiHead=0 : nuiTail=0 : nuiCount=0 : nuiActive=0
  If InputFocus()=#AIF_PAYLOAD : InputFocusSet(#AIF_NONE) : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i InputUiFlush(reason.i)
  If nuiActive=0 Or InputFocus()<>#AIF_PAYLOAD : ProcedureReturn #NUI_ERR_STATE : EndIf
  If reason<0 Or reason>#AIC_MAX : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If InputFocusGeneration()>=2147483646 : ProcedureReturn #NUI_ERR_STATE : EndIf
  InputCancelAll(reason)
  ProcedureReturn 0
EndProcedure
Procedure nuiEventFill(*e.NativeInputEvent,kind.i,source.i,code.i,mods.i,x.i,y.i,buttons.i,value.i,ticks.i)
  *e\kind=kind : *e\source=source : *e\code=code : *e\modifiers=mods
  *e\x=x : *e\y=y : *e\buttons=buttons : *e\value=value
  *e\ticks=ticks : *e\generation=InputFocusGeneration() : *e\reserved=0
EndProcedure
Procedure nuiPointerReconcile()
  If nuiGeneration<>InputFocusGeneration()
    nuiDiscarded=nuiDiscarded+nuiCount : nuiHead=0 : nuiTail=0 : nuiCount=0
    ; Keep the old generation until Pop emits its single cancellation.
  EndIf
EndProcedure
Procedure.i InputUiDevicePush(kind.i,source.i,code.i,mods.i,x.i,y.i,buttons.i,value.i,ticks.i)
  Protected e.NativeInputEvent,i.i,dest.i
  If nuiActive=0 Or InputFocus()<>#AIF_PAYLOAD : ProcedureReturn #NUI_ERR_STATE : EndIf
  ; A cancellation must be delivered before admitting new contact state.
  If nuiGeneration<>InputFocusGeneration() Or InputFocusGeneration()>=2147483646 : ProcedureReturn #NUI_ERR_STATE : EndIf
  If kind<>#NUI_POINTER And kind<>#NUI_WHEEL And kind<>#NUI_PHYSICAL_KEY : ProcedureReturn #NUI_ERR_ARGS : EndIf
  ; Check the full-width producer arguments before narrowing the wire fields.
  If source<>#NUI_SOURCE_MOUSE And source<>#NUI_SOURCE_TOUCH And (kind<>#NUI_PHYSICAL_KEY Or source<>#AIS_PHYSICAL) : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If code< -1 Or code>65535 Or mods<0 Or mods>15 Or x< -1 Or y< -1 Or x>1000000 Or y>1000000 Or buttons<0 Or buttons>7 Or value< -32768 Or value>32767 Or ticks<0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
  nuiEventFill(@e,kind,source,code,mods,x,y,buttons,value,ticks)
  If NativeInputEventValid(@e)=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
  nuiPointerReconcile()
  If nuiCount>=#NUI_QUEUE
    nuiOverflows=nuiOverflows+1 : InputUiFlush(#AIC_QUEUE_FULL)
    nuiPointerReconcile()
    ProcedureReturn #NUI_ERR_FULL
  EndIf
  dest=@nuiPointerQueue[0]+nuiHead*SizeOf(NativeInputEvent)
  For i=0 To SizeOf(NativeInputEvent)-8 Step 8 : PokeI(dest+i,PeekI(@e+i)) : Next
  nuiHead=(nuiHead+1)%#NUI_QUEUE : nuiCount=nuiCount+1
  ProcedureReturn 0
EndProcedure
Procedure.i InputUiPop(dest.i)
  Protected key.i,i.i,*e.NativeInputEvent,source.i,n.i
  Dim typed.q[4]
  If dest<=0 Or (dest & 7)<>0 Or dest+SizeOf(NativeInputEvent)<=dest : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If dest<@nuiPointerQueue[0]+3072 And dest+SizeOf(NativeInputEvent)>@nuiPointerQueue[0] : ProcedureReturn #NUI_ERR_ARGS : EndIf
  If nuiActive=0 : ProcedureReturn #NUI_ERR_STATE : EndIf
  *e=dest
  If InputFocusGeneration()<1 Or InputFocusGeneration()>2147483647 : ProcedureReturn #NUI_ERR_STATE : EndIf
  If nuiGeneration<>InputFocusGeneration() Or InputFocus()<>#AIF_PAYLOAD
    nuiPointerReconcile() : nuiGeneration=InputFocusGeneration()
    nuiEventFill(*e,#AIE_CANCEL,#AIS_PHYSICAL,InputCancelReason(),0,-1,-1,0,0,Ticks())
    If InputFocus()<>#AIF_PAYLOAD : nuiActive=0 : EndIf
    ProcedureReturn 1
  EndIf
  ; Alternate ready lanes. A held/repeating key cannot starve pointer releases.
  If nuiPreferPointer=0 Or nuiCount=0
    For n=1 To #AIE_QMAX
      key=InputEventsPop(@typed[0])
      If key=0 : Break : EndIf
      If PeekL(@typed[0]+#AIE_EV_KIND)<>#AIE_CANCEL
        nuiEventFill(*e,PeekL(@typed[0]+#AIE_EV_KIND),PeekL(@typed[0]+#AIE_EV_SRC),PeekL(@typed[0]+#AIE_EV_CODE),PeekL(@typed[0]+#AIE_EV_MODS),-1,-1,0,0,PeekI(@typed[0]+#AIE_EV_TIME))
        nuiPreferPointer=1 : ProcedureReturn 1
      EndIf
    Next
  EndIf
  If nuiCount>0
    source=@nuiPointerQueue[0]+nuiTail*SizeOf(NativeInputEvent)
    For i=0 To SizeOf(NativeInputEvent)-8 Step 8 : PokeI(dest+i,PeekI(source+i)) : Next
    nuiTail=(nuiTail+1)%#NUI_QUEUE : nuiCount=nuiCount-1 : nuiPreferPointer=0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure
