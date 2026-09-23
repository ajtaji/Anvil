#!/usr/bin/env python3
"""Focused source/runtime gate for the concrete resident present record."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
DISPLAY = ROOT / "Anvil/Graphics/Vulkan/neon_vk_display.pi4"
BRIDGE = ROOT / "Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pi4"
FIXTURE = ROOT / "RaspberryPi4/Tests/neon_vk_display_record_gate.pi4"
DEFAULT_COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
INTERP = ROOT / "tools/a64/a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0xDEAD0000


def must(text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing anchor: {needle}")


def load_interpreter():
    spec = importlib.util.spec_from_file_location("nvd_a64", INTERP)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_fixture(compiler: Path, source: str, work: Path, name: str):
    src = work / f"{name}.pi4"
    image = work / f"{name}.img"
    src.write_text(source, encoding="utf-8")
    run = subprocess.run(
        [str(compiler), "--compile", str(src), "-t", "pi4", "--load-addr", hex(LOAD),
         "--stack-addr", hex(STACK), "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
        capture_output=True, text=True, timeout=120,
    )
    if run.returncode or not image.is_file():
        raise AssertionError("fixture compile failed\n" + run.stdout + run.stderr)
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("|")
        if len(fields) >= 4 and fields[0] == "1" and fields[1].isdigit():
            entries[fields[2].lower()] = LOAD + int(fields[1])
    entry = entries.get("main")
    if entry is None:
        raise AssertionError("compiled fixture has no gate entry")
    return image.read_bytes(), entry


def execute_fixture(a64, product):
    blob, entry = product
    cpu = a64.A64()
    cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
    cpu.pc, cpu.sp, cpu.x[30] = entry, STACK, RETURN
    for _ in range(2_000_000):
        if cpu.pc == RETURN:
            return cpu.x[0]
        cpu.step()
    raise AssertionError("display record fixture did not return")


class Record:
    def __init__(self):
        self.state = 0
        self.target = 0
        self.framebuffer = 0
        self.sequence = 0

    def publish(self, target, framebuffer, sequence, width, height, pitch):
        if self.state or target < 1 or not framebuffer or sequence < 1:
            return False
        if width < 1 or height < 1 or pitch < width * 4:
            return False
        self.state, self.target, self.framebuffer, self.sequence = 1, target, framebuffer, sequence
        return True

    def matches(self, target, framebuffer):
        return self.state == 1 and self.target == target and self.framebuffer == framebuffer

    def consume(self, target, framebuffer):
        if not self.matches(target, framebuffer):
            return False
        self.state = 0
        return True

    def invalidate(self, target, framebuffer):
        if not self.state:
            return True
        if not self.matches(target, framebuffer):
            return False
        self.state = 0
        return True


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=Path(os.environ.get("PMF_COMPILER", DEFAULT_COMPILER)))
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler.is_file():
        raise AssertionError(f"compiler not found: {args.compiler}")
    adapter = ADAPTER.read_text(encoding="utf-8")
    display = DISPLAY.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    fixture = FIXTURE.read_text(encoding="utf-8")
    if "nvcPresent" in adapter:
        raise AssertionError("adapter retains a second present authority")
    for needle in (
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_display.pi4"',
        "nvcNextTargetGeneration = nvcNextTargetGeneration + 1",
        "nvcNextTargetGeneration = #NVC_MAX_GENERATION",
        "nvcTargetGeneration = nvcNextTargetGeneration",
        "nvcNextFrameSequence = nvcNextFrameSequence + 1",
        "nvdPresentPublish(nvcTargetGeneration, nvcFramebuffer",
        "nvdPresentMatches(nvcTargetGeneration, nvcFramebuffer)",
        "nvdPresentPending()",
        "nvdPresentConsume(nvcTargetGeneration, nvcFramebuffer)",
        "nvdPresentClear()",
        "nvdWsiMarkReady()", "nvdWsiReserve()", "nvdWsiCommit()", "nvdWsiRollback()",
        "NeonVkChromeWsiAttach(device.i, swapchain.i, imageIndex.i)",
    ):
        must(adapter, needle)
    for needle in (
        "frameSequence.q", "targetGeneration.i", "framebuffer.i",
        "nvdPresentPublish", "nvdPresentMatches", "nvdPresentConsume",
        "nvdPresentInvalidate",
    ):
        must(display, needle)
    for needle in (
        'XIncludeFile "Anvil/Graphics/Vulkan/vk_wsi.pbi"',
        "nvdWsiAttach", "nvdWsiMarkReady", "nvdWsiReserve", "nvdWsiCommit",
        "nvdWsiComplete", "nvdWsiRollback", "avkWsiImageKey",
        "avkWsiPresentReserve", "avkWsiPresentCommit", "avkWsiPresentComplete",
        "#NVD_WSI_RESERVED", "nvdWsiState = #NVD_WSI_RESERVED",
        "avkWsiReleaseImage",
    ):
        must(bridge, needle)
    for needle in (
        "nvdPresentPublish(4, $1234", "nvdPresentConsume(4, $1234)",
        "nvdPresentInvalidate(4, $1234)", "nvdPresentInvalidate(5, $1234)",
        "nvdPresentClear()", "NvdWsiRollbackGate()",
        "avkWsiImageState(device, swapchain, image) <> #ANVIL_VK_WSI_IMAGE_AVAILABLE",
        "nvdWsiTicket <> 0",
        "nvdWsiTicket = ticket + 1",
        "nvdPresentInvalidate(7, $5678) <> 0 Or nvdPresentPending() = 0",
    ):
        must(fixture, needle)

    rec = Record()
    assert rec.publish(4, 0x1234, 1, 640, 360, 2560)
    assert not rec.publish(4, 0x1234, 2, 640, 360, 2560)
    assert not rec.matches(5, 0x1234)
    assert not rec.consume(5, 0x1234)
    assert rec.consume(4, 0x1234)
    assert not rec.consume(4, 0x1234)
    assert rec.publish(4, 0x1234, 2, 640, 360, 2560)
    assert not rec.invalidate(4, 0x1235)
    assert rec.invalidate(4, 0x1234)
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="anvil-nvd-") as temp:
        work = Path(temp)
        product = compile_fixture(args.compiler, fixture, work, "baseline")
        if execute_fixture(a64, product) != 0:
            raise AssertionError("emitted baseline fixture returned nonzero")
        stale = fixture.replace("nvdPresentMatches(5, $1234) <> 0", "nvdPresentMatches(5, $1234) = 0")
        if execute_fixture(a64, compile_fixture(args.compiler, stale, work, "stale")) == 0:
            raise AssertionError("stale-target mutation was not rejected by emitted procedures")
        duplicate = fixture.replace("nvdPresentConsume(4, $1234) <> 0", "nvdPresentConsume(4, $1234) = 0")
        if execute_fixture(a64, compile_fixture(args.compiler, duplicate, work, "duplicate")) == 0:
            raise AssertionError("duplicate-consume mutation was not rejected by emitted procedures")
    print("neon_vk_display_record_check: PASS")
    print("  source anchors: PASS")
    print("  emitted baseline and stale/duplicate mutations: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as exc:
        print(f"neon_vk_display_record_check: FAIL - {exc}")
        raise SystemExit(1)
