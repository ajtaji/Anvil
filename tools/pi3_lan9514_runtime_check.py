#!/usr/bin/env python3
"""Desk gate for Pi 3 LAN9514 bring-up and bounded bulk frame runtime."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import subprocess
import tempfile

from pi3_usb_enumeration_check import execute, load_interpreter, require

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = ROOT / "RaspberryPi3" / "Tests" / "lan9514_runtime_host.pb"
EMITTED = ROOT / "RaspberryPi3" / "Tests" / "lan9514_runtime_emitted.pi3"
SOURCE = ROOT / "RaspberryPi3" / "Lib" / "lan9514_runtime.pbi"
PINNED = pathlib.Path(r"C:\Embedded Compiler\Datasheets\pi3\raspberrypi-linux-reference")
LOAD = 0x02000000
STACK = 0x03000000


def checked(command: list[str], env=None) -> str:
    result = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode:
        raise SystemExit("Pi3 LAN9514 runtime gate failed:\n" + result.stdout)
    return result.stdout


def body(text: str, name: str) -> str:
    match = re.search(
        rf"Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)EndProcedure",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise SystemExit("Pi3 LAN9514 runtime gate: missing " + name)
    return match.group(1)


def static_contract() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    for name in ("Pi3LanRuntimeStep", "Pi3LanBulkStep"):
        executable = "\n".join(line.split(";", 1)[0] for line in body(text, name).splitlines())
        if re.search(r"\b(while|wend|repeat|until|for|next)\b", executable, re.IGNORECASE):
            raise SystemExit(name + " contains a hidden wait/retry loop")
    required = (
        "#P3_LAN_PHY_ID = 1",
        "#P3_LAN_RX_BURST_BYTES = 2560",
        "#P3_LAN_RX_BURST_PACKETS = 5",
        "#P3_LAN_BULK_DELAY = $00002000",
        "#P3_LAN_AFC_DEFAULT = $00F830A1",
        "p3lan_runtime_value & (#P3_LAN_BMSR_LINK | #P3_LAN_BMSR_ANEG_COMPLETE)",
        "p3lan_runtime_quarantine=1",
        "bus+p3lan_bulk_offset",
        "p3lan_bulk_retries_left-1",
        "p3lan_runtime_tx_pid=p3lan_bulk_pid",
        "p3lan_runtime_rx_pid=p3lan_bulk_pid",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("Pi3 LAN9514 runtime contract missing: " + ", ".join(missing))
    smsc = require(PINNED / "drivers/net/usb/smsc95xx.c", "pinned smsc95xx.c").read_text(encoding="utf-8")
    header = require(PINNED / "drivers/net/usb/smsc95xx.h", "pinned smsc95xx.h").read_text(encoding="utf-8")
    for fact in (
        "#define SMSC95XX_INTERNAL_PHY_ID\t(1)",
        "DEFAULT_BULK_IN_DELAY",
        "DEFAULT_HS_BURST_CAP_SIZE",
        "smsc95xx_start_tx_path",
        "smsc95xx_start_rx_path",
        "first, a dummy read, needed to latch some MII phys",
    ):
        if fact not in smsc and fact not in header:
            raise SystemExit("pinned SMSC95xx authority lost fact: " + fact)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER") or
                        r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
    parser.add_argument("--purebasic", default=os.environ.get("PB_COMPILER") or
                        r"C:\Users\rajta\AppData\Local\Programs\PureBasic\Compilers\pbcompiler.exe")
    args = parser.parse_args()
    compiler = require(pathlib.Path(args.compiler), "unified IDE compiler")
    purebasic = require(pathlib.Path(args.purebasic), "host PureBasic compiler")
    static_contract()
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-lan-runtime-") as temp_name:
        temp = pathlib.Path(temp_name)
        host_exe = temp / "lan9514_runtime_host.exe"
        image = temp / "lan9514_runtime.img"
        checked([str(purebasic), "/CONSOLE", "/QUIET", "/EXE", str(host_exe), str(HOST)])
        checked([str(host_exe)])
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        checked([
            str(compiler), "--compile", str(EMITTED.relative_to(ROOT)).replace("\\", "/"),
            "-t", "pi3", "--entry-returns", "--load-addr", hex(LOAD),
            "--stack-addr", hex(STACK), "-o", str(image), "-s",
        ], env)
        if not image.is_file():
            raise SystemExit("Pi3 LAN9514 runtime gate: compiler produced no image")
        a64 = load_interpreter()
        expected = {1: 101, 2: 72, 3: 60}
        total_steps = 0
        for operation, wanted in expected.items():
            actual, steps = execute(a64, image, operation)
            total_steps += steps
            if actual != wanted:
                raise SystemExit(f"emitted operation {operation}: {actual:#x} != {wanted:#x}")
        print("PASS: Linux-ordered LAN9514 reset/config/autoneg/link hostile host gate")
        print("PASS: partial NAK resume, endpoint toggles, aggregates, detach and halt quarantine")
        print("PASS: runtime and bulk Step procedures contain no hidden wait/retry loop")
        print(f"PASS: 3 emitted A64 cases, {total_steps} interpreted instructions")
        print(f"Emitted SHA256: {hashlib.sha256(image.read_bytes()).hexdigest().upper()}")
        print(f"Compiler SHA256: {hashlib.sha256(compiler.read_bytes()).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
