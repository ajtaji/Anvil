#!/usr/bin/env python3
"""Drive one real driver through the whole module pipeline, as emitted A64.

This gate compiles the shipped thermal driver with a `--module` build, mutates
copies of the resulting container into the negative cases, compiles the real
Core/Hal loader sources against a modelled board and medium, and executes the
emitted A64 in the project's instruction interpreter.

What it proves: format production, structural validation, integrity, exact
bounds, relocation overlap/range refusal, ABI refusal, placement in an arena
checked against the board's own reserved map, cache-synchronisation as a
precondition, manifest discovery, device matching, side-effect-free probing,
initialisation exactly once, service publication, use by the real consumer,
refusal to unload while a consumer holds the service, and unwind of a failed
activation.

What it does NOT prove: anything about silicon. There is no MMU, no cache, no
DMA and no firmware here; the device register is interpreter RAM. Hardware
acceptance is a separate, board-slot claim.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build/tests/module_pipeline"
FIXTURES = WORK / "module_pipeline_fixtures.pi4"
GATE = ROOT / "RaspberryPi4/Tests/module_pipeline_emitted_gate.pi4"
IMAGE = WORK / "module_pipeline_gate.img"
DRIVER_SRC = ROOT / "RaspberryPi4/Modules/thermal_avs.pi4"
FAILINIT_SRC = ROOT / "RaspberryPi4/Tests/module_failinit_gate.pi4"
SEAMS = ROOT / "Anvil/Hal/seams.pbi"
RUNTIME = ROOT / "Anvil/Hal/module_runtime.pbi"
ABI = ROOT / "Anvil/Hal/abi.pbi"

LOAD = 0x00200000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
STEP_LIMIT = 200_000_000

HEADER = 160
DIGEST_OFF = 96
DIGEST_END = 128
RELOC_BYTES = 16
MATCH_BYTES = 64

MANIFEST_GOOD = (
    b"# Anvil driver modules, loaded in this order at boot.\r\n"
    b"#   file name, and an optional seam name that can only narrow it.\r\n"
    b"THERMAL.MOD\r\n"
)
MANIFEST_BADSEAM = (
    b"# the second line names a seam this Anvil does not publish\n"
    b"THERMAL.MOD    nosuchseam\n"
)


def locate_required(env_name: str, relative: str) -> Path:
    choices = []
    if os.environ.get(env_name):
        choices.append(Path(os.environ[env_name]))
    choices.append(ROOT / relative)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(
        f"module pipeline gate: set {env_name}, or provide {relative} in the repo"
    )


def constant(path: Path, name: str) -> int:
    """Read one `#NAME = value` out of a PureMetal constants file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.split(";", 1)[0]
        if "=" not in code:
            continue
        left, right = code.split("=", 1)
        if left.strip() != f"#{name}":
            continue
        text = right.strip()
        if text.startswith("$"):
            return int(text[1:], 16)
        return int(text, 0)
    raise SystemExit(f"module pipeline gate: {path.name} has no #{name}")


def check_vocabulary() -> list[str]:
    """The two halves of the seam vocabulary must agree.

    #MOD_SEAM_MAX sizes the registry and is declared in the loader's own
    vocabulary because the registry is included long before the service
    table exists. #SVCCAP_MAX is the published contract. Nothing in the
    language can compare them, so this does.
    """
    notes = []
    svccap_max = constant(SEAMS, "SVCCAP_MAX")
    seam_max = constant(RUNTIME, "MOD_SEAM_MAX")
    if svccap_max != seam_max:
        raise SystemExit(
            "module pipeline gate: #SVCCAP_MAX "
            f"({svccap_max}) and #MOD_SEAM_MAX ({seam_max}) disagree - the seam "
            "registry would have no row for the highest published seam"
        )
    notes.append(f"seam vocabulary agrees at {svccap_max}")
    thermal = constant(SEAMS, "SVCCAP_THERMAL")
    if thermal > seam_max:
        raise SystemExit("module pipeline gate: #SVCCAP_THERMAL is outside the registry")
    notes.append(check_table_built_on_first_use())
    return notes


