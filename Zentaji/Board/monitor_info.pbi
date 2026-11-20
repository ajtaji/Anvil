; Host-independent command formatting comes from the Anvil identity and monitor
; libraries. Machine characteristics come from the ROM's validated handoff.
Procedure ZentajiCmdInfo()
 Protected table.i=PeekQ(zenMemoryContext+#ZEN_BOOT_TABLE)
 SkipSpace()
 If gLine[gPos]<>0 : PrintN("!! info takes no arguments.") : ProcedureReturn : EndIf
 PutIdLine() : PutProcessorLine()
 Print("RAM bytes: ") : PrintDec(zenMemoryRam) : PrintNl()
 Print("CPU cores: ") : PrintDec(PeekU(table+32)) : PrintNl()
 Print("Current core: ") : PrintDec(ZenCpuCoreId()) : PrintNl()
 Print("Device table entries: ") : PrintDec(PeekL(table+16)) : PrintNl()
 Print("Boot source: ")
 Select PeekQ(zenMemoryContext+#ZEN_BOOT_SOURCE)
  Case 0 : PrintN("host file")
  Case 1 : Print("disk ") : PrintDec(PeekA(table+36)) : PrintNl()
  Case 2 : PrintN("direct load")
 EndSelect
 HwIdSayConsole()
EndProcedure

Procedure ZentajiCmdClock()
 SkipSpace()
 If gLine[gPos]<>0
  PrintN("!! TIME_HZ is read-only. The guest cannot set the machine clock rate.")
  ProcedureReturn
 EndIf
 Print("Nominal machine clock: ") : PrintDec(TickHz()) : PrintN(" Hz")
 Print("TIME ticks: ") : PrintDec(Ticks()) : PrintNl()
EndProcedure
