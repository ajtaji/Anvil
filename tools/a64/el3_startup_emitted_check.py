#!/usr/bin/env python3
"""Normal unified-compiler FP startup contract; no monitor/board build.

Register effects only: the interpreter does not enforce FP trapping or MMU
permissions. This fixture reproduces the board's first-statement DTB capture,
not its complete boot composition or subsequent stack relocation.
"""
import argparse
import hashlib
import os
import pathlib
import subprocess
import tempfile
import el3_runtime_emitted_check as base
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

CPTR2, CPTR3 = 0xD51C1140, 0xD51E1140
DTB = 0x12345000
BSS = 0x07000000


def execute(a64, data, el):
    cpu = a64.A64()
    for i,b in enumerate(data):
        cpu.memory[base.LOAD+i] = b
    for i in range(4096):
        cpu.memory[BSS+i] = 0xA5
    cpu.enable_system_registers(el=el, preset={CPTR3:0,CPTR2:0x400})
    cpu.pc, cpu.sp, cpu.x[0] = base.LOAD, 0x02000000, DTB
    writes, masked = [], False
    for steps in range(base.STEP_LIMIT):
        word = cpu.fetch(cpu.pc)
        assert word != 0xD69F03E0, 'startup attempted ERET'
        if word == 0xD5034FDF:
            masked = True
        if word & ~31 in (CPTR2,CPTR3):
            writes.append(word & ~31)
        if base.u64(cpu,base.OUT+32) == 0x1234:
            assert base.u64(cpu,base.OUT) == DTB, 'firmware x0 clobbered'
            assert base.u64(cpu,base.OUT+8) == el << 2 and cpu.current_el == el, 'exception level changed'
            sp = base.u64(cpu,base.OUT+16)
            assert sp % 16 == 0 and base.STACK-4096 <= sp <= base.STACK, 'initial stack'
            assert base.u64(cpu,base.OUT+24) == 0, 'BSS not zeroed'
            assert base.u64(cpu,base.OUT+40) == 0x40700000, 'FP witness is not 3.75'
            assert cpu.sysreg(CPTR3) == 0 and writes == [CPTR2], 'FP trap bank writes'
            assert cpu.sysreg(CPTR2) == 0x33FF, 'CPTR_EL2 FP gate'
            assert masked, 'normal startup did not mask asynchronous exceptions'
            return steps
        cpu.step()
    raise AssertionError('startup fixture did not finish')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True)
    parser.add_argument('--interp',default=str(base.INTERP))
    args = parser.parse_args()
    compiler = pathlib.Path(resolve_compiler(args.compiler))
    a64 = base.load_interpreter(base.required_path(args.interp,'interp'))
    with tempfile.TemporaryDirectory(prefix='anvil-el3-startup-') as temp:
        image = pathlib.Path(temp)/'startup.img'
        env = os.environ.copy()
        env['PMF_ROOT'] = str(base.ROOT)
        run = subprocess.run([str(compiler),'--compile','RaspberryPi4/Tests/el3_startup_emitted_gate.pi4',
                              '-t','pi4','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),
                              '--bss-addr',hex(BSS),'-o',str(image),'-s'],cwd=base.ROOT,env=env,
                             text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        assert run.returncode == 0 and image.is_file(), run.stdout
        data = image.read_bytes()
        steps = sum(execute(a64,data,el) for el in (2,3))
        # Replace entry DSB with either MOVZ x0,#0 or ERET. Neither mutant
        # relies on an unsupported instruction to make its assertion fail.
        slot = data.find((0xD5033F9F).to_bytes(4,'little'))
        assert slot >= 0 and slot % 4 == 0
        for word,reason in ((0xD2800000,'firmware x0 clobbered'),(0xD69F03E0,'startup attempted ERET')):
            mutant = bytearray(data)
            mutant[slot:slot+4] = word.to_bytes(4,'little')
            for el in (2,3):
                try:
                    execute(a64,mutant,el)
                except AssertionError as error:
                    assert str(error) == reason, error
                else:
                    raise AssertionError('startup mutation survived')
    print(f'el3_startup_emitted_check: PASS EL2/EL3 normal FP startup, 4 mutation rejections, {steps} instructions')
    print('compiler SHA256:',hashlib.sha256(compiler.read_bytes()).hexdigest())
    print('Register/entry proof only; FP trap enforcement and silicon boot remain unproven.')


if __name__ == '__main__':
    main()
