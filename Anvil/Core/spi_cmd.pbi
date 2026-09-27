; ======================================================================
;  spi_cmd.pbi - the `spi` command. Core, chip-free: it asks the board
;  whether it has SPI at all (RequireCap over #CAP_SPI) and then drives
;  the bus ENTIRELY through Anvil/Bus/spi.pbi, which sits on the HwSpi*
;  seam - the same model as i2c_cmd.pbi and gpio_cmd.pbi.
;
;  SUBCOMMANDS (bytes are HEX; chip select, mode and clock are DECIMAL,
;  the same split i2c uses - a byte is read in hex everywhere and a clock
;  rate in decimal everywhere):
;
;    spi                          the bus, its pins, what is open, and the
;                                 clock range, then this usage.
;    spi open <cs> <mode> <hz>    select a device: chip select 0 or 1,
;                                 mode 0..3 (CPOL*2 + CPHA), clock in Hz.
;                                 The achieved clock is printed - it is
;                                 never above the one asked for, and may be
;                                 below it, because the divider is even.
;    spi xfer <byte...>           ONE full-duplex transfer: the bytes go
;                                 out with the chip select held for all of
;                                 them, and the bytes that came back are
;                                 printed. A register read is one line:
;                                 `spi xfer 80 00 00` sends the address
;                                 then two dummy bytes and shows the reply.
;    spi close                    release the bus.
;
;  COMPILED ONLY WHERE #CAP_SPI = 1. The board includes this file (and the
;  dispatch arm) inside CompilerIf #CAP_SPI = 1, so a board without SPI -
;  the Pi 4 today - carries none of its bytes. The RequireCap below is
;  still the first line, so the sentence is right if a board ever
;  includes it without the capability.
; ======================================================================

EnableExplicit

#SPI_CMD_MAX = 64

