; ======================================================================
;  PutRevision() USED TO BE HERE, AND IT NAMED A CHIP.  Forum 575.
;
;  It decoded a Raspberry Pi firmware revision code into "Pi 4 Model B,
;  BCM2711, 4 GB, rev 1.1" - a table of one vendor's board names and one
;  vendor's part numbers, sitting in the SHARED CORE, in a file every
;  board compiles. Its only caller was ever
;  RaspberryPi4/Board/clock_info.pi4.
;
;  Nothing was WRONG on either board: no other board calls it, so no
;  other board printed it. It was found by the gate that closes 575 -
;  the one that reads every string literal in Anvil/Core and refuses a
;  board's name in any of them - and it is the same defect as the banner
;  in a quieter place. A core that carries one board's names is a core
;  the next board has to work around.
;
;  It now lives beside the mailbox call that produces the number it
;  decodes, in RaspberryPi4/Board/clock_info.pi4.
; ======================================================================
; ----------------------------------------------------------------------
;  CmdUptime() - how long since this monitor started, and how many times
;  the board has come up.
;
;  MACHINE-READABLE FIRST LINE, ON PURPOSE. A script should not have to
;  parse prose to answer "did it reset while I was not looking", so the
;  first line is exactly:
;
;      uptime <seconds> boots <n>
;
;  Two fields, fixed order, plain decimal. A tool records them before a
;  payload and again after: SECONDS GOING BACKWARDS means the board
;  restarted, and the boot count says how many times.
;
;  THE BOOT COUNT COMES FROM safety.pi4's LIVE COUNTER at
;  #SAFETY_COUNT_ADDR = $00001000, which survives a reset because it is
;  in DRAM below the image and is not zeroed by _start. It carries
;  #SAFETY_MAGIC in its high bits so an uninitialised or scribbled word
;  cannot be mistaken for a count - if the magic is absent the count is
;  reported as unknown rather than as zero, because "0 boots" is a
;  claim and this cannot make it.
; ----------------------------------------------------------------------
Procedure CmdUptime()
  Define now.i
  Define hz.i
  Define secs.i
  Define raw.i
  Define boots.i

  hz = TickHz()
  now = Ticks()
  secs = 0
  If hz > 0 And now >= gBootTicks
    secs = (now - gBootTicks) / hz
  EndIf

  raw = PeekN(#SAFETY_COUNT_ADDR)
  boots = -1
  If (raw & $FFFFFF00) = (#SAFETY_MAGIC & $FFFFFF00)
    boots = raw & $FF
  EndIf

  ; The machine-readable line, first and alone.
  Print("uptime ")
  PrintDec(secs)
  Print(" boots ")
  If boots < 0
    Print("?")
  Else
    PrintDec(boots)
  EndIf
  PrintNl()

  ; Then the same thing for a person.
  Print("This monitor has been up for ")
  PrintDec(secs)
  PrintN(" seconds.")
  If boots >= 0
    Print("The board has started ")
    PrintDec(boots)
    PrintN(" times since the counter was last cleared.")
  Else
    PrintN("The boot counter has no magic in it, so its value is not")
    PrintN("trustworthy and is reported as ? rather than guessed at.")
  EndIf
  PrintN("Watch the first line: if the seconds ever go DOWN between two")
  PrintN("readings, the board reset in between - which is how a payload")
  PrintN("that wedged the machine is told apart from one that returned.")
EndProcedure
