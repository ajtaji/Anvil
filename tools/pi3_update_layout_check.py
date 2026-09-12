"""Inspect existing counted loader/updater artifacts; never builds/deploys."""
import hashlib,pathlib,re,struct,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import build
ROOT=base.ROOT

def main():
    a64=base.load_interp(base.INTERP)
    for name,file,load,bss,stack,end,bss_end in [
        ('loader','kernel8.img',0x80000,0x180000,0x200000,0x180000,0x1f0000),
        ('updater','anvil.img',0x200000,0x1100000,0x1f00000,0x1000000,0x1e00000)]:
        image=ROOT/build.TARGETS['pi3-'+name]['output']
        raw=image.read_bytes();pmf=image.with_suffix(image.suffix+'.pmf').read_bytes();sym=base.parse_symbols(image)
        magic,version,hlen,where,entry,size,bwhere,bsize,flags,reserved=struct.unpack_from('<8sIIQQQQQII',pmf)
        assert (magic,version,hlen,where,entry,size,bwhere,flags,reserved)==(b'PMFBOOT\0',2,128,load,load,len(raw),bss,0,0)
        arch,target,pmf_stack=struct.unpack_from('<IIQ',pmf,96)
        assert (arch,target,pmf_stack)==(1,2837,stack)
        assert pmf[112:128]==bytes(16)
        assert pmf[128:]==raw and pmf[64:96]==hashlib.sha256(raw).digest()
        assert load+len(raw)<=end and bsize>=0 and bss+bsize<=bss_end
        assert sym['__bss_start__']==bss and sym['__bss_end__']==bss+bsize
        source=(ROOT/'RaspberryPi3/Board'/f'{name}.pi3').read_text()
        for directive,value in [('LoadAddress',load),('BssAddress',bss),('StackAddress',stack)]:
            assert re.search(r'^'+directive+r'\s+\$'+f'{value:X}'+r'\s*$',source,re.M|re.I)
        cpu=a64.A64();cpu.memory={load+i:b for i,b in enumerate(raw)};cpu.pc=load;cpu.x[0]=0x1000000
        for i in range(bsize):cpu.memory[bss+i]=0xa5
        cpu.enable_system_registers(el=2,preset={0xD51C1000:0,0xD51B4220:0x3c0})
        for n in range(1000000):
            if cpu.pc==load+sym['main']:break
            cpu.step()
        else:raise AssertionError('cold startup did not reach Main')
        assert cpu.sp==stack and cpu.x[0]==0x1000000
        # Constant global initializers legitimately follow BSS clearing (e.g.
        # slot=-1). Compare to the same startup from clean BSS, not all-zero.
        clean=a64.A64();clean.memory={load+i:b for i,b in enumerate(raw)};clean.pc=load;clean.x[0]=0x1000000
        clean.enable_system_registers(el=2,preset={0xD51C1000:0,0xD51B4220:0x3c0})
        for _ in range(1000000):
            if clean.pc==load+sym['main']:break
            clean.step()
        else:raise AssertionError('clean startup failed')
        assert all(cpu.memory.get(bss+i,0)==clean.memory.get(bss+i,0) for i in range(bsize))
        print(name,'PASS cold startup/DTB/BSS/stack/layout;',len(raw),'bytes; SHA256',hashlib.sha256(raw).hexdigest())
    print('pi3_update_layout_check PASS; existing counted images only, no hardware')
if __name__=='__main__':main()
