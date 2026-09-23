; Shared display connection policy. Boards dispatch the returned action;
; this keeps hardware dispatch separate from shared lifecycle policy.
#SCREEN_CONNECTION_DISABLED=0
#SCREEN_CONNECTION_ABSENT=1
#SCREEN_CONNECTION_PROBING=2
#SCREEN_CONNECTION_ATTACHING=3
#SCREEN_CONNECTION_REDRAWING=4
#SCREEN_CONNECTION_ATTACHED=5
#SCREEN_CONNECTION_DETACHING=6
#SCREEN_CONNECTION_QUARANTINED=7

#SCREEN_CONNECTION_ACTION_NONE=0
#SCREEN_CONNECTION_ACTION_PROBE=1
#SCREEN_CONNECTION_ACTION_ATTACH=2
#SCREEN_CONNECTION_ACTION_DETACH=3
#SCREEN_CONNECTION_ACTION_REDRAW=4

; Probe: PENDING while an asynchronous sample is in flight, COMPLETE when
; physical connection evidence is present, RESULT_ABSENT only for sampled
; HPD absence, negative for permanent failure. EDID failure is not absence.
#SCREEN_CONNECTION_PENDING=0
#SCREEN_CONNECTION_COMPLETE=1
#SCREEN_CONNECTION_RETRY=2
#SCREEN_CONNECTION_RESULT_ABSENT=3

#SCREEN_CONNECTION_DEFAULT_POLL_MS=1000
#SCREEN_CONNECTION_MIN_POLL_MS=50
#SCREEN_CONNECTION_MAX_POLL_MS=60000
#SCREEN_CONNECTION_DETACH_SAMPLES=2

Global gScreenConnectionState.i=#SCREEN_CONNECTION_DISABLED
Global gScreenConnectionGeneration.i=0
Global gScreenConnectionError.i=0
Global gScreenConnectionRegistered.i=0
Global gScreenConnectionPollMs.i=#SCREEN_CONNECTION_DEFAULT_POLL_MS
Global gScreenConnectionPollAt.i=0
Global gScreenConnectionProbeDue.i=0
Global gScreenConnectionProbeFrom.i=#SCREEN_CONNECTION_ABSENT
Global gScreenConnectionAbsentSamples.i=0
Global gScreenConnectionDetachTarget.i=#SCREEN_CONNECTION_ABSENT
Global gScreenConnectionAction.i=#SCREEN_CONNECTION_ACTION_NONE
Global gScreenConnectionActionClaimed.i=0
Global gScreenConnectionSurfaceOwned.i=0

Procedure.i ScreenConnectionState() : ProcedureReturn gScreenConnectionState : EndProcedure
Procedure.i ScreenConnectionGeneration() : ProcedureReturn gScreenConnectionGeneration : EndProcedure
Procedure.i ScreenConnectionError() : ProcedureReturn gScreenConnectionError : EndProcedure
Procedure.i ScreenConnectionRegistered() : ProcedureReturn gScreenConnectionRegistered : EndProcedure

Procedure ScreenConnectionQuarantine(error.i)
  If error>=0 : error=-1 : EndIf
  gScreenConnectionError=error
  gScreenConnectionState=#SCREEN_CONNECTION_QUARANTINED
  gScreenConnectionProbeDue=0
  gScreenConnectionAbsentSamples=0
EndProcedure

Procedure ScreenConnectionBeginDetach(target.i,error.i)
  If target<>#SCREEN_CONNECTION_ABSENT And target<>#SCREEN_CONNECTION_QUARANTINED : target=#SCREEN_CONNECTION_QUARANTINED : EndIf
  If target=#SCREEN_CONNECTION_QUARANTINED
    If error>=0 : error=-1 : EndIf
    gScreenConnectionError=error
  EndIf
  gScreenConnectionDetachTarget=target
  gScreenConnectionState=#SCREEN_CONNECTION_DETACHING
EndProcedure

