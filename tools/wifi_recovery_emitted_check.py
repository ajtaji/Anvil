#!/usr/bin/env python3
"""Emit and execute Anvil's shipped cooperative Wi-Fi recovery procedures."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "RaspberryPi4" / "Lib" / "wifi.pi4"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"wifi recovery gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"wifi recovery gate: production procedure {name} has no end")
    return "\n".join(lines[first:last + 1])


def source_range(source: str, first_text: str, last_text: str) -> str:
    lines = source.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(first_text))
    last = next(i for i in range(first, len(lines)) if lines[i].startswith(last_text))
    return "\n".join(lines[first:last + 1])


def probe_source() -> str:
    source = WIFI.read_text(encoding="utf-8")
    constants = source_range(source, "#WIFI_REC_IDLE", "#WIFI_REC_ENTROPY_MS")
    globals_ = source_range(source, "Global gWifiRecPhase", "Global Dim wifi_recPmk")
    names = (
        "WifiRecoveryCancel", "WifiRecoveryActive", "WifiRecoveryInitialJoinFailed",
        "wifi_RecoverForgetPmk",
        "wifi_RecoverCandidateFail", "wifi_RecoverFail",
        "wifi_RecoverControlFail", "wifi_RecoverSupplicantSendFail",
        "wifi_RecoverEventDropFail",
        "wifi_RecoverTeardownOk",
        "wifi_RecoverNextCandidate", "wifi_RecoverJoinFailed",
        "wifi_RecoverHandshakeFailed", "wifi_RecoverCredentialCurrent",
        "wifi_RecoverLeaseBound",
        "WifiRecoveryStart", "WifiRecoveryTick",
    )
    bodies = "\n\n".join(procedure(source, name) for name in names)
    prelude = r'''
EnableExplicit

#HW_LINK_WIFI = 2
#WPA2_PASS_MIN = 8
#WPA2_PASS_MAX = 63
#PBKDF2_STEP_IDLE = 0
#PBKDF2_STEP_RUNNING = 1
#PBKDF2_STEP_DONE = 2
#CYW43_JOIN_RUNNING = 0
#CYW43_JOIN_JOINED = 1
#CYW43_JOIN_FAILED = -1
#CYW43_SCAN_DONE = 2
#CYW43_SCAN_FAILED = -1
#CYW43_JOINEXP_NOKEY = 2
#WIFI_SCAN_SLICE_MS = 20
#WIFI_SCAN_BUDGET_MS = 5000
#WIFI_JOIN_SLICE_MS = 20
#WIFI_JOIN_SLICES = 400
#WIFI_EAPOL_M1_MS = 2600
#WIFI_EAPOL_M3_MS = 800
#WIFI_RSN_IE_LEN = 22
#ENTROPY_SPINS = 4000000
#WPA2SUP_SENT_M2 = 2
#WPA2SUP_SENT_M4 = 4
#CYW43_CRYPTO_ALGO_AES_CCM = 4
#CYW43_IO_OK = 0
#CYW43_IO_TIMEOUT = -1
#CYW43_IO_STATUS = -3
#ENTROPY_OK = 1
#ENTROPY_ERR_HEALTH = -2
#DHCPC_BOUND = 3
#NET_ADDR_LEASE = 1

Global gate_ms.i = 1000
Global gate_down.i
Global gate_wipes.i
Global gate_pbkdfCalls.i
Global gate_pbkdfState.i
Global gate_pbkdfBudget.i
Global gate_pbkdfPw.i
Global gate_pbkdfBegins.i
Global gate_pbkdfBeginRc.i = #PBKDF2_STEP_RUNNING
Global gate_cacheHit.i = 1
Global gate_passwordUseAlt.i
Global gate_scanPolls.i
Global gate_scanVerdict.i
Global gate_joinPolls.i
Global gate_joinVerdict.i
Global gate_dropOnJoinPoll.i
Global gate_receives.i
Global gate_eapolCode.i
Global gate_sendRc.i
Global gate_sendCalls.i
Global gate_dhcpStart.i
Global gate_dhcpRc.i = 1
Global gate_dhcpAcquire.i
Global gate_dhcpState.i = #DHCPC_BOUND
Global gate_dhcpIp.i = $01020304
Global gate_netIp.i = $01020304
Global gate_netSrc.i = #NET_ADDR_LEASE
Global gate_leave.i
Global gate_leaveRc.i
Global gate_disassoc.i
Global gate_disassocRc.i
Global gate_ioctlStatus.i
Global gate_secItem.i
Global gate_joinStart.i
Global gate_readSsid.i
Global gate_setKey.i
Global gate_setKeyFail.i
Global gate_settingsSave.i
Global gate_mismatch.i
Global gate_service.i
Global gate_fp.i = 123
Global gate_entropyRc.i = #ENTROPY_OK
Global gate_entropyCalls.i
Global gate_eventDrains.i
Global gate_teardownOnDrain.i
Global gate_eventDrops.i
Global gate_settingsRemove.i
Global gate_settingsSet.i
Global gate_settingsSetRc.i = 1

Global gWifiHealPend.i
Global gWifiHealLast.i
Global gWifiKaLast.i
Global gWifiLinkOn.i = 1
Global gWifiHealOn.i = 1
Global gWifiUp.i = 1
Global gWifiSecDone.i
Global gWifiKeyed.i
Global gWifiHaveIp.i
Global gWifiRejoins.i
Global gWifiPmkDirty.i
Global gWifiIp.i = $01020304
Global gWifiTeardown.i
Global Dim wifi_pmk.a[32]
Global Dim wifi_ourMac.a[6]
Global Dim wifi_snonce.a[32]
Global Dim wifi_apMac.a[6]
Global Dim wifi_ie.a[64]
Global wifi_ieLen.i
Global Dim wifi_pmkVal.a[80]
Global Dim wifi_joinSsid.a[36]
Global wifi_joinSsidLen.i
Global Dim gateScanSsid.a[8]
Global Dim gateReplySsid.a[8]
Global Dim gateCache.a[80]
Global Dim gatePassword.a[64]
Global Dim gatePasswordAlt.a[64]

Procedure.i millis() : ProcedureReturn gate_ms : EndProcedure
Procedure str_print_at(p.i) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PutIp(v.i) : EndProcedure
Procedure Pbkdf2StepWipe() : gate_wipes = gate_wipes + 1 : gate_pbkdfState = #PBKDF2_STEP_IDLE : EndProcedure
Procedure.i Pbkdf2StepState() : ProcedureReturn gate_pbkdfState : EndProcedure
Procedure.i Wpa2PskStepBegin(p.i, plen.i, s.i, slen.i, d.i) : gate_pbkdfBegins = gate_pbkdfBegins + 1 : gate_pbkdfPw = p : gate_pbkdfState = gate_pbkdfBeginRc : ProcedureReturn gate_pbkdfState : EndProcedure
Procedure.i Pbkdf2Step(budget.i)
  gate_pbkdfCalls = gate_pbkdfCalls + 1 : gate_pbkdfBudget = budget
  ProcedureReturn gate_pbkdfState
EndProcedure
Procedure Wpa2SupWipe() : gate_wipes = gate_wipes + 1 : EndProcedure
Procedure Cyw43KeyWipe() : gate_wipes = gate_wipes + 1 : EndProcedure
Procedure AesWipe() : gate_wipes = gate_wipes + 1 : EndProcedure
Procedure KwWipe() : gate_wipes = gate_wipes + 1 : EndProcedure
Procedure NetDhcpLinkDown(k.i) : gate_down = gate_down + 1 : EndProcedure
Procedure wifi_RecordLinkDown() : NetDhcpLinkDown(#HW_LINK_WIFI) : gWifiKeyed = 0 : gWifiHaveIp = 0 : gWifiTeardown = 0 : EndProcedure
Procedure WifiDrainEvents() : gate_eventDrains = gate_eventDrains + 1 : If gate_teardownOnDrain : gWifiTeardown = 1 : EndIf : EndProcedure
Procedure.i Cyw43Leave(ms.i) : gate_leave = gate_leave + 1 : ProcedureReturn gate_leaveRc : EndProcedure
Procedure.i Cyw43IoctlStatus() : ProcedureReturn gate_ioctlStatus : EndProcedure
Procedure.i Cyw43EventsDropped() : ProcedureReturn gate_eventDrops : EndProcedure
Procedure.i Cyw43MacAddress(p.i, ms.i) : ProcedureReturn 0 : EndProcedure
Procedure.i EntropyBegin() : ProcedureReturn 1 : EndProcedure
Procedure.i EntropyWarmupWait(n.i) : ProcedureReturn 1 : EndProcedure
Procedure.i EntropyBytes(p.i, n.i, spins.i)
  Define i.i : For i=0 To n-1 : PokeA(p+i, i+1) : Next : ProcedureReturn n
EndProcedure
Procedure.i EntropyTryWord(p.i)
  gate_entropyCalls = gate_entropyCalls + 1
  If gate_entropyRc = #ENTROPY_OK : PokeN(p, $01020304 + gate_entropyCalls) : EndIf
  ProcedureReturn gate_entropyRc
EndProcedure
Procedure.i Cyw43SetWpaIe(p.i, n.i, ms.i) : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43SecItem(item.i, ms.i) : gate_secItem = gate_secItem + 1 : ProcedureReturn 0 : EndProcedure
Procedure Cyw43SetJoinExpectation(v.i) : EndProcedure
Procedure.i Cyw43ScanStart(a.i, ms.i) : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43ScanPoll(ms.i) : gate_scanPolls = gate_scanPolls + 1 : ProcedureReturn gate_scanVerdict : EndProcedure
Procedure.i Cyw43ScanCount() : ProcedureReturn 1 : EndProcedure
Procedure.i Cyw43ScanSsid(i.i) : ProcedureReturn @gateScanSsid[0] : EndProcedure
Procedure.i Cyw43ScanSsidLen(i.i) : ProcedureReturn 4 : EndProcedure
Procedure.i Cyw43ScanChannel(i.i) : ProcedureReturn 6 : EndProcedure
Procedure.i SettingsWifiFindSsid(p.i) : ProcedureReturn 1 : EndProcedure
Procedure.i SettingsWifiSlotPassword(slot.i) : If gate_passwordUseAlt : ProcedureReturn @gatePasswordAlt[0] : EndIf : ProcedureReturn @gatePassword[0] : EndProcedure
Procedure.i SettingsWifiSlotPasswordKey(slot.i) : ProcedureReturn ?gatePassKey : EndProcedure
Procedure.i SettingsLength(k.i) : If k = ?gatePmkKey : ProcedureReturn 72 : EndIf : ProcedureReturn 8 : EndProcedure
Procedure.i wifi_Fp(s.i, sl.i, p.i, pl.i) : ProcedureReturn gate_fp : EndProcedure
Procedure.i wifi_PmkKey(slot.i) : ProcedureReturn ?gatePmkKey : EndProcedure
Procedure.i SettingsGet(k.i) : If gate_cacheHit = 0 : ProcedureReturn 0 : EndIf : ProcedureReturn @gateCache[0] : EndProcedure
Procedure.i wifi_HexToU32(p.i) : ProcedureReturn 123 : EndProcedure
Procedure.i wifi_HexToBytes(p.i, d.i, n.i)
  Define i.i : For i=0 To n-1 : PokeA(d+i, i+1) : Next : ProcedureReturn 1
EndProcedure
Procedure wifi_U32ToHex(p.i, v.i) : EndProcedure
Procedure wifi_ByteToHex(p.i, o.i, b.i) : EndProcedure
Procedure.i SettingsSet(k.i, v.i) : gate_settingsSet = gate_settingsSet + 1 : ProcedureReturn gate_settingsSetRc : EndProcedure
Procedure.i SettingsRemove(k.i) : gate_settingsRemove = gate_settingsRemove + 1 : gate_cacheHit = 0 : ProcedureReturn 1 : EndProcedure
Procedure.i Cyw43Disassoc(ms.i) : gate_disassoc = gate_disassoc + 1 : ProcedureReturn gate_disassocRc : EndProcedure
Procedure.i Cyw43JoinStart(p.i, n.i, ms.i) : gate_joinStart = gate_joinStart + 1 : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43JoinPoll(ms.i) : gate_joinPolls = gate_joinPolls + 1 : If gate_dropOnJoinPoll : gate_eventDrops = gate_eventDrops + 1 : EndIf : ProcedureReturn gate_joinVerdict : EndProcedure
Procedure.i Cyw43ReadSsid(ms.i) : gate_readSsid = gate_readSsid + 1 : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43LinkSsidLen() : ProcedureReturn 4 : EndProcedure
Procedure.i Cyw43LinkSsid() : If gate_mismatch : ProcedureReturn @gateReplySsid[0] : EndIf : ProcedureReturn @gateScanSsid[0] : EndProcedure
Procedure wifi_ReadAssocIe() : wifi_ieLen = 0 : EndProcedure
Procedure.i Wpa2SupBegin(p.i, m.i, a.i, ie.i, n.i) : ProcedureReturn 1 : EndProcedure
Procedure Wpa2SupSetSnonce(p.i) : EndProcedure
Procedure.i Cyw43Receive(ms.i) : gate_receives = gate_receives + 1 : ProcedureReturn 120 : EndProcedure
Procedure.i Cyw43ReceivePtr() : ProcedureReturn @gateCache[0] : EndProcedure
Procedure.i Wpa2SupHandle(p.i, n.i) : ProcedureReturn gate_eapolCode : EndProcedure
Procedure.i wifi_SendSup() : gate_sendCalls = gate_sendCalls + 1 : ProcedureReturn gate_sendRc : EndProcedure
Procedure.i Wpa2SupTk() : ProcedureReturn @gateCache[0] : EndProcedure
Procedure.i Wpa2SupTkLen() : ProcedureReturn 16 : EndProcedure
Procedure.i Wpa2SupApMac() : ProcedureReturn @wifi_apMac[0] : EndProcedure
Procedure.i Wpa2SupGtkIndex() : ProcedureReturn 1 : EndProcedure
Procedure.i Wpa2SupGtk() : ProcedureReturn @gateCache[16] : EndProcedure
Procedure.i Wpa2SupGtkLen() : ProcedureReturn 16 : EndProcedure
Procedure.i Wpa2SupGtkRsc() : ProcedureReturn @gateCache[32] : EndProcedure
Procedure.i Cyw43SetWsecKey(i.i, k.i, n.i, algo.i, mac.i, rsc.i, ms.i)
  gate_setKey = gate_setKey + 1 : ProcedureReturn gate_setKeyFail
EndProcedure
Procedure Wpa2SupSessionArm() : EndProcedure
Procedure wifi_PersistPmkIfDirty() : If gWifiPmkDirty : gate_settingsSave = gate_settingsSave + 1 : gWifiPmkDirty = 0 : EndIf : EndProcedure
Procedure.i NetDhcpStart(k.i, auto.i) : gate_dhcpStart = gate_dhcpStart + 1 : ProcedureReturn gate_dhcpRc : EndProcedure
Procedure.i NetDhcpAcquire(k.i, wait.i, keep.i) : gate_dhcpAcquire = gate_dhcpAcquire + 1 : ProcedureReturn 0 : EndProcedure
Procedure.i DhcpClientState(k.i) : ProcedureReturn gate_dhcpState : EndProcedure
Procedure.i DhcpClientIp(k.i) : ProcedureReturn gate_dhcpIp : EndProcedure
Procedure.i NetIPv4(k.i) : ProcedureReturn gate_netIp : EndProcedure
Procedure.i NetIfSrc(k.i) : ProcedureReturn gate_netSrc : EndProcedure

DataSection
  wifi_rsnIe: Data.a 0
  gatePassKey: Data.a 112,0
  gatePmkKey: Data.a 107,0
EndDataSection
'''
    tests = r'''
Procedure GateInit()
  Define i.i
  gate_ms = 1000 : gate_down = 0 : gate_wipes = 0
  gate_pbkdfCalls = 0 : gate_pbkdfState = #PBKDF2_STEP_RUNNING : gate_pbkdfBudget = 0
  gate_pbkdfPw = 0 : gate_pbkdfBegins = 0 : gate_pbkdfBeginRc = #PBKDF2_STEP_RUNNING : gate_cacheHit = 1 : gate_passwordUseAlt = 0
  gate_scanPolls = 0 : gate_scanVerdict = #CYW43_SCAN_DONE
  gate_joinPolls = 0 : gate_joinVerdict = #CYW43_JOIN_JOINED : gate_dropOnJoinPoll = 0
  gate_receives = 0 : gate_eapolCode = #WPA2SUP_SENT_M2 : gate_sendRc = 0 : gate_sendCalls = 0
  gate_dhcpStart = 0 : gate_dhcpRc = 1 : gate_dhcpAcquire = 0 : gate_leave = 0 : gate_leaveRc = 0
  gate_dhcpState = #DHCPC_BOUND : gate_dhcpIp = $01020304 : gate_netIp = $01020304 : gate_netSrc = #NET_ADDR_LEASE
  gate_disassoc = 0 : gate_disassocRc = 0 : gate_ioctlStatus = 0 : gate_secItem = 0 : gate_joinStart = 0
  gate_readSsid = 0 : gate_setKey = 0 : gate_setKeyFail = 0
  gate_settingsSave = 0 : gate_mismatch = 0 : gate_service = 0
  gate_fp = 123
  gate_entropyRc = #ENTROPY_OK : gate_entropyCalls = 0
  gate_eventDrains = 0 : gate_teardownOnDrain = 0 : gate_eventDrops = 0 : gWifiTeardown = 0
  gate_settingsRemove = 0 : gate_settingsSet = 0 : gate_settingsSetRc = 1
  gWifiLinkOn = 1 : gWifiHealOn = 1 : gWifiUp = 1
  gWifiSecDone = 0 : gWifiKeyed = 1 : gWifiHaveIp = 1
  gWifiHealPend = 0 : gWifiHealLast = 0 : gWifiKaLast = 0
  gWifiRejoins = 0 : gWifiPmkDirty = 0 : gWifiIp = $01020304
  gWifiRecEventDropBase = 0 : gWifiRecPmkCached = 0 : gWifiRecFreshFallback = 0 : gWifiRecPmkNeedsStore = 0
  gWifiRecLastFailPhase = #WIFI_REC_IDLE : gWifiRecLastFailRc = 0 : gWifiRecLastFailStatus = 0
  gateScanSsid[0]=116 : gateScanSsid[1]=101 : gateScanSsid[2]=115 : gateScanSsid[3]=116
  gateReplySsid[0]=98 : gateReplySsid[1]=97 : gateReplySsid[2]=100 : gateReplySsid[3]=33
  gatePassword[0]=112 : gatePassword[1]=97 : gatePassword[2]=115 : gatePassword[3]=115
  gatePassword[4]=119 : gatePassword[5]=111 : gatePassword[6]=114 : gatePassword[7]=100
  For i=0 To 7 : gatePasswordAlt[i]=gatePassword[i] : Next
  For i=0 To 71 : gateCache[i]=48 : Next
  gWifiRecPhase = #WIFI_REC_IDLE
EndProcedure

Procedure GateBindCredential()
  Define i.i
  gWifiRecPassLen = 8
  For i = 0 To 7 : wifi_recPass[i] = gatePassword[i] : Next
EndProcedure

Procedure.i Main()
  Define generation.i
  Define before.i
  Define after.i
  Define turns.i
  Define waitedDhcp.i
  Define i.i

  ; Starting recovery performs no firmware I/O and invalidates the address.
  GateInit()
  WifiRecoveryStart(1)
  If gWifiRecPhase <> #WIFI_REC_LEAVE Or gate_leave <> 0 Or gate_down <> 1 : ProcedureReturn 1 : EndIf
  generation = gWifiRecGeneration

  ; Each of scan/join/PBKDF polling advances only once per service call.
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_SCAN_POLL : gate_scanVerdict = #CYW43_JOIN_RUNNING
  WifiRecoveryTick()
  If gate_scanPolls <> 1 Or gWifiRecPhase <> #WIFI_REC_SCAN_POLL : ProcedureReturn 2 : EndIf
  gate_service = gate_service + 1
  WifiRecoveryTick()
  If gate_scanPolls <> 2 Or gate_service <> 1 : ProcedureReturn 3 : EndIf

  GateBindCredential()
  gWifiRecPhase = #WIFI_REC_PBKDF : gate_pbkdfState = #PBKDF2_STEP_RUNNING
  WifiRecoveryTick()
  If gate_pbkdfCalls <> 1 Or gate_pbkdfBudget <> 16 Or gWifiRecPhase <> #WIFI_REC_PBKDF : ProcedureReturn 4 : EndIf
  gate_service = gate_service + 1
  WifiRecoveryTick()
  If gate_pbkdfCalls <> 2 Or gate_service <> 2 : ProcedureReturn 5 : EndIf

  gWifiRecPhase = #WIFI_REC_JOIN_POLL : gate_joinVerdict = #CYW43_JOIN_RUNNING
  WifiRecoveryTick()
  If gate_joinPolls <> 1 Or gWifiRecPhase <> #WIFI_REC_JOIN_POLL : ProcedureReturn 6 : EndIf
  gate_service = gate_service + 1
  WifiRecoveryTick()
  If gate_joinPolls <> 2 Or gate_service <> 3 : ProcedureReturn 7 : EndIf

  ; EAPOL receive is one bounded receive per spin, with M1 then M3 order.
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gWifiRecM1 = 0 : gWifiRecAt = gate_ms
  gate_eapolCode = #WPA2SUP_SENT_M2
  WifiRecoveryTick()
  If gate_receives <> 1 Or gWifiRecM1 <> 1 Or gWifiRecPhase <> #WIFI_REC_EAPOL_RX : ProcedureReturn 8 : EndIf
  gate_service = gate_service + 1 : gate_eapolCode = #WPA2SUP_SENT_M4
  WifiRecoveryTick()
  If gate_receives <> 2 Or gWifiRecPhase <> #WIFI_REC_PTK_INSTALL : ProcedureReturn 9 : EndIf

  ; PTK and GTK installation are separate firmware-control phases.
  WifiRecoveryTick()
  If gate_setKey <> 1 Or gWifiRecPhase <> #WIFI_REC_GTK_INSTALL : ProcedureReturn 10 : EndIf
  gate_service = gate_service + 1
  WifiRecoveryTick()
  If gate_setKey <> 2 Or gWifiRecPhase <> #WIFI_REC_PERSIST Or gWifiKeyed = 0 : ProcedureReturn 11 : EndIf

  ; Persistence, DHCP start, and DHCP wait are distinct. No foreground
  ; NetDhcpAcquire or second DHCP retry loop may appear in automatic recovery.
  WifiRecoveryTick()
  If gate_settingsSave <> 0 Or gate_dhcpStart <> 0 Or gWifiRecPhase <> #WIFI_REC_DHCP_START : ProcedureReturn 12 : EndIf
  WifiRecoveryTick()
  If gate_dhcpStart <> 1 Or gate_dhcpAcquire <> 0 Or gWifiRecPhase <> #WIFI_REC_DHCP_WAIT : ProcedureReturn 13 : EndIf
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT Or gWifiRejoins <> 0 : ProcedureReturn 14 : EndIf
  gWifiHaveIp = 1 : gWifiIp = gate_dhcpIp
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRejoins <> 1 Or gWifiHealPend <> 0 : ProcedureReturn 15 : EndIf

  ; A prepared M2/M4 is not success unless the exact frame was transmitted.
  ; Refusal preserves the send rc, does not set M1, and never advances to key
  ; installation. It is an association/transport failure, not evidence that a
  ; cached PMK is wrong: preserve that PMK and do not begin fresh PBKDF2.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPmkCached = 1 : wifi_recPmk[0] = 77 : wifi_pmk[0] = 66
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gWifiRecAttempt = 0 : gWifiRecM1 = 0 : gWifiRecAt = gate_ms
  gate_eapolCode = #WPA2SUP_SENT_M2 : gate_sendRc = -4
  WifiRecoveryTick()
  If gate_sendCalls <> 1 : ProcedureReturn 68 : EndIf
  If gWifiRecM1 <> 0 : ProcedureReturn 78 : EndIf
  If gate_settingsRemove <> 0 Or gate_pbkdfBegins <> 0 : ProcedureReturn 82 : EndIf
  If gWifiRecPmkCached = 0 Or gWifiRecFreshFallback <> 0 : ProcedureReturn 82 : EndIf
  If wifi_recPmk[0] <> 77 Or wifi_pmk[0] <> 66 : ProcedureReturn 82 : EndIf
  If gWifiRecPhase <> #WIFI_REC_DISASSOC : ProcedureReturn 79 : EndIf
  If gWifiRecLastFailPhase <> #WIFI_REC_EAPOL_RX Or gWifiRecLastFailRc <> -4 : ProcedureReturn 69 : EndIf

  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPmkCached = 1 : wifi_recPmk[0] = 88 : wifi_pmk[0] = 55
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gWifiRecAttempt = 0 : gWifiRecM1 = 1 : gWifiRecAt = gate_ms
  gate_eapolCode = #WPA2SUP_SENT_M4 : gate_sendRc = -1
  WifiRecoveryTick()
  If gate_settingsRemove <> 0 Or gate_pbkdfBegins <> 0 : ProcedureReturn 83 : EndIf
  If gWifiRecPmkCached = 0 Or gWifiRecFreshFallback <> 0 : ProcedureReturn 83 : EndIf
  If wifi_recPmk[0] <> 88 Or wifi_pmk[0] <> 55 : ProcedureReturn 83 : EndIf
  If gate_sendCalls <> 1 Or gWifiRecPhase <> #WIFI_REC_DISASSOC Or gate_setKey <> 0 : ProcedureReturn 70 : EndIf
  If gWifiRecLastFailPhase <> #WIFI_REC_EAPOL_RX Or gWifiRecLastFailRc <> -1 : ProcedureReturn 71 : EndIf

  ; A radio that becomes unavailable does not remain armed for a pointless
  ; association retry. Incremental radio bring-up is a separate contract.
  GateInit() : WifiRecoveryStart(0) : gWifiUp = 0
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiHealPend <> 0 : ProcedureReturn 80 : EndIf
  If gate_leave <> 0 Or gate_scanPolls <> 0 Or gate_joinStart <> 0 : ProcedureReturn 81 : EndIf

  ; Explicit cancellation invalidates the generation and no old phase runs.
  WifiRecoveryStart(0) : generation = gWifiRecGeneration : before = gate_leave
  WifiRecoveryCancel()
  If gWifiRecGeneration = generation Or gWifiRecPhase <> #WIFI_REC_IDLE : ProcedureReturn 16 : EndIf
  WifiRecoveryTick()
  If gate_leave <> before : ProcedureReturn 17 : EndIf

  ; A generic settings mutation is caught from the copied candidate and
  ; fingerprint before another crypto/join phase can resume.
  WifiRecoveryStart(0) : generation = gWifiRecGeneration
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  GateBindCredential()
  gWifiRecPhase = #WIFI_REC_PBKDF : gate_fp = 124 : before = gate_pbkdfCalls
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecGeneration = generation : ProcedureReturn 18 : EndIf
  If gate_pbkdfCalls <> before : ProcedureReturn 19 : EndIf

  ; A settings table reset/reload with identical credential bytes/fingerprint
  ; cannot invalidate PBKDF's borrowed address: recovery gives the resumable
  ; engine its own bounded passphrase copy.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecPhase = #WIFI_REC_PMK
  gate_cacheHit = 0
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_PBKDF Or gate_pbkdfPw <> @wifi_recPass[0] : ProcedureReturn 37 : EndIf
  For i = 0 To 7 : If wifi_recPass[i] <> gatePassword[i] : ProcedureReturn 38 : EndIf : Next
  gate_passwordUseAlt = 1
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_PBKDF Or gate_pbkdfCalls <> 1 : ProcedureReturn 39 : EndIf
  If wifi_recPass[0] <> 112 Or gWifiRecPassLen <> 8 : ProcedureReturn 39 : EndIf
  ; A different credential with the same synthetic fingerprint is still a
  ; different generation and must be cancelled by the exact-byte binding.
  gatePasswordAlt[0] = 88 : generation = gWifiRecGeneration
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecGeneration = generation : ProcedureReturn 40 : EndIf
  GateInit() : WifiRecoveryStart(0)
  For i = 0 To 7 : wifi_recPass[i] = i + 1 : Next : gWifiRecPassLen = 8
  WifiRecoveryCancel()
  For i = 0 To #WPA2_PASS_MAX : If wifi_recPass[i] <> 0 : ProcedureReturn 41 : EndIf : Next
  If gWifiRecPassLen <> 0 : ProcedureReturn 41 : EndIf

  ; Cancelling during the handshake wipes its transcript; cancelling the
  ; later DHCP wait preserves the session-arm material for the live link.
  WifiRecoveryStart(0) : gWifiRecPhase = #WIFI_REC_EAPOL_RX : before = gate_wipes
  WifiRecoveryCancel()
  If gate_wipes - before <> 5 : ProcedureReturn 29 : EndIf
  WifiRecoveryStart(0) : gWifiRecPhase = #WIFI_REC_DHCP_WAIT : before = gate_wipes
  WifiRecoveryCancel()
  If gate_wipes - before <> 1 : ProcedureReturn 30 : EndIf

  ; A stale/mismatched SSID readback cannot promote old join events to a
  ; handshake. It schedules the same candidate's one explicit retry.
  WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_VERIFY_SSID : gWifiRecAttempt = 0 : gate_mismatch = 1
  gate_fp = 123 : gWifiRecFp = 123 : gWifiRecSlot = 1 : gWifiRecSsidLen = 4
  GateBindCredential()
  WifiRecoveryTick()
  If gate_readSsid <> 1 Or gWifiRecPhase <> #WIFI_REC_DISASSOC Or gWifiRecAttempt <> 1 : ProcedureReturn 20 : EndIf

  ; Once JoinPoll has returned JOINED, a newly queued definitive down edge
  ; cancels that generation before verify/handshake work can resume.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  GateBindCredential() : generation = gWifiRecGeneration : gate_teardownOnDrain = 1
  before = gate_receives
  WifiRecoveryTick()
  If gate_eventDrains <> 1 Or gWifiRecGeneration = generation Or gWifiRecPhase <> #WIFI_REC_LEAVE : ProcedureReturn 42 : EndIf
  If gate_receives <> before Or gWifiTeardown <> 0 : ProcedureReturn 43 : EndIf

  ; Failure leaves truthful down state and arms the existing slow retry clock.
  gWifiRecPhase = #WIFI_REC_SCAN_POLL : gate_scanVerdict = #CYW43_SCAN_FAILED : gate_ms = 9000
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiHealPend = 0 Or gWifiHealLast <> gate_ms : ProcedureReturn 21 : EndIf

  ; RNG warm-up/FIFO pending is nonblocking and has an elapsed deadline.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_SEC_ENTROPY : gWifiRecEntropyWords = -1
  WifiRecoveryTick()
  If gate_entropyCalls <> 0 Or gWifiRecEntropyWords <> 0 : ProcedureReturn 31 : EndIf
  gate_entropyRc = 0
  WifiRecoveryTick()
  If gate_entropyCalls <> 1 Or gWifiRecPhase <> #WIFI_REC_SEC_ENTROPY : ProcedureReturn 32 : EndIf
  gate_ms = gate_ms + #WIFI_REC_ENTROPY_MS
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiHealPend = 0 : ProcedureReturn 33 : EndIf

  ; A health fault fails immediately. A partial SNonce is wiped by explicit
  ; cancellation, while eight available words advance exactly one per tick.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_SEC_ENTROPY : gWifiRecEntropyWords = 0 : gWifiRecAt = gate_ms
  gate_entropyRc = #ENTROPY_ERR_HEALTH
  WifiRecoveryTick()
  If gate_entropyCalls <> 1 Or gWifiRecPhase <> #WIFI_REC_IDLE : ProcedureReturn 34 : EndIf
  GateInit() : WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_SEC_ENTROPY : gWifiRecEntropyWords = 0 : gWifiRecAt = gate_ms
  WifiRecoveryTick() : WifiRecoveryTick() : WifiRecoveryTick()
  WifiRecoveryCancel()
  For i = 0 To 31 : If wifi_snonce[i] <> 0 : ProcedureReturn 35 : EndIf : Next
  GateInit() : WifiRecoveryStart(0)
  gWifiRecPhase = #WIFI_REC_SEC_ENTROPY : gWifiRecEntropyWords = 0 : gWifiRecAt = gate_ms
  For i = 0 To 7 : WifiRecoveryTick() : gate_service = gate_service + 1 : Next
  If gate_entropyCalls <> 8 Or gWifiRecPhase <> #WIFI_REC_SEC_RSN Or gate_service <> 8 : ProcedureReturn 36 : EndIf

  ; A cumulative historical event-drop count is allowed. A new delta from
  ; immediately before JoinStart is not: reject it during JoinPoll, after a
  ; JOINED verdict, and while DHCP is pending before accepting an address.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_JOIN_START : gate_eventDrops = 7
  WifiRecoveryTick()
  If gWifiRecEventDropBase <> 7 Or gWifiRecPhase <> #WIFI_REC_JOIN_POLL : ProcedureReturn 44 : EndIf
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_VERIFY_SSID : ProcedureReturn 45 : EndIf

  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_JOIN_START : gate_eventDrops = 7
  WifiRecoveryTick() : gate_dropOnJoinPoll = 1 : before = gate_joinPolls
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gate_joinPolls <> before + 1 Or gWifiRecLastFailRc <> 1 : ProcedureReturn 46 : EndIf

  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gWifiRecEventDropBase = 11
  gate_eventDrops = 12 : gWifiKeyed = 1 : gWifiHaveIp = 1 : before = gate_receives
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gate_receives <> before Or gWifiKeyed <> 0 Or gWifiHaveIp <> 0 : ProcedureReturn 47 : EndIf

  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DHCP_WAIT : gWifiRecEventDropBase = 20
  gate_eventDrops = 21 : gWifiKeyed = 1 : gWifiHaveIp = 1
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRejoins <> 0 Or gWifiKeyed <> 0 Or gWifiHaveIp <> 0 : ProcedureReturn 48 : EndIf

  ; LEAVE and DISASSOC are control boundaries, not best-effort narration.
  ; Their exact transport/status errors survive cleanup and neither failure
  ; advances into quiet/scan/join.
  GateInit() : WifiRecoveryStart(0) : gate_leaveRc = #CYW43_IO_TIMEOUT
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecLastFailPhase <> #WIFI_REC_LEAVE Or gWifiRecLastFailRc <> #CYW43_IO_TIMEOUT : ProcedureReturn 49 : EndIf
  If gate_scanPolls <> 0 Or gate_joinStart <> 0 : ProcedureReturn 50 : EndIf

  GateInit() : WifiRecoveryStart(0) : gate_leaveRc = #CYW43_IO_STATUS : gate_ioctlStatus = -17
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_QUIET Or gWifiRecLastFailPhase <> #WIFI_REC_IDLE : ProcedureReturn 62 : EndIf

  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DISASSOC : gate_disassocRc = #CYW43_IO_STATUS : gate_ioctlStatus = -17
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_JOIN_QUIET Or gWifiRecLastFailPhase <> #WIFI_REC_IDLE : ProcedureReturn 51 : EndIf
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DISASSOC : gate_disassocRc = #CYW43_IO_STATUS : gate_ioctlStatus = -4
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecLastFailPhase <> #WIFI_REC_DISASSOC : ProcedureReturn 52 : EndIf
  If gWifiRecLastFailRc <> #CYW43_IO_STATUS Or gWifiRecLastFailStatus <> -4 Or gate_joinStart <> 0 : ProcedureReturn 63 : EndIf

  ; A cached PMK rejected by the four-way handshake gets one fresh derivation
  ; from the owned password. Failure after that derivation cannot loop back,
  ; and the replacement cache is not staged/persisted before key install.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecPhase = #WIFI_REC_PMK
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DISASSOC Or gWifiRecPmkCached = 0 : ProcedureReturn 53 : EndIf
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gate_eapolCode = -9 : gWifiRecAt = gate_ms
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_PBKDF : ProcedureReturn 54 : EndIf
  If gate_pbkdfBegins <> 1 : ProcedureReturn 66 : EndIf
  If gate_settingsRemove <> 1 : ProcedureReturn 67 : EndIf
  If gate_pbkdfPw <> @wifi_recPass[0] Or gWifiRecFreshFallback = 0 Or gate_settingsSet <> 0 : ProcedureReturn 55 : EndIf
  gate_pbkdfState = #PBKDF2_STEP_DONE
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DISASSOC Or gWifiRecPmkNeedsStore = 0 Or gate_settingsSet <> 0 : ProcedureReturn 56 : EndIf
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gate_eapolCode = -9 : gWifiRecAt = gate_ms
  WifiRecoveryTick()
  If gate_pbkdfBegins <> 1 Or gWifiRecPhase = #WIFI_REC_PBKDF : ProcedureReturn 57 : EndIf

  ; Only the successful-key-install persistence phase publishes a freshly
  ; derived replacement to settings.
  gWifiRecPhase = #WIFI_REC_PERSIST : gWifiRecPmkNeedsStore = 1
  WifiRecoveryTick()
  If gate_settingsSet <> 1 Or gate_settingsSave <> 1 Or gWifiRecPhase <> #WIFI_REC_DHCP_START : ProcedureReturn 58 : EndIf

  ; If the fresh derivation cannot even begin, the zeroed old PMK must never
  ; flow into DISASSOC/JOIN as a retry candidate.
  GateInit() : WifiRecoveryStart(0)
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecPhase = #WIFI_REC_PMK
  WifiRecoveryTick()
  gWifiRecPhase = #WIFI_REC_EAPOL_RX : gate_eapolCode = -9 : gate_pbkdfBeginRc = #PBKDF2_STEP_IDLE
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gate_pbkdfBegins <> 1 Or gate_joinStart <> 0 : ProcedureReturn 64 : EndIf

  ; A full/refusing settings table does not invalidate the live association,
  ; but it cannot set dirty or print the cache-save success path.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_PERSIST : gWifiRecPmkNeedsStore = 1 : gate_settingsSetRc = 0 : gWifiKeyed = 1
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_START Or gate_settingsSet <> 1 Or gate_settingsSave <> 0 : ProcedureReturn 65 : EndIf
  If gWifiPmkDirty <> 0 Or gWifiKeyed = 0 : ProcedureReturn 65 : EndIf

  ; Generic settings mutation remains generation-bound while DHCP is pending.
  ; It cannot announce an old candidate merely because the key install ended.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DHCP_WAIT : gWifiRecEventDropBase = 0
  gWifiKeyed = 1 : gWifiHaveIp = 1 : gate_fp = 124
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRejoins <> 0 Or gWifiKeyed <> 0 Or gWifiHaveIp <> 0 : ProcedureReturn 59 : EndIf

  ; The compatibility address flag alone cannot complete recovery. Require a
  ; BOUND common client, lease provenance and one exact nonzero IP in the
  ; client, interface row and Wi-Fi compatibility state.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DHCP_WAIT : gWifiRecEventDropBase = 0 : gWifiHaveIp = 1
  gate_dhcpState = 2
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT Or gWifiRejoins <> 0 : ProcedureReturn 72 : EndIf
  gate_dhcpState = #DHCPC_BOUND : gate_netSrc = 2
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT : ProcedureReturn 73 : EndIf
  gate_netSrc = #NET_ADDR_LEASE : gate_dhcpIp = 0
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT : ProcedureReturn 74 : EndIf
  gate_dhcpIp = $01020304 : gate_netIp = $05060708
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT : ProcedureReturn 75 : EndIf
  gate_netIp = gate_dhcpIp : gWifiIp = $05060708
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_DHCP_WAIT : ProcedureReturn 76 : EndIf
  gWifiIp = gate_dhcpIp
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRejoins <> 1 : ProcedureReturn 77 : EndIf

  ; DHCP start is a checked interface/listener boundary. Both no-usable-link
  ; and same-interface server conflict fail the candidate without entering an
  ; invented timeout or a false WAIT state.
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DHCP_START : gate_dhcpRc = 0
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecLastFailPhase <> #WIFI_REC_DHCP_START Or gWifiRecLastFailRc <> 0 : ProcedureReturn 60 : EndIf
  GateInit() : WifiRecoveryStart(0) : GateBindCredential()
  gWifiRecSlot = 1 : gWifiRecSsidLen = 4 : gWifiRecFp = 123
  gWifiRecPhase = #WIFI_REC_DHCP_START : gate_dhcpRc = -1
  WifiRecoveryTick()
  If gWifiRecPhase <> #WIFI_REC_IDLE Or gWifiRecLastFailRc <> -1 : ProcedureReturn 61 : EndIf

  ; Whole cache-hit recovery, driven exactly one production Tick at a time.
  ; Count every modeled firmware/network operation and require no Tick to
  ; combine two of them; the synthetic wired service runs between turns.
  GateInit()
  WifiRecoveryStart(0)
  turns = 0 : waitedDhcp = 0
  While gWifiRecPhase <> #WIFI_REC_IDLE And turns < 80
    If gWifiRecPhase = #WIFI_REC_QUIET Or gWifiRecPhase = #WIFI_REC_JOIN_QUIET
      gate_ms = gate_ms + #WIFI_REC_QUIET_MS
    EndIf
    If gWifiRecPhase = #WIFI_REC_EAPOL_RX
      If gWifiRecM1 = 0 : gate_eapolCode = #WPA2SUP_SENT_M2 : Else : gate_eapolCode = #WPA2SUP_SENT_M4 : EndIf
    EndIf
    If gWifiRecPhase = #WIFI_REC_DHCP_WAIT
      If waitedDhcp <> 0 : gWifiHaveIp = 1 : gWifiIp = gate_dhcpIp : EndIf
      waitedDhcp = 1
    EndIf
    before = gate_leave + gate_secItem + gate_scanPolls + gate_disassoc
    before = before + gate_joinStart + gate_joinPolls + gate_readSsid
    before = before + gate_receives + gate_setKey + gate_dhcpStart
    WifiRecoveryTick()
    after = gate_leave + gate_secItem + gate_scanPolls + gate_disassoc
    after = after + gate_joinStart + gate_joinPolls + gate_readSsid
    after = after + gate_receives + gate_setKey + gate_dhcpStart
    If after - before > 1 : ProcedureReturn 22 : EndIf
    gate_service = gate_service + 1
    turns = turns + 1
  Wend
  If gWifiRecPhase <> #WIFI_REC_IDLE : ProcedureReturn 23 : EndIf
  If turns < 20 : ProcedureReturn 27 : EndIf
  If gate_service <> turns : ProcedureReturn 28 : EndIf
  If gate_leave <> 1 Or gate_scanPolls <> 1 Or gate_disassoc <> 1 Or gate_joinStart <> 1 : ProcedureReturn 24 : EndIf
  If gate_joinPolls <> 1 Or gate_readSsid <> 1 Or gate_receives <> 2 Or gate_setKey <> 2 : ProcedureReturn 25 : EndIf
  If gate_dhcpStart <> 1 Or gate_dhcpAcquire <> 0 Or gWifiRejoins <> 1 Or gWifiHaveIp = 0 : ProcedureReturn 26 : EndIf

  ProcedureReturn 0
EndProcedure
'''
    return prelude + "\n" + constants + "\n" + globals_ + "\n" + bodies + "\n" + tests


def build(pmfc: Path, work: Path, probe: Path) -> Path:
    staged = work / pmfc.name
    shutil.copy2(pmfc, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    image = work / "wifi_recovery_gate.img"
    command = [str(staged), str(probe), "-t", "pi4",
               "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("wifi recovery gate: compile failed\n" + run.stdout)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-wifi-recovery-emitted-") as temporary:
        work = Path(temporary)
        probe = work / "wifi_recovery_gate.pi4"
        exact_source = probe_source()
        probe.write_text(exact_source, encoding="utf-8", newline="\n")
        image = build(pmfc, work, probe)
        result, steps = emitted.execute(a64, image)
        if result == 0:
            helper = procedure(exact_source, "wifi_RecoverSupplicantSendFail")
            wrong_owner = helper.replace(
                "  wifi_RecoverJoinFailed()", "  wifi_RecoverHandshakeFailed()", 1
            )
            if wrong_owner == helper:
                raise SystemExit("wifi recovery gate: cached-PMK owner mutation site not found")
            mutated = exact_source.replace(helper, wrong_owner, 1)
            probe.write_text(mutated, encoding="utf-8", newline="\n")
            mutant_image = build(pmfc, work, probe)
            mutant_result, _ = emitted.execute(a64, mutant_image)
            if mutant_result != 82:
                print(
                    "wifi_recovery_emitted_check: FAIL wrong-owner mutant returned "
                    f"{mutant_result}, expected 82"
                )
                return 1
    if result:
        print(f"wifi_recovery_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(
        "wifi_recovery_emitted_check: PASS - 83 assertions, "
        f"{steps:,} A64 instructions; cached-PMK wrong-owner mutant fails assertion 82"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
