; Inspect the fitted device or the ROM descriptor that contains the first
; address. Refuse a span crossing its end before the first register read.
Procedure.i ZentajiMmioRange(a.i,bytes.i)
 Protected table.i=PeekQ(zenMemoryContext+#ZEN_BOOT_TABLE)
 Protected total.i=PeekL(table+12),entries.i=PeekL(table+16),i.i,p.i,base.i,span.i
 If total<64 Or total>65536 Or entries<1 Or entries>(total-64)/64 : ProcedureReturn 0 : EndIf
 If a>=table And a<table+total : ProcedureReturn Bool(bytes<=table+total-a) : EndIf
 For i=0 To entries-1
  p=table+64+i*64 : base=PeekQ(p+8) : span=PeekQ(p+16)
  ; RAM also appears in the device table, with a nonnegative base.
  If base<0 And span=65536 And a>=base And a<base+span
   ProcedureReturn Bool(bytes<=base+span-a)
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure ZentajiCmdMmio()
 Protected a.i=ParseHex(),n.i=1,i.i
 If gParseOk=0 Or (a&7)<>0
  PrintN("!! mmio needs an eight-byte-aligned hexadecimal device address.") : ProcedureReturn
 EndIf
 SkipSpace()
 If gLine[gPos]<>0
  n=ParseHex() : SkipSpace()
  If gParseOk=0 Or n<1 Or n>64 Or gLine[gPos]<>0
   PrintN("!! mmio takes a hexadecimal count from 1 through 40 (64 registers).") : ProcedureReturn
  EndIf
 EndIf
 If ZentajiMmioRange(a,n*8)=0
  PrintN("!! the requested range is outside a fitted device or its ROM descriptor.") : ProcedureReturn
 EndIf
 For i=0 To n-1
  If OutBreak()<>0 : Break : EndIf
  PutHex16(a) : Print(": ") : PutHex16(PeekQ(a)) : PrintNl() : a=a+8
 Next
EndProcedure

Procedure ZentajiCmdBaud()
 Protected old.q=PeekQ(#ZEN_CONSOLE+$60),rate.i,started.q
 SkipSpace()
 If gLine[gPos]=0
  Print("UART0 baud: ") : PrintDec(old) : PrintN(" (0 selects unpaced TX).") : ProcedureReturn
 EndIf
 rate=ParseDec() : SkipSpace()
 If gParseOk=0 Or gLine[gPos]<>0 Or rate<0 Or (rate<>0 And rate<1200) Or rate>TickHz()
  PrintN("!! baud takes 0 for unpaced TX or a rate from 1200 through the machine timebase.") : ProcedureReturn
 EndIf
 If rate=old : PrintN("UART0 is already at that rate.") : ProcedureReturn : EndIf
 PrintN("Changing UART0 baud. Press Enter on UART0 within eight seconds to keep it.")
 If ZentajiConsoleDrain()=0 Or UartInit(rate)=0
  PrintN("!! UART0 could not switch baud.") : ProcedureReturn
 EndIf
 started=Ticks()
 While Ticks()-started<TickHz()*8
  If UartReadReady()<>0
   If UartRead()=13 : Print("UART0 baud kept: ") : PrintDec(rate) : PrintNl() : ProcedureReturn : EndIf
  EndIf
  If HwPromptIdleReady()=0 : Break : EndIf
  HwPromptIdleWait()
 Wend
 If UartInit(old)=0 : PrintN("!! UART0 could not restore its previous rate.") : ProcedureReturn : EndIf
 Print("UART0 baud restored: ") : PrintDec(old) : PrintNl()
EndProcedure

Procedure ZentajiCmdScreen()
 Protected on.i
 SkipSpace() : gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt : SkipSpace()
 If zngUp=0 : PrintN("!! this configuration has no active graphical console.") : ProcedureReturn : EndIf
 If gLine[gPos]<>0 : PrintN("Use screen status, screen off or screen on.") : ProcedureReturn : EndIf
 If gWordLen=0 Or WordIs("status")<>0
  If zngBlanked<>0 : Print("Screen off: ") : Else : Print("Screen on: ") : EndIf
  PrintDec(zgdWidth) : Print("x") : PrintDec(zgdHeight) : PrintN(" native Vulkan") : ProcedureReturn
 EndIf
 on=Bool(WordIs("on")<>0 Or WordIs("vulkan")<>0)
 If on=0 And WordIs("off")=0 : PrintN("Use screen status, screen off or screen on.") : ProcedureReturn : EndIf
 If on<>0
  If zngBlanked<>0
   zngBlanked=0 : zngPresented=0 : ConGridMarkAll()
   If ZentajiNeonConsolePump()<>1 : PrintN("!! the native display resize could not complete.") : ProcedureReturn : EndIf
   If NeonVkChromeFramePending()=0 And zngPresented=0 : zngPaint() : EndIf
   If zngDrainFrame()<>1 Or zgdEnabled=0
    PrintN("!! the native display could not present the console.") : ProcedureReturn
   EndIf
  EndIf
  PrintN("Screen on.")
 Else
  If zngBlanked=0
   If zngDrainFrame()<>1 Or ZentajiGraphicsDisplayBlank()<>1
    PrintN("!! the native display could not be blanked.") : ProcedureReturn
   EndIf
   zngBlanked=1 : zngPresented=0
  EndIf
  PrintN("Screen off.")
 EndIf
EndProcedure

Procedure ZentajiCmdVkStat()
 SkipSpace()
 If gLine[gPos]<>0 : PrintN("!! vkstat takes no arguments.") : ProcedureReturn : EndIf
 If avkZenUp=0
  PrintN("The monitor has no active Vulkan queue.") : ProcedureReturn
 EndIf
 Print("Native Vulkan queue sequence: ") : PrintDec(avkZenQueue\sequence)
 Print(", error: ") : PrintDec(avkZenQueue\error) : Print(", lost: ") : PrintDec(avkZenQueue\lost) : PrintNl()
 Print("Display: ") : PrintDec(zgdWidth) : Print("x") : PrintDec(zgdHeight)
 Print(", buffers: ") : PrintDec(zgdBuffers) : PrintNl()
 Print("Completed presents: ") : PrintDec(zgdSequence)
 Print(", pending: ") : PrintDec(zgdPending) : Print(", displayed buffer: ") : PrintDec(zgdShown) : PrintNl()
EndProcedure
