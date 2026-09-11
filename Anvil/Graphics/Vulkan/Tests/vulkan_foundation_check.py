#!/usr/bin/env python3
"""Registry and emitted-A64 gate for Anvil's Vulkan ABI and lifecycle.

This gate answers two questions and no others:

  1. does every constant, structure member name, member order and member
     type in Anvil's vocabulary match the PINNED Khronos registry, and
  2. does the compiled AArch64 code give every one of those structures
     the exact size and offsets the C ABI requires, and does the public
     vk* surface refuse what it does not implement.

It does NOT prove GPU execution. The behavioural gate for the resource,
layout, fence and submission engine is tools/vulkan_resource_check.py,
and the backend link gate is tools/vulkan_v3d_backend_check.py.

  VULKAN_REGISTRY=<pinned v1.4.350 registry/vk.xml> PMFC=<pmfc.exe> \\
      py -3 Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py
"""

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
V3D_BACKEND = HERE.parent / "vk_v3d_backend.pi4"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0xDEAD0000
OUT = 0x06000000
MMIO = 0xFC000000
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
    "VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO", "VK_STRUCTURE_TYPE_FENCE_CREATE_INFO",
    "VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO", "VK_STRUCTURE_TYPE_MEMORY_BARRIER",
    "VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER", "VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER",
    "VK_FORMAT_UNDEFINED", "VK_FORMAT_R8G8B8A8_UNORM", "VK_FORMAT_B8G8R8A8_UNORM",
    "VK_IMAGE_LAYOUT_UNDEFINED", "VK_IMAGE_LAYOUT_GENERAL",
    "VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL",
    "VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL", "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL",
    "VK_IMAGE_LAYOUT_PREINITIALIZED",
    "VK_IMAGE_TYPE_1D", "VK_IMAGE_TYPE_2D", "VK_IMAGE_TYPE_3D",
    "VK_IMAGE_TILING_OPTIMAL", "VK_IMAGE_TILING_LINEAR",
    "VK_SHARING_MODE_EXCLUSIVE", "VK_SHARING_MODE_CONCURRENT",
    "VK_SAMPLE_COUNT_1_BIT", "VK_SAMPLE_COUNT_2_BIT",
    "VK_IMAGE_USAGE_TRANSFER_SRC_BIT", "VK_IMAGE_USAGE_TRANSFER_DST_BIT",
    "VK_IMAGE_USAGE_SAMPLED_BIT", "VK_IMAGE_USAGE_STORAGE_BIT",
    "VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT",
    "VK_IMAGE_ASPECT_COLOR_BIT", "VK_IMAGE_ASPECT_DEPTH_BIT",
    "VK_IMAGE_ASPECT_STENCIL_BIT", "VK_IMAGE_ASPECT_METADATA_BIT",
    "VK_MAX_MEMORY_TYPES", "VK_MAX_MEMORY_HEAPS",
    "VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT", "VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT",
    "VK_MEMORY_PROPERTY_HOST_COHERENT_BIT", "VK_MEMORY_PROPERTY_HOST_CACHED_BIT",
    "VK_MEMORY_HEAP_DEVICE_LOCAL_BIT",
    "VK_QUEUE_GRAPHICS_BIT", "VK_QUEUE_COMPUTE_BIT", "VK_QUEUE_TRANSFER_BIT",
    "VK_QUEUE_SPARSE_BINDING_BIT",
    "VK_ACCESS_TRANSFER_READ_BIT", "VK_ACCESS_TRANSFER_WRITE_BIT",
    "VK_ACCESS_HOST_READ_BIT", "VK_ACCESS_HOST_WRITE_BIT",
    "VK_ACCESS_MEMORY_READ_BIT", "VK_ACCESS_MEMORY_WRITE_BIT",
    "VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT", "VK_PIPELINE_STAGE_TRANSFER_BIT",
    "VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT", "VK_PIPELINE_STAGE_HOST_BIT",
    "VK_PIPELINE_STAGE_ALL_COMMANDS_BIT",
    "VK_DEPENDENCY_BY_REGION_BIT", "VK_FENCE_CREATE_SIGNALED_BIT",
    "VK_QUEUE_FAMILY_IGNORED", "VK_REMAINING_MIP_LEVELS",
    "VK_REMAINING_ARRAY_LAYERS",
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
    "VkMemoryAllocateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkDeviceSize", "allocationSize"),
                             ("uint32_t", "memoryTypeIndex")),
    "VkMemoryRequirements": (("VkDeviceSize", "size"), ("VkDeviceSize", "alignment"),
                             ("uint32_t", "memoryTypeBits")),
    "VkMemoryType": (("VkMemoryPropertyFlags", "propertyFlags"), ("uint32_t", "heapIndex")),
    "VkMemoryHeap": (("VkDeviceSize", "size"), ("VkMemoryHeapFlags", "flags")),
    "VkPhysicalDeviceMemoryProperties": (("uint32_t", "memoryTypeCount"),
                                         ("VkMemoryType", "memoryTypes"),
                                         ("uint32_t", "memoryHeapCount"),
                                         ("VkMemoryHeap", "memoryHeaps")),
    "VkQueueFamilyProperties": (("VkQueueFlags", "queueFlags"), ("uint32_t", "queueCount"),
                                ("uint32_t", "timestampValidBits"),
                                ("VkExtent3D", "minImageTransferGranularity")),
    "VkImageCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("VkImageCreateFlags", "flags"), ("VkImageType", "imageType"),
                          ("VkFormat", "format"), ("VkExtent3D", "extent"),
                          ("uint32_t", "mipLevels"), ("uint32_t", "arrayLayers"),
                          ("VkSampleCountFlagBits", "samples"), ("VkImageTiling", "tiling"),
                          ("VkImageUsageFlags", "usage"), ("VkSharingMode", "sharingMode"),
                          ("uint32_t", "queueFamilyIndexCount"),
                          ("uint32_t", "pQueueFamilyIndices"),
                          ("VkImageLayout", "initialLayout")),
    "VkImageSubresourceRange": (("VkImageAspectFlags", "aspectMask"),
                                ("uint32_t", "baseMipLevel"), ("uint32_t", "levelCount"),
                                ("uint32_t", "baseArrayLayer"), ("uint32_t", "layerCount")),
    "VkImageMemoryBarrier": (("VkStructureType", "sType"), ("void", "pNext"),
                             ("VkAccessFlags", "srcAccessMask"),
                             ("VkAccessFlags", "dstAccessMask"),
                             ("VkImageLayout", "oldLayout"), ("VkImageLayout", "newLayout"),
                             ("uint32_t", "srcQueueFamilyIndex"),
                             ("uint32_t", "dstQueueFamilyIndex"), ("VkImage", "image"),
                             ("VkImageSubresourceRange", "subresourceRange")),
    "VkFenceCreateInfo": (("VkStructureType", "sType"), ("void", "pNext"),
                          ("VkFenceCreateFlags", "flags")),
}

