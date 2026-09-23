#!/usr/bin/env python3
"""Execute raw fault report with modeled PL011 FIFO; console mirror is stubbed."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LOAD = 0x400000
RETURN = 0x7000000
EXPECTED = (b'ANVIL FATAL EL=0000000000000003 SLOT=0000000000000004 '
            b'ESR=0000000096000021 PC=FEDCBA9876543210 FAR=123456789ABCDEF0\r\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', required=True)
    args = p.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    spec = importlib.util.spec_from_file_location('report_a64', ROOT/'tools/a64/a64_interp.py')
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    source = (ROOT/'RaspberryPi4/Board/exception_support.pi4').read_text()
    # Redirect only high-level console mirrors. Raw byte/text/hex code is unchanged.
    source = re.sub(r'\bPrintN\(', 'GatePrintN(', source)
    source = re.sub(r'\bPrint\(', 'GatePrint(', source)
    fixture = (ROOT/'RaspberryPi4/Tests/exception_report_gate.pi4').read_text()
    with tempfile.TemporaryDirectory(prefix='anvil-fault-report-') as tmp:
        tmp = Path(tmp); probe = tmp/'gate.pi4'; img = tmp/'gate.img'
        probe.write_text(fixture.replace('; @SUPPORT@', source))
        r = subprocess.run([args.compiler, '--compile', str(probe), '-t', 'pi4',
                            '--load-addr', hex(LOAD), '--stack-addr', '0x3000000',
                            '--entry-returns', '-o', str(img), '-s'], cwd=ROOT,
                           env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True)
        assert r.returncode == 0 and img.exists(), r.stdout+r.stderr
        data = img.read_bytes()
        labels = dict(line.split('=',1) for line in img.with_suffix('.img.sym').read_text().splitlines() if '=' in line)
        def execute(mode, entry='_start', arg=0):
            cpu = mod.A64(); cpu.memory.update({LOAD+i:b for i,b in enumerate(data)})
            cpu.memory.update({0x7200000+i: 65 for i in range(300)})
            cpu.enable_system_registers(el=3)
            cpu.pc = LOAD+int(labels[entry]); cpu.sp = 0x3000000; cpu.x[30] = RETURN; cpu.x[0] = arg
            output = bytearray(); polls = 0
            old_load, old_store = cpu.load, cpu.store
            def load(at, size):
                nonlocal polls
                if at == 0xFE201018:
                    assert size == 4
                    polls += 1
                    return 0x20 if mode == 'stuck' or (mode == 'delayed' and polls <= 3) else 0
                return old_load(at,size)
            def store(at, value, size):
                if at == 0xFE201000:
                    assert size == 4; output.append(value & 255); return
                old_store(at,value,size)
            cpu.load, cpu.store = load, store
            for steps in range(30000000):
                if cpu.pc == RETURN: return bytes(output), polls, cpu.x[0]
                cpu.step()
            raise AssertionError('Raw report did not finish its bounded FIFO loop')
        for mode in ('ready', 'delayed'):
            out,polls,mirrors = execute(mode)
            assert out == EXPECTED, (mode,out)
            assert polls == len(EXPECTED)+(3 if mode == 'delayed' else 0)
            assert mirrors == 16, mirrors
        out,polls,_ = execute('stuck', 'hwexceptionbyte', 65)
        assert out == b'' and polls == 4096, (out,polls)
        out,polls,_ = execute('ready', 'hwexceptiontext', 0x7200000)
        assert out == b'A'*192 and polls == 192
        print('exception_report_check: PASS - exact 64-bit EL/slot/ESR/PC/FAR report, delayed FIFO, 4096-poll stuck-byte bound, explicit console-mirror stubs')


if __name__ == '__main__': main()
