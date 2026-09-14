#!/usr/bin/env python3
"""Exact SPIR-V retained-record and typed-IR adapter desk gate.

The fixtures are assembled here from Khronos opcode/enumerant values.  The
production path validates once, retains immutable words plus semantic records,
and adapts those records without reparsing the caller's module.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VULKAN = ROOT / "Anvil" / "Graphics" / "Vulkan"
GATE = VULKAN / "Tests" / "vulkan_spirv_ir_adapter_gate.pi4"
FRONTEND = VULKAN / "vk_spirv.pbi"
ADAPTER = VULKAN / "vk_spirv_ir_adapter.pbi"

LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0xDEAD0000
IN = 0x06000000
FIXTURES = 0x06010000
MMIO = 0xFC000000
STEP_LIMIT = 120_000_000
MAGIC = 0x53504952
OK = 0
ERR_ARGS = -20001
IR_ERR_ARGS = -23201
IR_ERR_DOMINANCE = -23211
MAX_RECORDS = 128
MAX_WORDS = 1024
SLOTS = 22


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"adapter gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


oracle = load_module("anvil_spirv_fixture_oracle", HERE / "vulkan_spirv_check.py")
OP = dict(oracle.OP)
OP["FAdd"] = 129


def arithmetic(op: int, lanes: int) -> bytes:
    """One exact float32 arithmetic shape in a valid fragment module."""
    ins = oracle.ins
    ids = iter(range(1, 64))
    void = next(ids)
    fn_type = next(ids)
    f32 = next(ids)
    lane_type = f32 if lanes == 1 else next(ids)
    vec4 = lane_type if lanes == 4 else next(ids)
    out_ptr = next(ids)
    one = next(ids)
    two = next(ids)
    left = one if lanes == 1 else next(ids)
    right = two if lanes == 1 else next(ids)
    colour = left if lanes == 4 else next(ids)
    out_var = next(ids)
    function = next(ids)
    block = next(ids)
    result = next(ids)
    body = [
        ins(OP["Capability"], oracle.CAP_SHADER),
        ins(OP["MemoryModel"], oracle.ADDR_LOGICAL, oracle.MEM_GLSL450),
        ins(OP["EntryPoint"], oracle.EM_FRAGMENT, function, *oracle.lit("main"), out_var),
        ins(OP["ExecutionMode"], function, oracle.MODE_ORIGIN_UPPER_LEFT),
        ins(OP["Decorate"], out_var, oracle.DEC_LOCATION, 0),
        ins(OP["TypeVoid"], void),
        ins(OP["TypeFunction"], fn_type, void),
        ins(OP["TypeFloat"], f32, 32),
    ]
    if lanes != 1:
        body.append(ins(OP["TypeVector"], lane_type, f32, lanes))
    if lanes != 4:
        body.append(ins(OP["TypeVector"], vec4, f32, 4))
    body += [
        ins(OP["TypePointer"], out_ptr, oracle.SC_OUTPUT, vec4),
        ins(OP["Constant"], f32, one, oracle.F1),
        ins(OP["Constant"], f32, two, 0x40000000),
    ]
    if lanes != 1:
        body += [
            ins(OP["ConstantComposite"], lane_type, left, *([one] * lanes)),
            ins(OP["ConstantComposite"], lane_type, right, *([two] * lanes)),
        ]
    if lanes != 4:
        body.append(ins(OP["ConstantComposite"], vec4, colour, one, one, one, one))
    body += [
        ins(OP["Variable"], out_ptr, out_var, oracle.SC_OUTPUT),
        ins(OP["Function"], void, function, 0, fn_type),
        ins(OP["Label"], block),
        ins(op, lane_type, result, left, right),
        ins(OP["Store"], out_var, result if lanes == 4 else colour),
        ins(OP["Return"]),
        ins(OP["FunctionEnd"]),
    ]
    return oracle.module(next(ids), body)


def late_failure(blob: bytes) -> bytes:
    return oracle._replace_instruction(blob, oracle.ins(OP["FunctionEnd"]), oracle.ins(OP["Branch"]))


def arithmetic_self_use(blob: bytes, opcode: int) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at = 5
    while at < len(words):
        count, op = words[at] >> 16, words[at] & 0xFFFF
        if op == opcode:
            words[at + 3] = words[at + 2]
            return struct.pack(f"<{len(words)}I", *words)
        at += count
    raise AssertionError("arithmetic opcode missing")


def mutate_arithmetic(blob: bytes, opcode: int, field: int, value: int) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at = 5
    while at < len(words):
        count, op = words[at] >> 16, words[at] & 0xFFFF
        if op == opcode:
            words[at + field] = value
            return struct.pack(f"<{len(words)}I", *words)
        at += count
    raise AssertionError("arithmetic opcode missing")


def insert_before(blob: bytes, before_opcode: int, addition: list[int]) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at = 5
    while at < len(words):
        count, op = words[at] >> 16, words[at] & 0xFFFF
        if op == before_opcode:
            words[at:at] = addition
            return struct.pack(f"<{len(words)}I", *words)
        at += count
    raise AssertionError("insertion opcode missing")


def move_after_return(blob: bytes, opcode: int) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    chunks, at = [], 5
    while at < len(words):
        count = words[at] >> 16
        chunks.append(words[at:at + count])
        at += count
    arithmetic_index = next(i for i, chunk in enumerate(chunks) if (chunk[0] & 0xFFFF) == opcode)
    return_index = next(i for i, chunk in enumerate(chunks) if (chunk[0] & 0xFFFF) == OP["Return"])
    chunk = chunks.pop(arithmetic_index)
    return_index = next(i for i, part in enumerate(chunks) if (part[0] & 0xFFFF) == OP["Return"])
    chunks.insert(return_index + 1, chunk)
    flat = words[:5]
    for part in chunks: flat.extend(part)
    return struct.pack(f"<{len(flat)}I", *flat)


def fixtures() -> list[dict]:
    accepted = [
        ("legacy varying", oracle.fragment_varying()),
        ("legacy push constant", oracle.fragment_push()),
        ("legacy constant", oracle.fragment_constant()),
        ("legacy uniform buffer", oracle.fragment_uniform()),
        ("legacy sampled image", oracle.fragment_sampled()),
    ]
    for opname in ("FAdd", "FMul"):
        for lanes in (1, 2, 3, 4):
            accepted.append((f"{opname} float32 x{lanes}", arithmetic(OP[opname], lanes)))
    bad_late = late_failure(arithmetic(OP["FAdd"], 4))
    bad_dom = arithmetic_self_use(arithmetic(OP["FAdd"], 4), OP["FAdd"])
    bad_dom_records = [r for _, r in instruction_records(bad_dom)]
    bad_dom_node = next(r for r in bad_dom_records if r["sourceOpcode"] == OP["FAdd"])
    bad_dom_node_index = [r for r in bad_dom_records if r["section"] == 9].index(bad_dom_node)
    arith4 = arithmetic(OP["FAdd"], 4)
    arith_words = list(struct.unpack(f"<{len(arith4)//4}I", arith4))
    first_constant = next(r["sourceId"] for _, r in instruction_records(arith4)
                          if r["sourceOpcode"] == OP["Constant"])
    bad_type = mutate_arithmetic(arith4, OP["FAdd"], 3, first_constant)
    bad_id = mutate_arithmetic(arith4, OP["FAdd"], 2, arith_words[3])
    bad_order = move_after_return(arithmetic(OP["FMul"], 3), OP["FMul"])
    bad_decoration = oracle._replace_instruction(
        oracle.fragment_constant(), oracle.ins(OP["Decorate"], 6, oracle.DEC_LOCATION, 0),
        oracle.ins(OP["Decorate"], 6, oracle.DEC_BINDING, 0))
    verifier_refusal = insert_before(
        oracle.fragment_constant(), OP["TypeVoid"],
        oracle.ins(OP["Decorate"], 3, 0))  # RelaxedPrecision on a type is not representable.
    return ([dict(name=n, blob=b, ok=True) for n, b in accepted] +
            [dict(name="late failure invalidates prior accepted stream", blob=bad_late, ok=False),
             dict(name="arithmetic self-use has no dominating definition", blob=bad_dom, ok=False,
                  dominance_id=bad_dom_node["sourceId"],
                  dominance_opcode=bad_dom_node["sourceOpcode"],
                  dominance_index=bad_dom_node_index),
             dict(name="arithmetic operand type differs from result", blob=bad_type, ok=False),
             dict(name="arithmetic result id reaches the module bound", blob=bad_id, ok=False),
             dict(name="arithmetic appears after the block terminator", blob=bad_order, ok=False),
             dict(name="descriptor decoration is misplaced on output", blob=bad_decoration, ok=False),
             dict(name="IR verifier refusal never publishes adapter output", blob=verifier_refusal,
                  ok=True, adapt=False)])


def locate(explicit: str | None, env: str, candidates: list[pathlib.Path]) -> pathlib.Path:
    paths = ([pathlib.Path(explicit)] if explicit else [])
    value = os.environ.get(env)
    if value:
        paths.append(pathlib.Path(value))
    paths.extend(candidates)
    for path in paths:
        if path.is_file():
            return path.resolve()
    raise SystemExit(f"adapter gate: {env} was not found; pass its option")


def build(compiler: pathlib.Path, suffix: str, frontend: str | None = None,
          adapter: str | None = None) -> pathlib.Path:
    work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_spirv_ir_"))
    dst = work / "Anvil" / "Graphics" / "Vulkan"
    tests = dst / "Tests"
    tests.mkdir(parents=True)
    for source in (VULKAN / "vk_core_1_0.pbi", VULKAN / "vk_foundation.pbi",
                   VULKAN / "vk_ir.pbi"):
        shutil.copy2(source, dst / source.name)
    (dst / FRONTEND.name).write_text(
        FRONTEND.read_text(encoding="utf-8") if frontend is None else frontend,
        encoding="utf-8")
    (dst / ADAPTER.name).write_text(
        ADAPTER.read_text(encoding="utf-8") if adapter is None else adapter,
        encoding="utf-8")
    shutil.copy2(GATE, tests / GATE.name)
    shutil.copytree(ROOT / "RaspberryPi4" / "Intrinsics", work / "RaspberryPi4" / "Intrinsics")
    shutil.copytree(ROOT / "Boards", work / "Boards")
    shutil.copy2(ROOT / "keywords.def", work / "keywords.def")
    image = work / f"{suffix}.img"
    command = [str(compiler), "--compile", (tests / GATE.name).relative_to(work).as_posix(),
               "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(command, cwd=work, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise SystemExit("adapter gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path, cases: list[dict]):
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    address = FIXTURES
    table = [len(cases)]
    writable = set()
    for case in cases:
        blob = case["blob"]
        case["address"] = address
        writable.update(range(address, address + 4))
        for offset, byte in enumerate(blob):
            cpu.memory[address + offset] = byte
        table.extend((address, len(blob)))
        address = (address + len(blob) + 0xFF) & ~0xFF
    for index, value in enumerate(table):
        for byte in range(8):
            cpu.memory[IN + index * 8 + byte] = (value >> (8 * byte)) & 0xFF
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= MMIO:
            raise SystemExit(f"adapter gate: unexpected MMIO read ${addr:08X}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= MMIO:
            raise SystemExit(f"adapter gate: unexpected MMIO write ${addr:08X}")
        if FIXTURES <= addr < address and any(addr + i not in writable for i in range(size)):
            raise SystemExit(f"adapter gate: parser changed caller storage at ${addr:08X}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"adapter gate: did not return in {STEP_LIMIT:,} instructions")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def s64(cpu, addr: int) -> int:
    value = u64(cpu, addr)
    return value - (1 << 64) if value >= (1 << 63) else value


class Grade:
    def __init__(self):
        self.checks = 0
        self.failures: list[str] = []

    def need(self, name: str, got, want):
        self.checks += 1
        if got != want:
            self.failures.append(f"{name}: got {got!r}, wanted {want!r}")


REC_FIELDS = ("streamIndex", "wordOffset", "sourceOpcode", "sourceWordCount", "section",
              "sourceId", "resultType", "idCount", "id0", "id1", "id2", "id3",
              "id4", "id5", "id6", "id7", "id8", "literalCount", "literal0",
              "literal1", "literal2", "literal3", "literal4", "literal5", "literal6",
              "literal7")

TYPE_OPS = {OP[n] for n in ("TypeVoid", "TypeInt", "TypeFloat", "TypeVector", "TypeImage",
                              "TypeSampledImage", "TypeStruct", "TypePointer", "TypeFunction")}
NODE_OPS = {OP[n] for n in ("Load", "Store", "AccessChain", "CompositeExtract",
                              "CompositeConstruct", "ImageSampleImplicitLod", "FAdd", "FMul",
                              "Return")}


def instruction_records(blob: bytes) -> list[tuple[list[int], dict]]:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    records = []
    at = 5
    while at < len(words):
        count, op = words[at] >> 16, words[at] & 0xFFFF
        inst = words[at:at + count]
        record = {name: 0 for name in REC_FIELDS}
        record.update(streamIndex=len(records), wordOffset=at, sourceOpcode=op,
                      sourceWordCount=count, section=1)
        if op == OP["EntryPoint"]: record["section"] = 2
        elif op in TYPE_OPS: record["section"] = 3
        elif op in (OP["Constant"], OP["ConstantComposite"]): record["section"] = 4
        elif op == OP["Variable"]: record["section"] = 5
        elif op in (OP["Decorate"], OP["MemberDecorate"]): record["section"] = 6
        elif op == OP["Function"]: record["section"] = 7
        elif op == OP["Label"]: record["section"] = 8
        elif op in NODE_OPS: record["section"] = 9
        elif op == OP["FunctionEnd"]: record["section"] = 10
        ids: list[int] = []
        literals: list[int] = []
        if op == OP["Capability"]: literals = inst[1:2]
        elif op == OP["MemoryModel"]: literals = inst[1:3]
        elif op == OP["EntryPoint"]:
            record["sourceId"] = inst[2]; literals = inst[1:2]
            k = 3
            while k < len(inst):
                if any(((inst[k] >> shift) & 0xFF) == 0 for shift in (0, 8, 16, 24)):
                    k += 1; break
                k += 1
            ids = inst[k:]
        elif op == OP["ExecutionMode"]: record["sourceId"] = inst[1]; literals = inst[2:3]
        elif op == OP["TypeVoid"]: record["sourceId"] = inst[1]
        elif op == OP["TypeInt"]: record["sourceId"] = inst[1]; literals = inst[2:4]
        elif op == OP["TypeFloat"]: record["sourceId"] = inst[1]; literals = inst[2:3]
        elif op == OP["TypeVector"]: record["sourceId"] = inst[1]; ids = inst[2:3]; literals = inst[3:4]
        elif op == OP["TypeImage"]: record["sourceId"] = inst[1]; ids = inst[2:3]; literals = inst[3:9]
        elif op in (OP["TypeSampledImage"], OP["TypeFunction"]): record["sourceId"] = inst[1]; ids = inst[2:3]
        elif op == OP["TypeStruct"]: record["sourceId"] = inst[1]; ids = inst[2:]
        elif op == OP["TypePointer"]: record["sourceId"] = inst[1]; literals = inst[2:3]; ids = inst[3:4]
        elif op == OP["Constant"]: record["resultType"], record["sourceId"] = inst[1:3]; literals = inst[3:4]
        elif op == OP["ConstantComposite"]: record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:]
        elif op == OP["Decorate"]: record["sourceId"] = inst[1]; literals = inst[2:]
        elif op == OP["MemberDecorate"]: record["sourceId"] = inst[1]; literals = inst[2:]
        elif op == OP["Variable"]: record["resultType"], record["sourceId"] = inst[1:3]; literals = inst[3:4]
        elif op == OP["Function"]:
            record["resultType"], record["sourceId"] = inst[1:3]; literals = inst[3:4]; ids = inst[4:5]
        elif op == OP["Label"]: record["sourceId"] = inst[1]
        elif op == OP["Load"]: record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:4]
        elif op == OP["Store"]: ids = inst[1:3]
        elif op == OP["AccessChain"]: record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:5]
        elif op == OP["CompositeExtract"]:
            record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:4]; literals = inst[4:5]
        elif op in (OP["CompositeConstruct"],):
            record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:]
        elif op in (OP["ImageSampleImplicitLod"], OP["FAdd"], OP["FMul"]):
            record["resultType"], record["sourceId"] = inst[1:3]; ids = inst[3:5]
        record["idCount"], record["literalCount"] = len(ids), len(literals)
        for index, value in enumerate(ids): record[f"id{index}"] = value
        for index, value in enumerate(literals): record[f"literal{index}"] = value
        records.append((inst, record))
        at += count
    return records


IR_TYPE_KIND = {OP["TypeVoid"]: 1, OP["TypeInt"]: 2, OP["TypeFloat"]: 3,
                OP["TypeVector"]: 4, OP["TypeStruct"]: 5, OP["TypePointer"]: 6,
                OP["TypeFunction"]: 7, OP["TypeImage"]: 8, OP["TypeSampledImage"]: 9}
IR_NODE_KIND = {OP["Load"]: 1, OP["AccessChain"]: 2, OP["CompositeExtract"]: 3,
                OP["CompositeConstruct"]: 4, OP["ImageSampleImplicitLod"]: 5,
                OP["Store"]: 6, OP["Return"]: 7, OP["FAdd"]: 8, OP["FMul"]: 9}
IR_DEC_KIND = {0: 1, 2: 2, 5: 3, 6: 4, 7: 5, 11: 6, 30: 7, 34: 8, 33: 9, 35: 10}


def read_qwords(cpu, address: int, count: int) -> list[int]:
    return [u64(cpu, address + 8 * i) for i in range(count)]


def grade(cpu, result: int, cases: list[dict]) -> Grade:
    g = Grade()
    g.need("gate report address is nonzero", result != 0, True)
    g.need("gate magic", u64(cpu, result + 1000 * 8), MAGIC)
    g.need("case count", u64(cpu, result + 1001 * 8), len(cases))
    for ci, case in enumerate(cases):
        base = result + ci * SLOTS * 8
        report = [s64(cpu, base + i * 8) for i in range(SLOTS)]
        name = case["name"]
        module = read_qwords(cpu, report[5], 19)
        g.need(f"{name}: embedded IR pointers rebound",
               [module[8], module[10], module[12], module[14], module[16], module[18]],
               report[16:22])
        if not case["ok"]:
            g.need(f"{name}: walk rejects", report[0] != OK, True)
            g.need(f"{name}: retained stream invalid", report[1], 0)
            g.need(f"{name}: hidden record count", report[3], 0)
            g.need(f"{name}: hidden word count", report[11], 0)
            g.need(f"{name}: raw read refused", report[13], ERR_ARGS)
            g.need(f"{name}: adapter refused", report[4], IR_ERR_ARGS)
            g.need(f"{name}: poisoned output invalidated", report[14], 0)
            continue
        original_words = list(struct.unpack(f"<{len(case['blob'])//4}I", case["blob"]))
        records = instruction_records(case["blob"])
        g.need(f"{name}: walk", report[0], OK)
        g.need(f"{name}: records valid", report[1], 1)
        g.need(f"{name}: retained magic after caller mutation", report[2], oracle.MAGIC_SPV)
        g.need(f"{name}: record count", report[3], len(records))
        g.need(f"{name}: raw word count", report[11], len(original_words))
        g.need(f"{name}: raw read", report[13], OK)
        adapt_ok = case.get("adapt", True)
        if adapt_ok:
            g.need(f"{name}: adapter verified", report[4], OK)
            g.need(f"{name}: adapter published last", report[14], 1)
        else:
            g.need(f"{name}: verifier rejects", report[4] != OK, True)
            g.need(f"{name}: rejected adapter output stays invalid", report[14], 0)
        raw = read_qwords(cpu, report[12], len(original_words))
        g.need(f"{name}: immutable exact module words", raw, original_words)
        for ri, (_, expected) in enumerate(records):
            got = read_qwords(cpu, report[6] + ri * len(REC_FIELDS) * 8, len(REC_FIELDS))
            for fi, field in enumerate(REC_FIELDS):
                g.need(f"{name}: record {ri} {field}", got[fi], expected[field])

        if not adapt_ok:
            continue
        rec_values = [record for _, record in records]
        types = [r for r in rec_values if r["section"] == 3]
        constants = [r for r in rec_values if r["section"] == 4]
        variables = [r for r in rec_values if r["section"] == 5]
        decorations = [r for r in rec_values if r["section"] == 6]
        nodes = [r for r in rec_values if r["section"] == 9]
        function = next(r for r in rec_values if r["section"] == 7)
        block = next(r for r in rec_values if r["section"] == 8)
        bound = original_words[3]
        g.need(f"{name}: IR module header", module[:8],
               [bound, 2, function["sourceId"], OP["Function"], function["id0"],
                function["resultType"], block["sourceId"], len(types)])
        g.need(f"{name}: IR section counts", [module[9], module[11], module[13], module[15], module[17]],
               [len(constants), len(variables), len(decorations), 1, len(nodes)])
        type_rows = [read_qwords(cpu, module[8] + i * 21 * 8, 21) for i in range(len(types))]
        for i, (row, r) in enumerate(zip(type_rows, types)):
            expected = [r["sourceId"], r["sourceOpcode"], IR_TYPE_KIND[r["sourceOpcode"]]] + [0] * 18
            op = r["sourceOpcode"]
            if op == OP["TypeInt"]: expected[3:5] = [r["literal0"], r["literal1"]]
            elif op == OP["TypeFloat"]: expected[3] = r["literal0"]
            elif op == OP["TypeVector"]: expected[5:7] = [r["id0"], r["literal0"]]
            elif op == OP["TypePointer"]: expected[7:9] = [r["literal0"], r["id0"]]
            elif op == OP["TypeFunction"]: expected[9] = r["id0"]
            elif op == OP["TypeStruct"]: expected[10:15] = [r["idCount"], r["id0"], r["id1"], r["id2"], r["id3"]]
            elif op == OP["TypeImage"]: expected[5], expected[15:21] = r["id0"], [r[f"literal{k}"] for k in range(6)]
            elif op == OP["TypeSampledImage"]: expected[5] = r["id0"]
            g.need(f"{name}: typed IR type {i}", row, expected)
        for i, r in enumerate(constants):
            row = read_qwords(cpu, module[10] + i * 10 * 8, 10)
            expected = [r["sourceId"], r["sourceOpcode"], r["resultType"], 0, 0,
                        0, 0, 0, 0, 0]
            if r["sourceOpcode"] == OP["Constant"]:
                expected[3:5] = [1, r["literal0"]]
            else:
                expected[5:] = [r["idCount"], r["id0"], r["id1"], r["id2"], r["id3"]]
            g.need(f"{name}: typed IR constant {i}", row, expected)
        for i, r in enumerate(variables):
            row = read_qwords(cpu, module[12] + i * 4 * 8, 4)
            g.need(f"{name}: typed IR variable {i}", row,
                   [r["sourceId"], r["sourceOpcode"], r["resultType"], r["literal0"]])
        for i, r in enumerate(decorations):
            row = [s64(cpu, module[14] + i * 5 * 8 + j * 8) for j in range(5)]
            if r["sourceOpcode"] == OP["MemberDecorate"]:
                member, spv_kind, value = r["literal0"], r["literal1"], r["literal2"]
            else:
                member, spv_kind, value = -1, r["literal0"], r["literal1"]
            g.need(f"{name}: typed IR decoration {i}", row,
                   [r["sourceId"], r["sourceOpcode"], member, IR_DEC_KIND[spv_kind], value])
        g.need(f"{name}: typed IR block",
               read_qwords(cpu, module[16], 6),
               [block["sourceId"], block["sourceOpcode"], 0, len(nodes), 0, 0])
        for i, r in enumerate(nodes):
            row = read_qwords(cpu, module[18] + i * 12 * 8, 12)
            expected = [r["sourceId"], r["sourceOpcode"], IR_NODE_KIND[r["sourceOpcode"]],
                        r["resultType"], block["sourceId"], r["idCount"], r["id0"], r["id1"],
                        r["id2"], r["id3"], r["literalCount"], r["literal0"]]
            g.need(f"{name}: ordered IR node {i}", row, expected)
    return g


MUTANTS = (
    ("partial records publish before walk success", "front", "late failure",
     "  ProcedureReturn #ANVIL_VK_OK\nEndProcedure\n\nProcedure.i AnvilVkSpirvRecordsValid()",
     "  spvRecordsValid = 1\n  ProcedureReturn #ANVIL_VK_OK\nEndProcedure\n\nProcedure.i AnvilVkSpirvRecordsValid()"),
    ("retained source offset drifts", "front", "legacy constant",
     "  *r\\wordOffset = at\n", "  *r\\wordOffset = at + 1\n"),
    ("ordered arithmetic operands swap", "front", "FAdd float32 x4",
     "Case #SpvOpFAdd\n      *r\\resultType=avkSpvWord(*words,at+1):*r\\sourceId=avkSpvWord(*words,at+2):*r\\idCount=2:*r\\id0=avkSpvWord(*words,at+3):*r\\id1=avkSpvWord(*words,at+4)",
     "Case #SpvOpFAdd\n      *r\\resultType=avkSpvWord(*words,at+1):*r\\sourceId=avkSpvWord(*words,at+2):*r\\idCount=2:*r\\id0=avkSpvWord(*words,at+4):*r\\id1=avkSpvWord(*words,at+3)"),
    ("arithmetic use need not dominate", "front", "self-use",
     "If spvKind[id] <> #ANVIL_SPV_K_NONE Or (spvKind[b] <> #ANVIL_SPV_K_VALUE And spvKind[b] <> #ANVIL_SPV_K_CONST) Or (spvKind[k] <> #ANVIL_SPV_K_VALUE And spvKind[k] <> #ANVIL_SPV_K_CONST)\n        ProcedureReturn avkSpvMalformed(\"a SPIR-V OpFAdd redefined an id or used an operand not defined earlier in its block (Anvil code -20001, malformed arithmetic); SSA definitions must dominate every use.\")\n      EndIf\n      If avkSpvIsFloatish(a) = 0 Or avkSpvComponents(a) < 1 Or avkSpvComponents(a) > 4 Or spvValueType[b] <> a Or spvValueType[k] <> a",
     "If spvKind[id] <> #ANVIL_SPV_K_NONE Or (b <> id And spvKind[b] <> #ANVIL_SPV_K_VALUE And spvKind[b] <> #ANVIL_SPV_K_CONST) Or (spvKind[k] <> #ANVIL_SPV_K_VALUE And spvKind[k] <> #ANVIL_SPV_K_CONST)\n        ProcedureReturn avkSpvMalformed(\"a SPIR-V OpFAdd redefined an id or used an operand not defined earlier in its block (Anvil code -20001, malformed arithmetic); SSA definitions must dominate every use.\")\n      EndIf\n      If avkSpvIsFloatish(a) = 0 Or avkSpvComponents(a) < 1 Or avkSpvComponents(a) > 4 Or (b <> id And spvValueType[b] <> a) Or spvValueType[k] <> a"),
    ("adapter skips IR verification", "adapter", "IR verifier refusal",
     "  rc=AnvilVkIrVerify(*m)\n", "  rc=#ANVIL_IR_OK\n"),
    ("adapter omits final verified publication", "adapter", "legacy constant",
     "  *out\\valid = 1\n", "  *out\\valid = 0\n"),
    ("decoration identity changes", "adapter", "legacy constant",
     "ProcedureReturn #ANVIL_IR_DEC_LOCATION", "ProcedureReturn #ANVIL_IR_DEC_BINDING"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()
    compiler = locate(args.compiler, "PMF_COMPILER",
                      [pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")])
    interp = locate(args.interp, "PMF_A64_INTERP", [ROOT / "tools" / "a64" / "a64_interp.py"])
    a64 = load_module("anvil_spirv_ir_a64", interp)
    cases = fixtures()
    cpu, result, steps = execute(a64, build(compiler, "base"), cases)
    g = grade(cpu, result, cases)
    if g.failures:
        print(f"vulkan_spirv_ir_adapter_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures[:80]: print("  " + failure)
        if len(g.failures) > 80: print(f"  ... {len(g.failures)-80} more")
        return 1
    print(f"vulkan_spirv_ir_adapter_check: PASS - {g.checks} properties over {steps:,} A64 instructions")
    print("  5 legacy fragment families and FAdd/FMul scalar/vec2/vec3/vec4")
    print("  exact immutable words, record fields/order/offsets, typed IR and hostile stale/dominance failures")
    if not args.mutate:
        print("  (run with --mutate for focused source mutants)")
        return 0
    front = FRONTEND.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    escaped = []
    for index, (name, owner, case_text, old, new) in enumerate(MUTANTS):
        source = front if owner == "front" else adapter
        if source.count(old) != 1:
            escaped.append(f"{name}: mutation locator count {source.count(old)}")
            continue
        broken = source.replace(old, new, 1)
        try:
            image = build(compiler, f"mutant_{index}", frontend=broken if owner == "front" else None,
                          adapter=broken if owner == "adapter" else None)
            mutant_cases = [case for case in fixtures() if case_text in case["name"]]
            if not mutant_cases:
                escaped.append(f"{name}: no fixture matching {case_text!r}")
                continue
            mcpu, mresult, _ = execute(a64, image, mutant_cases)
            mg = grade(mcpu, mresult, mutant_cases)
            if name == "arithmetic use need not dominate":
                case = mutant_cases[0]
                report = [s64(mcpu, mresult + i * 8) for i in range(SLOTS)]
                proof = [report[0], report[4], report[7], report[8], report[9],
                         report[10], report[14]]
                expected = [OK, IR_ERR_DOMINANCE, IR_ERR_DOMINANCE,
                            case["dominance_id"], case["dominance_opcode"],
                            case["dominance_index"], 0]
                if proof != expected:
                    escaped.append(f"{name}: exact proof {proof!r}, wanted {expected!r}")
            elif not mg.failures:
                escaped.append(name)
        except SystemExit:
            pass
    if escaped:
        print(f"vulkan_spirv_ir_adapter_check: FAIL - {len(escaped)} mutants escaped")
        for name in escaped: print("  " + name)
        return 1
    print(f"vulkan_spirv_ir_adapter_check: all {len(MUTANTS)} focused mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
