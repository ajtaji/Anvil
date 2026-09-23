
; ======================================================================
;  The payload windows
;
;  Plain 64-bit comparisons of positive addresses. They mean what they
;  say, which is why the high window can exist at all.
; ======================================================================

; ----------------------------------------------------------------------
;  THE WINDOWS ARE ASKED FOR, NOT READ AS CONSTANTS - 2026-09-08
;
;  This file used to test #PAY0_LO/#PAY0_HI and #PAY1_LO/#PAY1_HI, four
;  constants out of a board file, in three procedures. That was the same
;  defect HitsMonitor() had already been cured of once: a CORE file
;  reading numbers only a BOARD can know. It became visible when the low
;  window's bottom edge stopped being a number at all - on the Pi 4 it is
;  now computed from the size of the running image, because the monitor's
;  extent is the monitor's extent and not a two-megabyte allowance.
;
;  So the board enumerates its windows (HwPayWindows / HwPayLo / HwPayHi)
;  and this file walks them. Two consequences worth stating: a board with
;  one window or three needs no change here, and nothing in the core can
;  disagree with the board about where a payload may go, because there is
;  only one answer and it is the board's.
; ----------------------------------------------------------------------
Procedure.i InPayload(lo.i, hi.i)
  ; hi is INCLUSIVE. A block that straddles the gap between two windows
  ; fails every test and is refused whole, rather than having the half
  ; that lands in DRAM written and the half that does not thrown at an
  ; address with no memory behind it.
  Define i.i
  Define n.i
  If lo<0 Or hi<lo
    ProcedureReturn 0
  EndIf
  ; A firmware-allocated object such as a framebuffer may be inside an
  ; otherwise valid DRAM window. Windows describe reachable payload DRAM;
  ; the board's live monitor-region list removes these dynamic exclusions.
  If HitsMonitor(lo,hi)<>0
    ProcedureReturn 0
  EndIf
  n = HwPayWindows()
  For i = 0 To n - 1
    If lo >= HwPayLo(i) And hi <= HwPayHi(i)
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  PayloadTop - the last address of the payload window `a` is in, or 0.
;
;  THE CAPACITY OF A get IS DECIDED HERE, and it is decided this way
;  because A TFTP CLIENT DOES NOT KNOW HOW BIG THE FILE IS. `load` can
;  check the whole range before it writes a byte because FatSize() has
;  already told it the length; TFTP has no such number - the transfer
;  ends when a short block arrives and not before - and this client asks
;  for no options, so there is no tsize either (tftp.pi4:395-419 gives
;  the three reasons options are not negotiated).
;
;  So the destination is bounded instead: TftpSetMemory() is handed the
;  distance from the address to the end of its own window, and
;  tftp.pi4 bounds-checks EVERY block against it and fails the transfer
;  with #TFTP_E_DEST_FULL rather than writing past it. A file that is
;  too big stops at the window edge, loudly, instead of walking into the
;  payload's stack corridor or off the top of DRAM.
;
;  THE SECOND CALLER, ADDED 2026-09-05, IS Anvil/Core/netrecv.pbi, and it
;  is here for exactly the same reason: a TCP stream does not know how
;  big it is either. That is what moved this procedure out of
;  Anvil/Core/net_cmd.pbi and into this file, beside the two other
;  procedures that answer questions about the same two windows.
; ----------------------------------------------------------------------
Procedure.i PayloadTop(a.i)
  Define i.i
  Define n.i
  n = HwPayWindows()
  For i = 0 To n - 1
    If a >= HwPayLo(i) And a <= HwPayHi(i)
      ProcedureReturn HwPayHi(i)
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; WHICH REGION THE LAST HitsMonitor() CALL MATCHED. Valid ONLY on the
; instruction after a call that returned non-zero; meaningless otherwise,
; and deliberately not initialised to anything that would look sensible
; if it were read out of turn.
;
; WHY GLOBALS RATHER THAN A RETURN CODE. There are sixteen refusal
; messages across this monitor, each written for its own command, and
; every one of them ends by naming the region the caller just aimed at.
; The alternatives were: a return code plus a Select at all sixteen
; sites, or a printer procedure that swallows sixteen different sentences
; into one. The first is sixteen copies of the same decision, the second
; throws away prose that was written per command on purpose. Globals set
; at the one place that knows the answer leave all sixteen sentences
; exactly as they were and make each name the region actually hit.
;
; gMonHitWhich is the region INDEX, added 2026-09-08 with the enumeration
; below, so a caller that wants the region's name can ask the board for it
; (HwMonRegionSay) instead of guessing from the addresses.
Global gMonHitLo.i
Global gMonHitHi.i
Global gMonHitWhich.i

