#!/usr/bin/env python3
"""Emitted primary EL2/EL3 vectors. Callback clobber/fault injection is modeled.
No interrupt controller or hardware exception delivery is simulated.
"""
import argparse
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LOAD = 0x400000
RETURN = 0x7000000
CALLBACK = 0x7100000
FPCR = 0xD51B4400
FPSR = 0xD51B4420
BANK = {2: (0xD51CC000, 0xD51C4020, 0xD51C4000, 0xD51C5200, 0xD51C6000),
        3: (0xD51EC000, 0xD51E4020, 0xD51E4000, 0xD51E5200, 0xD51E6000)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', required=True)
    p.add_argument('--mutant', choices=('simd', 'return', 'nested'), help=argparse.SUPPRESS)
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('exception_a64', ROOT / 'tools/a64/a64_interp.py')
    a64 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64
    spec.loader.exec_module(a64)
    with tempfile.TemporaryDirectory(prefix='anvil-exceptions-') as tmp:
        img = Path(tmp) / 'gate.img'
        env = dict(os.environ, PMF_ROOT=str(ROOT))
        r = subprocess.run([args.compiler, '--compile', 'RaspberryPi4/Tests/exceptions_gate.pi4',
                            '-t', 'pi4', '--load-addr', hex(LOAD), '--stack-addr', '0x3000000',
                            '--entry-returns', '-o', str(img), '-s'], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0 and img.exists(), r.stdout + r.stderr
        binary = img.read_bytes()
        if args.mutant:
            changed = bytearray(binary)
            hits = 0
            for i in range(0, len(binary)-3, 4):
                word = int.from_bytes(binary[i:i+4], 'little')
                match = ((args.mutant == 'simd' and word == 0x3DC05120) or
                         (args.mutant == 'return' and word == 0xD69F03E0) or
                         (args.mutant == 'nested' and word & 0xFF00001F == 0xB5000009))
                if match:
                    changed[i:i+4] = (0xD503201F).to_bytes(4, 'little')
                    hits += 1
            assert hits, 'Mutation did not match emitted bytes'
            binary = bytes(changed)
        symbols = dict(line.split('=', 1) for line in img.with_suffix('.img.sym').read_text().splitlines() if '=' in line)
        def addr(name):
            value = int(symbols[name], 0)
            return value if name.startswith('global_') else LOAD + value
        def put(cpu, at, value):
            for i in range(8): cpu.memory[at+i] = (value >> (i*8)) & 255
        def get(cpu, at):
            return sum(cpu.memory.get(at+i, 0) << (i*8) for i in range(8))
        def fresh(el, core=0):
            cpu = a64.A64()
            cpu.memory.update({LOAD+i: b for i, b in enumerate(binary)})
            cpu.enable_system_registers(el=el, preset={0xD51800A0: core})
            cpu.sp = 0x3000000
            return cpu
        def run_to(cpu, stop):
            for _ in range(10000):
                if cpu.pc == stop: return
                assert cpu.pc != CALLBACK, 'Unexpected callback instead of exception return'
                cpu.step()
            raise AssertionError(f'Never reached {stop:x}; at {cpu.pc:x}')
        for el in (2, 3):
            cpu = fresh(el)
            cptr = {2: 0xD51C1140, 3: 0xD51E1140}
            cpu.system_registers.update({cptr[2]: 0xBEEF37FF, cptr[3]: 0xCAFE57FF})
            original = dict(cpu.system_registers)
            cpu.pc = addr('exceptioninstall'); cpu.x[30] = RETURN
            run_to(cpu, RETURN)
            assert cpu.x[0] == el, ('install result', cpu.x[0])
            assert cpu.sysreg(BANK[el][0]) == addr(f'exception_vectors_{el}')
            assert cpu.sysreg(cptr[el]) == original[cptr[el]] & ~1024
            assert cpu.sysreg(cptr[5-el]) == original[cptr[5-el]]
            cpu.system_registers[BANK[el][0]] = 0x12340000
            cpu.system_registers[cptr[el]] |= 1024
            put(cpu, addr('global_exception_error'), 1)
            cpu.pc = addr('exceptioninstall'); cpu.x[30] = RETURN
            run_to(cpu, RETURN)
            assert cpu.sysreg(BANK[el][0]) == addr(f'exception_vectors_{el}')
            assert cpu.sysreg(cptr[el]) == original[cptr[el]] & ~1024
            assert get(cpu, addr('global_exception_error')) == 0
            assert addr(f'exception_vectors_{el}') % 2048 == 0
            # Inject a second exception during bulk capture, before any callback.
            mid = fresh(el)
            mid.pc = addr(f'exception_vectors_{el}') + 4*128
            run_to(mid, addr(f'exception_capture_{el}') + 16)
            base = (addr('global_exception_frame')+15)&~15
            partial = bytes(mid.memory.get(base+i, 0) for i in range(832))
            assert get(mid, addr('global_exception_active')) == 1
            mid.pc = addr(f'exception_vectors_{el}') + 4*128
            run_to(mid, addr(f'exception_park_{el}'))
            assert bytes(mid.memory.get(base+i, 0) for i in range(832)) == partial
            for core in (1, 2, 3):
                c = fresh(el, core); c.pc = addr('exceptioninstall'); c.x[30] = RETURN
                run_to(c, RETURN)
                assert c.x[0] == 0 and c.sysreg(BANK[el][0]) is None
            for slot in range(16):
                cpu = fresh(el)
                regs = [0x1111222200000000+i for i in range(31)]
                vectors = [0x123456789abcdef00123456789abc000+i for i in range(32)]
                cpu.x[:] = regs; cpu.v[:] = vectors
                cpu.system_registers.update({BANK[el][1]: RETURN, BANK[el][2]: (el<<2)|1|0xA00003C0,
                                             BANK[el][3]: 0x96000021, BANK[el][4]: 0x1234,
                                             FPCR: 0x400000, FPSR: 0x11})
                put(cpu, addr('global_exception_irq_handler'), CALLBACK)
                put(cpu, addr('global_exception_reporter'), CALLBACK)
                cpu.pc = addr(f'exception_vectors_{el}') + slot*128
                run_to(cpu, CALLBACK)
                frame = (addr('global_exception_frame')+15)&~15
                assert get(cpu, frame+256) == slot
                assert [get(cpu, frame+i*8) for i in range(31)] == regs
                assert get(cpu, frame+248) == 0x3000000
                assert get(cpu, frame+264) == 0x96000021 and get(cpu, frame+272) == 0x1234
                assert get(cpu, frame+280) == RETURN
                assert cpu.sp % 16 == 0
                if slot == 5:
                    declined = copy.deepcopy(cpu)
                    declined.pc = declined.x[30]; declined.x[0] = 0
                    run_to(declined, CALLBACK)
                    assert not declined.erets
                    resume = cpu.x[30]
                    cpu.x[:] = [0xBAD+i for i in range(31)]
                    cpu.v[:] = [0xBAD+i for i in range(32)]
                    cpu.system_registers[FPCR] = 0; cpu.system_registers[FPSR] = 0
                    cpu.x[0] = 1; cpu.pc = resume
                    run_to(cpu, RETURN)
                    assert cpu.x == regs and cpu.v == vectors
                    assert cpu.sp == 0x3000000 and cpu.sysreg(FPCR) == 0x400000 and cpu.sysreg(FPSR) == 0x11
                    assert cpu.sysreg(BANK[el][2]) == (el<<2)|1|0xA00003C0
                    assert get(cpu, addr('global_exception_active')) == 0
                else:
                    saved = bytes(cpu.memory.get(frame+i, 0) for i in range(832))
                    cpu.pc = addr(f'exception_vectors_{el}') + 4*128
                    run_to(cpu, addr(f'exception_park_{el}'))
                    assert bytes(cpu.memory.get(frame+i, 0) for i in range(832)) == saved
                    assert not cpu.erets
        print('exceptions_check: PASS - EL2/EL3 install, six secondary refusals, 32 slots, full IRQ context, nested first-record preservation')
    if args.self_test:
        for mutation in ('simd', 'return', 'nested'):
            result = subprocess.run([sys.executable, __file__, '--compiler', args.compiler,
                                     '--mutant', mutation], capture_output=True, text=True)
            assert result.returncode != 0 and 'AssertionError' in result.stderr, result.stdout + result.stderr
            assert 'Mutation did not match' not in result.stderr, result.stderr
        print('exceptions_check: PASS - three emitted-byte negative controls rejected')


if __name__ == '__main__':
    main()
