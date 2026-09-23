#!/usr/bin/env python3
"""The SPIR-V front end: the accepted subset, the refusals, and the plan.

It assembles SPIR-V modules HERE, word by word, from the numbers in the
Khronos specification's own instruction and enumerant tables, writes them
into the emitted gate's memory, runs the gate on the A64 interpreter and
compares every field of the plan the front end produced against what this
file independently expects.

The modules are assembled in Python and walked in PureMetal, so the two
sides of every check are written in different languages by different
code, which is the whole point: a fixture the implementation produced
would only ever prove that the implementation agrees with itself.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \\
      py -3 tools/vulkan_spirv_check.py

Add --mutate to also require every plausible mistake - in the modules and
in the front end's own source - to be caught.
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
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_spirv_gate.pi4"
FRONTEND = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_spirv.pbi"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 200_000_000
MMIO = 0xFC000000

IN = 0x06000000
FIXTURES = 0x06010000
OUT = 0x06100000
MAGIC = 0x564B5350
SLOTS = 24
HEAD = 64

# Anvil result codes, from vk_foundation.pbi.
OK = 0
ERR_ARGS = -20001
ERR_UNSUPPORTED = -20005

# ----------------------------------------------------------------------
#  A SPIR-V assembler, from the specification's own numbers.
# ----------------------------------------------------------------------
MAGIC_SPV = 0x07230203
VERSION_10 = 0x00010000

OP = {
    "Nop": 0, "Undef": 1, "Source": 3, "Name": 5, "MemberName": 6,
    "Extension": 10, "ExtInstImport": 11, "ExtInst": 12,
    "MemoryModel": 14, "EntryPoint": 15, "ExecutionMode": 16, "Capability": 17,
    "TypeVoid": 19, "TypeBool": 20, "TypeInt": 21, "TypeFloat": 22,
    "TypeVector": 23, "TypeMatrix": 24, "TypeImage": 25, "TypeSampler": 26,
    "TypeSampledImage": 27,
    "TypeArray": 28, "TypeStruct": 30, "TypePointer": 32, "TypeFunction": 33,
    "Constant": 43, "ConstantComposite": 44,
    "Function": 54, "FunctionEnd": 56, "Variable": 59,
    "Load": 61, "Store": 62, "AccessChain": 65,
    "Decorate": 71, "MemberDecorate": 72,
    "VectorShuffle": 79, "CompositeConstruct": 80, "CompositeExtract": 81,
    "SampledImage": 86, "ImageSampleImplicitLod": 87,
    "FMul": 133, "MatrixTimesVector": 145,
    "SelectionMerge": 247, "Label": 248, "Branch": 249,
    "BranchConditional": 250, "Return": 253, "FunctionEnd_": 56,
}

CAP_SHADER, CAP_GEOMETRY, CAP_FLOAT64 = 1, 2, 10
ADDR_LOGICAL, MEM_GLSL450 = 0, 1
EM_VERTEX, EM_FRAGMENT, EM_GLCOMPUTE = 0, 4, 5
MODE_ORIGIN_UPPER_LEFT = 7
SC_INPUT, SC_OUTPUT, SC_PUSH, SC_FUNCTION, SC_UNIFORM = 1, 3, 9, 7, 2
DEC_BLOCK, DEC_BUILTIN, DEC_LOCATION, DEC_OFFSET, DEC_DESCRIPTOR_SET = 2, 11, 30, 35, 34
DEC_BINDING, DEC_BUFFER_BLOCK = 33, 3
SC_UNIFORM_CONSTANT, SC_STORAGE_BUFFER = 0, 12
BUILTIN_POSITION, BUILTIN_POINTSIZE = 0, 1

F0 = 0x00000000
F1 = 0x3F800000
FHALF = 0x3F000000


def ins(op: int, *words: int) -> list[int]:
    return [((len(words) + 1) << 16) | op, *words]


def lit(name: str) -> list[int]:
    """A SPIR-V literal string: NUL terminated, padded to a whole word."""
    raw = name.encode("utf-8") + b"\0"
    raw += b"\0" * ((-len(raw)) % 4)
    return list(struct.unpack("<%dI" % (len(raw) // 4), raw))


def module(bound: int, body: list[list[int]], version: int = VERSION_10) -> bytes:
    words = [MAGIC_SPV, version, 0, bound, 0]
    for chunk in body:
        words.extend(chunk)
    return struct.pack("<%dI" % len(words), *words)


def vertex_passthrough(zbits: int = F0, wbits: int = F1) -> bytes:
    """in vec2 position, in vec4 colour -> gl_Position and one varying."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_VERTEX, 19, *lit("main"), 15, 16, 17, 18),
        ins(OP["MemberDecorate"], 9, 0, DEC_BUILTIN, BUILTIN_POSITION),
        ins(OP["Decorate"], 9, DEC_BLOCK),
        ins(OP["Decorate"], 15, DEC_LOCATION, 0),
        ins(OP["Decorate"], 16, DEC_LOCATION, 1),
        ins(OP["Decorate"], 17, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 2),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypePointer"], 6, SC_INPUT, 4),
        ins(OP["TypePointer"], 7, SC_INPUT, 5),
        ins(OP["TypePointer"], 8, SC_OUTPUT, 5),
        ins(OP["TypeStruct"], 9, 5),
        ins(OP["TypePointer"], 10, SC_OUTPUT, 9),
        ins(OP["TypeInt"], 11, 32, 1),
        ins(OP["Constant"], 11, 12, 0),
        ins(OP["Constant"], 3, 13, zbits),
        ins(OP["Constant"], 3, 14, wbits),
        ins(OP["Variable"], 6, 15, SC_INPUT),
        ins(OP["Variable"], 7, 16, SC_INPUT),
        ins(OP["Variable"], 8, 17, SC_OUTPUT),
        ins(OP["Variable"], 10, 18, SC_OUTPUT),
        ins(OP["Function"], 1, 19, 0, 2),
        ins(OP["Label"], 20),
        ins(OP["Load"], 4, 21, 15),
        ins(OP["CompositeExtract"], 3, 22, 21, 0),
        ins(OP["CompositeExtract"], 3, 23, 21, 1),
        ins(OP["CompositeConstruct"], 5, 24, 22, 23, 13, 14),
        ins(OP["AccessChain"], 8, 25, 18, 12),
        ins(OP["Store"], 25, 24),
        ins(OP["Load"], 5, 26, 16),
        ins(OP["Store"], 17, 26),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(27, b)


