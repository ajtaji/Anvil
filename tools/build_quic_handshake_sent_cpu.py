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
 assert 256+len(cases)*8<=65536
 source=out/'proof.pi4'
 source.write_text(r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_handshake_sent.pbi"
Global s.QuicHandshakeSent,job.QuicHandshakeSentAck,other.QuicHandshakeSentAck,frame.QuicHandshakeFrame
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
