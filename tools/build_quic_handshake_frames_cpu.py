"""Physical handshake-frame decoding against independently encoded packets."""
from pathlib import Path
import argparse,hashlib,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler

def vi(n,width=None):
 width=width or next(w for w,b in [(1,6),(2,14),(4,30),(8,62)] if n<1<<b)
 return (n|({1:0,2:1,4:2,8:3}[width]<<(width*8-2))).to_bytes(width,'big')

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/quic_handshake_frames.pbi','Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];vectors=[]
 def check(name,expr,want):
  steps.append(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def add(name,b,expected=None,error=None,level=0,consumed=None):
  index=len(vectors);vectors.append(b or b'\0');p=f'?V{index}'
  steps.append(f'For j=0 To 119 : PokeA(@v+j,$5A) : Next\nrc=QuicHandshakeFrameRead({p},{len(b)},{level},@v)')
  check(name+' result','rc',error if error is not None else consumed or len(b))
  fields=['kind','eliciting','data','bytes','offset','largest','delay','count','ranges','rangeBytes','ect0','ect1','ce','error','trigger']
  for field in fields:
   if error is not None:expr=f'v\\{field}';want=0x5a5a5a5a5a5a5a5a
   else:
    want=(expected or {}).get(field,0);expr=f'v\\{field}'
    if field in ('data','ranges') and want:expr+=f'-{p}'
   check(name+' '+field,expr,want)
 valid=[]
 def good(name,b,fields):valid.append((name,b,fields));add(name,b,fields)
 good('padding',b'\0',{})
 good('ping',b'\1',dict(kind=1,eliciting=1))
 good('crypto',b'\6'+vi(65,4)+vi(3,2)+b'abc',dict(kind=6,eliciting=1,offset=65,data=7,bytes=3))
 good('empty crypto',b'\6'+vi((1<<62)-1)+b'\0',dict(kind=6,eliciting=1,offset=(1<<62)-1,data=10))
 good('close',b'\x1c'+vi(256)+vi(6,4)+vi(3,2)+b'bye',dict(kind=28,error=256,trigger=6,data=9,bytes=3))
 rng=random.Random(1445)
 for i in range(24):
  high=rng.randrange(500,10000);blocks=[];top=high
  for j in range(rng.randrange(1,12)):
   low=top-rng.randrange(0,8);blocks.append((low,top));top=low-rng.randrange(2,10)
  encoded=vi(blocks[0][1]-blocks[0][0]);prev=blocks[0][0]
  for low,top in blocks[1:]:encoded+=vi(prev-top-2)+vi(top-low);prev=low
  kind=2+i%2;delay=rng.randrange(100000);head=bytes([kind])+vi(high)+vi(delay)+vi(len(blocks)-1)
  f=dict(kind=kind,largest=high,delay=delay,count=len(blocks),ranges=len(head),rangeBytes=len(encoded))
  tail=b''
  if kind==3:
   f.update(ect0=500,ect1=1,ce=(1<<62)-1);tail=vi(500)+vi(1)+vi((1<<62)-1)
  good('ack '+str(i),head+encoded+tail,f)
 head=b'\2'+vi(126)+b'\0'+vi(63);encoded=b'\0'+b'\0\0'*63
 good('64 ack ranges',head+encoded,dict(kind=2,largest=126,count=64,ranges=len(head),rangeBytes=len(encoded)))
 good('ack nonminimal fields',b'\2'+vi(0,8)+vi(0,4)+vi(0,2)+vi(0,8),dict(kind=2,count=1,ranges=15,rangeBytes=8))
 # Every prefix of representative complete frames must be refused without
 # modifying any output field; trailing packet frames are not consumed.
 for name,b,f in valid[:7]+valid[-2:]:
  for n in range(len(b)):add(name+' prefix '+str(n),b[:n],error=-3422)
  add(name+' following ping',b+b'\1',f,consumed=len(b))
  add(name+' handshake',b,f,level=2)
 for kind in [4,5,7,*range(8,28),29,30]:add('wrong level '+str(kind),bytes([kind]),error=-3427)
 for kind in [31,63,64,(1<<62)-1]:add('unknown '+str(kind),vi(kind),error=-3424)
 for level in [-1,1,3,4]:add('bad level '+str(level),b'\1',error=-3427,level=level)
 for kind in [0,1,2,3,6,28]:
  for width in [2,4,8]:add('long type '+str(kind)+'/'+str(width),vi(kind,width),error=-3427)
 for name,b in [('first underflow',b'\2\0\0\0\1'),('gap underflow',b'\2\1\0\1\0\0\0'),('range underflow',b'\2\4\0\1\0\0\3'),('huge gap',b'\2\x10\0\1\0'+vi((1<<62)-1)+b'\0')]:add(name,b,error=-3424)
 add('range work bound',b'\2'+vi(1000)+b'\0'+vi(64),error=-3425)
 add('crypto overflow',b'\6'+vi((1<<62)-1)+b'\1x',error=-3423)
 for expr in ['QuicHandshakeFrameRead(0,1,0,@v)','QuicHandshakeFrameRead(?V0,-1,0,@v)','QuicHandshakeFrameRead(?V0,1,0,0)','QuicHandshakeFrameRead(@v,1,0,@v)']:
  check('argument '+expr,expr,-3421)
 assert 256+8*len(cases)<=65536
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_handshake_frames.pbi"
Global v.QuicHandshakeFrame
Procedure.i Main()
 Define rc.i,j.i
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f'V{k}:\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[i:i+24]))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
