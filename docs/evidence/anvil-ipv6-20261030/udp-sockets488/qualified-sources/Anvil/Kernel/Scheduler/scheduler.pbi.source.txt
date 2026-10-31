; Portable bounded task-state foundation; no context switch or timer driver.
; All calls require ONE serialized kernel owner, never interrupt context.
; No callbacks run here. A target dispatcher must perform real stack/context
; ownership before treating SchedNext as permission to execute application code.
#SCHED_FREE = 0
#SCHED_READY = 1
#SCHED_RUNNING = 2
#SCHED_WAITING = 3
#SCHED_DONE = 4
#SCHED_CANCELLED = 5
#SCHED_LIMIT = 32
Global Dim sched_state.i[32]
Global Dim sched_generation.i[32]
Global Dim sched_key.i[32]
Global Dim sched_deadline.i[32]
Global Dim sched_queue.i[32]
Global Dim sched_waitqueue.i[32]
Global sched_count.i
Global sched_waitcount.i
Global sched_running.i
Global sched_now.i

Procedure.i SchedSlot(handle.i)
  Protected slot.i
  If handle < 32
    ProcedureReturn -1
  EndIf
  slot = handle % 32
  If sched_state[slot] = #SCHED_FREE Or sched_generation[slot] <> handle / 32
    ProcedureReturn -1
  EndIf
  ProcedureReturn slot
EndProcedure

Procedure.i SchedState(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn sched_state[slot]
EndProcedure

Procedure SchedEnqueue(slot.i)
  ; Internal: caller removes RUNNING/WAITING ownership first. At most32
  ; live slots exist, and a slot enters this queue once per READY transition.
  sched_queue[sched_count] = slot
  sched_count = sched_count + 1
  sched_state[slot] = #SCHED_READY
  sched_key[slot] = 0
  sched_deadline[slot] = 0
EndProcedure

Procedure SchedRemove(slot.i)
  Protected pos.i
  Protected nextpos.i
  For pos = 0 To sched_count - 1
    If sched_queue[pos] = slot
      For nextpos = pos + 1 To sched_count - 1
        sched_queue[nextpos - 1] = sched_queue[nextpos]
      Next
      sched_count = sched_count - 1
      ProcedureReturn
    EndIf
  Next
EndProcedure

Procedure.i SchedCreate()
  Protected slot.i
  For slot = 0 To #SCHED_LIMIT - 1
    ; Exhausted generations retire the slot, rather than alias a stale handle.
    If sched_state[slot] = #SCHED_FREE And sched_generation[slot] < 33554431
      sched_generation[slot] = sched_generation[slot] + 1
      SchedEnqueue(slot)
      ProcedureReturn sched_generation[slot] * 32 + slot
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure SchedRemoveWait(slot.i)
  Protected pos.i
  Protected nextpos.i
  For pos = 0 To sched_waitcount - 1
    If sched_waitqueue[pos] = slot
      For nextpos = pos + 1 To sched_waitcount - 1
        sched_waitqueue[nextpos - 1] = sched_waitqueue[nextpos]
      Next
      sched_waitcount = sched_waitcount - 1
      ProcedureReturn
    EndIf
  Next
EndProcedure

Procedure.i SchedNext()
  Protected slot.i
  If sched_running <> 0 Or sched_count = 0
    ProcedureReturn 0
  EndIf
  slot = sched_queue[0]
  SchedRemove(slot)
  sched_state[slot] = #SCHED_RUNNING
  sched_running = sched_generation[slot] * 32 + slot
  ProcedureReturn sched_running
EndProcedure

Procedure.i SchedYield(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0 Or handle <> sched_running
    ProcedureReturn 0
  EndIf
  sched_running = 0
  SchedEnqueue(slot)
  ProcedureReturn 1
EndProcedure

Procedure.i SchedWait(handle.i, key.i, deadline.i)
  Protected slot.i
  slot = SchedSlot(handle)
  ; deadline0 means no timeout; key0 means timer-only wait.
  If slot < 0 Or handle <> sched_running Or key < 0 Or deadline < 0
    ProcedureReturn 0
  EndIf
  If key = 0 And deadline = 0
    ProcedureReturn 0
  EndIf
  sched_running = 0
  If deadline <> 0 And deadline <= sched_now
    SchedEnqueue(slot)
    ProcedureReturn 1
  EndIf
  sched_state[slot] = #SCHED_WAITING
  sched_key[slot] = key
  sched_deadline[slot] = deadline
  sched_waitqueue[sched_waitcount] = slot
  sched_waitcount = sched_waitcount + 1
  ProcedureReturn 1
EndProcedure

Procedure.i SchedWake(key.i, maximum.i)
  Protected slot.i
  Protected woke.i
  Protected pos.i
  If key <= 0 Or maximum <= 0 Or maximum > #SCHED_LIMIT
    ProcedureReturn -1
  EndIf
  woke = 0
  pos = 0
  While pos < sched_waitcount
    slot = sched_waitqueue[pos]
    If sched_key[slot] = key
      SchedRemoveWait(slot)
      SchedEnqueue(slot)
      woke = woke + 1
      If woke = maximum
        ProcedureReturn woke
      EndIf
    Else
      pos = pos + 1
    EndIf
  Wend
  ProcedureReturn woke
EndProcedure

Procedure.i SchedAdvance(now.i)
  Protected slot.i
  Protected woke.i
  Protected pos.i
  If now < sched_now
    ProcedureReturn -1
  EndIf
  sched_now = now
  woke = 0
  pos = 0
  While pos < sched_waitcount
    slot = sched_waitqueue[pos]
    If sched_deadline[slot] <> 0 And sched_deadline[slot] <= now
      SchedRemoveWait(slot)
      SchedEnqueue(slot)
      woke = woke + 1
    Else
      pos = pos + 1
    EndIf
  Wend
  ProcedureReturn woke
EndProcedure

Procedure.i SchedFinish(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0 Or handle <> sched_running
    ProcedureReturn 0
  EndIf
  sched_running = 0
  sched_state[slot] = #SCHED_DONE
  ProcedureReturn 1
EndProcedure

Procedure.i SchedCancel(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0
    ProcedureReturn 0
  EndIf
  ; RUNNING cancellation requires a safe-point/context backend, absent here.
  If sched_state[slot] <> #SCHED_READY And sched_state[slot] <> #SCHED_WAITING
    ProcedureReturn 0
  EndIf
  If sched_state[slot] = #SCHED_READY
    SchedRemove(slot)
  Else
    SchedRemoveWait(slot)
  EndIf
  sched_state[slot] = #SCHED_CANCELLED
  sched_key[slot] = 0
  sched_deadline[slot] = 0
  ProcedureReturn 1
EndProcedure

Procedure.i SchedReap(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0
    ProcedureReturn 0
  EndIf
  If sched_state[slot] <> #SCHED_DONE And sched_state[slot] <> #SCHED_CANCELLED
    ProcedureReturn 0
  EndIf
  sched_state[slot] = #SCHED_FREE
  ProcedureReturn 1
EndProcedure
