"""Desk gate for the one-backend Vulkan composition seam."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / "Anvil/Graphics/Vulkan/vk_backend_select.pbi"
SOFTWARE_FIXTURE = ROOT / "Anvil/Graphics/Vulkan/vk_backend_software_test.pi4"
PI4_BOARD = ROOT / "RaspberryPi4/Board/board.pi4"


def source_checks(selector: str, fixture: str, board: str) -> list[str]:
    errors: list[str] = []
    if "#ANVIL_VULKAN_BACKEND_V3D = 1" not in selector:
        errors.append("V3D selector value missing")
    if "#ANVIL_VULKAN_BACKEND_SOFTWARE = 2" not in selector:
        errors.append("software selector value missing")
    if selector.count("CompilerIf #ANVIL_VULKAN_BACKEND =") != 1:
        errors.append("selector does not have one primary branch")
    if "CompilerElseIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_SOFTWARE" not in selector:
        errors.append("selector software branch missing")
    if "CompilerError \"#ANVIL_VULKAN_BACKEND must select exactly one Vulkan backend\"" not in selector:
        errors.append("selector unknown-value failure missing")
    if "#ANVIL_VULKAN_BACKEND = 2" not in fixture or "vk_backend_select.pbi" not in fixture or "Procedure Main()" not in fixture:
        errors.append("software fixture does not select through seam")
    if "#ANVIL_VULKAN_BACKEND = 1" not in board or "vk_backend_select.pbi" not in board:
        errors.append("Pi4 board does not retain V3D default through seam")
    if 'XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"' in board:
        errors.append("Pi4 board still directly includes V3D backend")
    return errors


def compile_fixture(compiler: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="vulkan-backend-select-") as temp_name:
        out_dir = Path(temp_name).resolve()
        output = (out_dir / "software.img").resolve()
        if out_dir.parent != Path(tempfile.gettempdir()).resolve():
            return False, "temporary directory escaped the system temporary root"
        command = [
            str(compiler), "--compile", str(SOFTWARE_FIXTURE), "-t", "pi4",
            "--load-addr", "0x500000", "--stack-addr", "0x4F00000",
            "--entry-returns", "-o", str(output),
        ]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    detail = (result.stdout + result.stderr).strip()
    return result.returncode == 0 and "pmfc:" in detail, detail


def run_self_test() -> int:
    selector = SELECTOR.read_text(encoding="utf-8")
    fixture = SOFTWARE_FIXTURE.read_text(encoding="utf-8")
    board = PI4_BOARD.read_text(encoding="utf-8")
    if source_checks(selector, fixture, board):
        return 1
    mutants = [
        (selector.replace("#ANVIL_VULKAN_BACKEND_SOFTWARE = 2", "#ANVIL_VULKAN_BACKEND_SOFTWARE = 1"), fixture, board),
        (selector.replace("CompilerElseIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_SOFTWARE", "CompilerElseIf 0"), fixture, board),
        (selector, fixture.replace("#ANVIL_VULKAN_BACKEND = 2", "#ANVIL_VULKAN_BACKEND = 1"), board),
        (selector, fixture, board.replace("#ANVIL_VULKAN_BACKEND = 1", "#ANVIL_VULKAN_BACKEND = 2")),
    ]
    if any(not source_checks(*candidate) for candidate in mutants):
        return 2
    print("PASS: backend selector baseline and four hostile mutations")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    errors = source_checks(
        SELECTOR.read_text(encoding="utf-8"),
        SOFTWARE_FIXTURE.read_text(encoding="utf-8"),
        PI4_BOARD.read_text(encoding="utf-8"),
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    if args.compiler:
        ok, detail = compile_fixture(args.compiler)
        if not ok:
            print(detail)
            return 1
        print("PASS: software backend selector fixture compiled")
    print("PASS: software backend selector and Pi4 V3D default")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
