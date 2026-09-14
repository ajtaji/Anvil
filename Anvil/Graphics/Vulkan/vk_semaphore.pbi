; ======================================================================
;  Target-neutral Vulkan 1.0 binary semaphore state engine
; ======================================================================
; SPDX-License-Identifier: MIT
;
; This is the lifetime/transaction owner behind vkCreateSemaphore,
; vkDestroySemaphore and vkQueueSubmit's wait/signal arrays.
;
; The state contract follows Vulkan-Docs v1.4.350, commit 81b1d516,
; chapters/synchronization.adoc: a binary semaphore is unsignaled or
; signaled; one wait consumes one signal; a signal must execute while the
; semaphore is unsignaled; and objects referenced by pending queue work
; remain alive until that work completes.  There is no host reset operation
; for a semaphore and no timeline behavior in this module.
;
; Reserve validates a whole ordered batch without changing semaphore state.
; Commit publishes all pending references atomically. A backend may complete
; immediately or remain pending until avkFlightPoll observes completion.
; Complete then publishes the final binary states; rollback restores the
; states that existed before commit.
;
; Include seam: vk_foundation/backend first, then this file, then the command
; and public API layers that consume these internal procedures.

#ANVIL_VK_TYPE_SEMAPHORE = 21
#ANVIL_VK_TYPE_SEMAPHORE_RESERVATION = 22

#ANVIL_VK_MAX_SEMAPHORES = 16
#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS = 4
#ANVIL_VK_MAX_SEMAPHORE_OPS = 16

#ANVIL_VK_SEM_UNSIGNALED = 0
#ANVIL_VK_SEM_SIGNALED = 1

#ANVIL_VK_SEM_OP_WAIT = 1
#ANVIL_VK_SEM_OP_SIGNAL = 2

#ANVIL_VK_SEM_TX_FREE = 0
#ANVIL_VK_SEM_TX_RESERVED = 1
#ANVIL_VK_SEM_TX_COMMITTED = 2

Structure AnvilVkSemaphoreOp Align #PB_Structure_AlignC
  semaphore.i
  operation.i
EndStructure