def vertex_texture() -> bytes:
    """in vec2 position, in vec2 UV -> gl_Position and one vec2 varying."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_VERTEX, 19, *lit("main"), 15, 16, 17, 18),
        ins(OP["MemberDecorate"], 9, 0, DEC_BUILTIN, BUILTIN_POSITION),
        ins(OP["Decorate"], 9, DEC_BLOCK),
        ins(OP["Decorate"], 15, DEC_LOCATION, 0),
        ins(OP["Decorate"], 16, DEC_LOCATION, 1),
        ins(OP["Decorate"], 17, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 2),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypePointer"], 6, SC_INPUT, 4),
        ins(OP["TypePointer"], 7, SC_INPUT, 4),
        ins(OP["TypePointer"], 8, SC_OUTPUT, 4),
        ins(OP["TypeStruct"], 9, 5),
        ins(OP["TypePointer"], 10, SC_OUTPUT, 9),
        ins(OP["TypePointer"], 27, SC_OUTPUT, 5),
        ins(OP["TypeInt"], 11, 32, 1),
        ins(OP["Constant"], 11, 12, 0),
        ins(OP["Constant"], 3, 13, F0),
        ins(OP["Constant"], 3, 14, F1),
        ins(OP["Variable"], 6, 15, SC_INPUT),
        ins(OP["Variable"], 7, 16, SC_INPUT),
        ins(OP["Variable"], 8, 17, SC_OUTPUT),
        ins(OP["Variable"], 10, 18, SC_OUTPUT),
        ins(OP["Function"], 1, 19, 0, 2),
        ins(OP["Label"], 20),
        ins(OP["Load"], 4, 21, 15),
        ins(OP["CompositeExtract"], 3, 22, 21, 0),
        ins(OP["CompositeExtract"], 3, 23, 21, 1),
        ins(OP["CompositeConstruct"], 5, 24, 22, 23, 13, 14),
        ins(OP["AccessChain"], 27, 25, 18, 12),
        ins(OP["Store"], 25, 24),
        ins(OP["Load"], 4, 26, 16),
        ins(OP["Store"], 17, 26),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(28, b)


def vertex_position_only() -> bytes:
    """in vec2 position -> gl_Position, and no varying at all."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_VERTEX, 16, *lit("main"), 13, 14),
        ins(OP["MemberDecorate"], 8, 0, DEC_BUILTIN, BUILTIN_POSITION),
        ins(OP["Decorate"], 8, DEC_BLOCK),
        ins(OP["Decorate"], 13, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 2),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypePointer"], 6, SC_INPUT, 4),
        ins(OP["TypeStruct"], 8, 5),
        ins(OP["TypePointer"], 9, SC_OUTPUT, 8),
        ins(OP["TypePointer"], 7, SC_OUTPUT, 5),
        ins(OP["TypeInt"], 10, 32, 1),
        ins(OP["Constant"], 10, 11, 0),
        ins(OP["Constant"], 3, 12, F0),
        ins(OP["Constant"], 3, 15, F1),
        ins(OP["Variable"], 6, 13, SC_INPUT),
        ins(OP["Variable"], 9, 14, SC_OUTPUT),
        ins(OP["Function"], 1, 16, 0, 2),
        ins(OP["Label"], 17),
        ins(OP["Load"], 4, 18, 13),
        ins(OP["CompositeExtract"], 3, 19, 18, 0),
        ins(OP["CompositeExtract"], 3, 20, 18, 1),
        ins(OP["CompositeConstruct"], 5, 21, 19, 20, 12, 15),
        ins(OP["AccessChain"], 7, 22, 14, 11),
        ins(OP["Store"], 22, 21),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(23, b)


def fragment_varying() -> bytes:
    """in vec4 colour -> out vec4 colour."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 9, *lit("main"), 7, 8),
        ins(OP["ExecutionMode"], 9, MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], 7, DEC_LOCATION, 0),
        ins(OP["Decorate"], 8, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
        ins(OP["TypePointer"], 5, SC_INPUT, 4),
        ins(OP["TypePointer"], 6, SC_OUTPUT, 4),
        ins(OP["Variable"], 5, 7, SC_INPUT),
        ins(OP["Variable"], 6, 8, SC_OUTPUT),
        ins(OP["Function"], 1, 9, 0, 2),
        ins(OP["Label"], 10),
        ins(OP["Load"], 4, 11, 7),
        ins(OP["Store"], 8, 11),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(12, b)


def fragment_push() -> bytes:
    """push_constant { vec4 colour; } -> out vec4 colour."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 13, *lit("main"), 9),
        ins(OP["ExecutionMode"], 13, MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], 5, DEC_BLOCK),
        ins(OP["MemberDecorate"], 5, 0, DEC_OFFSET, 0),
        ins(OP["Decorate"], 9, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
        ins(OP["TypeStruct"], 5, 4),
        ins(OP["TypePointer"], 6, SC_PUSH, 5),
        ins(OP["TypePointer"], 7, SC_OUTPUT, 4),
        ins(OP["TypePointer"], 12, SC_PUSH, 4),
        ins(OP["TypeInt"], 10, 32, 1),
        ins(OP["Constant"], 10, 11, 0),
        ins(OP["Variable"], 6, 8, SC_PUSH),
        ins(OP["Variable"], 7, 9, SC_OUTPUT),
        ins(OP["Function"], 1, 13, 0, 2),
        ins(OP["Label"], 14),
        ins(OP["AccessChain"], 12, 15, 8, 11),
        ins(OP["Load"], 4, 16, 15),
        ins(OP["Store"], 9, 16),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(17, b)


def fragment_uniform(set_: int = 0, binding: int = 0, block: bool = True,
                     storage: int = SC_UNIFORM, member_vec2: bool = False,
                     decorate: bool = True, read: bool = True,
                     second_block: bool = False, member1: bool = False) -> bytes:
    """layout(set, binding) uniform U { vec4 colour; } -> out vec4 colour.

    WITH ITS DEFAULTS THIS IS EXACTLY vk_spirv_fixtures.pbi's vtpBuildFsC,
    word for word, and the gate reports that module so the two can be
    compared. Every knob moves ONE thing for a refusal fixture: which
    set, which binding, whether the struct carries Block, which storage
    class, whether the first member is a vec2, whether the decorations
    are there at all, and whether the shader reads what it declared.
    """
    bound = 17
    head = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 13, *lit("main"), 9),
        ins(OP["ExecutionMode"], 13, MODE_ORIGIN_UPPER_LEFT),
    ]
    if block:
        head.append(ins(OP["Decorate"], 5, DEC_BLOCK))
    head.append(ins(OP["MemberDecorate"], 5, 0, DEC_OFFSET, 0))
    if member1:
        head.append(ins(OP["MemberDecorate"], 5, 1, DEC_OFFSET, 16))
    if second_block:
        head.append(ins(OP["Decorate"], 20, DEC_BLOCK))
        head.append(ins(OP["Decorate"], 22, DEC_DESCRIPTOR_SET, 0))
        head.append(ins(OP["Decorate"], 22, DEC_BINDING, 1))
    if decorate:
        head.append(ins(OP["Decorate"], 8, DEC_DESCRIPTOR_SET, set_))
        head.append(ins(OP["Decorate"], 8, DEC_BINDING, binding))
    head.append(ins(OP["Decorate"], 9, DEC_LOCATION, 0))

    member = 4
    body = head + [
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
    ]
    if member_vec2:
        body.append(ins(OP["TypeVector"], 17, 3, 2))
        member = 17
        bound = 18
    if member1:
        body.append(ins(OP["TypeStruct"], 5, member, member))
    else:
        body.append(ins(OP["TypeStruct"], 5, member))
    body += [
        ins(OP["TypePointer"], 6, storage, 5),
        ins(OP["TypePointer"], 7, SC_OUTPUT, 4),
        ins(OP["TypePointer"], 12, storage, member),
        ins(OP["TypeInt"], 10, 32, 1),
        ins(OP["Constant"], 10, 11, 0),
    ]
    chain_index = 11
    if member1:
        body.append(ins(OP["Constant"], 10, 18, 1))
        chain_index = 18
        bound = 19
    if second_block:
        body += [
            ins(OP["TypeStruct"], 20, 4),
            ins(OP["TypePointer"], 21, storage, 20),
            ins(OP["Variable"], 21, 22, storage),
        ]
        bound = 23
    if not read:
        body += [
            ins(OP["Constant"], 3, 18, FHALF),
            ins(OP["ConstantComposite"], 4, 19, 18, 18, 18, 18),
        ]
        bound = 20
    body += [
        ins(OP["Variable"], 6, 8, storage),
        ins(OP["Variable"], 7, 9, SC_OUTPUT),
        ins(OP["Function"], 1, 13, 0, 2),
        ins(OP["Label"], 14),
    ]
    if read:
        body += [
            ins(OP["AccessChain"], 12, 15, 8, chain_index),
            ins(OP["Load"], 4, 16, 15),
            ins(OP["Store"], 9, 16),
        ]
    else:
        body += [ins(OP["Store"], 9, 19)]
    body += [ins(OP["Return"]), ins(OP["FunctionEnd"])]
    return module(bound, body)


