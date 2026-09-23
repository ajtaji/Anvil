#!/usr/bin/env python3
"""Execute portable scheduler lifecycle code; no task/context-switch claim."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import build_count

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('scheduler_a64', ROOT/'tools/a64/a64_interp.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='anvil-scheduler-') as folder:
        image = Path(folder)/'lifecycle.img'
        source = ROOT/'Anvil/Kernel/Scheduler/Tests/lifecycle.pi4'
        result = subprocess.run([args.compiler,'--compile',str(source),'-t','pi4',
                                 '--load-addr','0x400000','--stack-addr','0x3000000',
                                 '--entry-returns','-o',str(image)],cwd=ROOT,
                                env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        if result.returncode or not image.is_file():
            raise SystemExit(result.stdout+result.stderr)
        build_count.record_build(source,'pi4',image,by='tools/scheduler_lifecycle_check.py',compiler=args.compiler)
        cpu = module.A64()
        for offset,byte in enumerate(image.read_bytes()): cpu.memory[0x400000+offset]=byte
        cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0xdead0000
        for step in range(2000000):
            if cpu.pc==0xdead0000: break
            cpu.step()
        else: raise AssertionError('Scheduler lifecycle fixture did not return.')
        checks,failures=cpu.load(0x6000000,8),cpu.load(0x6000008,8)
        assert checks==175 and failures==0,(checks,failures)
        print(f'PASS: {checks} emitted lifecycle assertions; {step} instructions. No context switch/hardware proof.')
if __name__=='__main__': main()
