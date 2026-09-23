#!/usr/bin/env python3
"""Execute real registration domain with deterministic reference services, not a DB."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
LOAD, STACK, RETURN, OUT = 0x400000, 0x3000000, 0x7000000, 0x6000000


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', required=True)
    args = p.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    spec = importlib.util.spec_from_file_location('reg_a64', ROOT/'tools/a64/a64_interp.py')
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix='forum-registration-') as tmp:
        image = Path(tmp)/'registration.img'
        r = subprocess.run([args.compiler, '--compile',
                            'Anvil/Applications/Forum/Tests/registration_native_gate.pi4',
                            '-t','pi4','--entry-returns','--load-addr',hex(LOAD),
                            '--stack-addr',hex(STACK),'-o',str(image),'-s'],
                           cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                           capture_output=True,text=True)
        assert r.returncode == 0 and image.exists(), r.stdout+r.stderr
        cpu = mod.A64(); cpu.enable_system_registers(el=3)
        cpu.memory.update({LOAD+i:b for i,b in enumerate(image.read_bytes())})
        cpu.pc=LOAD; cpu.sp=STACK; cpu.x[30]=RETURN
        for steps in range(100000):
            if cpu.pc==RETURN: break
            cpu.step()
        else: raise AssertionError('Registration fixture did not return')
        observed = [cpu.load(OUT+i*8,8) for i in range(14)]
        expected = [3,0,1,0,1,3,0,2,1,3,1,1,3,0]
        assert cpu.x[0]==0 and observed==expected, (cpu.x[0],observed,expected)
        print(f'forum_registration_check: PASS 14 native state witnesses, {steps} instructions; no account before proof, bad proof, once-only commit, replay, exact expiry. Reference services only.')


if __name__=='__main__':
    if not __debug__: raise SystemExit('Assertions must be enabled')
    main()
