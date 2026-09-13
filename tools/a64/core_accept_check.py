#!/usr/bin/env python3
"""Resident acceptance emitted gate. Interleaved PEs, not a cache model."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import shutil
import a64_core_worker_check as base

ROOT = base.ROOT
FIXTURE = ROOT / 'RaspberryPi4/Tests/core_accept_emitted_gate.pi4'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--compiler', required=True)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='core-accept-') as tmp:
        image, asm = base.build(args.compiler, Path(tmp), FIXTURE, 'accept')
        sym = base.parse_symbols(image)
        a64 = base.load_interp(base.INTERP)
        checks = base.Checks()
        # Compile the former monolithic default and the wrapper form with
        # identical options. Source/debug line movement must not change code.
        default_image, _ = base.build(args.compiler, Path(tmp)/'default')
        oldroot = Path(tmp)/'oldroot'
        for rel in ('RaspberryPi4/Board/memmap.pi4', 'RaspberryPi4/Lib/mmu.pi4',
                    'RaspberryPi4/Lib/mmu_secondary.pi4',
                    'RaspberryPi4/Tests/core_worker_emitted_gate.pi4',
                    'keywords.def'):
            dst = oldroot/rel
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/rel,dst)
        shutil.copytree(ROOT/'Boards',oldroot/'Boards')
        shutil.copytree(ROOT/'RaspberryPi4/Intrinsics',oldroot/'RaspberryPi4/Intrinsics')
        source = base.CORE.read_text(encoding='utf-8')
        hook = ('  EndASM\n  CompilerIf #CORE_RAW_RESIDENT_JOBS = 1\n'
                '    ASM\n      b coreAcceptSecondaryEntry\n    EndASM\n'
                '  CompilerEndIf\n  ASM\n')
        checks.yes(source.count(hook)==1,'one optional READY hook')
        (oldroot/'RaspberryPi4/Lib/core_worker.pi4').write_text(source.replace(hook,''),encoding='utf-8')
        old_image,_ = base.build(args.compiler,oldroot/'out',
            oldroot/'RaspberryPi4/Tests/core_worker_emitted_gate.pi4',source_root=oldroot)
        checks.yes(old_image.read_bytes()==default_image.read_bytes(),'default byte-equivalent to old implementation')
        # Owner mix is a compile-time refusal, not a silent second raw owner.
        for label, includes in [('mixed', ['core_worker.pi4','core_accept.pi4']),
                                ('unowned', ['core_worker_impl.pi4'])]:
            for lib in ('core_worker.pi4','core_worker_impl.pi4','core_accept.pi4','acceptance_lease.pi4'):
                shutil.copy2(ROOT/'RaspberryPi4/Lib'/lib,oldroot/'RaspberryPi4/Lib'/lib)
            f = oldroot/'RaspberryPi4/Tests/core_worker_emitted_gate.pi4'
            original = base.FIXTURE.read_text(encoding='utf-8')
            original = original.replace('XIncludeFile "RaspberryPi4/Lib/core_worker.pi4"',
                '\n'.join('XIncludeFile "RaspberryPi4/Lib/'+lib+'"' for lib in includes))
            f.write_text(original,encoding='utf-8')
            try:
                base.build(args.compiler,oldroot/label,f,source_root=oldroot)
            except AssertionError as e:
                checks.yes('CORE_RAW_RESIDENT_JOBS'.lower() in str(e).lower(),label+' named ownership refusal')
            else:
                raise AssertionError(label+' unexpectedly compiled')
        blob = image.read_bytes()
        def machine(el=3, smpen=64, mci=base.SCTLR_CACHED, daif=0x3C0, affinity=0):
            mem = {base.LOAD+i: b for i,b in enumerate(blob)}
            cpus = {}
            def cpu(core, cold=False):
                c = a64.A64()
                c.memory = mem
                c.enable_system_registers(el=el, preset={
                    base.MPIDR_EL1_KEY: core | affinity,
                    base.SCTLR_EL3_KEY: 0 if cold else mci,
                    base.CPUECTLR_EL1_KEY: smpen,
                    base.CCSIDR_EL1_KEY: base.A72_L1D_CCSIDR,
                    0xD51E2000: 0x900000, 0xD51E2040: 0x80803520,
                    0xD51EA200: 0xFF440400, 0xD51BE000: 54000000,
                    0xD51B4220: daif})
                c.sp = base.STACK
                old_store = c.store
                def bounded_store(address, value, size):
                    if core:
                        raw = (sym['global_core_raw_row']+255)&-256
                        jobs = (sym['global_core_accept_rows']+255)&-256
                        spans = [(raw+core*256,raw+(core+1)*256),
                                 (jobs+core*256,jobs+(core+1)*256),
                                 (0x1FC000+(core-1)*4096,0x1FC000+core*4096)]
                    else:
                        spans = [(sym['__bss_start__'],sym['__bss_end__']),
                                 (base.STACK-65536,base.STACK), (0xE0,0xF8)]
                    if not any(lo <= address and address+size <= hi for lo,hi in spans):
                        raise AssertionError(f'core {core} escaped owned writes: {address:#x}+{size}')
                    old_store(address,value,size)
                c.store = bounded_store
                return c
            primary = cpu(0)
            def call(name, run_workers=True, maximum=5000000, arguments=()):
                primary.pc = base.LOAD + sym[name.lower()]
                primary.x[30] = base.RETURN_PC
                for index,value in enumerate(arguments): primary.x[index] = value
                for step in range(maximum):
                    if primary.pc == base.RETURN_PC:
                        checks.yes(primary.sp == base.STACK, name+' stack balance')
                        return primary.x[0]
                    primary.step()
                    if run_workers:
                        for core in (1,2,3):
                            entry = base.u64(mem, 0xD8+core*8)
                            if entry and core not in cpus:
                                cpus[core] = cpu(core, True)
                                cpus[core].pc = entry
                            if core in cpus:
                                cpus[core].step()
                raise AssertionError('primary instruction ceiling: '+name)
            return mem,cpus,primary,call

        mem,cpus,primary,call = machine()
        checks.yes(call('CoreAcceptRun') == 1, 'first run')
        checks.yes(call('CoreAcceptRun') == 1, 'second run')
        checks.yes(base.u64(mem,sym['global_core_accept_runs']) == 2, 'two runs')
        checks.yes(base.u64(mem,sym['global_core_accept_nonce']) == 32, 'fresh nonce each round')
        checks.yes(set(cpus) == {1,2,3}, 'all three PEs entered emitted bootstrap')
        checks.yes(call('CoreAcceptStop') == 1, 'acknowledged stop')
        checks.yes(call('CoreAcceptRun') == 0, 'no run after stop')
        checks.yes(call('AcceptLeaseRelease',arguments=(1,3)) == 0,'stopped cores retain leases')
        for core,cpu in cpus.items():
            checks.yes(cpu.sp == 0x1FC000+(core)*0x1000, 'reserved stack')
            for _ in range(8): cpu.step()
            checks.yes(cpu.pc in (base.LOAD+sym['coreacceptsecondarypark'],
                                 base.LOAD+sym['coreacceptsecondarypark']+4), 'permanent park')

        mem,cpus,_,call = machine()
        checks.yes(call('CoreAcceptStart') == 1,'separate bootstrap')
        # Deliberately malformed request: fixed worker refuses oversized work
        # before any arithmetic, acknowledges the nonce, then parks permanently.
        row = ((sym['global_core_accept_rows']+255)&-256)+256
        base.put64(mem,row+16,4097)
        base.put64(mem,row,123)
        for _ in range(80): cpus[1].step()
        checks.yes(base.u64(mem,row+8)==123 and base.u64(mem,row+48)==3,
                   'oversized request acknowledged refusal')
        checks.yes(cpus[1].pc in (base.LOAD+sym['coreacceptsecondarypark'],
                                 base.LOAD+sym['coreacceptsecondarypark']+4),
                   'oversized request permanently parks')

        mem,cpus,_,call = machine()
        base.put64(mem,0xE8,0x11110000)
        checks.yes(call('CoreAcceptRun',False)==0,'foreign spin-slot owner refused')
        checks.yes(base.u64(mem,0xE8)==0x11110000 and base.u64(mem,0xE0)==0,
                   'foreign owner and untouched release preserved')

        for label, kwargs in [('EL2',{'el':2}),('SMPEN',{'smpen':0}),('MCI',{'mci':0}),('DAIF',{'daif':0}),
                              ('Aff1',{'affinity':0x100}),('Aff3',{'affinity':1<<32})]:
            mem,_,_,call = machine(**kwargs)
            checks.yes(call('CoreAcceptRun') == 0, label+' refused')
            checks.yes(all(base.u64(mem,0xD8+c*8)==0 for c in (1,2,3)),label+' no release')
        mem,_,_,call = machine()
        checks.yes(call('AcceptLeaseAcquire',arguments=(2,2))==1,'EL3 watchdog lease')
        checks.yes(call('AcceptLeaseAcquire',arguments=(1,3))==0,'pair refuses foreign watchdog')
        checks.yes(base.u64(mem,sym['global_accept_gic_owner'])==0,'failed pair made no partial GIC claim')
        checks.yes(call('AcceptLeaseRelease',arguments=(1,2))==0,'foreign release refused')
        checks.yes(call('CoreAcceptRun')==0,'EL3 lease blocks secondary start')
        checks.yes(all(base.u64(mem,0xD8+c*8)==0 for c in (1,2,3)),'lease refusal before release')
        checks.yes(call('AcceptLeaseRelease',arguments=(2,2))==1,'exact owner releases')
        base.put64(mem,sym['global_accept_secondary_owner'],1)
        checks.yes(call('AcceptLeaseAcquire',arguments=(2,3))==0,
                   'persistent secondary ownership refuses even with cleared lease fields')
        # Deadline refusal with an absent secondary; source also has a spin cap.
        mem,_,primary,call = machine()
        primary.cntpct_per_instruction = 1000000
        checks.yes(call('CoreAcceptRun',False) == 0,'absent secondary times out')
        checks.yes(base.u64(mem,sym['global_core_accept_fault']) == (2**64-6),'join timeout named')
        checks.yes(call('CoreAcceptStop',False) == 0,'failed join cannot be reclaimed')

        # Emitted mutations: corrupt result calculation and stale acknowledgments.
        for label, needle, replacement in [
            ('result','add x7, x7, x6','sub x7, x7, x6'),
            ('nonce','stlr x3, [x9]','stlr xzr, [x9]')]:
            import capstone
            cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
            start = sym['coreacceptsecondaryentry']
            end = sym['coreacceptsecondaryend']
            found = [i for i in cs.disasm(blob[start:end],base.LOAD+start)
                     if (i.mnemonic+' '+i.op_str) == needle]
            checks.yes(bool(found),label+' mutation site')
            mem,_,primary,call = machine()
            addr = found[0].address
            word = int.from_bytes(found[0].bytes,'little')
            word = word ^ 0x40000000 if label=='result' else (word & ~31)|31
            for i,b in enumerate(word.to_bytes(4,'little')): mem[addr+i]=b
            primary.cntpct_per_instruction = 1000
            checks.yes(call('CoreAcceptRun') == 0,label+' mutant rejected')
        print('core_accept_check: PASS',checks.count,'checks; full bootstrap + repeated jobs + stop + refusals + two emitted mutants')
        print('compiler SHA256',hashlib.sha256(Path(args.compiler).read_bytes()).hexdigest())
        print('No silicon/cache/store-buffer/WFE timing proof; PEs interleaved over shared memory.')

if __name__ == '__main__': main()
