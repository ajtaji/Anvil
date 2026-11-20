"""Qualify PMFMOD admission and unload against Zentaji UART1."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess

from zentaji_uart_module import build_module

ROOT = Path(__file__).resolve().parents[1]


def seed_modules(files, assembler, compiler, stage, manifest):
    raw = build_module(assembler)
    (files / "AUXUART.MOD").write_bytes(raw)

    # Mutations use wire offsets so the verifier is tested independently of the packer.
    def save_mutation(name, offset, replacement):
        mutated = bytearray(raw)
        mutated[offset:offset + len(replacement)] = replacement
        mutated[96:128] = hashlib.sha256(mutated[:96] + mutated[128:]).digest()
        (files / name).write_bytes(mutated)

    reloc_offset = struct.unpack_from("<I", raw, 68)[0]
    match_offset = struct.unpack_from("<I", raw, 132)[0]
    save_mutation("ARCH.MOD", 76, struct.pack("<I", 1))
    save_mutation("ALIGN.MOD", 56, struct.pack("<Q", 4))
    save_mutation("RELOC.MOD", reloc_offset + 4, struct.pack("<H", 1))
    save_mutation("OTHER.MOD", match_offset, b"zentaji,missing-v1".ljust(64, b"\0"))
    damaged = bytearray(raw)
    damaged[168] ^= 1
    (files / "HASH.MOD").write_bytes(damaged)
    if manifest:
        (files / "MODULES.TXT").write_text("AUXUART.MOD uart\n", encoding="ascii")

    path = files.parent / "client.zex"
    subprocess.run(
        [compiler, "--compile", ROOT / "Zentaji/Tests/module_uart_service.zentaji",
         "--entry-returns", "--wants-services", "--load-addr", hex(stage + 8),
         "--stack-addr", hex(stage + 0x200000), "-o", path],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), check=True,
    )
    (files / "SERIAL.PMF").write_bytes(Path(str(path) + ".pmf").read_bytes())


def check_modules(command, manifest):
    devices = command("mod devices", "zentaji,serial-v1")
    assert "FFFF000000110000" in devices and "Zentaji serial port 1" in devices
    if manifest:
        command("mod info AUXUART.MOD", "ACTIVE")
    else:
        command("mod", "no modules are loaded")
        command("boot SERIAL.PMF", "$00000000000000A0")
        for name, code in (("ARCH", 17), ("HASH", 5), ("ALIGN", 14), ("RELOC", 9), ("OTHER", 21)):
            reply = command("mod load " + name + ".MOD", f"[mod {code}]")
            if name == "ARCH":
                assert "architecture 1" in reply and "Anvil runs 2" in reply
        command("mod load AUXUART.MOD uart", "bound to Zentaji serial port 1")
    command("boot SERIAL.PMF", "$0000000055415254")
    command("mod unload AUXUART.MOD", "unloaded AUXUART.MOD")
    command("boot SERIAL.PMF", "$00000000000000A0")
