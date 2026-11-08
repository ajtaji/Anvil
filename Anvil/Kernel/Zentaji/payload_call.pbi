; Zentaji CPU payload call boundary. Select explicitly; no ARM register ABI.
; This is the CPU mechanism, not board device quiesce/recovery or a run command.
; The board must own all DMA/devices before calling and revalidate them afterward.
; Same-supervisor payloads are trusted code, not an isolation/security boundary.
; Include the selected memory HAL and shared memrange policy before this file.
; The explicit context must match that live memory view; no board globals are read.
;
; Entry: core0, STATUS=0, PROT=0, validated owned EVEC, entry in payload RAM,
; caller-supplied 16-byte-aligned stack with at least 16KB of payload-owned RAM.
; r1=argument; r2..r15=0; r255=stack top; r254=return link; FPCR/FPSR=0.
; Other volatile registers are unspecified. No architecture ID is invented here.
; Return: r1 result, monitor SP/link/r128..r253/v32..v63/masks/FP state restored,
; owned EVEC restored with IE masked. Payload stack contents are not unwound.
; A changed protection/busy exception context fail-stops before reading saved
; RAM or using either stack. No automatic trap recovery or privilege transition.
; Payloads must return in supervisor context with protection disabled and IRQs
; masked; restoring a vector base cannot recover from an earlier foreign IRQ.
;
; The standalone startup.zen trampoline owns the assembly mechanism and saved
; state; the version2 context publishes its address. No naked-leaf call rule is
; bypassed. Version1 has no call boundary and reports unavailable.
#ZEN_PAYLOAD_E_CONTEXT=1
#ZEN_PAYLOAD_E_ACTIVE=2
#ZEN_PAYLOAD_E_ENTRY=3
#ZEN_PAYLOAD_E_STACK=4
#ZEN_PAYLOAD_E_UNAVAILABLE=5
Global zenPayloadActive.i
Global zenPayloadError.i
Global zenPayloadResult.q

ProcedureNaked.i ZentajiPayloadProtection()
 ASM
  MFCR r1,PROT
  JR r254
 EndASM
EndProcedure
ProcedureNaked.i ZentajiPayloadVectors()
 ASM
  MFCR r1,EVEC
  JR r254
 EndASM
EndProcedure

Procedure.q ZentajiPayloadUnavailable(entry.i,argument.i,stack.i)
 ProcedureReturn 0
EndProcedure
Global *zenPayloadCaller=@ZentajiPayloadUnavailable

Procedure.i ZentajiPayloadFail(code.i)
 zenPayloadError=code
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiPayloadLastError() : ProcedureReturn zenPayloadError : EndProcedure
Procedure.q ZentajiPayloadReturnValue() : ProcedureReturn zenPayloadResult : EndProcedure

Procedure.i ZentajiPayloadEnter(context.i,entry.i,argument.i,stack.i,stackBytes.i)
 ; Never replace an active call's saved context. No staged argument survives.
 If zenPayloadActive<>0 : ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_ACTIVE) : EndIf
 zenPayloadResult=0
 If ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 Or ZentajiPayloadProtection()<>0
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_CONTEXT)
 EndIf
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_CONTEXT) : EndIf
 If HwMonLo()<>PeekQ(context+#ZEN_BOOT_LOAD) Or HwMonBytes()<>PeekQ(context+#ZEN_BOOT_IMAGE_END)-HwMonLo() Or HwMonStack()<>PeekQ(context+#ZEN_BOOT_STACK_TOP)
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_CONTEXT)
 EndIf
 If ZentajiPayloadVectors()<>PeekQ(context+#ZEN_BOOT_VECTORS)
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_CONTEXT)
 EndIf
 If entry<0 Or (entry&7)<>0 Or entry>$7FFFFFFFFFFFFFFF-7
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_ENTRY)
 EndIf
 If InPayload(entry,entry+7)=0 : ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_ENTRY) : EndIf
 If stack<=0 Or (stack&15)<>0 Or stackBytes<16384 Or (stackBytes&15)<>0 Or stackBytes>stack
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_STACK)
 EndIf
 If InPayload(stack-stackBytes,stack-1)=0 Or (entry>=stack-stackBytes And entry<stack)
  ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_STACK)
 EndIf
 If PeekQ(context+8)<>2 : ProcedureReturn ZentajiPayloadFail(#ZEN_PAYLOAD_E_UNAVAILABLE) : EndIf
 *zenPayloadCaller=PeekQ(context+#ZEN_BOOT_PAYLOAD_CALL)
 zenPayloadActive=1
 zenPayloadResult=zenPayloadCaller(entry,argument,stack)
 *zenPayloadCaller=@ZentajiPayloadUnavailable
 zenPayloadActive=0 : zenPayloadError=0
 ProcedureReturn 1
EndProcedure
