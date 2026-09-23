#!/usr/bin/env python3
"""Compile/execute the link/address status-truth gate.

The gate extracts the #LINK_WHY_* codes, LinkSelect and LinkWhyText from
RaspberryPi4/Lib/link.pi4 and NetAddrFromText from Anvil/Core/netcfg.pbi,
compiles those exact procedures against explicit interface-row seams, and
executes the emitted A64 through the shared interpreter.

Both recorded misleading-status defects are then restored, one at a time, in
an isolated generated source, and the gate must reject each:

  pin-hides-cable   the pin applied by zeroing the other interface's facts,
                    which is what stamped "there is nothing plugged into the
                    Ethernet socket" over a cable that was in and addressed
  wired-globals     the address provenance read out of gEthAddrFrom/gEthIp
                    instead of the selected interface's own row
  wired-address     only the address half restored, so the sharper
                    link-local warning follows the wired port's address
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
LINK = ROOT / "RaspberryPi4" / "Lib" / "link.pi4"
NETCFG = ROOT / "Anvil" / "Core" / "netcfg.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "link_status_truth_emitted_gate.pi4"

CODES_MARKER = "; @@PRODUCTION_LINK_WHY_CODES@@"
SELECT_MARKER = "; @@PRODUCTION_LINK_SELECT@@"
TEXT_MARKER = "; @@PRODUCTION_LINK_WHY_TEXT@@"
ADDR_MARKER = "; @@PRODUCTION_NET_ADDR_FROM_TEXT@@"

ASSERTIONS = 44

# The pin as it was applied before 2026-09-10: the caller hid the other
# interface's facts and LinkSelect stamped a reason about hardware.
HISTORICAL_PIN = """  If pin = #HW_LINK_WIRED
    wifiUp = 0
    wifiIp = 0
  ElseIf pin = #HW_LINK_WIFI
    wiredLink = 0
    wiredIp = 0
  EndIf