Procedure.i ScreenConnectionRegister(pollMs.i)
  ; Replacement is refused: disable the old, already-quiesced contract first.
  If gScreenConnectionRegistered<>0 : ProcedureReturn 0 : EndIf
  If pollMs<#SCREEN_CONNECTION_MIN_POLL_MS Or pollMs>#SCREEN_CONNECTION_MAX_POLL_MS : pollMs=#SCREEN_CONNECTION_DEFAULT_POLL_MS : EndIf
  gScreenConnectionPollMs=pollMs
  gScreenConnectionPollAt=0
  gScreenConnectionProbeDue=1
  gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ABSENT
  gScreenConnectionAbsentSamples=0
  gScreenConnectionDetachTarget=#SCREEN_CONNECTION_ABSENT
  gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_NONE
  gScreenConnectionActionClaimed=0
  gScreenConnectionGeneration=0
  gScreenConnectionError=0
  gScreenConnectionRegistered=1
  gScreenConnectionSurfaceOwned=0
  gScreenConnectionState=#SCREEN_CONNECTION_ABSENT
  ProcedureReturn 1
EndProcedure

Procedure.i ScreenConnectionDisable()
  ; Never forget a claimed action, an asynchronous hardware operation, or a
  ; surface/DMA owner. A pending PROBE may own a firmware mailbox buffer even
  ; before any surface exists. Only settled ABSENT, pre-ownership quarantine,
  ; or an already-disabled contract can be discarded.
  If gScreenConnectionActionClaimed<>0 Or gScreenConnectionAction<>#SCREEN_CONNECTION_ACTION_NONE Or gScreenConnectionSurfaceOwned<>0
    ProcedureReturn 0
  EndIf
  If gScreenConnectionState<>#SCREEN_CONNECTION_DISABLED And gScreenConnectionState<>#SCREEN_CONNECTION_ABSENT And gScreenConnectionState<>#SCREEN_CONNECTION_QUARANTINED
    ProcedureReturn 0
  EndIf
  gScreenConnectionRegistered=0
  gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_NONE
  gScreenConnectionActionClaimed=0
  gScreenConnectionState=#SCREEN_CONNECTION_DISABLED
  ProcedureReturn 1
EndProcedure

; Returns and claims at most one action. Nested/repeated calls return NONE
; until Complete consumes that exact action token.
Procedure.i ScreenConnectionNextAction(nowMs.i)
  Protected now.i
  Protected elapsed.i
  If gScreenConnectionRegistered=0 Or gScreenConnectionState=#SCREEN_CONNECTION_QUARANTINED Or gScreenConnectionActionClaimed<>0
    ProcedureReturn #SCREEN_CONNECTION_ACTION_NONE
  EndIf
  If gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_NONE
    Select gScreenConnectionState
      Case #SCREEN_CONNECTION_ABSENT
        now=nowMs&$FFFFFFFF : elapsed=(now-gScreenConnectionPollAt)&$FFFFFFFF
        If gScreenConnectionProbeDue<>0 Or elapsed>=gScreenConnectionPollMs
          gScreenConnectionProbeDue=0 : gScreenConnectionPollAt=now
          gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ABSENT
          gScreenConnectionState=#SCREEN_CONNECTION_PROBING
          gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_PROBE
        EndIf
      Case #SCREEN_CONNECTION_ATTACHED
        now=nowMs&$FFFFFFFF : elapsed=(now-gScreenConnectionPollAt)&$FFFFFFFF
        If gScreenConnectionProbeDue<>0 Or elapsed>=gScreenConnectionPollMs
          gScreenConnectionProbeDue=0 : gScreenConnectionPollAt=now
          gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ATTACHED
          gScreenConnectionState=#SCREEN_CONNECTION_PROBING
          gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_PROBE
        EndIf
      Case #SCREEN_CONNECTION_PROBING : gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_PROBE
      Case #SCREEN_CONNECTION_ATTACHING : gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_ATTACH
      Case #SCREEN_CONNECTION_REDRAWING : gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_REDRAW
      Case #SCREEN_CONNECTION_DETACHING : gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_DETACH
    EndSelect
  EndIf
  If gScreenConnectionAction<>#SCREEN_CONNECTION_ACTION_NONE : gScreenConnectionActionClaimed=1 : EndIf
  ProcedureReturn gScreenConnectionAction
EndProcedure

