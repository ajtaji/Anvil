#!/usr/bin/env python3
"""Registry and emitted-A64 gate for Anvil's Vulkan foundation."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VOCAB = HERE.parent / "vk_core_1_0.pbi"
PROBE = HERE / "vulkan_foundation.pi4"
PRODUCTION_PROBE = HERE / "vulkan_production_probe.pi4"
V3D_DEVELOPMENT_PROBE = HERE / "vulkan_v3d_development.pi4"
V3D_LINK_PROBE = HERE / "vulkan_v3d_link.pi4"
V3D_DEVELOPMENT = HERE.parent / "vk_v3d_development.pi4"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0xDEAD0000
OUT = 0x06000000
DEV_OUT = 0x06010000
REGISTRY_SHA256 = "50bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08"


CONSTANTS = {
    "VK_SUCCESS", "VK_NOT_READY", "VK_TIMEOUT", "VK_EVENT_SET",
    "VK_EVENT_RESET", "VK_INCOMPLETE", "VK_ERROR_OUT_OF_HOST_MEMORY",
    "VK_ERROR_OUT_OF_DEVICE_MEMORY", "VK_ERROR_INITIALIZATION_FAILED",
    "VK_ERROR_DEVICE_LOST", "VK_ERROR_MEMORY_MAP_FAILED",
    "VK_ERROR_LAYER_NOT_PRESENT", "VK_ERROR_EXTENSION_NOT_PRESENT",
    "VK_ERROR_FEATURE_NOT_PRESENT", "VK_ERROR_INCOMPATIBLE_DRIVER",
    "VK_ERROR_TOO_MANY_OBJECTS", "VK_ERROR_FORMAT_NOT_SUPPORTED",
    "VK_ERROR_FRAGMENTED_POOL", "VK_COMMAND_BUFFER_LEVEL_PRIMARY",
    "VK_COMMAND_BUFFER_LEVEL_SECONDARY",
    "VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT",
    "VK_COMMAND_BUFFER_USAGE_RENDER_PASS_CONTINUE_BIT",
    "VK_COMMAND_BUFFER_USAGE_SIMULTANEOUS_USE_BIT",
    "VK_COMMAND_POOL_CREATE_TRANSIENT_BIT",
    "VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT",
    "VK_COMMAND_POOL_RESET_RELEASE_RESOURCES_BIT",
    "VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT",
    "VK_STRUCTURE_TYPE_APPLICATION_INFO", "VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO", "VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_SUBMIT_INFO", "VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO",
    "VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO",
    "VK_FORMAT_B8G8R8A8_UNORM", "VK_IMAGE_LAYOUT_UNDEFINED",
    "VK_IMAGE_LAYOUT_GENERAL", "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL",
}

STRUCTS = {
    "VkExtent2D": (("uint32_t", "width"), ("uint32_t", "height")),
    "VkExtent3D": (("uint32_t", "width"), ("uint32_t", "height"), ("uint32_t", "depth")),
    "VkOffset2D": (("int32_t", "x"), ("int32_t", "y")),
    "VkOffset3D": (("int32_t", "x"), ("int32_t", "y"), ("int32_t", "z")),
    "VkViewport": (("float", "x"), ("float", "y"), ("float", "width"),
                   ("float", "height"), ("float", "minDepth"), ("float", "maxDepth")),
    "VkComponentMapping": (("VkComponentSwizzle", "r"), ("VkComponentSwizzle", "g"),
                           ("VkComponentSwizzle", "b"), ("VkComponentSwizzle", "a")),
    "VkRect2D": (("VkOffset2D", "offset"), ("VkExtent2D", "extent")),
    "VkExtensionProperties": (("char", "extensionName"), ("uint32_t", "specVersion")),
    "VkLayerProperties": (("char", "layerName"), ("uint32_t", "specVersion"),
                          ("uint32_t", "implementationVersion"), ("char", "description")),
    "VkApplicationInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("char", "pApplicationName"), ("uint32_t", "applicationVersion"),
                          ("char", "pEngineName"), ("uint32_t", "engineVersion"),
                          ("uint32_t", "apiVersion")),
    "VkAllocationCallbacks": (("void", "pUserData"),
                              ("PFN_vkAllocationFunction", "pfnAllocation"),
                              ("PFN_vkReallocationFunction", "pfnReallocation"),
                              ("PFN_vkFreeFunction", "pfnFree"),
                              ("PFN_vkInternalAllocationNotification", "pfnInternalAllocation"),
                              ("PFN_vkInternalFreeNotification", "pfnInternalFree")),
    "VkDeviceQueueCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                ("VkDeviceQueueCreateFlags", "flags"),
                                ("uint32_t", "queueFamilyIndex"),
                                ("uint32_t", "queueCount"), ("float", "pQueuePriorities")),
    "VkDeviceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                           ("VkDeviceCreateFlags", "flags"),
                           ("uint32_t", "queueCreateInfoCount"),
                           ("VkDeviceQueueCreateInfo", "pQueueCreateInfos"),
                           ("uint32_t", "enabledLayerCount"),
                           ("char", "ppEnabledLayerNames"),
                           ("uint32_t", "enabledExtensionCount"),
                           ("char", "ppEnabledExtensionNames"),
                           ("VkPhysicalDeviceFeatures", "pEnabledFeatures")),
    "VkInstanceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkInstanceCreateFlags", "flags"),
                             ("VkApplicationInfo", "pApplicationInfo"),
                             ("uint32_t", "enabledLayerCount"),
                             ("char", "ppEnabledLayerNames"),
                             ("uint32_t", "enabledExtensionCount"),
                             ("char", "ppEnabledExtensionNames")),
    "VkCommandPoolCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                ("VkCommandPoolCreateFlags", "flags"),
                                ("uint32_t", "queueFamilyIndex")),
    "VkCommandBufferAllocateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                    ("VkCommandPool", "commandPool"),
                                    ("VkCommandBufferLevel", "level"),
                                    ("uint32_t", "commandBufferCount")),
    "VkCommandBufferInheritanceInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                       ("VkRenderPass", "renderPass"),
                                       ("uint32_t", "subpass"),
                                       ("VkFramebuffer", "framebuffer"),
                                       ("VkBool32", "occlusionQueryEnable"),
                                       ("VkQueryControlFlags", "queryFlags"),
                                       ("VkQueryPipelineStatisticFlags", "pipelineStatistics")),
    "VkCommandBufferBeginInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                                 ("VkCommandBufferUsageFlags", "flags"),
                                 ("VkCommandBufferInheritanceInfo", "pInheritanceInfo")),
    "VkSubmitInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                     ("uint32_t", "waitSemaphoreCount"),
                     ("VkSemaphore", "pWaitSemaphores"),
                     ("VkPipelineStageFlags", "pWaitDstStageMask"),
                     ("uint32_t", "commandBufferCount"),
                     ("VkCommandBuffer", "pCommandBuffers"),
                     ("uint32_t", "signalSemaphoreCount"),
                     ("VkSemaphore", "pSignalSemaphores")),
}

PB_SUFFIX = {
    "uint32_t": ".l", "int32_t": ".l", "VkBool32": ".l",
    "VkComponentSwizzle": ".l", "VkStructureType": ".l",
    "VkDeviceQueueCreateFlags": ".l", "VkDeviceCreateFlags": ".l",
    "VkInstanceCreateFlags": ".l", "VkCommandPoolCreateFlags": ".l",
    "VkCommandBufferLevel": ".l", "VkQueryControlFlags": ".l",
    "VkQueryPipelineStatisticFlags": ".l", "VkCommandBufferUsageFlags": ".l",
    "VkPipelineStageFlags": ".l", "float": ".f",
    "VkCommandPool": ".i", "VkRenderPass": ".i", "VkFramebuffer": ".i",
    "VkSemaphore": ".i", "VkCommandBuffer": ".i",
    "VkOffset2D": ".VkOffset2D", "VkExtent2D": ".VkExtent2D",
}


def registry_path() -> pathlib.Path:
    value = os.environ.get("VULKAN_REGISTRY")
    if not value:
        raise SystemExit("set VULKAN_REGISTRY to pinned v1.4.350 registry/vk.xml")
    path = pathlib.Path(value)
    if not path.is_file():
        raise SystemExit("VULKAN_REGISTRY does not name a file: %s" % path)
    return path


def number(node: ET.Element, by_name: dict[str, ET.Element]) -> int:
    if node.get("value") is not None:
        return int(node.get("value"), 0)
    if node.get("bitpos") is not None:
        return 1 << int(node.get("bitpos"))
    alias = node.get("alias")
    if alias:
        return number(by_name[alias], by_name)
    raise ValueError("no core value for " + str(node.get("name")))


def parse_pbi_constants() -> dict[str, int]:
    found = {}
    for line in VOCAB.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#(VK_[A-Z0-9_]+)\s*=\s*([^\s;]+)", line)
        if match:
            token = match.group(2)
            found[match.group(1)] = int(token[1:], 16) if token.startswith("$") else int(token)
    return found


def parse_pbi_structs() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    current = None
    members: list[str] = []
    for source_line in VOCAB.read_text(encoding="utf-8").splitlines():
        line = source_line.strip()
        match = re.fullmatch(r"Structure\s+(Vk\w+)\s+Align\s+#PB_Structure_AlignC", line)
        if match:
            current = match.group(1)
            members = []
        elif line == "EndStructure" and current:
            found[current] = tuple(members)
            current = None
        elif current and line and not line.startswith(";"):
            members.append(line)
    return found


def expected_pbi_member(member: ET.Element) -> str:
    c_type = member.findtext("type")
    name = member.findtext("name")
    raw = "".join(member.itertext())
    if "*" in raw or c_type.startswith("PFN_"):
        return "*" + name
    enum = member.findtext("enum")
    if enum:
        if c_type != "char":
            raise ValueError("unsupported fixed array type " + c_type)
        return "%s.a[#%s]" % (name, enum)
    try:
        return name + PB_SUFFIX[c_type]
    except KeyError as exc:
        raise ValueError("no expected PureMetal mapping for " + c_type) from exc


def check_registry(failures: list[str]) -> int:
    path = registry_path()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != REGISTRY_SHA256:
        failures.append("registry SHA-256 %s, wanted %s" % (digest, REGISTRY_SHA256))
        return 1
    root = ET.parse(path).getroot()
    enums = {}
    for enum in root.findall(".//enum"):
        name = enum.get("name")
        if not name:
            continue
        if any(enum.get(key) is not None for key in ("value", "bitpos", "alias")):
            enums[name] = enum
    pbi = parse_pbi_constants()
    checks = 1
    if pbi.get("VK_API_VERSION_1_0") != 0x00400000:
        failures.append("VK_API_VERSION_1_0 is not 1.0.0")
    if pbi.get("VK_HEADER_VERSION") != 350:
        failures.append("VK_HEADER_VERSION is not 350")
    if pbi.get("VK_HEADER_VERSION_COMPLETE") != 0x0040415E:
        failures.append("VK_HEADER_VERSION_COMPLETE is not 1.4.350")
    checks += 3
    for name in sorted(CONSTANTS):
        if name not in enums:
            failures.append("registry has no " + name)
        elif name not in pbi:
            failures.append("vocabulary has no " + name)
        else:
            want = number(enums[name], enums)
            if pbi[name] != want:
                failures.append("%s=%d, registry says %d" % (name, pbi[name], want))
        checks += 1
    types = {t.get("name"): t for t in root.findall("./types/type") if t.get("name")}
    pbi_structs = parse_pbi_structs()
    for name, want in STRUCTS.items():
        node = types.get(name)
        if node is None:
            failures.append("registry has no structure " + name)
        else:
            got = tuple((m.findtext("type"), m.findtext("name")) for m in node.findall("member"))
            if got != want:
                failures.append("%s members %r, wanted %r" % (name, got, want))
            expected_decl = tuple(expected_pbi_member(m) for m in node.findall("member"))
            if pbi_structs.get(name) != expected_decl:
                failures.append("%s declaration %r, registry requires %r" %
                                (name, pbi_structs.get(name), expected_decl))
        checks += 2
    return checks


def locate(name: str, local: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(name)
    if value and pathlib.Path(value).is_file():
        return pathlib.Path(value)
    if local.is_file():
        return local
    raise SystemExit("set %s or provide %s" % (name, local))


def build(probe: pathlib.Path, output_name: str) -> pathlib.Path:
    compiler = locate("PMFC", ROOT / "pmfc.exe")
    image = pathlib.Path(tempfile.gettempdir()) / output_name
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(
        [str(compiler), str(probe.relative_to(ROOT)).replace("\\", "/"),
         "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("Vulkan foundation build failed\n" + run.stdout)
    return image


def run_image(image: pathlib.Path):
    interp = locate("PMF_A64_INTERP", ROOT / "tools" / "a64" / "a64_interp.py")
    spec = importlib.util.spec_from_file_location("anvil_vk_a64", interp)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cpu = module.A64()
    for i, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + i] = byte
    module.attach_symbols(cpu, image, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN
    for steps in range(5_000_000):
        if cpu.pc == RETURN:
            return cpu, cpu.x[0], steps
        cpu.step()
    raise SystemExit("Vulkan foundation probe did not return")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def main() -> int:
    failures = []
    checks = check_registry(failures)
    dev_source = V3D_DEVELOPMENT.read_text(encoding="utf-8")
    for required in ("NeonRetarget", "NeonFrameBegin", "NeonFrameEnd"):
        if required not in dev_source:
            failures.append("V3D development lowering omits " + required)
        checks += 1
    for forbidden in ("Poke", "DspCopy", "DmaCopy", "DisplayClear"):
        if forbidden in dev_source:
            failures.append("V3D development lowering contains CPU/DMA fallback token " + forbidden)
        checks += 1
    cpu, rc, steps = run_image(build(PROBE, "anvil_vk_foundation.img"))
    magic, model_checks, model_fails = u64(cpu, OUT), u64(cpu, OUT + 8), u64(cpu, OUT + 16)
    checks += 3 + model_checks
    if magic != 0x564B5445:
        failures.append("emitted probe magic is $%X" % magic)
    if rc != 0 or model_fails != 0:
        failures.append("emitted probe rc=%d failures=%d" % (rc, model_fails))
        failed_rows = [str(i + 1) for i in range(model_checks)
                       if u64(cpu, OUT + 0x100 + i * 8) == 0]
        failures.append("emitted failed check rows: " + ",".join(failed_rows))
        failures.append("handles: " + ",".join("$%016X" % u64(cpu, OUT + p)
                                                for p in (24, 32, 40, 48)))
    if model_checks < 50:
        failures.append("emitted probe ran only %d lifecycle checks" % model_checks)
    prod_cpu, prod_rc, prod_steps = run_image(
        build(PRODUCTION_PROBE, "anvil_vk_production.img")
    )
    checks += 3
    if u64(prod_cpu, OUT) != 0x564B5052:
        failures.append("production probe magic is wrong")
    if prod_rc != 0 or u64(prod_cpu, OUT + 8) != 0:
        failures.append("production probe exposed a backend/device")
    dev_cpu, dev_rc, dev_steps = run_image(
        build(V3D_DEVELOPMENT_PROBE, "anvil_vk_v3d_development.img")
    )
    dev_magic = u64(dev_cpu, DEV_OUT)
    dev_checks = u64(dev_cpu, DEV_OUT + 8)
    dev_fails = u64(dev_cpu, DEV_OUT + 16)
    checks += 3 + dev_checks
    if dev_magic != 0x564B4431:
        failures.append("V3D development probe magic is wrong")
    if dev_rc != 0 or dev_fails != 0:
        failures.append("V3D development probe rc=%d failures=%d" % (dev_rc, dev_fails))
        failed_rows = [str(i + 1) for i in range(dev_checks)
                       if u64(dev_cpu, DEV_OUT + 0x100 + i * 8) == 0]
        failures.append("V3D development failed check rows: " + ",".join(failed_rows))
    link_cpu, link_rc, link_steps = run_image(
        build(V3D_LINK_PROBE, "anvil_vk_v3d_link.img")
    )
    checks += 1
    if link_rc != 0:
        failures.append("real Neon/V3D link probe returned %d" % link_rc)
    if failures:
        print("vulkan_foundation_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1
    print("vulkan_foundation_check: PASS")
    print("  pinned registry values/member order checked")
    print("  %d emitted lifecycle checks, %d interpreted A64 instructions" % (model_checks, steps))
    print("  production boundary executed in %d A64 instructions" % prod_steps)
    print("  production device count remains zero; synthetic backend is test-only")
    print("  %d V3D development lowering checks, %d interpreted A64 instructions" %
          (dev_checks, dev_steps))
    print("  Neon submit calls are stubbed only at the hardware boundary in this host gate")
    print("  real Neon/V3D implementation linked; no MMIO executed (%d A64 instructions)" %
          link_steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
