; SPDX-License-Identifier: MIT
; Compatibility touch-to-retained adapter over the shared pointer owner.
XIncludeFile "Anvil/Graphics/neon_service_pointer.pbi"
#NEON_TOUCH_ERR_ARGS = -21600
#NEON_TOUCH_ERR_ABI = -21601
#NEON_TOUCH_ERR_UNBOUND = -21602
#NEON_TOUCH_ERR_BUSY = -21603
Global nstpPointer.NeonPointerState
Global nstpBound.i,nstpBusy.i,nstpFeedBusy.i,nstpCapture.i
Procedure.i nstpError(rc.i)
  If rc=#NPT_ERR_ARGS Or rc=#NPT_ERR_PROVIDER : ProcedureReturn #NEON_TOUCH_ERR_ARGS : EndIf
  If rc=#NPT_ERR_ABI : ProcedureReturn #NEON_TOUCH_ERR_ABI : EndIf
  If rc=#NPT_ERR_STATE : ProcedureReturn #NEON_TOUCH_ERR_UNBOUND : EndIf
  If rc=#NPT_ERR_BUSY : ProcedureReturn #NEON_TOUCH_ERR_BUSY : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i nstpEnsure()
  If nstpPointer\magic=0 : ProcedureReturn NeonPointerConfigure(@nstpPointer,1,1,1,1) : EndIf
  If nptValid(@nstpPointer)=0 : ProcedureReturn #NEON_TOUCH_ERR_UNBOUND : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i nstpCancel()
  Protected rc.i=nstpEnsure()
  If rc<>0 : ProcedureReturn nstpError(rc) : EndIf
  NeonPointerCancel(@nstpPointer) : nstpCapture=0
  ProcedureReturn NeonRetainedUpdateInput(-1.0,-1.0,0,0,0,0,0)
EndProcedure
Procedure.i NeonServiceTouchCancel()
  Protected rc.i
  If nstpBusy<>0 Or nstpFeedBusy<>0 : ProcedureReturn #NEON_TOUCH_ERR_BUSY : EndIf
  nstpFeedBusy=1 : rc=nstpCancel() : nstpFeedBusy=0 : ProcedureReturn rc
EndProcedure
Procedure.i NeonServiceTouchBind(services.i)
  Protected rc.i
  If nstpBusy<>0 Or nstpFeedBusy<>0 Or nstpPointer\down<>0 : ProcedureReturn #NEON_TOUCH_ERR_BUSY : EndIf
  ; Identity mapping retains the compatibility API's logical-screen coordinates.
  nstpBusy=1 : rc=NeonServicePointerBind(@nstpPointer,services,1,1,1,1) : nstpBusy=0
  If rc=#NPT_ERR_PROVIDER : ProcedureReturn #NEON_TOUCH_ERR_UNBOUND : EndIf
  If rc<>0 : ProcedureReturn nstpError(rc) : EndIf
  nstpBound=1 : nstpCapture=0 : ProcedureReturn 0
EndProcedure
Procedure.i nstpApplyCurrent()
  Protected rc.i,hit.i,captured.i
  If nstpPointer\changed=0 : ProcedureReturn 0 : EndIf
  If nstpPointer\cancelled<>0 : ProcedureReturn nstpCancel() : EndIf
  hit=NeonRetainedHit(nstpPointer\x,nstpPointer\y)
  If nstpPointer\pressed<>0 : nstpCapture=hit : EndIf
  If nstpPointer\released<>0
    captured=nstpCapture : nstpCapture=0
    If captured=0 Or hit<>captured : ProcedureReturn nstpCancel() : EndIf
    rc=NeonRetainedUpdateInput(nstpPointer\x,nstpPointer\y,0,1,0,0,0)
    If rc<>0 : ProcedureReturn rc : EndIf
    ProcedureReturn NeonRetainedUpdateInput(-1.0,-1.0,0,0,0,0,0)
  EndIf
  If nstpCapture=0 Or hit<>nstpCapture : ProcedureReturn NeonRetainedUpdateInput(-1.0,-1.0,1,0,0,0,0) : EndIf
  ProcedureReturn NeonRetainedUpdateInput(nstpPointer\x,nstpPointer\y,1,0,0,0,0)
EndProcedure
Procedure.i NeonServiceTouchFeed(*event.AnvilTouchEvent)
  Protected rc.i
  If nstpBusy<>0 Or nstpFeedBusy<>0 : ProcedureReturn #NEON_TOUCH_ERR_BUSY : EndIf
  nstpFeedBusy=1 : rc=nstpEnsure()
  If rc=0 : rc=NeonPointerFeed(@nstpPointer,*event) : EndIf
  If rc=0 : rc=nstpApplyCurrent() : EndIf
  nstpFeedBusy=0 : ProcedureReturn nstpError(rc)
EndProcedure
Procedure.i NeonServiceTouchDrain(limit.i)
  Protected rc.i,n.i,applied.i
  If nstpBusy<>0 Or nstpFeedBusy<>0 : ProcedureReturn #NEON_TOUCH_ERR_BUSY : EndIf
  If nstpBound=0 : ProcedureReturn #NEON_TOUCH_ERR_UNBOUND : EndIf
  If limit<1 Or limit>64 : ProcedureReturn #NEON_TOUCH_ERR_ARGS : EndIf
  nstpBusy=1
  For n=1 To limit
    rc=NeonServicePointerPoll(@nstpPointer)
    If rc=0 : Break : EndIf
    If rc<0
      nstpCancel() : nstpBusy=0 : ProcedureReturn nstpError(rc)
    EndIf
    rc=nstpApplyCurrent()
    If rc<>0 : nstpCancel() : nstpBusy=0 : ProcedureReturn rc : EndIf
    applied=applied+1
  Next
  nstpBusy=0 : ProcedureReturn applied
EndProcedure