Procedure.i ScreenConnectionComplete(action.i,result.i,nowMs.i)
  If gScreenConnectionActionClaimed=0 Or action<>gScreenConnectionAction : ProcedureReturn 0 : EndIf
  gScreenConnectionActionClaimed=0
  gScreenConnectionAction=#SCREEN_CONNECTION_ACTION_NONE
  Select action
    Case #SCREEN_CONNECTION_ACTION_PROBE
      If result<0
        If gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ATTACHED : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,result) : Else : ScreenConnectionQuarantine(result) : EndIf
      ElseIf result=#SCREEN_CONNECTION_PENDING
        ; Preserve PROBING while a mailbox/GPIO sample advances asynchronously.
      ElseIf result=#SCREEN_CONNECTION_COMPLETE
        gScreenConnectionAbsentSamples=0
        If gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ATTACHED
          gScreenConnectionState=#SCREEN_CONNECTION_ATTACHED
        Else
          ; ATTACH may acquire partial resources, so ownership begins before
          ; the first attach step and ends only after DETACH completes.
          gScreenConnectionSurfaceOwned=1
          gScreenConnectionState=#SCREEN_CONNECTION_ATTACHING
        EndIf
      ElseIf result=#SCREEN_CONNECTION_RESULT_ABSENT
        If gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ATTACHED
          gScreenConnectionAbsentSamples=gScreenConnectionAbsentSamples+1
          If gScreenConnectionAbsentSamples>=#SCREEN_CONNECTION_DETACH_SAMPLES
            ScreenConnectionBeginDetach(#SCREEN_CONNECTION_ABSENT,0)
          Else
            gScreenConnectionState=#SCREEN_CONNECTION_ATTACHED
            ; PollAt retains the first sample time, enforcing a real gap.
          EndIf
        Else
          gScreenConnectionState=#SCREEN_CONNECTION_ABSENT
        EndIf
      Else
        If gScreenConnectionProbeFrom=#SCREEN_CONNECTION_ATTACHED
          ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,-2)
        Else
          ScreenConnectionQuarantine(-2)
        EndIf
      EndIf
    Case #SCREEN_CONNECTION_ACTION_ATTACH
      If result<0 : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,result)
      ElseIf result=#SCREEN_CONNECTION_RETRY : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_ABSENT,0)
      ElseIf result=#SCREEN_CONNECTION_COMPLETE : gScreenConnectionState=#SCREEN_CONNECTION_REDRAWING
      ElseIf result<>#SCREEN_CONNECTION_PENDING : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,-2)
      EndIf
    Case #SCREEN_CONNECTION_ACTION_REDRAW
      If result<0 : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,result)
      ElseIf result=#SCREEN_CONNECTION_RETRY : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_ABSENT,0)
      ElseIf result=#SCREEN_CONNECTION_COMPLETE
        gScreenConnectionGeneration=gScreenConnectionGeneration+1
        gScreenConnectionAbsentSamples=0
        gScreenConnectionPollAt=nowMs&$FFFFFFFF
        gScreenConnectionState=#SCREEN_CONNECTION_ATTACHED
      ElseIf result<>#SCREEN_CONNECTION_PENDING : ScreenConnectionBeginDetach(#SCREEN_CONNECTION_QUARANTINED,-2)
      EndIf
    Case #SCREEN_CONNECTION_ACTION_DETACH
      If result<0 : ScreenConnectionQuarantine(result)
      ElseIf result=#SCREEN_CONNECTION_COMPLETE
        gScreenConnectionSurfaceOwned=0
        gScreenConnectionAbsentSamples=0
        gScreenConnectionPollAt=nowMs&$FFFFFFFF
        gScreenConnectionProbeDue=0
        If gScreenConnectionDetachTarget=#SCREEN_CONNECTION_QUARANTINED : gScreenConnectionState=#SCREEN_CONNECTION_QUARANTINED : Else : gScreenConnectionState=#SCREEN_CONNECTION_ABSENT : EndIf
      ElseIf result<>#SCREEN_CONNECTION_PENDING : ScreenConnectionQuarantine(-2)
      EndIf
  EndSelect
  ProcedureReturn 1
EndProcedure