def fragment_sampled(set_: int = 0, binding: int = 0, dim: int = 1,
                     coord_components: int = 2, decorate: bool = True,
                     sample: bool = True, image_operands: bool = False) -> bytes:
    """One combined sampler2D sampled with a whole Location-zero vec2."""
    head = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 14, *lit("main"), 12, 13),
        ins(OP["ExecutionMode"], 14, MODE_ORIGIN_UPPER_LEFT),
    ]
    if decorate:
        head += [
            ins(OP["Decorate"], 11, DEC_DESCRIPTOR_SET, set_),
            ins(OP["Decorate"], 11, DEC_BINDING, binding),
        ]
    head += [
        ins(OP["Decorate"], 12, DEC_LOCATION, 0),
        ins(OP["Decorate"], 13, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, coord_components),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypeImage"], 6, 3, dim, 0, 0, 0, 1, 0),
        ins(OP["TypeSampledImage"], 7, 6),
        ins(OP["TypePointer"], 8, SC_UNIFORM_CONSTANT, 7),
        ins(OP["TypePointer"], 9, SC_INPUT, 4),
        ins(OP["TypePointer"], 10, SC_OUTPUT, 5),
        ins(OP["Variable"], 8, 11, SC_UNIFORM_CONSTANT),
        ins(OP["Variable"], 9, 12, SC_INPUT),
        ins(OP["Variable"], 10, 13, SC_OUTPUT),
        ins(OP["Function"], 1, 14, 0, 2),
        ins(OP["Label"], 15),
        ins(OP["Load"], 7, 16, 11),
        ins(OP["Load"], 4, 17, 12),
    ]
    if sample:
        operands = [5, 18, 16, 17]
        if image_operands:
            operands.append(0)
        head += [
            ins(OP["ImageSampleImplicitLod"], *operands),
            ins(OP["Store"], 13, 18),
        ]
    else:
        head += [
            ins(OP["Constant"], 3, 19, FHALF),
            ins(OP["ConstantComposite"], 5, 20, 19, 19, 19, 19),
            ins(OP["Store"], 13, 20),
        ]
    head += [ins(OP["Return"]), ins(OP["FunctionEnd"])]
    return module(21 if not sample else 19, head)


def vertex_uniform() -> bytes:
    """A uniform block in a VERTEX shader, which has no uniform path."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_VERTEX, 16, *lit("main"), 13, 14),
        ins(OP["MemberDecorate"], 8, 0, DEC_BUILTIN, BUILTIN_POSITION),
        ins(OP["Decorate"], 8, DEC_BLOCK),
        ins(OP["Decorate"], 13, DEC_LOCATION, 0),
        ins(OP["Decorate"], 20, DEC_BLOCK),
        ins(OP["Decorate"], 21, DEC_DESCRIPTOR_SET, 0),
        ins(OP["Decorate"], 21, DEC_BINDING, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 2),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypePointer"], 6, SC_INPUT, 4),
        ins(OP["TypeStruct"], 8, 5),
        ins(OP["TypePointer"], 9, SC_OUTPUT, 8),
        ins(OP["TypePointer"], 7, SC_OUTPUT, 5),
        ins(OP["TypeStruct"], 20, 5),
        ins(OP["TypePointer"], 22, SC_UNIFORM, 20),
        ins(OP["TypeInt"], 10, 32, 1),
        ins(OP["Constant"], 10, 11, 0),
        ins(OP["Constant"], 3, 12, F0),
        ins(OP["Constant"], 3, 15, F1),
        ins(OP["Variable"], 6, 13, SC_INPUT),
        ins(OP["Variable"], 9, 14, SC_OUTPUT),
        ins(OP["Variable"], 22, 21, SC_UNIFORM),
        ins(OP["Function"], 1, 16, 0, 2),
        ins(OP["Label"], 17),
        ins(OP["Load"], 4, 18, 13),
        ins(OP["CompositeExtract"], 3, 19, 18, 0),
        ins(OP["CompositeExtract"], 3, 23, 18, 1),
        ins(OP["CompositeConstruct"], 5, 24, 19, 23, 12, 15),
        ins(OP["AccessChain"], 7, 25, 14, 11),
        ins(OP["Store"], 25, 24),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(26, b)


def fragment_constant() -> bytes:
    """out vec4 colour = a compile-time constant."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 12, *lit("main"), 6),
        ins(OP["ExecutionMode"], 12, MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], 6, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
        ins(OP["TypePointer"], 5, SC_OUTPUT, 4),
        ins(OP["Variable"], 5, 6, SC_OUTPUT),
        ins(OP["Constant"], 3, 7, FHALF),
        ins(OP["Constant"], 3, 8, F0),
        ins(OP["Constant"], 3, 9, F1),
        ins(OP["ConstantComposite"], 4, 10, 7, 8, 9, 9),
        ins(OP["Function"], 1, 12, 0, 2),
        ins(OP["Label"], 13),
        ins(OP["Store"], 6, 10),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(14, b)



