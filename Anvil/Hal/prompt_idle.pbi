; Prompt idle hardware contract (architecture-independent).
;
; HwPromptIdleReady() -> 1 only if the current execution context can safely
; enter a bounded idle wait and its wake source has been configured/qualified.
; Return 0 when unavailable. This check does not sleep or consume input.
;
; HwPromptIdleWait() -> wait for a configured timer/event/interrupt, then return
; in the same execution context with the monitor state preserved. The backend
; owns CPU instructions, privilege checks, wake-source configuration and the
; maximum delay appropriate to its device-service deadlines. It must tolerate
; an event becoming pending between the readiness check and the wait.
;
; The shared scheduler checks queued input and software PWM before waiting;
; its caller has already admitted input and run one bounded service lane.
; Ticks()/TickHz() must remain monotonic across the wait. Only time actually
; spent in this backend call contributes to the core's idle utilization.
; A backend must never claim readiness for an unbounded wait that cannot be
; woken by the machine's timers. A machine without a qualified wait returns 0.

; HwPromptBoardService() -> one bounded step of optional board-specific work.
; It runs in service slot 3 after temperature maintenance, outside the wait.
; A board without such work supplies an empty procedure. Preserve the caller's
; state and do not block waiting for new work. Existing AArch64 compositions
; forward it to their optional gAnvilIdleHook callback.
