; Zentaji version1 RTC: reading SECONDS latches NANOS. No writes to RTC,
; alarm, timezone or NVRAM. The service returns that coherent UTC sample;
; a manually set software wall clock is not promoted to a hardware source.
#ZEN_RTC=$FFFF000000060000
Global zenRtcEpoch.q,zenRtcNanos.q
Procedure.i ZentajiClockSampleValid(epoch.q,nanos.q)
 If epoch<#WALLCLOCK_EPOCH_MIN Or epoch>=#WALLCLOCK_EPOCH_MAX : ProcedureReturn 0 : EndIf
 If nanos<0 Or nanos>=1000000000 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiClockRead()
 Protected epoch.q,nanos.q
 zenRtcEpoch=0 : zenRtcNanos=0
 If ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 Or (PeekQ(#ZEN_RTC)&$FFFF)<>7 : ProcedureReturn 0 : EndIf
 epoch=PeekQ(#ZEN_RTC+$40) : nanos=PeekQ(#ZEN_RTC+$48)
 If ZentajiClockSampleValid(epoch,nanos)=0 : ProcedureReturn 0 : EndIf
 zenRtcEpoch=epoch : zenRtcNanos=nanos
 ProcedureReturn 1
EndProcedure
Procedure.i ZentajiClockSeed()
 ; Called after TimeBoot so its restored floor cannot replace the RTC seed.
 ; The existing wall-clock anchor has second precision, as on the Pi5 RTC.
 ; UTC services below read latched hardware subseconds instead of that anchor.
 If ZentajiClockRead()=0 : ProcedureReturn 0 : EndIf
 If WallClockRtcAdmit(1)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn WallClockSet(zenRtcEpoch,#WALLCLOCK_SRC_RTC)
EndProcedure
Procedure.i HwClockProvenance()
 If ZentajiClockRead()=0 : ProcedureReturn #HW_CLK_UNSET : EndIf
 ProcedureReturn #HW_CLK_RTC
EndProcedure
Procedure.i ZentajiClockRecord(*out,epoch.q,nanos.q)
 Protected i.i
 If *out=0 : ProcedureReturn 0 : EndIf
 For i=0 To 27 : PokeB(*out+i,0) : Next
 If ZentajiClockSampleValid(epoch,nanos)=0 Or WallClockToCivil(epoch)=0 : ProcedureReturn 0 : EndIf
 PokeL(*out,WallClockYear()) : PokeL(*out+4,WallClockMonth()) : PokeL(*out+8,WallClockDay())
 PokeL(*out+12,WallClockHour()) : PokeL(*out+16,WallClockMinute()) : PokeL(*out+20,WallClockSecond())
 PokeL(*out+24,nanos/1000000)
 ProcedureReturn 1
EndProcedure
Procedure.i HwClockUtc(*out)
 If *out=0 : ProcedureReturn #HW_CLK_UNSET : EndIf
 If ZentajiClockRead()=0
  ZentajiClockRecord(*out,0,0) : ProcedureReturn #HW_CLK_UNSET
 EndIf
 If ZentajiClockRecord(*out,zenRtcEpoch,zenRtcNanos)=0 : ProcedureReturn #HW_CLK_UNSET : EndIf
 ProcedureReturn #HW_CLK_RTC
EndProcedure
; No measured oscillator bound or authoritative GNSS sync is invented.
Procedure.i HwClockUncertaintyMs() : ProcedureReturn -1 : EndProcedure
Procedure.i HwClockLastSyncTicks() : ProcedureReturn -1 : EndProcedure
Procedure.i HwClockNotifyGnss(*fix) : ProcedureReturn 0 : EndProcedure
