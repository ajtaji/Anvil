#!/usr/bin/env python3
"""Emit and execute the shipped Wi-Fi link-down policy procedures.

The probe extracts the complete production procedure bodies instead of
maintaining a test copy. Hardware-facing calls are deterministic stubs; the
compiled AArch64 therefore proves policy/order/state mutations without SDIO.
Requires PMFC and PMF_A64_INTERP (or --pmfc/--interp).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "RaspberryPi4" / "Lib" / "wifi.pi4"
CYW43 = ROOT / "RaspberryPi4" / "Lib" / "cyw43.pi4"
BOOT = ROOT / "RaspberryPi4" / "Board" / "boot.pi4"
WIFI_CMD = ROOT / "Anvil" / "Core" / "wifi_cmd.pbi"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"wifi link policy gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"wifi link policy gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def source_range(source: str, first_text: str, last_text: str) -> str:
    lines = source.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(first_text))
    last = next(i for i in range(first, len(lines)) if lines[i].startswith(last_text))
    return "\n".join(lines[first : last + 1])


def probe_source() -> str:
    source = WIFI.read_text(encoding="utf-8")
    cyw_source = CYW43.read_text(encoding="utf-8")
    eapol_state = source_range(source, "#WIFI_EAPOL_FAIL_NONE", "Global gWifiEapolRecoverRc")
    wifi_names = ("wifi_RecordEapolFailure", "WifiDrainEvents", "WifiRadioPump",
                  "wifi_RecordLinkDown", "WifiRecoveryInitialJoinFailed",
                  "wifi_EapolFailureName", "wifi_ServiceDeferredEapolFailure",
                  "WifiLinkTick")
    cyw_names = ("cyw43_EvrPush", "cyw43_EvrPop", "cyw43_EvrClear", "cyw43_JoinClassify", "Cyw43JoinPoll")
    wifi_bodies = "\n\n".join(procedure(source, name) for name in wifi_names)
    cyw_bodies = "\n\n".join(procedure(cyw_source, name) for name in cyw_names)
    identifiers = sorted(set(re.findall(r"#CYW43_[A-Z0-9_]*[A-Z0-9](?![A-Z0-9_*])", cyw_bodies + "\n" + wifi_bodies)))
    constant_lines = []
    cyw_lines = cyw_source.splitlines()
    for identifier in identifiers:
        line = next((item for item in cyw_lines if item.startswith(identifier + " ") or item.startswith(identifier + "=")), None)
        if line is None:
            raise SystemExit(f"wifi link policy gate: production constant {identifier} not found")
        constant_lines.append(line)
    constants = "\n".join(constant_lines)
    prelude = r'''
EnableExplicit

#HW_LINK_WIFI = 2
#WIFI_HEAL_MS = 60000
#WIFI_KA_MS = 20000
#WIFI_BSSID_MS = 400
#WIFI_LINK_STRIKES = 2
#WIFI_PROOF_MS = 45000

Global gate_ms.i
Global gate_pumps.i
Global gate_linkDown.i
Global gate_rejoins.i
Global gate_dhcpStarts.i
Global gate_assoc.i
Global gate_assocCalls.i
Global gate_keepalive.i
Global gate_recActive.i
Global gate_recTicks.i
Global gate_recCancels.i
Global gate_liveWipes.i
Global gate_inReceive.i
Global gate_reentered.i
Global gate_latchInPump.i
Global gate_rxLen.i
Global gate_joinVerdict.i
Global gate_pollEvents.i

Global gWifiLinkOn.i
Global gWifiUp.i
Global gWifiKeyed.i
Global gWifiHaveIp.i
Global gWifiSecDone.i
Global gWifiBadReads.i
Global gWifiTeardown.i
Global gWifiVerify.i
Global gWifiHealPend.i
Global gWifiHealLast.i
Global gWifiKaProbes.i
Global gWifiKaLast.i
Global gWifiHealOn.i
Global gWifiTdType.i
Global gWifiTdReason.i
Global gWifiDropReq.i
Global gWifiRxProof.i
Global gWifiGw.i
Global gWifiRecPhase.i
Global gWifiRecGeneration.i
Global gWifiConOwnsRx.i
Global gWifiRadioLast.i
Global gWifiEvtDrops.i
Global gWifiEvtLast.i
Global gWifiEvtType.i
Global gWifiEvtReason.i
Global gWifiDeauths.i
Global gWifiRoams.i

#WIFI_PUMP_BUDGET = 4
#WIFI_REC_IDLE = 0
#WIFI_REC_QUIET = 2
#WIFI_REC_JOIN_POLL = 15
#WIFI_REC_DHCP_WAIT = 24
#CYW43_JS_ACTIVE = $0001

Global Dim cyw43_evrType.i[#CYW43_EVRING]
Global Dim cyw43_evrStatus.i[#CYW43_EVRING]
Global Dim cyw43_evrReason.i[#CYW43_EVRING]
Global Dim cyw43_evrFlags.i[#CYW43_EVRING]
Global cyw43_evrHead.i
Global cyw43_evrTail.i
Global cyw43_evrCount.i
Global cyw43_evrDropped.i
Global cyw43_evrTotal.i
Global cyw43_jevType.i
Global cyw43_jevStatus.i
Global cyw43_jevReason.i
Global cyw43_jevFlags.i
Global cyw43_jevNew.i
Global cyw43_joinSsidOk.i
Global cyw43_joinFail.i
Global cyw43_joinState.i
Global cyw43_joinTlink.i
Global cyw43_joinDone.i
Global cyw43_joinPhase.i
Global cyw43_linkLost.i
Global cyw43_joinT0.i
Global cyw43_hz.i = 1000
Global cyw43_icvCount.i

Procedure.i millis() : ProcedureReturn gate_ms : EndProcedure
Procedure NetDhcpLinkDown(kind.i) : gate_linkDown = gate_linkDown + 1 : EndProcedure
Procedure.i Cyw43EventName(t.i) : ProcedureReturn "event" : EndProcedure
Procedure str_print_at(p.i) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure UartWriteStr(p.i) : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PutIp(v.i) : EndProcedure
Procedure.i WifiRejoin(announce.i) : gate_rejoins = gate_rejoins + 1 : ProcedureReturn 1 : EndProcedure
Procedure WifiRecoveryCancel()
  gate_recCancels = gate_recCancels + 1 : gate_recActive = 0 : gWifiRecPhase = #WIFI_REC_IDLE
  gWifiRecGeneration = (gWifiRecGeneration + 1) & $FFFFFFFF
  gWifiEapolRecover = 0 : gWifiEapolRecoverStage = #WIFI_EAPOL_FAIL_NONE : gWifiEapolRecoverRc = 0
EndProcedure
Procedure WifiRecoveryStart(announce.i)
  If gate_inReceive <> 0 : gate_reentered = gate_reentered + 1 : EndIf
  gate_rejoins = gate_rejoins + 1 : WifiRecoveryCancel() : gate_recActive = 1
  gate_liveWipes = gate_liveWipes + 4 : wifi_RecordLinkDown()
EndProcedure
Procedure.i WifiRecoveryActive() : ProcedureReturn gate_recActive : EndProcedure
Procedure WifiRecoveryTick()
  gate_recTicks = gate_recTicks + 1
  If gWifiRecPhase = #WIFI_REC_JOIN_POLL
    gate_joinVerdict = Cyw43JoinPoll(20)
  EndIf
EndProcedure
Procedure.i NetDhcpStart(kind.i, automatic.i) : gate_dhcpStarts = gate_dhcpStarts + 1 : ProcedureReturn 1 : EndProcedure
Procedure.i Cyw43ReadBssid(ms.i) : gate_assocCalls = gate_assocCalls + 1 : ProcedureReturn gate_assoc : EndProcedure
Procedure.i wifi_KeepAliveArp(target.i) : ProcedureReturn gate_keepalive : EndProcedure
Procedure.i DhcpClientServer(kind.i) : ProcedureReturn 0 : EndProcedure
Procedure.i Cyw43EventsDropped() : ProcedureReturn cyw43_evrDropped : EndProcedure
Procedure.i Cyw43PopEvent() : ProcedureReturn cyw43_EvrPop() : EndProcedure
Procedure.i Cyw43JoinEventType() : ProcedureReturn cyw43_jevType : EndProcedure
Procedure.i Cyw43JoinEventReason() : ProcedureReturn cyw43_jevReason : EndProcedure
Procedure.i Cyw43JoinEventFlags() : ProcedureReturn cyw43_jevFlags : EndProcedure
Procedure.i Cyw43Receive(ms.i)
  gate_pumps = gate_pumps + 1
  ProcedureReturn gate_rxLen
EndProcedure
Procedure.i Cyw43ReceivePtr() : ProcedureReturn 0 : EndProcedure
Procedure.i HwLinkOfferRaw(kind.i, p.i, n.i)
  If gate_latchInPump <> 0
    gate_inReceive = 1
    wifi_RecordEapolFailure(#WIFI_EAPOL_FAIL_REKEY_M2_TX, -27, 1)
    gate_inReceive = 0 : gate_latchInPump = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NetInput(kind.i, p.i, n.i) : ProcedureReturn 0 : EndProcedure
Procedure HwLinkNoteRx(kind.i, n.i) : EndProcedure
Procedure NetServiceInput(kind.i, p.i, n.i) : EndProcedure
Procedure.i cyw43_Ticks() : ProcedureReturn gate_ms : EndProcedure
Procedure.i cyw43_PollEvent(ms.i) : gate_pollEvents = gate_pollEvents + 1 : ProcedureReturn 0 : EndProcedure
Procedure Wpa2SupWipe() : gate_liveWipes = gate_liveWipes + 1 : EndProcedure
Procedure Cyw43KeyWipe() : gate_liveWipes = gate_liveWipes + 1 : EndProcedure
Procedure AesWipe() : gate_liveWipes = gate_liveWipes + 1 : EndProcedure
Procedure KwWipe() : gate_liveWipes = gate_liveWipes + 1 : EndProcedure
'''
    main = r'''
Procedure GateReset()
  gate_pumps = 0 : gate_linkDown = 0 : gate_rejoins = 0
  gate_dhcpStarts = 0 : gate_assocCalls = 0 : gate_assoc = 1
  gate_keepalive = 0 : gate_ms = 100000
  gate_recActive = 0 : gate_recTicks = 0 : gate_recCancels = 0 : gate_joinVerdict = #CYW43_JOIN_RUNNING
  gate_liveWipes = 0 : gate_inReceive = 0 : gate_reentered = 0 : gate_latchInPump = 0 : gate_rxLen = 0
  gate_pollEvents = 0 : gWifiRecPhase = #WIFI_REC_IDLE : gWifiRecGeneration = 7
  gWifiLinkOn = 1 : gWifiUp = 1 : gWifiKeyed = 1 : gWifiHaveIp = 1
  gWifiSecDone = 1 : gWifiBadReads = 0 : gWifiTeardown = 0
  gWifiVerify = 0 : gWifiHealPend = 0 : gWifiHealLast = 0
  gWifiKaProbes = 0 : gWifiKaLast = gate_ms
  gWifiHealOn = 1 : gWifiTdType = 0 : gWifiTdReason = 0
  gWifiDropReq = 0 : gWifiRxProof = gate_ms : gWifiGw = 0
  gWifiConOwnsRx = 0 : gWifiRadioLast = 0
  gWifiEvtDrops = 0 : gWifiEvtLast = 0 : gWifiEvtType = 0 : gWifiEvtReason = 0
  gWifiDeauths = 0 : gWifiRoams = 0
  gWifiEapolFailStage = #WIFI_EAPOL_FAIL_NONE : gWifiEapolFailRc = 0
  gWifiEapolRecover = 0 : gWifiEapolRecoverStage = #WIFI_EAPOL_FAIL_NONE : gWifiEapolRecoverRc = 0
  cyw43_EvrClear() : cyw43_evrDropped = 0 : cyw43_evrTotal = 0
  cyw43_joinSsidOk = 0 : cyw43_joinFail = #CYW43_JOINFAIL_NONE
  cyw43_joinState = #CYW43_JS_ACTIVE : cyw43_joinTlink = gate_ms
  cyw43_joinDone = 0 : cyw43_joinPhase = 0 : cyw43_linkLost = 0
  cyw43_joinT0 = gate_ms
EndProcedure

Procedure.i Main()
  ; Policy off still services the radio, but does no health work.
  GateReset()
  gWifiLinkOn = 0
  WifiLinkTick()
  If gate_pumps <> 1 Or gate_assocCalls <> 0 Or gate_linkDown <> 0 : ProcedureReturn 1 : EndIf

  ; A definitive teardown is truth even when policy is off: no heal, but
  ; the live keyed/address claim and DHCP ownership are invalidated once.
  GateReset()
  gWifiLinkOn = 0 : gWifiTeardown = 1
  WifiLinkTick()
  If gate_pumps <> 1 Or gate_linkDown <> 1 Or gate_rejoins <> 0 : ProcedureReturn 2 : EndIf
  If gWifiKeyed <> 0 Or gWifiHaveIp <> 0 Or gWifiSecDone <> 0 Or gWifiTeardown <> 0 : ProcedureReturn 3 : EndIf

  ; Heal-off has the same truthful edge while ordinary policy remains on.
  GateReset()
  gWifiHealOn = 0 : gWifiTeardown = 1
  WifiLinkTick()
  If gate_linkDown <> 1 Or gate_rejoins <> 0 Or gWifiKeyed <> 0 : ProcedureReturn 4 : EndIf

  ; With both policy switches on, the existing recovery path owns teardown.
  GateReset()
  gWifiTeardown = 1
  WifiLinkTick()
  If gate_rejoins <> 1 Or gate_linkDown <> 1 Or gate_recActive = 0 : ProcedureReturn 5 : EndIf

  ; Two firmware NOTASSOCIATED answers plus heal-off mark the row down.
  GateReset()
  gate_assoc = 0 : gWifiBadReads = 1 : gWifiHealOn = 0
  gWifiKaLast = gate_ms - #WIFI_KA_MS
  WifiLinkTick()
  If gate_assocCalls <> 1 Or gate_linkDown <> 1 Or gWifiKeyed <> 0 : ProcedureReturn 6 : EndIf

  ; The TX-only proof path follows the same truthful no-heal transition.
  GateReset()
  gWifiHealOn = 0 : gWifiKaProbes = 2
  gWifiRxProof = gate_ms - #WIFI_PROOF_MS
  gWifiKaLast = gate_ms - #WIFI_KA_MS
  WifiLinkTick()
  If gate_assocCalls <> 1 Or gate_linkDown <> 1 Or gWifiHaveIp <> 0 : ProcedureReturn 7 : EndIf

  ; Real ring + real JoinPoll across the shipped WifiLinkTick boundary.
  ; AUTH was queued while SET_SSID waited for its control reply. The
  ; steady-state drain must not steal it before JoinPoll classifies it.
  GateReset()
  gate_recActive = 1 : gWifiRecPhase = #WIFI_REC_JOIN_POLL : gWifiKeyed = 0
  cyw43_joinState = #CYW43_JS_ACTIVE | #CYW43_JS_LINK | #CYW43_JS_KEYED
  cyw43_EvrPush(#CYW43_EV_AUTH, 0, 0, 0)
  WifiLinkTick()
  If gate_pumps <> 0 Or gate_recTicks <> 1 Or gate_joinVerdict <> #CYW43_JOIN_JOINED : ProcedureReturn 8 : EndIf
  If cyw43_evrCount <> 0 Or (cyw43_joinState & #CYW43_JS_AUTH) = 0 : ProcedureReturn 9 : EndIf

  ; Locally initiated LEAVE/DISASSOC fallout remains owned by the old
  ; recovery attempt. Multiple prompt turns neither latch teardown nor
  ; restart the generation; JoinStart's documented clear discards it.
  GateReset()
  gate_recActive = 1 : gWifiRecPhase = #WIFI_REC_QUIET : gWifiKeyed = 0
  cyw43_EvrPush(#CYW43_EV_LINK, 0, 0, 0)
  cyw43_EvrPush(#CYW43_EV_DISASSOC, 0, 0, 0)
  WifiLinkTick() : WifiLinkTick()
  If gate_pumps <> 0 Or gate_recTicks <> 2 Or gWifiTeardown <> 0 : ProcedureReturn 10 : EndIf
  If gate_rejoins <> 0 Or gWifiRecGeneration <> 7 Or cyw43_evrCount <> 2 : ProcedureReturn 11 : EndIf
  cyw43_EvrClear()
  If cyw43_evrCount <> 0 : ProcedureReturn 12 : EndIf

  ; A failed recovery's existing slow cadence starts one fresh generation;
  ; it does not call the old synchronous rejoin loop.
  GateReset()
  gWifiKeyed = 0 : gWifiHaveIp = 0 : gWifiHealPend = 1
  gWifiHealLast = gate_ms - #WIFI_HEAL_MS
  WifiLinkTick()
  If gate_rejoins <> 1 Or gate_recActive = 0 Or gate_linkDown <> 1 : ProcedureReturn 13 : EndIf

  ; Policy cancellation wins before an owned phase can resume.
  GateReset()
  gate_recActive = 1 : gWifiRecPhase = #WIFI_REC_JOIN_POLL : gWifiLinkOn = 0
  WifiLinkTick()
  If gate_recActive <> 0 Or gate_recTicks <> 0 : ProcedureReturn 14 : EndIf

  ; Heal-off also cancels an already-owned pre-DHCP generation before it can
  ; consume another join event. Radio service continues, but the cancelled
  ; generation is invalidated and recovery does not advance.
  GateReset()
  gate_recActive = 1 : gWifiRecPhase = #WIFI_REC_JOIN_POLL : gWifiHealOn = 0
  WifiLinkTick()
  If gate_recActive <> 0 Or gate_recTicks <> 0 Or gate_recCancels <> 1 : ProcedureReturn 24 : EndIf
  If gWifiRecGeneration <> 8 Or gate_pumps <> 1 : ProcedureReturn 25 : EndIf

  ; A failure latched while the production radio pump owns receive work cannot
  ; start recovery recursively. The outer service consumes it after the pump,
  ; preserves exact diagnostics and starts one generation.
  GateReset() : gate_latchInPump = 1 : gate_rxLen = 120
  WifiLinkTick()
  If gate_reentered <> 0 Or gate_pumps <> 1 Or gate_rejoins <> 1 : ProcedureReturn 26 : EndIf
  If gWifiEapolRecover <> 0 Or gWifiEapolFailStage <> #WIFI_EAPOL_FAIL_REKEY_M2_TX Or gWifiEapolFailRc <> -27 : ProcedureReturn 26 : EndIf
  WifiLinkTick()
  If gate_rejoins <> 1 Or gate_recTicks <> 1 : ProcedureReturn 26 : EndIf

  ; Heal policy may forbid a reconnect, but cannot bless a partially changed
  ; live key/session. Consume, wipe and record down even with healing disabled.
  GateReset() : gWifiHealOn = 0
  wifi_RecordEapolFailure(#WIFI_EAPOL_FAIL_REKEY_M4_GTK, -28, 1)
  WifiLinkTick()
  If gate_rejoins <> 0 Or gate_recCancels <> 1 Or gate_liveWipes <> 4 : ProcedureReturn 27 : EndIf
  If gate_linkDown <> 1 Or gWifiKeyed <> 0 Or gWifiHaveIp <> 0 Or gWifiEapolRecover <> 0 : ProcedureReturn 27 : EndIf

  ; Link policy off has the identical truth/cleanup requirement. The pump is
  ; entered, but immediate scalar invalidation makes its receive side ineligible;
  ; outer service still consumes the latch and leaves the identity down.
  GateReset() : gWifiLinkOn = 0
  wifi_RecordEapolFailure(#WIFI_EAPOL_FAIL_REKEY_G2_TX, -29, 1)
  WifiLinkTick()
  If gate_pumps <> 0 Or gate_rejoins <> 0 Or gate_liveWipes <> 4 : ProcedureReturn 28 : EndIf
  If gate_linkDown <> 1 Or gWifiKeyed <> 0 Or gWifiEapolRecover <> 0 : ProcedureReturn 28 : EndIf

  ; DHCP_WAIT is deliberately past the event/handshake ownership boundary:
  ; normal packet pumping resumes before the recovery observes the lease.
  GateReset()
  gate_recActive = 1 : gWifiRecPhase = #WIFI_REC_DHCP_WAIT
  WifiLinkTick()
  If gate_pumps <> 1 Or gate_recTicks <> 1 : ProcedureReturn 15 : EndIf

  ; A failed first boot join with a ready radio arms the same slow cooperative
  ; cadence. It performs no immediate scan/join and does not claim a lost
  ; association. One tick before the deadline is inert; the deadline starts
  ; exactly one recovery generation while wired service remains schedulable.
  GateReset() : gWifiKeyed = 0 : gWifiHaveIp = 0 : gate_ms = 5000
  WifiRecoveryInitialJoinFailed()
  If gWifiHealPend = 0 Or gWifiHealLast <> 5000 Or gate_rejoins <> 0 : ProcedureReturn 16 : EndIf
  gate_ms = 5000 + #WIFI_HEAL_MS - 1 : WifiLinkTick()
  If gate_rejoins <> 0 Or gate_recActive <> 0 : ProcedureReturn 17 : EndIf
  gate_ms = 5000 + #WIFI_HEAL_MS : WifiLinkTick()
  If gate_rejoins <> 1 Or gate_recActive = 0 : ProcedureReturn 18 : EndIf

  ; A radio-firmware bring-up failure is explicit and does not turn each
  ; prompt spin into another synchronous blob/init attempt. Policy-off likewise
  ; leaves the failed initial join down without arming a hidden retry.
  GateReset() : gWifiKeyed = 0 : gWifiHaveIp = 0 : gWifiUp = 0
  WifiRecoveryInitialJoinFailed()
  If gWifiHealPend <> 0 Or gate_rejoins <> 0 Or gate_linkDown <> 1 : ProcedureReturn 19 : EndIf
  gate_ms = gate_ms + #WIFI_HEAL_MS : WifiLinkTick()
  If gate_rejoins <> 0 Or gate_recActive <> 0 : ProcedureReturn 20 : EndIf
  GateReset() : gWifiKeyed = 0 : gWifiHaveIp = 0 : gWifiHealOn = 0
  WifiRecoveryInitialJoinFailed()
  If gWifiHealPend <> 0 Or gate_rejoins <> 0 : ProcedureReturn 21 : EndIf

  ; The 32-bit millisecond clock may wrap between scheduling and retry.
  GateReset() : gWifiKeyed = 0 : gWifiHaveIp = 0 : gate_ms = $FFFFFF00
  WifiRecoveryInitialJoinFailed()
  gate_ms = $00000100 : WifiLinkTick()
  If gate_rejoins <> 0 : ProcedureReturn 22 : EndIf
  gate_ms = ($FFFFFF00 + #WIFI_HEAL_MS) & $FFFFFFFF : WifiLinkTick()
  If gate_rejoins <> 1 Or gate_recActive = 0 : ProcedureReturn 23 : EndIf

  ProcedureReturn 0
EndProcedure
'''
    declarations = constants + "\n" + eapol_state
    prelude = prelude.replace("EnableExplicit", "EnableExplicit\n\n" + declarations, 1)
    return prelude + "\n" + cyw_bodies + "\n" + wifi_bodies + "\n" + main


def build(pmfc: Path, work: Path, probe: Path) -> Path:
    staged = work / pmfc.name
    shutil.copy2(pmfc, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards", dirs_exist_ok=True)
    image = work / "wifi_link_policy_gate.img"
    command = [
        str(staged), str(probe), "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("wifi link policy gate: compile failed\n" + run.stdout)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    boot_source = BOOT.read_text(encoding="utf-8")
    boot_body = procedure(boot_source, "BootNetUp")
    failure_branch = re.compile(
        r'Else\s+'
        r'PrintN\("Wi-Fi did not join any saved network\. The radio/firmware diagnostics above"\)\s+'
        r'PrintN\("name the failed stage; wired Ethernet remains available for recovery\."\)'
        r'.*?WifiRecoveryInitialJoinFailed\(\)\s+'
        r'ScreenServiceTick\(\)\s+'
        r'EndIf\s+gBootLog = 0',
        re.DOTALL,
    )
    if failure_branch.search(boot_body) is None:
        raise SystemExit("wifi link policy gate: BootNetUp initial-failure recovery hook is missing")
    boot_mutant = boot_body.replace("    WifiRecoveryInitialJoinFailed()", "    ; owner hook removed", 1)
    if failure_branch.search(boot_mutant) is not None:
        raise SystemExit("wifi link policy gate: BootNetUp failure-branch negative control survived")
    command_body = procedure(WIFI_CMD.read_text(encoding="utf-8"), "CmdWifi")
    status_tokens = (
        'UartWriteStr(wifi_EapolFailureName(gWifiEapolFailStage))',
        'PrintDec(gWifiEapolFailStage)',
        'PrintDec(gWifiEapolFailRc)',
        'If gWifiEapolRecover <> 0',
    )
    positions = [command_body.find(token) for token in status_tokens]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit("wifi link policy gate: ordered EAPOL failure status fields are missing")
    with tempfile.TemporaryDirectory(prefix="anvil-wifi-link-policy-emitted-") as temporary:
        work = Path(temporary)
        probe = work / "wifi_link_policy_gate.pi4"
        exact_source = probe_source()
        probe.write_text(exact_source, encoding="utf-8", newline="\n")
        image = build(pmfc, work, probe)
        result, steps = emitted.execute(a64, image)
        if result == 0:
            ownership = "If WifiRecoveryActive() <> 0 And gWifiRecPhase <> #WIFI_REC_DHCP_WAIT"
            if ownership not in exact_source:
                raise SystemExit("wifi link policy gate: ownership boundary not found for negative control")
            mutated = exact_source.replace(ownership, "If 0 <> 0 And gWifiRecPhase <> #WIFI_REC_DHCP_WAIT", 1)
            probe.write_text(mutated, encoding="utf-8", newline="\n")
            negative_image = build(pmfc, work, probe)
            negative_result, _ = emitted.execute(a64, negative_image)
            if negative_result != 8:
                print(f"wifi_link_policy_emitted_check: FAIL negative control returned {negative_result}, expected 8")
                return 1
            helper = procedure(exact_source, "wifi_RecordEapolFailure")
            reentrant = helper.replace(
                "    gWifiEapolRecover = 1",
                "    gWifiEapolRecover = 1\n    WifiRecoveryStart(1)",
                1,
            )
            if reentrant == helper:
                raise SystemExit("wifi link policy gate: callback-reentry mutation site not found")
            mutated = exact_source.replace(helper, reentrant, 1)
            probe.write_text(mutated, encoding="utf-8", newline="\n")
            negative_image = build(pmfc, work, probe)
            negative_result, _ = emitted.execute(a64, negative_image)
            if negative_result != 26:
                print(
                    "wifi_link_policy_emitted_check: FAIL callback-reentry mutant returned "
                    f"{negative_result}, expected 26"
                )
                return 1
    if result:
        print(f"wifi_link_policy_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(
        f"wifi_link_policy_emitted_check: PASS - 28 assertions, {steps:,} A64 instructions; "
        "pump-order/callback-reentry and BootNetUp-hook mutants rejected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
