; SPDX-License-Identifier: MIT
; One bounded owner of the native keyboard/mouse queue. Host auto-repeat is
; already in KEY_EVENT; no synthetic repeat timer or USB keyboard layout here.
; The existing NUI wire is ASCII text/three mouse buttons, not a Unicode API.
XIncludeFile "Anvil/Core/input_hid_keys.pbi"
XIncludeFile "Anvil/Core/input_ui.pbi"
XIncludeFile "Anvil/Hal/input_service.pbi"
#ZEN_INPUT=$FFFF0000000A0000
#ZEN_INPUT_BURST=32
Global ziInstalled.i,ziUp.i,ziGeneration.i,ziFencing.i,ziMods.i,ziBlockedMods.i
Global Dim ziBlocked.a[256]
Global Dim ziNamed.a[256]
Global ziMouseBlocked.i,ziMouseButtons.i,ziMouseX.i,ziMouseY.i
Global ziOwned.i,ziEpoch.i,ziCaps.i,ziWidth.i,ziHeight.i,ziResize.i
Global ziPromptAdmitted.i

Procedure.i ZentajiInputHardwareOwned()
 If ziInstalled=0 : ProcedureReturn 1 : EndIf
 If (PeekQ(#ZEN_INPUT)&$FFFF)<>11 Or PeekQ(#ZEN_INPUT+$10)<>0 Or PeekQ(#ZEN_INPUT+$20)<>0 Or PeekQ(#ZEN_INPUT+$B0)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiInputFence()
 Protected n.i,usage.i,word.q,ignored.q
 If ziInstalled=0 : ProcedureReturn 1 : EndIf
 ziGeneration=InputFocusGeneration() : ziFencing=1
 ; Drain at most one full hardware queue per call. An adversarial producer
 ; that keeps refilling it leaves the fence closed, never an unbounded loop.
 For n=1 To 256
  If PeekQ(#ZEN_INPUT+$48)=0 : Break : EndIf
  ignored=PeekQ(#ZEN_INPUT+$40)
 Next
 If PeekQ(#ZEN_INPUT+$48)<>0 : ProcedureReturn 0 : EndIf
 For n=0 To 3
  word=PeekQ(#ZEN_INPUT+$50+n*8)
  For usage=0 To 63
   ziBlocked[n*64+usage]=Bool((word & (1<<usage))<>0) : ziNamed[n*64+usage]=0
  Next
 Next
 ziBlockedMods=0
 If ziBlocked[225]<>0 Or ziBlocked[229]<>0 : ziBlockedMods=ziBlockedMods | #AIM_SHIFT : EndIf
 If ziBlocked[224]<>0 Or ziBlocked[228]<>0 : ziBlockedMods=ziBlockedMods | #AIM_CTRL : EndIf
 If ziBlocked[226]<>0 Or ziBlocked[230]<>0 : ziBlockedMods=ziBlockedMods | #AIM_ALT : EndIf
 If ziBlocked[227]<>0 Or ziBlocked[231]<>0 : ziBlockedMods=ziBlockedMods | #AIM_GUI : EndIf
 ziMods=0
 ziMouseBlocked=PeekQ(#ZEN_INPUT+$90)&7 : ziMouseButtons=0
 ziMouseX=PeekQ(#ZEN_INPUT+$80) : ziMouseY=PeekQ(#ZEN_INPUT+$88)
 If ziOwned<>0 And (ziCaps & #NUI_MOUSE)<>0
  If ziMouseX<0 : ziMouseX=0 : ElseIf ziMouseX>=ziWidth : ziMouseX=ziWidth-1 : EndIf
  If ziMouseY<0 : ziMouseY=0 : ElseIf ziMouseY>=ziHeight : ziMouseY=ziHeight-1 : EndIf
 EndIf
 ignored=PeekQ(#ZEN_INPUT+$98) : ignored=PeekQ(#ZEN_INPUT+$A0) : ignored=PeekQ(#ZEN_INPUT+$A8)
 ; Acknowledge only keyboard/mouse reasons; gamepads/rumble are unclaimed.
 PokeQ(#ZEN_INPUT+8,1) : PokeQ(#ZEN_INPUT+$18,3)
 ziFencing=0
 ProcedureReturn 1
EndProcedure

Procedure ZiTyped(kind.i,code.i,mods.i)
 Protected rc.i
 Dim event.q[4]
 InputEventInit(@event[0],kind,#AIS_PHYSICAL,code,mods)
 rc=InputEventsPush(@event[0])
 If rc=#AIE_OK And ziOwned=0 And (kind=#AIE_TEXT Or kind=#AIE_KEY_DOWN) : ziPromptAdmitted=1 : EndIf
EndProcedure

Procedure ZentajiInputKeys()
 Protected n.i,usage.i,down.i,raw.i,mods.i,named.i,oldNamed.i,ch.i,repeated.i,event.q
 If ziUp=0 Or InputFocus()=#AIF_NONE : ProcedureReturn : EndIf
 If ziGeneration<>InputFocusGeneration() Or ziFencing<>0
  ZentajiInputFence() : ProcedureReturn
 EndIf
 If (PeekQ(#ZEN_INPUT+8)&1)<>0
  InputCancelAll(#AIC_QUEUE_FULL)
  ; NUI must deliver its cancellation before any new pointer state is read.
  ; Keep the old generation until its next poll takes the held-state baseline.
  If ziOwned=0 : ZentajiInputFence() : EndIf
  ProcedureReturn
 EndIf
 For n=1 To #ZEN_INPUT_BURST
  If ziGeneration<>InputFocusGeneration() Or PeekQ(#ZEN_INPUT+$48)=0 : Break : EndIf
  event=PeekQ(#ZEN_INPUT+$40)
  usage=event&255 : down=(event>>8)&1 : raw=(event>>16)&255
  repeated=(event>>24)&1 : ch=(event>>32)&$FFFFFFFF
  ziBlockedMods=ziBlockedMods & raw : mods=(raw&15)&(15-ziBlockedMods) : ziMods=mods
  If usage>0
   If ziBlocked[usage]<>0
    If down=0 : ziBlocked[usage]=0 : EndIf
   Else
    If ziOwned<>0 And (repeated=0 Or down=0)
     InputUiDevicePush(#NUI_PHYSICAL_KEY,#AIS_PHYSICAL,usage,mods,-1,-1,0,down,Ticks())
     If ziGeneration<>InputFocusGeneration() : Break : EndIf
    EndIf
    oldNamed=ziNamed[usage]
    If down=0
     named=oldNamed : ziNamed[usage]=0
    Else
     named=InputHidNamedKey(usage,(raw>>5)&1)
     ; Num Lock can change a held keypad key's meaning, even on a repeat.
     ; Close its old named state before admitting the new text/navigation.
     If oldNamed>0 And oldNamed<>named
      ZiTyped(#AIE_KEY_UP,oldNamed,mods)
      If ziGeneration<>InputFocusGeneration() : Break : EndIf
     EndIf
     ziNamed[usage]=named
    EndIf
    If named>0
     If down<>0 : ZiTyped(#AIE_KEY_DOWN,named,mods) : Else : ZiTyped(#AIE_KEY_UP,named,mods) : EndIf
    ElseIf down<>0
     If usage=6 And (mods & #AIM_CTRL)<>0 And (mods & (#AIM_ALT | #AIM_GUI))=0
      ZiTyped(#AIE_KEY_DOWN,#AIK_CANCEL_COMMAND,mods)
     ElseIf (mods & (#AIM_CTRL | #AIM_ALT | #AIM_GUI))=0 And ch>=32 And ch<=126
      ZiTyped(#AIE_TEXT,ch,mods)
     EndIf
    EndIf
   EndIf
  EndIf
 Next
 If PeekQ(#ZEN_INPUT+$48)=0 : PokeQ(#ZEN_INPUT+$18,1) : EndIf
EndProcedure

Procedure ZentajiInputMouse()
 Protected x.i,y.i,buttons.i,state.i,wheel.i,ignored.i
 If ziOwned=0 Or (ziCaps & #NUI_MOUSE)=0 Or ziGeneration<>InputFocusGeneration() Or ziFencing<>0 : ProcedureReturn : EndIf
 x=PeekQ(#ZEN_INPUT+$80) : y=PeekQ(#ZEN_INPUT+$88)
 If x<0 : x=0 : ElseIf x>=ziWidth : x=ziWidth-1 : EndIf
 If y<0 : y=0 : ElseIf y>=ziHeight : y=ziHeight-1 : EndIf
 buttons=PeekQ(#ZEN_INPUT+$90)&7
 ziMouseBlocked=ziMouseBlocked & buttons : buttons=buttons & (7-ziMouseBlocked)
 If x<>ziMouseX Or y<>ziMouseY Or buttons<>ziMouseButtons
  state=#NUI_HOVER
  If buttons<>0
   state=1 : If ziMouseButtons=0 : state=0 : EndIf
  ElseIf ziMouseButtons<>0
   state=2
  EndIf
  ziMouseX=x : ziMouseY=y : ziMouseButtons=buttons
  InputUiDevicePush(#NUI_POINTER,#NUI_SOURCE_MOUSE,0,ziMods,x,y,buttons,state,Ticks())
 EndIf
 If ziGeneration<>InputFocusGeneration() : ProcedureReturn : EndIf
 wheel=PeekQ(#ZEN_INPUT+$98)
 ignored=PeekQ(#ZEN_INPUT+$A0) : ignored=PeekQ(#ZEN_INPUT+$A8)
 If wheel<>0
  If wheel< -32768 : wheel=-32768 : EndIf
  If wheel>32767 : wheel=32767 : EndIf
  InputUiDevicePush(#NUI_WHEEL,#NUI_SOURCE_MOUSE,0,ziMods,x,y,buttons,wheel,Ticks())
 EndIf
 PokeQ(#ZEN_INPUT+$18,2)
EndProcedure

Procedure.i ZentajiInputRequest(request.i,bytes.i,want.i)
 If bytes<>want : ProcedureReturn 0 : EndIf
 If want=0 : ProcedureReturn Bool(request=0) : EndIf
 If request<=0 Or (request&7)<>0 Or request>$7FFFFFFFFFFFFFFF-want : ProcedureReturn 0 : EndIf
 ProcedureReturn InPayload(request,request+want-1)
EndProcedure

Procedure.i ZentajiInputReset()
 If ziOwned<>0 : InputUiEnd() : EndIf
 ziOwned=0 : ziCaps=0 : ziResize=0
 If ziInstalled<>0
  If ZentajiInputHardwareOwned()=0 : ProcedureReturn #NUI_ERR_PROVIDER : EndIf
  ZentajiInputFence()
 EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i ZentajiInputDispatch(op.i,context.i,request.i,bytes.i)
 Protected *api.NativeInputApi,*open.NativeInputOpenRequest,required.i,caps.i,rc.i,w.i,h.i
 If ziUp=0 Or ZentajiInputHardwareOwned()=0 : ProcedureReturn #NUI_ERR_PROVIDER : EndIf
 Select op
  Case #NUI_QUERY
   If ZentajiInputRequest(request,bytes,SizeOf(NativeInputApi))=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   *api=request : *api\magic=#NUI_MAGIC : *api\major=#NUI_MAJOR : *api\minor=#NUI_MINOR
   *api\bytes=SizeOf(NativeInputApi) : *api\flags=#NUI_KEYBOARD | #NUI_MOUSE : *api\dispatch=@InputServiceCall
   ProcedureReturn 0
  Case #NUI_OPEN
   If ZentajiInputRequest(request,bytes,SizeOf(NativeInputOpenRequest))=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   If ziOwned<>0 : ProcedureReturn #NUI_ERR_BUSY : EndIf
   *open=request : required=*open\required
   If required<0 Or required>7 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   If ziEpoch>=2147483647 : ProcedureReturn #NUI_ERR_STATE : EndIf
   caps=#NUI_KEYBOARD : w=PeekQ(#ZEN_DISPLAY+$50) : h=PeekQ(#ZEN_DISPLAY+$58)
   If (PeekQ(#ZEN_DISPLAY)&$FFFF)=13 And w>0 And w<=65535 And h>0 And h<=65535 : caps=caps | #NUI_MOUSE : Else : w=0 : h=0 : EndIf
   If (caps & required)<>required : ProcedureReturn #NUI_ERR_CAPABILITY : EndIf
   rc=InputUiBegin() : If rc<>0 : ProcedureReturn rc : EndIf
   ziOwned=1 : ziCaps=caps : ziEpoch=ziEpoch+1 : ziResize=0 : ziWidth=w : ziHeight=h
   ZentajiInputFence()
   *open\capabilities=caps : *open\width=w : *open\height=h : *open\generation=ziGeneration
   ProcedureReturn ziEpoch
  Case #NUI_POLL
   If ZentajiInputRequest(request,bytes,SizeOf(NativeInputEvent))=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   If ziOwned=0 Or context<>ziEpoch : ProcedureReturn #NUI_ERR_STATE : EndIf
   If ziResize=0 And (PeekQ(#ZEN_DISPLAY+$50)<>ziWidth Or PeekQ(#ZEN_DISPLAY+$58)<>ziHeight)
    ziResize=1 : InputUiFlush(#AIC_SCREEN_CHANGE)
   EndIf
   rc=InputUiPop(request)
   If rc=1 And PeekL(request)=#AIE_CANCEL And InputUiActive()<>0 : ZentajiInputFence() : EndIf
   If rc<>0 : ProcedureReturn rc : EndIf
   If ziResize<>0 : ProcedureReturn #NUI_ERR_STATE : EndIf
   ZentajiInputKeys()
   If ziGeneration=InputFocusGeneration() : ZentajiInputMouse() : EndIf
   ProcedureReturn InputUiPop(request)
  Case #NUI_FLUSH
   If ZentajiInputRequest(request,bytes,0)=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   If ziOwned=0 Or context<>ziEpoch : ProcedureReturn #NUI_ERR_STATE : EndIf
   ProcedureReturn InputUiFlush(#AIC_PAYLOAD)
  Case #NUI_CLOSE
   If ZentajiInputRequest(request,bytes,0)=0 : ProcedureReturn #NUI_ERR_ARGS : EndIf
   If ziOwned=0 Or context<>ziEpoch : ProcedureReturn #NUI_ERR_STATE : EndIf
   ProcedureReturn ZentajiInputReset()
 EndSelect
 ProcedureReturn #NUI_ERR_ARGS
EndProcedure

Procedure.i ZentajiPromptInputs(operation.i)
 CompilerIf Defined(ANVIL_ZENTAJI_NET, #PB_Constant)
 If operation=#APS_NET_INPUT : ProcedureReturn NetConsoleGetc() : EndIf
 If operation=#APS_CLAIM_LOCAL : NetConsoleClaimLocal() : ProcedureReturn 0 : EndIf
 CompilerEndIf
 If operation=#APS_NET_INPUT : ProcedureReturn -1 : EndIf
 If operation=#APS_KEYBOARD And ziOwned=0 And ziUp<>0 And InputFocus()=#AIF_COMMAND_LINE
  ziPromptAdmitted=0
  ZentajiInputKeys()
  If ziPromptAdmitted<>0 : ProcedureReturn #APS_INPUT_QUEUED : EndIf
 EndIf
 ; Keys were pushed as normalized events. Returning a byte would duplicate it.
 ProcedureReturn 0
EndProcedure

Procedure ZentajiInputPromptResume()
 If ziInstalled=0 : ProcedureReturn : EndIf
 If InputFocus()<>#AIF_COMMAND_LINE : InputFocusSet(#AIF_COMMAND_LINE) : EndIf
 If ziGeneration<>InputFocusGeneration() Or ziFencing<>0 : ZentajiInputFence() : EndIf
EndProcedure

Procedure.i ZentajiInputStart()
 If ziInstalled<>0 Or AnvilPromptInputsPresent()<>0 Or InputServiceAvailable()<>0 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_INPUT)&$FFFF)<>11 Or PeekQ(#ZEN_INPUT+$10)<>0 Or PeekQ(#ZEN_INPUT+$20)<>0 Or PeekQ(#ZEN_INPUT+$B0)<>0 : ProcedureReturn 0 : EndIf
 ziInstalled=1 : ziUp=1
 If InputServiceBind(@ZentajiInputDispatch,@ZentajiInputReset)<>0 : ziInstalled=0 : ziUp=0 : ProcedureReturn 0 : EndIf
 If AnvilPromptInputsBind(@ZentajiPromptInputs)<>1 : ProcedureReturn 0 : EndIf
 ZentajiInputPromptResume()
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiInputPayload(enter.i,services.i)
 If ziInstalled=0 : ProcedureReturn 1 : EndIf
 If ZentajiInputHardwareOwned()=0 : ProcedureReturn 0 : EndIf
 If enter=0 And services<>0
  If InputServiceLeave()<>0 : ProcedureReturn 0 : EndIf
 EndIf
 InputFocusSet(#AIF_NONE) : InputPayloadSuspend() : ZentajiInputFence()
 ziUp=1
 If enter<>0 And services=0 : ziUp=0 : EndIf
 ProcedureReturn 1
EndProcedure
