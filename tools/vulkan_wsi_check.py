#!/usr/bin/env python3
"""Registry, source, emitted-code and mutation gate for vk_wsi.pbi.

The module under test is an unintegrated, target-neutral state engine for
VK_KHR_surface and VK_KHR_swapchain.  This gate never treats declaration or
state-machine coverage as extension advertisement or display presentation.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_wsi.pbi"
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_wsi_gate.pi4"
RESOURCE_CHECK = ROOT / "tools" / "vulkan_resource_check.py"
MAGIC = 0x564B5753
OUT = 0x06200000
ROWS = 0x06200100

MUTATIONS = (
    (
        "provider without mandatory FIFO accepted",
        "If hasFifo = 0 : ProcedureReturn 0 : EndIf",
        "If hasFifo < 0 : ProcedureReturn 0 : EndIf",
    ),
    (
        "combined transform bits accepted",
        "If *info\\preTransform = 0 Or (*info\\preTransform & (*info\\preTransform - 1)) <> 0",
        "If *info\\preTransform = 0 Or (*info\\preTransform & (*info\\preTransform - 1)) < 0",
    ),
    (
        "invalid provider publishes an output handle",
        "If avkWsiProviderInfoValid(*info) = 0\n    ProcedureReturn avkFault",
        "If avkWsiProviderInfoValid(*info) < 0\n    ProcedureReturn avkFault",
    ),
    (
        "cross-device swapchain creation accepted",
        "If avkWsiSurfInst[surf] <> avkPhysInst[avkDevPhys[d]] Or avkWsiSurfInstGen[surf] <> avkInstGen[avkWsiSurfInst[surf]]",
        "If avkWsiSurfInst[surf] < 0 Or avkWsiSurfInstGen[surf] <> avkInstGen[avkWsiSurfInst[surf]]",
    ),
    (
        "bad replacement retires the live chain",
        "If *info\\imageWidth <> avkWsiProvCaps[p]\\currentWidth Or *info\\imageHeight <> avkWsiProvCaps[p]\\currentHeight",
        "If *info\\imageWidth < 0 Or *info\\imageHeight <> avkWsiProvCaps[p]\\currentHeight",
    ),
    (
        "nonzero acquire timeout fakes a completed timeout",
        "ProcedureReturn avkFault(#ANVIL_VK_ERR_UNSUPPORTED, \"swapchain acquisition would have to wait for a provider completion (Anvil code -20005, blocking acquire not integrated); no image was acquired and no timeout was faked.\")",
        "ProcedureReturn #VK_TIMEOUT",
    ),
    (
        "reserved present image can be released",
        "If avkWsiPresentReservedByAny(s, imageIndex) <> 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf",
        "If avkWsiPresentReservedByAny(s, imageIndex) < 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf",
    ),
    (
        "failed present reserve mutates image ownership",
        "avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_RESERVED\n  PokeI(*out",
        "avkWsiSwapImageState[avkWsiImageIndex(avkWsiPresentSwapSlot[avkWsiPresentIndex(t, 0)], avkWsiPresentImage[avkWsiPresentIndex(t, 0)])] = #ANVIL_VK_WSI_IMAGE_PRESENT_PENDING\n  avkWsiPresentStage[t] = #ANVIL_VK_WSI_PRESENT_RESERVED\n  PokeI(*out",
    ),
    (
        "provider failure claims successful presentation",
        "If providerSucceeded <> 0\n      avkWsiSwapImageState[avkWsiImageIndex(s, index)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE",
        "If providerSucceeded = 0\n      avkWsiSwapImageState[avkWsiImageIndex(s, index)] = #ANVIL_VK_WSI_IMAGE_AVAILABLE",
    ),
    (
        "provider resize is ignored",
        "If width = avkWsiProvCaps[p]\\currentWidth And height = avkWsiProvCaps[p]\\currentHeight : ProcedureReturn #VK_SUCCESS : EndIf",
        "If width <> avkWsiProvCaps[p]\\currentWidth And height <> avkWsiProvCaps[p]\\currentHeight : ProcedureReturn #VK_SUCCESS : EndIf",
    ),
    (
        "surface loss ignored by present reservation",
        "If avkWsiSurfLost[surf] <> 0 : avkWsiPresentClear(t) : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf",
        "If avkWsiSurfLost[surf] < 0 : avkWsiPresentClear(t) : ProcedureReturn #VK_ERROR_SURFACE_LOST_KHR : EndIf",
    ),
    (
        "present commit trusts a recycled swapchain slot",
        "s = avkWsiSwapchainSlot(avkWsiPresentSwap[avkWsiPresentIndex(t, i)])\n    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]\n    If s = 0 Or s <> avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)] : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf\n    If avkWsiSwapDev[s]",
        "s = avkWsiPresentSwapSlot[avkWsiPresentIndex(t, i)]\n    index = avkWsiPresentImage[avkWsiPresentIndex(t, i)]\n    If s < 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf\n    If avkWsiSwapDev[s]",
    ),
    (
        "device reset discards acquired images",
        "        If avkWsiSwapImageState[avkWsiImageIndex(s, i)] <> #ANVIL_VK_WSI_IMAGE_AVAILABLE : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf",
        "        If avkWsiSwapImageState[avkWsiImageIndex(s, i)] < 0 : ProcedureReturn #ANVIL_VK_ERR_STATE : EndIf",
    ),
)


def load_harness():
    spec = importlib.util.spec_from_file_location("anvil_vkwsi_resource_gate", RESOURCE_CHECK)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load emitted-gate harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.GATE = GATE
    return module


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def emitted(harness, compiler: pathlib.Path, interpreter: pathlib.Path,
            mutation: tuple[str, str] | None = None):
    a64 = harness.load_interpreter(interpreter)
    sources: dict[str, str] = {}
    if mutation:
        before, after = mutation
        original = SOURCE.read_text(encoding="utf-8")
        if original.count(before) != 1:
            raise AssertionError("mutant anchor count is not one: " + before)
        sources[SOURCE.name] = original.replace(before, after, 1)
    cpu, rc, steps = harness.run_once(a64, compiler, sources)
    magic = u64(cpu, OUT)
    count = u64(cpu, OUT + 8)
    failures = u64(cpu, OUT + 16)
    failed_rows = [i + 1 for i in range(count) if u64(cpu, ROWS + i * 8) == 0]
    return rc, steps, magic, count, failures, failed_rows


def locate(value: str | None, choices: list[pathlib.Path], label: str) -> pathlib.Path:
    if value:
        choices.insert(0, pathlib.Path(value))
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise RuntimeError(label + " not found")


def registry_contract(registry: pathlib.Path) -> int:
    root = ET.fromstring(registry.read_bytes().replace(b"\r\n", b"\n"))
    required = {
        "vkDestroySurfaceKHR": ("void", "VkInstance"),
        "vkGetPhysicalDeviceSurfaceSupportKHR": ("VkResult", "VkPhysicalDevice"),
        "vkGetPhysicalDeviceSurfaceCapabilitiesKHR": ("VkResult", "VkPhysicalDevice"),
        "vkGetPhysicalDeviceSurfaceFormatsKHR": ("VkResult", "VkPhysicalDevice"),
        "vkGetPhysicalDeviceSurfacePresentModesKHR": ("VkResult", "VkPhysicalDevice"),
        "vkCreateSwapchainKHR": ("VkResult", "VkDevice"),
        "vkDestroySwapchainKHR": ("void", "VkDevice"),
        "vkGetSwapchainImagesKHR": ("VkResult", "VkDevice"),
        "vkAcquireNextImageKHR": ("VkResult", "VkDevice"),
        "vkQueuePresentKHR": ("VkResult", "VkQueue"),
    }
    commands = {}
    for command in root.findall("./commands/command"):
        proto = command.find("proto")
        if proto is None or proto.find("name") is None or proto.find("type") is None:
            continue
        name = proto.find("name").text or ""
        if name in required:
            first = command.find("param/type")
            commands[name] = (proto.find("type").text or "", "" if first is None else first.text or "")
    if commands != required:
        raise AssertionError(f"pinned WSI command prototypes drifted: {commands!r}")
    extension_commands = {}
    for name in ("VK_KHR_surface", "VK_KHR_swapchain"):
        ext = root.find(f"./extensions/extension[@name='{name}']")
        if ext is None:
            raise AssertionError("pinned registry lacks " + name)
        extension_commands[name] = {node.get("name") for node in ext.findall("./require/command")}
    if set(required) - (extension_commands["VK_KHR_surface"] | extension_commands["VK_KHR_swapchain"]):
        raise AssertionError("required WSI commands no longer belong to the pinned extensions")
    core = {node.get("name") for feature in root.findall("./feature[@number='1.0']")
            for node in feature.findall("./require/command")}
    if set(required) & core:
        raise AssertionError("extension WSI commands were incorrectly classified as core 1.0")
    return len(required) * 2 + 3


def source_contract(text: str) -> int:
    required = (
        "Procedure.i avkWsiProviderRegister(", "Procedure.i avkWsiSurfaceCreate(",
        "Procedure.i avkWsiSwapchainCreate(", "Procedure.i avkWsiAcquire(",
        "Procedure.i avkWsiMarkRenderReady(", "Procedure.i avkWsiPresentReserve(",
        "Procedure.i avkWsiPresentCommit(", "Procedure.i avkWsiPresentComplete(",
        "Procedure.i avkWsiPresentRollback(", "Procedure.i avkWsiProviderResize(",
        "Procedure.i avkWsiProviderLose(", "Procedure.i avkWsiResetDevice(",
        "avkWsiSwapDevGen[s] = avkTokenGen(device)",
        "avkWsiSurfProvSlot[s] = p", "avkWsiPresentSwap[",
        "If hasFifo = 0", "#ANVIL_VK_WSI_IMAGE_PRESENT_PENDING",
    )
    for token in required:
        if token not in text:
            raise AssertionError("source contract token missing: " + token)
    forbidden = (
        "Procedure.i vkCreateSwapchainKHR(", "Procedure vkDestroySwapchainKHR(",
        "Procedure.i vkAcquireNextImageKHR(", "Procedure.i vkQueuePresentKHR(",
        "AnvilVkAdvertise", "RockCdn", "V3dSubmit", "DmaCopy",
    )
    for token in forbidden:
        if token in text:
            raise AssertionError("unintegrated WSI module crosses its seam: " + token)
    reserve = text.split("Procedure.i avkWsiPresentReserve(", 1)[1].split(
        "Procedure.i avkWsiPresentCommit(", 1)[0]
    if "\n  avkWsiSwapImageState[" in reserve:
        raise AssertionError("present reservation mutates image ownership")
    create = text.split("Procedure.i avkWsiSwapchainCreate(", 1)[1].split(
        "Procedure.i avkWsiSwapchainRetire(", 1)[0]
    publish = create.find("avkWsiSwapLive[s] = 1")
    retire = create.find("avkWsiSwapRetired[old] = 1")
    if publish < 0 or retire < publish:
        raise AssertionError("old swapchain can retire before replacement publication")
    return len(required) + len(forbidden) + 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(argv)
    try:
        checks = registry_contract(args.registry)
        checks += source_contract(SOURCE.read_text(encoding="utf-8"))
        harness = load_harness()
        compiler = locate(args.compiler, [ROOT / "PureMetalForge.exe",
            pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")], "PureMetalForge")
        interpreter = locate(args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"], "A64 interpreter")
        rc, steps, magic, count, failures, failed_rows = emitted(harness, compiler, interpreter)
        if (rc, magic, failures) != (0, MAGIC, 0) or count < 80:
            raise AssertionError(f"emitted gate rc={rc} magic={magic:#x} rows={count} failures={failures} bad={failed_rows}")
        checks += count + 3
        print(f"PASS: {checks} WSI registry/source/emitted checks; {count} emitted rows, {steps:,} A64 instructions")
        if args.mutate:
            for label, before, after in MUTATIONS:
                mrc, _, mmagic, _, mfails, _ = emitted(harness, compiler, interpreter, (before, after))
                if mrc == 0 and mmagic == MAGIC and mfails == 0:
                    raise AssertionError(label + " mutant survived")
                print("RED:", label)
        return 0
    except (AssertionError, OSError, RuntimeError, ET.ParseError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
