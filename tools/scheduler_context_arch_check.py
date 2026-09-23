"""Independent IRQ-entry/ERET state tests, not scheduler progress simulation.

Fixed ERET/DAIF/SPSel encodings are architectural test vectors, not injected
production assembly. Arm102412 sections5/6 are cited by A64.take_irq.
"""
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
spec=importlib.util.spec_from_file_location('irq_arch',ROOT/'tools/a64/a64_interp.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def instruction(c,word):
    c.store(c.pc,word,4);c.step()
def cpu(el=3):
    c=m.A64();c.enable_system_registers(el,{0xd51ec000:0x8000,0xd51cc000:0xa000,0xd518c000:0xc000,0xd51b4220:0})
    c.pc=0x4000;c.sp=0x10000
    c.n,c.z,c.c,c.vflag=1,0,1,1
    return c
def main():
    checks=0
    c=cpu();old=c.pstate()
    assert c.take_irq() and c.pc==0x8280;checks+=1
    assert c.system_registers[0xd51e4020]==0x4000 and c.system_registers[0xd51e4000]==old;checks+=1
    assert not c.take_irq() and c.pc==0x8280;checks+=1
    c.n,c.z,c.c,c.vflag=0,1,0,0
    instruction(c,0xd69f03e0)
    assert (c.pc,c.pstate(),c.sp)==(0x4000,old,0x10000);checks+=1
    # Same EL using SP_EL0 selects vector group0 and switches to SP_EL3.
    instruction(c,0xd50040bf);c.sp=0x20000;old=c.pstate();oldpc=c.pc
    assert c.take_irq() and (c.pc,c.sp)==(0x8080,0x10000);checks+=1
    instruction(c,0xd69f03e0)
    assert (c.pc,c.sp,c.pstate())==(oldpc,0x20000,old);checks+=1
    # Higher routed EL ignores lower-EL I mask, using lower-A64 vector group.
    c=cpu(1);c.system_registers[0xd51b4220]=0x3c0;c.stack_banks[3]=0x30000
    old=c.pstate();assert c.take_irq(3) and (c.pc,c.sp)==(0x8480,0x30000);checks+=1
    instruction(c,0xd69f03e0)
    assert (c.current_el,c.sp,c.pstate())==(1,0x10000,old);checks+=1
    # Explicitly unmasked nested entry overwrites architectural bank, not a
    # fictional hidden saved state. Software owns preservation before nesting.
    c=cpu();assert c.take_irq();first=c.system_registers[0xd51e4020]
    instruction(c,0xd50342ff);nestedpc=c.pc
    assert c.take_irq() and c.system_registers[0xd51e4020]==nestedpc!=first;checks+=1
    for mode in (1,2,3,6,7,10,11,14,15,16,31):
        c=cpu();c.system_registers[0xd51e4000]=mode;c.system_registers[0xd51e4020]=0x4000
        try:instruction(c,0xd69f03e0)
        except RuntimeError:checks+=1
        else:raise AssertionError(('invalid mode accepted',mode))
    c=cpu(1);c.system_registers[0xd5184000]=13;c.system_registers[0xd5184020]=0x4000
    try:instruction(c,0xd69f03e0)
    except RuntimeError:checks+=1
    else:raise AssertionError('Privilege-increasing return accepted.')
    c=cpu();c.system_registers[0xd51ec000]=0x8001
    try:c.take_irq()
    except RuntimeError:checks+=1
    else:raise AssertionError('Unaligned vector accepted.')
    c=cpu();c.v[0]=0x7fc00000;c.v[1]=0x3f800000
    instruction(c,0x1e212000) # FCMP S0,S1: unordered sets C and V.
    assert (c.n,c.z,c.c,c.vflag)==(0,0,1,1) and c.cond(6);checks+=1
    c.v[0]=0x3f800000
    instruction(c,0x1e212000)
    assert (c.n,c.z,c.c,c.vflag)==(0,1,1,0) and not c.cond(6);checks+=1
    print(f'PASS: {checks} IRQ-entry/ERET architectural state checks.')
if __name__=='__main__':main()
