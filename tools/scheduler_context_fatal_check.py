"""Prove fatal reporting abandons a broken stack and cannot recurse."""
import argparse,hashlib,importlib.util,os,subprocess,sys,tempfile
from pathlib import Path
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    compiler=Path(a.compiler);digest=hashlib.sha256(compiler.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('fatal_model',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    source=ROOT/'Anvil/Kernel/Scheduler/Tests/preempt_fatal.pi4'
    with tempfile.TemporaryDirectory(prefix='scheduler-fatal-') as tmp:
        image=Path(tmp)/'fatal.img'
        r=subprocess.run([str(compiler),'--compile',str(source),'-t','pi4','--load-addr','0x400000','--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert digest==hashlib.sha256(compiler.read_bytes()).hexdigest()
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/scheduler_context_fatal_check.py',compiler=str(compiler))
        cpu=m.A64();cpu.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        cpu.pc,cpu.sp,cpu.x[30]=0x400000,0x3000000,0x7000000
        cpu.enable_system_registers(el=3,preset={0xd51ec000:0x8000,0xd51800a0:0,0xd51b4220:960,0xd51e1140:0,0xd51ed040:0,0xd51e4020:0x12345678})
        for steps in range(400000):
            if cpu.load(cpu.pc,4)==0xd503205f:break
            cpu.step()
        else:raise AssertionError('Fatal handler did not park.')
        assert [cpu.load(0x6000000+i*8,8) for i in range(4)]==[1,0x12345678,1,1]
        assert [cpu.load(0x6000020+i*8,8) for i in range(3)]==[8,6,7]
        assert cpu.sp != 3 and cpu.sp%16==0 and cpu.system_registers[0xd51b4220]==960
        before=[cpu.load(0x6000000+i*8,8) for i in range(4)]
        for _ in range(30):cpu.step()
        assert before==[cpu.load(0x6000000+i*8,8) for i in range(4)]
        print('PASS: fatal callback once, raw record preserved, corrupt SP abandoned, aligned emergency stack, DAIF masked, recursive stop parked; desk only.')
if __name__=='__main__':main()