PB_SUFFIX = {
    "uint32_t": ".l", "int32_t": ".l", "VkBool32": ".l",
    "VkComponentSwizzle": ".l", "VkStructureType": ".l",
    "VkDeviceQueueCreateFlags": ".l", "VkDeviceCreateFlags": ".l",
    "VkInstanceCreateFlags": ".l", "VkCommandPoolCreateFlags": ".l",
    "VkCommandBufferLevel": ".l", "VkQueryControlFlags": ".l",
    "VkQueryPipelineStatisticFlags": ".l", "VkCommandBufferUsageFlags": ".l",
    "VkPipelineStageFlags": ".l", "float": ".f",
    "VkImageCreateFlags": ".l", "VkImageType": ".l", "VkFormat": ".l",
    "VkSampleCountFlagBits": ".l", "VkImageTiling": ".l",
    "VkImageUsageFlags": ".l", "VkSharingMode": ".l", "VkImageLayout": ".l",
    "VkImageAspectFlags": ".l", "VkAccessFlags": ".l",
    "VkMemoryPropertyFlags": ".l", "VkMemoryHeapFlags": ".l",
    "VkQueueFlags": ".l", "VkFenceCreateFlags": ".l",
    "VkDeviceSize": ".q", "uint64_t": ".q",
    "VkCommandPool": ".i", "VkRenderPass": ".i", "VkFramebuffer": ".i",
    "VkSemaphore": ".i", "VkCommandBuffer": ".i", "VkImage": ".i",
    "VkDeviceMemory": ".i", "VkFence": ".i",
    "VkOffset2D": ".VkOffset2D", "VkExtent2D": ".VkExtent2D",
    "VkExtent3D": ".VkExtent3D",
    "VkImageSubresourceRange": ".VkImageSubresourceRange",
    "VkMemoryType": ".VkMemoryType", "VkMemoryHeap": ".VkMemoryHeap",
}

