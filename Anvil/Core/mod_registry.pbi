; ======================================================================
;  THE SEAM REGISTRY - WHERE A LOADED DRIVER'S SERVICES LIVE
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Hal/module_format.pbi
;    Anvil/Hal/module_runtime.pbi
;
;  AND NOTHING ELSE, ON PURPOSE. This file is included near the TOP of a
;  board composition, ahead of every driver, because a driver that a
;  module may replace has to be able to ask the registry whether one has.
;  It reads no hardware, prints nothing, allocates nothing and calls no
;  other Anvil procedure, so putting it first costs nothing and being
;  able to put it first is what lets the question be asked in the right
;  place - inside the seam's own core file - instead of through a hook
;  bolted on beside it.
;
;  WHAT IT IS. One row per #SVCCAP_* id, each row holding up to
;  #MOD_SEAM_FNS function pointers, the record index that owns them, the
;  durable bindings consumers have taken on it, and the depth of calls
;  currently inside it. That is the whole of "a module published a
;  service" and the whole of "something still needs that service".
;
;  WHAT IT DELIBERATELY IS NOT. It is not the service table. The service
;  table (Anvil/Hal/abi.pbi) is the ABI a payload or a module CALLS
;  THROUGH; this is where the monitor records what a module handed back.
;  SvcSeamFill is the one slot that joins them, and it is three lines
;  that call into here.
;
;  THE THREE RULES THE REGISTRY ENFORCES, AND WHY EACH IS HERE RATHER
;  THAN IN THE LOADER:
;
;    A FILL IS ONLY LEGAL DURING init. A probe is side-effect-free by
;    contract, and publishing a function other code can immediately call
;    is a side effect. The loader opens the window (ModSeamFillOpen) for
;    exactly the duration of one init call, so a fill from a probe, from
;    a quiesce, or from a callback later is refused by the same test
;    rather than by three separate ones.
;
;    A FILL IS ONLY LEGAL FOR A SEAM THE HEADER DECLARED. The container's
;    seam list is signed into its digest, so a module cannot be edited
;    into claiming a seam; making the list ENFORCED rather than
;    documentation is what turns that into a guarantee. The loader calls
;    ModSeamAllow once per declared seam before it opens the window.
;
;    TWO OWNERS OF ONE SEAM IS REFUSED. Two drivers holding one piece of
;    hardware is how a board hangs, and the second one to arrive is the
;    one that has to be told.
; ======================================================================

#MOD_SEAM_ROWS = #MOD_SEAM_MAX + 1
#MOD_SEAM_NONE = -1

