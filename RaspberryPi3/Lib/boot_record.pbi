; Named A/B control-record I/O for every Pi 3 boot composition.
; Include after filesystem, shared ab_record and the SDHOST block interface.
; No allocation/metadata writes: each record owns exactly one writable sector.
Procedure.i Pi3BootRecordName(slot.i)
  If slot = 0 : ProcedureReturn "1:P3CTRLA.BIN" : EndIf
  If slot = 1 : ProcedureReturn "1:P3CTRLB.BIN" : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i Pi3BootReadRecord(slot.i, buffer.i)
  Protected got.i
  If slot < 0 Or slot > 1 Or buffer = 0 : ProcedureReturn 0 : EndIf
  If FsOpen(Pi3BootRecordName(slot)) = 0 : ProcedureReturn 0 : EndIf
  If FsSize() <> #P3AB_RECORD_BYTES
    FsClose()
    ProcedureReturn 0
  EndIf
  got = FsRead(buffer, #P3AB_RECORD_BYTES)
  FsClose()
  ProcedureReturn Bool(got = #P3AB_RECORD_BYTES)
EndProcedure

Procedure.i Pi3BootWriteRecord(slot.i, buffer.i)
  Protected first.i
  Protected blocks.i
  Protected bytes.i
  Protected ok.i
  FsSetRangeWriter(0)
  Pi3SdSetWriteWindow(0, 0)
  If slot < 0 Or slot > 1 Or buffer = 0 : ProcedureReturn 0 : EndIf
  If FsExtentOf(Pi3BootRecordName(slot), @first, @blocks, @bytes) = 0 : ProcedureReturn 0 : EndIf
  If bytes <> #P3AB_RECORD_BYTES Or blocks < 1 : ProcedureReturn 0 : EndIf
  ; Allocation can be a whole 4 KiB cluster; only the logical 512 bytes change.
  If Pi3SdSetWriteWindow(first, 1) = 0 : ProcedureReturn 0 : EndIf
  FsSetRangeWriter(@Pi3SdWriteBlocks)
  ok = FsOverwriteFixed(Pi3BootRecordName(slot), buffer, #P3AB_RECORD_BYTES)
  FsSetRangeWriter(0)
  Pi3SdSetWriteWindow(0, 0)
  If ok = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn FsFlush()
EndProcedure