Procedure.i HitsMonitor(lo.i, hi.i)
  ; Strictly redundant for the loaders - no payload window overlaps a
  ; region the monitor owns, so InPayload() already refuses these. It
  ; exists so the REASON can be reported: "outside the payload window"
  ; and "you just aimed at the monitor" are the same refusal and very
  ; different mistakes, and the second one is the one somebody actually
  ; makes (an image built with --load-addr 0x200000, sent to a monitor
  ; living at 0x200000).
  ;
  ; It is NOT redundant for w, g or a, none of which are window-checked.
  ; Those three are the reason it is a procedure and not a comment.
  ;
  ; THE BOARD ENUMERATES ITS REGIONS AND THIS WALKS THEM - 2026-09-08.
  ; The history is worth keeping because it is the same lesson three
  ; times. It began as one hard-written range, #MON_LO..#MON_HI. On
  ; 2026-08-28 BSS left the image and a SECOND range had to be added
  ; here, because the board's data window is outside both payload windows
  ; and `w <bss-base> 0` would quietly change one of this program's own
  ; variables with the prompt still returning "ok". On 2026-09-08 the
  ; autoboot record left the image window too - it had to, it was the
  ; ceiling - and that would have been a THIRD `If` in a core file about
  ; a region only one board has.
  ;
  ; A core procedure that grows a branch every time a board gains a
  ; region is the wrong shape. The board knows what it reserves; the
  ; core knows what to do about it. So the board answers
  ; HwMonRegions() / HwMonRegionLo() / HwMonRegionHi() and this loop does
  ; not change again.
  ;
  ; THE RETURN VALUE IS THE REGION NUMBER, ONE-BASED, which keeps the
  ; contract every caller was already written against: zero means clear,
  ; non-zero means refused. 1 is still the code region and 2 is still
  ; the data region on both boards, because that is the order they are
  ; declared in.
  Define i.i
  Define n.i
  Define rlo.i
  Define rhi.i
  n = HwMonRegions()
  For i = 0 To n - 1
    rlo = HwMonRegionLo(i)
    rhi = HwMonRegionHi(i)
    If hi >= rlo And lo <= rhi
      gMonHitLo = rlo
      gMonHitHi = rhi
      gMonHitWhich = i
      ProcedureReturn i + 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  PutSizeApprox(bytes) - "(about 123 MB)", WORKED OUT, not typed.
;
;  FOUND 2026-09-04 WHILE CLOSING FORUM 575, AND IT IS THE SAME DEFECT IN
;  A THIRD PLACE. PutWindows() below printed "(about 123 MB)" and
;  "(about 3 GB)" as LITERALS beside whatever addresses the board
;  declares. Those two numbers are the Raspberry Pi 4's. On the other
;  board the low window is 40000000..FFFFFFFF - three gigabytes - and it
;  was labelled 123 MB, while its one-gigabyte high window was labelled
;  3 GB. Both wrong, on a live board, in the paragraph a dozen refusals
;  print to answer "then where AM I allowed to put it".
;
;  It is worse than the banner was, in one way: the banner was obviously
;  about a different computer, and a size is just a number that looks
;  plausible. The string-literal check that closes 575
;  (tools/a64/a64_anvil_check.py section 8a) did NOT catch this, because
;  "123 MB" is not a board's NAME - so it is recorded here as the reason
;  that check is a floor and not a proof.
;
;  ROUNDING IS CHOSEN TO KEEP THE PI 4'S OUTPUT BYTE-IDENTICAL. Its low
;  window is 123 MiB exactly and its high window is 2.9375 GiB, which has
;  to come out as "3 GB" and not "2 GB" - so gigabytes round to nearest
;  rather than truncating. MB here means MiB, which is what the two
;  literals meant.
; ----------------------------------------------------------------------
Procedure PutSizeApprox(bytes.i)
  Define kib.i
  Define mib.i
  Print("   (about ")
  If bytes <= 0
    ; A window with nothing in it is a board misconfiguration, and
    ; printing "0 MB" beside two addresses reads like a rounding result.
    Print("NOTHING - this window is empty, which is a fault in this board's")
    Print(" memory map")
    PrintN(")")
    ProcedureReturn
  EndIf
  kib = bytes / 1024
  mib = kib / 1024
  If mib >= 1024
    PrintDec((mib + 512) / 1024)      ; nearest GB, not truncated
    Print(" GB")
  ElseIf mib >= 1
    PrintDec(mib)
    Print(" MB")
  ElseIf kib >= 1
    PrintDec(kib)
    Print(" KB")
  Else
    PrintDec(bytes)
    Print(" bytes")
  EndIf
  PrintN(")")