Global Dim gSpiTx.a[#SPI_CMD_MAX + 1]
Global Dim gSpiRx.a[#SPI_CMD_MAX + 1]

Procedure SpiCmdSayWhy()
  Print("!! ")
  UartWriteStr(SpiWhy())
  PrintN(".")
EndProcedure

Procedure SpiCmdPin(bus.i, which.i, *label)
  Define p.i
  p = HwSpiPin(bus, which)
  Print("  ")
  UartWriteStr(*label)
  If p < 0
    PrintN(" (not wired on this board)")
  Else
    Print(" GPIO ")
    PrintDec(p)
    PrintNl()
  EndIf
EndProcedure

Procedure SpiCmdStatus(bus.i)
  Print("SPI bus ")
  PrintDec(bus)
  Print(": data pins on ")
  UartWriteStr(HwSpiPinFunc(bus))
  Print(", ")
  PrintDec(HwSpiCsCount(bus))
  PrintN(" chip selects, driven as GPIO outputs.")
  SpiCmdPin(bus, #HW_SPI_SCLK, "SCLK")
  SpiCmdPin(bus, #HW_SPI_MOSI, "MOSI")
  SpiCmdPin(bus, #HW_SPI_MISO, "MISO")
  SpiCmdPin(bus, #HW_SPI_CS0, "CS0 ")
  SpiCmdPin(bus, #HW_SPI_CS1, "CS1 ")
  Print("Clock range ")
  PrintDec(HwSpiRateMin(bus))
  Print(" to ")
  PrintDec(HwSpiRateMax(bus))
  PrintN(" Hz.")
  If SpiIsOpen() <> 0
    Print("Open: chip select ")
    PrintDec(SpiOpenCs())
    Print(", mode ")
    PrintDec(HwSpiGetMode(bus))
    Print(", ")
    PrintDec(HwSpiGetSpeed(bus))
    PrintN(" Hz.")
  Else
    PrintN("Nothing is open.")
  EndIf
EndProcedure

Procedure SpiCmdUsage()
  PrintN("spi talks to devices on this board's SPI bus. The subcommands are:")
  PrintN("  spi open <cs> <mode> <hz>   select chip select, mode 0-3 and clock")
  PrintN("  spi xfer <byte...>          one full-duplex transfer, bytes in hex")
  PrintN("  spi close                   release the bus")
  PrintN("cs, mode and hz are DECIMAL; bytes are HEX. The chip select is held")
  PrintN("for the whole of one xfer, so a command and its reply go on one line.")
EndProcedure

Procedure SpiCmdOpen(bus.i)
  Define cs.i
  Define mode.i
  Define hz.i
  cs = ParseDec()
  If gParseOk = 0
    PrintN("!! spi open needs a chip select, a mode and a clock, all decimal, for")
    PrintN("   example spi open 0 0 1000000. Nothing was done.")
    ProcedureReturn
  EndIf
  mode = ParseDec()
  If gParseOk = 0
    PrintN("!! spi open needs a mode (0 to 3) after the chip select. Nothing was done.")
    ProcedureReturn
  EndIf
  hz = ParseDec()
  If gParseOk = 0
    PrintN("!! spi open needs a clock in Hz after the mode. Nothing was done.")
    ProcedureReturn
  EndIf
  If SpiOpen(bus, cs, mode, hz) = 0
    SpiCmdSayWhy()
    PrintN("   Nothing was opened.")
    ProcedureReturn
  EndIf
  Print("Chip select ")
  PrintDec(cs)
  Print(" open in mode ")
  PrintDec(mode)
  Print(" at ")
  PrintDec(HwSpiGetSpeed(bus))
  Print(" Hz (asked for ")
  PrintDec(hz)
  PrintN(").")
EndProcedure

Procedure SpiCmdXfer()
  Define n.i
  Define b.i
  Define i.i
  n = 0
  Repeat
    SkipSpace()
    If gLine[gPos] = 0
      Break
    EndIf
    b = ParseHex()
    If gParseOk = 0 Or b < 0 Or b > $FF
      PrintN("!! every byte must be hex, 00 to ff. Nothing was sent - a partial")
      PrintN("   transfer is worse than none.")
      ProcedureReturn
    EndIf
    If n >= #SPI_CMD_MAX
      Print("!! that is more than ")
      PrintDec(#SPI_CMD_MAX)
      PrintN(" bytes for one line. Nothing was sent.")
      ProcedureReturn
    EndIf
    gSpiTx[n] = b
    n = n + 1
  ForEver
  If n = 0
    PrintN("!! spi xfer needs at least one byte to send. Nothing was sent.")
    ProcedureReturn
  EndIf
  If SpiTransfer(@gSpiTx[0], @gSpiRx[0], n) = 0
    SpiCmdSayWhy()
    ProcedureReturn
  EndIf
  Print("Sent ")
  PrintDec(n)
  Print(" byte")
  If n <> 1
    UartWrite(115)                      ; 's'
  EndIf
  PrintN(", received:")
  Print(" ")
  i = 0
  While i < n
    UartWrite(32)
    PutHex2(gSpiRx[i] & $FF)
    i = i + 1
  Wend
  PrintNl()
EndProcedure

; ----------------------------------------------------------------------
;  CmdSpi - the dispatcher. gPos is already past "spi".
; ----------------------------------------------------------------------
Procedure CmdSpi()
  Define bus.i
  If RequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn
  EndIf
  bus = HwSpiDefaultBus()
  SkipSpace()
  If gLine[gPos] = 0
    SpiCmdStatus(bus)
    SpiCmdUsage()
    ProcedureReturn
  EndIf
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("open") <> 0
    SpiCmdOpen(bus)
  ElseIf WordIs("xfer") <> 0
    SpiCmdXfer()
  ElseIf WordIs("close") <> 0
    SpiClose()
    PrintN("SPI closed; both chip selects are released (high).")
  Else
    PrintN("!! spi does not know that subcommand.")
    SpiCmdUsage()
  EndIf
EndProcedure
