"""BCM2837 SDHOST actual-emission PIO gate, explicit fake controller/card."""
import argparse,hashlib,os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
ROOT=base.ROOT
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi3-sdhost-') as tmp:
        image=pathlib.Path(tmp)/'sd.img';env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([args.compiler,'--compile','RaspberryPi3/Tests/sdhost_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
        if r.returncode or not image.exists():raise AssertionError(r.stdout+r.stderr)
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP);checks=0
        class SD(a64.A64):
            def __init__(self,mode='normal',el=2,affinity=0):
                super().__init__();self.mode=mode;self.device_regs={};self.ticks=0;self.command=-1;self.words=0;self.writes=[];self.data=[]
                self.memory={base.LOAD+i:b for i,b in enumerate(blob)};self.sp=base.STACK
                self.enable_system_registers(el=el,preset={0xD51800A0:affinity,0xD51C1000:0,0xD51E1000:0,0xD51B4220:0x3c0})
            def load(self,addr,size):
                if addr==0x3f003008:return 0
                if addr==0x3f003004:self.ticks+=1000;return self.ticks
                if addr in (0x3f200010,0x3f200014):return 0xffffffff
                if 0x3f202000<=addr<=0x3f202050:
                    assert size==4,'MMIO width';off=addr-0x3f202000
                    if off==0:return 0x8000 if self.mode=='command-timeout' and self.command==8 else self.command&63
                    if off==0x20:
                        if self.mode=='crc' and self.command==17:return 0x20
                        return 0x400 if self.command==7 and self.mode!='busy-timeout' else 0
                    if off==0x34:
                        if self.command==17 and self.words<128:return 2|(8<<4)
                        if self.command==24 and self.words<128:return 3
                        return 1
                    if off==0x40:self.words+=1;return 0xa5000000+self.words-1
                    if off==0x10:
                        return {8:0x1aa,55:0x20,41:0x80ff8000 if self.mode=='sdsc' else 0xc0ff8000,3:0x12340000,13:0xe00 if self.mode=='program-timeout' else 0x900}.get(self.command,0)
                    if off==0x14:return (0x34560000 if self.mode=='wide-csd' else 2047<<16) if self.command==9 else 0
                    if off==0x18:return 0x12 if self.command==9 and self.mode=='wide-csd' else 0
                    if off==0x1c:return 0x40000000 if self.command==9 and self.mode!='bad-csd' else 0
                    return self.device_regs.get(off,0)
                return super().load(addr,size)
            def store(self,addr,value,size):
                if 0x3f000000<=addr<0x40000000:
                    assert size==4,'MMIO width';self.writes.append((addr,value&0xffffffff))
                    if 0x3f202000<=addr<=0x3f202050:
                        off=addr-0x3f202000;self.device_regs[off]=value&0xffffffff
                        if off==0 and value&0x8000:self.command=value&63;self.words=0
                        if off==0x40:self.data.append(value&0xffffffff);self.words+=1
                    return
                assert not 0xfe000000<=addr<0xff000000,'Pi4 alias touched'
                return super().store(addr,value,size)
            def call(self,name,*args):
                self.pc=base.LOAD+sym[name.lower()];self.x[30]=base.RETURN_PC
                for i,v in enumerate(args):self.x[i]=v
                for n in range(3000000):
                    if self.pc==base.RETURN_PC:return self.x[0]
                    self.step()
                raise AssertionError('unbounded '+name)
        c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1;checks+=1
        assert c.call('Pi3SdBlockCount')==2097152;checks+=1
        assert (0x3f200010,0xe4ffffff) in c.writes and (0x3f200014,0xfffff924) in c.writes;checks+=1
        b=sym['global_sd_gate_buffer'];assert c.call('Pi3SdReadBlock',42,b)==1;checks+=1
        assert all(c.load(b+i*4,4)==0xa5000000+i for i in range(128));checks+=128
        assert c.call('Pi3SdSetWriteWindow',40,10)==1
        assert c.call('Pi3SdWriteBlock',42,b)==1 and c.data==[0xa5000000+i for i in range(128)];checks+=2
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==0;checks+=1
        c=SD('wide-csd');assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        assert c.call('Pi3SdBlockCount')==(0x123456+1)*1024;checks+=1
        for mode in ('command-timeout','busy-timeout','sdsc','program-timeout','bad-csd'):
            c=SD(mode);assert c.call('Pi3SdInit',400000000,0,0x8000000)==0,mode;checks+=1
        c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        c.mode='crc';assert c.call('Pi3SdReadBlock',42,b)==0
        count=len(c.writes);assert c.call('Pi3SdWriteBlock',42,b)==0 and len(c.writes)==count;checks+=2
        for el,aff in ((1,0),(2,0x100),(2,1<<32)):
            c=SD(el=el,affinity=aff);assert c.call('Pi3SdInit',400000000,0,0x8000000)==0 and not c.writes;checks+=1
        for lba in (39,50,2097152):
            c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
            assert c.call('Pi3SdSetWriteWindow',40,10)==1
            before=len(c.writes);assert c.call('Pi3SdWriteBlock',lba,b)==0 and len(c.writes)==before;checks+=1
        print('pi3_sdhost_check PASS',checks,'checks; real emitted MMIO/PIO, seven refusal cases; no silicon claim')
        print('compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
if __name__=='__main__':main()
