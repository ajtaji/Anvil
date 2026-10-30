; Optional diagnostics. The caller supplies a microsecond clock; no hardware
; or output dependency is introduced into the standalone filesystem.
#EXFAT_PROFILE_PHASES = 7
Global *exfatprof_clock
Global Dim exfatprof_count.i[#EXFAT_PROFILE_PHASES]
Global Dim exfatprof_total.i[#EXFAT_PROFILE_PHASES]
Global Dim exfatprof_max.i[#EXFAT_PROFILE_PHASES]
Procedure ExFatProfileSetClock(clock.i)
 Define i.i
 If clock=exfatprof_clock : ProcedureReturn : EndIf
 exfatprof_clock=clock
 For i=0 To #EXFAT_PROFILE_PHASES-1
  exfatprof_count[i]=0 : exfatprof_total[i]=0 : exfatprof_max[i]=0
 Next
EndProcedure
Procedure.i ExFatProfileBegin()
 If exfatprof_clock=0 : ProcedureReturn -1 : EndIf
 ProcedureReturn exfatprof_clock()
EndProcedure
Procedure ExFatProfileEnd(phase.i,started.i)
 Define elapsed.i
 If exfatprof_clock=0 Or started<0 Or phase<0 Or phase>=#EXFAT_PROFILE_PHASES : ProcedureReturn : EndIf
 elapsed=exfatprof_clock()-started
 If elapsed<0 : ProcedureReturn : EndIf
 exfatprof_count[phase]=exfatprof_count[phase]+1
 exfatprof_total[phase]=exfatprof_total[phase]+elapsed
 If elapsed>exfatprof_max[phase] : exfatprof_max[phase]=elapsed : EndIf
EndProcedure
Procedure.i ExFatProfileValue(phase.i,field.i)
 If phase<0 Or phase>=#EXFAT_PROFILE_PHASES : ProcedureReturn -1 : EndIf
 If field=0 : ProcedureReturn exfatprof_count[phase] : EndIf
 If field=1 : ProcedureReturn exfatprof_total[phase] : EndIf
 If field=2 : ProcedureReturn exfatprof_max[phase] : EndIf
 ProcedureReturn -1
EndProcedure
