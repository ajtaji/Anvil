; Live Anvil memory layout from its validated Zentaji startup context.
; Include boot_context, console, HAL and format before the shared range policy.
; RAM between the page-rounded image end and owned stack is the payload window.
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
 ProcedureReturn 3
EndProcedure
Procedure.i HwMonRegionLo(index.i)
 Select index
  Case 0 : ProcedureReturn 0
  Case 1 : ProcedureReturn zenMemoryStackBottom
  Case 2 : ProcedureReturn zenMemoryStackTop
 EndSelect
 ProcedureReturn -1
EndProcedure
Procedure.i HwMonRegionHi(index.i)
 Select index
  Case 0 : ProcedureReturn zenMemoryPayload-1
  Case 1 : ProcedureReturn zenMemoryStackTop-1
  Case 2 : ProcedureReturn zenMemoryRam-1
 EndSelect
 ProcedureReturn -1
EndProcedure
Procedure HwMonRegionSay(index.i)
 Select index
  Case 0 : Print("monitor image, data, vectors and low reserved RAM")
  Case 1 : Print("Anvil supervisor stack")
  Case 2 : Print("ROM workspace and loader stack")
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
 ProcedureReturn zenMemoryStackBottom-1
EndProcedure
Procedure.i HwStageAddr()
 If zenMemoryContext=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn zenMemoryPayload
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