def vertex_split_position() -> bytes:
    """gl_Position.x from one attribute and .y from another - legal
    SPIR-V, and a shape this emitter cannot lower."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_VERTEX, 19, *lit("main"), 15, 16, 17, 18),
        ins(OP["MemberDecorate"], 9, 0, DEC_BUILTIN, BUILTIN_POSITION),
        ins(OP["Decorate"], 9, DEC_BLOCK),
        ins(OP["Decorate"], 15, DEC_LOCATION, 0),
        ins(OP["Decorate"], 16, DEC_LOCATION, 1),
        ins(OP["Decorate"], 17, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 2),
        ins(OP["TypeVector"], 5, 3, 4),
        ins(OP["TypePointer"], 6, SC_INPUT, 4),
        ins(OP["TypePointer"], 7, SC_INPUT, 5),
        ins(OP["TypePointer"], 8, SC_OUTPUT, 5),
        ins(OP["TypeStruct"], 9, 5),
        ins(OP["TypePointer"], 10, SC_OUTPUT, 9),
        ins(OP["TypeInt"], 11, 32, 1),
        ins(OP["Constant"], 11, 12, 0),
        ins(OP["Constant"], 3, 13, F0),
        ins(OP["Constant"], 3, 14, F1),
        ins(OP["Variable"], 6, 15, SC_INPUT),
        ins(OP["Variable"], 7, 16, SC_INPUT),
        ins(OP["Variable"], 8, 17, SC_OUTPUT),
        ins(OP["Variable"], 10, 18, SC_OUTPUT),
        ins(OP["Function"], 1, 19, 0, 2),
        ins(OP["Label"], 20),
        ins(OP["Load"], 4, 21, 15),
        ins(OP["Load"], 5, 26, 16),
        ins(OP["CompositeExtract"], 3, 22, 21, 0),
        ins(OP["CompositeExtract"], 3, 23, 26, 1),
        ins(OP["CompositeConstruct"], 5, 24, 22, 23, 13, 14),
        ins(OP["AccessChain"], 8, 25, 18, 12),
        ins(OP["Store"], 25, 24),
        ins(OP["Store"], 17, 26),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(27, b)


def fragment_two_outputs() -> bytes:
    """Two Location outputs, which this render pass has no second
    attachment for."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 9, *lit("main"), 7, 8, 12),
        ins(OP["ExecutionMode"], 9, MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], 7, DEC_LOCATION, 0),
        ins(OP["Decorate"], 8, DEC_LOCATION, 0),
        ins(OP["Decorate"], 12, DEC_LOCATION, 1),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
        ins(OP["TypePointer"], 5, SC_INPUT, 4),
        ins(OP["TypePointer"], 6, SC_OUTPUT, 4),
        ins(OP["Variable"], 5, 7, SC_INPUT),
        ins(OP["Variable"], 6, 8, SC_OUTPUT),
        ins(OP["Variable"], 6, 12, SC_OUTPUT),
        ins(OP["Function"], 1, 9, 0, 2),
        ins(OP["Label"], 10),
        ins(OP["Load"], 4, 11, 7),
        ins(OP["Store"], 8, 11),
        ins(OP["Store"], 12, 11),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(13, b)


