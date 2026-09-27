#!/usr/bin/env python3
"""Independent V3D 7.1 control-list packet and state-record model (Pi 5 oracle).

The desk oracle for the BCM2712 (V3D 7.1, VideoCore VII) arm of Anvil's
control-list encoders.  It imports nothing from Anvil.  Every layout below is
transcribed from Mesa's src/broadcom/cle/v3d_packet.xml at commit
61f259049cf0eb0c69ad2fae50d1268f82fd54e3 -- ONLY the min_ver="71" variants
(and the version-independent packets named here) -- with the XML line range
beside each entry.  The packing rules are Mesa's generator,
src/broadcom/cle/gen_pack_header.py at the same commit:

* :101-110   a packet's <field> start is counted from the bit AFTER the
             opcode byte (start += 8); a struct's is not; "Nb" means byte N.
* :228       length = (highest end bit // 8) + 1 (the opcode byte included).
* :293-294   minus_one fields are stored as value - 1.
* :299-301   an address field is the 32-bit address OR-ed in at the byte
             holding the field's start; its low bits carry the other
             fields, so the address must be aligned to 1 << (32 - size).
* :316-317   f187 = the top 16 bits of an IEEE binary32.

`--xml PATH` re-parses the pinned XML and proves every table below equals it
field for field (name, start, size, type, minus_one, default), so a
transcription slip cannot hide.  The vault copy is
"Raspberry Pi 5/Sources/mesa-61f25904/cle_v3d_packet.xml".

The derived helpers follow Mesa's 7.1 driver code:
* tile size choice      src/broadcom/common/v3d_util.c:101-206
* RT row stride          src/broadcom/common/v3d_util.c:316-325
* RT base-address walk   src/broadcom/vulkan/v3dvx_cmd_buffer.c:1083-1199
* clear-colour split     src/broadcom/vulkan/v3dvx_cmd_buffer.c:1151-1186
* viewport scale (1/64)  src/broadcom/common/v3d_device_info.c:85-93,
                         src/broadcom/vulkan/v3dvx_cmd_buffer.c:1367-1372
* CLE read-ahead 1024    src/broadcom/common/v3d_device_info.c:90-92
* D0 (7.1.10) record     src/broadcom/common/v3d_device_info.h:93-97
                         (IDENT3 IPREV >= 10 selects the Draw Index record)

Run:  py -3 -B tools/v3d71_cle.py --self-test [--xml <v3d_packet.xml>]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


class PackError(ValueError):
    """A value does not fit its field, or a field is unknown."""


class DecodeError(ValueError):
    """Bytes are not the packet asked for."""


@dataclass(frozen=True)
class Field:
    name: str
    start: str          # exactly as written in the XML ("3b" or "67")
    size: int
    type: str
    minus_one: bool = False
    default: Optional[int] = None


@dataclass(frozen=True)
class Layout:
    xml_name: str       # the XML "name" attribute
    kind: str           # "packet" or "struct"
    code: Optional[int]
    xml_lines: str
    fields: tuple

    def bit_start(self, f: Field) -> int:
        s = int(f.start[:-1]) * 8 if f.start.endswith("b") else int(f.start)
        return s + 8 if self.kind == "packet" else s

    @property
    def length(self) -> int:
        ends = [self.bit_start(f) + f.size - 1 for f in self.fields]
        if self.kind == "packet":
            ends.append(7)
        return max(ends) // 8 + 1


def F(name, start, size, type_, minus_one=False, default=None) -> Field:
    return Field(name, str(start), size, type_, minus_one, default)


# ------------------------------------------------ the 7.1 tables (v3d_packet.xml)

LAYOUTS: dict[str, Layout] = {}


def _add(key: str, layout: Layout) -> None:
    LAYOUTS[key] = layout


_add("CLEAR_RENDER_TARGETS", Layout(
    "Clear Render Targets", "packet", 25, "485", ()))

_add("STORE_TILE_BUFFER_GENERAL", Layout(
    "Store Tile Buffer General", "packet", 29, "491-526", (
        F("Address", 64, 32, "address"),
        F("Height", 48, 16, "uint"),
        F("Height in UB or Stride", 28, 20, "uint"),
        F("R/B swap", 20, 1, "bool"),
        F("Channel Reverse", 19, 1, "bool"),
        F("Clear buffer being stored", 18, 1, "bool"),
        F("Output Image Format", 12, 6, "Output Image Format"),
        F("Decimate mode", 10, 2, "Decimate Mode"),
        F("Dither Mode", 8, 2, "Dither Mode"),
        F("Flip Y", 7, 1, "bool"),
        F("Memory Format", 4, 3, "Memory Format"),
        F("Buffer to Store", 0, 4, "uint"),
    )))

_add("BLEND_CFG", Layout(
    "Blend Cfg", "packet", 84, "787-795", (
        F("Render Target Mask", 24, 8, "uint"),
        F("Color blend dst factor", 20, 4, "Blend Factor"),
        F("Color blend src factor", 16, 4, "Blend Factor"),
        F("Color blend mode", 12, 4, "Blend Mode"),
        F("Alpha blend dst factor", 8, 4, "Blend Factor"),
        F("Alpha blend src factor", 4, 4, "Blend Factor"),
        F("Alpha blend mode", 0, 4, "Blend Mode"),
    )))

_add("CFG_BITS", Layout(
    "Cfg Bits", "packet", 96, "849-866", (
        F("Z Clipping mode", 22, 2, "Z Clip Mode"),
        F("Direct3D Provoking Vertex", 21, 1, "bool"),
        F("Direct3D 'Point-fill' mode", 20, 1, "bool"),
        F("Blend enable", 19, 1, "bool"),
        F("Stencil enable", 18, 1, "bool"),
        F("Z updates enable", 15, 1, "bool"),
        F("Depth-Test Function", 12, 3, "Compare Function"),
        F("Direct3D Wireframe triangles mode", 11, 1, "bool"),
        F("Z Clamp Mode", 10, 1, "bool"),
        F("Rasterizer Oversample Mode", 6, 2, "uint"),
        F("Depth Bounds Test Enable", 5, 1, "bool"),
        F("Line Rasterization", 4, 1, "uint"),
        F("Enable Depth Offset", 3, 1, "bool"),
        F("Clockwise Primitives", 2, 1, "bool"),
        F("Enable Reverse Facing Primitive", 1, 1, "bool"),
        F("Enable Forward Facing Primitive", 0, 1, "bool"),
    )))

_add("CLIPPER_XY_SCALING", Layout(
    "Clipper XY Scaling", "packet", 110, "924-927", (
        F("Viewport Half-Height in 1/64th of pixel", 32, 32, "float"),
        F("Viewport Half-Width in 1/64th of pixel", 0, 32, "float"),
    )))

_add("CLIPPER_Z_SCALE_AND_OFFSET_NO_GUARDBAND", Layout(
    "Clipper Z Scale and Offset no guardband", "packet", 112, "934-937", (
        F("Viewport Z Offset (Zc to Zs)", 32, 32, "float"),
        F("Viewport Z Scale (Zc to Zs)", 0, 32, "float"),
    )))

_add("TILE_BINNING_MODE_CFG", Layout(
    "Tile Binning Mode Cfg", "packet", 120, "967-994", (
        F("Height (in pixels)", 48, 16, "uint", minus_one=True),
        F("Width (in pixels)", 32, 16, "uint", minus_one=True),
        F("Log2 Tile Height", 11, 3, "uint"),
        F("Log2 Tile Width", 8, 3, "uint"),
        F("tile allocation block size", 4, 2, "uint"),
        F("tile allocation initial block size", 2, 2, "uint"),
    )))

_add("TILE_RENDERING_MODE_CFG_COMMON", Layout(
    "Tile Rendering Mode Cfg (Common)", "packet", 121, "1025-1060", (
        F("Pad", 58, 6, "uint"),
        F("Log2 Tile Height", 55, 3, "uint"),
        F("Log2 Tile Width", 52, 3, "uint"),
        F("Early Depth/Stencil Clear", 51, 1, "bool"),
        F("Internal Depth Type", 47, 4, "Internal Depth Type"),
        F("Early-Z disable", 46, 1, "bool"),
        F("Early-Z Test and Update Direction", 45, 1, "uint"),
        F("Depth-buffer disable", 44, 1, "bool"),
        F("Double-buffer in non-ms mode", 43, 1, "bool"),
        F("Multisample Mode (4x)", 42, 1, "bool"),
        F("Image Height (pixels)", 24, 16, "uint"),
        F("Image Width (pixels)", 8, 16, "uint"),
        F("Number of Render Targets", 4, 4, "uint", minus_one=True),
        F("sub-id", 0, 3, "uint", default=0),
    )))

_add("TILE_RENDERING_MODE_CFG_ZS_CLEAR_VALUES", Layout(
    "Tile Rendering Mode Cfg (ZS Clear Values)", "packet", 121, "1094-1101", (
        F("unused", 48, 16, "uint"),
        F("Z Clear Value", 16, 32, "float"),
        F("Stencil Clear Value", 8, 8, "uint"),
        F("sub-id", 0, 4, "uint", default=1),
    )))

_add("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1", Layout(
    "Tile Rendering Mode Cfg (Render Target Part1)", "packet", 121, "1112-1123", (
        F("Clear Color low bits", 32, 32, "uint"),
        F("Internal Type and Clamping", 27, 5, "Render Target Type Clamp"),
        F("Internal BPP", 25, 2, "Internal BPP"),
        F("Stride", 18, 7, "uint", minus_one=True),
        F("Base Address", 7, 11, "uint"),
        F("Render Target number", 3, 3, "uint"),
        F("sub-id", 0, 3, "uint", default=2),
    )))

_add("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART2", Layout(
    "Tile Rendering Mode Cfg (Render Target Part2)", "packet", 121, "1134-1139", (
        F("Clear Color mid bits", 24, 40, "uint"),
        F("Render Target number", 3, 3, "uint"),
        F("sub-id", 0, 3, "uint", default=3),
    )))

_add("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART3", Layout(
    "Tile Rendering Mode Cfg (Render Target Part3)", "packet", 121, "1152-1157", (
        F("Clear Color top bits", 8, 56, "uint"),
        F("Render Target number", 3, 3, "uint"),
        F("sub-id", 0, 3, "uint", default=4),
    )))

_SHREC_COMMON_TAIL = (
    F("Number of varyings in Fragment Shader", "3b", 8, "uint"),
    F("Coordinate Shader output VPM segment size", "4b", 4, "uint"),
    F("Min Coord Shader output segments required in play in addition to VCM cache size", 36, 4, "uint"),
    F("Coordinate Shader input VPM segment size", "5b", 4, "uint"),
    F("Min Coord Shader input segments required in play", 44, 4, "uint", minus_one=True),
    F("Vertex Shader output VPM segment size", "6b", 4, "uint"),
    F("Min Vertex Shader output segments required in play in addition to VCM cache size", 52, 4, "uint"),
    F("Vertex Shader input VPM segment size", "7b", 4, "uint"),
    F("Min Vertex Shader input segments required in play", 60, 4, "uint", minus_one=True),
    F("Fragment Shader Code Address", 67, 29, "address"),
    F("Fragment Shader 4-way threadable", 64, 1, "bool"),
    F("Fragment Shader start in final thread section", 65, 1, "bool"),
    F("Fragment Shader Propagate NaNs", 66, 1, "bool"),
    F("Fragment Shader Uniforms Address", "12b", 32, "address"),
    F("Vertex Shader Code Address", 131, 29, "address"),
    F("Vertex Shader 4-way threadable", 128, 1, "bool"),
    F("Vertex Shader start in final thread section", 129, 1, "bool"),
    F("Vertex Shader Propagate NaNs", 130, 1, "bool"),
    F("Vertex Shader Uniforms Address", "20b", 32, "address"),
    F("Coordinate Shader Code Address", 195, 29, "address"),
    F("Coordinate Shader 4-way threadable", 192, 1, "bool"),
    F("Coordinate Shader start in final thread section", 193, 1, "bool"),
    F("Coordinate Shader Propagate NaNs", 194, 1, "bool"),
    F("Coordinate Shader Uniforms Address", "28b", 32, "address"),
)

_add("GL_SHADER_STATE_RECORD", Layout(
    "GL Shader State Record", "struct", None, "1256-1311", (
        F("Point size in shaded vertex data", 0, 1, "bool"),
        F("Enable clipping", 1, 1, "bool"),
        F("Vertex ID read by coordinate shader", 2, 1, "bool"),
        F("Instance ID read by coordinate shader", 3, 1, "bool"),
        F("Base Instance ID read by coordinate shader", 4, 1, "bool"),
        F("Vertex ID read by vertex shader", 5, 1, "bool"),
        F("Instance ID read by vertex shader", 6, 1, "bool"),
        F("Base Instance ID read by vertex shader", 7, 1, "bool"),
        F("Fragment shader does Z writes", 8, 1, "bool"),
        F("Turn off early-z test", 9, 1, "bool"),
        F("Fragment shader uses real pixel centre W in addition to centroid W2", 12, 1, "bool"),
        F("Enable Sample Rate Shading", 13, 1, "bool"),
        F("Any shader reads hardware-written Primitive ID", 14, 1, "bool"),
        F("Insert Primitive ID as first varying to fragment shader", 15, 1, "bool"),
        F("Turn off scoreboard", 16, 1, "bool"),
        F("Do scoreboard wait on first thread switch", 17, 1, "bool"),
        F("Disable implicit point/line varyings", 18, 1, "bool"),
        F("No prim pack", 19, 1, "bool"),
        F("Never defer FEP depth writes", 20, 1, "bool"),
    ) + _SHREC_COMMON_TAIL))

_add("GL_SHADER_STATE_RECORD_DRAW_INDEX", Layout(
    "GL Shader State Record Draw Index", "struct", None, "1314-1374", (
        F("Point size in shaded vertex data", 0, 1, "bool"),
        F("Enable clipping", 1, 1, "bool"),
        F("Vertex ID read by coordinate shader", 2, 1, "bool"),
        F("Instance ID read by coordinate shader", 3, 1, "bool"),
        F("Base Instance ID read by coordinate shader", 4, 1, "bool"),
        F("cs_basevertex", 5, 1, "bool"),
        F("cs_drawindex", 6, 1, "bool"),
        F("Vertex ID read by vertex shader", 7, 1, "bool"),
        F("Instance ID read by vertex shader", 8, 1, "bool"),
        F("Base Instance ID read by vertex shader", 9, 1, "bool"),
        F("vs_basevertex", 10, 1, "bool"),
        F("vs_drawindex", 11, 1, "bool"),
        F("Fragment shader does Z writes", 12, 1, "bool"),
        F("Turn off early-z test", 13, 1, "bool"),
        F("Fragment shader uses real pixel centre W in addition to centroid W2", 15, 1, "bool"),
        F("Enable Sample Rate Shading", 16, 1, "bool"),
        F("Any shader reads hardware-written Primitive ID", 17, 1, "bool"),
        F("Insert Primitive ID as first varying to fragment shader", 18, 1, "bool"),
        F("Turn off scoreboard", 19, 1, "bool"),
        F("Do scoreboard wait on first thread switch", 20, 1, "bool"),
        F("Disable implicit point/line varyings", 21, 1, "bool"),
        F("No prim pack", 22, 1, "bool"),
        F("Never defer FEP depth writes", 23, 1, "bool"),
    ) + _SHREC_COMMON_TAIL))

_add("TEXTURE_SHADER_STATE", Layout(
    "Texture Shader State", "struct", None, "1633-1707", (
        F("Pad", 190, 2, "uint"),
        F("texture_base pointer_Cr", 164, 26, "uint"),
        F("texture base pointer Cb", 138, 26, "uint"),
        F("Chroma offset y", 137, 1, "uint"),
        F("Chroma offset x", 136, 1, "uint"),
        F("UIF XOR disable", 135, 1, "bool"),
        F("Level 0 is strictly UIF", 134, 1, "bool"),
        F("Level 0 XOR enable", 132, 1, "bool"),
        F("Level 0 UB_PAD", 128, 4, "uint"),
        F("Base Level", 124, 4, "uint"),
        F("Max Level", 120, 4, "uint"),
        F("Swizzle A", 117, 3, "uint"),
        F("Swizzle B", 114, 3, "uint"),
        F("Swizzle G", 111, 3, "uint"),
        F("Swizzle R", 108, 3, "uint"),
        F("Extended", 107, 1, "bool"),
        F("Texture type", 100, 7, "uint"),
        F("Image Depth", 86, 14, "uint"),
        F("Image Height", 72, 14, "uint"),
        F("Image Width", 58, 14, "uint"),
        F("Array Stride (64-byte aligned)", 33, 24, "uint"),
        F("R/B swap", 32, 1, "bool"),
        F("Texture base pointer", 0, 32, "address"),
        F("Reverse", 5, 1, "bool"),
        F("Transfer func", 2, 3, "uint"),
        F("Flip texture Y Axis", 1, 1, "bool"),
        F("Flip texture X Axis", 0, 1, "bool"),
    )))

# Expected sizes, stated independently of the tables so a dropped field shows.
EXPECTED_LENGTH = {
    "CLEAR_RENDER_TARGETS": 1, "STORE_TILE_BUFFER_GENERAL": 13,
    "BLEND_CFG": 5, "CFG_BITS": 4, "CLIPPER_XY_SCALING": 9,
    "CLIPPER_Z_SCALE_AND_OFFSET_NO_GUARDBAND": 9,
    "TILE_BINNING_MODE_CFG": 9, "TILE_RENDERING_MODE_CFG_COMMON": 9,
    "TILE_RENDERING_MODE_CFG_ZS_CLEAR_VALUES": 9,
    "TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1": 9,
    "TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART2": 9,
    "TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART3": 9,
    "GL_SHADER_STATE_RECORD": 32, "GL_SHADER_STATE_RECORD_DRAW_INDEX": 32,
    "TEXTURE_SHADER_STATE": 24,
}

# Render Target Type Clamp (v3d_packet.xml:154-178) and Internal BPP (:135-139).
RT_TYPE_CLAMP_8 = 8
INTERNAL_BPP_32, INTERNAL_BPP_64, INTERNAL_BPP_128 = 0, 1, 2

# ------------------------------------------------ packing


def _f32_bits(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


def _bits_f32(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


def pack(key: str, **values) -> bytes:
    """Pack one packet or struct.  Values are keyed by the XML field name
    with non-alphanumerics replaced by '_' (see field_key)."""
    lay = LAYOUTS[key]
    by_key = {field_key(f.name): f for f in lay.fields}
    for k in values:
        if k not in by_key:
            raise PackError(f"{key} has no field '{k}'")
    word = lay.code if lay.kind == "packet" else 0
    for f in lay.fields:
        k = field_key(f.name)
        # An absent field packs as zero bits, as Mesa's zero-initialised
        # struct does; for a minus_one field that means the value 1.
        dflt = f.default if f.default is not None else (1 if f.minus_one else 0)
        v = values.get(k, dflt)
        start = lay.bit_start(f)
        if f.type == "address":
            v = int(v)
            align = 32 - f.size
            if v & ((1 << align) - 1):
                raise PackError(f"{key}.{f.name}: address {v:#x} is not "
                                f"{1 << align}-byte aligned")
            shared = _address_shared_bits(lay, f)
            if v & shared:
                raise PackError(f"{key}.{f.name}: address {v:#x} has bits set "
                                f"under other fields (mask {shared:#x})")
            if not 0 <= v < (1 << 32):
                raise PackError(f"{key}.{f.name}: address {v:#x} exceeds 32 bits")
            byte = start // 8
            if (start - byte * 8) + f.size != 32 and start % 8 + f.size > 32:
                raise PackError("address straddles more than a dword")
            word |= v << (byte * 8)
            continue
        if f.type == "float":
            if start % 8 or f.size != 32:
                raise PackError(f"{key}.{f.name}: float must be a whole dword")
            raw = _f32_bits(float(v))
        elif f.type == "f187":
            raw = _f32_bits(float(v)) >> 16
        elif f.type == "bool":
            raw = 1 if v else 0
        elif f.type == "int":
            raw = int(v)
            if not -(1 << (f.size - 1)) <= raw < (1 << (f.size - 1)):
                raise PackError(f"{key}.{f.name}: {raw} does not fit {f.size} signed bits")
            raw &= (1 << f.size) - 1
        else:   # uint and enums
            raw = int(v)
            if f.minus_one:
                if raw < 1:
                    raise PackError(f"{key}.{f.name}: minus_one field needs >= 1, got {raw}")
                raw -= 1
            if not 0 <= raw < (1 << f.size):
                raise PackError(f"{key}.{f.name}: {values.get(k, v)} does not fit "
                                f"{f.size} bits{' (minus one)' if f.minus_one else ''}")
        word |= raw << start
    return word.to_bytes(lay.length, "little")


def unpack(key: str, data: bytes) -> dict:
    lay = LAYOUTS[key]
    if len(data) != lay.length:
        raise DecodeError(f"{key} is {lay.length} bytes, got {len(data)}")
    word = int.from_bytes(data, "little")
    if lay.kind == "packet" and data[0] != lay.code:
        raise DecodeError(f"{key} opcode is {lay.code}, got {data[0]}")
    out = {}
    addr_bits = 0
    for f in lay.fields:
        start = lay.bit_start(f)
        if f.type == "address":
            byte = start // 8
            out[field_key(f.name)] = ((word >> (byte * 8)) & 0xFFFFFFFF
                                      & ~((1 << (32 - f.size)) - 1)
                                      & ~_address_shared_bits(lay, f))
            continue
        raw = (word >> start) & ((1 << f.size) - 1)
        if f.type == "float":
            v = _bits_f32(raw)
        elif f.type == "f187":
            v = _bits_f32(raw << 16)
        elif f.type == "bool":
            v = bool(raw)
        elif f.type == "int":
            v = raw - (1 << f.size) if raw >> (f.size - 1) else raw
        else:
            v = raw + 1 if f.minus_one else raw
        out[field_key(f.name)] = v
    if lay.kind == "packet":
        for f in lay.fields:
            if f.default is not None and out[field_key(f.name)] != f.default:
                raise DecodeError(f"{key}: sub-id {out[field_key(f.name)]}, want {f.default}")
    return out


def _address_shared_bits(lay: Layout, a: Field) -> int:
    """Bits of the address dword that other fields own (the XML lets the
    Texture Shader State base pointer share bits 0-5 with the flip/transfer
    flags, xml 1694-1706).  Those bits of the address must be zero."""
    base = (lay.bit_start(a) // 8) * 8
    m = 0
    for f in lay.fields:
        if f is a or f.type == "address":
            continue
        s = lay.bit_start(f)
        for b in range(s, s + f.size):
            if base <= b < base + 32:
                m |= 1 << (b - base)
    return m


def field_key(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


# ------------------------------------------------ derived 7.1 helpers

TILE_SIZES = [(64, 64), (64, 32), (32, 32), (32, 16), (16, 16), (16, 8), (8, 8)]
TLB_COLOR, TLB_DEPTH, TLB_AUX_DEPTH = 16 * 1024, 16 * 1024, 8 * 1024


def choose_tile_size(total_color_bpp: int, msaa: bool = False,
                     double_buffer: bool = False) -> tuple[int, int]:
    """v3d_util.c:101-206, the ver >= 71 arm.  total_color_bpp is BYTES per
    pixel summed over every colour attachment."""
    color = total_color_bpp * (4 if msaa else 1)
    depth = 4 * (4 if msaa else 1)
    idx = 0
    while idx < len(TILE_SIZES):
        w, h = TILE_SIZES[idx]
        px = w * h
        if (px * depth <= TLB_AUX_DEPTH and px * color <= TLB_COLOR + TLB_DEPTH) or \
                (px * depth <= TLB_DEPTH and px * color <= TLB_COLOR):
            break
        idx += 1
    if double_buffer:
        idx += 1
    if idx >= len(TILE_SIZES):
        raise PackError("no tile size fits this render-target set")
    return TILE_SIZES[idx]


def log2_tile(n: int) -> int:
    """8 -> 0, 16 -> 1, 32 -> 2, 64 -> 3 (v3d_packet.xml:971-982)."""
    if n not in (8, 16, 32, 64):
        raise PackError(f"tile dimension {n} is not 8, 16, 32 or 64")
    return {8: 0, 16: 1, 32: 2, 64: 3}[n]


def bpp_words(internal_bpp: int) -> int:
    return {INTERNAL_BPP_32: 1, INTERNAL_BPP_64: 2, INTERNAL_BPP_128: 4}[internal_bpp]


def rt_stride(tile_width: int, internal_bpp: int) -> int:
    """v3d_util.c:316-325: 128-bit units covering two rows."""
    return tile_width * bpp_words(internal_bpp) // 2


def render_target_packets(tile_w: int, tile_h: int, rts: list[dict]) -> list[bytes]:
    """The per-RT TRMC packets, v3dvx_cmd_buffer.c:1083-1199.  Each rt dict:
    {"type_clamp": int, "bpp": int, "clear": [u32, u32, u32, u32]} or None
    for an unused attachment.  With no colour RT at all, one Part1 with
    stride 1 marks it unused (:1190-1198)."""
    out = []
    base = 0
    for i, rt in enumerate(rts):
        if rt is None:
            out.append(pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1",
                            render_target_number=i, stride=1))
            continue
        c = list(rt.get("clear", [0, 0, 0, 0])) + [0, 0, 0, 0]
        stride = rt_stride(tile_w, rt["bpp"])
        out.append(pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1",
                        clear_color_low_bits=c[0],
                        internal_type_and_clamping=rt["type_clamp"],
                        internal_bpp=rt["bpp"], stride=stride,
                        base_address=base, render_target_number=i))
        base += tile_h * stride // 8     # 512-bit units (:1162-1167)
        if rt["bpp"] >= INTERNAL_BPP_64:
            out.append(pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART2",
                            clear_color_mid_bits=c[1] | ((c[2] & 0xFF) << 32),
                            render_target_number=i))
        if rt["bpp"] >= INTERNAL_BPP_128:
            out.append(pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART3",
                            clear_color_top_bits=((c[2] & 0xFFFFFF00) >> 8) | (c[3] << 24),
                            render_target_number=i))
    if not rts:
        out.append(pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1", stride=1))
    return out


def clipper_xy(half_width_px: float, half_height_px: float) -> bytes:
    """Clipper XY Scaling in 1/64 pixel (v3d_device_info.c:90-91)."""
    return pack("CLIPPER_XY_SCALING",
                viewport_half_width_in_1_64th_of_pixel=half_width_px * 64.0,
                viewport_half_height_in_1_64th_of_pixel=half_height_px * 64.0)


def shader_record_key(ipre: int) -> str:
    """IDENT3 IPREV >= 10 is BCM2712 D0 (V3D 7.1.10): the Draw Index record
    (v3d_device_info.h:93-97; v3dvx_cmd_buffer.c:2473-2480)."""
    return "GL_SHADER_STATE_RECORD_DRAW_INDEX" if ipre >= 10 else "GL_SHADER_STATE_RECORD"


CLE_READAHEAD = 1024       # v3d_device_info.c:90-92 (4.2: 256)

# ------------------------------------------------ XML proof


def verify_xml(path: str) -> int:
    """Every embedded layout must equal the min_ver=71-applicable entry in
    the XML: same name, code, and field list (name/start/size/type/
    minus_one/default)."""
    data = open(path, "rb").read()
    print(f"xml {path}\n  sha256 {hashlib.sha256(data).hexdigest()}")
    root = ET.fromstring(data)
    failures = 0

    def applies71(el) -> bool:
        lo = int(el.get("min_ver", "0"))
        hi = int(el.get("max_ver", "999"))
        return lo <= 71 <= hi

    candidates = [el for el in root if el.tag in ("packet", "struct") and applies71(el)]
    for key, lay in LAYOUTS.items():
        m = [el for el in candidates if el.tag == lay.kind and el.get("name") == lay.xml_name]
        if len(m) != 1:
            print(f"FAIL {key}: {len(m)} 7.1 XML entries named {lay.xml_name!r}")
            failures += 1
            continue
        el = m[0]
        if lay.kind == "packet" and int(el.get("code")) != lay.code:
            print(f"FAIL {key}: code {el.get('code')} != {lay.code}")
            failures += 1
        xf = []
        for f in el.findall("field"):
            if f.get("min_ver") or f.get("max_ver"):
                if not applies71(f):
                    continue
            xf.append(Field(f.get("name"), f.get("start"), int(f.get("size")),
                            f.get("type"), f.get("minus_one") == "true",
                            int(f.get("default")) if f.get("default") is not None else None))
        if tuple(xf) != lay.fields:
            print(f"FAIL {key}: field list differs from the XML")
            for a, b in zip(xf, lay.fields):
                if a != b:
                    print(f"   xml {a}\n   tab {b}")
            if len(xf) != len(lay.fields):
                print(f"   xml has {len(xf)} fields, table {len(lay.fields)}")
            failures += 1
    print(f"xml proof: {len(LAYOUTS)} layouts, {failures} failure(s)")
    return failures


# ------------------------------------------------ self-test


def self_test() -> int:
    fails = 0

    def check(cond: bool, what: str) -> None:
        nonlocal fails
        if not cond:
            print("FAIL", what)
            fails += 1

    for key, n in EXPECTED_LENGTH.items():
        check(LAYOUTS[key].length == n, f"{key} length {LAYOUTS[key].length} != {n}")
    check(set(EXPECTED_LENGTH) == set(LAYOUTS), "every layout has a stated length")

    # No two fields of one layout overlap, except the address fields whose
    # low bits the XML deliberately shares with flag bits.
    for key, lay in LAYOUTS.items():
        used = {}
        for f in lay.fields:
            if f.type == "address":
                continue
            s = lay.bit_start(f)
            for b in range(s, s + f.size):
                if b in used:
                    check(False, f"{key}: {f.name} overlaps {used[b]} at bit {b}")
                    break
                used[b] = f.name

    # Round trip: every field at its maximum and at a walking pattern.
    for key, lay in LAYOUTS.items():
        for pattern in ("max", "one"):
            vals = {}
            for f in lay.fields:
                k = field_key(f.name)
                if f.default is not None:
                    continue
                if f.type == "address":
                    low = (1 << (32 - f.size)) - 1 | _address_shared_bits(lay, f)
                    vals[k] = (0xFFFFFFFF & ~low) if pattern == "max" else (low + 1) & ~low
                elif f.type == "float":
                    vals[k] = -1.5 if pattern == "max" else 61440.0
                elif f.type == "bool":
                    vals[k] = pattern == "max"
                else:
                    top = (1 << f.size) - 1
                    vals[k] = (top + 1 if f.minus_one else top) if pattern == "max" else 1
            # address low bits collide with flags in the same dword by design;
            # keep them disjoint by clearing flags under an address dword.
            data = pack(key, **vals)
            back = unpack(key, data)
            for k, v in vals.items():
                if back[k] != v and not (isinstance(v, bool) and back[k] == v):
                    # address + flags share a dword: the flags round-trip
                    # separately, the address is masked
                    f = next(f for f in lay.fields if field_key(f.name) == k)
                    check(False, f"{key}.{k} round trip {v!r} -> {back[k]!r} ({pattern})")

    # Refusals.
    for bad in (lambda: pack("TILE_BINNING_MODE_CFG", width_in_pixels=0),
                lambda: pack("TILE_BINNING_MODE_CFG", log2_tile_width=8),
                lambda: pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1", stride=129),
                lambda: pack("GL_SHADER_STATE_RECORD", fragment_shader_code_address=0x1004),
                lambda: pack("CLEAR_RENDER_TARGETS", clear_z_stencil_buffer=True),
                lambda: pack("TILE_BINNING_MODE_CFG", number_of_render_targets=1),
                lambda: log2_tile(128)):
        try:
            bad()
            check(False, "a refusal was accepted")
        except PackError:
            pass

    # Hand-derived vectors (bit positions read off the XML, not the tables).
    # Clear Render Targets is the bare opcode 25 (xml 485).
    check(pack("CLEAR_RENDER_TARGETS") == bytes([25]), "clear_rt bytes")
    # 1920x1080 binning, 64x64 tiles, 128B initial / 64B overflow blocks
    # (Mesa v3d_limits.h:94-100 -> enums 1 and 0):
    # after the opcode, bits 2-3 init=1 -> 0x04; bits 8-10=3, 11-13=3 -> 0x1B00;
    # width-1=1919 at 32, height-1=1079 at 48.
    exp = bytes([120]) + (0x04 | (3 << 8) | (3 << 11) | (1919 << 32) | (1079 << 48)).to_bytes(8, "little")
    check(pack("TILE_BINNING_MODE_CFG", width_in_pixels=1920, height_in_pixels=1080,
               log2_tile_width=3, log2_tile_height=3,
               tile_allocation_initial_block_size=1,
               tile_allocation_block_size=0) == exp, "binning cfg vector")
    # TRMC common: sub-id 0, 1 RT (field 0), width 1920 at 8, height 1080 at 24,
    # log2 64 at 52 and 55, early-Z disable (46).
    exp = bytes([121]) + ((1920 << 8) | (1080 << 24) | (1 << 46) | (3 << 52) | (3 << 55)).to_bytes(8, "little")
    check(pack("TILE_RENDERING_MODE_CFG_COMMON", image_width_pixels=1920,
               image_height_pixels=1080, number_of_render_targets=1,
               early_z_disable=True, log2_tile_width=3, log2_tile_height=3) == exp,
          "TRMC common vector")
    # Viewport 1920x1080: half extents 960 and 540 pixels = 61440.0 and 34560.0
    # in 1/64 px; the 4.2 encoding would have been 245760.0 / 138240.0.
    b = clipper_xy(960, 540)
    check(b == bytes([110]) + struct.pack("<ff", 61440.0, 34560.0), "clipper 1/64 vector")
    # RGBA8 single RT on a 64x64 tile: stride = 64*1/2 = 32 -> stored 31;
    # type_clamp 8 (xml 161), bpp 0, base 0, RT 0, sub-id 2; clear 0xFF0000FF.
    p1 = render_target_packets(64, 64, [{"type_clamp": RT_TYPE_CLAMP_8,
                                         "bpp": INTERNAL_BPP_32,
                                         "clear": [0xFF0000FF, 0, 0, 0]}])
    exp = bytes([121]) + (2 | (31 << 18) | (8 << 27) | (0xFF0000FF << 32)).to_bytes(8, "little")
    check(p1 == [exp], "RT part1 vector")
    # Two RTs, the second 128bpp: base of RT1 = 64 * 32 / 8 = 256 (512-bit units).
    p = render_target_packets(64, 64, [
        {"type_clamp": 8, "bpp": 0, "clear": [1, 0, 0, 0]},
        {"type_clamp": 10, "bpp": 2, "clear": [0x11111111, 0x22222222, 0x33333333, 0x44444444]}])
    check(len(p) == 4, "RT set emits part1, part1, part2, part3")
    u = unpack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1", p[1])
    check(u["base_address"] == 256 and u["stride"] == 128 and u["render_target_number"] == 1,
          f"RT1 base/stride {u}")
    u2 = unpack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART2", p[2])
    check(u2["clear_color_mid_bits"] == 0x22222222 | (0x33 << 32), "part2 clear split")
    u3 = unpack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART3", p[3])
    check(u3["clear_color_top_bits"] == (0x333333) | (0x44444444 << 24), "part3 clear split")
    check(render_target_packets(64, 64, []) ==
          [pack("TILE_RENDERING_MODE_CFG_RENDER_TARGET_PART1", stride=1)], "no-RT marker")
    # Tile choice: one RGBA8 RT, no MSAA -> 64x64; eight 128bpp RTs + MSAA ->
    # 128 B/px * 4 = 512 B/px, only 8x8 fits (64*512 = 32 KB with aux depth).
    check(choose_tile_size(4) == (64, 64), "tile size 1xRGBA8")
    check(choose_tile_size(128, msaa=True) == (8, 8), "tile size 8x128bpp MSAA")
    check(choose_tile_size(4, double_buffer=True) == (64, 32), "tile size double buffer")
    # Shader record: 32 bytes; FS code at byte 8, FS uniforms byte 12, VS 16/20,
    # CS 24/28 (4.2 had them 4 bytes later behind the default-attribute address).
    r = pack("GL_SHADER_STATE_RECORD", fragment_shader_code_address=0x1000,
             fragment_shader_uniforms_address=0x2000, vertex_shader_code_address=0x3000,
             vertex_shader_uniforms_address=0x4000, coordinate_shader_code_address=0x5000,
             coordinate_shader_uniforms_address=0x6000, fragment_shader_4_way_threadable=True,
             enable_clipping=True)
    w = struct.unpack("<8I", r)
    check(w[2] == 0x1001 and w[3] == 0x2000 and w[4] == 0x3000 and w[5] == 0x4000
          and w[6] == 0x5000 and w[7] == 0x6000 and w[0] == 2, f"shader record words {w}")
    # D0 layout: the same flag lands on a different bit.
    a = struct.unpack("<I", pack("GL_SHADER_STATE_RECORD", fragment_shader_does_z_writes=True)[:4])[0]
    d = struct.unpack("<I", pack("GL_SHADER_STATE_RECORD_DRAW_INDEX", fragment_shader_does_z_writes=True)[:4])[0]
    check(a == 1 << 8 and d == 1 << 12, "D0 moves FS Z-write from bit 8 to 12")
    check(shader_record_key(9) == "GL_SHADER_STATE_RECORD"
          and shader_record_key(10) == "GL_SHADER_STATE_RECORD_DRAW_INDEX", "IPREV selects record")
    # TSR: sRGB is transfer func 1 at bits 2-4; R/B swap bit 32; array stride at 33.
    t = int.from_bytes(pack("TEXTURE_SHADER_STATE", transfer_func=1, r_b_swap=True,
                            array_stride_64_byte_aligned=1), "little")
    check(t == (1 << 2) | (1 << 32) | (1 << 33), f"TSR bits {t:#x}")
    # ZS clear values: sub-id is 1 on 7.1 (2 on 4.2).
    check(pack("TILE_RENDERING_MODE_CFG_ZS_CLEAR_VALUES", z_clear_value=1.0)[1] & 0xF == 1,
          "ZS clear sub-id 1")
    print(f"v3d71_cle self-test: {len(LAYOUTS)} layouts, {fails} failure(s)")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--xml", metavar="PATH",
                    help="prove the embedded tables equal the pinned v3d_packet.xml")
    ap.add_argument("--list", action="store_true", help="print layouts and lengths")
    ns = ap.parse_args(argv)
    rc = 0
    if ns.self_test:
        rc |= self_test()
    if ns.xml:
        rc |= 1 if verify_xml(ns.xml) else 0
    if ns.list:
        for k, lay in LAYOUTS.items():
            print(f"{k:48s} {lay.kind:6s} code={lay.code} len={lay.length} xml:{lay.xml_lines}")
    if not (ns.self_test or ns.xml or ns.list):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
