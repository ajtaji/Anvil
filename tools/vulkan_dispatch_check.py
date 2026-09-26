#!/usr/bin/env python3
"""Registry, source, and emitted-code gate for vk_dispatch.pbi.

This gate keeps dispatch exposure separate from declaration discovery.  Its
allowlist was reviewed command by command against Vulkan compatibility docs,
public validation bodies, and the existing emitted resource/pipeline gates.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import sys

import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
from vulkan_dispatch_inventory import (InventoryError, classify,
                                       pinned_registry_bytes, public_procedures,
                                       registry_commands)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DISPATCH = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_dispatch.pbi"
GATE = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests" / "vulkan_dispatch_gate.pi4"
RESOURCE_CHECK = ROOT / "tools" / "vulkan_resource_check.py"
MAGIC = 0x564B4450
OUT = 0x06000000
ROWS = 0x06000100

WITHHELD = frozenset(("vkFreeDescriptorSets",))
ALLOWLIST = frozenset("""vkAllocateCommandBuffers vkAllocateDescriptorSets
vkAllocateMemory vkBeginCommandBuffer vkBindBufferMemory vkBindImageMemory
vkCmdBeginRenderPass vkCmdBindDescriptorSets vkCmdBindPipeline
vkCmdBindIndexBuffer vkCmdBindVertexBuffers vkCmdClearColorImage vkCmdCopyBufferToImage
vkCmdDraw vkCmdDrawIndexed vkCmdEndRenderPass
vkCmdPipelineBarrier vkCmdPushConstants vkCmdSetScissor vkCmdSetViewport vkCreateBuffer vkCreateCommandPool
vkCreateDescriptorPool vkCreateDescriptorSetLayout vkCreateDevice vkCreateFence
vkCreateFramebuffer vkCreateGraphicsPipelines vkCreateImage vkCreateImageView
vkCreateInstance vkCreatePipelineLayout vkCreateRenderPass vkCreateSampler
vkCreateSemaphore vkCreateShaderModule vkDestroyBuffer vkDestroyCommandPool
vkDestroyDescriptorPool vkDestroyDescriptorSetLayout vkDestroyDevice
vkDestroyFence vkDestroyFramebuffer vkDestroyImage vkDestroyImageView
vkDestroyInstance vkDestroyPipeline vkDestroyPipelineLayout
vkDestroyRenderPass vkDestroySampler vkDestroySemaphore vkDestroyShaderModule vkDeviceWaitIdle
vkEndCommandBuffer vkEnumerateDeviceExtensionProperties vkEnumerateDeviceLayerProperties
vkEnumerateInstanceExtensionProperties vkEnumerateInstanceLayerProperties
vkEnumeratePhysicalDevices vkFreeCommandBuffers vkFreeMemory
vkGetBufferMemoryRequirements vkGetDeviceQueue vkGetFenceStatus
vkGetImageMemoryRequirements vkGetPhysicalDeviceFeatures
vkGetPhysicalDeviceFormatProperties vkGetPhysicalDeviceImageFormatProperties
vkGetPhysicalDeviceMemoryProperties vkGetPhysicalDeviceQueueFamilyProperties
vkGetPhysicalDeviceSparseImageFormatProperties
vkMapMemory vkQueueSubmit vkQueueWaitIdle vkResetCommandBuffer vkResetCommandPool
vkResetDescriptorPool vkResetFences vkUnmapMemory vkUpdateDescriptorSets
vkWaitForFences""".split())
RESOLVERS = frozenset(("vkGetInstanceProcAddr", "vkGetDeviceProcAddr"))
DOMAIN_TOKEN = {"global": "#AVK_DISPATCH_GLOBAL", "instance": "#AVK_DISPATCH_INSTANCE",
                "device": "#AVK_DISPATCH_DEVICE", "gipa": "#AVK_DISPATCH_INSTANCE",
                "gdpa": "#AVK_DISPATCH_DEVICE"}


def load_resource_check():
    spec = importlib.util.spec_from_file_location("anvil_vkdispatch_resource_gate", RESOURCE_CHECK)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load emitted-gate harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.GATE = GATE
    return module


def table(source: str) -> dict[str, tuple[str, str]]:
    pattern = re.compile(
        r'If\s+avkDispatchName\(\*pName,\s*"([^"]+)"\)\s*:\s*'
        r'ProcedureReturn\s+avkDispatchAddress\((#[A-Z_]+),\s*@([A-Za-z0-9_]+),\s*domain\)')
    result: dict[str, tuple[str, str]] = {}
    for match in pattern.finditer(source):
        name = match.group(1)
        if name in result:
            raise AssertionError("duplicate dispatch key " + name)
        result[name] = (match.group(2), match.group(3))
    return result


def validate(rows: dict[str, tuple[str, str]], commands) -> int:
    wanted = ALLOWLIST | RESOLVERS
    if set(rows) != wanted:
        raise AssertionError("dispatch keys differ: missing=%r extra=%r" %
                             (sorted(wanted - set(rows)), sorted(set(rows) - wanted)))
    checks = 1
    for name in sorted(wanted):
        domain, target = rows[name]
        if target != name:
            raise AssertionError(f"{name} resolves to wrong procedure {target}")
        command = commands.get(name)
        if command is None:
            raise AssertionError(name + " is not a pinned core-1.0 registry command")
        if domain != DOMAIN_TOKEN[command.dispatch]:
            raise AssertionError(f"{name} has {domain}, registry requires {command.dispatch}")
        if name in ALLOWLIST and command.status != "declared_callable":
            raise AssertionError(f"{name} is allowlisted but declaration is {command.status}")
        checks += 4
    for name in WITHHELD:
        if name in rows:
            raise AssertionError("withheld declaration was exposed: " + name)
        checks += 1
    return checks


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def emitted(harness, compiler: pathlib.Path, interpreter: pathlib.Path,
            source_mutation: tuple[str, str] | None = None):
    a64 = harness.load_interpreter(interpreter)
    sources = {}
    if source_mutation:
        before, after = source_mutation
        original = DISPATCH.read_text(encoding="utf-8")
        if original.count(before) != 1:
            raise AssertionError("emitted mutant anchor count is not one")
        sources[DISPATCH.name] = original.replace(before, after, 1)
    cpu, rc, steps = harness.run_once(a64, compiler, sources)
    magic, count, failures = u64(cpu, OUT), u64(cpu, OUT + 8), u64(cpu, OUT + 16)
    failed_rows = [i + 1 for i in range(count) if u64(cpu, ROWS + i * 8) == 0]
    return rc, steps, magic, count, failures, failed_rows


def locate(value: str | None, choices: list[pathlib.Path], label: str) -> pathlib.Path:
    if value:
        choices.insert(0, pathlib.Path(value))
    for path in choices:
        if path.is_file():
            return path.resolve()
    raise RuntimeError(label + " not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    try:
        data, transport = pinned_registry_bytes(args.registry)
        commands = classify(registry_commands(data), public_procedures())
        source = DISPATCH.read_text(encoding="utf-8")
        rows = table(source)
        checks = validate(rows, commands)

        # Source contract: validation precedes lookup, names are byte-exact,
        # bounded, and Vulkan 1.0 null-instance behavior is explicit.
        required_source = (
            "While n < 128", "If a <> b : ProcedureReturn 0", "If a = 0 : ProcedureReturn 1",
            "If instance = #VK_NULL_HANDLE", "If avkInstSlot(instance) = 0 : ProcedureReturn 0",
            "If *pName = 0 Or avkDevSlot(device) = 0 : ProcedureReturn 0",
            "#AVK_QUERY_GIPA_NULL", "#AVK_QUERY_GIPA_INSTANCE", "#AVK_QUERY_GDPA_DEVICE",
        )
        for token in required_source:
            if token not in source:
                raise AssertionError("dispatch source lost contract token " + token)
            checks += 1

        # Hostile table models: unreviewed exposure, wrong pointer, wrong
        # domain, case drift, a removed audited command, and both withheld rows.
        mutants = []
        missing = dict(rows); missing.pop("vkQueueSubmit"); mutants.append(("removed audited row", missing))
        extra = dict(rows); extra["vkCreateEvent"] = ("#AVK_DISPATCH_DEVICE", "vkCreateEvent"); mutants.append(("missing command exposed", extra))
        target = dict(rows); target["vkDeviceWaitIdle"] = ("#AVK_DISPATCH_DEVICE", "vkQueueSubmit"); mutants.append(("wrong pointer", target))
        domain = dict(rows); domain["vkCreateDevice"] = ("#AVK_DISPATCH_DEVICE", "vkCreateDevice"); mutants.append(("wrong domain", domain))
        case = dict(rows); case["vkdevicewaitidle"] = case.pop("vkDeviceWaitIdle"); mutants.append(("case-folded key", case))
        for withheld in WITHHELD:
            leaked = dict(rows); leaked[withheld] = ("#AVK_DISPATCH_DEVICE", withheld)
            mutants.append(("withheld exposure " + withheld, leaked))
        for label, mutant in mutants:
            try:
                validate(mutant, commands)
            except AssertionError:
                checks += 1
            else:
                raise AssertionError(label + " mutant survived")

        harness = load_resource_check()
        compiler = locate(args.compiler, [ROOT / "PureMetalForge.exe",
            pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")], "PureMetalForge")
        interpreter = locate(args.interp, [ROOT / "tools" / "a64" / "a64_interp.py"], "A64 interpreter")
        rc, steps, magic, count, failures, failed_rows = emitted(harness, compiler, interpreter)
        if (rc, magic, failures) != (0, MAGIC, 0) or count < 50:
            raise AssertionError(f"emitted gate rc={rc} magic={magic:#x} rows={count} failures={failures} bad={failed_rows}")
        checks += count + 3
        print(f"PASS: {checks} dispatch registry/source/emitted checks; {count} emitted rows, {steps:,} A64 instructions ({transport})")

        if args.mutate:
            mutations = (
                ("wrong domain", "@vkCreateDevice, domain)", "@vkCreateDevice, #AVK_QUERY_GDPA_DEVICE)"),
                ("withheld exposure", "  ProcedureReturn 0\nEndProcedure\n\nProcedure.i vkGetInstanceProcAddr",
                 "  If avkDispatchName(*pName, \"vkFreeDescriptorSets\") : ProcedureReturn @vkFreeDescriptorSets : EndIf\n  ProcedureReturn 0\nEndProcedure\n\nProcedure.i vkGetInstanceProcAddr"),
                ("wrong pointer", "@vkDeviceWaitIdle, domain)", "@vkQueueSubmit, domain)"),
            )
            for label, before, after in mutations:
                mrc, _, mmagic, _, mfails, _ = emitted(harness, compiler, interpreter, (before, after))
                if mrc == 0 and mmagic == MAGIC and mfails == 0:
                    raise AssertionError(label + " emitted mutant survived")
                print("RED:", label)
        return 0
    except (AssertionError, InventoryError, OSError, RuntimeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
