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

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "RaspberryPi4" / "Lib" / "wifi.pi4"


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


def probe_source() -> str:
    source = WIFI.read_text(encoding="utf-8")
    bodies = "\n\n".join(
        (procedure(source, "wifi_RecordLinkDown"), procedure(source, "WifiLinkTick"))
    )
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

Global gWifiLinkOn.i
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

Procedure.i millis() : ProcedureReturn gate_ms : EndProcedure
Procedure WifiRadioPump() : gate_pumps = gate_pumps + 1 : EndProcedure
Procedure NetDhcpLinkDown(kind.i) : gate_linkDown = gate_linkDown + 1 : EndProcedure
Procedure.i Cyw43EventName(t.i) : ProcedureReturn "event" : EndProcedure
Procedure str_print_at(p.i) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure UartWriteStr(p.i) : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PutIp(v.i) : EndProcedure
Procedure.i WifiRejoin(announce.i) : gate_rejoins = gate_rejoins + 1 : ProcedureReturn 1 : EndProcedure
Procedure.i NetDhcpStart(kind.i, automatic.i) : gate_dhcpStarts = gate_dhcpStarts + 1 : ProcedureReturn 1 : EndProcedure
Procedure.i Cyw43ReadBssid(ms.i) : gate_assocCalls = gate_assocCalls + 1 : ProcedureReturn gate_assoc : EndProcedure
Procedure.i wifi_KeepAliveArp(target.i) : ProcedureReturn gate_keepalive : EndProcedure
Procedure.i DhcpClientServer(kind.i) : ProcedureReturn 0 : EndProcedure
'''
    main = r'''
Procedure GateReset()
  gate_pumps = 0 : gate_linkDown = 0 : gate_rejoins = 0
  gate_dhcpStarts = 0 : gate_assocCalls = 0 : gate_assoc = 1
  gate_keepalive = 0 : gate_ms = 100000
  gWifiLinkOn = 1 : gWifiKeyed = 1 : gWifiHaveIp = 1
  gWifiSecDone = 1 : gWifiBadReads = 0 : gWifiTeardown = 0
  gWifiVerify = 0 : gWifiHealPend = 0 : gWifiHealLast = 0
  gWifiKaProbes = 0 : gWifiKaLast = gate_ms
  gWifiHealOn = 1 : gWifiTdType = 0 : gWifiTdReason = 0
  gWifiDropReq = 0 : gWifiRxProof = gate_ms : gWifiGw = 0
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
  If gate_rejoins <> 1 Or gate_linkDown <> 0 : ProcedureReturn 5 : EndIf

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

  ProcedureReturn 0
EndProcedure
'''
    return prelude + "\n" + bodies + "\n" + main


def build(pmfc: Path, work: Path, probe: Path) -> Path:
    staged = work / pmfc.name
    shutil.copy2(pmfc, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
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
    with tempfile.TemporaryDirectory(prefix="anvil-wifi-link-policy-emitted-") as temporary:
        work = Path(temporary)
        probe = work / "wifi_link_policy_gate.pi4"
        probe.write_text(probe_source(), encoding="utf-8", newline="\n")
        image = build(pmfc, work, probe)
        result, steps = emitted.execute(a64, image)
    if result:
        print(f"wifi_link_policy_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"wifi_link_policy_emitted_check: PASS - 7 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
