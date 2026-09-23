#!/usr/bin/env python3
"""Compile, execute and byte-grade the isolated typed vertex V3D 4.2 pair."""

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
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/vulkan_vertex_ir_v3d42_gate.pi4"
MODULE = ROOT / "Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4"
COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
COMPILER_SHA = "06efee6763efb53ae5a2ca325b367ce9cbb8cb80680d76d491d82de44120b740"
INTERPRETER = ROOT / "tools/a64/a64_interp.py"
INTERPRETER_SHA = "7bf5c82987fdf6c014b14349070355ee4d539da28f7bfe1befd73f54d6da2b6e"
LOAD = 0x400000
STACK = 0x3000000
RETURN = 0xDEAD0000
MMIO = 0xFC000000
MAGIC = 0x56523432
STRIDE = 48
STEP_LIMIT = 45_000_000

B_CS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3C00218ABC806000 3C00218BBC806040 54001306BBF80288 54001346BBF802C9 3C003186BB800000 3C00218CF581E300 3C00218DF581E340 3C002180F883E00A 3C002180F883E04B 3C002180F883E086 3C002180F883E0C7 3C002180F883E10C 3C002180F883E14D 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
B_VS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3C002188BC806000 3C002189BC806040 54001286BBF80206 540012C6BBF80247 3C003186BB800000 3C00218AF581E280 3C00218BF581E2C0 3C002180F883E00A 3C002180F883E04B 3C002180F883E084 3C002180F883E0C5 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
D_CS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3D82B186BB800000 3D82F186BB800000 3C00218CBC806000 3C00218DBC806040 3C00218EBC806080 3C00218FBC8060C0 54001406BBF8030A 54001446BBF8034B 3C003186BB800000 3C002190F581E400 3C002191F581E440 3C002180F883E00C 3C002180F883E04D 3C002180F883E088 3C002180F883E0C9 3C002180F883E110 3C002180F883E151 3C002180F883E18E 3C002180F883E1CF 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
D_VS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3C00218ABC806000 3C00218BBC806040 3C00218CBC806080 3C00218DBC8060C0 54001386BBF80288 540013C6BBF802C9 3C003186BB800000 3C00218EF581E380 3C00218FF581E3C0 3C002180F883E00E 3C002180F883E04F 3C002180F883E086 3C002180F883E0C7 3C002180F883E10C 3C002180F883E14D 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
A_CS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3D82B186BB800000 3D82F186BB800000 3D833186BB800000 3D837186BB800000 3C00218EBC806000 3C00218FBC806040 3C002190BC806080 3C002191BC8060C0 3C002192BC806100 3C002193BC806140 54001506BBF8038C 54001546BBF803CD 3C003186BB800000 3C002194F581E500 3C002195F581E540 3C002180F883E00E 3C002180F883E04F 3C002180F883E08A 3C002180F883E0CB 3C002180F883E114 3C002180F883E155 3C002180F883E190 3C002180F883E1D1 3C002180F883E212 3C002180F883E253 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
A_VS = tuple(int(x, 16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3D82B186BB800000 3D82F186BB800000 3C00218CBC806000 3C00218DBC806040 3C00218EBC806080 3C00218FBC8060C0 3C002190BC806100 3C002191BC806140 54001486BBF8030A 540014C6BBF8034B 3C003186BB800000 3C002192F581E480 3C002193F581E4C0 3C002180F883E012 3C002180F883E053 3C002180F883E088 3C002180F883E0C9 3C002180F883E10E 3C002180F883E14F 3C002180F883E190 3C002180F883E1D1 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
# A dead declared/listed vec2 input shifts register allocation as well as
# adding its two VPM reads. These independently captured complete streams are
# the oracle shared only by cases 13/14; they are not derived from live A.
DEAD_CS = tuple(int(x,16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3D82B186BB800000 3D82F186BB800000 3D833186BB800000 3D837186BB800000 3C00218EBC806000 3C00218FBC806040 3C002190BC806080 3C002191BC8060C0 3C002192BC806100 3C002193BC806140 3C002194BC806180 3C002195BC8061C0 54001586BBF8038C 540015C6BBF803CD 3C003186BB800000 3C002196F581E580 3C002197F581E5C0 3C002180F883E00E 3C002180F883E04F 3C002180F883E08A 3C002180F883E0CB 3C002180F883E116 3C002180F883E157 3C002180F883E190 3C002180F883E1D1 3C002180F883E212 3C002180F883E253 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
DEAD_VS = tuple(int(x,16) for x in """3D803186BB800000 3D807186BB800000 3D80B186BB800000 3D80F186BB800000 3D813186BB800000 3D817186BB800000 3D81B186BB800000 3D81F186BB800000 3D823186BB800000 3D827186BB800000 3D82B186BB800000 3D82F186BB800000 3C00218CBC806000 3C00218DBC806040 3C00218EBC806080 3C00218FBC8060C0 3C002190BC806100 3C002191BC806140 3C002192BC806180 3C002193BC8061C0 54001506BBF8030A 54001546BBF8034B 3C003186BB800000 3C002194F581E500 3C002195F581E540 3C002180F883E014 3C002180F883E055 3C002180F883E088 3C002180F883E0C9 3C002180F883E10E 3C002180F883E14F 3C002180F883E190 3C002180F883E1D1 3C003186BB816000 3C203186BB800000 3C003186BB800000 3C003186BB800000 3C003186BB800000""".split())
DUP_LOAD_CS = A_CS[:33] + (0x3C002180F883E210, 0x3C002180F883E251) + A_CS[35:]
DUP_LOAD_VS = A_VS[:29] + (0x3C002180F883E18E, 0x3C002180F883E1CF) + A_VS[31:]
SHARED_INPUT_CS = D_CS[:27] + (0x3C002180F883E18C, 0x3C002180F883E1CD) + D_CS[29:]
SHARED_INPUT_VS = D_VS[:23] + (0x3C002180F883E10A, 0x3C002180F883E14B) + D_VS[25:]

def qword_sha(values): return hashlib.sha256(struct.pack(f"<{len(values)}Q", *values)).hexdigest()

SPECIAL_ORACLE_SHA = {
    "dead-cs": (DEAD_CS,"4c32b80a65f3ad65a1b46984bee8027d63f27984f82e38656ed25185574a80d8"),
    "dead-vs": (DEAD_VS,"ad6d15c9da255be43ab161719eeeb657ad93241abe5726afc8aaec50243b4126"),
    "duplicate-load-cs": (DUP_LOAD_CS,"118f8cfb199f854a08490e2bc4c15115c3768f06902b8ed06c400ec55c151c11"),
    "duplicate-load-vs": (DUP_LOAD_VS,"07c9e9993b9775445ad155a3fcf244914180e8adb39ccb0d8fcbb955144490d9"),
    "position-share-cs": (SHARED_INPUT_CS,"b4f4251b97886a3b5c06b2f52445aefb25c58b5935ffc43e031cdcac2215830c"),
    "position-share-vs": (SHARED_INPUT_VS,"fc7134053912525d9d9ecdba85e9457e85f3fc81e33dca13d761155b284389ae"),
}
for oracle_name,(oracle_words,oracle_hash) in SPECIAL_ORACLE_SHA.items():
    if qword_sha(oracle_words) != oracle_hash: raise RuntimeError(f"frozen {oracle_name} oracle drift")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_private_tree(path: pathlib.Path | None) -> None:
    if path is None:
        return
    if path.exists():
        shutil.rmtree(path)
    if path.exists():
        raise RuntimeError(f"vertex IR42 gate: private tree did not clean up: {path}")


def finalize_snapshot(guard, snapshot: pathlib.Path, primary: BaseException | None) -> None:
    """Preserve an active primary failure while still guarding and cleaning."""
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


@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try: yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_module(name: str, path: pathlib.Path):
    """Execute exact frozen bytes without creating adjacent bytecode."""
    source = path.read_bytes(); code = compile(source, str(path), "exec")
    module = types.ModuleType(name); module.__file__ = str(path); module.__package__ = name.rpartition(".")[0]
    prior = sys.modules.get(name); sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        if prior is None: sys.modules.pop(name, None)
        else: sys.modules[name] = prior
        raise
    return module


def compile_entries() -> dict[str, bytes]:
    entries = {}
    for rel in ("Anvil/Graphics/Vulkan/vk_core_1_0.pbi", "Anvil/Graphics/Vulkan/vk_foundation.pbi",
                "Anvil/Graphics/Vulkan/vk_ir.pbi", "Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4",
                "Anvil/Graphics/Vulkan/Tests/vulkan_vertex_ir_v3d42_gate.pi4",
                "RaspberryPi4/Lib/v3dqpu.pi4"):
        entries[rel] = (ROOT / rel).read_bytes()
    for directory in (ROOT / "RaspberryPi4/Intrinsics", ROOT / "Boards"):
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            entries[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    entries[pathlib.Path(__file__).resolve().relative_to(ROOT).as_posix()] = pathlib.Path(__file__).resolve().read_bytes()
    entries[INTERPRETER.relative_to(ROOT).as_posix()] = INTERPRETER.read_bytes()
    return entries


def framed_manifest(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(entries):
        encoded = name.encode(); data = entries[name]
        digest.update(len(encoded).to_bytes(4, "little")); digest.update(encoded)
        digest.update(len(data).to_bytes(8, "little")); digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def snapshot_manifest(snapshot: pathlib.Path) -> str:
    return framed_manifest({p.relative_to(snapshot).as_posix(): p.read_bytes()
                            for p in snapshot.rglob("*") if p.is_file()})


def freeze_inputs(entries: dict[str, bytes]) -> tuple[pathlib.Path, str]:
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vertex_ir42_snapshot_"))
    try:
        for rel, data in entries.items():
            dst = snapshot / rel; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(data)
        manifest = framed_manifest(entries)
        if snapshot_manifest(snapshot) != manifest:
            raise RuntimeError("vertex IR42 gate: frozen snapshot differs from framed inputs")
        return snapshot, manifest
    except BaseException:
        remove_private_tree(snapshot); raise


def guard_inputs(shared_supplier, shared_hash: str, snapshot: pathlib.Path, snapshot_hash: str,
                 compiler: pathlib.Path, compiler_hash: str) -> None:
    if framed_manifest(shared_supplier()) != shared_hash:
        raise RuntimeError("vertex IR42 gate: shared compile inputs changed")
    if sha(compiler) != compiler_hash:
        raise RuntimeError("vertex IR42 gate: compiler changed")
    if snapshot_manifest(snapshot) != snapshot_hash:
        raise RuntimeError("vertex IR42 gate: frozen snapshot changed")


def build(compiler: pathlib.Path, snapshot: pathlib.Path,
          manifest: str, compiler_hash: str,
          module: bytes | None = None, runner=subprocess.run,
          timeout: float = 300) -> tuple[pathlib.Path, pathlib.Path]:
    if snapshot_manifest(snapshot) != manifest: raise RuntimeError("vertex IR42 gate: frozen snapshot changed before compile")
    if sha(compiler) != compiler_hash: raise RuntimeError("vertex IR42 gate: compiler changed before compile")
    work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vertex_ir42_"))
    try:
        shutil.copytree(snapshot, work, dirs_exist_ok=True)
        if module is not None:
            (work / MODULE.relative_to(ROOT)).write_bytes(module)
        out = work / "vertex_ir42.img"
        cmd = [str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(), "-t", "pi4",
               "--load-addr", hex(LOAD), "-s", "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(out)]
        env = os.environ.copy(); env["PMF_ROOT"] = str(work)
        proc = runner(cmd, cwd=work, env=env, text=True, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, timeout=timeout)
        if sha(compiler) != compiler_hash: raise RuntimeError("vertex IR42 gate: compiler changed during compile")
        if snapshot_manifest(snapshot) != manifest: raise RuntimeError("vertex IR42 gate: frozen snapshot changed during compile")
        if proc.returncode or "pmfc: OK" not in proc.stdout or not out.is_file():
            raise RuntimeError("vertex IR42 compile failed\n" + proc.stdout)
        return out, work
    except BaseException:
        remove_private_tree(work); raise


def build_execute(a64, compiler: pathlib.Path, snapshot: pathlib.Path,
                  manifest: str, compiler_hash: str,
                  module: bytes | None = None, runner=subprocess.run,
                  timeout: float = 300, execute_fn=None):
    image = work = None
    try:
        image, work = build(compiler, snapshot, manifest, compiler_hash,
                            module=module, runner=runner, timeout=timeout)
        return (execute_fn or execute)(a64, image)
    finally:
        remove_private_tree(work)


def execute(a64, image: pathlib.Path):
    cpu = a64.A64(); data = image.read_bytes(); cpu.memory.update({LOAD+i:b for i,b in enumerate(data)})
    a64.attach_symbols(cpu, image, LOAD); cpu.pc = LOAD; cpu.sp = STACK; cpu.x[30] = RETURN
    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if addr >= MMIO: raise RuntimeError(f"unexpected MMIO read {addr:#x}")
        return sum(cpu.memory.get(addr+i, 0) << (8*i) for i in range(size))
    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if addr >= MMIO: raise RuntimeError(f"unexpected MMIO write {addr:#x}")
        for i in range(size): cpu.memory[addr+i] = (value >> (8*i)) & 255
    cpu.load = load; cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN: return cpu, cpu.x[0], steps
        cpu.step()
    raise RuntimeError("vertex IR42 fixture timeout")


def q(cpu, addr): return sum(cpu.memory.get(addr+i, 0) << (8*i) for i in range(8))
def u32(cpu, addr): return sum(cpu.memory.get(addr+i, 0) << (8*i) for i in range(4))
def words(cpu, addr, size): return tuple(q(cpu, addr+i) for i in range(0, size, 8))
def f32(value): return struct.unpack("<I", struct.pack("<f", value))[0]
def neg(value): return (1 << 64) + value


def grade(cpu, report):
    bad = []; checks = 0
    def need(ok, text):
        nonlocal checks; checks += 1
        if not ok: bad.append(text)
    need(q(cpu, report+4000*8) == MAGIC, "report magic")
    successful = {0:(B_CS,B_VS,0), 1:(D_CS,D_VS,2), 2:(A_CS,A_VS,4),
                  3:(A_CS,A_VS,4), 5:(D_CS,D_VS,2), 6:(A_CS,A_VS,4),
                  8:(B_CS,B_VS,0), 9:(B_CS,B_VS,0), 11:(B_CS,B_VS,0),
                  12:(A_CS,A_VS,4), 15:(A_CS,A_VS,4), 20:(B_CS,B_VS,0),
                  44:(DUP_LOAD_CS,DUP_LOAD_VS,4), 45:(SHARED_INPUT_CS,SHARED_INPUT_VS,2),
                  47:(B_CS,B_VS,0)}
    for case, (want_cs, want_vs, vary) in successful.items():
        base = report + case*STRIDE*8
        rc = q(cpu, base); csb = q(cpu, base+5*8); vsb = q(cpu, base+6*8)
        csuw = q(cpu,base+7*8); vsuw = q(cpu,base+8*8)
        expected_csu = {0:10,2:12,4:14}[vary]; expected_vsu = {0:8,2:10,4:12}[vary]
        lengths_ok = (csb == len(want_cs)*8 and vsb == len(want_vs)*8 and
                      csuw == expected_csu and vsuw == expected_vsu)
        need(rc == 0, f"case {case} rc {rc:#x}")
        need(lengths_ok, f"case {case} code/uniform counts {csb}/{vsb}/{csuw}/{vsuw}")
        if lengths_ok:
            need(words(cpu, q(cpu,base+13*8),len(want_cs)*8) == want_cs, f"case {case} exact coordinate bytes")
            need(words(cpu, q(cpu,base+14*8),len(want_vs)*8) == want_vs, f"case {case} exact vertex bytes")
        need(q(cpu,base+10*8) == vary, f"case {case} varying components")
        need(q(cpu,base+9*8) == vary+2, f"case {case} exact input-slot ABI")
        width,height = ({5:(3,5),6:(257,257),8:(1,1),9:(65535,65535)}.get(case,(4,4)))
        if lengths_ok:
            csu = [u32(cpu,q(cpu,base+15*8)+4*i) for i in range(expected_csu)]
            vsu = [u32(cpu,q(cpu,base+16*8)+4*i) for i in range(expected_vsu)]
            half = [0,0x3f800000,f32(width*128),f32(height*128)]
            need(csu == list(range(expected_csu-4))+half, f"case {case} complete coordinate uniform stream {csu}")
            need(vsu == list(range(expected_vsu-4))+half, f"case {case} complete vertex uniform stream {vsu}")
        need(q(cpu,base+11*8) == width*128 and q(cpu,base+12*8) == height*128, f"case {case} checked half extents")
        if case == 5: need(f32(width*128) == 0x43c00000 and f32(height*128) == 0x44200000, "3x5 exact f32 extent words")
        if case == 6: need(f32(width*128) == 0x47008000, "257x257 exact f32 extent words")
        if case == 9: need(f32(width*128) == 0x4affff00, "65535 exact f32 extent words")
    # A declared/listed dead input remains part of the VPM ABI, but a dead
    # SSA Load must not affect either complete stream.
    for case in (13, 14):
        base = report + case*STRIDE*8
        need(q(cpu,base) == 0, f"dead-input case {case} succeeds")
        need(q(cpu,base+9*8) == 8 and q(cpu,base+10*8) == 4,
             f"dead-input case {case} preserves exact eight-slot ABI")
        need((q(cpu,base+5*8),q(cpu,base+6*8),q(cpu,base+7*8),q(cpu,base+8*8)) == (336,304,14,12),
             f"dead-input case {case} exact counts")
        need(words(cpu,q(cpu,base+13*8),336) == DEAD_CS,
             f"dead-input case {case} independent exact coordinate bytes")
        need(words(cpu,q(cpu,base+14*8),304) == DEAD_VS,
             f"dead-input case {case} independent exact vertex bytes")
        half=[0,0x3f800000,f32(4*128),f32(4*128)]
        need([u32(cpu,q(cpu,base+15*8)+4*i) for i in range(14)] == list(range(10))+half,
             f"dead-input case {case} independent exact coordinate uniforms")
        need([u32(cpu,q(cpu,base+16*8)+4*i) for i in range(12)] == list(range(8))+half,
             f"dead-input case {case} independent exact vertex uniforms")
    d0 = report + 13*STRIDE*8; d1 = report + 14*STRIDE*8
    dead_lengths_ok = all(q(cpu,b+o*8)==want for b in (d0,d1) for o,want in ((5,336),(6,304),(7,14),(8,12)))
    if dead_lengths_ok:
        for pointer_slot, size, label in ((13,336,"coordinate code"),(14,304,"vertex code"),(15,56,"coordinate uniforms"),(16,48,"vertex uniforms")):
            need(bytes(cpu.memory.get(q(cpu,d0+pointer_slot*8)+i,0) for i in range(size)) ==
                 bytes(cpu.memory.get(q(cpu,d1+pointer_slot*8)+i,0) for i in range(size)),
                 f"dead listed Load DCE exact {label}")
    plan_oracles = {
        0: ((20,-1,10,-1,40), ()),
        11:((20,0,10,-1,40), ()),
        12:((20,-1,10,-1,40), ((0,21,-1,11,-1,44,2),(1,22,-1,12,-1,45,2))),
        15:((20,-1,10,-1,40), ((0,21,-1,11,-1,45,2),(1,22,-1,12,-1,44,2))),
        44:((20,-1,10,-1,40), ((0,21,-1,11,-1,44,2),(1,22,-1,11,-1,45,2))),
        45:((20,-1,10,-1,40), ((0,21,-1,10,-1,44,2),)),
    }
    for case,(position,varyings) in plan_oracles.items():
        base=report+case*STRIDE*8
        normalize=lambda seq: tuple(neg(v) if v < 0 else v for v in seq)
        need(tuple(q(cpu,base+i*8) for i in range(18,23)) == normalize(position),
             f"case {case} exact canonical Position plan")
        need(tuple(q(cpu,base+i*8) for i in (23,24)) == (len(varyings),sum(v[-1] for v in varyings)),
             f"case {case} exact canonical varying counts")
        for vi,varying in enumerate(varyings):
            at=25+vi*7
            need(tuple(q(cpu,base+(at+i)*8) for i in range(7)) == normalize(varying),
                 f"case {case} exact canonical varying {vi} plan")
    b = report + 4*STRIDE*8
    need(q(cpu,b) == (1<<64)-23403 and q(cpu,b+4*8) == 2, "direct vec4 Position exact refusal")
    need(q(cpu,b+17*8) == 1, "direct vec4 refusal preserves four spans/result")
    b = report + 7*STRIDE*8
    need(q(cpu,b) == (1<<64)-23405 and q(cpu,b+4*8) == 6 and q(cpu,b+17*8) == 1,
         "late vertex span failure is transactional")
    b = report + 10*STRIDE*8
    need(q(cpu,b) == (1<<64)-23405 and q(cpu,b+4*8) == 3 and q(cpu,b+17*8) == 1,
         "viewport 65536 refuses transactionally")
    exact_stage2 = {
        16:(-23404,20,62),17:(-23403,20,62),18:(-23404,20,62),
        21:(-23404,20,62),22:(-23403,20,62),23:(-23404,21,62),24:(-23404,22,62),
        25:(-23403,43,62),26:(-23403,43,62),27:(-23403,44,62),
        34:(-23403,20,62),35:(-23403,23,62),36:(-23403,23,62),
        37:(-23403,21,62),38:(-23403,21,62),39:(-23403,21,62),
        40:(-23403,21,62),41:(-23403,21,62),42:(-23403,44,62),43:(-23403,49,62),
    }
    for case,(code,source_id,opcode) in exact_stage2.items():
        base=report+case*STRIDE*8
        need(tuple(q(cpu,base+i*8) for i in (0,1,2,3,4,17)) ==
             (neg(code),neg(code),source_id,opcode,2,1),
             f"case {case} exact semantic refusal provenance and transaction")
    base=report+19*STRIDE*8
    need(tuple(q(cpu,base+i*8) for i in (0,1,2,3,4,17)) ==
         (neg(-23402),neg(-23402),54,72,1,1),
         "case 19 exact verifier decoration-conflict provenance and transaction")
    base=report+46*STRIDE*8
    need(tuple(q(cpu,base+i*8) for i in (0,1,2,3,4,17)) ==
         (neg(-23402),neg(-23402),21,15,1,1),
         "missing live EntryPoint interface exact verifier provenance")
    for case,want,label in ((28,7,"Plan null/verifier/semantic sentinels"),
                            (29,15,"Pair null-m/null-target/verifier/semantic five-region transaction"),
                            (30,15,"input and viewport stage3 transaction"),
                            (31,63,"all six pair overlaps"),
                            (32,1023,"null/alignment/capacity/range spans")):
        need(q(cpu,report+(case*STRIDE+17)*8) == want, label)
    base=report+33*STRIDE*8
    need(tuple(q(cpu,base+i*8) for i in (0,1,2,3,4,17)) ==
         (neg(-23403),neg(-23403),40,62,2,1),
         "direct vec4 Position exact Plan refusal and sentinel")
    base=report+47*STRIDE*8
    if tuple(q(cpu,base+i*8) for i in (0,1,2,3,17)) == (neg(-23406),neg(-23406),0,0,1) and q(cpu,base+4*8) in (4,5):
        checks += 1
        bad.append(f"forced encoder stage {q(cpu,base+4*8)} preserves all five caller regions")
    for case,label in ((48,"Plan null output"),(49,"Pair null result")):
        base=report+case*STRIDE*8
        expected=(neg(-23401),neg(-23401),0,0,1)
        need(tuple(q(cpu,base+i*8) for i in range(5)) == expected,
             f"{label} exact args provenance")
    need(q(cpu,report+(49*STRIDE+17)*8) == 1,
         "Pair null result leaves all four caller spans untouched")
    return checks, bad


def encoded_anchor(source: bytes, text: str) -> bytes:
    choices = [text.encode("utf-8")]
    if "\n" in text: choices.append(text.replace("\n", "\r\n").encode("utf-8"))
    hits = [(item, source.count(item)) for item in choices]
    exact = [item for item, count in hits if count == 1]
    if len(exact) != 1 or sum(count for _, count in hits) != 1:
        raise RuntimeError(f"vertex IR42 gate: mutation anchor is not unique: {text!r}; counts={hits!r}")
    return exact[0]


def mutate_source(source: bytes, old_text: str, new_text: str) -> bytes:
    import re
    old = encoded_anchor(source, old_text)
    newline = "\r\n" if b"\r\n" in old else "\n"
    new = new_text.replace("\n", newline).encode("utf-8")
    old_eols = [m.group(0) for m in re.finditer(br"\r\n|\n|\r", old)]
    new_eols = [m.group(0) for m in re.finditer(br"\r\n|\n|\r", new)]
    if old_eols != new_eols: raise RuntimeError("vertex IR42 gate: mutation changes newline sequence")
    at = source.index(old); broken = source[:at] + new + source[at + len(old):]
    if broken[:at] != source[:at] or broken[at + len(new):] != source[at + len(old):]:
        raise RuntimeError("vertex IR42 gate: mutation changed bytes outside its one anchor")
    return broken


class MutationTally:
    def __init__(self): self.rejected = 0
    def semantic_rejection(self): self.rejected += 1


# Every replacement is a one-hit byte splice over the frozen lowerer.  The
# causal text must be present in grade() only when that invariant is violated;
# compile/timeout/execute/hash failures propagate and never increment tally.
MUTANTS = (
    ("Position extracts may be reversed", "case 0 rc",
     "Or *x\\literal0 <> 0 Or *y\\literal0 <> 1 Or *x\\operand0 <> *y\\operand0",
     "Or *x\\literal0 <> 1 Or *y\\literal0 <> 0 Or *x\\operand0 <> *y\\operand0"),
    ("Position exact zero and one may swap", "case 0 rc",
     "If avk42VertexScalarBits(*m, *construct\\operand2, $00000000) = 0 Or avk42VertexScalarBits(*m, *construct\\operand3, $3F800000) = 0",
     "If avk42VertexScalarBits(*m, *construct\\operand2, $3F800000) = 0 Or avk42VertexScalarBits(*m, *construct\\operand3, $00000000) = 0"),
    ("direct vec4 Position is accepted", "direct vec4 Position exact Plan refusal",
     "  Protected variableId.i\n  If *construct = 0 Or *construct\\kind <> #ANVIL_IR_OP_COMPOSITE_CONSTRUCT",
     "  Protected variableId.i : If *construct <> 0 And *construct\\kind = #ANVIL_IR_OP_LOAD : PokeI(*loadOut, *construct\\sourceId) : PokeI(*variableOut, *construct\\operand0) : ProcedureReturn 1 : EndIf\n  If *construct = 0 Or *construct\\kind <> #ANVIL_IR_OP_COMPOSITE_CONSTRUCT"),
    ("Location classification aliases every varying to zero", "case 12 rc",
     "        *vary = *p + OffsetOf(AvkIrV3d42VertexPlan\\varyings) + location * SizeOf(AvkIrV3d42VertexVarying)\n",
     "        *vary = *p + OffsetOf(AvkIrV3d42VertexPlan\\varyings) + 0 * SizeOf(AvkIrV3d42VertexVarying)\n"),
    ("Store union liveness drops the final two roots", "case 12 code/uniform counts",
     "  While i < *m\\nodeCount\n    *n = avkIrNodeAt(*m, i)\n    If *n\\kind = #ANVIL_IR_OP_STORE\n      variableId = 0 : member = -1",
     "  While i < *m\\nodeCount - 2\n    *n = avkIrNodeAt(*m, i)\n    If *n\\kind = #ANVIL_IR_OP_STORE\n      variableId = 0 : member = -1"),
    ("backend emits varyings in reverse semantic order", "case 12 exact coordinate bytes",
     "  While k < *p\\varyingCount And r = 0\n    *vary = *p + OffsetOf(AvkIrV3d42VertexPlan\\varyings) + k * SizeOf(AvkIrV3d42VertexVarying)\n",
     "  While k < *p\\varyingCount And r = 0\n    *vary = *p + OffsetOf(AvkIrV3d42VertexPlan\\varyings) + (*p\\varyingCount - 1 - k) * SizeOf(AvkIrV3d42VertexVarying)\n"),
    ("odd viewport reuses truncating legacy arithmetic", "case 5 complete coordinate uniform stream",
     "  halfW = *t\\viewportWidth * 128 : halfH = *t\\viewportHeight * 128\n",
     "  halfW = (*t\\viewportWidth / 2) * 256 : halfH = (*t\\viewportHeight / 2) * 256\n"),
    ("plan publication clears instead of copying", "case 12 exact canonical Position plan",
     "  i = 0 : While i < SizeOf(AvkIrV3d42VertexPlan) : PokeA(*p + i, PeekA(@avk42VertexPlanPending + i)) : i = i + 1 : Wend\n",
     "  i = 0 : While i < SizeOf(AvkIrV3d42VertexPlan) : PokeA(*p + i, 0) : i = i + 1 : Wend\n"),
    ("pair overlap is ignored", "all six pair overlaps",
     "      If avk42RangesOverlap(bases[i], sizes[i], bases[j], sizes[j]) <> 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_RANGE, 0, 0, 6) : EndIf\n",
     "      If avk42RangesOverlap(bases[i], sizes[i], bases[j], sizes[j]) < 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_RANGE, 0, 0, 6) : EndIf\n"),
    ("pair result publishes zero bytes", "case 0 code/uniform counts",
     "  i = 0 : While i < SizeOf(AvkIrV3d42VertexPairResult) : PokeA(*r + i, PeekA(@avk42VertexPairPending + i)) : i = i + 1 : Wend\n",
     "  i = 0 : While i < SizeOf(AvkIrV3d42VertexPairResult) : PokeA(*r + i, 0) : i = i + 1 : Wend\n"),
    ("coordinate final encoder error", "forced encoder stage 4 preserves all five caller regions",
     "  If coordinate <> 0\n    If r = 0 : r = avk42EmitStvpm(0, b + *pos\\firstSlot) : EndIf",
     "  If coordinate <> 0 : r = -1\n    If r = 0 : r = avk42EmitStvpm(0, b + *pos\\firstSlot) : EndIf"),
    ("vertex final encoder error", "forced encoder stage 5 preserves all five caller regions",
     "    slot = 6\n  Else\n    If r = 0 : r = avk42EmitStvpm(0, temp) : EndIf",
     "    slot = 6\n  Else : r = -1\n    If r = 0 : r = avk42EmitStvpm(0, temp) : EndIf"),
    ("Position interface block incorrectly requires Offset", "case 11 rc",
     "  If avk42Decoration(*m, *block\\sourceId, -1, #ANVIL_IR_DEC_BLOCK) < 0 : ProcedureReturn 0 : EndIf\n  If avk42Decoration(*m, *block\\sourceId, member, #ANVIL_IR_DEC_BUILTIN) <> #ANVIL_IR_BUILTIN_POSITION",
     "  If avk42Decoration(*m, *block\\sourceId, -1, #ANVIL_IR_DEC_BLOCK) < 0 Or avk42Decoration(*m, *block\\sourceId, member, #ANVIL_IR_DEC_OFFSET) < 0 : ProcedureReturn 0 : EndIf\n  If avk42Decoration(*m, *block\\sourceId, member, #ANVIL_IR_DEC_BUILTIN) <> #ANVIL_IR_BUILTIN_POSITION"),
    ("isolated viewport cap is reduced below public decoder", "case 9 rc",
     "*t\\viewportWidth > 65535 Or *t\\viewportHeight > 65535",
     "*t\\viewportWidth > 32767 Or *t\\viewportHeight > 32767"),
    ("Plan clears caller storage before validation", "Plan null/verifier/semantic sentinels",
     "  If *p = 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_ARGS, 0, 0, 1) : EndIf\n  ; Planning is transactional too",
     "  If *p = 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_ARGS, 0, 0, 1) : EndIf : avk42ClearVertexPlan(*p)\n  ; Planning is transactional too"),
    ("Pair clears caller result before validation", "Pair null-m/null-target/verifier/semantic five-region transaction",
     "  If *r = 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_ARGS, 0, 0, 1) : EndIf\n  ; The caller's result is part of the same four-span transaction",
     "  If *r = 0 : ProcedureReturn avk42Fail(#ANVIL_IR_V3D42_ERR_ARGS, 0, 0, 1) : EndIf : avk42ClearVertexPairResult(*r)\n  ; The caller's result is part of the same four-span transaction"),
    ("Position source Load need not be exact vec2", "case 0 rc",
     "  loadId = avk42VertexWholeInputLoad(*m, *x\\operand0, 2, @variableId)\n",
     "  loadId = avk42VertexWholeInputLoad(*m, *x\\operand0, 4, @variableId)\n"),
)


def infra_self_test(compiler: pathlib.Path) -> None:
    temp = pathlib.Path(tempfile.gettempdir())
    before = {p.resolve() for pattern in ("anvil_vertex_ir42_*",)
              for p in temp.glob(pattern) if p.is_dir()}
    entries = compile_entries()
    snapshot, manifest = freeze_inputs(entries)
    fake = pathlib.Path(tempfile.mkdtemp(prefix="anvil_vertex_ir42_fake_"))
    fake_compiler = fake / "compiler.exe"
    fake_compiler.write_bytes(b"compiler")
    tally = MutationTally()
    flags = {name: False for name in ("immutable", "compile", "timeout", "execute",
                                      "compiler", "snapshot", "shared", "combined")}

    def failed(*args, **kwargs): return subprocess.CompletedProcess(args[0], 1, "injected compile failure")
    def timed(*args, **kwargs): raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    def success(*args, **kwargs):
        pathlib.Path(args[0][args[0].index("-o") + 1]).write_bytes(b"image")
        return subprocess.CompletedProcess(args[0], 0, "pmfc: OK")
    def execute_failure(*args, **kwargs): raise SystemExit("injected execute failure")
    def compiler_drift(*args, **kwargs): fake_compiler.write_bytes(b"changed"); return success(*args, **kwargs)
    def snapshot_drift(*args, **kwargs):
        victim = snapshot / MODULE.relative_to(ROOT); victim.write_bytes(victim.read_bytes() + b"\n")
        return success(*args, **kwargs)
    try:
        before_load = snapshot_manifest(snapshot)
        loaded = load_module("anvil_vertex_ir42_a64_selftest", snapshot / INTERPRETER.relative_to(ROOT))
        flags["immutable"] = snapshot_manifest(snapshot) == before_load and callable(getattr(loaded, "A64", None))
        sys.modules.pop("anvil_vertex_ir42_a64_selftest", None)
        try: build(compiler, snapshot, manifest, sha(compiler), runner=failed)
        except RuntimeError as error: flags["compile"] = "injected compile failure" in str(error)
        try: build(compiler, snapshot, manifest, sha(compiler), runner=timed, timeout=.01)
        except subprocess.TimeoutExpired: flags["timeout"] = True
        try: build_execute(None, compiler, snapshot, manifest, sha(compiler), runner=success, execute_fn=execute_failure)
        except SystemExit as error: flags["execute"] = "injected execute failure" in str(error)
        fh = sha(fake_compiler)
        try: build(fake_compiler, snapshot, manifest, fh, runner=compiler_drift)
        except RuntimeError as error: flags["compiler"] = "compiler changed during compile" in str(error)
        fake_compiler.write_bytes(b"compiler")
        altered = dict(entries); key = sorted(altered)[0]; altered[key] += b"changed"
        try: guard_inputs(lambda: altered, framed_manifest(entries), snapshot, manifest, compiler, sha(compiler))
        except RuntimeError as error: flags["shared"] = "shared compile inputs changed" in str(error)
        try: build(compiler, snapshot, manifest, sha(compiler), runner=snapshot_drift)
        except RuntimeError as error: flags["snapshot"] = "frozen snapshot changed during compile" in str(error)
        # Restore only the private injected snapshot bytes for final cleanup tests.
        (snapshot / MODULE.relative_to(ROOT)).write_bytes(entries[MODULE.relative_to(ROOT).as_posix()])
        combined, _ = freeze_inputs({"sentinel": b"frozen"})
        primary = SystemExit("injected combined execute failure")
        def persistent_drift(): raise RuntimeError("injected persistent guard drift")
        try:
            try: raise primary
            finally: finalize_snapshot(persistent_drift, combined, sys.exc_info()[1])
        except SystemExit as error:
            flags["combined"] = error is primary and not combined.exists() and any("persistent guard drift" in n for n in getattr(error, "__notes__", ()))
        sample = b"a\r\nb\nc\r\n"; broken = mutate_source(sample, "b\n", "x\n")
        if broken != b"a\r\nx\nc\r\n": raise RuntimeError("vertex IR42 gate: EOL splice self-test failed")
    finally:
        try: remove_private_tree(snapshot)
        finally: remove_private_tree(fake)
    after = {p.resolve() for pattern in ("anvil_vertex_ir42_*",)
             for p in temp.glob(pattern) if p.is_dir()}
    if not all(flags.values()): raise RuntimeError(f"vertex IR42 gate: infra self-test failed: {flags}")
    if tally.rejected != 0: raise RuntimeError("vertex IR42 gate: infra failure counted as semantic kill")
    if after != before: raise RuntimeError(f"vertex IR42 gate: infra self-test leaked roots: {after-before}")
    print("vulkan_vertex_ir_v3d42_check: infra self-test PASS - immutable load; compile/timeout/execute/compiler/snapshot/shared drift abort; combined primary preserved; rejected=0; temp roots unchanged")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--compiler", default=str(COMPILER)); parser.add_argument("--self-test-infra", action="store_true"); parser.add_argument("--mutate", action="store_true"); args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = pathlib.Path(args.compiler).resolve()
    if compiler != COMPILER.resolve() or sha(compiler) != COMPILER_SHA: raise RuntimeError("pinned compiler mismatch")
    if sha(INTERPRETER) != INTERPRETER_SHA: raise RuntimeError("pinned interpreter mismatch")
    if args.self_test_infra:
        infra_self_test(compiler); return 0
    entries = compile_entries(); shared_manifest = framed_manifest(entries)
    snapshot, manifest = freeze_inputs(entries); primary = None
    try:
        def guard(): guard_inputs(lambda: compile_entries(), shared_manifest, snapshot, manifest, compiler, COMPILER_SHA)
        frozen_checker = snapshot / pathlib.Path(__file__).resolve().relative_to(ROOT)
        frozen_interp = snapshot / INTERPRETER.relative_to(ROOT)
        if sha(frozen_checker) != sha(pathlib.Path(__file__).resolve()): raise RuntimeError("frozen checker mismatch")
        if sha(frozen_interp) != INTERPRETER_SHA: raise RuntimeError("frozen interpreter mismatch")
        a64 = load_module("anvil_vertex_ir42_a64", frozen_interp)
        if snapshot_manifest(snapshot) != manifest: raise RuntimeError("snapshot changed while loading interpreter")
        source=(snapshot / MODULE.relative_to(ROOT)).read_bytes()
        preflight_mutants=[]
        if args.mutate:
            preflight_mutants=[(item,mutate_source(source,item[2],item[3])) for item in MUTANTS]
        guard()
        cpu, report, steps = build_execute(a64, compiler, snapshot, manifest, COMPILER_SHA)
        guard(); checks, bad = grade(cpu, report)
        print(f"vulkan_vertex_ir_v3d42_check: compiler={compiler} sha256={sha(compiler)}", flush=True)
        print(f"vulkan_vertex_ir_v3d42_check: checker={sha(pathlib.Path(__file__).resolve())} interpreter={sha(INTERPRETER)} manifest={manifest}", flush=True)
        if bad:
            print(f"vulkan_vertex_ir_v3d42_check: FAIL - {checks} checks / {steps:,} A64")
            for item in bad: print("  " + item)
            return 1
        print(f"vulkan_vertex_ir_v3d42_check: PASS - {checks} properties / {steps:,} A64")
        if args.mutate:
            escaped=[]; tally=MutationTally()
            for index,(item,broken) in enumerate(preflight_mutants):
                name,causal,old,new=item; guard()
                mcpu,mreport,msteps=build_execute(a64,compiler,snapshot,manifest,COMPILER_SHA,module=broken)
                guard(); mchecks,mbad=grade(mcpu,mreport)
                causal_bad=[item for item in mbad if causal in item]
                if not causal_bad:
                    escaped.append(name)
                    print(f"  SURVIVED {name}: {mchecks} properties / {msteps:,} A64",flush=True)
                    break
                tally.semantic_rejection()
                print(f"  RED {name}: {causal_bad[0]}",flush=True)
            if escaped:
                print(f"vulkan_vertex_ir_v3d42_check: FAIL - {tally.rejected}/{len(MUTANTS)} semantic mutants rejected; first survivor={escaped[0]}")
                return 1
            print(f"vulkan_vertex_ir_v3d42_check: PASS - {tally.rejected}/{len(MUTANTS)} semantic mutants rejected")
        return 0
    except BaseException as error:
        primary = error; raise
    finally:
        finalize_snapshot(lambda: guard_inputs(lambda: compile_entries(), shared_manifest, snapshot, manifest, compiler, COMPILER_SHA), snapshot, primary)


if __name__ == "__main__":
    with checker_lock(): raise SystemExit(main())
