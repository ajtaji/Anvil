#!/usr/bin/env python3
"""Compile real banner formatter and prove measured CurrentEL in its ASCII text.

EL0/EL1 are synthetic interpreter inputs, not claims that privileged CurrentEL
reads or the monitor can run at those levels on silicon. No board is accessed.
"""
import argparse
import hashlib
import pathlib
import tempfile
import el3_runtime_emitted_check as base


def execute(a64, data, el):
    cpu = a64.A64()
    for offset, byte in enumerate(data):
        cpu.memory[base.LOAD + offset] = byte
    cpu.enable_system_registers(el=el)
    cpu.pc, cpu.sp, cpu.x[30] = base.LOAD, base.STACK, base.RETURN_PC
    for _ in range(base.STEP_LIMIT):
        if cpu.pc == base.RETURN_PC:
            address = base.u64(cpu, base.OUT)
            result = bytearray()
            for offset in range(96):
                value = cpu.memory.get(address + offset, 0)
                if not value:
                    break
                result.append(value)
            else:
                raise AssertionError('banner lacks bounded terminator')
            expected = f'bare-metal monitor   -   Raspberry Pi 4   -   BCM2711   -   AArch64 at EL{el}'
            assert result.decode('ascii') == expected, (result, expected)
            return
        cpu.step()
    raise AssertionError('banner probe failed to return')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--interp', default=str(base.INTERP))
    args = parser.parse_args()
    compiler = base.required_path(args.compiler, 'compiler')
    a64 = base.load_interpreter(base.required_path(args.interp, 'interp'))
    base.PROBE = base.ROOT / 'RaspberryPi4/Tests/banner_el_emitted_gate.pi4'
    with tempfile.TemporaryDirectory(prefix='anvil-banner-el-') as temp:
        data = base.build(compiler, pathlib.Path(temp)).read_bytes()
        for el in range(4):
            execute(a64, data, el)
        mutant = bytearray(data)
        hits = 0
        for offset in range(0,len(data)-3,4):
            word = int.from_bytes(data[offset:offset+4], 'little')
            if word & ~31 == 0xD5384240:  # MRS CurrentEL
                # MOVZ Xt,#8: hardcode EL2's encoded CurrentEL value.
                mutant[offset:offset+4] = (0xD2800100 | (word & 31)).to_bytes(4,'little')
                hits += 1
        assert hits, 'CurrentEL mutation did not apply'
        execute(a64, mutant, 2)
        for el in (0,1,3):
            try:
                execute(a64, mutant, el)
            except AssertionError:
                pass
            else:
                raise AssertionError(f'fixed EL2 mutation survived at EL{el}')
    print('banner_el_emitted_check: PASS all 4 EL text values; fixed-EL2 mutant rejected at EL0/1/3')
    print('compiler SHA256:', hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
