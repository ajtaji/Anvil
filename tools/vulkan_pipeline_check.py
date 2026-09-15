#!/usr/bin/env python3
"""The graphics pipeline: the public path, and the bytes the GPU is given.

It drives vkCreateShaderModule through vkQueueSubmit over the state-only
test backend, then compiles the same two pipelines with the REAL V3D QPU
emitter and reads back every byte it produced: the GL shader state
record, its attribute records, the two vertex uniform streams, the
fragment uniform stream and the default attribute values.

EVERY EXPECTATION IN THIS FILE IS BUILT HERE, from the documented V3D
field layouts and from the emitter's stated rules - not from the
emitter's output. The record this file packs and the record the emitter
packs are two independent implementations of one layout, and the gate is
the comparison between them.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \\
      py -3 tools/vulkan_pipeline_check.py

Add --mutate to require every plausible mistake to be caught.
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import importlib.util
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RUN_DIR = pathlib.Path(tempfile.mkdtemp(
    prefix=f"anvil_vk_pipeline_{os.getpid()}_"))
atexit.register(shutil.rmtree, RUN_DIR, True)
sys.path.insert(0, str(HERE))
import vulkan_spirv_check as spv  # noqa: E402  - the SPIR-V assembler lives there

GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_pipeline_gate.pi4"
EMITTER = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_v3d_shader.pi4"
PIPELINE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_pipeline.pbi"
# The board diagnostic is not executed here - it needs the GPU - but it is
# BUILT, so it cannot rot silently between slots. A diagnostic that no
# longer compiles is discovered on the bench otherwise, which is the most
# expensive place to discover it.
DIAGNOSTIC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanTriangleProof.pi4"
DIAGNOSTIC2 = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanVaryingProof.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
# The mixed descriptor/lifetime matrix is deliberately much larger than the
# original pipeline gate. This remains a finite execution ceiling: a valid
# gate must return, while a mutation-created loop still terminates as an
# infrastructure failure rather than being misreported as a semantic kill.
STEP_LIMIT = int(os.environ.get("ANVIL_VK_PIPELINE_STEP_LIMIT", "150000000"))
MMIO = 0xFC000000

IN = 0x06000000
FIXTURES = 0x06010000
OUT = 0x06100000
MAGIC = 0x564B5047

# The emitter's own memory map, from vk_v3d_shader.pi4's header.
OFF_CS_CODE = 0
OFF_VS_CODE = 1024
OFF_FS_CODE = 2048
OFF_UNIF_CS = 3072
OFF_UNIF_VS = 3328
OFF_UNIF_FS = 3584
OFF_DEFAULTS = 3840
OFF_SHREC = 4096
OFF_TEX_STATE = 4608
OFF_SAMP_STATE = 4864
PIPE_BYTES = 8192

SHREC_BYTES = 36
ATTR_BYTES = 16
ATTR_FLOAT = 2

F0 = 0x00000000
F1 = 0x3F800000
TLB_CONF = 0xFFFFFFFF
TMU_GENERAL_VEC4 = 0xFFFFFF7C

# Independent 9897ddc legacy executable oracle, captured before the typed-IR
# production switch. These are complete V3D 4.2 instruction words, not a
# length or a pattern sampled from the new lowerer's answer.
FS_FLAT_QWORDS = [
    0x3D803186BB800000, 0x3D807186BB800000, 0x3D80B186BB800000,
    0x3D80F186BB800000, 0x3C203186BB800000, 0x3C203186BB800000,
    0x3C003186BB800000, 0x3C003186BB800000, 0x3C0031883583E001,
    0x3C0031873583E083, 0x3C203186BB800000, 0x3C003186BB800000,
    0x3C003186BB800000, 0x3C003186BB800000,
]
FS_VARYING_QWORDS = [
    0x3D003186BB800000, 0x3C003186BB800000, 0x3C00218405835000,
    0x3D007186BB800000, 0x3C003186BB800000, 0x3C00218505835040,
    0x3D00B186BB800000, 0x3C003186BB800000, 0x3C00218605835080,
    0x3D00F186BB800000, 0x3C003186BB800000, 0x3C002187058350C0,
    0x3C203186BB800000, 0x3C203186BB800000, 0x3C003186BB800000,
    0x3C003186BB800000, 0x3C0031883583E185, 0x3C0031873583E107,
    0x3C203186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
    0x3C003186BB800000,
]
FS_UBO_QWORDS = [
    0x3D823186BB800000, 0x3C20318DB6836200, 0x3C003186BB800000,
    0x3C003186BB800000, 0x3C803186BB800000, 0x3C807186BB800000,
    0x3C80B186BB800000, 0x3C80F186BB800000, 0x3C203186BB800000,
    0x3C203186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
    0x3C0031883583E081, 0x3C0031873583E003, 0x3C203186BB800000,
    0x3C003186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
]
FS_SAMPLED_QWORDS = [
    0x3E403186BB800000, 0x3E403186BB800000, 0x3D02B186BB800000,
    0x3C003186BB800000, 0x3C00218C05835280, 0x3D02F186BB800000,
    0x3C003186BB800000, 0x3C00218D058352C0, 0x3C0031A2B6836340,
    0x3C0031A1B6836300, 0x3C203186BB800000, 0x3C003186BB800000,
    0x3C003186BB800000, 0x3C803186BB800000, 0x3C807186BB800000,
    0x3C80B186BB800000, 0x3C80F186BB800000, 0x3C203186BB800000,
    0x3C203186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
    0x3C0031883583E081, 0x3C0031873583E003, 0x3C203186BB800000,
    0x3C003186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
]


def qwords_blob(values: list[int]) -> bytes:
    return struct.pack("<%dQ" % len(values), *values)

W = H = 64
STRIDE1, STRIDE2 = 24, 8
# The split layout: position in one buffer, colour in another, at two
# different strides. These are the gate's #PG_STRIDE_POS and
# #PG_STRIDE_COL and they are written here so the two sides of the
# comparison do not share a constant.
STRIDE_POS, STRIDE_COL = 8, 16
PUSH = (0x3F800000, 0x3F000000, 0x00000000, 0x3F800000)   # r, g, b, a
# The four words in the uniform buffer a descriptor points at. They are
# the gate's #PG_UNIFORM_* and they are written again here so the two
# sides of the comparison do not share a constant - and none of them is
# any of PUSH's, so the two streams cannot be confused for each other.
UNIFORM = (0x3E800000, 0x3F400000, 0x3F800000, 0x3E000000)

ERR_UNSUPPORTED = -20005
ERR_ARGS = -20001
ERR_HANDLE = -20002
ERR_STATE = -20004
VK_ERROR_FEATURE_NOT_PRESENT = -8
VK_ERROR_OUT_OF_POOL_MEMORY = -1000069000


def f32_from_int(n: int) -> int:
    """The same exact conversion the emitter documents, computed here."""
    if n <= 0:
        return 0
    return struct.unpack("<I", struct.pack("<f", float(n)))[0]


def out_seg(slots: int, vary: int) -> int:
    """align(n,8)/8 sectors, plus one whenever there are varyings."""
    n = max(1, (slots + 7) // 8)
    if vary:
        n += 1
    return min(n, 15)


def interleaved(vertex_base: int, stride: int, records: int):
    """The attribute records of a pipeline whose attributes all come out
    of ONE binding: one record per component, four bytes apart, at one
    stride."""
    return [(vertex_base + n * 4, stride) for n in range(records)]


def expected_shader_record(base: int, records, max_index: int,
                           vary: int) -> bytes:
    """The 36-byte record and its attribute records, packed here.

    `records` is one (address, stride) pair per attribute record, which
    is what the hardware carries: a pipeline reading position from one
    buffer and colour from another has records with two different bases
    AND two different strides, and nothing about that is a special case.

    The field positions are v3d.pi4's documented ones: flags at 0, the
    VPM configuration at 4, the default-values address at 8, and two
    words for each of the fragment, vertex and coordinate stages. Each
    code word carries the address with its low three bits replaced by
    four-way threading, final-segment and propagate-NaNs.
    """
    flags = 0
    flags |= 1 << 1                      # enable clipping
    flags |= 1 << 18                     # disable implicit point/line varyings
    flags |= (vary & 0xFF) << 24         # varying components the FS reads

    cs_seg = out_seg(6 + vary, vary)
    vs_seg = out_seg(4 + vary, vary)
    vpm = (cs_seg & 0xF)
    vpm |= (0 & 0xF) << 4                # csVe
    vpm |= (1 & 0xF) << 8                # csInSeg, shared segments
    vpm |= ((1 - 1) & 0xF) << 12         # csAs, minus one
    vpm |= (vs_seg & 0xF) << 16
    vpm |= (0 & 0xF) << 20
    vpm |= (1 & 0xF) << 24
    vpm |= ((1 - 1) & 0xF) << 28

    def code(addr: int, four_way: int, final_seg: int, nans: int) -> int:
        v = addr & 0xFFFFFFF8
        if four_way:
            v |= 1
        if final_seg:
            v |= 2
        if nans:
            v |= 4
        return v

    words = [
        flags,
        vpm,
        base + OFF_DEFAULTS,
        code(base + OFF_FS_CODE, 1, 0, 1), base + OFF_UNIF_FS,
        code(base + OFF_VS_CODE, 1, 1, 1), base + OFF_UNIF_VS,
        code(base + OFF_CS_CODE, 1, 1, 1), base + OFF_UNIF_CS,
    ]
    out = struct.pack("<9I", *words)
    assert len(out) == SHREC_BYTES

    # One attribute record per component, every record read by both
    # phases, each with the address and stride its own binding gives it.
    for addr, stride in records:
        out += struct.pack("<I", addr)
        out += bytes([1 | (ATTR_FLOAT << 2)])     # vec size 1, type float
        out += bytes([(1 & 0xF) | ((1 & 0xF) << 4)])  # read by cs and vs
        out += struct.pack("<H", 0)               # instance divisor
        out += struct.pack("<I", stride)
        out += struct.pack("<I", max_index)
    return out


def expected_vertex_uniforms(kcount: int, half_w: int, half_h: int) -> bytes:
    words = list(range(kcount)) + [F0, F1, f32_from_int(half_w), f32_from_int(half_h)]
    return struct.pack("<%dI" % len(words), *words)


def locate(env_name: str, explicit, fallbacks) -> pathlib.Path:
    choices = []
    if explicit:
        choices.append(pathlib.Path(explicit))
    if os.environ.get(env_name):
        choices.append(pathlib.Path(os.environ[env_name]))
    choices.extend(fallbacks)
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit(f"vulkan_pipeline_check: {env_name} was not found; set it or pass its option")



def locate_compiler(explicit) -> pathlib.Path:
    """The one compiler.

    `PMF_COMPILER` is the name the toolchain uses now that PureMetalForge
    builds from the command line and pmfc is retired; `PMFC` is still
    accepted so a transcript written before the rename runs unchanged.
    """
    choices = []
    if explicit:
        choices.append(pathlib.Path(explicit))
    for name in ("PMF_COMPILER", "PMFC"):
        value = os.environ.get(name)
        if value:
            choices.append(pathlib.Path(value))
    choices.append(ROOT / "PureMetalForge.exe")
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise SystemExit("set PMF_COMPILER to PureMetalForge.exe, or pass --compiler")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_vkpg_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan_pipeline_check: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def compile_one(compiler: pathlib.Path, source: pathlib.Path, name: str,
                load: int = LOAD, stack: int = STACK) -> pathlib.Path:
    # Every checker process owns its artifacts. A fixed %TEMP% name let a
    # concurrent gate replace another process's image/debug sidecar between
    # compile and interpretation, producing shifting false results.
    image = RUN_DIR / name
    command = [
        str(compiler), "--compile", source.relative_to(ROOT).as_posix(),
        "-t", "pi4", "--load-addr", hex(load), "--stack-addr", hex(stack),
        "--entry-returns", "-o", str(image),
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan_pipeline_check: %s failed to compile\n%s"
                         % (source.name, run.stdout))
    return image


def build(compiler: pathlib.Path) -> pathlib.Path:
    return compile_one(compiler, GATE, "anvil_vk_pipeline_gate.img")


def fragment_varying_with_dead_io() -> bytes:
    """Direct varying colour plus dead decorated input/output declarations."""
    I, O = spv.ins, spv.OP
    body = [
        I(O["Capability"], spv.CAP_SHADER),
        I(O["MemoryModel"], spv.ADDR_LOGICAL, spv.MEM_GLSL450),
        I(O["EntryPoint"], spv.EM_FRAGMENT, 9, *spv.lit("main"), 7, 8, 12, 13),
        I(O["ExecutionMode"], 9, spv.MODE_ORIGIN_UPPER_LEFT),
        I(O["Decorate"], 7, spv.DEC_LOCATION, 0),
        I(O["Decorate"], 8, spv.DEC_LOCATION, 0),
        I(O["Decorate"], 12, spv.DEC_LOCATION, 1),
        I(O["Decorate"], 13, spv.DEC_LOCATION, 1),
        I(O["TypeVoid"], 1), I(O["TypeFunction"], 2, 1),
        I(O["TypeFloat"], 3, 32), I(O["TypeVector"], 4, 3, 4),
        I(O["TypePointer"], 5, spv.SC_INPUT, 4),
        I(O["TypePointer"], 6, spv.SC_OUTPUT, 4),
        I(O["Variable"], 5, 7, spv.SC_INPUT),
        I(O["Variable"], 6, 8, spv.SC_OUTPUT),
        I(O["Variable"], 5, 12, spv.SC_INPUT),
        I(O["Variable"], 6, 13, spv.SC_OUTPUT),
        I(O["Function"], 1, 9, 0, 2), I(O["Label"], 10),
        I(O["Load"], 4, 11, 7), I(O["Load"], 4, 14, 12),
        I(O["Store"], 8, 11), I(O["Return"]), I(O["FunctionEnd"]),
    ]
    return spv.module(15, body)


def fragment_mixed_sample_push_uniform() -> bytes:
    """sample(binding 1) * push vec4 + UBO(binding 0) -> out vec4.

    This is the smallest public shader that forces both descriptor families,
    push constants and arithmetic through one retained typed-IR pipeline.
    """
    I, O = spv.ins, spv.OP
    body = [
        I(O["Capability"], spv.CAP_SHADER),
        I(O["MemoryModel"], spv.ADDR_LOGICAL, spv.MEM_GLSL450),
        I(O["EntryPoint"], spv.EM_FRAGMENT, 24, *spv.lit("main"), 12, 13),
        I(O["ExecutionMode"], 24, spv.MODE_ORIGIN_UPPER_LEFT),
        I(O["Decorate"], 11, spv.DEC_DESCRIPTOR_SET, 0),
        I(O["Decorate"], 11, spv.DEC_BINDING, 1),
        I(O["Decorate"], 12, spv.DEC_LOCATION, 0),
        I(O["Decorate"], 13, spv.DEC_LOCATION, 0),
        I(O["Decorate"], 14, spv.DEC_BLOCK),
        I(O["MemberDecorate"], 14, 0, spv.DEC_OFFSET, 0),
        I(O["Decorate"], 16, spv.DEC_DESCRIPTOR_SET, 0),
        I(O["Decorate"], 16, spv.DEC_BINDING, 0),
        I(O["Decorate"], 20, spv.DEC_BLOCK),
        I(O["MemberDecorate"], 20, 0, spv.DEC_OFFSET, 0),
        I(O["TypeVoid"], 1),
        I(O["TypeFunction"], 2, 1),
        I(O["TypeFloat"], 3, 32),
        I(O["TypeVector"], 4, 3, 2),
        I(O["TypeVector"], 5, 3, 4),
        I(O["TypeImage"], 6, 3, 1, 0, 0, 0, 1, 0),
        I(O["TypeSampledImage"], 7, 6),
        I(O["TypePointer"], 8, spv.SC_UNIFORM_CONSTANT, 7),
        I(O["TypePointer"], 9, spv.SC_INPUT, 4),
        I(O["TypePointer"], 10, spv.SC_OUTPUT, 5),
        I(O["TypeStruct"], 14, 5),
        I(O["TypePointer"], 15, spv.SC_UNIFORM, 14),
        I(O["TypePointer"], 17, spv.SC_UNIFORM, 5),
        I(O["TypeInt"], 18, 32, 1),
        I(O["Constant"], 18, 19, 0),
        I(O["TypeStruct"], 20, 5),
        I(O["TypePointer"], 21, spv.SC_PUSH, 20),
        I(O["TypePointer"], 23, spv.SC_PUSH, 5),
        I(O["Variable"], 8, 11, spv.SC_UNIFORM_CONSTANT),
        I(O["Variable"], 9, 12, spv.SC_INPUT),
        I(O["Variable"], 10, 13, spv.SC_OUTPUT),
        I(O["Variable"], 15, 16, spv.SC_UNIFORM),
        I(O["Variable"], 21, 22, spv.SC_PUSH),
        I(O["Function"], 1, 24, 0, 2),
        I(O["Label"], 25),
        I(O["Load"], 7, 26, 11),
        I(O["Load"], 4, 27, 12),
        I(O["ImageSampleImplicitLod"], 5, 28, 26, 27),
        I(O["AccessChain"], 17, 29, 16, 19),
        I(O["Load"], 5, 30, 29),
        I(O["AccessChain"], 23, 31, 22, 19),
        I(O["Load"], 5, 32, 31),
        I(133, 5, 33, 28, 32),       # OpFMul
        I(129, 5, 34, 33, 30),       # OpFAdd
        I(O["Store"], 13, 34),
        I(O["Return"]),
        I(O["FunctionEnd"]),
    ]
    return spv.module(35, body)


def modules() -> list[bytes]:
    return [spv.vertex_passthrough(), spv.fragment_varying(),
            spv.vertex_position_only(), spv.fragment_push(),
            spv.fragment_uniform(),
            # The same uniform fragment shader at BINDING ONE. The gate
            # offers it against a set layout that has binding zero only,
            # which is the one way a shader and a layout can disagree
            # that no other rule in the path can see.
            spv.fragment_uniform(binding=1),
            # Direct immutable RGBA. The module is created only after the
            # direct-push source module is destroyed, so it proves same-slot
            # incompatible IR reuse without increasing the live-module cap.
            spv.fragment_constant(),
            # Retains valid dead interface declarations and a dead Load. The
            # public compiler must derive its ABI from the sole Store root.
            fragment_varying_with_dead_io(),
            fragment_mixed_sample_push_uniform()]


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)

    addr = FIXTURES
    table = []
    for blob in modules():
        for i, byte in enumerate(blob):
            cpu.memory[addr + i] = byte
        table.extend([addr, len(blob)])
        addr = (addr + len(blob) + 0x100) & ~0xFF
    for i, value in enumerate(table):
        for b in range(8):
            cpu.memory[IN + i * 8 + b] = (value >> (8 * b)) & 0xFF

    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(a: int) -> None:
        if a >= MMIO:
            raise SystemExit(
                f"vulkan_pipeline_check: MMIO access at ${a:08X} - the object engine, "
                "the test backend and the QPU emitter own no hardware, so reaching a "
                "peripheral means one of them started talking to V3D")

    def load(a: int, size: int) -> int:
        cpu.align_guard(a, size, False)
        guard(a)
        return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(size))

    def store(a: int, value: int, size: int) -> None:
        cpu.align_guard(a, size, True)
        guard(a)
        for i in range(size):
            cpu.memory[a + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    where = cpu.locate(cpu.pc) if cpu.locate else f"${cpu.pc:016X}"
    progress_slot = load(OUT + 680 * 8, 8)
    progress_value = load(OUT + progress_slot * 8, 8) if progress_slot <= 679 else 0
    raise SystemExit(
        f"vulkan_pipeline_check: the gate did not return in {STEP_LIMIT} steps; "
        f"pc=${cpu.pc:016X} ({where}), x0=${cpu.x[0]:016X}, "
        f"x1=${cpu.x[1]:016X}, sp=${cpu.sp:016X}, "
        f"last-report-slot={progress_slot}, value=${progress_value:016X}")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def s64(cpu, addr: int) -> int:
    v = u64(cpu, addr)
    return v - (1 << 64) if v >= (1 << 63) else v


def blob(cpu, addr: int, length: int) -> bytes:
    return bytes(cpu.memory.get(addr + i, 0) for i in range(length))


def cstr(cpu, addr: int, limit: int = 2048) -> str:
    out = []
    for i in range(limit):
        b = cpu.memory.get(addr + i, 0)
        if b == 0:
            break
        out.append(chr(b))
    return "".join(out)


class Grader:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def need(self, name, got, want) -> None:
        self.checks += 1
        if got != want:
            self.failures.append(f"{name}: got {got!r}, wanted {want!r}")

    def need_bytes(self, name, got: bytes, want: bytes) -> None:
        self.checks += 1
        if got != want:
            where = next((i for i in range(min(len(got), len(want))) if got[i] != want[i]), -1)
            self.failures.append(
                f"{name}: first difference at byte {where} - got "
                f"{got[max(0,where-2):where+6].hex()}, wanted {want[max(0,where-2):where+6].hex()}")

    def want_true(self, name, cond, detail="") -> None:
        self.checks += 1
        if not cond:
            self.failures.append(f"{name}{(': ' + detail) if detail else ''}")


def grade(cpu, rc) -> Grader:
    """`rc` is the address of the gate's own 64-slot report block, which
    is what its Main() returns - the same shape the board diagnostics
    use."""
    base = rc

    def slot(n: int) -> int:
        return s64(cpu, base + n * 8)

    g = Grader()
    g.want_true("the gate returned a report address", base != 0, hex(base))
    g.need("gate magic", hex(u64(cpu, base)), hex(MAGIC))
    # Grade the four public dead-interface semantic boundaries before the
    # global end-row. A deliberate liveness mutant can stop at pipeline or V3D
    # creation (93/94); its exact causal property must still be published and
    # must not be misclassified as an infrastructure-only early stop.
    g.need("[dead-io] shader module with valid dead declarations creates",
           slot(341), 0)
    g.need("[dead-io] retained fragment summary has only the Store output",
           (slot(629), slot(630), slot(631)), (1, 4, 0))
    g.need("[dead-io] public pipeline ignores the dead input and output",
           slot(342), 0)
    g.need("[dead-io] real typed-IR V3D compilation succeeds", slot(343), 0)
    g.need("the gate ran to the end", slot(1), 0)
    if slot(1) != 0:
        g.failures.append("  fault: " + cstr(cpu, u64(cpu, base + 32 * 8))[:200])
        return g

    g.need("the test backend reports a draw capability", slot(38), 1)
    g.need("vkCreateSampler accepts the bounded texture sampler", slot(165), 0)
    g.need("the sampler is a typed Vulkan object", slot(166), 20)
    g.want_true("the created sampler handle resolves to live state", slot(170) > 0)
    g.need("an unsupported sampler address mode is refused", slot(167), ERR_UNSUPPORTED)
    g.need("a refused sampler creation writes VK_NULL_HANDLE", slot(168), 0)
    g.need("a destroyed sampler handle becomes stale", slot(169), ERR_HANDLE)
    g.need("a transfer-only image remains valid", slot(151), 0)
    g.need("a view of that transfer-only image remains valid", slot(152), 0)
    g.need("a transfer-only image is refused as a framebuffer colour attachment",
           slot(153), ERR_ARGS)
    attachment_usage_text = cstr(cpu, u64(cpu, base + 154 * 8))
    g.want_true("the framebuffer refusal names COLOR_ATTACHMENT as the missing usage",
                "VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT" in attachment_usage_text,
                repr(attachment_usage_text[:170]))
    g.need("the image is the size its pitch and height say",
           slot(4), slot(5) * H)
    g.want_true("the image pitch covers a row", slot(5) >= W * 4, str(slot(5)))

    # --- the public path reached the backend with the right numbers ---
    vertex_base = slot(6)
    g.need("a zero draw was a no-op and the following real draw reached the backend",
           slot(21), 2)
    g.need("four pipeline slots are live after the fifth reused one", slot(22), 4)
    g.need("the draw named the bound vertex buffer", slot(23), vertex_base)
    g.need("the draw carried the binding's stride", slot(24), STRIDE1)
    g.need("the draw carried its vertex count", slot(25), 3)
    g.need("the draw carried its first vertex", slot(26), 0)
    g.need("the draw carried no push constants", slot(27), 0)
    # 0.2, 0.5, 0.7, 1.0 as UNORM8 in B, G, R, A order.
    g.need("the render pass clear value reached the backend packed",
           slot(37) & 0xFFFFFFFF, 0xFF3380B2)
    g.need("vkQueueSubmit succeeded", slot(28), 0)
    g.need("vkWaitForFences succeeded", slot(29), 0)
    g.need("the attachment ends in the render pass's final layout",
           slot(30), 6)     # VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL
    g.need("NOT ONE PIXEL of the image was written", slot(39), 0)

    # --- the refusals ---
    g.need("a pipeline that asks for blending is refused",
           slot(42), ERR_UNSUPPORTED)
    g.need("a fragment module at the vertex stage is refused",
           slot(47), ERR_ARGS)
    g.need("a render pass with loadOp LOAD is refused",
           slot(46), ERR_UNSUPPORTED)
    g.need("a fragment shader that reads push constants through a layout "
           "without a range is refused", slot(49), ERR_ARGS)
    g.need("a draw of two instances is refused", slot(43), ERR_UNSUPPORTED)
    g.need("a draw with one incomplete final triangle records", slot(44), 0)
    g.need("the incomplete-triangle draw submits", slot(161), 0)
    g.need("the incomplete-triangle draw's fence signals", slot(162), 0)
    g.need("the backend receives the original four-vertex count", slot(163), 4)
    g.need("the incomplete-triangle draw is the second real backend draw",
           slot(164), 3)
    g.need("a draw naming vertices past the end of the buffer is refused",
           slot(45), ERR_ARGS)
    g.need("ending a command buffer inside a render pass is refused",
           slot(48), ERR_STATE)
    g.need("an attribute format with the wrong component count is refused",
           slot(53), ERR_ARGS)
    g.need("a fragment shader that reads a varying nothing writes is refused",
           slot(54), ERR_ARGS)
    g.need("[dead-io] only the live varying remains in the pipeline",
           slot(347), 1)
    dead_base = slot(348)
    g.want_true("[dead-io] emitted cache base existed before the frozen copy",
                slot(344) != 0, hex(slot(344)))
    g.want_true("[dead-io] frozen executable storage exists", dead_base != 0,
                hex(dead_base))
    g.need("[dead-io] fragment byte length remains the frozen legacy length",
           slot(345), len(FS_VARYING_QWORDS) * 8)
    g.need("[dead-io] fragment uniform stream remains one TLB word",
           slot(346), 1)
    if dead_base:
        g.need_bytes("[dead-io] dead input/load/output change no fragment QPU byte",
                     blob(cpu, dead_base + OFF_FS_CODE, slot(345)),
                     qwords_blob(FS_VARYING_QWORDS))
        g.need_bytes("[dead-io] dead declarations change no uniform word",
                     blob(cpu, dead_base + OFF_UNIF_FS, 4),
                     struct.pack("<I", TLB_CONF))
    vary_text = cstr(cpu, u64(cpu, base + 50 * 8))
    g.want_true("the varying refusal says the two stages disagree on how MANY "
                "varyings there are", "number of varyings" in vary_text,
                repr(vary_text[:120]))
    g.need("a command buffer holding both a clear and a render pass is refused "
           "at submit", slot(36), VK_ERROR_FEATURE_NOT_PRESENT)
    stage_text = cstr(cpu, u64(cpu, base + 55 * 8))
    g.want_true("the stage refusal names the execution model it wanted",
                "Vertex entry point" in stage_text, repr(stage_text[:120]))

    # --- pipeline A: two attributes, four varying components ---
    baseA = slot(7)
    g.need("[A] attributes", slot(40), 2)
    g.need("[A] attribute records, one per component", slot(8), 6)
    g.need("[A] varying components", slot(9), 4)
    g.need("[A] the colour comes from a varying", slot(33), 0)
    g.need("[A] the viewport reached the emitter", slot(51), W)
    g.need("[A] the shader record offset", slot(19), OFF_SHREC)
    g.need_bytes("[A] the GL shader state record and its attribute records",
                 blob(cpu, baseA + OFF_SHREC, SHREC_BYTES + 6 * ATTR_BYTES),
                 expected_shader_record(baseA, interleaved(vertex_base, STRIDE1, 6), 2, 4))
    g.need_bytes("[A] the coordinate shader's uniform stream",
                 blob(cpu, baseA + OFF_UNIF_CS, (10 + 4) * 4),
                 expected_vertex_uniforms(10, (W // 2) * 256, (H // 2) * 256))
    g.need_bytes("[A] the vertex shader's uniform stream",
                 blob(cpu, baseA + OFF_UNIF_VS, (8 + 4) * 4),
                 expected_vertex_uniforms(8, (W // 2) * 256, (H // 2) * 256))
    g.need_bytes("[A] the fragment shader's uniform stream is the tile "
                 "configuration word alone",
                 blob(cpu, baseA + OFF_UNIF_FS, 4), struct.pack("<I", TLB_CONF))
    g.need_bytes("[A] the default attribute values",
                 blob(cpu, baseA + OFF_DEFAULTS, 16),
                 struct.pack("<4I", F0, F0, F0, F1))

    # --- pipeline B: one attribute, no varyings, a push-constant colour ---
    baseB = slot(13)
    g.need("[B] attributes", slot(41), 1)
    g.need("[B] attribute records", slot(14), 2)
    g.need("[B] varying components", slot(15), 0)
    g.need("[B] the colour comes from the push-constant block", slot(34), 1)
    g.need_bytes("[B] the GL shader state record and its attribute records",
                 blob(cpu, baseB + OFF_SHREC, SHREC_BYTES + 2 * ATTR_BYTES),
                 expected_shader_record(slot(233), interleaved(vertex_base, STRIDE2, 2), 2, 0))
    g.need_bytes("[B] the coordinate shader's uniform stream",
                 blob(cpu, baseB + OFF_UNIF_CS, (6 + 4) * 4),
                 expected_vertex_uniforms(6, (W // 2) * 256, (H // 2) * 256))
    g.need_bytes("[B] the vertex shader's uniform stream",
                 blob(cpu, baseB + OFF_UNIF_VS, (4 + 4) * 4),
                 expected_vertex_uniforms(4, (W // 2) * 256, (H // 2) * 256))
    # THE COLOUR ORDER IS THE TARGET'S, NOT THE SHADER'S: the push block
    # arrives as red, green, blue, alpha and VK_FORMAT_B8G8R8A8_UNORM
    # wants blue first.
    g.need_bytes("[B] the fragment shader's uniform stream is blue, green, "
                 "red, alpha and then the tile configuration word",
                 blob(cpu, baseB + OFF_UNIF_FS, 20),
                 struct.pack("<5I", PUSH[2], PUSH[1], PUSH[0], PUSH[3], TLB_CONF))

    # The source module may die immediately after pipeline creation. Its old
    # token must never alias same-slot replacement IR, while the pipeline owns
    # a complete immutable executable image and exact patch ABI of its own.
    g.want_true("[lifetime] the original push module owned a real slot and generation",
                slot(288) > 0 and slot(289) > 0, f"{slot(288)} / {slot(289)}")
    g.want_true("[lifetime] the original module exposed verified typed IR",
                slot(290) != 0 and slot(291) == slot(289),
                f"{slot(290):#x} / {slot(291)}")
    g.need("[lifetime] B's retained executable base was frozen", slot(292), slot(233))
    g.need("[lifetime] B's retained fragment length was frozen", slot(293), slot(18))
    g.need("[lifetime] direct push retained five uniform words", slot(294), 5)
    g.need("[lifetime] pushFirst is the first returned lane index", slot(295), 0)
    g.need("[lifetime] red's exact stream word", slot(296), 2)
    g.need("[lifetime] green's exact stream word", slot(297), 1)
    g.need("[lifetime] blue's exact stream word", slot(298), 0)
    g.need("[lifetime] alpha's exact stream word", slot(299), 3)
    g.need("[lifetime] push owns no UBO address index", slot(300), -1)
    g.need("[lifetime] push owns no UBO configuration index", slot(301), -1)
    g.need("[lifetime] push owns no texture index", slot(302), -1)
    g.need("[lifetime] push owns no sampler index", slot(303), -1)
    g.need("[lifetime] push's TLB index is exact", slot(304), 4)
    g.need("[lifetime] destroy invalidates the stale IR pointer", slot(305), 0)
    g.need("[lifetime] destroy invalidates the stale IR generation", slot(306), 0)
    g.need("[lifetime] a stale module token cannot create a pipeline", slot(307), ERR_HANDLE)
    g.need("[lifetime] stale pipeline creation writes null", slot(308), 0)
    g.need("[lifetime] incompatible replacement module creates", slot(309), 0)
    g.need("[lifetime] replacement reuses the exact module slot", slot(310), slot(288))
    g.want_true("[lifetime] replacement advances the module generation",
                slot(311) != 0 and slot(311) != slot(289), str(slot(311)))
    g.want_true("[lifetime] replacement exposes its own verified IR",
                slot(312) != 0 and slot(313) == slot(311),
                f"{slot(312):#x} / {slot(313)}")
    g.need("[lifetime] old token remains stale after same-slot reuse", slot(314), ERR_HANDLE)
    g.need("[lifetime] reused-slot stale creation still writes null", slot(315), 0)
    g.need("[lifetime] replacement immutable pipeline creates", slot(316), 0)
    g.need("[lifetime] replacement typed IR compiles", slot(317), 0)
    constant_base = slot(331)
    g.want_true("[constant] same-slot replacement owns emitted storage",
                constant_base != 0, hex(constant_base))
    g.need("[constant] direct immutable fragment length is legacy-flat",
           slot(332), len(FS_FLAT_QWORDS) * 8)
    g.need("[constant] direct immutable fragment has five uniform words",
           slot(333), 5)
    if constant_base:
        g.need_bytes("[constant] repeated blue/alpha IDs still emit four exact loads",
                     blob(cpu, constant_base + OFF_FS_CODE, slot(332)),
                     qwords_blob(FS_FLAT_QWORDS))
        g.need_bytes("[constant] immutable stream remains exact BGRA plus TLB",
                     blob(cpu, constant_base + OFF_UNIF_FS, 20),
                     struct.pack("<5I", 0x3F800000, 0x00000000,
                                 0x3F000000, 0x3F800000, TLB_CONF))
    g.need("[lifetime] replacement compile changes no byte of old B", slot(318), 0)
    g.need("[lifetime] every retained old-B metadata field remains exact", slot(319), 1)
    g.need("[lifetime] replacement destroy invalidates its IR pointer", slot(320), 0)
    g.need("[lifetime] replacement destroy invalidates its IR generation", slot(321), 0)
    g.need("[lifetime] retained copy accepts metadata-only patch", slot(322), 0)
    g.need("[lifetime] retained-copy patch changes no unnamed byte", slot(323), 0)
    g.need("[lifetime] all four named semantic push words receive exact values", slot(324), 1)
    g.need("[metadata] an out-of-range lowerer index is refused", slot(334), ERR_STATE)
    g.need("[metadata] refusal occurs before any retained byte changes", slot(335), 0)
    g.need("[lifetime] private proof fence creates", slot(336), 0)
    for name, n in (("record", 325), ("end", 326), ("submit", 327), ("wait", 328)):
        g.need(f"[lifetime] old pipeline public draw {name} succeeds", slot(n), 0)
    old_push = slot(329)
    g.want_true("[lifetime] old pipeline draw retained a complete push block", old_push != 0,
                hex(old_push))
    g.need("[lifetime] old draw retained push red", slot(337) & 0xFFFFFFFF, PUSH[0])
    g.need("[lifetime] old draw retained push green", slot(338) & 0xFFFFFFFF, PUSH[1])
    g.need("[lifetime] old draw retained push blue", slot(339) & 0xFFFFFFFF, PUSH[2])
    g.need("[lifetime] old draw retained push alpha", slot(340) & 0xFFFFFFFF, PUSH[3])
    g.need("[lifetime] exactly one old-pipeline draw preceded the ordinary suite", slot(330), 1)

    # --- the programs are the length the emission rules predict ---
    csA, vsA, fsA = slot(10), slot(11), slot(12)
    csB, vsB, fsB = slot(16), slot(17), slot(18)
    for name, value in (("[A] coordinate", csA), ("[A] vertex", vsA),
                        ("[A] fragment", fsA), ("[B] coordinate", csB),
                        ("[B] vertex", vsB), ("[B] fragment", fsB)):
        g.want_true(f"{name} program is a whole number of instructions",
                    value > 0 and value % 8 == 0, str(value))
        g.want_true(f"{name} program fits its slot", value <= 1024, str(value))
    g.need_bytes("[A] typed lowering preserves every legacy varying QPU word",
                 blob(cpu, baseA + OFF_FS_CODE, fsA), qwords_blob(FS_VARYING_QWORDS))
    g.need_bytes("[B] typed lowering preserves every legacy push QPU word",
                 blob(cpu, baseB + OFF_FS_CODE, fsB), qwords_blob(FS_FLAT_QWORDS))

    # The DIFFERENCES between the two pipelines are what the emission
    # rules predict exactly, and they are checked rather than the
    # absolute lengths, so the thread-end tail is not written down twice.
    #   coordinate: (K+4) uniforms + inSlots loads + 5 arithmetic
    #               + outSlots stores + 1 VPMWT
    #   A: K=10 inSlots=6 out=10   B: K=6 inSlots=2 out=6
    g.need("the coordinate programs differ by exactly what the rule says",
           (csA - csB) // 8, ((14 + 6 + 10) - (10 + 2 + 6)))
    #   vertex:     A: K=8 inSlots=6 out=8    B: K=4 inSlots=2 out=4
    g.need("the vertex programs differ by exactly what the rule says",
           (vsA - vsB) // 8, ((12 + 6 + 8) - (8 + 2 + 4)))
    #   fragment:   A is four LDVARY triples and two packs, B is four
    #               uniform loads and two packs.
    g.need("the fragment programs differ by exactly what the rule says",
           (fsA - fsB) // 8, (12 + 2) - (4 + 2))

    # THE BOARD DIAGNOSTIC'S HAND-ASSEMBLED MODULES. The same four words
    # streams the payload feeds the front end, compared against the ones
    # this file assembles - so a transposed operand in the listing is
    # found here and not on the bench.
    for name, (addr_slot, len_slot), want in (
            ("the position-only vertex module", (56, 57), spv.vertex_position_only()),
            ("the push-constant fragment module", (58, 59), spv.fragment_push()),
            ("the pass-through vertex module", (60, 61), spv.vertex_passthrough()),
            ("the interpolated fragment module", (62, 63), spv.fragment_varying())):
        g.need(f"{name} is the length this checker assembles",
               slot(len_slot), len(want))
        g.need_bytes(f"{name}, word for word",
                     blob(cpu, slot(addr_slot), min(slot(len_slot), len(want))), want)

    # THE VIEWPORT TRANSFORM IS STILL THERE. Replacing its two rounding
    # instructions with nothing keeps every length the same, so the
    # lengths cannot see it. This can: the interpolated fragment program
    # is four LDVARY triples, and the middle instruction of each triple
    # is a delay slot - so its most common instruction word IS the no-op,
    # and it must appear exactly four times there. The coordinate
    # program has exactly ONE no-op, between the two multiplies and the
    # two roundings, and an emitter that stopped rounding would have
    # three. Neither number is written down anywhere in the emitter.
    def words(addr: int, length: int) -> list[bytes]:
        raw = blob(cpu, addr, length)
        return [raw[i:i + 8] for i in range(0, length, 8)]

    counts = {}
    for w in words(baseA + OFF_FS_CODE, fsA):
        counts[w] = counts.get(w, 0) + 1
    nop = max(counts, key=lambda k: counts[k])

    def nops(addr: int, length: int) -> int:
        return words(addr, length).count(nop)

    # The interpolated fragment program is the flat one plus four LDVARY
    # triples, and the middle of each triple is a delay slot. The two
    # programs share every other instruction, including the thread-end
    # tail, so their difference is exactly four - and that fixes what the
    # no-op word is without this file knowing its encoding.
    g.need("the interpolated fragment program has four more delay slots "
           "than the flat one", nops(baseA + OFF_FS_CODE, fsA)
           - nops(baseB + OFF_FS_CODE, fsB), 4)
    # The coordinate and the vertex programs each hold exactly ONE no-op,
    # between the two multiplies and the two roundings, and they share
    # their thread-end tail. An emitter that stopped rounding would have
    # three in the coordinate program and one in the vertex program.
    g.need("the coordinate and vertex programs hold the same number of "
           "no-ops, so the viewport roundings are still in both",
           nops(baseA + OFF_CS_CODE, csA), nops(baseA + OFF_VS_CODE, vsA))
    g.need("and the same is true of the second pipeline",
           nops(baseB + OFF_CS_CODE, csB), nops(baseB + OFF_VS_CODE, vsB))

    # ------------------------------------------------------------------
    #  PIPELINE C: the same two attributes out of TWO bindings.
    # ------------------------------------------------------------------
    pos_base, col_base = slot(74), slot(75)
    g.want_true("the position and colour buffers are different allocations",
                pos_base != col_base and pos_base != 0 and col_base != 0,
                f"{pos_base:#x} / {col_base:#x}")

    g.need("[C] the pipeline describes two bindings", slot(84), 2)
    g.need("[C] binding 0 carries the position stride", slot(85), STRIDE_POS)
    g.need("[C] binding 1 carries the colour stride", slot(86), STRIDE_COL)
    g.need("[C] the position attribute reads binding 0", slot(87), 0)
    g.need("[C] the colour attribute reads binding 1", slot(88), 1)
    g.need("[C] the position attribute is at offset zero of its vertex", slot(89), 0)
    g.need("[C] the colour attribute is at offset zero of ITS vertex", slot(90), 0)
    g.need("[C] attributes", slot(91), 2)
    g.need("[C] the colour comes from a varying", slot(92), 0)
    g.need("[C] attribute records, one per component", slot(94), 6)
    g.need("[C] varying components", slot(95), 4)

    # THE RECORD IS THE WHOLE ARGUMENT for this step. Two of its six
    # attribute records must carry the position buffer's address and
    # stride and four must carry the colour buffer's, and this checker
    # packs both from the two addresses it read out of the gate.
    baseC = slot(93)
    two_binding_records = ([(pos_base + n * 4, STRIDE_POS) for n in range(2)]
                           + [(col_base + n * 4, STRIDE_COL) for n in range(4)])
    g.need_bytes("[C] the GL shader state record, with two attribute bases "
                 "and two strides",
                 blob(cpu, baseC + OFF_SHREC, SHREC_BYTES + 6 * ATTR_BYTES),
                 expected_shader_record(baseC, two_binding_records, 2, 4))
    # Pipeline A reads the same two attributes out of one binding, so its
    # programs and uniform streams must be byte for byte the same: the
    # split is a change to where the data IS and not to what runs.
    g.need_bytes("[C] the coordinate shader's uniform stream is pipeline A's",
                 blob(cpu, baseC + OFF_UNIF_CS, (10 + 4) * 4),
                 blob(cpu, baseA + OFF_UNIF_CS, (10 + 4) * 4))
    g.need("[C] the coordinate program is the same length as pipeline A's",
           slot(96), csA)
    g.need("[C] the vertex program is the same length as pipeline A's",
           slot(97), vsA)
    g.need("[C] the fragment program is the same length as pipeline A's",
           slot(98), fsA)
    g.need_bytes("[C] the three emitted programs are pipeline A's, byte for byte",
                 blob(cpu, baseC + OFF_CS_CODE, csA) + blob(cpu, baseC + OFF_VS_CODE, vsA)
                 + blob(cpu, baseC + OFF_FS_CODE, fsA),
                 blob(cpu, baseA + OFF_CS_CODE, csA) + blob(cpu, baseA + OFF_VS_CODE, vsA)
                 + blob(cpu, baseA + OFF_FS_CODE, fsA))

    # --- the refusals the split makes possible ---
    g.need("an attribute naming a binding the pipeline does not describe "
           "is refused", slot(76), ERR_ARGS)
    bind_text = cstr(cpu, u64(cpu, base + 77 * 8))
    g.want_true("that refusal names the binding as the thing at fault",
                "binding" in bind_text and "pVertexBindingDescriptions" in bind_text,
                repr(bind_text[:140]))
    g.need("a binding no attribute reads is refused", slot(78), ERR_ARGS)
    unused_text = cstr(cpu, u64(cpu, base + 79 * 8))
    g.want_true("that refusal says the binding is unused",
                "unused binding" in unused_text, repr(unused_text[:140]))
    g.need("two bindings with the same number are refused", slot(80), ERR_ARGS)
    duplicate_text = cstr(cpu, u64(cpu, base + 141 * 8))
    g.want_true("the duplicate-binding refusal is the owning rule, not a later "
                "unused-binding refusal",
                "same binding number" in duplicate_text,
                repr(duplicate_text[:150]))
    g.need("a binding number outside the pipeline's binding count is refused",
           slot(142), ERR_UNSUPPORTED)
    binding_number_text = cstr(cpu, u64(cpu, base + 143 * 8))
    g.want_true("the out-of-range binding-number refusal names the binding count",
                "number is not less than the binding count" in binding_number_text,
                repr(binding_number_text[:150]))
    g.need("a binding stride that is not a whole number of components is "
           "refused", slot(81), ERR_ARGS)
    g.need("an attribute past the end of ITS OWN binding's stride is refused",
           slot(82), ERR_ARGS)
    stride_text = cstr(cpu, u64(cpu, base + 83 * 8))
    g.want_true("that refusal says WHICH stride had to cover it",
                "ITS OWN binding" in stride_text, repr(stride_text[:140]))

    # --- the draw, over two buffers ---
    g.need("a draw with only binding zero bound is refused", slot(99), ERR_STATE)
    nobuf_text = cstr(cpu, u64(cpu, base + 100 * 8))
    g.want_true("that refusal says every binding needs a buffer",
                "every binding" in nobuf_text, repr(nobuf_text[:140]))
    g.need("a draw that fits binding zero and overruns binding one is refused",
           slot(101), ERR_ARGS)
    g.need("the two-binding draw records cleanly", slot(102), 0)
    g.need("the two-binding draw submits", slot(103), 0)
    g.need("its fence signals", slot(104), 0)
    g.need("the draw reached the backend carrying two bindings", slot(105), 2)
    g.need("binding 0 carried the position buffer", slot(106), pos_base)
    g.need("binding 1 carried the colour buffer", slot(107), col_base)
    g.need("binding 0 carried the position stride", slot(108), STRIDE_POS)
    g.need("binding 1 carried the colour stride", slot(109), STRIDE_COL)
    g.need("a binding this pipeline does not have carries no address",
           slot(110), 0)
    g.need("and no stride", slot(111), 0)
    g.need("four draws have now reached the backend", slot(112), 4)
    g.need("NOT ONE PIXEL was written by the two-binding draw either",
           slot(113), 0)

    # ------------------------------------------------------------------
    #  PIPELINE D: the fragment colour comes out of a uniform buffer.
    # ------------------------------------------------------------------
    g.need("[D] the descriptor set layout was created", slot(115), 0)
    g.need("[D] the descriptor pool was created", slot(116), 0)
    g.need("[D] one descriptor set was allocated", slot(117), 0)
    g.need("[D] a set of the second layout's two-binding shape was allocated",
           slot(150), 0)
    g.need("[D] the write raised no fault", slot(118), 0)
    g.need("[D] a descriptor copy is refused", slot(70), ERR_UNSUPPORTED)
    uniform_base = slot(69)
    g.want_true("[D] the uniform buffer has an address", uniform_base != 0,
                hex(uniform_base))
    g.need("[D] the descriptor resolves to the buffer's own address",
           slot(119), uniform_base)
    g.need("[D] the descriptor's range", slot(120), 16)
    g.need("[D] the colour comes from a uniform buffer", slot(66), 3)
    g.need("[D] attributes", slot(73), 1)

    # THE STREAM AND THE RAW QPU WORDS ARE THE PROOF. The stream keeps
    # the descriptor's address and a V3D 4.2 general-load configuration;
    # it does not contain a processor-side copy of the buffer's colour.
    baseD = slot(127)
    g.want_true("[D] the pipeline was compiled by the emitter", baseD != 0,
                hex(baseD))
    g.need_bytes("[D] the fragment uniform stream is address, TMU general "
                 "vec4-load configuration, then tile configuration",
                 blob(cpu, baseD + OFF_UNIF_FS, 12),
                 struct.pack("<3I", uniform_base, TMU_GENERAL_VEC4, TLB_CONF))
    g.want_true("[D] no processor-side copy of the descriptor colour remains "
                "in the fragment stream",
                blob(cpu, baseD + OFF_UNIF_FS, 20).find(
                    struct.pack("<4I", UNIFORM[2], UNIFORM[1], UNIFORM[0],
                                UNIFORM[3])) < 0)

    fsD = slot(140)
    g.need("[D] the descriptor fragment program has the documented eighteen "
           "instructions", fsD, 18 * 8)
    raw_d = [u64(cpu, baseD + OFF_FS_CODE + i)
             for i in range(0, fsD, 8)]
    g.need_bytes("[D] typed lowering preserves every legacy UBO QPU word",
                 blob(cpu, baseD + OFF_FS_CODE, fsD), qwords_blob(FS_UBO_QWORDS))

    def sig(word: int) -> int:
        return (word >> 53) & 0x1F

    def sig_dest(word: int) -> int:
        return (word >> 46) & 0x7F

    # Signal indices are the V3D 4.2 table in Mesa qpu_pack.c, decoded
    # here from the raw instruction words rather than through the emitter.
    g.need("[D] the raw descriptor program's signal sequence",
           [sig(w) for w in raw_d],
           [12, 1, 0, 0, 4, 4, 4, 4,
            1, 1, 0, 0, 0, 0, 1, 0, 0, 0])
    g.need("[D] LDUNIFRF puts the descriptor address in rf8",
           sig_dest(raw_d[0]), 8)
    g.need("[D] four LDTMU signals return RGBA in rf0 through rf3",
           [sig_dest(raw_d[i]) for i in range(4, 8)], [0, 1, 2, 3])
    fire = raw_d[1]
    # Independently assembled by py-videocore6 as mov(tmuau, rf8). Its
    # public assembler spells an ADD-side OR of the source with itself.
    # Comparing the complete word keeps opcode, magic destination, TMUAU,
    # both muxes and raddr A under one exact gate.
    g.need("[D] the lookup instruction is the primary-source TMUAU rf8 move",
           fire, 0x3C20318DB6836200)
    g.need("the draw carried the descriptor's address to the backend",
           slot(121), uniform_base)
    g.need("and its range", slot(122), 16)
    g.need("five draws have now reached the backend", slot(68), 5)

    # pSampleMask is not optional semantics. With one sample, bit zero
    # clear suppresses every fragment while the render-pass clear still
    # runs. The state-only backend records the closed draw contract; the
    # real V3D gate separately requires the primitive-emission branch.
    g.need("the zero-sample-mask pipeline was created", slot(155), 0)
    g.need("the zero-sample-mask draw recorded cleanly", slot(156), 0)
    g.need("the zero-sample-mask draw submitted", slot(157), 0)
    g.need("the zero-sample-mask draw's fence signalled", slot(158), 0)
    g.need("the draw record carries sample bit zero clear", slot(159), 0)
    g.need("the suppressed draw still reached the backend as the sixth draw",
           slot(160), 6)

    # --- descriptor state: one uniform path and one bounded sampled path ---
    g.need("a storage-image descriptor is refused",
           slot(123), ERR_UNSUPPORTED)
    sampler_text = cstr(cpu, u64(cpu, base + 71 * 8))
    g.want_true("that refusal names the unsupported storage-image type",
                "storage image descriptor" in sampler_text, repr(sampler_text[:140]))
    g.need("the bounded combined-image-sampler set layout was created", slot(171), 0)
    g.need("the earlier mixed sampler and UBO layout smoke test creates",
           slot(196), 0)
    g.need("a UBO pool cannot allocate a combined-image-sampler set",
           slot(172), VK_ERROR_OUT_OF_POOL_MEMORY)
    g.need("the combined-image-sampler pool was created", slot(173), 0)
    g.need("the combined-image-sampler set was allocated", slot(174), 0)
    g.need("a sampled write cannot claim the uniform-buffer descriptor type",
           slot(197), ERR_ARGS)
    g.need("a bound image without SAMPLED usage is refused by the descriptor write",
           slot(194), ERR_ARGS)
    g.need("a combined image sampler naming the wrong layout is refused",
           slot(195), ERR_ARGS)
    g.need("the exact sampled descriptor write succeeds", slot(175), 0)
    g.need("the sampled record stays closed before the promised layout holds", slot(176), 0)
    g.need("the shader-read transition records", slot(177), 0)
    g.need("the barrier-only submission succeeds", slot(178), 0)
    g.need("the barrier-only submission's fence signals", slot(179), 0)
    g.need("the sampled descriptor resolves after the layout transition", slot(180), 1)
    g.need("the sampled record owns the current image base", slot(181), slot(3))
    g.need("the sampled record owns the whole bound image", slot(182), slot(4))
    g.need("the sampled record owns image width", slot(183), W)
    g.need("the sampled record owns image height", slot(184), H)
    g.need("the sampled record owns image pitch", slot(185), slot(5))
    g.need("the sampled record owns the BGRA8 format", slot(186), 44)
    g.need("the sampled record owns shader-read layout", slot(187), 5)
    g.need("the sampled record owns linear magnification", slot(188), 1)
    g.need("the sampled record owns nearest minification", slot(189), 0)
    g.need("a second full image view was created for descriptor lifetime proof", slot(191), 0)
    g.need("destroying that view closes the descriptor record", slot(190), 0)
    g.need("an image view with zero mip levels is refused", slot(192), ERR_ARGS)
    g.need("an image view with zero array layers is refused", slot(193), ERR_ARGS)
    g.need("a uniform-reading shader on a layout with no set layout is "
           "refused", slot(124), ERR_ARGS)
    g.need("a draw with no descriptor set bound is refused",
           slot(125), ERR_STATE)
    noset_text = cstr(cpu, u64(cpu, base + 72 * 8))
    g.want_true("that refusal says to bind a set",
                "vkCmdBindDescriptorSets" in noset_text, repr(noset_text[:140]))
    g.need("a set bound through a layout the pipeline was not created with "
           "is refused", slot(126), ERR_ARGS)
    g.need("the descriptor draw records cleanly", slot(114), 0)

    # --- the rules the mutants found nothing checking ---
    g.need("a set layout binding at a stage that cannot read it is refused",
           slot(128), ERR_UNSUPPORTED)
    g.need("a second set layout of a different shape was created", slot(137), 0)
    g.need("a pipeline layout for it was created", slot(138), 0)
    g.need("a write naming a buffer without the uniform usage is refused",
           slot(129), ERR_ARGS)
    g.need("a uniform offset that is not a multiple of sixteen is refused",
           slot(130), ERR_ARGS)
    offset_text = cstr(cpu, u64(cpu, base + 149 * 8))
    g.want_true("the offset refusal is specifically the sixteen-byte alignment rule",
                "not a multiple of sixteen" in offset_text,
                repr(offset_text[:150]))
    g.need("a range shorter than the sixteen-byte block is refused",
           slot(131), ERR_ARGS)
    g.need("a write at a binding the set layout has not got is refused",
           slot(132), ERR_ARGS)
    g.need("and the write that is right still succeeds after all of them",
           slot(136), 0)
    g.need("a layout that declares a set layout no shader reads is refused",
           slot(133), ERR_ARGS)
    g.need("a shader at a binding its set layout does not declare is refused",
           slot(134), ERR_ARGS)
    nolayout_text = cstr(cpu, u64(cpu, base + 135 * 8))
    g.want_true("the no-set-layout refusal says the layout declares none",
                "declares no descriptor set layout" in nolayout_text,
                repr(nolayout_text[:140]))
    g.need("a set bound through a layout declaring a set of a different shape "
           "is refused", slot(139), ERR_ARGS)
    shape_text = cstr(cpu, u64(cpu, base + 146 * 8))
    g.want_true("the wrong-shape refusal is owned by descriptor-set layout "
                "compatibility",
                "immutable binding schema is incompatible" in shape_text,
                repr(shape_text[:170]))
    g.need("a correctly shaped set bound through the wrong pipeline layout is "
           "refused at draw", slot(147), ERR_ARGS)
    pipeline_layout_text = cstr(cpu, u64(cpu, base + 148 * 8))
    g.want_true("the wrong-pipeline-layout refusal is the draw-time layout rule",
                "immutable set and push-range compatibility signature differs"
                in pipeline_layout_text,
                repr(pipeline_layout_text[:170]))
    g.need("a one-binding descriptor draw clears binding one's old address",
           slot(144), 0)
    g.need("a one-binding descriptor draw clears binding one's old stride",
           slot(145), 0)

    # The fifth hand-assembled module, compared word for word.
    g.need("the uniform-buffer fragment module is the length this checker "
           "assembles", slot(65), len(spv.fragment_uniform()))
    g.need_bytes("the uniform-buffer fragment module, word for word",
                 blob(cpu, slot(64), min(slot(65), len(spv.fragment_uniform()))),
                 spv.fragment_uniform())

    # The two texture fixtures are assembled independently here and in the
    # target-language gate. A bad opcode, result type or decoration cannot be
    # blessed merely because the same bytes happen to reach both sides.
    for name, (addr_slot, len_slot), want in (
            ("the texture-coordinate vertex module", (208, 209), spv.vertex_texture()),
            ("the combined-sampler fragment module", (210, 211), spv.fragment_sampled())):
        g.need(f"{name} is the length this checker assembles", slot(len_slot), len(want))
        g.need_bytes(f"{name}, word for word",
                     blob(cpu, slot(addr_slot), min(slot(len_slot), len(want))), want)

    # The executable sampled pipeline owns a separate one-texel source image;
    # it is not a colour attachment sampled while rendering to itself.
    texel_base = slot(234)
    g.need("the sampled pipeline layout was created", slot(212), 0)
    g.need("the one-texel descriptor update succeeds", slot(213), 0)
    g.need("the one-texel shader-read transition records", slot(214), 0)
    g.need("the one-texel shader-read transition submits", slot(215), 0)
    g.need("the one-texel transition fence signals", slot(216), 0)
    g.need("the texture-coordinate vertex module creates", slot(217), 0)
    g.need("the combined-sampler fragment module creates", slot(218), 0)
    g.need("the sampled graphics pipeline creates", slot(219), 0)
    g.need("the pipeline records sampled-image colour", slot(220), 4)
    g.need("the pipeline records set-zero binding zero", slot(221), 0)
    g.need("the pipeline records the whole location-zero vec2 coordinate", slot(222), 0)
    g.need("the real V3D emitter compiles the sampled pipeline", slot(223), 0)
    g.need("the sampled fragment receives two varying components", slot(226), 2)
    g.need("the sampled draw records", slot(227), 0)
    g.need("the sampled draw submits", slot(228), 0)
    g.need("the sampled draw fence signals", slot(229), 0)
    g.need("the backend receives the sampled image base", slot(230), texel_base)
    g.need("the backend receives one sampled texel across", slot(231), 1)
    g.need("the backend receives one sampled texel down", slot(232), 1)

    tex_base = slot(224)
    tex_address_base = slot(632)
    g.want_true("the sampled pipeline has a real emitted-code allocation",
                tex_address_base != 0, hex(tex_address_base))
    g.want_true("the sampled fragment program is a whole nonempty QPU program",
                slot(225) > 0 and slot(225) % 8 == 0, str(slot(225)))
    sampled_words = [u64(cpu, tex_base + OFF_FS_CODE + i)
                     for i in range(0, slot(225), 8)]
    g.need_bytes("the sampled typed lowering preserves every legacy QPU word",
                 blob(cpu, tex_base + OFF_FS_CODE, slot(225)),
                 qwords_blob(FS_SAMPLED_QWORDS))
    g.want_true("the sampled fragment program reaches its T-then-S request",
                len(sampled_words) > 9, str(len(sampled_words)))
    if len(sampled_words) > 9:
        g.need("the texture request writes T before S fires it",
               [(sampled_words[8] >> 32) & 0x3F,
                (sampled_words[9] >> 32) & 0x3F], [34, 33])
    g.need_bytes("the texture state carries the exact one-texel BGRA8 request and ZYXW logical swizzle",
                 blob(cpu, tex_base + OFF_TEX_STATE, 16),
                 struct.pack("<4I", texel_base, 1 << 26, (1 << 8) | (1 << 22),
                             (4 << 4) | (4 << 12) | (3 << 15) | (2 << 18) | (5 << 21)))
    g.need_bytes("the sampler state carries linear-mag, nearest-min and clamp-to-edge",
                 blob(cpu, tex_base + OFF_SAMP_STATE, 8),
                 struct.pack("<2I", 0x82, (1 << 16) | (1 << 19)))
    g.need_bytes("the sampled fragment stream points at texture state, sampler state, then TLB",
                 blob(cpu, tex_base + OFF_UNIF_FS, 12),
                 struct.pack("<3I", (tex_address_base + OFF_TEX_STATE) | 0xF,
                             (tex_address_base + OFF_SAMP_STATE) | 1, TLB_CONF))

    # The first core buffer-to-optimal-image transaction. The held test
    # backend proves observable lifetime/fence/layout semantics without
    # pretending to produce pixels; the board diagnostic is the pixel proof.
    for name, n in (("transfer source buffer creates", 235),
                    ("transfer source memory allocates", 236),
                    ("transfer source memory binds", 237),
                    ("transfer source memory maps", 238),
                    ("optimal sampled image creates", 239),
                    ("optimal image memory allocates", 242),
                    ("optimal image memory binds", 243),
                    ("copy command buffer records", 244),
                    ("held copy submission starts", 245),
                    ("held copy eventually signals", 253),
                    ("failure-case optimal image creates", 260),
                    ("failure-case image memory allocates", 261),
                    ("failure-case image memory binds", 262),
                    ("failure-case command buffer records", 263),
                    ("stale-image command records against the old generation", 273),
                    ("replacement image reuses the released slot", 274),
                    ("replacement image memory allocates", 275),
                    ("replacement image memory binds", 276)):
        g.need(name, slot(n), 0)
    g.need("17x13 UIF_NO_XOR allocation is 32x16x4 bytes", slot(240), 2048)
    g.need("optimal tiling never publishes a linear row pitch", slot(241), 0)
    g.need("held copy remains outstanding", slot(246), 1)
    g.need("layout is not published before copy completion", slot(247), 0)
    g.need("source buffer is retained while copy is in flight", slot(248), ERR_STATE)
    g.need("source memory is retained while copy is in flight", slot(249), ERR_STATE)
    g.need("destination image is retained while copy is in flight", slot(250), ERR_STATE)
    g.need("destination memory is retained while copy is in flight", slot(251), ERR_STATE)
    g.need("held copy fence is not ready", slot(252), 1)
    g.need("successful copy publishes shader-read layout", slot(254), 5)
    g.need("exactly one image copy reached the backend", slot(255), 1)
    g.need("backend received source address plus VkBufferImageCopy offset",
           slot(256), slot(256) & ~63)
    g.want_true("backend received a different optimal destination",
                slot(257) != 0 and slot(257) != slot(256),
                f"{slot(256):#x} / {slot(257):#x}")
    g.need("backend received the complete padded optimal allocation", slot(258), 2048)
    g.need("successful wait settles the outstanding transaction", slot(259), 0)
    g.need("backend failure is reported as device lost", slot(264), -4)
    g.need("failed copy does not publish its final shader-read layout", slot(265), 0)
    g.need("failed-copy fence is settled", slot(266), 0)
    g.need("failed copy leaves no outstanding transaction", slot(267), 0)
    g.need("backend-native failure evidence survives", slot(268), 77)
    g.need("all seven hostile region/layout/count/alignment requests are refused", slot(269), 7)
    g.need("stale-source command records while the source is live", slot(271), 0)
    g.need("destroyed source is revalidated before submission", slot(272), ERR_STATE)
    g.need("destroyed and slot-replaced image is revalidated before submission",
           slot(277), ERR_STATE)
    for name, n in (("framebuffer-alias command records", 278),
                    ("replacement framebuffer reuses the released slot", 279),
                    ("image-view-alias command records", 281),
                    ("replacement image view reuses the released slot", 282),
                    ("framebuffer rebuilds on the current view", 284),
                    ("render-pass-alias command records", 285),
                    ("replacement render pass reuses the released slot", 286)):
        g.need(name, slot(n), 0)
    g.need("recorded framebuffer generation cannot alias its replacement",
           slot(280), ERR_STATE)
    g.need("framebuffer view generation cannot alias its replacement",
           slot(283), ERR_STATE)
    g.need("framebuffer render-pass generation cannot alias its replacement",
           slot(287), ERR_STATE)
    optimal_state = slot(270)
    g.need_bytes("optimal texture state names the TFU destination and exact 17x13 UIF level",
                 blob(cpu, optimal_state + OFF_TEX_STATE, 20),
                 struct.pack("<5I", slot(257), 17 << 26,
                             (13 << 8) | (1 << 22),
                             (4 << 4) | (4 << 12) | (3 << 15) | (2 << 18)
                              | (5 << 21) | (1 << 11),
                              1 << 6))

    # Mixed descriptor schemas are consumed by value at every Vulkan lifetime
    # boundary. These public rows deliberately destroy/reuse source layouts and
    # reorder pool rows; handles are allowed to differ, schema and behaviour are
    # not.
    for name, n in (("mixed UBO+sampler set layout creates", 360),
                    ("interleaved duplicate-row descriptor pool creates", 361),
                    ("mixed descriptor set allocates atomically", 364),
                    ("mixed UBO binding updates", 365),
                    ("mixed sampled binding updates independently", 366),
                    ("mixed pipeline layout copies source schema", 372),
                    ("reversed input binding rows canonicalise", 373),
                    ("compatible distinct pipeline layout creates", 374),
                    ("compatible distinct layout binds old set", 379),
                    ("second duplicate-row ordering creates", 392)):
        g.need(name, slot(n), 0)
    g.need("duplicate UBO pool rows sum to two", slot(362), 2)
    g.need("sample pool capacity remains one", slot(363), 1)
    g.want_true("mixed set retained its UBO handle", slot(367) != 0, hex(slot(367)))
    g.want_true("mixed set retained its sampler handle", slot(368) != 0, hex(slot(368)))
    g.want_true("mixed set retained its image-view handle", slot(369) != 0, hex(slot(369)))
    g.need("near-maximum UBO range is refused", slot(370), ERR_ARGS)
    g.need("failed UBO replacement preserves both descriptor families", slot(371), 1)
    g.need("copied mixed schema has two bindings", slot(375), 2)
    g.need("copied binding zero remains uniform-buffer type", slot(376), 6)
    g.need("copied binding one remains combined-sampler type", slot(377), 1)
    g.need("copied push signature remains sixteen bytes", slot(378), 16)
    g.need("schema compatibility compares descriptor stages", slot(596), 0)
    g.need("stale destroyed source layout cannot create a new layout", slot(380), ERR_HANDLE)
    g.need("stale-source refusal nulls output", slot(381), 0)
    g.need("pipeline-layout creation flags are refused", slot(382), ERR_UNSUPPORTED)
    g.need("flags refusal nulls output before inner creation", slot(383), 0)
    g.need("second live device creates", slot(384), 0)
    g.need("second-device mixed source layout creates", slot(385), 0)
    g.need("foreign source layout is refused at pipeline-layout create", slot(386), -20003)
    g.need("foreign-source refusal nulls output", slot(387), 0)
    g.need("second-device pipeline layout creates", slot(388), 0)
    g.need("foreign layout cannot bind into first-device command buffer", slot(389), -20003)
    g.need("foreign layout cannot update first-device push constants", slot(390), -20003)
    g.need("foreign push refusal leaves existing word untouched", slot(391), 0xA5C30FF0)
    g.need("reordered duplicate pool still sums two UBO descriptors", slot(393), 2)
    g.need("reordered duplicate pool still has one sampler", slot(394), 1)
    g.need("late duplicate-row overflow refuses pool creation", slot(395), -1)
    g.need("overflow refusal nulls pool output", slot(396), 0)
    g.need("UBO-overflow refusal mutates no pool slot state", slot(610), 1)
    g.need("single-UBO source layout creates", slot(397), 0)
    g.need("remaining per-type UBO capacity allocates independently", slot(398), 0)
    g.need("exhausted UBO capacity refuses another set", slot(399), VK_ERROR_OUT_OF_POOL_MEMORY)
    g.need("UBO exhaustion nulls output", slot(400), 0)
    g.need("single-sampler source layout creates", slot(401), 0)
    g.need("exhausted sampler capacity refuses independently", slot(402), VK_ERROR_OUT_OF_POOL_MEMORY)
    g.need("sampler exhaustion nulls output", slot(403), 0)
    g.need("failed allocations leave exact UBO outstanding count", slot(404), 2)
    g.need("failed allocations leave exact sampler outstanding count", slot(405), 1)
    g.need("single-type pool creates for atomic mixed shortage", slot(406), 0)
    g.need("missing second descriptor family refuses mixed allocation", slot(407), VK_ERROR_OUT_OF_POOL_MEMORY)
    g.need("mixed-shortage refusal nulls output", slot(408), 0)
    g.need("mixed-shortage refusal spends no UBO capacity", slot(409), 0)
    g.need("mixed-shortage refusal spends no sampler capacity", slot(410), 0)
    g.need("following UBO-only allocation still succeeds", slot(411), 0)
    g.need("successful UBO-only allocation spends exactly one", slot(412), 1)
    g.need("late unsupported pool row refuses whole creation", slot(413), ERR_UNSUPPORTED)
    g.need("late unsupported row leaves output null", slot(414), 0)
    g.need("late zero-count pool row refuses whole creation", slot(415), ERR_ARGS)
    g.need("late zero-count row leaves output null", slot(416), 0)
    g.need("reordered-pool mixed set allocates", slot(417), 0)
    g.need("sample-first mixed update succeeds", slot(418), 0)
    g.need("UBO-second mixed update succeeds", slot(419), 0)
    g.need("both descriptor arms survive reverse update order", slot(420), 1)

    # The real retained-IR mixed shader and its runtime lifetime transaction.
    for name, n in (("mixed arithmetic shader module creates", 421),
                    ("incompatible source layout reuses the destroyed slot", 422),
                    ("sample image creates", 424),
                    ("sample memory allocates", 425),
                    ("sample memory binds", 426),
                    ("sample view creates", 427),
                    ("sample descriptor updates", 428),
                    ("sample layout transition records", 429),
                    ("sample layout transition submits", 430),
                    ("sample layout transition completes", 431),
                    ("mixed arithmetic pipeline creates", 432),
                    ("typed mixed fragment lowers to V3D", 437),
                    ("incompatible pipeline-layout slot replacement creates", 440),
                    ("framebuffer rebuilds against current render-pass generation", 442),
                    ("valid mixed command records", 443),
                    ("valid mixed draw submits", 444),
                    ("valid mixed draw completes", 445),
                    ("incompatible CB-layout slot replacement creates", 591),
                    ("compatible CB bind layout is recreated", 593),
                    ("stale-sample command records while resources are live", 451),
                    ("replacement sample view creates", 457),
                    ("replacement sample descriptor updates", 458),
                    ("held mixed draw submits", 459),
                    ("held mixed draw completes", 467),
                    ("alias layout transition records", 491),
                    ("alias layout transition submits", 492),
                    ("alias layout transition completes", 493),
                    ("alias sample descriptor updates", 494),
                    ("alias-accounting draw records", 495),
                    ("alias-accounting draw submits", 496),
                    ("alias-accounting draw completes", 509)):
        g.need(name, slot(n), 0)
    g.need("source layout really reused the incompatible slot", slot(423), 1)
    g.want_true("mixed pipeline published a live slot", 0 < slot(433) <= 7,
                str(slot(433)))
    g.need("mixed pipeline retained its UBO requirement", slot(434), 1)
    g.need("mixed pipeline retained its sample requirement", slot(435), 1)
    g.need("mixed pipeline retained its push requirement", slot(436), 1)
    g.want_true("mixed fragment emitted executable bytes", slot(438) > 0,
                str(slot(438)))
    g.need("mixed fragment emitted its exact nine-word uniform stream",
           slot(439), 9)
    g.need("mixed fragment retained its live varying", slot(543), 1)
    g.need("runtime patching consumes lowerer metadata", slot(544), 0)
    mixed_indices = ([slot(i) for i in range(545, 550)] + [slot(605)] +
                     [slot(i) for i in range(550, 553)])
    g.want_true("all nine mixed dynamic/TLB indices are in range",
                all(0 <= i < slot(439) for i in mixed_indices),
                str(mixed_indices))
    g.want_true("all nine mixed dynamic/TLB indices are distinct",
                len(set(mixed_indices)) == 9, str(mixed_indices))
    g.need("mixed UBO address is patched through its returned index",
           slot(553) & 0xFFFFFFFF, slot(447) & 0xFFFFFFFF)
    mixed_base = slot(564)
    mixed_words = [slot(i) & 0xFFFFFFFF for i in range(620, 629)]
    for channel, index, word, expected in zip(
            "RGBA", mixed_indices[:4], mixed_words[:4], PUSH):
        g.need(f"mixed push {channel} is patched through its semantic index",
               word, expected)
    g.need("mixed UBO address word is exact", mixed_words[4],
           slot(447) & 0xFFFFFFFF)
    g.need("mixed UBO vec4 config word is exact", mixed_words[5],
           TMU_GENERAL_VEC4)
    g.need("mixed texture pointer uses its lowerer-returned index",
           mixed_words[6], (mixed_base + OFF_TEX_STATE) | 0xF)
    g.need("mixed sampler pointer uses its lowerer-returned index",
           mixed_words[7], (mixed_base + OFF_SAMP_STATE) | 1)
    g.need("mixed TLB word uses its lowerer-returned index",
           mixed_words[8], TLB_CONF)
    g.need("pipeline layout slot really reused with incompatible schema", slot(441), 1)
    g.need("incompatible descriptor type/shape is refused at bind", slot(540), ERR_ARGS)
    g.need("failed incompatible bind preserves prior copied CB state", slot(595), 1)
    g.need("same schema without the required push signature creates", slot(541), 0)
    g.need("push-signature mismatch is refused before a draw publishes", slot(542), ERR_ARGS)
    g.need("exactly one valid mixed draw reaches the backend", slot(446), 1)
    g.need("mixed backend receives exact UBO base", slot(447), slot(553))
    g.need("mixed backend receives exactly one vec4 UBO", slot(448), 16)
    g.want_true("mixed backend receives the dedicated sampled image",
                slot(449) != 0 and slot(449) != slot(447), hex(slot(449)))
    g.need("mixed backend receives a push block", slot(450), 1)
    g.need("CB source layout reuses the exact incompatible slot", slot(592), 1)
    g.need("CB source layout returns to the exact compatible slot", slot(594), 1)
    g.need("stale sampler-family view refuses before flight", slot(452), ERR_STATE)
    g.need("stale sampler refusal changes no submit counter", slot(453), 0)
    g.need("stale sampler refusal calls no draw backend", slot(454), 0)
    g.need("stale sampler refusal leaves no outstanding flight", slot(455), 0)
    g.need("stale sampler refusal leaves fence unsignalled", slot(456), 1)
    g.need("stale sampler refusal creates its fresh signal semaphore", slot(597), 0)
    g.need("stale sampler refusal leaves signal semaphore unsignalled", slot(598), 0)
    g.need("stale sampler refusal leaves no semaphore reservation stage", slot(599), 0)
    g.need("stale sampler refusal never reaches the retain observer",
           slot(600), 0x13579BDF)
    g.need("stale sampler refusal changes no completion counter", slot(606), 0)
    g.need("stale sampler refusal changes no backend-call counter", slot(608), 0)

    for index, label in enumerate(("UBO buffer", "UBO memory", "sampler",
                                   "sample view", "sample image", "sample memory",
                                   "attachment view", "attachment image",
                                   "attachment memory")):
        g.need(f"backend callback sees {label} retained before dispatch",
               slot(473 + index), 1)
        g.need(f"forced-failure callback still sees {label} retained",
               slot(482 + index), 1)
    for n, label in ((460, "UBO buffer"), (461, "UBO memory"),
                     (462, "sample image"), (463, "sample memory"),
                     (464, "sampler"), (465, "sample view"),
                     (466, "attachment view")):
        g.need(f"held flight exposes exact {label} retain count", slot(n), 1)
    for n, label in ((554, "UBO buffer"), (555, "UBO memory"),
                     (556, "sampler"), (557, "sample view"),
                     (558, "sample image"), (559, "sample memory"),
                     (560, "framebuffer")):
        g.need(f"held flight refuses destruction of {label}", slot(n), ERR_STATE)
    g.need("successful held completion releases every observed owner", slot(468), 0)
    g.need("forced draw failure reports device lost", slot(469), -4)
    g.need("forced draw failure releases every observed owner", slot(470), 0)
    g.need("forced draw failure leaves no outstanding flight", slot(471), 0)
    g.need("forced draw failure settles its fence", slot(472), 0)

    alias_expected = [1, 1, 1, 2, 2, 2, 2, 2, 2]
    for index, expected in enumerate(alias_expected):
        g.need(f"alias accounting callback counter {index}", slot(497 + index), expected)
    g.need("active-flight framebuffer destruction is refused", slot(506), ERR_STATE)
    g.need("a second framebuffer may create without aliasing the active slot", slot(507), 0)
    g.want_true("second framebuffer publishes a handle", slot(508) != 0,
                hex(slot(508)))
    g.need("second framebuffer occupies a distinct slot", slot(511), 1)
    g.need("alias-accounting completion releases view/image/memory", slot(510), 0)
    g.need("five interleaved pool rows create without an arbitrary bound", slot(565), 0)
    g.need("five-row pool sums three UBO descriptors", slot(566), 3)
    g.need("five-row pool sums two sampled descriptors", slot(567), 2)
    g.need("reverse five-row ordering creates", slot(568), 0)
    g.need("reverse ordering preserves UBO total", slot(569), 3)
    g.need("reverse ordering preserves sampled total", slot(570), 2)
    g.need("sample duplicate-row overflow refuses pool creation", slot(571), -1)
    g.need("sample-overflow refusal nulls output", slot(572), 0)
    g.need("sample-overflow refusal mutates no pool slot state", slot(573), 1)
    g.need("sampler-only pool creates for mirrored atomic shortage", slot(574), 0)
    g.need("sampler-only pool refuses a mixed allocation", slot(575), VK_ERROR_OUT_OF_POOL_MEMORY)
    g.need("mirrored mixed-shortage refusal nulls output", slot(576), 0)
    g.need("mirrored shortage spends no UBO descriptors", slot(577), 0)
    g.need("mirrored shortage spends no sampled descriptors", slot(578), 0)
    g.need("following sampler-only allocation succeeds", slot(579), 0)
    g.need("successful sampler-only allocation spends exactly one", slot(580), 1)
    g.need("incompatible descriptor stage is refused at source creation", slot(581), ERR_UNSUPPORTED)
    g.need("stage refusal publishes no source layout", slot(582), 0)
    for kind, rc_slot, out_slot, live_slot in (
            ("descriptor-set-layout", 611, 612, 613),
            ("descriptor-pool", 614, 615, 616),
            ("sampler", 617, 618, 619)):
        g.need(f"public {kind} allocator is refused", slot(rc_slot), ERR_UNSUPPORTED)
        g.need(f"public {kind} allocator refusal nulls output", slot(out_slot), 0)
        g.need(f"public {kind} allocator refusal publishes no live slot", slot(live_slot), 1)
    g.need("UBO-mirror restores a valid dedicated sampled view", slot(583), 0)
    g.need("UBO-mirror command records while both families are live", slot(584), 0)
    g.need("stale UBO family refuses before flight", slot(585), ERR_STATE)
    g.need("stale UBO refusal changes no submit counter", slot(586), 0)
    g.need("stale UBO refusal calls no draw backend", slot(587), 0)
    g.need("stale UBO refusal leaves no outstanding flight", slot(588), 0)
    g.need("stale UBO refusal leaves fence unsignalled", slot(589), 1)
    g.need("stale UBO refusal retains no surviving sampled owner", slot(590), 0)
    g.need("stale UBO refusal creates its fresh signal semaphore", slot(601), 0)
    g.need("stale UBO refusal leaves signal semaphore unsignalled", slot(602), 0)
    g.need("stale UBO refusal leaves no semaphore reservation stage", slot(603), 0)
    g.need("stale UBO refusal never reaches the retain observer",
           slot(604), 0x2468ACE0)
    g.need("stale UBO refusal changes no completion counter", slot(607), 0)
    g.need("stale UBO refusal changes no backend-call counter", slot(609), 0)
    return g


MUTANTS = (
    ("the V3D target includes a dead decorated fragment input",
     "If *variable\\storageClass = #ANVIL_IR_STORAGE_INPUT And avkqIrLive[*variable\\sourceId] <> 0",
     "If *variable\\storageClass = #ANVIL_IR_STORAGE_INPUT"),
    ("the V3D target includes a dead decorated fragment output",
     "ElseIf *variable\\storageClass = #ANVIL_IR_STORAGE_OUTPUT And *variable\\sourceId = outputVariableId",
     "ElseIf *variable\\storageClass = #ANVIL_IR_STORAGE_OUTPUT"),
    ("optimal sampled state loses the strict-UIF level-zero bit",
     "      avkqPoke32(base + #AVKQ_OFF_TEX_STATE + 16, (1 << 6))\n",
     "      avkqPoke32(base + #AVKQ_OFF_TEX_STATE + 16, 0)\n"),
    ("the BGRA8 texture state uses identity swizzle and returns BGR as shader RGB",
     "    k = (4 << 4) | (4 << 12) | (3 << 15) | (2 << 18) | (5 << 21)\n",
     "    k = (4 << 4) | (2 << 12) | (3 << 15) | (4 << 18) | (5 << 21)\n"),
    ("the sampled texture-state width is packed in the wrong field",
     "    avkqPoke32(base + #AVKQ_OFF_TEX_STATE + 4, (*sampled\\width << 26) & $FFFFFFFF)\n",
     "    avkqPoke32(base + #AVKQ_OFF_TEX_STATE + 4, (*sampled\\width << 25) & $FFFFFFFF)\n"),
    ("the sampled fragment stream points one word into texture state",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsTextureState[pipe] * 4), (base + #AVKQ_OFF_TEX_STATE) | $F)\n",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsTextureState[pipe] * 4), (base + #AVKQ_OFF_TEX_STATE + 16) | $F)\n"),
    ("the texture request fires S before receiving T",
     "    r = V3dQpuAdd2(#V3DQ_A_OR, #V3DQ_WADDR_TMUT, 1, #V3DQ_MUX_A, #V3DQ_MUX_A, 13, 0)\n    If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n    r = V3dQpuAdd2(#V3DQ_A_OR, #V3DQ_WADDR_TMUS, 1, #V3DQ_MUX_A, #V3DQ_MUX_A, 12, 0)\n",
     "    r = V3dQpuAdd2(#V3DQ_A_OR, #V3DQ_WADDR_TMUS, 1, #V3DQ_MUX_A, #V3DQ_MUX_A, 12, 0)\n    If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n    r = V3dQpuAdd2(#V3DQ_A_OR, #V3DQ_WADDR_TMUT, 1, #V3DQ_MUX_A, #V3DQ_MUX_A, 13, 0)\n"),
    ("the varying count is left out of the shader record's flags",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, varyComps)\n",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, 0)\n"),
    ("clipping is no longer enabled in the shader record",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, varyComps)\n",
     "  V3dShaderRecordFlags(0, 0, 0, 1, 1, varyComps)\n"),
    ("the fragment program is declared single segment",
     "  singleSegFs = 0\n",
     "  singleSegFs = 1\n"),
    ("every attribute record is built against the first binding's buffer",
     "    *bind = *d\\bindings + (bidx * SizeOf(AnvilVkBackendBinding))\n",
     "    *bind = *d\\bindings\n"),
    ("the attribute records all point at the same component",
     "      V3dAttrRecord(n, vbase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 1, 1)\n",
     "      V3dAttrRecord(n, vbase + AnvilVkPipelineAttrOffset(pipe, a), stride, maxIndex, 1, 1)\n"),
    ("an attribute record is no longer read by the coordinate shader",
     "      V3dAttrRecord(n, vbase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 1, 1)\n",
     "      V3dAttrRecord(n, vbase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 0, 1)\n"),
    ("the VPM output segment loses its extra sector for varyings",
     "  If varyComps > 0 : n = n + 1 : EndIf\n",
     "  If varyComps > 99 : n = n + 1 : EndIf\n"),
    ("the uniform stream's viewport scale is half what it should be",
     "  halfW = (AnvilVkPipelineViewportWidth(pipe) / 2) * 256\n",
     "  halfW = (AnvilVkPipelineViewportWidth(pipe) / 4) * 256\n"),
    ("the fragment uniform stream is left in the shader's component order",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsPushR[pipe] * 4), r)\n",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsPushR[pipe] * 4), b)\n"),
    ("the tile-buffer configuration word is left out of the stream",
     "  target\\tlbConfig = #AVKQ_TLB_CONF\n",
     "  target\\tlbConfig = 0\n"),
    ("the descriptor stream copies the first buffer word instead of keeping its address",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsUniformAddress[pipe] * 4), uniformBase & $FFFFFFFF)\n",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + (avkqFsUniformAddress[pipe] * 4), PeekL(uniformBase) & $FFFFFFFF)\n"),
    ("the descriptor stream omits the regular-operation field from the TMU config",
     "  If AnvilVkPipelineUsesUniformBuffer(pipe) <> 0 : target\\uniformBlockAddress = 4 : EndIf\n",
     "  If AnvilVkPipelineUsesUniformBuffer(pipe) <> 0 : target\\uniformBlockAddress = 8 : EndIf\n"),
    ("the descriptor lookup uses TMUA instead of uniform-configured TMUAU",
     "    V3dQpuAdd(#V3DQ_A_OR, #V3DQ_WADDR_TMUAU, 1, #V3DQ_MUX_A, #V3DQ_MUX_A)\n",
     "    V3dQpuAdd(#V3DQ_A_OR, #V3DQ_WADDR_TMUA, 1, #V3DQ_MUX_A, #V3DQ_MUX_A)\n"),
    ("the descriptor lookup incorrectly adds WRTMUC as a second sideband-uniform consumer",
     "    r = V3dQpuSig(#V3DQ_SIG_THRSW)\n",
     "    r = V3dQpuSig(#V3DQ_SIG_THRSW | #V3DQ_SIG_WRTMUC)\n"),
    ("the descriptor lookup starts from the wrong address register",
     "    V3dQpuRaddr(8, 0)\n",
     "    V3dQpuRaddr(7, 0)\n"),
    ("the default attribute values end in zero rather than one",
     "  avkqPoke32(base + #AVKQ_OFF_DEFAULTS + 12, #AVKQ_F_ONE)\n",
     "  avkqPoke32(base + #AVKQ_OFF_DEFAULTS + 12, #AVKQ_F_ZERO)\n"),
    ("the coordinate shader stops writing the varyings",
     "    While c < AnvilVkPipelineVaryingComponents(pipe, v)\n      r = V3dQpuStvpm(#V3DQ_A_STVPMV, #V3DQ_MUX_A, #V3DQ_MUX_B, slot, b + src + c)\n      If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n      slot = slot + 1\n      c = c + 1\n    Wend\n    v = v + 1\n  Wend\n\n  ; GFXH-1684",
     "    While c < 0\n      r = V3dQpuStvpm(#V3DQ_A_STVPMV, #V3DQ_MUX_A, #V3DQ_MUX_B, slot, b + src + c)\n      If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n      slot = slot + 1\n      c = c + 1\n    Wend\n    v = v + 1\n  Wend\n\n  ; GFXH-1684"),
    ("the viewport transform is dropped from the coordinate shader",
     "  r = V3dQpuAdd1(#V3DQ_A_FTOIN, t, 0, #V3DQ_MUX_A, t)\n  If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n  r = V3dQpuAdd1(#V3DQ_A_FTOIN, t + 1, 0, #V3DQ_MUX_A, t + 1)\n  If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n\n  ; Xc, Yc, Zc = 0.0",
     "  r = V3dQpuNop()\n  If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n  r = V3dQpuNop()\n  If r <> #V3DQ_OK : ProcedureReturn r : EndIf\n\n  ; Xc, Yc, Zc = 0.0"),
)

COMMAND = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_command.pbi"
DESCRIPTOR = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_descriptor.pbi"
MEMORY = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_memory.pbi"
API = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_api.pbi"

COMMAND_MUTANTS = (
    ("buffer-to-image copy accepts a shader-read destination layout",
     "  If dstImageLayout <> #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL\n",
     "  If dstImageLayout < 0\n"),
    ("buffer-to-image copy accepts a partial width",
     "*r\\imageExtent\\width <> avkImgW[s] Or *r\\imageExtent\\height <> avkImgH[s]",
     "*r\\imageExtent\\width < 0 Or *r\\imageExtent\\height <> avkImgH[s]"),
    ("buffer-to-image submit does not revalidate the source buffer",
     "    If avkCopyBufferResolve(avkOpBuffer[copyOp], d, avkOpBufferOffset[copyOp], avkOpSourceBytes[copyOp], @sourceBase) = 0\n",
     "    If avkCopyBufferResolve(avkOpBuffer[copyOp], d, avkOpBufferOffset[copyOp], avkOpSourceBytes[copyOp], @sourceBase) = 99\n"),
    ("buffer-to-image submit trusts a reused destination slot",
     "    s = avkImgSlot(avkRefImage[avkRefIndex(c, k)])\n    If s = 0 Or s <> avkRefSlot[avkRefIndex(c, k)] Or avkImgBound[s] = 0\n",
     "    s = avkRefSlot[avkRefIndex(c, k)]\n    If avkImgLive[s] = 0 Or avkImgBound[s] = 0\n"),
    ("a failed TFU copy publishes its final image layout",
     "    If job < 0\n      avkFlightComplete(0)\n      avkFault(#VK_ERROR_DEVICE_LOST, \"the graphics device failed while executing vkCmdCopyBufferToImage",
     "    If job < 0\n      avkFlightComplete(1)\n      avkFault(#VK_ERROR_DEVICE_LOST, \"the graphics device failed while executing vkCmdCopyBufferToImage"),
    ("buffer-to-image submit does not retain the source buffer",
     "  avkCopyBufferRetain(c)\n  avkSubmitCount = avkSubmitCount + 1\n",
     "  avkSubmitCount = avkSubmitCount + 1\n"),
    ("a command buffer may end inside a render pass",
     "  If avkCbRpActive[c] <> 0\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n",
     "  If avkCbRpActive[c] = -1\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n"),
    ("a command buffer holding both a clear and a render pass is submitted",
     "  If avkCbDrawCount[c] > 0 And (clears > 0 Or copies > 0)\n",
     "  If avkCbDrawCount[c] > 0 And (clears > 99 Or copies > 99)\n"),
)

PIPELINE_MUTANTS = (
    ("the fragment summary includes a dead decorated input",
     "If *v\\storageClass = #ANVIL_IR_STORAGE_INPUT And avkShIrLive[*v\\sourceId] <> 0",
     "If *v\\storageClass = #ANVIL_IR_STORAGE_INPUT"),
    ("the fragment summary includes a dead decorated output",
     "ElseIf *v\\storageClass = #ANVIL_IR_STORAGE_OUTPUT And *v\\sourceId = outputVariableId",
     "ElseIf *v\\storageClass = #ANVIL_IR_STORAGE_OUTPUT"),
    ("draw submission trusts a reused framebuffer slot",
     "  fb = avkFbSlot(avkCbFbHandle[c])\n  If p = 0 Or fb = 0 Or fb <> avkCbFb[c]\n",
     "  fb = avkCbFb[c]\n  If p = 0 Or fb = 0\n"),
    ("draw submission trusts a reused framebuffer image-view slot",
     "  iv = avkIvSlot(avkFbViewHandle[fb])\n  If rp = 0 Or rp <> avkFbRp[fb] Or iv = 0 Or iv <> avkFbView[fb]\n",
     "  iv = avkFbView[fb]\n  If rp = 0 Or rp <> avkFbRp[fb] Or iv = 0\n"),
    ("draw submission trusts a reused framebuffer render-pass slot",
     "  rp = avkRpSlot(avkFbRpHandle[fb])\n  iv = avkIvSlot(avkFbViewHandle[fb])\n",
     "  rp = avkFbRp[fb]\n  iv = avkIvSlot(avkFbViewHandle[fb])\n"),
    ("the sampled pipeline records the next descriptor binding",
     "  avkPipeSampleBinding[s] = avkShSampleBinding[fs]\n",
     "  avkPipeSampleBinding[s] = avkShSampleBinding[fs] + 1\n"),
    ("submit drops the closed sampled-image record",
     "    avkDrawRecord\\sampledImage = @avkSampleStage\n",
     "    avkDrawRecord\\sampledImage = 0\n"),
    ("a created sampler is left non-live",
     "  avkSampInFlight[s] = 0\n  avkSampLive[s] = 1\n",
     "  avkSampInFlight[s] = 0\n  avkSampLive[s] = 0\n"),
    ("a sampler silently accepts repeat addressing",
     "  If (*ci\\addressModeU & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE Or (*ci\\addressModeV & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE Or (*ci\\addressModeW & $FFFFFFFF) <> #VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE\n",
     "  If (*ci\\addressModeU & $FFFFFFFF) < 0 Or (*ci\\addressModeV & $FFFFFFFF) < 0 Or (*ci\\addressModeW & $FFFFFFFF) < 0\n"),
    ("a supplied zero sample mask is read as all enabled",
     "    PokeI(*outMask, PeekL(*ms\\pSampleMask) & 1)\n",
     "    PokeI(*outMask, 1)\n"),
    ("the draw record always enables sample zero",
     "  avkDrawRecord\\sampleMask = avkPipeSampleMask[p]\n",
     "  avkDrawRecord\\sampleMask = 1\n"),
    ("a transfer-only image is accepted as a framebuffer colour attachment",
     "  If (avkImgUsage[img] & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkCreateFramebuffer was given",
     "  If (avkImgUsage[img] & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = -1\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkCreateFramebuffer was given"),
    ("a render pass requires TRANSFER_DST instead of COLOR_ATTACHMENT",
     "  If (avkImgUsage[img] & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) = 0\n    avkCbFail(c, #ANVIL_VK_ERR_ARGS, \"vkCmdBeginRenderPass reached",
     "  If (avkImgUsage[img] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0\n    avkCbFail(c, #ANVIL_VK_ERR_ARGS, \"vkCmdBeginRenderPass reached"),
    ("a draw may name vertices past the end of its buffer",
     "    If stride <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k]) < need\n",
     "    If stride <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[(c * #ANVIL_VK_MAX_BINDINGS) + k]) < 0\n"),
    # --- the second binding ---
    ("every attribute is recorded as reading binding zero",
     "    avkPipeAttrBinding[base + loc] = bidx\n",
     "    avkPipeAttrBinding[base + loc] = 0\n"),
    ("an attribute is measured against binding zero's stride rather than "
     "against its own",
     "    If (j + (comps * 4)) > avkPipeBindStride[bbase + bidx]\n",
     "    If (j + (comps * 4)) > avkPipeBindStride[bbase + 0]\n"),
    ("a binding no attribute reads is accepted",
     "    If (usedBind & (1 << k)) = 0\n",
     "    If (usedBind & (1 << k)) = 99\n"),
    ("two bindings may carry the same binding number",
     "    If (seenBind & (1 << bidx)) <> 0\n",
     "    If (seenBind & (1 << bidx)) = 99\n"),
    ("a binding number outside the pipeline's own count is accepted",
     "    If bidx < 0 Or bidx >= nb\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED,",
     "    If bidx < 0 Or bidx >= 99\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED,"),
    ("an attribute may name a binding the pipeline does not describe",
     "    If bidx < 0 Or bidx >= nb\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS,",
     "    If bidx < 0 Or bidx >= 99\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS,"),
    ("a draw needs a buffer on binding zero only",
     "  While k < avkPipeBindCount[p]\n    If avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]) = 0\n      avkCbFail(",
     "  While k < 1\n    If avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k]) = 0\n      avkCbFail("),
    ("the range check is made against binding zero's stride for every binding",
     "    stride = avkPipeBindStride[(p * #ANVIL_VK_MAX_BINDINGS) + k]\n",
     "    stride = avkPipeBindStride[(p * #ANVIL_VK_MAX_BINDINGS) + 0]\n"),
    ("every binding in the draw record is filled from binding zero's buffer",
     "      b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + k])\n      avkBindStage[(k * 2) + 0] =",
     "      b = avkBufSlot(avkCbVtxBuf[(c * #ANVIL_VK_MAX_BINDINGS) + 0])\n      avkBindStage[(k * 2) + 0] ="),
    ("a binding the pipeline does not have keeps the last draw's address",
     "      avkBindStage[(k * 2) + 0] = 0\n      avkBindStage[(k * 2) + 1] = 0\n",
     "      avkBindStage[(k * 2) + 0] = avkBindStage[(k * 2) + 0]\n      avkBindStage[(k * 2) + 1] = avkBindStage[(k * 2) + 1]\n"),
    # --- the descriptor ---
    ("a uniform-reading shader is accepted on a layout with no set layout",
     "  If avkShUniform[fs] <> 0\n    If avkLaySetCount[lay] <> 1 Or avkLayBindingCount[lay] = 0\n",
     "  If avkShUniform[fs] <> 0\n    If avkLaySetCount[lay] < 0 Or avkLayBindingCount[lay] < 0\n"),
    ("the shader's binding need not be one the set layout declares",
     "    If avkLayHasBinding(lay, avkShUniformBinding[fs], #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER) = 0\n",
     "    If avkLayHasBinding(lay, avkShUniformBinding[fs], #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER) = 99\n"),
    ("a draw may read a uniform buffer with no descriptor set bound",
     "  If avkPipeUsesUniform[p] <> 0\n    If avkCbDescSet[c] = 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE,",
     "  If avkPipeUsesUniform[p] <> 0\n    If avkCbDescSet[c] = -1\n      avkCbFail(c, #ANVIL_VK_ERR_STATE,"),
    ("a bound set need not have been allocated from the layout's own shape",
     "  If avkSetMatchesLayout(set, lay) = 0\n",
     "  If avkSetMatchesLayout(set, lay) = 99\n"),
    ("a set may be bound through a layout the pipeline was not built with",
     "    If avkCbMatchesPipe(c, p) = 0\n      avkCbFail(c, #ANVIL_VK_ERR_ARGS, \"vkCmdDraw was called with descriptor state",
     "    If avkCbMatchesPipe(c, p) = 99\n      avkCbFail(c, #ANVIL_VK_ERR_ARGS, \"vkCmdDraw was called with descriptor state"),
    ("the draw record takes no descriptor address at all",
     "    avkDrawRecord\\uniformBase = AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p])\n",
     "    avkDrawRecord\\uniformBase = AnvilVkDescriptorSetAddress(avkCbDescSet[c], 0) + 4\n"),
    ("a pipeline layout may declare a set layout no shader reads",
     "  If avkShUniform[fs] = 0 And avkShSample[fs] = 0 And avkLaySetCount[lay] <> 0\n",
     "  If avkShUniform[fs] = 0 And avkShSample[fs] = 0 And avkLaySetCount[lay] < 0\n"),
    ("a draw of more than one instance is accepted",
     "  If instanceCount <> 1 Or firstInstance <> 0\n",
     "  If instanceCount < 0 Or firstInstance <> 0\n"),
    ("a zero-vertex draw consumes the backend's real-draw slot",
     "  If vertexCount = 0\n    ProcedureReturn\n  EndIf\n",
     "  If vertexCount = 0\n    avkCbDrawCount[c] = 1\n    ProcedureReturn\n  EndIf\n"),
    ("an incomplete final triangle is refused",
     "  If vertexCount < 0\n",
     "  If vertexCount < 0 Or (vertexCount > 0 And (vertexCount % 3) <> 0)\n"),
    ("blending is accepted and then not carried out",
     "  If (*a\\blendEnable & $FFFFFFFF) <> #VK_FALSE\n",
     "  If (*a\\blendEnable & $FFFFFFFF) = -1\n"),
    ("a vertex attribute may name a format with the wrong component count",
     "    If comps <> avkShInComp[(vs * #ANVIL_SPV_MAX_ATTRS) + loc]\n",
     "    If comps < 0\n"),
    ("the vertex and fragment stages need not agree on their varyings",
     "  If avkShOutCount[vs] <> avkShInCount[fs]\n",
     "  If avkShOutCount[vs] < 0\n"),
    ("a fragment shader may read push constants a layout never declared",
     "  If avkShPush[fs] <> 0 And avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES\n",
     "  If avkShPush[fs] <> 0 And avkLayPushBytes[lay] < 0\n"),
    ("a render pass whose loadOp is not CLEAR is accepted",
     "  If (*att\\loadOp & $FFFFFFFF) <> #VK_ATTACHMENT_LOAD_OP_CLEAR\n",
     "  If (*att\\loadOp & $FFFFFFFF) < 0\n"),
    ("a module is accepted at a stage that is not its own execution model",
     "      If avkShStage[s] <> 0\n",
     "      If avkShStage[s] < 0\n"),
)


DESCRIPTOR_MUTANTS = (
    ("an unsupported descriptor type is accepted in a layout",
     "    If (*bind\\descriptorType & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER And (*bind\\descriptorType & $FFFFFFFF) <> #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER\n",
     "    If (*bind\\descriptorType & $FFFFFFFF) < 0\n"),
    ("duplicate uniform-buffer pool rows are not summed",
     "      uboCapacity = uboCapacity + count\n",
     "      uboCapacity = count\n"),
    ("a set layout may declare a binding for a stage that cannot read it",
     "    If (*bind\\stageFlags & $FFFFFFFF) <> #VK_SHADER_STAGE_FRAGMENT_BIT\n",
     "    If (*bind\\stageFlags & $FFFFFFFF) < 0\n"),
    ("a write may name a buffer without the uniform usage",
     "  If avkDescBufferUniform(buf) = 0\n",
     "  If avkDescBufferUniform(buf) = 99\n"),
    ("a uniform buffer may sit at any offset",
     "  If off < 0 Or off >= size Or (off % #ANVIL_VK_UNIFORM_ALIGN) <> 0\n",
     "  If off < 0 Or off >= size Or (off % #ANVIL_VK_UNIFORM_ALIGN) < 0\n"),
    ("a descriptor range may wrap past the end of its buffer",
     "    If range < #ANVIL_VK_UNIFORM_BYTES Or range > (size - off)\n",
     "    If range < #ANVIL_VK_UNIFORM_BYTES Or range > size\n"),
    ("a descriptor copy is accepted",
     "  If copyCount <> 0 Or *pCopies <> 0\n",
     "  If copyCount < 0 Or *pCopies = -1\n"),
    ("a write may claim a descriptor type different from its copied set schema",
     "  If t <> avkDsType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + b]\n",
     "  If t < 0\n"),
    ("a mixed allocation ignores sampled-image-sampler capacity",
     "  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p]) Or needSample > (avkDpSampleCapacity[p] - avkDpSampleOut[p])\n",
     "  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p])\n"),
    ("a sampled descriptor accepts an image without SAMPLED usage",
     "    If (avkImgUsage[img] & #VK_IMAGE_USAGE_SAMPLED_BIT) = 0\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkUpdateDescriptorSets was given an image not created",
     "    If (avkImgUsage[img] & #VK_IMAGE_USAGE_SAMPLED_BIT) = -1\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkUpdateDescriptorSets was given an image not created"),
    ("a sampled descriptor accepts a layout it cannot consume",
     "    If (*imageInfo\\imageLayout & $FFFFFFFF) <> #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL\n",
     "    If (*imageInfo\\imageLayout & $FFFFFFFF) < 0\n"),
    ("a sampled descriptor resolves before its promised image layout holds",
     "  If avkImgLayout[img] <> avkDsImageLayout[idx] Or avkImgLayout[img] <> #VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : ProcedureReturn 0 : EndIf\n",
     "  If avkImgLayout[img] < 0 : ProcedureReturn 0 : EndIf\n"),
    ("the sampled record drops the image pitch",
     "  *out\\pitch = avkImgPitch[img]\n",
     "  *out\\pitch = 0\n"),
    ("the sampled record drops the sampler's magnification filter",
     "  *out\\magFilter = avkDescSamplerMagFilter(sampler)\n",
     "  *out\\magFilter = 0\n"),
)


MEMORY_MUTANTS = (
    ("an optimal image publishes a fake linear row pitch",
     "  avkImgPitch[s] = plan\\rowPitch\n  avkImgSize[s] = plan\\bytes\n",
     "  avkImgPitch[s] = 64\n  avkImgSize[s] = plan\\bytes\n"),
    ("COLOR_ATTACHMENT image creation is refused",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT))) <> 0 Or usage = 0\n"),
    ("SAMPLED image creation is refused",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n"),
)

API_MUTANTS = (
    ("vkCmdCopyBufferToImage accepts more than one region",
     "  If regionCount <> 1 Or *pRegions = 0\n    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, \"vkCmdCopyBufferToImage was given other than one copy region",
     "  If regionCount < 0 Or *pRegions = 0\n    avkCbFail(c, #ANVIL_VK_ERR_UNSUPPORTED, \"vkCmdCopyBufferToImage was given other than one copy region"),
    ("an image view with an empty mip range is accepted",
     "  If (*pCreateInfo\\subresourceRange\\levelCount & $FFFFFFFF) <> 1 Or (*pCreateInfo\\subresourceRange\\layerCount & $FFFFFFFF) <> 1\n",
     "  If (*pCreateInfo\\subresourceRange\\levelCount & $FFFFFFFF) < 0 Or (*pCreateInfo\\subresourceRange\\layerCount & $FFFFFFFF) <> 1\n"),
    ("an image view with an empty layer range is accepted",
     "  If (*pCreateInfo\\subresourceRange\\levelCount & $FFFFFFFF) <> 1 Or (*pCreateInfo\\subresourceRange\\layerCount & $FFFFFFFF) <> 1\n",
     "  If (*pCreateInfo\\subresourceRange\\levelCount & $FFFFFFFF) <> 1 Or (*pCreateInfo\\subresourceRange\\layerCount & $FFFFFFFF) < 0\n"),
)


# The 2026-09-12 full run exposed six older mutants whose request reached a
# later rule returning the same code. Keep them as a named focused batch: it
# makes their repair gate minutes rather than half an hour, while plain
# --mutate remains the complete suite and cannot silently omit anything.
VALIDATION_TRUTH_MUTANTS = frozenset({
    "two bindings may carry the same binding number",
    "a binding number outside the pipeline's own count is accepted",
    "a binding the pipeline does not have keeps the last draw's address",
    "a bound set need not have been allocated from the layout's own shape",
    "a set may be bound through a layout the pipeline was not built with",
    "a uniform buffer may sit at any offset",
})

IMAGE_USAGE_TRUTH_MUTANTS = frozenset({
    "COLOR_ATTACHMENT image creation is refused",
    "a transfer-only image is accepted as a framebuffer colour attachment",
    "a render pass requires TRANSFER_DST instead of COLOR_ATTACHMENT",
})

SAMPLE_MASK_TRUTH_MUTANTS = frozenset({
    "a supplied zero sample mask is read as all enabled",
    "the draw record always enables sample zero",
})

DRAW_COUNT_TRUTH_MUTANTS = frozenset({
    "a zero-vertex draw consumes the backend's real-draw slot",
    "an incomplete final triangle is refused",
})

LIFETIME_ALIAS_MUTANTS = frozenset({
    "buffer-to-image submit trusts a reused destination slot",
    "draw submission trusts a reused framebuffer slot",
    "draw submission trusts a reused framebuffer image-view slot",
    "draw submission trusts a reused framebuffer render-pass slot",
})

SAMPLED_STATE_MUTANTS = frozenset({
    "an unsupported descriptor type is accepted in a layout",
    "a combined image sampler is accepted in a multi-binding layout",
    "a write may claim a descriptor type different from its layout",
    "a pool type is ignored when a descriptor set is allocated",
    "a sampled descriptor accepts an image without SAMPLED usage",
    "a sampled descriptor accepts a layout it cannot consume",
    "a sampled descriptor resolves before its promised image layout holds",
    "the sampled record drops the image pitch",
    "the sampled record drops the sampler's magnification filter",
    "SAMPLED image creation is refused",
    "an image view with an empty mip range is accepted",
    "an image view with an empty layer range is accepted",
})

SAMPLED_EXEC_MUTANTS = frozenset({
    "the sampled texture-state width is packed in the wrong field",
    "the sampled fragment stream points one word into texture state",
    "the texture request fires S before receiving T",
    "the sampled pipeline records the next descriptor binding",
    "submit drops the closed sampled-image record",
})

TEST_BACKEND = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_backend_test.pbi"
TEST_BACKEND_MUTANTS = (
    ("the portable copy recorder ignores backend source alignment",
     "Procedure.i avkBackendImageCopySourceAlignment()\n  ProcedureReturn avkTbCopyAlign\nEndProcedure\n",
     "Procedure.i avkBackendImageCopySourceAlignment()\n  ProcedureReturn 64\nEndProcedure\n"),
    ("the copy backend cannot hold an in-flight transfer",
     "  avkTbLastCopyBytes = *copy\\destinationBytes\n  avkTbNative = 0\n  If avkTbHold <> 0\n",
     "  avkTbLastCopyBytes = *copy\\destinationBytes\n  avkTbNative = 0\n  If avkTbHold = 99\n"),
    ("the copy backend reports source bytes as destination capacity",
     "  avkTbLastCopyBytes = *copy\\destinationBytes\n",
     "  avkTbLastCopyBytes = *copy\\sourceBytes\n"),
)

OPTIMAL_COPY_MUTANTS = frozenset({
    "optimal sampled state loses the strict-UIF level-zero bit",
    "buffer-to-image copy accepts a shader-read destination layout",
    "buffer-to-image copy accepts a partial width",
    "buffer-to-image submit does not revalidate the source buffer",
    "buffer-to-image submit trusts a reused destination slot",
    "the portable copy recorder ignores backend source alignment",
    "a failed TFU copy publishes its final image layout",
    "buffer-to-image submit does not retain the source buffer",
    "an optimal image publishes a fake linear row pitch",
    "vkCmdCopyBufferToImage accepts more than one region",
    "the copy backend cannot hold an in-flight transfer",
    "the copy backend reports source bytes as destination capacity",
})


def run(a64, compiler):
    cpu, rc, steps = execute(a64, build(compiler))
    return grade(cpu, rc), steps


@contextlib.contextmanager
def checker_lock():
    """Serialize the checker because mutation mode temporarily edits source.

    Unique output directories stop artifact aliasing; this OS lock closes the
    other half of the race by ensuring a baseline cannot compile while another
    process has installed a hostile source mutation.
    """
    lock_path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with lock_path.open("a+b") as stream:
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


def main() -> int:
    all_mutants = (MUTANTS + PIPELINE_MUTANTS + COMMAND_MUTANTS +
                   DESCRIPTOR_MUTANTS + MEMORY_MUTANTS + API_MUTANTS +
                   TEST_BACKEND_MUTANTS)
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--coordination-probe", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--mutate-only", choices=("validation-truth", "image-usage",
                                                   "sample-mask", "draw-count",
                                                   "lifetime-alias",
                                                   "sampled-state", "sampled-exec",
                                                   "optimal-copy"))
    parser.add_argument("--mutate-name", choices=tuple(m[0] for m in all_mutants),
                        help="run exactly one named mutation after the green gate")
    args = parser.parse_args()
    if args.coordination_probe:
        start = time.monotonic_ns()
        time.sleep(0.25)
        print(f"{RUN_DIR}|{start}|{time.monotonic_ns()}")
        return 0
    if args.mutate_only or args.mutate_name:
        args.mutate = True

    # Mutation proof is meaningful only when every requested edit is a unique,
    # byte-exact change to the intended production rule. Missing or ambiguous
    # anchors are checker infrastructure failures, never semantic rejections.
    if args.mutate:
        anchor_errors = []
        for path, mutants in ((EMITTER, MUTANTS), (PIPELINE, PIPELINE_MUTANTS),
                              (COMMAND, COMMAND_MUTANTS),
                              (DESCRIPTOR, DESCRIPTOR_MUTANTS),
                              (MEMORY, MEMORY_MUTANTS), (API, API_MUTANTS),
                              (TEST_BACKEND, TEST_BACKEND_MUTANTS)):
            source = path.read_text(encoding="utf-8")
            for name, fixed, _broken in mutants:
                hits = source.count(fixed)
                if hits != 1:
                    anchor_errors.append(f"{path.name}: {name}: {hits} hits")
        if anchor_errors:
            print("vulkan_pipeline_check: INFRA - mutation anchors are not unique")
            for error in anchor_errors:
                print("  " + error)
            return 2

    compiler = locate_compiler(args.compiler)
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    # The board diagnostic must at least build, at its own load address.
    compile_one(compiler, DIAGNOSTIC, "anvil_vulkanTriangleProof.img",
                0x500000, 0x4F00000)
    compile_one(compiler, DIAGNOSTIC2, "anvil_vulkanVaryingProof.img",
                0x500000, 0x4F00000)
    g, steps = run(a64, compiler)
    if g.failures:
        print(f"vulkan_pipeline_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"vulkan_pipeline_check: PASS - {g.checks} property checks over "
          f"{steps:,} executed A64 instructions")
    print("  the whole public path runs: eight shader modules, five pipeline layouts, a")
    print("  render pass, a framebuffer, four buffers, a sampler, three descriptor set layouts, two pools")
    print("  and three sets, six graphics pipelines over four live slots, six render passes each holding one draw,")
    print("  seven submissions and a fence")
    print("  all five shader variants were compiled by the REAL V3D QPU emitter, and every byte")
    print("  of their shader records, attribute records, uniform streams and default")
    print("  attribute values matches a record this checker packed from the documented layout")
    print("  the third pipeline reads POSITION FROM ONE BUFFER AND COLOUR FROM ANOTHER, at")
    print("  two different strides: two of its six attribute records carry one base and")
    print("  stride and four carry the other, and its three emitted programs are byte for")
    print("  byte the one-buffer pipeline's - the split moves where the data is, not what runs")
    print("  the fourth takes its colour from a UNIFORM BUFFER through a descriptor set;")
    print("  its stream keeps the descriptor address and the raw QPU words decode to a V3D")
    print("  4.2 TMU general vec4 lookup - no CPU copy of the buffer values remains")
    print("  the sampled shader consumes a separate one-texel image through a closed descriptor;")
    print("  the gate independently checks both SPIR-V modules, pipeline state, exact V3D 4.2")
    print("  texture/sampler words, uniform pointers and the executable backend record")
    print("  NOT ONE PIXEL of the render target was written and NOT ONE MMIO access was made")
    print("  RaspberryPi4/Examples/Diagnostics/vulkanTriangleProof.pi4 and")
    print("  RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4 both build at $500000")
    print("  (not executed: it needs the GPU, and that is a board slot)")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    missed = 0
    for path, mutants in ((EMITTER, MUTANTS), (PIPELINE, PIPELINE_MUTANTS),
                          (COMMAND, COMMAND_MUTANTS),
                          (DESCRIPTOR, DESCRIPTOR_MUTANTS),
                          (MEMORY, MEMORY_MUTANTS), (API, API_MUTANTS),
                          (TEST_BACKEND, TEST_BACKEND_MUTANTS)):
        original = path.read_text(encoding="utf-8")
        for name, fixed, broken in mutants:
            if args.mutate_name and name != args.mutate_name:
                continue
            if args.mutate_only == "validation-truth" and name not in VALIDATION_TRUTH_MUTANTS:
                continue
            if args.mutate_only == "image-usage" and name not in IMAGE_USAGE_TRUTH_MUTANTS:
                continue
            if args.mutate_only == "sample-mask" and name not in SAMPLE_MASK_TRUTH_MUTANTS:
                continue
            if args.mutate_only == "draw-count" and name not in DRAW_COUNT_TRUTH_MUTANTS:
                continue
            if args.mutate_only == "lifetime-alias" and name not in LIFETIME_ALIAS_MUTANTS:
                continue
            if args.mutate_only == "sampled-state" and name not in SAMPLED_STATE_MUTANTS:
                continue
            if args.mutate_only == "sampled-exec" and name not in SAMPLED_EXEC_MUTANTS:
                continue
            if args.mutate_only == "optimal-copy" and name not in OPTIMAL_COPY_MUTANTS:
                continue
            if original.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor appears {original.count(fixed)} times")
                missed += 1
                continue
            path.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
            try:
                mg, _ = run(a64, compiler)
                red = bool(mg.failures)
                first = mg.failures[0][:96] if mg.failures else ""
            except SystemExit as exc:
                red, first = True, str(exc).splitlines()[0][:96]
            finally:
                path.write_text(original, encoding="utf-8")
            if red:
                print(f"  RED    {name} - {first}")
            else:
                print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE")
                missed += 1

    if args.mutate_name:
        total = 1
    elif args.mutate_only == "validation-truth":
        total = len(VALIDATION_TRUTH_MUTANTS)
    elif args.mutate_only == "image-usage":
        total = len(IMAGE_USAGE_TRUTH_MUTANTS)
    elif args.mutate_only == "sample-mask":
        total = len(SAMPLE_MASK_TRUTH_MUTANTS)
    elif args.mutate_only == "draw-count":
        total = len(DRAW_COUNT_TRUTH_MUTANTS)
    elif args.mutate_only == "lifetime-alias":
        total = len(LIFETIME_ALIAS_MUTANTS)
    elif args.mutate_only == "sampled-state":
        total = len(SAMPLED_STATE_MUTANTS)
    elif args.mutate_only == "sampled-exec":
        total = len(SAMPLED_EXEC_MUTANTS)
    elif args.mutate_only == "optimal-copy":
        total = len(OPTIMAL_COPY_MUTANTS)
    else:
        total = (len(MUTANTS) + len(PIPELINE_MUTANTS) + len(COMMAND_MUTANTS)
                 + len(DESCRIPTOR_MUTANTS) + len(MEMORY_MUTANTS) + len(API_MUTANTS))
        total += len(TEST_BACKEND_MUTANTS)
    print()
    if missed:
        print(f"vulkan_pipeline_check: {missed} of {total} mutations were not caught")
        return 1
    print(f"vulkan_pipeline_check: all {total} mutations rejected")
    return 0


if __name__ == "__main__":
    with checker_lock():
        raise SystemExit(main())
