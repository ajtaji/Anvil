; Board-neutral saved-network scan policy for the shared CYW43 scan API.
; The caller supplies storage lookup, candidate and optional progress
; callbacks. Security setup, key derivation, radio power/firmware startup
; and address configuration remain adapter-owned.

#ANVIL_WIFI_SCAN_BUDGET_MS = 5000
#ANVIL_WIFI_SCAN_SLICE_MS  = 50

; The find callback writes the matching stored slot to its output argument
; for (SSID pointer,length); candidate receives (slot, SSID pointer,length).
; Returns 1 when the candidate callback accepted a stored network, 0 when
; none of the scanned stored networks was accepted, or -1 if scan start
; failed / the callback contract was incomplete. Outputs are zero on entry.
Procedure.i AnvilWifiJoinKnownScan(*findFn, *candidateFn, *progressFn, *slotOut, *ssidOut, *ssidLenOut)
  Define r.i
  Define slices.i
  Define stop.i
  Define found.i
  Define i.i
  Define slot.i
  Define band.i
  Define ssid.i
  Define ssidLen.i
  Define storedSlot.i

  If *slotOut = 0 Or *ssidOut = 0 Or *ssidLenOut = 0 Or *findFn = 0 Or *candidateFn = 0
    ProcedureReturn -1
  EndIf
  PokeL(*slotOut, 0)
  PokeI(*ssidOut, 0)
  PokeL(*ssidLenOut, 0)

  If Cyw43ScanStart(0, 2000) <> 0
    ProcedureReturn -1
  EndIf
  slices = 0
  stop = 0
  While stop = 0 And slices < (#ANVIL_WIFI_SCAN_BUDGET_MS / #ANVIL_WIFI_SCAN_SLICE_MS)
    r = Cyw43ScanPoll(#ANVIL_WIFI_SCAN_SLICE_MS)
    slices = slices + 1
    If progressFn <> 0 : progressFn() : EndIf
    If r = #CYW43_SCAN_DONE Or r = #CYW43_SCAN_FAILED
      stop = 1
    EndIf
  Wend

  found = Cyw43ScanCount()
  For band = 0 To 1
    i = 0
    While i < found
      ssid = Cyw43ScanSsid(i)
      ssidLen = Cyw43ScanSsidLen(i)
      storedSlot = 0
      If ssid <> 0 And ssidLen > 0 And ssidLen <= 32
        findFn(ssid, ssidLen, @storedSlot)
      EndIf
      slot = storedSlot
      If slot <> 0 And ssid <> 0 And ssidLen > 0 And ssidLen <= 32
        If (band = 0 And Cyw43ScanChannel(i) <= 14) Or (band = 1 And Cyw43ScanChannel(i) > 14)
          If candidateFn(slot, ssid, ssidLen) <> 0
            PokeL(*slotOut, slot)
            PokeI(*ssidOut, ssid)
            PokeL(*ssidLenOut, ssidLen)
            ProcedureReturn 1
          EndIf
        EndIf
      EndIf
      i = i + 1
    Wend
  Next
  ProcedureReturn 0
EndProcedure
