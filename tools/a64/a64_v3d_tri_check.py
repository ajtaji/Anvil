#!/usr/bin/env python3
"""Executable gate for V3D stage 4 - the draw.

Run:
  python tools/a64/a64_v3d_tri_check.py --compiler PureMetalForge.exe
  python tools/a64/a64_v3d_tri_check.py --compiler PureMetalForge.exe --mutate

=====================================================================
 WHAT IS NEW AT STAGE 4 AND THEREFORE WHAT THIS FILE IS FOR
=====================================================================

a64_v3d_rcl_check.py covers the control lists a CLEAR needs.  A DRAW
adds four things it does not cover, and every one of them is a
structure the hardware reads directly:

  1. the GL SHADER STATE RECORD, 36 bytes, twenty booleans and eight
     nibbles and six addresses;
  2. eight GL SHADER STATE ATTRIBUTE RECORDS, 16 bytes each;
  3. the draw state in the BIN list - the clip window, the clipper
     scaling, the viewport offset, the shader state pointer and the
     primitive;
  4. three QPU PROGRAMS built through v3dqpu.pi4's emitter.

=====================================================================
 WHERE THE EXPECTATIONS COME FROM
=====================================================================

 * The V3D model, the control-list walker and the packet and struct
   layouts are IMPORTED from a64_v3d_rcl_check.py, which pins them from
   Mesa's v3d_packet.xml (mesa-24.3.4) with line citations.  Two copies
   of a V3D model would drift.

 * The three QPU programs are compared against GOLDEN WORDS produced by
   py-videocore6 (Idein Inc., commit
   175741a389348a739a7d2bf559b9d302d7e390a9, assembler.py), an
   independent assembler, for every instruction it can encode.  The
   words are PINNED below beside the py-videocore6 spelling that
   produced each one; none of that project's code is in this repository
   and it is not imported.  The ten LDVPMV_IN instructions it cannot
   encode are assembled here from a64_v3d_qpu_check.py's pinned Mesa
   tables - a model against a model, counted separately.

 * Every program is also run through tools/v3d42_qpu_decode.py's
   straight-line verifier, an Anvil-owned decoder that imports nothing
   from the packer, under the coordinate, vertex and flat-fragment
   contracts.

 * The bin list's packet ORDER is checked as a subsequence of Mesa's
   emission order, pinned per function from
   src/gallium/drivers/v3d/v3dx_draw.c, v3dx_emit.c and v3dx_job.c
   (mesa-24.3.4) below.  That is mechanical, not independent.

=====================================================================
 WHAT THIS GATE CANNOT DO.  READ THIS BEFORE TRUSTING A GREEN RUN.
=====================================================================

 1. IT CANNOT RASTERISE.  There is no V3D in the interpreter.  The model
    bumps CLE_BFC and CLE_RFC when the end-address registers are written
    and does nothing else, so the render target keeps every poison word.
    THE GATE ASSERTS THAT FIRST - it requires the probe to report zero
    triangle pixels and 4096 still poison - so a green run can never be
    mistaken for a picture.  Only pi4V3dTri.pi4 on the board can say
    there is a triangle.

 2. IT CANNOT SAY THE RECORD LAYOUT IS RIGHT, only that the library and
    the pinned v3d_packet.xml layout agree about it.  What it CAN fail on
    is a transposed shift, a wrong width, a missing minus_one and a field
    written into the wrong byte.

 3. IT CANNOT SAY THE SHADERS COMPUTE ANYTHING.  Comparing sixty-four
    bits against another assembler says the bits are what both files
    think; it says nothing about what the QPU does with them.

 4. IT CANNOT CATCH A COHERENCY BUG.  Flat dictionary of bytes, no
    caches - the same hole a64_v3d_check.py records.

=====================================================================
 MUTATION
=====================================================================

 --mutate injects single faults into TEMPORARY COPIES of v3d.pi4 and
 v3dqpu.pi4 (the tree is never written), rebuilds the probe against the
 copies and requires every fault to be caught.

 Three faults once survived and all had one shape: the field they
 corrupted is ZERO in this draw.  The answer was an ENCODER CORPUS - a
 second shader state record with a non-zero value in every field, built
 into a page the probe fills with poison and the V3D MMU never maps.

 Deleting V3dShaderRecordBegin()'s zeroing pass kills no test, because
 the five setters between them write all thirty-six bytes as whole
 32-bit words; that fault is deliberately not listed.  Two v3dqpu.pi4
 faults are also not listed here and a64_v3d_qpu_check.py kills both:
 the STVPM waddr override (every STVPM in these shaders is STVPMV,
 whose substituted waddr is zero) and VFPACK's opcode 53 -> 52 (its
 packing rule rewrites the low four bits, so both encode identically).
"""

import argparse
import importlib.util
import os
import pathlib
import re
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "RaspberryPi4" / "Lib" / "v3d.pi4"
QLIB = ROOT / "RaspberryPi4" / "Lib" / "v3dqpu.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dTri.pi4"
LIBS = {
    "v3d": (LIB, 'XIncludeFile "RaspberryPi4/Lib/v3d.pi4"'),
    "v3dqpu": (QLIB, 'XIncludeFile "RaspberryPi4/Lib/v3dqpu.pi4"'),
}


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(HERE))
# The model, the pinned packet layouts and the control-list walker.
R = _load("a64_v3d_rcl_check", HERE / "a64_v3d_rcl_check.py")
# The pinned Mesa QPU tables and py-videocore6's golden bare nop.
Q = _load("a64_v3d_qpu_check", HERE / "a64_v3d_qpu_check.py")
sys.path.insert(0, str(ROOT / "tools"))
import v3d42_qpu_decode as QD  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

