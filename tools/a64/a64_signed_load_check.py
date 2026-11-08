"""Raw ARM DDI0596 integer unsigned-offset loads: value, width and no stores.

Instruction bases are fixed from the architecture encoding diagrams, independent
of the compiler/assembler. In particular B9800020 is LDRSW X0,[X1], not STR.
https://support.arm.com/documentation/ddi0596/2020-12/Base-Instructions/LDRSW--immediate---Load-Register-Signed-Word--immediate--?lang=en
"""
import a64_interp as A


def check(cpu_type=A.A64):
    count=0
    # name, encoding with Rn/Rt zero, access bytes, signed, destination bits.
    for name,base,size,signed,bits in [('LDRSB-X',0x39800000,1,True,64),('LDRSB-W',0x39C00000,1,True,32),('LDRSH-X',0x79800000,2,True,64),('LDRSH-W',0x79C00000,2,True,32),('LDRSW-X',0xB9800000,4,True,64),('LDRB',0x39400000,1,False,32),('LDRH',0x79400000,2,False,32),('LDR-W',0xB9400000,4,False,32),('LDR-X',0xF9400000,8,False,64)]:
        for value in (0,1,(1<<(size*8-1))-1,1<<(size*8-1),(1<<(size*8))-1):
            for rn,rt in ((1,0),(31,7),(2,2),(1,31)):
                for units in (0,17):
                    cpu=cpu_type();cpu.pc=0x1000;cpu.sp=0x8000;cpu.x=[0xA5A5A5A5A5A5A5A5]*31
                    if rn!=31:cpu.x[rn]=0x8000
                    word=base|(units<<10)|(rn<<5)|rt;target=0x8000+units*size
                    cpu.raw_store(0x1000,word,4);cpu.raw_store(target,value,size)
                    before=dict(cpu.memory);reads=[];stores=[];load=cpu.load;store=cpu.store
                    def observe_load(addr,n):
                        reads.append((addr,n));return load(addr,n)
                    def observe_store(addr,v,n):
                        stores.append((addr,v,n));return store(addr,v,n)
                    cpu.load=observe_load;cpu.store=observe_store;cpu.step()
                    expected=int.from_bytes(value.to_bytes(size,'little'),'little',signed=signed)&((1<<bits)-1)
                    if rt!=31:assert cpu.x[rt]==expected,(name,value,rn,rt,units,hex(cpu.x[rt]),hex(expected))
                    assert cpu.memory==before and not stores,('load wrote memory',name,value,stores)
                    assert (target,size) in reads and cpu.sp==0x8000,(name,reads,cpu.sp)
                    count+=1
    for word in (0xF9800020,0xB9C00020,0xF9C00020):
        cpu=cpu_type();cpu.pc=0x1000;cpu.raw_store(0x1000,word,4);before=dict(cpu.memory)
        try:cpu.step()
        except RuntimeError:pass
        else:raise AssertionError(('prefetch/reserved was not refused',hex(word)))
        assert cpu.memory==before
        count+=1
    return count


def main():
    count=check();killed=0
    for defect in ('store','zero-extend'):
        class Broken(A.A64):
            def step(self):
                word=self.raw_load(self.pc,4)
                if word & 0xFFC00000==0xB9800000:
                    rt=word&31;rn=(word>>5)&31;addr=(self.sp if rn==31 else self.x[rn])+((word>>10)&4095)*4
                    if defect=='store':self.store(addr,self.reg(rt,0),4)
                    else:self.put(rt,self.load(addr,4),1)
                    self.pc+=4
                else:super().step()
        try:check(Broken)
        except AssertionError:killed+=1
        else:raise AssertionError('missed signed-load defect: '+defect)
    print('PASS A64 signed/unsigned load oracle: %d raw-word cases; memory preserved, W/X/SP/ZR/alias/offset/sign bounds; %d/2 defects rejected'%(count,killed))


if __name__=='__main__':main()
