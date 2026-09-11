#!/usr/bin/env python3
"""Compile/execute the TFTP transfer's route-and-preconditions gate.

The gate extracts NetXferServer from Anvil/Core/netcfg.pbi and the transfer
session block ending in EthStart from Anvil/Core/net_cmd.pbi, compiles those
exact procedures against explicit settings/route/hardware seams, and executes
the emitted A64 through the shared interpreter.

It then rebuilds the same fixture with each historical behaviour restored in
an isolated generated source and requires the gate to reject it:

  four-key      the EthConfig()-style precondition that made a transfer
                refuse on a board already holding three addresses
  selection     the route read off LinkKind() instead of the destination
  bind          the transfer's own port bound on the selected interface
  resolve       the next hop resolved against the selected interface
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
NETCFG = ROOT / "Anvil" / "Core" / "netcfg.pbi"
NET_CMD = ROOT / "Anvil" / "Core" / "net_cmd.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "net_xfer_route_emitted_gate.pi4"

SERVER_MARKER = "; @@PRODUCTION_NET_XFER_SERVER@@"
START_MARKER = "; @@PRODUCTION_ETH_START@@"

ASSERTIONS = 48

# The precondition that used to stand in front of every transfer. Restored
# verbatim in shape: all four keys or nothing happens.
FOUR_KEY_GATE = """  If SettingsHas(EthKeyAddress()) = 0 Or SettingsHas(EthKeyNetmask()) = 0 Or SettingsHas(EthKeyGateway()) = 0
    ProcedureReturn 0
  EndIf
"""


def extract(source: str, header: str, label: str) -> str:
    if source.count(header) != 1:
        raise SystemExit(
            f"net xfer route gate: {label} start count {source.count(header)}"
        )
    start = source.index(header)
    end = source.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"net xfer route gate: {label} has no end")
    end += len("\nEndProcedure")
    return source[start:end] + "\n"


def production() -> tuple[str, str]:
    server = extract(
        NETCFG.read_text(encoding="utf-8"),
        "Procedure.i NetXferServer()",
        "NetXferServer",
    )
    cmd = NET_CMD.read_text(encoding="utf-8")
    session_header = "Global gXferKind.i = #HW_LINK_NONE"
    if cmd.count(session_header) != 1:
        raise SystemExit(
            f"net xfer route gate: session field count {cmd.count(session_header)}"
        )
    session_start = cmd.index(session_header)
    start = extract(cmd[session_start:], "Procedure.i EthStart()", "EthStart")
    block = cmd[session_start : session_start + cmd[session_start:].index(start)] + start
    for required in ("Procedure.i XferKind()", "NetIfForDest(gEthSrv)", "NetXferServer()"):
        if required not in block:
            raise SystemExit(f"net xfer route gate: EthStart block lost {required!r}")
    return server, block


def fixture(server: str, start: str) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    for marker in (SERVER_MARKER, START_MARKER):
        if template.count(marker) != 1:
            raise SystemExit(
                f"net xfer route gate: fixture marker {marker} count "
                f"{template.count(marker)}"
            )
    return template.replace(SERVER_MARKER, server).replace(START_MARKER, start)


def mutate(start: str, name: str) -> str:
    """Restore one historical behaviour in the EthStart block."""
    if name == "four-key":
        needle = "  gEthSrv = NetXferServer()\n"
        replacement = FOUR_KEY_GATE + needle
    elif name == "selection":
        needle = "  k = NetIfForDest(gEthSrv)\n"
        replacement = "  k = LinkKind()\n"
    elif name == "bind":
        needle = "  If NetUdpBind(k, port) = 0\n"
        replacement = "  If NetUdpBind(LinkKind(), port) = 0\n"
    elif name == "resolve":
        needle = "  If NetResolveHop(k, gEthSrv) = 0\n"
        replacement = "  If NetResolveHop(LinkKind(), gEthSrv) = 0\n"
    else:
        raise SystemExit(f"net xfer route gate: unknown mutation {name}")
    if start.count(needle) != 1:
        raise SystemExit(
            f"net xfer route gate: {name} mutation site count {start.count(needle)}"
        )
    return start.replace(needle, replacement, 1)


def build(pmfc: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / pmfc.name
    if not staged.exists():
        shutil.copy2(pmfc, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    command = [
        str(staged),
        str(source),
        "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    run = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"net xfer route gate: {stem} compile failed\n{run.stdout}")
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"net xfer route gate: {stem} compiler omitted image or symbol map"
        )
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    server, start = production()
    digest = hashlib.sha256((server + start).encode("utf-8")).hexdigest()

    # Each mutation names the first assertion that must reject it.
    mutations = (
        ("four-key", 1),
        ("selection", 14),
        ("bind", 16),
        ("resolve", 15),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-net-xfer-route-") as temporary:
        work = Path(temporary)
        image = build(pmfc, work, fixture(server, start), "net_xfer_route_gate")
        result, steps = emitted.execute(a64, image)
        if result:
            print(
                f"net_xfer_route_emitted_check: FAIL assertion {result} "
                f"after {steps:,} A64 instructions"
            )
            return 1

        killed = []
        for name, expected in mutations:
            mutant = fixture(server, mutate(start, name))
            mutant_image = build(pmfc, work, mutant, f"net_xfer_route_mutant_{name}")
            mutant_result, mutant_steps = emitted.execute(a64, mutant_image)
            if mutant_result != expected:
                print(
                    f"net_xfer_route_emitted_check: FAIL {name} mutation returned "
                    f"{mutant_result}; expected assertion {expected}"
                )
                return 1
            killed.append((name, expected, mutant_steps))

    print(
        f"net_xfer_route_emitted_check: PASS - {ASSERTIONS} assertions, "
        f"{steps:,} A64 instructions"
    )
    for name, expected, mutant_steps in killed:
        print(
            f"  {name} mutation rejected at assertion {expected} "
            f"after {mutant_steps:,} instructions"
        )
    print(f"  production NetXferServer+EthStart sha256 {digest}")
    print("No hardware was contacted; the link, the route and the settings store")
    print("are modelled seams, so this is a source and emitted-code proof only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
