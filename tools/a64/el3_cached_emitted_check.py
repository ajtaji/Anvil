#!/usr/bin/env python3
"""Desk-only emitted cached-MMU bank/ordering gate; no silicon cache model.

Executes the real library, observing architectural instruction encodings before
the interpreter models maintenance/barriers as no-ops. It does not prove cache
coherency, translation, privilege access or multicore operation on silicon.
"""
import argparse
import hashlib
import pathlib
import tempfile

import el3_runtime_emitted_check as base
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

SCTLR = {2: base.SCTLR_EL2, 3: base.SCTLR_EL3}
TLBI = {2: 0xD50C871F, 3: 0xD50E871F}
DSB, ISB, IC = 0xD5033F9F, 0xD5033FDF, 0xD508751F
ISW, CISW = 0xD5087640, 0xD5087E40
CLIDR, CCSIDR, CSSELR = 0xD5190020, 0xD5190000, 0xD51A0000
MCI = 0x1005


def clz32(value):
    return 32 - (value & 0xFFFFFFFF).bit_length()


def execute(a64, data, el, mode, warm):
    cpu = a64.A64()
    for offset, byte in enumerate(data):
        cpu.memory[base.LOAD + offset] = byte
    cpu.memory[base.OUT] = mode
    selected = base.STUB_SCTLR | (MCI if warm else 0)
    other = base.STUB_SCTLR | (0 if warm else MCI)
    cpu.enable_system_registers(el=el, preset={
        SCTLR[el]: selected, SCTLR[5-el]: other,
        CLIDR: (1 << 24) | 2, CCSIDR: (1 << 13) | (1 << 3) | 2,
    })
    cpu.pc, cpu.sp, cpu.x[30] = base.LOAD, base.STACK, base.RETURN_PC
    events = []
    gap = False
    for steps in range(base.STEP_LIMIT):
        if cpu.pc == base.RETURN_PC:
            break
        word = cpu.fetch(cpu.pc)
        key = word & ~31
        if word in (DSB, ISB, IC, *TLBI.values()):
            events.append((word, None))
        elif key in (ISW, CISW, CSSELR, *SCTLR.values(),
                     *base.TRANSLATION[2], *base.TRANSLATION[3]):
            events.append((key, cpu.x[word & 31]))
        # No load/store (not merely SP-relative) between cache-off and the
        # completing DSB after the inline set/way walk. Includes literal loads.
        if gap and (word & 0x0A000000) == 0x08000000:
            raise AssertionError("memory access in cache-off flush gap")
        if mode == 2 and key == SCTLR[el]:
            gap = True
        if gap and word == DSB and any(e[0] == CISW for e in events):
            gap = False
        # Interpreter lacks scalar CLZ W. Supply only that architectural
        # operation locally, with zero-extension; do not weaken its decoder.
        if word & 0xFFFFFC00 == 0x5AC01000:
            rn, rd = (word >> 5) & 31, word & 31
            value = (cpu.x[rn] if rn != 31 else 0) & 0xFFFFFFFF
            if rd != 31:
                cpu.x[rd] = clz32(value)
            cpu.pc += 4
        else:
            cpu.step()
    else:
        raise AssertionError("probe did not return")
    want = selected | MCI if mode == 0 else selected & ~MCI
    assert cpu.sysreg(SCTLR[el]) == want, "selected SCTLR value"
    assert cpu.sysreg(SCTLR[5-el]) == other, "other SCTLR bank changed"
    for bank, regs in base.TRANSLATION.items():
        want_regs = base.TRANSLATION_VALUES if mode == 0 and bank == el else (None,)*3
        assert tuple(cpu.sysreg(r) for r in regs) == want_regs, "translation bank"
    walk = [(DSB,None), (CSSELR,0), (ISB,None)]
    operands = [0x80000040, 0x40, 0x80000000, 0]
    tail = [(CSSELR,0), (DSB,None), (ISB,None)]
    if mode == 0:
        expected = [] if warm else walk + [(ISW,x) for x in operands] + tail
        expected += [(DSB,None),(TLBI[el],None),(DSB,None),(ISB,None)]
        expected += list(zip(base.TRANSLATION[el],base.TRANSLATION_VALUES))
        expected += [(DSB,None),(ISB,None),(IC,None),(DSB,None),(ISB,None),
                     (SCTLR[el],want),(ISB,None)]
    elif mode == 1:
        expected = [(DSB,None),(SCTLR[el],want),(ISB,None),(IC,None),
                    (TLBI[el],None),(DSB,None),(ISB,None)]
    else:
        expected = [(DSB,None),(SCTLR[el],want),(ISB,None)] + walk
        expected += [(CISW,x) for x in operands] + tail
        expected += [(IC,None),(TLBI[el],None),(DSB,None),(ISB,None)]
    # Unified compiler startup completes firmware memory work before BSS.
    expected = [(DSB,None),(ISB,None)] + expected
    assert events == expected, f"maintenance ordering: {events!r} != {expected!r}"
    return steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--interp', default=str(base.INTERP))
    args = parser.parse_args()
    assert [clz32(v) for v in (0,1,2,0x80000000,0xFFFFFFFF,0x100000000)] == [32,31,30,0,0,32]
    compiler = pathlib.Path(resolve_compiler(args.compiler))
    a64 = base.load_interpreter(base.required_path(args.interp, 'interp'))
    base.PROBE = base.ROOT / 'RaspberryPi4/Tests/el3_cached_emitted_gate.pi4'
    with tempfile.TemporaryDirectory(prefix='anvil-el3-cached-') as temp:
        data = base.build(compiler, pathlib.Path(temp)).read_bytes()
        cases = [(el,mode,warm) for el in (2,3) for mode in range(3) for warm in (False,True)]
        steps = sum(execute(a64,data,*case) for case in cases)
        # Each emitted mutation must trip our assertions, never merely fail
        # to decode. Exact ordering catches erased barriers and cache ops too.
        mutations = [(TLBI[2], TLBI[3]), (TLBI[3], TLBI[2]),
                     (SCTLR[2], SCTLR[3]), (SCTLR[3], SCTLR[2]),
                     (DSB,0xD503201F),(ISB,0xD503201F),
                     (ISW,0xD503201F),(CISW,0xD503201F),(IC,0xD503201F),
                     (CISW,0xF94003E0)]  # inject a stack load into the flush gap
        mutations += [(reg,base.TRANSLATION[5-el][i])
                      for el in (2,3) for i,reg in enumerate(base.TRANSLATION[el])]
        for old,new in mutations:
            mutant = bytearray(data)
            hits = 0
            first_barrier = True
            for offset in range(0,len(mutant)-3,4):
                word = int.from_bytes(mutant[offset:offset+4],'little')
                match = word == old if old in (DSB,ISB,IC,*TLBI.values()) else word & ~31 == old
                if match:
                    if old in (DSB, ISB) and first_barrier:
                        # Keep the startup barrier: prove library ordering,
                        # not merely that the common entry stub was changed.
                        first_barrier = False
                        continue
                    replacement = new if new == 0xD503201F or old in TLBI.values() else new | (word & 31)
                    mutant[offset:offset+4] = replacement.to_bytes(4,'little')
                    hits += 1
            assert hits, f"mutation not applied {old:#x}"
            rejected = False
            for case in cases:
                try:
                    execute(a64,mutant,*case)
                except AssertionError as error:
                    if new == 0xF94003E0:
                        assert str(error) == 'memory access in cache-off flush gap'
                    rejected = True
                    break
            assert rejected, f"mutation survived {old:#x}"
    print(f'el3_cached_emitted_check: PASS 12 cases, {len(mutations)} emitted mutations rejected, {steps} instructions')
    print('compiler SHA256:', hashlib.sha256(compiler.read_bytes()).hexdigest())
    print('Desk proof only: cache/TLB effects and barriers are not simulated.')
    print('CLZ W uses a local architectural adapter (6 boundary checks); no interpreter changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
