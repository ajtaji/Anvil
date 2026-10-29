; Shared EDID test dispatch. The composition supplies parser, entry and storage.
; control owns 72 writable bytes; edid names the bounded input provided by the caller.

Procedure.i EdidParseGateDispatch(control.i,edid.i)
  Select PeekI(control)
    Case 1 : ProcedureReturn AnvilEdidParse(edid,PeekI(control+8),PeekI(control+16),PeekI(control+24))
    Case 2 : ProcedureReturn AnvilEdidPreferredWidth()
    Case 3 : ProcedureReturn AnvilEdidPreferredHeight()
    Case 4 : ProcedureReturn AnvilEdidModeCount()
    Case 5 : ProcedureReturn AnvilEdidValid()
    Case 6 : ProcedureReturn AnvilEdidTruncated()
    Case 7 : ProcedureReturn AnvilEdidError()
    Case 8 : ProcedureReturn AnvilEdidBlockCount()
    Case 9 : ProcedureReturn AnvilEdidExtensionCount()
    Case 10 : ProcedureReturn AnvilEdidPreferredPixelClockKHz()
    Case 11 : ProcedureReturn AnvilEdidPreferredRefreshMilliHz()
    Case 12 : ProcedureReturn AnvilEdidModeAt(PeekI(control+8),control+40,control+48,control+56,control+64)
    Case 13 : ProcedureReturn AnvilEdidPreferredTimingValid()
    Case 14 : ProcedureReturn AnvilEdidPreferredHSyncStart()
    Case 15 : ProcedureReturn AnvilEdidPreferredHSyncEnd()
    Case 16 : ProcedureReturn AnvilEdidPreferredHTotal()
    Case 17 : ProcedureReturn AnvilEdidPreferredVSyncStart()
    Case 18 : ProcedureReturn AnvilEdidPreferredVSyncEnd()
    Case 19 : ProcedureReturn AnvilEdidPreferredVTotal()
    Case 20 : ProcedureReturn AnvilEdidPreferredInterlaced()
    Case 21 : ProcedureReturn AnvilEdidPreferredSeparateSync()
    Case 22 : ProcedureReturn AnvilEdidPreferredVSyncPositive()
    Case 23 : ProcedureReturn AnvilEdidPreferredHSyncPositive()
  EndSelect
  ProcedureReturn -1
EndProcedure
