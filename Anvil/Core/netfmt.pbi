Procedure.i EthKeyAddress()
  ProcedureReturn "net.address"
EndProcedure

Procedure.i EthKeyNetmask()
  ProcedureReturn "net.netmask"
EndProcedure

Procedure.i EthKeyGateway()
  ProcedureReturn "net.gateway"
EndProcedure

Procedure.i EthKeyServer()
  ProcedureReturn "net.server"
EndProcedure

; The DNS resolver's address, for the dns command and for resolving a
; name in ping. Separate from the four above because it is a fifth,
; genuinely optional thing: get and put never need it, and dhcp fills it
; in automatically. Set by hand with `net dns <a.b.c.d>`.
Procedure.i EthKeyDns()
  ProcedureReturn "net.dns"
EndProcedure

; ----------------------------------------------------------------------
;  An IPv4 address, printed the way a person writes one.
;
;  net.pi4 holds an address with its FIRST OCTET IN THE MOST SIGNIFICANT
;  BYTE (net.pi4's ENDIANNESS note, and NetMakeIPv4 at :789), so this
;  reads it from the top down and there is nothing to reverse. Getting
;  that backwards prints a plausible address that is not the one
;  configured, which is the worst possible failure for a line whose
;  whole job is to be compared against what somebody typed on a server.
;
;  46 is the full stop. This language has no character literals.
; ----------------------------------------------------------------------
Procedure PutIp(ip.i)
  PrintDec((ip >> 24) & $FF)
  UartWrite(46)
  PrintDec((ip >> 16) & $FF)
  UartWrite(46)
  PrintDec((ip >> 8) & $FF)
  UartWrite(46)
  PrintDec(ip & $FF)
EndProcedure

; ----------------------------------------------------------------------
;  ParseDotted - "192.168.1.50" to net.pi4's representation, or -1.
;
;  -1 IS A SAFE SENTINEL HERE and it is worth saying why, because on a
;  32-bit machine it would not be. Every value this returns is built by
;  shifting four bytes into a 64-bit signed .i, so the largest it can
;  ever produce is $00000000FFFFFFFF, which is 4294967295 and positive.
;  -1 is $FFFFFFFFFFFFFFFF and cannot collide with it. The same
;  statement on the 32-bit model would have been false, and 255.255.255.
;  255 would have read as a parse failure.
;
;  IT IS STRICT ON PURPOSE. Four fields, one to three digits each, every
;  field 0 to 255, single dots between them, nothing else and nothing
;  after. A parser that accepted "192.168.1" and filled in a zero, or
;  that stopped at the first junk character and returned what it had,
;  would turn a typo into a board that is quietly on the wrong network.
; ----------------------------------------------------------------------
Procedure.i ParseDotted(*s)
  Define i.i
  Define c.i
  Define part.i
  Define digits.i
  Define fields.i
  Define ip.i

  If *s = 0
    ProcedureReturn -1
  EndIf
  ip = 0
  part = 0
  digits = 0
  fields = 0
  i = 0
  Repeat
    c = PeekA(*s + i) & $FF
    If c >= 48 And c <= 57                 ; 48..57 are the digits 0..9
      If digits >= 3
        ProcedureReturn -1
      EndIf
      part = part * 10 + (c - 48)
      digits = digits + 1
      If part > 255
        ProcedureReturn -1
      EndIf
    ElseIf c = 46 Or c = 0                 ; 46 is a full stop
      If digits = 0
        ProcedureReturn -1                 ; "1..2" or a leading dot
      EndIf
      ; (ip << 8) - the parentheses are load bearing. & | ! bind TIGHTER
      ; than << on this compiler, so "ip << 8 | part" would parse as
      ; "ip << (8 | part)". See the LANGUAGE FACTS note in the header.
      ip = (ip << 8) | part
      fields = fields + 1
      part = 0
      digits = 0
      If c = 0
        Break
      EndIf
      If fields >= 4
        ProcedureReturn -1                 ; a fifth field
      EndIf
    Else
      ProcedureReturn -1
    EndIf
    i = i + 1
  ForEver
  If fields <> 4
    ProcedureReturn -1
  EndIf
  ProcedureReturn ip
EndProcedure

; ----------------------------------------------------------------------
;  Why the last call into each of the three libraries refused.
;
;  THREE PROCEDURES AND NOT ONE, because the three libraries have three
;  separate error variables and printing the wrong one while chasing a
;  fault costs more time than the two extra procedures cost. That is
;  pi4TftpProbe.pi4's own reasoning and it was right.
;
;  Each of the three ErrorText calls returns a POINTER, so it goes to
;  UartWriteStr and not to Print - Print picks its formatter from the
;  argument's type and would print the address as a decimal number. That
;  exact defect shipped once in this file, in PutClockRow(), and the
;  warning is recorded there.
; ----------------------------------------------------------------------
Procedure EthWhyGenet()
  Print("   The Ethernet controller said: ")
  UartWriteStr(GenetErrorText())
  PrintNl()
EndProcedure

Procedure EthWhyNet()
  Print("   The network stack said: ")
  UartWriteStr(NetErrorText())
  PrintNl()
EndProcedure

Procedure EthWhyTftp()
  Print("   The transfer said: ")
  UartWriteStr(TftpErrorText())
  PrintNl()
EndProcedure

; ----------------------------------------------------------------------
;  EthMacFetch - this board's own hardware address, from the firmware.
;
;  THE VIDEOCORE KNOWS IT AND WE DO NOT. Tag $00010003,
;  RPI_FIRMWARE_GET_BOARD_MAC_ADDRESS, six bytes of response
;  [Datasheets/pi4/hdmi/raspberrypi-firmware-downstream.h:47, and named
;  in Lib/mailbox.pi4:248]. Asking is better than inventing one: the
;  address on the board is what a DHCP reservation, a switch port
;  security list and anybody's packet capture already expect, and a
;  made-up address that works on a bare cable stops working the moment
;  the board is plugged into a managed network.
;
;  THE BYTES ARE READ ONE AT A TIME, in the order the firmware wrote
;  them, and NOT through MailboxWord(). A MAC address is six octets in
;  transmission order; reading it as one-and-a-half 32-bit words would
;  make the answer depend on a byte order nothing here has verified.
;  PeekA is the raw-byte accessor - a MAC octet is not a signed .b.
;
;  IT IS SANITY CHECKED AND IT FALLS BACK RATHER THAN FAILING. An
;  all-zero or all-ones answer, or one with the multicast bit set in the
;  first octet, is not a unicast station address and would produce a
;  MAC that nothing on the segment will talk to. The fallback is
;  02:00:4D:46:00:01 - the locally-administered address
;  pi4TftpProbe.pi4 and pi4NetProbe.pi4 already use, so a bench that has
;  seen one of those in a capture sees the same one here. Bit 1 of the
;  first octet is the locally-administered bit and $02 sets it, which is
;  what makes an invented address legal rather than a squatted one.
;
;  WHICH OF THE TWO WAS USED IS PRINTED. A board answering to an address
;  nobody expects is a fault that takes an afternoon to find from the
;  server end, and one line here removes it.
; ----------------------------------------------------------------------
