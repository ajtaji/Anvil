#!/usr/bin/env python3
"""Compile, execute, and mutation-test the compact public descriptor gate."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/vulkan_descriptor_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
LR = 0xDEAD0000
REPORT = 0x06100000
SEEN = REPORT + (513 * 8)
MMIO = 0xFC000000
MAGIC = 0x564B4447
VERSION = 1
STEP_LIMIT = 50_000_000

# Exactly 42 production mutations.  The final tuple item names the causal
# compact-gate assertion(s) that must turn red.  An unrelated red is not a kill.
MUTANTS = (
    # P1-P8 -- per-type arithmetic, overflow, atomicity, publication.
    ("P1 UBO duplicate rows do not sum", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      uboCapacity = uboCapacity + count", "      uboCapacity = count", ("P1 UBO duplicate sum",)),
    ("P2 sample duplicate rows do not sum", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      sampleCapacity = sampleCapacity + count", "      sampleCapacity = count", ("P2 sample duplicate sum",)),
    ("P3 UBO pool sum overflow accepted", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      If count > ($FFFFFFFF - uboCapacity)", "      If count < 0", ("P3 UBO overflow rc", "P3 UBO overflow publication")),
    ("P4 sample pool sum overflow accepted", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      If count > ($FFFFFFFF - sampleCapacity)", "      If count < 0", ("P4 sample overflow rc", "P4 sample overflow publication")),
    ("P5 mixed allocation ignores UBO shortage", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p]) Or needSample > (avkDpSampleCapacity[p] - avkDpSampleOut[p])",
     "  If needSample > (avkDpSampleCapacity[p] - avkDpSampleOut[p])", ("P5 UBO shortage rc", "P5 UBO shortage atomic")),
    ("P6 mixed allocation ignores sample shortage", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p]) Or needSample > (avkDpSampleCapacity[p] - avkDpSampleOut[p])",
     "  If needUbo > (avkDpUboCapacity[p] - avkDpUboOut[p])", ("P6 sample shortage rc", "P6 sample shortage atomic")),
    ("P7 UBO allocation counter not spent", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  avkDpUboOut[p] = avkDpUboOut[p] + needUbo", "  avkDpUboOut[p] = avkDpUboOut[p] + 0", ("P7/P8 mixed spend",)),
    ("P8 sample allocation counter not spent", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  avkDpSampleOut[p] = avkDpSampleOut[p] + needSample", "  avkDpSampleOut[p] = avkDpSampleOut[p] + 0", ("P7/P8 mixed spend",)),

    # S1-S8 -- immutable type/stage schema copied at every ownership hop.
    ("S1 set drops copied binding type", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      avkDsType[idx] = avkDslType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "      avkDsType[idx] = -1", ("S1/S2 initial set schema", "S1/S2 set schema survives DSL reuse")),
    ("S2 set drops copied binding stages", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "      avkDsStages[idx] = avkDslStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "      avkDsStages[idx] = 0", ("S1/S2 initial set schema", "S1/S2 set schema survives DSL reuse")),
    ("S3 layout drops copied binding type", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "      avkLayBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = AnvilVkSetLayoutBindingTypeOf(dsl, k)", "      avkLayBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1", ("S3/S4 initial layout schema", "S3/S4 compatible layout schema", "S3/S4 layout survives DSL reuse")),
    ("S4 layout drops copied binding stages", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "      avkLayBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = AnvilVkSetLayoutBindingStagesOf(dsl, k)", "      avkLayBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0", ("S3/S4 initial layout schema", "S3/S4 compatible layout schema", "S3/S4 layout survives DSL reuse")),
    ("S5 pipeline drops copied binding type", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    avkPipeBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "    avkPipeBindingType[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1", ("S5 initial pipeline copied type", "S5/S6 pipeline schema survives layout reuse")),
    ("S6 pipeline drops copied binding stages", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    avkPipeBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "    avkPipeBindingStages[(s * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0", ("S6 initial pipeline copied stages", "S5/S6 pipeline schema survives layout reuse")),
    ("S7 command buffer drops copied binding type", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    avkCbDescType[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingType[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "    avkCbDescType[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = -1", ("S7/S8 initial CB schema", "S7/S8 CB copied schema", "S7/S8 CB survives layout reuse")),
    ("S8 command buffer drops copied binding stages", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    avkCbDescStages[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = avkLayBindingStages[(lay * #ANVIL_VK_MAX_SET_BINDINGS) + k]", "    avkCbDescStages[(c * #ANVIL_VK_MAX_SET_BINDINGS) + k] = 0", ("S7/S8 initial CB schema", "S7/S8 CB copied schema", "S7/S8 CB survives layout reuse")),

    # D1-D6 -- each device-owner branch has an isolated public call.
    ("D1 foreign DSL accepted by pipeline layout", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If AnvilVkSetLayoutDeviceSlotOf(dsl) <> d", "    If 0", ("D1 foreign DSL layout rc",)),
    ("D2 foreign DSL accepted by set allocation", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  If avkDpDev[p] <> d Or avkDslDev[lay] <> d", "  If 0", ("D2 foreign allocate rc",)),
    ("D3 wrong-device descriptor update accepted", "Anvil/Graphics/Vulkan/vk_descriptor.pbi",
     "  If avkDsDev[s] <> d", "  If 0", ("D3 foreign update fault", "D3 foreign update preservation")),
    ("D4 foreign set accepted by command buffer", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  If AnvilVkDescriptorSetDeviceSlot(set) <> d", "  If 0", ("D4 foreign set bind fault", "D4 foreign set bind preservation")),
    ("D5 foreign layout accepted by descriptor bind", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  d = avkPoolDev[avkCmdPool[c]]\n  If avkLayDev[lay] <> d", "  d = avkPoolDev[avkCmdPool[c]]\n  If 0", ("D5 foreign bind layout fault",)),
    ("D6 foreign layout accepted by push constants", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  If avkLayDev[lay] <> avkPoolDev[avkCmdPool[c]]", "  If 0", ("D6 foreign push fault", "D6 foreign push preservation")),

    # F1-F2 -- both families must fail before submission mutation.
    ("F1 stale UBO preflight skipped", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  If avkPipeUsesUniform[p] <> 0\n    If AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p]) = 0 Or AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p]) < #ANVIL_VK_UNIFORM_BYTES",
     "  If avkPipeUsesUniform[p] < 0\n    If AnvilVkDescriptorSetAddress(avkCbDescSet[c], avkPipeUniformBinding[p]) = 0 Or AnvilVkDescriptorSetRange(avkCbDescSet[c], avkPipeUniformBinding[p]) < #ANVIL_VK_UNIFORM_BYTES", ("F1 stale UBO submit rc", "F1 stale UBO no mutation")),
    ("F2 stale sample preflight skipped", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  If avkPipeUsesSample[p] <> 0\n    If AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0",
     "  If avkPipeUsesSample[p] < 0\n    If AnvilVkDescriptorSetSampledImage(avkCbDescSet[c], avkPipeSampleBinding[p], @avkSampleStage) = 0", ("F2 stale sample submit rc", "F2 stale sample no mutation")),

    # R1-R6 -- six independent descriptor dependencies.
    ("R1 UBO buffer retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    avkBufInFlight[b] = avkBufInFlight[b] + 1",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    avkBufInFlight[b] = avkBufInFlight[b] + 0", ("R1 UBO buffer callback", "R1 UBO buffer destroy guard")),
    ("R2 UBO memory retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    avkBufInFlight[b] = avkBufInFlight[b] + 1\n    avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 1",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    avkBufInFlight[b] = avkBufInFlight[b] + 1\n    avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] + 0", ("R2 UBO memory callback", "R2 UBO memory destroy guard")),
    ("R3 sampler retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If samp <> 0 : avkSampInFlight[samp] = avkSampInFlight[samp] + 1 : EndIf", "    If samp <> 0 : avkSampInFlight[samp] = avkSampInFlight[samp] + 0 : EndIf", ("R3 sampler callback", "R3 sampler destroy guard")),
    ("R4 sampled view retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If iv <> 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 1 : EndIf", "    If iv <> 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 0 : EndIf", ("R4 sampled view callback", "R4 sampled view destroy guard")),
    ("R5 sampled image retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    avkImgInFlight[img] = avkImgInFlight[img] + 1",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    avkImgInFlight[img] = avkImgInFlight[img] + 0", ("R5 sampled image callback", "R5 sampled image destroy guard")),
    ("R6 sampled memory retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    avkImgInFlight[img] = avkImgInFlight[img] + 1\n    avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] + 1",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    avkImgInFlight[img] = avkImgInFlight[img] + 1\n    avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] + 0", ("R6 sampled memory callback", "R6 sampled memory destroy guard")),

    # L1-L6 -- matching releases are individually observable after completion.
    ("L1 UBO buffer release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 0 : EndIf", ("L1 UBO buffer release",)),
    ("L2 UBO memory release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf\n    If avkMemInFlight[avkBufMemSlot[b]] > 0\n      avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 1",
     "  b = avkBufSlot(avkDrawUniformBuffer(c, p))\n  If b <> 0\n    If avkBufInFlight[b] > 0 : avkBufInFlight[b] = avkBufInFlight[b] - 1 : EndIf\n    If avkMemInFlight[avkBufMemSlot[b]] > 0\n      avkMemInFlight[avkBufMemSlot[b]] = avkMemInFlight[avkBufMemSlot[b]] - 0", ("L2 UBO memory release",)),
    ("L3 sampler release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If samp <> 0 And avkSampInFlight[samp] > 0 : avkSampInFlight[samp] = avkSampInFlight[samp] - 1 : EndIf",
     "    If samp <> 0 And avkSampInFlight[samp] > 0 : avkSampInFlight[samp] = avkSampInFlight[samp] - 0 : EndIf", ("L3 sampler release",)),
    ("L4 sampled view release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If iv <> 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 1 : EndIf",
     "    If iv <> 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 0 : EndIf", ("L4 sampled view release",)),
    ("L5 sampled image release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    If avkImgInFlight[img] > 0 : avkImgInFlight[img] = avkImgInFlight[img] - 1 : EndIf",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    If avkImgInFlight[img] > 0 : avkImgInFlight[img] = avkImgInFlight[img] - 0 : EndIf", ("L5 sampled image release",)),
    ("L6 sampled memory release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    If avkImgInFlight[img] > 0 : avkImgInFlight[img] = avkImgInFlight[img] - 1 : EndIf\n    If avkMemInFlight[avkImgMemSlot[img]] > 0\n      avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] - 1",
     "  image = avkDrawSampleImage(c, p)\n  img = avkImgSlot(image)\n  If img <> 0\n    If avkImgInFlight[img] > 0 : avkImgInFlight[img] = avkImgInFlight[img] - 1 : EndIf\n    If avkMemInFlight[avkImgMemSlot[img]] > 0\n      avkMemInFlight[avkImgMemSlot[img]] = avkMemInFlight[avkImgMemSlot[img]] - 0", ("L6 sampled memory release",)),

    # A1-A3 -- attachment view flight ownership and framebuffer guard.
    ("A1 attachment view retain omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If iv > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 1 : EndIf", "    If iv > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] + 0 : EndIf", ("A1 attachment view callback", "A1 attachment view destroy guard")),
    ("A2 attachment view release omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "    If iv > 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 1 : EndIf", "    If iv > 0 And avkIvInFlight[iv] > 0 : avkIvInFlight[iv] = avkIvInFlight[iv] - 0 : EndIf", ("A2 attachment view release",)),
    ("A3 active framebuffer destroy guard omitted", "Anvil/Graphics/Vulkan/vk_pipeline.pbi",
     "  If avkFlightActive <> 0 And avkCbFbHandle[avkFlightCb] = framebuffer", "  If avkFlightActive < 0 And avkCbFbHandle[avkFlightCb] = framebuffer", ("A3 active framebuffer guard",)),

    # O1-O3 -- public outputs are nulled before any failure.
    ("O1 descriptor layout output not nulled", "Anvil/Graphics/Vulkan/vk_api.pbi",
     "  PokeI(*pSetLayout, #VK_NULL_HANDLE)", "  PokeI(*pSetLayout, $5A3CC3A5)", ("O1 layout output null",)),
    ("O2 descriptor pool output not nulled", "Anvil/Graphics/Vulkan/vk_api.pbi",
     "  PokeI(*pDescriptorPool, #VK_NULL_HANDLE)", "  PokeI(*pDescriptorPool, $5A3CC3A5)", ("O2 pool output null",)),
    ("O3 sampler output not nulled", "Anvil/Graphics/Vulkan/vk_api.pbi",
     "  PokeI(*pSampler, #VK_NULL_HANDLE)", "  PokeI(*pSampler, $5A3CC3A5)", ("O3 sampler output null",)),
)


def locate(explicit: str | None, env_name: str, fallback: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(explicit) if explicit else pathlib.Path(os.environ[env_name]) if os.environ.get(env_name) else fallback
    if not path.is_file():
        raise SystemExit(f"{env_name} not found: {path}")
    return path.resolve()


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def checker_lock():
    path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_private_tree(path: pathlib.Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    if path.exists():
        raise RuntimeError(f"private descriptor tree did not clean up: {path}")


def manifest_hash(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix())
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "little"))
        digest.update(rel)
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


# Only a real directive at the start of a source line is an include. Vulkan's
# design comments deliberately mention `XIncludeFile "<exactly one backend>"`;
# treating prose as a path would make the frozen closure depend on a comment.
INCLUDE_RE = re.compile(rb'^[ \t]*XIncludeFile[ \t]+"([^"]+)"', re.IGNORECASE | re.MULTILINE)


def include_closure(start: pathlib.Path) -> set[pathlib.Path]:
    pending = [start.resolve()]
    found: set[pathlib.Path] = set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        if not path.is_file() or ROOT not in path.parents:
            raise RuntimeError(f"descriptor include escaped/missing: {path}")
        found.add(path)
        for raw in INCLUDE_RE.findall(path.read_bytes()):
            child = (ROOT / raw.decode("utf-8").replace("\\", "/")).resolve()
            pending.append(child)
    return found


def shared_hashes(paths: set[pathlib.Path]) -> dict[pathlib.Path, str]:
    return {path: sha256_file(path) for path in paths}


def assert_shared_unchanged(expected: dict[pathlib.Path, str]) -> None:
    for path, wanted in expected.items():
        actual = sha256_file(path)
        if actual != wanted:
            raise RuntimeError(f"shared source changed: {path} {actual} != {wanted}")


def normalized_source_with_offsets(raw: bytes) -> tuple[bytes, list[int]]:
    """Return LF-normalized bytes and every normalized boundary in raw bytes."""
    normalized = bytearray()
    offsets = [0]
    index = 0
    while index < len(raw):
        if raw[index:index + 2] == b"\r\n":
            normalized.append(10)
            index += 2
        else:
            normalized.append(raw[index])
            index += 1
        offsets.append(index)
    return bytes(normalized), offsets


def surgical_replacement(raw: bytes, old: str, new: str, name: str) -> bytes:
    normalized, offsets = normalized_source_with_offsets(raw)
    old_bytes = old.encode("utf-8")
    new_bytes = new.encode("utf-8")
    hits = normalized.count(old_bytes)
    if hits != 1:
        raise RuntimeError(f"mutation anchor {name!r} hit {hits} times")
    at = normalized.index(old_bytes)
    raw_at = offsets[at]
    raw_end = offsets[at + len(old_bytes)]
    old_slice = raw[raw_at:raw_end]
    separators = re.findall(rb"\r\n|\n", old_slice)
    parts = new_bytes.split(b"\n")
    if len(parts) - 1 != len(separators):
        raise RuntimeError(f"mutation {name!r} changes newline count")
    replacement = parts[0]
    for separator, part in zip(separators, parts[1:]):
        replacement += separator + part
    mutant = raw[:raw_at] + replacement + raw[raw_end:]
    mutant_slice = mutant[raw_at:raw_at + len(replacement)]
    if re.findall(rb"\r\n|\n", mutant_slice) != separators:
        raise RuntimeError(f"mutation {name!r} changes newline sequence")
    if mutant[:raw_at] != raw[:raw_at] or mutant[raw_at + len(replacement):] != raw[raw_end:]:
        raise RuntimeError(f"mutation {name!r} changed non-anchor bytes")
    return mutant


def freeze_build_inputs() -> tuple[pathlib.Path, str, set[pathlib.Path]]:
    sources = include_closure(GATE)
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="anvil_descriptor_snapshot_"))
    try:
        for source in sources:
            target = snapshot / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copytree(ROOT / "RaspberryPi4/Intrinsics", snapshot / "RaspberryPi4/Intrinsics")
        shutil.copytree(ROOT / "Boards", snapshot / "Boards")
        shutil.copy2(ROOT / "keywords.def", snapshot / "keywords.def")
        return snapshot, manifest_hash(snapshot), sources
    except BaseException:
        remove_private_tree(snapshot)
        raise


def build(compiler: pathlib.Path, suffix: str, snapshot: pathlib.Path, snapshot_hash: str,
          compiler_hash: str, mutation=None, runner=subprocess.run, timeout=300):
    if manifest_hash(snapshot) != snapshot_hash:
        raise RuntimeError("descriptor frozen input changed before compile")
    if sha256_file(compiler) != compiler_hash:
        raise RuntimeError("descriptor compiler changed before compile")
    work = pathlib.Path(tempfile.mkdtemp(prefix="anvil_descriptor_"))
    try:
        shutil.copytree(snapshot, work, dirs_exist_ok=True)
        if mutation is not None:
            name, rel, old, new, _killers = mutation
            path = work / rel
            original = path.read_bytes()
            path.write_bytes(surgical_replacement(original, old, new, name))
        out = work / f"{suffix}.img"
        gate = (work / GATE.relative_to(ROOT)).relative_to(work).as_posix()
        command = [str(compiler), "--compile", gate, "-t", "pi4", "--load-addr", hex(LOAD),
                   "-s", "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(work)
        result = runner(command, cwd=work, env=env, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=timeout)
        if sha256_file(compiler) != compiler_hash:
            raise RuntimeError("descriptor compiler changed during compile")
        if manifest_hash(snapshot) != snapshot_hash:
            raise RuntimeError("descriptor frozen input changed during compile")
        if result.returncode or "pmfc: OK" not in result.stdout or not out.is_file():
            raise RuntimeError("descriptor compile failed\n" + result.stdout)
        return out, work
    except BaseException:
        remove_private_tree(work)
        raise


def execute(a64, image: pathlib.Path):
    cpu = a64.A64()
    cpu.memory.update({LOAD + i: byte for i, byte in enumerate(image.read_bytes())})
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LR

    def load(address, size):
        cpu.align_guard(address, size, False)
        if address >= MMIO:
            raise RuntimeError(f"descriptor gate unexpected MMIO read {address:#x}")
        return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

    def store(address, value, size):
        cpu.align_guard(address, size, True)
        if address >= MMIO:
            raise RuntimeError(f"descriptor gate unexpected MMIO write {address:#x}")
        for i in range(size):
            cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LR:
            return cpu, steps
        cpu.step()
    raise RuntimeError("descriptor gate interpreter timeout")


def u64(cpu, slot: int) -> int:
    address = REPORT + slot * 8
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def s64(cpu, slot: int) -> int:
    value = u64(cpu, slot)
    return value - (1 << 64) if value & (1 << 63) else value


def grade(cpu):
    red: list[tuple[str, str]] = []

    def exact(slot, expected, label):
        if cpu.memory.get(SEEN + slot, 0) != 1:
            red.append((f"report row {slot} published", f"slot {slot} was not executed"))
            return
        actual = s64(cpu, slot)
        if actual != expected:
            red.append((label, f"slot {slot}={actual}, expected {expected}"))

    def true(slot, label):
        exact(slot, 1, label)

    exact(0, MAGIC, "report magic")
    exact(4, VERSION, "report version")
    exact(1, 0, "gate completion")
    exact(2, 0, "final fault clear")

    exact(100, 2, "P1 UBO duplicate sum")
    exact(101, 1, "P2 canonical sample capacity")
    exact(102, 0, "mixed UBO update")
    exact(103, 0, "mixed sample update")
    exact(104, 0, "mixed held submit")
    if s64(cpu, 105) < 1:
        red.append(("mixed backend draw", f"slot 105={s64(cpu, 105)}, expected >=1"))
    exact(106, 0, "mixed held completion")
    exact(107, 0, "mixed held releases")
    true(108, "S1/S2 initial set schema")
    true(109, "S3/S4 initial layout schema")
    true(127, "S5 initial pipeline copied type")
    true(128, "S6 initial pipeline copied stages")
    for index in range(9):
        exact(110 + index, 1, f"mixed callback dependency {index}")
    true(119, "S7/S8 initial CB schema")
    exact(130, 0, "compatible reverse DSL create")
    true(131, "compatible reverse DSL schema")
    exact(132, 0, "reverse duplicate pool create")
    true(133, "P2 sample duplicate sum")
    exact(155, 0, "five-row pool create")
    true(156, "five-row pool accumulation")
    exact(157, -20005, "unsupported fifth pool row refusal")
    exact(158, 0, "unsupported fifth pool row output")
    true(159, "unsupported fifth pool row no publication")
    exact(134, -1, "P3 UBO overflow rc")
    exact(135, 0, "P3 UBO overflow output")
    true(136, "P3 UBO overflow publication")
    exact(137, -1, "P4 sample overflow rc")
    exact(138, 0, "P4 sample overflow output")
    true(139, "P4 sample overflow publication")
    exact(140, 0, "single UBO DSL")
    exact(141, 0, "single sample DSL")
    exact(142, 0, "UBO-short pool create")
    exact(143, -1000069000, "P5 UBO shortage rc")
    exact(144, 0, "P5 UBO shortage output")
    true(145, "P5 UBO shortage atomic")
    exact(146, 0, "P5 following UBO allocation")
    true(147, "P5 following UBO accounting")
    exact(148, 0, "sample-short pool create")
    exact(149, -1000069000, "P6 sample shortage rc")
    exact(150, 0, "P6 sample shortage output")
    true(151, "P6 sample shortage atomic")
    exact(152, 0, "P6 following sample allocation")
    true(153, "P6 following sample accounting")
    true(154, "P7/P8 mixed spend")

    exact(160, 0, "compatible layout create")
    true(161, "S3/S4 compatible layout schema")
    exact(162, 0, "no-push layout create")
    exact(163, 0, "DSL same-slot incompatible reuse create")
    true(164, "DSL same-slot incompatible reuse")
    true(165, "S1/S2 set schema survives DSL reuse")
    true(166, "S3/S4 layout survives DSL reuse")
    exact(167, -20002, "stale DSL rejected")
    exact(168, 0, "stale DSL output null")
    exact(169, 0, "compatible distinct layout record")
    true(170, "S7/S8 CB copied schema")
    exact(171, 0, "layout same-slot incompatible reuse create")
    true(172, "layout same-slot incompatible reuse")
    true(173, "S5/S6 pipeline schema survives layout reuse")
    true(174, "S7/S8 CB survives layout reuse")
    exact(175, 0, "destroyed layout retained submit")
    exact(176, 0, "destroyed layout retained completion")
    exact(177, -20001, "incompatible set/layout bind fault")
    true(178, "incompatible bind preserves CB")
    exact(330, -20001, "count-only schema mismatch refusal")
    true(331, "count-only mismatch preserves full CB")
    exact(332, -20001, "type-only schema mismatch refusal")
    true(333, "type-only mismatch preserves full CB")
    exact(334, -20001, "stage-only schema mismatch refusal")
    true(335, "stage-only mismatch preserves full CB")
    exact(336, -20001, "push-only draw mismatch refusal")
    true(337, "push-only mismatch preserves draw publication")

    exact(180, 0, "dev2 DSL create")
    exact(181, -20003, "D1 foreign DSL layout rc")
    exact(182, 0, "D1 foreign DSL layout output")
    true(339, "D1 foreign DSL layout no publication")
    exact(183, 0, "dev2 layout create")
    exact(341, 0, "D2 fresh dev1 pool create")
    exact(184, -20003, "D2 foreign allocate rc")
    exact(185, 0, "D2 foreign allocate output")
    true(340, "D2 foreign allocate no pool/set mutation")
    exact(186, 0, "dev2 pool create")
    exact(187, 0, "dev2 set allocate")
    exact(188, -20003, "D3 foreign update fault")
    true(189, "D3 foreign update preservation")
    exact(190, -20003, "D4 foreign set bind fault")
    true(191, "D4 foreign set bind preservation")
    exact(192, -20003, "D5 foreign bind layout fault")
    true(338, "D5 foreign bind layout full preservation")
    exact(193, -20003, "D6 foreign push fault")
    true(194, "D6 foreign push preservation")

    exact(200, 0, "reverse sample update")
    exact(201, 0, "reverse UBO update")
    true(202, "reverse update preservation")
    exact(203, -20001, "failed UBO replacement rc")
    true(204, "failed UBO replacement preservation")
    exact(207, -20001, "near-max UBO range refusal")
    true(208, "near-max UBO range full preservation")
    exact(205, -20001, "failed sample replacement rc")
    true(206, "failed sample replacement preservation")

    exact(210, 0, "retention record")
    exact(211, 0, "retention submit")
    retain_labels = (
        "R1 UBO buffer callback", "R2 UBO memory callback", "R3 sampler callback",
        "R4 sampled view callback", "R5 sampled image callback", "R6 sampled memory callback",
        "A1 attachment view callback", "attachment image callback", "attachment memory callback")
    for index, label in enumerate(retain_labels):
        exact(212 + index, 1, label)
    guard_labels = (
        "R1 UBO buffer destroy guard", "R2 UBO memory destroy guard", "R3 sampler destroy guard",
        "R4 sampled view destroy guard", "R5 sampled image destroy guard", "R6 sampled memory destroy guard",
        "A1 attachment view destroy guard", "attachment image destroy guard", "attachment memory destroy guard")
    for index, label in enumerate(guard_labels):
        exact(221 + index, -20004, label)
    exact(309, -20004, "A3 active framebuffer guard")
    true(319, "A3 guarded framebuffer remains live")
    exact(320, 0, "A3 parallel framebuffer create")
    true(321, "A3 active framebuffer slot not reused")
    exact(230, 0, "retention completion")
    exact(322, 0, "A3 post-completion framebuffer destroy")
    true(323, "A3 post-completion framebuffer stale")
    exact(324, 0, "A3 framebuffer recreate for following rows")
    exact(231, 0, "retention aggregate release")
    release_labels = (
        "L1 UBO buffer release", "L2 UBO memory release", "L3 sampler release",
        "L4 sampled view release", "L5 sampled image release", "L6 sampled memory release",
        "A2 attachment view release", "attachment image release", "attachment memory release")
    for index, label in enumerate(release_labels):
        exact(300 + index, 0, label)
    exact(232, 0, "backend refusal record")
    exact(233, -4, "backend refusal rc")
    for index in range(9):
        exact(234 + index, 1, f"backend refusal callback {index}")
    exact(243, 0, "backend refusal rollback")
    for slot, label in ((244, "alias transition record"), (245, "alias transition submit"),
                        (246, "alias transition completion"), (247, "alias descriptor update"),
                        (248, "alias draw record"), (249, "alias draw submit"),
                        (256, "alias draw completion"), (257, "alias release"),
                        (258, "alias descriptor restore")):
        exact(slot, 0, label)
    for slot in range(250, 256):
        exact(slot, 2, f"alias count2 slot {slot}")

    exact(260, 0, "stale sample record")
    exact(261, -20004, "F2 stale sample submit rc")
    exact(293, -20004, "F2 stale sample fault provenance")
    for slot in (262, 263, 264, 265, 266, 283):
        exact(slot, 0, "F2 stale sample no mutation")
    exact(267, 0x13579BDF, "F2 stale sample observer untouched")
    exact(282, 1, "F2 stale sample fence untouched")
    exact(268, 0, "stale sample view recreate")
    exact(269, 0, "stale sample descriptor restore")
    exact(270, 0, "stale UBO record")
    exact(271, -20004, "F1 stale UBO submit rc")
    exact(294, -20004, "F1 stale UBO fault provenance")
    for slot in (272, 273, 274, 275, 276, 285):
        exact(slot, 0, "F1 stale UBO no mutation")
    exact(277, 0x2468ACE0, "F1 stale UBO observer untouched")
    exact(284, 1, "F1 stale UBO fence untouched")
    for slot in (278, 279, 280, 281):
        exact(slot, 0, f"stale UBO restore slot {slot}")
    exact(286, 0, "stale framebuffer record")
    exact(287, -20004, "stale framebuffer submit")
    true(288, "stale framebuffer no mutation")
    for slot in (289, 290, 291, 292):
        exact(slot, 0, f"final valid draw slot {slot}")

    exact(120, -20001, "O1 layout null-info rc")
    exact(121, 0, "O1 layout output null")
    exact(122, -20001, "O2 pool null-info rc")
    exact(123, 0, "O2 pool output null")
    exact(124, -20001, "O3 sampler null-info rc")
    exact(125, 0, "O3 sampler output null")
    exact(310, -20005, "allocator layout refusal rc")
    exact(311, 0, "allocator layout output null")
    true(312, "allocator layout registry unchanged")
    exact(313, -20005, "allocator pool refusal rc")
    exact(314, 0, "allocator pool output null")
    true(315, "allocator pool registry unchanged")
    exact(316, -20005, "allocator sampler refusal rc")
    exact(317, 0, "allocator sampler output null")
    true(318, "allocator sampler registry unchanged")
    exact(126, 0, "seeded shader teardown")
    return red


def run_one(compiler, a64, suffix, snapshot, snapshot_hash, compiler_hash,
            mutation=None, runner=subprocess.run, execute_fn=execute):
    image, work = build(compiler, suffix, snapshot, snapshot_hash, compiler_hash,
                        mutation=mutation, runner=runner)
    try:
        cpu, steps = execute_fn(a64, image)
        return steps, grade(cpu)
    finally:
        remove_private_tree(work)


def sourcecheck(snapshot: pathlib.Path) -> list[str]:
    errors = []
    if len(MUTANTS) != 42:
        errors.append(f"mutation inventory is {len(MUTANTS)}, expected 42")
    names = [m[0] for m in MUTANTS]
    if len(names) != len(set(names)):
        errors.append("mutation names are not unique")
    expected_groups = {"P": 8, "S": 8, "D": 6, "F": 2, "R": 6, "L": 6, "A": 3, "O": 3}
    actual_groups = {prefix: sum(name.startswith(prefix) for name in names) for prefix in expected_groups}
    if actual_groups != expected_groups:
        errors.append(f"mutation groups are {actual_groups}, expected {expected_groups}")
    for mutation in MUTANTS:
        name, rel, old, _new, killers = mutation
        path = snapshot / rel
        raw = path.read_bytes()
        normalized, _offsets = normalized_source_with_offsets(raw)
        hits = normalized.count(old.encode("utf-8"))
        if hits != 1:
            errors.append(f"{name}: anchor hits {hits}")
        if not killers:
            errors.append(f"{name}: no causal killer")
        surgical_replacement(raw, old, _new, name)
    return errors


def infra_self_test(compiler: pathlib.Path) -> int:
    temp = pathlib.Path(tempfile.gettempdir())
    before = {p.resolve() for p in temp.glob("anvil_descriptor_*") if p.is_dir()}
    snapshot, snapshot_hash, sources = freeze_build_inputs()
    hashes = shared_hashes(sources)
    compiler_hash = sha256_file(compiler)
    rejected = 0
    seen = {"failure": False, "timeout": False, "drift": False, "execute": False, "mixed_eol": False}

    def failed_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "injected compiler failure")

    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    def success_runner(*args, **kwargs):
        out = pathlib.Path(args[0][args[0].index("-o") + 1])
        out.write_bytes(b"injected image")
        return subprocess.CompletedProcess(args[0], 0, "pmfc: OK")

    def execute_failure(*args, **kwargs):
        raise RuntimeError("injected execute failure")

    fake_dir = pathlib.Path(tempfile.mkdtemp(prefix="anvil_descriptor_compiler_"))
    fake = fake_dir / "compiler.exe"
    fake.write_bytes(b"frozen compiler")

    def drift_runner(*args, **kwargs):
        fake.write_bytes(b"changed compiler")
        return success_runner(*args, **kwargs)

    try:
        raw_eol = b"prefix\r\nold one\nold two\r\nsuffix"
        changed_eol = surgical_replacement(raw_eol, "old one\nold two", "new one\nnew two", "mixed-EOL self-test")
        seen["mixed_eol"] = changed_eol == b"prefix\r\nnew one\nnew two\r\nsuffix"
        try:
            build(compiler, "infra_fail", snapshot, snapshot_hash, compiler_hash, runner=failed_runner)
        except RuntimeError as exc:
            seen["failure"] = "injected compiler failure" in str(exc)
        try:
            build(compiler, "infra_timeout", snapshot, snapshot_hash, compiler_hash, runner=timeout_runner, timeout=.01)
        except subprocess.TimeoutExpired:
            seen["timeout"] = True
        try:
            build(fake, "infra_drift", snapshot, snapshot_hash, sha256_file(fake), runner=drift_runner)
        except RuntimeError as exc:
            seen["drift"] = "compiler changed during compile" in str(exc)
        try:
            run_one(compiler, None, "infra_execute", snapshot, snapshot_hash, compiler_hash,
                    runner=success_runner, execute_fn=execute_failure)
        except RuntimeError as exc:
            seen["execute"] = "injected execute failure" in str(exc)
    finally:
        assert_shared_unchanged(hashes)
        remove_private_tree(snapshot)
        remove_private_tree(fake_dir)
    after = {p.resolve() for p in temp.glob("anvil_descriptor_*") if p.is_dir()}
    if not all(seen.values()) or rejected != 0 or after != before:
        raise RuntimeError(f"descriptor infra self-test failed: {seen}, rejected={rejected}, leaked={sorted(str(p) for p in after-before)}")
    print(f"vulkan_descriptor_check: infra self-test PASS - compiler failure abort, timeout abort, "
          f"hash-drift abort, execute abort, mixed-EOL surgicality, source unchanged, rejected={rejected}, "
          f"temp-before={len(before)}, temp-after={len(after)}")
    return 0


def campaign(args, compiler, a64, snapshot, snapshot_hash, sources):
    compiler_hash = sha256_file(compiler)
    hashes = shared_hashes(sources)
    print(f"vulkan_descriptor_check: compiler={compiler} sha256={compiler_hash}", flush=True)
    print(f"vulkan_descriptor_check: frozen-input-manifest={snapshot_hash}", flush=True)
    problems = sourcecheck(snapshot)
    if problems:
        raise RuntimeError("descriptor baseline sourcecheck failed:\n  " + "\n  ".join(problems))
    steps, red = run_one(compiler, a64, "base", snapshot, snapshot_hash, compiler_hash)
    if red:
        raise RuntimeError("descriptor baseline red:\n  " + "\n  ".join(f"{name}: {detail}" for name, detail in red))
    print(f"vulkan_descriptor_check: PASS - compact public baseline, {steps:,} A64 instructions", flush=True)
    if not args.mutate:
        return 0
    selected = MUTANTS
    if args.only_mutation:
        wanted = set(args.only_mutation)
        selected = tuple(m for m in MUTANTS if m[0] in wanted)
        missing = wanted - {m[0] for m in selected}
        if missing:
            raise SystemExit("unknown mutation(s): " + ", ".join(sorted(missing)))
    escaped = 0
    for mutation in selected:
        name, _rel, _old, _new, killers = mutation
        assert_shared_unchanged(hashes)
        try:
            _steps, red = run_one(compiler, a64, "mutant", snapshot, snapshot_hash, compiler_hash, mutation=mutation)
        finally:
            assert_shared_unchanged(hashes)
        labels = {label for label, _detail in red}
        causal = labels.intersection(killers)
        if causal:
            detail = next(detail for label, detail in red if label in causal)
            print(f"  RED {name} - {sorted(causal)[0]}: {detail}", flush=True)
        else:
            detail = red[0][0] + ": " + red[0][1] if red else "no semantic red"
            print(f"  GREEN {name} - {detail}", flush=True)
            escaped += 1
    if escaped:
        print(f"vulkan_descriptor_check: FAIL - {escaped} of {len(selected)} mutants escaped")
        return 1
    print(f"vulkan_descriptor_check: all {len(selected)} mutations causally rejected")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--interp")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--only-mutation", action="append", default=[])
    parser.add_argument("--self-test-infra", action="store_true")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = locate(args.compiler, "PMF_COMPILER", pathlib.Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"))
    if args.self_test_infra:
        return infra_self_test(compiler)
    interp = locate(args.interp, "PMF_A64_INTERP", ROOT / "tools/a64/a64_interp.py")
    a64 = load_module("descriptor_a64", interp)
    snapshot, snapshot_hash, sources = freeze_build_inputs()
    try:
        return campaign(args, compiler, a64, snapshot, snapshot_hash, sources)
    finally:
        remove_private_tree(snapshot)


if __name__ == "__main__":
    with checker_lock():
        raise SystemExit(main())