EndProcedure

Procedure PutWindows()
  ; ONE LABELLED LINE PER WINDOW, NOT ONE PACKED ONE. This used to print
  ;     low  00400000..07EFFFFF   high 40000000..FBFFFFFF
  ; on a single line, which reads as four numbers and a pair of words. It
  ; is called from a dozen refusals, and in every one of them it is the
  ; answer to "then where AM I allowed to put it" - so it says so.
  ;
  ; THE SIZES ARE COMPUTED FROM THE SAME NUMBERS AS THE ADDRESSES, so a
  ; board whose windows are not this board's windows gets its own
  ; numbers. See PutSizeApprox above for what that cost before.
  ;
  ; THE WINDOWS ARE ASKED FOR - 2026-09-08. Two named constants became a
  ; walk over the board's own list for the reason at the top of this
  ; file: on the Pi 4 the low window's bottom edge is now arithmetic on
  ; the size of the running image, so there is no constant to print.
  ; "low" and "high" are the only two names this monitor has ever needed
  ; and both boards declare exactly two; a board that declares more gets
  ; numbered lines rather than a wrong name.
  Define i.i
  Define n.i
  n = HwPayWindows()
  For i = 0 To n - 1
    If i = 0 And n = 2
      Print("  the low window   ")
    ElseIf i = 1 And n = 2
      Print("  the high window  ")
    Else
      Print("  window ")
      PrintDec(i)
      Print("         ")
    EndIf
    PutAddr(HwPayLo(i))
    Print(" to ")
    PutAddr(HwPayHi(i))
    PutSizeApprox(HwPayHi(i) - HwPayLo(i) + 1)
  Next
EndProcedure

; ----------------------------------------------------------------------
;  PutMonitorMap() - WHAT THE MONITOR OWNS, AND WHERE THE NUMBERS CAME
;  FROM. New 2026-09-08 with the ruling that this program has no size
;  cap.
;
;  It exists because the map stopped being something a reader could look
;  up. While the monitor's extent was two constants in a source file,
;  "$00200000..$003FFFFF" was a fact anybody could quote from the header
;  of board.pi4 and it was the same on every build. It is now a
;  MEASUREMENT the running image takes of itself, so the only honest
;  place to read it is from the running image - which means it has to be
;  printed, and printed with the byte count it was derived from, or the
;  next person is back to quoting a number that was true last month.
;
;  Called by `map`, by the banner and by `help`, so the three cannot
;  describe three different computers.
; ----------------------------------------------------------------------
Procedure PutMonitorMap()
  Define i.i
  Define n.i
  ; THE EXACT END, NOT THE RESERVED ONE. HwMonHi() is rounded up so that
  ; payload addresses do not move on every build, and printing the
  ; rounded end beside the exact byte count would put two numbers on one
  ; line that do not add up. This line is what the image IS; the reserved
  ; lines below are what the monitor refuses to let anything touch, and
  ; the difference between them is the rounding.
  Print("  this image      ")
  PutAddr(HwMonLo())
  Print(" to ")
  PutAddr(HwMonLo() + HwMonBytes() - 1)
  Print("   ")
  PrintDec(HwMonBytes())
  PrintN(" bytes, measured from the image itself")
  n = HwMonRegions()
  For i = 0 To n - 1
    Print("  reserved        ")
    PutAddr(HwMonRegionLo(i))
    Print(" to ")
    PutAddr(HwMonRegionHi(i))
    Print("   ")
    HwMonRegionSay(i)
    PrintNl()
  Next
  Print("  its stack top   ")
  PutAddr(HwMonStack())
  PrintN("               and it grows downwards from there")
  Print("  stage a file at ")
  PutAddr(HwStageAddr())
  PrintN("               which is what the upload tools ask for")
EndProcedure
