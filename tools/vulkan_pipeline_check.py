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
import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
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

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 400_000_000
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
PIPE_BYTES = 8192

SHREC_BYTES = 36
ATTR_BYTES = 16
ATTR_FLOAT = 2

F0 = 0x00000000
F1 = 0x3F800000
TLB_CONF = 0xFFFFFFFF

W = H = 64
STRIDE1, STRIDE2 = 24, 8
PUSH = (0x3F800000, 0x3F000000, 0x00000000, 0x3F800000)   # r, g, b, a

ERR_UNSUPPORTED = -20005
ERR_ARGS = -20001
ERR_STATE = -20004
VK_ERROR_FEATURE_NOT_PRESENT = -8


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


def expected_shader_record(base: int, vertex_base: int, stride: int,
                           max_index: int, vary: int, records: int) -> bytes:
    """The 36-byte record and its attribute records, packed here.

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

    # One attribute record per component: same base array, one four-byte
    # step per record, every record read by both phases.
    for n in range(records):
        addr = vertex_base + n * 4
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
    image = pathlib.Path(tempfile.gettempdir()) / name
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


def modules() -> list[bytes]:
    return [spv.vertex_passthrough(), spv.fragment_varying(),
            spv.vertex_position_only(), spv.fragment_push()]


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
    raise SystemExit(f"vulkan_pipeline_check: the gate did not return in {STEP_LIMIT} steps")


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
    g.need("the gate ran to the end", slot(1), 0)
    if slot(1) != 0:
        g.failures.append("  fault: " + cstr(cpu, u64(cpu, base + 32 * 8))[:200])
        return g

    g.need("the test backend reports a draw capability", slot(38), 1)
    g.need("the image is the size its pitch and height say",
           slot(4), slot(5) * H)
    g.want_true("the image pitch covers a row", slot(5) >= W * 4, str(slot(5)))

    # --- the public path reached the backend with the right numbers ---
    vertex_base = slot(6)
    g.need("one draw reached the backend", slot(21), 1)
    g.need("two pipelines were compiled by the backend", slot(22), 2)
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
    g.need("a vertex count that is not a multiple of three is refused",
           slot(44), ERR_ARGS)
    g.need("a draw naming vertices past the end of the buffer is refused",
           slot(45), ERR_ARGS)
    g.need("ending a command buffer inside a render pass is refused",
           slot(48), ERR_STATE)
    g.need("an attribute format with the wrong component count is refused",
           slot(53), ERR_ARGS)
    g.need("a fragment shader that reads a varying nothing writes is refused",
           slot(54), ERR_ARGS)
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
                 expected_shader_record(baseA, vertex_base, STRIDE1, 2, 4, 6))
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
                 expected_shader_record(baseB, vertex_base, STRIDE2, 2, 0, 2))
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

    # --- the programs are the length the emission rules predict ---
    csA, vsA, fsA = slot(10), slot(11), slot(12)
    csB, vsB, fsB = slot(16), slot(17), slot(18)
    for name, value in (("[A] coordinate", csA), ("[A] vertex", vsA),
                        ("[A] fragment", fsA), ("[B] coordinate", csB),
                        ("[B] vertex", vsB), ("[B] fragment", fsB)):
        g.want_true(f"{name} program is a whole number of instructions",
                    value > 0 and value % 8 == 0, str(value))
        g.want_true(f"{name} program fits its slot", value <= 1024, str(value))

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
    return g


MUTANTS = (
    ("the varying count is left out of the shader record's flags",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, varyComps)\n",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, 0)\n"),
    ("clipping is no longer enabled in the shader record",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, varyComps)\n",
     "  V3dShaderRecordFlags(0, 0, 0, 1, 1, varyComps)\n"),
    ("the fragment program is declared single segment",
     "  singleSegFs = 0\n",
     "  singleSegFs = 1\n"),
    ("the attribute records all point at the same component",
     "      V3dAttrRecord(n, vertexBase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 1, 1)\n",
     "      V3dAttrRecord(n, vertexBase + AnvilVkPipelineAttrOffset(pipe, a), stride, maxIndex, 1, 1)\n"),
    ("an attribute record is no longer read by the coordinate shader",
     "      V3dAttrRecord(n, vertexBase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 1, 1)\n",
     "      V3dAttrRecord(n, vertexBase + AnvilVkPipelineAttrOffset(pipe, a) + (c * 4), stride, maxIndex, 0, 1)\n"),
    ("the VPM output segment loses its extra sector for varyings",
     "  If varyComps > 0 : n = n + 1 : EndIf\n",
     "  If varyComps > 99 : n = n + 1 : EndIf\n"),
    ("the uniform stream's viewport scale is half what it should be",
     "  halfW = (AnvilVkPipelineViewportWidth(pipe) / 2) * 256\n",
     "  halfW = (AnvilVkPipelineViewportWidth(pipe) / 4) * 256\n"),
    ("the fragment uniform stream is left in the shader's component order",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, b)\n",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, r)\n"),
    ("the tile-buffer configuration word is left out of the stream",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 16, #AVKQ_TLB_CONF)\n",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 16, 0)\n"),
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

COMMAND_MUTANTS = (
    ("a command buffer may end inside a render pass",
     "  If avkCbRpActive[c] <> 0\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n",
     "  If avkCbRpActive[c] = -1\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n"),
    ("a command buffer holding both a clear and a render pass is submitted",
     "  If avkCbDrawCount[c] > 0 And clears > 0\n",
     "  If avkCbDrawCount[c] > 0 And clears > 99\n"),
)

PIPELINE_MUTANTS = (
    ("a draw may name vertices past the end of its buffer",
     "  If avkPipeStride[p] <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[c]) < need\n",
     "  If avkPipeStride[p] <= 0 Or need <= 0 Or (avkBufSize[b] - avkCbVtxOffset[c]) < 0\n"),
    ("a draw of more than one instance is accepted",
     "  If instanceCount <> 1 Or firstInstance <> 0\n",
     "  If instanceCount < 0 Or firstInstance <> 0\n"),
    ("a vertex count that is not a whole number of triangles is accepted",
     "  If vertexCount < 3 Or (vertexCount % 3) <> 0\n",
     "  If vertexCount < 3\n"),
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
     "  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_PUSH And avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES\n",
     "  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_PUSH And avkLayPushBytes[lay] < 0\n"),
    ("a render pass whose loadOp is not CLEAR is accepted",
     "  If (*att\\loadOp & $FFFFFFFF) <> #VK_ATTACHMENT_LOAD_OP_CLEAR\n",
     "  If (*att\\loadOp & $FFFFFFFF) < 0\n"),
    ("a module is accepted at a stage that is not its own execution model",
     "      If avkShStage[s] <> 0\n",
     "      If avkShStage[s] < 0\n"),
)


def run(a64, compiler):
    cpu, rc, steps = execute(a64, build(compiler))
    return grade(cpu, rc), steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate_compiler(args.compiler)
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    # The board diagnostic must at least build, at its own load address.
    compile_one(compiler, DIAGNOSTIC, "anvil_vulkanTriangleProof.img",
                0x500000, 0x4F00000)
    g, steps = run(a64, compiler)
    if g.failures:
        print(f"vulkan_pipeline_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"vulkan_pipeline_check: PASS - {g.checks} property checks over "
          f"{steps:,} executed A64 instructions")
    print("  the whole public path runs: two shader modules, two pipeline layouts, a render")
    print("  pass, a framebuffer, a vertex buffer, two graphics pipelines, one render pass")
    print("  holding one draw, a submission and a fence")
    print("  both pipelines were compiled by the REAL V3D QPU emitter, and every byte of")
    print("  their shader records, attribute records, uniform streams and default attribute")
    print("  values matches a record this checker packed itself from the documented layout")
    print("  NOT ONE PIXEL of the render target was written and NOT ONE MMIO access was made")
    print("  RaspberryPi4/Examples/Diagnostics/vulkanTriangleProof.pi4 builds at $500000")
    print("  (not executed: it needs the GPU, and that is a board slot)")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    missed = 0
    for path, mutants in ((EMITTER, MUTANTS), (PIPELINE, PIPELINE_MUTANTS),
                          (COMMAND, COMMAND_MUTANTS)):
        original = path.read_text(encoding="utf-8")
        for name, fixed, broken in mutants:
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

    total = len(MUTANTS) + len(PIPELINE_MUTANTS) + len(COMMAND_MUTANTS)
    print()
    if missed:
        print(f"vulkan_pipeline_check: {missed} of {total} mutations were not caught")
        return 1
    print(f"vulkan_pipeline_check: all {total} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
