; ======================================================================
;  a2dp.pbi - Bluetooth audio out: an A2DP source (AVDTP over L2CAP) that
;  streams SBC to one speaker or headset. SHARED AND CHIP-FREE, over
;  Anvil/Net/l2cap.pbi and Anvil/Net/hci.pbi; frames from Anvil/Audio/sbc.pbi.
;
;  Moved here 2026-10-16 from the NES payload's audio plugin
;  (NesEmulatorPicoSeries/anvil/audio_bluetooth.pi4), which streamed the
;  NES's sound to Ron's speaker from the Pi 4 under Anvil ("sounds great
;  now", stereo, 2026-10-15). The sequence and every byte it sends are
;  that plugin's; what changed is the shape - a state machine with a
;  deadline per step and a sentence for every way it stops, instead of
;  flags read by the game loop.
;
;    A2dpBegin(*addr, stereo)   start: link, then the steps below. 1, or 0
;    A2dpPoll()                 the pump; call it every millisecond or so.
;                               The state (#A2DP_*).
;    A2dpStreaming()            1 once the sink has accepted START
;    A2dpSend(*frames, count)   one media packet of `count` SBC frames
;                               (each SbcFrameBytes() long, back to back).
;                               1, or 0 if the controller had no buffer -
;                               keep them and try again on the next poll
;    A2dpPause() / A2dpResume() AVDTP SUSPEND / START
;    A2dpEnd()                  suspend, close the link
;    A2dpWhy()                  a sentence once A2dpPoll says FAILED
;
;  PROVEN ON THE PI 4, 2026-10-16 (RaspberryPi4/Examples/Diagnostics/
;  pi4BtProbe.pi4): Ron's headset paired fresh, kept its key (hci.pbi's
;  bond) and reconnected on it without pairing again; link + L2CAP + AVDTP
;  set up in 0.5-1.4 s; a 1 kHz tone, 1,250 packets in 9.8 s, no waits for
;  a controller buffer - "now thats a steady tone". THE CALLER'S CACHES MUST
;  BE ON: with them off the SBC encoder ran at 39% of real time and the
;  headset played the starved stream as a pulse.
;
;  ---- THE SEQUENCE (AVDTP 1.3 ch. 8; A2DP 1.3 ch. 4) --------------------
;    ACL link (hci.pbi, pairing answered there) -> L2CAP PSM $19, the
;    signalling channel -> DISCOVER (1): the first audio SINK endpoint
;    not in use -> GET_CAPABILITIES (2) (the answer is not read: the NES
;    plugin never needed it) -> SET_CONFIGURATION (3): media transport,
;    and SBC 48 kHz, mono or (duplicated) stereo, 16 blocks, 8 subbands,
;    loudness, bitpool 28..28 -> OPEN (6) -> a second L2CAP channel on
;    PSM $19, the media channel -> START (7) -> streaming.
;    A signalling header is: transaction label << 4 | packet type 0
;    (single) << 2 | message type (0 command, 2 accept, 3 reject), then
;    the signal id. Commands FROM the sink are not answered (the NES
;    plugin did not either); they are counted.
;  ---- A MEDIA PACKET -----------------------------------------------------
;    RTP (RFC 3550): $80, payload type 96, sequence (BE), timestamp (BE,
;    +128 a frame at 48 kHz), SSRC "PMNS"; then the SBC payload header
;    (the frame count) and the frames.
; ======================================================================

EnableExplicit

#A2DP_IDLE      = 0
#A2DP_LINK      = 1
#A2DP_SIGNAL    = 2
#A2DP_DISCOVER  = 3
#A2DP_CAPS      = 4
#A2DP_CONFIG    = 5
#A2DP_OPEN      = 6
#A2DP_MEDIA     = 7
#A2DP_START     = 8
#A2DP_STREAMING = 9
#A2DP_PAUSED    = 10
#A2DP_FAILED    = 11

#AVDTP_DISCOVER   = 1
#AVDTP_GET_CAPS   = 2
#AVDTP_SET_CONFIG = 3
#AVDTP_OPEN       = 6
#AVDTP_START      = 7
#AVDTP_SUSPEND    = 9

#A2DP_LINK_MS = 15000          ; paging and pairing
#A2DP_STEP_MS = 5000           ; each signalling step

Global a2dp_state.i
Global a2dp_stereo.i
Global a2dp_sig.i = -1
Global a2dp_media.i = -1
Global a2dp_seid.i
Global a2dp_label.i
Global a2dp_pending.i          ; the signal id we wait for an answer to
Global a2dp_deadline.i
Global a2dp_why.i
Global a2dp_failStep.i         ; the state it failed in
Global a2dp_failCode.i         ; the reject's error code, the link's reason
Global a2dp_peerCommands.i
Global a2dp_seq.i
Global a2dp_ts.i
Global a2dp_packets.i
Global Dim a2dp_tx.a[1024]
Global Dim a2dp_addr.a[6]

Procedure a2dp_Fail(why.i, code.i)
  a2dp_failStep = a2dp_state
  a2dp_failCode = code
  a2dp_why = why
  a2dp_state = #A2DP_FAILED
EndProcedure

Procedure a2dp_Step(state.i, ms.i)
  a2dp_state = state
  a2dp_deadline = HciDeadline(ms)
EndProcedure

; A signalling command: header, signal, then n bytes already at a2dp_tx[2].
Procedure.i a2dp_Command(signal.i, n.i)
  a2dp_tx[0] = (a2dp_label & 15) << 4
  a2dp_tx[1] = signal
  a2dp_label = a2dp_label + 1
  a2dp_pending = signal
  ProcedureReturn L2Send(a2dp_sig, @a2dp_tx[0], n + 2)
EndProcedure

Procedure a2dp_SetConfiguration()
  a2dp_tx[2] = a2dp_seid << 2           ; ACP SEID
  a2dp_tx[3] = 1 << 2                   ; INT SEID
  a2dp_tx[4] = 1 : a2dp_tx[5] = 0       ; media transport
  a2dp_tx[6] = 7 : a2dp_tx[7] = 6       ; media codec, 6 bytes
  a2dp_tx[8] = 0                        ; audio
  a2dp_tx[9] = 0                        ; SBC
  If a2dp_stereo <> 0
    a2dp_tx[10] = $12                   ; 48 kHz, stereo
  Else
    a2dp_tx[10] = $18                   ; 48 kHz, mono
  EndIf
  a2dp_tx[11] = $15                     ; 16 blocks, 8 subbands, loudness
  a2dp_tx[12] = 28 : a2dp_tx[13] = 28   ; bitpool
  a2dp_Command(#AVDTP_SET_CONFIG, 12)
EndProcedure

; An answer (or a command) on the signalling channel.
Procedure a2dp_SignalIn(*p, n.i)
  Define kind.i, signal.i, i.i, b0.i, b1.i
  If n < 2 : ProcedureReturn : EndIf
  kind = PeekA(*p) & 3
  signal = PeekA(*p + 1) & 63
  If kind = 0
    a2dp_peerCommands = a2dp_peerCommands + 1
    ProcedureReturn
  EndIf
  If signal <> a2dp_pending : ProcedureReturn : EndIf
  If kind = 3
    b0 = 0
    If n >= 3 : b0 = PeekA(*p + n - 1) & $FF : EndIf
    a2dp_Fail("the speaker refused a step of setting up the audio stream (AVDTP reject)", b0)
    ProcedureReturn
  EndIf
  If kind <> 2 : ProcedureReturn : EndIf
  a2dp_pending = 0
  Select signal
    Case #AVDTP_DISCOVER
      a2dp_seid = 0
      i = 2
      While i + 1 < n And a2dp_seid = 0
        b0 = PeekA(*p + i) & $FF
        b1 = PeekA(*p + i + 1) & $FF
        If (b1 & $F8) = 8 And (b0 & 2) = 0  ; audio, sink, not in use
          a2dp_seid = b0 >> 2
        EndIf
        i = i + 2
      Wend
      If a2dp_seid = 0
        a2dp_Fail("the device offers no free audio sink (it is not a speaker or headset, or another source holds it)", 0)
        ProcedureReturn
      EndIf
      a2dp_tx[2] = a2dp_seid << 2
      a2dp_Command(#AVDTP_GET_CAPS, 1)
      a2dp_Step(#A2DP_CAPS, #A2DP_STEP_MS)
    Case #AVDTP_GET_CAPS
      a2dp_SetConfiguration()
      a2dp_Step(#A2DP_CONFIG, #A2DP_STEP_MS)
    Case #AVDTP_SET_CONFIG
      a2dp_tx[2] = a2dp_seid << 2
      a2dp_Command(#AVDTP_OPEN, 1)
      a2dp_Step(#A2DP_OPEN, #A2DP_STEP_MS)
    Case #AVDTP_OPEN
      a2dp_media = L2Connect(#L2_PSM_AVDTP)
      If a2dp_media < 0
        a2dp_Fail("the media channel could not be requested", 0)
        ProcedureReturn
      EndIf
      a2dp_Step(#A2DP_MEDIA, #A2DP_STEP_MS)
    Case #AVDTP_START
      a2dp_state = #A2DP_STREAMING
    Case #AVDTP_SUSPEND
      a2dp_state = #A2DP_PAUSED
  EndSelect
EndProcedure

; l2cap.pbi's data sink: only the signalling channel says anything to us.
Procedure a2dp_DataIn(ch.i, *p, n.i)
  If ch = a2dp_sig : a2dp_SignalIn(*p, n) : EndIf
EndProcedure

Procedure.i A2dpBegin(*addr, stereo.i)
  Define i.i
  a2dp_why = 0
  a2dp_failCode = 0
  a2dp_sig = -1
  a2dp_media = -1
  a2dp_seid = 0
  a2dp_pending = 0
  a2dp_stereo = stereo
  a2dp_seq = 0
  a2dp_ts = 0
  a2dp_packets = 0
  For i = 0 To 5 : a2dp_addr[i] = PeekA(*addr + i) : Next
  L2Init()
  *l2_dataIn = @a2dp_DataIn
  a2dp_state = #A2DP_IDLE
  If HciConnect(*addr) = 0
    a2dp_Fail(HciWhy(), HciError())
    ProcedureReturn 0
  EndIf
  a2dp_Step(#A2DP_LINK, #A2DP_LINK_MS)
  ProcedureReturn 1
EndProcedure

Procedure.i A2dpPoll()
  HciPoll()
  If a2dp_state = #A2DP_IDLE Or a2dp_state = #A2DP_FAILED : ProcedureReturn a2dp_state : EndIf
  If HciLinkState() = #HCI_LINK_NONE
    a2dp_Fail("the Bluetooth link to the speaker could not be made or went down (the controller's reason is the code)", HciLinkStatus())
    ProcedureReturn a2dp_state
  EndIf
  Select a2dp_state
    Case #A2DP_LINK
      If HciLinkState() = #HCI_LINK_UP
        a2dp_sig = L2Connect(#L2_PSM_AVDTP)
        If a2dp_sig < 0
          a2dp_Fail("the signalling channel could not be requested", 0)
          ProcedureReturn a2dp_state
        EndIf
        a2dp_Step(#A2DP_SIGNAL, #A2DP_STEP_MS)
      EndIf
    Case #A2DP_SIGNAL
      If L2State(a2dp_sig) = #L2_ST_OPEN
        a2dp_Command(#AVDTP_DISCOVER, 0)
        a2dp_Step(#A2DP_DISCOVER, #A2DP_STEP_MS)
      ElseIf L2State(a2dp_sig) = #L2_ST_FAILED
        a2dp_Fail("the speaker refused the audio signalling channel (L2CAP result is the code)", L2Result(a2dp_sig))
      EndIf
    Case #A2DP_MEDIA
      If L2State(a2dp_media) = #L2_ST_OPEN
        a2dp_tx[2] = a2dp_seid << 2
        a2dp_Command(#AVDTP_START, 1)
        a2dp_Step(#A2DP_START, #A2DP_STEP_MS)
      ElseIf L2State(a2dp_media) = #L2_ST_FAILED
        a2dp_Fail("the speaker refused the audio media channel (L2CAP result is the code)", L2Result(a2dp_media))
      EndIf
  EndSelect
  If a2dp_state <> #A2DP_STREAMING And a2dp_state <> #A2DP_PAUSED And a2dp_state <> #A2DP_FAILED
    If Ticks() > a2dp_deadline
      a2dp_Fail("the speaker did not answer a step of setting up the audio stream in time", 0)
    EndIf
  EndIf
  ProcedureReturn a2dp_state
EndProcedure

Procedure.i A2dpState() : ProcedureReturn a2dp_state : EndProcedure
Procedure.i A2dpStreaming() : ProcedureReturn Bool(a2dp_state = #A2DP_STREAMING) : EndProcedure
Procedure.i A2dpPackets() : ProcedureReturn a2dp_packets : EndProcedure
Procedure.i A2dpFailStep() : ProcedureReturn a2dp_failStep : EndProcedure
Procedure.i A2dpFailCode() : ProcedureReturn a2dp_failCode : EndProcedure
Procedure.i A2dpPeerCommands() : ProcedureReturn a2dp_peerCommands : EndProcedure

Procedure.i A2dpWhy()
  If a2dp_why = 0 : ProcedureReturn "nothing has gone wrong" : EndIf
  ProcedureReturn a2dp_why
EndProcedure

; Bytes in one SBC frame of this stream (sbc.pbi's sizes).
Procedure.i A2dpFrameBytes()
  If a2dp_stereo <> 0 : ProcedureReturn 68 : EndIf
  ProcedureReturn 64
EndProcedure

Procedure.i A2dpSend(*frames, count.i)
  Define n.i, i.i
  If a2dp_state <> #A2DP_STREAMING : ProcedureReturn 0 : EndIf
  n = count * A2dpFrameBytes()
  If count < 1 Or count > 15 Or n + 13 > 1024 : ProcedureReturn 0 : EndIf
  a2dp_tx[0] = $80
  a2dp_tx[1] = 96
  a2dp_tx[2] = (a2dp_seq >> 8) & $FF
  a2dp_tx[3] = a2dp_seq & $FF
  a2dp_tx[4] = (a2dp_ts >> 24) & $FF
  a2dp_tx[5] = (a2dp_ts >> 16) & $FF
  a2dp_tx[6] = (a2dp_ts >> 8) & $FF
  a2dp_tx[7] = a2dp_ts & $FF
  a2dp_tx[8] = $50 : a2dp_tx[9] = $4D : a2dp_tx[10] = $4E : a2dp_tx[11] = $53
  a2dp_tx[12] = count
  For i = 0 To n - 1 : a2dp_tx[13 + i] = PeekA(*frames + i) : Next
  If L2Send(a2dp_media, @a2dp_tx[0], n + 13) = 0 : ProcedureReturn 0 : EndIf
  a2dp_ts = (a2dp_ts + 128 * count) & $FFFFFFFF
  a2dp_seq = (a2dp_seq + 1) & $FFFF
  a2dp_packets = a2dp_packets + 1
  ProcedureReturn 1
EndProcedure

Procedure A2dpPause()
  If a2dp_state <> #A2DP_STREAMING : ProcedureReturn : EndIf
  a2dp_tx[2] = a2dp_seid << 2
  a2dp_Command(#AVDTP_SUSPEND, 1)
EndProcedure

Procedure A2dpResume()
  If a2dp_state <> #A2DP_PAUSED : ProcedureReturn : EndIf
  a2dp_tx[2] = a2dp_seid << 2
  a2dp_Command(#AVDTP_START, 1)
EndProcedure

Procedure A2dpEnd()
  If a2dp_state = #A2DP_STREAMING
    a2dp_tx[2] = a2dp_seid << 2
    a2dp_Command(#AVDTP_SUSPEND, 1)
  EndIf
  HciDisconnect()
  a2dp_state = #A2DP_IDLE
EndProcedure
