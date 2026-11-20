; The architecture orders data with FENCE.full and publishes new instruction
; words to the calling core with IFENCE. Neither takes an address interval.
ProcedureNaked ZentajiCodeSync()
 ASM
  FENCE.full
  FENCE.IFENCE
  JR r254
 EndASM
EndProcedure
