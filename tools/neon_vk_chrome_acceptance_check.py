#!/usr/bin/env python3
"""Desk acceptance gate for the resident Neon-to-Vulkan chrome adapter.

The emitted fixture is deliberately independent of the adapter. It proves the
oracle and its hostile cases now. The production source gate becomes active as
soon as neon_vk_chrome.pi4 lands; until then the default command exits 2 with a
single explicit prerequisite rather than pretending the adapter passed.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_acceptance_gate.pi4"
HOOK_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_draw_backend_hook_gate.pi4"
GEOMETRY_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_geometry_gate.pi4"
BOX_BATCH_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_box_batch_gate.pi4"
REAL_SCENE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
DEFAULT_COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
DEFAULT_INTERP = ROOT / "tools/a64/a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 2_000_000
HOOK_STEP_LIMIT = 6_000_000
HOOK_ASSERTIONS = 48
GEOMETRY_ASSERTIONS = 45
BOX_BATCH_ASSERTIONS = 19

HOOK_LIBS = (
    "uart.pi4", "timer.pi4", "safety.pi4", "mailbox.pi4", "display.pi4",
    "v3dqpu.pi4", "v3d.pi4", "neon.pi4",
)

# Centralized: these are the frozen public names. Signatures may be tightened
# here once the implementation publishes them; the fixture never duplicates
# the list.
API_NAMES = (
    "NeonVkChromeCreate",
    "NeonVkChromeCreateWithCapacities",
    "NeonVkChromeBegin",
    "NeonVkChromeBox",
    "NeonVkChromeBoxBatchBegin",
    "NeonVkChromeBoxBatchEnd",
    "NeonVkChromeText",
    "NeonVkChromeTextTex",
    "NeonVkChromeFanBegin",
    "NeonVkChromeFanPoint",
    "NeonVkChromeFanEnd",
    "NeonVkChromeFanOutline",
    "NeonVkChromeLinesBegin",
    "NeonVkChromeLine",
    "NeonVkChromeLinesEnd",
    "NeonVkChromeScissorSet",
    "NeonVkChromeScissorClear",
    "NeonVkChromeEnd",
    "NeonVkChromeDestroy",
)

CREATION_CALLS = (
    "vkCreateImage(", "vkCreateImageView(", "vkCreateBuffer(",
    "vkCreateSampler(", "vkCreateDescriptorSetLayout(",
    "vkCreateDescriptorPool(", "vkAllocateDescriptorSets(",
    "vkCreatePipelineLayout(", "vkCreateRenderPass(",
    "vkCreateFramebuffer(", "vkCreateGraphicsPipelines(",
    "vkCreateCommandPool(", "vkAllocateCommandBuffers(", "vkCreateFence(",
)

MUTANTS = (
    ("resource identity changes between frames", "NvcSeedResources(@nvcFrame2)", "NvcSeedResources(@nvcFrame2) : nvcFrame2\\pipeline = $777", 3),
    ("a box leaves the white atlas texel", "nvcDraw[0]\\u1 = #NVC_WHITE_X1 : nvcDraw[0]\\v1 = #NVC_WHITE_Y1", "nvcDraw[0]\\u1 = 2 : nvcDraw[0]\\v1 = #NVC_WHITE_Y1", 11),
    ("text stops using the copied glyph right edge", "nvcDraw[1]\\u1 = #NVC_A_UR : nvcDraw[1]\\v1 = #NVC_A_VB", "nvcDraw[1]\\u1 = #NVC_A_UL : nvcDraw[1]\\v1 = #NVC_A_VB", 14),
    ("a later scissor overwrites an earlier draw", "nvcDraw[1]\\scissorX = 20 : nvcDraw[1]\\scissorY = 40", "nvcDraw[1]\\scissorX = 500 : nvcDraw[1]\\scissorY = 600", 18),
    ("one frame submits twice", "nvcSubmitCount = 1", "nvcSubmitCount = 2", 20),
    ("one frame presents twice", "nvcPresentCount = 1", "nvcPresentCount = 2", 21),
    ("overflow advances the draw cursor", "nvcOverflowDrawsAfter = #NVC_MAX_DRAWS", "nvcOverflowDrawsAfter = #NVC_MAX_DRAWS + 1", 24),
    ("overflow still submits", "nvcOverflowSubmitDelta = 0", "nvcOverflowSubmitDelta = 1", 25),
)


def locate(value: str | None, fallback: Path, label: str) -> Path:
    path = Path(value).expanduser() if value else fallback
    path = path.resolve()
    if not path.is_file():
        raise AssertionError(f"{label} not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_neon_vk_chrome_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor drifted: " + old)
    return text.replace(old, new, 1)


def build(compiler: Path, work: Path, name: str, source: str) -> Path:
    src = work / f"{name}.pi4"
    image = work / f"{name}.img"
    src.write_text(source, encoding="utf-8")
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        [
            str(compiler), "--compile", str(src), "-t", "pi4", "-s",
            "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", "0x800000",
            "--stack-addr", hex(STACK), "-o", str(image),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise AssertionError(name + " compile failed\n" + run.stdout)
    return image


def build_hook_gate(compiler: Path, work: Path) -> Path:
    root = work / "hook"
    libdir = root / "RaspberryPi4/Lib"
    testdir = root / "Anvil/Graphics/Vulkan/Tests"
    intrinsics = root / "RaspberryPi4/Intrinsics"
    coredir = root / "Anvil/Core"
    libdir.mkdir(parents=True)
    testdir.mkdir(parents=True)
    intrinsics.mkdir(parents=True)
    coredir.mkdir(parents=True)
    for item in HOOK_LIBS:
        shutil.copy2(ROOT / "RaspberryPi4/Lib" / item, libdir / item)
    shutil.copy2(HOOK_GATE, testdir / HOOK_GATE.name)
    shutil.copy2(
        ROOT / "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
        intrinsics / "bcm2711_hardware.def",
    )
    shutil.copy2(ROOT / "Anvil/Core/console_style.pbi", coredir / "console_style.pbi")
    image = root / "hook.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(root)
    run = subprocess.run(
        [
            str(compiler), "--compile", str(testdir / HOOK_GATE.name), "-t", "pi4", "-s",
            "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", "0x800000",
            "--stack-addr", hex(STACK), "-o", str(image),
        ],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise AssertionError("hook gate compile failed\n" + run.stdout)
    return image


def build_geometry_gate(compiler: Path, work: Path, adapter_text: str) -> Path:
    source = GEOMETRY_GATE.read_text(encoding="utf-8-sig")
    marker = "; @PRODUCTION_GEOMETRY@"
    if source.count(marker) != 1:
        raise AssertionError("production geometry injection marker drifted")
    names = (
        "nvcSolidTriangle", "nvcSolidQuad", "nvcLineQuad",
        "NeonVkChromeFanBegin", "NeonVkChromeFanPoint",
        "NeonVkChromeFanOutline", "NeonVkChromeFanEnd",
        "NeonVkChromeLinesBegin", "NeonVkChromeLine", "NeonVkChromeLinesEnd",
    )
    production = "\n\n".join(procedure_body(adapter_text, name) for name in names)
    return build(compiler, work, "geometry", source.replace(marker, production))


def build_box_batch_gate(compiler: Path, work: Path, adapter_text: str) -> Path:
    source = BOX_BATCH_GATE.read_text(encoding="utf-8-sig")
    marker = "; @PRODUCTION_BOX_BATCH@"
    if source.count(marker) != 1:
        raise AssertionError("production box batch injection marker drifted")
    names = ("NeonVkChromeBox", "NeonVkChromeBoxBatchBegin", "NeonVkChromeBoxBatchEnd")
    production = "\n\n".join(procedure_body(adapter_text, name) for name in names)
    return build(compiler, work, "box-batch", source.replace(marker, production))


def symbol_bounds(path: Path) -> tuple[int, int]:
    found: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in ("__bss_start__", "__bss_end__"):
            found[key] = int(value.strip(), 0)
    return found["__bss_start__"], found["__bss_end__"]


def execute(a64, image: Path, step_limit: int = STEP_LIMIT) -> tuple[int, int]:
    blob = image.read_bytes()
    bss = symbol_bounds(Path(str(image) + ".sym"))
    code = (LOAD, LOAD + len(blob))
    stack = (STACK - STACK_BYTES, STACK + 16)

    def contains(ranges, address: int, size: int) -> bool:
        return size > 0 and any(lo <= address and address + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(address: int, size: int) -> int:
        cpu.align_guard(address, size, False)
        if not contains((code, bss, stack), address, size):
            raise AssertionError(f"oracle read outside image/BSS/stack: {address:#x}+{size}")
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address: int, value: int, size: int) -> None:
        cpu.align_guard(address, size, True)
        if not contains((bss, stack), address, size):
            raise AssertionError(f"oracle write outside BSS/stack: {address:#x}+{size}")
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(step_limit):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError(f"emitted gate did not return within {step_limit:,} instructions")


def procedure_body(text: str, name: str) -> str:
    match = re.search(rf"(?mi)^Procedure(?:\.[A-Za-z])?\s+{re.escape(name)}\s*\([^\r\n]*\)", text)
    if not match:
        raise AssertionError(f"adapter is missing public procedure {name}")
    end = re.search(r"(?mi)^EndProcedure\s*$", text[match.end():])
    if not end:
        raise AssertionError(f"adapter procedure {name} has no EndProcedure")
    return text[match.start():match.end() + end.end()]


def procedure_containing(text: str, needle: str) -> tuple[str, str]:
    owners: list[tuple[str, str]] = []
    for match in re.finditer(r"(?mi)^Procedure(?:\.[A-Za-z])?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
        name = match.group(1)
        body = procedure_body(text, name)
        if needle in body:
            owners.append((name, body))
    if len(owners) != 1:
        raise AssertionError(f"{needle} must have one procedure owner, found {len(owners)}")
    return owners[0]


def neon_hook_source_gate(text: str) -> int:
    names = (
        "NeonDrawBackendInstall", "NeonDrawBackendClear", "NeonDrawBackendActive",
        "Neon_Box", "Neon_Text", "Neon_TextTex", "Neon_ScissorSet", "Neon_ScissorClear",
        "NeonFanBegin", "NeonFanPoint", "NeonFanEnd", "NeonFanOutline",
        "NeonLinesBegin", "NeonLine", "NeonLinesEnd",
    )
    bodies = {name: procedure_body(text, name) for name in names}
    checks = len(names)

    install = bodies["NeonDrawBackendInstall"]
    clear = bodies["NeonDrawBackendClear"]
    # Forum 915: the family is PARAMETERS. An address loaded out of a structure
    # cannot be followed by the compiler and closed a recursion loop.
    if re.search(r"\*backend|Structure\s+NeonDrawBackend", text, re.I):
        raise AssertionError("Neon hook family is loaded from memory again (forum 915)")
    if not re.search(r"boxProc\s*=\s*0\s+And\s+textProc\s*=\s*0", install, re.I) or "NeonDrawBackendClear()" not in install:
        raise AssertionError("Neon hook null install does not clear the complete family")
    checks += 1
    refusal = re.search(r"boxProc\s*=\s*0\s+Or\s+textProc\s*=\s*0", install, re.I)
    if not refusal or install.count("ProcedureReturn #NEON_ERR_ARGS") < 3:
        raise AssertionError("Neon hook partial-family install is not refused")
    checks += 1
    assignments = (
        "gNeonBackendBox          = boxProc",
        "gNeonBackendText         = textProc",
        "gNeonBackendTextTex      = textTexProc",
        "gNeonBackendScissorSet   = scissorSetProc",
        "gNeonBackendScissorClear = scissorClearProc",
        "gNeonBackendFanBegin     = fanBeginProc",
        "gNeonBackendFanPoint     = fanPointProc",
        "gNeonBackendFanEnd       = fanEndProc",
        "gNeonBackendFanOutline   = fanOutlineProc",
        "gNeonBackendLinesBegin   = linesBeginProc",
        "gNeonBackendLine         = lineProc",
        "gNeonBackendLinesEnd     = linesEndProc",
        "gNeonBackendActive       = 1",
    )
    for assignment in assignments:
        if assignment not in install or install.index(assignment) < refusal.end():
            raise AssertionError("Neon hook family is published before complete-family refusal")
    checks += len(assignments)

    clear_targets = (
        "gNeonBackendBox          = @neon_BackendBoxUnbound",
        "gNeonBackendText         = @neon_BackendTextUnbound",
        "gNeonBackendTextTex      = @neon_BackendTextTexUnbound",
        "gNeonBackendScissorSet   = @neon_BackendScissorSetUnbound",
        "gNeonBackendScissorClear = @neon_BackendScissorClearUnbound",
        "gNeonBackendFanBegin     = @neon_BackendFanBeginUnbound",
        "gNeonBackendFanPoint     = @neon_BackendFanPointUnbound",
        "gNeonBackendFanEnd       = @neon_BackendFanEndUnbound",
        "gNeonBackendFanOutline   = @neon_BackendFanOutlineUnbound",
        "gNeonBackendLinesBegin   = @neon_BackendLinesBeginUnbound",
        "gNeonBackendLine         = @neon_BackendLineUnbound",
        "gNeonBackendLinesEnd     = @neon_BackendLinesEndUnbound",
        "gNeonBackendActive       = 0",
    )
    for target in clear_targets:
        if target not in clear:
            raise AssertionError("Neon hook clear does not restore the complete native family: " + target)
    checks += len(clear_targets)

    forwarding = (
        ("Neon_Box", "gNeonBackendBox(x, y, w, h, colour)"),
        ("Neon_Text", "gNeonBackendText(font, x, y, *s, colour)"),
        ("Neon_TextTex", "gNeonBackendTextTex(font, x, y, *s, colour)"),
        ("Neon_ScissorSet", "gNeonBackendScissorSet(x, y, w, h)"),
        ("Neon_ScissorClear", "gNeonBackendScissorClear()"),
        ("NeonFanBegin", "gNeonBackendFanBegin()"),
        ("NeonFanPoint", "gNeonBackendFanPoint(x, y)"),
        ("NeonFanEnd", "gNeonBackendFanEnd(colour)"),
        ("NeonFanOutline", "gNeonBackendFanOutline(colour)"),
        ("NeonLinesBegin", "gNeonBackendLinesBegin()"),
        ("NeonLine", "gNeonBackendLine(x0, y0, x1, y1)"),
        ("NeonLinesEnd", "gNeonBackendLinesEnd(colour)"),
    )
    for name, call in forwarding:
        if call not in bodies[name]:
            raise AssertionError(f"{name} does not forward its exact public arguments")
    checks += len(forwarding)

    widget_at = text.find("Procedure NeonPalette()")
    if widget_at < 0:
        raise AssertionError("Neon widget section entry point is missing")
    widgets = text[widget_at:]
    if "NeonVkChrome" in widgets or "gNeonBackend" in widgets:
        raise AssertionError("widget code bypasses the renderer-neutral Neon primitive family")
    expected_calls = {
        "Neon_Box": 52,
        "Neon_Text": 9,
        "Neon_TextRight": 3,
        "Neon_TextCentre": 8,
        "Neon_ScissorSet": 6,
        "Neon_ScissorClear": 6,
    }
    for name, expected in expected_calls.items():
        actual = len(re.findall(rf"\b{re.escape(name)}\s*\(", widgets))
        if actual != expected:
            raise AssertionError(f"existing widget {name} call surface changed: {actual}, expected {expected}")
    checks += 1 + len(expected_calls)
    return checks


def source_gate(text: str) -> int:
    bodies = {name: procedure_body(text, name) for name in API_NAMES}
    checks = len(API_NAMES)

    # Resources are resident. Per-frame and per-primitive entry points may not
    # allocate or destroy Vulkan objects.
    frame_names = tuple(name for name in API_NAMES if name not in ("NeonVkChromeCreate", "NeonVkChromeCreateWithCapacities", "NeonVkChromeDestroy"))
    for name in frame_names:
        body = bodies[name]
        for call in CREATION_CALLS:
            if call in body:
                raise AssertionError(f"{name} creates persistent resource via {call}")
        if re.search(r"\b(?:vkDestroy|vkFree)(?:[A-Z][A-Za-z0-9_]*)\s*\(", body):
            raise AssertionError(f"{name} destroys a persistent resource")
        checks += len(CREATION_CALLS) + 1

    if not any(call in text for call in CREATION_CALLS):
        raise AssertionError("adapter creates no Vulkan resource")
    checks += 1

    box = bodies["NeonVkChromeBox"]
    if not re.search(r"(?i)white", box):
        raise AssertionError("box path does not name/use the atlas white texel")
    checks += 1

    glyph = bodies["NeonVkChromeText"]
    if not re.search(
        r"(?mi)^Procedure\.i\s+NeonVkChromeText\s*\(\s*font\.i\s*,\s*x\.i\s*,\s*"
        r"y\.i\s*,\s*\*s\s*,\s*colour\.i\s*\)",
        glyph,
    ):
        raise AssertionError("adapter text entry point is not hook-signature compatible")
    checks += 1
    if "Neon_AtlasRasterGlyphUV(" not in glyph:
        raise AssertionError("text path does not consume the copied Neon glyph UV contract")
    checks += 1
    batch_begin = bodies["NeonVkChromeBoxBatchBegin"]
    batch_end = bodies["NeonVkChromeBoxBatchEnd"]
    if "nvcBoxBatchActive = 1" not in batch_begin or "nvcBoxBatchCount = nvcBoxBatchCount + 6" not in box:
        raise AssertionError("box batch does not retain consecutive geometry")
    if "nvcDraw(first, count, colour)" not in batch_end or "nvcBoxBatchActive <> 0" not in bodies["NeonVkChromeEnd"]:
        raise AssertionError("box batch is not flushed explicitly before frame end")
    checks += 2
    textured = bodies["NeonVkChromeTextTex"]
    for marker in ("Neon_A(colour)", "Neon_AtlasRasterGeneration()", "glyphCount * 6", "Neon_AtlasRasterGlyphUV(", "nvcDraw(first, count, colour)"):
        if marker not in textured:
            raise AssertionError("textured text path lacks " + marker)
    checks += 5
    if "nvcAtlasRefresh()" not in bodies["NeonVkChromeBegin"]:
        raise AssertionError("Begin does not refresh the bitmap atlas before recording")
    checks += 1

    wrapper = bodies["NeonVkChromeCreate"]
    create = bodies["NeonVkChromeCreateWithCapacities"]
    destroy = bodies["NeonVkChromeDestroy"]
    compact_create = re.sub(r"\s+", " ", create)
    if "NeonVkChromeCreateWithCapacities(physicalDevice, device, queue, commandPool, renderPass, framebuffer, width, height, maxQuads, maxQuads)" not in re.sub(r"\s+", " ", wrapper):
        raise AssertionError("legacy Create wrapper does not preserve the single-capacity contract")
    checks += 1
    if compact_create.count("NeonDrawBackendInstall(@NeonVkChromeBox,") != 1:
        raise AssertionError("Create does not install exactly one complete hook-compatible primitive family")
    checks += 1
    callback_names = (
        "Box", "Text", "TextTex", "ScissorSet", "ScissorClear", "FanBegin", "FanPoint",
        "FanEnd", "FanOutline", "LinesBegin", "Line", "LinesEnd",
    )
    for callback in callback_names:
        if f"@NeonVkChrome{callback}" not in create:
            raise AssertionError(f"Create omits the {callback} primitive callback")
    checks += len(callback_names)
    if "If NeonDrawBackendActive() <> 0" not in create:
        raise AssertionError("Create does not refuse an already-owned Neon primitive family")
    if destroy.count("NeonDrawBackendClear()") != 1 or "nvcHooksInstalled = 0" not in destroy:
        raise AssertionError("Destroy does not clear its installed backend ownership exactly once")
    if "nvcHooksInstalled = 1" not in create:
        raise AssertionError("Create does not publish its ownership record after hook installation")
    checks += 3
    install_at = compact_create.index("NeonDrawBackendInstall(@NeonVkChromeBox,")
    measure_install = "NeonMeasureBackendInstall(@NeonVkChromeMeasureWidth, @NeonVkChromeMeasureLineHeight)"
    if compact_create.count(measure_install) != 1 or compact_create.index(measure_install) <= install_at:
        raise AssertionError("Create does not install its optional measurements after the draw backend")
    checks += 1
    last_create = max((compact_create.rfind(call) for call in CREATION_CALLS), default=-1)
    if install_at <= last_create:
        raise AssertionError("Create publishes Neon hooks before persistent Vulkan resources succeed")
    if text.count("NeonDrawBackendInstall(") != 1:
        raise AssertionError("adapter installs Neon ownership outside the successful Create path")
    checks += 2

    # Ordered draw capture must exist, and no primitive path may sort/reorder.
    if not re.search(r"(?i)\b\w*(drawCount|drawCursor|primitiveCount)\s*=\s*\w*\1\s*\+\s*1", text):
        raise AssertionError("adapter has no monotonic ordered-draw append")
    if re.search(r"(?i)\bSort(?:Array|StructuredArray|List)?\s*\(", box + glyph):
        raise AssertionError("primitive path sorts immutable draw records")
    checks += 2

    # Scissor must be recorded through public Vulkan state, not read only at
    # final submission. Both state procedures and the command must exist.
    if "vkCmdSetScissor(" not in text:
        raise AssertionError("adapter emits no Vulkan scissor snapshot")
    if not re.search(r"(?i)scissor", bodies["NeonVkChromeScissorSet"]):
        raise AssertionError("ScissorSet does not own scissor state")
    if not re.search(r"(?i)scissor", bodies["NeonVkChromeScissorClear"]):
        raise AssertionError("ScissorClear does not own scissor state")
    checks += 3

    if text.count("vkQueueSubmit(") != 1:
        raise AssertionError(f"adapter must contain one shared queue-submit site, found {text.count('vkQueueSubmit(')}")
    submit_name, _ = procedure_containing(text, "vkQueueSubmit(")
    if submit_name == "NeonVkChromeEnd" or submit_name == "nvcAtlasCreateAndUpload":
        raise AssertionError("queue-submit site is duplicated by purpose instead of shared by atlas upload and each frame")
    if len(re.findall(rf"\b{re.escape(submit_name)}\s*\(", bodies["NeonVkChromeEnd"])) != 1:
        raise AssertionError("End does not make exactly one call through the shared queue-submit helper")
    atlas_upload = procedure_body(text, "nvcAtlasCreateAndUpload")
    if len(re.findall(rf"\b{re.escape(submit_name)}\s*\(", atlas_upload)) != 1:
        raise AssertionError("atlas upload does not use the shared queue-submit helper")
    checks += 3

    pending = procedure_body(text, "NeonVkChromePresentPending")
    consume = procedure_body(text, "NeonVkChromePresentConsume")
    end = bodies["NeonVkChromeEnd"]
    if "ProcedureReturn nvdPresentPending()" not in pending:
        raise AssertionError("PresentPending does not expose the generation-tagged owner record")
    if "nvdPresentConsume(nvcTargetGeneration, nvcFramebuffer)" not in consume or "ProcedureReturn 1" not in consume:
        raise AssertionError("PresentConsume does not consume exactly one generation-tagged owner record")
    if end.count("nvdPresentPublish(nvcTargetGeneration, nvcFramebuffer") != 1:
        raise AssertionError("End does not publish exactly one generation-tagged presentation record")
    if re.search(r"\bnvcPresent\b", text):
        raise AssertionError("adapter retains the obsolete parallel one-bit presentation authority")
    if "DisplayBlit(" in text:
        raise AssertionError("adapter performs display DMA instead of leaving presentation to the display/WSI owner")
    checks += 4

    # Refusal is bounded and failure-atomic by named draw/vertex capacities.
    if not re.search(r"(?i)#\w*(?:MAX|CAP)\w*(?:DRAW|QUAD)", text):
        raise AssertionError("adapter declares no draw/quad capacity")
    if not re.search(r"(?i)#\w*(?:MAX|CAP)\w*VERT", text):
        raise AssertionError("adapter declares no vertex capacity")
    if not re.search(r"(?i)(overflow|capacity|full)", text):
        raise AssertionError("adapter names no capacity refusal")
    checks += 3

    for name in ("NeonVkChromeBox", "NeonVkChromeText"):
        body = bodies[name]
        write_at = body.find("nvcQuad(")
        if write_at < 0:
            raise AssertionError(f"{name} emits no geometry")
        prefix = body[:write_at]
        if "nvcDrawCount >= nvcMaxQuads" not in prefix:
            raise AssertionError(f"{name} does not preflight draw capacity before its first geometry write")
        if not re.search(r"nvcVertices\s*\+[^\r\n]*>\s*nvcMaxVertexQuads\s*\*\s*6", prefix):
            raise AssertionError(f"{name} does not preflight complete vertex capacity before its first geometry write")
    first_text_write = glyph.find("nvcQuad(")
    if glyph[:first_text_write].count("While ") < 1:
        raise AssertionError("Text has no complete preflight pass before writing its first glyph")
    if "#NEON_VK_CHROME_ERR_CAPACITY" in glyph[first_text_write:]:
        raise AssertionError("Text can refuse capacity after partially writing glyph geometry")
    checks += 6

    # Fan, outline and line-list primitives are lowered only into bounded
    # triangle-list vertex data. They may not call native Neon draw/V3D paths.
    geometry_names = (
        "NeonVkChromeFanBegin", "NeonVkChromeFanPoint", "NeonVkChromeFanEnd",
        "NeonVkChromeFanOutline", "NeonVkChromeLinesBegin", "NeonVkChromeLine",
        "NeonVkChromeLinesEnd",
    )
    geometry_helpers = ("nvcSolidTriangle", "nvcSolidQuad", "nvcLineQuad")
    geometry = "\n".join(
        [bodies[name] for name in geometry_names]
        + [procedure_body(text, name) for name in geometry_helpers]
    )
    for forbidden in ("neon_Draw(", "neon_Vertex(", "V3dCl", "Display", "PokeL(nvcFramebuffer"):
        if forbidden in geometry:
            raise AssertionError(f"geometry adapter bypasses Vulkan triangle-list path via {forbidden}")
    if "nvcSolidTriangle(" not in bodies["NeonVkChromeFanEnd"]:
        raise AssertionError("fan does not triangulate through the Vulkan vertex writer")
    if "nvcLineQuad(" not in bodies["NeonVkChromeFanOutline"] or "nvcLineQuad(" not in bodies["NeonVkChromeLinesEnd"]:
        raise AssertionError("outline/line list does not expand into Vulkan triangle quads")
    if "#NEON_VK_CHROME_MAX_PATH_POINTS" not in bodies["NeonVkChromeFanPoint"] or "#NEON_VK_CHROME_MAX_PATH_POINTS" not in bodies["NeonVkChromeLine"]:
        raise AssertionError("logical primitive staging is not explicitly bounded")
    for name in ("NeonVkChromeFanEnd", "NeonVkChromeFanOutline", "NeonVkChromeLinesEnd"):
        body = bodies[name]
        write_at = min((at for at in (body.find("nvcSolidTriangle("), body.find("nvcLineQuad(")) if at >= 0), default=-1)
        if write_at < 0 or "nvcVertices + needed > nvcMaxVertexQuads * 6" not in body[:write_at]:
            raise AssertionError(f"{name} writes geometry before whole-primitive capacity preflight")
    checks += 5 + len(geometry_names) + 3
    return checks


def real_scene_gate(text: str) -> int:
    if text.count("DisplayBlit(") != 1:
        raise AssertionError(f"real widget scene must have one display-owner DMA presentation, found {text.count('DisplayBlit(')}")
    if text.count("If NeonVkChromePresentConsume() <> 1") != 1:
        raise AssertionError("real widget success path does not consume exactly one adapter presentation intent")
    if "If NeonVkChromePresentPending() <> 1" not in text or "If NeonVkChromePresentPending() <> 0" not in text:
        raise AssertionError("real widget scene does not prove presentation ownership before and after consume")
    if "DisplayDmaOps() <> dmaOps + 1" not in text:
        raise AssertionError("real widget scene does not require exactly one display-owner DMA operation")
    if "DisplayDmaFallbacks() <> dmaFallbacks" not in text or "DisplayDmaRefusals() <> dmaRefusals" not in text:
        raise AssertionError("real widget scene permits display fallback or DMA refusal")
    return 5


def run_oracle(compiler: Path, a64) -> tuple[int, int, int]:
    source = GATE.read_text(encoding="utf-8-sig")
    with tempfile.TemporaryDirectory(prefix="anvil-neon-vk-chrome-") as temporary:
        work = Path(temporary)
        image = build(compiler, work, "baseline", source)
        result, steps = execute(a64, image)
        if result:
            raise AssertionError(f"oracle baseline failed assertion {result} after {steps:,} instructions")
        mutant_steps = 0
        for index, (label, old, new, expected) in enumerate(MUTANTS, 1):
            image = build(compiler, work, f"mutant{index}", replace_once(source, old, new))
            result, used = execute(a64, image)
            mutant_steps += used
            if result != expected:
                raise AssertionError(f"oracle mutant escaped ({label}): returned {result}, expected {expected}")
    return steps, mutant_steps, len(MUTANTS)


def run_hook_gate(compiler: Path, a64) -> int:
    with tempfile.TemporaryDirectory(prefix="anvil-neon-hook-") as temporary:
        image = build_hook_gate(compiler, Path(temporary))
        result, steps = execute(a64, image, HOOK_STEP_LIMIT)
        if result:
            raise AssertionError(f"Neon hook gate failed assertion {result} after {steps:,} instructions")
    return steps


def run_geometry_gate(compiler: Path, a64, adapter_text: str) -> int:
    with tempfile.TemporaryDirectory(prefix="anvil-neon-vk-geometry-") as temporary:
        image = build_geometry_gate(compiler, Path(temporary), adapter_text)
        result, steps = execute(a64, image, HOOK_STEP_LIMIT)
        if result:
            raise AssertionError(f"production geometry gate failed assertion {result} after {steps:,} instructions")
    return steps


def run_box_batch_gate(compiler: Path, a64, adapter_text: str) -> int:
    with tempfile.TemporaryDirectory(prefix="anvil-neon-vk-box-batch-") as temporary:
        image = build_box_batch_gate(compiler, Path(temporary), adapter_text)
        result, steps = execute(a64, image, HOOK_STEP_LIMIT)
        if result:
            raise AssertionError(f"production box batch gate failed assertion {result} after {steps:,} instructions")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    parser.add_argument("--oracle-only", action="store_true", help="prove the independent emitted oracle even before the adapter lands")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    try:
        compiler = locate(args.compiler, DEFAULT_COMPILER, "PureMetalForge.exe")
        interp = locate(args.interp, DEFAULT_INTERP, "A64 interpreter")
        a64 = load_interpreter(interp)
        adapter_text = ADAPTER.read_text(encoding="utf-8-sig") if ADAPTER.is_file() else ""
        hook_checks = neon_hook_source_gate(NEON.read_text(encoding="utf-8-sig"))
        hook_steps = run_hook_gate(compiler, a64)
        steps, mutant_steps, mutants = run_oracle(compiler, a64)
        if args.oracle_only:
            print(f"neon_vk_chrome_acceptance_check: ORACLE PASS - 27 emitted invariants, {steps:,} baseline A64 instructions")
            print(f"  {mutants} hostile traces rejected in {mutant_steps:,} emitted instructions")
            print(f"  Neon hook PASS: {hook_checks} source checks, {HOOK_ASSERTIONS} emitted assertions, {hook_steps:,} A64 instructions")
            return 0
        if not ADAPTER.is_file():
            print(f"neon_vk_chrome_acceptance_check: WAITING - adapter prerequisite is not present: {ADAPTER}")
            print(f"  independent oracle PASS: 27 invariants, {mutants} hostile traces rejected")
            print(f"  Neon hook PASS: {hook_checks} source checks, {HOOK_ASSERTIONS} emitted assertions")
            return 2
        checks = source_gate(adapter_text)
        geometry_steps = run_geometry_gate(compiler, a64, adapter_text)
        box_batch_steps = run_box_batch_gate(compiler, a64, adapter_text)
        scene_checks = 0
        if REAL_SCENE.is_file():
            scene_checks = real_scene_gate(REAL_SCENE.read_text(encoding="utf-8-sig"))
    except (AssertionError, KeyError, OSError, ValueError) as exc:
        print("neon_vk_chrome_acceptance_check: FAIL - " + str(exc))
        return 1
    print(f"neon_vk_chrome_acceptance_check: PASS - {checks} adapter checks and 27 emitted invariants")
    print(f"  Neon hook: {hook_checks} source checks, {HOOK_ASSERTIONS} emitted assertions in {hook_steps:,} A64 instructions")
    print(f"  Production geometry: {GEOMETRY_ASSERTIONS} emitted assertions in {geometry_steps:,} A64 instructions")
    print(f"  Box batching: {BOX_BATCH_ASSERTIONS} emitted assertions in {box_batch_steps:,} A64 instructions")
    print(f"  Oracle: {steps:,} baseline A64 instructions; {mutants} hostile traces rejected in {mutant_steps:,}")
    if scene_checks:
        print(f"  Real widget scene: {scene_checks} display-owner presentation checks")
    else:
        print(f"  Real widget scene pending: {REAL_SCENE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
