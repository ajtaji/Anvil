#!/usr/bin/env python3
"""Compile and execute the production network-console ownership gate.

Requires PMF_COMPILER and PMF_A64_INTERP (or --compiler/--interp). The execution
sandbox is the shared emitted-gate runner's image/BSS/stack whitelist.

Forum 888: an endpoint that stops talking must not keep the console. Four
mutants of the real Anvil/Core/netconsole.pbi restore a way it could, and each
must be caught by its own assertion.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler

CONSOLE = "Anvil/Core/netconsole.pbi"

# (fixed text, broken text, assertion that must fire, what it restores)
MUTATIONS = {
    "empty_claims": (
        "  If NetUdpRxLen() = 0\n    If netcon_PeerMatches(*frame, kind) <> 0\n",
        "  If NetUdpRxLen() = 1000000\n    If netcon_PeerMatches(*frame, kind) <> 0\n",
        52,
        "an empty keepalive taking the idle console",
    ),
    "never_lapses": (
        "  If gConOwner <> #NETCON_OWNER_NET Or gConAtPrompt = 0\n    ProcedureReturn 0\n",
        "  If 1 = 1\n    ProcedureReturn 0\n",
        55,
        "an owner with nothing in progress keeping the console until a restart",
    ),
    "lapses_mid_command": (
        "  If gConOwner <> #NETCON_OWNER_NET Or gConAtPrompt = 0\n",
        "  If gConOwner <> #NETCON_OWNER_NET\n",
        8,
        "a running command's console handed to another host - caught at the "
        "first refusal, which runs before any command has finished",
    ),
    "keeps_half_line": (
        "        If TextEditLength() > 0\n          TextEditDiscard()\n",
        "        If TextEditLength() > 1000000\n          TextEditDiscard()\n",
        60,
        "a silent host's half-typed line joined to the next host's typing",
    ),
}


def build_mutant(compiler: Path, work: Path, name: str) -> Path:
    fixed, broken, _, _ = MUTATIONS[name]
    text = (emitted.ROOT / CONSOLE).read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.count(fixed) != 1:
        raise SystemExit(f"netconsole owner mutant {name}: site drifted")
    mutated = work / "netconsole_mutant.pbi"
    mutated.write_text(text.replace(fixed, broken, 1), encoding="utf-8")
    probe = emitted.PROBE.read_text(encoding="utf-8")
    include = f'XIncludeFile "{CONSOLE}"'
    if probe.count(include) != 1:
        raise SystemExit("netconsole owner mutant: include drifted")
    staged = work / "netconsole_owner_mutant.pi4"
    staged.write_text(probe.replace(include, f'XIncludeFile "{mutated.as_posix()}"'), encoding="utf-8")
    saved = emitted.PROBE
    emitted.PROBE = staged
    try:
        return emitted.build(compiler, work)
    finally:
        emitted.PROBE = saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    emitted.PROBE = emitted.ROOT / "RaspberryPi4" / "Tests" / "netconsole_owner_emitted_gate.pi4"
    a64 = emitted.load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-netconsole-owner-emitted-") as temporary:
        image = emitted.build(compiler, Path(temporary))
        result, steps = emitted.execute(a64, image)
    if result:
        print(f"netconsole_owner_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    for name, (_, _, expected, why) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix=f"anvil-netconsole-owner-{name}-") as temporary:
            mutant = build_mutant(compiler, Path(temporary), name)
            got, _ = emitted.execute(a64, mutant)
        if got != expected:
            print(f"netconsole_owner_emitted_check: FAIL mutant {name} returned {got}; "
                  f"expected assertion {expected} ({why})")
            return 1
    print(f"netconsole_owner_emitted_check: PASS - 64 assertions, {steps:,} A64 instructions; "
          f"{len(MUTATIONS)} mutants caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
