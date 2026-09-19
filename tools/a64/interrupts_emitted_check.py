#!/usr/bin/env python3
"""Execute the real primary GIC driver against a register-level model, not silicon."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_count

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('irq_a64', ROOT / 'tools/a64/a64_interp.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    d, c = 0xff841000, 0xff842000
    class Model(mod.A64):
        def __init__(self):
            super().__init__()
            self.writes = []
            self.irq_masks = []
            self.reject = None
        def step(self):
            word = self.load(self.pc,4)
            if word in (0xd50342ff,0xd50342df):
                self.irq_masks.append(word)
                key = 0xd51b4220
                old = self.system_registers.get(key,0)
                self.system_registers[key] = old & ~0x80 if word == 0xd50342ff else old | 0x80
            return super().step()
        def store(self, addr, value, size):
            if addr == 0x6000300:
                # Test-only device-state injection, never a production register.
                for offset, case in ((0x200, 1), (0x300, 2), (0x100, 3)):
                    mod.A64.store(self, d+offset, (1 << 20) if value == case else 0, 4)
            if d <= addr < c + 0x1000:
                self.writes.append((addr, value & ((1 << (size * 8)) - 1), size))
            if self.reject == (addr,value):
                return
            if d + 0x100 <= addr < d + 0x120:
                return super().store(addr, self.load(addr, size) | value, size)
            if d + 0x180 <= addr < d + 0x1a0:
                return super().store(addr - 0x80, self.load(addr - 0x80, size) & ~value, size)
            return super().store(addr, value, size)
    with tempfile.TemporaryDirectory(prefix='anvil-irq-') as td:
        image = Path(td) / 'irq.img'
        source = ROOT / 'RaspberryPi4/Tests/interrupts_emitted_gate.pi4'
        command = [args.compiler, '--compile', str(source), '-t', 'pi4', '--load-addr', '0x400000',
                   '--stack-addr', '0x3000000', '--entry-returns', '-o', str(image), '-s']
        result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True)
        if result.returncode or not image.exists():
            raise SystemExit(result.stdout + result.stderr)
        build_count.record_build(source, 'pi4', image, by='tools/a64/interrupts_emitted_check.py', compiler=args.compiler)
        count = 0
        for el in (2, 3):
            for raw in (29, 40, 255, 30, 7 | (2 << 10), 1020, 1021, 1022, 1023):
                cpu = Model()
                for i, byte in enumerate(image.read_bytes()): cpu.memory[0x400000 + i] = byte
                cpu.enable_system_registers(el=el, preset={0xd51cC000:0x8000, 0xd51eC000:0x8000,
                                                           0xd51b4220:0x3c0, 0xd51800a0:0})
                for addr, value in ((d+0xfe8,0x20),(d+8,0x43b),(c+0xfc,0x0202143b),(d+4,0x407),(d,3),(c,0x1e7),(c+4,255),
                                    (d+0x80,0xffffffff),(d+0x84,0xffffffff),(d+0x9c,0xffffffff),(c+0xc,raw)):
                    mod.A64.store(cpu, addr, value, 4)
                mod.A64.store(cpu,d+0x400+40,0xc0,1)
                mod.A64.store(cpu,d+0x800+40,8,1)
                cpu.pc, cpu.sp, cpu.x[30] = 0x400000, 0x3000000, 0xdead0000
                for _ in range(200000):
                    if cpu.pc == 0xdead0000: break
                    cpu.step()
                else: raise AssertionError('Execution did not return.')
                out = [cpu.load(0x6000000 + i*8,8) for i in range(5)]
                expected = [1,1,1,int(raw in (29,40,255) or (raw & 1023) >= 1020),1]
                assert out == expected, (el,raw,out,expected,cpu.writes[-12:])
                assert [cpu.load(0x6000200+i*8,8) for i in range(8)] == [1,0,0,0,1,1,0,0]
                assert [cpu.load(0x6000240+i*8,8) for i in range(6)] == [0]*6
                assert [cpu.load(0x6000040+i*8,8) for i in range(4)] == [0]*4
                assert [cpu.load(0x6000060+i*8,8) for i in range(2)] == [1,1]
                assert cpu.irq_masks == [0xd50342ff,0xd50342df]
                assert [cpu.load(0x6000070+i*8,8) for i in range(2)] == [1,1]
                assert [cpu.load(0x6000080+i*8,8) for i in range(2)] == [1,1]
                assert cpu.load(0x6000100,8) == int(raw in (29,40,255))
                assert cpu.load(d+0x400+40,1) == 0xc0 and cpu.load(d+0x800+40,1) == 8
                eois = [v for a,v,s in cpu.writes if a == c+0x10]
                assert eois == ([] if (raw & 1023) >= 1020 else [raw]), (raw,eois)
                if raw == 30:
                    mask = next(i for i,w in enumerate(cpu.writes) if w[0] == d+0x180 and w[1] == 1<<30)
                    eoi = next(i for i,w in enumerate(cpu.writes) if w[0] == c+0x10)
                    assert mask < eoi
                assert cpu.load(d,4)==3 and cpu.load(c,4)==0x1e7 and cpu.load(c+4,4)==255
                assert (d,3 if el == 3 else 1,4) in cpu.writes
                assert (c,0x1e7 if el == 3 else 1,4) in cpu.writes
                count += 1
        print(f'PASS: {count} emitted EL2/EL3 claim, dispatch, reserved-ID and restoration cases (register model only).')
        for el in (2,3):
            for defect in ('core','daif','vbar','typer','pidr','iidr') + (('security',) if el == 3 else ()):
                cpu = Model()
                for i, byte in enumerate(image.read_bytes()): cpu.memory[0x400000+i] = byte
                cpu.enable_system_registers(el=el, preset={0xd51cc000:0x8000,0xd51ec000:0x8000,
                                                           0xd51b4220:0x3c0,0xd51800a0:0})
                for addr,value in ((d+0xfe8,0x20),(d+8,0x43b),(c+0xfc,0x0202143b),(d+4,0x407)):
                    mod.A64.store(cpu,addr,value,4)
                if defect == 'core': cpu.system_registers[0xd51800a0] = 1
                if defect == 'daif': cpu.system_registers[0xd51b4220] = 0
                if defect == 'vbar': cpu.system_registers[0xd51cc000 if el==2 else 0xd51ec000] = 0x9000
                if defect == 'typer': mod.A64.store(cpu,d+4,0x408,4)
                if defect == 'pidr': mod.A64.store(cpu,d+0xfe8,0,4)
                if defect == 'iidr': mod.A64.store(cpu,d+8,0,4)
                if defect == 'security': mod.A64.store(cpu,d+4,7,4)
                cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0xdead0000
                for _ in range(200000):
                    if cpu.pc==0xdead0000: break
                    cpu.step()
                else: raise AssertionError('Refusal did not return.')
                assert [cpu.load(0x6000000+i*8,8) for i in range(5)] == [0]*5, (el,defect)
                assert not cpu.writes, (el,defect,cpu.writes)
                assert not cpu.irq_masks, (el,defect,cpu.irq_masks)
        print('PASS: 13 bad-context/identity refusals perform zero MMIO writes.')
        for el in (2,3):
            for defect in ('dist','cpu','pmr','priority','target','active','enabled'):
                cpu = Model()
                for i,byte in enumerate(image.read_bytes()): cpu.memory[0x400000+i]=byte
                cpu.enable_system_registers(el=el,preset={0xd51cc000:0x8000,0xd51ec000:0x8000,
                                                          0xd51b4220:0x3c0,0xd51800a0:0})
                for addr,value in ((d+0xfe8,0x20),(d+8,0x43b),(c+0xfc,0x0202143b),(d+4,0x407),
                                   (d,0),(c,0),(c+4,0xff),(d+0x80,0xffffffff),(d+0x84,0xffffffff),(c+0xc,1023)):
                    mod.A64.store(cpu,addr,value,4)
                mod.A64.store(cpu,d+0x400+40,0xc0,1)
                mod.A64.store(cpu,d+0x800+40,8,1)
                rejects={'dist':(d,3 if el==3 else 1),'cpu':(c,0x1e7 if el==3 else 1),
                         'pmr':(c+4,0xf0),'priority':(d+0x400+40,0xa0),'target':(d+0x800+40,1)}
                cpu.reject=rejects.get(defect)
                if defect=='active': mod.A64.store(cpu,d+0x304,1<<8,4)
                if defect=='enabled': mod.A64.store(cpu,d+0x104,1<<8,4)
                cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0xdead0000
                for _ in range(200000):
                    if cpu.pc==0xdead0000: break
                    cpu.step()
                else: raise AssertionError('Rollback did not return.')
                assert cpu.load(0x6000070,8)==0 and cpu.load(0x6000078,8)==0, (el,defect)
                assert cpu.load(d,4)==0 and cpu.load(c,4)==0 and cpu.load(c+4,4)==255, (el,defect)
                assert cpu.load(d+0x400+40,1)==0xc0 and cpu.load(d+0x800+40,1)==8, (el,defect)
                if defect in ('dist','cpu','pmr'):
                    assert cpu.load(0x6000000,8)==0 and not cpu.irq_masks
                if defect in ('active','enabled'):
                    assert not [w for w in cpu.writes if w[0] in (d+0x400+40,d+0x800+40)]
        print('PASS: 14 failed-readback rollback and foreign active/enabled ownership cases.')
if __name__ == '__main__': main()