; The function table, flattened: seam * #MOD_SEAM_FNS + index.
Global Dim gSeamFn.i[#MOD_SEAM_ROWS * #MOD_SEAM_FNS]

; Which module record owns each seam, or #MOD_SEAM_NONE.
Global Dim gSeamOwner.i[#MOD_SEAM_ROWS]

; Which record the loader has ALLOWED to fill each seam. Set from the
; container's declared seam list before init, cleared when the record is
; released. A seam nobody has been allowed to fill cannot be filled.
Global Dim gSeamAllow.i[#MOD_SEAM_ROWS]

; How many of a seam's function slots are filled.
Global Dim gSeamFilled.i[#MOD_SEAM_ROWS]

; Depth of calls currently inside a seam. Non-zero means a consumer is
; ON THE STACK inside module code right now; unloading under that is a
; return address into memory about to be reused.
Global Dim gSeamDepth.i[#MOD_SEAM_ROWS]

; The durable bindings. gBindSeam[] is #MOD_SEAM_NONE for a free row.
Global Dim gBindSeam.i[#MOD_BIND_MAX]
Global Dim gBindSay.i[#MOD_BIND_MAX]      ; a procedure that prints the owner
Global Dim gBindDetach.i[#MOD_BIND_MAX]   ; what releases it, supplied by the owner

; The one record the registry will accept a fill from, and only while
; ModSeamFillOpen has been called. -1 the rest of the time, which is all
; of the time except inside one init call.
Global gSeamFillOwner.i = #MOD_SEAM_NONE
Global gSeamFillCount.i                   ; fills made inside the open window

; The last refusal the registry produced, for the sentence the loader
; prints. Valid immediately after the refusing call.
Global gSeamError.i
Global gSeamErrorSeam.i
Global gSeamErrorValue.i

Procedure.i ModSeamFail(code.i, sid.i, value.i)
  gSeamError = code
  gSeamErrorSeam = sid
  gSeamErrorValue = value
  ProcedureReturn code
EndProcedure

Procedure.i ModSeamIdOk(sid.i)
  If sid < 0 Or sid > #MOD_SEAM_MAX
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamReset() - cold start. Every row empty, every binding free.
;
;  It is NOT the mirror of ModArenaInit()'s cold-start refusal, and the
;  difference is deliberate: the arena refuses a second init because
;  forgetting a READY record would make live code available for
;  overwrite. The registry has no such hazard on its own, but it is only
;  ever called from the one place the arena is, so the arena's refusal
;  covers both.
; ----------------------------------------------------------------------
Procedure ModSeamReset()
  Define i.i
  i = 0
  While i < #MOD_SEAM_ROWS * #MOD_SEAM_FNS
    gSeamFn[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #MOD_SEAM_ROWS
    gSeamOwner[i] = #MOD_SEAM_NONE
    gSeamAllow[i] = #MOD_SEAM_NONE
    gSeamFilled[i] = 0
    gSeamDepth[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #MOD_BIND_MAX
    gBindSeam[i] = #MOD_SEAM_NONE
    gBindSay[i] = 0
    gBindDetach[i] = 0
    i = i + 1
  Wend
  gSeamFillOwner = #MOD_SEAM_NONE
  gSeamFillCount = 0
  gSeamError = #MOD_OK
  gSeamErrorSeam = #MOD_SEAM_NONE
  gSeamErrorValue = 0
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamAllow(owner, seam) - the loader transcribing one line of the
;  container's declared seam list.
;
;  It refuses a seam another record already OWNS, because a permission to
;  fill something that is already filled would turn into a #MOD_ERR_SEAM_
;  TAKEN halfway through an init - after the module had begun acquiring
;  hardware - instead of before it was entered at all. The collision is
;  knowable from the header, so it is answered from the header.
; ----------------------------------------------------------------------
Procedure.i ModSeamAllow(owner.i, sid.i)
  If ModSeamIdOk(sid) = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_ID, sid, owner)
  EndIf
  If gSeamOwner[sid] <> #MOD_SEAM_NONE
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_TAKEN, sid, gSeamOwner[sid])
  EndIf
  gSeamAllow[sid] = owner
  ProcedureReturn #MOD_OK
EndProcedure

; Withdraw every permission granted to one record without touching what
; it already filled. Used when a narrowing manifest line, a refused
; match or a refused probe means the module will not be entered.
Procedure ModSeamAllowClear(owner.i)
  Define i.i
  i = 0
  While i < #MOD_SEAM_ROWS
    If gSeamAllow[i] = owner
      gSeamAllow[i] = #MOD_SEAM_NONE
    EndIf
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamFillOpen / ModSeamFillClose - the window inside which a fill is
;  legal, opened by the loader around exactly one init call.
;
;  ModSeamFillClose answers how many fills happened, because "init
;  returned 0 and published nothing" is a failed activation and the
;  loader needs the number to say so.
; ----------------------------------------------------------------------
Procedure ModSeamFillOpen(owner.i)
  gSeamFillOwner = owner
  gSeamFillCount = 0
EndProcedure

Procedure.i ModSeamFillClose()
  gSeamFillOwner = #MOD_SEAM_NONE
  ProcedureReturn gSeamFillCount
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamFill(seam, index, fn) - what a driver's init calls, through the
;  service table, to publish one function.
;
;  EVERY REFUSAL HERE IS A CONTRACT VIOLATION BY THE MODULE, not an
;  operator mistake, so each returns a distinct code the loader turns
;  into a sentence naming the module's file. A module that ignores the
;  return and carries on is a module whose init will be unwound anyway,
;  because a seam it believes it filled answers nothing.
; ----------------------------------------------------------------------
Procedure.i ModSeamFill(sid.i, index.i, fn.i)
  Define slot.i
  If gSeamFillOwner = #MOD_SEAM_NONE
    ProcedureReturn ModSeamFail(#MOD_ERR_STATE, sid, 0)
  EndIf
  If ModSeamIdOk(sid) = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_ID, sid, index)
  EndIf
  If index < 0 Or index >= #MOD_SEAM_FNS
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_ID, sid, index)
  EndIf
  If fn = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_NOSERVICE, sid, index)
  EndIf
  If gSeamAllow[sid] <> gSeamFillOwner
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_UNDECLARED, sid, gSeamFillOwner)
  EndIf
  If gSeamOwner[sid] <> #MOD_SEAM_NONE And gSeamOwner[sid] <> gSeamFillOwner
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_TAKEN, sid, gSeamOwner[sid])
  EndIf
  slot = sid * #MOD_SEAM_FNS + index
  If gSeamFn[slot] <> 0
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_TAKEN, sid, index)
  EndIf
  gSeamFn[slot] = fn
  gSeamFilled[sid] = gSeamFilled[sid] + 1
  gSeamOwner[sid] = gSeamFillOwner
  gSeamFillCount = gSeamFillCount + 1
  gSeamError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamFn(seam, index) - the pointer, or 0.
;
;  A CONSUMER MUST TEST THE ZERO. There is no refusal stub here the way
;  the service table fills its unused slots with SvcUnimplemented,
;  because a seam's function signatures are not uniform - a stub could
;  not return the right kind of nothing for all of them - and because a
;  consumer that has to test anyway is a consumer that can fall back to
;  whatever it did before the module existed. That fallback is the
;  difference between a missing module and a dead feature.
; ----------------------------------------------------------------------
Procedure.i ModSeamFn(sid.i, index.i)
  If ModSeamIdOk(sid) = 0 Or index < 0 Or index >= #MOD_SEAM_FNS
    ProcedureReturn 0
  EndIf
  ProcedureReturn gSeamFn[sid * #MOD_SEAM_FNS + index]
EndProcedure

; 1 when anything at all fills this seam.
Procedure.i ModSeamFilledCount(sid.i)
  If ModSeamIdOk(sid) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn gSeamFilled[sid]
EndProcedure

Procedure.i ModSeamHas(sid.i)
  If ModSeamFilledCount(sid) > 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i ModSeamOwner(sid.i)
  If ModSeamIdOk(sid) = 0
    ProcedureReturn #MOD_SEAM_NONE
  EndIf
  ProcedureReturn gSeamOwner[sid]
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamEnter / ModSeamLeave - the depth of calls inside module code.
;
;  A consumer brackets its call with these. It is not a lock and it is
;  not reentrancy protection: this monitor runs one flow of control, and
;  the compiler's locals are static storage, so two calls into one
;  driver at once would be wrong for reasons this counter cannot fix.
;  What it is for is the case that CAN happen on one flow of control - a
;  console command issued from inside a driver callback asking to unload
;  the driver it is called from - and for that a depth is exactly right.
; ----------------------------------------------------------------------
Procedure ModSeamEnter(sid.i)
  If ModSeamIdOk(sid) <> 0
    gSeamDepth[sid] = gSeamDepth[sid] + 1
  EndIf
EndProcedure

Procedure ModSeamLeave(sid.i)
  If ModSeamIdOk(sid) <> 0 And gSeamDepth[sid] > 0
    gSeamDepth[sid] = gSeamDepth[sid] - 1
  EndIf
EndProcedure

Procedure.i ModSeamDepth(sid.i)
  If ModSeamIdOk(sid) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn gSeamDepth[sid]
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamBind(seam, saySelf, detach) - a consumer saying "I have taken
;  this service as my source and I intend to keep calling it".
;
;  THIS IS THE THING THAT MAKES AN UNLOAD REFUSABLE. Without it the only
;  honest answers to `mod unload` are "never" - because a filled pointer
;  may have been copied anywhere - or "always", which strands callers on
;  memory that is about to be reused. A binding is the third answer: a
;  consumer that keeps a service states so, and states HOW TO GIVE IT
;  BACK, and until it does the unload is refused with the count in the
;  sentence.
;
;  BOTH ARGUMENTS ARE REQUIRED AND THE SECOND IS THE IMPORTANT ONE. A
;  binding with no detach is a permanent refusal wearing a counter's
;  clothes. `saySelf` prints the owner's name for the refusal sentence -
;  a printing procedure rather than a string because the core owns the
;  layout of the line and the consumer owns the words in it, which is the
;  same split HwMonRegionSay() is written under.
; ----------------------------------------------------------------------
Procedure.i ModSeamBind(sid.i, saySelf.i, detach.i)
  Define i.i
  If ModSeamIdOk(sid) = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_SEAM_ID, sid, 0)
  EndIf
  If gSeamFilled[sid] = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_NOSERVICE, sid, 0)
  EndIf
  If saySelf = 0 Or detach = 0
    ProcedureReturn ModSeamFail(#MOD_ERR_STATE, sid, 0)
  EndIf
  i = 0
  While i < #MOD_BIND_MAX
    If gBindSeam[i] = #MOD_SEAM_NONE
      gBindSeam[i] = sid
      gBindSay[i] = saySelf
      gBindDetach[i] = detach
      gSeamError = #MOD_OK
      ProcedureReturn i
    EndIf
    i = i + 1
  Wend
  ProcedureReturn ModSeamFail(#MOD_ERR_RECORDS_FULL, sid, #MOD_BIND_MAX)
EndProcedure

Procedure ModSeamUnbind(handle.i)
  If handle < 0 Or handle >= #MOD_BIND_MAX
    ProcedureReturn
  EndIf
  gBindSeam[handle] = #MOD_SEAM_NONE
  gBindSay[handle] = 0
  gBindDetach[handle] = 0
EndProcedure

Procedure.i ModSeamBindCount(sid.i)
  Define i.i
  Define n.i
  n = 0
  i = 0
  While i < #MOD_BIND_MAX
    If gBindSeam[i] = sid
      n = n + 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn n
EndProcedure

; Print the owners of a seam's bindings, comma separated. The caller has
; already printed whatever introduces them.
Procedure ModSeamSayBinders(sid.i)
  Define i.i
  Define n.i
  Define *say
  n = 0
  i = 0
  While i < #MOD_BIND_MAX
    If gBindSeam[i] = sid
      If n > 0
        Print(", ")
      EndIf
      *say = gBindSay[i]
      If *say <> 0
        say()
      Else
        Print("an owner that did not name itself")
      EndIf
      n = n + 1
    EndIf
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamDetachAll(seam) - ask every binding on this seam to let go.
;
;  It calls the owner's own detach procedure rather than simply clearing
;  the row, because the consumer has state of its own to put back - a
;  cached pointer, a source it must fall back to - and a registry that
;  freed the row behind its back would leave exactly the dangling call
;  the binding existed to prevent. A detach that does not unbind is a
;  defect in the consumer and leaves the count where it was, so the
;  unload that provoked it is still refused.
; ----------------------------------------------------------------------
Procedure.i ModSeamDetachAll(sid.i)
  Define i.i
  Define *fn
  Define n.i
  i = 0
  While i < #MOD_BIND_MAX
    If gBindSeam[i] = sid
      *fn = gBindDetach[i]
      If *fn <> 0
        fn()
      EndIf
    EndIf
    i = i + 1
  Wend
  n = ModSeamBindCount(sid)
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  ModSeamReleaseOwner(owner) - THE UNWIND.
;
;  Called when an activation fails and when a module is unloaded. It
;  clears every function the record filled, every permission it held and
;  every binding pointing at a seam it owned, in that order, so that
;  nothing can observe a seam that is half-released.
;
;  It does NOT call the detach hooks. An unload has already refused if a
;  binding existed; a failed activation cannot have been bound, because
;  nothing outside init has seen the seam yet. Calling consumer code
;  from an unwind path would be the one place a driver failure could
;  re-enter the monitor, and it has no reason to.
; ----------------------------------------------------------------------
Procedure.i ModSeamReleaseOwner(owner.i)
  Define sid.i
  Define j.i
  Define released.i
  released = 0
  sid = 0
  While sid < #MOD_SEAM_ROWS
    If gSeamOwner[sid] = owner
      j = 0
      While j < #MOD_SEAM_FNS
        gSeamFn[sid * #MOD_SEAM_FNS + j] = 0
        j = j + 1
      Wend
      gSeamFilled[sid] = 0
      gSeamOwner[sid] = #MOD_SEAM_NONE
      gSeamDepth[sid] = 0
      j = 0
      While j < #MOD_BIND_MAX
        If gBindSeam[j] = sid
          gBindSeam[j] = #MOD_SEAM_NONE
          gBindSay[j] = 0
          gBindDetach[j] = 0
        EndIf
        j = j + 1
      Wend
      released = released + 1
    EndIf
    If gSeamAllow[sid] = owner
      gSeamAllow[sid] = #MOD_SEAM_NONE
    EndIf
    sid = sid + 1
  Wend
  ProcedureReturn released
EndProcedure
