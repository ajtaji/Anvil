"""Physical handshake sent-history checks against an independent packet ledger."""
from pathlib import Path
import argparse,hashlib,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/quic_handshake_sent.pbi','Anvil/Network/quic_handshake_frames.pbi','Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 steps=[];cases=[];slots=[];capacity=0;level=0;last=-1;lasttime=0;first=0
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def fnv(b):
  h=2166136261
  for x in b:h=((h^x)*16777619)&0xffffffff
  return h
 def observe(name):
  acked=[i for i,x in enumerate(slots) if x[0]&16]
  values={'first':first,'issued':len(slots),'lastSent':last,'lastTime':lasttime,'acked':len(acked),'largestAcked':max(acked,default=-1),'inFlight':sum(x[1] for x in slots if x[0]&8),'level':level,'capacity':capacity}
  for f,v in values.items():check(name+' '+f,'s\\'+f,v)
  raw=b''.join(struct.pack('<4q',*x) for x in slots)
  if first:
   ring=[b'\xa5'*32 for _ in range(capacity)]
   for n,x in enumerate(slots):ring[n%capacity]=bytes(32) if n<first else struct.pack('<4q',*x)
   raw=b''.join(ring)
  check(name+' exact slots',f'Hash(@storage[16],{len(raw)})',fnv(raw))
  check(name+' prefix guard','Hash(@storage[0],16)',fnv(b'\xa5'*16))
  check(name+' suffix guard',f'Hash(@storage[{16+capacity*32}],16)',fnv(b'\xa5'*16))
 def init(cap=128,lev=0):
  nonlocal slots,capacity,level,last,lasttime,first
  code('If s\\phase=1 : rc=QuicHandshakeSentDiscard(@s) : EndIf\nFor i=0 To 131103 : storage[i]=$A5 : Next')
  check('initialize',f'QuicHandshakeSentInit(@s,{lev},@storage[16],{cap})',0)
  slots=[];capacity=cap;level=lev;last=-1;lasttime=0;first=0
 def reserve():
  n=len(slots);check('reserve', 'QuicHandshakeSentReserve(@s)', n if n-first<capacity else -3463)
  if n-first<capacity:slots.append([1,0,0,0])
 def commit(n,size=1200,time=None,eliciting=1,padded=0):
  nonlocal last,lasttime
  time=n+100 if time is None else time
  if n<0 or size<1 or size>65527 or time<0 or eliciting not in (0,1) or padded not in (0,1):want=-3461
  elif n>=len(slots):want=-3465
  elif n<first or slots[n][0]!=1 or n<=last or time<lasttime:want=-3462
  else:
   want=0;slots[n]=[2+eliciting*4+8*int(bool(eliciting or padded)),size,time,n+70];last=n;lasttime=time
  check('commit',f'QuicHandshakeSentCommit(@s,{n},{size},{time},{eliciting},{padded},{n+70})',want)
 def lost(n):
  if n<0:want=-3461
  elif n>=len(slots) or not slots[n][0]&2:want=-3465
  elif slots[n][0]&48:want=0
  else:want=1;slots[n][0]=(slots[n][0]|32)&~8
  check('loss',f'QuicHandshakeSentLost(@s,{n})',want)
 def prepare(numbers,ecn=False,mutation=''):
  groups=[]
  for n in sorted(numbers):
   if groups and groups[-1][1]+1==n:groups[-1][1]=n
   else:groups.append([n,n])
  groups.reverse();b=vi(3 if ecn else 2)+vi(groups[0][1])+vi(0)+vi(len(groups)-1)+vi(groups[0][1]-groups[0][0])
  for (prev,_),(lo,hi) in zip(groups,groups[1:]):b+=vi(prev-hi-2)+vi(hi-lo)
  if ecn:b+=vi(100)+vi(2)+vi(1)
  code('For i=0 To 1099 : wire[i]=0 : Next')
  for i,v in enumerate(b):code(f'wire[{i}]={v}')
  check('decode ACK',f'QuicHandshakeFrameRead(@wire[0],{len(b)},{2 if level==4 else level},@frame)',len(b))
  if mutation:code(mutation)
  check('begin ACK',f'QuicHandshakeSentAckBegin(@job,@s,{level},@frame)',0)
 def apply(numbers,limit=None):
  fresh=[n for n in sorted(numbers,reverse=True) if n>=first and not slots[n][0]&16]
  if limit is not None:fresh=fresh[:limit]
  byte_sum=sum(slots[n][1] for n in fresh);flight=sum(slots[n][1] for n in fresh if slots[n][0]&8)
  cookie_sum=sum(slots[n][3] for n in fresh);time_sum=sum(slots[n][2] for n in fresh)
  # Event order matters, including ACKs for packets already declared lost.
  digest=fnv(b''.join(struct.pack('<6q',n,slots[n][1],slots[n][2],slots[n][3],slots[n][0],slots[n][1] if slots[n][0]&8 else 0) for n in fresh))
  for n in fresh:slots[n][0]=(slots[n][0]|16)&~8
  return len(fresh),byte_sum,flight,cookie_sum,time_sum,digest
 def ack(numbers,ecn=False,mutation='',error=None):
  prepare(numbers,ecn,mutation)
  if error is None and any(n>=len(slots) or not slots[n][0]&2 for n in numbers):error=-3465
  values=(0,0,0,0,0,2166136261) if error else apply(numbers)
  code('rc=RunAck(0)');check('ACK terminal','rc',error or 2)
  for f,v in zip(['events','byteSum','flightSum','cookieSum','timeSum','eventHash'],values):check('events '+f,f,v)
  check('lock released','s\\busy',0);observe('after ACK')
 init(8)
 reserve();commit(0);reserve();reserve();commit(2,100,eliciting=0);reserve();commit(3,500,eliciting=0,padded=1);lost(3)
 ack({0,2,3},True);ack({0,2,3});lost(3)
 reserve();commit(4);reserve();commit(5);ack({1,4,5});ack({7});ack({(1<<62)-1})
 reserve();reserve();commit(7);commit(6);reserve();commit(8);commit(7);commit(6,time=1);commit(6,size=0);lost(6)
 observe('refusals unchanged')
 init(128,2)
 code('For i=0 To 127\n rc=QuicHandshakeSentReserve(@s)\n If i>0 : rc=QuicHandshakeSentCommit(@s,i,1200,100+i,1,0,70+i) : EndIf\nNext')
 slots=[[1,0,0,0]]+[[14,1200,100+i,70+i] for i in range(1,128)];last=127;lasttime=227
 prepare(set(range(128)));check('validation bounded first step','QuicHandshakeSentAckStep(@job)',0)
 check('no early ACK','s\\acked',0);check('busy reserve','QuicHandshakeSentReserve(@s)',-3464)
 check('busy loss','QuicHandshakeSentLost(@s,127)',-3464);check('busy discard','QuicHandshakeSentDiscard(@s)',-3464)
 check('busy commit','QuicHandshakeSentCommit(@s,0,1200,999,1,0,70)',-3464)
 check('busy other job','QuicHandshakeSentAckBegin(@other,@s,2,@frame)',-3464)
 code('rc=RunAck(0)');check('late unsent refuses all','rc',-3465);check('no partial events','events',0);observe('late refusal atomic')
 prepare({127});check('cancel validation','QuicHandshakeSentAckCancel(@job)',-3467);check('cancel remains terminal','QuicHandshakeSentAckStep(@job)',-3467);observe('cancel unchanged')
 prepare(set(range(1,128)));code('rc=RunAck(1)');check('first application event','rc',1)
 values=apply(set(range(1,128)),1)
 for f,v in zip(['events','byteSum','flightSum','cookieSum','timeSum','eventHash'],values):check('partial '+f,f,v)
 check('cancel application','QuicHandshakeSentAckCancel(@job)',-3467);observe('partial application retained')
 ack(set(range(1,128)),mutation='frame\\count=frame\\count+1',error=-3466)
 ack({127},mutation='frame\\rangeBytes=frame\\rangeBytes+1',error=-3466)
 ack({127},mutation='PokeA(frame\\ranges,255)',error=-3466)
 for expr in ['QuicHandshakeSentInit(@s,1,@storage[16],128)','QuicHandshakeSentInit(@s,0,@storage[16],4097)','QuicHandshakeSentInit(@s,0,@s,1)','QuicHandshakeSentAckBegin(@other,@s,0,@frame)']:
  check('invalid admission',expr,-3461)
 check('active reinit','QuicHandshakeSentInit(@s,2,@storage[16],128)',-3462)
 init(4096)
 code('For i=0 To 4095\n rc=QuicHandshakeSentReserve(@s)\n rc=QuicHandshakeSentCommit(@s,i,1200,100+i,1,0,70+i)\nNext')
 slots=[[14,1200,100+i,70+i] for i in range(4096)];last=4095;lasttime=4195
 reserve();ack(set(range(4096)));ack(set(range(4096)))

 def prune(budget=64):
  nonlocal first
  old=first
  while first<len(slots) and first-old<budget and slots[first][0]&18==18:first+=1
  check('prune exact count',f'QuicHandshakeSentPrune(@s,{budget})',first-old)
  observe('pruned')
 init(4,4)
 for _ in range(4):reserve();commit(len(slots)-1)
 reserve();ack({1,2,3});prune();ack({0});prune(2)
 commit(0);lost(0)
 for _ in range(2):reserve();commit(len(slots)-1)
 ack(set(range(6)));prune()
 for cycle in range(12):
  for _ in range(4):reserve();commit(len(slots)-1)
  ack(set(range(len(slots))))
  prepare({len(slots)-1});check('busy prune','QuicHandshakeSentPrune(@s,64)',-3464)
  check('cancel duplicate validation','QuicHandshakeSentAckCancel(@job)',-3467)
  prune(3);prune(1)
 check('bad prune zero','QuicHandshakeSentPrune(@s,0)',-3461)
 check('bad prune budget','QuicHandshakeSentPrune(@s,65)',-3461)
 reserve();reserve();commit(len(slots)-1);ack({len(slots)-1});prune()
 ack({len(slots)-2,len(slots)-1});prune()

 def loss_scan(now,delay=1000,threshold=3,stop_after=0):
  acked=[n for n,x in enumerate(slots) if x[0]&16]
  newest=max(acked,default=-1);victims=[];deadlines=[]
  for n,x in enumerate(slots):
   sent,flight,done,lost=bool(x[0]&2),bool(x[0]&8),bool(x[0]&16),bool(x[0]&32)
   if n>=first and n<newest and sent and flight and not done and not lost:
    if newest-n>=threshold or now-x[2]>=delay:victims.append(n)
    else:deadlines.append(min((1<<63)-1,x[2]+delay))
  if stop_after:victims=victims[:stop_after]
  rows=[(n,*slots[n][1:],slots[n][0],slots[n][1]) for n in victims]
  # rows are PN,bytes,time,cookie,previous flags,removed flight bytes.
  digest=fnv(b''.join(struct.pack('<6q',*row) for row in rows))
  values=[len(rows),sum(r[1] for r in rows),sum(r[5] for r in rows),sum(r[3] for r in rows),sum(r[2] for r in rows),digest]
  check('begin loss scan',f'QuicHandshakeSentLossBegin(@lossJob,@s,{now},{delay},{threshold})',0)
  code(f'rc=RunLoss({stop_after})');check('loss terminal','rc',1 if stop_after and rows else 2)
  for f,v in zip(['events','byteSum','flightSum','cookieSum','timeSum','eventHash'],values):check('loss events '+f,f,v)
  for n in victims:slots[n][0]=(slots[n][0]|32)&~8
  if stop_after and rows:
   check('cancel loss after event','QuicHandshakeSentLossCancel(@lossJob)',-3467)
   check('cancel loss terminal','QuicHandshakeSentLossStep(@lossJob)',-3467)
  else:
   check('loss next deadline','lossJob\\nextTime',min(deadlines,default=0))
   check('loss terminal repeat','QuicHandshakeSentLossStep(@lossJob)',2)
  check('loss unlocked','s\\busy',0);observe('loss ledger')
 init(8,4)
 for _ in range(6):reserve();commit(len(slots)-1)
 loss_scan(500);ack({3});loss_scan(500);prune();loss_scan(1100);loss_scan(1101);loss_scan(1102);loss_scan(20000)
 ack({0});loss_scan(20000);ack({5});loss_scan(20000);ack(set(range(6)));prune()
 init(8,2)
 reserve();commit(0,eliciting=0);reserve();commit(1,500,eliciting=0,padded=1);reserve();reserve();commit(3)
 ack({3});loss_scan(500);loss_scan(1101);ack({2},error=-3465)
 init(128,0)
 for _ in range(128):reserve();commit(len(slots)-1)
 loss_scan(227);ack({127})
 check('begin bounded loss','QuicHandshakeSentLossBegin(@lossJob,@s,227,1000,1000)',0)
 check('bounded loss step','QuicHandshakeSentLossStep(@lossJob)',0)
 check('bounded loss cursor','lossJob\\cursor',64)
 check('loss busy reserve','QuicHandshakeSentReserve(@s)',-3464)
 check('loss busy prune','QuicHandshakeSentPrune(@s,64)',-3464)
 check('loss busy discard','QuicHandshakeSentDiscard(@s)',-3464)
 check('loss busy ACK','QuicHandshakeSentAckBegin(@other,@s,0,@frame)',-3464)
 check('loss cancel no events','QuicHandshakeSentLossCancel(@lossJob)',-3467);observe('loss cancellation unchanged')
 loss_scan(227,stop_after=1);loss_scan(227);ack(set(range(128)));prune();prune()
 for args in ['-1,1000,3','0,1000,3','227,0,3','227,1000,2']:
  check('invalid loss admission',f'QuicHandshakeSentLossBegin(@lossJob,@s,{args})',-3461)
 check('loss owner alias','QuicHandshakeSentLossBegin(@s,@s,227,1000,3)',-3461)
 init(4,4)
 reserve();commit(0,time=(1<<63)-11);reserve();commit(1,time=(1<<63)-10);ack({1})
 loss_scan((1<<63)-10,100)

 # Independent arbitrary-precision oracle for path RTT and timer arithmetic.
 import random
 M=(1<<63)-1
 state={}
 def observe_rtt(label):
  for field in ['hasSample','latest','minimum','smoothed','variation','granularity']:
   check(label+' '+field,'rtt\\'+field,state[field])
  delay=max(state['latest'],state['smoothed'])
  check(label+' loss delay','QuicRttLossDelay(@rtt)',min(M,max(state['granularity'],(9*delay+7)//8)))
  for level,confirmed,cap,backoff in [(0,0,25000,0),(2,1,25000,1),(4,0,25000,0),(4,1,25000,0),(4,1,25000,5),(4,1,M,63)]:
   want=-3462 if level==4 and not confirmed else min(M,(state['smoothed']+max(4*state['variation'],state['granularity'])+(cap if level==4 else 0))*(1<<backoff))
   check(label+' PTO',f'QuicRttPto(@rtt,{level},{confirmed},{cap},{backoff})',want)
 def reset_rtt(initial=333000,granularity=1000):
  state.update(hasSample=0,latest=initial,minimum=0,smoothed=initial,variation=initial//2,granularity=granularity)
  check('RTT init',f'QuicRttInit(@rtt,{initial},{granularity})',0);observe_rtt('initial RTT')
 def sample_rtt(elapsed,delay=0,cap=25000,level=4,confirmed=1):
  check('RTT sample',f'QuicRttSample(@rtt,{elapsed},{delay},{cap},{level},{confirmed})',0)
  if not state['hasSample']:
   state.update(hasSample=1,latest=elapsed,minimum=elapsed,smoothed=elapsed,variation=elapsed//2)
  else:
   minimum=min(state['minimum'],elapsed)
   effective=0 if level!=4 else min(delay,cap) if confirmed else delay
   adjusted=elapsed-effective if elapsed-effective>=minimum else elapsed
   state['variation']=(3*state['variation']+abs(state['smoothed']-adjusted))//4
   state['smoothed']=(7*state['smoothed']+adjusted)//8
   state.update(latest=elapsed,minimum=minimum)
  observe_rtt('updated RTT')
 check('uninitialized RTT','QuicRttLossDelay(@rtt)',-3462)
 check('null RTT','QuicRttInit(0,333000,1000)',-3461)
 reset_rtt();sample_rtt(100000,99000);sample_rtt(200000);sample_rtt(125000,100000)
 sample_rtt(125000,100000,level=0);sample_rtt(125000,100000,level=2)
 sample_rtt(200000,50000,confirmed=0);sample_rtt(90000,100000);sample_rtt(1,M)
 rng=random.Random(1874)
 for i in range(60):
  sample_rtt(rng.randrange(1,1000000),rng.randrange(100000),level=rng.choice([0,2,4]),confirmed=rng.randrange(2))
 reset_rtt(M,M);sample_rtt(M);sample_rtt(1);sample_rtt(M,M);sample_rtt(M-1,1)
 reset_rtt(1,1)
 for v in [1,2,7,8,9,15,16,17,M//8,M//4,M//2,M-1,M]:sample_rtt(v)
 for args in ['0,1000','333000,0','-1,1000']:
  check('invalid RTT init',f'QuicRttInit(@rtt,{args})',-3461)
 for args in ['0,0,0,4,1','1,-1,0,4,1','1,0,-1,4,1','1,0,0,1,1','1,0,0,4,2']:
  check('invalid RTT sample',f'QuicRttSample(@rtt,{args})',-3461)
 for args in ['4,1,0,64','4,1,0,-1','3,1,0,0','4,2,0,0','4,1,-1,0']:
  check('invalid PTO',f'QuicRttPto(@rtt,{args})',-3461)
 observe_rtt('refusals preserve RTT')
 for start,duration in [(0,1),(100,999),(M-2,2),(M-2,3),(M,M),(0,M),(-1,1),(0,0)]:
  check('deadline',f'QuicRttDeadline({start},{duration})',-3461 if start<0 or duration<1 else min(M,start+duration))

 # Eligibility comes from completed ledger events, not only the ACK largest PN.
 reset_rtt();init(8,4)
 reserve();commit(0,time=1000,eliciting=0)
 reserve();commit(1,time=2000)
 reserve();commit(2,time=3000,eliciting=0)
 prepare({1,2})
 check('RTT before validation','QuicRttAck(@rtt,@job,4000,3,25000,1)',-3462)
 code('rc=RunAck(0)');apply({1,2});check('eligible ACK done','rc',2)
 check('largest noneliciting still eligible','QuicRttAck(@rtt,@job,4000,3,25000,1)',1)
 check('largest timestamp used','rtt\\latest',1000)
 check('same completed ACK not sampled twice','QuicRttAck(@rtt,@job,9000,3,25000,1)',0)
 check('duplicate helper unchanged','rtt\\latest',1000)
 ack({0,1,2});check('duplicate largest no sample','QuicRttAck(@rtt,@job,10000,3,25000,1)',0)
 reserve();commit(3,time=5000)
 reserve();commit(4,time=6000,eliciting=0)
 ack({4});check('only noneliciting newly ACKed','QuicRttAck(@rtt,@job,10000,3,25000,1)',0)
 ack({3,4});check('new eliciting but old largest','QuicRttAck(@rtt,@job,10000,3,25000,1)',0)
 check('ineligible samples unchanged','rtt\\latest',1000)
 reserve();commit(5,time=7000)
 prepare({5},mutation='frame\\delay=#QUIC_INTEGER_MAX')
 # Mutation above occurs after frame parsing and before ACK admission.
 code('rc=RunAck(0)');apply({5});check('large delay ACK done','rc',2)
 check('bad receive clock','QuicRttAck(@rtt,@job,6999,20,25000,1)',-3461)
 check('zero elapsed rejected','QuicRttAck(@rtt,@job,7000,20,25000,1)',-3461)
 check('bad exponent','QuicRttAck(@rtt,@job,9000,21,25000,1)',-3461)
 check('alias owner','QuicRttAck(@s,@job,9000,20,25000,1)',-3461)
 check('refusals do not consume sample','job\\rttUsed',0)
 check('saturated decode safe','QuicRttAck(@rtt,@job,9000,20,25000,1)',1)
 check('raw sample retained','rtt\\latest',2000)
 check('oversize delay not subtracted','rtt\\smoothed',1125)
 reserve();commit(6,time=8000)
 prepare({6});code('rc=RunAck(1)');apply({6},limit=1)
 check('partial ACK cannot sample','QuicRttAck(@rtt,@job,10000,3,25000,1)',-3462)
 check('cancel partial ACK','QuicHandshakeSentAckCancel(@job)',-3467)
 check('cancelled ACK cannot sample','QuicRttAck(@rtt,@job,10000,3,25000,1)',-3462)
 check('cancel preserves RTT','rtt\\latest',2000)

 # Timer-space selection, boundary firing, backoff and ownership lifecycle.
 reset_rtt();check('probe init','QuicProbeTimerInit(@timer)',0)
 def arm(initial,handshake,application,confirmed=1,backoff=0):
  eligible=[(base+min(M,(333000+666000+(25000 if level==4 else 0))*(1<<backoff)),level) for base,level in [(initial,0),(handshake,2),(application,4)] if base>=0 and (level!=4 or confirmed)]
  expected=min([(min(M,d),level) for d,level in eligible],default=(0,-1))
  check('arm spaces',f'QuicProbeTimerArm(@timer,@rtt,{confirmed},25000,{initial},{handshake},{application})',int(bool(eligible)))
  check('selected deadline','timer\\deadline',expected[0]);check('selected space','timer\\level',expected[1])
  return expected[0]
 for spaces in [(-1,-1,-1),(0,-1,-1),(-1,5,-1),(-1,-1,0),(100,100,0),(100,200,0),(200,100,0),(100000,100000,0)]:arm(*spaces)
 arm(-1,-1,0,confirmed=0);arm(0,1,0,confirmed=0)
 due=arm(-1,-1,0)
 check('before deadline','QuicProbeTimerPoll(@timer,1023999)',0)
 check('at deadline','QuicProbeTimerPoll(@timer,1024000)',1)
 check('expiry backoff','timer\\backoff',1)
 check('expiry only once','QuicProbeTimerPoll(@timer,1024001)',0)
 arm(-1,-1,100,backoff=1)
 check('unvalidated ACK','QuicProbeTimerAcknowledged(@timer,1,0)',0);check('backoff retained','timer\\backoff',1)
 check('duplicate ACK','QuicProbeTimerAcknowledged(@timer,0,1)',0);check('backoff retained','timer\\backoff',1)
 check('fresh validated ACK','QuicProbeTimerAcknowledged(@timer,1,1)',0);check('backoff reset','timer\\backoff',0)
 due=arm(5,-1,-1)
 for args in ['2,25000,0,-1,-1','1,-1,0,-1,-1','1,25000,-2,-1,-1']:
  check('bad arm atomic',f'QuicProbeTimerArm(@timer,@rtt,{args})',-3461)
 check('refused arm preserves deadline','timer\\deadline',due)
 check('negative poll','QuicProbeTimerPoll(@timer,-1)',-3461)
 check('cancel timer','QuicProbeTimerDiscard(@timer)',0)
 check('closed timer cannot fire','QuicProbeTimerPoll(@timer,999999999)',-3462)
 check('closed arm refused','QuicProbeTimerArm(@timer,@rtt,1,0,0,0,0)',-3462)
 check('reinitialize timer','QuicProbeTimerInit(@timer)',0)
 # Repeated expiries reach saturation without a shift overflow or event loop.
 for k in range(65):
  due=arm(0,-1,-1,backoff=min(k,63))
  check('backoff expiry',f'QuicProbeTimerPoll(@timer,{due})',1)
  check('bounded backoff','timer\\backoff',min(k+1,63))
 arm(M,M,M,backoff=63)
 check('saturated tie prefers initial','timer\\level',0)
 check('discard saturated timer','QuicProbeTimerDiscard(@timer)',0)
 assert 256+len(cases)*8<=65536
 source=out/'proof.pi4'
 source.write_text(r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_handshake_sent.pbi"
Global s.QuicHandshakeSent,job.QuicHandshakeSentAck,other.QuicHandshakeSentAck,frame.QuicHandshakeFrame
Global lossJob.QuicHandshakeSentLoss
Global rtt.QuicRtt
Global timer.QuicProbeTimer
Global Dim storage.a[131104]
Global Dim wire.a[1100]
Global events.i,byteSum.i,flightSum.i,cookieSum.i,timeSum.i,eventHash.i
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i RunAck(stopAfter.i)
 Define rc.i,n.i,i.i,v.i,k.i
 events=0 : byteSum=0 : flightSum=0 : cookieSum=0 : timeSum=0 : eventHash=2166136261
 For n=0 To 19999
  rc=QuicHandshakeSentAckStep(@job)
  If rc=1
   events=events+1 : byteSum=byteSum+job\packetBytes : flightSum=flightSum+job\inFlightBytes
   cookieSum=cookieSum+job\cookie : timeSum=timeSum+job\sentAt
   For i=0 To 5
    v=PeekI(@job\number+i*8)
    For k=0 To 7 : eventHash=((eventHash ! ((v>>(k*8))&255))*16777619)&$FFFFFFFF : Next
   Next
   If stopAfter<>0 And events=stopAfter : ProcedureReturn rc : EndIf
  ElseIf rc<>0
   ProcedureReturn rc
  EndIf
 Next
 ProcedureReturn -9999
EndProcedure
Procedure.i RunLoss(stopAfter.i)
 Define rc.i,n.i,i.i,v.i,k.i
 events=0 : byteSum=0 : flightSum=0 : cookieSum=0 : timeSum=0 : eventHash=2166136261
 For n=0 To 19999
  rc=QuicHandshakeSentLossStep(@lossJob)
  If rc=1
   events=events+1 : byteSum=byteSum+lossJob\packetBytes : flightSum=flightSum+lossJob\inFlightBytes
   cookieSum=cookieSum+lossJob\cookie : timeSum=timeSum+lossJob\sentAt
   For i=0 To 5
    v=PeekI(@lossJob\number+i*8)
    For k=0 To 7 : eventHash=((eventHash ! ((v>>(k*8))&255))*16777619)&$FFFFFFFF : Next
   Next
   If stopAfter<>0 And events=stopAfter : ProcedureReturn rc : EndIf
  ElseIf rc<>0
   ProcedureReturn rc
  EndIf
 Next
 ProcedureReturn -9999
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 65535 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\n')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
