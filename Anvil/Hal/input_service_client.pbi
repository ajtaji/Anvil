; SPDX-License-Identifier: MIT
; Pure payload client. The kernel owns all devices and focus.
XIncludeFile "Anvil/Hal/input_service_api.pbi"
Procedure.i nicUnbound(op.i,context.i,request.i,bytes.i)
  ProcedureReturn #NUI_ERR_UNBOUND
EndProcedure
Global nicDispatch.i=@nicUnbound,nicContext.i,nicRequired.i,nicSupported.i
Global nicCaps.i,nicWidth.i,nicHeight.i,nicGeneration.i,nicBusy.i,nicStatus.i
Procedure.i AnvilInputError()
  ProcedureReturn nicStatus
EndProcedure
Procedure.i AnvilInputContext()
  ProcedureReturn nicContext
EndProcedure
Procedure.i AnvilInputCapabilities()
  ProcedureReturn nicCaps
EndProcedure
Procedure.i AnvilInputWidth()
  ProcedureReturn nicWidth
EndProcedure
Procedure.i AnvilInputHeight()
  ProcedureReturn nicHeight
EndProcedure
Procedure.i AnvilInputGeneration()
  ProcedureReturn nicGeneration
EndProcedure
Procedure.i nicResult(rc.i)
  nicStatus=rc : ProcedureReturn rc
EndProcedure
Procedure.i AnvilInputBind(services.i,required.i)
  Protected dispatch.i=@nicUnbound,rc.i,i.i,api.NativeInputApi
  If nicBusy<>0 Or nicContext<>0 : ProcedureReturn nicResult(#NUI_ERR_BUSY) : EndIf
  If required<0 Or required>7 Or services<=0 Or (services & 7)<>0 Or services+336<=services : ProcedureReturn nicResult(#NUI_ERR_ARGS) : EndIf
  If (PeekL(services) & $FFFFFFFF)<>$53564E41 Or PeekL(services+4)<>1 Or PeekL(services+8)<#NUI_SERVICE_ABI_MINOR Or (PeekL(services+12) & $FFFFFFFF)<40 : ProcedureReturn nicResult(#NUI_ERR_ABI) : EndIf
  dispatch=PeekI(services+16+#NUI_SERVICE_SLOT*8)
  If dispatch<=0 : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  For i=0 To SizeOf(NativeInputApi)-8 Step 8 : PokeI(@api+i,0) : Next
  nicBusy=1 : rc=dispatch(#NUI_QUERY,0,@api,SizeOf(NativeInputApi)) : nicBusy=0
  If rc<>0
    If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
    ProcedureReturn nicResult(rc)
  EndIf
  If api\magic<>#NUI_MAGIC Or api\major<>#NUI_MAJOR Or api\minor<0 Or api\bytes<>SizeOf(NativeInputApi) Or api\flags<0 Or api\flags>7 Or api\dispatch<=0 : ProcedureReturn nicResult(#NUI_ERR_ABI) : EndIf
  If (api\flags & required)<>required : ProcedureReturn nicResult(#NUI_ERR_CAPABILITY) : EndIf
  nicDispatch=api\dispatch : nicSupported=api\flags : nicRequired=required
  ProcedureReturn nicResult(0)
EndProcedure
Procedure.i AnvilInputOpen()
  Protected request.NativeInputOpenRequest,rc.i
  If nicBusy<>0 Or nicContext<>0 : ProcedureReturn nicResult(#NUI_ERR_BUSY) : EndIf
  request\required=nicRequired : request\capabilities=0 : request\width=0 : request\height=0 : request\generation=0
  nicBusy=1 : rc=nicDispatch(#NUI_OPEN,0,@request,SizeOf(NativeInputOpenRequest)) : nicBusy=0
  If rc<=0
    If rc=0 : rc=#NUI_ERR_PROVIDER : EndIf
    ProcedureReturn nicResult(rc)
  EndIf
  ; Positive context is ownership even if the returned descriptor is malformed.
  ; Retain it so checked Close (or kernel scope retirement) can release it.
  nicContext=rc
  If request\required<>nicRequired Or request\capabilities<1 Or request\capabilities>7 Or (request\capabilities & nicRequired)<>nicRequired Or (request\capabilities & nicSupported)<>request\capabilities Or request\generation<1 Or request\generation>2147483647
    ProcedureReturn nicResult(#NUI_ERR_PROVIDER)
  EndIf
  If request\width<0 Or request\height<0 Or request\width>8192 Or request\height>8192 : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  If (request\width=0 And request\height<>0) Or (request\height=0 And request\width<>0) : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  If (request\capabilities & 6)<>0 And (request\width=0 Or request\height=0) : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  nicCaps=request\capabilities : nicWidth=request\width : nicHeight=request\height : nicGeneration=request\generation
  ProcedureReturn nicResult(0)
EndProcedure
Procedure.i AnvilInputPoll(event.i)
  Protected candidate.NativeInputEvent,rc.i,i.i
  If nicBusy<>0 : ProcedureReturn nicResult(#NUI_ERR_BUSY) : EndIf
  If nicContext=0 : ProcedureReturn nicResult(#NUI_ERR_STATE) : EndIf
  If event<=0 Or (event & 7)<>0 Or event+SizeOf(NativeInputEvent)<=event : ProcedureReturn nicResult(#NUI_ERR_ARGS) : EndIf
  For i=0 To SizeOf(NativeInputEvent)-8 Step 8 : PokeI(@candidate+i,0) : Next
  nicBusy=1 : rc=nicDispatch(#NUI_POLL,nicContext,@candidate,SizeOf(NativeInputEvent)) : nicBusy=0
  If rc=0 : ProcedureReturn nicResult(0) : EndIf
  If rc<>1
    If rc>1 : rc=#NUI_ERR_PROVIDER : EndIf
    ProcedureReturn nicResult(rc)
  EndIf
  If NativeInputEventValid(@candidate)=0 : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  If candidate\kind=#AIE_CANCEL
    If candidate\generation<nicGeneration : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
    nicGeneration=candidate\generation
  Else
    If candidate\generation<>nicGeneration : ProcedureReturn nicResult(#NUI_ERR_PROVIDER) : EndIf
  EndIf
  For i=0 To SizeOf(NativeInputEvent)-8 Step 8 : PokeI(event+i,PeekI(@candidate+i)) : Next
  ProcedureReturn nicResult(1)
EndProcedure
Procedure.i AnvilInputFlush()
  Protected rc.i
  If nicBusy<>0 : ProcedureReturn nicResult(#NUI_ERR_BUSY) : EndIf
  If nicContext=0 : ProcedureReturn nicResult(#NUI_ERR_STATE) : EndIf
  nicBusy=1 : rc=nicDispatch(#NUI_FLUSH,nicContext,0,0) : nicBusy=0
  If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
  ProcedureReturn nicResult(rc)
EndProcedure
Procedure.i AnvilInputClose()
  Protected rc.i
  If nicBusy<>0 : ProcedureReturn nicResult(#NUI_ERR_BUSY) : EndIf
  If nicContext=0 : ProcedureReturn nicResult(0) : EndIf
  nicBusy=1 : rc=nicDispatch(#NUI_CLOSE,nicContext,0,0) : nicBusy=0
  If rc>0 : rc=#NUI_ERR_PROVIDER : EndIf
  If rc=0 : nicContext=0 : nicCaps=0 : nicWidth=0 : nicHeight=0 : nicGeneration=0 : EndIf
  ProcedureReturn nicResult(rc)
EndProcedure
