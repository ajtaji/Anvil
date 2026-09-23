#!/usr/bin/env python3
"""Emitted fail-closed Pi 3 VC4/V3D power/IDENT gate."""
from __future__ import annotations
import argparse, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_gate_build
import truetype_slots_check as slots
ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3/Tests/v3d_probe_gate.pi3"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 2_000_000
DTB_ADDR = 0x06000000

def run_proc(cpu, pc, args, limit=LIMIT):
    cpu.pc = pc
    cpu.sp = STACK
    cpu.x[30] = slots.base.RETURN_PC
    for i, value in enumerate(args): cpu.x[i] = value
    steps = 0
    while steps < limit and cpu.pc != slots.base.RETURN_PC:
        cpu.step(); steps += 1
    if cpu.pc != slots.base.RETURN_PC:
        raise RuntimeError(f"procedure did not return; pc=0x{cpu.pc:x} after {steps} instructions")
    return cpu.x[0] & 0xFFFFFFFF, steps

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    ap.add_argument("--dtb", type=Path, default=ROOT / "_work/pi3-build35-font-boot-stage/bcm2710-rpi-3-b.dtb")
    args = ap.parse_args()
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file(): raise SystemExit("compiler does not exist")
    source_text = GATE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-v3d-") as tmp:
        tmp = Path(tmp); source = tmp / "v3d_probe_gate.pi3"; image = tmp / "v3d_probe_gate.img"
        source.write_text(source_text, encoding="utf-8")
        env = os.environ.copy(); env["PMF_ROOT"] = str(ROOT)
        def compile_fixture():
            result = subprocess.run([str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)], cwd=ROOT, env=env, capture_output=True, text=True)
            if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
                raise SystemExit("V3D gate compile failed\n" + result.stdout + result.stderr)
        pi3_gate_build.compile_counted(compile_fixture, source, image, compiler=compiler, by="tools/pi3_v3d_probe_check.py", root=ROOT)
        symbols = slots.base.parse_symbols(image)
        raw = image.read_bytes()
        cpu = slots.base.load_interp(slots.base.INTERP).A64()
        cpu.memory = {LOAD + i: b for i, b in enumerate(raw)}
        result, steps = run_proc(cpu, LOAD + symbols["main"], [])
        if result:
            raise SystemExit(f"synthetic Pi3 V3D gate assertion {result}; {steps:,} instructions")
        print(f"Pi3 V3D power/IDENT emitted gate PASS; synthetic DTB, revision matrix, no-MMIO failure paths; {steps:,} A64 instructions")
        dtb = args.dtb.read_bytes()
        if len(dtb) < 40 or len(dtb) > 0x100000: raise SystemExit(f"DTB size outside parser bounds: {len(dtb)}")
        cpu.memory.update({DTB_ADDR + i: b for i, b in enumerate(dtb)})
        parser = LOAD + symbols["pi3v3ddtbvalid"]
        valid, parser_steps = run_proc(cpu, parser, [DTB_ADDR, DTB_ADDR + len(dtb)])
        if valid != 1:
            stage_pair = next(((k, v) for k, v in symbols.items() if "dtb_stage" in k.lower()), None)
            stage_symbol = stage_pair[1] if stage_pair is not None else None
            stage_addr = stage_symbol if stage_symbol and stage_symbol >= LOAD else LOAD + stage_symbol if stage_symbol is not None else 0
            stage = cpu.memory.get(stage_addr, 0) if stage_symbol is not None else -1
            raise SystemExit(f"production DTB parser rejected Build35 staged DTB (result={valid}, stage={stage}, {parser_steps:,} instructions)")
        print(f"Build35 staged bcm2710-rpi-3-b.dtb accepted by emitted production parser: {len(dtb)} bytes, {parser_steps:,} instructions")
        mutated = bytearray(dtb)
        marker = bytes.fromhex("7e0000003f00000001000000")
        at = mutated.find(marker)
        if at < 0: raise SystemExit("cannot locate BCM2837 /soc ranges tuple in staged DTB")
        mutated[at + 4] = 0x3E
        cpu.memory.update({DTB_ADDR + i: b for i, b in enumerate(mutated)})
        refused, _ = run_proc(cpu, parser, [DTB_ADDR, DTB_ADDR + len(mutated)])
        if refused != 0: raise SystemExit("production parser accepted changed BCM2837 /soc ranges")
        print("Build35 DTB mutated /soc ranges rejected before firmware/GPU access")
    return 0
if __name__ == "__main__": raise SystemExit(main())
