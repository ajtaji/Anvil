; ======================================================================
;  shotarm.pbi - IS THE MONITOR TO KEEP THE PAYLOAD'S LAST FRAME?
;
;  ONE BOOLEAN AND A SEQUENCE NUMBER, AND THEY ARE HERE RATHER THAN IN A
;  BOARD FILE ON PURPOSE. The QUESTION is policy - an operator, or a host
;  tool, saying "whatever this payload leaves on the screen, keep it" -
;  and it is the same question on every board Anvil runs on. The ANSWER
;  is mechanism: which bytes the panel is actually scanning, and where a
;  board has room to put a copy of them. That half cannot leave the
;  board, and it does not: the board's payload-entry path asks
;  ShotArmed() and does its own copying.
;
;  A BOARD THAT CANNOT CAPTURE SIMPLY NEVER ASKS. Arming on such a board
;  costs one word of BSS and changes nothing, which is the right cost for
;  a core file a board is not obliged to use.
;
;  WHY THE ARM IS ONE-SHOT. `shot arm` is armed for THE NEXT RUN, and the
;  board's capture clears it. An arm that stayed set would quietly
;  overwrite the picture somebody was still reading with the next run's,
;  and the second run is the one nobody was watching. A host tool that
;  wants every run captured arms before every run, which is one line in
;  the tool and is what tools/board_run.py does.
;
;  THE SEQUENCE NUMBER RISES ON EVERY COMPLETED CAPTURE and is never
;  reset - not even by a reset of the board, which is the part that went
;  wrong (forum 876). The capture area is DRAM and survives a reset; this
;  counter is BSS and does not. So after a reset the area still said
;  "picture number 8" while the next capture was numbered 1, and the host
;  refused a genuinely new picture as stale on the first run of every boot.
;  The board's capture path now hands the number the area already holds
;  to ShotSeqCarry before it writes, and the count continues from there. It is what lets a host tell "the capture I asked for" from "the
;  capture that was already sitting there from the run before" - the one
;  failure a magic alone cannot catch, because a stale capture is
;  perfectly well formed. tools/board_run.py reads it before the run and
;  refuses a picture whose sequence did not move.
;
;  Include it before any board file whose payload-entry path asks, and
;  before the boot command that arms it.
; ======================================================================

; 1 while the next payload entry is to be captured on its way back.
Global gShotArm.i

; How many captures have completed since this board started. Never reset.
Global gShotSeq.i

; Arm or disarm. Any non-zero arms; the spelling is a flag rather than a
; count because "capture the next two runs" is not a thing anybody asked
; for and a counter that can be left at 3 is a trap.
Procedure ShotArm(on.i)
  If on <> 0
    gShotArm = 1
  Else
    gShotArm = 0
  EndIf
EndProcedure

Procedure.i ShotArmed()
  ProcedureReturn gShotArm
EndProcedure

; Take the arm, one-shot: answers whether it was armed AND clears it in
; the same breath, so the capture path cannot read it, decide to capture,
; and then forget to put it back. One caller, one call, no ordering to
; get wrong.
Procedure.i ShotTakeArm()
  Define was.i
  was = gShotArm
  gShotArm = 0
  ProcedureReturn was
EndProcedure

; Continue from a number a previous boot left in the capture area. Never
; lowers the count, so a torn or foreign header cannot move it backwards.
Procedure ShotSeqCarry(seen.i)
  If seen > gShotSeq
    gShotSeq = seen
  EndIf
EndProcedure

; The next sequence number. Called by a capture that has already written
; every other header word and is about to write its magic.
Procedure.i ShotNextSeq()
  gShotSeq = gShotSeq + 1
  ProcedureReturn gShotSeq
EndProcedure

Procedure.i ShotSeq()
  ProcedureReturn gShotSeq
EndProcedure
