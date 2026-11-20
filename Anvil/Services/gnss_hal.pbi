; Shared receiver selection and payload HAL for boards without a PPS input.
Procedure.i GnssPreferredSource()
  If UsbSerialAvailable()=0 Or SettingsKeySame(SettingsGet("gnss.source"),"network")<>0
    ProcedureReturn #GNSS_SRC_NETWORK
  EndIf
  ProcedureReturn #GNSS_SRC_USB
EndProcedure
Procedure.i HwGnssUp()
  If GnssSource()<>#GNSS_SRC_NONE : ProcedureReturn 1 : EndIf
  ProcedureReturn GnssOpen(GnssPreferredSource())
EndProcedure

Procedure.i HwGnssPoll()
  ProcedureReturn GnssPump()
EndProcedure

Procedure.i HwGnssFix(*fix)
  ProcedureReturn GnssFix(*fix)
EndProcedure

Procedure.i HwGnssAgeMs()
  ProcedureReturn GnssAgeMs()
EndProcedure

Procedure.i HwGnssPpsTicks()
  ProcedureReturn -1
EndProcedure

Procedure.i HwGnssSatsUsed()
  ProcedureReturn GnssSatsUsed()
EndProcedure

Procedure.i HwGnssErrText()
  ProcedureReturn GnssWhy()
EndProcedure