# The registry writes its all-ones sentinels as C expressions.
C_SENTINELS = {"(~0U)": 0xFFFFFFFF, "(~0ULL)": 0xFFFFFFFFFFFFFFFF, "(~0U-1)": 0xFFFFFFFE}


def registry_path() -> pathlib.Path:
    value = os.environ.get("VULKAN_REGISTRY")
    if not value:
        raise SystemExit("set VULKAN_REGISTRY to pinned v1.4.350 registry/vk.xml")
    path = pathlib.Path(value)
    if not path.is_file():
        raise SystemExit("VULKAN_REGISTRY does not name a file: %s" % path)
    return path


def number(node: ET.Element, by_name: dict[str, ET.Element]) -> int:
    value = node.get("value")
    if value is not None:
        if value in C_SENTINELS:
            return C_SENTINELS[value]
        return int(value, 0)
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
        # A fixed array keeps the registry's own extent constant, so a
        # changed VK_MAX_MEMORY_TYPES cannot be missed by this gate.
        if c_type == "char":
            return "%s.a[#%s]" % (name, enum)
        try:
            return "%s%s[#%s]" % (name, PB_SUFFIX[c_type], enum)
        except KeyError as exc:
            raise ValueError("no expected PureMetal mapping for array of " + c_type) from exc
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
    # Anvil declares no Vulkan union, and must not: PureMetal has no
    # union, and one arm of VkClearColorValue masquerading as the whole
    # type is exactly the silent wrong answer this project refuses.
    if "VkClearColorValue" in pbi_structs:
        failures.append("vk_core_1_0.pbi declares VkClearColorValue as a structure; it is a union")
    checks += 1
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

    # AN MMIO HARD STOP. Neither of these probes may touch hardware: one
    # links the test backend and one links no backend at all.
    def guard(addr: int, write: bool) -> None:
        if addr >= MMIO:
            kind = "write" if write else "read"
            raise SystemExit(
                "vulkan_foundation_check: unexpected MMIO %s at $%08X - this probe "
                "is supposed to touch no hardware at all" % (kind, addr))

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
    for steps in range(20_000_000):
        if cpu.pc == RETURN:
            return cpu, cpu.x[0], steps
        cpu.step()
    raise SystemExit("Vulkan foundation probe did not return")


def u64(cpu, addr: int) -> int:
    return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(8))


def main() -> int:
    failures = []
    checks = check_registry(failures)

    # The Pi backend must lower through the engine this tree proves on
    # silicon, and must not contain a processor-side or DMA fallback: a
    # fallback would let a green board test be a test of memcpy.
    backend_source = V3D_BACKEND.read_text(encoding="utf-8")
    for required in ("NeonRetarget", "NeonFrameBegin", "NeonFrameEnd"):
        if required not in backend_source:
            failures.append("the Pi 4 V3D backend omits " + required)
        checks += 1
    for forbidden in ("PokeN(", "PokeI(", "PokeL(", "DspCopy", "DmaCopy", "DisplayClear",
                      "DspDmaFill"):
        if forbidden in backend_source:
            failures.append("the Pi 4 V3D backend contains the fallback token " + forbidden)
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
    if model_checks < 100:
        failures.append("emitted probe ran only %d checks" % model_checks)

    prod_cpu, prod_rc, prod_steps = run_image(
        build(PRODUCTION_PROBE, "anvil_vk_production.img"))
    checks += 3
    if u64(prod_cpu, OUT) != 0x564B5052:
        failures.append("production probe magic is wrong")
    if prod_rc != 0 or u64(prod_cpu, OUT + 8) != 0:
        failures.append("production probe exposed a backend or a device")

    if failures:
        print("vulkan_foundation_check: FAIL")
        for failure in failures:
            print("  " + failure)
        return 1
    print("vulkan_foundation_check: PASS")
    print("  pinned registry values, member names, member order and member types checked")
    print("  %d emitted ABI and lifecycle checks, %d interpreted A64 instructions, no MMIO"
          % (model_checks, steps))
    print("  production boundary executed in %d A64 instructions; device count stays zero"
          % prod_steps)
    print("  the Pi 4 V3D backend lowers through Neon/V3D and holds no CPU or DMA fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