Global Dim avkSemLive.a[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemGen.i[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemDev.i[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemDevGen.i[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemSignaled.a[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemPendingSignal.a[#ANVIL_VK_MAX_SEMAPHORES + 1]
Global Dim avkSemPendingWait.a[#ANVIL_VK_MAX_SEMAPHORES + 1]

Global Dim avkSemTxStage.a[#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1]
Global Dim avkSemTxGen.i[#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1]
Global Dim avkSemTxDev.i[#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1]
Global Dim avkSemTxDevGen.i[#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1]
Global Dim avkSemTxCount.i[#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1]

; Fixed storage keeps a reservation alive after its caller's VkSubmitInfo
; storage has gone away.  Index zero is intentionally unused in each row.
Global Dim avkSemTxOpSlot.i[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORE_OPS + 1)]
Global Dim avkSemTxOpKind.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORE_OPS + 1)]
Global Dim avkSemTxTouched.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORES + 1)]
Global Dim avkSemTxPrior.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORES + 1)]
Global Dim avkSemTxFinal.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORES + 1)]
Global Dim avkSemTxSawWait.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORES + 1)]
Global Dim avkSemTxSawSignal.a[(#ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS + 1) * (#ANVIL_VK_MAX_SEMAPHORES + 1)]

Procedure.i avkSemTxOpIndex(t.i, n.i)
  ProcedureReturn t * (#ANVIL_VK_MAX_SEMAPHORE_OPS + 1) + n
EndProcedure

Procedure.i avkSemTxStateIndex(t.i, s.i)
  ProcedureReturn t * (#ANVIL_VK_MAX_SEMAPHORES + 1) + s
EndProcedure

Procedure.i avkSemaphoreSlot(h.i)
  Define s.i
  s = avkTokenShape(h, #ANVIL_VK_TYPE_SEMAPHORE, #ANVIL_VK_MAX_SEMAPHORES)
  If s = 0 Or avkSemLive[s] = 0 Or avkSemGen[s] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn s
EndProcedure

Procedure.i avkSemaphoreReservationSlot(h.i)
  Define t.i
  t = avkTokenShape(h, #ANVIL_VK_TYPE_SEMAPHORE_RESERVATION, #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS)
  If t = 0 Or avkSemTxStage[t] = #ANVIL_VK_SEM_TX_FREE Or avkSemTxGen[t] <> avkTokenGen(h) : ProcedureReturn 0 : EndIf
  ProcedureReturn t
EndProcedure

Procedure avkSemaphoreClearReservation(t.i)
  Define n.i
  Define x.i
  If t < 1 Or t > #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS
    ProcedureReturn
  EndIf
  n = 0
  While n <= #ANVIL_VK_MAX_SEMAPHORE_OPS
    x = avkSemTxOpIndex(t, n)
    avkSemTxOpSlot[x] = 0
    avkSemTxOpKind[x] = 0
    n = n + 1
  Wend
  n = 0
  While n <= #ANVIL_VK_MAX_SEMAPHORES
    x = avkSemTxStateIndex(t, n)
    avkSemTxTouched[x] = 0
    avkSemTxPrior[x] = 0
    avkSemTxFinal[x] = 0
    avkSemTxSawWait[x] = 0
    avkSemTxSawSignal[x] = 0
    n = n + 1
  Wend
  avkSemTxDev[t] = 0
  avkSemTxDevGen[t] = 0
  avkSemTxCount[t] = 0
  avkSemTxStage[t] = #ANVIL_VK_SEM_TX_FREE
EndProcedure

Procedure.i avkSemaphoreCreate(device.i, flags.i, *out)
  Define d.i
  Define s.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  ; VkSemaphoreCreateFlags has no core Vulkan 1.0 bits.
  If flags <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, "binary semaphore creation was given non-zero core Vulkan 1.0 flags (Anvil code -20001, invalid argument); no semaphore was created.")
  EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES And avkSemLive[s] <> 0 : s = s + 1 : Wend
  If s > #ANVIL_VK_MAX_SEMAPHORES : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkSemGen[s] = avkNextGen(avkSemGen[s])
  avkSemLive[s] = 1
  avkSemDev[s] = d
  avkSemDevGen[s] = avkTokenGen(device)
  avkSemSignaled[s] = #ANVIL_VK_SEM_UNSIGNALED
  avkSemPendingSignal[s] = 0
  avkSemPendingWait[s] = 0
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_SEMAPHORE, s, avkSemGen[s]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkSemaphoreState(device.i, semaphore.i)
  Define d.i
  Define s.i
  d = avkDevSlot(device)
  s = avkSemaphoreSlot(semaphore)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSemDev[s] <> d Or avkSemDevGen[s] <> avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkSemSignaled[s] <> 0 : ProcedureReturn #ANVIL_VK_SEM_SIGNALED : EndIf
  ProcedureReturn #ANVIL_VK_SEM_UNSIGNALED
EndProcedure

Procedure.i avkSemaphoreReservedByAny(s.i)
  Define t.i
  Define x.i
  t = 1
  While t <= #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS
    If avkSemTxStage[t] = #ANVIL_VK_SEM_TX_RESERVED
      x = avkSemTxStateIndex(t, s)
      If avkSemTxTouched[x] <> 0 : ProcedureReturn 1 : EndIf
    EndIf
    t = t + 1
  Wend
  ProcedureReturn 0
EndProcedure

; Internal adapter with a result so the future void vkDestroySemaphore
; wrapper can report a refusal through avkFault and leave the object alive.
Procedure.i avkSemaphoreDestroy(device.i, semaphore.i)
  Define d.i
  Define s.i
  If semaphore = #VK_NULL_HANDLE : ProcedureReturn #VK_SUCCESS : EndIf
  d = avkDevSlot(device)
  s = avkSemaphoreSlot(semaphore)
  If d = 0 Or s = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSemDev[s] <> d Or avkSemDevGen[s] <> avkTokenGen(device) : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0
    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "binary semaphore destruction was requested while a reservation or submitted operation still references it (Anvil code -20004, semaphore in use); the semaphore was left alive.")
  EndIf
  avkSemLive[s] = 0
  avkSemDev[s] = 0
  avkSemDevGen[s] = 0
  avkSemSignaled[s] = 0
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Reserve an ORDERED list of wait/signal operations.  A signal earlier in
; the list may satisfy a later wait, which is how a future adapter can model
; several VkSubmitInfo batches in queue order.  A wait never guesses that a
; future signal will arrive.  One wait and one signal for the same semaphore
; are allowed when their order is legal; repeating either role is refused.
;
; All validation writes only private reservation staging.  Every failure
; clears that staging and leaves every externally observable semaphore bit
; unchanged.
Procedure.i avkSemaphoreReserve(device.i, count.i, *ops.AnvilVkSemaphoreOp, *out)
  Define d.i
  Define t.i
  Define i.i
  Define s.i
  Define x.i
  Define oi.i
  Define kind.i
  If *out = 0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  PokeI(*out, #VK_NULL_HANDLE)
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If count < 1 Or count > #ANVIL_VK_MAX_SEMAPHORE_OPS Or *ops = 0
    ProcedureReturn #ANVIL_VK_ERR_ARGS
  EndIf
  t = 1
  While t <= #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS And avkSemTxStage[t] <> #ANVIL_VK_SEM_TX_FREE : t = t + 1 : Wend
  If t > #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS : ProcedureReturn #VK_ERROR_TOO_MANY_OBJECTS : EndIf
  avkSemaphoreClearReservation(t)
  avkSemTxDev[t] = d
  avkSemTxDevGen[t] = avkTokenGen(device)
  avkSemTxCount[t] = count

  i = 0
  While i < count
    s = avkSemaphoreSlot(PeekI(*ops + (i * SizeOf(AnvilVkSemaphoreOp))))
    kind = PeekI(*ops + (i * SizeOf(AnvilVkSemaphoreOp)) + OffsetOf(AnvilVkSemaphoreOp\operation))
    If s = 0
      avkSemaphoreClearReservation(t)
      ProcedureReturn #ANVIL_VK_ERR_HANDLE
    EndIf
    If avkSemDev[s] <> d Or avkSemDevGen[s] <> avkTokenGen(device)
      avkSemaphoreClearReservation(t)
      ProcedureReturn #ANVIL_VK_ERR_OWNER
    EndIf
    ; Exactly one reservation may own a payload. This also prevents two
    ; independently validated batches from both committing against the same
    ; old binary state.
    If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0 Or avkSemaphoreReservedByAny(s) <> 0
      avkSemaphoreClearReservation(t)
      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "a binary semaphore operation was reserved while earlier submitted work still owns that semaphore (Anvil code -20004, semaphore pending); the whole reservation was refused.")
    EndIf
    x = avkSemTxStateIndex(t, s)
    If avkSemTxTouched[x] = 0
      avkSemTxTouched[x] = 1
      avkSemTxPrior[x] = avkSemSignaled[s]
      avkSemTxFinal[x] = avkSemSignaled[s]
    EndIf
    If kind = #ANVIL_VK_SEM_OP_SIGNAL
      If avkSemTxSawSignal[x] <> 0 Or avkSemTxFinal[x] <> #ANVIL_VK_SEM_UNSIGNALED
        avkSemaphoreClearReservation(t)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "an ordered binary semaphore reservation would signal one payload twice or signal it while already signaled (Anvil code -20004, illegal signal); no operation was reserved.")
      EndIf
      avkSemTxSawSignal[x] = 1
      avkSemTxFinal[x] = #ANVIL_VK_SEM_SIGNALED
    ElseIf kind = #ANVIL_VK_SEM_OP_WAIT
      If avkSemTxSawWait[x] <> 0 Or avkSemTxFinal[x] <> #ANVIL_VK_SEM_SIGNALED
        avkSemaphoreClearReservation(t)
        ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, "an ordered binary semaphore reservation has a duplicate wait or a wait with no earlier signal to consume (Anvil code -20004, unsatisfied wait); no operation was reserved.")
      EndIf
      avkSemTxSawWait[x] = 1
      avkSemTxFinal[x] = #ANVIL_VK_SEM_UNSIGNALED
    Else
      avkSemaphoreClearReservation(t)
      ProcedureReturn #ANVIL_VK_ERR_ARGS
    EndIf
    oi = avkSemTxOpIndex(t, i + 1)
    avkSemTxOpSlot[oi] = s
    avkSemTxOpKind[oi] = kind
    i = i + 1
  Wend

  avkSemTxGen[t] = avkNextGen(avkSemTxGen[t])
  avkSemTxStage[t] = #ANVIL_VK_SEM_TX_RESERVED
  PokeI(*out, avkToken(#ANVIL_VK_TYPE_SEMAPHORE_RESERVATION, t, avkSemTxGen[t]))
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Publish pending references only after every staged object is known good.
Procedure.i avkSemaphoreCommit(reservation.i)
  Define t.i
  Define s.i
  Define x.i
  t = avkSemaphoreReservationSlot(reservation)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSemTxStage[t] <> #ANVIL_VK_SEM_TX_RESERVED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkSemTxDev[t] < 1 Or avkSemTxDev[t] > #ANVIL_VK_MAX_DEVICES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkDevLive[avkSemTxDev[t]] = 0 Or avkDevGen[avkSemTxDev[t]] <> avkSemTxDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES
    x = avkSemTxStateIndex(t, s)
    If avkSemTxTouched[x] <> 0
      ; Reserve blocked destruction, so this is a consistency refusal rather
      ; than permission to partially commit a damaged transaction.
      If avkSemLive[s] = 0 Or avkSemDev[s] <> avkSemTxDev[t] Or avkSemDevGen[s] <> avkSemTxDevGen[t]
        ProcedureReturn #ANVIL_VK_ERR_STATE
      EndIf
    EndIf
    s = s + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES
    x = avkSemTxStateIndex(t, s)
    If avkSemTxTouched[x] <> 0
      avkSemSignaled[s] = #ANVIL_VK_SEM_UNSIGNALED
      avkSemPendingSignal[s] = avkSemTxSawSignal[x]
      avkSemPendingWait[s] = avkSemTxSawWait[x]
    EndIf
    s = s + 1
  Wend
  avkSemTxStage[t] = #ANVIL_VK_SEM_TX_COMMITTED
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Called only when the associated immediate or polled submission has really
; completed.  A signal followed by a wait finishes unsignaled; a final
; unconsumed signal finishes signaled.
Procedure.i avkSemaphoreComplete(reservation.i)
  Define t.i
  Define s.i
  Define x.i
  t = avkSemaphoreReservationSlot(reservation)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSemTxStage[t] <> #ANVIL_VK_SEM_TX_COMMITTED : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf
  If avkSemTxDev[t] < 1 Or avkSemTxDev[t] > #ANVIL_VK_MAX_DEVICES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkDevLive[avkSemTxDev[t]] = 0 Or avkDevGen[avkSemTxDev[t]] <> avkSemTxDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES
    x = avkSemTxStateIndex(t, s)
    If avkSemTxTouched[x] <> 0
      avkSemSignaled[s] = avkSemTxFinal[x]
      avkSemPendingSignal[s] = 0
      avkSemPendingWait[s] = 0
    EndIf
    s = s + 1
  Wend
  avkSemaphoreClearReservation(t)
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Submission setup or execution failed.  Reserved-only transactions have
; changed no semaphore.  Committed transactions restore every prior bit and
; release every pending reference as one operation.
Procedure.i avkSemaphoreRollback(reservation.i)
  Define t.i
  Define s.i
  Define x.i
  t = avkSemaphoreReservationSlot(reservation)
  If t = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  If avkSemTxDev[t] < 1 Or avkSemTxDev[t] > #ANVIL_VK_MAX_DEVICES : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkDevLive[avkSemTxDev[t]] = 0 Or avkDevGen[avkSemTxDev[t]] <> avkSemTxDevGen[t] : ProcedureReturn #ANVIL_VK_ERR_OWNER : EndIf
  If avkSemTxStage[t] = #ANVIL_VK_SEM_TX_COMMITTED
    s = 1
    While s <= #ANVIL_VK_MAX_SEMAPHORES
      x = avkSemTxStateIndex(t, s)
      If avkSemTxTouched[x] <> 0
        avkSemSignaled[s] = avkSemTxPrior[x]
        avkSemPendingSignal[s] = 0
        avkSemPendingWait[s] = 0
      EndIf
      s = s + 1
    Wend
  EndIf
  avkSemaphoreClearReservation(t)
  ProcedureReturn #VK_SUCCESS
EndProcedure

; Device teardown helper.  Vulkan requires device work to be quiescent
; before owned objects disappear.  This scan is atomic: one pending or
; reserved semaphore leaves every object live; otherwise all are retired.
Procedure.i avkSemaphoreResetDevice(device.i)
  Define d.i
  Define s.i
  Define t.i
  d = avkDevSlot(device)
  If d = 0 : ProcedureReturn #ANVIL_VK_ERR_HANDLE : EndIf
  t = 1
  While t <= #ANVIL_VK_MAX_SEMAPHORE_RESERVATIONS
    If avkSemTxStage[t] <> #ANVIL_VK_SEM_TX_FREE And avkSemTxDev[t] = d And avkSemTxDevGen[t] = avkTokenGen(device)
      ProcedureReturn #ANVIL_VK_ERR_STATE
    EndIf
    t = t + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES
    If avkSemLive[s] <> 0 And avkSemDev[s] = d And avkSemDevGen[s] = avkTokenGen(device)
      If avkSemPendingSignal[s] <> 0 Or avkSemPendingWait[s] <> 0
        ProcedureReturn #ANVIL_VK_ERR_STATE
      EndIf
    EndIf
    s = s + 1
  Wend
  s = 1
  While s <= #ANVIL_VK_MAX_SEMAPHORES
    If avkSemLive[s] <> 0 And avkSemDev[s] = d And avkSemDevGen[s] = avkTokenGen(device)
      avkSemLive[s] = 0
      avkSemDev[s] = 0
      avkSemDevGen[s] = 0
      avkSemSignaled[s] = 0
    EndIf
    s = s + 1
  Wend
  ProcedureReturn #VK_SUCCESS
EndProcedure
