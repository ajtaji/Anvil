; Shared-only public metric proof. No native renderer, lifecycle provider,
; hardware libraries or GPU execution are linked by this composition.
XIncludeFile "Anvil/Graphics/neon_frontend.pbi"
Global mmChecks.i,mmFailures.i,mmWidths.i,mmHeights.i,mmWidthRc.i,mmHeightRc.i,mmFont.i,mmTextPointer.i,mmRevision.i
Global Dim mmBits.a[16]
Global Dim mmMixed.a[8]
Global Dim mmEmpty.a[1]
Global Dim mmLong.a[4101]
Procedure MmCheck(value.i,wanted.i)
 PokeI(#MM_REPORT+64+mmChecks*16,mmChecks+1)
 PokeI(#MM_REPORT+72+mmChecks*16,value)
 mmChecks=mmChecks+1
 If value<>wanted : mmFailures=mmFailures+1 : EndIf
EndProcedure
Procedure.i MmSame(a.i,b.i) : ProcedureReturn Bool(a=b) : EndProcedure
Procedure.i MmBox(x.i,y.i,w.i,h.i,c.i) : ProcedureReturn 0 : EndProcedure
Procedure.i MmText(f.i,x.i,y.i,*s,c.i) : ProcedureReturn 0 : EndProcedure
Procedure MmScissor(x.i,y.i,w.i,h.i) : EndProcedure
Procedure MmClear() : EndProcedure
Procedure.i MmBegin() : ProcedureReturn 0 : EndProcedure
Procedure MmPoint(x.i,y.i) : EndProcedure
Procedure.i MmEnd(c.i) : ProcedureReturn 0 : EndProcedure
Procedure MmLine(x.i,y.i,a.i,b.i) : EndProcedure
Procedure.i MmInstallDraw()
 ProcedureReturn NeonDrawBackendInstall(@MmBox,@MmText,@MmText,@MmScissor,@MmClear,@MmBegin,@MmPoint,@MmEnd,@MmEnd,@MmBegin,@MmLine,@MmEnd)
EndProcedure
Procedure.i MmWidth(font.i,*s)
 mmWidths=mmWidths+1 : mmFont=font : mmTextPointer=*s : ProcedureReturn mmWidthRc
EndProcedure
Procedure.i MmHeight(font.i)
 mmHeights=mmHeights+1 : mmFont=font : ProcedureReturn mmHeightRc
EndProcedure
Procedure.i SharedTextMetricsProof()
 Define i.i
 ; @METRIC_CASES@
 ProcedureReturn mmFailures
EndProcedure
