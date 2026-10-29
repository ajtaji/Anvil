; Cooperative HTTP polling boundary. An absent service has no work.
; The composition installs its callback before scheduler polling begins.
; Installation and dispatch are serialized; the callback must remain live.
Global *gHttpPollCallback = 0

Procedure HttpPollInstall(callback.i)
  gHttpPollCallback = callback
EndProcedure

Procedure HttpServerPoll()
  If gHttpPollCallback <> 0
    gHttpPollCallback()
  EndIf
EndProcedure
