; ======================================================================
;  gnss.pbi - a GNSS receiver's stream: where it comes from, its frames, and
;  the fix in it. For the HwGnss* seam (Anvil/Hal/hal.pbi) and the `gnss`
;  command; RaspberryPi4/Board/hw_gnss.pi4 is the seam over this file.
;
;  SOURCES, AS GNSS BRIDGE HAS THEM. The Android app reads a receiver from
;  USB, Bluetooth (classic, SPP), Bluetooth LE (the Nordic UART service the
;  GNSS Bridge Pico speaks) or the network (a TCP stream). Anvil does the
;  same, one source at a time:
;    #GNSS_SRC_USB        LIVE: a CDC-ACM receiver or a USB-to-serial bridge
;                         (FTDI, Prolific, Silicon Labs, WCH) - Lib/usbserial.pi4
;    #GNSS_SRC_BLUETOOTH  PLACEHOLDER: an SPP link over Anvil/Net/hci.pbi
;    #GNSS_SRC_BLE        PLACEHOLDER: the Nordic UART service, as a GNSS
;                         Bridge Pico serves it
;    #GNSS_SRC_NETWORK    PLACEHOLDER: a TCP stream (a GNSS Bridge on Wi-Fi,
;                         an NTRIP caster's NMEA, gpsd's JSON)
;  A placeholder is a source this file names and opens with a sentence
;  saying it is not built yet - never a silent nothing. Filling one in is
;  one procedure: give gnss_SrcRead() its bytes.
;
;  FRAMES, AS GNSS BRIDGE FRAMES THEM. The framer below is the GNSS Bridge
;  Pico's gb_frame.gbinc, carried over unchanged but for its names (gnf_):
;  NMEA, UBX, RTCM3, SiRF, Garmin, SBP, BINEX, JSON and Meinberg, with its
;  rule that a protocol whose frames start with one common byte is only
;  taken once it is PROVEN on the stream (three good frames, more good than
;  bad). So every receiver family GNSS Bridge knows - u-blox, MTK, Airoha
;  PAIR, CASIC, Quectel, SiRF, Garmin, Septentrio, Trimble, and gpsd - is
;  framed and counted here.
;
;  THE FIX comes from what every one of those families can send: NMEA
;  (GGA / GNS position, RMC speed course and date, GSV satellites in view)
;  and u-blox UBX NAV-PVT, read by the rules of the GNSS Bridge Pico's
;  NavFrameRead (display.gbinc): NAV-PVT is preferred while it keeps coming
;  (3 s), GGA over GNS, no float anywhere. The other binary protocols are
;  framed and counted but their positions are not read yet - their
;  decoders are the next placeholders (gnss_FrameBinary).
;
;  ONE CALLER. gnss_Pump() is called from one place at a time (the console's
;  `gnss` command, or a payload through the GNSS slots); nothing here is
;  re-entrant, and nothing here waits.
; ======================================================================

#GNSS_SRC_NONE      = 0
#GNSS_SRC_USB       = 1
#GNSS_SRC_BLUETOOTH = 2
#GNSS_SRC_BLE       = 3
#GNSS_SRC_NETWORK   = 4

