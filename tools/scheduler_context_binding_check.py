"""Native secure timer -> GIC IAR/EOI -> async tasks -> restored vector lease."""
import argparse,hashlib,importlib.util,os,subprocess,sys,tempfile
from pathlib import Path
import build_count
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
    compiler=Path(a.compiler);digest=hashlib.sha256(compiler.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('binding_model',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    d,c=0xff841000,0xff842000
    class Model(m.A64):
        active=False
        eois=0
        install_fault=0
        def step(self):
            if self.install_fault and self.load(self.pc,4)&~31==0xd51ec000:
                super().step()
                self.system_registers[0xd51ec000]=0x18000
                self.install_fault-=1
                return
            return super().step()
        def load(self,addr,size):
            if addr==c+12:
                if not self.active and super().load(d+0x200,4)&(1<<29) and super().load(d+0x100,4)&(1<<29):
                    self.active=True
                    super().store(d+0x300,1<<29,4)
                    return 29
                return 1023
            return super().load(addr,size)
        def store(self,addr,value,size):
            if addr==0x6000300:
                m.A64.store(self,d+0x80,0 if value==1 else 0xffffffff,4)
                if value==2:self.install_fault=2
            if addr==c+16:
                assert self.active and value==29
                self.active=False;self.eois+=1
                super().store(d+0x300,0,4)
            if d+0x100<=addr<d+0x120:value=super().load(addr,size)|value
            if d+0x180<=addr<d+0x1a0:
                return super().store(addr-0x80,super().load(addr-0x80,size)&~value,size)
            return super().store(addr,value,size)
    fixture=(ROOT/'Anvil/Kernel/Scheduler/Tests/preempt.pi4').read_text()
    fixture=fixture.replace('Global quantum.i = 5000','XIncludeFile "RaspberryPi4/Lib/interrupts.pi4"\nXIncludeFile "Anvil/Kernel/Scheduler/timer_el3.pbi"\nXIncludeFile "Anvil/Kernel/Scheduler/binding_pi4.pbi"\nGlobal quantum.i = 5000')
    fixture=fixture.replace('Check(ApInstall($8000, @TimerAck, @TimerArm, @TimerStop, $400000, $200000), 1)','InterruptInit($8000)\n  Check(AbPrepare(5000, $400000, $200000, @TimerStop), 1)')
    fixture=fixture.replace('Check(ApUninstall(), 1)','Check(AbRollback(), 1)')
    fixture=fixture.replace('InterruptInit($8000)','InterruptInit($8000)\n  PokeI($6000040, AbPrepare(5000, $400000, $200000, 0))\n  PokeI($6000048, ab_state)\n  PokeI($6000300, 1)\n  PokeI($6000050, AbPrepare(5000, $400000, $200000, @TimerStop))\n  PokeI($6000058, ab_state)\n  PokeI($6000300, 0)')
    fixture=fixture.replace('PokeI($6000000, checks)','PokeI($6000010, ap_ticks)\n  PokeI($6000000, checks)')
    fixture=fixture.replace('PokeI($6000300, 0)','PokeI($6000300, 0)\n  PokeI($6000300, 2)\n  PokeI($6000060, AbPrepare(5000, $400000, $200000, @TimerStop))\n  PokeI($6000068, ab_state)\n  PokeI($6000070, AbRollback())\n  PokeI($6000078, ab_state)')
    fixture=fixture.replace('progress[id] = n','progress[id] = n\n    If progress[0] > 0 And progress[1] > 0\n      If SchedState(first) <> #SCHED_DONE And SchedState(second) <> #SCHED_DONE\n        overlap = 1\n      EndIf\n    EndIf')
    with tempfile.TemporaryDirectory(prefix='scheduler-binding-') as tmp:
        source=Path(tmp)/'binding.pi4';source.write_text(fixture);image=Path(tmp)/'binding.img'
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest()
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_binding_check.py',compiler=str(compiler))
        cpu=Model();cpu.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0x7000000
        cpu.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51800a0:0,0xd51b4220:960,0xd51e1100:0x5b1,0xd51e1140:0,0xd51ed040:0,0xd51fe220:2,0xd51fe240:1234})
        for addr,value in ((d+0xfe8,0x20),(d+8,0x43b),(c+0xfc,0x0202143b),(d+4,0x407),(d,3),(c,0x1e7),(c+4,255),(d+0x80,0xffffffff)):
            m.A64.store(cpu,addr,value,4)
        irqs=0
        spurious=0
        for steps in range(4000000):
            if cpu.pc==0x7000000:break
            ctl=cpu.system_registers.get(0xd51fe220,0)&3
            pending=bool(ctl&1 and cpu.cntpct>=cpu.system_registers.get(0xd51fe240,0))
            cpu.system_registers[0xd51fe220]=ctl|(4 if pending else 0)
            m.A64.store(cpu,d+0x200,(1<<29) if pending and not ctl&2 else 0,4)
            if pending and not ctl&2 and not cpu.active and cpu.load(d+0x100,4)&(1<<29):
                if cpu.take_irq(3):irqs+=1
            elif cpu.eois==1 and not pending and not spurious:
                # Inject one controller-spurious IRQ after an acknowledged tick.
                # IAR returns1023; no comparator event or task progress invented.
                if cpu.take_irq(3):spurious=1
            cpu.step()
        else:raise AssertionError('Binding execution exceeded bound.')
        assert [cpu.load(0x6000000+i*8,8) for i in range(2)]==[18,0]
        assert [cpu.load(0x6000040+i*8,8) for i in range(4)]==[0]*4
        assert [cpu.load(0x6000060+i*8,8) for i in range(4)]==[0,1,1,0]
        assert irqs==cpu.eois and irqs>4 and not cpu.active
        assert spurious==1 and cpu.load(0x6000010,8)==cpu.eois
        assert cpu.system_registers[0xd51fe220]==2 and cpu.system_registers[0xd51fe240]==1234
        assert cpu.system_registers[0xd51ec000]==0x8000 and cpu.load(d+0x100,4)==0
        print(f'PASS: 18 native bound-scheduler assertions, {irqs} secure-timer GIC IRQ/EOI pairs, {steps} instructions; timer/vector lease restored. Desk only.')
if __name__=='__main__':main()
