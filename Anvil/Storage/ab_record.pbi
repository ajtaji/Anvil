; Shared A/B boot-control record and handoff protocol. No filesystem or
; board dependencies: callers install Read(slot, buffer) and Write(slot, buffer)
; callbacks for exact 512-byte records. Both callbacks answer 1 or 0.
;
; Owns the format, validation, state editing, CRC and independent write
; readback. Loader/updater selection and placement policy remain with callers.
; The monitor confirms the loader's handoff without rehashing the whole slot
; inside its never-fed watchdog window. The Pi 3 compositions all use this
; implementation and one named-file adapter.
;
; Dependency: Anvil/Core/crc.pbi must be included first. No includes here.

; ----------------------------------------------------------------------
;  THE RECORD, 512 bytes. Offsets as update_ab.pbi writes and reads them.
; ----------------------------------------------------------------------
#P3AB_MAGIC     = $42413350   ; "P3AB" as a little-endian word
#P3AB_VERSION   = 2

#P3AB_OFF_MAGIC   = 0
#P3AB_OFF_VERSION = 4
#P3AB_OFF_GEN     = 8         ; 64-bit generation, strictly increasing
#P3AB_OFF_LENGTH  = 16        ; 64-bit slot length in bytes, header included
#P3AB_OFF_SLOT    = 24        ; 32-bit, which slot this record describes
#P3AB_OFF_LOAD    = 28        ; 32-bit, the load address the slot is for
#P3AB_OFF_DIGEST  = 32        ; 32 bytes of SHA-256 over the slot
#P3AB_OFF_STATE   = 64        ; 32-bit, one of the three below
#P3AB_OFF_CRC     = 508       ; 32-bit CRC-32 over bytes 0..507

#P3AB_PENDING   = 1
#P3AB_TRIED     = 2
#P3AB_CONFIRMED = 3

#P3AB_RECORD_BYTES = 512
#P3AB_LOAD         = $200000   ; #PI3_UPDATE_LOAD, the slot entry address
#P3AB_HEADER       = 256       ; P3SLOT 128 + PMFBOOT v2 128

; ----------------------------------------------------------------------
;  THE HANDOFF PAGE, 128 bytes at $1FF0000, written by the loader after
;  it placed a slot and before it branched. CRC-32 protected at +124.
; ----------------------------------------------------------------------
#P3AB_HANDOFF        = $1FF0000
#P3AB_HANDOFF_MAGIC  = $0031464F483350   ; "P3HOF1" and a NUL
#P3AB_HOFF_VERSION   = 8
#P3AB_HOFF_SLOT      = 12
#P3AB_HOFF_GEN       = 16
#P3AB_HOFF_DTB       = 24
#P3AB_HOFF_STATE     = 32
#P3AB_HOFF_LENGTH    = 40
#P3AB_HOFF_DIGEST    = 48
#P3AB_HOFF_CRC       = 124

; ----------------------------------------------------------------------
;  THE TWO CALLBACKS. This is the whole of what this file knows about a
;  medium.
;
;    Read(slot, *buf)   read that slot's 512-byte record into *buf.
;    Write(slot, *buf)  replace it with the 512 bytes at *buf.
;
;  Both answer 1 or 0. slot is 0 for A and 1 for B.
;
;  A WRITER IS OPTIONAL AND ITS ABSENCE IS NOT AN ERROR UNTIL SOMETHING
;  TRIES TO WRITE. A monitor on a read-only card can still READ its
;  record and report what state it is in, which is exactly the diagnostic
;  somebody wants when a card has gone read-only.
; ----------------------------------------------------------------------
Global *p3ab_read
Global *p3ab_write
Global p3ab_err.i

