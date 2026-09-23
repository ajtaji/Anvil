"""Execute native CNTPS/GIC adapter; explicit device model, not silicon."""
import argparse, hashlib, importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    compiler=Path(a.compiler);digest=hashlib.sha256(compiler.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('timer_model',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    d,c=0xff841000,0xff842000
    class Model(m.A64):
        refusal_guard=False
        def step(self):
            if self.refusal_guard:
                assert self.load(self.pc,4)&~31 not in (0xd51fe200,0xd51fe220,0xd51fe240), 'Refusal wrote secure timer.'
            return super().step()
        def store(self,addr,value,size):
            if self.refusal_guard and d<=addr<c+0x1000:
                raise AssertionError('Refusal wrote GIC ownership state.')
            if addr==0x6000100:
                if value<=2:
                    m.A64.store(self,c+12,29 if value==1 else 1023,4)
                    self.system_registers[0xd51fe220]=5 if value==1 else 1
                else:
                    self.refusal_guard=True
                    m.A64.store(self,d+0x200,(1<<29) if value==3 else 0,4)
                    m.A64.store(self,d+0x80,0 if value==4 else 0xffffffff,4)
                    self.system_registers[0xd51e1100]=0 if value==5 else 0x5b1
                    if value==6:self.current_el=2
            if d+0x100<=addr<d+0x120:value=self.load(addr,size)|value
            if d+0x180<=addr<d+0x1a0:
                return super().store(addr-0x80,self.load(addr-0x80,size)&~value,size)
            return super().store(addr,value,size)
    source=ROOT/'Anvil/Kernel/Scheduler/Tests/timer_el3.pi4'
    with tempfile.TemporaryDirectory(prefix='scheduler-timer-') as tmp:
        image=Path(tmp)/'timer.img'
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest()
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_timer_check.py',compiler=str(compiler))
        cpu=Model();cpu.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0x7000000
        cpu.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51800a0:0,0xd51b4220:960,0xd51e1100:0x5b1,0xd51fe220:2,0xd51fe240:1234})
        for addr,value in ((d+0xfe8,0x20),(d+8,0x43b),(c+0xfc,0x0202143b),(d+4,0x407),(d,3),(c,0x1e7),(c+4,255),(d+0x80,0xffffffff),(c+12,1023)):
            m.A64.store(cpu,addr,value,4)
        for steps in range(300000):
            if cpu.pc==0x7000000:break
            cpu.step()
        else:raise AssertionError('Timer fixture exceeded bound.')
        values=[cpu.load(0x6000000+i*8,8) for i in range(10)]
        assert values==[1,1,2,1,2,1,2,1,2,1234],values
        assert [cpu.load(0x6000050+i*8,8) for i in range(4)]==[0]*4
        assert cpu.system_registers[0xd51fe220]==2 and cpu.system_registers[0xd51fe240]==1234
        print('PASS: 14 native secure-timer/GIC checks, including pending/group/SCR/EL refusals, spurious acknowledgment and comparator restoration; desk model only.')
if __name__=='__main__':main()
