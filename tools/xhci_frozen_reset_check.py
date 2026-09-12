"""Execute frozen full-monitor reset bytes; model only device and counter."""
import argparse, pathlib, sys, hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
from a64_interp import A64
BASE=0x200000; STOP=0xdead0000; OP=0x600000040
def run(data,symbols,mode):
 c=A64();c.memory.update({BASE+i:v for i,v in enumerate(data)})
 c.sp=0x7000000;c.x[29]=0x12345678;c.x[30]=STOP;c.pc=BASE+symbols['xh_reset']
 load=c.load;store=c.store;state={'ticks':0,'reset':False,'writes':0,'reset_writes':0}
 def rd(addr,size):
  if OP<=addr<OP+0x100:
   assert size==4,('MMIO width',size)
   if addr==OP+4:
    if mode=='initial_cnr' or (mode=='post_cnr' and state['reset']):return 0x801
    return 0 if mode=='halt_stuck' else 1
   if addr==OP:return 2 if state['reset'] and mode=='reset_stuck' else (1 if mode=='halt_stuck' else 0)
   return 0
  return load(addr,size)
 def wr(addr,val,size):
  if OP<=addr<OP+0x100:
   assert size==4
   state['writes']+=1
   if addr==OP and val&2:
    state['reset']=True;state['reset_writes']+=1
  else:store(addr,val,size)
 c.load=rd;c.store=wr
 store(symbols['global_xh_op'],OP,8);store(symbols['global_xh_hz'],54000000,8)
 for steps in range(500000):
  if c.pc==STOP:break
  ins=load(c.pc,4)
  if ins&0xffffffe0==0xd53be020:
   state['ticks']+=54000;c.x[ins&31]=state['ticks'];c.pc+=4
  else:c.step()
 else:raise AssertionError(('did not return',mode,hex(c.pc)))
 assert c.x[0]==(1 if mode=='ready' else 0),(mode,c.x[0])
 assert c.sp==0x7000000 and c.x[29]==0x12345678,('frame damaged',mode)
 expected={'ready':0,'initial_cnr':14,'halt_stuck':12,'reset_stuck':13,'post_cnr':14}[mode]
 assert load(symbols['global_xh_err'],8)==expected,('wrong error',mode,load(symbols['global_xh_err'],8))
 assert state['reset_writes']==(0 if mode in ('initial_cnr','halt_stuck') else 1),('reset ownership',mode,state)
 if mode=='initial_cnr':assert state['writes']==0
 return steps,state

def main():
 p=argparse.ArgumentParser();p.add_argument('image');a=p.parse_args()
 image=pathlib.Path(a.image);data=image.read_bytes()
 symbols={k:int(v) for k,v in (s.split('=',1) for s in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in s)}
 for mode in ('ready','initial_cnr','halt_stuck','reset_stuck','post_cnr'):
  print(mode,'PASS',run(data,symbols,mode))
 # Mutate only an in-memory copy: invert the signed expiry branch in
 # xh_Expired, making the actual emitted function refuse too early.
 start=symbols['xh_expired'];end=symbols['xh_delayms']
 candidates=[off for off in range(start,end,4) if int.from_bytes(data[off:off+4],'little')&0xff00001f==0x5400000b]
 assert len(candidates)==1,('expiry branch identification',candidates)
 mutant=bytearray(data);off=candidates[0];word=int.from_bytes(mutant[off:off+4],'little')
 mutant[off:off+4]=(word^1).to_bytes(4,'little')
 # The stuck-CNR path still returns the same failure, so also assert the
 # real counter deadline was reached rather than accepting early expiry.
 for blob in (data,):
  _,state=run(blob,symbols,'initial_cnr');assert state['ticks']>=13500000
 try:
  _,state=run(mutant,symbols,'initial_cnr')
  assert state['ticks']>=13500000,('early timeout',state)
 except AssertionError as err:print('PASS in-memory inverted expiry mutation rejected:',err)
 else:raise AssertionError('expiry mutant survived')
 print('Frozen SHA256',hashlib.sha256(data).hexdigest())
if __name__=='__main__':main()
