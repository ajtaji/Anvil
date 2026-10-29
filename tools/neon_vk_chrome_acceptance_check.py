#!/usr/bin/env python3
"""Desk acceptance gate for the resident Neon-to-Vulkan chrome adapter.

The emitted fixture is deliberately independent of the adapter. It proves the
oracle and its hostile cases now. The production source gate becomes active as
soon as neon_vk_chrome.pbi lands; until then the default command exits 2 with a
single explicit prerequisite rather than pretending the adapter passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
from neon_vk_geometry_contract import compose as compose_geometry, cases as geometry_cases, validate_constants as validate_geometry_constants, validate_vulkan_constants


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pbi"
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_acceptance_gate.pbi"
HOOK_GATE = ROOT / "RaspberryPi4/Tests/neon_draw_backend_hook_gate.pi4"
GEOMETRY_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_geometry_gate.pbi"
BOX_BATCH_GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_chrome_box_batch_gate.pbi"
REAL_SCENE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
FRONTEND = ROOT / "Anvil/Graphics/neon_frontend.pbi"
ADAPTER_HELPERS = (
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_line_stream.pbi",
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_outline.pbi",
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pbi",
)
DEFAULT_COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
DEFAULT_INTERP = ROOT / "tools/a64/a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 2_000_000
HOOK_STEP_LIMIT = 6_000_000
HOOK_ASSERTIONS = 55
GEOMETRY_ASSERTIONS = len(geometry_cases()[1])
BOX_BATCH_ASSERTIONS = 28
GEOMETRY_STEP_LIMIT = 20_000_000

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
    "NeonVkChromeDestroyChecked",
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
    work = work.resolve()
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
    # Canonical include closure supplies the shared owners. A partial copied
    # tree silently falls behind every native/shared ownership move.
    return build(compiler, work, "hook", HOOK_GATE.read_text(encoding="utf-8-sig"))


def build_geometry_gate(compiler: Path, work: Path, adapter_text: str) -> Path:
    source = GEOMETRY_GATE.read_text(encoding="utf-8-sig")
    marker = "; @PRODUCTION_GEOMETRY@"
    if source.count(marker) != 1:
        raise AssertionError("production geometry injection marker drifted")
    hooks, _ = hook_source_inputs()
    validate_geometry_constants(hooks, adapter_text)
    validate_vulkan_constants((ROOT / "Anvil/Graphics/Vulkan/vk_core_1_0.pbi").read_text(encoding="utf8"))
    source, _ = compose_geometry(source, adapter_text, procedure_body)
    return build(compiler, work, "geometry", source)


def build_box_batch_gate(compiler: Path, work: Path, adapter_text: str) -> Path:
    return build(compiler, work, "box-batch", box_batch_source(adapter_text))


def box_batch_source(adapter_text: str) -> str:
    source = BOX_BATCH_GATE.read_text(encoding="utf-8-sig")
    marker = "; @PRODUCTION_BOX_BATCH@"
    if source.count(marker) != 1:
        raise AssertionError("production box batch injection marker drifted")
    names = ("nvcBudgetCan", "nvcBudgetVertices", "nvcLogicalClip", "nvcLogicalVisible", "NeonVkChromeBox", "NeonVkChromeBoxBatchBegin", "NeonVkChromeBoxBatchEnd")
    production = "\n\n".join(procedure_body(adapter_text, name) for name in names)
    return source.replace(marker, production)


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
    deadline = time.monotonic() + 300
    for steps in range(step_limit):
        if steps % 1024 == 0 and time.monotonic() > deadline:
            raise AssertionError("emitted gate exceeded its five-minute wall-clock bound")
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError(f"emitted gate did not return within {step_limit:,} instructions")


def procedure_body(text: str, name: str) -> str:
    matches = list(re.finditer(rf"(?mi)^Procedure(?:\.[A-Za-z])?\s+{re.escape(name)}\s*\([^\r\n]*\)", text))
    if len(matches) != 1:
        raise AssertionError(f"expected one procedure owner for {name}, found {len(matches)}")
    match = matches[0]
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


def code_without_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        quoted = False
        for index, char in enumerate(line):
            if char == '"':
                quoted = not quoted
            if char == ';' and not quoted:
                line = line[:index]
                break
        lines.append(line)
    return "\n".join(lines)


def hook_source_inputs() -> tuple[str, dict[str, str]]:
    paths = (FRONTEND, NEON)
    text = {p: p.read_text(encoding="utf-8-sig") for p in paths}
    if 'XIncludeFile "Anvil/Graphics/neon_frontend.pbi"' not in code_without_comments(text[NEON]):
        raise AssertionError("native Neon no longer includes the named shared frontend")
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    # Widgets remain the tail of the native module; prepend the shared owner
    # so the original widget-surface check cannot consume unrelated hook code.
    return text[FRONTEND] + "\n" + text[NEON], hashes


def source_inputs() -> tuple[str, str, dict[str, str]]:
    """Read only the named native/shared owners and direct include helpers."""
    hooks, hashes = hook_source_inputs()
    paths = (ADAPTER,) + ADAPTER_HELPERS
    text = {p: p.read_text(encoding="utf-8-sig") for p in paths}
    for path in ADAPTER_HELPERS:
        include = 'XIncludeFile "' + path.relative_to(ROOT).as_posix() + '"'
        if include not in code_without_comments(text[ADAPTER]):
            raise AssertionError("adapter no longer includes its named geometry owner: " + str(path))
    hashes.update({p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    adapter = "\n".join(text[p] for p in (ADAPTER,) + ADAPTER_HELPERS)
    return hooks, adapter, hashes


def neon_hook_source_gate(text: str) -> int:
    text = code_without_comments(text)
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
        "gNeonBackendBox          = @nfc_BackendBoxUnbound",
        "gNeonBackendText         = @nfc_BackendTextUnbound",
        "gNeonBackendTextTex      = @nfc_BackendTextTexUnbound",
        "gNeonBackendScissorSet   = @nfc_BackendScissorSetUnbound",
        "gNeonBackendScissorClear = @nfc_BackendScissorClearUnbound",
        "gNeonBackendFanBegin     = @nfc_BackendFanBeginUnbound",
        "gNeonBackendFanPoint     = @nfc_BackendFanPointUnbound",
        "gNeonBackendFanEnd       = @nfc_BackendFanEndUnbound",
        "gNeonBackendFanOutline   = @nfc_BackendFanOutlineUnbound",
        "gNeonBackendLinesBegin   = @nfc_BackendLinesBeginUnbound",
        "gNeonBackendLine         = @nfc_BackendLineUnbound",
        "gNeonBackendLinesEnd     = @nfc_BackendLinesEndUnbound",
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
        # The former 52nd match was a commented seven-argument example.
        # Count actual widget calls after comments have been removed.
        "Neon_Box": 51,
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
    text = code_without_comments(text)
    bodies = {name: procedure_body(text, name) for name in API_NAMES}
    checks = len(API_NAMES)

    # Resources are resident. Per-frame and per-primitive entry points may not
    # allocate or destroy Vulkan objects.
    frame_names = tuple(name for name in API_NAMES if name not in ("NeonVkChromeCreate", "NeonVkChromeCreateWithCapacities", "NeonVkChromeDestroy", "NeonVkChromeDestroyChecked"))
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
    if "nvcAtlasMapBitmapUV(@nvcBitmapPlan[i], NeonBitmapFontBold(font))" not in glyph:
        raise AssertionError("bitmap text ignores the configured NeonFontSetup bold face")
    checks += 1
    batch_begin = bodies["NeonVkChromeBoxBatchBegin"]
    batch_end = bodies["NeonVkChromeBoxBatchEnd"]
    if "nvcBoxBatchActive = 1" not in batch_begin or "nvcBoxBatchCount = nvcBoxBatchCount + 6" not in box:
        raise AssertionError("box batch does not retain consecutive geometry")
    if "nvcDraw(first, count, colour)" not in batch_end or "nvcBoxBatchActive <> 0" not in bodies["NeonVkChromeEnd"]:
        raise AssertionError("box batch is not flushed explicitly before frame end")
    checks += 2
    textured = bodies["NeonVkChromeTextTex"]
    for marker in ("Neon_A(colour)", "Neon_AtlasRasterGeneration()", "glyphCount * 6", "Neon_AtlasRasterGlyphUV(", "nvcDrawSet(first, glyphCount * 6, colour, nvcDescriptorSet)"):
        if marker not in textured:
            raise AssertionError("textured text path lacks " + marker)
    checks += 5
    if "nvcAtlasRefresh()" not in bodies["NeonVkChromeBegin"]:
        raise AssertionError("Begin does not refresh the bitmap atlas before recording")
    checks += 1

    begin = bodies["NeonVkChromeBegin"]
    recording_guard = "If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0"
    recording_refusal = recording_guard + "\n    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE)\n  EndIf"
    if begin.count(recording_guard) != 1 or recording_refusal not in begin:
        raise AssertionError("Begin lacks terminal WSI recording preflight")
    guard_end = begin.index(recording_refusal) + len(recording_refusal)
    if any(begin.index(call) < guard_end for call in ("rc = nvcAtlasRefresh()", "rc = vkMapMemory(", "rc = vkResetCommandBuffer(")):
        raise AssertionError("Begin mutates renderer resources before WSI recording preflight")
    recording = procedure_body(text, "nvdWsiRecordingAllowed")
    markers = (
        "If nvdWsiState = #NVD_WSI_FREE : ProcedureReturn 1 : EndIf",
        "nvdWsiState <> #NVD_WSI_ACQUIRED", "nvdWsiDevice <> device",
        "nvdWsiTargetGeneration <> targetGeneration",
        "imageKey = avkWsiImageKey(device, nvdWsiSwapchain, nvdWsiImageIndex)",
        "If imageKey = 0 Or imageKey <> nvdWsiImageKey : ProcedureReturn 0 : EndIf",
        "ProcedureReturn Bool(avkWsiImageState(device, nvdWsiSwapchain, nvdWsiImageIndex) = #ANVIL_VK_WSI_IMAGE_ACQUIRED)",
    )
    if any(marker not in recording for marker in markers):
        raise AssertionError("WSI recording preflight loses acquired-image identity")
    calls=set(re.findall(r"\b(\w+)\s*\(",recording)) - {"nvdWsiRecordingAllowed","Bool","avkWsiImageKey","avkWsiImageState"}
    if calls or re.search(r"(?m)^\s*nvdWsi\w+\s*=",recording):
        raise AssertionError("WSI recording preflight is not read-only")
    checks += 4

    wrapper = bodies["NeonVkChromeCreate"]
    create = bodies["NeonVkChromeCreateWithCapacities"]
    destroy = bodies["NeonVkChromeDestroyChecked"]
    if bodies["NeonVkChromeDestroy"].count("NeonVkChromeDestroyChecked()") != 1:
        raise AssertionError("legacy Destroy does not delegate to the checked resource owner")
    checks += 1
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
    validate = procedure_body(text, "NeonVkChromePresentValidate")
    consume = procedure_body(text, "NeonVkChromePresentConsume")
    end = bodies["NeonVkChromeEnd"]
    if "ProcedureReturn nvdPresentPending()" not in pending:
        raise AssertionError("PresentPending does not expose the generation-tagged owner record")
    if "If nvdPresentPending() = 0 : ProcedureReturn 0 : EndIf" not in validate or "If nvdPresentMatches(nvcTargetGeneration, nvcFramebuffer) = 0" not in validate or "ProcedureReturn 1" not in validate:
        raise AssertionError("PresentValidate loses pending/identity refusal")
    if "nvdPresentConsume(" in validate or re.search(r"(?m)^\s*nvc\w+\s*=", validate):
        raise AssertionError("PresentValidate changes presentation ownership")
    checks += 2
    if "nvdPresentConsume(nvcTargetGeneration, nvcFramebuffer)" not in consume or "ProcedureReturn 1" not in consume:
        raise AssertionError("PresentConsume does not consume exactly one generation-tagged owner record")
    publish = procedure_body(text, "nvcFramePublish")
    finish = procedure_body(text, "NeonVkChromeFinish")
    if end.count("ProcedureReturn nvcFramePublish()") != 1 or finish.count("ProcedureReturn nvcFramePublish()") != 1:
        raise AssertionError("End/Finish do not delegate one completed-frame publication")
    if publish.count("nvdPresentPublish(nvcTargetGeneration, nvcFramebuffer") != 1:
        raise AssertionError("completed frame does not publish exactly one generation-tagged presentation record")
    if "If nvcAsync <> 0" not in end or end.index("nvcFramePending = 1") > end.index("ProcedureReturn nvcFramePublish()"):
        raise AssertionError("async End does not retain its submission before deferred publication")
    wait_error = "If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf"
    pending_clears = list(re.finditer(r"(?m)^\s*nvcFramePending\s*=\s*0\s*$", finish))
    if len(pending_clears) != 1 or wait_error not in finish or not finish.index("vkWaitForFences(") < finish.index(wait_error) < pending_clears[0].start() < finish.index("ProcedureReturn nvcFramePublish()"):
        raise AssertionError("failed completion wait releases pending resources or publishes early")
    if re.search(r"\bnvcPresent\b", text):
        raise AssertionError("adapter retains the obsolete parallel one-bit presentation authority")
    if "DisplayBlit(" in text:
        raise AssertionError("adapter performs display DMA instead of leaving presentation to the display/WSI owner")
    checks += 7

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
        physical_bound = ("glyphCount * 6 > nvcMaxVertexQuads * 6 - nvcVertices" in prefix) if name == "NeonVkChromeText" else bool(re.search(r"nvcVertices\s*\+[^\r\n]*>\s*nvcMaxVertexQuads\s*\*\s*6", prefix))
        if not physical_bound:
            raise AssertionError(f"{name} does not preflight complete vertex capacity before its first geometry write")
    first_text_write = glyph.find("nvcQuad(")
    if glyph[:first_text_write].count("While ") < 1:
        raise AssertionError("Text has no complete preflight pass before writing its first glyph")
    if "#NEON_VK_CHROME_ERR_CAPACITY" in glyph[first_text_write:]:
        raise AssertionError("Text can refuse capacity after partially writing glyph geometry")
    checks += 6

    for name, budget in (("NeonVkChromeText", "nvcBudgetCan(0, 1, logicalVertices)"), ("NeonVkChromeTextTex", "nvcBudgetCan(1, 1, glyphCount * 6)")):
        body = bodies[name]
        before, after = body.split("nvcQuad(", 1)
        if budget not in before or "nvcBitmapPlanLive[i] = 0" not in before or "nvcBitmapPlanLive[i] = 1" not in before:
            raise AssertionError(f"{name} lacks complete copied-glyph/budget preflight")
        if "Neon_AtlasRasterGlyphUV(" in after or "nvcAtlasMapBitmapUV(" in after:
            raise AssertionError(f"{name} re-resolves glyphs after writing starts")
        for field in ("left", "top", "right", "bottom"):
            if "nvcBitmapPlan[i]\\" + field not in after:
                raise AssertionError(f"{name} does not emit its copied glyph {field}")
        checks += 7

    checks += resource_ownership_source_gate(text)
    checks += geometry_source_gate(text)
    return checks


RESOURCE_MUTATION_ENTRIES = {
    "nvcAtlasUploadImage": "vkResetCommandBuffer(",
    "nvcAtlasRefresh": "Neon_AtlasRasterEnsure(",
    "nvcAtlasReplaceGeneration": "avkHeapBind(",
    "nvcImageSpriteReplace": "vkGetPhysicalDeviceImageFormatProperties(",
    "nvcImageSpriteClear": "vkDeviceWaitIdle(",
    "nvcTTCacheClear": "For y =",
    "NeonVkChromeWarmTrueTypeText": "AnvilTrueTypeSlotSelected(",
    "NeonVkChromeGridWarm": "AnvilTrueTypeSlotSelected(",
    "NeonVkChromeTTCacheReset": "nvcTTCacheClear(",
    "NeonVkChromeRebind": "nvcFramebuffer = framebuffer",
    "NeonVkChromeWsiAttach": "nvdWsiAttach(",
}


def resource_ownership_source_gate(text: str) -> int:
    # This checks the source entry/refusal ordering only, not execution or GPU
    # completion. The full emitted and hardware legs retain their own status.
    text = code_without_comments(text)
    checks = 0
    for name, first_effect in RESOURCE_MUTATION_ENTRIES.items():
        body = procedure_body(text, name)
        guard = re.search(r"(?m)^\s*If [^\n]*nvcInFrame <> 0[^\n]*", body)
        if not guard or first_effect not in body or guard.start() >= body.index(first_effect):
            raise AssertionError(name + " lacks an early frame-ownership refusal")
        condition = guard.group().split(":", 1)[0]
        for field in ("nvcFramePending", "nvcFrameAbortable"):
            if " Or " + field + " <> 0" not in condition:
                raise AssertionError(name + " lacks frame-ownership guard for " + field)
            checks += 1
        end = body.find("EndIf", guard.start())
        branch = body[guard.end():end] if ":" not in guard.group() else guard.group()
        if end < 0 or not re.search(r"ProcedureReturn (?:nvcFail\(#NEON_VK_CHROME_ERR_STATE\)|#NEON_VK_CHROME_ERR_STATE|0)(?:\s|:|$)", branch):
            raise AssertionError(name + " lacks a terminal frame-ownership refusal")
        checks += 1
    rebind = procedure_body(text, "NeonVkChromeRebind")
    query = "rc = AnvilVkFramebufferTargetCheck(nvcDevice, nvcRenderPass, framebuffer, physicalW, physicalH, pitch)"
    refusal = "If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf"
    publish = "nvcFramebuffer = framebuffer"
    if rebind.count(query) != 1:
        raise AssertionError("Rebind lacks one exact framebuffer-owner target preflight")
    if refusal not in rebind or not rebind.index(query) < rebind.index(refusal) < rebind.index(publish):
        raise AssertionError("Rebind publishes before framebuffer-owner refusal is complete")
    target_fields = "nvcFramebuffer|nvcLogicalW|nvcLogicalH|nvcPhysicalW|nvcPhysicalH|nvcPitch|nvcRotation|nvcWidth|nvcHeight|nvcTargetGeneration|nvcNextTargetGeneration"
    if re.search(r"(?m)^\s*(?:" + target_fields + r")\s*=", rebind[:rebind.index(query)]):
        raise AssertionError("Rebind changes target fields before framebuffer-owner preflight")
    checks += 3
    create = procedure_body(text, "NeonVkChromeCreateWithCapacities")
    pitch_query = "targetPitch = AnvilVkFramebufferTargetPitch(device, renderPass, framebuffer, width, height)"
    pitch_guard = "If targetPitch < 1"
    pitch_return = "ProcedureReturn nvcFail(targetPitch)"
    zero_refusal = "If targetPitch = 0 : targetPitch = #NEON_VK_CHROME_ERR_STATE : EndIf"
    if create.count(pitch_query) != 1:
        raise AssertionError("Create lacks one exact framebuffer-owner pitch query")
    if pitch_guard not in create or pitch_return not in create or zero_refusal not in create or not create.index(pitch_query) < create.index(pitch_guard) < create.index(zero_refusal) < create.index(pitch_return) < create.index("nvcLogicalW = width") < create.index("rc = vkAllocateCommandBuffers("):
        raise AssertionError("Create does not finish target-pitch refusal before mutation/allocation")
    if re.search(r"(?m)^\s*(?:" + target_fields + r")\s*=", create[:create.index(pitch_query)]):
        raise AssertionError("Create changes target fields before framebuffer-owner pitch query")
    if "nvcPitch = targetPitch" not in create or "nvcPitch = width * 4" in create:
        raise AssertionError("Create does not publish the framebuffer-owner row pitch")
    checks += 4
    destroy = procedure_body(text, "NeonVkChromeDestroyChecked")
    quarantine = "nvcReady = 0 : nvcInFrame = 0"
    idle = "idleRc = vkDeviceWaitIdle(nvcDevice)"
    idle_guard = "If idleRc <> #VK_SUCCESS"
    idle_return = "ProcedureReturn nvcFail(idleRc)"
    rollback = "rollbackRc = nvdWsiRollback()"
    rollback_guard = "If rollbackRc <> #VK_SUCCESS : ProcedureReturn nvcFail(rollbackRc) : EndIf"
    if quarantine not in destroy or idle not in destroy or destroy.index(quarantine) > destroy.index(idle):
        raise AssertionError("Destroy does not quarantine recording before completion wait")
    if destroy.count(idle) != 1 or destroy.count("nvdWsiRollback()") != 1 or rollback not in destroy:
        raise AssertionError("Destroy lacks one ordered idle/WSI rollback transaction")
    if idle_guard not in destroy or idle_return not in destroy or not destroy.index(idle) < destroy.index(idle_guard) < destroy.index(idle_return) < destroy.index(rollback):
        raise AssertionError("Destroy does not establish completion before WSI rollback")
    if rollback_guard not in destroy:
        raise AssertionError("Destroy ignores WSI rollback refusal")
    safe_at = destroy.index(rollback_guard) + len(rollback_guard)
    prefix = destroy[:safe_at]
    if any(call in prefix for call in ("nvdPresentClear()", "NeonDrawBackendClear()", "vkUnmapMemory(")) or re.search(r"(?m)^\s*(?:nvcMapped|nvcHooksInstalled|nvcDevice|nvcCommand|nvcFramePending)\s*=", prefix):
        raise AssertionError("Destroy discards retained presentation/callback/mapping state before safe rollback")
    releases = list(re.finditer(r"\b(?:vkDestroy\w+|vkFree\w+|nvc\w+Release)\s*\(", destroy))
    if not releases or any(m.start() < safe_at for m in releases):
        raise AssertionError("Destroy releases resources before safe WSI rollback")
    checks += 6
    return checks


def geometry_source_gate(text: str) -> int:
    """Check current fan/indexed/compact routes, not their obsolete expansion.

    These source relationships do not prove emitted shader behavior or pixels.
    The frozen complete-frame GPU oracle remains separate acceptance evidence.
    """
    geometry_names = (
        "NeonVkChromeFanBegin", "NeonVkChromeFanPoint", "NeonVkChromeFanEnd",
        "NeonVkChromeFanOutline", "NeonVkChromeLinesBegin", "NeonVkChromeLine",
        "NeonVkChromeLinesEnd",
    )
    helper_names = (
        "nvcOutlineDraw", "nvcOutlinePrepare", "nvcOutlineEnsure",
        "nvcOutlineDrawRange", "nvcOutlineEdgeAt", "nvcFanListDraw",
        "nvcLineRecordAt", "nvcLineStreamDraw",
    )
    bodies = {name: procedure_body(text, name) for name in geometry_names + helper_names}
    checks = len(bodies)
    geometry = "\n".join(bodies.values())
    if re.search(r"\b(?:neon_Draw|neon_Vertex|V3d\w*|Display\w*)\s*\(", geometry, re.I) or "PokeL(nvcFramebuffer" in geometry:
        raise AssertionError("geometry bypasses public Vulkan recording through native drawing")
    checks += 1
    if "#NEON_VK_CHROME_MAX_PATH_POINTS" not in bodies["NeonVkChromeFanPoint"] or "#NEON_VK_CHROME_MAX_PATH_POINTS" not in bodies["NeonVkChromeLine"]:
        raise AssertionError("logical primitive staging is not explicitly bounded")
    checks += 2
    fan = bodies["NeonVkChromeFanEnd"]
    for route in ("ElseIf nvcFanIndexedStart >= 0", "rc = nvcOutlineDraw(colour, 1)", "ElseIf nvcFanPipeline = 0", "rc = nvcFanListDraw(colour)", "vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcFanPipeline)"):
        if route not in fan:
            raise AssertionError("fan loses an advertised or indexed fallback route: " + route)
    if "ProcedureReturn nvcOutlineDraw(colour, 0)" not in bodies["NeonVkChromeFanOutline"]:
        raise AssertionError("outline does not use its immutable indexed owner")
    checks += 6
    for name, write in (("NeonVkChromeFanEnd", "nvcVertex("), ("NeonVkChromeLinesEnd", "nvcLineRecordAt(")):
        body = bodies[name]
        prefix = body[:body.index(write)]
        for bound in ("nvcBudgetCan(0, 1, 0)", "nvcDrawCount >= nvcMaxQuads", "nvcVertices + needed > nvcMaxVertexQuads * 6"):
            if bound not in prefix:
                raise AssertionError(name + " writes before whole-primitive capacity preflight: " + bound)
        checks += 3
    lines = bodies["NeonVkChromeLinesEnd"]
    for marker in ("((nvcPathCount / 2) * 32 + #NEON_VK_CHROME_VERTEX_BYTES - 1) / #NEON_VK_CHROME_VERTEX_BYTES", "p = p + 32 : i = i + 2", "rc = nvcLineStreamDraw(first, nvcPathCount / 2, colour)"):
        if marker not in lines:
            raise AssertionError("line storage/draw contract differs: " + marker)
    draw = bodies["nvcLineStreamDraw"]
    for marker in ("rc = nvcDrawSetRawWithInstances(0, 4, colour, 0, nvcLineLayout, count)", "buffers[0] = nvcVertexBuffer : offsets[0] = 0", "vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)"):
        if marker not in draw:
            raise AssertionError("compact line draw or state restoration differs: " + marker)
    checks += 6
    record = bodies["nvcLineRecordAt"]
    for index in range(4):
        if f"PokeL(p{' + '+str(index*4) if index else ''}, c{index})" not in record or f"PokeL(p + {16+index*4}, c{index} >> 32)" not in record:
            raise AssertionError("compact record drops an exact corner component")
    checks += 8
    prepare = bodies["nvcOutlinePrepare"]
    prefix = prepare[:prepare.index("PokeI(")]
    for marker in ("delta < 0", "nvcBudgetCan(0, 1, 0)", "rawRows > nvcMaxQuads - nvcDrawCount", "rawRows > avkRecordedDrawFreeCount", "needed > nvcMaxVertexQuads * 6 - nvcVertices", "delta > points - nvcOutlinePointsUsed", "nvcOutlineClosingsUsed >= #NEON_MAX_DRAWS", "rc = nvcOutlineEnsure()", "If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf"):
        if marker not in prefix:
            raise AssertionError("indexed outline writes before complete reservation: " + marker)
    if "If nvcOutlineBuffer <> 0 : ProcedureReturn #VK_SUCCESS : EndIf" not in bodies["nvcOutlineEnsure"]:
        raise AssertionError("outline resource cache is not retained on reuse")
    checks += 10
    outline = bodies["nvcOutlineDraw"]
    if outline.index("rc = nvcOutlinePrepare(1 - filled, rows)") > outline.index("vkCmdBindVertexBuffers(") or "If rc <> 0 : ProcedureReturn rc : EndIf" not in outline[:outline.index("vkCmdBindVertexBuffers(")]:
        raise AssertionError("outline records before successful complete preparation")
    for marker in ("nvcOutlineDrawRange(nvcFanIndexedEdgeStart * 6, (nvcPathCount - 1) * 6, colour)", "nvcOutlineDrawRange(nvcFanIndexedClose, 6, colour)", "vkCmdBindIndexBuffer(nvcCommand, nvcOutlineBuffer, 0, #VK_INDEX_TYPE_UINT32)"):
        if marker not in outline:
            raise AssertionError("immutable outline draw ranges differ: " + marker)
    fallback = bodies["nvcFanListDraw"]
    prefix = fallback[:fallback.index("nvcVertex(")]
    for marker in ("nvcBudgetCan(0, 1, 0)", "nvcDrawCount >= nvcMaxQuads", "avkRecordedDrawFreeCount < 1", "nvcPathCount > nvcMaxVertexQuads * 6 - nvcVertices", "count > points * 3 - nvcFanListIndicesUsed"):
        if marker not in prefix:
            raise AssertionError("fan fallback writes before complete reservation: " + marker)
    if "vkCmdDrawIndexed(nvcCommand, count, 1, nvcFanListIndicesUsed, 0, 0)" not in fallback:
        raise AssertionError("fan fallback loses its immutable first-index range")
    checks += 10
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
        result, steps = execute(a64, image, GEOMETRY_STEP_LIMIT)
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
    parser.add_argument("--source-only", action="store_true", help="check exact named source owners only; never resolves a compiler, loads an interpreter or executes hardware")
    parser.add_argument("--source-report", type=Path, help="write the source-only result, source hashes and explicitly unrun emitted/hardware legs")
    args = parser.parse_args()
    if args.source_report and not args.source_only:
        parser.error("--source-report requires --source-only")
    if args.source_only and args.oracle_only:
        parser.error("--source-only and --oracle-only describe different validation legs")
    if args.source_only:
        report = {"scope": "source relationships only", "emitted": "NOT RUN", "gpu": "NOT RUN", "full_acceptance": "NOT RUN"}
        try:
            hooks, adapter, hashes = source_inputs()
            report["source_hashes"] = hashes
            report["hook_checks"] = neon_hook_source_gate(hooks)
            report["adapter_checks"] = source_gate(adapter)
            report["scene_checks"] = real_scene_gate(REAL_SCENE.read_text(encoding="utf-8-sig"))
            report["source_status"] = "PASS"
        except (AssertionError, KeyError, OSError, ValueError) as exc:
            report.update(source_status="FAIL", error=str(exc))
        if args.source_report:
            args.source_report.write_text(json.dumps(report, indent=2), encoding="utf8")
        print(json.dumps(report))
        return 0 if report["source_status"] == "PASS" else 1
    args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    try:
        compiler = locate(args.compiler, DEFAULT_COMPILER, "PureMetalForge.exe")
        interp = locate(args.interp, DEFAULT_INTERP, "A64 interpreter")
        a64 = load_interpreter(interp)
        if args.oracle_only or not ADAPTER.is_file():
            hooks, _ = hook_source_inputs()
            adapter_text = ""
        else:
            hooks, adapter_text, _ = source_inputs()
        hook_checks = neon_hook_source_gate(hooks)
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
