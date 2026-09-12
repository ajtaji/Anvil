"""Actual asynchronous timer IRQs preempt two native nonyielding FP loops."""
import argparse,hashlib,importlib.util,os,subprocess,sys,tempfile
from pathlib import Path
import build_count
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);p.add_argument('--mutate',action='store_true');a=p.parse_args()
    compiler=Path(a.compiler);digest=hashlib.sha256(compiler.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('preempt_a64',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    source=ROOT/'Anvil/Kernel/Scheduler/Tests/preempt.pi4'
    with tempfile.TemporaryDirectory(prefix='scheduler-preempt-') as d:
        image=Path(d)/'preempt.img'
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image),'-s'],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest(),'Compiler changed during gate.'
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_preempt_check.py',compiler=str(compiler))
        c=m.A64();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
        c.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51e1140:0,0xd51800a0:0,0xd51b4220:960,0xd51b4400:0,0xd51b4420:0,0xd51ed040:0,0xd51be220:0})
        interrupts=0
        for steps in range(8000000):
            if c.pc==0x7000000:break
            # Timer device model: one count per executed instruction, explicitly
            # routed to EL3. No task state/counters/PC manufactured by the gate.
            ctl=c.system_registers.get(0xd51be220,0)&3
            pending=bool(ctl&1 and c.cntpct>=c.system_registers.get(0xd51be240,0))
            c.system_registers[0xd51be220]=ctl|(4 if pending else 0)
            if pending and not ctl&2 and c.take_irq(3):interrupts+=1
            c.step()
        else:raise AssertionError('Preemption fixture exceeded execution bound.')
        checks,failures=c.load(0x6000000,8),c.load(0x6000008,8)
        assert checks==18 and failures==0,(checks,failures,interrupts,steps)
        assert interrupts>4 and not c.system_registers[0xd51be220]&1,(interrupts,c.system_registers[0xd51be220])
        print(f'PASS: {checks} native preemption assertions, {interrupts} asynchronous IRQs, {steps} instructions; compiler {digest}. No hardware proof.')
        source=ROOT/'Anvil/Kernel/Scheduler/Tests/preempt_refuse.pi4'
        image=Path(d)/'refuse.img'
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest(),'Compiler changed during gate.'
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_preempt_check.py',compiler=str(compiler))
        class RefusalModel(m.A64):
            old_vector=0
            def store(self,addr,value,size):
                if addr==0x6000100:
                    if value in (1,2):self.system_registers[0xd51800a0]=1 if value==1 else 0
                    if value in (3,4):self.system_registers[0xd51b4220]=832 if value==3 else 960
                    if value==5:
                        self.old_vector=self.system_registers[0xd51ec000];self.system_registers[0xd51ec000]=0x18000
                    if value==6:self.system_registers[0xd51ec000]=self.old_vector
                    if value in (7,8):self.system_registers[0xd51ed040]=1 if value==7 else 0
                return super().store(addr,value,size)
        c=RefusalModel();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
        c.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51e1140:0,0xd51800a0:0,0xd51b4220:960,0xd51ed040:0})
        for steps in range(2000000):
            if c.pc==0x7000000:break
            c.step()
        else:raise AssertionError('Ownership fixture exceeded execution bound.')
        checks,failures=c.load(0x6000000,8),c.load(0x6000008,8)
        assert checks==31 and failures==0,(checks,failures)
        print(f'PASS: {checks} vector/core/mask/span/context/refusal assertions, {steps} instructions.')
        if a.mutate:
            fixture=(ROOT/'Anvil/Kernel/Scheduler/Tests/preempt.pi4').read_text()
            runtime=(ROOT/'Anvil/Kernel/Scheduler/preempt_a64.pbi').read_text()
            for name,before,after in (('q0_restore','    ldr q0, [x9, #288]','    ldr q0, [x9, #304]'),('saved_pc','    mrs x10, elr_el3','    movz x10, #0')):
                assert runtime.count(before)==1,(name,'mutation anchor not unique')
                source=Path(d)/(name+'.pi4');image=Path(d)/(name+'.img')
                source.write_text(fixture.replace('XIncludeFile "Anvil/Kernel/Scheduler/preempt_a64.pbi"',runtime.replace(before,after)))
                r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
                assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest(),'Compiler changed during gate.'
                assert r.returncode==0 and image.exists(),r.stdout+r.stderr
                build_count.record_build(source,'pi4',image,by='tools/scheduler_context_preempt_check.py',compiler=str(compiler))
                c=m.A64();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
                c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
                c.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51e1140:0,0xd51800a0:0,0xd51b4220:960,0xd51b4400:0,0xd51b4420:0,0xd51ed040:0,0xd51be220:0})
                rejected=False
                try:
                    for steps in range(2000000):
                        if c.pc==0x7000000:
                            rejected=c.load(0x6000008,8)>0;break
                        ctl=c.system_registers.get(0xd51be220,0)&3
                        pending=bool(ctl&1 and c.cntpct>=c.system_registers.get(0xd51be240,0))
                        c.system_registers[0xd51be220]=ctl|(4 if pending else 0)
                        if pending and not ctl&2:c.take_irq(3)
                        c.step()
                    else:rejected=True
                except RuntimeError:rejected=True
                assert rejected,('undetected context corruption',name)
                print('PASS: context corruption rejected:',name)
if __name__=='__main__':main()