"""


def extract_procedure(source: str, header: str, label: str) -> str:
    if source.count(header) != 1:
        raise SystemExit(
            f"link status truth gate: {label} start count {source.count(header)}"
        )
    start = source.index(header)
    end = source.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"link status truth gate: {label} has no end")
    return source[start : end + len("\nEndProcedure")] + "\n"


def extract_codes(source: str) -> str:
    first = "#LINK_WHY_UNSET      = 0"
    last = "#LINK_WHY_PIN_DOWN   = 11"
    if source.count(first) != 1 or source.count(last) != 1:
        raise SystemExit("link status truth gate: reason-code block boundary drifted")
    start = source.index(first)
    end = source.index("\n", source.index(last))
    block = source[start:end] + "\n"
    for name in (
        "#LINK_WHY_WIRED_BOTH",
        "#LINK_WHY_WIFI_NOCBL",
        "#LINK_WHY_PINNED",
        "#LINK_WHY_PIN_BARE",
        "#LINK_WHY_PIN_DOWN",
    ):
        if name not in block:
            raise SystemExit(f"link status truth gate: reason-code block lost {name}")
    return block


def production() -> dict[str, str]:
    link = LINK.read_text(encoding="utf-8")
    netcfg = NETCFG.read_text(encoding="utf-8")
    select = extract_procedure(
        link, "Procedure.i LinkSelect(pin.i, wiredLink.i", "LinkSelect"
    )
    if "gLinkWhy = w" not in select:
        raise SystemExit("link status truth gate: LinkSelect no longer stamps a reason")
    addr = extract_procedure(
        netcfg, "Procedure.i NetAddrFromText(kind.i)", "NetAddrFromText"
    )
    return {
        "codes": extract_codes(link),
        "select": select,
        "text": extract_procedure(link, "Procedure.i LinkWhyText()", "LinkWhyText"),
        "addr": addr,
    }


def fixture(parts: dict[str, str]) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    for marker in (CODES_MARKER, SELECT_MARKER, TEXT_MARKER, ADDR_MARKER):
        if template.count(marker) != 1:
            raise SystemExit(
                f"link status truth gate: fixture marker {marker} count "
                f"{template.count(marker)}"
            )
    return (
        template.replace(CODES_MARKER, parts["codes"])
        .replace(SELECT_MARKER, parts["select"])
        .replace(TEXT_MARKER, parts["text"])
        .replace(ADDR_MARKER, parts["addr"])
    )


def mutate(parts: dict[str, str], name: str) -> dict[str, str]:
    out = dict(parts)
    if name == "pin-hides-cable":
        head = "  If pin <> #HW_LINK_NONE\n"
        select = out["select"]
        if select.count(head) != 1:
            raise SystemExit(
                f"link status truth gate: pin arm site count {select.count(head)}"
            )
        start = select.index(head)
        tail = "    ProcedureReturn k\n  EndIf\n"
        if select.count(tail) != 1:
            raise SystemExit("link status truth gate: pin arm has no recognisable end")
        end = select.index(tail) + len(tail)
        out["select"] = select[:start] + HISTORICAL_PIN + select[end:]
        return out
    if name in ("wired-globals", "wired-address"):
        addr = out["addr"]
        needle = "  If NetIsLinkLocal(NetIPv4(kind)) <> 0\n"
        if addr.count(needle) != 1:
            raise SystemExit(
                f"link status truth gate: address-test site count {addr.count(needle)}"
            )
        addr = addr.replace(needle, "  If NetIsLinkLocal(gEthIp) <> 0\n", 1)
        if name == "wired-globals":
            src = "  src = NetIfSrc(kind)\n"
            if addr.count(src) != 1:
                raise SystemExit(
                    f"link status truth gate: provenance site count {addr.count(src)}"
                )
            addr = addr.replace(src, "  src = gEthAddrFrom\n", 1)
        out["addr"] = addr
        return out
    raise SystemExit(f"link status truth gate: unknown mutation {name}")


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
        raise SystemExit(f"link status truth gate: {stem} compile failed\n{run.stdout}")
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"link status truth gate: {stem} compiler omitted image or symbol map"
        )
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    parts = production()
    digest = hashlib.sha256(
        "".join(parts[k] for k in ("codes", "select", "text", "addr")).encode("utf-8")
    ).hexdigest()

    mutations = (
        ("pin-hides-cable", 5),
        ("wired-globals", 36),
        ("wired-address", 41),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-link-status-truth-") as temporary:
        work = Path(temporary)
        image = build(compiler, work, fixture(parts), "link_status_truth_gate")
        result, steps = emitted.execute(a64, image)
        if result:
            print(
                f"link_status_truth_emitted_check: FAIL assertion {result} "
                f"after {steps:,} A64 instructions"
            )
            return 1

        killed = []
        for name, expected in mutations:
            mutant = fixture(mutate(parts, name))
            mutant_image = build(compiler, work, mutant, f"link_status_truth_mutant_{name}")
            mutant_result, mutant_steps = emitted.execute(a64, mutant_image)
            if mutant_result != expected:
                print(
                    f"link_status_truth_emitted_check: FAIL {name} mutation returned "
                    f"{mutant_result}; expected assertion {expected}"
                )
                return 1
            killed.append((name, expected, mutant_steps))

    print(
        f"link_status_truth_emitted_check: PASS - {ASSERTIONS} assertions, "
        f"{steps:,} A64 instructions"
    )
    for name, expected, mutant_steps in killed:
        print(
            f"  {name} mutation rejected at assertion {expected} "
            f"after {mutant_steps:,} instructions"
        )
    print(f"  production codes+LinkSelect+LinkWhyText+NetAddrFromText sha256 {digest}")
    print("No hardware was contacted; the interface rows are modelled seams, so")
    print("this is a source and emitted-code proof only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