; A 512-byte working record and a second one to read the write back into.
; Two buffers, not one: the read-back check below compares what the
; medium now holds against what we meant to write, and reading into the
; buffer we wrote from would compare it against itself.
Global Dim p3ab_rec.a[#P3AB_RECORD_BYTES]
Global Dim p3ab_back.a[#P3AB_RECORD_BYTES]

#P3AB_E_NONE      = 0
#P3AB_E_NOIO      = -1    ; no reader was installed
#P3AB_E_READ      = -2    ; the reader refused
#P3AB_E_WRITE     = -3    ; the writer refused
#P3AB_E_READBACK  = -4    ; the write was accepted and did not take
#P3AB_E_RECORD    = -5    ; the record on the medium is not a valid one
#P3AB_E_HANDOFF   = -6    ; the loader's handoff page is not valid
#P3AB_E_MISMATCH  = -7    ; handoff and record describe different things
#P3AB_E_STATE     = -8    ; the state is not one a confirm may act on
#P3AB_E_NOWRITER  = -9    ; a write was needed and none was installed

Procedure AbSetIo(*readRecord, *writeRecord)
  *p3ab_read = *readRecord
  *p3ab_write = *writeRecord
EndProcedure

Procedure.i AbLastError()
  ProcedureReturn p3ab_err
EndProcedure

Procedure.i ab_Fail(code.i)
  p3ab_err = code
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  AbRecordAddr() - the working record, for a caller that wants to read a
;  field out of it after a successful load.
; ----------------------------------------------------------------------
Procedure.i AbRecordAddr()
  ProcedureReturn @p3ab_rec[0]
EndProcedure

; ----------------------------------------------------------------------
;  AbRecordValid(p, slot) - is what is at p a control record for slot.
;
;  EVERY CHECK update_ab.pbi's pi3UpRecordValid() MAKES, except the two
;  that are about the medium rather than the record: the length is not
;  compared against the mapped file size or the staging arena here,
;  because neither is a property of the record and the caller that cares
;  has both. maxLength lets a caller that DOES care hand its own ceiling
;  in; 0 means do not check it.
; ----------------------------------------------------------------------
Procedure.i AbRecordValid(p.i, slot.i, maxLength.i)
  Define length.i
  If (PeekL(p + #P3AB_OFF_MAGIC) & $FFFFFFFF) <> #P3AB_MAGIC
    ProcedureReturn 0
  EndIf
  If PeekL(p + #P3AB_OFF_VERSION) <> #P3AB_VERSION
    ProcedureReturn 0
  EndIf
  If PeekI(p + #P3AB_OFF_GEN) < 1 Or PeekI(p + #P3AB_OFF_GEN) >= $7FFFFFFFFFFFFFFF
    ProcedureReturn 0
  EndIf
  length = PeekI(p + #P3AB_OFF_LENGTH)
  If length < #P3AB_HEADER + 4
    ProcedureReturn 0
  EndIf
  If maxLength > 0 And length > maxLength
    ProcedureReturn 0
  EndIf
  If PeekL(p + #P3AB_OFF_SLOT) <> slot Or PeekL(p + #P3AB_OFF_LOAD) <> #P3AB_LOAD
    ProcedureReturn 0
  EndIf
  If PeekL(p + #P3AB_OFF_STATE) < #P3AB_PENDING Or PeekL(p + #P3AB_OFF_STATE) > #P3AB_CONFIRMED
    ProcedureReturn 0
  EndIf
  ProcedureReturn Bool((PeekL(p + #P3AB_OFF_CRC) & $FFFFFFFF) = Crc32(p, #P3AB_OFF_CRC))
EndProcedure

Procedure.i AbRecordState(p.i)
  ProcedureReturn PeekL(p + #P3AB_OFF_STATE)
EndProcedure

Procedure.i AbRecordGeneration(p.i)
  ProcedureReturn PeekI(p + #P3AB_OFF_GEN)
EndProcedure

Procedure.i AbRecordLength(p.i)
  ProcedureReturn PeekI(p + #P3AB_OFF_LENGTH)
EndProcedure

; Build the one shared on-disk record shape. Callers provide only policy
; values; offsets, zeroing, and CRC remain owned here.
Procedure.i AbRecordInit(p.i, slot.i, generation.i, length.i, digest.i, state.i)
  Define n.i
  If p = 0 Or slot < 0 Or slot > 1 Or generation < 1 Or length < #P3AB_HEADER + 4 Or digest = 0
    ProcedureReturn 0
  EndIf
  For n = 0 To #P3AB_RECORD_BYTES - 1 : PokeA(p + n, 0) : Next
  PokeL(p + #P3AB_OFF_MAGIC, #P3AB_MAGIC)
  PokeL(p + #P3AB_OFF_VERSION, #P3AB_VERSION)
  PokeI(p + #P3AB_OFF_GEN, generation)
  PokeI(p + #P3AB_OFF_LENGTH, length)
  PokeL(p + #P3AB_OFF_SLOT, slot)
  PokeL(p + #P3AB_OFF_LOAD, #P3AB_LOAD)
  For n = 0 To 31 : PokeA(p + #P3AB_OFF_DIGEST + n, PeekA(digest + n)) : Next
  PokeL(p + #P3AB_OFF_STATE, state)
  PokeL(p + #P3AB_OFF_CRC, Crc32(p, #P3AB_OFF_CRC))
  ProcedureReturn 1
EndProcedure

Procedure.i AbWriteRecord(slot.i, p.i)
  Define n.i
  p3ab_err = #P3AB_E_NONE
  If *p3ab_read = 0 : ProcedureReturn ab_Fail(#P3AB_E_NOIO) : EndIf
  If *p3ab_write = 0 : ProcedureReturn ab_Fail(#P3AB_E_NOWRITER) : EndIf
  If AbRecordValid(p, slot, 0) = 0 : ProcedureReturn ab_Fail(#P3AB_E_RECORD) : EndIf
  If p3ab_write(slot, p) = 0 : ProcedureReturn ab_Fail(#P3AB_E_WRITE) : EndIf
  If *p3ab_read = 0 Or p3ab_read(slot, @p3ab_back[0]) = 0 : ProcedureReturn ab_Fail(#P3AB_E_READBACK) : EndIf
  For n = 0 To #P3AB_RECORD_BYTES - 1
    If p3ab_back[n] <> PeekA(p + n) : ProcedureReturn ab_Fail(#P3AB_E_READBACK) : EndIf
  Next
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  AbHandoffValid() - is the loader's page one it wrote this boot.
;
;  MAGIC, VERSION AND CRC. The page is in DRAM that survives a reset, so
;  a stale one from an earlier boot is a real possibility and the CRC is
;  what makes it detectable rather than merely unlikely.
; ----------------------------------------------------------------------
Procedure.i AbHandoffValid()
  Define h.i
  h = #P3AB_HANDOFF
  If PeekI(h) <> #P3AB_HANDOFF_MAGIC
    ProcedureReturn 0
  EndIf
  If PeekL(h + #P3AB_HOFF_VERSION) <> 2
    ProcedureReturn 0
  EndIf
  If PeekL(h + #P3AB_HOFF_SLOT) < 0 Or PeekL(h + #P3AB_HOFF_SLOT) > 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn Bool((PeekL(h + #P3AB_HOFF_CRC) & $FFFFFFFF) = Crc32(h, #P3AB_HOFF_CRC))
EndProcedure

Procedure.i AbHandoffSlot()
  ProcedureReturn PeekL(#P3AB_HANDOFF + #P3AB_HOFF_SLOT)
EndProcedure

Procedure.i AbHandoffGeneration()
  ProcedureReturn PeekI(#P3AB_HANDOFF + #P3AB_HOFF_GEN)
EndProcedure

Procedure.i AbHandoffDtb()
  ProcedureReturn PeekI(#P3AB_HANDOFF + #P3AB_HOFF_DTB)
EndProcedure

; Are the handoff page and the record talking about the same slot content?
Procedure.i ab_HandoffMatches(p.i)
  Define h.i
  Define n.i
  h = #P3AB_HANDOFF
  If PeekI(p + #P3AB_OFF_GEN) <> PeekI(h + #P3AB_HOFF_GEN)
    ProcedureReturn 0
  EndIf
  If PeekL(p + #P3AB_OFF_STATE) <> PeekL(h + #P3AB_HOFF_STATE)
    ProcedureReturn 0
  EndIf
  If PeekI(p + #P3AB_OFF_LENGTH) <> PeekI(h + #P3AB_HOFF_LENGTH)
    ProcedureReturn 0
  EndIf
  For n = 0 To 31
    If PeekA(p + #P3AB_OFF_DIGEST + n) <> PeekA(h + #P3AB_HOFF_DIGEST + n)
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  AbLoadRecord(slot) - read it through the caller's reader and check it.
; ----------------------------------------------------------------------
Procedure.i AbLoadRecord(slot.i)
  p3ab_err = #P3AB_E_NONE
  If *p3ab_read = 0
    ProcedureReturn ab_Fail(#P3AB_E_NOIO)
  EndIf
  If slot < 0 Or slot > 1
    ProcedureReturn ab_Fail(#P3AB_E_RECORD)
  EndIf
  If p3ab_read(slot, @p3ab_rec[0]) = 0
    ProcedureReturn ab_Fail(#P3AB_E_READ)
  EndIf
  If AbRecordValid(@p3ab_rec[0], slot, 0) = 0
    ProcedureReturn ab_Fail(#P3AB_E_RECORD)
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  ab_WriteState(slot, state) - set the state, re-CRC, write, READ BACK.
;
;  THE READ-BACK IS THE POINT AND IT IS NOT OPTIONAL. This is the write
;  that decides whether the board boots this image again or falls back to
;  the last one. A medium that accepted the write and did not perform it
;  would leave the record saying TRIED, the watchdog would reset the
;  board, and the loader would fall back - which looks exactly like the
;  new image having crashed. So the bytes are read back through the
;  caller's reader and compared, and a mismatch is its own error code.
;
;  The working-record helper delegates to the public state API used
;  by the updater, so both paths share the exact edit and write proof.
; ----------------------------------------------------------------------
Procedure.i ab_WriteState(slot.i, state.i)
  ProcedureReturn AbSetRecordState(slot, @p3ab_rec[0], state)
EndProcedure

; Public state transition of a previously loaded record: validate it, edit
; only its state, then commit and read back through the shared record writer.
Procedure.i AbSetRecordState(slot.i, p.i, state.i)
  If state < #P3AB_PENDING Or state > #P3AB_CONFIRMED : ProcedureReturn ab_Fail(#P3AB_E_STATE) : EndIf
  If AbRecordValid(p, slot, 0) = 0 : ProcedureReturn ab_Fail(#P3AB_E_RECORD) : EndIf
  PokeL(p + #P3AB_OFF_STATE, state)
  PokeL(p + #P3AB_OFF_CRC, Crc32(p, #P3AB_OFF_CRC))
  ProcedureReturn AbWriteRecord(slot, p)
EndProcedure

; ----------------------------------------------------------------------
;  AbConfirmRunning() - THE ONE THING A MONITOR HAS TO DO AT BOOT.
;
;  Read the loader's handoff page, find the slot it says is running, read
;  that slot's record, check the two describe the same content, and move
;  it from TRIED to CONFIRMED. Answers 1 when the running slot is
;  confirmed - INCLUDING when it already was, which is the ordinary case
;  on every boot after the first of a new image.
;
;  IT DOES NOT RE-HASH THE SLOT. The loader hashed it before it branched
;  and the handoff page carries that digest; re-reading fourteen
;  megabytes off the card to hash it again inside a fifteen-second
;  deadline would be the wrong kind of thorough. What this checks is that
;  the record and the handoff AGREE, which is what catches the case the
;  hash cannot: a record rewritten underneath a running image.
;
;  A CONFIRM IS NOT A REBOOT-LOOP GUARD. Confirming says "this image
;  started"; it does not say it works. That distinction is the loader's
;  to make and it makes it with the generation counter.
; ----------------------------------------------------------------------
Procedure.i AbConfirmRunning()
  Define slot.i
  Define state.i

  p3ab_err = #P3AB_E_NONE
  If AbHandoffValid() = 0
    ProcedureReturn ab_Fail(#P3AB_E_HANDOFF)
  EndIf
  slot = AbHandoffSlot()
  If AbLoadRecord(slot) = 0
    ProcedureReturn 0
  EndIf
  If ab_HandoffMatches(@p3ab_rec[0]) = 0
    ProcedureReturn ab_Fail(#P3AB_E_MISMATCH)
  EndIf

  state = AbRecordState(@p3ab_rec[0])
  If state = #P3AB_CONFIRMED
    ProcedureReturn 1
  EndIf
  If state <> #P3AB_TRIED
    ; PENDING here means the loader branched into a slot it had not
    ; marked as being tried, which it never does. Refuse rather than
    ; promote it: a PENDING record that became CONFIRMED without ever
    ; being TRIED would defeat the whole trial.
    ProcedureReturn ab_Fail(#P3AB_E_STATE)
  EndIf
  ProcedureReturn ab_WriteState(slot, #P3AB_CONFIRMED)
EndProcedure

; ----------------------------------------------------------------------
;  AbErrorText() - a whole sentence with the code's meaning in it and the
;  first thing to check.
; ----------------------------------------------------------------------
Procedure.i AbErrorText()
  If p3ab_err = #P3AB_E_NONE
    ProcedureReturn "nothing went wrong"
  EndIf
  If p3ab_err = #P3AB_E_NOIO
    ProcedureReturn "A/B error 1: no way to reach the control records was installed, which is a fault in this monitor and not in the card"
  EndIf
  If p3ab_err = #P3AB_E_READ
    ProcedureReturn "A/B error 2: the control record could not be read off the card. Check that the boot partition mounted and that the record file is there"
  EndIf
  If p3ab_err = #P3AB_E_WRITE
    ProcedureReturn "A/B error 3: the control record could not be written. The card may be read-only, or the write window may not have been opened"
  EndIf
  If p3ab_err = #P3AB_E_READBACK
    ProcedureReturn "A/B error 4: the control record was written, and reading it back gave different bytes. Treat the card as unreliable and do not reset the board until it has been looked at"
  EndIf
  If p3ab_err = #P3AB_E_RECORD
    ProcedureReturn "A/B error 5: the control record on the card is not a valid one - wrong magic, wrong version, a length or a slot number that does not belong to it, or a bad checksum"
  EndIf
  If p3ab_err = #P3AB_E_HANDOFF
    ProcedureReturn "A/B error 6: the loader's handoff page is not valid, so this image cannot tell which slot it is running from. It was probably not started by the loader"
  EndIf
  If p3ab_err = #P3AB_E_MISMATCH
    ProcedureReturn "A/B error 7: the loader's handoff page and the control record on the card describe different content, which means the record was changed after this image was started"
  EndIf
  If p3ab_err = #P3AB_E_STATE
    ProcedureReturn "A/B error 8: the running slot's record is not in the trial state the loader leaves it in, so there is nothing to confirm and promoting it would defeat the trial"
  EndIf
  If p3ab_err = #P3AB_E_NOWRITER
    ProcedureReturn "A/B error 9: the running slot needs confirming and the card is mounted read-only, so the deadman cannot be released. The board will reset and fall back"
  EndIf
  ProcedureReturn "an A/B error with no sentence written for it, which is a defect in this monitor"
EndProcedure