; ---------------------------------------------------------------- the framer (GNSS Bridge's)
#GNF_NPROTO = 9
#GNF_N      = 2                    ; instance 0 the receiver's stream, 1 the weak-start finder
Global Dim gnf_fr_st.i[#GNF_N]
Global Dim gnf_fr_p.i[#GNF_N]
Global Dim gnf_fr_cnt.l[#GNF_N]
Global Dim gnf_fr_rem.l[#GNF_N]
Global Dim gnf_fr_aux.i[#GNF_N]
Global Dim gnf_fv_a.l[#GNF_N]
Global Dim gnf_fv_b.l[#GNF_N]
Global Dim gnf_fv_x.l[#GNF_N]
Global Dim gnf_fv_bad.i[#GNF_N]
Global gnf_weak_ok.l                  ; bit p: protocol p is proven
Global Dim gnf_weak_good.l[#GNF_NPROTO]
Global Dim gnf_weak_bad.l[#GNF_NPROTO]

Procedure.i GnfHex(c.i)
  If c >= 48 And c <= 57 : ProcedureReturn c - 48 : EndIf
  If c >= 65 And c <= 70 : ProcedureReturn c - 55 : EndIf
  If c >= 97 And c <= 102 : ProcedureReturn c - 87 : EndIf
  ProcedureReturn -1
EndProcedure

Procedure.l GnfCrc16(crc.l, c.i)
  Define n.i
  crc = crc ! ((c & 255) << 8)
  For n = 1 To 8
    If (crc & $8000) <> 0
      crc = ((crc << 1) ! $1021) & $FFFF
    Else
      crc = (crc << 1) & $FFFF
    EndIf
  Next
  ProcedureReturn crc
EndProcedure

Procedure.l GnfCrc24(crc.l, c.i)
  Define n.i
  crc = crc ! ((c & 255) << 16)
  For n = 1 To 8
    If (crc & $800000) <> 0
      crc = ((crc << 1) ! $1864CFB) & $FFFFFF
    Else
      crc = (crc << 1) & $FFFFFF
    EndIf
  Next
  ProcedureReturn crc
EndProcedure

; May instance k take a one-byte start of protocol p?
Procedure.i GnfWeak(k.i, p.i)
  If k = 1
    If (gnf_weak_ok & (1 << p)) = 0 : ProcedureReturn 1 : EndIf
    ProcedureReturn 0
  EndIf
  If (gnf_weak_ok & (1 << p)) <> 0 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure GnfReset(k.i)
  gnf_fr_st[k] = 0
EndProcedure

Procedure.i GnfStep(k.i, c.i)
  Define h.i
  Define s.i
  s = gnf_fr_st[k]
  If s = 0
    If k <> 1
      If c = 36 Or c = 33
        gnf_fr_st[k] = 1 : gnf_fr_p[k] = 0 : gnf_fr_cnt[k] = 0
        gnf_fv_a[k] = 0 : gnf_fv_b[k] = 0 : gnf_fv_x[k] = 0
        ProcedureReturn 0
      ElseIf c = $B5
        gnf_fr_st[k] = 2 : gnf_fr_p[k] = 1
        ProcedureReturn 0
      ElseIf c = $D3
        gnf_fr_st[k] = 5 : gnf_fr_p[k] = 2
        gnf_fv_a[k] = GnfCrc24(0, c)
        ProcedureReturn 0
      ElseIf c = $A0
        gnf_fr_st[k] = 8 : gnf_fr_p[k] = 3
        ProcedureReturn 0
      EndIf
    EndIf
    If c = $10
      If GnfWeak(k, 4) = 1
        gnf_fr_st[k] = 16 : gnf_fr_p[k] = 4 : gnf_fv_bad[k] = 0
      EndIf
    ElseIf c = $55
      If GnfWeak(k, 5) = 1
        gnf_fr_st[k] = 25 : gnf_fr_p[k] = 5 : gnf_fr_cnt[k] = 0 : gnf_fv_a[k] = 0
      EndIf
    ElseIf c = $C2 Or c = $E2
      If GnfWeak(k, 6) = 1
        gnf_fr_st[k] = 29 : gnf_fr_p[k] = 6 : gnf_fr_aux[k] = 0
        If c = $E2 : gnf_fr_aux[k] = 1 : EndIf
        gnf_fv_a[k] = 0 : gnf_fv_x[k] = 0
      EndIf
    ElseIf c = 123
      If GnfWeak(k, 7) = 1
        gnf_fr_st[k] = 34 : gnf_fr_p[k] = 7 : gnf_fr_cnt[k] = 0 : gnf_fv_b[k] = c : gnf_fv_bad[k] = 0
      EndIf
    ElseIf c = 2
      If GnfWeak(k, 8) = 1
        gnf_fr_st[k] = 35 : gnf_fr_p[k] = 8 : gnf_fr_cnt[k] = 0 : gnf_fv_bad[k] = 0
      EndIf
    EndIf
    ProcedureReturn 0
  EndIf
  Select s
    ; ---- NMEA: gnf_fv_b 0 before the *, 1 and 2 = hex digits taken, 9 = spoiled ----
    Case 1
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      If c = 42 And gnf_fv_b[k] = 0
        gnf_fv_b[k] = 1
      ElseIf gnf_fv_b[k] = 0
        If c <> 13 And c <> 10 : gnf_fv_a[k] = gnf_fv_a[k] ! c : EndIf
      ElseIf c <> 13 And c <> 10
        h = GnfHex(c)
        If h < 0 Or gnf_fv_b[k] > 2
          gnf_fv_b[k] = 9
        Else
          gnf_fv_x[k] = (gnf_fv_x[k] << 4) | h
          gnf_fv_b[k] = gnf_fv_b[k] + 1
        EndIf
      EndIf
      If c = 10
        gnf_fr_st[k] = 0
        If gnf_fv_b[k] = 3 And gnf_fv_x[k] = (gnf_fv_a[k] & 255) : ProcedureReturn 1 : EndIf
        ProcedureReturn 2
      ElseIf gnf_fr_cnt[k] > 1000
        gnf_fr_st[k] = 0
        ProcedureReturn 2
      EndIf
    ; ---- UBX ----
    Case 2
      If c = $62
        gnf_fr_st[k] = 3 : gnf_fr_cnt[k] = 0 : gnf_fr_rem[k] = 0
        gnf_fv_a[k] = 0 : gnf_fv_b[k] = 0 : gnf_fv_bad[k] = 0
      ElseIf c <> $B5
        gnf_fr_st[k] = 0
      EndIf
    Case 3
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255 : gnf_fv_b[k] = (gnf_fv_b[k] + gnf_fv_a[k]) & 255
      If gnf_fr_cnt[k] = 3
        gnf_fr_rem[k] = c
      ElseIf gnf_fr_cnt[k] = 4
        gnf_fr_rem[k] = gnf_fr_rem[k] | (c << 8)
        If gnf_fr_rem[k] > 8192
          gnf_fr_st[k] = 0
        Else
          gnf_fr_rem[k] = gnf_fr_rem[k] + 2
          gnf_fr_st[k] = 4
        EndIf
      EndIf
    Case 4
      If gnf_fr_rem[k] > 2
        gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255 : gnf_fv_b[k] = (gnf_fv_b[k] + gnf_fv_a[k]) & 255
      ElseIf gnf_fr_rem[k] = 2
        If c <> gnf_fv_a[k] : gnf_fv_bad[k] = 1 : EndIf
      Else
        If c <> gnf_fv_b[k] : gnf_fv_bad[k] = 1 : EndIf
      EndIf
      gnf_fr_rem[k] = gnf_fr_rem[k] - 1
      If gnf_fr_rem[k] <= 0
        gnf_fr_st[k] = 0
        ProcedureReturn 1 + gnf_fv_bad[k]
      EndIf
    ; ---- RTCM3 ----
    Case 5
      If (c & $FC) <> 0
        gnf_fr_st[k] = 0
      Else
        gnf_fr_rem[k] = (c & 3) << 8
        gnf_fr_st[k] = 6
        gnf_fv_a[k] = GnfCrc24(gnf_fv_a[k], c)
      EndIf
    Case 6
      gnf_fr_rem[k] = (gnf_fr_rem[k] | c) + 3
      gnf_fr_st[k] = 7
      gnf_fv_a[k] = GnfCrc24(gnf_fv_a[k], c)
    Case 7
      gnf_fv_a[k] = GnfCrc24(gnf_fv_a[k], c)
      gnf_fr_rem[k] = gnf_fr_rem[k] - 1
      If gnf_fr_rem[k] <= 0
        gnf_fr_st[k] = 0
        ; the CRC of a frame with its own CRC behind it is zero
        If gnf_fv_a[k] = 0 : ProcedureReturn 1 : EndIf
        ProcedureReturn 2
      EndIf
    ; ---- SiRF binary ----
    Case 8
      If c = $A2
        gnf_fr_st[k] = 9
      ElseIf c <> $A0
        gnf_fr_st[k] = 0
      EndIf
    Case 9
      If c > $7F
        gnf_fr_st[k] = 0
      Else
        gnf_fr_rem[k] = c << 8
        gnf_fr_st[k] = 10
      EndIf
    Case 10
      gnf_fr_rem[k] = gnf_fr_rem[k] | c
      If gnf_fr_rem[k] = 0 Or gnf_fr_rem[k] > 2047
        gnf_fr_st[k] = 0
      Else
        gnf_fr_st[k] = 11
        gnf_fv_a[k] = 0 : gnf_fv_bad[k] = 0
      EndIf
    Case 11
      gnf_fv_a[k] = (gnf_fv_a[k] + c) & $7FFF
      gnf_fr_rem[k] = gnf_fr_rem[k] - 1
      If gnf_fr_rem[k] <= 0 : gnf_fr_st[k] = 12 : EndIf
    Case 12
      gnf_fv_b[k] = c << 8
      gnf_fr_st[k] = 13
    Case 13
      If (gnf_fv_b[k] | c) <> gnf_fv_a[k] : gnf_fv_bad[k] = 1 : EndIf
      gnf_fr_st[k] = 14
    Case 14
      If c = $B0
        gnf_fr_st[k] = 15
      Else
        gnf_fr_st[k] = 0
        ProcedureReturn 2
      EndIf
    Case 15
      gnf_fr_st[k] = 0
      If c = $B3 : ProcedureReturn 1 + gnf_fv_bad[k] : EndIf
      ProcedureReturn 2
    ; ---- Garmin binary ----
    Case 16
      ; the packet id. DLE DLE and DLE ETX are not the start of a packet.
      If c = $10 Or c = 3
        gnf_fr_st[k] = 0
      Else
        gnf_fv_a[k] = c
        gnf_fr_st[k] = 17
      EndIf
    Case 17
      If c = $10
        gnf_fr_st[k] = 18
      Else
        gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255
        gnf_fr_rem[k] = c
        If c = 0 : gnf_fr_st[k] = 21 : Else : gnf_fr_st[k] = 19 : EndIf
      EndIf
    Case 18
      If c = $10
        gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255
        gnf_fr_rem[k] = 16
        gnf_fr_st[k] = 19
      Else
        gnf_fr_st[k] = 0
      EndIf
    Case 19
      If c = $10
        gnf_fr_st[k] = 20
      Else
        gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255
        gnf_fr_rem[k] = gnf_fr_rem[k] - 1
        If gnf_fr_rem[k] <= 0 : gnf_fr_st[k] = 21 : EndIf
      EndIf
    Case 20
      If c = $10
        gnf_fv_a[k] = (gnf_fv_a[k] + c) & 255
        gnf_fr_rem[k] = gnf_fr_rem[k] - 1
        If gnf_fr_rem[k] <= 0 : gnf_fr_st[k] = 21 : Else : gnf_fr_st[k] = 19 : EndIf
      Else
        ; a single DLE inside the data: the packet is broken off here
        gnf_fr_st[k] = 0
        ProcedureReturn 2
      EndIf
    Case 21
      If c = $10
        gnf_fr_st[k] = 22
      Else
        If ((gnf_fv_a[k] + c) & 255) <> 0 : gnf_fv_bad[k] = 1 : EndIf
        gnf_fr_st[k] = 23
      EndIf
    Case 22
      If c <> $10 Or ((gnf_fv_a[k] + c) & 255) <> 0 : gnf_fv_bad[k] = 1 : EndIf
      gnf_fr_st[k] = 23
    Case 23
      If c = $10
        gnf_fr_st[k] = 24
      Else
        gnf_fr_st[k] = 0
        ProcedureReturn 2
      EndIf
    Case 24
      gnf_fr_st[k] = 0
      If c = 3 : ProcedureReturn 1 + gnf_fv_bad[k] : EndIf
      ProcedureReturn 2
    ; ---- Swift SBP ----
    Case 25
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      gnf_fv_a[k] = GnfCrc16(gnf_fv_a[k], c)
      If gnf_fr_cnt[k] = 5
        gnf_fr_rem[k] = c
        If c = 0 : gnf_fr_st[k] = 27 : Else : gnf_fr_st[k] = 26 : EndIf
      EndIf
    Case 26
      gnf_fv_a[k] = GnfCrc16(gnf_fv_a[k], c)
      gnf_fr_rem[k] = gnf_fr_rem[k] - 1
      If gnf_fr_rem[k] <= 0 : gnf_fr_st[k] = 27 : EndIf
    Case 27
      gnf_fv_b[k] = c
      gnf_fr_st[k] = 28
    Case 28
      gnf_fr_st[k] = 0
      If ((c << 8) | gnf_fv_b[k]) = gnf_fv_a[k] : ProcedureReturn 1 : EndIf
      ProcedureReturn 2
    ; ---- BINEX ----
    Case 29
      ; the record id: one byte (the ids in use are below 128)
      If c > $7F
        gnf_fr_st[k] = 0
      Else
        gnf_fv_a[k] = GnfCrc16(gnf_fv_a[k], c) : gnf_fv_x[k] = gnf_fv_x[k] ! c
        gnf_fr_cnt[k] = 0
        gnf_fr_rem[k] = 0
        gnf_fr_st[k] = 30
      EndIf
    Case 30
      ; the length: 1 to 4 bytes, 7 bits each (the 4th has 8), bit 7 = more
      gnf_fv_a[k] = GnfCrc16(gnf_fv_a[k], c) : gnf_fv_x[k] = gnf_fv_x[k] ! c
      If gnf_fr_aux[k] = 1
        If gnf_fr_cnt[k] < 3
          gnf_fr_rem[k] = (gnf_fr_rem[k] << 7) | (c & $7F)
        Else
          gnf_fr_rem[k] = (gnf_fr_rem[k] << 8) | c
        EndIf
      Else
        If gnf_fr_cnt[k] < 3
          gnf_fr_rem[k] = gnf_fr_rem[k] | ((c & $7F) << (7 * gnf_fr_cnt[k]))
        Else
          gnf_fr_rem[k] = gnf_fr_rem[k] | (c << 21)
        EndIf
      EndIf
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      If (c & $80) = 0 Or gnf_fr_cnt[k] = 4
        ; gnf_fr_cnt becomes the size of id + length + message: it picks the checksum
        gnf_fr_cnt[k] = 1 + gnf_fr_cnt[k] + gnf_fr_rem[k]
        If gnf_fr_cnt[k] > 4095 Or gnf_fr_rem[k] < 0
          gnf_fr_st[k] = 0
        ElseIf gnf_fr_rem[k] = 0
          gnf_fr_st[k] = 32
        Else
          gnf_fr_st[k] = 31
        EndIf
      EndIf
    Case 31
      gnf_fv_a[k] = GnfCrc16(gnf_fv_a[k], c) : gnf_fv_x[k] = gnf_fv_x[k] ! c
      gnf_fr_rem[k] = gnf_fr_rem[k] - 1
      If gnf_fr_rem[k] <= 0 : gnf_fr_st[k] = 32 : EndIf
    Case 32
      If gnf_fr_cnt[k] < 128
        gnf_fr_st[k] = 0
        If c = (gnf_fv_x[k] & 255) : ProcedureReturn 1 : EndIf
        ProcedureReturn 2
      Else
        gnf_fv_b[k] = c
        gnf_fr_st[k] = 33
      EndIf
    Case 33
      gnf_fr_st[k] = 0
      If gnf_fr_aux[k] = 1
        If ((gnf_fv_b[k] << 8) | c) = gnf_fv_a[k] : ProcedureReturn 1 : EndIf
      Else
        If ((c << 8) | gnf_fv_b[k]) = gnf_fv_a[k] : ProcedureReturn 1 : EndIf
      EndIf
      ProcedureReturn 2
    ; ---- a JSON line (gpsd): good = text only, ending in } ----
    Case 34
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      If c = 10
        gnf_fr_st[k] = 0
        If gnf_fv_b[k] = 125 And gnf_fv_bad[k] = 0 : ProcedureReturn 1 : EndIf
        ProcedureReturn 2
      ElseIf gnf_fr_cnt[k] > 2000
        gnf_fr_st[k] = 0
        ProcedureReturn 2
      ElseIf c <> 13
        gnf_fv_b[k] = c
        If c < 32 Or c > 126 : gnf_fv_bad[k] = 1 : EndIf
      EndIf
    ; ---- the Meinberg time string: good = at least 16 characters of text ----
    Case 35
      gnf_fr_cnt[k] = gnf_fr_cnt[k] + 1
      If c = 3
        gnf_fr_st[k] = 0
        If gnf_fr_cnt[k] > 16 And gnf_fv_bad[k] = 0 : ProcedureReturn 1 : EndIf
        ProcedureReturn 2
      ElseIf gnf_fr_cnt[k] > 80
        gnf_fr_st[k] = 0
      ElseIf c < 32 Or c > 126
        gnf_fv_bad[k] = 1
      EndIf
  EndSelect
  ProcedureReturn 0
EndProcedure


; ---------------------------------------------------------------- the stream
#GNSS_HEAD = 256                         ; the first bytes of a frame, kept for reading the fix
Global Dim gnss_buf.a[#GNSS_HEAD]
Global gnss_n.i, gnss_src.i, gnss_why.i, gnss_bytes.i, gnss_good.i, gnss_bad.i
Global Dim gnss_ok.i[#GNF_NPROTO] : Global Dim gnss_ko.i[#GNF_NPROTO]
Global Dim gnss_in.a[512]
Global gnss_lastGoodUs.i, gnss_openUs.i
; the baud search, for a bridge chip whose receiver speed is not known
Global Dim gnss_bauds.i[8]
Global gnss_baudAt.i, gnss_baudUs.i
#GNSS_BAUD_WAIT_US = 4000000

; ---------------------------------------------------------------- the fix
; THE 64-BYTE FIX RECORD, as HwGnssFix(*fix) fills it (the layout hal.pbi
; names; it is set down here, at the first backend):
;   +0  l  quality: #HW_GNSS_NOFIX, _2D, _3D, _DGPS
;   +4  l  latitude, 1e-7 degree (north +)        +8  l  longitude, 1e-7 degree (east +)
;   +12 l  altitude above mean sea level, mm       +16 l  hacc_mm: the receiver's own horizontal
;                                                         accuracy estimate, -1 if it gave none
;   +20 l  speed_mmps over ground, -1 unknown      +24 l  course over ground, 1e-5 degree, -1 unknown
;   +28 l  satellites used, -1 unknown              +32 l  date yyyymmdd, 0 unknown
;   +36 l  time of day, ms (UTC), -1 unknown        +40 l  HDOP x 100, -1 unknown
;   +44 l  source: #GNSS_SRC_*                      +48 q  HwMicros() when this fix was read
;   +56 l  satellites in view, -1 unknown           +60 l  where from: 1 UBX NAV-PVT, 3 GGA, 4 GNS
Global gnss_q.i, gnss_lat.i, gnss_lon.i, gnss_alt.i, gnss_hacc.i, gnss_spd.i, gnss_cog.i
Global gnss_used.i, gnss_date.i, gnss_tod.i, gnss_hdop.i, gnss_atUs.i, gnss_view.i, gnss_from.i
Global gnss_validUs.i, gnss_fixes.i, gnss_ubxUs.i, gnss_ggaUs.i, gnss_satUs.i
Global Dim gnss_gsv.i[6]

Procedure gnss_FixReset()
  Define i.i
  gnss_q = #HW_GNSS_NOFIX : gnss_lat = 0 : gnss_lon = 0 : gnss_alt = 0 : gnss_hacc = -1
  gnss_spd = -1 : gnss_cog = -1 : gnss_used = -1 : gnss_date = 0 : gnss_tod = -1 : gnss_hdop = -1
  gnss_atUs = 0 : gnss_view = -1 : gnss_from = 0 : gnss_validUs = 0 : gnss_fixes = 0
  gnss_ubxUs = 0 : gnss_ggaUs = 0 : gnss_satUs = 0
  For i = 0 To 5 : gnss_gsv[i] = 0 : Next
EndProcedure

; ---- NMEA fields (the Pico's NvField / NvFixed, over gnss_buf) ----
Global gnss_nvOk.i
Procedure.i gnss_Field(k.i)
  Define i.i, n.i
  If k = 0 : ProcedureReturn 1 : EndIf
  n = 0
  For i = 1 To gnss_n - 1
    If gnss_buf[i] = 42 : ProcedureReturn -1 : EndIf
    If gnss_buf[i] = 44
      n = n + 1
      If n = k : ProcedureReturn i + 1 : EndIf
    EndIf
  Next
  ProcedureReturn -1
EndProcedure

; The number in field k times 10^decimals; gnss_nvOk = 0 when the field is empty.
Procedure.i gnss_Fixed(k.i, decimals.i)
  Define i.i, v.i, c.i, neg.i, frac.i, got.i
  gnss_nvOk = 0
  i = gnss_Field(k)
  If i < 0 : ProcedureReturn 0 : EndIf
  v = 0 : neg = 0 : frac = -1 : got = 0
  If gnss_buf[i] = 45 : neg = 1 : i = i + 1 : EndIf
  While i < gnss_n
    c = gnss_buf[i]
    If c = 46 And frac < 0
      frac = 0
    ElseIf c >= 48 And c <= 57
      If frac < 0
        If v < 200000000 : v = v * 10 + (c - 48) : EndIf
        got = 1
      ElseIf frac < decimals
        v = v * 10 + (c - 48) : frac = frac + 1 : got = 1
      EndIf
    Else
      Break
    EndIf
    i = i + 1
  Wend
  If got = 0 : ProcedureReturn 0 : EndIf
  If frac < 0 : frac = 0 : EndIf
  While frac < decimals : v = v * 10 : frac = frac + 1 : Wend
  gnss_nvOk = 1
  If neg = 1 : ProcedureReturn 0 - v : EndIf
  ProcedureReturn v
EndProcedure

; ddmm.mmmm (or dddmm.mmmm) in field k and its hemisphere in k + 1, as
; 1e-7 degree. Every decimal sent is used, to seven; gnss_nvOk = 0 if empty.
Procedure.i gnss_Coord(k.i)
  Define i.i, c.i, ip.i, num.i, den.i, n.i, got.i, v.i
  gnss_nvOk = 0
  i = gnss_Field(k)
  If i < 0 : ProcedureReturn 0 : EndIf
  ip = 0 : got = 0
  c = gnss_buf[i]
  While i < gnss_n And c >= 48 And c <= 57
    ip = ip * 10 + (c - 48) : got = 1 : i = i + 1 : c = gnss_buf[i]
  Wend
  If got = 0 : ProcedureReturn 0 : EndIf
  num = 0 : den = 1 : n = 0
  If c = 46
    i = i + 1 : c = gnss_buf[i]
    While i < gnss_n And c >= 48 And c <= 57
      If n < 7 : num = num * 10 + (c - 48) : den = den * 10 : n = n + 1 : EndIf
      i = i + 1 : c = gnss_buf[i]
    Wend
  EndIf
  ; degrees + (minutes + num/den) / 60, in 1e-7 degree, rounded
  v = (ip / 100) * 10000000 + (((ip % 100) * den + num) * 10000000 + den * 30) / (den * 60)
  i = gnss_Field(k + 1)
  If i >= 0
    If gnss_buf[i] = 83 Or gnss_buf[i] = 87 : v = 0 - v : EndIf
  EndIf
  gnss_nvOk = 1
  ProcedureReturn v
EndProcedure

Procedure.i gnss_L(at.i)
  Define v.i
  v = gnss_buf[at] | (gnss_buf[at + 1] << 8) | (gnss_buf[at + 2] << 16) | (gnss_buf[at + 3] << 24)
  If v > $7FFFFFFF : v = v - $100000000 : EndIf
  ProcedureReturn v
EndProcedure

; PLACEHOLDER: the position in a binary protocol's frame other than UBX
; (SiRF, Garmin, SBP, BINEX, JSON from gpsd, Meinberg). Framed and counted
; already; reading their fixes is the next work, protocol by protocol.
Procedure gnss_FrameBinary(p.i)
EndProcedure

; A frame of protocol p has ended with its checksum right: its first bytes are gnss_buf[0 .. gnss_n - 1].
Procedure gnss_FrameRead(p.i)
  Define t.i, v.i, i.i, ubx.i, now.i, lat.i, lon.i, fx.i
  now = HwMicros()
  ubx = 0
  If gnss_ubxUs <> 0 And now - gnss_ubxUs < 3000000 : ubx = 1 : EndIf
  If p = 1
    If gnss_n >= 98 And gnss_buf[2] = 1 And gnss_buf[3] = 7
      ; UBX NAV-PVT (payload at 6)
      gnss_ubxUs = now : gnss_from = 1
      t = gnss_buf[26]
      fx = #HW_GNSS_NOFIX
      If t = 2 : fx = #HW_GNSS_2D : EndIf
      If t = 3 Or t = 4 : fx = #HW_GNSS_3D : EndIf
      If (gnss_buf[27] & 1) = 0 : fx = #HW_GNSS_NOFIX : EndIf
      If fx <> #HW_GNSS_NOFIX And (gnss_buf[27] & 2) <> 0 : fx = #HW_GNSS_DGPS : EndIf
      gnss_q = fx
      gnss_used = gnss_buf[29]
      gnss_lon = gnss_L(30) : gnss_lat = gnss_L(34) : gnss_alt = gnss_L(42) : gnss_hacc = gnss_L(46)
      gnss_spd = gnss_L(66) : gnss_cog = gnss_L(70)
      If (gnss_buf[17] & 1) <> 0
        gnss_date = (gnss_buf[10] | (gnss_buf[11] << 8)) * 10000 + gnss_buf[12] * 100 + gnss_buf[13]
      EndIf
      If (gnss_buf[17] & 2) <> 0
        gnss_tod = ((gnss_buf[14] * 60 + gnss_buf[15]) * 60 + gnss_buf[16]) * 1000
      EndIf
      gnss_atUs = now : gnss_fixes = gnss_fixes + 1
      If fx <> #HW_GNSS_NOFIX : gnss_validUs = now : EndIf
    ElseIf gnss_n >= 12 And gnss_buf[2] = 1 And gnss_buf[3] = $35
      gnss_view = gnss_buf[11] : gnss_satUs = now          ; NAV-SAT: satellites listed
    EndIf
    ProcedureReturn
  EndIf
  If p <> 0 Or gnss_n < 12
    gnss_FrameBinary(p)
    ProcedureReturn
  EndIf
  ; NMEA: $ttSSS,...  (any talker: GP, GN, GL, GA, GB, GQ, ...)
  t = 0
  If gnss_buf[3] = 71 And gnss_buf[4] = 71 And gnss_buf[5] = 65 : t = 3 : EndIf      ; GGA
  If gnss_buf[3] = 71 And gnss_buf[4] = 78 And gnss_buf[5] = 83 : t = 4 : EndIf      ; GNS
  If t <> 0
    If ubx = 1
      ProcedureReturn
    EndIf
    If t = 4 And gnss_from = 3 And now - gnss_ggaUs < 3000000
      ProcedureReturn                                         ; GGA is read when both come
    EndIf
    If t = 3 : gnss_ggaUs = now : EndIf
    fx = #HW_GNSS_NOFIX
    If t = 3
      v = gnss_Fixed(6, 0)
      If gnss_nvOk = 1 And v > 0
        fx = #HW_GNSS_3D
        If v = 2 Or v = 4 Or v = 5 : fx = #HW_GNSS_DGPS : EndIf
      EndIf
    Else
      i = gnss_Field(6)
      While i >= 0 And i < gnss_n And gnss_buf[i] <> 44 And gnss_buf[i] <> 42
        If gnss_buf[i] <> 78 And fx = #HW_GNSS_NOFIX : fx = #HW_GNSS_3D : EndIf
        If gnss_buf[i] = 68 Or gnss_buf[i] = 70 Or gnss_buf[i] = 82 : fx = #HW_GNSS_DGPS : EndIf
        i = i + 1
      Wend
    EndIf
    v = gnss_Fixed(1, 3)
    If gnss_nvOk = 1
      gnss_tod = ((v / 10000000) * 3600 + ((v / 100000) % 100) * 60) * 1000 + (v % 100000)
    EndIf
    v = gnss_Fixed(7, 0) : If gnss_nvOk = 1 : gnss_used = v : EndIf
    v = gnss_Fixed(8, 2) : If gnss_nvOk = 1 : gnss_hdop = v : EndIf
    lat = gnss_Coord(2)
    If gnss_nvOk = 1
      lon = gnss_Coord(4)
      If gnss_nvOk = 1
        gnss_lat = lat : gnss_lon = lon : gnss_from = t
      Else
        fx = #HW_GNSS_NOFIX
      EndIf
    Else
      fx = #HW_GNSS_NOFIX
    EndIf
    v = gnss_Fixed(9, 3) : If gnss_nvOk = 1 : gnss_alt = v : EndIf
    gnss_hacc = -1                                            ; NMEA gives no accuracy estimate here
    gnss_q = fx : gnss_atUs = now : gnss_fixes = gnss_fixes + 1
    If fx <> #HW_GNSS_NOFIX : gnss_validUs = now : EndIf
  ElseIf gnss_buf[3] = 82 And gnss_buf[4] = 77 And gnss_buf[5] = 67
    ; RMC: speed (knots), course, date
    If ubx = 1
      ProcedureReturn
    EndIf
    v = gnss_Fixed(7, 3) : If gnss_nvOk = 1 : gnss_spd = (v * 514) / 1000 : EndIf
    v = gnss_Fixed(8, 5) : If gnss_nvOk = 1 : gnss_cog = v : Else : gnss_cog = -1 : EndIf
    i = gnss_Field(9)
    If i >= 0 And i + 5 < gnss_n
      If gnss_buf[i] >= 48 And gnss_buf[i] <= 57
        gnss_date = (2000 + (gnss_buf[i + 4] - 48) * 10 + (gnss_buf[i + 5] - 48)) * 10000 + ((gnss_buf[i + 2] - 48) * 10 + (gnss_buf[i + 3] - 48)) * 100 + (gnss_buf[i] - 48) * 10 + (gnss_buf[i + 1] - 48)
      EndIf
    EndIf
  ElseIf gnss_buf[3] = 71 And gnss_buf[4] = 83 And gnss_buf[5] = 86
    ; GSV: this talker's satellites in view
    t = 5
    If gnss_buf[2] = 80 : t = 0 : EndIf
    If gnss_buf[2] = 76 : t = 1 : EndIf
    If gnss_buf[2] = 65 : t = 2 : EndIf
    If gnss_buf[2] = 66 : t = 3 : EndIf
    If gnss_buf[2] = 81 : t = 4 : EndIf
    v = gnss_Fixed(3, 0) : If gnss_nvOk = 1 : gnss_gsv[t] = v : EndIf
    If gnss_satUs = 0 Or now - gnss_satUs > 3000000
      gnss_view = gnss_gsv[0] + gnss_gsv[1] + gnss_gsv[2] + gnss_gsv[3] + gnss_gsv[4] + gnss_gsv[5]
    EndIf
  EndIf
EndProcedure

; ---------------------------------------------------------------- the pump
; One byte of the receiver's stream, by the GNSS Bridge Pico's PpRxByte: instance
; 0 frames the stream; instance 1 looks, in what is in no frame, for the
; one-byte-start protocols not yet proven, and proves them.
Procedure gnss_Byte(c.i)
  Define was.i, st.i, r.i, r1.i, p.i
  gnss_bytes = gnss_bytes + 1
  was = gnf_fr_st[0]
  r = GnfStep(0, c)
  st = gnf_fr_st[0]
  If gnf_fr_st[1] <> 0 Or (was = 0 And st = 0)
    r1 = GnfStep(1, c)
    If r1 <> 0
      p = gnf_fr_p[1]
      If r1 = 1
        gnf_weak_good[p] = gnf_weak_good[p] + 1
        If gnf_weak_good[p] >= 3 And gnf_weak_good[p] > gnf_weak_bad[p] : gnf_weak_ok = gnf_weak_ok | (1 << p) : EndIf
      Else
        gnf_weak_bad[p] = gnf_weak_bad[p] + 1
      EndIf
    EndIf
  EndIf
  If was = 0 And st <> 0 : gnss_n = 0 : EndIf                 ; a frame starts with this byte
  If st <> 0 Or r <> 0
    If gnss_n < #GNSS_HEAD : gnss_buf[gnss_n] = c : gnss_n = gnss_n + 1 : EndIf
  EndIf
  If r = 1
    p = gnf_fr_p[0]
    gnss_ok[p] = gnss_ok[p] + 1 : gnss_good = gnss_good + 1 : gnss_lastGoodUs = HwMicros()
    gnss_FrameRead(p)
  ElseIf r = 2
    gnss_ko[gnf_fr_p[0]] = gnss_ko[gnf_fr_p[0]] + 1 : gnss_bad = gnss_bad + 1
  EndIf
EndProcedure

; ---------------------------------------------------------------- the sources
; The bytes waiting at the open source, up to max, into *dst; -1 if it is not up.
Procedure.i gnss_SrcRead(*dst, max.i)
  Select gnss_src
    Case #GNSS_SRC_USB
      ProcedureReturn UsbSerRead(*dst, max)
    Case #GNSS_SRC_BLUETOOTH
      ProcedureReturn -1                                      ; PLACEHOLDER: SPP over hci.pbi
    Case #GNSS_SRC_BLE
      ProcedureReturn -1                                      ; PLACEHOLDER: the Nordic UART service
    Case #GNSS_SRC_NETWORK
      ProcedureReturn -1                                      ; PLACEHOLDER: a TCP stream
  EndSelect
  ProcedureReturn -1
EndProcedure

Procedure.i GnssSourceName(src.i)
  Select src
    Case #GNSS_SRC_USB       : ProcedureReturn "USB"
    Case #GNSS_SRC_BLUETOOTH : ProcedureReturn "Bluetooth"
    Case #GNSS_SRC_BLE       : ProcedureReturn "Bluetooth LE"
    Case #GNSS_SRC_NETWORK   : ProcedureReturn "network"
  EndSelect
  ProcedureReturn "none"
EndProcedure

; Why the last open failed, as a whole sentence.
Procedure.i GnssWhy()
  Select gnss_why
    Case 0 : ProcedureReturn "no error"
    Case 1 : ProcedureReturn "no USB serial device was found: a CDC-ACM receiver, or an FTDI, Prolific, Silicon Labs or WCH bridge"
    Case 2 : ProcedureReturn "a USB device was found but its descriptors could not be read"
    Case 3 : ProcedureReturn "the USB device has no bulk endpoint pair to read a receiver from"
    Case 4 : ProcedureReturn "the USB device refused SET_CONFIGURATION"
    Case 5 : ProcedureReturn "the USB controller refused the device's endpoints"
    Case 10 : ProcedureReturn "Bluetooth (SPP) is a placeholder: the source is named but not built yet"
    Case 11 : ProcedureReturn "Bluetooth LE (the GNSS Bridge Nordic UART service) is a placeholder: not built yet"
    Case 12 : ProcedureReturn "a network stream is a placeholder: not built yet"
    Case 13 : ProcedureReturn "there is no such source"
  EndSelect
  ProcedureReturn "an unknown reason"
EndProcedure

; Opens a source. 1, or 0 with GnssWhy().
Procedure.i GnssOpen(src.i)
  Define i.i
  gnss_src = #GNSS_SRC_NONE : gnss_why = 0
  GnfReset(0) : GnfReset(1)
  gnss_n = 0 : gnss_bytes = 0 : gnss_good = 0 : gnss_bad = 0 : gnss_lastGoodUs = 0
  For i = 0 To #GNF_NPROTO - 1 : gnss_ok[i] = 0 : gnss_ko[i] = 0 : Next
  gnss_FixReset()
  Select src
    Case #GNSS_SRC_USB
      If UsbSerKind() = #USBSER_NONE
        If UsbSerFind() = 0
          gnss_why = UsbSerError() : If gnss_why < 1 Or gnss_why > 5 : gnss_why = 1 : EndIf
          ProcedureReturn 0
        EndIf
      EndIf
      gnss_bauds[0] = 9600 : gnss_bauds[1] = 115200 : gnss_bauds[2] = 38400 : gnss_bauds[3] = 57600
      gnss_bauds[4] = 19200 : gnss_bauds[5] = 4800 : gnss_bauds[6] = 230400 : gnss_bauds[7] = 460800
      gnss_baudAt = 0 : gnss_baudUs = HwMicros()
      If UsbSerNeedsBaud() <> 0 : UsbSerSetBaud(gnss_bauds[0]) : EndIf
    Case #GNSS_SRC_BLUETOOTH : gnss_why = 10 : ProcedureReturn 0
    Case #GNSS_SRC_BLE       : gnss_why = 11 : ProcedureReturn 0
    Case #GNSS_SRC_NETWORK   : gnss_why = 12 : ProcedureReturn 0
    Default                  : gnss_why = 13 : ProcedureReturn 0
  EndSelect
  gnss_src = src : gnss_openUs = HwMicros()
  ProcedureReturn 1
EndProcedure

Procedure.i GnssSource() : ProcedureReturn gnss_src : EndProcedure

; Reads what the source has and frames it. Never waits. 1 if a new fix was
; read by this call, 0 if not, -1 when no source is open.
Procedure.i GnssPump()
  Define n.i, i.i, before.i, now.i
  If gnss_src = #GNSS_SRC_NONE
    ProcedureReturn -1
  EndIf
  before = gnss_fixes
  n = gnss_SrcRead(@gnss_in[0], 512)
  For i = 0 To n - 1 : gnss_Byte(gnss_in[i]) : Next
  ; a bridge chip whose receiver says nothing we can frame: the next speed
  If gnss_src = #GNSS_SRC_USB And UsbSerNeedsBaud() <> 0
    now = HwMicros()
    If (gnss_lastGoodUs = 0 Or now - gnss_lastGoodUs > #GNSS_BAUD_WAIT_US) And now - gnss_baudUs > #GNSS_BAUD_WAIT_US
      gnss_baudAt = (gnss_baudAt + 1) % 8 : gnss_baudUs = now
      UsbSerSetBaud(gnss_bauds[gnss_baudAt])
      GnfReset(0) : GnfReset(1)
    EndIf
  EndIf
  If gnss_fixes <> before : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

; The 64-byte record (above) into *fix; answers its quality.
Procedure.i GnssFix(*fix)
  If *fix = 0
    ProcedureReturn gnss_q
  EndIf
  PokeL(*fix + 0, gnss_q) : PokeL(*fix + 4, gnss_lat) : PokeL(*fix + 8, gnss_lon) : PokeL(*fix + 12, gnss_alt)
  PokeL(*fix + 16, gnss_hacc) : PokeL(*fix + 20, gnss_spd) : PokeL(*fix + 24, gnss_cog) : PokeL(*fix + 28, gnss_used)
  PokeL(*fix + 32, gnss_date) : PokeL(*fix + 36, gnss_tod) : PokeL(*fix + 40, gnss_hdop) : PokeL(*fix + 44, gnss_src)
  PokeI(*fix + 48, gnss_atUs) : PokeL(*fix + 56, gnss_view) : PokeL(*fix + 60, gnss_from)
  ProcedureReturn gnss_q
EndProcedure

; Since the last VALID fix, ms, or -1.
Procedure.i GnssAgeMs()
  If gnss_validUs = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn (HwMicros() - gnss_validUs) / 1000
EndProcedure

Procedure.i GnssSatsUsed() : ProcedureReturn gnss_used : EndProcedure
Procedure.i GnssBytes()    : ProcedureReturn gnss_bytes : EndProcedure
Procedure.i GnssGood()     : ProcedureReturn gnss_good : EndProcedure
Procedure.i GnssBad()      : ProcedureReturn gnss_bad : EndProcedure
Procedure.i GnssProtoOk(p.i)
  If p < 0 Or p >= #GNF_NPROTO : ProcedureReturn 0 : EndIf
  ProcedureReturn gnss_ok[p]
EndProcedure
Procedure.i GnssProtoName(p.i)
  Select p
    Case 0 : ProcedureReturn "NMEA"
    Case 1 : ProcedureReturn "UBX"
    Case 2 : ProcedureReturn "RTCM3"
    Case 3 : ProcedureReturn "SiRF"
    Case 4 : ProcedureReturn "Garmin"
    Case 5 : ProcedureReturn "SBP"
    Case 6 : ProcedureReturn "BINEX"
    Case 7 : ProcedureReturn "JSON"
    Case 8 : ProcedureReturn "Meinberg"
  EndSelect
  ProcedureReturn "?"
EndProcedure
