; Live Anvil memory layout from its validated Zentaji startup context.
; Include boot_context, console, HAL and format before the shared range policy.
; RAM between the page-rounded image end and owned stack is the payload window,
; less an optional boot-time reservation for native text cells at its high end.
; The low prefix, complete image/BSS/vectors, stack and ROM's top 1MB stay owned.
XIncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
Global zenMemoryContext.i
Global zenMemoryRam.i
Global zenMemoryFirst.i
Global zenMemoryLast.i
Global zenMemoryPayload.i
Global zenMemoryStackBottom.i
Global zenMemoryStackTop.i
Global zenMemoryAddrLo.i
Global zenMemoryAddrHi.i
Global zenMemoryAddrWhy.i
Global zenMemoryTextBase.i,zenMemoryTextBytes.i,zenMemoryTextTried.i

Procedure.i ZentajiMemoryBind(context.i)
 Protected last.i,nextPage.i,bottom.i
 If ZentajiBootContextValid(context)<>1 : ProcedureReturn 0 : EndIf
 If zenMemoryContext<>0 : ProcedureReturn Bool(zenMemoryContext=context) : EndIf
 last=PeekQ(context+#ZEN_BOOT_IMAGE_END)
 bottom=PeekQ(context+#ZEN_BOOT_STACK_BOTTOM)
 If last>$7FFFFFFFFFFFFFFF-4095 : ProcedureReturn 0 : EndIf
 nextPage=(last+4095)&-4096
 If nextPage>=bottom Or bottom-nextPage<4096 : ProcedureReturn 0 : EndIf
 zenMemoryRam=PeekQ(context+#ZEN_BOOT_RAM)
 zenMemoryFirst=PeekQ(context+#ZEN_BOOT_LOAD) : zenMemoryLast=last
 zenMemoryPayload=nextPage
 zenMemoryStackBottom=bottom : zenMemoryStackTop=PeekQ(context+#ZEN_BOOT_STACK_TOP)
 zenMemoryContext=context
 ProcedureReturn 1
EndProcedure
Procedure.i HwMonLo() : ProcedureReturn zenMemoryFirst : EndProcedure
Procedure.i HwMonHi() : ProcedureReturn zenMemoryLast-1 : EndProcedure
Procedure.i HwMonBytes() : ProcedureReturn zenMemoryLast-zenMemoryFirst : EndProcedure
Procedure.i HwMonStack() : ProcedureReturn zenMemoryStackTop : EndProcedure
Procedure.i HwMonRegions()
 If zenMemoryContext=0 : ProcedureReturn 0 : EndIf
 If zenMemoryTextBase<>0 : ProcedureReturn 4 : EndIf
 ProcedureReturn 3
EndProcedure
Procedure.i HwMonRegionLo(index.i)
 Select index
  Case 0 : ProcedureReturn 0
  Case 1 : ProcedureReturn zenMemoryStackBottom
  Case 2 : ProcedureReturn zenMemoryStackTop
  Case 3 : If zenMemoryTextBase<>0 : ProcedureReturn zenMemoryTextBase : EndIf
 EndSelect
 ProcedureReturn -1
EndProcedure
Procedure.i HwMonRegionHi(index.i)
 Select index
  Case 0 : ProcedureReturn zenMemoryPayload-1
  Case 1 : ProcedureReturn zenMemoryStackTop-1
  Case 2 : ProcedureReturn zenMemoryRam-1
  Case 3 : If zenMemoryTextBase<>0 : ProcedureReturn zenMemoryStackBottom-1 : EndIf
 EndSelect
 ProcedureReturn -1
EndProcedure
Procedure HwMonRegionSay(index.i)
 Select index
  Case 0 : Print("monitor image, data, vectors and low reserved RAM")
  Case 1 : Print("Anvil supervisor stack")
  Case 2 : Print("ROM workspace and loader stack")
  Case 3 : Print("native text cells (all configured modes and fonts)")
 EndSelect
EndProcedure
Procedure.i HwPayWindows()
 If zenMemoryContext=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i HwPayLo(index.i)
 If zenMemoryContext=0 Or index<>0 : ProcedureReturn -1 : EndIf
 ProcedureReturn zenMemoryPayload
EndProcedure
Procedure.i HwPayHi(index.i)
 If zenMemoryContext=0 Or index<>0 : ProcedureReturn -1 : EndIf
 If zenMemoryTextBase<>0 : ProcedureReturn zenMemoryTextBase-1 : EndIf
 ProcedureReturn zenMemoryStackBottom-1
EndProcedure
Procedure.i HwStageAddr()
 If zenMemoryContext=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn zenMemoryPayload
EndProcedure

; Called once, during boot before settings, staging or payload admission. Seal
; even a failed attempt: the payload map never changes under an existing user.
Procedure.i ZentajiMemoryTextInit(table.i)
 Protected bytes.i,base.i
 If zenMemoryContext=0 Or zenMemoryTextTried<>0 : ProcedureReturn 0 : EndIf
 zenMemoryTextTried=1
 bytes=ZentajiTextRequired(table)
 If bytes<4 Or bytes>$7FFFFFFFFFFFFFFF-4095 : ProcedureReturn 0 : EndIf
 bytes=(bytes+4095)&-4096
 If bytes>zenMemoryStackBottom-zenMemoryPayload-4096 : ProcedureReturn 0 : EndIf
 base=zenMemoryStackBottom-bytes
 zenMemoryTextBase=base : zenMemoryTextBytes=bytes
 If ZentajiTextStart(base,bytes)=0
  zenMemoryTextBase=0 : zenMemoryTextBytes=0
  ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure

; Raw memory inspection is safe throughout fitted RAM, including monitor data;
; write/load ownership is the shared HitsMonitor/InPayload policy's decision.
; MMIO has side effects and is not admitted as ordinary staging RAM.
Procedure.i HwAddrCheck(lo.i,hi.i,forWrite.i)
 zenMemoryAddrLo=lo : zenMemoryAddrHi=hi
 If zenMemoryContext=0
  zenMemoryAddrWhy="the Zentaji memory layout has not been bound to a validated startup context"
  ProcedureReturn #HW_ADDR_UNKNOWN
 EndIf
 If (forWrite<>0 And forWrite<>1) Or lo<0 Or hi<lo
  zenMemoryAddrWhy="this range is not an admitted positive RAM interval; device and ROM apertures require deliberate inspection"
  ProcedureReturn #HW_ADDR_UNKNOWN
 EndIf
 If lo<zenMemoryRam And hi<zenMemoryRam : ProcedureReturn #HW_ADDR_SAFE : EndIf
 zenMemoryAddrLo=zenMemoryRam : zenMemoryAddrHi=$7FFFFFFFFFFFFFFF
 zenMemoryAddrWhy="this address is beyond the RAM fitted to the Zentaji machine"
 ProcedureReturn #HW_ADDR_ABSENT
EndProcedure
Procedure.i HwAddrReason() : ProcedureReturn zenMemoryAddrWhy : EndProcedure
Procedure.i HwAddrBlockLo() : ProcedureReturn zenMemoryAddrLo : EndProcedure
Procedure.i HwAddrBlockHi() : ProcedureReturn zenMemoryAddrHi : EndProcedure
