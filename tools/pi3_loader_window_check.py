#!/usr/bin/env python3
"""Desk gate for the Pi 3 immutable loader's whole pre-branch watchdog window."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = ROOT / "RaspberryPi3/Board/loader.pi3"
UPDATER = ROOT / "RaspberryPi3/Board/updater.pi3"
AB = ROOT / "RaspberryPi3/Lib/update_ab.pbi"
WATCHDOG = ROOT / "RaspberryPi3/Lib/update_watchdog.pbi"


def procedure(text: str, name: str) -> str:
    match = re.search(
        rf"Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)EndProcedure",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("missing procedure " + name)
    return match.group(1)


def ordered(text: str, needles: tuple[str, ...]) -> None:
    at = -1
    for needle in needles:
        found = text.find(needle, at + 1)
        if found < 0:
            raise ValueError("missing or out-of-order loader boundary: " + needle)
        at = found


def contract(loader: str, updater: str, ab: str, watchdog: str) -> None:
    main = procedure(loader, "Main")
    ordered(main, (
        'Pi3Say("L0: arm 15-second pre-branch watchdog")',
        "Pi3UpdateBootProgressHandler(@Pi3LoaderBootProgress)",
        "Pi3UpdateWatchdogArmWindow()",
        "Pi3UpdateLoad",
        'Pi3Say("L5: write handoff identity")',
        "Pi3UpdatePrepareHandoff",
        'Pi3Say("L6: watchdog owned; branch to payload")',
        "Pi3UpdateEnter()",
    ))
    if "Pi3UpdateWatchdogArm()" in main:
        raise ValueError("loader feeds/restarts watchdog after slot load")
    progress = procedure(loader, "Pi3LoaderBootProgress")
    for phase in range(1, 5):
        if f"Case {phase}" not in progress or f'L{phase}:' not in progress:
            raise ValueError(f"loader lost serial/LED phase L{phase}")
    if "Pi3StatusLed(phase & 1)" not in progress:
        raise ValueError("loader lost persistent LED phase state")
    ab_load = procedure(ab, "Pi3UpdateLoad")
    ab_place = procedure(ab, "pi3UpPlace")
    for phase, body in ((1, ab_load), (2, ab_load), (3, ab_place), (4, ab_place)):
        if f"BootProgress({phase})" not in body:
            raise ValueError(f"A/B owner lost phase {phase} at its blocking boundary")
    ordered(ab_load, (
        "Pi3UpBootProgress(1)",
        "pi3UpVerifySlot(slot)",
        "Pi3UpBootProgress(2)",
        "pi3UpState(slot, #PI3_UPDATE_TRIED)",
    ))
    ordered(ab_place, (
        "pi3UpBootProgress(3)",
        "pi3UpVerifySlot(slot)",
        "pi3UpBootProgress(4)",
        "For n = 0 To bytes - 1",
    ))
    progress_dispatch = procedure(ab, "pi3UpBootProgress")
    if "ProcedureReturn pi3_up_boot_progress()" not in progress_dispatch:
        raise ValueError("A/B owner lost the registered progress callback dispatch")
    window = procedure(watchdog, "Pi3UpdateWatchdogArmWindow")
    executable = "\n".join(line.split(";", 1)[0] for line in window.splitlines())
    if re.search(r"\b(for|next|while|wend|repeat|until)\b", executable, re.IGNORECASE):
        raise ValueError("pre-branch watchdog owner hides a wait loop")
    if window.count("$5A0F0000") != 1 or window.count("p3uwWrite($3F10001C") != 1:
        raise ValueError("pre-branch watchdog must be armed exactly once")
    arm = procedure(watchdog, "Pi3UpdateWatchdogArm")
    if "pi3_update_watchdog_window_owned" not in arm or "ProcedureReturn (p3uwRead($3F10001C) & $30)=$20" not in arm:
        raise ValueError("post-load ownership check can feed the existing window")
    up_main = procedure(updater, "Main")
    if up_main.find('pi3ut_WriteLine("C0: candidate Main entered")') < 0:
        raise ValueError("candidate has no earliest source-level entry evidence")
    if up_main.find('pi3ut_WriteLine("C0: candidate Main entered")') > up_main.find("Pi3UpdateBootStart(0)"):
        raise ValueError("candidate entry evidence occurs after a blocking boot call")


def compile_image(compiler: pathlib.Path, source: pathlib.Path, output: pathlib.Path) -> None:
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    result = subprocess.run(
        [str(compiler), "--compile", str(source.relative_to(ROOT)).replace("\\", "/"),
         "-t", "pi3", "-o", str(output), "-s"],
        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if result.returncode or not output.is_file():
        raise SystemExit("Pi3 loader window compile failed:\n" + result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER") or
                        r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
    args = parser.parse_args()
    compiler = pathlib.Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit("missing unified compiler: " + str(compiler))
    originals = tuple(path.read_text(encoding="utf-8") for path in (LOADER, UPDATER, AB, WATCHDOG))
    contract(*originals)
    mutants = (
        (originals[0].replace("If Pi3UpdateWatchdogArmWindow()=0", "If Pi3UpdateWatchdogArm()=0", 1), *originals[1:]),
        (originals[0].replace("Pi3UpdateBootProgressHandler(@Pi3LoaderBootProgress)", "Pi3NoBootProgress()", 1), *originals[1:]),
        (originals[0].replace('Pi3Say("L5: write handoff identity")', 'Pi3Say("stage missing")', 1), *originals[1:]),
        (originals[0], originals[1].replace('pi3ut_WriteLine("C0: candidate Main entered")', "", 1), originals[2], originals[3]),
        (originals[0], originals[1], originals[2].replace("Pi3UpBootProgress(2)", "Pi3UpBootProgress(1)", 1), originals[3]),
        (originals[0], originals[1], originals[2], originals[3].replace("$5A0F0000", "$5A0E0000", 1)),
    )
    for index, mutant in enumerate(mutants, 1):
        try:
            contract(*mutant)
        except ValueError:
            continue
        raise SystemExit(f"Pi3 loader window mutant {index} survived")
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-loader-window-") as temp_name:
        temp = pathlib.Path(temp_name)
        loader_image = temp / "kernel8.img"
        updater_image = temp / "updater.img"
        compile_image(compiler, LOADER, loader_image)
        compile_image(compiler, UPDATER, updater_image)
        print("PASS: watchdog ownership precedes every selected-slot blocking phase and is never fed")
        print("PASS: L0-L6 serial/LED boundaries and earliest C0 candidate entry evidence")
        print(f"PASS: {len(mutants)} hostile structural mutants rejected")
        print(f"Loader: {loader_image.stat().st_size} bytes; SHA256 {hashlib.sha256(loader_image.read_bytes()).hexdigest().upper()}")
        print(f"Updater: {updater_image.stat().st_size} bytes; SHA256 {hashlib.sha256(updater_image.read_bytes()).hexdigest().upper()}")
        print(f"Compiler SHA256: {hashlib.sha256(compiler.read_bytes()).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
