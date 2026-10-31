"""Build physical CPU UDP/IPv6 emission and parser proofs with independent bytes."""
from pathlib import Path
import argparse, hashlib, ipaddress, json, os, re, struct, subprocess
from pmf_compiler import resolve_compiler

def build(compiler, out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_udp.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 src=ipaddress.IPv6Address('fd3f:f605:b7f1:cfd6::1').packed
 dst=ipaddress.IPv6Address('fd3f:f605:b7f1:cfd6::2').packed
 def checksum(b):
  if len(b)%2:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def datagram(data=b'',sport=49152,dport=443):
  return struct.pack('>4H',sport,dport,len(data)+8,0)+data
 def packet(seg,ext=b'',proto=17,source=src,destination=dst,pad=b''):
  seg=bytearray(seg);struct.pack_into('>H',seg,4,len(seg));struct.pack_into('>H',seg,6,0)
  c=checksum(source+destination+struct.pack('>I3xB',len(seg),17)+seg)
  struct.pack_into('>H',seg,6,c or 65535)
  return struct.pack('>IHBB',0x60000000,len(seg)+len(ext)+len(pad),proto,64)+source+destination+ext+seg+pad
 cases=[];steps=[];vectors=[]
 def vec(b):
  vectors.append(bytes(b));return f'?V{len(vectors)-1}'
 def add(name,code,rc,wire=b'',fields=None):
  cases.append(dict(name=name,expected=[rc]+(fields if fields is not None else [-1]*8),wire=wire.hex()));steps.append(code)
 def emit(name,seg,capacity=1514,source='?Source',hops=64,rc=None):
  p=vec(seg);code=f'For i=0 To {len(seg)-1} : output[40+i]=PeekA({p}+i) : Next\n rc=IPv6UdpBuild(@output[0],{capacity},{source},?Destination,{len(seg)},{hops})'
  good=packet(seg);add(name,code,len(good) if rc is None else rc,good if rc is None else b'\xa5'*40+seg)
 def parse(name,b,rc=0,offset=40):
  p=vec(b);fields=None
  if rc==0:
   sport,dport,size=struct.unpack_from('>3H',b,offset)
   fields=[offset,size,8,24,sport,dport,offset+8,size-8]
  add(name,f'base={p}\n rc=IPv6UdpParse(base,{len(b)},@view)',rc,fields=fields)
 emit('empty datagram',datagram())
 emit('odd payload',datagram(b'hello'))
 emit('1200 byte QUIC payload',datagram(bytes(range(256))*4+bytes(176)))
 emit('IPv6 minimum MTU payload',datagram(bytes(1232)),capacity=1280)
 stale=bytearray(datagram(b'abc'));stale[4:8]=b'\x12\x34\x56\x78';emit('stale length and checksum overwritten',stale)
 zero=None
 for n in range(65536):
  s=datagram(struct.pack('>H',n))
  if checksum(src+dst+struct.pack('>I3xB',len(s),17)+s)==0:zero=s;break
 assert zero is not None
 emit('computed zero emitted as FFFF',zero)
 emit('optional source port zero',datagram(b'abc',sport=0))
 emit('short capacity refused',datagram(),capacity=47,rc=-3501)
 emit('capacity smaller than datagram refused',datagram(b'a'),capacity=48,rc=-3501)
 emit('excess capacity refused',datagram(),capacity=65576,rc=-3501)
 emit('hop zero refused',datagram(),hops=0,rc=-3501)
 emit('hop overflow refused',datagram(),hops=256,rc=-3501)
 emit('source overlaps payload refused',datagram(),source='@output[40]',rc=-3501)
 emit('source span overflow refused',datagram(),source='$7FFFFFFFFFFFFFFF',rc=-3501)
 emit('null source refused',datagram(),source='0',rc=-3501)
 parse('empty receive',packet(datagram()))
 parse('odd receive',packet(datagram(b'abc')))
 parse('computed zero accepted as FFFF',packet(zero))
 parse('optional source port accepted',packet(datagram(b'a',sport=0)))
 parse('IPv6 trailing bytes excluded',packet(datagram(b'abc'),pad=b'\xa5'*7))
 parse('Ethernet padding excluded',packet(datagram(b'abc'))+b'\xa5'*10)
 parse('destination option checksum',packet(datagram(b'abc'),b'\x11\0'+bytes(6),60),offset=48)
 parse('atomic fragment accepted',packet(datagram(),b'\x11\0\0\0\x12\x34\x56\x78',44),offset=48)
 parse('non atomic fragment refused',packet(datagram(),b'\x11\0\0\x01\x12\x34\x56\x78',44),rc=-704)
 parse('multicast destination retained for endpoint policy',packet(datagram(),destination=ipaddress.IPv6Address('ff02::1').packed))
 b=bytearray(packet(datagram(b'abc')));b[-1]^=1;parse('corrupt payload refused',b,rc=-3503)
 b=bytearray(packet(datagram()));b[8]^=1;parse('corrupt pseudo header refused',b,rc=-3503)
 b=bytearray(packet(datagram()));b[46:48]=b'\0\0';parse('zero wire checksum refused',b,rc=-3503)
 b=bytearray(packet(datagram()));b[6]=6;parse('wrong protocol refused',b,rc=-3504)
 for length in [0,7,9,65535]:
  b=bytearray(packet(datagram()));struct.pack_into('>H',b,44,length);parse(f'invalid UDP length {length}',b,rc=-3502)
 parse('truncated packet refused',packet(datagram())[:-1],rc=-701)
 b=bytearray(packet(datagram()));struct.pack_into('>H',b,4,7);parse('short UDP header refused',b[:-1],rc=-3502)
 add('view aliases packet refused','rc=IPv6UdpParse(@output[0],48,@output[0])',-3501)
 add('null view refused','rc=IPv6UdpParse(@output[0],48,0)',-3501)
 add('packet span overflow refused','rc=IPv6UdpParse($7FFFFFFFFFFFFFFF,48,@view)',-3501)
 add('output span overflow refused','rc=IPv6UdpBuild($7FFFFFFFFFFFFFFF,48,?Source,?Destination,8,64)',-3501)
 add('short datagram refused','rc=IPv6UdpBuild(@output[0],1514,?Source,?Destination,7,64)',-3501)
 assert len(cases)<=63
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_udp.pbi"\n'+r'''
Global Dim output.a[1514]
Global view.IPv6UdpView
Procedure Save(index.i,rc.i,base.i)
 Define p.i,i.i
 p=$E1C00100+index*2048 : PokeI(p,rc)
 For i=0 To 7 : PokeI(p+8+i*8,PeekI(@view+i*8)) : Next
 If rc=0
  PokeI(p+8,view\datagram-base) : PokeI(p+24,view\source-base)
  PokeI(p+32,view\destination-base) : PokeI(p+56,view\data-base)
 EndIf
 For i=0 To 1513 : PokeA(p+80+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,base.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$55445036)
 MmuClearNc()
 MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):
  s+='For i=0 To 1513 : output[i]=$A5 : Next\nFor i=0 To 7 : PokeI(@view+i*8,-1) : Next\nbase=0\n'+code+f'\nSave({k},rc,base)\n'
 s+=f'PokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Source',src),('Destination',dst)]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
  s+=name+':\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
