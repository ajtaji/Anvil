#!/usr/bin/env python3
"""Compile/execute net_PinApply's identity-preservation regression gate.

The gate extracts the production procedure from net_cmd.pbi, compiles that
exact flow caller with explicit hardware/address seams, and executes emitted
A64 through the shared interpreter. It then restores the former binding tail
in an isolated generated source and requires the Wi-Fi identity assertion to
reject that historical behavior.
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
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
NET_CMD = ROOT / "Anvil" / "Core" / "net_cmd.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "net_pin_identity_emitted_gate.pi4"
MARKER = "; @@PRODUCTION_NET_PIN_APPLY@@"
OLD_TAIL = """  If LinkKind() <> #HW_LINK_NONE And EthHasIpConfig() <> 0
    NetAddressBound(LinkKind(), gEthIp, gEthMask, gEthGw, #NET_ADDR_SAVED)
  EndIf
"""


def extract_pin_apply(source: str) -> str:
    start_marker = "Procedure net_PinApply()"
    if source.count(start_marker) != 1:
        raise SystemExit(
            f"net pin identity gate: production start count {source.count(start_marker)}"
        )
    start = source.index(start_marker)
    end_marker = "EndProcedure"
    end = source.find(end_marker, start)
    if end < 0:
        raise SystemExit("net pin identity gate: production procedure has no end")
    end += len(end_marker)
    procedure = source[start:end] + "\n"
    if procedure.count("Procedure net_PinApply()") != 1 or procedure.count("EndProcedure") != 1:
        raise SystemExit("net pin identity gate: production procedure boundary drifted")
    return procedure


def fixture(procedure: str) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    if template.count(MARKER) != 1:
        raise SystemExit(
            f"net pin identity gate: fixture marker count {template.count(MARKER)}"
        )
    return template.replace(MARKER, procedure)


def historical_mutant(procedure: str) -> str:
    needle = "  LinkSay()\n"
    if procedure.count(needle) != 1:
        raise SystemExit(
            f"net pin identity gate: LinkSay insertion site count {procedure.count(needle)}"
        )
    return procedure.replace(needle, OLD_TAIL + needle, 1)


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile",
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
        raise SystemExit(f"net pin identity gate: {stem} compile failed\n{run.stdout}")
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"net pin identity gate: {stem} compiler omitted image or symbol map"
        )
    return image


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    production = extract_pin_apply(NET_CMD.read_text(encoding="utf-8"))
    mutant = historical_mutant(production)
    source_hash = sha256(production.encode("utf-8"))
    with tempfile.TemporaryDirectory(prefix="anvil-net-pin-identity-") as temporary:
        work = Path(temporary)
        fixed_image = build(compiler, work, fixture(production), "net_pin_identity_gate")
        result, steps = emitted.execute(a64, fixed_image)
        fixed_hash = sha256(fixed_image.read_bytes())
        if result:
            print(
                f"net_pin_identity_emitted_check: FAIL assertion {result} "
                f"after {steps:,} A64 instructions"
            )
            return 1

        mutant_image = build(
            compiler, work, fixture(mutant), "net_pin_identity_historical_mutant"
        )
        mutant_result, mutant_steps = emitted.execute(a64, mutant_image)
        mutant_hash = sha256(mutant_image.read_bytes())
        if mutant_result != 3:
            print(
                "net_pin_identity_emitted_check: FAIL historical binding-tail "
                f"mutation returned {mutant_result}; expected Wi-Fi identity assertion 3"
            )
            return 1

    print(
        "net_pin_identity_emitted_check: PASS - 27 assertions, "
        f"{steps:,} A64 instructions; historical tail rejected at assertion 3 "
        f"after {mutant_steps:,} instructions"
    )
    print(f"  production net_PinApply sha256 {source_hash}")
    print(f"  fixed image sha256 {fixed_hash}")
    print(f"  mutant image sha256 {mutant_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
