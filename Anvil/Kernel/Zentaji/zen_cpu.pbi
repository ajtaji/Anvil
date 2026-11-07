; Zentaji CPU access for ordinary guest libraries and architecture backends.
;
; WHAT: read machine time/core identity and control interrupt admission/sleep.
; HOW: assembly-only leaf procedures use the same r1 result/first argument and
; r254 link as compiled callers. They touch only volatile registers. There is
; no hidden frame, parameter receiver, epilogue or compiler-inserted return.
; WHY ASM: WFI and control-register access are architectural operations; a
; portable polling loop is not an equivalent implementation of CPU sleep.
; These are guest library procedures, not compiler intrinsics or host waits.
;
; Status operations and WFI require supervisor mode. IRQ disable/enable and
; SwapStatus return the previous complete STATUS word. SwapStatus writes the
; complete supplied word; callers must keep privilege/context bits valid.
; Enabling delivery requires valid exception vectors. WFI completes before
; waiting, and an enabled/routed interrupt wakes it even when STATUS.IE=0.
; The caller owns interrupt routing/deadlines and must recheck its work after
; waking. Time is the 64-bit nominal-cycle clock, not instruction work.

ProcedureNaked.q ZenCpuTime()
  ASM
    MFCR r1,TIME
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuCoreId()
  ASM
    MFCR r1,COREID
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuStatus()
  ASM
    MFCR r1,STATUS
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuSwapStatus(value.i)
  ASM
    MTCR r1,r1,STATUS
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuIrqDisable()
  ASM
    LI r16,1
    MTCR.CLEAR r1,r16,STATUS
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuIrqEnable()
  ASM
    LI r16,1
    MTCR.SET r1,r16,STATUS
    JR r254
  EndASM
EndProcedure

ProcedureNaked.i ZenCpuWait()
  ASM
    WFI
    LI r1,0
    JR r254
  EndASM
EndProcedure
