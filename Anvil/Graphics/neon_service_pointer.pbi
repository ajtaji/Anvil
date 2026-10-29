; SPDX-License-Identifier: MIT
; Single-consumer transport for the portable pointer tracker; no driver copy.
XIncludeFile "Anvil/Graphics/neon_pointer.pbi"
Procedure.i nspNoPoll(record.i)
  ProcedureReturn #NPT_ERR_STATE
EndProcedure
Procedure.i nspNoFlush()
  ProcedureReturn #NPT_ERR_STATE
EndProcedure
Global nspPoll.i=@nspNoPoll,nspFlush.i=@nspNoFlush,nspOwner.i,nspBusy.i
Procedure.i NeonServicePointerBind(*s.NeonPointerState,services.i,sourceW.i,sourceH.i,canvasW.i,canvasH.i)
  Protected poll.i,flushQueuePtr.i=@nspNoFlush,rc.i,i.i,*old.NeonPointerState,candidate.NeonPointerState
  If nspBusy<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  If nspOwner<>0
    *old=nspOwner : If *old\down<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  EndIf
  If services=0 Or (services & 7)<>0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If (PeekL(services)&$FFFFFFFF)<>$53564E41 Or PeekL(services+4)<>1 Or PeekL(services+8)<0 Or (PeekL(services+12)&$FFFFFFFF)<44 : ProcedureReturn #NPT_ERR_ABI : EndIf
  poll=PeekI(services+16+40*8) : flushQueuePtr=PeekI(services+16+42*8)
  If poll=0 Or flushQueuePtr=0 : ProcedureReturn #NPT_ERR_PROVIDER : EndIf
  If *s=0 Or (*s & 7)<>0 : ProcedureReturn #NPT_ERR_ARGS : EndIf
  If *s\magic<>0 And *s\magic<>#NPT_MAGIC : ProcedureReturn #NPT_ERR_STATE : EndIf
  If *s\magic=#NPT_MAGIC And *s\down<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  rc=NeonPointerConfigure(@candidate,sourceW,sourceH,canvasW,canvasH) : If rc<>0 : ProcedureReturn rc : EndIf
  nspBusy=1 : rc=flushQueuePtr() : nspBusy=0
  If rc<>0
    If rc>0 : rc=#NPT_ERR_PROVIDER : EndIf
    ProcedureReturn rc
  EndIf
  For i=0 To SizeOf(NeonPointerState)-8 Step 8 : PokeI(*s+i,PeekI(@candidate+i)) : Next
  nspPoll=poll : nspFlush=flushQueuePtr : nspOwner=*s : ProcedureReturn 0
EndProcedure
Procedure.i NeonServicePointerPoll(*s.NeonPointerState)
  Protected event.AnvilTouchEvent,rc.i
  If nspBusy<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  If nptValid(*s)=0 Or nspOwner<>*s : ProcedureReturn #NPT_ERR_STATE : EndIf
  nspBusy=1 : rc=nspPoll(@event)
  If rc=0 : NeonPointerIdle(*s)
  ElseIf rc=1
    rc=NeonPointerFeed(*s,@event) : If rc=0 : rc=1 : EndIf
  ElseIf rc>1 : rc=#NPT_ERR_PROVIDER : EndIf
  If rc<0 : NeonPointerCancel(*s) : EndIf
  nspBusy=0 : ProcedureReturn rc
EndProcedure
Procedure.i NeonServicePointerUnbind(*s.NeonPointerState)
  If nspBusy<>0 : ProcedureReturn #NPT_ERR_BUSY : EndIf
  If nptValid(*s)=0 Or nspOwner<>*s : ProcedureReturn #NPT_ERR_STATE : EndIf
  NeonPointerCancel(*s) : nspOwner=0 : nspPoll=@nspNoPoll : nspFlush=@nspNoFlush : ProcedureReturn 0
EndProcedure
