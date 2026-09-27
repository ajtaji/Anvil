; ======================================================================
;  spi.pbi - the shared SPI layer. Chip-free: it names no chip and touches
;  no register. It sits on the HwSpi* seam (Anvil/Hal/hal.pbi) and gives
;  its callers - the `spi` command, and later the LoRa driver - three
;  verbs and one honest answer:
;
;    SpiOpen(bus, cs, mode, hz)  check every argument against what the
;                                board says it can do, then bring the bus
;                                up. 1, or 0 with SpiWhy() set.
;    SpiTransfer(*tx, *rx, n)    ONE full-duplex transfer with the open
;                                chip select held for all n bytes. Either
;                                buffer may be 0. 1, or 0 with SpiWhy().
;    SpiClose()                  release the bus and forget the session.
;    SpiWhy()                    the ADDRESS of a whole sentence saying why
;                                the last call refused - never a code the
;                                reader has to look up.
;
;  THE ARGUMENTS ARE CHECKED HERE, ONCE, FOR EVERY BOARD, before any seam
;  call - a bad mode or chip select is refused with nothing touched,
;  whatever the silicon underneath would have done with it.
;
;  #CAP_SPI GATES THE WHOLE FILE. A board with #CAP_SPI = 0 does not include
;  it (it has no HwSpi* to call), so no board without SPI carries its bytes.
;
;  Desk gate: tools/a64/spi_dw_check.py drives it over the Pi 5 backend.
; ======================================================================

EnableExplicit

#SPI_MAX_XFER = 4096               ; one transfer; the LoRa FIFO is 256

Global spi_open.i
Global spi_bus.i
Global spi_cs.i
Global spi_why.i

Procedure.i SpiWhy()
  If spi_why = 0
    ProcedureReturn "nothing has gone wrong"
  EndIf
  ProcedureReturn spi_why
EndProcedure

Procedure.i SpiIsOpen()
  ProcedureReturn spi_open
EndProcedure

Procedure.i SpiOpenBus()
  ProcedureReturn spi_bus
EndProcedure

Procedure.i SpiOpenCs()
  ProcedureReturn spi_cs
EndProcedure

Procedure.i SpiSayCode(code.i)
  Select code
    Case #HW_SPI_NOBUS
      ProcedureReturn "this board has no SPI bus with that number"
    Case #HW_SPI_ARG
      ProcedureReturn "the board refused the request as out of range, and nothing was sent"
    Case #HW_SPI_IO
      ProcedureReturn "the SPI controller did not finish the transfer in time; it was stopped and the chip select released, so check the wiring and that the device is powered"
  EndSelect
  ProcedureReturn "the board answered with a code this layer does not know, which is a backend fault"
EndProcedure

Procedure.i SpiOpen(bus.i, cs.i, mode.i, hz.i)
  Define r.i
  spi_why = 0
  If HwSpiBusValid(bus) = 0
    spi_why = "this board has no SPI bus with that number"
    ProcedureReturn 0
  EndIf
  If cs < 0 Or cs >= HwSpiCsCount(bus)
    spi_why = "that chip select does not exist on this bus; the board offers only the ones spi lists"
    ProcedureReturn 0
  EndIf
  If mode < 0 Or mode > 3
    spi_why = "SPI modes run from 0 to 3 (clock polarity times two, plus clock phase)"
    ProcedureReturn 0
  EndIf
  If hz < HwSpiRateMin(bus)
    spi_why = "that clock is slower than this bus can divide down to; spi shows the slowest it can reach"
    ProcedureReturn 0
  EndIf
  r = HwSpiUp(bus, hz, mode)
  If r <> #HW_SPI_OK
    spi_why = SpiSayCode(r)
    ProcedureReturn 0
  EndIf
  spi_open = 1
  spi_bus = bus
  spi_cs = cs
  ProcedureReturn 1
EndProcedure

Procedure.i SpiTransfer(*tx, *rx, n.i)
  Define r.i
  spi_why = 0
  If spi_open = 0
    spi_why = "no SPI device is open; open one first with its chip select, mode and clock"
    ProcedureReturn 0
  EndIf
  If n < 1 Or n > #SPI_MAX_XFER
    spi_why = "a transfer must be from 1 to 4096 bytes, and nothing was sent"
    ProcedureReturn 0
  EndIf
  r = HwSpiXfer(spi_bus, spi_cs, *tx, *rx, n)
  If r <> #HW_SPI_OK
    spi_why = SpiSayCode(r)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure SpiClose()
  If spi_open <> 0
    HwSpiDown(spi_bus)
  EndIf
  spi_open = 0
  spi_why = 0
EndProcedure
