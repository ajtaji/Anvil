#!/usr/bin/env python3
"""Prove the immutable V3D pipeline / private 896-byte draw-slot ABI.

This is a desk-only A64 execution gate. It compiles the isolated synthetic
emitter fixture with the canonical unified compiler, runs it in the checked
interpreter, and derives every expected address and checksum independently.
No MMIO or board is available to the test.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_v3d_draw_slot_gate.pi4"
EMITTER = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_v3d_shader.pi4"
DEFAULT_COMPILER = pathlib.Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)
COMPILER_SHA256 = "bde17c26fd5ba64ddad92dad05d429e14b7d4048d2877834ec7e1e8cf32a9335"

LOAD = 0x00400000
STACK = 0x03000000
LR = 0xDEAD0000
MMIO = 0xFC000000
OUT = 0x07400000
MAGIC = 0x56445347
PIPE = 0x07000000
ARENA = 0x07100000
SLOT_BYTES = 896
SLOTS = 4096

CONTRACTS = (
    "#AVKQ_DRAW_SHREC_BYTES = 320",
    "#AVKQ_DRAW_UNIF_FS_BYTES = 256",
    "#AVKQ_DRAW_TEX_STATE_BYTES = 32",
    "#AVKQ_DRAW_SAMP_STATE_BYTES = 32",
    "#AVKQ_DRAW_OFF_UNIF_CS = 640",
    "#AVKQ_DRAW_OFF_UNIF_VS = 768",
    "#AVKQ_DRAW_SLOT_BYTES = 896",
    "#AVKQ_MAX_DRAW_SLOTS = 4096",
    "Procedure.i AnvilVkV3dDrawSlotBase(arenaBase.i, arenaBytes.i, drawIndex.i)",
    "Procedure.i AnvilVkV3dPrepareDrawSlot(pipe.i, pipelineBase.i, drawBase.i, *push, uniformBase.i, *sampled.AnvilVkBackendSampledImage)",
    "Procedure.i AnvilVkV3dPrepareClosedDrawSlot(pipe.i, pipelineBase.i, drawBase.i, *d.AnvilVkBackendDraw)",
    "Procedure.i AnvilVkV3dBuildDrawSlotRecord(pipe.i, pipelineBase.i, drawBase.i, *d.AnvilVkBackendDraw, maxIndex.i, varyComps.i)",
    "Procedure.i AnvilVkV3dDrawCacheRangeCount(pipe.i)",
)

MUTANTS = (
    (
        "a later draw reuses and overwrites the first draw slot",
        "  ProcedureReturn arenaBase + off\nEndProcedure\n\n; Allocation guard only.",
        "  ProcedureReturn arenaBase\nEndProcedure\n\n; Allocation guard only.",
    ),
    (
        "the fragment-uniform clone starts one word into the immutable template",
        "PeekL(pipelineBase + #AVKQ_OFF_UNIF_FS + i) & $FFFFFFFF)",
        "PeekL(pipelineBase + #AVKQ_OFF_UNIF_FS + i + 4) & $FFFFFFFF)",
    ),
    (
        "the clone writes poisoned draw bytes back into the immutable pipeline template",
        "    avkqPoke32(drawBase + #AVKQ_DRAW_OFF_UNIF_FS + i, PeekL(pipelineBase + #AVKQ_OFF_UNIF_FS + i) & $FFFFFFFF)\n",
        "    avkqPoke32(pipelineBase + #AVKQ_OFF_UNIF_FS + i, PeekL(drawBase + #AVKQ_DRAW_OFF_UNIF_FS + i) & $FFFFFFFF)\n",
    ),
    (
        "the fragment-uniform clone copies the full reservation instead of the live span",
        "  While i < avkqDrawTemplateBytes[pipe]\n",
        "  While i < #AVKQ_DRAW_UNIF_FS_BYTES\n",
    ),
    (
        "draw slots use a 576-byte stride and overlap sampler state",
        "#AVKQ_DRAW_SLOT_BYTES = 896",
        "#AVKQ_DRAW_SLOT_BYTES = 832",
    ),
    (
        "the 32-bit address overflow refusal is disabled",
        "  If arenaBase > ($FFFFFFFF - off - (#AVKQ_DRAW_SLOT_BYTES - 1))\n",
        "  If arenaBase < 0 And arenaBase > ($FFFFFFFF - off - (#AVKQ_DRAW_SLOT_BYTES - 1))\n",
    ),
    (
        "cache maintenance omits the texture/sampler cache line",
        "avkqDrawCacheAppend(pipe, #AVKQ_DRAW_OFF_TEX_STATE, #AVKQ_DRAW_TEX_STATE_BYTES + #AVKQ_DRAW_SAMP_STATE_BYTES)",
        "avkqDrawCacheAppend(pipe, #AVKQ_DRAW_OFF_TEX_STATE, #AVKQ_DRAW_TEX_STATE_BYTES)",
    ),
    (
        "the closed fast path re-queries mutable portable push state",
        "  If avkqDrawUsesPush[pipe] <> 0\n",
        "  If AnvilVkPipelineUsesPushConstants(pipe) <> 0\n",
    ),
    (
        "dynamic CS width is patched from the height scale",
        "avkqPoke32(drawBase + #AVKQ_DRAW_OFF_UNIF_CS + csBytes - 8, halfWBits)",
        "avkqPoke32(drawBase + #AVKQ_DRAW_OFF_UNIF_CS + csBytes - 8, halfHBits)",
    ),
    (
        "the texture-state width loses its upper eight bits",
        "(((*sampled\\width >> 6) & $FF) | ((*sampled\\height << 8) & $003FFF00) | (1 << 22))",
        "(((*sampled\\height << 8) & $003FFF00) | (1 << 22))",
    ),
    (
        "dynamic shader records keep the immutable coordinate uniforms",
        "coordinateUniformBase = drawBase + #AVKQ_DRAW_OFF_UNIF_CS",
        "coordinateUniformBase = pipelineBase + #AVKQ_OFF_UNIF_CS",
    ),
    (
        "a viewport wider than V3D u14.8 is accepted",
        "width > 32767 Or height < 1 Or height > 32767",
        "width > 65535 Or height < 1 Or height > 32767",
    ),
)


@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locate(explicit: str | None, env: str, fallback: pathlib.Path) -> pathlib.Path:
    value = explicit or os.environ.get(env)
    path = pathlib.Path(value) if value else fallback
    if not path.is_file():
        raise SystemExit(f"vulkan draw-slot gate: {env} not found: {path}")
    return path.resolve()


def load_interp(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_vdsg_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan draw-slot gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_gate(compiler: pathlib.Path, output: pathlib.Path) -> None:
    command = [
        str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(output), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         check=False)
    if run.returncode or "pmfc: OK" not in run.stdout or not output.is_file():
        raise SystemExit("vulkan draw-slot gate: compile failed\n" + run.stdout)


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            raise SystemExit(
                f"vulkan draw-slot gate: unexpected MMIO {'write' if write else 'read'} "
                f"at ${addr:08X}"
            )

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    for steps in range(40_000_000):
        if cpu.pc == LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit("vulkan draw-slot gate: execution ceiling reached")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def fnv(data) -> int:
    h = 0x811C9DC5
    for byte in data:
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h


def grade(cpu, rc: int) -> list[str]:
    slots = [u64(cpu, OUT + i * 8) for i in range(73)]
    failures: list[str] = []

    def need(name: str, got_value: int, expected: int) -> None:
        if got_value != expected:
            failures.append(f"{name}: got {got_value:#x}, expected {expected:#x}")

    need("entry return", rc, OUT)
    need("magic", slots[0], MAGIC)
    for name, index, expected in (
        ("slot bytes", 1, 896), ("record reservation", 2, 320),
        ("uniform offset", 3, 320), ("texture offset", 4, 576),
        ("sampler offset", 5, 608), ("4096 arena", 6, 4096 * 896),
        ("zero draws refused", 7, 0), ("4097 draws refused", 8, 0),
        ("draw zero base", 9, ARENA), ("draw one base", 10, ARENA + 896),
        ("last draw base", 11, ARENA + 4095 * 896),
        ("draw 4096 refused", 12, 0),
        ("exact top-of-u32 slot", 13, 0xFFFFFC80),
        ("overflowing top-of-u32 slot refused", 14, 0),
        ("aligned draw allocation accepted", 15, 1),
        ("unaligned draw allocation refused", 16, 0),
        ("overflowing draw allocation refused", 17, 0),
        ("first clone", 18, 0), ("second clone", 19, 0),
        ("first push is private", 24, 0x3F800000),
        ("second push is private", 25, 0x3DCCCCCD),
        ("first texture address", 26, (ARENA + 576) | 0xF),
        ("first sampler address", 27, (ARENA + 608) | 1),
        ("second texture address", 28, (ARENA + 896 + 576) | 0xF),
        ("second sampler address", 29, (ARENA + 896 + 608) | 1),
        ("maximum record build", 30, 0),
        ("maximum record size", 31, 36 + 16 * 16),
        ("record private FS uniforms", 32, ARENA + 320),
        ("record private VS uniforms", 33, ARENA + 768),
        ("record private CS uniforms", 34, ARENA + 640),
        ("record padding remains untouched", 35, fnv(bytes([0xA5]) * 28)),
        ("record preserved push", 36, 0x3F800000),
        ("record preserved texture pointer", 37, (ARENA + 576) | 0xF),
        ("record preserved sampler pointer", 38, (ARENA + 608) | 1),
        ("overlapping clone refused", 41, (-20001) & 0xFFFFFFFFFFFFFFFF),
        ("overlapping record refused", 42, 27),
        ("missing sample refused before clone", 43, (-20001) & 0xFFFFFFFFFFFFFFFF),
        ("first byte beyond live clone remains untouched", 48, 0xA5),
        ("last reserved uniform byte remains untouched", 49, 0xA5),
        ("template metadata closes once", 50, 0),
        ("live maximum record bytes", 51, 292),
        ("live fragment uniform bytes", 52, 28),
        ("exact clean range count", 53, 3),
        ("coalesced record/uniform range offset", 54, 0),
        ("coalesced record/uniform range bytes", 55, 384),
        ("texture/sampler range offset", 56, 576),
        ("texture/sampler/CS range bytes", 57, 128),
        ("VS clean range offset", 58, 768),
        ("first CS width scale", 59, 0x44900000),
        ("first CS height scale", 60, 0x44B00000),
        ("first VS width scale", 61, 0x44900000),
        ("second CS width scale", 62, 0x46000000),
        ("second CS height scale", 63, 0x45800000),
        ("record private VS pointer", 64, ARENA + 768),
        ("record private CS pointer", 65, ARENA + 640),
        ("overflow viewport refused", 66, (-20001) & 0xFFFFFFFFFFFFFFFF),
        ("513-wide texture low six width bits", 71, 1 << 26),
        ("513-wide texture upper width bits plus height/depth", 72,
         8 | (1024 << 8) | (1 << 22)),
    ):
        need(name, slots[index], expected)

    template = bytes((i * 29 + 7) & 0xFF for i in range(256))
    expected_template_hash = fnv(template)
    need("template checksum before", slots[20], expected_template_hash)
    need("template checksum after both clones", slots[21], expected_template_hash)
    need("template checksum after record", slots[40], expected_template_hash)
    need("second draw cannot overwrite first", slots[23], slots[22])
    need("missing-resource refusal changes no byte", slots[45], slots[44])
    first_uniforms = bytearray(template[:28])
    struct.pack_into("<4I", first_uniforms, 0,
                     0x3F800000, 0x3F000000, 0x3E800000, 0x3F400000)
    struct.pack_into("<II", first_uniforms, 16,
                     (ARENA + 576) | 0xF, (ARENA + 608) | 1)
    second_uniforms = bytearray(template[:28])
    struct.pack_into("<4I", second_uniforms, 0,
                     0x3DCCCCCD, 0x3E4CCCCD, 0x3E99999A, 0x3F800000)
    struct.pack_into("<II", second_uniforms, 16,
                     (ARENA + 896 + 576) | 0xF, (ARENA + 896 + 608) | 1)
    need("first exact cloned uniform template", slots[46], fnv(first_uniforms))
    need("second exact cloned uniform template", slots[47], fnv(second_uniforms))
    need("invalid viewport changes no slot byte", slots[68], slots[67])
    cs_template = bytes((i * 31 + 11) & 0xFF for i in range(128))
    vs_template = bytes((i * 37 + 13) & 0xFF for i in range(128))
    need("immutable CS uniforms unchanged", slots[69], fnv(cs_template))
    need("immutable VS uniforms unchanged", slots[70], fnv(vs_template))
    if slots[22] == slots[39]:
        failures.append("two draws with different push/texture state had identical slot checksums")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument(
        "--compiler-sha",
        default=COMPILER_SHA256,
        help="expected compiler digest (defaults to the historical pinned build)",
    )
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate(args.compiler, "PMF_COMPILER", DEFAULT_COMPILER)
    interp = locate(args.interp, "PMF_A64_INTERP", HERE / "a64" / "a64_interp.py")
    got = sha256(compiler)
    if got.lower() != args.compiler_sha.lower():
        raise SystemExit(
            "vulkan draw-slot gate: unified compiler hash mismatch\n"
            f"  got {got}\n  expected {args.compiler_sha}"
        )
    source = EMITTER.read_text(encoding="utf-8")
    missing = [token for token in CONTRACTS if source.count(token) != 1]
    if missing:
        for token in missing:
            print(f"vulkan_v3d_draw_slot_check: STALE - contract count != 1: {token}")
        return 1

    a64 = load_interp(interp)
    with checker_lock():
        with tempfile.TemporaryDirectory(prefix="anvil-vdsg-") as temp:
            image = pathlib.Path(temp) / "vulkan_v3d_draw_slot_gate.img"
            compile_gate(compiler, image)
            cpu, rc, steps = execute(a64, image)

    failures = grade(cpu, rc)
    if failures:
        print(f"vulkan_v3d_draw_slot_check: FAIL ({steps:,} A64 instructions)")
        for failure in failures:
            print("  " + failure)
        return 1
    print(
        "vulkan_v3d_draw_slot_check: PASS - 72 independent properties, "
        f"{steps:,} executed A64 instructions"
    )
    print(f"  compiler sha256 {got}")
    print("  maximum record ends at byte 292; bytes 292..319 remain private padding")
    print("  4096 slots occupy 3,670,016 bytes; slot 4097 and u32 overflow refuse")
    print("  dynamic viewport clones exact CS/VS words and emits three exact clean ranges")
    if not args.mutate:
        print(f"  (run with --mutate to require {len(MUTANTS)} hostile ABI mistakes to go red)")
        return 0

    original_bytes = EMITTER.read_bytes()
    # Path.read_text normalises a mixed Windows working tree to one mutation
    # vocabulary; the exact original bytes are still restored after each run.
    original = EMITTER.read_text(encoding="utf-8")
    stale = [(name, original.count(fixed)) for name, fixed, _ in MUTANTS
             if original.count(fixed) != 1]
    if stale:
        for name, count in stale:
            print(f"  STALE  {name}: anchor count {count}")
        return 2
    missed = 0
    print()
    with checker_lock():
        try:
            for number, (name, fixed, broken) in enumerate(MUTANTS):
                EMITTER.write_bytes(original.replace(fixed, broken, 1).encode("utf-8"))
                try:
                    with tempfile.TemporaryDirectory(prefix="anvil-vdsg-mut-") as temp:
                        image = pathlib.Path(temp) / f"mutant-{number}.img"
                        compile_gate(compiler, image)
                        mcpu, mrc, msteps = execute(a64, image)
                    mfailures = grade(mcpu, mrc)
                    if mfailures:
                        print(f"  RED    {name} - {mfailures[0]} ({msteps:,} instructions)")
                    else:
                        print(f"  GREEN  {name} <-- gate did not notice")
                        missed += 1
                except SystemExit as exc:
                    print(f"  RED    {name} - {str(exc).splitlines()[0]}")
                finally:
                    EMITTER.write_bytes(original_bytes)
        finally:
            EMITTER.write_bytes(original_bytes)
    if sha256(EMITTER) != hashlib.sha256(original_bytes).hexdigest():
        print("vulkan_v3d_draw_slot_check: FAIL - source restoration hash mismatch")
        return 2
    if missed:
        print(f"vulkan_v3d_draw_slot_check: FAIL - {missed} of {len(MUTANTS)} mutations escaped")
        return 1
    print(f"vulkan_v3d_draw_slot_check: PASS - all {len(MUTANTS)} hostile mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
