"""Physical QUIC CRYPTO reassembly checks, including an independent byte-map oracle."""
from pathlib import Path
import argparse,hashlib,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(bytes(b));return f'?V{len(vectors)-1}'
 def code(s):steps.append(s)
 def check(name,expr,want):
  code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def init(level=2):code(f'rc=QuicCryptoRxInit(@s,{level},@data[0],4096,@bits[0],512)')
 def put(off,b,level=2):code(f'rc=QuicCryptoRxPut(@s,{level},{off},{vec(b or bytes(1))},{len(b)})')
 def peek(n=4096):code(f'rc=QuicCryptoRxPeek(@s,{n},@v)')
 def consume(n):code(f'rc=QuicCryptoRxConsume(@s,{n})')
 def fnv(b):
  h=2166136261
  for c in b:h=((h^c)*16777619)&0xffffffff
  return h
 init();check('init','rc',0)
 put(3,b'def');check('out of order accepted','rc',3);peek();check('gap not delivered','rc',0)
 put(0,b'abc');peek();check('joined length','rc',6);check('joined contents','Hash(v\\data,v\\bytes)',fnv(b'abcdef'))
 put(2,b'cdef');check('duplicate overlap','rc',0);check('unique count','s\\buffered',6)
 put(1,b'bZ');check('conflict','rc',-3426);peek();check('conflict leaves data','Hash(v\\data,v\\bytes)',fnv(b'abcdef'))
 consume(2);check('partial consume','s\\base',2);put(0,b'ZZcde');check('discarded prefix ignored','rc',0)
 peek();check('remaining','Hash(v\\data,v\\bytes)',fnv(b'cdef'));consume(5);check('overconsume refused','rc',-3421);check('refusal preserves base','s\\base',2)
 consume(4);check('drained','s\\buffered',0);code('rc=QuicCryptoRxSeal(@s)');check('seal drained','rc',0)
 put(0,b'abcdef');check('sealed duplicate','rc',0);put(6,b'x');check('sealed extension refused','rc',-3427)
 init();put(2,b'cd');code('rc=QuicCryptoRxSeal(@s)');check('cannot abandon old level','rc',-3427);check('seal refusal unchanged','s\\phase',1)
 put(0,b'abc',0);check('cross-level refused','rc',-3427)
 code('rc=QuicCryptoRxInit(@s,1,@data[0],4096,@bits[0],512)');check('0RTT refused','rc',-3427);check('invalid init retains level','s\\level',2)
 code('rc=QuicCryptoRxInit(@s,2,@data[0],4096,@data[0],512)');check('storage alias refused','rc',-3421)
 init();code('rc=QuicCryptoRxPut(@s,2,0,@data[0],1)');check('input alias refused','rc',-3421)
 code('rc=QuicCryptoRxPeek(@s,1,@s)');check('view alias refused','rc',-3421)
 code('rc=QuicCryptoRxPut(@s,2,$3FFFFFFFFFFFFFFF,?V0,1)');check('offset overflow','rc',-3423)
 put(4095,b'ab');check('window overflow atomic','rc',-3425);check('overflow retained none','s\\buffered',0)
 put(0,bytes((i*17+13)&255 for i in range(4096)));check('full capacity','rc',4096);peek();check('full offer','rc',4096);consume(4090)
 put(4096,b'uvwxyz');peek();check('peek stops at ring end','rc',6);consume(6);peek();check('wrapped data','Hash(v\\data,v\\bytes)',fnv(b'uvwxyz'));consume(6);check('wrapped base','s\\base',4102)
 init();put(2,b'c');put(0,b'abZ');check('late conflict refuses entire write','rc',-3426);peek();check('refused prefix not committed','rc',0);check('one retained byte','s\\buffered',1)
 init();code('rc=QuicCryptoRxPut(@s,2,$3FFFFFFFFFFFFFFF,0,0)');check('empty high-offset frame','rc',0);check('empty frame does not extend stream','s\\highest',0)
 code('rc=QuicCryptoRxPut(@s,2,0,?V0,16385)');check('bounded put argument','rc',-3421)
 code('rc=QuicCryptoRxPeek(@s,4097,@v)');check('bounded peek argument','rc',-3421)
 code('rc=QuicCryptoRxInit(@s,2,@data[0],262145,@bits[0],32769)');check('oversize init refused','rc',-3421)
 # Deterministic byte-map model. Every operation checks result and all
 # externally meaningful state, without mirroring circular storage/bitmap.
 rng=random.Random(1430);present={};base=0;offered=b'';highest=0
 init()
 for step in range(90):
  if step%3!=2:
   off=max(0,base+rng.choice([-17,0,0,1,10,30,60,4080,4090]))
   b=bytes((i*17+13)&255 for i in range(off,off+rng.randint(1,31)))
   if step%13==0:b=bytes((x+1)&255 for x in b)
   ending=off+len(b);new={i:b[i-off] for i in range(max(off,base),ending)}
   if ending-base>4096:want=-3425
   elif any(i in present and present[i]!=v for i,v in new.items()):want=-3426
   else:
    want=sum(i not in present for i in new);present.update(new)
    if ending>base:highest=max(highest,ending)
   put(off,b);check(f'model {step} put','rc',want)
  else:
   limit=rng.randint(1,63);end=base
   while end in present and end-base<limit and end%4096>=base%4096:end+=1
   offered=bytes(present[i] for i in range(base,end))
   peek(limit);check(f'model {step} peek','rc',len(offered));check(f'model {step} data','Hash(v\\data,v\\bytes)',fnv(offered))
   n=rng.randint(0,len(offered));consume(n);check(f'model {step} consume','rc',0)
   for i in range(base,base+n):del present[i]
   base+=n
  check(f'model {step} base','s\\base',base);check(f'model {step} buffered','s\\buffered',len(present));check(f'model {step} high','s\\highest',highest)
 # Parser vectors generated independently of the implementation.
 wire=[(b'\x06\0\x03abc',6,0,3),(b'\x40\x06\x40\0\x40\x03abcZ',9,0,3),(b'\x06\0\0',3,0,0),(b'\x07\0\0',-3424,99,99),(b'',-3422,99,99),(b'\x06\x40',-3422,99,99),(b'\x06\0\x03ab',-3422,99,99),(b'\x06'+b'\xff'*8+b'\x01x',-3423,99,99)]
 for i,(b,result,offset,length) in enumerate(wire):
  code(f'v\\offset=99 : v\\bytes=99 : v\\data=99\nrc=QuicCryptoFrameRead({vec(b or bytes(1))},{len(b)},@v)')
  check(f'wire{i} result','rc',result);check(f'wire{i} offset','v\\offset',offset);check(f'wire{i} length','v\\bytes',length)
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_crypto_stream.pbi"
Global s.QuicCryptoRx,v.QuicCryptoSlice
Global Dim data.a[8192]
Global Dim bits.a[1024]
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
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
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
