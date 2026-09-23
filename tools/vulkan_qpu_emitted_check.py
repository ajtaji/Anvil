#!/usr/bin/env python3
"""Decode and validate every QPU program emitted by Vulkan's five fixtures.

The canonical fixture is built and executed, so this gate reads the bytes made
by the real PureMetal Vulkan translator rather than a handwritten copy.  The
decoder/verifier is the independent `v3d42_qpu_decode.py` transcription of
Mesa's V3D 4.2 unpack and validation sources.  No GPU or MMIO is used.

  python tools/vulkan_qpu_emitted_check.py --compiler PureMetalForge.exe
  python tools/vulkan_qpu_emitted_check.py --compiler ... --mutate
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
from v3d42_qpu_decode import (DecodeError, ProgramContract, VerifyError,
                              decode_program, verify_program)  # noqa: E402


def load_pipeline_harness():
    path = HERE / "vulkan_pipeline_check.py"
    spec = importlib.util.spec_from_file_location("anvil_vulkan_pipeline_harness", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load canonical fixture harness {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def s64(cpu, addr: int) -> int:
    value = sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))
    return value - (1 << 64) if value >= (1 << 63) else value


def raw(cpu, addr: int, size: int) -> bytes:
    return bytes(cpu.memory.get(addr + i, 0) for i in range(size))


def is_plain_nop(ins) -> bool:
    return (ins.kind == "alu" and not ins.signals and
            ins.add_op == "nop" and ins.mul_op == "nop")


def scan_program(cpu, addr: int) -> bytes:
    """Find the documented THRSW + three-NOP end, never a zero-pad sentinel."""
    words = []
    for index in range(128):
        word = int.from_bytes(raw(cpu, addr + index * 8, 8), "little")
        words.append(word)
        try:
            decoded = decode_program(words)
        except DecodeError as exc:
            raise VerifyError(f"program at {addr:#x} became undecodable before its end: {exc}") from exc
        if len(decoded) >= 4:
            tail = decoded[-4:]
            if "thrsw" in tail[0].signals and all(is_plain_nop(i) for i in tail[1:]):
                return b"".join(w.to_bytes(8, "little") for w in words)
    raise VerifyError(f"program at {addr:#x} has no THRSW/three-NOP end in its 1 KiB slot")


def emitted_programs(cpu, report: int, harness):
    slot = lambda n: s64(cpu, report + n * 8)
    cs, vs, fs = harness.OFF_CS_CODE, harness.OFF_VS_CODE, harness.OFF_FS_CODE
    specs = []

    def known(variant, base, lengths, uniforms, fs_role):
        specs.extend([
            (f"{variant}/coordinate", raw(cpu, base + cs, lengths[0]),
             ProgramContract(f"{variant}/coordinate", "coordinate", uniforms[0])),
            (f"{variant}/vertex", raw(cpu, base + vs, lengths[1]),
             ProgramContract(f"{variant}/vertex", "vertex", uniforms[1])),
            (f"{variant}/fragment", raw(cpu, base + fs, lengths[2]),
             ProgramContract(f"{variant}/fragment", fs_role, uniforms[2])),
        ])

    known("A-varying", slot(7), (slot(10), slot(11), slot(12)), (14, 12, 1),
          "fragment:varying")
    known("B-push", slot(13), (slot(16), slot(17), slot(18)), (10, 8, 5),
          "fragment:flat")
    known("C-split-binding", slot(93), (slot(96), slot(97), slot(98)), (14, 12, 1),
          "fragment:varying")

    base_d = slot(127)
    known("D-uniform-buffer", base_d,
          (len(scan_program(cpu, base_d + cs)), len(scan_program(cpu, base_d + vs)), slot(140)),
          (10, 8, 3), "fragment:uniform")

    base_t = slot(224)
    known("E-sampled-image", base_t,
          (len(scan_program(cpu, base_t + cs)), len(scan_program(cpu, base_t + vs)), slot(225)),
          (12, 10, 3), "fragment:sampled")
    return specs


def set_field(word: int, shift: int, width: int, value: int) -> int:
    mask = ((1 << width) - 1) << shift
    return (word & ~mask) | ((value << shift) & mask)


def words(blob: bytes) -> list[int]:
    return [int.from_bytes(blob[i:i + 8], "little") for i in range(0, len(blob), 8)]


def encoded(items: list[int]) -> bytes:
    return b"".join(item.to_bytes(8, "little") for item in items)


def require_red(name, blob, contract, alter, expected: type[Exception]) -> None:
    mutant = words(blob)
    alter(mutant)
    try:
        verify_program(encoded(mutant), contract)
    except expected:
        print(f"  RED  {name}")
        return
    except (DecodeError, VerifyError) as exc:
        raise AssertionError(f"{name}: caught by wrong layer ({type(exc).__name__}: {exc})") from exc
    raise AssertionError(f"{name}: malformed program passed")


def mutations(programs) -> int:
    by_name = {name: (blob, contract) for name, blob, contract in programs}
    uniform, uc = by_name["D-uniform-buffer/fragment"]
    sampled, sc = by_name["E-sampled-image/fragment"]
    varying, vc = by_name["A-varying/fragment"]
    coord, cc = by_name["A-varying/coordinate"]
    count = 0

    def one(label, blob, contract, alter, expected=VerifyError):
        nonlocal count
        require_red(label, blob, contract, alter, expected)
        count += 1

    one("reserved signal index", varying, vc,
        lambda w: w.__setitem__(0, set_field(w[0], 53, 5, 26)), DecodeError)

    def invalid_condition(w):
        i = next(i for i, x in enumerate(w) if ((x >> 53) & 31) == 0)
        w[i] = set_field(w[i], 46, 7, 0x10)
    one("reserved condition encoding", coord, cc, invalid_condition, DecodeError)

    def vpm_in_to_out(w):
        i = next(i for i, x in enumerate(w) if ((x >> 24) & 255) == 188)
        w[i] |= 1 << 44
    one("input VPM load changed to output side", coord, cc, vpm_in_to_out)

    def wrong_ldtmu_dest(w):
        i = next(i for i, x in enumerate(w) if ((x >> 53) & 31) in (4, 5, 6, 7, 31))
        w[i] = set_field(w[i], 46, 7, 7)
    one("LDTMU result destination", uniform, uc, wrong_ldtmu_dest)

    # The bytes are unchanged; the declared stream is one word too short.
    short = ProgramContract(uc.name, uc.role, uc.uniform_words - 1)
    one("uniform stream underflow", uniform, short, lambda w: None)

    def tmuau_to_tmua(w):
        i = next(i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) == 13)
        w[i] = set_field(w[i], 32, 6, 12)
    one("TMUAU launch lost its uniform configuration", uniform, uc, tmuau_to_tmua)

    def remove_launch_thrsw(w):
        i = next(i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) == 13)
        w[i] = set_field(w[i], 53, 5, 0)
    one("TMU launch lost THRSW", uniform, uc, remove_launch_thrsw)

    def early_tmu_result(w):
        launch = next(i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) == 13)
        first = next(i for i, x in enumerate(w) if ((x >> 53) & 31) == 4)
        w[launch + 2], w[first] = w[first], w[launch + 2]
    one("TMU result in THRSW delay slots", uniform, uc, early_tmu_result)

    def dual_unit(w):
        i = next(i for i, x in enumerate(w) if ((x >> 53) & 31) == 4)
        x = set_field(w[i], 24, 8, 182)       # ADD OR
        x = set_field(x, 32, 6, 12)           # TMUA
        x |= 1 << 44                           # magic ADD destination
        w[i] = x
    one("LDTMU dual-issued with a TMU write", uniform, uc, dual_unit)

    def ldvary_in_thrsw_shadow(w):
        launch = next(i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) == 13)
        w[launch + 1] = set_field(w[launch + 1], 53, 5, 8)
        w[launch + 1] = set_field(w[launch + 1], 46, 7, 10)
    one("LDVARY in THRSW delay slots", uniform, uc, ldvary_in_thrsw_shadow)

    def remove_last_marker(w):
        for i in range(len(w) - 1):
            if ((w[i] >> 53) & 31) == 1 and ((w[i + 1] >> 53) & 31) == 1:
                w[i + 1] = set_field(w[i + 1], 53, 5, 0)
                return
        raise AssertionError("fixture has no last-THRSW pair")
    one("missing last-THRSW marker", varying, vc, remove_last_marker)

    def reverse_tlb(w):
        places = [i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) in (7, 8)]
        w[places[0]] = set_field(w[places[0]], 32, 6, 7)
        w[places[1]] = set_field(w[places[1]], 32, 6, 8)
    one("TLB written before TLBU configuration", varying, vc, reverse_tlb)

    def reverse_coords(w):
        places = [i for i, x in enumerate(w) if ((x >> 44) & 1) and ((x >> 32) & 63) in (33, 34)]
        w[places[0]] = set_field(w[places[0]], 32, 6, 33)
        w[places[1]] = set_field(w[places[1]], 32, 6, 34)
    one("TMUS written before TMUT", sampled, sc, reverse_coords)

    def lose_wrtmuc(w):
        i = next(i for i, x in enumerate(w) if ((x >> 53) & 31) == 18)
        w[i] = set_field(w[i], 53, 5, 0)
    one("missing sampler/texture WRTMUC", sampled, sc, lose_wrtmuc)

    def rf_write_after_thrend(w):
        i = len(w) - 1
        w[i] = set_field(w[i], 24, 8, 182)
        w[i] = set_field(w[i], 32, 6, 0)
        w[i] &= ~(1 << 44)
    one("register-file write after THREND", varying, vc, rf_write_after_thrend)
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--image", type=pathlib.Path,
                        help="execute this previously built canonical gate image")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler

    harness = load_pipeline_harness()
    a64_path = harness.locate("PMF_A64_INTERP", args.interp,
                              [ROOT / "tools" / "a64" / "a64_interp.py"])
    a64 = harness.load_interpreter(a64_path)
    if args.image:
        image = args.image.resolve()
        if not image.is_file():
            raise SystemExit(f"image does not exist: {image}")
    else:
        image = harness.build(harness.locate_compiler(args.compiler))
    cpu, report, steps = harness.execute(a64, image)
    if s64(cpu, report) != harness.MAGIC or s64(cpu, report + 8) != 0:
        raise SystemExit("canonical Vulkan fixture did not finish successfully")

    programs = emitted_programs(cpu, report, harness)
    total_words = 0
    for name, blob, contract in programs:
        decoded = verify_program(blob, contract)
        total_words += len(decoded)
        print(f"  OK   {name}: {len(decoded)} instructions, {contract.uniform_words} uniforms")
    # C must be the same executable code as A; its separate verification
    # still proves the independently allocated pipeline was fully decoded.
    names = {name: blob for name, blob, _ in programs}
    for stage in ("coordinate", "vertex", "fragment"):
        if names[f"A-varying/{stage}"] != names[f"C-split-binding/{stage}"]:
            raise VerifyError(f"split-binding {stage} unexpectedly changed executable code")

    red = mutations(programs) if args.mutate else 0
    print(f"vulkan_qpu_emitted_check: PASS - {len(programs)} emitted programs, "
          f"{total_words} V3D 4.2 instructions, {steps:,} A64 setup instructions"
          + (f", {red} hostile mutations rejected" if args.mutate else ""))
    if not args.mutate:
        print("  (run with --mutate to prove malformed encodings and schedules go red)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
