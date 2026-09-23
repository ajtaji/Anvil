"""Execute real cooperative task stacks and continuations, without a board."""
import argparse, importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    spec=importlib.util.spec_from_file_location('context_a64',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    source=ROOT/'Anvil/Kernel/Scheduler/Tests/context.pi4'
    with tempfile.TemporaryDirectory(prefix='scheduler-context-') as d:
        image=Path(d)/'context.img'
        r=subprocess.run([a.compiler,'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image),'-s'],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_check.py',compiler=a.compiler)
        c=m.A64();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
        # Explicit model firmware state: EL3, core0, FP enabled, IRQs masked.
        c.enable_system_registers(el=3,preset={0xd51e1140:0,0xd51800a0:0,0xd51b4220:0x3c0,0xd51b4400:0,0xd51b4420:0})
        for steps in range(8000000):
            if c.pc==0x7000000:break
            c.step()
        else:raise AssertionError('Context fixture exceeded execution bound.')
        checks,failures=c.load(0x6000000,8),c.load(0x6000008,8)
        assert checks==81 and failures==0,(checks,failures)
        print(f'PASS: {checks} actual cooperative-context assertions, {steps} instructions. No preemption or board proof.')
        source=ROOT/'Anvil/Kernel/Scheduler/Tests/environment.pi4'
        image=Path(d)/'environment.img'
        r=subprocess.run([a.compiler,'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_check.py',compiler=a.compiler)
        class EnvironmentModel(m.A64):
            def store(self,addr,value,size):
                if addr==0x6000100:
                    self.system_registers[0xd51800a0]=0 if value==3 else 1
                    self.system_registers[0xd51e1140]=1024 if value==1 else 0
                return super().store(addr,value,size)
        for el,trap,expected in ((1,0,0),(2,0,0),(3,1024,0),(3,0,1)):
            c=EnvironmentModel();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
            c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
            c.enable_system_registers(el=el,preset={0xd51e1140:trap,0xd51800a0:0})
            for steps in range(500000):
                if c.pc==0x7000000:break
                c.step()
            else:raise AssertionError('Environment refusal did not return.')
            assert c.x[0]==expected,(el,trap,c.x[0])
        print('PASS: EL1/EL2 refusal, EL3 trapped-FP refusal, EL3 enabled admission. EL0 is outside privileged-call contract.')
if __name__=='__main__':main()
