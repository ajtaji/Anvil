#!/usr/bin/env python3
"""Desk gate for the two-cycle Neon/V3D ownership proof payload."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/neonV3dOwnershipProof.pi4"
V3D = ROOT / "RaspberryPi4/Lib/v3d.pi4"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
DEFAULT_COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")


class GateError(Exception):
    pass


def require(text: str, needle: str) -> None:
    if needle not in text:
        raise GateError(f"missing anchor: {needle}")


def check(source: str, v3d: str, neon: str) -> int:
    for needle in (
        '#NVP_CYCLES = 2', '#NVP_HEADER_WORDS = 16',
        '#NVP_RECORD_WORDS = 56', 'Global Dim nvpReport.l[#NVP_REPORT_WORDS]',
        'NeonInit()', 'NeonFrameBegin(', 'Neon_Box(', 'NeonFrameEnd()',
        'NeonShutdown()', 'nvpCycle(0) : nvpCycle(1)',
        'ProcedureReturn @nvpReport[0]', 'V3dBinBfcBefore()',
        'V3dBinCt0cs()', 'V3dBinCt0ca()', 'V3dBinCt0ea()',
        'V3dBinIntSts()', 'V3dMmuCtlNow()', 'V3dMmuPtBase()',
        'v3d_resetCt0csBefore', 'v3d_resetCt0csAfter',
        'v3d_resetCt1csBefore', 'v3d_resetCt1csAfter',
        'v3d_resetBfcBefore', 'v3d_resetBfcAfter',
    ):
        require(source, needle)
    if source.count('nvpCycle(') != 3:  # declaration plus two calls
        raise GateError('cycle count drift')
    for needle in ('Procedure.i V3dOwnershipReset()', 'Procedure.i V3dOwnershipClaim()', 'Procedure.i V3dOwnershipRelease()'):
        require(v3d, needle)
    require(neon, 'r = V3dOwnershipClaim()')
    require(neon, 'r = V3dOwnershipRelease()')
    if v3d.index('r = V3dOwnershipReset()') > v3d.index('v3d_owner = 1'):
        raise GateError('claim no longer follows reset')
    release = v3d.index('Procedure.i V3dOwnershipRelease()')
    if v3d.index('r = V3dOwnershipReset()', release) > v3d.rindex('v3d_owner = 0'):
        raise GateError('release no longer follows reset')
    return 1


def compile_proof(compiler: Path) -> tuple[int, str]:
    if not compiler.is_file():
        raise GateError(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-v3d-owner-proof-") as name:
        image = Path(name) / "neon_v3d_ownership_proof.img"
        run = subprocess.run(
            [str(compiler), "--compile", SOURCE.relative_to(ROOT).as_posix(),
             "-t", "pi4", "--load-addr", "0x500000", "--stack-addr", "0x7F00000",
             "--entry-returns", "-o", str(image), "-s"],
            cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
        )
        if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
            raise GateError("ownership proof compile failed\n" + run.stdout)
        blob = image.read_bytes()
    return len(blob), hashlib.sha256(blob).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mutate', action='store_true')
    ap.add_argument('--compiler', type=Path,
                    default=Path(os.environ.get('PMF_COMPILER', DEFAULT_COMPILER)))
    args = ap.parse_args(argv)
    source, v3d, neon = SOURCE.read_text(), V3D.read_text(), NEON.read_text()
    if not args.mutate:
        checks = check(source, v3d, neon)
        size, digest = compile_proof(args.compiler)
        print(f'PASS: ownership proof source/layout ({checks} checks); compiled {size} bytes sha256 {digest}')
        return 0
    mutations = (
        ('drop second cycle', source.replace('nvpCycle(0) : nvpCycle(1)', 'nvpCycle(0)')),
        ('drop reset telemetry', source.replace('v3d_resetCt0csBefore', 'RESET_TELEMETRY_REMOVED')),
        ('drop primitive', source.replace('rBox = Neon_Box', 'rBox = Neon_NoBox')),
        ('drop report return', source.replace('ProcedureReturn @nvpReport[0]', 'ProcedureReturn 0')),
    )
    rejected = 0
    for label, mutated in mutations:
        try:
            check(mutated, v3d, neon)
        except GateError:
            rejected += 1
        else:
            raise GateError(f'mutation escaped: {label}')
    print(f'PASS: {rejected}/{len(mutations)} hostile proof mutations rejected')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
