#!/usr/bin/env python3
"""Executable gate for the control-list half of RaspberryPi4/Lib/v3d.pi4:
the control list writer, the packet encoders, the bin list and the render
list.

It builds RaspberryPi4/Examples/Diagnostics/pi4V3dClear.pi4, runs it on the
A64 interpreter (tools/a64/a64_interp.py) against a model of the V3D hub and
core registers, takes the three control lists the library wrote out of the
model's memory, and decodes them packet by packet.

WHAT THIS GATE CAN FAIL ON

  1. A WRONG FIELD SHIFT, WIDTH OR minus_one.  Every packet this gate decodes
     has its field layout PINNED below from Mesa's v3d_packet.xml (name,
     start, size, minus_one, default), with the XML line it came from.  The
     bytes the library produced are decoded with that layout and the field
     values are compared against what the probe asked for.  The library's
     own shifts are never read.

  2. A WRONG PACKET LENGTH.  Derived by v3d_decoder.c's rule (below), and
     the walk must end exactly on the list's last byte.

  3. A REORDERED LIST.  The library's packet sequence must be a SUBSEQUENCE
     of the order Mesa's driver emits them in, pinned below per function
     from v3dx_draw.c, v3dx_job.c and v3dx_rcl.c.

  4. AN UNALIGNED ACCESS.  a64_interp.py refuses one and this gate does not
     turn that off.  A control list is a stream of unaligned fields and the
     writer is byte-wise for that reason.

  5. A CONSTANT THAT DRIFTED.  The tile-size table, the output-format to
     internal-type mapping, the CLE readahead, the tile-state size per tile
     and the tile-alloc arithmetic are pinned from Mesa and compared against
     the library's constants and the geometry the probe printed.

WHAT THIS GATE CANNOT DO

  1. IT CANNOT RENDER ANYTHING.  The model makes CLE_BFC and CLE_RFC
     increment when an end-address register is written and does nothing
     else.  The gate asserts its own blindness: it requires the probe to
     report 4096 pixels still poison and zero correct.
  2. It cannot say the packet SUBSET is right - a missing or a spurious
     packet both survive a subsequence test.
  3. It cannot say the XML describes this silicon.
  4. It cannot catch a cache coherency bug: the model's memory is a flat
     dictionary of bytes.
  5. It touches no board.

THIRD-PARTY SOURCES ARE CITED, NOT COPIED.  The Mesa files below are not
part of this repository.  Their facts are pinned in this file with the
upstream project, tag, path and line so a reader can check each one:

  mesa-24.3.4 (commit 769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de)
    src/broadcom/cle/v3d_packet.xml
    src/broadcom/cle/v3d_decoder.c
    src/broadcom/common/v3d_device_info.c
    src/broadcom/common/v3d_util.c
    src/gallium/drivers/v3d/v3dx_draw.c
    src/gallium/drivers/v3d/v3dx_job.c
    src/gallium/drivers/v3d/v3dx_rcl.c
    src/gallium/drivers/v3d/v3dx_format_table.c

  python tools/a64/a64_v3d_rcl_check.py --compiler <PureMetalForge.exe>
  python tools/a64/a64_v3d_rcl_check.py --compiler <PureMetalForge.exe> --mutate
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from a64_interp import A64, AlignmentFault   # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB = ROOT / "RaspberryPi4" / "Lib" / "v3d.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dClear.pi4"
LIB_INCLUDE = 'XIncludeFile "RaspberryPi4/Lib/v3d.pi4"'

LOAD = 0x400000
STACK = 0x3000000
LOADER_LR = 0xDEAD0000

UART_DR = 0xFE201000
UART_FR = 0xFE201018
MBX_READ = 0xFE00B880
MBX_STATUS0 = 0xFE00B898
MBX_WRITE = 0xFE00B8A0
MBX_STATUS1 = 0xFE00B8B8
MBX_EMPTY = 0x40000000

HUB = 0xFEC00000
CORE0 = 0xFEC04000
PM = 0xFE100000
ASB_LEGACY = 0xFE00A000
ASB_RPIVID = 0xFEC11000
BRDG_ID = 0x62726467


def text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# =====================================================================
#  THE PACKET LAYOUTS, PINNED FROM mesa-24.3.4 src/broadcom/cle/v3d_packet.xml
#
#  Only the V3D 4.2 form of each packet (the Pi 4's engine; the XML gates
#  packets and fields with min_ver/max_ver).  Where the XML carries a 4.2
#  and a 7.1 form under one code, the cited line is the max_ver="42" one.
#
#  Every start and size is in BITS of the payload after the opcode byte.
#  The XML writes some as bytes with a trailing 'b'; v3d_decoder.c:188-191
#  (is_byte_offset) and :318-329 multiply those by eight, and that
#  conversion was applied when these rows were pinned.
#
#  Row: (code, name, xml line, ((field, start, size, minus_one, default,
#  is_address), ...)).  A packet this table does not carry is refused by
#  the walk with a sentence naming it, not skipped.
# =====================================================================
VER = 42
A = True     # an address-typed field
U = False    # anything else

PACKETS_42 = (
    (4, "Flush", 330, ()),
    (6, "Start Tile Binning", 332, ()),
    (13, "End of rendering", 339, ()),
    (16, "Branch", 349, (("address", 0, 32, False, None, A),)),
    (18, "Return from sub-list", 357, ()),
    (19, "Flush VCD cache", 358, ()),
    (20, "Start Address of Generic Tile List", 360, (
        ("start", 0, 32, False, None, A),
        ("end", 32, 32, False, None, A))),
    (21, "Branch to Implicit Tile List", 365, (
        ("tile list set number", 0, 8, False, None, U),)),
    (23, "Supertile Coordinates", 376, (
        ("row number in supertiles", 8, 8, False, None, U),
        ("column number in supertiles", 0, 8, False, None, U))),
    (25, "Clear Tile Buffers", 381, (
        ("Clear Z/Stencil Buffer", 1, 1, False, None, U),
        ("Clear all Render Targets", 0, 1, False, None, U))),
    (26, "End of Loads", 388, ()),
    (27, "End of Tile Marker", 390, ()),
    (29, "Store Tile Buffer General", 392, (
        ("Address", 64, 32, False, None, A),
        ("Height", 48, 16, False, None, U),
        ("Height in UB or Stride", 28, 20, False, None, U),
        ("R/B swap", 20, 1, False, None, U),
        ("Channel Reverse", 19, 1, False, None, U),
        ("Clear buffer being stored", 18, 1, False, None, U),
        ("Output Image Format", 12, 6, False, None, U),
        ("Decimate mode", 10, 2, False, None, U),
        ("Dither Mode", 8, 2, False, None, U),
        ("Flip Y", 7, 1, False, None, U),
        ("Memory Format", 4, 3, False, None, U),
        ("Buffer to Store", 0, 4, False, None, U))),
    (36, "Vertex Array Prims", 508, (
        ("Index of First Vertex", 40, 32, False, None, U),
        ("Length", 8, 32, False, None, U),
        ("mode", 0, 8, False, None, U))),
    (54, "Set InstanceID", 550, (("Instance ID", 0, 32, False, None, U),)),
    (56, "Prim List Format", 558, (
        ("tri strip or fan", 7, 1, False, None, U),
        ("primitive type", 0, 6, False, None, U))),
    (64, "GL Shader State", 576, (
        ("address", 5, 27, False, None, A),
        ("number of attribute arrays", 0, 5, False, None, U))),
    (71, "VCM Cache Size", 596, (
        ("Number of 16-vertex batches for rendering", 4, 4, False, None, U),
        ("Number of 16-vertex batches for binning", 0, 4, False, None, U))),
    (83, "Blend Enables", 674, (("Mask", 0, 8, False, None, U),)),
    (84, "Blend Cfg", 678, (
        ("Render Target Mask", 24, 4, False, None, U),
        ("Color blend dst factor", 20, 4, False, None, U),
        ("Color blend src factor", 16, 4, False, None, U),
        ("Color blend mode", 12, 4, False, None, U),
        ("Alpha blend dst factor", 8, 4, False, None, U),
        ("Alpha blend src factor", 4, 4, False, None, U),
        ("Alpha blend mode", 0, 4, False, None, U))),
    (87, "Color Write Masks", 705, (("Mask", 0, 32, False, None, U),)),
    (88, "Zero All Centroid Flags", 709, ()),
    (91, "Sample State", 718, (
        ("Coverage", 16, 16, False, None, U),
        ("Mask", 0, 4, False, None, U))),
    (92, "Occlusion Query Counter", 723, (("address", 0, 32, False, None, A),)),
    (96, "Cfg Bits", 732, (
        ("Direct3D Provoking Vertex", 21, 1, False, None, U),
        ("Direct3D 'Point-fill' mode", 20, 1, False, None, U),
        ("Blend enable", 19, 1, False, None, U),
        ("Stencil enable", 18, 1, False, None, U),
        ("Early Z updates enable", 17, 1, False, None, U),
        ("Early Z enable", 16, 1, False, None, U),
        ("Z updates enable", 15, 1, False, None, U),
        ("Depth-Test Function", 12, 3, False, None, U),
        ("Direct3D Wireframe triangles mode", 11, 1, False, None, U),
        ("Rasterizer Oversample Mode", 6, 2, False, None, U),
        ("Line Rasterization", 4, 2, False, None, U),
        ("Enable Depth Offset", 3, 1, False, None, U),
        ("Clockwise Primitives", 2, 1, False, None, U),
        ("Enable Reverse Facing Primitive", 1, 1, False, None, U),
        ("Enable Forward Facing Primitive", 0, 1, False, None, U))),
    (97, "Zero All Flat Shade Flags", 769, ()),
    (99, "Zero All Non-perspective Flags", 778, ()),
    (104, "Point size", 787, (("Point Size", 0, 32, False, None, U),)),
    (105, "Line width", 791, (("Line width", 0, 32, False, None, U),)),
    (107, "clip_window", 801, (
        ("Clip Window Height in pixels", 48, 16, False, None, U),
        ("Clip Window Width in pixels", 32, 16, False, None, U),
        ("Clip Window Bottom Pixel Coordinate", 16, 16, False, None, U),
        ("Clip Window Left Pixel Coordinate", 0, 16, False, None, U))),
    (108, "Viewport Offset", 808, (
        ("Coarse Y", 54, 10, False, None, U),
        ("Fine Y", 32, 22, False, None, U),
        ("Coarse X", 22, 10, False, None, U),
        ("Fine X", 0, 22, False, None, U))),
    (109, "Clipper Z min/max clipping planes", 815, (
        ("Maximum Zw", 32, 32, False, None, U),
        ("Minimum Zw", 0, 32, False, None, U))),
    (110, "Clipper XY Scaling", 820, (
        ("Viewport Half-Height in 1/256th of pixel", 32, 32, False, None, U),
        ("Viewport Half-Width in 1/256th of pixel", 0, 32, False, None, U))),
    (111, "Clipper Z Scale and Offset", 830, (
        ("Viewport Z Offset (Zc to Zs)", 32, 32, False, None, U),
        ("Viewport Z Scale (Zc to Zs)", 0, 32, False, None, U))),
    (119, "Number of Layers", 840, (("Number of Layers", 0, 8, True, None, U),)),
    (120, "Tile Binning Mode Cfg", 844, (
        ("Height (in pixels)", 48, 16, True, None, U),
        ("Width (in pixels)", 32, 16, True, None, U),
        ("Double-buffer in non-ms mode", 15, 1, False, None, U),
        ("Multisample Mode (4x)", 14, 1, False, None, U),
        ("Maximum BPP of all render targets", 12, 2, False, None, U),
        ("Number of Render Targets", 8, 4, True, None, U),
        ("tile allocation block size", 4, 2, False, None, U),
        ("tile allocation initial block size", 2, 2, False, None, U))),
    (121, "Tile Rendering Mode Cfg (Common)", 897, (
        ("Pad", 52, 12, False, None, U),
        ("Early Depth/Stencil Clear", 51, 1, False, None, U),
        ("Internal Depth Type", 47, 4, False, None, U),
        ("Early-Z disable", 46, 1, False, None, U),
        ("Early-Z Test and Update Direction", 45, 1, False, None, U),
        ("Double-buffer in non-ms mode", 43, 1, False, None, U),
        ("Multisample Mode (4x)", 42, 1, False, None, U),
        ("Maximum BPP of all render targets", 40, 2, False, None, U),
        ("Image Height (pixels)", 24, 16, False, None, U),
        ("Image Width (pixels)", 8, 16, False, None, U),
        ("Number of Render Targets", 4, 4, True, None, U),
        ("sub-id", 0, 4, False, 0, U))),
    (121, "Tile Rendering Mode Cfg (Color)", 963, (
        ("Pad", 36, 28, False, None, U),
        ("Render Target 3 Clamp", 34, 2, False, None, U),
        ("Render Target 3 Internal Type", 30, 4, False, None, U),
        ("Render Target 3 Internal BPP", 28, 2, False, None, U),
        ("Render Target 2 Clamp", 26, 2, False, None, U),
        ("Render Target 2 Internal Type", 22, 4, False, None, U),
        ("Render Target 2 Internal BPP", 20, 2, False, None, U),
        ("Render Target 1 Clamp", 18, 2, False, None, U),
        ("Render Target 1 Internal Type", 14, 4, False, None, U),
        ("Render Target 1 Internal BPP", 12, 2, False, None, U),
        ("Render Target 0 Clamp", 10, 2, False, None, U),
        ("Render Target 0 Internal Type", 6, 4, False, None, U),
        ("Render Target 0 Internal BPP", 4, 2, False, None, U),
        ("sub-id", 0, 4, False, 1, U))),
    (121, "Tile Rendering Mode Cfg (ZS Clear Values)", 986, (
        ("unused", 48, 16, False, None, U),
        ("Z Clear Value", 16, 32, False, None, U),
        ("Stencil Clear Value", 8, 8, False, None, U),
        ("sub-id", 0, 4, False, 2, U))),
    (121, "Tile Rendering Mode Cfg (Clear Colors Part1)", 1004, (
        ("Clear Color next 24 bits", 40, 24, False, None, U),
        ("Clear Color low 32 bits", 8, 32, False, None, U),
        ("Render Target number", 4, 4, False, None, U),
        ("sub-id", 0, 4, False, 3, U))),
    (122, "Multicore Rendering Supertile Cfg", 1065, (
        ("Number of Bin Tile Lists", 61, 3, True, None, U),
        ("Supertile Raster Order", 60, 1, False, None, U),
        ("Multicore Enable", 56, 1, False, None, U),
        ("Total Frame Height in Tiles", 44, 12, False, None, U),
        ("Total Frame Width in Tiles", 32, 12, False, None, U),
        ("Total Frame Height in Supertiles", 24, 8, False, None, U),
        ("Total Frame Width in Supertiles", 16, 8, False, None, U),
        ("Supertile Height in Tiles", 8, 8, True, None, U),
        ("Supertile Width in Tiles", 0, 8, True, None, U))),
    (123, "Multicore Rendering Tile List Set Base", 1080, (
        ("address", 6, 26, False, None, A),
        ("Tile List Set Number", 0, 4, False, None, U))),
    (124, "Tile Coordinates", 1060, (
        ("tile row number", 12, 12, False, None, U),
        ("tile column number", 0, 12, False, None, U))),
    (125, "Tile Coordinates Implicit", 1086, ()),
    (126, "Tile List Initial Block Size", 1088, (
        ("Use auto-chained tile lists", 2, 1, False, None, U),
        ("Size of first block in chained tile lists", 0, 2, False, None, U))),
)

# The lengths the XML's layout gives, pinned separately from the fields so
# that a mistyped field row above is caught by the gate itself before any
# list is decoded (see check_pins()).
PACKET_LENGTHS_42 = {
    "Flush": 1, "Start Tile Binning": 1, "End of rendering": 1, "Branch": 5,
    "Return from sub-list": 1, "Flush VCD cache": 1,
    "Start Address of Generic Tile List": 9, "Branch to Implicit Tile List": 2,
    "Supertile Coordinates": 3, "Clear Tile Buffers": 2, "End of Loads": 1,
    "End of Tile Marker": 1, "Store Tile Buffer General": 13,
    "Vertex Array Prims": 10, "Set InstanceID": 5, "Prim List Format": 2,
    "GL Shader State": 5, "VCM Cache Size": 2, "Blend Enables": 2,
    "Blend Cfg": 5, "Color Write Masks": 5, "Zero All Centroid Flags": 1,
    "Sample State": 5, "Occlusion Query Counter": 5, "Cfg Bits": 4,
    "Zero All Flat Shade Flags": 1, "Zero All Non-perspective Flags": 1,
    "Point size": 5, "Line width": 5, "clip_window": 9, "Viewport Offset": 9,
    "Clipper Z min/max clipping planes": 9, "Clipper XY Scaling": 9,
    "Clipper Z Scale and Offset": 9, "Number of Layers": 2,
    "Tile Binning Mode Cfg": 9, "Tile Rendering Mode Cfg (Common)": 9,
    "Tile Rendering Mode Cfg (Color)": 9,
    "Tile Rendering Mode Cfg (ZS Clear Values)": 9,
    "Tile Rendering Mode Cfg (Clear Colors Part1)": 9,
    "Multicore Rendering Supertile Cfg": 9,
    "Multicore Rendering Tile List Set Base": 5, "Tile Coordinates": 4,
    "Tile Coordinates Implicit": 1, "Tile List Initial Block Size": 2,
}

# <struct>s carry no opcode byte, so their bit positions are not shifted.
STRUCTS_42 = {
    # v3d_packet.xml:1098, the max_ver="42" form.
    "GL Shader State Record": (36, (
        ("Point size in shaded vertex data", 0, 1, False, None, U),
        ("Enable clipping", 1, 1, False, None, U),
        ("Vertex ID read by coordinate shader", 2, 1, False, None, U),
        ("Instance ID read by coordinate shader", 3, 1, False, None, U),
        ("Base Instance ID read by coordinate shader", 4, 1, False, None, U),
        ("Vertex ID read by vertex shader", 5, 1, False, None, U),
        ("Instance ID read by vertex shader", 6, 1, False, None, U),
        ("Base Instance ID read by vertex shader", 7, 1, False, None, U),
        ("Fragment shader does Z writes", 8, 1, False, None, U),
        ("Turn off early-z test", 9, 1, False, None, U),
        ("Coordinate shader has separate input and output VPM blocks", 10, 1, False, None, U),
        ("Vertex shader has separate input and output VPM blocks", 11, 1, False, None, U),
        ("Fragment shader uses real pixel centre W in addition to centroid W2", 12, 1, False, None, U),
        ("Enable Sample Rate Shading", 13, 1, False, None, U),
        ("Any shader reads hardware-written Primitive ID", 14, 1, False, None, U),
        ("Insert Primitive ID as first varying to fragment shader", 15, 1, False, None, U),
        ("Turn off scoreboard", 16, 1, False, None, U),
        ("Do scoreboard wait on first thread switch", 17, 1, False, None, U),
        ("Disable implicit point/line varyings", 18, 1, False, None, U),
        ("No prim pack", 19, 1, False, None, U),
        ("Number of varyings in Fragment Shader", 24, 8, False, None, U),
        ("Coordinate Shader output VPM segment size", 32, 4, False, None, U),
        ("Min Coord Shader output segments required in play in addition to VCM cache size", 36, 4, False, None, U),
        ("Coordinate Shader input VPM segment size", 40, 4, False, None, U),
        ("Min Coord Shader input segments required in play", 44, 4, True, None, U),
        ("Vertex Shader output VPM segment size", 48, 4, False, None, U),
        ("Min Vertex Shader output segments required in play in addition to VCM cache size", 52, 4, False, None, U),
        ("Vertex Shader input VPM segment size", 56, 4, False, None, U),
        ("Min Vertex Shader input segments required in play", 60, 4, True, None, U),
        ("Address of default attribute values", 64, 32, False, None, A),
        ("Fragment Shader Code Address", 99, 29, False, None, A),
        ("Fragment Shader 4-way threadable", 96, 1, False, None, U),
        ("Fragment Shader start in final thread section", 97, 1, False, None, U),
        ("Fragment Shader Propagate NaNs", 98, 1, False, None, U),
        ("Fragment Shader Uniforms Address", 128, 32, False, None, A),
        ("Vertex Shader Code Address", 163, 29, False, None, A),
        ("Vertex Shader 4-way threadable", 160, 1, False, None, U),
        ("Vertex Shader start in final thread section", 161, 1, False, None, U),
        ("Vertex Shader Propagate NaNs", 162, 1, False, None, U),
        ("Vertex Shader Uniforms Address", 192, 32, False, None, A),
        ("Coordinate Shader Code Address", 227, 29, False, None, A),
        ("Coordinate Shader 4-way threadable", 224, 1, False, None, U),
        ("Coordinate Shader start in final thread section", 225, 1, False, None, U),
        ("Coordinate Shader Propagate NaNs", 226, 1, False, None, U),
        ("Coordinate Shader Uniforms Address", 256, 32, False, None, A))),
    # v3d_packet.xml:1374.
    "GL Shader State Attribute Record": (16, (
        ("Address", 0, 32, False, None, A),
        ("Vec size", 32, 2, False, None, U),
        ("Type", 34, 3, False, None, U),
        ("Signed int type", 37, 1, False, None, U),
        ("Normalized int type", 38, 1, False, None, U),
        ("Read as int/uint", 39, 1, False, None, U),
        ("Number of values read by Coordinate shader", 40, 4, False, None, U),
        ("Number of values read by Vertex shader", 44, 4, False, None, U),
        ("Instance Divisor", 48, 16, False, None, U),
        ("Stride", 64, 32, False, None, U),
        ("Maximum Index", 96, 32, False, None, U))),
}

# The enumeration values this gate and a64_neon_check.py compare against,
# by the XML's own value names.  Only the values actually used are pinned.
ENUMS_42 = {
    "Blend Factor": {"SRC_ALPHA": 6, "INV_SRC_ALPHA": 7},      # xml:14
    "Blend Mode": {"ADD": 0},                                   # xml:32
    "Primitive": {"TRIANGLES": 4},                              # xml:55
    "Memory Format": {"Raster": 0, "UIF (XOR)": 5},             # xml:108
    "Decimate Mode": {"sample 0": 0},                           # xml:117
    "Internal Type": {"8": 2},                                  # xml:123
    "Internal BPP": {"32": 0},                                   # xml:135
    "Output Image Format": {"bgr565": 7, "rgba8": 27},          # xml:222
}


class Field:
    def __init__(self, row):
        (self.name, self.start, self.size, self.minus_one, self.default,
         self.is_address) = row

    def get(self, payload: int) -> int:
        raw = (payload >> self.start) & ((1 << self.size) - 1)
        if self.minus_one:
            return raw + 1
        if self.is_address:
            # AN ADDRESS FIELD NARROWER THAN 32 BITS HOLDS THE ADDRESS
            # SHIFTED DOWN, and the shift is a function of the WIDTH.
            # v3d_decoder.c:880-882 reconstructs one as
            # `unpack_uint(p, s, e) << (31 - (e - s))`, so the shift is
            # `32 - size`: nothing for a 32-bit field, six bits for the
            # 26-bit tile-list base, five for the 27-bit shader state
            # record pointer.  Decoding this wrong would read a correct
            # $660000 as $19800 and call it a mismatch - or, worse, agree
            # with a wrong encoder.
            return raw << (32 - self.size)
        return raw


class Packet:
    def __init__(self, code, name, fields, opcode_byte=True):
        self.code = code
        self.name = name
        self.short = name
        self.fields = [Field(f) for f in fields]
        # v3d_decoder.c:728-738, v3d_group_get_length: the highest bit any
        # field touches, after :512-518 has shifted every start up by the
        # eight opcode bits, divided by eight, plus one.  Structs have no
        # opcode byte and no shift.
        shift = 8 if opcode_byte else 0
        last = 0 if opcode_byte else -1
        for f in self.fields:
            last = max(last, f.start + f.size - 1 + shift)
        self.length = last // 8 + 1
        # The packets that share code 121 are told apart by the `default`
        # on their sub-id field.
        self.subid_field = None
        self.subid = None
        for f in self.fields:
            if f.name == "sub-id" and f.default is not None:
                self.subid_field = f
                self.subid = f.default

    def decode(self, data: bytes, off: int) -> dict:
        payload = 0
        for i in range(1, self.length):
            payload |= data[off + i] << (8 * (i - 1))
        return {f.name: f.get(payload) for f in self.fields}


def check_pins() -> None:
    """Refuse to run on a pinned table that disagrees with itself."""
    seen = set()
    for code, name, _line, fields in PACKETS_42:
        p = Packet(code, name, fields)
        if PACKET_LENGTHS_42.get(name) != p.length:
            raise SystemExit(
                "The pinned layout of %r gives a %d-byte packet but its pinned "
                "length is %s; one of the two rows was mistyped when it was "
                "pinned from v3d_packet.xml." % (name, p.length,
                                                 PACKET_LENGTHS_42.get(name)))
        if name in seen:
            raise SystemExit("The packet %r is pinned twice." % name)
        seen.add(name)
    for name, (length, fields) in STRUCTS_42.items():
        if Packet(-1, name, fields, opcode_byte=False).length != length:
            raise SystemExit("The pinned layout of the %r struct does not give "
                             "its pinned %d-byte length." % (name, length))


def parse_packets() -> dict:
    check_pins()
    by_code: dict[int, list[Packet]] = {}
    for code, name, _line, fields in PACKETS_42:
        by_code.setdefault(code, []).append(Packet(code, name, fields))
    return by_code


def parse_struct(name: str) -> Packet | None:
    row = STRUCTS_42.get(name)
    if row is None:
        return None
    return Packet(-1, name, row[1], opcode_byte=False)


def decode_list(by_code: dict, data: bytes) -> list[tuple[str, dict, int]]:
    """Walk a control list packet by packet.

    A LIST THAT DOES NOT END EXACTLY ON ITS LAST BYTE IS A FAILURE.  If a
    packet's length is wrong the walk desynchronises and either runs past
    the end or stops short, and both are reported with the offset.
    """
    out = []
    off = 0
    while off < len(data):
        op = data[off]
        cands = by_code.get(op)
        if not cands:
            raise SystemExit(
                "a64_v3d_rcl_check: opcode %d at offset %d is not a packet this "
                "gate pins for V3D %d.  If the library legitimately emits it, "
                "pin its layout from v3d_packet.xml.  The walk had consumed %d "
                "packets.\n  %s"
                % (op, off, VER, len(out),
                   " ".join("%02X" % b for b in data[max(0, off - 8):off + 8])))
        p = cands[0]
        if len(cands) > 1:
            probe = cands[0].subid_field
            if probe is None:
                raise SystemExit("a64_v3d_rcl_check: opcode %d has %d forms "
                                 "and no sub-id field." % (op, len(cands)))
            sub = (data[off + 1] >> probe.start) & ((1 << probe.size) - 1)
            match = [c for c in cands if c.subid == sub]
            if len(match) != 1:
                raise SystemExit(
                    "a64_v3d_rcl_check: opcode %d sub-id %d at offset %d "
                    "matches %d pinned packets." % (op, sub, off, len(match)))
            p = match[0]
        if off + p.length > len(data):
            raise SystemExit(
                "a64_v3d_rcl_check: %s at offset %d needs %d bytes and the "
                "list has %d left.  A packet length is wrong, or the list "
                "was truncated." % (p.name, off, p.length, len(data) - off))
        out.append((p.name, p.decode(data, off), off))
        off += p.length
    return out


def enum_value(enum_name: str, value_name: str) -> int:
    for name, values in ENUMS_42.items():
        if name != enum_name:
            continue
        for k, v in values.items():
            if k.lower() == value_name.lower():
                return v
    raise SystemExit("a64_v3d_rcl_check: %r in enum %r is not pinned from "
                     "v3d_packet.xml." % (value_name, enum_name))


# =====================================================================
#  THE PACKET ORDER, PINNED PER FUNCTION FROM MESA'S DRIVER
#
#  Each list is the `cl_emit(...)` calls of one function in SOURCE ORDER,
#  with the V3D 7.1 arms removed - Mesa writes the version choice both as
#  `#if V3D_VERSION >= 71` and as `#if V3D_VERSION < 71 ... #else`
#  (v3dx_rcl.c:573-580), and keeping the 7.1 arm would put
#  CLEAR_RENDER_TARGETS into the expected 4.2 order.  C control flow is
#  deliberately not resolved: the check is SUBSEQUENCE, so packets Mesa
#  emits conditionally may be absent.
#
#  The composition below - inlining the loads and stores helpers, moving
#  START_ADDRESS_OF_GENERIC_TILE_LIST to the render list, unrolling the
#  GFXH-1742 loop - is done here from these per-function lists rather than
#  pinned as one flat answer, so the reasoning is checkable.
# =====================================================================
MESA_EMITS = {
    # src/gallium/drivers/v3d/v3dx_draw.c:44-139, v3dX(start_binning).
    "start_binning": ["NUMBER_OF_LAYERS", "TILE_BINNING_MODE_CFG",
                      "FLUSH_VCD_CACHE", "OCCLUSION_QUERY_COUNTER",
                      "START_TILE_BINNING"],
    # src/gallium/drivers/v3d/v3dx_job.c:33-69, v3dX(bcl_epilogue).
    "bcl_epilogue": ["PRIMITIVE_COUNTS_FEEDBACK", "TRANSFORM_FEEDBACK_SPECS",
                     "FLUSH"],
    # v3dx_rcl.c:319-358, v3d_rcl_emit_generic_per_tile_list.  The loads
    # helper is called after TILE_COORDINATES_IMPLICIT (:333), the stores
    # helper after BRANCH_TO_IMPLICIT_TILE_LIST (:349), and the final
    # START_ADDRESS_OF_GENERIC_TILE_LIST goes into the RENDER list (:355).
    "generic_per_tile_list": ["TILE_COORDINATES_IMPLICIT", "PRIM_LIST_FORMAT",
                              "SET_INSTANCEID", "BRANCH_TO_IMPLICIT_TILE_LIST",
                              "END_OF_TILE_MARKER", "RETURN_FROM_SUB_LIST",
                              "START_ADDRESS_OF_GENERIC_TILE_LIST"],
    # v3dx_rcl.c:166, v3d_rcl_emit_loads.
    "emit_loads": ["END_OF_LOADS"],
    # v3dx_rcl.c:218, v3d_rcl_emit_stores.
    "emit_stores": ["STORE_TILE_BUFFER_GENERAL", "CLEAR_TILE_BUFFERS"],
    # v3dx_rcl.c:87, store_general.
    "store_general": ["STORE_TILE_BUFFER_GENERAL"],
    # v3dx_rcl.c:619-, v3dX(emit_rcl).  emit_render_layer is called from
    # the loop that follows TILE_LIST_INITIAL_BLOCK_SIZE.
    "emit_rcl": ["TILE_RENDERING_MODE_CFG_COMMON",
                 "TILE_RENDERING_MODE_CFG_CLEAR_COLORS_PART1",
                 "TILE_RENDERING_MODE_CFG_CLEAR_COLORS_PART2",
                 "TILE_RENDERING_MODE_CFG_CLEAR_COLORS_PART3",
                 "TILE_RENDERING_MODE_CFG_COLOR",
                 "TILE_RENDERING_MODE_CFG_ZS_CLEAR_VALUES",
                 "TILE_LIST_INITIAL_BLOCK_SIZE", "END_OF_RENDERING"],
    # v3dx_rcl.c:500-, emit_render_layer: before the GFXH-1742 loop
    # (:509-546), inside it (:566-582), and after it (:584-609), where the
    # call to v3d_rcl_emit_generic_per_tile_list at :586 contributes
    # START_ADDRESS_OF_GENERIC_TILE_LIST to this list.
    "layer_before": ["MULTICORE_RENDERING_TILE_LIST_SET_BASE",
                     "MULTICORE_RENDERING_SUPERTILE_CFG", "TILE_COORDINATES"],
    "layer_inside": ["TILE_COORDINATES", "END_OF_LOADS",
                     "STORE_TILE_BUFFER_GENERAL", "CLEAR_TILE_BUFFERS",
                     "END_OF_TILE_MARKER"],
    "layer_after": ["FLUSH_VCD_CACHE", "START_ADDRESS_OF_GENERIC_TILE_LIST",
                    "SUPERTILE_COORDINATES"],
}
# v3dx_rcl.c:556-564: one dummy store on V3D 3.x and TWO on 4.x -
# `for (int i = 0; i < 2; i++)`.  The count IS the workaround.
GFXH_1742_ITERATIONS = 2
# Packets that exist only on V3D 7.1 and must never be in the 4.2 order.
V3D71_ONLY = {"CLEAR_RENDER_TARGETS",
              "TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1"}


def derive_mesa_order() -> dict:
    e = MESA_EMITS
    for names in e.values():
        stray = V3D71_ONLY.intersection(names)
        if stray:
            raise SystemExit("The pinned Mesa order carries the 7.1-only "
                             "packet(s) %s." % sorted(stray))
    bcl = e["start_binning"] + e["bcl_epilogue"]
    tile = []
    for name in e["generic_per_tile_list"]:
        if name == "TILE_COORDINATES_IMPLICIT":
            tile.append(name)
            tile += e["emit_loads"]
        elif name == "BRANCH_TO_IMPLICIT_TILE_LIST":
            tile.append(name)
            tile += e["emit_stores"]
            tile += e["store_general"]
        elif name == "START_ADDRESS_OF_GENERIC_TILE_LIST":
            continue
        else:
            tile.append(name)
    layer = (e["layer_before"] + e["layer_inside"] * GFXH_1742_ITERATIONS
             + e["layer_after"])
    out = []
    for name in e["emit_rcl"]:
        out.append(name)
        if name == "TILE_LIST_INITIAL_BLOCK_SIZE":
            out += layer
    return {"bcl": bcl, "tile": tile, "rcl": out}


# Packets Mesa emits inside a loop whose trip count depends on the FRAME.
# A run of them is collapsed to one before the subsequence test; the COUNT
# is checked separately against the geometry.
REPEATABLE = {"SUPERTILE_COORDINATES"}


def is_subsequence(small: list[str], big: list[str]) -> tuple[bool, str]:
    collapsed: list[str] = []
    for s in small:
        if collapsed and s == collapsed[-1] and s in REPEATABLE:
            continue
        collapsed.append(s)
    it = iter(big)
    for s in collapsed:
        for b in it:
            if b == s:
                break
        else:
            return False, s
    return True, ""


# =====================================================================
#  CONSTANTS PINNED FROM MESA
# =====================================================================
# src/broadcom/common/v3d_device_info.c:74-76, the `case 42:` arm.
CLE_READAHEAD_42 = 256
# src/broadcom/common/v3d_util.c:122-130, tile_sizes[].
TILE_SIZES = [(64, 64), (64, 32), (32, 32), (32, 16), (16, 16), (16, 8), (8, 8)]
# src/gallium/drivers/v3d/v3dx_format_table.c:226-233,
# v3dX(get_internal_type_bpp_for_output_format): the RGBA8 arm sets
# V3D_INTERNAL_TYPE_8 and V3D_INTERNAL_BPP_32, resolved through the XML
# enums pinned above.
RGBA8_INTERNAL = ("8", "32")
# src/gallium/drivers/v3d/v3dx_draw.c:80.
TSDA_PER_TILE = 256
# src/gallium/drivers/v3d/v3dx_draw.c:60-76: layers * tiles * 64 (:60-61),
# aligned to 4096 (:64), plus 8192 (:70), plus 512 KB (:76).
TILE_ALLOC_PER_TILE = 64
TILE_ALLOC_ALIGN = 4096
TILE_ALLOC_PLUS = (8192, 512 * 1024)


def derive_readahead() -> int:
    return CLE_READAHEAD_42


def derive_tile_sizes() -> list[tuple[int, int]]:
    return list(TILE_SIZES)


def derive_internal_for_rgba8() -> tuple[int, int]:
    ty, bpp = RGBA8_INTERNAL
    return enum_value("Internal Type", ty), enum_value("Internal BPP", bpp)


def derive_output_format(name: str) -> int:
    return enum_value("Output Image Format", name)


def derive_tsda_per_tile() -> int:
    return TSDA_PER_TILE


def derive_tile_alloc_bytes(tiles_x: int, tiles_y: int, layers: int) -> int:
    n = layers * tiles_x * tiles_y * TILE_ALLOC_PER_TILE
    n = ((n + TILE_ALLOC_ALIGN - 1) // TILE_ALLOC_ALIGN) * TILE_ALLOC_ALIGN
    for p in TILE_ALLOC_PLUS:
        n += p
    return n


def _constant(src: str, name: str, where: str) -> int:
    m = re.search(r"^#%s\s*=\s*(\S+)" % re.escape(name), src, re.M)
    if not m:
        raise SystemExit("a64_v3d_rcl_check: %s has no #%s." % (where, name))
    v = m.group(1)
    return int(v[1:], 16) if v.startswith("$") else int(v)


def probe_constant(name: str) -> int:
    return _constant(text(PROBE), name, "the probe")


def lib_constant(name: str) -> int:
    return _constant(text(LIB), name, "v3d.pi4")


# =====================================================================
#  BUILD
# =====================================================================
class Context:
    """Which compiler, where to put images, and which probe to build."""

    def __init__(self, compiler: str, work: pathlib.Path,
                 probe: pathlib.Path = PROBE) -> None:
        self.compiler = compiler
        self.work = work
        self.probe = probe
        self.image = work / "v3dclear.img"


def compile_probe(compiler: str, probe: pathlib.Path,
                  img: pathlib.Path) -> pathlib.Path:
    img.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [compiler, "--compile", str(probe), "-t", "pi4",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-s", "-o", str(img)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.is_file():
        raise SystemExit("The probe %s did not build.\n%s%s"
                         % (probe.name, r.stdout[-3000:], r.stderr[-2000:]))
    return img


# =====================================================================
#  THE MODEL - it does not render; it only lets the payload reach the end
#  of Main() so the lists it built can be read out of its memory.
# =====================================================================
class Model:
    def __init__(self, bfc_moves=True, rfc_moves=True, render_done=True):
        self.ident1 = 0x000E1124
        self.ident2 = 0x00000100          # WITH_MMU
        self.grafx = 0x1020 | 0x06
        self.asb = {0x08: 0x03, 0x0C: 0x03}
        self.mmu_ctl = 0
        self.mmu_pt = 0
        self.mmu_illegal = 0
        self.mmuc = 0
        self.l2t = 0
        self.uart = bytearray()
        self.mbx = None
        # THE CLE, AND IT IS A COUNTER AND NOTHING ELSE.
        self.cle = {}
        self.bfc = 0
        self.rfc = 0
        self.int_sts = 0
        self.bfc_moves = bfc_moves
        self.rfc_moves = rfc_moves
        self.render_done = render_done
        self.ptb = {}
        self.core_regs_written: list[int] = []


def symbols(img: pathlib.Path):
    dbg = pathlib.Path(str(img) + ".dbg")
    out = []
    if dbg.exists():
        for line in text(dbg).splitlines():
            f = line.split("|")
            if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
                out.append((LOAD + int(f[1]), f[2], f[3]))
    out.sort()
    return out


def where(syms, pc):
    best = None
    for addr, nm, src in syms:
        if addr <= pc:
            best = (addr, nm, src)
        else:
            break
    if best is None:
        return "$%08X" % pc
    return "$%08X - %s+%d, %s" % (pc, best[1], pc - best[0], best[2])


def run(img: pathlib.Path, m: Model, limit=200_000_000):
    cpu = A64()
    syms = symbols(img)
    cpu.locate = lambda pc: where(syms, pc)
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def mmio_guard(addr, size, write):
        # WIDTH AS WELL AS ALIGNMENT: a bare Peek/Poke is eight bytes on
        # this target and takes the neighbouring register with it.
        if size != 4:
            raise SystemExit(
                "a64_v3d_rcl_check: a %d-BYTE %s at $%08X.  Peripheral "
                "registers on this part are 32 bits.\n  at %s"
                % (size, "write" if write else "read", addr,
                   where(syms, cpu.this_instr)))

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if addr < 0xFC000000:
            return sum(cpu.memory.get(addr + i, 0) << (8 * i)
                       for i in range(size))
        mmio_guard(addr, size, False)
        if addr == UART_FR:
            return 0
        if addr == MBX_STATUS1:
            return 0
        if addr == MBX_STATUS0:
            return 0 if m.mbx is not None else MBX_EMPTY
        if addr == MBX_READ:
            r, m.mbx = m.mbx, None
            return r if r is not None else 0
        if addr == ASB_LEGACY + 0x20:
            return BRDG_ID
        if addr == ASB_RPIVID + 0x20:
            return BRDG_ID
        if ASB_RPIVID <= addr < ASB_RPIVID + 0x20:
            return m.asb.get(addr - ASB_RPIVID, 0)
        if addr == PM + 0x10C:
            return m.grafx
        if HUB <= addr < HUB + 0x4000:
            return hub_read(m, addr - HUB)
        if CORE0 <= addr < CORE0 + 0x4000:
            return core_read(m, addr - CORE0)
        raise SystemExit("a64_v3d_rcl_check: unmodelled read at $%08X\n  at %s"
                         % (addr, where(syms, cpu.this_instr)))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        value &= (1 << (8 * size)) - 1
        if addr < 0xFC000000:
            for i in range(size):
                cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF
            return
        mmio_guard(addr, size, True)
        if addr == UART_DR:
            m.uart.append(value & 0xFF)
            return
        if addr == MBX_WRITE:
            # Every state bit reads 0 and every set replies 1; clock-rate
            # queries answer 500 MHz.  v3d.pi4 treats none of it as proof.
            req = value & ~0xF
            tag = sum(cpu.memory.get(req + 8 + i, 0) << (8 * i) for i in range(4))
            for off, val in ((4, 0x80000000), (8 + 8, 0x80000000 | 8)):
                for i in range(4):
                    cpu.memory[req + off + i] = (val >> (8 * i)) & 0xFF
            base = req + 20
            if tag in (0x00030002, 0x00038002, 0x00030047):
                for i in range(4):
                    cpu.memory[base + i] = (500000000 >> (8 * i)) & 0xFF
            else:
                for i in range(4):
                    cpu.memory[base + i] = (1 >> (8 * i)) & 0xFF
            m.mbx = value
            return
        if addr == PM + 0x10C:
            if (value >> 24) == 0x5A:
                m.grafx = value & 0x00FFFFFF
            return
        if ASB_RPIVID <= addr < ASB_RPIVID + 0x20:
            if (value >> 24) != 0x5A:
                return
            v = value & 0x00FFFFFF
            m.asb[addr - ASB_RPIVID] = (v | 2) if (v & 1) else (v & ~2)
            return
        if HUB <= addr < HUB + 0x4000:
            hub_write(m, addr - HUB, value)
            return
        if CORE0 <= addr < CORE0 + 0x4000:
            core_write(m, addr - CORE0, value, syms, cpu)
            return
        raise SystemExit("a64_v3d_rcl_check: unmodelled write at $%08X\n  at %s"
                         % (addr, where(syms, cpu.this_instr)))

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    # CNTPCT_EL0 MUST ADVANCE: every bounded wait in v3d.pi4 is written
    # against it.  The step is a modelling knob: it changes how long a
    # timeout takes to arrive, not whether it is enforced.
    ticks = [0]

    def step() -> None:
        ins = load(cpu.pc, 4)
        base = ins & 0xFFFFFFE0
        if base == 0xD53BE020:          # mrs Xt, cntpct_el0
            ticks[0] += 4096
            cpu.x[ins & 31] = ticks[0]
            cpu.pc += 4
            return
        if base == 0xD53BE000:          # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = 54_000_000
            cpu.pc += 4
            return
        plain_step()

    n = 0
    try:
        while cpu.pc != LOADER_LR and n < limit:
            step()
            n += 1
    except AlignmentFault as f:
        raise SystemExit("a64_v3d_rcl_check: ALIGNMENT FAULT.\n  %s" % f)
    if n >= limit:
        raise SystemExit("a64_v3d_rcl_check: the probe never returned after "
                         "%d instructions.\n  at %s"
                         % (n, where(syms, cpu.pc)))
    return cpu, m.uart.decode("utf-8", "replace")


def hub_read(m, off):
    up = (m.grafx & 0x40) and not (m.asb[0x08] & 2) and not (m.asb[0x0C] & 2)
    if off == 0x0000C:
        return m.ident1 if up else 0
    if not up:
        return 0
    if off == 0x00008:
        return 0
    if off == 0x00010:
        return m.ident2
    if off == 0x00014:
        return 0
    if off == 0x01238:
        return (6 << 8) | (6 << 4) | 2
    if off == 0x00050:
        return 0
    if off == 0x0005C:
        return 0xFFFFFFFF
    if off == 0x01200:
        return m.mmu_ctl
    if off == 0x01204:
        return m.mmu_pt
    if off == 0x01230:
        return m.mmu_illegal
    if off == 0x01208 or off == 0x0120C:
        return 0
    if off == 0x01234 or off == 0x0122C:
        return 0
    if off == 0x01000:
        return m.mmuc & ~4
    raise SystemExit("a64_v3d_rcl_check: unmodelled hub read at $%05X" % off)


def hub_write(m, off, value):
    if off == 0x00058 or off == 0x00060 or off == 0x00064:
        return
    if off == 0x01204:
        m.mmu_pt = value
        return
    if off == 0x01200:
        m.mmu_ctl = value & ~4
        return
    if off == 0x01230:
        m.mmu_illegal = value
        return
    if off == 0x01000:
        m.mmuc = value & ~2
        return
    raise SystemExit("a64_v3d_rcl_check: unmodelled hub write at $%05X" % off)


def core_read(m, off):
    if off == 0x00000:
        return 0
    if off == 0x00004:
        return (16 << 16) | (2 << 12) | (4 << 8) | (2 << 4) | 2
    if off == 0x00008:
        return 0
    if off == 0x00050:
        return m.int_sts
    if off == 0x00030:
        return m.l2t
    if off == 0x00F20:
        return 0x00001000
    if off == 0x00134:
        return m.bfc
    if off == 0x00138:
        return m.rfc
    if off in (0x00100, 0x00104, 0x00110, 0x00114, 0x00130):
        return m.cle.get(off, 0)
    if off in (0x00108, 0x0010C):
        return m.cle.get(off, 0)
    if off in (0x00300, 0x00304, 0x00308, 0x0030C):
        return m.ptb.get(off, 0)
    raise SystemExit("a64_v3d_rcl_check: unmodelled core read at $%05X" % off)


def core_write(m, off, value, syms, cpu):
    m.core_regs_written.append(off)
    if off in (0x00024, 0x00030, 0x00034, 0x00038):
        if off == 0x00030:
            m.l2t = 0          # every flush completes instantly
        return
    if off == 0x00058:
        m.int_sts &= ~value
        return
    if off in (0x00300, 0x00304, 0x00308, 0x0030C):
        m.ptb[off] = value
        return
    if off in (0x0015C, 0x00160, 0x00164, 0x00170, 0x00174):
        m.cle[off] = value
        return
    # WRITING THE END REGISTER IS WHAT STARTS THE JOB.  The model's entire
    # response is to bump a counter.
    if off == 0x00168:
        m.cle[off] = value
        m.cle[0x00110] = value
        m.cle[0x00108] = value
        if m.bfc_moves:
            m.bfc = (m.bfc + 1) & 0xFF
            m.int_sts |= 2              # FLDONE
        return
    if off == 0x0016C:
        m.cle[off] = value
        m.cle[0x00114] = value
        m.cle[0x0010C] = value
        if m.rfc_moves:
            m.rfc = (m.rfc + 1) & 0xFF
        if m.render_done:
            m.int_sts |= 1              # FRDONE
        return
    raise SystemExit("a64_v3d_rcl_check: write to core register $%05X, which "
                     "the model has no name for.\n  at %s"
                     % (off, where(syms, cpu.this_instr)))


# =====================================================================
#  THE CHECKS
# =====================================================================
ROWS = [0]


def row(name, want, got, fails):
    ROWS[0] += 1
    ok = (want == got)
    print("    %-46s %-12s %s" % (name, str(want), "ok" if ok else
                                  "WRONG, got %s" % (got,)))
    if not ok:
        fails.append("%s: wanted %s, got %s" % (name, want, got))


def check(fails: list[str], ctx: Context) -> None:
    by_code = parse_packets()
    order = derive_mesa_order()

    img = compile_probe(ctx.compiler, ctx.probe, ctx.image)
    m = Model()
    cpu, out = run(img, m)

    print("  0  the model's own blindness")
    correct = re.search(r"pixels correct\s+(\d+)", out)
    poison = re.search(r"pixels still poison\s+(\d+)", out)
    if not correct or not poison:
        fails.append("the probe never reached its pixel count under the model")
        print(out[-2000:])
        return
    row("pixels correct under the model", 0, int(correct.group(1)), fails)
    row("pixels still poison", 4096, int(poison.group(1)), fails)

    print("  1  constants against Mesa")
    row("CLE readahead", derive_readahead(), lib_constant("V3D_CLE_READAHEAD"),
        fails)
    row("tile state bytes per tile", derive_tsda_per_tile(),
        lib_constant("V3D_TILE_STATE_PER_TILE"), fails)
    sizes = derive_tile_sizes()
    row("tile size at index 0", (64, 64), sizes[0], fails)
    row("tile size table length", 7, len(sizes), fails)
    ity, ibpp = derive_internal_for_rgba8()
    row("rgba8 output format code", derive_output_format("rgba8"),
        lib_constant("V3D_OFMT_RGBA8"), fails)
    row("rgba8 internal type", ity, lib_constant("V3D_ITYPE_8"), fails)
    row("rgba8 internal bpp", ibpp, lib_constant("V3D_IBPP_32"), fails)
    row("raster memory format", enum_value("Memory Format", "Raster"),
        lib_constant("V3D_MEMFMT_RASTER"), fails)
    row("store buffer NONE", 8, lib_constant("V3D_BUF_NONE"), fails)
    row("max supertiles", 256, lib_constant("V3D_MAX_SUPERTILES"), fails)

    def printed(label, cast=int):
        mm = re.search(r"^\s+%s\s+(\S+)" % re.escape(label), out, re.M)
        if not mm:
            fails.append("the probe never printed %r" % label)
            return None
        return cast(mm.group(1))

    print("  2  the geometry the library computed")
    row("tile width", sizes[0][0], printed("tile width"), fails)
    row("tile height", sizes[0][1], printed("tile height"), fails)
    row("tiles across", 1, printed("tiles across"), fails)
    row("tiles down", 1, printed("tiles down"), fails)
    row("supertile w in tiles", 1, printed("supertile w in tiles"), fails)
    row("frame w in supertiles", 1, printed("frame w in supertiles"), fails)
    row("RT internal type", ity, printed("RT internal type"), fails)
    row("RT internal bpp", ibpp, printed("RT internal bpp"), fails)
    row("tile alloc needed", derive_tile_alloc_bytes(1, 1, 1),
        printed("tile alloc needed"), fails)
    row("tile state needed", derive_tsda_per_tile(),
        printed("tile state needed"), fails)

    print("  3  the three lists, decoded with the pinned v3d_packet.xml layouts")
    bcl_a, bcl_b = m.cle[0x00160], m.cle[0x00168]
    rcl_a, rcl_b = m.cle[0x00164], m.cle[0x0016C]
    target = probe_constant("CLR_TARGET")
    stride = probe_constant("CLR_STRIDE")
    colour = probe_constant("CLR_COLOR")
    talloc = probe_constant("CLR_TALLOC")
    tstate = probe_constant("CLR_TSTATE")
    tl = probe_constant("CLR_TILELIST")

    def grab(a, b):
        return bytes(cpu.memory.get(a + i, 0) for i in range(b - a))

    bcl = decode_list(by_code, grab(bcl_a, bcl_b))
    rcl = decode_list(by_code, grab(rcl_a, rcl_b))

    # The tile list's extent comes out of the RENDER list's own
    # START_ADDRESS_OF_GENERIC_TILE_LIST packet, not from the probe.
    gtl = [f for n, f, _ in rcl if n == "Start Address of Generic Tile List"]
    if len(gtl) != 1:
        fails.append("expected one Start Address of Generic Tile List, "
                     "found %d" % len(gtl))
        return
    tlist = decode_list(by_code, grab(gtl[0]["start"], gtl[0]["end"]))
    row("generic tile list start", tl, gtl[0]["start"], fails)

    for label, seq, nbytes in (("bin list", bcl, bcl_b - bcl_a),
                               ("tile list", tlist,
                                gtl[0]["end"] - gtl[0]["start"]),
                               ("render list", rcl, rcl_b - rcl_a)):
        print("     %-13s %d packets, %d bytes" % (label, len(seq), nbytes))
        for n, f, o in seq:
            print("       +%-4d %s" % (o, n))

    print("  4  packet order is a subsequence of Mesa's")
    upper = {
        "Number of Layers": "NUMBER_OF_LAYERS",
        "Tile Binning Mode Cfg": "TILE_BINNING_MODE_CFG",
        "Flush VCD cache": "FLUSH_VCD_CACHE",
        "Occlusion Query Counter": "OCCLUSION_QUERY_COUNTER",
        "Start Tile Binning": "START_TILE_BINNING",
        "Flush": "FLUSH",
        "Tile Coordinates Implicit": "TILE_COORDINATES_IMPLICIT",
        "End of Loads": "END_OF_LOADS",
        "Prim List Format": "PRIM_LIST_FORMAT",
        "Set InstanceID": "SET_INSTANCEID",
        "Branch to Implicit Tile List": "BRANCH_TO_IMPLICIT_TILE_LIST",
        "Store Tile Buffer General": "STORE_TILE_BUFFER_GENERAL",
        "Clear Tile Buffers": "CLEAR_TILE_BUFFERS",
        "End of Tile Marker": "END_OF_TILE_MARKER",
        "Return from sub-list": "RETURN_FROM_SUB_LIST",
        "Tile Rendering Mode Cfg (Common)": "TILE_RENDERING_MODE_CFG_COMMON",
        "Tile Rendering Mode Cfg (Clear Colors Part1)":
            "TILE_RENDERING_MODE_CFG_CLEAR_COLORS_PART1",
        "Tile Rendering Mode Cfg (Color)": "TILE_RENDERING_MODE_CFG_COLOR",
        "Tile Rendering Mode Cfg (ZS Clear Values)":
            "TILE_RENDERING_MODE_CFG_ZS_CLEAR_VALUES",
        "Tile List Initial Block Size": "TILE_LIST_INITIAL_BLOCK_SIZE",
        "Multicore Rendering Tile List Set Base":
            "MULTICORE_RENDERING_TILE_LIST_SET_BASE",
        "Multicore Rendering Supertile Cfg":
            "MULTICORE_RENDERING_SUPERTILE_CFG",
        "Tile Coordinates": "TILE_COORDINATES",
        "Start Address of Generic Tile List":
            "START_ADDRESS_OF_GENERIC_TILE_LIST",
        "Supertile Coordinates": "SUPERTILE_COORDINATES",
        "End of rendering": "END_OF_RENDERING",
    }

    def as_mesa(seq):
        names = []
        for n, _, _ in seq:
            if n not in upper:
                fails.append("no Mesa spelling known for packet %r" % n)
                return None
            names.append(upper[n])
        return names

    for label, got, want in (("bin list", as_mesa(bcl), order["bcl"]),
                             ("tile list", as_mesa(tlist), order["tile"]),
                             ("render list", as_mesa(rcl), order["rcl"])):
        if got is None:
            continue
        ROWS[0] += 1
        ok, missing = is_subsequence(got, want)
        print("     %-12s %d packets against Mesa's %d  %s"
              % (label, len(got), len(want),
                 "ok" if ok else "OUT OF ORDER at %s" % missing))
        if not ok:
            fails.append("%s is not a subsequence of Mesa's order; %s is out "
                         "of place.\n      library: %s\n      mesa:    %s"
                         % (label, missing, got, want))

    print("  5  field values, decoded with the pinned layouts")

    def one(seq, name, idx=0):
        hits = [f for n, f, _ in seq if n == name]
        if len(hits) <= idx:
            fails.append("no %s (index %d) in the list" % (name, idx))
            return {}
        return hits[idx]

    b = one(bcl, "Tile Binning Mode Cfg")
    row("binning width in pixels", 64, b.get("Width (in pixels)"), fails)
    row("binning height in pixels", 64, b.get("Height (in pixels)"), fails)
    row("binning render targets", 1, b.get("Number of Render Targets"), fails)
    row("binning max bpp", ibpp, b.get("Maximum BPP of all render targets"),
        fails)
    row("binning block size", 0, b.get("tile allocation block size"), fails)
    row("layers", 1, one(bcl, "Number of Layers").get("Number of Layers"),
        fails)
    row("occlusion query address", 0,
        one(bcl, "Occlusion Query Counter").get("address"), fails)

    c = one(rcl, "Tile Rendering Mode Cfg (Common)")
    row("image width pixels", 64, c.get("Image Width (pixels)"), fails)
    row("image height pixels", 64, c.get("Image Height (pixels)"), fails)
    row("render targets", 1, c.get("Number of Render Targets"), fails)
    row("early-Z disable", 1, c.get("Early-Z disable"), fails)
    row("multisample", 0, c.get("Multisample Mode (4x)"), fails)
    row("double buffer", 0, c.get("Double-buffer in non-ms mode"), fails)

    cc = one(rcl, "Tile Rendering Mode Cfg (Clear Colors Part1)")
    row("clear colour low 32", colour, cc.get("Clear Color low 32 bits"), fails)
    row("clear colour next 24", 0, cc.get("Clear Color next 24 bits"), fails)
    row("clear render target", 0, cc.get("Render Target number"), fails)

    col = one(rcl, "Tile Rendering Mode Cfg (Color)")
    row("RT0 internal bpp", ibpp, col.get("Render Target 0 Internal BPP"),
        fails)
    row("RT0 internal type", ity, col.get("Render Target 0 Internal Type"),
        fails)
    row("RT0 clamp", 0, col.get("Render Target 0 Clamp"), fails)

    zs = one(rcl, "Tile Rendering Mode Cfg (ZS Clear Values)")
    row("Z clear value", probe_constant("CLR_ZCLEAR"), zs.get("Z Clear Value"),
        fails)

    ib = one(rcl, "Tile List Initial Block Size")
    row("auto-chained tile lists", 1, ib.get("Use auto-chained tile lists"),
        fails)
    row("first block size", b.get("tile allocation initial block size"),
        ib.get("Size of first block in chained tile lists"), fails)

    tb = one(rcl, "Multicore Rendering Tile List Set Base")
    row("tile list set base", talloc, tb.get("address"), fails)
    row("tile list set number", 0, tb.get("Tile List Set Number"), fails)

    st = one(rcl, "Multicore Rendering Supertile Cfg")
    row("supertile width in tiles", 1, st.get("Supertile Width in Tiles"),
        fails)
    row("supertile height in tiles", 1, st.get("Supertile Height in Tiles"),
        fails)
    row("frame width in tiles", 1, st.get("Total Frame Width in Tiles"), fails)
    row("frame height in tiles", 1, st.get("Total Frame Height in Tiles"),
        fails)
    row("frame width in supertiles", 1,
        st.get("Total Frame Width in Supertiles"), fails)
    row("bin tile lists", 1, st.get("Number of Bin Tile Lists"), fails)
    row("multicore enable", 0, st.get("Multicore Enable"), fails)

    row("supertile coordinates emitted", 1,
        len([1 for n, _, _ in rcl if n == "Supertile Coordinates"]), fails)
    sc = one(rcl, "Supertile Coordinates")
    row("supertile column", 0, sc.get("column number in supertiles"), fails)
    row("supertile row", 0, sc.get("row number in supertiles"), fails)

    # THE GFXH-1742 LOOP: two dummy stores on 4.x.
    dummies = [f for n, f, _ in rcl if n == "Store Tile Buffer General"]
    row("GFXH-1742 dummy stores", GFXH_1742_ITERATIONS, len(dummies), fails)
    for i, d in enumerate(dummies):
        row("  dummy store %d buffer" % i, lib_constant("V3D_BUF_NONE"),
            d.get("Buffer to Store"), fails)
    row("clears in the render prologue", 1,
        len([1 for n, _, _ in rcl if n == "Clear Tile Buffers"]), fails)

    s = one(tlist, "Store Tile Buffer General")
    row("store buffer", 0, s.get("Buffer to Store"), fails)
    row("store address", target, s.get("Address"), fails)
    row("store output format", derive_output_format("rgba8"),
        s.get("Output Image Format"), fails)
    row("store memory format", enum_value("Memory Format", "Raster"),
        s.get("Memory Format"), fails)
    row("store stride", stride, s.get("Height in UB or Stride"), fails)
    row("store R/B swap", 0, s.get("R/B swap"), fails)
    row("store clear-being-stored", 0, s.get("Clear buffer being stored"),
        fails)
    row("store decimate mode", enum_value("Decimate Mode", "sample 0"),
        s.get("Decimate mode"), fails)
    row("store flip Y", 0, s.get("Flip Y"), fails)
    row("store height (y flip)", 0, s.get("Height"), fails)

    row("prim list format", 2,
        one(tlist, "Prim List Format").get("primitive type"), fails)
    row("instance id", 0, one(tlist, "Set InstanceID").get("Instance ID"),
        fails)
    row("implicit tile list set", 0,
        one(tlist, "Branch to Implicit Tile List").get("tile list set number"),
        fails)

    # -----------------------------------------------------------------
    #  5b. THE ENCODER CORPUS - packets the clear path never emits,
    #  carrying values chosen so that a wrong shift MOVES them.
    # -----------------------------------------------------------------
    print("  5b the encoder corpus")
    clen = printed("corpus bytes")
    corpus_at = probe_constant("CLR_CORPUS")
    corpus = decode_list(by_code, grab(corpus_at, corpus_at + clen))
    print("     %d packets, %d bytes" % (len(corpus), clen))

    def cf(name, field, want, idx=0):
        hits = [f for n, f, _ in corpus if n == name]
        if len(hits) <= idx:
            fails.append("corpus: no %s" % name)
            return
        row("corpus %s / %s" % (name, field), want, hits[idx].get(field), fails)

    cf("Tile Coordinates", "tile column number", 4095)
    cf("Tile Coordinates", "tile row number", 2731)
    cf("Supertile Coordinates", "column number in supertiles", 255)
    cf("Supertile Coordinates", "row number in supertiles", 170)
    cf("Store Tile Buffer General", "Buffer to Store", 1)
    cf("Store Tile Buffer General", "Address", 0x12345670)
    cf("Store Tile Buffer General", "Output Image Format",
       derive_output_format("bgr565"))
    cf("Store Tile Buffer General", "Memory Format",
       enum_value("Memory Format", "UIF (XOR)"))
    cf("Store Tile Buffer General", "Height in UB or Stride", 0xABCDE)
    cf("Store Tile Buffer General", "R/B swap", 1)
    cf("Store Tile Buffer General", "Clear buffer being stored", 1)
    cf("Tile Binning Mode Cfg", "Width (in pixels)", 1920)
    cf("Tile Binning Mode Cfg", "Height (in pixels)", 1080)
    cf("Tile Binning Mode Cfg", "Number of Render Targets", 4)
    cf("Tile Binning Mode Cfg", "Maximum BPP of all render targets", 2)
    cf("Tile Binning Mode Cfg", "tile allocation block size", 1)
    cf("Tile Binning Mode Cfg", "tile allocation initial block size", 2)
    cf("Tile Rendering Mode Cfg (Common)", "Image Width (pixels)", 1920)
    cf("Tile Rendering Mode Cfg (Common)", "Image Height (pixels)", 1080)
    cf("Tile Rendering Mode Cfg (Common)", "Number of Render Targets", 4)
    cf("Tile Rendering Mode Cfg (Common)", "Early-Z disable", 0)
    cf("Tile Rendering Mode Cfg (Common)", "Internal Depth Type", 3)
    cf("Tile Rendering Mode Cfg (Color)", "Render Target 0 Internal BPP", 2)
    cf("Tile Rendering Mode Cfg (Color)", "Render Target 0 Internal Type", 10)
    cf("Tile Rendering Mode Cfg (Color)", "Render Target 0 Clamp", 3)
    cf("Tile Rendering Mode Cfg (Clear Colors Part1)", "Render Target number", 7)
    cf("Tile Rendering Mode Cfg (Clear Colors Part1)",
       "Clear Color low 32 bits", 0x12345678)
    cf("Tile Rendering Mode Cfg (Clear Colors Part1)",
       "Clear Color next 24 bits", 0xABCDEF)
    cf("Tile Rendering Mode Cfg (ZS Clear Values)", "Z Clear Value", 0x3F800000)
    cf("Tile Rendering Mode Cfg (ZS Clear Values)", "Stencil Clear Value", 0x5A)
    cf("Multicore Rendering Supertile Cfg", "Supertile Width in Tiles", 3)
    cf("Multicore Rendering Supertile Cfg", "Supertile Height in Tiles", 5)
    cf("Multicore Rendering Supertile Cfg",
       "Total Frame Width in Supertiles", 30)
    cf("Multicore Rendering Supertile Cfg",
       "Total Frame Height in Supertiles", 17)
    cf("Multicore Rendering Supertile Cfg", "Total Frame Width in Tiles", 4000)
    cf("Multicore Rendering Supertile Cfg", "Total Frame Height in Tiles", 3000)
    cf("Multicore Rendering Supertile Cfg", "Number of Bin Tile Lists", 4)
    cf("Multicore Rendering Tile List Set Base", "address", 0x01234C00)
    cf("Multicore Rendering Tile List Set Base", "Tile List Set Number", 9)
    cf("GL Shader State", "address", 0x02468A00)
    cf("GL Shader State", "number of attribute arrays", 17)
    cf("Vertex Array Prims", "Length", 3)
    cf("Vertex Array Prims", "Index of First Vertex", 7)
    cf("Vertex Array Prims", "mode", 4)
    cf("clip_window", "Clip Window Left Pixel Coordinate", 11)
    cf("clip_window", "Clip Window Bottom Pixel Coordinate", 22)
    cf("clip_window", "Clip Window Width in pixels", 33)
    cf("clip_window", "Clip Window Height in pixels", 44)
    cf("VCM Cache Size", "Number of 16-vertex batches for binning", 3)
    cf("VCM Cache Size", "Number of 16-vertex batches for rendering", 12)
    cf("Tile List Initial Block Size", "Use auto-chained tile lists", 1)
    cf("Tile List Initial Block Size",
       "Size of first block in chained tile lists", 2)
    cf("Number of Layers", "Number of Layers", 200)
    cf("Prim List Format", "primitive type", 1)
    cf("Prim List Format", "tri strip or fan", 1)
    cf("Branch to Implicit Tile List", "tile list set number", 200)
    cf("Set InstanceID", "Instance ID", 0xDEADBEEF)
    cf("Start Address of Generic Tile List", "start", 0x11112220)
    cf("Start Address of Generic Tile List", "end", 0x33334440)
    cf("Occlusion Query Counter", "address", 0x07654320)
    cf("Branch", "address", 0x0ABCDEF0)
    cf("Clear Tile Buffers", "Clear Z/Stencil Buffer", 1)
    cf("Clear Tile Buffers", "Clear all Render Targets", 0)
    cf("Sample State", "Mask", 15)
    cf("Point size", "Point Size", 0x40000000)
    cf("Line width", "Line width", 0x40400000)
    cf("Cfg Bits", "Enable Forward Facing Primitive", 1)
    cf("Cfg Bits", "Enable Reverse Facing Primitive", 1)
    cf("Cfg Bits", "Clockwise Primitives", 1)
    cf("Cfg Bits", "Depth-Test Function", 5)
    cf("Clipper XY Scaling", "Viewport Half-Width in 1/256th of pixel",
       0x44000000)
    cf("Clipper XY Scaling", "Viewport Half-Height in 1/256th of pixel",
       0x45000000)
    cf("Clipper Z Scale and Offset", "Viewport Z Scale (Zc to Zs)", 0x3F000000)
    cf("Clipper Z Scale and Offset", "Viewport Z Offset (Zc to Zs)", 0xBF800000)
    cf("Clipper Z min/max clipping planes", "Maximum Zw", 0x3F800000)

    print("  5c the refusals")
    row("refusal cases correct", 13, printed("refusal cases correct"), fails)
    row("first wrong refusal case", -1, printed("first wrong case"), fails)

    print("  6  the CLE readahead slack")
    ra = derive_readahead()
    for label, a, bnd, cap in (
            ("bin list", bcl_a, bcl_b, probe_constant("CLR_BCL_BYTES")),
            ("render list", rcl_a, rcl_b, probe_constant("CLR_RCL_BYTES")),
            ("tile list", gtl[0]["start"], gtl[0]["end"],
             probe_constant("CLR_TL_BYTES"))):
        ROWS[0] += 1
        slack = cap - (bnd - a)
        ok = slack >= ra
        print("     %-12s %d bytes used of %d, %d spare (needs %d)  %s"
              % (label, bnd - a, cap, slack, ra, "ok" if ok else "TOO TIGHT"))
        if not ok:
            fails.append("%s leaves %d bytes of slack, less than the %d-byte "
                         "CLE readahead" % (label, slack, ra))

    print("  7  the submission registers")
    row("CT0QMA (tile alloc)", talloc, m.cle.get(0x00170), fails)
    row("CT0QMS (tile alloc size)", probe_constant("CLR_TALLOC_BYTES"),
        m.cle.get(0x00174), fails)
    row("CT0QTS (tile state | enable)", tstate | 2, m.cle.get(0x0015C), fails)
    row("PTB_BPOS cleared before the job", 0, m.ptb.get(0x0030C), fails)
    row("CLE_BFC moved", 1, m.bfc, fails)
    row("CLE_RFC moved", 1, m.rfc, fails)
    # The base register has to be written before the end register, which
    # is what starts the job.
    seq = [o for o in m.core_regs_written if o in (0x160, 0x168, 0x164, 0x16C)]
    row("CT0QBA/QEA/CT1QBA/QEA order", [0x160, 0x168, 0x164, 0x16C], seq,
        fails)


def negatives(fails: list[str], ctx: Context) -> None:
    print("  8  negative models")
    for label, kw, want in (
            ("the binner never completes", {"bfc_moves": False},
             "BIN_TIMEOUT"),
            ("RFC advances before render done", {"render_done": False},
             "RENDER_TIMEOUT")):
        ROWS[0] += 1
        cpu, out = run(ctx.image, Model(**kw))
        ok = want in out
        print("     %-34s %s" % (label, "ok" if ok else "DID NOT REPORT " + want))
        if not ok:
            fails.append("%s: the probe did not report %s" % (label, want))
    ROWS[0] += 1
    cpu, out = run(ctx.image, Model(rfc_moves=False))
    ok = "render wait: OK" in out
    print("     %-34s %s" % ("FRDONE completes without RFC movement",
                             "ok" if ok else "DID NOT COMPLETE"))
    if not ok:
        fails.append("FRDONE did not complete the render wait when RFC stayed still")
    ROWS[0] += 1
    cpu, out = run(ctx.image, Model(bfc_moves=False))
    ok = "render submit" not in out
    print("     %-34s %s" % ("no render after a failed bin",
                             "ok" if ok else "THE RENDER WAS SUBMITTED ANYWAY"))
    if not ok:
        fails.append("a failed bin did not stop the render submission")


# =====================================================================
#  MUTATION - each is a textual edit to a TEMPORARY COPY of v3d.pi4; the
#  probe is copied beside it with its include pointed at the copy.  The
#  library under RaspberryPi4/ is never written.
# =====================================================================
MUTANTS = [
    ("store stride field one bit narrow",
     "lo = lo | ((strideOrUbHeight & $F) << 28)",
     "lo = lo | ((strideOrUbHeight & 7) << 28)"),
    ("supertile cfg loses its minus_one",
     "lo = ((stW - 1) & $FF)",
     "lo = ((stW) & $FF)"),
    ("binning cfg render target count not minus one",
     "lo = lo | (((nrRts - 1) & $F) << 8)",
     "lo = lo | (((nrRts) & $F) << 8)"),
    ("common cfg image width shifted wrong",
     "lo = lo | ((imgW & $FFFF) << 8)",
     "lo = lo | ((imgW & $FFFF) << 4)"),
    ("clear colour byte lost across the word boundary",
     "hi = (low32 >> 24) & $FF",
     "hi = 0"),
    ("the second GFXH-1742 iteration dropped",
     "While i < 2\n    If i > 0",
     "While i < 1\n    If i > 0"),
    ("the clear moved out of the render prologue",
     "    If i = 0\n      ; do_double_initial_tile_clear()",
     "    If i = 2\n      ; do_double_initial_tile_clear()"),
    ("ZS clear values emitted before the colour config",
     "  V3dClTrmcClearColor1(0, v3d_clearColor, 0)\n"
     "  V3dClTrmcColor(v3d_rtBpp, v3d_rtType, v3d_rtClamp)\n"
     "  V3dClTrmcZsClear(v3d_clearZ, v3d_clearS)",
     "  V3dClTrmcZsClear(v3d_clearZ, v3d_clearS)\n"
     "  V3dClTrmcClearColor1(0, v3d_clearColor, 0)\n"
     "  V3dClTrmcColor(v3d_rtBpp, v3d_rtType, v3d_rtClamp)"),
    ("tile coordinates emitted as one 16-bit field",
     "v = (col & $FFF) | ((row & $FFF) << 12)",
     "v = (col & $FFF) | ((row & $FFF) << 16)"),
    # THE READAHEAD IS GUARDED TWICE AND EITHER GUARD ALONE CATCHES THE
    # CORPUS CASE, so a single-fault mutation of either one survives.
    # v3d_ClU8 refuses the byte that would cross into the slack, and
    # V3dClFinish refuses a list that ends inside it.  A hand deleting
    # "the readahead thing" would delete both, so this mutation does.
    ("both readahead guards deleted",
     ["  If (v3d_clPos + 1) > (v3d_clCap - #V3D_CLE_READAHEAD)",
      "  If (v3d_clPos + #V3D_CLE_READAHEAD) > v3d_clCap"],
     ["  If (v3d_clPos + 1) > v3d_clCap",
      "  If (v3d_clPos + 0) > v3d_clCap"]),
    ("the tile alloc minimum dropped its 512 KB margin",
     "  n = n + (512 * 1024)",
     "  n = n + 0"),
    ("PTB_BPOS not cleared before the bin job",
     "  V3dCoreWrite(#V3D_PTB_BPOS, 0)",
     "  V3dCoreWrite(#V3D_PTB_BPOS, 4096)"),
    ("CT0QEA written before CT0QBA",
     "  V3dCoreWrite(#V3D_CLE_CT0QBA, v3d_bclStart)\n"
     "  V3dCoreWrite(#V3D_CLE_CT0QEA, v3d_bclEnd)",
     "  V3dCoreWrite(#V3D_CLE_CT0QEA, v3d_bclEnd)\n"
     "  V3dCoreWrite(#V3D_CLE_CT0QBA, v3d_bclStart)"),
    ("the tile state enable bit dropped",
     "V3dCoreWrite(#V3D_CLE_CT0QTS, #V3D_CLE_CT0QTS_ENABLE | v3d_tsAddr)",
     "V3dCoreWrite(#V3D_CLE_CT0QTS, v3d_tsAddr)"),
    ("the store address written into the wrong word",
     "  v3d_ClU32(lo)\n  v3d_ClU32(mid)\n  v3d_ClU32(addr)",
     "  v3d_ClU32(lo)\n  v3d_ClU32(addr)\n  v3d_ClU32(mid)"),
    # --- reachable only through the encoder corpus ------------------
    ("store memory format field one bit narrow",
     "lo = lo | ((memFmt & 7) << 4)",
     "lo = lo | ((memFmt & 3) << 4)"),
    ("store output format shifted one nibble",
     "lo = lo | ((outFmt & $3F) << 12)",
     "lo = lo | ((outFmt & $3F) << 16)"),
    ("common cfg internal depth type shifted",
     "hi = hi | ((depthType & $F) << 15)",
     "hi = hi | ((depthType & $F) << 16)"),
    ("colour cfg RT0 type and clamp transposed",
     "  lo = lo | ((type0 & $F) << 6)\n  lo = lo | ((clamp0 & 3) << 10)",
     "  lo = lo | ((clamp0 & 3) << 6)\n  lo = lo | ((type0 & $F) << 10)"),
    ("supertile cfg frame height in tiles overlaps the width",
     "hi = hi | ((fhTiles & $FFF) << 12)",
     "hi = hi | ((fhTiles & $FFF) << 11)"),
    ("clear colour next-24 field dropped",
     "hi = hi | ((next24 & $FFFFFF) << 8)",
     "hi = hi | 0"),
    ("tile list set base loses its alignment refusal",
     "  If (addr % 64) <> 0\n    v3d_clErr = #V3D_ERR_CL_ARGS\n    ProcedureReturn\n  EndIf\n  If setNo < 0 Or setNo > 15",
     "  If setNo < 0 Or setNo > 15"),
    ("shader state record loses its alignment refusal",
     "  If (recordAddr % 32) <> 0\n    v3d_clErr = #V3D_ERR_CL_ARGS\n    ProcedureReturn\n  EndIf",
     "  If recordAddr < 0\n    v3d_clErr = #V3D_ERR_CL_ARGS\n    ProcedureReturn\n  EndIf"),
    ("the tile coordinate range refusal deleted",
     "  If col < 0 Or col > 4095\n    v3d_clErr = #V3D_ERR_CL_ARGS\n    ProcedureReturn\n  EndIf\n  If row < 0 Or row > 4095",
     "  If row < 0 Or row > 4095"),
    ("vertex array prims first-vertex and length transposed",
     "  v3d_ClU32(length)\n  v3d_ClU32(firstVertex)",
     "  v3d_ClU32(firstVertex)\n  v3d_ClU32(length)"),
    ("clip window fields emitted in reverse",
     "  v3d_ClU16(left)\n  v3d_ClU16(bottom)\n  v3d_ClU16(width)\n  v3d_ClU16(height)",
     "  v3d_ClU16(height)\n  v3d_ClU16(width)\n  v3d_ClU16(bottom)\n  v3d_ClU16(left)"),
    ("VCM cache size nibbles swapped",
     "v3d_ClU8((binBatches & $F) | ((renderBatches & $F) << 4))",
     "v3d_ClU8((renderBatches & $F) | ((binBatches & $F) << 4))"),
    ("prim list format strip bit at the wrong end",
     "    b = b | $80",
     "    b = b | $40"),
    ("cfg bits depth function shifted",
     "  v = v | ((depthFunc & 7) << 12)",
     "  v = v | ((depthFunc & 7) << 13)"),
    ("the control list writer made word-wise",
     "Procedure v3d_ClU32(v.i)\n  v3d_ClU8(v)\n  v3d_ClU8(v >> 8)\n"
     "  v3d_ClU8(v >> 16)\n  v3d_ClU8(v >> 24)",
     "Procedure v3d_ClU32(v.i)\n  PokeN(v3d_clBase + v3d_clPos, v)\n"
     "  v3d_clPos = v3d_clPos + 4\n  v3d_ClU8(0)\n  v3d_clPos = v3d_clPos - 1"),
]


def mutant_probe(work: pathlib.Path, lib_file: pathlib.Path, lib_text: str,
                 probe: pathlib.Path, include: str) -> pathlib.Path:
    """Write a library copy and a probe copy that includes it."""
    work.mkdir(parents=True, exist_ok=True)
    lib_file.write_text(lib_text, encoding="utf-8")
    src = text(probe)
    if src.count(include) != 1:
        raise SystemExit("The probe %s does not include %s exactly once, so a "
                         "mutant copy of the library cannot be substituted."
                         % (probe.name, include))
    src = src.replace(include, 'XIncludeFile "%s"'
                      % lib_file.resolve().as_posix())
    out = work / ("mutant_" + probe.name)
    out.write_text(src, encoding="utf-8")
    return out


def mutate(compiler: str, work: pathlib.Path) -> int:
    original = text(LIB)
    survivors = []
    for i, (label, old, new) in enumerate(MUTANTS):
        olds = old if isinstance(old, list) else [old]
        news = new if isinstance(new, list) else [new]
        if any(original.count(o) != 1 for o in olds):
            print("  %2d  %-52s ANCHOR MISSING" % (i, label))
            survivors.append(label + " (anchor missing)")
            continue
        mutated = original
        for o, nw in zip(olds, news):
            mutated = mutated.replace(o, nw, 1)
        mdir = work / ("mutant%02d" % i)
        probe = mutant_probe(mdir, mdir / "v3d_mutant.pi4", mutated, PROBE,
                             LIB_INCLUDE)
        fails: list[str] = []
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                check(fails, Context(compiler, mdir, probe))
        except SystemExit as e:
            fails.append(str(e))
        except Exception as e:                      # noqa: BLE001
            fails.append("%s: %s" % (type(e).__name__, e))
        killed = bool(fails)
        print("  %2d  %-52s %s" % (i, label, "killed" if killed else "SURVIVED"))
        if not killed:
            survivors.append(label)
    print()
    print("  %d faults, %d killed, %d survived"
          % (len(MUTANTS), len(MUTANTS) - len(survivors), len(survivors)))
    for s in survivors:
        print("    SURVIVED: %s" % s)
    return 1 if survivors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge executable (default: PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    if not a.compiler:
        raise SystemExit("No compiler was named. Pass --compiler or set "
                         "PMF_COMPILER to the PureMetalForge executable.")
    with tempfile.TemporaryDirectory(prefix="anvil-v3d-rcl-") as td:
        work = pathlib.Path(td)
        if a.mutate:
            return mutate(a.compiler, work)
        fails: list[str] = []
        ctx = Context(a.compiler, work)
        print("a64_v3d_rcl_check - the V3D control lists")
        print()
        check(fails, ctx)
        negatives(fails, ctx)
    print()
    if fails:
        print("FAIL - %d of %d checks" % (len(fails), ROWS[0]))
        for f in fails:
            print("  * %s" % f)
        return 1
    print("PASS - %d checks" % ROWS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
