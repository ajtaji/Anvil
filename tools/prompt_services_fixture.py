"""Bindings for existing diagnostic service adapters (not product backends)."""
FULL_BINDING=r'''
; This board wires its existing bounded services to the portable prompt.
Procedure.i TestPromptServices(operation.i)
 Select operation
  Case #APS_POINTER
   MouseTick() : TouchTick()
   CompilerIf #CAP_TOUCH=1
    TouchKeyboardServiceTick()
   CompilerEndIf
  Case #APS_SCREEN : ScreenServiceTick()
  Case #APS_ATTACH
   If gMouseTried=0 And gScreen<>0 : MouseTryAttach() : EndIf
  Case #APS_DHCP : NetDhcpTick()
  Case #APS_NTP
   CompilerIf #CAP_NET=1
    NtpServiceTick()
   CompilerEndIf
  Case #APS_FAN : FanTick()
  Case #APS_TEMPERATURE : HwTempSampleTick()
  Case #APS_NET_REARM : NetConsoleRearm()
  Case #APS_NET_LINKLOCAL : NetConsoleLlTick()
  Case #APS_HTTP
   CompilerIf #CAP_NET=1
    HttpServerPoll()
   CompilerEndIf
  Case #APS_TCP
   CompilerIf #CAP_NET=0
    TcpTick()
   CompilerEndIf
 EndSelect
 ProcedureReturn 0
EndProcedure

Procedure.i TestPromptInputs(operation.i)
 Select operation
  Case #APS_KEYBOARD
   If gKbdH<>0 : ProcedureReturn KeyboardChar() : EndIf
  Case #APS_CLAIM_LOCAL : NetConsoleClaimLocal()
  Case #APS_NET_INPUT : ProcedureReturn NetConsoleGetc()
 EndSelect
 ProcedureReturn 0
EndProcedure

Procedure.i TestPromptPump(operation.i)
 NetConsolePump()
 ProcedureReturn 0
EndProcedure

'''

LANE_BINDING=r'''
; This board wires its existing bounded services to the portable prompt.
Procedure.i TestPromptServices(operation.i)
 Select operation
  Case #APS_POINTER
   MouseTick() : TouchTick()
   CompilerIf #CAP_TOUCH=1
    TouchKeyboardServiceTick()
   CompilerEndIf
  Case #APS_SCREEN : ScreenServiceTick()
  Case #APS_DHCP : NetDhcpTick()
  Case #APS_NTP
   CompilerIf #CAP_NET=1
    NtpServiceTick()
   CompilerEndIf
  Case #APS_FAN : FanTick()
  Case #APS_TEMPERATURE : HwTempSampleTick()
  Case #APS_NET_REARM : NetConsoleRearm()
  Case #APS_NET_LINKLOCAL : NetConsoleLlTick()
  Case #APS_HTTP
   CompilerIf #CAP_NET=1
    HttpServerPoll()
   CompilerEndIf
  Case #APS_TCP
   CompilerIf #CAP_NET=0
    TcpTick()
   CompilerEndIf
 EndSelect
 ProcedureReturn 0
EndProcedure

Procedure.i TestPromptPump(operation.i)
 NetConsolePump()
 ProcedureReturn 0
EndProcedure

'''
