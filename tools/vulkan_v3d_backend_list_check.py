#!/usr/bin/env python3
"""Emitted A64 gate for the atomic Pi 4 V3D draw-list backend."""
from __future__ import annotations

import argparse, contextlib, importlib.util, os, pathlib, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/vulkan_v3d_backend_list_gate.pi4"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
COMPILER = pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, LR, OUT = 0x400000, 0x3000000, 0xDEAD0000, 0x7000000
MAGIC = 0x564C3344

CONTRACTS = (
    "#ANVIL_VK_CAP_DRAW_LIST", "Procedure.i avkBackendSubmitDraw(*payload)",
    "AnvilVkV3dPrepareClosedDrawSlot", "AnvilVkV3dBuildDrawSlotRecord",
    "AnvilVkV3dDrawCacheRangeOffset", "AnvilVkV3dVaryingComponents", "avkInternalAlloc(arenaBytes)",
    "avkV3dCleanCacheIntervals()", "avkV3dCacheIntervalAdd", "If *d\\sampleMask <> 0",
    "If began <> 0", "packetBytes > (Neon_BclBytes() - 8192)",
    "avkV3dNormalizeScissor", "V3dClClipWindow(sc\\x, sc\\y, sc\\w, sc\\h)",
    "avkV3dDrawViewportHalfWidthBits", "*d\\viewportW <> *d\\width",
    "V3dCacheBatchBegin()", "V3dCacheBatchRange(firstByte, endByte - firstByte)",
    "batchRc = V3dCacheBatchEnd()",
    "V3dClIndexBufferSetup(*d\\indexBase, *d\\indexBytes)",
    "V3dClIndexedPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, 1, *d\\firstVertex * 2)",
    "AnvilVkV3dBuildDrawSlotRecord(pipe, pbase, drawBase, *d, *d\\maxVertex",
)

MUTANTS = (
    ("4096 is rejected", "*list\\drawCount > #ANVIL_VK_MAX_RECORDED_DRAWS", "*list\\drawCount >= #ANVIL_VK_MAX_RECORDED_DRAWS"),
    ("stale draw k passes preflight", "If AnvilVkV3dCodeBase(pipe) = 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf", "If AnvilVkV3dCodeBase(pipe) < 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf"),
    ("firstVertex is omitted from cache maintenance", "avkV3dCacheIntervalAdd(*bind\\base + off, bytes)", "avkV3dCacheIntervalAdd(*bind\\base, bytes)"),
    ("BCL overflow reaches frame begin", "packetBytes > (Neon_BclBytes() - 8192)", "packetBytes < 0"),
    ("negative vertex index reaches address arithmetic", "If *d\\firstVertex < 0 Or *d\\firstVertex > $FFFFFFFF Or *d\\vertexCount < 1 Or *d\\vertexCount > $FFFFFFFF Or *d\\maxVertex < 0 Or *d\\maxVertex > $FFFFFFFF", "If *d\\firstVertex < -1 Or *d\\firstVertex > $FFFFFFFF Or *d\\vertexCount < 1 Or *d\\vertexCount > $FFFFFFFF Or *d\\maxVertex < 0 Or *d\\maxVertex > $FFFFFFFF"),
    ("errored frame is not ended", "If began <> 0\n    endRc = NeonFrameEnd()", "If began < 0\n    endRc = NeonFrameEnd()"),
    ("sample mask zero emits primitives", "; A zero sample mask is still fully validated and owns a private slot,\n      ; but emits no state and no primitive.\n      If *d\\sampleMask <> 0", "; A zero sample mask is still fully validated and owns a private slot,\n      ; but emits no state and no primitive.\n      If *d\\sampleMask >= 0"),
    ("blend transitions are not cached", "If blend <> *d\\blendMode\n          If *d\\blendMode = #ANVIL_VK_BLEND_SRC_OVER", "If blend < -1\n          If *d\\blendMode = #ANVIL_VK_BLEND_SRC_OVER"),
    ("adjacent physical cache spans are not merged", "If avkV3dCacheInterval[i]\\firstByte <= endByte", "If avkV3dCacheInterval[i]\\firstByte < endByte"),
    ("last record aliases freed draw arena", "avkV3dLastRecord = @avkV3dLastRecordCopy[0]", "avkV3dLastRecord = source"),
    ("scissor transition cache is bypassed", "ElseIf sc\\x <> clipX Or sc\\y <> clipY Or sc\\w <> clipW Or sc\\h <> clipH", "ElseIf 1 = 1"),
    ("negative scissor offset does not reduce the extent", "If w <= cut : w = 0 : Else : w = w - cut : EndIf", "If w <= cut : w = 0 : EndIf"),
    ("hostile scissor width escapes atomic preflight", "Or *d\\scissorW < 0 Or *d\\scissorW > $FFFFFFFF", "Or *d\\scissorW < 0 Or *d\\scissorW > $1FFFFFFFF"),
    ("cache transaction is not completed", "batchRc = V3dCacheBatchEnd()", "batchRc = cleaned"),
    ("indexed firstIndex is doubled", "V3dClIndexedPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, 1, *d\\firstVertex * 2)", "V3dClIndexedPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, 1, *d\\firstVertex * 4)"),
    ("indexed draw slot uses count instead of scanned max", "AnvilVkV3dBuildDrawSlotRecord(pipe, pbase, drawBase, *d, *d\\maxVertex, AnvilVkV3dVaryingComponents(pipe))", "AnvilVkV3dBuildDrawSlotRecord(pipe, pbase, drawBase, *d, *d\\firstVertex + *d\\vertexCount - 1, AnvilVkV3dVaryingComponents(pipe))"),
    ("index cache clean starts at bind base", "avkV3dCacheIntervalAdd(*d\\indexBase + indexOffset, bytes)", "avkV3dCacheIntervalAdd(*d\\indexBase, bytes)"),
)