def check_table_built_on_first_use() -> str:
    """The real table must be filled before its address is handed out.

    This gate models the service table and fills its model by hand, so it
    cannot see whether the monitor's own table is built when the loader
    asks for it. On 2026-09-11 it was not: the only builder call was the
    payload boot path, the module walk runs before any payload, and the
    first module on silicon read a zero out of the seam-fill slot and
    refused itself. The owning fix is that the address getter builds the
    table on first use. That is a property of the real source this gate
    does not compile, so it is asserted here on the source itself: the
    getter tests the built flag and calls the builder, and it is defined
    after the builder, because a procedure must be defined before it is
    called in this language.
    """
    text = ABI.read_text(encoding="utf-8", errors="replace")
    builder_at = text.find("Procedure BuildServiceTable()")
    getter_at = text.find("Procedure.i SvcTableAddr()")
    if builder_at < 0 or getter_at < 0:
        raise SystemExit("module pipeline gate: abi.pbi no longer defines the builder or the getter by those names")
    if getter_at < builder_at:
        raise SystemExit("module pipeline gate: SvcTableAddr is defined above BuildServiceTable, so it cannot build on first use")
    body = text[getter_at:text.find("EndProcedure", getter_at)]
    if "gSvcBuilt = 0" not in body or "BuildServiceTable()" not in body:
        raise SystemExit(
            "module pipeline gate: SvcTableAddr does not build the table on first use - a module "
            "initialised before a payload boot would read zeros"
        )
    return "the real table is built on first use of its address"


