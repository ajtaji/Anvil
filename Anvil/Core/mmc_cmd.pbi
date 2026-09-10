; ======================================================================
;  mmc_cmd.pi4 - the raw `mmc` command. Core, chip-free: it names no chip
;  and touches no register or CMDn word. It asks the board whether it has
;  a card controller at all (RequireCap over #CAP_MMC) and then works the
;  card as 512-byte blocks through the HwMmc* seam the board supplies
;  (RaspberryPi4/Board/hw_mmc.pi4 on the Pi 4, over Lib/emmc.pi4).
;
;  DISTINCT FROM `f`/`mount`/`load`/`save`. Those put a FAT filesystem
;  over a block medium and try USB first (Anvil/Core/fs_cmd.pbi over
;  RaspberryPi4/Board/storage.pi4). `mmc` is the debugger's view: no
;  filesystem, no USB, straight at the SD card's raw blocks. It shares the
;  card bring-up record (gSdUp) with storage.pi4 so the two never reset the
;  controller out from under each other - see hw_mmc.pi4's header.
;
;  SYNTAX:
;    mmc                     the same as `mmc info`
;    mmc info                capacity, block size, block count, card class
;    mmc read  <blk> <addr> [count]
;                            read count blocks (default 1) from the card,
;                            starting at block <blk>, into RAM at <addr>.
;    mmc write <blk> <addr> [count]
;                            write count blocks (default 1) FROM RAM at
;                            <addr> onto the card, starting at block <blk>.
;                            Only when the backend can write; otherwise it
;                            refuses loudly and does nothing.
;
;  ALL THREE NUMBERS ARE HEXADECIMAL, like the memory family - <blk> is a
;  block (LBA) index, <addr> is a byte address in RAM, <count> is a count
;  of blocks. A leading 0x or $ is accepted and optional.
;
;  THE RAM SIDE IS GUARDED, BOTH WAYS. read WRITES into RAM and write READS
;  from it; either way the RAM range [addr, addr + count*blocksize) is run
;  through HitsMonitor() and refused if it touches the monitor's own code
;  or variables - the same guard `w`, `fill` and `copy` use. <addr> must
;  also be 4-byte aligned, because emmc.pi4 moves blocks a 32-bit word at
;  a time and an unaligned buffer is refused (#SD_ERR_ALIGN).
;
;  NOT HARDWARE-VERIFIED. Lib/emmc.pi4 has executed on silicon but no SD
;  card has ever answered it (the bench boots from USB), so neither the
;  read nor the write path here has moved a byte to or from a real card.
;  This command is COMPILE-VERIFIED ONLY; a real transfer is owed a Pi 4
;  with a card in the slot.
; ======================================================================

; ----------------------------------------------------------------------
;  PutMmcType - the card class as a word, from the #HW_MMC_* code.
; ----------------------------------------------------------------------
Procedure PutMmcType(t.i)
  If t = #HW_MMC_SDHC
    Print("SDHC/SDXC, high capacity, block addressed")
  ElseIf t = #HW_MMC_SDSC
    Print("SDSC, standard capacity, byte addressed")
  Else
    Print("unknown")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  MmcBringUp - bring the card up and, on failure, print the honest
;  reason. Returns 1 ready, 0 not. Shared by info/read/write so the
;  bring-up message is written once.
; ----------------------------------------------------------------------
Procedure.i MmcBringUp()
  If HwMmcInfo() <> 0
    ProcedureReturn 1
  EndIf
  PrintN("!! no SD card came up, so nothing on it can be read or written. On")
  PrintN("   this board the card-detect line is not trustworthy, so the only")
  PrintN("   honest test is to try to talk to a card - and none answered. Check")
  PrintN("   that a card is seated in the slot. A card the firmware already took")
  PrintN("   to 1.8V signalling cannot be reset from here either.")
  Print("   The card slot said: ")
  ; UartWriteStr, NOT PrintN: HwMmcErrorText returns an .i POINTER and
  ; Print/PrintN would print its ADDRESS in decimal. This trap is
  ; documented all over this tree (PutClockRow, UsbDiskUp, SdErrorText).
  UartWriteStr(HwMmcErrorText())
  PrintNl()
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  MmcInfo - capacity, block size, block count, card class.
; ----------------------------------------------------------------------
Procedure MmcInfo()
  Define blocks.i
  Define bsize.i
  Define bytes.i

  If MmcBringUp() = 0
    ProcedureReturn
  EndIf

  bsize  = HwMmcBlockSize()
  blocks = HwMmcBlockCount()

  Print("card class:  ")
  PutMmcType(HwMmcType())
  PrintNl()

  Print("block size:  ")
  PrintDec(bsize)
  PrintN(" bytes")

  Print("block count: ")
  If blocks <= 0
    ; emmc.pi4 reports 0 for "the CSD did not decode", which is not an
    ; error and does not stop a read - so it is named as unknown, not
    ; reported as an empty card.
    PrintN("unknown (the card did not report a decodable capacity)")
    PrintN("capacity:    unknown")
  Else
    PrintDec(blocks)
    PrintNl()
    ; blocks * 512 fits a 64-bit .i for any real card (a 1 TB card is
    ; about 2e9 blocks, so ~1e12 bytes - far inside signed 64-bit).
    bytes = blocks * bsize
    Print("capacity:    ")
    PrintDec(bytes / (1024 * 1024))
    Print(" MB (about ")
    PrintDec(bytes / (1024 * 1024 * 1024))
    PrintN(" GB)")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  MmcParseXfer - parse the shared "<blk> <addr> [count]" tail for read
;  and write. Fills the three globals below and returns 1, or prints the
;  specific complaint and returns 0. All three numbers are hexadecimal.
;
;  Globals rather than by-reference because this language's procedures
;  take scalars by value; the pair of callers read these back immediately
;  and nothing else touches them.
; ----------------------------------------------------------------------
Global gMmcBlk.i
Global gMmcAddr.i
Global gMmcCount.i

Procedure.i MmcParseXfer(*verb)
  Define blocks.i

  ; <blk>
  SkipSpace()
  If gLine[gPos] = 0
    Print("!! mmc ")
    UartWriteStr(*verb)
    PrintN(" needs a starting block and a RAM address, both in hex,")
    PrintN("   with an optional block count after them. Nothing was done.")
    ProcedureReturn 0
  EndIf
  gMmcBlk = ParseHex()
  If gParseOk = 0
    PrintN("!! that starting block is not a hexadecimal number, so nothing was")
    Print("   done. Write it in hex, for example mmc read 0 ")
    PutAddr(HwStageAddr())
    PrintN(".")
    ProcedureReturn 0
  EndIf

  ; <addr>
  SkipSpace()
  If gLine[gPos] = 0
    Print("!! mmc ")
    UartWriteStr(*verb)
    PrintN(" also needs a RAM address in hex after the block. Nothing")
    PrintN("   was done.")
    ProcedureReturn 0
  EndIf
  gMmcAddr = ParseHex()
  If gParseOk = 0
    PrintN("!! that RAM address is not a hexadecimal number, so nothing was done.")
    ProcedureReturn 0
  EndIf

  ; [count], optional, default 1
  SkipSpace()
  If gLine[gPos] = 0
    gMmcCount = 1
  Else
    gMmcCount = ParseHex()
    If gParseOk = 0
      PrintN("!! that block count is not a hexadecimal number, so nothing was")
      PrintN("   done. Leave it out for a single block.")
      ProcedureReturn 0
    EndIf
  EndIf

  If gMmcCount <= 0
    PrintN("!! a block count of zero moves nothing, so nothing was done.")
    ProcedureReturn 0
  EndIf

  ; ADDRESS ALIGNMENT. emmc.pi4 moves each block as 32-bit words, so the
  ; buffer must be 4-byte aligned; it would refuse otherwise, but say so
  ; here with a clearer message before anything is attempted.
  If (gMmcAddr & 3) <> 0
    PrintN("!! the RAM address must be 4-byte aligned - the card is read and")
    PrintN("   written a 32-bit word at a time. Round it down to a multiple of 4")
    PrintN("   and try again. Nothing was done.")
    ProcedureReturn 0
  EndIf

  ; CARD-SIDE RANGE CHECK, only when the capacity is known. A card that
  ; did not report a decodable capacity (blocks = 0) is not range-checked
  ; here; the transfer itself will fail at the card if the block is out
  ; of range, and that failure is reported per block below.
  blocks = HwMmcBlockCount()
  If blocks > 0
    If gMmcBlk >= blocks
      Print("!! this card has blocks 0 to ")
      PrintDec(blocks - 1)
      Print(", and ")
      PrintDec(gMmcBlk)
      PrintN(" is past the end,")
      PrintN("   so nothing was done.")
      ProcedureReturn 0
    EndIf
    If gMmcBlk + gMmcCount > blocks
      Print("!! that runs off the end of the card - it has ")
      PrintDec(blocks)
      PrintN(" blocks and the")
      PrintN("   transfer would need more than that. Nothing was done.")
      ProcedureReturn 0
    EndIf
  EndIf

  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  MmcGuardRam - refuse a RAM range that touches the monitor, the same
;  guard w/fill/copy use. Returns 1 if the range is clear, 0 (with the
;  refusal printed) if it is not. bytes is the whole transfer length.
; ----------------------------------------------------------------------
Procedure.i MmcGuardRam(addr.i, bytes.i)
  If HitsMonitor(addr, addr + bytes - 1) <> 0
    Print("!! that RAM range runs into the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". Nothing was transferred and memory is untouched.")
    PrintN("   Point it inside one of the payload windows instead:")
    PutWindows()
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  MmcRead - mmc read <blk> <addr> [count]
; ----------------------------------------------------------------------
Procedure MmcRead()
  Define bsize.i
  Define bytes.i
  Define i.i
  Define addr.i

  If MmcBringUp() = 0
    ProcedureReturn
  EndIf
  If MmcParseXfer("read") = 0
    ProcedureReturn
  EndIf

  bsize = HwMmcBlockSize()
  bytes = gMmcCount * bsize
  If MmcGuardRam(gMmcAddr, bytes) = 0
    ProcedureReturn
  EndIf

  i = 0
  While i < gMmcCount
    ; ONE BREAK CHECK PER BLOCK, at the top, so a stopped read never
    ; leaves half a block's worth of stale expectation - the block just
    ; read completed before the check.
    If OutBreak() <> 0
      Print("   stopped after ")
      PrintDec(i)
      Print(" of ")
      PrintDec(gMmcCount)
      PrintN(" blocks. What was read is in memory; the rest is not.")
      ProcedureReturn
    EndIf
    addr = gMmcAddr + (i * bsize)
    If HwMmcReadBlock(gMmcBlk + i, addr) = 0
      Print("!! reading block ")
      PrintDec(gMmcBlk + i)
      Print(" failed after ")
      PrintDec(i)
      PrintN(" blocks. The card slot said:")
      Print("   ")
      UartWriteStr(HwMmcErrorText())
      PrintNl()
      ProcedureReturn
    EndIf
    i = i + 1
  Wend

  PrintDec(gMmcCount)
  Print(" block(s) = ")
  PrintDec(bytes)
  Print(" bytes read from card block ")
  PrintDec(gMmcBlk)
  Print(" to RAM at ")
  PutAddr(gMmcAddr)
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  MmcWrite - mmc write <blk> <addr> [count]
;
;  GATED ON HwMmcCanWrite(). On a backend that cannot write, this refuses
;  loudly and does nothing - it never silently no-ops. On this board the
;  backend rides Lib/emmc.pi4's SdWriteBlock, so writing is available -
;  but see the header: it has never moved a byte to a real card.
; ----------------------------------------------------------------------
Procedure MmcWrite()
  Define bsize.i
  Define bytes.i
  Define i.i
  Define addr.i

  If HwMmcCanWrite() = 0
    PrintN("!! writing to the card is not available on this board. The card")
    PrintN("   controller here can be read but this build has no write path for")
    PrintN("   it, so mmc write does nothing rather than pretend. mmc read and")
    PrintN("   mmc info still work.")
    ProcedureReturn
  EndIf

  If MmcBringUp() = 0
    ProcedureReturn
  EndIf
  If MmcParseXfer("write") = 0
    ProcedureReturn
  EndIf

  bsize = HwMmcBlockSize()
  bytes = gMmcCount * bsize
  If MmcGuardRam(gMmcAddr, bytes) = 0
    ProcedureReturn
  EndIf

  ; A RAW BLOCK WRITE IS DESTRUCTIVE AND UNCONDITIONAL. It overwrites
  ; whatever is on those card blocks - a filesystem included - with no
  ; undo. That is what the command is for, so it is not blocked, but it
  ; is named, and there is no are-you-sure prompt because a monitor that
  ; second-guesses an explicit command is not one to trust.
  i = 0
  While i < gMmcCount
    If OutBreak() <> 0
      Print("   stopped after ")
      PrintDec(i)
      Print(" of ")
      PrintDec(gMmcCount)
      PrintN(" blocks. Those already written are on the card; the rest are not.")
      ProcedureReturn
    EndIf
    addr = gMmcAddr + (i * bsize)
    If HwMmcWriteBlock(gMmcBlk + i, addr) = 0
      Print("!! writing block ")
      PrintDec(gMmcBlk + i)
      Print(" failed after ")
      PrintDec(i)
      PrintN(" blocks. The card slot said:")
      Print("   ")
      UartWriteStr(HwMmcErrorText())
      PrintNl()
      ProcedureReturn
    EndIf
    i = i + 1
  Wend

  PrintDec(gMmcCount)
  Print(" block(s) = ")
  PrintDec(bytes)
  Print(" bytes written from RAM at ")
  PutAddr(gMmcAddr)
  Print(" to card block ")
  PrintDec(gMmcBlk)
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  CmdMmc - the dispatcher. Gate first, then the sub-command word.
; ----------------------------------------------------------------------
Procedure CmdMmc()
  ; THE GATE, FIRST. On a board without #CAP_MMC this prints the honest
  ; "not available on this board" sentence and returns 0, and this command
  ; returns cleanly having touched no seam. The reason is generic to the
  ; hardware class, not to any chip.
  If RequireCap(#CAP_MMC, "mmc", "this board has no SD or eMMC card controller Anvil can reach") = 0
    ProcedureReturn
  EndIf

  SkipSpace()
  If gLine[gPos] = 0
    ; Bare `mmc` is `mmc info`, plus a one-line reminder of the rest.
    MmcInfo()
    PrintN("Type mmc read <blk> <addr> [count] or mmc write <blk> <addr> [count],")
    PrintN("all three numbers in hex, to move raw blocks between the card and RAM.")
    ProcedureReturn
  EndIf

  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If WordIs("info") <> 0
    MmcInfo()
  ElseIf WordIs("read") <> 0
    MmcRead()
  ElseIf WordIs("write") <> 0
    MmcWrite()
  Else
    PrintN("!! mmc takes info, read or write. That was none of those, so nothing")
    PrintN("   was done. Type mmc on its own for the card's details, or help for")
    PrintN("   the full syntax.")
  EndIf
EndProcedure
