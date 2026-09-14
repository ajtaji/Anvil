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
DIAGNOSTIC2 = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanVaryingProof.pi4"

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
TMU_GENERAL_VEC4 = 0xFFFFFF7C

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
            spv.vertex_position_only(), spv.fragment_push(),
            spv.fragment_uniform(),
            # The same uniform fragment shader at BINDING ONE. The gate
            # offers it against a set layout that has binding zero only,
            # which is the one way a shader and a layout can disagree
            # that no other rule in the path can see.
            spv.fragment_uniform(binding=1)]


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
           slot(21), 1)
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
           slot(164), 2)
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
                 expected_shader_record(baseB, interleaved(vertex_base, STRIDE2, 2), 2, 0))
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
    g.need("three draws have now reached the backend", slot(112), 3)
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
    g.need("four draws have now reached the backend", slot(68), 4)

    # pSampleMask is not optional semantics. With one sample, bit zero
    # clear suppresses every fragment while the render-pass clear still
    # runs. The state-only backend records the closed draw contract; the
    # real V3D gate separately requires the primitive-emission branch.
    g.need("the zero-sample-mask pipeline was created", slot(155), 0)
    g.need("the zero-sample-mask draw recorded cleanly", slot(156), 0)
    g.need("the zero-sample-mask draw submitted", slot(157), 0)
    g.need("the zero-sample-mask draw's fence signalled", slot(158), 0)
    g.need("the draw record carries sample bit zero clear", slot(159), 0)
    g.need("the suppressed draw still reached the backend as the fifth draw",
           slot(160), 5)

    # --- descriptor state: one uniform path and one bounded sampled path ---
    g.need("a storage-image descriptor is refused",
           slot(123), ERR_UNSUPPORTED)
    sampler_text = cstr(cpu, u64(cpu, base + 71 * 8))
    g.want_true("that refusal names the unsupported storage-image type",
                "storage image descriptor" in sampler_text, repr(sampler_text[:140]))
    g.need("the bounded combined-image-sampler set layout was created", slot(171), 0)
    g.need("a combined image sampler in a multi-binding layout is refused",
           slot(196), ERR_UNSUPPORTED)
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
                "allocated from a different VkDescriptorSetLayout" in shape_text,
                repr(shape_text[:170]))
    g.need("a correctly shaped set bound through the wrong pipeline layout is "
           "refused at draw", slot(147), ERR_ARGS)
    pipeline_layout_text = cstr(cpu, u64(cpu, base + 148 * 8))
    g.want_true("the wrong-pipeline-layout refusal is the draw-time layout rule",
                "bound through a different pipeline layout" in pipeline_layout_text,
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
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, b)\n",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, r)\n"),
    ("the tile-buffer configuration word is left out of the stream",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 16, #AVKQ_TLB_CONF)\n",
     "  avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 16, 0)\n"),
    ("the descriptor stream copies the first buffer word instead of keeping its address",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, *push & $FFFFFFFF)\n",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 0, PeekL(*push) & $FFFFFFFF)\n"),
    ("the descriptor stream omits the regular-operation field from the TMU config",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 4, #AVKQ_TMU_LOAD_VEC4)\n",
     "    avkqPoke32(base + #AVKQ_OFF_UNIF_FS + 4, $FFFFFF84)\n"),
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
    ("a command buffer may end inside a render pass",
     "  If avkCbRpActive[c] <> 0\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n",
     "  If avkCbRpActive[c] = -1\n    avkCmdState[c] = #ANVIL_VK_CB_INVALID\n"),
    ("a command buffer holding both a clear and a render pass is submitted",
     "  If avkCbDrawCount[c] > 0 And clears > 0\n",
     "  If avkCbDrawCount[c] > 0 And clears > 99\n"),
)

