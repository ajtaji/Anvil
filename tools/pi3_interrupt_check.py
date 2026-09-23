"""Execute Pi3 timer code with explicit local-MMIO and architectural timer model."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import build_count
ROOT=Path(__file__).resolve().parents[1]
LOAD,STACK,RETURN=0x400000,0x3000000,0x7000000
CTL,TVAL,FREQ,MPIDR,DAIF=0xD51BE220,0xD51BE200,0xD51BE000,0xD51800A0,0xD51B4220
ROUTE,SOURCE=0x40000040,0x40000060

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);args=p.parse_args()
    spec=importlib.util.spec_from_file_location('pi3_interrupt_cpu',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory(prefix='pi3-interrupt-') as work:
        work=Path(work)
        def compile_image(src,name):
            image=work/(name+'.img')
            r=subprocess.run([args.compiler,'--compile',str(src),'-t','pi3','--entry-returns',
                '--load-addr',hex(LOAD),'--stack-addr',hex(STACK),'-s','-o',str(image)],
                cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
            assert r.returncode==0 and image.exists(),r.stdout+r.stderr
            build_count.record_build(src,'pi3',image,by='tools/pi3_interrupt_check.py',compiler=args.compiler)
            symbols={k:int(v)+LOAD for k,v in (line.split('=',1) for line in Path(str(image)+'.sym').read_text().splitlines() if '=' in line)}
            return image.read_bytes(),symbols
        blob,symbols=compile_image(ROOT/'RaspberryPi3/Tests/pi3_timer.pi3','timer')
        class Model:
            def __init__(self,blob=blob,symbols=symbols,el=2,core=0,mask=0x80,frequency=19200000,route=0x85,control=0):
                self.symbols=symbols;self.cpu=m.A64();self.cpu.enable_system_registers(el=el,preset={MPIDR:core,DAIF:mask,FREQ:frequency,CTL:control,TVAL:0})
                self.cpu.memory.update({LOAD+i:b for i,b in enumerate(blob)})
                self.counter=100000;self.deadline=0;self.route=route;self.control=control;self.extra=0;self.writes=[];self.mmio=[]
                load,store=self.cpu.load,self.cpu.store
                def read(address,size):
                    if address in (ROUTE,SOURCE):
                        assert size==4;self.mmio.append(('read',address))
                        if address==ROUTE:return self.route
                        active=(self.control&3)==1 and self.counter>=self.deadline
                        routed=(self.route&0x22)==2
                        return self.extra | (2 if active and routed else 0)
                    return load(address,size)
                def write(address,value,size):
                    if address==ROUTE:
                        assert size==4;self.mmio.append(('write',address));self.route=value&0xffffffff;self.writes.append(('route',self.route));return
                    assert address!=SOURCE,'IRQ status is read-only, not an EOI register'
                    store(address,value,size)
                self.cpu.load,self.cpu.store=read,write
            def call(self,name,*args):
                c=self.cpu;c.pc=self.symbols[name.lower()];c.sp=STACK;c.x[30]=RETURN
                for i,arg in enumerate(args):c.x[i]=arg&((1<<64)-1)
                for steps in range(100000):
                    if c.pc==RETURN:return c.x[0]
                    ins=c.load(c.pc,4);base=(ins&0xffffffe0)&~0x200000
                    if (ins&0xfff00000)==0xd5300000 and base==CTL:
                        c.system_registers[CTL]=self.control | (4 if (self.control&1) and self.counter>=self.deadline else 0)
                    c.step();self.counter+=1
                    if (ins&0xfff00000)==0xd5100000:
                        if base==CTL:
                            self.control=c.system_registers[CTL]&3;self.writes.append(('ctl',self.control))
                        elif base==TVAL:
                            ticks=c.system_registers[TVAL]&0xffffffff
                            if ticks&0x80000000:ticks-=1<<32
                            self.deadline=self.counter+ticks;self.writes.append(('tval',ticks))
                        else:raise AssertionError(('unexpected system write',hex(base)))
                raise AssertionError('Timer function exceeded bounded instruction budget')
        checks=0
        def check(value):
            nonlocal checks
            assert value;checks+=1
        def happy(t):
            check(t.call('Pi3IrqTimerInit',19200)==1)
            check(t.call('Pi3IrqTimerFrequency')==19200000)
            check(t.writes==[])
            check(t.call('Pi3IrqTimerArm')==1)
            check(t.route==0x87 and t.control==1)
            check(t.writes==[('ctl',0),('tval',19200),('route',0x87),('ctl',1)])
            check(t.call('Pi3IrqTimerPending')==0)
            t.counter=t.deadline
            check(t.call('Pi3IrqTimerHandle')==1)
            check(t.writes[-2:]==[('tval',19200),('ctl',1)])
            check(t.call('Pi3IrqTimerPending')==0)
            t.counter=t.deadline;t.extra=8;before=list(t.writes)
            check(t.call('Pi3IrqTimerHandle')==0 and t.writes==before)
            t.extra=0
            check(t.call('Pi3IrqTimerStop')==1 and t.control==0 and t.route==0x85)
            check(t.call('Pi3IrqTimerFrequency')==0)
            check(t.call('Pi3IrqTimerInit',1)==1)
        happy(Model())
        for kwargs in ({'el':1},{'el':3},{'core':1},{'core':0x100},{'core':1<<32},{'mask':0}):
            t=Model(**kwargs);check(t.call('Pi3IrqTimerInit',19200)==0);check(t.call('Pi3IrqTimerError')==1);check(t.mmio==[] and t.writes==[])
        for ticks in (0,-1,0x80000000):
            t=Model();check(t.call('Pi3IrqTimerInit',ticks)==0);check(t.call('Pi3IrqTimerError')==2);check(t.writes==[])
        for kwargs in ({'route':2},{'route':32},{'control':1}):
            t=Model(**kwargs);check(t.call('Pi3IrqTimerInit',1)==0);check(t.call('Pi3IrqTimerError')==3);check(t.writes==[])
        t=Model(frequency=0);check(t.call('Pi3IrqTimerInit',1)==0);check(t.call('Pi3IrqTimerError')==4)
        t=Model();check(t.call('Pi3IrqTimerArm')==0);check(t.call('Pi3IrqTimerError')==5)
        t=Model();check(t.call('Pi3IrqTimerInit',100)==1);t.route|=32
        check(t.call('Pi3IrqTimerArm')==0 and t.writes==[]);check(t.call('Pi3IrqTimerError')==6)
        print(f'PASS: {checks} emitted timer/context/routing/rearm/refusal checks; no global interrupt unmask.')
        mutant=work/'mutant.pi3'
        fixture=(ROOT/'RaspberryPi3/Tests/pi3_timer.pi3').read_text().split('\n',1)[1]
        mutant.write_text((ROOT/'RaspberryPi3/Lib/interrupt_timer.pbi').read_text().replace('route | 2','route | 1')+'\n'+fixture)
        mb,ms=compile_image(mutant,'mutant')
        try:happy(Model(blob=mb,symbols=ms))
        except AssertionError:print('PASS: wrong local IRQ routing mutation rejected.')
        else:raise AssertionError('Routing mutation escaped the test.')
if __name__=='__main__':main()
