#!/usr/bin/env python3
"""Exact SPIR-V retained-record and typed-IR adapter desk gate.

The fixtures are assembled here from Khronos opcode/enumerant values.  The
production path validates once, retains immutable words plus semantic records,
and adapts those records without reparsing the caller's module.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VULKAN = ROOT / "Anvil" / "Graphics" / "Vulkan"
GATE = VULKAN / "Tests" / "vulkan_spirv_ir_adapter_gate.pi4"
FRONTEND = VULKAN / "vk_spirv.pbi"
ADAPTER = VULKAN / "vk_spirv_ir_adapter.pbi"
IR = VULKAN / "vk_ir.pbi"
EXPECTED_COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
EXPECTED_COMPILER_SHA = "06efee6763efb53ae5a2ca325b367ce9cbb8cb80680d76d491d82de44120b740"
EXPECTED_KEYWORDS_SHA = "e236923aa5c152bead53b04dafed91cb5656d21ebd7cfff115c32360f8057402"

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
IR_ERR_BOUNDS = -23202
IR_ERR_DUPLICATE = -23203
IR_ERR_UNDEFINED = -23204
IR_ERR_TYPE = -23205
IR_ERR_STORAGE = -23206
IR_ERR_DOMINANCE = -23211
SPV_IR_ERR_RECORD = -23301
SPV_IR_ERR_RANGE = -23302
MAX_RECORDS = 128
MAX_WORDS = 1024
SLOTS = 24


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def remove_private_tree(path: pathlib.Path | None) -> None:
    if path is None:
        return
    if path.exists():
        shutil.rmtree(path)
    if path.exists():
        raise RuntimeError(f"adapter gate: private tree did not clean up: {path}")


def finalize_snapshot(guard, snapshot: pathlib.Path,
                      primary: BaseException | None) -> None:
    """Guard and clean a snapshot without masking an active primary failure."""
    if primary is not None:
        try:
            guard()
        except BaseException as secondary:
            primary.add_note(f"secondary final input guard failure: {secondary}")
        try:
            remove_private_tree(snapshot)
        except BaseException as secondary:
            primary.add_note(f"secondary snapshot cleanup failure: {secondary}")
        return
    try:
        guard()
    except BaseException as guard_error:
        try:
            remove_private_tree(snapshot)
        except BaseException as cleanup_error:
            guard_error.add_note(f"secondary snapshot cleanup failure: {cleanup_error}")
        raise
    remove_private_tree(snapshot)


def compile_input_entries(runtime_keywords: pathlib.Path,
                          interpreter: pathlib.Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    roots = [VULKAN / "vk_core_1_0.pbi", VULKAN / "vk_foundation.pbi", IR,
             FRONTEND, ADAPTER, GATE]
    for path in roots:
        entries[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for directory in (ROOT / "RaspberryPi4" / "Intrinsics", ROOT / "Boards"):
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            entries[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    entries["_compiler/keywords.def"] = runtime_keywords.read_bytes()
    entries[(HERE / "vulkan_spirv_check.py").relative_to(ROOT).as_posix()] = (HERE / "vulkan_spirv_check.py").read_bytes()
    entries[interpreter.relative_to(ROOT).as_posix()] = interpreter.read_bytes()
    checker = pathlib.Path(__file__).resolve()
    entries[checker.relative_to(ROOT).as_posix()] = checker.read_bytes()
    return entries


def framed_manifest(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(entries):
        encoded = name.encode("utf-8")
        data = entries[name]
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def snapshot_manifest(snapshot: pathlib.Path) -> str:
    entries = {path.relative_to(snapshot).as_posix(): path.read_bytes()
               for path in snapshot.rglob("*") if path.is_file()}
    return framed_manifest(entries)


def freeze_inputs(entries: dict[str, bytes]) -> tuple[pathlib.Path, str]:
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_spirv_ir_snapshot_"))
    try:
        for name, data in entries.items():
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest = framed_manifest(entries)
        if snapshot_manifest(snapshot) != manifest:
            raise RuntimeError("adapter gate: frozen snapshot differs from framed inputs")
        return snapshot, manifest
    except BaseException:
        remove_private_tree(snapshot)
        raise


def guard_campaign_inputs(shared_supplier, shared_hash: str, snapshot: pathlib.Path,
                          snapshot_hash: str, compiler: pathlib.Path,
                          compiler_hash: str, runtime_keywords: pathlib.Path,
                          keywords_hash: str) -> None:
    if framed_manifest(shared_supplier()) != shared_hash:
        raise RuntimeError("adapter gate: shared compile inputs changed during frozen campaign")
    if sha256_file(compiler) != compiler_hash:
        raise RuntimeError("adapter gate: installed compiler changed during frozen campaign")
    if sha256_file(runtime_keywords) != keywords_hash:
        raise RuntimeError("adapter gate: compiler keywords changed during frozen campaign")
    if snapshot_manifest(snapshot) != snapshot_hash:
        raise RuntimeError("adapter gate: frozen snapshot changed during campaign")


def create_infra_roots(entries: dict[str, bytes]) -> tuple[pathlib.Path, str, pathlib.Path,
                                                            pathlib.Path, pathlib.Path]:
    snapshot, snapshot_hash = freeze_inputs(entries)
    try:
        fake = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_spirv_ir_fake_"))
        fake_compiler = fake / "compiler.exe"
        fake_keywords = fake / "keywords.def"
        fake_compiler.write_bytes(b"frozen compiler")
        fake_keywords.write_bytes(b"frozen keywords")
        return snapshot, snapshot_hash, fake, fake_compiler, fake_keywords
    except BaseException:
        remove_private_tree(snapshot)
        if "fake" in locals():
            remove_private_tree(fake)
        raise


def load_module(name: str, path: pathlib.Path):
    """Execute the exact bytes at path without creating adjacent bytecode."""
    source = path.read_bytes()
    code = compile(source, str(path), "exec")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name.rpartition(".")[0]
    prior = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior
        raise
    return module


ORACLE_PATH = HERE / "vulkan_spirv_check.py"
ORACLE_LOADED_HASH = sha256_file(ORACLE_PATH)
oracle = load_module("anvil_spirv_fixture_oracle", ORACLE_PATH)
if sha256_file(ORACLE_PATH) != ORACLE_LOADED_HASH:
    raise RuntimeError("adapter gate: SPIR-V oracle changed while it was loaded")
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


def entry_interface(blob: bytes) -> tuple[int, int, list[int]]:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at = 5
    while at < len(words):
        count, op = words[at] >> 16, words[at] & 0xFFFF
        if op == OP["EntryPoint"]:
            k = at + 3
            while k < at + count:
                word = words[k]
                k += 1
                if any(((word >> shift) & 0xFF) == 0 for shift in (0, 8, 16, 24)):
                    return at, k, words[k:at + count]
            raise AssertionError("unterminated EntryPoint name")
        at += count
    raise AssertionError("EntryPoint missing")


def rewrite_interface(blob: bytes, ids: list[int], version: int | None = None,
                      bound: int | None = None) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at, first_id, _ = entry_interface(blob)
    old_count = words[at] >> 16
    prefix = words[at + 1:first_id]
    replacement = [((1 + len(prefix) + len(ids)) << 16) | OP["EntryPoint"], *prefix, *ids]
    words[at:at + old_count] = replacement
    if version is not None:
        words[1] = version
    if bound is not None:
        words[3] = bound
    return struct.pack(f"<{len(words)}I", *words)


def unterminated_entry_name(blob: bytes) -> bytes:
    words = list(struct.unpack(f"<{len(blob)//4}I", blob))
    at, _, _ = entry_interface(blob)
    old_count = words[at] >> 16
    execution_model, entry = words[at + 1:at + 3]
    words[at:at + old_count] = [
        (4 << 16) | OP["EntryPoint"], execution_model, entry, 0x6E69616D]
    return struct.pack(f"<{len(words)}I", *words)


def variable_rows(blob: bytes) -> list[tuple[int, int]]:
    rows = []
    for _, record in instruction_records(blob):
        if record["sourceOpcode"] == OP["Variable"]:
            rows.append((record["sourceId"], record["literal0"]))
    return rows


def function_id(blob: bytes) -> int:
    return next(record["sourceId"] for _, record in instruction_records(blob)
                if record["sourceOpcode"] == OP["Function"])


def fragment_ten_interfaces() -> bytes:
    o = oracle
    ins = o.ins
    ids = iter(range(1, 64))
    void = next(ids); fn_type = next(ids); f32 = next(ids); vec4 = next(ids)
    out_ptr = next(ids); one = next(ids); colour = next(ids)
    variables = [next(ids) for _ in range(10)]
    function = next(ids); block = next(ids)
    body = [ins(OP["Capability"], o.CAP_SHADER),
            ins(OP["MemoryModel"], o.ADDR_LOGICAL, o.MEM_GLSL450),
            ins(OP["EntryPoint"], o.EM_FRAGMENT, function, *o.lit("main"), *variables),
            ins(OP["ExecutionMode"], function, o.MODE_ORIGIN_UPPER_LEFT)]
    body += [ins(OP["Decorate"], variable, o.DEC_LOCATION, 0) for variable in variables]
    body += [ins(OP["TypeVoid"], void), ins(OP["TypeFunction"], fn_type, void),
             ins(OP["TypeFloat"], f32, 32), ins(OP["TypeVector"], vec4, f32, 4),
             ins(OP["TypePointer"], out_ptr, o.SC_OUTPUT, vec4),
             ins(OP["Constant"], f32, one, o.F1),
             ins(OP["ConstantComposite"], vec4, colour, one, one, one, one)]
    body += [ins(OP["Variable"], out_ptr, variable, o.SC_OUTPUT) for variable in variables]
    body += [ins(OP["Function"], void, function, 0, fn_type), ins(OP["Label"], block),
             ins(OP["Store"], variables[0], colour), ins(OP["Return"]),
             ins(OP["FunctionEnd"])]
    blob = o.module(next(ids), body)
    assert len(blob) == 588
    assert hashlib.sha256(blob).hexdigest() == "efb170d9743b16ea9461102ded73fa121134c95c8f0330070d6950513c7829f6"
    return blob


def interface_cases() -> list[dict]:
    ten = fragment_ten_interfaces()
    _, _, ten_ids = entry_interface(ten)
    constant = oracle.fragment_constant()
    _, _, constant_ids = entry_interface(constant)
    varying = oracle.fragment_varying()
    _, _, varying_ids = entry_interface(varying)
    duplicated = rewrite_interface(varying, varying_ids + [varying_ids[-1]], 0x00010300)
    duplicated_14 = rewrite_interface(duplicated, varying_ids + [varying_ids[-1]], 0x00010400)
    constant_bound = struct.unpack_from("<I", constant, 12)[0]
    undefined = rewrite_interface(constant, constant_ids + [constant_bound],
                                  bound=constant_bound + 1)
    outbound = rewrite_interface(constant, constant_ids + [constant_bound])
    nonvariable = rewrite_interface(constant, constant_ids + [function_id(constant)])
    push = oracle.fragment_push()
    push_vars = variable_rows(push)
    push_resource = next(identifier for identifier, storage in push_vars
                         if storage == oracle.SC_PUSH)
    wrong_pre14 = rewrite_interface(push, entry_interface(push)[2] + [push_resource],
                                    0x00010300)
    result = [
        dict(name="ten exact EntryPoint interface IDs", blob=ten, ok=True),
        dict(name="thirty-two EntryPoint operands", blob=rewrite_interface(
            constant, [constant_ids[0]] * 32, 0x00010300), ok=True),
        dict(name="thirty-three EntryPoint operands refuse before publication",
             blob=rewrite_interface(constant, [constant_ids[0]] * 33, 0x00010300), ok=True,
             adapt=False, adapt_code=SPV_IR_ERR_RANGE, fault_id=function_id(constant),
             fault_opcode=OP["EntryPoint"], fault_index=2),
        dict(name="SPIR-V 1.3 duplicate interface operands are accepted",
             blob=duplicated, ok=True),
        dict(name="SPIR-V 1.4 duplicate interface operands are rejected",
             blob=duplicated_14, ok=True, adapt=False, adapt_code=IR_ERR_DUPLICATE,
             fault_id=varying_ids[-1], fault_opcode=OP["EntryPoint"], fault_index=2),
        dict(name="undefined EntryPoint interface ID", blob=undefined, ok=True,
             adapt=False, adapt_code=IR_ERR_UNDEFINED, fault_id=constant_bound,
             fault_opcode=OP["EntryPoint"], fault_index=len(constant_ids)),
        dict(name="out-of-bound EntryPoint interface ID", blob=outbound, ok=True,
             adapt=False, adapt_code=IR_ERR_BOUNDS, fault_id=constant_bound,
             fault_opcode=OP["EntryPoint"], fault_index=len(constant_ids)),
        dict(name="non-variable EntryPoint interface ID", blob=nonvariable, ok=True,
             adapt=False, adapt_code=IR_ERR_TYPE, fault_id=function_id(constant),
             fault_opcode=OP["EntryPoint"], fault_index=len(constant_ids)),
        dict(name="pre-1.4 resource interface operand has wrong storage",
             blob=wrong_pre14, ok=True, adapt=False, adapt_code=IR_ERR_STORAGE,
             fault_id=push_resource, fault_opcode=OP["EntryPoint"],
             fault_index=len(entry_interface(push)[2])),
        dict(name="SPIR-V 1.4 listed dead global is accepted",
             blob=rewrite_interface(ten, ten_ids, 0x00010400), ok=True),
        dict(name="unterminated retained EntryPoint name refuses exact interface extraction",
             blob=unterminated_entry_name(constant), ok=True, adapt=False,
             adapt_code=SPV_IR_ERR_RECORD, fault_id=function_id(constant),
             fault_opcode=OP["EntryPoint"], fault_index=2),
    ]
    for label, factory, storage in (
            ("push", oracle.fragment_push, oracle.SC_PUSH),
            ("uniform", oracle.fragment_uniform, oracle.SC_UNIFORM),
            ("sample", oracle.fragment_sampled, oracle.SC_UNIFORM_CONSTANT)):
        blob = factory()
        variables = variable_rows(blob)
        all_ids = [identifier for identifier, _ in variables]
        resource = next(identifier for identifier, value in variables if value == storage)
        valid = rewrite_interface(blob, all_ids, 0x00010400)
        missing = rewrite_interface(blob, [identifier for identifier in all_ids
                                           if identifier != resource], 0x00010400)
        variable_index = [identifier for identifier, _ in variables].index(resource)
        result += [
            dict(name=f"SPIR-V 1.4 valid {label} global interface", blob=valid, ok=True),
            dict(name=f"SPIR-V 1.4 missing live {label} global interface", blob=missing,
                 ok=True, adapt=False, adapt_code=IR_ERR_UNDEFINED,
                 fault_id=resource, fault_opcode=OP["EntryPoint"],
                 fault_index=variable_index),
        ]
    for label, missing_id in (("input", varying_ids[-1]), ("output", varying_ids[0])):
        variables = variable_rows(varying)
        variable_index = [identifier for identifier, _ in variables].index(missing_id)
        result.append(dict(
            name=f"missing live {label} EntryPoint interface",
            blob=rewrite_interface(varying, [identifier for identifier in varying_ids
                                             if identifier != missing_id]),
            ok=True, adapt=False, adapt_code=IR_ERR_UNDEFINED, fault_id=missing_id,
            fault_opcode=OP["EntryPoint"], fault_index=variable_index))
    return result


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
                  ok=True, adapt=False)] + interface_cases())


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


def build(compiler: pathlib.Path, runtime_keywords: pathlib.Path, suffix: str,
          snapshot: pathlib.Path, snapshot_hash: str, compiler_hash: str,
          keywords_hash: str, frontend: bytes | None = None,
          adapter: bytes | None = None, ir: bytes | None = None,
          runner=subprocess.run, compile_timeout: float = 120) -> tuple[pathlib.Path, pathlib.Path]:
    if snapshot_manifest(snapshot) != snapshot_hash:
        raise RuntimeError("adapter gate: frozen snapshot changed before compile")
    if sha256_file(compiler) != compiler_hash:
        raise RuntimeError("adapter gate: compiler changed before compile")
    if sha256_file(runtime_keywords) != keywords_hash:
        raise RuntimeError("adapter gate: compiler keywords changed before compile")
    work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vk_spirv_ir_"))
    try:
        shutil.copytree(snapshot, work, dirs_exist_ok=True)
        for source, replacement in ((IR, ir), (FRONTEND, frontend), (ADAPTER, adapter)):
            if replacement is not None:
                target = work / source.relative_to(ROOT)
                target.write_bytes(replacement)
        tests = work / GATE.parent.relative_to(ROOT)
        image = work / f"{suffix}.img"
        command = [str(compiler), "--compile", (tests / GATE.name).relative_to(work).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image), "-s"]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(work)
        run = runner(command, cwd=work, env=env, text=True,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     check=False, timeout=compile_timeout)
        if sha256_file(compiler) != compiler_hash:
            raise RuntimeError("adapter gate: compiler changed during compile")
        if sha256_file(runtime_keywords) != keywords_hash:
            raise RuntimeError("adapter gate: compiler keywords changed during compile")
        if snapshot_manifest(snapshot) != snapshot_hash:
            raise RuntimeError("adapter gate: frozen snapshot changed during compile")
        if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
            raise RuntimeError("adapter gate: compile failed\n" + run.stdout)
        return image, work
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def build_execute(a64, compiler: pathlib.Path, runtime_keywords: pathlib.Path,
                  suffix: str, cases: list[dict], snapshot: pathlib.Path,
                  snapshot_hash: str, compiler_hash: str, keywords_hash: str,
                  frontend: bytes | None = None, adapter: bytes | None = None,
                  ir: bytes | None = None, runner=subprocess.run,
                  compile_timeout: float = 120, execute_fn=None):
    image = None
    work = None
    try:
        image, work = build(compiler, runtime_keywords, suffix, snapshot,
                            snapshot_hash, compiler_hash, keywords_hash,
                            frontend=frontend, adapter=adapter, ir=ir,
                            runner=runner, compile_timeout=compile_timeout)
        if execute_fn is None:
            execute_fn = execute
        return execute_fn(a64, image, cases)
    finally:
        remove_private_tree(work)


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
        for index, value in enumerate(ids[:9]): record[f"id{index}"] = value
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
        module = read_qwords(cpu, report[5], 22)
        g.need(f"{name}: embedded IR pointers rebound",
               [module[9], module[11], module[13], module[15], module[17], module[19], module[21]],
               [report[16], report[17], report[18], report[22], report[19], report[20], report[21]])
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
            expected_code = case.get("adapt_code")
            if expected_code is None:
                g.need(f"{name}: verifier rejects", report[4] != OK, True)
            else:
                g.need(f"{name}: exact adapter refusal", report[4], expected_code)
                g.need(f"{name}: exact retained refusal code", report[7], expected_code)
                g.need(f"{name}: exact refusal source ID", report[8], case["fault_id"])
                g.need(f"{name}: exact refusal opcode", report[9], case["fault_opcode"])
                g.need(f"{name}: exact refusal index", report[10], case["fault_index"])
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
        entry = next(r for r in rec_values if r["section"] == 2)
        interface_words = original_words[entry["wordOffset"]:entry["wordOffset"] + entry["sourceWordCount"]]
        name_at = 3
        while name_at < len(interface_words):
            word = interface_words[name_at]
            name_at += 1
            if any(((word >> shift) & 0xFF) == 0 for shift in (0, 8, 16, 24)):
                break
        interfaces = interface_words[name_at:]
        g.need(f"{name}: IR module header", module[:9],
               [original_words[1], bound, 2, function["sourceId"], OP["Function"], function["id0"],
                function["resultType"], block["sourceId"], len(types)])
        g.need(f"{name}: IR section counts", [module[10], module[12], module[16], module[18], module[20]],
               [len(constants), len(variables), len(decorations), 1, len(nodes)])
        g.need(f"{name}: exact EntryPoint interface count", module[14], len(interfaces))
        g.need(f"{name}: exact EntryPoint interface IDs",
               read_qwords(cpu, module[15], len(interfaces)), interfaces)
        g.need(f"{name}: interface pointer rebound", module[15], report[22])
        g.need(f"{name}: source version copied", report[15], original_words[1])
        g.need(f"{name}: interface count copied", report[23], len(interfaces))
        type_rows = [read_qwords(cpu, module[9] + i * 21 * 8, 21) for i in range(len(types))]
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
            row = read_qwords(cpu, module[11] + i * 10 * 8, 10)
            expected = [r["sourceId"], r["sourceOpcode"], r["resultType"], 0, 0,
                        0, 0, 0, 0, 0]
            if r["sourceOpcode"] == OP["Constant"]:
                expected[3:5] = [1, r["literal0"]]
            else:
                expected[5:] = [r["idCount"], r["id0"], r["id1"], r["id2"], r["id3"]]
            g.need(f"{name}: typed IR constant {i}", row, expected)
        for i, r in enumerate(variables):
            row = read_qwords(cpu, module[13] + i * 4 * 8, 4)
            g.need(f"{name}: typed IR variable {i}", row,
                   [r["sourceId"], r["sourceOpcode"], r["resultType"], r["literal0"]])
        for i, r in enumerate(decorations):
            row = [s64(cpu, module[17] + i * 5 * 8 + j * 8) for j in range(5)]
            if r["sourceOpcode"] == OP["MemberDecorate"]:
                member, spv_kind, value = r["literal0"], r["literal1"], r["literal2"]
            else:
                member, spv_kind, value = -1, r["literal0"], r["literal1"]
            g.need(f"{name}: typed IR decoration {i}", row,
                   [r["sourceId"], r["sourceOpcode"], member, IR_DEC_KIND[spv_kind], value])
        g.need(f"{name}: typed IR block",
               read_qwords(cpu, module[19], 6),
               [block["sourceId"], block["sourceOpcode"], 0, len(nodes), 0, 0])
        for i, r in enumerate(nodes):
            row = read_qwords(cpu, module[21] + i * 12 * 8, 12)
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

INTERFACE_MUTANTS = (
    ("authoritative interface is not truncated to nine IDs", "adapter",
     "ten exact EntryPoint interface IDs", "exact EntryPoint interface IDs",
     "  count = 0\n  While k < *r\\sourceWordCount\n",
     "  count = 0\n  While k < *r\\sourceWordCount And count < 9\n"),
    ("interface operands are copied into owned storage", "adapter",
     "ten exact EntryPoint interface IDs", "adapter verified",
     "    PokeI(*m\\interfaces + (count * SizeOf(.i)), id)\n",
     "    PokeI(*m\\interfaces + (count * SizeOf(.i)), 0)\n"),
    ("published interface pointer is rebound", "adapter",
     "ten exact EntryPoint interface IDs", "interface pointer rebound",
     "  *out\\module\\interfaces = *out+OffsetOf(AvkSpirvIrStorage\\interfaces)\n",
     "  *out\\module\\interfaces = 0\n"),
    ("source SPIR-V version is retained", "adapter",
     "ten exact EntryPoint interface IDs", "source version copied",
     "  *m\\sourceVersion=AnvilVkSpirvVersion()\n",
     "  *m\\sourceVersion=0\n"),
    ("EntryPoint name terminator is mandatory", "adapter",
     "unterminated retained EntryPoint name", "exact adapter refusal",
     "  If terminated = 0\n",
     "  If terminated < 0\n"),
    ("interface storage cap is exactly thirty-two", "adapter",
     "thirty-three EntryPoint operands", "exact adapter refusal",
     "  If count < 0 Or count > #ANVIL_IR_MAX_VARIABLES\n",
     "  If count < 0 Or count > (#ANVIL_IR_MAX_VARIABLES + 1)\n"),
    ("SPIR-V 1.4 duplicate interface operands are rejected", "ir",
     "SPIR-V 1.4 duplicate interface operands", "exact adapter refusal",
     "    If *m\\sourceVersion >= $00010400\n      j = 0\n",
     "    If *m\\sourceVersion > $00010400\n      j = 0\n"),
    ("pre-1.4 interface operands are only Input or Output", "ir",
     "pre-1.4 resource interface operand", "exact adapter refusal",
     "    If *m\\sourceVersion < $00010400 And *v\\storageClass <> #ANVIL_IR_STORAGE_INPUT And *v\\storageClass <> #ANVIL_IR_STORAGE_OUTPUT\n",
     "    If *m\\sourceVersion < $00010400 And *v\\storageClass = -1\n"),
    ("every statically referenced global is in the interface", "ir",
     "SPIR-V 1.4 missing live sample global", "exact adapter refusal",
     "    If avkIrVariableReferenced(*m, *v\\sourceId) <> 0\n",
     "    If avkIrVariableReferenced(*m, *v\\sourceId) < 0\n"),
)


def encoded_anchor(source: bytes, text: str) -> bytes:
    candidates = [text.encode("utf-8")]
    if "\n" in text:
        candidates.append(text.replace("\n", "\r\n").encode("utf-8"))
    hits = [(candidate, source.count(candidate)) for candidate in candidates]
    exact = [candidate for candidate, count in hits if count == 1]
    if len(exact) != 1 or sum(count for _, count in hits) != 1:
        raise RuntimeError(f"adapter gate: mutation anchor is not unique: {text!r}; counts={hits!r}")
    return exact[0]


def mutate_source(source: bytes, old_text: str, new_text: str) -> bytes:
    old = encoded_anchor(source, old_text)
    newline = "\r\n" if b"\r\n" in old else "\n"
    new = new_text.replace("\n", newline).encode("utf-8")
    old_eols = [match.group(0) for match in __import__("re").finditer(br"\r\n|\n|\r", old)]
    new_eols = [match.group(0) for match in __import__("re").finditer(br"\r\n|\n|\r", new)]
    if old_eols != new_eols:
        raise RuntimeError("adapter gate: mutation changes its anchor's newline sequence")
    at = source.index(old)
    broken = source[:at] + new + source[at + len(old):]
    if broken[:at] != source[:at] or broken[at + len(new):] != source[at + len(old):]:
        raise RuntimeError("adapter gate: mutation changed bytes outside its one anchor")
    return broken


class MutationTally:
    def __init__(self):
        self.rejected = 0

    def semantic_rejection(self) -> None:
        self.rejected += 1


def infra_self_test(compiler: pathlib.Path, runtime_keywords: pathlib.Path,
                    interpreter: pathlib.Path) -> None:
    temp = pathlib.Path(tempfile.gettempdir())
    before = {path.resolve() for pattern in ("anvil_vk_spirv_ir_*",)
              for path in temp.glob(pattern) if path.is_dir()}
    entries = compile_input_entries(runtime_keywords, interpreter)
    snapshot, snapshot_hash, fake_dir, fake_compiler, fake_keywords = create_infra_roots(entries)
    tally = MutationTally()
    compile_abort = timeout_abort = execute_abort = drift_abort = False
    keyword_abort = snapshot_abort = shared_abort = False
    immutable_load = False
    combined_primary = False

    def failed_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "injected compile failure")

    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    def success_runner(*args, **kwargs):
        output = pathlib.Path(args[0][args[0].index("-o") + 1])
        output.write_bytes(b"injected image")
        return subprocess.CompletedProcess(args[0], 0, "pmfc: OK")

    def execute_failure(*args, **kwargs):
        raise SystemExit("injected execute failure")

    def drift_runner(*args, **kwargs):
        fake_compiler.write_bytes(b"changed compiler")
        return success_runner(*args, **kwargs)

    def keyword_drift_runner(*args, **kwargs):
        fake_keywords.write_bytes(b"changed keywords")
        return success_runner(*args, **kwargs)

    def snapshot_drift_runner(*args, **kwargs):
        victim = snapshot / IR.relative_to(ROOT)
        victim.write_bytes(victim.read_bytes() + b"\n")
        return success_runner(*args, **kwargs)

    try:
        load_name = "anvil_spirv_ir_a64_immutable_selftest"
        load_manifest = snapshot_manifest(snapshot)
        try:
            loaded = load_module(load_name, snapshot / interpreter.relative_to(ROOT))
            immutable_load = (snapshot_manifest(snapshot) == load_manifest and
                              callable(getattr(loaded, "A64", None)) and
                              callable(getattr(loaded, "attach_symbols", None)))
        finally:
            sys.modules.pop(load_name, None)
        try:
            build(compiler, runtime_keywords, "infra_compile", snapshot, snapshot_hash,
                  sha256_file(compiler), sha256_file(runtime_keywords), runner=failed_runner)
        except RuntimeError as error:
            compile_abort = "injected compile failure" in str(error)
        try:
            build(compiler, runtime_keywords, "infra_timeout", snapshot, snapshot_hash,
                  sha256_file(compiler), sha256_file(runtime_keywords), runner=timeout_runner,
                  compile_timeout=0.01)
        except subprocess.TimeoutExpired:
            timeout_abort = True
        try:
            build_execute(None, compiler, runtime_keywords, "infra_execute", [], snapshot,
                          snapshot_hash, sha256_file(compiler), sha256_file(runtime_keywords),
                          runner=success_runner, execute_fn=execute_failure)
        except SystemExit as error:
            execute_abort = "injected execute failure" in str(error)
        original_fake_hash = sha256_file(fake_compiler)
        try:
            build(fake_compiler, fake_keywords, "infra_drift", snapshot, snapshot_hash,
                  original_fake_hash, sha256_file(fake_keywords), runner=drift_runner)
        except RuntimeError as error:
            drift_abort = "compiler changed during compile" in str(error)
        fake_compiler.write_bytes(b"frozen compiler")
        fake_keywords.write_bytes(b"frozen keywords")
        try:
            build(fake_compiler, fake_keywords, "infra_keyword_drift", snapshot, snapshot_hash,
                  sha256_file(fake_compiler), sha256_file(fake_keywords),
                  runner=keyword_drift_runner)
        except RuntimeError as error:
            keyword_abort = "compiler keywords changed during compile" in str(error)
        fake_keywords.write_bytes(b"frozen keywords")
        altered_entries = dict(entries)
        first_name = sorted(altered_entries)[0]
        altered_entries[first_name] += b"changed"
        try:
            guard_campaign_inputs(lambda: altered_entries, framed_manifest(entries),
                                  snapshot, snapshot_hash, compiler, sha256_file(compiler),
                                  runtime_keywords, sha256_file(runtime_keywords))
        except RuntimeError as error:
            shared_abort = "shared compile inputs changed" in str(error)
        for mutant in INTERFACE_MUTANTS:
            _, owner, _, _, old, new = mutant
            source = {"adapter": ADAPTER.read_bytes(), "ir": IR.read_bytes()}[owner]
            mutate_source(source, old, new)
        try:
            build(compiler, runtime_keywords, "infra_snapshot_drift", snapshot, snapshot_hash,
                  sha256_file(compiler), sha256_file(runtime_keywords),
                  runner=snapshot_drift_runner)
        except RuntimeError as error:
            snapshot_abort = "frozen snapshot changed during compile" in str(error)
        combined_snapshot, _ = freeze_inputs({"sentinel": b"frozen"})
        injected_primary = SystemExit("injected combined execute failure")

        def persistent_drift_guard():
            raise RuntimeError("injected persistent final guard drift")

        try:
            try:
                raise injected_primary
            finally:
                finalize_snapshot(persistent_drift_guard, combined_snapshot,
                                  sys.exc_info()[1])
        except SystemExit as error:
            combined_primary = (error is injected_primary and
                                any("injected persistent final guard drift" in note
                                    for note in getattr(error, "__notes__", ())) and
                                not combined_snapshot.exists())
    finally:
        try:
            if "combined_snapshot" in locals():
                remove_private_tree(combined_snapshot)
        finally:
            try:
                remove_private_tree(snapshot)
            finally:
                remove_private_tree(fake_dir)
    after = {path.resolve() for pattern in ("anvil_vk_spirv_ir_*",)
             for path in temp.glob(pattern) if path.is_dir()}
    if not all((immutable_load, combined_primary, compile_abort, timeout_abort,
                execute_abort, drift_abort,
                keyword_abort, snapshot_abort, shared_abort)):
        raise RuntimeError(f"adapter gate: infrastructure self-test failed: immutable-load={immutable_load} combined-primary={combined_primary} compile={compile_abort} timeout={timeout_abort} execute={execute_abort} compiler-drift={drift_abort} keyword-drift={keyword_abort} snapshot-drift={snapshot_abort} shared-drift={shared_abort}")
    if tally.rejected != 0:
        raise RuntimeError(f"adapter gate: infrastructure failures counted as {tally.rejected} semantic kills")
    if after != before:
        raise RuntimeError(f"adapter gate: infrastructure self-test leaked temp roots: {sorted(str(path) for path in after - before)}")
    print("vulkan_spirv_ir_adapter_check: infra self-test PASS - immutable frozen-byte module load leaves snapshot exact; combined execute primary + guard drift preserves primary/note/cleanup; compile failure, timeout, execute/SystemExit, compiler/keyword/snapshot/shared drift abort; rejected=0; temp roots unchanged; EOL/prefix/suffix splices exact")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--mutate-interface", action="store_true")
    parser.add_argument("--self-test-infra", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = locate(args.compiler, "PMF_COMPILER",
                      [EXPECTED_COMPILER])
    if compiler != EXPECTED_COMPILER.resolve():
        raise RuntimeError(f"adapter gate: compiler must be the installed pinned executable {EXPECTED_COMPILER}")
    compiler_hash = sha256_file(compiler)
    if compiler_hash != EXPECTED_COMPILER_SHA:
        raise RuntimeError(f"adapter gate: compiler SHA-256 {compiler_hash} != {EXPECTED_COMPILER_SHA}")
    runtime_keywords = compiler.parent / "keywords.def"
    if not runtime_keywords.is_file():
        raise RuntimeError(f"adapter gate: compiler-owned keywords missing: {runtime_keywords}")
    keywords_hash = sha256_file(runtime_keywords)
    if keywords_hash != EXPECTED_KEYWORDS_SHA:
        raise RuntimeError(f"adapter gate: keywords SHA-256 {keywords_hash} != {EXPECTED_KEYWORDS_SHA}")
    interp = locate(args.interp, "PMF_A64_INTERP", [ROOT / "tools" / "a64" / "a64_interp.py"])
    if args.self_test_infra:
        infra_self_test(compiler, runtime_keywords, interp)
        return 0
    entries = compile_input_entries(runtime_keywords, interp)
    shared_hash = framed_manifest(entries)
    snapshot, snapshot_hash = freeze_inputs(entries)
    try:
        def guard_inputs() -> None:
            guard_campaign_inputs(lambda: compile_input_entries(runtime_keywords, interp),
                                  shared_hash, snapshot, snapshot_hash, compiler,
                                  compiler_hash, runtime_keywords, keywords_hash)

        frozen_oracle = snapshot / ORACLE_PATH.relative_to(ROOT)
        if sha256_file(frozen_oracle) != ORACLE_LOADED_HASH:
            raise RuntimeError("adapter gate: loaded oracle differs from frozen oracle bytes")
        print(f"vulkan_spirv_ir_adapter_check: compiler={compiler} sha256={compiler_hash}", flush=True)
        print(f"vulkan_spirv_ir_adapter_check: keywords={runtime_keywords} sha256={keywords_hash}", flush=True)
        print(f"vulkan_spirv_ir_adapter_check: frozen-input-manifest={snapshot_hash}", flush=True)
        print(f"vulkan_spirv_ir_adapter_check: oracle={ORACLE_PATH} sha256={ORACLE_LOADED_HASH}", flush=True)
        print(f"vulkan_spirv_ir_adapter_check: interpreter={interp} sha256={sha256_file(interp)}", flush=True)
        a64 = load_module("anvil_spirv_ir_a64", snapshot / interp.relative_to(ROOT))
        if snapshot_manifest(snapshot) != snapshot_hash:
            raise RuntimeError("adapter gate: frozen snapshot changed while loading interpreter")
        cases = fixtures()
        if args.mutate_interface:
            causal_names = {mutant[2] for mutant in INTERFACE_MUTANTS}
            cases = [case for case in cases if any(name in case["name"] for name in causal_names)]
        guard_inputs()
        cpu, result, steps = build_execute(
            a64, compiler, runtime_keywords, "base", cases, snapshot, snapshot_hash,
            compiler_hash, keywords_hash)
        guard_inputs()
        g = grade(cpu, result, cases)
        if g.failures:
            print(f"vulkan_spirv_ir_adapter_check: FAIL ({g.checks} checks, {steps:,} instructions)")
            for failure in g.failures[:80]: print("  " + failure)
            if len(g.failures) > 80: print(f"  ... {len(g.failures)-80} more")
            return 1
        print(f"vulkan_spirv_ir_adapter_check: PASS - {g.checks} properties over {steps:,} A64 instructions")
        if args.mutate_interface:
            print("  compact exact EntryPoint retention, version, ownership and hostile interface baseline")
        else:
            print("  5 legacy fragment families and FAdd/FMul scalar/vec2/vec3/vec4")
            print("  exact immutable words, record fields/order/offsets, typed IR and hostile stale/dominance failures")
        if not args.mutate and not args.mutate_interface:
            print("  (run with --mutate for focused source mutants)")
            return 0
        sources = {
            "front": (snapshot / FRONTEND.relative_to(ROOT)).read_bytes(),
            "adapter": (snapshot / ADAPTER.relative_to(ROOT)).read_bytes(),
            "ir": (snapshot / IR.relative_to(ROOT)).read_bytes(),
        }
        selected = INTERFACE_MUTANTS if args.mutate_interface else MUTANTS
        escaped = []
        tally = MutationTally()
        for index, mutant in enumerate(selected):
            if args.mutate_interface:
                name, owner, case_text, causal, old, new = mutant
            else:
                name, owner, case_text, old, new = mutant
                causal = None
            broken = mutate_source(sources[owner], old, new)
            mutant_cases = [case for case in fixtures() if case_text in case["name"]]
            if len(mutant_cases) != 1:
                raise RuntimeError(f"adapter gate: {name}: expected one causal fixture for {case_text!r}, got {len(mutant_cases)}")
            overrides = {owner: broken}
            guard_inputs()
            mcpu, mresult, _ = build_execute(
                a64, compiler, runtime_keywords, f"mutant_{index}", mutant_cases,
                snapshot, snapshot_hash, compiler_hash, keywords_hash,
                frontend=overrides.get("front"), adapter=overrides.get("adapter"),
                ir=overrides.get("ir"))
            guard_inputs()
            mg = grade(mcpu, mresult, mutant_cases)
            caught = bool(mg.failures)
            if name == "arithmetic use need not dominate":
                case = mutant_cases[0]
                report = [s64(mcpu, mresult + i * 8) for i in range(SLOTS)]
                proof = [report[0], report[4], report[7], report[8], report[9],
                         report[10], report[14]]
                expected = [OK, IR_ERR_DOMINANCE, IR_ERR_DOMINANCE,
                            case["dominance_id"], case["dominance_opcode"],
                            case["dominance_index"], 0]
                caught = proof != expected
                if not caught:
                    escaped.append(f"{name}: exact proof {proof!r}, wanted {expected!r}")
            elif not caught:
                escaped.append(name)
            elif causal is not None:
                prefix = f"{mutant_cases[0]['name']}: {causal}:"
                caught = any(failure.startswith(prefix) for failure in mg.failures)
                if not caught:
                    escaped.append(f"{name}: causal property {prefix!r} did not fail; got {mg.failures[:3]!r}")
            if caught:
                tally.semantic_rejection()
            detail = mg.failures[0] if mg.failures else ""
            print(f"  {'RED' if caught else 'GREEN'} {index + 1}/{len(selected)} {name}" +
                  (f": {detail}" if detail else ""), flush=True)
        if escaped:
            print(f"vulkan_spirv_ir_adapter_check: FAIL - {len(escaped)} mutants escaped")
            for name in escaped: print("  " + name)
            return 1
        if tally.rejected != len(selected):
            raise RuntimeError(f"adapter gate: semantic rejection tally {tally.rejected} != {len(selected)}")
        print(f"vulkan_spirv_ir_adapter_check: all {len(selected)} focused mutations rejected")
        return 0
    finally:
        finalize_snapshot(guard_inputs, snapshot, sys.exc_info()[1])


if __name__ == "__main__":
    with checker_lock():
        raise SystemExit(main())
