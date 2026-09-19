"""Actual emitted deadline/recovery checks. Counter rate is a model, not silicon timing."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from a64_interp import A64
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_count
LOAD,STACK,RETURN=0x400000,0x3000000,0x7000000
BASE=0xfe804000

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='i2c-deadline-') as td:
        td=Path(td)
        def build(source,name):
            image=td/(name+'.img')
            r=subprocess.run([a.compiler,'--compile',str(source),'-t','pi4','--entry-returns',
                '--load-addr',hex(LOAD),'--stack-addr',hex(STACK),'-s','-o',str(image)],
                cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
            assert r.returncode==0,r.stdout+r.stderr
            build_count.record_build(source,'pi4',image,by='tools/a64/i2c_deadline_check.py',compiler=a.compiler)
            syms={k:int(v,0)+LOAD for k,v in (s.split('=',1) for s in Path(str(image)+'.sym').read_text().splitlines() if '=' in s)}
            return image.read_bytes(),syms
        original=ROOT/'RaspberryPi4/Tests/i2c_deadline.pi4'
        blob,syms=build(original,'original')
        class Machine:
            def __init__(self,hz=19200000,rate=20,program=None):
                b,s=program or (blob,syms);self.syms=s;self.cpu=A64()
                self.cpu.memory.update({LOAD+i:x for i,x in enumerate(b)})
                self.hz=hz;self.rate=rate;self.ticks=100000;self.tick_reads=[]
                self.release=None;self.writes=[];self.status_reads=0
                read,write=self.cpu.load,self.cpu.store
                def load(addr,size):
                    if addr==BASE+4:
                        assert size==4;self.status_reads+=1
                        return 1 if self.release is None or self.ticks<self.release else 0
                    return read(addr,size)
                def store(addr,value,size):
                    if BASE<=addr<BASE+32:
                        assert size==4;self.writes.append((addr-BASE,value));return
                    write(addr,value,size)
                self.cpu.load,self.cpu.store=load,store
            def call(self,name,*args):
                c=self.cpu;c.pc=self.syms[name.lower()];c.sp=STACK;c.x[30]=RETURN
                for i,value in enumerate(args):c.x[i]=value&((1<<64)-1)
                for _ in range(2000000):
                    if c.pc==RETURN:return c.x[0]
                    ins=c.load(c.pc,4)&0xffffffe0
                    if ins==0xd53be000:c.x[c.load(c.pc,4)&31]=self.hz;c.pc+=4
                    elif ins==0xd53be020:
                        self.tick_reads.append(self.ticks);c.x[c.load(c.pc,4)&31]=self.ticks;c.pc+=4
                    else:c.step()
                    self.ticks+=self.rate
                raise AssertionError('bounded fixture did not return')
        checks=0
        def check(x):
            nonlocal checks
            assert x;checks+=1
        for hz in (19200000,54000000,32768):
            t=Machine(hz,0);deadline=t.call('I2cDeadlineUs',20000)
            expected=(hz*20000+999999)//1000000
            check(deadline==100000+expected)
            t.ticks=deadline-1;check(t.call('I2cWaitExpired',deadline,-2000000)==0)
            t.ticks=deadline;check(t.call('I2cWaitExpired',deadline,2000000)==1)
            t.ticks=deadline+1;check(t.call('I2cWaitExpired',deadline,2000000)==1)
        t=Machine(0,0);check(t.call('I2cDeadlineUs',20000)==0)
        check(t.call('I2cWaitExpired',0,1)==0);check(t.call('I2cWaitExpired',0,0)==1)
        check(t.call('I2cWaitExpired',0,-1)==1)
        for hz in (19200000,54000000):
            for rate in (20,100):
                t=Machine(hz,rate);start=t.ticks;t.release=start+hz*15//1000
                check(t.call('I2cRecover')==1)
                check(t.ticks-start>=hz*15//1000)
                check(all(not(v&128) for off,v in t.writes if off==0))
                t=Machine(hz,rate);check(t.call('I2cRecover')==0)
                check(t.tick_reads[-1]-t.tick_reads[0]>=hz*20//1000)
                check(t.writes[-1]==(0,0))
                # An unsuccessful abort stays refused; no START or optimistic idle.
                check(t.call('I2cEnsureIdle')==0)
                check(all(not(v&128) for off,v in t.writes if off==0))
        print(f'PASS: {checks} exact deadline, variable loop-rate, recovery and fail-closed checks.')
        src=(ROOT/'RaspberryPi4/Lib/i2c.pi4').read_text()
        assert src.count('I2cWaitExpired(deadline, spin)')==4
        # Restore the old OR policy and prove exhausted spins expire too soon.
        mutant=td/'mutant.pi4'
        source=src.replace('ProcedureReturn I2cDeadlinePassed(deadline)',
            'ProcedureReturn Bool(spinsRemaining <= 0 Or I2cDeadlinePassed(deadline) <> 0)')
        deps='\n'.join(original.read_text().splitlines()[:3])+'\n'
        mutant.write_text(deps+source+'\nProcedure Main()\nI2cWaitExpired(1,0)\nEndProcedure\n')
        mb,ms=build(mutant,'mutant');t=Machine(rate=0,program=(mb,ms))
        assert t.call('I2cWaitExpired',200000,-1)==1
        print('PASS: old count-first policy mutation produces the forbidden premature expiry.')
if __name__=='__main__':main()
