#!/usr/bin/env python3
"""Grade Anvil's Vulkan resource, layout, fence and submission engine.

This is an emitted-code gate. It builds RaspberryPi4/Tests/
vulkan_resource_emitted_gate.pi4 with the real compiler, runs the real
image in the A64 interpreter with an MMIO hard stop armed, and then
checks PROPERTIES of what the image left in DRAM. It re-implements none
of the driver: it does not know how a row pitch is chosen or how a fence
is signalled, only what has to be true of the result.

The gate links the explicit test backend, which owns no GPU and writes no
pixels, so the strongest thing this checker does is read the image memory
itself and require that every poisoned word survived - if any CPU clear
were hiding in the driver, that check would go red.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> \\
      py -3 tools/vulkan_resource_check.py

Add --mutate to apply a list of plausible mistakes to the driver sources,
one at a time, and require the gate to go RED for each.
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
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_resource_emitted_gate.pi4"
VULKAN = ROOT / "Anvil" / "Graphics" / "Vulkan"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 200_000_000
MMIO = 0xFC000000

OUT = 0x06000000
ROWS = 0x06000100
TEXTS = 0x06002000
CONV = 0x06003000

MAGIC = 0x564B5247  # "VKRG"
POISON = 0xA5C3F00D

# The binary32 patterns the gate converts, and the exact 8-bit UNORM the
# specification's clamp-and-round produces for each. Worked out here from
# the definition, not from what the code happened to answer.
CONVERSIONS = (
    ("0.0", 0),
    ("1.0", 255),
    ("0.5", 128),        # 0.5 * 255 = 127.5, round to nearest, ties up
    ("0.2f", 51),        # 0.200000003 * 255 = 51.0000007
    ("0.7f", 178),       # 0.699999988 * 255 = 178.4999969
    ("1/255", 1),
    ("-1.0", 0),         # clamped
    ("2.0", 255),        # clamped
    ("+infinity", 255),
    ("NaN", 0),
    ("smallest subnormal", 0),
)

# Every sentence the gate captured must be a real sentence: it names its
# numeric code, it says what to do, and it is not a bare code.
SENTENCE_MIN_WORDS = 14

MUTANTS = (
    (
        "a row pitch that ignores the backend's alignment",
        "vk_memory.pbi",
        "  pitch = avkBackendRowPitchFor(width)\n",
        "  pitch = width * #ANVIL_VK_BGRA8_TEXEL_BYTES\n",
    ),
    (
        "image size measured from the width instead of the pitch",
        "vk_memory.pbi",
        "  avkImgSize[s] = pitch * height\n",
        "  avkImgSize[s] = width * 4 * height\n",
    ),
    (
        "vkCreateImage accepts a color attachment on a transfer-only backend",
        "vk_memory.pbi",
        "  If (usage & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) <> 0 And AnvilVkBackendCanDraw() = 0\n    avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED,",
        "  If (usage & #VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) <> 0 And AnvilVkBackendCanDraw() < 0\n    avkFault(#VK_ERROR_FORMAT_NOT_SUPPORTED,",
    ),
    (
        "vkMapMemory accepts a memory type that is not HOST_VISIBLE",
        "vk_memory.pbi",
        "  If (avkBackendMemoryTypeFlags(avkMemType[s]) & #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) = 0\n",
        "  If (avkBackendMemoryTypeFlags(avkMemType[s]) & #VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) = -1\n",
    ),
    (
        "vkMapMemory accepts a second active mapping",
        "vk_memory.pbi",
        "  If avkMemMapped[s] <> 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkMapMemory was called on an allocation that is already host mapped",
        "  If avkMemMapped[s] < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkMapMemory was called on an allocation that is already host mapped",
    ),
    (
        "vkMapMemory ignores the allocation's owning device",
        "vk_memory.pbi",
        "  If avkMemDev[s] <> d\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, \"vkMapMemory was called through a device",
        "  If avkMemDev[s] < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_OWNER, \"vkMapMemory was called through a device",
    ),
    (
        "vkMapMemory accepts non-zero core map flags",
        "vk_memory.pbi",
        "  If flags <> 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkMapMemory was given non-zero",
        "  If flags < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_ARGS, \"vkMapMemory was given non-zero",
    ),
    (
        "vkMapMemory accepts an offset equal to allocation size",
        "vk_memory.pbi",
        "  If offset < 0 Or offset >= avkMemSize[s]\n",
        "  If offset < 0 Or offset > avkMemSize[s]\n",
    ),
    (
        "vkMapMemory accepts a range past the allocation end",
        "vk_memory.pbi",
        "    If size <= 0 Or size > (avkMemSize[s] - offset)\n",
        "    If size <= 0\n",
    ),
    (
        "vkMapMemory returns the allocation base instead of the requested offset",
        "vk_memory.pbi",
        "  PokeI(*out, avkHeapBase + avkMemOffset[s] + offset)\n",
        "  PokeI(*out, avkHeapBase + avkMemOffset[s])\n",
    ),
    (
        "vkUnmapMemory leaves the allocation mapped",
        "vk_memory.pbi",
        "  avkMemMapped[s] = 0\n  avkMemMapOffset[s] = 0\n  avkMemMapSize[s] = 0\nEndProcedure\n\n; vkFreeMemory",
        "  avkMemMapped[s] = 1\n  avkMemMapOffset[s] = 0\n  avkMemMapSize[s] = 0\nEndProcedure\n\n; vkFreeMemory",
    ),
    (
        "vkFreeMemory releases an allocation while it is mapped",
        "vk_memory.pbi",
        "  If avkMemMapped[s] <> 0\n    avkFault(#ANVIL_VK_ERR_STATE, \"vkFreeMemory was called while the allocation is host mapped",
        "  If avkMemMapped[s] < 0\n    avkFault(#ANVIL_VK_ERR_STATE, \"vkFreeMemory was called while the allocation is host mapped",
    ),
    (
        "the public vkMapMemory adapter discards the caller's offset",
        "vk_api.pbi",
        "  ProcedureReturn AnvilVkMemoryMap(device, memory, offset, size, flags, *ppData)\n",
        "  ProcedureReturn AnvilVkMemoryMap(device, memory, 0, size, flags, *ppData)\n",
    ),
    (
        "bind accepts an offset that is not a multiple of the alignment",
        "vk_memory.pbi",
        "  If (avkImgAlign[s] < 1) Or ((memoryOffset % avkImgAlign[s]) <> 0)\n",
        "  If avkImgAlign[s] < 1\n",
    ),
    (
        "bind stops checking that the image fits in the allocation",
        "vk_memory.pbi",
        "  If (avkMemSize[m] - memoryOffset) < avkImgSize[s]\n",
        "  If memoryOffset > avkMemSize[m]\n",
    ),
    (
        "an image may be bound twice",
        "vk_memory.pbi",
        "  If avkImgBound[s] <> 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkBindImageMemory was called on an image that is already bound",
        "  If avkImgBound[s] < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkBindImageMemory was called on an image that is already bound",
    ),
    (
        "memory an image is still bound to can be freed",
        "vk_memory.pbi",
        "  If avkMemBinds[s] <> 0\n",
        "  If avkMemBinds[s] < 0\n",
    ),
    (
        "the heap allocator bumps past a freed hole instead of reusing it",
        "vk_memory.pbi",
        "        If off < (avkMemOffset[i] + avkMemSize[i]) And (off + bytes) > avkMemOffset[i]\n",
        "        If off <= (avkMemOffset[i] + avkMemSize[i])\n",
    ),
    (
        "a transition into TRANSFER_DST no longer needs a transfer write",
        "vk_command.pbi",
        "    If (dstAccessMask & (#VK_ACCESS_TRANSFER_WRITE_BIT | #VK_ACCESS_MEMORY_WRITE_BIT)) = 0\n",
        "    If dstAccessMask < 0\n",
    ),
    (
        "a transition into TRANSFER_DST no longer needs the transfer stage",
        "vk_command.pbi",
        "    If (dstStageMask & (#VK_PIPELINE_STAGE_TRANSFER_BIT | #VK_PIPELINE_STAGE_ALL_COMMANDS_BIT)) = 0\n",
        "    If dstStageMask < 0\n",
    ),
    (
        "a queue-family ownership transfer is accepted on a one-family device",
        "vk_command.pbi",
        "  If Not ((srcQueueFamily = #VK_QUEUE_FAMILY_IGNORED And dstQueueFamily = #VK_QUEUE_FAMILY_IGNORED) Or (srcQueueFamily = #ANVIL_VK_QUEUE_FAMILY And dstQueueFamily = #ANVIL_VK_QUEUE_FAMILY))\n",
        "  If srcQueueFamily < 0\n",
    ),
    (
        "the recorded layout claim is not checked against the recording",
        "vk_command.pbi",
        "  If avkRefCur[idx] <> claim : ProcedureReturn 0 : EndIf\n",
        "  If avkRefCur[idx] < -99 : ProcedureReturn 0 : EndIf\n",
    ),
    (
        "the entry layout is not checked against the image at submit",
        "vk_command.pbi",
        "      If avkImgLayout[s] <> avkRefEntry[avkRefIndex(c, k)]\n",
        "      If avkImgLayout[s] < -99\n",
    ),
    (
        "a clear is accepted in a layout the specification forbids",
        "vk_command.pbi",
        "  If imageLayout <> #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL And imageLayout <> #VK_IMAGE_LAYOUT_GENERAL\n",
        "  If imageLayout < 0\n",
    ),
    (
        "a clear is accepted on an image without TRANSFER_DST usage",
        "vk_command.pbi",
        "  If (avkImgUsage[s] & #VK_IMAGE_USAGE_TRANSFER_DST_BIT) = 0\n",
        "  If avkImgUsage[s] < 0\n",
    ),
    (
        "the backend is not asked whether it can run the clear",
        "vk_command.pbi",
        "  If avkBackendClearSupported(AnvilVkImageAddress(image), avkImgSize[s], avkImgW[s], avkImgH[s], avkImgPitch[s]) <> #VK_SUCCESS\n",
        "  If avkBackendClearSupported(AnvilVkImageAddress(image), avkImgSize[s], avkImgW[s], avkImgH[s], avkImgPitch[s]) = 12345\n",
    ),
    (
        "the clear colour is packed in R, G, B, A byte order instead of B, G, R, A",
        "vk_command.pbi",
        "  avkOpColor[o] = (alpha << 24) | (red << 16) | (green << 8) | blue\n",
        "  avkOpColor[o] = (alpha << 24) | (blue << 16) | (green << 8) | red\n",
    ),
    (
        "the UNORM conversion truncates instead of rounding to nearest",
        "vk_command.pbi",
        "  r = (n + (1 << (shift - 1))) >> shift\n",
        "  r = n >> shift\n",
    ),
    (
        "a submitted image is not retained",
        "vk_command.pbi",
        "    avkImgInFlight[s] = avkImgInFlight[s] + 1\n",
        "    avkImgInFlight[s] = avkImgInFlight[s]\n",
    ),
    (
        "a failed submission advances the image's layout anyway",
        "vk_command.pbi",
        "Procedure avkFlightComplete(ok.i)\n  Define c.i\n  Define k.i\n  Define s.i\n  If avkFlightActive = 0\n    ProcedureReturn\n  EndIf\n  c = avkFlightCb\n  If ok <> 0\n",
        "Procedure avkFlightComplete(ok.i)\n  Define c.i\n  Define k.i\n  Define s.i\n  If avkFlightActive = 0\n    ProcedureReturn\n  EndIf\n  c = avkFlightCb\n  If ok >= 0\n",
    ),
    (
        "a second submission is accepted while one is outstanding",
        "vk_command.pbi",
        "  If avkFlightActive <> 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkQueueSubmit was called while an earlier submission",
        "  If avkFlightActive < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkQueueSubmit was called while an earlier submission",
    ),
    (
        "a command buffer may be reset while it is pending",
        "vk_command.pbi",
        "  If avkCmdState[c] = #ANVIL_VK_CB_PENDING\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkResetCommandBuffer was called on a command buffer that is still executing",
        "  If avkCmdState[c] = 999\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkResetCommandBuffer was called on a command buffer that is still executing",
    ),
    (
        "an already signalled fence may be handed to a submission",
        "vk_sync.pbi",
        "  If avkFenceSignaled[s] <> 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkQueueSubmit was given a fence that is already signalled",
        "  If avkFenceSignaled[s] < 0\n    ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkQueueSubmit was given a fence that is already signalled",
    ),
    (
        "a fence in use may be reset",
        "vk_sync.pbi",
        "    If avkFenceInUse[s] <> 0\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkResetFences was given a fence",
        "    If avkFenceInUse[s] < 0\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_STATE, \"vkResetFences was given a fence",
    ),
    (
        "a fence in use may be destroyed",
        "vk_sync.pbi",
        "  If avkFenceInUse[s] <> 0\n    avkFault(#ANVIL_VK_ERR_STATE, \"vkDestroyFence was called while a submitted command buffer",
        "  If avkFenceInUse[s] < 0\n    avkFault(#ANVIL_VK_ERR_STATE, \"vkDestroyFence was called while a submitted command buffer",
    ),
    (
        "a fence signals on creation regardless of the flag",
        "vk_sync.pbi",
        "  If (flags & #VK_FENCE_CREATE_SIGNALED_BIT) <> 0\n    avkFenceSignaled[s] = 1\n",
        "  If (flags & #VK_FENCE_CREATE_SIGNALED_BIT) >= 0\n    avkFenceSignaled[s] = 1\n",
    ),
    (
        "an unsignalled UINT64_MAX wait falls through to a bounded timeout",
        "vk_command.pbi",
        "    If timeoutNs = -1\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, \"vkWaitForFences was given UINT64_MAX",
        "    If timeoutNs = -2\n      ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, \"vkWaitForFences was given UINT64_MAX",
    ),
    (
        "an already-signalled UINT64_MAX wait is refused",
        "vk_command.pbi",
        "      If signalled >= count : ProcedureReturn #VK_SUCCESS : EndIf\n",
        "      If signalled >= count And timeoutNs <> -1 : ProcedureReturn #VK_SUCCESS : EndIf\n",
    ),
    (
        "the bounded optimal transfer image is refused",
        "vk_memory.pbi",
        "  ElseIf tiling = #VK_IMAGE_TILING_OPTIMAL\n",
        "  ElseIf tiling = -99\n",
    ),
    (
        "host allocation callbacks are accepted and then ignored",
        "vk_api.pbi",
        "Procedure.i avkNoAllocator(*pAllocator, site.i)\n  If *pAllocator = 0 : ProcedureReturn #VK_SUCCESS : EndIf\n",
        "Procedure.i avkNoAllocator(*pAllocator, site.i)\n  If *pAllocator >= 0 : ProcedureReturn #VK_SUCCESS : EndIf\n",
    ),
    (
        "a pNext chain is ignored instead of refused",
        "vk_api.pbi",
        "Procedure.i avkNoPNext(*pNext)\n  If *pNext = 0 : ProcedureReturn #VK_SUCCESS : EndIf\n",
        "Procedure.i avkNoPNext(*pNext)\n  If *pNext >= 0 : ProcedureReturn #VK_SUCCESS : EndIf\n",
    ),
    (
        "a multi-range clear silently clears only the first range",
        "vk_api.pbi",
        "  If rangeCount <> 1 Or *pRanges = 0\n",
        "  If *pRanges = 0\n",
    ),
    (
        "vkCmdPipelineBarrier discards its ninth stack argument",
        "vk_api.pbi",
        "  imageMemoryBarrierCount = imageMemoryBarrierCount & $FFFFFFFF\n",
        "  imageMemoryBarrierCount = 0\n",
    ),
    (
        "vkCmdPipelineBarrier discards its tenth stack argument",
        "vk_api.pbi",
        "  AnvilVkCmdImageBarrier(commandBuffer, srcStageMask, dstStageMask, *pImageMemoryBarriers)\n",
        "  AnvilVkCmdImageBarrier(commandBuffer, srcStageMask, dstStageMask, 0)\n",
    ),
)

FENCE_UNLIMITED_MUTANTS = frozenset({
    "an unsignalled UINT64_MAX wait falls through to a bounded timeout",
    "an already-signalled UINT64_MAX wait is refused",
})

MAP_MEMORY_MUTANTS = frozenset({
    "vkMapMemory accepts a memory type that is not HOST_VISIBLE",
    "vkMapMemory accepts a second active mapping",
    "vkMapMemory ignores the allocation's owning device",
    "vkMapMemory accepts non-zero core map flags",
    "vkMapMemory accepts an offset equal to allocation size",
    "vkMapMemory accepts a range past the allocation end",
    "vkMapMemory returns the allocation base instead of the requested offset",
    "vkUnmapMemory leaves the allocation mapped",
    "vkFreeMemory releases an allocation while it is mapped",
    "the public vkMapMemory adapter discards the caller's offset",
})

FORMAT_TRUTH_MUTANTS = frozenset({
    "vkCreateImage accepts a color attachment on a transfer-only backend",
    "the bounded optimal transfer image is refused",
})

PIPELINE_BARRIER_ABI_MUTANTS = frozenset({
    "vkCmdPipelineBarrier discards its ninth stack argument",
    "vkCmdPipelineBarrier discards its tenth stack argument",
})


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
    raise SystemExit(f"vulkan resource gate: {env_name} was not found; set it or pass its option")


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_vkres_a64_interp", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"vulkan resource gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def stage(work: pathlib.Path, sources: dict[str, str]) -> pathlib.Path:
    """A small root holding only what this gate executes, so a mutation
    never touches the repository."""
    (work / "Anvil" / "Graphics" / "Vulkan").mkdir(parents=True, exist_ok=True)
    (work / "RaspberryPi4" / "Tests").mkdir(parents=True, exist_ok=True)
    for path in VULKAN.glob("*.pbi"):
        text = sources.get(path.name)
        if text is None:
            text = path.read_text(encoding="utf-8")
        (work / "Anvil" / "Graphics" / "Vulkan" / path.name).write_text(text, encoding="utf-8")
    shutil.copy2(GATE, work / "RaspberryPi4" / "Tests" / GATE.name)
    for name in ("Intrinsics",):
        src = ROOT / "RaspberryPi4" / name
        if src.is_dir():
            shutil.copytree(src, work / "RaspberryPi4" / name, dirs_exist_ok=True)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards", dirs_exist_ok=True)
    return work / "RaspberryPi4" / "Tests" / GATE.name


def build(compiler: pathlib.Path, work: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    image = work / "vulkan_resource_gate.img"
    command = [
        str(compiler), "--compile", source.relative_to(work).as_posix(),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(work)
    run = subprocess.run(command, cwd=work, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("vulkan resource gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(
                f"vulkan resource gate: unexpected MMIO {kind} at ${addr:08X} - this gate "
                "links the test backend and is supposed to touch no hardware at all")

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
    raise SystemExit(f"vulkan resource gate: the probe did not return in {STEP_LIMIT} instructions")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def u32(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(4))


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

    def need(self, name: str, got, want) -> None:
        self.checks += 1
        if got != want:
            self.failures.append(f"{name}: got {got!r}, wanted {want!r}")

    def want_true(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(f"{name}{(': ' + detail) if detail else ''}")


def grade(cpu, rc) -> Grader:
    g = Grader()
    g.need("gate magic", hex(u64(cpu, OUT)), hex(MAGIC))
    rows = u64(cpu, OUT + 8)
    fails = u64(cpu, OUT + 16)
    g.need("gate return code", rc, 0)
    g.need("in-image failures", fails, 0)
    g.want_true("the gate ran a substantial number of checks", rows >= 150, str(rows))
    if fails:
        bad = [str(i + 1) for i in range(rows) if u64(cpu, ROWS + i * 8) == 0]
        g.failures.append("failed in-image rows: " + ",".join(bad))
    for i in range(rows):
        g.checks += 1

    # THE IMAGE WAS NEVER WRITTEN. The driver asked a backend that owns
    # no GPU to clear it, twice, and the poison must all still be there.
    g.need("the driver reports the image was untouched", u64(cpu, OUT + 72), 1)
    base = u64(cpu, OUT + 80)
    size = u64(cpu, OUT + 88)
    g.want_true("the image had an address", base != 0)
    g.want_true("the image had a size", size == 16384, str(size))
    if base and size:
        wrong = 0
        first = None
        for off in range(0, size, 4):
            if u32(cpu, base + off) != POISON:
                wrong += 1
                if first is None:
                    first = off
        g.want_true(
            "every poisoned word of the image survived the whole path",
            wrong == 0,
            f"{wrong} words changed, first at +{first}" if wrong else "")

    # The backend was called exactly as often as work was submitted, and
    # the last call carried the colour this format actually stores.
    g.need("backend clear calls", u64(cpu, OUT + 24), 3)
    g.need("last clear word is opaque red in B8G8R8A8_UNORM byte order",
           hex(u64(cpu, OUT + 32) & 0xFFFFFFFF), hex(0xFFFF0000))
    g.want_true("the backend names itself", u64(cpu, OUT + 64) != 0)
    name = cstr(cpu, u64(cpu, OUT + 64))
    g.want_true("the backend says it owns no GPU",
                "owns no GPU" in name and "never writes a pixel" in name, repr(name[:80]))

    # binary32 -> UNORM8, at the edges, against values worked out from
    # the specification rather than from the implementation.
    for i, (label, want) in enumerate(CONVERSIONS):
        g.need(f"clear value {label} converts to UNORM8", u64(cpu, CONV + i * 8), want)

    # EVERY REFUSAL IS A WHOLE SENTENCE. The checker reads the actual
    # bytes out of the built image rather than trusting one was set.
    texts = u64(cpu, OUT + 48)
    g.want_true("the gate captured a refusal sentence for every refusal path",
                texts >= 25, str(texts))
    for i in range(texts):
        ptr = u64(cpu, TEXTS + i * 8)
        g.want_true(f"refusal {i + 1} has a sentence", ptr != 0)
        if not ptr:
            continue
        text = cstr(cpu, ptr)
        g.want_true(f"refusal {i + 1} ends as a sentence", text.endswith("."), repr(text[:70]))
        g.want_true(f"refusal {i + 1} is not a bare code",
                    len(text.split()) >= SENTENCE_MIN_WORDS, repr(text[:70]))
        g.want_true(f"refusal {i + 1} names its numeric code",
                    ("Anvil code -200" in text) or ("VkResult -" in text) or ("VkResult 2," in text),
                    repr(text[:110]))
        g.want_true(f"refusal {i + 1} says what to check or do next",
                    any(w in text for w in ("Call ", "call ", "Wait ", "Pass ", "Check ",
                                            "check ", "Destroy ", "Free ", "Reset ", "reset ",
                                            "Ask ", "ask ", "Create ", "create ", "set sType",
                                            "Set ", "use ", "Use ", "record ", "Record ",
                                            "submit ", "Submit ", "round ", "choose ", "split ",
                                            "allocate ", "bring ", "must ", "should ", "so ")),
                    repr(text[:130]))
    return g


def run_once(a64, compiler, sources: dict[str, str]):
    with tempfile.TemporaryDirectory(prefix="anvil-vkres-") as td:
        work = pathlib.Path(td)
        source = stage(work, sources)
        image = build(compiler, work, source)
        return execute(a64, image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--mutate-only", choices=("fence-unlimited", "map-memory", "format-truth", "pipeline-barrier-abi"))
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if args.mutate_only:
        args.mutate = True

    compiler = locate("PMF_COMPILER", args.compiler, [ROOT / "PureMetalForge.exe", ROOT / "compiler"])
    a64 = load_interpreter(locate("PMF_A64_INTERP", args.interp,
                                  [ROOT / "tools" / "a64" / "a64_interp.py"]))

    originals = {p.name: p.read_text(encoding="utf-8") for p in VULKAN.glob("*.pbi")}

    cpu, rc, steps = run_once(a64, compiler, {})
    g = grade(cpu, rc)
    if g.failures:
        print(f"vulkan_resource_check: FAIL ({g.checks} checks, {steps:,} instructions)")
        for failure in g.failures:
            print("  " + failure)
        return 1

    print(f"vulkan_resource_check: PASS - {g.checks} independent property checks over "
          f"{steps:,} executed A64 instructions")
    print("  the real vkCreateImage, vkGetImageMemoryRequirements, vkAllocateMemory,")
    print("  vkBindImageMemory, vkMapMemory, vkUnmapMemory, vkCmdPipelineBarrier,")
    print("  vkCmdClearColorImage, vkCmdCopyBuffer, vkCmdFillBuffer, vkQueueSubmit, vkCreateFence, vkGetFenceStatus,")
    print("  vkWaitForFences, vkResetFences and")
    print("  vkDeviceWaitIdle ran; no MMIO, framebuffer, GPU or DMA was touched")
    print("  every byte of the bound image still held its poison: no CPU image clear exists")

    if not args.mutate:
        print("  (run with --mutate to also require every plausible mistake to be caught)")
        return 0

    print()
    missed = 0
    for name, where, fixed, broken in MUTANTS:
        if args.mutate_only == "fence-unlimited" and name not in FENCE_UNLIMITED_MUTANTS:
            continue
        if args.mutate_only == "map-memory" and name not in MAP_MEMORY_MUTANTS:
            continue
        if args.mutate_only == "format-truth" and name not in FORMAT_TRUTH_MUTANTS:
            continue
        if args.mutate_only == "pipeline-barrier-abi" and name not in PIPELINE_BARRIER_ABI_MUTANTS:
            continue
        text = originals.get(where)
        if text is None or text.count(fixed) != 1:
            found = 0 if text is None else text.count(fixed)
            print(f"  STALE  {name} - its anchor appears {found} times in {where}; not tested")
            missed += 1
            continue
        sources = dict()
        sources[where] = text.replace(fixed, broken, 1)
        try:
            mcpu, mrc, msteps = run_once(a64, compiler, sources)
        except SystemExit as exc:
            # A MUTATION THAT WILL NOT BUILD PROVES NOTHING ABOUT THE GATE.
            print(f"  STALE  {name} - the mutation did not build or run, so the gate's")
            print(f"         checks were never exercised: {str(exc).splitlines()[0][:100]}")
            missed += 1
            continue
        mg = grade(mcpu, mrc)
        if mg.failures:
            print(f"  RED    {name} - {len(mg.failures)} checks failed, "
                  f"first: {mg.failures[0][:100]}")
        else:
            print(f"  GREEN  {name}  <-- THE GATE DID NOT NOTICE ({msteps:,} instructions)")
            missed += 1

    if args.mutate_only == "fence-unlimited":
        total = len(FENCE_UNLIMITED_MUTANTS)
    elif args.mutate_only == "map-memory":
        total = len(MAP_MEMORY_MUTANTS)
    elif args.mutate_only == "format-truth":
        total = len(FORMAT_TRUTH_MUTANTS)
    elif args.mutate_only == "pipeline-barrier-abi":
        total = len(PIPELINE_BARRIER_ABI_MUTANTS)
    else:
        total = len(MUTANTS)
    if missed:
        print(f"\nvulkan_resource_check: {missed} of {total} mutations were not caught")
        return 1
    print(f"\nvulkan_resource_check: all {total} mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