@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0: f.write(b"0"); f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try: yield
            finally: f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def build(compiler: pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(tempfile.gettempdir()) / "anvil_v3d_backend_list.img"
    env = os.environ.copy(); env["PMF_ROOT"] = str(ROOT)
    cmd = [str(compiler), "--compile", GATE.relative_to(ROOT).as_posix(), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "--entry-returns",
           "-o", str(out), "-s"]
    run = subprocess.run(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise RuntimeError("compile failed\n" + run.stdout)
    return out

def execute(interp: pathlib.Path, image: pathlib.Path, ceiling=200_000_000):
    spec = importlib.util.spec_from_file_location("anvil_v3d_list_a64", interp)
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    cpu = mod.A64()
    for i, b in enumerate(image.read_bytes()): cpu.memory[LOAD + i] = b
    mod.attach_symbols(cpu, image, LOAD); cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR
    for steps in range(ceiling):
        if cpu.pc == LR: return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise RuntimeError("execution ceiling reached")

def u64(cpu, addr): return sum(cpu.memory.get(addr+i, 0) << (8*i) for i in range(8))

def grade(cpu, rc, stress_n=3505, admission_n=4096):
    s = [u64(cpu, OUT+i*8) for i in range(120)]; bad=[]
    def need(name, i, want):
        if s[i] != want: bad.append(f"{name}: got {s[i]:#x}, expected {want:#x}")
    need("return", -1, OUT) if False else None
    if rc != OUT: bad.append(f"return: got {rc:#x}, expected {OUT:#x}")
    for name,i,w in (
      ("magic",0,MAGIC),("DRAW_LIST",1,1),
      ("one rc",2,0),("one begin",3,1),("one end",4,1),("one rebind+restore",5,2),("one alloc",6,1),("one free",7,1),("one primitive",8,1),
      ("three rc",9,0),("masked primitive count",10,2),("shader count",11,2),("viewport transitions",12,1),("cfg transitions",13,2),("blend enables",14,2),("blend cfg",15,1),("varying transitions",16,2),
      ("exact slot cache ranges",17,4),("merged vertex range count",18,1),("merged vertex start",19,0x2200010),("merged vertex bytes",20,64),
      ("live stress rc",23,0),("live stress arena",24,stress_n*896),("live stress primitives",25,stress_n),("live stress begin",26,1),("live stress free",27,1),
      ("admission rc",28,0),("admission arena",29,admission_n*896),("admission masked primitives",30,0),("admission begin",31,1),("admission free",32,1),
      ("stale k refused",33,(-1)&0xffffffffffffffff),("stale pre-begin",34,0),("stale pre-allocation",35,0),
      ("overflow refused",36,(-1)&0xffffffffffffffff),("overflow pre-begin",37,0),("overflow pre-allocation",38,0),
      ("capacity refused",39,(-1)&0xffffffffffffffff),("capacity pre-begin",40,0),("capacity pre-allocation",41,0),
      ("rollback rc",42,(-1)&0xffffffffffffffff),("rollback begin",43,1),("rollback end",44,1),("rollback restore",45,2),("rollback free",46,1),("successful jobs only",47,6),
      ("pipeline build",50,0),("immutable pipeline clean count",51,1),("immutable pipeline clean base",52,0x02400000),("immutable pipeline clean bytes",53,8192),
      ("negative firstVertex refused",54,(-1)&0xffffffffffffffff),("negative pre-begin",55,0),("negative pre-allocation",56,0),
      ("stable record bytes",58,64),("stable record first",59,0xA5),("stable record last",60,0x5A),
      ("alias rc",61,0),("alias input ranges",62,15),("alias merged ranges",63,8),("alias cache calls",64,8),
      ("alias vertex line",65,0x02200000),("alias vertex bytes",66,0x70),("alias resource line",67,0x02201000),("alias resource bytes",68,0x14),
      ("alias slot calls",69,6),("alias resource inputs",70,6),
      ("stress prepares",71,stress_n),("stress builds",72,stress_n),("stress shader packets",73,stress_n),
      ("stress merged barriers",74,2*stress_n+1),("stress input ranges",75,3*stress_n),("stress merged getter",76,2*stress_n+1),
      ("stress slot barriers",77,2*stress_n),("stress vertex barrier",78,1),("stress viewport transitions",79,1),
      ("scissor list rc",80,0),("scissor transition packets",81,2),("clipped x",82,0),("clipped y",83,60),("clipped width",84,5),("clipped height",85,4),
      ("scissor transition getter",86,2),("scissor list primitives",87,4),
      ("extreme scissor rc",88,0),("extreme clip packets",89,1),("extreme clip x",90,0),("extreme clip y",91,0),("extreme clip width",92,2),("extreme clip height",93,3),
      ("hostile scissor refused",94,(-1)&0xffffffffffffffff),("hostile scissor pre-begin",95,0),("hostile scissor pre-allocation",96,0),
      ("one draw cache barriers",97,1),("stress cache barriers",98,1),("alias cache barriers",99,1),
      ("indexed rc",100,0),("indexed excludes array packet",101,0),("indexed primitive packets",102,1),("index setup packets",103,1),
      ("index setup bind base",104,0x02202000),("index setup byte size",105,32),("hardware uint16 type",106,1),("firstIndex byte offset",107,4),
      ("indexed count",108,3),("draw slot scanned max",109,2),("indexed cache inputs",110,4),("indexed resource inputs",111,1),
      ("index range refused",112,(-1)&0xffffffffffffffff),("index range pre-begin",113,0),("index range pre-allocation",114,0),
      ("max vertex refused",115,(-1)&0xffffffffffffffff),("max vertex pre-begin",116,0),("max vertex pre-allocation",117,0),
      ("selected index cache start",118,0x02202004),("selected index cache bytes",119,6),
    ): need(name,i,w)
    if 0x03000000 <= s[57] < 0x03000000 + 4096*896: bad.append("stable record pointer still aliases the freed arena")
    return bad

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--compiler"); ap.add_argument("--interp"); ap.add_argument("--mutate",action="store_true"); ap.add_argument("--mutations-only",action="store_true"); ap.add_argument("--mutation"); args=ap.parse_args()
    compiler=pathlib.Path(args.compiler) if args.compiler else COMPILER
    interp=pathlib.Path(args.interp) if args.interp else ROOT/"tools/a64/a64_interp.py"
    src=BACKEND.read_text(encoding="utf-8")
    missing=[x for x in CONTRACTS if x not in src]
    if missing: print("vulkan_v3d_backend_list_check: FAIL missing",missing); return 1
    if not args.mutations_only:
      with checker_lock():
        t0=time.perf_counter(); cpu,rc,steps=execute(interp,build(compiler)); elapsed=time.perf_counter()-t0; bad=grade(cpu,rc)
      if bad:
        print("vulkan_v3d_backend_list_check: FAIL"); [print("  "+x) for x in bad]; return 1
      print(f"vulkan_v3d_backend_list_check: PASS - 100 property checks over 1/3/{3505}/4096 lists, {steps:,} A64 instructions, {elapsed:.3f}s")
      print("  3505 is LIVE; 4096 is admission-only (sampleMask zero); physical cache union, one-barrier transaction, lifetime, transitions and rollback passed")
    if not args.mutate: return 0
    misses=0; gate_src=GATE.read_text(encoding="utf-8")
    compact_stress=gate_src.replace("#GATE_STRESS_DRAWS = 3505", "#GATE_STRESS_DRAWS = 35", 1)
    compact=compact_stress.replace("Fill(4096,0)", "Fill(40,0)", 1)
    try:
      for name,fixed,broken in MUTANTS:
        if args.mutation and args.mutation not in name: continue
        if src.count(fixed)!=1: print("  STALE "+name); misses+=1; continue
        admission=4096 if name == "4096 is rejected" else 40
        GATE.write_text(compact_stress if admission == 4096 else compact,encoding="utf-8")
        BACKEND.write_text(src.replace(fixed,broken,1),encoding="utf-8")
        try:
            with checker_lock(): mcpu,mrc,_=execute(interp,build(compiler),20_000_000); caught=bool(grade(mcpu,mrc,35,admission))
        except Exception: caught=True
        finally: BACKEND.write_text(src,encoding="utf-8")
        print(("  CAUGHT " if caught else "  MISSED ")+name); misses += 0 if caught else 1
    finally:
      GATE.write_text(gate_src,encoding="utf-8")
    return 1 if misses else 0

if __name__ == "__main__": raise SystemExit(main())
