"""Build a physical CPU proof of TCP IPv6 wire emission and validation."""
from pathlib import Path
import argparse, hashlib, ipaddress, json, os, re, struct, subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_tcp.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 src=ipaddress.IPv6Address('fd3f:f605:b7f1:cfd6::1').packed
 dst=ipaddress.IPv6Address('fd3f:f605:b7f1:cfd6::2').packed
 def checksum(b):
  if len(b)%2:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def segment(data=b'',options=b''):
  return struct.pack('>HHIIBBHHH',49152,80,0xfedcba98,0x87654321,((20+len(options))//4)<<4,0x18,8192,0,0)+options+data
 def packet(seg,ext=b'',proto=6,source=src,destination=dst):
  seg=bytearray(seg);struct.pack_into('>H',seg,16,0)
  struct.pack_into('>H',seg,16,checksum(source+destination+struct.pack('>I3xB',len(seg),6)+seg))
  return struct.pack('>IHBB',0x60000000,len(seg)+len(ext),proto,64)+source+destination+ext+seg
 cases=[];steps=[];vectors=[]
 def vec(b):
  vectors.append(bytes(b));return f'?V{len(vectors)-1}'
 def add(name,code,rc,wire=b'',fields=None):
  cases.append(dict(name=name,expected=[rc]+(fields if fields is not None else [-1]*9),wire=wire.hex()));steps.append(code)
 def emit(name,seg,capacity=1514,source='?Source',hops=64,rc=None):
  p=vec(seg);code=f'For i=0 To {len(seg)-1} : output[40+i]=PeekA({p}+i) : Next\n rc=IPv6TcpBuild(@output[0],{capacity},{source},?Destination,{len(seg)},{hops})'
  good=packet(seg);add(name,code,len(good) if rc is None else rc,good if rc is None else b'\xa5'*40+seg)
 def parse(name,b,rc=0,offset=40,header=20,payload=None):
  p=vec(b)
  fields=None
  if rc==0:
   size=struct.unpack_from('>H',b,4)[0]+40-offset
   fields=[offset,size,8,24,49152,80,header,offset+header,size-header]
  add(name,f'base={p}\n rc=IPv6TcpParse(base,{len(b)},@view)',rc,fields=fields)
 emit('empty TCP segment',segment())
 emit('odd payload checksum',segment(b'GET / HTTP/1.1\r\n\r\n!'))
 emit('MSS option',segment(b'',b'\x02\x04\x05\xa0'))
 emit('maximum Ethernet TCP payload',segment(bytes(range(256))*5+bytes(160)),capacity=1500)
 stale=bytearray(segment(b'abc'));stale[16:18]=b'\x12\x34';emit('stale checksum overwritten',stale)
 zero=None
 for n in range(65536):
  s=segment(struct.pack('>H',n))
  if checksum(src+dst+struct.pack('>I3xB',len(s),6)+s)==0:zero=s;break
 assert zero is not None
 emit('computed zero checksum preserved',zero)
 emit('insufficient capacity',segment(),59,rc=-890)
 emit('hop limit zero refused',segment(),hops=0,rc=-890)
 emit('unspecified source refused',segment(),source='?Zero',rc=-890)
 emit('output alias refused',segment(),source='@output[0]',rc=-890)
 bad=bytearray(segment());bad[12]=0x40;emit('short data offset refused',bad,rc=-891)
 bad[12]=0xf0;emit('data offset beyond segment refused',bad,rc=-891)
 parse('valid empty',packet(segment()))
 parse('valid odd payload',packet(segment(b'abc')))
 parse('valid zero checksum',packet(zero))
 parse('TCP options preserved',packet(segment(b'abc',b'\x02\x04\x05\xa0')),header=24)
 parse('Ethernet padding excluded',packet(segment(b'abc'))+b'\xa5'*10)
 ext=b'\x06\x00'+bytes(6)
 parse('destination extension excluded from checksum',packet(segment(b'abc'),ext,60),offset=48)
 parse('atomic fragment accepted',packet(segment(),b'\x06\0\0\0\x12\x34\x56\x78',44),offset=48)
 parse('fragment needs reassembly',packet(segment(),b'\x06\0\0\x01\x12\x34\x56\x78',44),rc=-704)
 b=bytearray(packet(segment(b'abc')));b[-1]^=1;parse('payload corruption refused',b,rc=-892)
 b=bytearray(packet(segment()));b[8]^=1;parse('pseudo header corruption refused',b,rc=-892)
 b=bytearray(packet(segment()));b[6]=17;parse('wrong protocol refused',b,rc=-893)
 parse('truncated packet refused',packet(segment())[:-1],rc=-701)
 b=bytearray(packet(segment()));b[52]=0x40;parse('receive short data offset refused',b,rc=-891)
 b[52]=0xf0;parse('receive oversize data offset refused',b,rc=-891)
 parse('multicast destination refused',packet(segment(),destination=bytes.fromhex('ff020000000000000000000000000001')),rc=-890)
 add('view alias refused','rc=IPv6TcpParse(@output[0],60,@output[0])',-890)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_tcp.pbi"\n'+r'''
Global Dim output.a[1514]
Global view.IPv6TcpView
Procedure Save(index.i,rc.i,base.i)
 Define p.i,i.i
 p=$E1C00100+index*2048 : PokeI(p,rc)
 For i=0 To 8 : PokeI(p+8+i*8,PeekI(@view+i*8)) : Next
 If rc=0
  PokeI(p+8,view\segment-base) : PokeI(p+24,view\source-base)
  PokeI(p+32,view\destination-base) : PokeI(p+64,view\data-base)
 EndIf
 For i=0 To 1513 : PokeA(p+80+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,base.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$54435036)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):
  s+='For i=0 To 1513 : output[i]=$A5 : Next\nFor i=0 To 8 : PokeI(@view+i*8,-1) : Next\nbase=0\n'+code+f'\nSave({k},rc,base)\n'
 s+=f'PokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Source',src),('Destination',dst),('Zero',bytes(16))]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
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
