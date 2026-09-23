; CYW43 SDPCM receive-glom parser.
; Adapted from Linux brcmfmac sdio.c/bcmsdh.c receive-glom semantics:
; Copyright (c) 2010 Broadcom Corporation, ISC license.
; See licenses/Broadcom-brcmfmac-ISC.txt and docs/THIRD_PARTY_NOTICES.md.
;
; This file owns no register and performs no I/O.  A transport first hands it
; the complete channel-3 descriptor.  If that descriptor is valid,
; Cyw43RxGlomReadPtr()/Cyw43RxGlomReadBytes() name one bounded buffer and the
; exact number of F2 bytes to read.  Only after that whole read has completed
; does Cyw43RxGlomAcceptSuperframe() validate every embedded header and expose
; any frame.  Thus an invalid late subframe cannot cause an earlier subframe
; from the same aggregate to be delivered.
;
; The limits and layout are from Linux brcmfmac 6.12:
;   brcmfmac/bcmsdh.c BRCMF_DEFAULT_RXGLOM_SIZE = 32
;   brcmfmac/sdio.c   MAX_DATA_BUF = 32 * 1024
;   brcmfmac/sdio.c   SDPCM_GLOMDESC, brcmf_sdio_rxglom()
; The first descriptor length includes the outer superframe header and the
; first inner frame.  Later lengths each hold one inner frame.  The final F2
; read is rounded to the negotiated function-2 block size; padding is never
; exposed as a packet.

#CYW43_RXG_MAX_FRAMES = 32
#CYW43_RXG_MAX_BYTES  = 32768
#CYW43_RXG_SDPCM_HDR  = 12
#CYW43_RXG_FRAME_MAX  = 2048

#CYW43_RXG_CH_CONTROL = 0
#CYW43_RXG_CH_EVENT   = 1
#CYW43_RXG_CH_DATA    = 2
#CYW43_RXG_CH_GLOM    = 3
#CYW43_RXG_CH_MASK    = $0F
#CYW43_RXG_DESC_FLAG  = $80

#CYW43_RXG_OK             = 1
#CYW43_RXG_E_NULL         = -1
#CYW43_RXG_E_DESCRIPTOR   = -2
#CYW43_RXG_E_COUNT        = -3
#CYW43_RXG_E_LENGTH       = -4
#CYW43_RXG_E_ALIGNMENT    = -5
#CYW43_RXG_E_CAPACITY     = -6
#CYW43_RXG_E_READ_LENGTH  = -7
#CYW43_RXG_E_SUPER_HEADER = -8
#CYW43_RXG_E_SUB_HEADER   = -9
#CYW43_RXG_E_CHANNEL      = -10
#CYW43_RXG_E_OFFSET       = -11

