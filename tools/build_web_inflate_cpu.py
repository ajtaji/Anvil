"""Physical known-length and chunked upload proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse,zlib,random
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile streaming HTTP upload qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Network/web_inflate.pbi']
s=(r/names[0]).read_text(encoding='utf8')+r'''
Global decoder.WebInflate
Global Dim history.a[32770]
Global Dim workspace.a[11024]
Global Dim output.a[259]
Procedure Record(index.i,wire.i,bytes.i,expected.i,expectedBytes.i,fragment.i,cap.i,limit.i)
 Define rc.i,i.i,off.i,got.i,bad.i,steps.i,n.i,outCap.i,p.i
 For i=0 To 32769 : history[i]=$A5 : Next
 For i=0 To 11023 : workspace[i]=$A5 : Next
 rc=WebInflateInit(@decoder,@history[1],32768,@workspace[8],11008,limit)
 While rc=0
  n=bytes-off : If n>fragment : n=fragment : EndIf
  outCap=cap : If steps % 5=0 : outCap=0 : EndIf
  For i=0 To 258 : output[i]=$A5 : Next
  rc=WebInflateFeed(@decoder,wire+off,n,@output[1],outCap)
  off=off+decoder\consumed
  For i=0 To decoder\written-1
   If got>=expectedBytes : bad=bad+1 : ElseIf (output[i+1] & 255)<>(PeekA(expected+got) & 255) : bad=bad+1 : EndIf
   got=got+1
  Next
  If output[0]<>$A5 Or output[outCap+1]<>$A5 : bad=bad+1 : EndIf
  steps=steps+1
  If rc=0 And n=0 And decoder\written=0 And outCap>0 : rc=WebInflateEof(@decoder) : EndIf
  If steps>200000 : rc=-999 : Break : EndIf
 Wend
 p=$E1C00100+index*128
 For i=0 To 127 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,off) : PokeI(p+16,got) : PokeI(p+24,bad) : PokeI(p+32,steps)
 PokeI(p+40,history[0]) : PokeI(p+48,history[32769]) : PokeI(p+56,workspace[0]) : PokeI(p+64,workspace[11016])
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$494E4631)
'''
def compress(data,level=6,strategy=zlib.Z_DEFAULT_STRATEGY):
 c=zlib.compressobj(level,zlib.DEFLATED,-15,8,strategy);return c.compress(data)+c.flush()
rng=random.Random(4813)
raw=bytes(rng.randrange(256) for _ in range(2000))
long=bytes(range(251))*180
text=(b'Anvil networking streams a verified response. '*100)
fixtures=[('empty',b'',compress(b'')),('stored',raw,compress(raw,0)),('fixed',text,compress(text,6,zlib.Z_FIXED)),('dynamic',text,compress(text)),('history-wrap',long,compress(long)),('binary',raw,compress(raw)),('huffman',text,compress(text,6,zlib.Z_HUFFMAN_ONLY))]
# Force multiple blocks and transitions, retaining LZ history between blocks.
c=zlib.compressobj(6,zlib.DEFLATED,-15);multi=c.compress(text)+c.flush(zlib.Z_SYNC_FLUSH)+c.compress(text)+c.flush();fixtures.append(('multi',text+text,multi))
cases=[];data='\nDataSection\n'
for name,expected,wire in fixtures:
 for frag,cap in [(1,1),(7,31),(4096,257)]:
  if name=='history-wrap' and frag==1:continue
  i=len(cases);cases.append(dict(name=name,wireBytes=len(wire),outputBytes=len(expected),fragment=frag,cap=cap,error=0))
  s+=f' Record({i},?wire{i},{len(wire)},?expected{i},{len(expected)},{frag},{cap},1000000)\n'
  for label,payload in [('wire',wire),('expected',expected)]:
   data+=f'{label}{i}:\n'
   if not payload:payload=b'\0'
   for start in range(0,len(payload),32):data+=' Data.a '+','.join(map(str,payload[start:start+32]))+'\n'
for name,wire,expected,error,limit in [('reserved',b'\x07',b'',-581,1000),('stored-complement',b'\x01\x01\x00\xff\xffx',b'',-581,1000),('truncated',compress(text)[:-1],text,-584,100000),('output-limit',compress(text),text,-583,10)]:
 i=len(cases);cases.append(dict(name=name,wireBytes=len(wire),outputBytes=len(expected),error=error))
 s+=f' Record({i},?wire{i},{len(wire)},?expected{i},{len(expected)},7,31,{limit})\n'
 for label,payload in [('wire',wire),('expected',expected)]:
  data+=f'{label}{i}:\n'
  if not payload:payload=b'\0'
  for start in range(0,len(payload),32):data+=' Data.a '+','.join(map(str,payload[start:start+32]))+'\n'
s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\n'+data+'EndDataSection\n'
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
