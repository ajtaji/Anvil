"""Execute the compiled RK3399 SD entry contract in the A64 model."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'a64'))
import a64_interp as model

def check(blob, *, quiet=False):
 cases=[(1,0,0),(2,0,0),(3,1,0),(3,4,0),(3,0x1000,0),(3,0,0),(3,0,1),(3,0x1005,0),(3,0x123456789abcdef1,0)]
 for el,control,timer_on in cases:
  c=model.A64();model.load_words(c,[int.from_bytes(blob[i:i+4],'little') for i in range(0,len(blob),4)],0x40000)
  c.enable_system_registers(el=el,preset={0xD51E1000:control,0xD51E1140:0x400})
  c.pc=0x40000;out=[];writes=[];read=c.load;write=c.store
  def load(a,n):
   if a==0xff1a0014:return 0x20
   if a==0xff8680bc:return timer_on
   return read(a,n)
  def store(a,v,n):
   writes.append((a,v,n))
   if a==0xff1a0000:out.append(v)
   else:write(a,v,n)
  c.load=load;c.store=store
  for _ in range(700):
   if c.pc==0x00041000:break
   c.step()
  good=el==3 and (control&5)==0
  assert (c.pc==0x00041000)==good,(el,control,hex(c.pc))
  report=b'SCTLR_EL3='+f'{control:016X}'.encode()+b'\r\n'
  if good:
   assert bytes(out).startswith(report),(el,hex(control),bytes(out))
   assert bytes(out)==report+b'ANVIL SD EL3\r\n',bytes(out)
   assert c.current_el==3 and c.sp==0x05000000
   assert c.x[:4]==[0x001C0000,0,0,0]
   assert c.sysreg(0xD51BE000)==24000000
   assert c.sysreg(0xD51E1000)&0x1005==0
   assert not c.sysreg(0xD51E1140)&0x400
   st=[x for x in writes if 0xff8680a0<=x[0]<0xff8680c0]
   assert len(st)==(0 if timer_on else 5),st
  elif el!=3:
   assert bytes(out)==b'' and not writes
  else:
   assert bytes(out)==report+b'!',(hex(control),bytes(out))
   assert not [x for x in writes if 0xff8680a0<=x[0]<0xff8680c0]
 if not quiet:
  print(f'PASS: {len(cases)} emitted entry cases: EL3 handoff, lower-EL/M-C refusal, I-only normalization, full SCTLR report, timer adoption')

if __name__=='__main__':check(Path(sys.argv[1]).read_bytes())
