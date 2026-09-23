"""Desk-only Pi3 USB native MMIO and host-state emitted gate."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True)
    p.add_argument('--purebasic',default=str(Path.home()/'AppData/Local/Programs/PureBasic/Compilers/pbcompiler.exe'))
    args=p.parse_args();env=dict(os.environ,PMF_ROOT=str(ROOT));checks=0
    def run(command):
        r=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        assert r.returncode==0,r.stdout+r.stderr
    with tempfile.TemporaryDirectory(prefix='pi3-usb-native-') as folder:
        work=Path(folder);host=work/'host.exe'
        run([args.purebasic,'/CONSOLE','/QUIET','/EXE',str(host),str(ROOT/'RaspberryPi3/Tests/usb_host_init_host.pb')]);run([str(host)])
        def build(source,name):
            image=work/(name+'.img')
            run([args.compiler,'--compile',source,'-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(image)])
            return image.read_bytes(),base.parse_symbols(image)
        m=base.load_interp(base.INTERP)
        host_blob,host_syms=build('RaspberryPi3/Tests/usb_host_init.pi3','init')
        native_blob,native_syms=build('RaspberryPi3/Tests/usb_native.pi3','native')
        class Model(m.A64):
            def __init__(self,blob=native_blob,symbols=native_syms,el=2,core=0,mask=0x3c0,sctlr=0,mutant=False):
                super().__init__();self.symbols=symbols;self.events=[]
                if mutant:blob=blob.replace(bytes.fromhex('9f3f03d5'),bytes.fromhex('1f2003d5'))
                self.memory.update({base.LOAD+i:b for i,b in enumerate(blob)})
                self.enable_system_registers(el=el,preset={0xD51800A0:core,0xD51C1000:sctlr,0xD51E1000:sctlr,0xD51B4220:mask})
            def load(self,address,size):
                if 0x3f980000<=address<0x3f981000:
                    assert size==4
                    assert self.events[-2:]==['dsb','isb'],'unordered native USB read'
                    self.events.append(('read',address));return 0x4f54280a
                return super().load(address,size)
            def store(self,address,value,size):
                if 0x3f980000<=address<0x3f981000:
                    assert size==4
                    assert self.events[-2:]==['dsb','isb'],'unordered native USB write'
                    self.events.append(('write',address,value&0xffffffff));return
                super().store(address,value,size)
            def call(self,name,*values,limit=1000000):
                self.pc=base.LOAD+self.symbols[name.lower()];self.sp=base.STACK;self.x[30]=base.RETURN_PC
                for i,value in enumerate(values):self.x[i]=value&((1<<64)-1)
                for _ in range(limit):
                    if self.pc==base.RETURN_PC:return self.x[0]&((1<<64)-1)
                    word=super().load(self.pc,4)
                    if word==0xd5033f9f:self.events.append('dsb')
                    if word==0xd5033fdf:self.events.append('isb')
                    self.step()
                raise AssertionError('emitted path exceeded bound: '+name)
        for case in (*range(7),8):
            c=Model(host_blob,host_syms);assert c.call('UsbHostScenario',case)==1,case;checks+=1
        # Frozen-timer backstop runs natively in the host gate (2M bounded spins).
        for el in (2,3):
            c=Model(el=el);assert c.call('Pi3UsbPowerAcquire')==1;checks+=1
            assert c.call('Pi3UsbRead',0x40)==0x4f54280a;checks+=1
            assert c.events[-2:]==['dsb','isb'];checks+=1
            c.call('Pi3UsbWrite',0x18,0);assert ('write',0x3f980018,0) in c.events;checks+=1
            before=list(c.events);assert c.call('Pi3UsbRead',3)==(1<<64)-1 and c.events==before;checks+=1
        for state in ({'el':1},{'core':1},{'core':0x100},{'core':1<<32},{'mask':0},{'sctlr':1},{'sctlr':4}):
            c=Model(**state);assert c.call('Pi3UsbPowerAcquire')==0 and not c.events;checks+=1
        for mode in (1,2):
            c=Model();c.store(native_syms['global_native_reply_mode'],mode,8)
            assert c.call('Pi3UsbPowerAcquire')==0 and c.call('Pi3UsbPowerAcquire')==0 and not c.events;checks+=1
        c=Model(mutant=True);assert c.call('Pi3UsbPowerAcquire')==1
        try:c.call('Pi3UsbRead',0x40)
        except AssertionError as error:assert 'unordered' in str(error);checks+=1
        else:raise AssertionError('missing DSB mutant survived')
        print('PASS',checks,'emitted checks + 9 hostile host scenarios; missing-barrier mutant rejected')
        print('Compiler SHA256',hashlib.sha256(Path(args.compiler).read_bytes()).hexdigest())
if __name__=='__main__':main()
