; ======================================================================
;  l2cap.pbi - Bluetooth L2CAP channels over Anvil/Net/hci.pbi's one ACL
;  link. SHARED AND CHIP-FREE (above the HwBt* seam, like hci.pbi).
;
;  Moved here 2026-10-16 (Ron: "it made its own bluetooth stack instead of
;  adding one to anvil ... lets add it to anvil") from the NES payload's
;  A2DP plugin (NesEmulatorPicoSeries/anvil/audio_bluetooth.pi4), which
;  opened two channels to a speaker and streamed over them on the Pi 4.
;  There the channels were two fixed variables; here they are a table, so
;  AVDTP (Anvil/Net/a2dp.pbi) and later RFCOMM (a GNSS receiver's serial
;  port) use the same code.
;
;    L2Init()              hook into hci.pbi (once)
;    L2Connect(psm)        open a channel: its number, or -1
;    L2State(ch)           #L2_ST_*: OPEN once both configurations are done
;    L2Send(ch, *p, n)     one frame: 1, or 0 (HciError(): no credit ...)
;    L2Disconnect(ch)
;    *l2_dataIn            (ch, *p, n): a frame that arrived on a channel
;
;  ---- THE SIGNALLING (Bluetooth Core v5.x Vol 3 Part A, ch. 4) ---------
;  On CID 1, each command = code, identifier, length(2), data:
;    2 Connection Request (psm, scid)        we REFUSE (result 2, PSM not
;      supported): nothing here accepts an incoming channel yet
;    3 Connection Response (dcid, scid, result, status): 0 = go on to
;      configure, 1 = pending (wait), anything else = refused
;    4 Configuration Request (dcid, flags, options) -> we accept as asked
;    5 Configuration Response (scid, flags, result): 0 = our request taken
;    6 Disconnection Request -> 7 Response; 8 Echo -> 9; 10 Information
;      Request -> 11: extended features none, fixed channels = signalling
;    The Configuration Response's first field is the PEER's CID for the
;    channel (Linux l2cap_build_conf_rsp: rsp->scid = chan->dcid). The NES
;    payload sent its own CID there; its speaker did not mind.
;  Our Configuration Request asks for an MTU of 672 (the default) and
;  nothing else. Frames that arrive split over ACL packets (boundary 1)
;  are not reassembled: they are counted (L2Fragments) and dropped - no
;  peer used so far sends a frame larger than one ACL packet.
; ======================================================================

EnableExplicit

#L2_MAX_CH     = 4
#L2_CID_SIGNAL = 1
#L2_CID_FIRST  = $40
#L2_MTU        = 672
#L2_FRAME_MAX  = 1100

#L2_ST_FREE    = 0
#L2_ST_WAIT    = 1        ; Connection Request sent
#L2_ST_CONFIG  = 2        ; connected, configurations in progress
#L2_ST_OPEN    = 3
#L2_ST_FAILED  = 4        ; refused, or the link went down

#L2_PSM_SDP    = $0001
#L2_PSM_RFCOMM = $0003
#L2_PSM_AVDTP  = $0019

Global Dim l2_state.i[#L2_MAX_CH]
Global Dim l2_psm.i[#L2_MAX_CH]
Global Dim l2_rcid.i[#L2_MAX_CH]
Global Dim l2_cfgOut.i[#L2_MAX_CH]      ; the peer took our configuration
Global Dim l2_cfgIn.i[#L2_MAX_CH]       ; we took the peer's
Global Dim l2_result.i[#L2_MAX_CH]      ; the refusal's result code
Global l2_nextId.i = 1
Global l2_fragments.i
Global l2_refused.i                     ; incoming channels refused
Global l2_inited.i
Global Dim l2_tx.a[#L2_FRAME_MAX]
Global *l2_dataIn                       ; (ch, *p, n)

Procedure.i l2_Id()
  Define id.i = l2_nextId
  l2_nextId = l2_nextId + 1
  If l2_nextId > 255 : l2_nextId = 1 : EndIf
  ProcedureReturn id
EndProcedure

; The channel whose local CID is cid, or -1.
Procedure.i l2_ByLocal(cid.i)
  Define ch.i = cid - #L2_CID_FIRST
  If ch < 0 Or ch >= #L2_MAX_CH : ProcedureReturn -1 : EndIf
  If l2_state[ch] = #L2_ST_FREE : ProcedureReturn -1 : EndIf
  ProcedureReturn ch
EndProcedure

Procedure l2_Put16(at.i, v.i)
  l2_tx[at] = v & $FF
  l2_tx[at + 1] = (v >> 8) & $FF
EndProcedure

; Send what is in l2_tx[4..4+n) on cid: the basic header goes in front.
Procedure.i l2_SendRaw(cid.i, n.i)
  l2_Put16(0, n)
  l2_Put16(2, cid)
  ProcedureReturn HciAclSend(@l2_tx[0], n + 4)
EndProcedure

; One signalling command: code, id, then n data bytes already at l2_tx[8].
Procedure.i l2_Signal(code.i, id.i, n.i)
  l2_tx[4] = code
  l2_tx[5] = id
  l2_Put16(6, n)
  ProcedureReturn l2_SendRaw(#L2_CID_SIGNAL, n + 4)
EndProcedure

Procedure l2_SendConfigRequest(ch.i)
  l2_Put16(8, l2_rcid[ch])
  l2_Put16(10, 0)                       ; flags: no continuation
  l2_tx[12] = 1 : l2_tx[13] = 2         ; option MTU, 2 bytes
  l2_Put16(14, #L2_MTU)
  l2_Signal(4, l2_Id(), 8)
EndProcedure

Procedure l2_CheckOpen(ch.i)
  If l2_state[ch] = #L2_ST_CONFIG And l2_cfgIn[ch] <> 0 And l2_cfgOut[ch] <> 0
    l2_state[ch] = #L2_ST_OPEN
  EndIf
EndProcedure

; The commands in one signalling frame of n bytes at *p.
Procedure l2_SignalIn(*p, n.i)
  Define at.i, code.i, id.i, length.i, cid.i, ch.i, result.i, kind.i, i.i
  at = 0
  While at + 4 <= n
    code = PeekA(*p + at) & $FF
    id = PeekA(*p + at + 1) & $FF
    length = (PeekA(*p + at + 2) & $FF) | ((PeekA(*p + at + 3) & $FF) << 8)
    If at + 4 + length > n : ProcedureReturn : EndIf
    Select code
      Case 2                              ; Connection Request: refused
        If length >= 4
          l2_Put16(8, 0)
          l2_tx[10] = PeekA(*p + at + 6) : l2_tx[11] = PeekA(*p + at + 7)
          l2_Put16(12, 2)                 ; PSM not supported
          l2_Put16(14, 0)
          l2_Signal(3, id, 8)
          l2_refused = l2_refused + 1
        EndIf
      Case 3                              ; Connection Response
        If length >= 8
          cid = (PeekA(*p + at + 6) & $FF) | ((PeekA(*p + at + 7) & $FF) << 8)
          result = (PeekA(*p + at + 8) & $FF) | ((PeekA(*p + at + 9) & $FF) << 8)
          ch = l2_ByLocal(cid)
          If ch >= 0 And l2_state[ch] = #L2_ST_WAIT
            If result = 0
              l2_rcid[ch] = (PeekA(*p + at + 4) & $FF) | ((PeekA(*p + at + 5) & $FF) << 8)
              l2_state[ch] = #L2_ST_CONFIG
              l2_SendConfigRequest(ch)
            ElseIf result <> 1
              l2_result[ch] = result
              l2_state[ch] = #L2_ST_FAILED
            EndIf
          EndIf
        EndIf
      Case 4                              ; Configuration Request: accepted
        If length >= 4
          cid = (PeekA(*p + at + 4) & $FF) | ((PeekA(*p + at + 5) & $FF) << 8)
          ch = l2_ByLocal(cid)
          If ch >= 0
            l2_Put16(8, l2_rcid[ch])
            l2_Put16(10, 0)
            l2_Put16(12, 0)               ; success
            l2_Signal(5, id, 6)
            l2_cfgIn[ch] = 1
            l2_CheckOpen(ch)
          EndIf
        EndIf
      Case 5                              ; Configuration Response
        If length >= 6
          cid = (PeekA(*p + at + 4) & $FF) | ((PeekA(*p + at + 5) & $FF) << 8)
          result = (PeekA(*p + at + 8) & $FF) | ((PeekA(*p + at + 9) & $FF) << 8)
          ch = l2_ByLocal(cid)
          If ch >= 0
            If result = 0
              l2_cfgOut[ch] = 1
              l2_CheckOpen(ch)
            Else
              l2_result[ch] = result
              l2_state[ch] = #L2_ST_FAILED
            EndIf
          EndIf
        EndIf
      Case 6                              ; Disconnection Request
        If length >= 4
          For i = 0 To 3 : l2_tx[8 + i] = PeekA(*p + at + 4 + i) : Next
          l2_Signal(7, id, 4)
          cid = (PeekA(*p + at + 4) & $FF) | ((PeekA(*p + at + 5) & $FF) << 8)
          ch = l2_ByLocal(cid)
          If ch >= 0 : l2_state[ch] = #L2_ST_FAILED : EndIf
        EndIf
      Case 7                              ; Disconnection Response
        If length >= 4
          cid = (PeekA(*p + at + 6) & $FF) | ((PeekA(*p + at + 7) & $FF) << 8)
          ch = l2_ByLocal(cid)
          If ch >= 0 : l2_state[ch] = #L2_ST_FREE : EndIf
        EndIf
      Case 8                              ; Echo Request
        l2_Signal(9, id, 0)
      Case 10                             ; Information Request
        If length >= 2
          kind = (PeekA(*p + at + 4) & $FF) | ((PeekA(*p + at + 5) & $FF) << 8)
          l2_Put16(8, kind)
          For i = 12 To 19 : l2_tx[i] = 0 : Next
          If kind = 2                     ; extended features: none
            l2_Put16(10, 0)
            l2_Signal(11, id, 8)
          ElseIf kind = 3                 ; fixed channels: signalling only
            l2_Put16(10, 0)
            l2_tx[12] = 2
            l2_Signal(11, id, 12)
          Else
            l2_Put16(10, 1)               ; not supported
            l2_Signal(11, id, 4)
          EndIf
        EndIf
    EndSelect
    at = at + 4 + length
  Wend
EndProcedure

; hci.pbi's ACL sink: pb 2 = the start of a frame, 1 = a continuation.
Procedure l2_AclIn(pb.i, *p, n.i)
  Define length.i, cid.i, ch.i
  If pb = 1 Or n < 4
    l2_fragments = l2_fragments + 1
    ProcedureReturn
  EndIf
  length = (PeekA(*p) & $FF) | ((PeekA(*p + 1) & $FF) << 8)
  cid = (PeekA(*p + 2) & $FF) | ((PeekA(*p + 3) & $FF) << 8)
  If length + 4 > n
    l2_fragments = l2_fragments + 1
    ProcedureReturn
  EndIf
  If cid = #L2_CID_SIGNAL
    l2_SignalIn(*p + 4, length)
    ProcedureReturn
  EndIf
  ch = l2_ByLocal(cid)
  If ch >= 0 And l2_state[ch] = #L2_ST_OPEN And *l2_dataIn <> 0
    l2_dataIn(ch, *p + 4, length)
  EndIf
EndProcedure

; The link went down (or came up): every channel is gone either way.
Procedure l2_LinkNote(up.i)
  Define ch.i
  For ch = 0 To #L2_MAX_CH - 1
    If l2_state[ch] <> #L2_ST_FREE : l2_state[ch] = #L2_ST_FAILED : EndIf
  Next
EndProcedure

Procedure L2Init()
  Define ch.i
  For ch = 0 To #L2_MAX_CH - 1 : l2_state[ch] = #L2_ST_FREE : Next
  *hci_aclIn = @l2_AclIn
  *hci_linkNote = @l2_LinkNote
  l2_inited = 1
EndProcedure

; Open a channel to psm on the link. Its number (0..3), or -1: no link,
; or every slot busy. Poll L2State until #L2_ST_OPEN or #L2_ST_FAILED.
Procedure.i L2Connect(psm.i)
  Define ch.i, k.i
  If l2_inited = 0 : L2Init() : EndIf
  If HciLinkState() <> #HCI_LINK_UP : ProcedureReturn -1 : EndIf
  ch = -1
  For k = 0 To #L2_MAX_CH - 1
    If l2_state[k] = #L2_ST_FREE Or l2_state[k] = #L2_ST_FAILED
      ch = k : Break
    EndIf
  Next
  If ch < 0 : ProcedureReturn -1 : EndIf
  l2_state[ch] = #L2_ST_WAIT
  l2_psm[ch] = psm
  l2_rcid[ch] = 0
  l2_cfgIn[ch] = 0
  l2_cfgOut[ch] = 0
  l2_result[ch] = 0
  l2_Put16(8, psm)
  l2_Put16(10, #L2_CID_FIRST + ch)
  If l2_Signal(2, l2_Id(), 4) = 0
    l2_state[ch] = #L2_ST_FAILED
    ProcedureReturn -1
  EndIf
  ProcedureReturn ch
EndProcedure

Procedure.i L2State(ch.i)
  If ch < 0 Or ch >= #L2_MAX_CH : ProcedureReturn #L2_ST_FAILED : EndIf
  ProcedureReturn l2_state[ch]
EndProcedure

Procedure.i L2Result(ch.i)
  If ch < 0 Or ch >= #L2_MAX_CH : ProcedureReturn -1 : EndIf
  ProcedureReturn l2_result[ch]
EndProcedure

; One frame of n bytes at *p on an open channel. 1, or 0 (HciError()).
Procedure.i L2Send(ch.i, *p, n.i)
  Define i.i
  If ch < 0 Or ch >= #L2_MAX_CH : ProcedureReturn 0 : EndIf
  If l2_state[ch] <> #L2_ST_OPEN : ProcedureReturn 0 : EndIf
  If n + 4 > #L2_FRAME_MAX : ProcedureReturn 0 : EndIf
  For i = 0 To n - 1 : l2_tx[4 + i] = PeekA(*p + i) : Next
  ProcedureReturn l2_SendRaw(l2_rcid[ch], n)
EndProcedure

Procedure L2Disconnect(ch.i)
  If ch < 0 Or ch >= #L2_MAX_CH : ProcedureReturn : EndIf
  If l2_state[ch] = #L2_ST_OPEN Or l2_state[ch] = #L2_ST_CONFIG
    l2_Put16(8, l2_rcid[ch])
    l2_Put16(10, #L2_CID_FIRST + ch)
    l2_Signal(6, l2_Id(), 4)
  EndIf
  l2_state[ch] = #L2_ST_FREE
EndProcedure

Procedure.i L2Fragments() : ProcedureReturn l2_fragments : EndProcedure
Procedure.i L2Refused() : ProcedureReturn l2_refused : EndProcedure