def build_module(compiler: Path, source: Path, output: Path) -> bytes:
    command = [
        str(compiler), "--compile", "-t", "pi4", "--module", "-o", str(output), str(source),
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode != 0 or not output.is_file():
        raise SystemExit(
            f"module pipeline gate: {source.name} would not build as a module\n"
            + run.stdout
        )
    return output.read_bytes()


def seal(blob: bytearray) -> bytes:
    blob[DIGEST_OFF:DIGEST_END] = hashlib.sha256(
        bytes(blob[:DIGEST_OFF]) + bytes(blob[DIGEST_END:])
    ).digest()
    return bytes(blob)


def with_relocations(container: bytes, relocs: list[tuple[int, int, int]]) -> bytes:
    """Rebuild a real container carrying the given relocation records.

    The layout is header, image, zero padding to eight, relocation records,
    then the compatible-id records - so inserting records means shifting the
    id block and restating two header fields. Doing it this way, rather than
    synthesising a container from nothing, keeps the negative cases anchored
    to the bytes the compiler actually produced for the shipped driver.
    """
    blob = bytearray(container)
    reloc_off = struct.unpack_from("<I", blob, 68)[0]
    match_off = struct.unpack_from("<I", blob, 132)[0]
    match_count = struct.unpack_from("<I", blob, 128)[0]
    matches = bytes(blob[match_off:match_off + match_count * MATCH_BYTES])
    body = bytearray(blob[:reloc_off])
    for site, kind, addend in relocs:
        body += struct.pack("<IHHq", site, kind, 0, addend)
    new_match_off = len(body)
    body += matches
    struct.pack_into("<I", body, 64, len(relocs))
    struct.pack_into("<I", body, 68, reloc_off)
    struct.pack_into("<I", body, 132, new_match_off)
    return seal(body)


def fixtures(thermal: bytes, failinit: bytes) -> list[tuple[str, bytes]]:
    image_bytes = struct.unpack_from("<Q", thermal, 32)[0]

    bad_magic = bytearray(thermal)
    bad_magic[0] ^= 1
    bad_magic = seal(bad_magic)

    bad_minor = bytearray(thermal)
    struct.pack_into("<I", bad_minor, 20, 99)
    bad_minor = seal(bad_minor)

    # Integrity: one image byte flipped and the digest left alone. This is
    # the shape a short or corrupted copy to the card has.
    bad_hash = bytearray(thermal)
    bad_hash[HEADER + 16] ^= 0x40
    bad_hash = bytes(bad_hash)

    # Two eight-byte destinations at the same site. Each record is legal on
    # its own; together they claim one byte twice, and every destination
    # byte must have exactly one owner.
    reloc_overlap = with_relocations(thermal, [(8, 3, 0), (8, 3, 0)])

    # A target outside both the image and the BSS. It is refused before the
    # instruction at the site is even decoded, which is the order that keeps
    # a forged length from turning validation into an out-of-bounds read.
    reloc_range = with_relocations(thermal, [(8, 3, image_bytes + 0x40000000)])

    return [
        ("THERMAL.MOD", thermal),
        ("FAILINIT.MOD", failinit),
        ("BADMAGIC.MOD", bad_magic),
        ("BADMINOR.MOD", bad_minor),
        ("BADHASH.MOD", bad_hash),
        ("RELOVL.MOD", reloc_overlap),
        ("RELRNG.MOD", reloc_range),
        ("MODULES.GOOD", MANIFEST_GOOD),
        ("MODULES.BAD", MANIFEST_BADSEAM),
    ]


def data_lines(label: str, blob: bytes) -> list[str]:
    lines = [f"  {label}:"]
    for start in range(0, len(blob), 24):
        row = ", ".join(str(value) for value in blob[start:start + 24])
        lines.append("  Data.a " + row)
    return lines


def write_fixtures(items: list[tuple[str, bytes]]) -> None:
    names = [name for name, _ in items]
    labels = [f"fx_{index}" for index in range(len(items))]

    addr = ["Procedure.i GateFxAddr(i.i)", "  Select i"]
    size = ["Procedure.i GateFxLen(i.i)", "  Select i"]
    text = ["Procedure.i GateFxName(i.i)", "  Select i"]
    for index, (name, blob) in enumerate(items):
        addr.append(f"    Case {index} : ProcedureReturn ?{labels[index]}")
        size.append(f"    Case {index} : ProcedureReturn {len(blob)}")
        text.append(f'    Case {index} : ProcedureReturn "{name}"')
    for block in (addr, size, text):
        block.append("  EndSelect")
        block.append("  ProcedureReturn 0")
        block.append("EndProcedure")

    data: list[str] = []
    for index, (_, blob) in enumerate(items):
        data.extend(data_lines(labels[index], blob))

    body = "\n".join([
        "; GENERATED by tools/module_pipeline_check.py - do not edit.",
        ";",
        "; The containers below are the bytes the current compiler produced from the",
        "; current module sources, plus mutations of them. Regenerating is the",
        "; only way to change them, so the gate can never drift from the driver.",
        "",
        f"#FX_COUNT = {len(items)}",
        f"#FX_MODULES_GOOD = {names.index('MODULES.GOOD')}",
        f"#FX_MODULES_BADSEAM = {names.index('MODULES.BAD')}",
        "",
        "\n".join(addr),
        "",
        "\n".join(size),
        "",
        "\n".join(text),
        "",
        "DataSection",
        "\n".join(data),
        "EndDataSection",
        "",
    ])
    WORK.mkdir(parents=True, exist_ok=True)
    FIXTURES.write_text(body, encoding="utf-8", newline="\n")


def build_gate(compiler: Path) -> None:
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [
        str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(IMAGE), "-s",
    ]
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode != 0 or "pmfc: OK" not in run.stdout:
        raise SystemExit("module pipeline gate: gate build failed\n" + run.stdout)


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_module_pipeline_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"module pipeline gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def execute(a64) -> tuple[int, int]:
    cpu = a64.A64()
    for index, value in enumerate(IMAGE.read_bytes()):
        cpu.memory[LOAD + index] = value
    a64.attach_symbols(cpu, IMAGE, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(
        f"module pipeline gate: no return in {STEP_LIMIT} instructions"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=os.environ.get("PMF_COMPILER"))
    args = parser.parse_args()

    _compiler_named = args.compiler or os.environ.get("PMF_COMPILER")
    compiler = (Path(resolve_compiler(_compiler_named)) if _compiler_named
                else locate_required("PMF_COMPILER", "PureMetalForge.exe"))
    interpreter = locate_required("PMF_A64_INTERP", "tools/a64/a64_interp.py")
    notes = check_vocabulary()

    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anvil-module-pipeline-") as name:
        stage = Path(name)
        thermal = build_module(compiler, DRIVER_SRC, stage / "THERMAL.MOD")
        failinit = build_module(compiler, FAILINIT_SRC, stage / "FAILINIT.MOD")

    items = fixtures(thermal, failinit)
    write_fixtures(items)
    build_gate(compiler)
    rc, steps = execute(load_interpreter(interpreter))

    driver_digest = hashlib.sha256(thermal).hexdigest()
    if rc:
        print(f"module pipeline gate: FAIL - {rc} check(s) did not hold")
        return 1
    print("module pipeline gate: PASS")
    for note in notes:
        print(f"  {note}")
    print(f"  interpreted {steps} A64 instructions")
    print(f"  driver THERMAL.MOD {len(thermal)} bytes, SHA-256 {driver_digest}")
    print("  refused: bad magic, ABI minor too high, integrity mismatch,")
    print("           overlapping relocation, out-of-range relocation,")
    print("           arena inside a reserved region, arena inside a payload")
    print("           window, no arena at all, cache-sync failure,")
    print("           a fill from outside an init, a manifest line that")
    print("           narrows to an undeclared seam, a second owner of a seam")
    print("  proved:  manifest discovery, device match on a compatible id,")
    print("           side-effect-free probe declining invalid silicon,")
    print("           init exactly once, service published and used by the")
    print("           shipped consumer, unload refused while bound, detach,")
    print("           clean unload, fallback after unload, failed-init unwind,")
    print("           the same container answering at two arena bases")
    print("  MODELLED: medium, service table, memory map and device register.")
    print("           No MMU, cache, DMA or firmware. Silicon acceptance is a")
    print("           separate board-slot claim and is NOT made here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
