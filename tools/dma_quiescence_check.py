"""Execute legacy DMA completion/quarantine and display refusal on a register model."""
import argparse, os, pathlib, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
from a64_interp import A64
import build_count
LOAD,BSS,STACK,RETURN=0x400000,0x800000,0x3000000,0x7000000
BASE=0xfe007000
def main():
 p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
 with tempfile.TemporaryDirectory(prefix='dma-quiescence-') as td:
  image=pathlib.Path(td)/'gate.img';src=ROOT/'RaspberryPi4/Tests/dma_quiescence.pi4'
  r=subprocess.run([a.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(LOAD),'--bss-addr',hex(BSS),'--stack-addr',hex(STACK),'-s','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
  assert r.returncode==0 and image.exists(),r.stdout+r.stderr
  build_count.record_build(src,'pi4',image,by='tools/dma_quiescence_check.py',compiler=a.compiler)
  symbols={k:int(v,0) for k,v in (l.split('=',1) for l in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in l)}
  class Model:
   def __init__(self,mode):
    self.c=A64();self.c.memory.update({LOAD+i:b for i,b in enumerate(image.read_bytes())})
    self.mode=mode;self.t=0;self.paused=False;self.reset=False;self.writes=[];self.memwrites=[]
    ld,st=self.c.load,self.c.store
    def load(addr,size):
     if addr==BASE:
      if self.reset:return 1 if self.mode=='reset-stuck' else 0
      if self.mode=='active-stuck':return 1
      if self.paused:return 0x50 if self.mode=='writes-stuck' else 0x10
      if self.mode=='error':return 0x100
      if self.t<2000:return 1
      if self.t<7000:return 0x40
      return 2
     if addr==BASE+32:
      if self.reset:return 0
      if self.mode=='writes-stuck':return 0x20
      if self.mode=='error' and not self.paused:return 4
      return 0x10 if not self.paused and 2000<=self.t<7000 else 0
     return ld(addr,size)
    def store(addr,val,size):
     if BASE<=addr<BASE+256:
      assert size==4;self.writes.append((self.t,addr-BASE,val))
      if addr==BASE and val&0x80000000:
       assert self.mode not in ('active-stuck','writes-stuck'),'RESET erased unresolved transfer evidence'
       self.reset=True
      elif addr==BASE and val==0x10000000:self.paused=True
      return
     if 0xa00000<=addr<0xa20000:self.memwrites.append((addr,val,size))
     st(addr,val,size)
    self.c.load,self.c.store=load,store
   def set(self,name,value):self.c.store(symbols['global_'+name],value,8)
   def call(self,name,*args):
    c=self.c;c.pc=LOAD+symbols[name.lower()];c.sp=STACK;c.x[30]=RETURN
    for i,v in enumerate(args):c.x[i]=v
    for _ in range(200000):
     if c.pc==RETURN:return c.x[0]
     ins=c.load(c.pc,4);op=ins&0xffffffe0
     if op==0xd53be000:c.x[ins&31]=1000000;c.pc+=4
     elif op==0xd53be020:c.x[ins&31]=self.t;c.pc+=4
     else:c.step()
     self.t+=10
    raise AssertionError('gate failed to return')
  checks=0
  def check(x):
   nonlocal checks
   assert x;checks+=1
  t=Model('normal');check(t.call('DmaWait',20000)==1);check(t.t>=7000);check(not t.writes)
  t=Model('error');check(t.call('DmaWait',20000)==0);check(t.reset);check(t.call('DmaQuarantined')==0)
  for mode in ('active-stuck','writes-stuck'):
   t=Model(mode);check(t.call('DmaWait',20000)==0);check(t.call('DmaQuarantined')==1);check(not t.reset)
   check(t.call('DmaSetChannel',2)==0);check(t.call('DmaSetScratch',0x900000,512)==0)
   check(t.call('DmaSetBounds',0xa00000,4096)==0);check(t.call('DmaInit')==0)
   # A caller disabling acceleration cannot bypass quarantine.
   t.set('dsp_ready',1);t.set('dsp_base',0xa00000);t.set('dsp_size',4096)
   t.set('dsp_w',16);t.set('dsp_h',16);t.set('dsp_pitch',64);t.set('dsp_bpp',4)
   t.call('DisplayUseDma',0);check(t.call('DisplayMemorySafe')==0);check(t.call('DisplayBase')==0)
   check(t.call('DisplayGetPixel',0,0)==(1<<64)-1)
   for name,args in [('DisplayFillRect',(0,0,2,2,1)),('DisplayPixel',(0,0,1)),('DisplayCopyRect',(0,0,1,1,1,1)),('DisplayBlit',(0xa10000,8,0,0,2,2)),('DisplayChar',(0,0,65,1,0)),('DisplayCharClear',(0,0,65,1)),('DisplayFlush',())]:t.call(name,*args)
   check(not t.memwrites)
   # Explicit recovery is allowed only when the same channel really drains.
   t.mode='normal';check(t.call('DmaAbort')==1);check(t.call('DmaQuarantined')==0)
   check(t.call('DisplayMemorySafe')==1)
   t.call('DisplayFillRect',0,0,2,2,0x12345678)
   check(bool(t.memwrites))
  t=Model('reset-stuck');check(t.call('DmaAbort')==0);check(t.call('DmaQuarantined')==1)
  check(t.writes[-1][2]==0x80000000) # no sticky flag clear after failed reset
  for duration in (0,(1<<64)-1,0x80000000):
   for mode in ('normal','active-stuck'):
    t=Model(mode);check(t.call('DmaWait',duration)==0)
    check(t.call('DmaQuarantined')==int(mode=='active-stuck'))
  print(f'PASS: {checks} emitted completion/drain/quarantine/display refusal assertions.')
  # Compile the old ACTIVE-only completion policy as a negative control.
  production=(ROOT/'RaspberryPi4/Lib/dma.pi4').read_text()
  old='ElseIf (cs & (#DMA_CS_ACTIVE | #DMA_CS_WAITING | #DMA_CS_END)) = #DMA_CS_END And (dbg & #DMA_DEBUG_WRITES) = 0'
  assert production.count(old)==1
  lib=pathlib.Path(td)/'mutant_dma.pi4';lib.write_text(production.replace(old,'ElseIf (cs & #DMA_CS_ACTIVE) = 0'))
  mut=pathlib.Path(td)/'mutant.pi4';mut.write_text(src.read_text().replace('"RaspberryPi4/Lib/dma.pi4"','"'+lib.as_posix()+'"'))
  image=pathlib.Path(td)/'mutant.img'
  r=subprocess.run([a.compiler,'--compile',str(mut),'-t','pi4','--entry-returns','--load-addr',hex(LOAD),'--bss-addr',hex(BSS),'--stack-addr',hex(STACK),'-s','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
  assert r.returncode==0 and image.exists(),r.stdout+r.stderr
  build_count.record_build(mut,'pi4',image,by='tools/dma_quiescence_check.py',compiler=a.compiler)
  symbols={k:int(v,0) for k,v in (l.split('=',1) for l in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in l)}
  t=Model('normal');assert t.call('DmaWait',20000)==1 and t.t<7000
  print('PASS: ACTIVE-only mutation violates the required final-write completion boundary.')
  display=(ROOT/'RaspberryPi4/Lib/display.pi4').read_text()
  guard='If DmaQuarantined() <> 0 : ProcedureReturn 0 : EndIf'
  assert display.count(guard)==1
  lib=pathlib.Path(td)/'mutant_display.pi4';lib.write_text(display.replace(guard,'If 0 <> 0 : ProcedureReturn 0 : EndIf'))
  mut=pathlib.Path(td)/'mutant_display_gate.pi4';mut.write_text(src.read_text().replace('"RaspberryPi4/Lib/display.pi4"','"'+lib.as_posix()+'"'))
  image=pathlib.Path(td)/'mutant_display.img'
  r=subprocess.run([a.compiler,'--compile',str(mut),'-t','pi4','--entry-returns','--load-addr',hex(LOAD),'--bss-addr',hex(BSS),'--stack-addr',hex(STACK),'-s','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
  assert r.returncode==0 and image.exists(),r.stdout+r.stderr
  build_count.record_build(mut,'pi4',image,by='tools/dma_quiescence_check.py',compiler=a.compiler)
  symbols={k:int(v,0) for k,v in (l.split('=',1) for l in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in l)}
  t=Model('active-stuck');assert t.call('DmaWait',20000)==0
  assert t.call('DmaQuarantined')==1
  for key,v in [('dsp_ready',1),('dsp_base',0xa00000),('dsp_size',4096),('dsp_w',16),('dsp_h',16),('dsp_pitch',64),('dsp_bpp',4)]:t.set(key,v)
  t.call('DisplayUseDma',0);t.call('DisplayFillRect',0,0,2,2,1)
  assert t.memwrites,'caller guard mutation did not exercise unsafe framebuffer writes'
  print('PASS: removed quarantine guard allows forbidden CPU writes and is detected.')
if __name__=='__main__':main()
