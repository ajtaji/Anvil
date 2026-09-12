#!/usr/bin/env python3
"""Desk gate for scheduler-owned Pi 3 USB control and LAN9514 enumeration."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = ROOT / "RaspberryPi3" / "Tests" / "usb_enumeration_host.pb"
EMITTED = ROOT / "RaspberryPi3" / "Tests" / "usb_enumeration_emitted.pi3"
CONTROL = ROOT / "RaspberryPi3" / "Lib" / "usb_control.pbi"
ENUMERATION = ROOT / "RaspberryPi3" / "Lib" / "usb_enumeration.pbi"
INTERPRETER = ROOT / "tools" / "a64" / "a64_interp.py"
PINNED = pathlib.Path(
    r"C:\Embedded Compiler\Datasheets\pi3\raspberrypi-linux-reference"
)
LOAD = 0x02000000
STACK = 0x03000000
ARGS = 0x06000000
RETURN_PC = 0xDEAD0000


def require(path: pathlib.Path, label: str) -> pathlib.Path:
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"Pi 3 USB enumeration gate: {label} not found: {path}")
    return path


def run(command: list[str], cwd: pathlib.Path, env=None) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode:
        raise SystemExit(
            "Pi 3 USB enumeration gate: command failed\n"
            + " ".join(command) + "\n" + result.stdout
        )
    return result.stdout


def procedure_body(text: str, name: str) -> str:
    match = re.search(
        rf"Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)EndProcedure",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise SystemExit(f"Pi 3 USB enumeration gate: missing procedure {name}")
    return match.group(1)


def static_contract() -> None:
    control = CONTROL.read_text(encoding="utf-8")
    step = procedure_body(control, "Pi3UsbControlStep")
    executable_step = "\n".join(line.split(";", 1)[0] for line in step.splitlines())
    if re.search(r"\b(while|wend|repeat|until|for|next)\b", executable_step, re.IGNORECASE):
        raise SystemExit("Pi 3 USB enumeration gate: control step contains a hidden loop")
    if step.count("Pi3UsbChannelTransfer(") != 3:
        raise SystemExit("Pi 3 USB enumeration gate: control stages do not each own one submit site")
    required = (
        "#P3_USB_PID_SETUP = 3", "#P3_USB_PID_DATA1 = 2",
        "#P3_USB_CONTROL_RETRY", "p3usb_control_retries_left-1",
        "p3usb_enum_wait_until=nowUs+10000", "p3usb_enum_wait_until=nowUs+20000",
        "#P3_USB_LAN_HUB_PID", "#P3_USB_LAN_PID",
        "#P3_USB_ENUM_FINAL_STATUS_WAIT", "#P3_USB_ENUM_PUBLISH",
    )
    combined = control + ENUMERATION.read_text(encoding="utf-8")
    missing = [item for item in required if item not in combined]
    if missing:
        raise SystemExit("Pi 3 USB enumeration gate: missing contract: " + ", ".join(missing))
    if not (PINNED / "drivers" / "net" / "usb" / "smsc95xx.c").is_file():
        raise SystemExit("Pi 3 USB enumeration gate: pinned SMSC95xx source is absent")
    dtsi = PINNED / "arch" / "arm" / "boot" / "dts" / "broadcom" / "bcm283x-rpi-smsc9514.dtsi"
    source = require(dtsi, "pinned Pi 3 topology").read_text(encoding="utf-8")
    for fact in ('compatible = "usb424,9514"', 'compatible = "usb424,ec00"', "reg = <1>"):
        if fact not in source:
            raise SystemExit(f"Pi 3 USB enumeration gate: pinned topology lost {fact}")


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_usb_enum_a64", INTERPRETER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Pi 3 USB enumeration gate: cannot load {INTERPRETER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def put64(cpu, address: int, value: int) -> None:
    for offset in range(8):
        cpu.memory[address + offset] = (value >> (offset * 8)) & 0xFF


def execute(a64, image: pathlib.Path, operation: int) -> tuple[int, int]:
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    put64(cpu, ARGS, operation)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    for steps in range(2_000_000):
        if cpu.pc == RETURN_PC:
            return cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"Pi 3 USB enumeration gate: operation {operation} did not return")


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

    with tempfile.TemporaryDirectory(prefix="anvil-pi3-usb-enum-") as temp_name:
        temp = pathlib.Path(temp_name)
        host_exe = temp / "usb_enumeration_host.exe"
        run([str(purebasic), "/CONSOLE", "/QUIET", "/EXE", str(host_exe), str(HOST)], ROOT)
        run([str(host_exe)], ROOT)

        image = temp / "usb_enumeration.img"
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        run([
            str(compiler), "--compile", str(EMITTED.relative_to(ROOT)).replace("\\", "/"),
            "-t", "pi3", "--entry-returns", "--load-addr", hex(LOAD),
            "--stack-addr", hex(STACK), "-o", str(image), "-s",
        ], ROOT, env)
        a64 = load_interpreter()
        total_steps = 0
        for operation in range(1, 5):
            actual, steps = execute(a64, image, operation)
            total_steps += steps
            if actual != operation:
                raise SystemExit(
                    f"Pi 3 USB enumeration gate: emitted operation {operation} "
                    f"returned 0x{actual:016x}"
                )

        image_hash = hashlib.sha256(image.read_bytes()).hexdigest().upper()
        compiler_hash = hashlib.sha256(compiler.read_bytes()).hexdigest().upper()
        print("PASS: exact control composition and LAN9514 enumeration hostile host gate")
        print("PASS: no hidden control retry loop; retry and wait budgets are scheduler-visible")
        print(f"PASS: 4 emitted A64 cases, {total_steps} interpreted instructions")
        print(f"Emitted image: {image.stat().st_size} bytes; SHA256 {image_hash}")
        print(f"Compiler SHA256: {compiler_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
