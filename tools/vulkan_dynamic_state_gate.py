#!/usr/bin/env python3
"""Emitted regression for Vulkan's packed 32-bit dynamic-state enum array."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import neon_vk_chrome_acceptance_check as chrome  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "Anvil/Graphics/Vulkan/vk_pipeline.pbi"
CORE_TYPES = 'XIncludeFile "Anvil/Graphics/Vulkan/vk_core_1_0.pbi"'
MARKER = "; @PRODUCTION_DYNAMIC_STATE_VALIDATOR@"


def fixture(array_type: str, expect_success: bool) -> str:
    expected = "#VK_SUCCESS" if expect_success else "#ANVIL_VK_ERR_UNSUPPORTED"
    output_checks = (
        "  If viewport <> 1 Or scissor <> 1 : ProcedureReturn 2 : EndIf\n"
        if expect_success else ""
    )
    return f'''{CORE_TYPES}
#ANVIL_VK_ERR_ARGS = -20001
#ANVIL_VK_ERR_UNSUPPORTED = -20005

Procedure.i avkFault(code.i, text.i)
  ProcedureReturn code
EndProcedure

{MARKER}

Procedure.i Main()
  Dim dynStates.{array_type}[2]
  Define ds.VkPipelineDynamicStateCreateInfo
  Define viewport.i, scissor.i, rc.i
  dynStates[0] = #VK_DYNAMIC_STATE_VIEWPORT
  dynStates[1] = #VK_DYNAMIC_STATE_SCISSOR
  ds\\sType = #VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO
  ds\\dynamicStateCount = 2
  ds\\pDynamicStates = @dynStates[0]
  rc = avkPipeDynamicState(@ds, @viewport, @scissor)
  If rc <> {expected} : ProcedureReturn 1 : EndIf
{output_checks}  ProcedureReturn 0
EndProcedure
'''


def build_and_run(compiler: Path, work: Path, name: str, source: str,
                  expected: int) -> int:
    image = chrome.build(compiler, work, name, source)
    a64 = chrome.load_interpreter(chrome.DEFAULT_INTERP)
    result, steps = chrome.execute(a64, image, step_limit=500_000)
    if result != expected:
        raise AssertionError(f"{name} returned {result}, expected {expected}; {steps} instructions")
    return steps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True, type=Path)
    args = ap.parse_args()
    pipeline = PIPELINE.read_text(encoding="utf-8-sig")
    production = chrome.procedure_body(pipeline, "avkPipeDynamicState")
    checks = 0
    with tempfile.TemporaryDirectory(prefix="anvil-vk-dynamic-state-") as temp:
        work = Path(temp)
        for name, kind, success, expected in (
            ("packed_l", "l", True, 0),
            ("wide_i_mutant", "i", False, 0),
        ):
            source = fixture(kind, success).replace(MARKER, production)
            checks += build_and_run(args.compiler.resolve(), work, name, source, expected)
    print("vulkan_dynamic_state_gate: PASS - actual pipeline validator accepts packed .l enums and rejects the .i stride mutant")
    print(f"  emitted validator instructions across baseline and mutant: {checks:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
