"""Physical ACK tracking against a packet-number set and independent wire encoder."""
from pathlib import Path
import argparse,hashlib,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['tools/build_quic_handshake_ack_cpu.py','Anvil/Network/quic_packet_ack.pbi','Anvil/Network/quic_handshake_ack.pbi','Anvil/Network/quic_handshake_frames.pbi','Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];received=set();demand=0;pending=0;capacity=64;token=0
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def groups(values):
  rows=[]
  for n in sorted(values):
   if rows and n==rows[-1][1]+1:rows[-1][1]=n
   else:rows.append([n,n])
  return rows[::-1]
 def observe(name):
  g=groups(received)
  for field,value in [('count',len(g)),('demand',demand),('pending',pending)]:check(name+' '+field,'s\\'+field,value)
  for i,(lo,hi) in enumerate(g):
   check(name+' low '+str(i),f'PeekI(@ranges[0]+{16*i})',lo)
   check(name+' high '+str(i),f'PeekI(@ranges[0]+{16*i+8})',hi)
 def init(cap=64,level=0):
  nonlocal received,demand,pending,capacity,token
  received=set();demand=0;pending=0;capacity=cap;token=0
  code(f'rc=QuicHandshakeAckInit(@s,{level},@ranges[0],{cap})');check('init','rc',0)
 def record(pn,eliciting=1):
  nonlocal received,demand,pending
  if pn<0 or pn>=1<<62 or eliciting not in (0,1):want=-3441
  elif len(groups(received|{pn}))>capacity:want=-3443
  else:
   want=int(pn not in received);received.add(pn)
   if eliciting:demand+=1;pending=1
  code(f'rc=QuicHandshakeAckRecord(@s,{pn},{eliciting})');check(f'record {pn}/{eliciting}','rc',want);observe('after record')
  if 0<=pn<1<<62:check('seen',f'QuicHandshakeAckSeen(@s,{pn})',int(pn in received))
 def wire():
  g=groups(received)
  if not g:return b''
  b=b'\2'+vi(g[0][1])+b'\0'+vi(len(g)-1)+vi(g[0][1]-g[0][0])
  for (prev,_),(lo,hi) in zip(g,g[1:]):b+=vi(prev-hi-2)+vi(hi-lo)
  return b
 def fnv(b):
  h=2166136261
  for c in b:h=((h^c)*16777619)&0xffffffff
  return h
 def write(cap=1100):
  nonlocal token
  expected=wire();code('For j=0 To 1099 : output[j]=$A5 : Next\ntoken=-7')
  code(f'rc=QuicHandshakeAckWrite(@s,@output[0],{cap},@token)')
  if len(expected)>cap:
   check('small output','rc',-3444);check('token unchanged','token',-7);check('output unchanged','Hash(@output[0],1100)',fnv(b'\xa5'*1100))
  else:
   token=demand;check('encoded length','rc',len(expected));check('snapshot token','token',token)
   check('exact output and guard','Hash(@output[0],1100)',fnv(expected+b'\xa5'*(1100-len(expected))))
   for i,c in enumerate(expected):check('wire byte '+str(i),f'PeekA(@output[0]+{i})',c)
   if expected:
    code(f'rc=QuicHandshakeFrameRead(@output[0],{len(expected)},s\\level,@frame)')
    check('decoder accepts ACK','rc',len(expected));check('decoded ranges','frame\\count',len(groups(received)))
 def sent(t=None):
  nonlocal pending
  t=token if t is None else t
  if t<0 or t>demand:want=-3441
  elif t==demand:want=1;pending=0
  else:want=0
  code(f'rc=QuicHandshakeAckSent(@s,{t})');check('send completion','rc',want);observe('after completion')
 init();write();sent();record(10,0);write();sent()
 record(12);write();old=token;record(14);sent(old);write();sent()
 record(13);record(11);write();sent();record(11);write();old=token;record(20,0);sent(old)
 record(0);record((1<<62)-1);write();write(1);record(-1);record(1<<62);record(3,2);sent(demand+1)
 init(2,2);record(0);record(4);record(8);record(2);record(1);record(2);record(3);record(8);write();sent()
 init();rng=random.Random(1452)
 for i in range(100):
  record(rng.randrange(64),rng.randrange(2))
  if i%11==0:
   write();old=token;record(rng.randrange(64),i%2);sent(old)
 init()
 # Fill range capacity without excessive intermediate observations.
 for n in range(0,128,2):
  code(f'rc=QuicHandshakeAckRecord(@s,{n},1)');check('fill '+str(n),'rc',1)
 received=set(range(0,128,2));demand=64;pending=1
 observe('full');write();record(200);record(1);record(200);write()
 code('rc=QuicHandshakeAckInit(@s,1,@ranges[0],64)');check('invalid level','rc',-3441);observe('invalid init unchanged')
 for expr in ['QuicHandshakeAckWrite(@s,@ranges[0],16,@token)','QuicHandshakeAckWrite(@s,@output[0],1100,@s)','QuicHandshakeAckWrite(@s,@output[0],1100,@output[0])','QuicHandshakeAckInit(@s,0,@s,1)','QuicHandshakeAckInit(@s,0,@ranges[0],65)','QuicHandshakeAckSeen(@s,-1)']:
  check('argument '+expr,expr,-3441)
 init(1);record(1);record(2);record(0);record(4);write();sent()
 code('s\\demand=$7FFFFFFFFFFFFFFF\nrc=QuicHandshakeAckRecord(@s,3,1)');check('token exhaustion','rc',-3443);check('exhaustion no range change','PeekI(@ranges[0]+8)',2)
 code('s\\phase=0');check('uninitialized','QuicHandshakeAckSeen(@s,0)',-3442)
 assert 256+8*len(cases)<=65536
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_handshake_ack.pbi"
XIncludeFile "Anvil/Network/quic_handshake_frames.pbi"
Global s.QuicHandshakeAck,frame.QuicHandshakeFrame,token.i
Global Dim ranges.a[1024]
Global Dim output.a[1100]
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i Main()
 Define rc.i,j.i
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
