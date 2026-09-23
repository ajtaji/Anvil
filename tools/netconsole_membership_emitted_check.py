#!/usr/bin/env python3
"""Emit exact console preference/disarm procedures with deterministic seams."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
NETCON = ROOT / "Anvil" / "Core" / "netconsole.pbi"


def procedure(source: str, name: str) -> str:
    starts = (f"Procedure {name}(", f"Procedure.i {name}(")
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith(starts)), None)
    if first is None:
        raise SystemExit(f"netconsole membership gate: production procedure {name} not found")
    last = next((i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure"), None)
    if last is None:
        raise SystemExit(f"netconsole membership gate: production procedure {name} has no end")
    return "\n".join(lines[first : last + 1])


def probe_source() -> str:
    source = NETCON.read_text(encoding="utf-8")
    bodies = "\n\n".join(
        procedure(source, name)
        for name in ("netcon_PublishDisarmed", "netcon_Disarm", "NetConsoleRearm")
    )
    prelude = r'''
EnableExplicit
#HW_LINK_NONE = 0
#HW_LINK_WIRED = 1
#HW_LINK_WIFI = 2
#NETIF_KINDS = 6
#NETCON_OWNER_NONE = 0
#NETCON_OWNER_NET = 1
#NETCON_PORT = 5555

Global gConOn.i
Global gConMemberMask.i
Global gConKind.i
Global gConIp.i
Global gConPeerKind.i
Global gConPeerDstIp.i
Global gConPeerOk.i
Global gConOwner.i
Global gConInHead.i
Global gConInTail.i
Global gConPeerIp.i
Global gConPeerPort.i
Global Dim gConPeerMac.a[6]
Global gate_preferred.i
Global Dim gate_ip.i[6]
Global Dim gate_alt.i[6]
Global Dim gate_usable.a[6]
Global gate_notify.i
Global gate_wifiOwner.i
; The console's port is a PERSISTENT LISTENER, taken and given back on the
; same membership edges as driver receive ownership - so a disarm that
; published an off edge and left the port owned would leave the IP layer
; delivering to a console that is no longer there.
Global gate_listen.i
Global gate_listenCalls.i

Procedure str_print_at(p.i) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure.i NetIfPreferred() : ProcedureReturn gate_preferred : EndProcedure
Procedure.i NetIfUsable(kind.i) : ProcedureReturn gate_usable[kind] & $FF : EndProcedure
Procedure.i NetIPv4(kind.i) : ProcedureReturn gate_ip[kind] : EndProcedure
Procedure.i NetIPv4Alt(kind.i) : ProcedureReturn gate_alt[kind] : EndProcedure
Procedure NetUdpBind(kind.i, port.i) : EndProcedure
Procedure NetUdpListen(kind.i, port.i, on.i)
  gate_listenCalls = gate_listenCalls + 1
  If kind = #HW_LINK_WIFI And port = #NETCON_PORT
    gate_listen = on
  EndIf
EndProcedure
Procedure NetConsoleSayLinks() : EndProcedure
Procedure NetConsoleStart(kind.i) : EndProcedure
Procedure netcon_ForgetOwner() : gConOwner = #NETCON_OWNER_NONE : EndProcedure
Procedure HwLinkConsoleArmed(kind.i, on.i)
  gate_notify = gate_notify + 1
  If kind = #HW_LINK_WIFI
    If on <> 0 : gate_wifiOwner = 1 : Else : gate_wifiOwner = 0 : EndIf
  EndIf
EndProcedure
'''
    main = r'''
Procedure.i Main()
  ; A route-preference announcement change before any receive walk has no
  ; authority to claim Wi-Fi's queue. Immediate disarm therefore has no
  ; unrecorded owner to strand.
  gConOn = 1
  gConKind = #HW_LINK_WIRED
  gConIp = $A9FEAAFA
  gConMemberMask = 0
  gate_preferred = #HW_LINK_WIFI
  gate_ip[#HW_LINK_WIFI] = $C0A80110
  gate_usable[#HW_LINK_WIFI] = 1
  NetConsoleRearm()
  If gConKind <> #HW_LINK_WIFI Or gConMemberMask <> 0 Or gate_notify <> 0 Or gate_wifiOwner <> 0 : ProcedureReturn 1 : EndIf
  netcon_Disarm()
  If gate_notify <> 0 Or gate_wifiOwner <> 0 Or gConMemberMask <> 0 : ProcedureReturn 2 : EndIf
  ; Nothing was a member, so no port was given back either.
  If gate_listenCalls <> 0 : ProcedureReturn 4 : EndIf

  ; A queue that an actual receive walk recorded is explicitly released.
  gConOn = 1
  gConMemberMask = 1 << #HW_LINK_WIFI
  gate_wifiOwner = 1
  gate_notify = 0
  gate_listen = 1
  gate_listenCalls = 0
  netcon_Disarm()
  If gate_notify <> 1 Or gate_wifiOwner <> 0 Or gConMemberMask <> 0 : ProcedureReturn 3 : EndIf
  ; THE PORT GOES BACK WITH THE MEMBERSHIP, on the same edge and once.
  If gate_listen <> 0 Or gate_listenCalls <> 1 : ProcedureReturn 5 : EndIf
  ProcedureReturn 0
EndProcedure
'''
    return prelude + "\n" + bodies + "\n" + main


def build(compiler: Path, work: Path, probe: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "netconsole_membership_gate.img"
    command = [
        str(staged), "--compile", str(probe), "-t", "pi4",
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
        raise SystemExit("netconsole membership gate: compile failed\n" + run.stdout)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-netconsole-membership-emitted-") as temporary:
        work = Path(temporary)
        probe = work / "netconsole_membership_gate.pi4"
        probe.write_text(probe_source(), encoding="utf-8", newline="\n")
        image = build(compiler, work, probe)
        result, steps = emitted.execute(a64, image)
    if result:
        print(f"netconsole_membership_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"netconsole_membership_emitted_check: PASS - 5 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
