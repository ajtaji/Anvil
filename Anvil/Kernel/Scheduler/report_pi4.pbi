; Include after Pi4 exception_support.pi4 and preempt_a64.pbi.
; Reuse bounded raw UART formatting only; never the shared display/network log.
Procedure ApPi4FatalReport()
  HwExceptionText("ANVIL SCHEDULER STOP (1): execution stopped; check this build's symbols.")
  HwExceptionByte(13) : HwExceptionByte(10)
  HwExceptionText("Raw ELR/ESR may predate the stop; no validated fault frame. EL=")
  HwExceptionHex(ap_fatal_record[0])
  HwExceptionText(" ELR=") : HwExceptionHex(ap_fatal_record[2])
  HwExceptionText(" ESR=") : HwExceptionHex(ap_fatal_record[1])
  HwExceptionText(" FAR=") : HwExceptionHex(ap_fatal_record[3])
  HwExceptionByte(13) : HwExceptionByte(10)
  HwExceptionText("Observed SP=") : HwExceptionHex(ap_fatal_record[4])
  HwExceptionText(" task=") : HwExceptionHex(ap_fatal_record[5])
  HwExceptionText(" in IRQ=") : HwExceptionHex(ap_fatal_record[6])
  HwExceptionByte(13) : HwExceptionByte(10)
EndProcedure
