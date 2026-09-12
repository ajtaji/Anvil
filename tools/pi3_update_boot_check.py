"""Emitted DTB arena admission + watchdog MMIO model; no reset/hardware."""
import argparse,hashlib,os,pathlib,struct,subprocess,sys,tempfile
import capstone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
ROOT=base.ROOT

def dtb(reserve=(),fixed=None):
    names=b'#address-cells\0#size-cells\0ranges\0reg\0'
    def word(x):return struct.pack('>I',x)
    def node(s):
        raw=s.encode()+b'\0';return word(1)+raw+b'\0'*((-len(raw))%4)
    def prop(name,value):
        return word(3)+word(len(value))+word(names.index(name.encode()+b'\0'))+value+b'\0'*((-len(value))%4)
    tree=node('')+prop('#address-cells',word(2))+prop('#size-cells',word(2))
    if fixed is not None:
        tree+=node('reserved-memory')+prop('#address-cells',word(2))+prop('#size-cells',word(2))+prop('ranges',b'')
        tree+=node('test@0')+prop('reg',struct.pack('>QQ',*fixed))+word(2)+word(2)
    tree+=word(2)+word(9)
    reservations=b''.join(struct.pack('>QQ',*r) for r in reserve)+bytes(16)
    off=40+len(reservations);strings=off+len(tree);total=strings+len(names)
    header=struct.pack('>10I',0xd00dfeed,total,off,strings,40,17,16,0,len(names),len(tree))
    return header+reservations+tree+names

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi3-update-boot-') as tmp:
        image=pathlib.Path(tmp)/'gate.img';env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([args.compiler,'--compile','RaspberryPi3/Tests/update_boot_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
        if r.returncode or not image.exists():raise AssertionError(r.stdout+r.stderr)
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP);checks=0
        class Rig(a64.A64):
            def __init__(self,el=2,aff=0,ignored=False):
                super().__init__();self.memory={base.LOAD+i:b for i,b in enumerate(blob)};self.sp=base.STACK
                self.enable_system_registers(el=el,preset={0xD51800A0:aff,0xD51C1000:0,0xD51E1000:0,0xD51B4220:0x3c0})
                self.regs={0x3f10001c:0};self.writes=[];self.ignored=ignored;self.allow_reset=0
                self.store(sym['global_pi3_up_loaded'],1024,8);self.store(sym['global_pi3_up_active'],0,8)
                self.store(sym['global_pi3_up_record']+64,2,4)
            def load(self,addr,size):
                if 0x3f100000<=addr<0x3f101000:
                    assert size==4 and addr==0x3f10001c;return self.regs.get(addr,0)
                return super().load(addr,size)
            def store(self,addr,value,size):
                if 0x3f100000<=addr<0x3f101000:
                    assert size==4 and addr in (0x3f10001c,0x3f100024)
                    assert value>>24==0x5a
                    self.writes.append((addr,value&0xffffffff))
                    if not self.ignored:self.regs[addr]=value&0xffffff
                    return
                return super().store(addr,value,size)
            def call(self,name,*args):
                self.pc=base.LOAD+sym[name.lower()];self.x[30]=base.RETURN_PC
                for i,v in enumerate(args):self.x[i]=v
                for _ in range(1000000):
                    if self.pc==base.RETURN_PC:return self.x[0]
                    if self.pc==base.LOAD+sym['pi3updateresetready']:
                        self.x[0]=self.allow_reset;self.pc=self.x[30];continue
                    if self.pc==base.LOAD+sym['pi3delayus']:
                        self.x[0]=1;self.pc=self.x[30];continue
                    self.step()
                raise AssertionError('unbounded '+name)
        for reserve,fixed,want in [((),None,1),(((0x1000000,4096),),None,1),(((0x2000000,1),),None,0),(((0x80000,1),),None,0),((),(0x2000000,4096),0),((),(0x30000000,4096),1),((),(0x1ff0000,1),0)]:
            c=Rig();data=dtb(reserve,fixed)
            for i,b in enumerate(data):c.memory[0x1000000+i]=b
            assert c.call('Pi3BootRanges',0x1000000,len(data))==want,(reserve,fixed)
            assert not c.writes;checks+=1
        for field,value in ((16,41),(36,0x100000),(12,0xffffff),(20,16)):
            c=Rig();data=bytearray(dtb());struct.pack_into('>I',data,field,value)
            for i,b in enumerate(data):c.memory[0x1000000+i]=b
            assert c.call('Pi3BootRanges',0x1000000,len(data))==0;checks+=1
        for el in (2,3):
            c=Rig(el);assert c.call('Pi3UpdateWatchdogArm')==1
            assert c.writes==[(0x3f100024,0x5a0f0000),(0x3f10001c,0x5a000020)]
            assert c.call('Pi3UpdateWatchdogStop')==0
            c.store(sym['global_pi3_up_record']+64,3,4)
            assert c.call('Pi3UpdateWatchdogStop')==1 and c.writes[-1]==(0x3f10001c,0x5a000102);checks+=4
        # The immutable loader acquires one un-fed window before the
        # post-recovery selected-slot load. A later trial-arm check must not
        # restart that timer.
        c=Rig();c.store(sym['global_pi3_up_loaded'],0,8)
        c.store(sym['global_pi3_up_mounted'],1,8)
        c.store(sym['global_pi3_up_receiving'],0,8)
        assert c.call('Pi3UpdateWatchdogArmWindow')==1
        assert c.writes==[(0x3f100024,0x5a0f0000),(0x3f10001c,0x5a000020)]
        c.store(sym['global_pi3_up_loaded'],1024,8)
        assert c.call('Pi3UpdateWatchdogArm')==1
        assert c.writes==[(0x3f100024,0x5a0f0000),(0x3f10001c,0x5a000020)]
        assert c.call('Pi3UpdateWatchdogArmWindow')==0
        assert len(c.writes)==2;checks+=4
        for el,aff in ((1,0),(2,0x100),(2,1<<32)):
            c=Rig(el,aff);assert c.call('Pi3UpdateWatchdogArm')==0 and not c.writes;checks+=1
        c=Rig(ignored=True);assert c.call('Pi3UpdateWatchdogArm')==0;checks+=1
        c=Rig();c.regs[0x3f10001c]=0x20;assert c.call('Pi3UpdateWatchdogArm')==1;checks+=1
        c=Rig();c.regs[0x3f10001c]=0x20
        assert c.call('Pi3UpdateWatchdogColdStop')==1 and c.writes==[(0x3f10001c,0x5a000102)];checks+=1
        c=Rig(ignored=True);c.regs[0x3f10001c]=0x20
        assert c.call('Pi3UpdateWatchdogColdStop')==0;checks+=1
        c=Rig();assert c.call('Pi3UpdateResetNow')==0 and not c.writes;checks+=1
        c=Rig();c.allow_reset=1
        assert c.call('Pi3UpdateResetNow')==0
        assert c.writes==[(0x3f100024,0x5a00000a),(0x3f10001c,0x5a000020)];checks+=1
        # Inspect actual device helpers: DSB+ISB pairs bracket the sole 32-bit
        # load/store. Removing any barrier from the fixture must fail this gate.
        md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
        for name,op in [('p3uwread','ldr'),('p3uwwrite','str')]:
            at=sym[name];end=min(sym[k] for k in ('p3uwread','p3uwwrite','pi3updatewatchdogarm','pi3updatewatchdogstop') if sym[k]>at)
            ins=list(md.disasm(blob[at:end],base.LOAD+at))
            barriers=[i for i,x in enumerate(ins) if x.mnemonic in ('dsb','isb')]
            assert [ins[i].mnemonic for i in barriers]==['dsb','isb','dsb','isb']
            assert any(x.mnemonic==op and x.op_str.startswith('w') for x in ins[barriers[1]+1:barriers[2]])
            checks+=1
        print('pi3_update_boot_check PASS',checks,'checks; emitted admission/watchdog; no silicon claim')
        print('compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
if __name__=='__main__':main()
