#!/usr/bin/env python3
"""Emit and execute the production Pi 3 FDT-MAC and NVRAM rewrite helpers."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

import pi3_gate_build
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "RaspberryPi3" / "Tests" / "wifi_bringup_gate.pi3"
HELPER = ROOT / "RaspberryPi3" / "Lib" / "wifi_bringup.pi3"
NVRAM = ROOT / "RaspberryPi3" / "Data" / "wifi" / "brcmfmac43430-sdio.raspberrypi,3-model-b.txt"
MANIFEST = ROOT / "RaspberryPi3" / "Data" / "wifi" / "manifest.json"
STAGED_MODEL_B_DTB = ROOT / "_work" / "pi3-build29-final-stage" / "bcm2710-rpi-3-b.dtb"
STAGED_MODEL_B_DTB_SHA256 = "cd922193672e391b6194d6d94e34ffab6fc154205375fcfb362cad191f7f8aae"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_wifi_bringup_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fdt(props: list[tuple[str, bytes]], *, host_reg: int = 0x7E300000,
        host_name: str = "mmc@7e300000",
        child_compat: bytes = b"brcm,bcm4329-fmac\0", child_reg: int = 1) -> bytes:
    strings = bytearray()
    offsets: dict[str, int] = {}

    def prop(name: str, value: bytes) -> bytes:
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(name.encode("ascii") + b"\0")
        return struct.pack(">III", 3, len(value), offsets[name]) + value + b"\0" * ((-len(value)) & 3)

    body = bytearray()
    body += struct.pack(">I", 1) + b"\0\0\0\0"  # root node name
    body += prop("#address-cells", struct.pack(">I", 1))
    body += prop("#size-cells", struct.pack(">I", 1))
    body += struct.pack(">I", 1) + b"soc\0"
    host = host_name.encode("ascii") + b"\0"
    body += struct.pack(">I", 1) + host + b"\0" * ((-len(host)) & 3)
    body += prop("compatible", b"brcm,bcm2835-mmc\0brcm,bcm2835-sdhci\0")
    body += prop("reg", struct.pack(">II", host_reg, 0x100))
    body += struct.pack(">I", 1) + b"wifi@1\0" + b"\0"
    body += prop("reg", struct.pack(">I", child_reg))
    body += prop("compatible", child_compat)
    for name, value in props:
        body += prop(name, value)
    body += struct.pack(">IIIII", 2, 2, 2, 2, 9)

    reserve_off = 40
    struct_off = 56
    strings_off = struct_off + len(body)
    total = strings_off + len(strings)
    header = struct.pack(">10I", 0xD00DFEED, total, struct_off, strings_off,
                         reserve_off, 17, 17, 0, len(strings), len(body))
    return header + b"\0" * 16 + bytes(body) + bytes(strings)


def data_label(name: str, blob: bytes) -> str:
    rows = [f"{name}:"]
    rows.extend("  Data.b " + ",".join(f"${b:02X}" for b in blob[i:i + 16])
                for i in range(0, len(blob), 16))
    rows.append(f"{name}_end:")
    return "\n".join(rows)


def generated_source() -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    include = 'XIncludeFile "RaspberryPi3/Lib/wifi_bringup.pi3"'
    if template.count(include) != 1:
        raise SystemExit("fixture helper include drifted")
    valid = fdt([("mac-address", bytes.fromhex("021122334455")),
                 ("local-mac-address", bytes.fromhex("0266778899aa")),
                 ("address", bytes.fromhex("02aabbccddee"))])
    fallback = fdt([("mac-address", bytes.fromhex("011122334455")),
                    ("local-mac-address", bytes.fromhex("0266778899aa"))])
    parent_bad = fdt([("local-mac-address", bytes.fromhex("021122334455"))], host_reg=0x7E202000)
    child_bad = fdt([("local-mac-address", bytes.fromhex("021122334455"))],
                    child_compat=b"brcm,bcm43438-bt\0")
    invalid = fdt([("mac-address", bytes.fromhex("010000000001")),
                   ("local-mac-address", bytes.fromhex("000000000000")),
                   ("address", bytes.fromhex("ffffffffffff"))])
    # The pinned staged Raspberry Pi 3 Model B DTB spells the parent
    # `mmcnr@7e300000`, with the same SDHCI compatible+reg binding, and has no
    # static WLAN MAC. Firmware may populate local-mac-address at boot; never
    # invent a value when that has not happened.
    staged_shape_no_mac = fdt([], host_name="mmcnr@7e300000")
    firmware_mac = fdt([("local-mac-address", bytes.fromhex("021122334455"))],
                       host_name="mmcnr@7e300000")
    staged_dtb = None
    if STAGED_MODEL_B_DTB.is_file():
        staged_dtb = STAGED_MODEL_B_DTB.read_bytes()
        if hashlib.sha256(staged_dtb).hexdigest() != STAGED_MODEL_B_DTB_SHA256:
            raise SystemExit("staged Model B DTB differs from the Build29 manifest-pinned source")
    actual_nvram = NVRAM.read_bytes()
    replacement = b"02:11:22:33:44:55"
    expected_nvram = actual_nvram.replace(b"macaddr=00:90:4c:c5:12:38", b"macaddr=" + replacement)
    expected_nvram = expected_nvram.replace(b"il0macaddr=00:90:4c:c5:12:38", b"il0macaddr=" + replacement)
    small = b"boardrev=0x1202\nfoo=bar\n"
    small_expected = small + b"macaddr=" + replacement + b"\nil0macaddr=" + replacement + b"\n"
    blobs = [
        data_label("dtb_good", valid),
        data_label("dtb_fallback", fallback),
        data_label("dtb_parent_mismatch", parent_bad),
        data_label("dtb_child_mismatch", child_bad),
        data_label("dtb_invalid", invalid),
        data_label("dtb_staged_shape_no_mac", staged_shape_no_mac),
        data_label("dtb_firmware_mac", firmware_mac),
        data_label("nvram", actual_nvram),
        data_label("nvram_expected", expected_nvram),
        data_label("nvram_minimal", small),
        data_label("nvram_minimal_expected", small_expected),
        "expected_mac:\n  Data.b $02,$11,$22,$33,$44,$55\nexpected_mac_end:",
        "bad_mac:\n  Data.b $01,$00,$00,$00,$00,$01\nbad_mac_end:",
    ]
    if template.count("; @@GENERATED_BLOBS@@") != 1:
        raise SystemExit("fixture data insertion point drifted")
    lengths = {
        "DTB_GOOD": len(valid), "DTB_FALLBACK": len(fallback),
        "DTB_PARENT_MISMATCH": len(parent_bad), "DTB_CHILD_MISMATCH": len(child_bad),
        "DTB_INVALID": len(invalid), "NVRAM": len(actual_nvram),
        "DTB_STAGED_SHAPE_NO_MAC": len(staged_shape_no_mac),
        "DTB_FIRMWARE_MAC": len(firmware_mac),
        "NVRAM_EXPECTED": len(expected_nvram), "NVRAM_MINIMAL": len(small),
        "NVRAM_MINIMAL_EXPECTED": len(small_expected),
    }
    if staged_dtb is not None:
        blobs.append(data_label("dtb_staged_model_b", staged_dtb))
        lengths["DTB_STAGED_MODEL_B"] = len(staged_dtb)
    constants = "\n".join(f"#GATE_{key}_BYTES = {value}" for key, value in lengths.items())
    constants += f"\n#GATE_HAS_STAGED_MODEL_B_DTB = {1 if staged_dtb is not None else 0}"
    template = template.replace(include, constants + "\n" + helper, 1)
    return template.replace("; @@GENERATED_BLOBS@@", "\n".join(blobs), 1)


def compile_fixture(compiler: Path, temp: Path) -> tuple[bytes, dict[str, int]]:
    fixture = temp / "pi3_wifi_bringup_gate.pi3"
    fixture.write_text(generated_source(), encoding="utf-8", newline="\n")
    image = temp / "pi3_wifi_bringup_gate.img"
    command = [str(compiler), "--compile", str(fixture), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
               hex(STACK), "-s", "-o", str(image)]

    def compile_one() -> None:
        result = subprocess.run(command, cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        if result.returncode or not image.is_file():
            raise SystemExit("Pi 3 Wi-Fi bring-up fixture compile failed\n" +
                             result.stdout + result.stderr)

    pi3_gate_build.compile_counted(compile_one, fixture, image, compiler=compiler,
                                   by="pi3_wifi_bringup_check", root=ROOT)
    symbols: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        try:
            symbols[name.lower()] = int(value, 0)
        except ValueError:
            pass
    return image.read_bytes(), symbols


def execute(a64, image: bytes, symbols: dict[str, int]):
    if "main" not in symbols:
        raise AssertionError("compiler omitted fixture Main")
    cpu = a64.A64()
    for offset, byte in enumerate(image):
        cpu.memory[LOAD + offset] = byte
    for address in range(symbols.get("__bss_start__", 0), symbols.get("__bss_end__", 0)):
        cpu.memory[address] = 0
    cpu.pc = LOAD + symbols["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    # A pinned complete Model B DTB is ~35 KiB; the bounded token/name walk
    # is proportionate to that exact input rather than the tiny fixtures.
    for steps in range(1, 10_000_000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps, cpu
        if steps % 1_000_000 == 0:
            print(f"fixture progress {steps:,} pc=0x{cpu.pc:X}", flush=True)
        cpu.step()
    raise AssertionError("Pi 3 Wi-Fi bring-up gate exceeded 10,000,000 instructions")


def read_u32(memory: dict[int, int], address: int) -> int:
    return sum((memory.get(address + i, 0) & 0xFF) << (8 * i) for i in range(4))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    if not MANIFEST.is_file():
        raise SystemExit("Wi-Fi asset provenance manifest is missing")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in manifest.get("files", []):
        asset = MANIFEST.parent / item["path"]
        raw = asset.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise SystemExit(f"packaged Wi-Fi asset failed manifest verification: {item['path']}")
    for item in manifest.get("licenses", []):
        license_file = MANIFEST.parent / item["path"]
        raw = license_file.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise SystemExit(f"packaged Wi-Fi license failed manifest verification: {item['path']}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="pi3-wifi-bringup-") as tmp:
        image, symbols = compile_fixture(compiler, Path(tmp))
        result, steps, cpu = execute(a64, image, symbols)
    if result:
        detail = ""
        if result == 12 and "global_gate_n2" in symbols:
            expected_len = symbols.get("nvram_minimal_expected_end", 0) - symbols.get("nvram_minimal_expected", 0)
            detail = f" (minimal NVRAM returned {cpu.memory.get(symbols['global_gate_n2'], 0)} bytes; fixture expects {expected_len})"
        raise SystemExit(f"emitted Pi 3 Wi-Fi bring-up assertion {result} failed{detail}")
    mac = bytes.fromhex("021122334455")
    nvram = NVRAM.read_bytes()
    expected = nvram.replace(b"macaddr=00:90:4c:c5:12:38", b"macaddr=" + b"02:11:22:33:44:55")
    expected = expected.replace(b"il0macaddr=00:90:4c:c5:12:38", b"il0macaddr=" + b"02:11:22:33:44:55")
    minimal = b"boardrev=0x1202\nfoo=bar\nmacaddr=02:11:22:33:44:55\nil0macaddr=02:11:22:33:44:55\n"
    for buffer_symbol, length_symbol, wanted in (("global_gate_output", "global_gate_n", expected),
                                                  ("global_gate_output2", "global_gate_n2", minimal)):
        base = symbols[buffer_symbol]
        length = read_u32(cpu.memory, symbols[length_symbol])
        got = bytes(cpu.memory.get(base + i, 0) & 0xFF for i in range(length))
        if length != len(wanted) or got != wanted:
            raise SystemExit(f"host comparison failed for {buffer_symbol}: {length} bytes, expected {len(wanted)}")
    runtime_addr = symbols["global_gate_nvram_runtime"]
    runtime_len = read_u32(cpu.memory, symbols["global_gate_runtime_bytes"])
    runtime = bytes(cpu.memory.get(runtime_addr + i, 0) & 0xFF for i in range(runtime_len))
    if runtime_len != len(nvram) or runtime != nvram:
        raise SystemExit("absent-DTB-MAC preparation did not preserve the exact packaged NVRAM bytes")
    print("PASS: FDT lookup is scoped to the SDHCI wifi@1 node; precedence, invalid MAC fallback, host/child mismatch and truncation fail safely")
    print("PASS: packaged board NVRAM is preserved except both per-device MAC fields; missing fields are added and bad MAC/capacity/alias fail closed")
    print("PASS: exact Model B 43430 A1 paths are selected after attach, all package/license hashes match, reads stay at 4 KiB, and unsupported profiles refuse")
    print("PASS: mocked startup order is prepare, firmware, NVRAM, core start, HT, host announce, F2 enable, transport reset, MAC policy, CLM/event-mask/WLC_UP")
    print("PASS: valid DTB MAC bypasses firmware pre-read; absent DTB MAC retains a valid firmware address or replaces only the exact Linux placeholder with RNG-backed unicast, then verifies SET readback")
    print(f"PASS: emitted A64 executed in {steps:,} instructions; compiler SHA-256 {hashlib.sha256(compiler.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
