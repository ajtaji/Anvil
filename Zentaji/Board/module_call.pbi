; A separately loaded driver's lifecycle entries use the normal Zentaji
; register ABI. Tail transfer preserves the original caller's link and stack.
Procedure.i ZentajiModuleUnavailable(entry.i,arg1.i,arg2.i)
 ProcedureReturn #SVC_ESTATE
EndProcedure
Global *zenModuleGate=@ZentajiModuleUnavailable
Procedure.i ZentajiModuleGateInit()
 Protected gate.i
 If zenMemoryContext<HwMonLo()+48 Or PeekQ(zenMemoryContext-48)<>$3130444F4D4E455A : ProcedureReturn 0 : EndIf
 gate=PeekQ(zenMemoryContext-40)
 If gate<ZentajiPayloadVectors()+4096 Or gate>=zenMemoryContext-48 Or (gate&7)<>0 : ProcedureReturn 0 : EndIf
 *zenModuleGate=gate
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiModuleCall(entry.i,arg1.i,arg2.i)
 ProcedureReturn CallFunctionFast(zenModuleGate,entry,arg1,arg2)
EndProcedure
Procedure.i HwModuleEntryOk(owner.i,entry.i)
 Protected base.i
 If owner<0 Or owner>=gModRecordCount : ProcedureReturn 0 : EndIf
 base=gModRecBase[owner]
 ProcedureReturn Bool((entry&7)=0 And entry>=base And entry<=base+gModRecImageBytes[owner]-8)
EndProcedure
Procedure.i HwModuleLifecycleCall(owner.i,entry.i,services.i,token.i)
 If HwModuleEntryOk(owner,entry)=0 : ProcedureReturn #SVC_ESTATE : EndIf
 ProcedureReturn ZentajiModuleCall(entry,services,token)
EndProcedure
Procedure.i HwModuleBindingOk(entry.i)
 ProcedureReturn Bool((entry&7)=0 And entry>=HwMonLo() And entry<=HwMonHi()-7)
EndProcedure
Procedure HwModuleNotify(entry.i)
 If HwModuleBindingOk(entry)<>0 : ZentajiModuleCall(entry,0,0) : EndIf
EndProcedure
