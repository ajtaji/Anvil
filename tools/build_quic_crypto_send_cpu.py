"""Physical outgoing CRYPTO ring checks against independent retained-byte state."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/quic_crypto_send.pbi','Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 steps=[];cases=[];data=bytearray(b'\xa5'*4096);meta=bytearray(b'\xa5'*1024);base=tail=head=level=0
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def fnv(b):
  h=2166136261
  for x in b:h=((h^x)*16777619)&0xffffffff
  return h
 def index(off):return (head+off-base)%4096
 def state(off):
  p=index(off);return (meta[p//4]>>((p%4)*2))&3
 def setstate(off,v):
  p=index(off);shift=(p%4)*2;meta[p//4]=(meta[p//4]&~(3<<shift))|(v<<shift)
 def observe(name):
  for f,v in [('base',base),('tail',tail),('head',head),('level',level)]:check(name+' '+f,'s\\'+f,v)
  check(name+' data','Hash(@data[0],4128)',fnv(b'\xa5'*16+data+b'\xa5'*16))
  check(name+' metadata','Hash(@meta[0],1056)',fnv(b'\xa5'*16+meta+b'\xa5'*16))
 def init(lev):
  nonlocal base,tail,head,level
  check('init',f'QuicCryptoTxInit(@s,{lev},@data[16],4096,@meta[16],1024)',0)
  base=tail=head=0;level=lev;observe('init untouched storage')
 def append(n,seed):
  nonlocal tail
  payload=bytes((i*17+seed)&255 for i in range(n))
  code(f'For i=0 To {max(0,n-1)} : input[i]=(i*17+{seed})&255 : Next')
  if n>16384:want=-3481
  elif n>(1<<62)-1-tail:want=-3484
  elif n>4096-(tail-base):want=-3483
  else:
   want=n
   for i,b in enumerate(payload):data[index(tail+i)]=b;setstate(tail+i,0)
   tail+=n
  check('append',f'QuicCryptoTxAppend(@s,@input[0],{n})',want);observe('after append')
 def mark(mode,off,n):
  api={1:'Sent',2:'Retry',3:'Ack'}[mode]
  if off<0 or n<0 or n>16384 or off+n>(1<<62)-1 or off+n>tail:want=-3484
  elif mode!=1 and any(state(i)==0 for i in range(max(base,off),off+n)):want=-3482
  else:
   want=0
   for i in range(max(base,off),off+n):
    if state(i)!=3:setstate(i,mode)
  check(api,f'QuicCryptoTx{api}(@s,{off},{n})',want);observe('after '+api)
 def reclaim(budget):
  nonlocal base,head
  if budget<1 or budget>16384:want=-3481
  else:
   want=0
   while want<budget and base<tail and state(base)==3:base+=1;head=(head+1)%4096;want+=1
  check('reclaim',f'QuicCryptoTxReclaim(@s,{budget})',want);observe('after reclaim')
 def find(off,budget=4096):
  code(f'rc=QuicCryptoTxFind(@s,{off},{budget},@view)')
  p=max(off,base);stop=min(tail,p+budget)
  while p<stop and state(p) not in (0,2):p+=1
  count=0
  while p+count<stop and index(p)+count<4096 and state(p+count) in (0,2):count+=1
  check('find result','rc',int(count>0));check('find offset','view\\offset',p);check('find bytes','view\\bytes',count)
  if count:
   check('find pointer','view\\data-@data[16]',index(p));check('find data','Hash(view\\data,view\\bytes)',fnv(data[index(p):index(p)+count]))
  else:check('empty pointer','view\\data',0)
 def frame(off,n,cap=16432):
  code('For i=0 To 16431 : output[i]=$A5 : Next')
  if off<0 or n>16384 or off+n>tail or off+n>(1<<62)-1:want=-3484;wire=b''
  elif n==0 or off<base:want=-3481;wire=b''
  else:
   wire=b'\6'+vi(off)+vi(n)+bytes(data[index(i)] for i in range(off,off+n));want=len(wire)
   if cap<len(wire):want=-3485;wire=b''
  check('frame length',f'QuicCryptoTxFrame(@s,{off},{n},@output[0],{cap})',want)
  check('frame exact bytes and guard','Hash(@output[0],16432)',fnv(wire+b'\xa5'*(16432-len(wire))))
  observe('frame leaves retention unchanged')
 init(0);append(0,0);append(17,1);find(0,4);frame(0,17);frame(0,17,4)
 mark(3,0,1);mark(1,0,10);mark(2,0,17);find(0,7);mark(2,0,10);find(0)
 mark(1,0,17);mark(3,5,12);reclaim(4096);mark(3,0,5);reclaim(7);frame(7,10)
 mark(1,0,17);mark(2,0,17);reclaim(4096);mark(3,0,17);mark(1,0,0)
 append(4000,2);frame(17,4000);mark(1,17,4000);mark(3,17,3990);reclaim(3000);reclaim(990)
 append(200,3);find(4017);find(4096);frame(4007,210);mark(2,4007,210);mark(1,4017,200)
 mark(2,4007,210);mark(3,4100,117);find(4007);mark(3,4007,93);reclaim(50);reclaim(4096)
 append(4096,4);append(1,5);mark(1,4217,4096);mark(3,6217,2096);reclaim(4096);mark(3,4217,2000);reclaim(1);reclaim(4096)
 frame(0,1);mark(3,tail+1,0);mark(2,-1,1);reclaim(0)
 for expr in ['QuicCryptoTxInit(@s,1,@data[16],4096,@meta[16],1024)','QuicCryptoTxInit(@s,0,@data[16],4097,@meta[16],1024)','QuicCryptoTxAppend(@s,@data[16],1)','QuicCryptoTxFrame(@s,s\\base,1,@meta[16],100)','QuicCryptoTxFind(@s,s\\base,1,@s)']:
  # Frame's range check precedes output validation on the empty stream.
  check('alias/argument',expr,-3484 if 'TxFrame' in expr else -3481)
 observe('refusals unchanged')
 for lev in [2,3]:init(lev);append(33,lev);find(0);mark(3,0,33);mark(1,0,33);mark(3,0,33);reclaim(4096)
 init(0);base=tail=(1<<62)-9;head=0;code(f's\\base={base} : s\\tail={tail} : s\\head=0')
 append(8,7);append(1,8);mark(1,base,8);mark(3,base,8);reclaim(8);find(tail,1);frame(tail,1)
 assert 256+len(cases)*8<=65536
 source=out/'proof.pi4';source.write_text(r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_crypto_send.pbi"
Global s.QuicCryptoTx,view.QuicCryptoSlice
Global Dim data.a[4128]
Global Dim meta.a[1056]
Global Dim input.a[16384]
Global Dim output.a[16432]
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 65535 : PokeA($E1C00000+i,$A5) : Next
 For i=0 To 4127 : data[i]=$A5 : Next
 For i=0 To 1055 : meta[i]=$A5 : Next
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