PIPELINE_MUTANTS = (
    ("a created sampler is left non-live",
     "  avkSampLive[s] = 1\n  avkSampDev[s] = d\n",
     "  avkSampLive[s] = 0\n  avkSampDev[s] = d\n"),
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
     "    If avkLaySetCount[lay] <> 1 Or avkLaySetLayout[lay] = 0\n",
     "    If avkLaySetCount[lay] < 0 Or avkLaySetLayout[lay] < 0\n"),
    ("the shader's binding need not be one the set layout declares",
     "    If AnvilVkSetLayoutHasUniform(avkLaySetLayout[lay], avkShUniformBinding[fs]) = 0\n",
     "    If AnvilVkSetLayoutHasUniform(avkLaySetLayout[lay], avkShUniformBinding[fs]) = 99\n"),
    ("a draw may read a uniform buffer with no descriptor set bound",
     "    If avkCbDescSet[c] = 0\n      avkCbFail(c, #ANVIL_VK_ERR_STATE,",
     "    If avkCbDescSet[c] = -1\n      avkCbFail(c, #ANVIL_VK_ERR_STATE,"),
    ("a bound set need not have been allocated from the layout's own shape",
     "  If AnvilVkDescriptorSetLayoutSlot(set) <> avkLaySetLayout[lay]\n",
     "  If AnvilVkDescriptorSetLayoutSlot(set) < 0\n"),
    ("a set may be bound through a layout the pipeline was not built with",
     "    If avkLaySlot(avkCbDescLayout[c]) <> avkPipeLayout[p]\n",
     "    If avkLaySlot(avkCbDescLayout[c]) < 0\n"),
    ("the draw record takes no descriptor address at all",
     "    avkDrawRecord\\uniformBase = AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p])\n",
     "    avkDrawRecord\\uniformBase = AnvilVkDescriptorSetAddress(avkCbDescSet[c], 0) + 4\n"),
    ("a pipeline layout may declare a set layout no shader reads",
     "  If avkShColourSrc[fs] <> #ANVIL_SPV_COLOUR_UNIFORM And avkLaySetCount[lay] <> 0\n",
     "  If avkShColourSrc[fs] <> #ANVIL_SPV_COLOUR_UNIFORM And avkLaySetCount[lay] < 0\n"),
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
     "  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_PUSH And avkLayPushBytes[lay] <> #ANVIL_VK_PUSH_BYTES\n",
     "  If avkShColourSrc[fs] = #ANVIL_SPV_COLOUR_PUSH And avkLayPushBytes[lay] < 0\n"),
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
    ("a combined image sampler is accepted in a multi-binding layout",
     "    If (*bind\\descriptorType & $FFFFFFFF) = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER And (n <> 1 Or b <> 0)\n",
     "    If (*bind\\descriptorType & $FFFFFFFF) = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER And n < 0\n"),
    ("a set layout may declare a binding for a stage that cannot read it",
     "    If (*bind\\stageFlags & $FFFFFFFF) <> #VK_SHADER_STAGE_FRAGMENT_BIT\n",
     "    If (*bind\\stageFlags & $FFFFFFFF) < 0\n"),
    ("a write may name a buffer without the uniform usage",
     "  If avkDescBufferUniform(buf) = 0\n",
     "  If avkDescBufferUniform(buf) = 99\n"),
    ("a uniform buffer may sit at any offset",
     "  If off < 0 Or off >= size Or (off % #ANVIL_VK_UNIFORM_ALIGN) <> 0\n",
     "  If off < 0 Or off >= size Or (off % #ANVIL_VK_UNIFORM_ALIGN) < 0\n"),
    ("a descriptor range shorter than the block is accepted",
     "  If range < #ANVIL_VK_UNIFORM_BYTES Or (off + range) > size\n",
     "  If range < 0 Or (off + range) > size\n"),
    ("a descriptor copy is accepted",
     "  If copyCount <> 0 Or *pCopies <> 0\n",
     "  If copyCount < 0 Or *pCopies = -1\n"),
    ("a write may claim a descriptor type different from its layout",
     "  If t <> avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + b]\n",
     "  If t < 0\n"),
    ("a pool type is ignored when a descriptor set is allocated",
     "    If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k] <> avkDpType[p]\n",
     "    If avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k] < 0\n"),
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
    ("COLOR_ATTACHMENT image creation is refused",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT))) <> 0 Or usage = 0\n"),
    ("SAMPLED image creation is refused",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_SAMPLED_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n",
     "  If (usage & (~(#VK_IMAGE_USAGE_TRANSFER_SRC_BIT | #VK_IMAGE_USAGE_TRANSFER_DST_BIT | #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))) <> 0 Or usage = 0\n"),
)

API_MUTANTS = (
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


def run(a64, compiler):
    cpu, rc, steps = execute(a64, build(compiler))
    return grade(cpu, rc), steps


def main() -> int:
    all_mutants = (MUTANTS + PIPELINE_MUTANTS + COMMAND_MUTANTS +
                   DESCRIPTOR_MUTANTS + MEMORY_MUTANTS + API_MUTANTS)
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--mutate-only", choices=("validation-truth", "image-usage",
                                                   "sample-mask", "draw-count",
                                                   "sampled-state"))
    parser.add_argument("--mutate-name", choices=tuple(m[0] for m in all_mutants),
                        help="run exactly one named mutation after the green gate")
    args = parser.parse_args()
    if args.mutate_only or args.mutate_name:
        args.mutate = True

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
    print("  the whole public path runs: six shader modules, four pipeline layouts, a")
    print("  render pass, a framebuffer, four buffers, a sampler, three descriptor set layouts, two pools")
    print("  and three sets, five graphics pipelines over four live slots, five render passes each holding one draw,")
    print("  five submissions and a fence")
    print("  all four shader variants were compiled by the REAL V3D QPU emitter, and every byte")
    print("  of their shader records, attribute records, uniform streams and default")
    print("  attribute values matches a record this checker packed from the documented layout")
    print("  the third pipeline reads POSITION FROM ONE BUFFER AND COLOUR FROM ANOTHER, at")
    print("  two different strides: two of its six attribute records carry one base and")
    print("  stride and four carry the other, and its three emitted programs are byte for")
    print("  byte the one-buffer pipeline's - the split moves where the data is, not what runs")
    print("  the fourth takes its colour from a UNIFORM BUFFER through a descriptor set;")
    print("  its stream keeps the descriptor address and the raw QPU words decode to a V3D")
    print("  4.2 TMU general vec4 lookup - no CPU copy of the buffer values remains")
    print("  a combined image sampler also resolves into one closed backend record only while")
    print("  its sampler, full view, sampled-usage image and shader-read layout are all live")
    print("  (state only: this gate makes no sampled-pixel or texture-opcode claim)")
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
                          (MEMORY, MEMORY_MUTANTS), (API, API_MUTANTS)):
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
            if args.mutate_only == "sampled-state" and name not in SAMPLED_STATE_MUTANTS:
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
    elif args.mutate_only == "sampled-state":
        total = len(SAMPLED_STATE_MUTANTS)
    else:
        total = (len(MUTANTS) + len(PIPELINE_MUTANTS) + len(COMMAND_MUTANTS)
                 + len(DESCRIPTOR_MUTANTS) + len(MEMORY_MUTANTS) + len(API_MUTANTS))
    print()
    if missed:
        print(f"vulkan_pipeline_check: {missed} of {total} mutations were not caught")
        return 1
    print(f"vulkan_pipeline_check: all {total} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
