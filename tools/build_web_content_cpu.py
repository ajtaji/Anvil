"""Physical known-length and chunked upload proof; no emulator is started."""
from pathlib import Path
import subprocess,os,re,json,hashlib
import argparse,zlib,random,gzip,struct
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description="Compile streaming HTTP upload qualification for a physical Pi 4")
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=args.out.resolve();d.mkdir(parents=True,exist_ok=False)
names=['Anvil/Core/crc_constants.pbi','Anvil/Core/crc.pbi','Anvil/Network/web_inflate.pbi','Anvil/Network/web_content.pbi']
s='\n'.join(x for n in names for x in (r/n).read_text(encoding='utf8').splitlines() if not x.startswith('XIncludeFile'))+r'''
Global decoder.WebContent
Global Dim history.a[32770]
Global Dim workspace.a[11024]
Global Dim output.a[259]
Procedure Record(index.i,wire.i,bytes.i,expected.i,expectedBytes.i,fragment.i,cap.i,limit.i,kind.i)
 Define rc.i,i.i,off.i,got.i,bad.i,steps.i,n.i,outCap.i,p.i
 For i=0 To 32769 : history[i]=$A5 : Next
 For i=0 To 11023 : workspace[i]=$A5 : Next
 rc=WebContentInit(@decoder,kind,@history[1],32768,@workspace[8],11008,limit)
 While rc=0
  n=bytes-off : If n>fragment : n=fragment : EndIf
  outCap=cap : If steps % 5=0 : outCap=0 : EndIf
  For i=0 To 258 : output[i]=$A5 : Next
  rc=WebContentFeed(@decoder,wire+off,n,Bool(off+n=bytes),@output[1],outCap)
  off=off+decoder\consumed
  For i=0 To decoder\written-1
   If got>=expectedBytes : bad=bad+1 : ElseIf (output[i+1] & 255)<>(PeekA(expected+got) & 255) : bad=bad+1 : EndIf
   got=got+1
  Next
  If output[0]<>$A5 Or output[outCap+1]<>$A5 : bad=bad+1 : EndIf
  steps=steps+1
  If steps>200000 : rc=-999 : Break : EndIf
 Wend
 p=$E1C00100+index*128
 For i=0 To 127 : PokeA(p+i,0) : Next
 PokeI(p,rc) : PokeI(p+8,off) : PokeI(p+16,got) : PokeI(p+24,bad) : PokeI(p+32,steps)
 PokeI(p+72,decoder\members)
 PokeI(p+40,history[0]) : PokeI(p+48,history[32769]) : PokeI(p+56,workspace[0]) : PokeI(p+64,workspace[11016])
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$494E4632)
'''
text=(b'Anvil gzip and deflate streaming response. '*70)
raw=bytes(range(256))*3
base=gzip.compress(text,mtime=0)
co=zlib.compressobj(6,zlib.DEFLATED,-15);deflated=co.compress(text)+co.flush()
header=b'\x1f\x8b\x08\x1e'+bytes(6)+struct.pack('<H',3)+b'abc'+b'name.txt\0comment\0'
optional=header+struct.pack('<H',zlib.crc32(header)&65535)+deflated+struct.pack('<II',zlib.crc32(text),len(text))
fixtures=[('gzip',1,base,text,1),('empty-gzip',1,gzip.compress(b'',mtime=0),b'',1),('binary-gzip',1,gzip.compress(raw,mtime=0),raw,1),('gzip-optional',1,optional,text,1),('gzip-members',1,base+gzip.compress(raw,mtime=0),text+raw,2),('zlib',2,zlib.compress(text),text,1),('empty-zlib',2,zlib.compress(b''),b'',1),('stored-zlib',2,zlib.compress(raw,0),raw,1)]
cases=[];data='\nDataSection\n'
def add(name,kind,wire,expected,members,frag,cap,error=0,limit=1000000):
 global s,data
 i=len(cases);cases.append(dict(name=name,wireBytes=len(wire),outputBytes=len(expected),members=members,error=error))
 s+=f' Record({i},?wire{i},{len(wire)},?expected{i},{len(expected)},{frag},{cap},{limit},{kind})\n'
 for label,payload in [('wire',wire),('expected',expected)]:
  data+=f'{label}{i}:\n'
  if not payload:payload=b'\0'
  for start in range(0,len(payload),32):data+=' Data.a '+','.join(map(str,payload[start:start+32]))+'\n'
for name,kind,wire,expected,members in fixtures:
 for frag,cap in [(1,1),(17,257)]:add(name,kind,wire,expected,members,frag,cap)
badcrc=bytearray(base);badcrc[-8]^=1
badsize=bytearray(base);badsize[-4]^=1
badheader=bytearray(optional);badheader[len(header)]^=1
badzlib=bytearray(zlib.compress(text));badzlib[-1]^=1
badflags=bytearray(base);badflags[3]|=128
for name,kind,wire,expected,error in [('gzip-crc',1,bytes(badcrc),text,-591),('gzip-size',1,bytes(badsize),text,-591),('gzip-header-crc',1,bytes(badheader),b'',-591),('gzip-flags',1,bytes(badflags),b'',-590),('gzip-truncated',1,base[:-1],text,-584),('zlib-checksum',2,bytes(badzlib),text,-591),('zlib-trailing',2,zlib.compress(text)+b'x',text,-593),('zlib-dictionary',2,b'\x78\x20',b'',-592),('gzip-empty-input',1,b'',b'',-584)]:
 add(name,kind,wire,expected,0,7,31,error)
add('output-limit',1,base,text,0,7,31,-583,10)
s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\n'+data+'EndDataSection\n'
p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=str(resolve_compiler(args.compiler))
q=subprocess.run([c,'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
