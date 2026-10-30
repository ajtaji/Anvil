; Bounded diagnostics for the shared payload network service. Microseconds.
; Current phase totals also preserve the component breakdown of the slowest
; whole call. Nested calls contribute to their outer phase, without clobbering it.
#NET_SERVICE_PHASES = 14
Global netprof_busy.i
Global Dim netprof_count.i[#NET_SERVICE_PHASES]
Global Dim netprof_total.i[#NET_SERVICE_PHASES]
Global Dim netprof_max.i[#NET_SERVICE_PHASES]
Global Dim netprof_current.i[#NET_SERVICE_PHASES]
Global Dim netprof_worst.i[#NET_SERVICE_PHASES]
Procedure.i NetServiceProfileBegin()
 Define i.i
 If netprof_busy : ProcedureReturn 0 : EndIf
 netprof_busy=1
 For i=0 To #NET_SERVICE_PHASES-1 : netprof_current[i]=0 : Next
 ProcedureReturn 1
EndProcedure
Procedure NetServiceProfileRecord(active.i,phase.i,started.i)
 Define elapsed.i
 If active=0 Or phase<0 Or phase>=#NET_SERVICE_PHASES : ProcedureReturn : EndIf
 elapsed=HwMicros()-started
 If elapsed<0 : ProcedureReturn : EndIf
 netprof_count[phase]=netprof_count[phase]+1
 netprof_total[phase]=netprof_total[phase]+elapsed
 netprof_current[phase]=netprof_current[phase]+elapsed
 If elapsed>netprof_max[phase] : netprof_max[phase]=elapsed : EndIf
EndProcedure
Procedure NetServiceProfileEnd(active.i,started.i)
 Define i.i
 If active=0 : ProcedureReturn : EndIf
 NetServiceProfileRecord(active,0,started)
 If netprof_current[0]>=netprof_max[0]
  For i=0 To #NET_SERVICE_PHASES-1 : netprof_worst[i]=netprof_current[i] : Next
 EndIf
 netprof_busy=0
EndProcedure
