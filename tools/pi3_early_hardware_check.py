"""Execute real early-library emission against explicit fake BCM2837 MMIO.

--target pi4 is CPU-only bootstrap evidence, NOT a Pi3 target/boot test.
No firmware, peripheral electrical timing, or board access is simulated.
"""
import argparse, hashlib, pathlib, sys, tempfile, subprocess, os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base

def run(a64,data,mode,el=2):
    class Machine(a64.A64):
        def __init__(self):
            super().__init__(); self.ticks=0; self.writes=[]; self.request=None
        def load(self,addr,size):
            if addr==0x3f003008: return 0
            if addr==0x3f003004: self.ticks+=1000; return self.ticks
            if addr==0x3f201018: return 0x20 if mode=='txfull' else (0x10 if mode=='rxempty' else 0)
            if addr==0x3f201000: return 0xF42 if mode=='rxerror' else 66
            if addr==0x3f200004: return 0xffffffff
            if addr==0x3f00b8b8: return 0x80000000 if mode=='mbfull' else 0
            if addr==0x3f00b898: return 0x40000000 if mode=='mbempty' else 0
            if addr==0x3f00b880: return self.request or 0
            return super().load(addr,size)
        def store(self,addr,value,size):
            if 0x3f000000<=addr<0x40000000:
                self.writes.append((addr,value&0xffffffff))
                if addr==0x3f00b8a0:
                    self.request=value&0xffffffff
                    buf=value&0x3ffffff0
                    super().store(buf+4,0x80000000,4)
                    super().store(buf+16,0x80000008,4)
                    super().store(buf+24,48000000,4)
                return
            if 0xfe000000<=addr<0xff000000: raise AssertionError('Pi4 MMIO alias')
            return super().store(addr,value,size)
    cpu=Machine()
    for n,b in enumerate(data): cpu.memory[base.LOAD+n]=b
    cpu.enable_system_registers(el=el,preset={base.SCTLR_EL2:5 if mode=='cached' else 0,base.SCTLR_EL3:0})
    cpu.pc,cpu.sp,cpu.x[30]=base.LOAD,base.STACK,base.RETURN_PC
    for steps in range(1000000):
        if cpu.pc==base.RETURN_PC: break
        cpu.step()
    else: raise AssertionError('unbounded fixture')
    out=[base.u64(cpu,base.OUT+n*8) for n in range(7)]
    assert out[0]==1000 and out[1]==1 and out[2]==1,out
    assert out[3]==(0 if mode=='txfull' else 1),out
    assert out[4]==({'rxempty':2**64-1,'rxerror':2**64-2}.get(mode,66)),out
    assert out[5]==(2**64-1 if mode in ('mbfull','mbempty','cached') or el==1 else 48000000),out
    assert out[6]==out[5],out
    if mode=='mbempty': assert sum(a==0x3f00b8a0 for a,v in cpu.writes)==1,'timed-out buffer reused'
    assert (0x3f201024,26) in cpu.writes and (0x3f201028,3) in cpu.writes
    assert (0x3f200004,0xfffe4fff) in cpu.writes,cpu.writes
    assert all(a!=0x3f00b8a0 for a,v in cpu.writes) if mode in ('mbfull','cached') or el==1 else True
    return steps

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',required=True);p.add_argument('--target',choices=['pi3','pi4'],default='pi3')
    args=p.parse_args(); compiler=pathlib.Path(args.compiler).resolve()
    a64=base.load_interpreter(base.INTERP)
    with tempfile.TemporaryDirectory(prefix='anvil-pi3-') as tmp:
        image=pathlib.Path(tmp)/'early.img'
        cmd=[str(compiler),'--compile','RaspberryPi3/Tests/early_hardware.pi3','-t',args.target,'--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(image),'-s']
        env=os.environ.copy();env['PMF_ROOT']=str(base.ROOT)
        r=subprocess.run(cmd,cwd=base.ROOT,env=env,capture_output=True,text=True)
        if r.returncode or not image.exists():raise SystemExit(r.stdout+r.stderr)
        data=image.read_bytes();steps=0
        for mode in ('normal','txfull','rxempty','rxerror','mbfull','mbempty','cached'):steps+=run(a64,data,mode)
        steps+=run(a64,data,'normal',3);steps+=run(a64,data,'normal',1)
        print('PASS: 9 fake-MMIO emitted cases;',steps,'instructions; target',args.target)
        print('Compiler SHA256:',hashlib.sha256(compiler.read_bytes()).hexdigest())
if __name__=='__main__':main()
