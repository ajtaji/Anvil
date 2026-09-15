#!/usr/bin/env python3
"""Link and production-boundary gate for the Pi 4 V3D Vulkan backend.

It builds RaspberryPi4/Tests/vulkan_v3d_backend_emitted_gate.pi4 against
the REAL display, V3D, QPU and Neon implementation, runs it on the A64
interpreter with an MMIO hard stop armed, and requires that reaching the
"no device" answer touches no hardware at all.

This gate deliberately proves nothing about GPU execution. The backend's
clear is proved on the board by
RaspberryPi4/Examples/Diagnostics/vulkanClearProof.pi4.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \\
      py -3 tools/vulkan_v3d_backend_check.py

Add --mutate to require the gate to notice a backend that claims a
device it does not have.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_v3d_backend_emitted_gate.pi4"
BACKEND = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_v3d_backend.pi4"
V3D_CORE = ROOT / "RaspberryPi4" / "Lib" / "v3d.pi4"
NEON_CORE = ROOT / "RaspberryPi4" / "Lib" / "neon.pi4"
# The board diagnostic is not executed here - it needs the GPU - but it is
# BUILT, so it cannot rot silently between slots. A diagnostic that no
# longer compiles is discovered on the bench otherwise, which is the most
# expensive place to discover it.
DIAGNOSTICS = (
    ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanClearProof.pi4",
    ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanClearRefusals.pi4",
    ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "vulkanDynamicGeometryProof.pi4",
)

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 200_000_000
MMIO = 0xFC000000

OUT = 0x06000000
ROWS = 0x06000100
TEXTS = 0x06002000
MAGIC = 0x564B4233  # "VKB3"

# A backend that lowers a clear anywhere but through the engine this tree
# proves on silicon, or that keeps a processor-side fallback, is not the
# thing the board diagnostic tests.
REQUIRED_CALLS = ("NeonRebindSurface", "NeonFrameBegin", "NeonFrameEnd",
                  "Neon_SurfaceW", "Neon_SurfaceH", "Neon_SurfacePitch",
                  "Neon_SurfaceBytes", "Neon_SurfaceFormat",
                  "Neon_SurfaceRotation", "Neon_CapacityPhysicalW",
                  "Neon_CapacityPhysicalH")
REQUIRED_DESCRIPTOR_CONTRACT = (
    "If (colourBase - avkV3dWindowBase) > (avkV3dWindowBytes - 16)",
    "V3dCacheRange(colourBase, 16)",
)
REQUIRED_SAMPLE_MASK_CONTRACT = (
    "If *d\\sampleMask <> 0",
    "V3dClVertexArrayPrims(#AVKQ_PRIM_TRIANGLES, *d\\vertexCount, *d\\firstVertex)",
)
REQUIRED_HOST_COHERENT_BACKEND = (
    "#VK_MEMORY_PROPERTY_HOST_COHERENT_BIT",
    "V3dCacheRange(pbase, #AVKQ_BYTES)",
    "V3dCacheRange(*bind\\base, lastVertex * *bind\\stride)",
)
REQUIRED_HOST_COHERENT_COMPLETION = (
    "If (sts & #V3D_CTL_INT_FRDONE) <> 0",
    "v3d_renCleanRc = V3dCleanCaches()",
    "V3dCacheRange(v3d_rtAddr, v3d_rtBytes)",
)
FORBIDDEN_TOKENS = ("PokeN(", "PokeI(", "PokeL(", "PokeA(", "DspCopy", "DmaCopy",
                    "DisplayClear", "DspDmaFill", "DisplayFillRect", "CopyMemory")

MUTANTS = (
    (
        "the backend claims a device with the engine down",
        "  If Neon_Ready() = 0 : ProcedureReturn 0 : EndIf\n"
        "  ProcedureReturn #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR | #ANVIL_VK_CAP_GPU | #ANVIL_VK_CAP_DRAW\n",
        "  ProcedureReturn #ANVIL_VK_CAP_DEVICE | #ANVIL_VK_CAP_CLEAR_COLOR | #ANVIL_VK_CAP_GPU | #ANVIL_VK_CAP_DRAW\n",
    ),
    (
        "vkCreateDevice no longer checks that the engine is initialised",
        "Procedure.i avkBackendPrepare()\n  If Neon_Ready() = 0\n",
        "Procedure.i avkBackendPrepare()\n  If Neon_Ready() < 0\n",
    ),
    (
        "a window that is not page aligned is accepted",
        "  If base <= 0 Or (base % 4096) <> 0\n",
        "  If base <= 0\n",
    ),
    (
        "a clear is attempted with no geometry to render it at",
        "  If Neon_Ready() = 0 : ProcedureReturn #VK_ERROR_DEVICE_LOST : EndIf\n",
        "  If Neon_Ready() < 0 : ProcedureReturn #VK_ERROR_DEVICE_LOST : EndIf\n",
    ),
    (
        "a descriptor-backed TMU load no longer proves its sixteen bytes are mapped",
        "    If (colourBase - avkV3dWindowBase) > (avkV3dWindowBytes - 16)\n",
        "    If (colourBase - avkV3dWindowBase) > avkV3dWindowBytes\n",
    ),
    (
        "a descriptor-backed TMU load is submitted without a cache clean",
        "      V3dCacheRange(colourBase, 16)\n",
        "      V3dCacheRange(colourBase, 0)\n",
    ),
    (
        "sample mask zero still emits a primitive",
        "    If *d\\sampleMask <> 0\n      V3dClGlShaderState",
        "    If *d\\sampleMask >= 0\n      V3dClGlShaderState",
    ),
    (
        "a HOST_COHERENT vertex range reaches the GPU without cache maintenance",
        "      V3dCacheRange(*bind\\base, lastVertex * *bind\\stride)\n",
        "      V3dCacheRange(*bind\\base, 0)\n",
    ),
)

DYNAMIC_MUTANTS = (
    (
        "the public render fence is published from RFC before FRDONE",
        V3D_CORE,
        "    sts = V3dCoreRead(#V3D_CTL_INT_STS)\n"
        "    If (sts & #V3D_CTL_INT_FRDONE) <> 0\n",
        "    sts = V3dCoreRead(#V3D_CLE_RFC)\n"
        "    If sts <> v3d_renRfcBefore\n",
    ),
    (
        "partial right and bottom tiles are truncated instead of rounded outward",
        V3D_CORE,
        "  tilesX = (width  + tileW - 1) / tileW\n  tilesY = (height + tileH - 1) / tileH\n",
        "  tilesX = width / tileW\n  tilesY = height / tileH\n",
    ),
    (
        "the planner loses the binner allocation headroom",
        V3D_CORE,
        "  n = n + (512 * 1024)\n  ProcedureReturn n\nEndProcedure\n",
        "  ProcedureReturn n\nEndProcedure\n",
    ),
    (
        "a geometry change is accepted during an active frame",
        NEON_CORE,
        "  Protected plan.V3dRenderPlan\n\n  If gNeonReady = 0\n    neon_err = #NEON_ERR_ARENA\n    ProcedureReturn #NEON_ERR_ARENA\n  EndIf\n  If neon_inFrame <> 0\n",
        "  Protected plan.V3dRenderPlan\n\n  If gNeonReady = 0\n    neon_err = #NEON_ERR_ARENA\n    ProcedureReturn #NEON_ERR_ARENA\n  EndIf\n  If neon_inFrame < 0\n",
    ),
    (
        "a render target outside the mapped span reaches V3D",
        NEON_CORE,
        "  If base < neon_mapBase Or (base - neon_mapBase) > (neon_mapBytes - bytes)\n",
        "  If base < neon_mapBase And (base - neon_mapBase) > (neon_mapBytes - bytes)\n",
    ),
    (
        "a geometry larger than the carved capacity is accepted",
        NEON_CORE,
        "  If pw > neon_capPhysW Or ph > neon_capPhysH\n",
        "  If pw > neon_capPhysW And ph > neon_capPhysH\n",
    ),
    (
        "a rebind ignores undersized tile pools",
        NEON_CORE,
        "  If plan\\tileAllocBytes > neon_tallocBytes Or plan\\tileStateBytes > neon_tstateBytes\n",
        "  If plan\\tileAllocBytes > neon_tallocBytes And plan\\tileStateBytes > neon_tstateBytes\n",
    ),
    (
        "a failed rebind no longer reinstalls the old geometry",
        NEON_CORE,
        "    rollbackRc = V3dRenderBegin(oldPw, oldPh, oldFmt)\n",
        "    rollbackRc = r\n",
    ),
    (
        "a successful rebind leaves stale coordinate tables",
        NEON_CORE,
        "  neon_BuildCoordinateTables(pw, ph, cx, cy)\n",
        "  ; coordinate tables deliberately left stale\n",
    ),
)

# RULES THIS DESK GATE CANNOT REACH. Each compares against a number that
# only exists once the graphics engine is initialised, so no desk run can
# mutate-test it - the engine-not-ready refusal answers first. They are
# NOT therefore unproven: each carries the board run that settled it, in
# BOTH directions. A rule added here without a proof prints as OWED and
# FAILS the gate, so it stays visible until it has one.
DESK_UNREACHABLE = (
    ("the backend refuses the buffer the display is scanning out",
     "with the engine down Neon_SurfaceBase() is zero and the engine-not-ready "
     "refusal answers first, so no desk run reaches that comparison",
     "PROVEN BOTH DIRECTIONS on silicon. Accepting: board run 2 (2026-09-11, "
     "container a06b43e5, vulkanClearProof) cleared an image at $063E8000 against "
     "a surface at $06000000 and the rule correctly did not fire. Refusing: board "
     "run 3 (2026-09-11, container 504bd049, vulkanClearRefusals) offered it an "
     "image of EXACTLY the render geometry placed at the surface base, so every "
     "earlier check passed and only this rule could answer - vkEndCommandBuffer "
     "returned VK_ERROR_FEATURE_NOT_PRESENT (-8); report slot 2 = 1, slot 3 = -8"),
    ("dynamic render geometry rebinds completely and restores the display geometry",
     "the transaction requires an initialised Neon/V3D engine, mapped render memory, "
     "GPU submission, exact output inspection, and a subsequent display frame",
     "PROVEN BOTH DIRECTIONS on Pi 4 build 101, 2026-09-13, container "
     "275fdb26, vulkanDynamicGeometryProof. Accepting: 800x1280, 640x360 and "
     "partial-tile 257x193 each advanced bin/render once, completed a fence, "
     "had zero mismatches and exact first/last FF3380B2; a restored ordinary "
     "800x1280 frame then advanced both jobs and every word was FF2060A0. "
     "Refusing: 1281x64 returned invalid extent -20001 before either counter "
     "moved. Fixed report at 05900000 returned status zero"),
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
    raise SystemExit(f"vulkan V3D backend gate: {env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_vkv3d_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan V3D backend gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: pathlib.Path, root: pathlib.Path, source: pathlib.Path,
          load: int = LOAD, stack: int = STACK, name: str = "anvil_vk_v3d_backend.img"
          ) -> pathlib.Path:
    image = pathlib.Path(tempfile.gettempdir()) / name
    command = [
        str(compiler), "--compile", source.relative_to(root).as_posix(),
        "-t", "pi4", "--load-addr", hex(load), "--stack-addr", hex(stack),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(root)
    run = subprocess.run(command, cwd=root, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan V3D backend gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR
    seen = []

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            seen.append((addr, write))
            kind = "write" if write else "read"
            raise SystemExit(
                f"vulkan V3D backend gate: MMIO {kind} at ${addr:08X} - reaching the "
                "'no device' answer must touch no hardware, so this image is not safe "
                "to run on a desk and the refusal path has started talking to V3D")

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        guard(addr, False)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        guard(addr, True)
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"vulkan V3D backend gate: the probe did not return in {STEP_LIMIT} steps")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def cstr(cpu, addr: int, limit: int = 1024) -> str:
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


def grade(cpu, rc) -> Grader:
    g = Grader()
    g.need("gate magic", hex(u64(cpu, OUT)), hex(MAGIC))
    rows = u64(cpu, OUT + 8)
    fails = u64(cpu, OUT + 16)
    g.need("gate return code", rc, 0)
    g.need("in-image failures", fails, 0)
    g.want_true("the gate ran its checks", rows >= 30, str(rows))
    if fails:
        bad = [str(i + 1) for i in range(rows) if u64(cpu, ROWS + i * 8) == 0]
        g.failures.append("failed in-image rows: " + ",".join(bad))
    for _ in range(rows):
        g.checks += 1

    name = cstr(cpu, u64(cpu, OUT + 24))
    g.want_true("the backend names the part and the path it uses",
                "V3D" in name and "GPU" in name and "processor" in name, repr(name[:110]))

    for i in range(3):
        ptr = u64(cpu, TEXTS + i * 8)
        g.want_true(f"refusal {i + 1} has a sentence", ptr != 0)
        if not ptr:
            continue
        text = cstr(cpu, ptr)
        g.want_true(f"refusal {i + 1} ends as a sentence", text.endswith("."), repr(text[:70]))
        g.want_true(f"refusal {i + 1} is not a bare code", len(text.split()) >= 14, repr(text[:70]))
        g.want_true(f"refusal {i + 1} names its code",
                    ("Anvil code -200" in text) or ("VkResult -" in text), repr(text[:110]))
    return g


def source_contract(text: str) -> list[str]:
    """Rules that need a live engine to execute, kept visible at the desk.

    The board diagnostic supplies the silicon half. This source half prevents
    the mapped-range and cache-maintenance calls from disappearing before the
    board run can exercise the descriptor lookup.
    """
    failures = []
    for call in REQUIRED_CALLS:
        if call not in text:
            failures.append("the backend never calls " + call)
    for snippet in REQUIRED_DESCRIPTOR_CONTRACT:
        if snippet not in text:
            failures.append("the descriptor TMU contract lost: " + snippet)
    for snippet in REQUIRED_SAMPLE_MASK_CONTRACT:
        if snippet not in text:
            failures.append("the sample-mask suppression contract lost: " + snippet)
    for snippet in REQUIRED_HOST_COHERENT_BACKEND:
        if snippet not in text:
            failures.append("the HOST_COHERENT submit contract lost: " + snippet)
    core = V3D_CORE.read_text(encoding="utf-8")
    start = core.find("Procedure.i V3dRenderWait(us.i)")
    end = core.find("EndProcedure", start)
    render_wait = core[start:end] if start >= 0 and end > start else ""
    for snippet in REQUIRED_HOST_COHERENT_COMPLETION:
        if snippet not in render_wait:
            failures.append("the HOST_COHERENT completion contract lost: " + snippet)
    for token in FORBIDDEN_TOKENS:
        if token in text:
            failures.append("the backend holds a processor-side fallback token " + token)

    neon = NEON_CORE.read_text(encoding="utf-8")
    begin = neon.find("Procedure.i NeonRebindSurface(")
    end = neon.find("EndProcedure", begin)
    rebind = neon[begin:end] if begin >= 0 and end > begin else ""
    dynamic_required = (
        "If neon_inFrame <> 0",
        "If base < neon_mapBase Or (base - neon_mapBase) > (neon_mapBytes - bytes)",
        "If pw > neon_capPhysW Or ph > neon_capPhysH",
        "If plan\\tileAllocBytes > neon_tallocBytes Or plan\\tileStateBytes > neon_tstateBytes",
        "rollbackRc = V3dRenderBegin(oldPw, oldPh, oldFmt)",
        "neon_BuildCoordinateTables(pw, ph, cx, cy)",
    )
    for snippet in dynamic_required:
        if snippet not in rebind:
            failures.append("the transactional geometry contract lost: " + snippet)
    planned = rebind.find("r = V3dRenderBegin(pw, ph, outFmt)")
    tabled = rebind.find("neon_BuildCoordinateTables(pw, ph, cx, cy)")
    published = rebind.find("neon_fb = base")
    if planned < 0 or tabled < planned or published < tabled:
        failures.append("the new surface is published before V3D and its coordinate tables are complete")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()

    compiler = locate("PMF_COMPILER", args.compiler, [ROOT / "PureMetalForge.exe", ROOT / "compiler"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    original = BACKEND.read_text(encoding="utf-8")
    source_failures = source_contract(original)
    if source_failures:
        print("vulkan_v3d_backend_check: FAIL")
        for failure in source_failures:
            print("  " + failure)
        return 1

    # Both board diagnostics must at least build, at their own load address.
    for diagnostic in DIAGNOSTICS:
        try:
            build(compiler, ROOT, diagnostic, 0x500000, 0x4F00000,
                  "anvil_" + diagnostic.stem + ".img")
        except SystemExit as exc:
            print("vulkan_v3d_backend_check: FAIL")
            print("  %s no longer builds, so the next GPU slot would" % diagnostic.name)
            print("  have been spent discovering that on the bench:")
            print("  " + str(exc).splitlines()[0][:160])
            return 1
    diagnostic_built = True

    cpu, rc, steps = execute(a64, build(compiler, ROOT, GATE))
    g = grade(cpu, rc)
    if g.failures:
        print(f"vulkan_v3d_backend_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"vulkan_v3d_backend_check: PASS - {g.checks} property checks over "
          f"{steps:,} executed A64 instructions")
    print("  the real display, V3D, QPU and Neon implementation is linked with the Vulkan")
    print("  object engine and the V3D backend; the whole closure resolves at this revision")
    print("  with the engine down the backend enumerates no device and refuses every clear")
    print("  NOT ONE MMIO ACCESS was made reaching that answer")
    print("  the backend lowers only through NeonRebindSurface/NeonFrameBegin/NeonFrameEnd and")
    print("  holds no processor-side or DMA image fallback")
    print("  HOST_COHERENT is backed by required submit and render-completion cache maintenance")
    if diagnostic_built:
        print("  all three board diagnostics build at $500000 - vulkanClearProof.pi4,")
        print("  vulkanClearRefusals.pi4 and vulkanDynamicGeometryProof.pi4")
        print("  (not executed: they need the GPU, and that is a slot)")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    missed = 0
    with tempfile.TemporaryDirectory(prefix="anvil-vkv3d-") as td:
        work = pathlib.Path(td)
        for name, fixed, broken in MUTANTS:
            if original.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor appears "
                      f"{original.count(fixed)} times; not tested")
                missed += 1
                continue
            mutated = original.replace(fixed, broken, 1)
            BACKEND.write_text(mutated, encoding="utf-8")
            try:
                source_red = source_contract(mutated)
                if source_red:
                    red, first = True, source_red[0][:100]
                else:
                    mcpu, mrc, msteps = execute(a64, build(compiler, ROOT, GATE))
                    mg = grade(mcpu, mrc)
                    red = bool(mg.failures)
                    first = mg.failures[0][:100] if mg.failures else ""
            except SystemExit as exc:
                # An MMIO stop or a build failure IS the gate noticing.
                red, first = True, str(exc).splitlines()[0][:100]
            finally:
                BACKEND.write_text(original, encoding="utf-8")
            if red:
                print(f"  RED    {name} - {first}")
            else:
                print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE")
                missed += 1

        for name, path, fixed, broken in DYNAMIC_MUTANTS:
            original_dynamic = path.read_text(encoding="utf-8")
            if original_dynamic.count(fixed) != 1:
                print(f"  STALE  {name} - its anchor appears "
                      f"{original_dynamic.count(fixed)} times; not tested")
                missed += 1
                continue
            path.write_text(original_dynamic.replace(fixed, broken, 1), encoding="utf-8")
            try:
                source_red = source_contract(BACKEND.read_text(encoding="utf-8"))
                if source_red:
                    red, first = True, source_red[0][:100]
                else:
                    mcpu, mrc, msteps = execute(a64, build(compiler, ROOT, GATE))
                    mg = grade(mcpu, mrc)
                    red = bool(mg.failures)
                    first = mg.failures[0][:100] if mg.failures else ""
            except SystemExit as exc:
                red, first = True, str(exc).splitlines()[0][:100]
            finally:
                path.write_text(original_dynamic, encoding="utf-8")
            if red:
                print(f"  RED    {name} - {first}")
            else:
                print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE")
                missed += 1

    owed = 0
    for name, why, proof in DESK_UNREACHABLE:
        if proof:
            print(f"  BOARD  {name}")
            print(f"         {proof}")
        else:
            owed += 1
            print(f"  OWED   {name}")
            print(f"         not reachable from a desk, and not proven on one: {why}")

    if missed:
        print()
        print(f"vulkan_v3d_backend_check: {missed} of {len(MUTANTS) + len(DYNAMIC_MUTANTS)} mutations were not caught")
        return 1
    if owed:
        print()
        print(f"vulkan_v3d_backend_check: all {len(MUTANTS) + len(DYNAMIC_MUTANTS)} desk-reachable mutations rejected, "
              f"but {owed} desk-unreachable rule(s) have no board proof and are not claimed")
        return 1
    print()
    print(f"vulkan_v3d_backend_check: all {len(MUTANTS) + len(DYNAMIC_MUTANTS)} desk-reachable mutations rejected; "
          f"the {len(DESK_UNREACHABLE)} desk-unreachable rules are proven on silicon in both "
          f"directions, above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