Global Dim cyw43_rxg_buf.a[#CYW43_RXG_MAX_BYTES]
Global Dim cyw43_rxg_seg.i[#CYW43_RXG_MAX_FRAMES]
Global Dim cyw43_rxg_off.i[#CYW43_RXG_MAX_FRAMES]
Global Dim cyw43_rxg_len.i[#CYW43_RXG_MAX_FRAMES]
Global Dim cyw43_rxg_doff.i[#CYW43_RXG_MAX_FRAMES]
Global Dim cyw43_rxg_chan.i[#CYW43_RXG_MAX_FRAMES]
Global Dim cyw43_rxg_seq.i[#CYW43_RXG_MAX_FRAMES]

Global cyw43_rxg_descReady.i = 0
Global cyw43_rxg_superReady.i = 0
Global cyw43_rxg_count.i = 0
Global cyw43_rxg_wire.i = 0
Global cyw43_rxg_sum.i = 0
Global cyw43_rxg_block.i = 0
Global cyw43_rxg_align.i = 0
Global cyw43_rxg_next.i = 0
Global cyw43_rxg_nextMismatch.i = 0
Global cyw43_rxg_outerLen.i = 0
Global cyw43_rxg_outerSeq.i = 0
Global cyw43_rxg_outerFlow.i = 0
Global cyw43_rxg_outerWindow.i = 0
Global cyw43_rxg_lastError.i = 0

Procedure.i cyw43_rxg_U8(*p)
  ProcedureReturn PeekA(*p) & $FF
EndProcedure

Procedure.i cyw43_rxg_LE16(*p)
  ProcedureReturn (PeekA(*p) & $FF) | ((PeekA(*p + 1) & $FF) << 8)
EndProcedure

Procedure.i cyw43_rxg_RoundUp(n.i, unit.i)
  ProcedureReturn ((n + unit - 1) / unit) * unit
EndProcedure

Procedure.i cyw43_rxg_HeaderOk(*p, available.i)
  Define n.i
  Define c.i
  If *p = 0 Or available < #CYW43_RXG_SDPCM_HDR
    ProcedureReturn 0
  EndIf
  n = cyw43_rxg_LE16(*p)
  c = cyw43_rxg_LE16(*p + 2)
  If (n ! c) <> $FFFF
    ProcedureReturn 0
  EndIf
  If n < #CYW43_RXG_SDPCM_HDR Or n > available
    ProcedureReturn 0
  EndIf
  ProcedureReturn n
EndProcedure

Procedure.i cyw43_rxg_Fail(code.i)
  cyw43_rxg_descReady = 0
  cyw43_rxg_superReady = 0
  cyw43_rxg_count = 0
  cyw43_rxg_wire = 0
  cyw43_rxg_sum = 0
  cyw43_rxg_block = 0
  cyw43_rxg_align = 0
  cyw43_rxg_next = 0
  cyw43_rxg_nextMismatch = 0
  cyw43_rxg_outerLen = 0
  cyw43_rxg_outerSeq = 0
  cyw43_rxg_outerFlow = 0
  cyw43_rxg_outerWindow = 0
  cyw43_rxg_lastError = code
  ProcedureReturn code
EndProcedure

Procedure Cyw43RxGlomReset()
  cyw43_rxg_descReady = 0
  cyw43_rxg_superReady = 0
  cyw43_rxg_count = 0
  cyw43_rxg_wire = 0
  cyw43_rxg_sum = 0
  cyw43_rxg_block = 0
  cyw43_rxg_align = 0
  cyw43_rxg_next = 0
  cyw43_rxg_nextMismatch = 0
  cyw43_rxg_outerLen = 0
  cyw43_rxg_outerSeq = 0
  cyw43_rxg_outerFlow = 0
  cyw43_rxg_outerWindow = 0
  cyw43_rxg_lastError = 0
EndProcedure

; Validate the complete descriptor before retaining any of its lengths.
; `bytes` is the descriptor's declared SDPCM length, not its word padding.
; `blockBytes` is the negotiated F2 block size and `entryAlign` is the SDIO
; scatter-entry alignment (four on BCM2711/CYW43455).
Procedure.i Cyw43RxGlomLoadDescriptor(*frame, bytes.i, blockBytes.i, entryAlign.i)
  Define declared.i
  Define rawchan.i
  Define doff.i
  Define payload.i
  Define count.i
  Define i.i
  Define n.i
  Define total.i
  Define wire.i

  Cyw43RxGlomReset()
  If *frame = 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_NULL)
  EndIf
  If bytes < (#CYW43_RXG_SDPCM_HDR + 2)
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_DESCRIPTOR)
  EndIf
  If blockBytes < 4 Or blockBytes > 512 Or (blockBytes & 3) <> 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_ALIGNMENT)
  EndIf
  If entryAlign < 4 Or entryAlign > blockBytes Or (entryAlign & 3) <> 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_ALIGNMENT)
  EndIf

  declared = cyw43_rxg_HeaderOk(*frame, bytes)
  If declared <> bytes
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_DESCRIPTOR)
  EndIf
  rawchan = cyw43_rxg_U8(*frame + 5)
  If (rawchan & #CYW43_RXG_CH_MASK) <> #CYW43_RXG_CH_GLOM
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_CHANNEL)
  EndIf
  If (rawchan & #CYW43_RXG_DESC_FLAG) = 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_DESCRIPTOR)
  EndIf
  doff = cyw43_rxg_U8(*frame + 7)
  If doff <> #CYW43_RXG_SDPCM_HDR
    ; brcmf_sdio_readframes removes exactly SDPCM_HDRLEN from a glom
    ; descriptor, not a variable data offset.  Refuse an ambiguous list.
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_OFFSET)
  EndIf

  payload = declared - #CYW43_RXG_SDPCM_HDR
  If payload < 2 Or (payload & 1) <> 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_DESCRIPTOR)
  EndIf
  count = payload / 2
  If count < 1 Or count > #CYW43_RXG_MAX_FRAMES
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_COUNT)
  EndIf

  ; First pass: no state becomes consumable until every entry is sound.
  total = 0
  For i = 0 To count - 1
    n = cyw43_rxg_LE16(*frame + #CYW43_RXG_SDPCM_HDR + (i * 2))
    If n < #CYW43_RXG_SDPCM_HDR
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_LENGTH)
    EndIf
    If i = 0 And n < (#CYW43_RXG_SDPCM_HDR * 2)
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_LENGTH)
    EndIf
    If (n % entryAlign) <> 0
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_ALIGNMENT)
    EndIf
    If total > (#CYW43_RXG_MAX_BYTES - n)
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_CAPACITY)
    EndIf
    total = total + n
  Next
  wire = cyw43_rxg_RoundUp(total, blockBytes)
  If wire < total Or wire > #CYW43_RXG_MAX_BYTES
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_CAPACITY)
  EndIf

  ; Second pass: commit the validated list.
  For i = 0 To count - 1
    cyw43_rxg_seg[i] = cyw43_rxg_LE16(*frame + #CYW43_RXG_SDPCM_HDR + (i * 2))
  Next
  cyw43_rxg_count = count
  cyw43_rxg_sum = total
  cyw43_rxg_wire = wire
  cyw43_rxg_block = blockBytes
  cyw43_rxg_align = entryAlign
  cyw43_rxg_next = cyw43_rxg_U8(*frame + 6) * 16
  cyw43_rxg_nextMismatch = 0
  If cyw43_rxg_next <> 0 And cyw43_rxg_next <> wire
    ; Linux logs this mismatch and trusts the fully validated descriptor.
    ; Keeping that policy avoids rejecting a valid aggregate merely because
    ; the eight-bit read-ahead hint cannot represent a large superframe.
    cyw43_rxg_nextMismatch = 1
  EndIf
  cyw43_rxg_descReady = 1
  cyw43_rxg_lastError = 0
  ProcedureReturn #CYW43_RXG_OK
EndProcedure

; Validate a complete F2 superframe already read into Cyw43RxGlomReadPtr().
; All subframes are checked in a first pass and published only in a second.
Procedure.i Cyw43RxGlomAcceptSuperframe(bytesRead.i)
  Define *base
  Define outerLen.i
  Define rawchan.i
  Define outerOff.i
  Define segmentStart.i
  Define segmentEnd.i
  Define frameStart.i
  Define available.i
  Define frameLen.i
  Define frameOff.i
  Define channel.i
  Define i.i

  cyw43_rxg_superReady = 0
  If cyw43_rxg_descReady = 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_DESCRIPTOR)
  EndIf
  If bytesRead <> cyw43_rxg_wire
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_READ_LENGTH)
  EndIf
  *base = @cyw43_rxg_buf[0]
  outerLen = cyw43_rxg_HeaderOk(*base, bytesRead)
  If outerLen < (#CYW43_RXG_SDPCM_HDR * 2)
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_SUPER_HEADER)
  EndIf
  If cyw43_rxg_RoundUp(outerLen, cyw43_rxg_block) <> bytesRead
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_SUPER_HEADER)
  EndIf
  If outerLen > cyw43_rxg_sum
    ; Bytes declared meaningful by the outer header must all belong to a
    ; descriptor segment.  The reverse inequality is allowed because the
    ; descriptor's final segment may include negotiated alignment padding.
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_SUPER_HEADER)
  EndIf
  rawchan = cyw43_rxg_U8(*base + 5)
  If (rawchan & #CYW43_RXG_CH_MASK) <> #CYW43_RXG_CH_GLOM Or (rawchan & #CYW43_RXG_DESC_FLAG) <> 0
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_CHANNEL)
  EndIf
  outerOff = cyw43_rxg_U8(*base + 7)
  If outerOff < #CYW43_RXG_SDPCM_HDR Or outerOff >= cyw43_rxg_seg[0]
    ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_OFFSET)
  EndIf

  ; First pass over every inner header.  Segment limits come from the
  ; descriptor; outerLen is a second independent bound over meaningful bytes.
  segmentStart = 0
  For i = 0 To cyw43_rxg_count - 1
    segmentEnd = segmentStart + cyw43_rxg_seg[i]
    If segmentEnd > outerLen
      segmentEnd = outerLen
    EndIf
    If i = 0
      frameStart = outerOff
    Else
      frameStart = segmentStart
    EndIf
    available = segmentEnd - frameStart
    frameLen = cyw43_rxg_HeaderOk(*base + frameStart, available)
    If frameLen = 0 Or frameLen > #CYW43_RXG_FRAME_MAX
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_SUB_HEADER)
    EndIf
    channel = cyw43_rxg_U8(*base + frameStart + 5) & #CYW43_RXG_CH_MASK
    If channel <> #CYW43_RXG_CH_DATA And channel <> #CYW43_RXG_CH_EVENT
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_CHANNEL)
    EndIf
    frameOff = cyw43_rxg_U8(*base + frameStart + 7)
    If frameOff < #CYW43_RXG_SDPCM_HDR Or frameOff > frameLen
      ProcedureReturn cyw43_rxg_Fail(#CYW43_RXG_E_OFFSET)
    EndIf
    segmentStart = segmentStart + cyw43_rxg_seg[i]
  Next

  ; Second pass publishes immutable coordinates into the raw aggregate.
  segmentStart = 0
  For i = 0 To cyw43_rxg_count - 1
    If i = 0
      frameStart = outerOff
    Else
      frameStart = segmentStart
    EndIf
    frameLen = cyw43_rxg_LE16(*base + frameStart)
    cyw43_rxg_off[i] = frameStart
    cyw43_rxg_len[i] = frameLen
    cyw43_rxg_doff[i] = cyw43_rxg_U8(*base + frameStart + 7)
    cyw43_rxg_chan[i] = cyw43_rxg_U8(*base + frameStart + 5) & #CYW43_RXG_CH_MASK
    cyw43_rxg_seq[i] = cyw43_rxg_U8(*base + frameStart + 4)
    segmentStart = segmentStart + cyw43_rxg_seg[i]
  Next

  cyw43_rxg_outerLen = outerLen
  cyw43_rxg_outerSeq = cyw43_rxg_U8(*base + 4)
  cyw43_rxg_outerFlow = cyw43_rxg_U8(*base + 8)
  cyw43_rxg_outerWindow = cyw43_rxg_U8(*base + 9)
  cyw43_rxg_descReady = 0
  cyw43_rxg_superReady = 1
  cyw43_rxg_lastError = 0
  ProcedureReturn #CYW43_RXG_OK
EndProcedure

Procedure.i Cyw43RxGlomReadPtr()
  If cyw43_rxg_descReady = 0 And cyw43_rxg_superReady = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn @cyw43_rxg_buf[0]
EndProcedure

Procedure.i Cyw43RxGlomReadBytes()
  If cyw43_rxg_descReady = 0 And cyw43_rxg_superReady = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn cyw43_rxg_wire
EndProcedure

Procedure.i Cyw43RxGlomDescriptorFrames()
  ProcedureReturn cyw43_rxg_count
EndProcedure

Procedure.i Cyw43RxGlomDescriptorBytes()
  ProcedureReturn cyw43_rxg_sum
EndProcedure

Procedure.i Cyw43RxGlomDescriptorNextBytes()
  ProcedureReturn cyw43_rxg_next
EndProcedure

Procedure.i Cyw43RxGlomDescriptorNextMismatch()
  ProcedureReturn cyw43_rxg_nextMismatch
EndProcedure

Procedure.i Cyw43RxGlomReady()
  ProcedureReturn cyw43_rxg_superReady
EndProcedure

Procedure.i Cyw43RxGlomFrameCount()
  If cyw43_rxg_superReady = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn cyw43_rxg_count
EndProcedure

Procedure.i Cyw43RxGlomFramePtr(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn @cyw43_rxg_buf[0] + cyw43_rxg_off[index]
EndProcedure

Procedure.i Cyw43RxGlomFrameBytes(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn cyw43_rxg_len[index]
EndProcedure

Procedure.i Cyw43RxGlomPayloadPtr(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn @cyw43_rxg_buf[0] + cyw43_rxg_off[index] + cyw43_rxg_doff[index]
EndProcedure

Procedure.i Cyw43RxGlomPayloadBytes(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn cyw43_rxg_len[index] - cyw43_rxg_doff[index]
EndProcedure

Procedure.i Cyw43RxGlomFrameChannel(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn -1
  EndIf
  ProcedureReturn cyw43_rxg_chan[index]
EndProcedure

Procedure.i Cyw43RxGlomFrameSequence(index.i)
  If cyw43_rxg_superReady = 0 Or index < 0 Or index >= cyw43_rxg_count
    ProcedureReturn -1
  EndIf
  ProcedureReturn cyw43_rxg_seq[index]
EndProcedure

Procedure.i Cyw43RxGlomOuterLength()
  ProcedureReturn cyw43_rxg_outerLen
EndProcedure

Procedure.i Cyw43RxGlomOuterSequence()
  ProcedureReturn cyw43_rxg_outerSeq
EndProcedure

Procedure.i Cyw43RxGlomOuterFlowControl()
  ProcedureReturn cyw43_rxg_outerFlow
EndProcedure

Procedure.i Cyw43RxGlomOuterWindow()
  ProcedureReturn cyw43_rxg_outerWindow
EndProcedure

Procedure.i Cyw43RxGlomLastError()
  ProcedureReturn cyw43_rxg_lastError
EndProcedure
