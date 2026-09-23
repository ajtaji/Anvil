"""Run an already-counted cold candidate with fake MMIO, no new compilation."""
import pathlib,sys,argparse,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
p=argparse.ArgumentParser(description=__doc__);p.add_argument('image');p.add_argument('--repeat-only',action='store_true');args=p.parse_args()
image=pathlib.Path(args.image);data=image.read_bytes();a64=base.load_interpreter(base.INTERP)
syms={k:int(v,0) for k,v in (s.split('=',1) for s in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in s)}
def address(name):return syms[name] if name.startswith('global_') else 0x80000+syms[name]
assert syms['__bss_end__']<=0x1f0000,'BSS collides with reserved stack'
assert 0x80000+len(data)<=0x1f0000,'image collides with reserved stack'
def case(mode):
 class CPU(a64.A64):
  def __init__(self):super().__init__();self.tick=0;self.req=0;self.text=bytearray();self.pixels=0;self.led=[]
  def load(self,addr,size):
   if addr==0x3f003008:return 0
   # Ten-millisecond fake ticks keep the visible diagnostic delays faithful
   # in ordering while avoiding millions of interpreter-only spin iterations.
   if addr==0x3f003004:self.tick+=10000;return self.tick
   if addr in (0x3f201018,0x3f200004,0x3f00b898,0x3f00b8b8):return 0
   if addr==0x3f00b880:return self.req
   return super().load(addr,size)
  def store(self,addr,value,size):
   if 0x3b800000<=addr<0x3c800000:
    assert addr<0x3b800000+2560*480,'framebuffer write beyond allocation'
    self.pixels+=1;return
   if addr==0x3f201000:self.text.append(value&255);return
   if addr==0x3f00b8a0:
    self.req=value&0xffffffff;b=value&0x3ffffff0;tag=super().load(b+8,4)
    super().store(b+4,0x80000000,4)
    if tag==0x38041:
     assert super().load(b+12,4)==8 and super().load(b+16,4)==8,'bad status LED tag shape'
     assert super().load(b+20,4)==130,'Pi3 status LED must use firmware GPIO 130'
     state=super().load(b+24,4);assert state in (0,1),'invalid status LED state'
     self.led.append(state)
     super().store(b+16,0x80000008,4)
     super().store(b+20,130 if mode=='badled' else 0,4)
    elif tag==0x30002:super().store(b+16,0x80000008,4);super().store(b+24,48000000,4)
    elif tag==0x10005:super().store(b+16,0x80000008,4);super().store(b+20,0,4);super().store(b+24,0x100000 if mode=='smallram' else 0x8000000,4)
    else:
     assert super().load(b,4)==176 and super().load(b+172,4)==0,'bad framebuffer property envelope'
     for offset,length in ((8,8),(28,8),(48,4),(64,8),(84,8),(104,4),(120,4),(136,4),(152,8)):super().store(b+offset+8,0x80000000|length,4)
     # Model the normal 1 GiB split: VC owns the upper 76 MiB through
     # 0x40000000, while the returned framebuffer itself remains below the
     # BCM2837 peripheral window at 0x3f000000.  The former implementation
     # rejected this ordinary firmware response before drawing one pixel.
     super().store(b+96,0xfb800000,4);super().store(b+100,2560*480,4)
     super().store(b+116,128 if mode=='badpitch' else 2560,4)
     super().store(b+132,0 if mode=='bgr' else 1,4)
     super().store(b+148,0 if mode=='bgr' else 2,4)
     super().store(b+164,0x3b400000,4);super().store(b+168,0x4c00000,4)
     if mode=='baddepth':super().store(b+60,16,4)
     if mode=='badspan':super().store(b+100,4,4)
    return
   return super().store(addr,value,size)
 cpu=CPU()
 for n,b in enumerate(data):cpu.memory[0x80000+n]=b
 dtb=0x180000 if mode=='overlap' else 0x300000
 for n,b in enumerate((0 if mode=='badmagic' else 0xd00dfeed).to_bytes(4,'big')+(4096).to_bytes(4,'big')+bytes(32)):cpu.memory[dtb+n]=b
 cpu.enable_system_registers(el=2,preset={base.SCTLR_EL2:0x30c50830})
 cpu.pc=0x80000;cpu.sp=0;cpu.x[0]=dtb
 for n in range(20000000):
  if cpu.pc==address('pi3_cold_park'):break
  cpu.step()
 else:raise AssertionError('did not park')
 assert base.u64(cpu,address('global_pi3_dtb'))==dtb,'startup lost x0'
 validram=mode not in ('smallram','overlap','badmagic')
 validfb=validram and mode not in ('badpitch','baddepth','badspan')
 expected=2 if validfb else (2**64-5 if validram else 2**64-4)
 assert base.u64(cpu,address('global_pi3_boot_status'))==expected,(mode,cpu.text)
 assert (b'UART ready\r\n' in cpu.text)==validfb
 assert (b'ARM RAM verified' in cpu.text)==validfb
 assert (cpu.pixels>=307200)==validfb,(mode,cpu.pixels)
 if not validfb:assert cpu.pixels==0
 if mode=='badled':assert cpu.led,'optional LED diagnostic was not attempted'
 assert 0x1f0000<=cpu.sp<=0x200000
 if validfb:
  before=cpu.pixels;allocation=base.u64(cpu,address('global_pi3_fb'))
  cpu.pc=address('pi3fbinit');cpu.x[0]=dtb;cpu.x[1]=dtb+4096;cpu.x[30]=base.RETURN_PC
  for retry in range(500):
   if cpu.pc==base.RETURN_PC:break
   cpu.step()
  else:raise AssertionError('repeat init did not return')
  assert cpu.x[0]==0 and cpu.pixels==before
  assert base.u64(cpu,address('global_pi3_fb'))==allocation,'repeat init discarded allocation'
 return n
def repeat_gate():
 cpu=a64.A64()
 for n,b in enumerate(data):cpu.memory[0x80000+n]=b
 cpu.store(address('global_pi3_fb_attempted'),1,8)
 cpu.store(address('global_pi3_fb'),0x10000000,8)
 cpu.pc=address('pi3fbinit');cpu.sp=0x200000;cpu.x[30]=base.RETURN_PC
 before=dict(cpu.memory)
 for n in range(500):
  if cpu.pc==base.RETURN_PC:break
  cpu.step()
 else:raise AssertionError('repeat guard did not return')
 assert cpu.x[0]==0 and base.u64(cpu,address('global_pi3_fb'))==0x10000000
 error=address('global_pi3_fb_error')
 assert base.u64(cpu,error)==1,'repeat refusal did not report ownership'
 assert all(v==before.get(k) for k,v in cpu.memory.items() if not (0x1f0000<=k<0x200000 or error<=k<error+8)),'repeat guard changed state other than its error result'
 print('PASS: emitted repeat init refuses before allocation/MMIO changes;',n,'instructions')
repeat_gate()
if args.repeat_only:raise SystemExit(0)
steps=sum(case(m) for m in ('normal','bgr','badled','smallram','overlap','badmagic','badpitch','baddepth','badspan'))
print('PASS: 9 cold-entry cases,',steps,'instructions; preserved firmware x0; accepted RGB/BGR; validated framebuffer writes and Pi3 status LED protocol')
print('SHA256',hashlib.sha256(data).hexdigest())
