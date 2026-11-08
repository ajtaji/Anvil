; Optional prompt services. This is registration, not device discovery.
; One synchronous provider per monitor composition; serialize registration and
; prompt execution. Providers perform bounded work and must not reenter this
; dispatcher. No provider means no optional hardware/service work or input.
#APS_POINTER=1
#APS_SCREEN=2
#APS_ATTACH=3
#APS_KEYBOARD=4
#APS_CLAIM_LOCAL=5
#APS_NET_INPUT=6
#APS_DHCP=7
#APS_NTP=8
#APS_FAN=9
#APS_TEMPERATURE=10
#APS_NET_REARM=11
#APS_NET_PUMP=12
#APS_NET_LINKLOCAL=13
#APS_HTTP=14
#APS_TCP=15
#APS_ERR_OPERATION=1
#APS_ERR_ACTIVE=2
; KEYBOARD result: 0 none, 1..255 transport byte, 256 accepted normalized
; text/key-down events already queued. The latter claims local ownership but
; must not be fed through the byte translator a second time.
#APS_INPUT_QUEUED=256
Global anvil_promptPumpBound.i
Global anvil_promptPumpActive.i
Global anvil_promptInputsBound.i
Global anvil_promptInputsActive.i
Global anvil_promptServicesBound.i
Global anvil_promptServicesActive.i
Global anvil_promptServicesError.i
Procedure.i AnvilPromptServicesAbsent(operation.i)
 If operation=#APS_NET_INPUT : ProcedureReturn -1 : EndIf
 ProcedureReturn 0
EndProcedure
Global *anvil_promptServicesProvider=@AnvilPromptServicesAbsent
Global *anvil_promptInputsProvider=@AnvilPromptServicesAbsent
Global *anvil_promptPumpProvider=@AnvilPromptServicesAbsent
Procedure.i AnvilPromptServicesBind(provider.i)
 If anvil_promptServicesActive<>0 Or anvil_promptInputsActive<>0 Or anvil_promptPumpActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn 0
 EndIf
 *anvil_promptServicesProvider=@AnvilPromptServicesAbsent
 anvil_promptServicesBound=0
 If provider<>0
  *anvil_promptServicesProvider=provider : anvil_promptServicesBound=1
 EndIf
 anvil_promptServicesError=0
 ProcedureReturn 1
EndProcedure
Procedure.i AnvilPromptServicesPresent() : ProcedureReturn anvil_promptServicesBound : EndProcedure
Procedure.i AnvilPromptServicesLastError() : ProcedureReturn anvil_promptServicesError : EndProcedure
Procedure.i AnvilPromptService(operation.i)
 Protected result.i
 If operation<#APS_POINTER Or operation>#APS_TCP Or operation=#APS_KEYBOARD Or operation=#APS_CLAIM_LOCAL Or operation=#APS_NET_INPUT Or operation=#APS_NET_PUMP
  anvil_promptServicesError=#APS_ERR_OPERATION : ProcedureReturn -2
 EndIf
 If anvil_promptServicesActive<>0 Or anvil_promptInputsActive<>0 Or anvil_promptPumpActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn -2
 EndIf
 anvil_promptServicesActive=1 : anvil_promptServicesError=0
 result=anvil_promptServicesProvider(operation)
 anvil_promptServicesActive=0
 ProcedureReturn result
EndProcedure

; Input/ownership is separate from service work: a transport's bounded service
; may check cancellation without recursively driving the service dispatcher.
Procedure.i AnvilPromptInputsBind(provider.i)
 If anvil_promptInputsActive<>0 Or anvil_promptServicesActive<>0 Or anvil_promptPumpActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn 0
 EndIf
 *anvil_promptInputsProvider=@AnvilPromptServicesAbsent : anvil_promptInputsBound=0
 If provider<>0 : *anvil_promptInputsProvider=provider : anvil_promptInputsBound=1 : EndIf
 anvil_promptServicesError=0
 ProcedureReturn 1
EndProcedure
Procedure.i AnvilPromptInputsPresent() : ProcedureReturn anvil_promptInputsBound : EndProcedure
Procedure.i AnvilPromptInput(operation.i)
 Protected result.i
 If operation<>#APS_KEYBOARD And operation<>#APS_CLAIM_LOCAL And operation<>#APS_NET_INPUT
  anvil_promptServicesError=#APS_ERR_OPERATION : ProcedureReturn -2
 EndIf
 If anvil_promptInputsActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn -2
 EndIf
 anvil_promptInputsActive=1 : anvil_promptServicesError=0
 result=anvil_promptInputsProvider(operation)
 anvil_promptInputsActive=0
 ProcedureReturn result
EndProcedure

; Cancellation may pump transport while a background service is active. Keep
; this callable target separate from generic work so the call graph cannot
; acquire a false path back into link-local, DHCP or other command services.
Procedure.i AnvilPromptPumpBind(provider.i)
 If anvil_promptInputsActive<>0 Or anvil_promptServicesActive<>0 Or anvil_promptPumpActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn 0
 EndIf
 *anvil_promptPumpProvider=@AnvilPromptServicesAbsent : anvil_promptPumpBound=0
 If provider<>0 : *anvil_promptPumpProvider=provider : anvil_promptPumpBound=1 : EndIf
 anvil_promptServicesError=0
 ProcedureReturn 1
EndProcedure
Procedure.i AnvilPromptPumpPresent() : ProcedureReturn anvil_promptPumpBound : EndProcedure
Procedure.i AnvilPromptPump()
 Protected result.i
 If anvil_promptPumpActive<>0 Or anvil_promptInputsActive<>0
  anvil_promptServicesError=#APS_ERR_ACTIVE : ProcedureReturn -2
 EndIf
 anvil_promptPumpActive=1 : anvil_promptServicesError=0
 result=anvil_promptPumpProvider(#APS_NET_PUMP)
 anvil_promptPumpActive=0
 ProcedureReturn result
EndProcedure