def fragment_int_input() -> bytes:
    """A four-component INTEGER input, which the emitter cannot move."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["EntryPoint"], EM_FRAGMENT, 9, *lit("main"), 7, 8),
        ins(OP["ExecutionMode"], 9, MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], 7, DEC_LOCATION, 0),
        ins(OP["Decorate"], 8, DEC_LOCATION, 0),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFunction"], 2, 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
        ins(OP["TypeInt"], 12, 32, 1),
        ins(OP["TypeVector"], 13, 12, 4),
        ins(OP["TypePointer"], 5, SC_INPUT, 13),
        ins(OP["TypePointer"], 6, SC_OUTPUT, 4),
        ins(OP["Variable"], 5, 7, SC_INPUT),
        ins(OP["Variable"], 6, 8, SC_OUTPUT),
        ins(OP["Function"], 1, 9, 0, 2),
        ins(OP["Label"], 10),
        ins(OP["Load"], 4, 11, 7),
        ins(OP["Store"], 8, 11),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return module(14, b)


def types_only() -> bytes:
    """A module with no entry point and no function at all."""
    b = [
        ins(OP["Capability"], CAP_SHADER),
        ins(OP["MemoryModel"], ADDR_LOGICAL, MEM_GLSL450),
        ins(OP["TypeVoid"], 1),
        ins(OP["TypeFloat"], 3, 32),
        ins(OP["TypeVector"], 4, 3, 4),
    ]
    return module(5, b)


def _mutate_words(blob: bytes, index: int, value: int) -> bytes:
    words = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    words[index] = value
    return struct.pack("<%dI" % len(words), *words)


def _replace_instruction(blob: bytes, old: list[int], new: list[int]) -> bytes:
    words = list(struct.unpack("<%dI" % (len(blob) // 4), blob))
    for i in range(len(words) - len(old) + 1):
        if words[i:i + len(old)] == old:
            words[i:i + len(old)] = new
            return struct.pack("<%dI" % len(words), *words)
    raise SystemExit("vulkan_spirv_check: an instruction a mutant needs is not in the module")


# ----------------------------------------------------------------------
#  The fixtures: the module, and what the front end must make of it.
# ----------------------------------------------------------------------
def build_fixtures() -> list[dict]:
    good_vertex = vertex_passthrough()
    good_fragment = fragment_varying()

    # A matrix transform: the shape every real vertex shader has, and the
    # first thing this front end has to refuse by name.
    matrix = _replace_instruction(
        vertex_passthrough(),
        ins(OP["TypeInt"], 11, 32, 1),
        ins(OP["TypeMatrix"], 11, 5, 4))

    # An if statement.
    branch = _replace_instruction(
        fragment_varying(),
        ins(OP["Load"], 4, 11, 7),
        ins(OP["Branch"], 10))

    # A descriptor-bound uniform.
    descriptor = _replace_instruction(
        fragment_push(),
        ins(OP["Decorate"], 9, DEC_LOCATION, 0),
        ins(OP["Decorate"], 9, DEC_DESCRIPTOR_SET, 0))

    return [
        dict(name="a vertex shader that passes a position and a colour through",
             blob=good_vertex,
             rc=OK, stage=0, inputs=2, outputs=1, pos=0, colour=-1,
             comps=(2, 4), outcomp=4, outsrc=1, push=0),
        dict(name="a vertex shader with a position and no varying",
             blob=vertex_position_only(),
             rc=OK, stage=0, inputs=1, outputs=0, pos=0, colour=-1,
             comps=(2, 0), outcomp=0, outsrc=-1, push=0),
        dict(name="a fragment shader that writes its interpolated input",
             blob=good_fragment,
             rc=OK, stage=4, inputs=1, outputs=1, pos=-1, colour=0,
             comps=(4, 0), outcomp=4, outsrc=-1, push=0),
        dict(name="a fragment shader that writes the push-constant colour",
             blob=fragment_push(),
             rc=OK, stage=4, inputs=0, outputs=1, pos=-1, colour=1,
             comps=(0, 0), outcomp=4, outsrc=-1, push=1),
        dict(name="a fragment shader that writes a constant colour",
             blob=fragment_constant(),
             rc=OK, stage=4, inputs=0, outputs=1, pos=-1, colour=2,
             comps=(0, 0), outcomp=4, outsrc=-1, push=0, const=FHALF),
        dict(name="a fragment shader that writes a uniform-buffer colour",
             blob=fragment_uniform(),
             rc=OK, stage=4, inputs=0, outputs=1, pos=-1, colour=3,
             comps=(0, 0), outcomp=4, outsrc=-1, push=0,
             uniform=1, uset=0, ubinding=0),
        dict(name="the same, at binding one of set zero",
             blob=fragment_uniform(binding=1),
             rc=OK, stage=4, inputs=0, outputs=1, pos=-1, colour=3,
             comps=(0, 0), outcomp=4, outsrc=-1, push=0,
             uniform=1, uset=0, ubinding=1),
        dict(name="a fragment shader that samples one combined image sampler",
             blob=fragment_sampled(),
             rc=OK, stage=4, inputs=1, outputs=1, pos=-1, colour=4,
             comps=(2, 0), outcomp=4, outsrc=-1, push=0,
             sampled=1, sset=0, sbinding=0, scoord=0),

        dict(name="a module whose magic number is not SPIR-V",
             blob=_mutate_words(good_vertex, 0, 0xDEADBEEF),
             rc=ERR_ARGS, text="magic"),
        dict(name="a module whose words are byte swapped",
             blob=_mutate_words(good_vertex, 0, 0x03022307),
             rc=ERR_ARGS, text="byte swapped"),
        dict(name="a module whose id bound is zero",
             blob=_mutate_words(good_vertex, 3, 0),
             rc=ERR_ARGS, text="bound is zero"),
        dict(name="a module declaring more ids than the front end holds",
             blob=_mutate_words(good_vertex, 3, 4096),
             rc=ERR_ARGS, text="more result ids"),
        dict(name="a module that declares an instruction schema",
             blob=_mutate_words(good_vertex, 4, 1),
             rc=ERR_ARGS, text="schema"),
        dict(name="a module whose last instruction runs past its end",
             blob=good_vertex + struct.pack("<I", (5 << 16) | OP["Store"]),
             rc=ERR_ARGS, text="past the end"),
        dict(name="an instruction with a word count of zero",
             blob=_mutate_words(good_vertex, 5, OP["Capability"]),
             rc=ERR_ARGS, text="word count of zero"),
        dict(name="a codeSize that is not a multiple of four",
             blob=good_vertex, trim=2,
             rc=ERR_ARGS, text="multiple of four"),

        dict(name="a vertex shader with a matrix transform",
             blob=matrix, rc=ERR_UNSUPPORTED, opcode=OP["TypeMatrix"],
             text="OpTypeMatrix"),
        dict(name="a fragment shader with a branch",
             blob=branch, rc=ERR_UNSUPPORTED, opcode=OP["Branch"],
             text="OpBranch"),
        dict(name="a fragment shader that declares a non-2D sampled image",
             blob=fragment_sampled(dim=3), rc=ERR_UNSUPPORTED,
             opcode=OP["TypeImage"], text="non-depth, non-arrayed"),
        dict(name="a sampled image without DescriptorSet and Binding",
             blob=fragment_sampled(decorate=False), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="both DescriptorSet and Binding"),
        dict(name="a sampled image at descriptor set one",
             blob=fragment_sampled(set_=1), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="DescriptorSet other than zero"),
        dict(name="a sample whose coordinate is not vec2",
             blob=fragment_sampled(coord_components=4), rc=ERR_UNSUPPORTED,
             opcode=OP["ImageSampleImplicitLod"], text="coordinate"),
        dict(name="an implicit sample carrying image operands",
             blob=fragment_sampled(image_operands=True), rc=ERR_UNSUPPORTED,
             opcode=OP["ImageSampleImplicitLod"], text="image operands"),
        dict(name="a combined sampler declared but never sampled",
             blob=fragment_sampled(sample=False), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="never samples it"),
        dict(name="a descriptor-set decoration on an output variable",
             blob=descriptor, rc=ERR_UNSUPPORTED, opcode=OP["Decorate"],
             text="DescriptorSet"),
        dict(name="a uniform block at a descriptor set other than zero",
             blob=fragment_uniform(set_=1), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="DescriptorSet other than zero"),
        dict(name="a uniform block at a binding the set layout cannot hold",
             blob=fragment_uniform(binding=2), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="Binding this implementation"),
        dict(name="a uniform structure that is not decorated Block",
             blob=fragment_uniform(block=False), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="not decorated Block"),
        dict(name="a uniform block whose first member is a vec2",
             blob=fragment_uniform(member_vec2=True), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="four-component"),
        dict(name="a uniform block with no DescriptorSet or Binding",
             blob=fragment_uniform(decorate=False), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="both DescriptorSet and Binding"),
        dict(name="a uniform block that is declared and never read",
             blob=fragment_uniform(read=False), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="never reads it"),
        dict(name="a module with two Uniform-storage blocks",
             blob=fragment_uniform(second_block=True), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="second Uniform-storage block"),
        dict(name="a fragment shader that reads uniform-block member one",
             blob=fragment_uniform(member1=True), rc=ERR_UNSUPPORTED,
             opcode=OP["Store"], text="member other than the first"),
        dict(name="a uniform block in a vertex shader",
             blob=vertex_uniform(), rc=ERR_UNSUPPORTED,
             opcode=OP["Variable"], text="vertex shader"),
        dict(name="a variable in the StorageBuffer storage class",
             blob=fragment_uniform(storage=SC_STORAGE_BUFFER),
             rc=ERR_UNSUPPORTED, opcode=OP["Variable"], text="StorageBuffer"),
        dict(name="a variable in the UniformConstant storage class",
             blob=fragment_uniform(storage=SC_UNIFORM_CONSTANT),
             rc=ERR_UNSUPPORTED, opcode=OP["Variable"], text="UniformConstant"),
        dict(name="a shader with a BufferBlock decoration",
             blob=_replace_instruction(fragment_uniform(),
                                       ins(OP["Decorate"], 5, DEC_BLOCK),
                                       ins(OP["Decorate"], 5, DEC_BUFFER_BLOCK)),
             rc=ERR_UNSUPPORTED, opcode=OP["Decorate"], text="BufferBlock"),
        dict(name="a module that declares the Geometry capability",
             blob=_replace_instruction(good_vertex,
                                       ins(OP["Capability"], CAP_SHADER),
                                       ins(OP["Capability"], CAP_GEOMETRY)),
             rc=ERR_UNSUPPORTED, opcode=OP["Capability"], text="Geometry"),
        dict(name="a module that declares the Float64 capability",
             blob=_replace_instruction(good_vertex,
                                       ins(OP["Capability"], CAP_SHADER),
                                       ins(OP["Capability"], CAP_FLOAT64)),
             rc=ERR_UNSUPPORTED, opcode=OP["Capability"], text="Float64"),
        dict(name="a compute entry point",
             blob=_replace_instruction(
                 good_vertex,
                 ins(OP["EntryPoint"], EM_VERTEX, 19, *lit("main"), 15, 16, 17, 18),
                 ins(OP["EntryPoint"], EM_GLCOMPUTE, 19, *lit("main"), 15, 16, 17, 18)),
             rc=ERR_UNSUPPORTED, opcode=OP["EntryPoint"], text="compute"),
        dict(name="an extended instruction set call",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Load"], 4, 11, 7),
                                       ins(OP["ExtInst"], 4, 11, 7, 1)),
             rc=ERR_UNSUPPORTED, opcode=OP["ExtInst"], text="OpExtInst"),
        dict(name="a multiply in a fragment shader",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Load"], 4, 11, 7),
                                       ins(OP["FMul"], 4, 11, 7, 7)),
             rc=ERR_UNSUPPORTED, opcode=OP["FMul"], text="OpFMul"),
        dict(name="a swizzle",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Load"], 4, 11, 7),
                                       ins(OP["VectorShuffle"], 4, 11, 7, 7, 3, 2, 1, 0)),
             rc=ERR_UNSUPPORTED, opcode=OP["VectorShuffle"], text="OpVectorShuffle"),
        dict(name="a local variable in the Function storage class",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Variable"], 5, 7, SC_INPUT),
                                       ins(OP["Variable"], 5, 7, SC_FUNCTION)),
             rc=ERR_UNSUPPORTED, opcode=OP["Variable"], text="Function"),
        dict(name="a Uniform-storage variable with no descriptor decorations",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Variable"], 5, 7, SC_INPUT),
                                       ins(OP["Variable"], 5, 7, SC_UNIFORM)),
             rc=ERR_UNSUPPORTED, opcode=OP["Variable"],
             text="both DescriptorSet and Binding"),
        dict(name="a vertex shader whose gl_Position.z is not zero",
             blob=vertex_passthrough(zbits=FHALF),
             rc=ERR_UNSUPPORTED, text="gl_Position.z"),
        dict(name="a vertex shader whose gl_Position.w is not one",
             blob=vertex_passthrough(wbits=FHALF),
             rc=ERR_UNSUPPORTED, text="gl_Position.w"),
        dict(name="a vertex shader that writes gl_PointSize",
             blob=_replace_instruction(
                 vertex_passthrough(),
                 ins(OP["MemberDecorate"], 9, 0, DEC_BUILTIN, BUILTIN_POSITION),
                 ins(OP["MemberDecorate"], 9, 0, DEC_BUILTIN, BUILTIN_POINTSIZE)),
             rc=ERR_UNSUPPORTED, text="Position"),
        dict(name="a fragment shader with no OriginUpperLeft",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["ExecutionMode"], 9, MODE_ORIGIN_UPPER_LEFT),
                                       ins(OP["Nop"])),
             rc=ERR_ARGS, text="OriginUpperLeft"),
        dict(name="a shader whose input locations have a gap",
             blob=_replace_instruction(vertex_passthrough(),
                                       ins(OP["Decorate"], 16, DEC_LOCATION, 1),
                                       ins(OP["Decorate"], 16, DEC_LOCATION, 2)),
             rc=ERR_UNSUPPORTED, text="locations"),
        dict(name="a module with no entry point at all",
             blob=_replace_instruction(
                 good_fragment,
                 ins(OP["EntryPoint"], EM_FRAGMENT, 9, *lit("main"), 7, 8),
                 ins(OP["Nop"])),
             rc=ERR_UNSUPPORTED, opcode=OP["Function"], text="entry point"),
        dict(name="a vertex shader whose position mixes two attributes",
             blob=vertex_split_position(),
             rc=ERR_UNSUPPORTED, text="same input attribute"),
        dict(name="a fragment shader with two Location outputs",
             blob=fragment_two_outputs(),
             rc=ERR_UNSUPPORTED, text="exactly one Location output"),
        dict(name="a fragment shader whose input is a built-in",
             blob=_replace_instruction(good_fragment,
                                       ins(OP["Decorate"], 7, DEC_LOCATION, 0),
                                       ins(OP["Decorate"], 7, DEC_BUILTIN, 15)),
             rc=ERR_UNSUPPORTED, text="built-in input"),
        dict(name="a module with neither an entry point nor a function",
             blob=types_only(), rc=ERR_ARGS, text="declares no entry point"),
        dict(name="a vertex shader that writes a built-in output variable "
                  "other than Position",
             blob=_replace_instruction(good_vertex,
                                       ins(OP["Decorate"], 17, DEC_LOCATION, 0),
                                       ins(OP["Decorate"], 17, DEC_BUILTIN,
                                           BUILTIN_POINTSIZE)),
             rc=ERR_UNSUPPORTED, text="built-in output"),
        dict(name="a fragment shader with a four-component integer input",
             blob=fragment_int_input(),
             rc=ERR_UNSUPPORTED, text="32-bit float"),
        dict(name="a vertex shader whose varying is computed, not passed through",
             blob=_replace_instruction(good_vertex,
                                       ins(OP["Store"], 17, 26),
                                       ins(OP["Store"], 17, 24)),
             rc=ERR_UNSUPPORTED, text="whole load of one input"),
    ]


# SOURCE MUTANTS. Each is a plausible way to get the front end wrong, and
# the gate must go red on every one of them.
MUTANTS = (
    ("the magic number is not checked",
     "  If magic <> #ANVIL_SPV_MAGIC\n",
     "  If magic = -1\n"),
    ("an instruction's word count may run past the end of the module",
     "    If (at + count) > words\n",
     "    If (at + count) > (words + 4096)\n"),
    ("a word count of zero no longer stops the walk",
     "    If count = 0\n",
     "    If count = -1\n"),
    ("an unimplemented opcode is accepted instead of refused",
     "    Default\n      ProcedureReturn avkSpvRefuseOpcode(op)\n",
     "    Default\n      ProcedureReturn #ANVIL_VK_OK\n"),
    ("gl_Position.z is no longer required to be zero",
     "  If spvKind[c2] <> #ANVIL_SPV_K_CONST Or spvConstWord[c2] <> 0\n",
     "  If spvKind[c2] <> #ANVIL_SPV_K_CONST Or spvConstWord[c2] = -1\n"),
    ("gl_Position.w is no longer required to be one",
     "  If spvKind[c3] <> #ANVIL_SPV_K_CONST Or spvConstWord[c3] <> $3F800000\n",
     "  If spvKind[c3] <> #ANVIL_SPV_K_CONST Or spvConstWord[c3] = -1\n"),
    ("gl_Position.x and .y may come from different attributes",
     "  If a0 < 0 Or a1 < 0 Or a0 <> a1\n",
     "  If a0 < 0 Or a1 < 0\n"),
    ("input locations need not be dense",
     "    If spvPlanAttrLoc[at] <> at\n",
     "    If spvPlanAttrLoc[at] < 0\n"),
    ("a fragment shader may write more than one Location output",
     "  If spvPlanVaryCount <> 1\n",
     "  If spvPlanVaryCount < 1\n"),
    ("a built-in input is accepted instead of refused",
     "        If spvDecBuiltIn[id] <> -1\n",
     "        If spvDecBuiltIn[id] = -12345\n"),
    ("a fragment shader need not declare its origin",
     "  If spvOriginUpperLeft = 0\n",
     "  If spvOriginUpperLeft = -1\n"),
    ("a module with no entry point is walked anyway",
     "  If spvEntry = 0\n    ProcedureReturn avkSpvMalformed",
     "  If spvEntry = -1\n    ProcedureReturn avkSpvMalformed"),
    ("a capability other than Shader is accepted",
     "      If a = #SpvCapabilityShader : ProcedureReturn #ANVIL_VK_OK : EndIf\n",
     "      ProcedureReturn #ANVIL_VK_OK\n"),
    ("a store into an Output that is not the colour is silently ignored",
     "        If spvDecBuiltIn[a] <> -1\n",
     "        If spvDecBuiltIn[a] = -12345\n"),
    ("an interface variable of the wrong component type is accepted",
     "  If avkSpvIsFloatish(spvValueType[id]) = 0\n",
     "  If avkSpvIsFloatish(spvValueType[id]) = -1\n"),
    ("a vertex varying may be computed rather than passed through",
     "    If a < 0\n      ProcedureReturn avkSpvRefuse(#SpvOpStore,",
     "    If a < -1\n      ProcedureReturn avkSpvRefuse(#SpvOpStore,"),
    # --- the uniform block ---
    ("a uniform block need not be decorated Block",
     "  If spvDecBlock[t] = 0\n",
     "  If spvDecBlock[t] = -1\n"),
    ("a uniform block may sit at any descriptor set",
     "  If spvDecSet[spvUniformVar] <> 0\n",
     "  If spvDecSet[spvUniformVar] < 0\n"),
    ("a uniform block may sit at a binding the set layout cannot hold",
     "  If spvDecBinding[spvUniformVar] < 0 Or spvDecBinding[spvUniformVar] >= #ANVIL_VK_MAX_SET_BINDINGS\n",
     "  If spvDecBinding[spvUniformVar] < 0 Or spvDecBinding[spvUniformVar] >= 99\n"),
    ("a uniform block's first member may be any width",
     "  If avkSpvIdOk(m) = 0 Or avkSpvIsFloatish(m) = 0 Or avkSpvComponents(m) <> 4\n",
     "  If avkSpvIdOk(m) = 0 Or avkSpvIsFloatish(m) = 0 Or avkSpvComponents(m) < 0\n"),
    ("a Uniform variable need not carry DescriptorSet and Binding",
     "        If spvDecSet[id] < 0 Or spvDecBinding[id] < 0\n",
     "        If spvDecSet[id] < -1 Or spvDecBinding[id] < -1\n"),
    ("a descriptor decoration on an interface variable is ignored",
     "      ElseIf spvDecSet[id] >= 0 Or spvDecBinding[id] >= 0\n",
     "      ElseIf spvDecSet[id] >= 99 Or spvDecBinding[id] >= 99\n"),
    ("a second uniform block is accepted",
     "        If spvUniformVar <> 0\n          ProcedureReturn avkSpvRefuse(op, \"the SPIR-V front end refused a second Uniform-storage block",
     "        If spvUniformVar < 0\n          ProcedureReturn avkSpvRefuse(op, \"the SPIR-V front end refused a second Uniform-storage block"),
    ("a uniform block in a vertex shader is accepted and then read as zero",
     "    If spvUniformVar <> 0\n      ProcedureReturn avkSpvRefuse(#SpvOpVariable, \"the SPIR-V front end refused a Uniform-storage block in a vertex shader",
     "    If spvUniformVar < 0\n      ProcedureReturn avkSpvRefuse(#SpvOpVariable, \"the SPIR-V front end refused a Uniform-storage block in a vertex shader"),
    ("a uniform block declared and never read is accepted",
     "  If spvUniformVar <> 0 And spvPlanColourSrc <> #ANVIL_SPV_COLOUR_UNIFORM\n",
     "  If spvUniformVar < 0 And spvPlanColourSrc <> #ANVIL_SPV_COLOUR_UNIFORM\n"),
    ("a uniform-block member other than the first may be read",
     "    If spvValueA[v] <> 0\n      ProcedureReturn avkSpvRefuse(#SpvOpStore, \"the SPIR-V front end refused a fragment shader that reads a uniform-block member",
     "    If spvValueA[v] < 0\n      ProcedureReturn avkSpvRefuse(#SpvOpStore, \"the SPIR-V front end refused a fragment shader that reads a uniform-block member"),
    ("the StorageBuffer storage class is accepted",
     "      If b = #SpvStorageClassStorageBuffer\n",
     "      If b = -1\n"),
    # --- the bounded combined sampler ---
    ("a non-2D image type is accepted",
     "      If avkSpvWord(*words, at + 3) <> #SpvDim2D Or avkSpvWord(*words, at + 4) <> 0 Or avkSpvWord(*words, at + 5) <> 0 Or avkSpvWord(*words, at + 6) <> 0\n",
     "      If avkSpvWord(*words, at + 3) < 0 Or avkSpvWord(*words, at + 4) <> 0 Or avkSpvWord(*words, at + 5) <> 0 Or avkSpvWord(*words, at + 6) <> 0\n"),
    ("a UniformConstant variable need not be a combined sampled image",
     "        If spvTypeClass[spvValueType[id]] <> #ANVIL_SPV_T_SAMPLED_IMAGE\n",
     "        If spvTypeClass[spvValueType[id]] < 0\n"),
    ("an image sample may name an unrelated sampled value",
     "      If spvValueSrc[b] <> #ANVIL_SPV_V_SAMPLED Or spvValueA[b] <> spvSampleVar\n",
     "      If spvValueSrc[b] < 0 Or spvValueA[b] <> spvSampleVar\n"),
    ("a sample coordinate need not be a whole vec2 input",
     "      If spvValueSrc[k] <> #ANVIL_SPV_V_INPUT Or avkSpvIsFloatish(spvValueType[k]) = 0 Or avkSpvComponents(spvValueType[k]) <> 2\n",
     "      If spvValueSrc[k] <> #ANVIL_SPV_V_INPUT Or avkSpvIsFloatish(spvValueType[k]) = 0 Or avkSpvComponents(spvValueType[k]) < 0\n"),
    ("a sampled image may sit at any descriptor set",
     "    If spvDecSet[spvSampleVar] <> 0\n",
     "    If spvDecSet[spvSampleVar] < 0\n"),
    ("a declared combined sampler may go unused",
     "  If spvSampleVar <> 0 And spvPlanColourSrc <> #ANVIL_SPV_COLOUR_SAMPLED\n",
     "  If spvSampleVar < 0 And spvPlanColourSrc <> #ANVIL_SPV_COLOUR_SAMPLED\n"),
)


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
    raise SystemExit(f"vulkan_spirv_check: {env_name} was not found; set it or pass its option")



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
    spec = importlib.util.spec_from_file_location("anvil_vkspv_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan_spirv_check: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def build(compiler: pathlib.Path) -> pathlib.Path:
    image = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_spirv_gate.img"
    command = [
        str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image),
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan_spirv_check: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path, fixtures: list[dict]):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)

    # The fixture table and the modules, written by this file and read by
    # the gate. The gate never writes here.
    addr = FIXTURES
    table = [len(fixtures)]
    for spec in fixtures:
        blob = spec["blob"]
        for i, byte in enumerate(blob):
            cpu.memory[addr + i] = byte
        spec["addr"] = addr
        length = len(blob) - spec.get("trim", 0)
        table.extend([addr, length])
        addr = (addr + len(blob) + 0x100) & ~0xFF
    for i, value in enumerate(table):
        for b in range(8):
            cpu.memory[IN + i * 8 + b] = (value >> (8 * b)) & 0xFF

    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(a: int) -> None:
        if a >= MMIO:
            raise SystemExit(
                f"vulkan_spirv_check: MMIO access at ${a:08X} - the SPIR-V front end is "
                "target neutral and must touch no hardware at all")

    def load(a: int, size: int) -> int:
        cpu.align_guard(a, size, False)
        guard(a)
        return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(size))

    def store(a: int, value: int, size: int) -> None:
        cpu.align_guard(a, size, True)
        guard(a)
        if FIXTURES <= a < OUT:
            raise SystemExit(
                f"vulkan_spirv_check: the gate wrote to ${a:08X}, inside the fixture "
                "table - a front end that edits the module it was handed could make any "
                "module parse")
        for i in range(size):
            cpu.memory[a + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"vulkan_spirv_check: the gate did not return in {STEP_LIMIT} steps")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def s64(cpu, addr: int) -> int:
    v = u64(cpu, addr)
    return v - (1 << 64) if v >= (1 << 63) else v


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

    def want_true(self, name, cond, detail="") -> None:
        self.checks += 1
        if not cond:
            self.failures.append(f"{name}{(': ' + detail) if detail else ''}")


def grade(cpu, rc, fixtures) -> Grader:
    g = Grader()
    g.need("gate magic", hex(u64(cpu, OUT)), hex(MAGIC))
    g.need("gate report address", rc, OUT)
    g.need("fixtures walked", u64(cpu, OUT + 8), len(fixtures))
    for i, spec in enumerate(fixtures):
        base = OUT + HEAD + i * SLOTS * 8
        name = spec["name"]
        got_rc = s64(cpu, base)
        g.need(f"[{i}] {name} - result", got_rc, spec["rc"])
        text = cstr(cpu, u64(cpu, base + 64))
        if spec["rc"] == OK:
            g.need(f"[{i}] {name} - stage", s64(cpu, base + 16), spec["stage"])
            g.need(f"[{i}] {name} - inputs", s64(cpu, base + 24), spec["inputs"])
            g.need(f"[{i}] {name} - outputs", s64(cpu, base + 32), spec["outputs"])
            g.need(f"[{i}] {name} - position attribute", s64(cpu, base + 40), spec["pos"])
            g.need(f"[{i}] {name} - colour source", s64(cpu, base + 48), spec["colour"])
            g.need(f"[{i}] {name} - input 0 components", s64(cpu, base + 72), spec["comps"][0])
            g.need(f"[{i}] {name} - input 1 components", s64(cpu, base + 80), spec["comps"][1])
            g.need(f"[{i}] {name} - output 0 components", s64(cpu, base + 88), spec["outcomp"])
            g.need(f"[{i}] {name} - output 0 source", s64(cpu, base + 96), spec["outsrc"])
            g.need(f"[{i}] {name} - push constants used", s64(cpu, base + 104), spec["push"])
            g.need(f"[{i}] {name} - uniform block used", s64(cpu, base + 128),
                   spec.get("uniform", 0))
            g.need(f"[{i}] {name} - uniform descriptor set", s64(cpu, base + 136),
                   spec.get("uset", -1))
            g.need(f"[{i}] {name} - uniform binding", s64(cpu, base + 144),
                   spec.get("ubinding", -1))
            g.need(f"[{i}] {name} - sampled image used", s64(cpu, base + 152),
                   spec.get("sampled", 0))
            g.need(f"[{i}] {name} - sampled descriptor set", s64(cpu, base + 160),
                   spec.get("sset", -1))
            g.need(f"[{i}] {name} - sampled binding", s64(cpu, base + 168),
                   spec.get("sbinding", -1))
            g.need(f"[{i}] {name} - sample coordinate input", s64(cpu, base + 176),
                   spec.get("scoord", -1))
            if "const" in spec:
                g.need(f"[{i}] {name} - constant colour", u64(cpu, base + 112) & 0xFFFFFFFF,
                       spec["const"])
            g.want_true(f"[{i}] {name} - walked the whole module",
                        s64(cpu, base + 56) >= 10, str(s64(cpu, base + 56)))
        else:
            g.want_true(f"[{i}] {name} - has a sentence", bool(text), repr(text[:60]))
            g.want_true(f"[{i}] {name} - ends as a sentence", text.endswith("."), repr(text[-60:]))
            g.want_true(f"[{i}] {name} - is not a bare code", len(text.split()) >= 14,
                        repr(text[:70]))
            g.want_true(f"[{i}] {name} - names its code", "Anvil code -200" in text,
                        repr(text[:90]))
            if "text" in spec:
                g.want_true(f"[{i}] {name} - names what it refused",
                            spec["text"].lower() in text.lower(), repr(text[:120]))
            if "opcode" in spec:
                g.need(f"[{i}] {name} - names the opcode number",
                       s64(cpu, base + 8), spec["opcode"])
    return g


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate_compiler(args.compiler)
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    fixtures = build_fixtures()
    accepted = sum(1 for f in fixtures if f["rc"] == OK)
    cpu, rc, steps = execute(a64, build(compiler), fixtures)
    g = grade(cpu, rc, fixtures)
    if g.failures:
        print(f"vulkan_spirv_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"vulkan_spirv_check: PASS - {g.checks} property checks over "
          f"{steps:,} executed A64 instructions")
    print(f"  {len(fixtures)} SPIR-V modules assembled in this file from the specification's")
    print(f"  own opcode numbers: {accepted} inside the subset and lowered to a plan whose")
    print(f"  every field was checked, {len(fixtures) - accepted} outside it and refused")
    print("  every refusal is a whole sentence naming its Anvil code and what it refused")
    print("  the front end made NOT ONE MMIO access and did not write one byte of the module")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    original = FRONTEND.read_text(encoding="utf-8")
    missed = 0
    for name, fixed, broken in MUTANTS:
        if original.count(fixed) != 1:
            print(f"  STALE  {name} - its anchor appears {original.count(fixed)} times")
            missed += 1
            continue
        FRONTEND.write_text(original.replace(fixed, broken, 1), encoding="utf-8")
        try:
            mcpu, mrc, _ = execute(a64, build(compiler), build_fixtures())
            mg = grade(mcpu, mrc, build_fixtures())
            red = bool(mg.failures)
            first = mg.failures[0][:96] if mg.failures else ""
        except SystemExit as exc:
            red, first = True, str(exc).splitlines()[0][:96]
        finally:
            FRONTEND.write_text(original, encoding="utf-8")
        if red:
            print(f"  RED    {name} - {first}")
        else:
            print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE")
            missed += 1

    print()
    if missed:
        print(f"vulkan_spirv_check: {missed} of {len(MUTANTS)} mutations were not caught")
        return 1
    print(f"vulkan_spirv_check: all {len(MUTANTS)} source mutations rejected, and the "
          f"{len(fixtures) - accepted} corrupted or out-of-subset modules above are the "
          "module mutants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