# =====================================================================
#  PINNED REFERENCE DATA
#
#  Golden words: py-videocore6 (Idein Inc.), commit
#  175741a389348a739a7d2bf559b9d302d7e390a9, assembler.py - the word its
#  public API produced for the spelling beside it.  A row whose word is
#  None has no py-videocore6 spelling (LDVPMV_IN) and is assembled by
#  expected_shaders() from a64_v3d_qpu_check.py's pinned Mesa tables; the
#  spelling there gives (write address, read address).
#
#  Mesa: tag mesa-24.3.4, commit 769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de.
# =====================================================================
PV6_SHADERS = {
    'coordinate': [
        ('nop(sig=ldunifrf(rf[0]))', 0x3D803186BB800000),
        ('nop(sig=ldunifrf(rf[1]))', 0x3D807186BB800000),
        ('nop(sig=ldunifrf(rf[2]))', 0x3D80B186BB800000),
        ('nop(sig=ldunifrf(rf[3]))', 0x3D80F186BB800000),
        ('nop(sig=ldunifrf(rf[4]))', 0x3D813186BB800000),
        ('nop(sig=ldunifrf(rf[5]))', 0x3D817186BB800000),
        ('ldvpmv_in(rf[8], 0)', None),
        ('ldvpmv_in(rf[9], 1)', None),
        ('ldvpmv_in(rf[10], 2)', None),
        ('ldvpmv_in(rf[11], 3)', None),
        ('ldvpmv_in(rf[12], 4)', None),
        ('ldvpmv_in(rf[13], 5)', None),
        ('stvpmv(rf[0], rf[0], rf[8])', 0x3C002180F883E008),
        ('stvpmv(rf[0], rf[1], rf[9])', 0x3C002180F883E049),
        ('stvpmv(rf[0], rf[2], rf[10])', 0x3C002180F883E08A),
        ('stvpmv(rf[0], rf[3], rf[11])', 0x3C002180F883E0CB),
        ('stvpmv(rf[0], rf[4], rf[12])', 0x3C002180F883E10C),
        ('stvpmv(rf[0], rf[5], rf[13])', 0x3C002180F883E14D),
        ('vpmwt(null)', 0x3C003186BB816000),
        ('nop(sig=thrsw)', 0x3C203186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
    ],
    'vertex': [
        ('nop(sig=ldunifrf(rf[0]))', 0x3D803186BB800000),
        ('nop(sig=ldunifrf(rf[1]))', 0x3D807186BB800000),
        ('nop(sig=ldunifrf(rf[2]))', 0x3D80B186BB800000),
        ('nop(sig=ldunifrf(rf[3]))', 0x3D80F186BB800000),
        ('nop(sig=ldunifrf(rf[4]))', 0x3D813186BB800000),
        ('nop(sig=ldunifrf(rf[5]))', 0x3D817186BB800000),
        ('nop(sig=ldunifrf(rf[6]))', 0x3D81B186BB800000),
        ('nop(sig=ldunifrf(rf[7]))', 0x3D81F186BB800000),
        ('ldvpmv_in(rf[8], 4)', None),
        ('ldvpmv_in(rf[9], 5)', None),
        ('ldvpmv_in(rf[10], 6)', None),
        ('ldvpmv_in(rf[11], 7)', None),
        ('stvpmv(rf[0], rf[0], rf[8])', 0x3C002180F883E008),
        ('stvpmv(rf[0], rf[1], rf[9])', 0x3C002180F883E049),
        ('stvpmv(rf[0], rf[2], rf[10])', 0x3C002180F883E08A),
        ('stvpmv(rf[0], rf[3], rf[11])', 0x3C002180F883E0CB),
        ('vpmwt(null)', 0x3C003186BB816000),
        ('nop(sig=thrsw)', 0x3C203186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
    ],
    'fragment': [
        ('nop(sig=ldunifrf(rf[0]))', 0x3D803186BB800000),
        ('nop(sig=ldunifrf(rf[1]))', 0x3D807186BB800000),
        ('nop(sig=ldunifrf(rf[2]))', 0x3D80B186BB800000),
        ('nop(sig=ldunifrf(rf[3]))', 0x3D80F186BB800000),
        ('nop(sig=thrsw)', 0x3C203186BB800000),
        ('nop(sig=thrsw)', 0x3C203186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('vfpack(tlbu, rf[0], rf[1])', 0x3C0031883583E001),
        ('vfpack(tlb, rf[2], rf[3])', 0x3C0031873583E083),
        ('nop(sig=thrsw)', 0x3C203186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
        ('nop()', 0x3C003186BB800000),
    ],
}

# Every word of the three programs as recorded when the tables were pinned
# (golden and Mesa-assembled alike); check_pins() recomputes and compares.
PINNED_SHADER_WORDS = {
    'coordinate': [
        0x3D803186BB800000, 0x3D807186BB800000, 0x3D80B186BB800000,
        0x3D80F186BB800000, 0x3D813186BB800000, 0x3D817186BB800000,
        0x3C002188BC806000, 0x3C002189BC806040, 0x3C00218ABC806080,
        0x3C00218BBC8060C0, 0x3C00218CBC806100, 0x3C00218DBC806140,
        0x3C002180F883E008, 0x3C002180F883E049, 0x3C002180F883E08A,
        0x3C002180F883E0CB, 0x3C002180F883E10C, 0x3C002180F883E14D,
        0x3C003186BB816000, 0x3C203186BB800000, 0x3C003186BB800000,
        0x3C003186BB800000, 0x3C003186BB800000,
    ],
    'vertex': [
        0x3D803186BB800000, 0x3D807186BB800000, 0x3D80B186BB800000,
        0x3D80F186BB800000, 0x3D813186BB800000, 0x3D817186BB800000,
        0x3D81B186BB800000, 0x3D81F186BB800000, 0x3C002188BC806100,
        0x3C002189BC806140, 0x3C00218ABC806180, 0x3C00218BBC8061C0,
        0x3C002180F883E008, 0x3C002180F883E049, 0x3C002180F883E08A,
        0x3C002180F883E0CB, 0x3C003186BB816000, 0x3C203186BB800000,
        0x3C003186BB800000, 0x3C003186BB800000, 0x3C003186BB800000,
    ],
    'fragment': [
        0x3D803186BB800000, 0x3D807186BB800000, 0x3D80B186BB800000,
        0x3D80F186BB800000, 0x3C203186BB800000, 0x3C203186BB800000,
        0x3C003186BB800000, 0x3C003186BB800000, 0x3C0031883583E001,
        0x3C0031873583E083, 0x3C203186BB800000, 0x3C003186BB800000,
        0x3C003186BB800000, 0x3C003186BB800000,
    ],
}

# The contracts tools/v3d42_qpu_decode.py verifies each program against:
# (program, role, uniform words consumed).  The fragment shader consumes
# FIVE: four LDUNIFRF colour components and the TLB configuration word its
# TLBU write pulls from the stream (Mesa qpu_instr.c:646-658 names TLBU as
# a uniform-loading magic address).  pi4V3dTri.pi4's BuildUniforms() lays
# exactly those five words into #TRI_UNIF_FS.
VERIFY_CONTRACTS = (("coordinate", "coordinate", 6), ("vertex", "vertex", 8),
                    ("fragment", "fragment:flat", 5))

# Mesa's bin-list emission order, the `cl_emit` calls of each function in
# source order with the V3D 7.1 arms removed, in the order v3d_draw_vbo
# calls them and v3d_job_submit caps the list.  The check is SUBSEQUENCE,
# so packets Mesa emits conditionally may be absent.
MESA_DRAW_EMITS = (
    # src/gallium/drivers/v3d/v3dx_draw.c:44, v3dX(start_binning)
    ('v3dX(start_binning)', (
        'NUMBER_OF_LAYERS', 'TILE_BINNING_MODE_CFG', 'FLUSH_VCD_CACHE',
        'OCCLUSION_QUERY_COUNTER', 'START_TILE_BINNING',
    )),
    # src/gallium/drivers/v3d/v3dx_emit.c:220, v3dX(emit_state)
    ('v3dX(emit_state)', (
        'CLIP_WINDOW', 'CFG_BITS', 'POINT_SIZE',
        'LINE_WIDTH', 'CLIPPER_XY_SCALING', 'CLIPPER_Z_SCALE_AND_OFFSET',
        'CLIPPER_Z_MIN_MAX_CLIPPING_PLANES', 'VIEWPORT_OFFSET', 'BLEND_ENABLES',
        'COLOR_WRITE_MASKS', 'BLEND_CONSTANT_COLOR', 'ZERO_ALL_FLAT_SHADE_FLAGS',
        'ZERO_ALL_NON_PERSPECTIVE_FLAGS', 'ZERO_ALL_CENTROID_FLAGS', 'TRANSFORM_FEEDBACK_SPECS',
        'TRANSFORM_FEEDBACK_SPECS', 'TRANSFORM_FEEDBACK_BUFFER', 'OCCLUSION_QUERY_COUNTER',
        'SAMPLE_STATE',
    )),
    # src/gallium/drivers/v3d/v3dx_draw.c:709, v3d_emit_gl_shader_state
    ('v3d_emit_gl_shader_state', (
        'GL_SHADER_STATE_ATTRIBUTE_RECORD', 'VCM_CACHE_SIZE', 'GL_SHADER_STATE_INCLUDING_GS',
        'GL_SHADER_STATE',
    )),
    # src/gallium/drivers/v3d/v3dx_draw.c, v3d_draw_vbo
    ('v3d_draw_vbo', (
        'BASE_VERTEX_BASE_INSTANCE', 'INDEX_BUFFER_SETUP', 'INDIRECT_INDEXED_INSTANCED_PRIM_LIST',
        'INDEXED_INSTANCED_PRIM_LIST', 'INDEXED_PRIM_LIST', 'INDIRECT_VERTEX_ARRAY_INSTANCED_PRIMS',
        'VERTEX_ARRAY_INSTANCED_PRIMS', 'VERTEX_ARRAY_PRIMS', 'TRANSFORM_FEEDBACK_FLUSH_AND_COUNT',
    )),
    # src/gallium/drivers/v3d/v3dx_job.c:33, v3dX(bcl_epilogue)
    ('v3dX(bcl_epilogue)', (
        'PRIMITIVE_COUNTS_FEEDBACK', 'TRANSFORM_FEEDBACK_SPECS', 'FLUSH',
    )),
)

# The XML's packet names in the spelling Mesa's cl_emit() uses, for the
# packets this draw emits.  A packet with no entry is a failure, not a skip.
MESA_SPELLING = {
    "Number of Layers": "NUMBER_OF_LAYERS",
    "Tile Binning Mode Cfg": "TILE_BINNING_MODE_CFG",
    "Flush VCD cache": "FLUSH_VCD_CACHE",
    "Occlusion Query Counter": "OCCLUSION_QUERY_COUNTER",
    "Start Tile Binning": "START_TILE_BINNING",
    "clip_window": "CLIP_WINDOW",
    "Cfg Bits": "CFG_BITS",
    "Point size": "POINT_SIZE",
    "Line width": "LINE_WIDTH",
    "Clipper XY Scaling": "CLIPPER_XY_SCALING",
    "Clipper Z Scale and Offset": "CLIPPER_Z_SCALE_AND_OFFSET",
    "Clipper Z min/max clipping planes": "CLIPPER_Z_MIN_MAX_CLIPPING_PLANES",
    "Viewport Offset": "VIEWPORT_OFFSET",
    "Color Write Masks": "COLOR_WRITE_MASKS",
    "Zero All Flat Shade Flags": "ZERO_ALL_FLAT_SHADE_FLAGS",
    "Zero All Non-perspective Flags": "ZERO_ALL_NON_PERSPECTIVE_FLAGS",
    "Zero All Centroid Flags": "ZERO_ALL_CENTROID_FLAGS",
    "Sample State": "SAMPLE_STATE",
    "VCM Cache Size": "VCM_CACHE_SIZE",
    "GL Shader State": "GL_SHADER_STATE",
    "Vertex Array Prims": "VERTEX_ARRAY_PRIMS",
    "Flush": "FLUSH",
}

# Enumeration values, src/broadcom/cle/v3d_packet.xml.
ENUMS_TRI = {
    "Compare Function": {"ALWAYS": 7},   # v3d_packet.xml:3
    "Primitive": {"TRIANGLES": 4},       # v3d_packet.xml:55
}
# The attribute record's Type field carries its values inline,
# v3d_packet.xml:1380.
ATTRIBUTE_TYPE = {
    'Attribute short': 5,
    'Attribute byte': 4,
    'Attribute float': 2,
    'Attribute int': 6,
}

# Draw packets a64_v3d_rcl_check.py may not pin, with their 4.2 layout from
# v3d_packet.xml: (code, name, xml line, length, fields).  Used only when
# the rcl gate's table lacks the name.
EXTRA_PACKETS_42 = (
    (100, 'Non-perspective Flags', 780, 5, (
        ('Non-perspective Flags for varyings V0*24', 8, 24, False, None, False),
        ('Action for Non-perspective Flags of higher numbered varyings', 6, 2, False, None, False),
        ('Action for Non-perspective Flags of lower numbered varyings', 4, 2, False, None, False),
        ('Varying offset V0', 0, 4, False, None, False),
    )),
)

# Set only by mutate(): {"v3d" or "v3dqpu": the text of the mutated copy}.
_OVERRIDE: dict = {}


def _text(p: pathlib.Path) -> str:
    if not p.exists():
        raise SystemExit("a64_v3d_tri_check: the source file %s is missing." % p)
    return p.read_text(encoding="utf-8", errors="replace")


def _constant(src: str, name: str, where: str) -> int:
    m = re.search(r"^#%s\s*=\s*([^\s;]+)" % re.escape(name), src, re.M)
    if not m:
        raise SystemExit("a64_v3d_tri_check: %s has no #%s constant." % (where, name))
    tok = m.group(1)
    return int(tok[1:], 16) if tok.startswith("$") else int(tok, 10)


def probe_constant(name: str) -> int:
    return _constant(_text(PROBE), name, "pi4V3dTri.pi4")


def lib_constant(name: str) -> int:
    return _constant(_OVERRIDE.get("v3d") or _text(LIB), name, "v3d.pi4")


def build(compiler: str, workdir: pathlib.Path, name: str) -> pathlib.Path:
    """Compile the probe; with _OVERRIDE set, against temporary library copies."""
    src = PROBE
    if _OVERRIDE:
        probe_text = _text(PROBE)
        for key, lib_text in _OVERRIDE.items():
            path, include = LIBS[key]
            if include not in probe_text:
                raise SystemExit("a64_v3d_tri_check: pi4V3dTri.pi4 no longer has the "
                                 "line %s, so a mutant library cannot be substituted."
                                 % include)
            copy = workdir / ("mutant_" + path.name)
            copy.write_text(lib_text, encoding="utf-8")
            probe_text = probe_text.replace(include, 'XIncludeFile "%s"' % copy.as_posix())
        src = workdir / ("mutant_" + PROBE.name)
        src.write_text(probe_text, encoding="utf-8")
    img = workdir / name
    if img.exists():
        img.unlink()
    return R.compile_probe(compiler, src, img)


# =====================================================================
#  READING A STRUCT OUT OF THE PROBE'S MEMORY
#
#  A <struct> has no opcode byte and Packet.decode() assumes one, so the
#  struct path is written out separately rather than reusing a function
#  whose contract is different.
# =====================================================================
def decode_struct(p, data: bytes) -> dict:
    payload = 0
    for i in range(p.length):
        payload |= data[i] << (8 * i)
    return {f.name: f.get(payload) for f in p.fields}


def grab(cpu, lo: int, n: int) -> bytes:
    return bytes(cpu.memory.get(lo + i, 0) for i in range(n))


def enum_value(enum_name: str, value_name: str) -> int:
    try:
        return ENUMS_TRI[enum_name][value_name]
    except KeyError:
        raise SystemExit("a64_v3d_tri_check: %r in enum %r is not pinned."
                         % (value_name, enum_name)) from None


def derive_bcl_order() -> list:
    out = []
    for _function, names in MESA_DRAW_EMITS:
        out += names
    return out


def by_code_with_extras() -> dict:
    by_code = R.parse_packets()
    known = {p.name for plist in by_code.values() for p in plist}
    for code, name, _line, length, fields in EXTRA_PACKETS_42:
        if name in known:
            continue
        p = R.Packet(code, name, fields)
        if p.length != length:
            raise SystemExit("a64_v3d_tri_check: the pinned %r layout gives %d bytes "
                             "and its pinned length is %d." % (name, p.length, length))
        by_code.setdefault(code, []).append(p)
    return by_code


# =====================================================================
#  THE THREE SHADERS
# =====================================================================
def expected_shaders() -> dict:
    """{name: [(word, witnessed)]}: golden words where py-videocore6 has an
    opinion, LDVPMV_IN assembled from the pinned Mesa tables where not."""
    shifts = Q.derive_field_shifts()
    opcodes = Q.derive_opcode_table("add")
    muxes = Q.derive_mux_firsts("add")
    nsrcs = Q.derive_add_num_src()
    _stvpm, _nomagic, out_ma = Q.derive_vpm_rules()
    nopword = Q.PV6_CORPUS[0][1]

    def field_mask(name):
        _s, hi, lo = shifts[name]
        return ((1 << (hi - lo + 1)) - 1) << lo

    addmask = 0
    for f in ("OP_ADD", "ADD_A", "ADD_B", "WADDR_A", "MA", "RADDR_A", "RADDR_B"):
        addmask |= field_mask(f)
    base = nopword & ~addmask & 0xFFFFFFFFFFFFFFFF

    def sh(n):
        return shifts[n][0]

    def ldvpmv_in(waddr, raddr_a):
        op = "LDVPMV_IN"
        mux_b = muxes[op][1] if nsrcs[op] < 2 else 0
        w = base
        w |= opcodes[op] << sh("OP_ADD")
        w |= 6 << sh("ADD_A")           # mux 6 reads RADDR_A
        w |= mux_b << sh("ADD_B")
        w |= waddr << sh("WADDR_A")
        w |= raddr_a << sh("RADDR_A")
        if op in out_ma:
            w |= 1 << sh("MA")
        return w

    out = {}
    for name, rows in PV6_SHADERS.items():
        prog = []
        for spelling, word in rows:
            if word is None:
                m = re.fullmatch(r"ldvpmv_in\(rf\[(\d+)\], (\d+)\)", spelling)
                prog.append((ldvpmv_in(int(m.group(1)), int(m.group(2))), False))
            else:
                prog.append((word, True))
        out[name] = prog
    return out


# =====================================================================
#  THE CHECKS
# =====================================================================
def check(fails: list, counts: dict, compiler: str, workdir: pathlib.Path) -> None:
    by_code = by_code_with_extras()

    img = build(compiler, workdir, "v3dtri.img")
    m = R.Model()
    cpu, out = R.run(img, m)

    # -----------------------------------------------------------------
    #  0. THE MODEL'S OWN BLINDNESS, ASSERTED BEFORE ANYTHING ELSE.
    # -----------------------------------------------------------------
    print("  0  the model's own blindness")
    tri = re.search(r"pixels triangle colour\s+(\d+)", out)
    poison = re.search(r"pixels still poison\s+(\d+)", out)
    if not tri or not poison:
        fails.append("The probe never reached its pixel count under the model, so "
                     "it did not get through Main().")
        print(out[-3000:])
        return
    R.row("triangle pixels under the model", 0, int(tri.group(1)), fails)
    R.row("pixels still poison", 4096, int(poison.group(1)), fails)
    if "verdict: NO TRIANGLE" not in out:
        fails.append("The probe did not say NO TRIANGLE under a model that cannot "
                     "render.  Either the model grew a rasteriser or the verdict is "
                     "not reading the pixels.")

    # -----------------------------------------------------------------
    #  1. THE THREE SHADERS, INSTRUCTION BY INSTRUCTION.
    # -----------------------------------------------------------------
    print("  1  the three QPU programs")
    want = expected_shaders()
    got = {}
    for name in ("coordinate", "vertex", "fragment"):
        mm = re.search(r"%s shader: OK" % name, out)
        if not mm:
            fails.append("The probe did not build the %s shader." % name)
            continue
        block = out[mm.end():]
        rows = re.findall(r"^  Q (\d+) ([0-9A-F]{8}) ([0-9A-F]{8})\s*$", block, re.M)
        prog = []
        for idx, hi, lo in rows:
            if int(idx) != len(prog):
                break
            prog.append((int(hi, 16) << 32) | int(lo, 16))
        got[name] = prog

    for name in ("coordinate", "vertex", "fragment"):
        if name not in got:
            continue
        w = want[name]
        g = got[name]
        if len(g) != len(w):
            fails.append("The %s shader is %d instructions and the expected program "
                         "is %d." % (name, len(g), len(w)))
            continue
        bad = 0
        for i, (word, witnessed) in enumerate(w):
            if g[i] != word:
                bad += 1
                fails.append(
                    "%s shader instruction %d: v3dqpu.pi4 says %016X and %s says "
                    "%016X (they differ in %016X)."
                    % (name, i, g[i],
                       "py-videocore6's golden word" if witnessed
                       else "the pinned Mesa tables", word, g[i] ^ word))
            elif witnessed:
                counts["oracle"] += 1
            else:
                counts["model"] += 1
        print("     %-11s %2d instructions, %d witnessed, %d modelled%s"
              % (name, len(g), sum(1 for _, wt in w if wt),
                 sum(1 for _, wt in w if not wt),
                 "" if bad == 0 else "  %d WRONG" % bad))

    # -----------------------------------------------------------------
    #  1b. THE ANVIL DECODER'S STRAIGHT-LINE VERIFIER.
    # -----------------------------------------------------------------
    print("  1b the three programs under tools/v3d42_qpu_decode.py")
    for name, role, uniforms in VERIFY_CONTRACTS:
        if name not in got:
            continue
        try:
            QD.verify_program(got[name], QD.ProgramContract(name, role, uniforms))
        except (QD.DecodeError, QD.VerifyError) as e:
            fails.append("The %s shader fails the Anvil decoder's %s contract: %s"
                         % (name, role, e))
            continue
        counts["verified"] += 1
        print("     %-11s verified as %s, %d uniform words" % (name, role, uniforms))

    # -----------------------------------------------------------------
    #  2. THE SHADER STATE RECORD, decoded with the pinned XML layout.
    # -----------------------------------------------------------------
    print("  2  the GL Shader State Record")
    srec = R.parse_struct("GL Shader State Record")
    if srec is None:
        fails.append("a64_v3d_rcl_check.py pins no GL Shader State Record layout.")
        return
    R.row("record length, bytes", srec.length, lib_constant("V3D_SHREC_BYTES"), fails)

    at = probe_constant("TRI_SHREC")
    f = decode_struct(srec, grab(cpu, at, srec.length))

    code_cs = probe_constant("TRI_CODE_CS")
    code_vs = probe_constant("TRI_CODE_VS")
    code_fs = probe_constant("TRI_CODE_FS")
    unif_cs = probe_constant("TRI_UNIF_CS")
    unif_vs = probe_constant("TRI_UNIF_VS")
    unif_fs = probe_constant("TRI_UNIF_FS")
    defaults = probe_constant("TRI_DEFAULTS")

    R.row("enable clipping", 1, f.get("Enable clipping"), fails)
    R.row("point size in shaded vertex data", 0,
          f.get("Point size in shaded vertex data"), fails)
    R.row("fragment shader does Z writes", 0,
          f.get("Fragment shader does Z writes"), fails)
    R.row("turn off early-z test", 0, f.get("Turn off early-z test"), fails)
    R.row("do scoreboard wait on first thread switch", 0,
          f.get("Do scoreboard wait on first thread switch"), fails)
    R.row("disable implicit point/line varyings", 1,
          f.get("Disable implicit point/line varyings"), fails)
    R.row("number of varyings in fragment shader", 0,
          f.get("Number of varyings in Fragment Shader"), fails)
    R.row("coord shader separate VPM blocks", 0,
          f.get("Coordinate shader has separate input and output VPM blocks"), fails)
    R.row("vertex shader separate VPM blocks", 0,
          f.get("Vertex shader has separate input and output VPM blocks"), fails)
    R.row("coord shader output VPM segment size", 1,
          f.get("Coordinate Shader output VPM segment size"), fails)
    R.row("coord shader input VPM segment size", 1,
          f.get("Coordinate Shader input VPM segment size"), fails)
    R.row("vertex shader output VPM segment size", 1,
          f.get("Vertex Shader output VPM segment size"), fails)
    R.row("vertex shader input VPM segment size", 1,
          f.get("Vertex Shader input VPM segment size"), fails)
    # Ve is zero and As is one, and As's field carries minus_one, so the
    # decoder adds the one back.  A library that forgot the minus_one would
    # decode as two here.
    R.row("min coord output segments (Ve)", 0,
          f.get("Min Coord Shader output segments required in play in "
                "addition to VCM cache size"), fails)
    R.row("min vertex output segments (Ve)", 0,
          f.get("Min Vertex Shader output segments required in play in "
                "addition to VCM cache size"), fails)
    R.row("min coord input segments (As)", 1,
          f.get("Min Coord Shader input segments required in play"), fails)
    R.row("min vertex input segments (As)", 1,
          f.get("Min Vertex Shader input segments required in play"), fails)
    R.row("address of default attribute values", defaults,
          f.get("Address of default attribute values"), fails)
    R.row("fragment shader code address", code_fs,
          f.get("Fragment Shader Code Address"), fails)
    R.row("vertex shader code address", code_vs,
          f.get("Vertex Shader Code Address"), fails)
    R.row("coordinate shader code address", code_cs,
          f.get("Coordinate Shader Code Address"), fails)
    R.row("fragment shader uniforms address", unif_fs,
          f.get("Fragment Shader Uniforms Address"), fails)
    R.row("vertex shader uniforms address", unif_vs,
          f.get("Vertex Shader Uniforms Address"), fails)
    R.row("coordinate shader uniforms address", unif_cs,
          f.get("Coordinate Shader Uniforms Address"), fails)
    R.row("fragment shader 4-way threadable", 1,
          f.get("Fragment Shader 4-way threadable"), fails)
    R.row("vertex shader 4-way threadable", 1,
          f.get("Vertex Shader 4-way threadable"), fails)
    R.row("coordinate shader 4-way threadable", 1,
          f.get("Coordinate Shader 4-way threadable"), fails)
    # The three final-thread-section bits are not all the same, and that is
    # the point: the vertex and coordinate shaders have no thread switch of
    # their own; the fragment shader's TLB writes must follow a real
    # last-THRSW.
    R.row("fragment shader start in final thread section", 0,
          f.get("Fragment Shader start in final thread section"), fails)
    R.row("vertex shader start in final thread section", 1,
          f.get("Vertex Shader start in final thread section"), fails)
    R.row("coordinate shader start in final thread section", 1,
          f.get("Coordinate Shader start in final thread section"), fails)
    R.row("fragment shader propagate NaNs", 1,
          f.get("Fragment Shader Propagate NaNs"), fails)
    R.row("vertex shader propagate NaNs", 1,
          f.get("Vertex Shader Propagate NaNs"), fails)
    R.row("coordinate shader propagate NaNs", 1,
          f.get("Coordinate Shader Propagate NaNs"), fails)

    for name in ("Vertex ID read by coordinate shader",
                 "Instance ID read by coordinate shader",
                 "Base Instance ID read by coordinate shader",
                 "Vertex ID read by vertex shader",
                 "Instance ID read by vertex shader",
                 "Base Instance ID read by vertex shader",
                 "Fragment shader uses real pixel centre W in addition to centroid W2",
                 "Enable Sample Rate Shading",
                 "Any shader reads hardware-written Primitive ID",
                 "Insert Primitive ID as first varying to fragment shader",
                 "Turn off scoreboard",
                 "No prim pack"):
        if name not in f:
            fails.append("The pinned GL Shader State Record has no field %r, so this "
                         "gate's zero list has rotted." % name)
            continue
        R.row("zero: %s" % name, 0, f[name], fails)

    # -----------------------------------------------------------------
    #  2b. THE ENCODER CORPUS RECORD - a second record over a poisoned page
    #  with a non-zero value in every field.
    # -----------------------------------------------------------------
    print("  2b the encoder corpus record")
    cat = probe_constant("TRI_CORPUS")
    c = decode_struct(srec, grab(cpu, cat, srec.length))
    for label, wantv in (
            ("Point size in shaded vertex data", 0),
            ("Enable clipping", 1),
            ("Fragment shader does Z writes", 1),
            ("Turn off early-z test", 1),
            ("Do scoreboard wait on first thread switch", 1),
            ("Disable implicit point/line varyings", 1),
            ("Number of varyings in Fragment Shader", 0xAD),
            ("Coordinate Shader output VPM segment size", 3),
            ("Min Coord Shader output segments required in play in "
             "addition to VCM cache size", 5),
            ("Coordinate Shader input VPM segment size", 7),
            ("Min Coord Shader input segments required in play", 9),
            ("Vertex Shader output VPM segment size", 11),
            ("Min Vertex Shader output segments required in play in "
             "addition to VCM cache size", 13),
            ("Vertex Shader input VPM segment size", 15),
            ("Min Vertex Shader input segments required in play", 16),
            ("Address of default attribute values", 0x12345678),
            ("Fragment Shader Code Address", 0x0ABCDEF8),
            ("Fragment Shader 4-way threadable", 1),
            ("Fragment Shader start in final thread section", 0),
            ("Fragment Shader Propagate NaNs", 1),
            ("Fragment Shader Uniforms Address", 0x13579BDC),
            ("Vertex Shader Code Address", 0x01234568),
            ("Vertex Shader 4-way threadable", 0),
            ("Vertex Shader start in final thread section", 1),
            ("Vertex Shader Propagate NaNs", 0),
            ("Vertex Shader Uniforms Address", 0x2468ACE0),
            ("Coordinate Shader Code Address", 0x0FEDCBA8),
            ("Coordinate Shader 4-way threadable", 1),
            ("Coordinate Shader start in final thread section", 1),
            ("Coordinate Shader Propagate NaNs", 0),
            ("Coordinate Shader Uniforms Address", 0x3141592C)):
        if label not in c:
            fails.append("The corpus record has no field %r." % label)
            continue
        R.row("corpus %s" % label, wantv, c[label], fails)
    for name in ("Vertex ID read by coordinate shader",
                 "Instance ID read by coordinate shader",
                 "Enable Sample Rate Shading",
                 "Turn off scoreboard",
                 "No prim pack"):
        R.row("corpus zero: %s" % name, 0, c.get(name), fails)

    arec0 = R.parse_struct("GL Shader State Attribute Record")
    if arec0 is None:
        fails.append("a64_v3d_rcl_check.py pins no GL Shader State Attribute Record.")
        return
    ca0 = decode_struct(arec0, grab(cpu, cat + srec.length, arec0.length))
    ca1 = decode_struct(arec0, grab(cpu, cat + srec.length + arec0.length,
                                    arec0.length))
    for tag, a, wantd in (
            ("0", ca0, {"Address": 0xABCDEF00, "Stride": 0x00010203,
                        "Maximum Index": 0x04050607,
                        "Number of values read by Coordinate shader": 13,
                        "Number of values read by Vertex shader": 7,
                        "Vec size": 2,
                        "Type": ATTRIBUTE_TYPE["Attribute short"],
                        "Signed int type": 1, "Normalized int type": 1,
                        "Read as int/uint": 0, "Instance Divisor": 0xBEEF}),
            ("1", ca1, {"Address": 0x76543210, "Stride": 0x0A0B0C0D,
                        "Maximum Index": 0x0E0F1011,
                        "Number of values read by Coordinate shader": 5,
                        "Number of values read by Vertex shader": 12,
                        "Vec size": 3,
                        "Type": ATTRIBUTE_TYPE["Attribute byte"],
                        "Signed int type": 0, "Normalized int type": 1,
                        "Read as int/uint": 1, "Instance Divisor": 0x1234})):
        for k, v in wantd.items():
            R.row("corpus attr %s %s" % (tag, k), v, a.get(k), fails)

    # -----------------------------------------------------------------
    #  3. THE EIGHT ATTRIBUTE RECORDS.
    # -----------------------------------------------------------------
    print("  3  the eight attribute records")
    arec = arec0
    R.row("attribute record length, bytes", arec.length,
          lib_constant("V3D_ATTR_BYTES"), fails)
    verts = probe_constant("TRI_VERTS")
    attr_float = ATTRIBUTE_TYPE["Attribute float"]
    attr_int = ATTRIBUTE_TYPE["Attribute int"]
    for k in range(8):
        a = decode_struct(arec, grab(cpu, at + srec.length + k * arec.length,
                                     arec.length))
        R.row("attr %d address" % k, verts + 4 * k, a.get("Address"), fails)
        R.row("attr %d stride" % k, 32, a.get("Stride"), fails)
        R.row("attr %d maximum index" % k, 0xFFFFFF, a.get("Maximum Index"), fails)
        R.row("attr %d instance divisor" % k, 0, a.get("Instance Divisor"), fails)
        R.row("attr %d vec size" % k, 1, a.get("Vec size"), fails)
        R.row("attr %d values read by vertex shader" % k, 1,
              a.get("Number of values read by Vertex shader"), fails)
        # Records 6 and 7 are Zs and 1/Wc, which only the vertex shader reads.
        R.row("attr %d values read by coordinate shader" % k, 1 if k < 6 else 0,
              a.get("Number of values read by Coordinate shader"), fails)
        # Slots 4 and 5 are the screen coordinates, signed integers.
        if k in (4, 5):
            R.row("attr %d type" % k, attr_int, a.get("Type"), fails)
            R.row("attr %d read as int" % k, 1, a.get("Read as int/uint"), fails)
            R.row("attr %d signed" % k, 1, a.get("Signed int type"), fails)
        else:
            R.row("attr %d type" % k, attr_float, a.get("Type"), fails)
            R.row("attr %d read as int" % k, 0, a.get("Read as int/uint"), fails)
        R.row("attr %d normalized" % k, 0, a.get("Normalized int type"), fails)

    # -----------------------------------------------------------------
    #  4. THE VERTEX DATA, against arithmetic done here from the probe's
    #  own constants.  Both sides use the same reading of Mesa's
    #  v3d_nir_lower_io.c, so only the board can say the transform is right.
    # -----------------------------------------------------------------
    print("  4  the three shaded vertices")
    cx = probe_constant("TRI_CX")
    cy = probe_constant("TRI_CY")
    one = probe_constant("TRI_F_ONE")
    zero = probe_constant("TRI_F_ZERO")
    pts = [(probe_constant("TRI_V0X"), probe_constant("TRI_V0Y")),
           (probe_constant("TRI_V1X"), probe_constant("TRI_V1Y")),
           (probe_constant("TRI_V2X"), probe_constant("TRI_V2Y"))]
    for n, (px, py) in enumerate(pts):
        w = [int.from_bytes(grab(cpu, verts + n * 32 + i * 4, 4), "little")
             for i in range(8)]
        xc = struct.unpack("<f", struct.pack("<I", w[0]))[0]
        yc = struct.unpack("<f", struct.pack("<I", w[1]))[0]
        R.row("v%d Xc" % n, (px - cx) / float(cx), xc, fails)
        R.row("v%d Yc" % n, (py - cy) / float(cy), yc, fails)
        R.row("v%d Zc" % n, zero, w[2], fails)
        R.row("v%d Wc" % n, one, w[3], fails)
        R.row("v%d Xs" % n, ((px - cx) * 256) & 0xFFFFFFFF, w[4], fails)
        R.row("v%d Ys" % n, ((py - cy) * 256) & 0xFFFFFFFF, w[5], fails)
        R.row("v%d Zs" % n, zero, w[6], fails)
        R.row("v%d 1/Wc" % n, one, w[7], fails)

    # -----------------------------------------------------------------
    #  5. THE BIN LIST - the walk, the order, and the field values.
    # -----------------------------------------------------------------
    print("  5  the bin control list")
    mm = re.search(r"^\s+bin list bytes\s+(\d+)", out, re.M)
    if not mm:
        fails.append("The probe never printed the bin list length.")
        return
    blen = int(mm.group(1))
    bcl_at = probe_constant("TRI_BCL")
    bcl = R.decode_list(by_code, grab(cpu, bcl_at, blen))
    print("     %d packets, %d bytes, the walk ended exactly on the last byte"
          % (len(bcl), blen))

    names = []
    for n, _, _ in bcl:
        if n not in MESA_SPELLING:
            fails.append("No Mesa spelling is known for packet %r in the bin list, "
                         "so this gate's map has rotted." % n)
            names = None
            break
        names.append(MESA_SPELLING[n])
    if names is not None:
        want_order = derive_bcl_order()
        ok, missing = R.is_subsequence(names, want_order)
        print("     order: %d packets against Mesa's %d  %s"
              % (len(names), len(want_order),
                 "ok" if ok else "OUT OF ORDER at %s" % missing))
        if not ok:
            fails.append("The bin list is not a subsequence of Mesa's own emission "
                         "order; %s is out of place.\n      library: %s\n      "
                         "mesa:    %s" % (missing, names, want_order))

    def one_pkt(name):
        hits = [ff for nn, ff, _ in bcl if nn == name]
        if len(hits) != 1:
            fails.append("The bin list has %d %s packets and should have one."
                         % (len(hits), name))
            return {}
        return hits[0]

    w = probe_constant("TRI_W")
    h = probe_constant("TRI_H")
    cw = one_pkt("clip_window")
    R.row("clip window left", 0, cw.get("Clip Window Left Pixel Coordinate"), fails)
    R.row("clip window bottom", 0, cw.get("Clip Window Bottom Pixel Coordinate"), fails)
    R.row("clip window width", w, cw.get("Clip Window Width in pixels"), fails)
    R.row("clip window height", h, cw.get("Clip Window Height in pixels"), fails)

    cb = one_pkt("Cfg Bits")
    R.row("enable forward facing primitive", 1,
          cb.get("Enable Forward Facing Primitive"), fails)
    R.row("enable reverse facing primitive", 1,
          cb.get("Enable Reverse Facing Primitive"), fails)
    R.row("depth-test function", enum_value("Compare Function", "ALWAYS"),
          cb.get("Depth-Test Function"), fails)
    R.row("blend enable", 0, cb.get("Blend enable"), fails)
    R.row("early z enable", 0, cb.get("Early Z enable"), fails)
    R.row("stencil enable", 0, cb.get("Stencil enable"), fails)

    # The clipper's half-width is in 1/256ths of a pixel and the viewport
    # offset's Fine X is u14.8, also 1/256ths.  If they ever disagree a
    # clipped vertex lands somewhere a shaded one does not.
    quarter = (w // 2) * 256
    cs_pkt = one_pkt("Clipper XY Scaling")
    hw = struct.unpack("<f", struct.pack(
        "<I", cs_pkt.get("Viewport Half-Width in 1/256th of pixel", 0)))[0]
    hh = struct.unpack("<f", struct.pack(
        "<I", cs_pkt.get("Viewport Half-Height in 1/256th of pixel", 0)))[0]
    R.row("clipper half-width, 1/256 px", float(quarter), hw, fails)
    R.row("clipper half-height, 1/256 px", float((h // 2) * 256), hh, fails)

    vo = one_pkt("Viewport Offset")
    R.row("viewport fine x, 1/256 px", quarter, vo.get("Fine X"), fails)
    R.row("viewport fine y, 1/256 px", (h // 2) * 256, vo.get("Fine Y"), fails)
    R.row("viewport coarse x", 0, vo.get("Coarse X"), fails)
    R.row("viewport coarse y", 0, vo.get("Coarse Y"), fails)

    R.row("colour write mask", 0, one_pkt("Color Write Masks").get("Mask"), fails)

    ss = one_pkt("Sample State")
    R.row("sample mask", 0xF, ss.get("Mask"), fails)

    vcm = one_pkt("VCM Cache Size")
    R.row("vcm batches for binning", 4,
          vcm.get("Number of 16-vertex batches for binning"), fails)
    R.row("vcm batches for rendering", 4,
          vcm.get("Number of 16-vertex batches for rendering"), fails)

    gs = one_pkt("GL Shader State")
    R.row("shader state record address", at, gs.get("address"), fails)
    R.row("number of attribute arrays", 8, gs.get("number of attribute arrays"), fails)

    vp = one_pkt("Vertex Array Prims")
    R.row("primitive mode", enum_value("Primitive", "TRIANGLES"), vp.get("mode"), fails)
    R.row("primitive length", 3, vp.get("Length"), fails)
    R.row("index of first vertex", 0, vp.get("Index of First Vertex"), fails)


def check_pins(fails: list) -> None:
    """The pinned tables must agree with themselves and with what they share."""
    for name, rows in PV6_SHADERS.items():
        want = PINNED_SHADER_WORDS[name]
        got = [w for w, _ in expected_shaders()[name]]
        if got != want:
            fails.append("The %s shader assembled from the pinned tables does not "
                         "match the words recorded when they were pinned." % name)
    r_prim = R.ENUMS_42.get("Primitive", {}).get("TRIANGLES")
    if r_prim is not None and r_prim != ENUMS_TRI["Primitive"]["TRIANGLES"]:
        fails.append("a64_v3d_rcl_check.py pins Primitive TRIANGLES as %d and this "
                     "gate pins %d." % (r_prim, ENUMS_TRI["Primitive"]["TRIANGLES"]))


# =====================================================================
#  MUTATION - one fault per temporary library copy.
# =====================================================================
MUTANTS = [
    # ---- the shader state record ------------------------------------
    ("shrec-length", "v3d", "#V3D_SHREC_BYTES = 36", "#V3D_SHREC_BYTES = 40"),
    ("shrec-clip-bit", "v3d", "    v = v | 2                      ; bit 1",
     "    v = v | 4                      ; bit 1"),
    ("shrec-varyings-shift", "v3d",
     "  v = v | ((numVaryingsFs & $FF) << 24)",
     "  v = v | ((numVaryingsFs & $FF) << 23)"),
    ("shrec-as-minus-one", "v3d", "  v = v | (((csAs - 1) & $F) << 12)",
     "  v = v | ((csAs & $F) << 12)"),
    ("shrec-vs-out-shift", "v3d", "  v = v | ((vsOutSeg & $F) << 16)",
     "  v = v | ((vsOutSeg & $F) << 20)"),
    ("shrec-code-flags", "v3d", "  If finalSeg <> 0\n    v = v | 2",
     "  If finalSeg <> 0\n    v = v | 1"),
    ("shrec-code-mask", "v3d", "  v = addr & $FFFFFFF8", "  v = addr & $FFFFFFF0"),
    ("shrec-vs-offset", "v3d",
     "  v3d_ShrecCode(20, codeAddr, fourWay, finalSeg, propagateNans)",
     "  v3d_ShrecCode(24, codeAddr, fourWay, finalSeg, propagateNans)"),
    # ---- the attribute records --------------------------------------
    ("attr-length", "v3d", "#V3D_ATTR_BYTES  = 16", "#V3D_ATTR_BYTES  = 20"),
    ("attr-type-shift", "v3d", "  v = v | ((type & 7) << 2)",
     "  v = v | ((type & 7) << 3)"),
    ("attr-readasint-bit", "v3d", "  If readAsInt <> 0\n    v = v | 128",
     "  If readAsInt <> 0\n    v = v | 64"),
    ("attr-counts-swapped", "v3d",
     "  PokeA(base + 5, (csValues & $F) | ((vsValues & $F) << 4))",
     "  PokeA(base + 5, (vsValues & $F) | ((csValues & $F) << 4))"),
    ("attr-stride-offset", "v3d", "  PokeA(base + 8,  stride & $FF)",
     "  PokeA(base + 7,  stride & $FF)"),
    # ---- the new packet ---------------------------------------------
    ("cwm-opcode", "v3d", "#V3D_PKT_COLOR_WRITE_MASKS     = 87",
     "#V3D_PKT_COLOR_WRITE_MASKS     = 86"),
    # ---- the QPU side the shaders depend on -------------------------
    ("ldvpm-muxb", "v3dqpu",
     "    Case #V3DQ_A_LDVPMV_IN\n      ProcedureReturn 0   ; :520 b_mask OP_MASK(0)",
     "    Case #V3DQ_A_LDVPMV_IN\n      ProcedureReturn 3   ; :520 b_mask OP_MASK(0)"),
]


def mutate(compiler: str, workdir: pathlib.Path, only=None) -> int:
    survivors = []
    killed = 0
    tried = 0
    originals = {key: _text(path).replace("\r\n", "\n") for key, (path, _i) in LIBS.items()}
    for name, key, old, new in MUTANTS:
        if only and name not in only:
            continue
        tried += 1
        backup = originals[key]
        if old not in backup:
            print("  %-20s NOT APPLIED - the text this fault edits is gone.  The "
                  "mutant list has rotted and this is a hole." % name)
            survivors.append(name + " (not applied)")
            continue
        _OVERRIDE.clear()
        _OVERRIDE[key] = backup.replace(old, new, 1)
        fails: list = []
        counts = {"oracle": 0, "model": 0, "verified": 0}
        try:
            check(fails, counts, compiler, workdir)
        except SystemExit as e:
            fails = ["build or run refused: %s" % str(e)[:120]]
        finally:
            _OVERRIDE.clear()
        if fails:
            killed += 1
            print("  %-20s killed   (%s)" % (name, fails[0][:90]))
        else:
            survivors.append(name)
            print("  %-20s SURVIVED - the gate cannot see this fault" % name)
    print()
    print("  %d of %d faults killed" % (killed, tried))
    if survivors:
        print("  survivors: %s" % ", ".join(survivors))
    return 0 if not survivors else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Executable gate for the V3D stage 4 draw.")
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler executable")
    ap.add_argument("--mutate", action="store_true",
                    help="inject faults into temporary copies of v3d.pi4 and "
                         "v3dqpu.pi4 and require the gate to catch every one")
    ap.add_argument("--only", action="append",
                    help="with --mutate, run only the named mutant (repeatable)")
    a = ap.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    if not a.compiler:
        ap.error("No compiler was named.  Pass --compiler or set PMF_COMPILER to the "
                 "PureMetalForge executable.")
    with tempfile.TemporaryDirectory(prefix="v3d-tri-") as td:
        workdir = pathlib.Path(td)
        if a.mutate:
            print("a64_v3d_tri_check --mutate")
            print()
            return mutate(a.compiler, workdir, a.only)

        fails: list = []
        counts = {"oracle": 0, "model": 0, "verified": 0}
        print("a64_v3d_tri_check - the V3D stage 4 draw")
        print()
        check_pins(fails)
        check(fails, counts, a.compiler, workdir)
    print()
    print("  %3d shader instructions compared against py-videocore6's pinned"
          % counts["oracle"])
    print("      golden words, an independent implementation of this encoding.")
    print("  %3d compared against the pinned Mesa tables, because" % counts["model"])
    print("      py-videocore6 has no ldvpm operation.  That half is a model")
    print("      agreeing with a model.")
    print("  %3d programs accepted by tools/v3d42_qpu_decode.py's verifier."
          % counts["verified"])
    print("  %3d field rows checked." % R.ROWS[0])
    print()
    print("  WHAT THIS GATE CANNOT SAY: that any of it rasterises.  There is no")
    print("      V3D in the interpreter, the model leaves every poison word in")
    print("      place, and the run above REQUIRES the probe to report NO")
    print("      TRIANGLE.  Only pi4V3dTri.pi4 on the board can say there is one.")
    print()
    if fails:
        print("FAIL - %d" % len(fails))
        for f in fails:
            print("  * %s" % f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
