'''Build physical qualification of owned IPv6 router-advertisement decoding.'''
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_router.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/internet_checksum.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda s:ipaddress.IPv6Address(s).packed
 src=addr('fe80::1');local=addr('fe80::1234');allnodes=addr('ff02::1');mac=bytes.fromhex('020102030405')
 def checksum(b):
  if len(b)&1:b+=b'\0'
  n=sum(struct.unpack('>'+str(len(b)//2)+'H',b))
  while n>>16:n=(n&65535)+(n>>16)
  return (~n)&65535
 def packet(opts=b'',source=src,dest=allnodes,hop=255,kind=134,code=0,fields=(64,192,1800,30000,1000),fragment=False):
  body=bytes([kind,code,0,0])+struct.pack('>BBHII',*fields)+opts
  c=checksum(source+dest+struct.pack('>I3xB',len(body),58)+body);body=body[:2]+struct.pack('>H',c)+body[4:]
  ext=b'\x3a\0\0\0\0\0\0\0' if fragment else b''
  return struct.pack('>IHBB',0x60000000,len(body)+len(ext),44 if fragment else 58,hop)+source+dest+ext+body
 def pio(prefix='2001:db8:1:2::abcd',bits=64,flags=192,valid=10000,preferred=5000):
  return bytes([3,4,bits,flags])+struct.pack('>III',valid,preferred,0)+addr(prefix)
 def row(prefix='2001:db8:1:2::abcd',bits=64,flags=192,valid=10000,preferred=5000):
  net=ipaddress.IPv6Network((prefix,bits),strict=False).network_address.packed
  return struct.pack('<5q',bits,(flags>>7)&1,(flags>>6)&1,valid,preferred)+net
 def header(count=0,mtu=0,sm=b'',fields=(64,192,1800,30000,1000)):
  return src+sm.ljust(8,b'\0')+struct.pack('<8q',int(bool(sm)),*fields,mtu,count)
 cases=[];steps=[];vectors=[]
 def add(name,b,rc=0,h=None,rows=b'',cap=4,localarg='?Local',mtu=1500,outarg='@output[0]',parg='@prefixes[0]',length=None):
  i=len(vectors);vectors.append(b)
  if rc==0:
   expected=(header() if h is None else h)+b'\xa5'*24+rows+b'\xa5'*(256-len(rows))
  else:expected=b'\xa5'*368
  cases.append(dict(name=name,rc=rc,output=expected.hex()))
  steps.append(f'rc=IPv6RouterDecode(?V{i},{len(b) if length is None else length},{localarg},{mtu},{outarg},{parg},{cap})')
 add('header fields',packet())
 add('unspecified configuration fields preserved zero',packet(fields=(0,0,0,0,0)),h=header(fields=(0,0,0,0,0)))
 add('assigned unicast destination',packet(dest=local))
 add('multicast before address assignment',packet(),localarg='0')
 add('unicast without assigned address refused',packet(dest=local),-832,localarg='0')
 add('foreign unicast refused',packet(dest=addr('fe80::9999')),-832)
 add('foreign multicast refused',packet(dest=addr('ff02::2')),-832)
 add('global source refused',packet(source=addr('2001:db8::1')),-720)
 add('wrong hop limit refused',packet(hop=254),-720)
 add('nonzero ICMP code refused',packet(code=1),-720)
 b=bytearray(packet());b[-1]^=1;add('checksum refused',bytes(b),-721)
 add('atomic fragment refused',packet(fragment=True),-720)
 rsbody=b'\x85\0\0\0'+bytes(4)
 c=checksum(src+allnodes+struct.pack('>I3xB',8,58)+rsbody)
 rs=struct.pack('>IHBB',0x60000000,8,58,255)+src+allnodes+rsbody[:2]+struct.pack('>H',c)+rsbody[4:]
 add('wrong ND type refused',rs,-722)
 add('short packet refused',packet()[:39],-830)
 add('truncated IPv6 payload refused',packet()[:-1],-701)
 add('source MAC copied',packet(b'\x01\x01'+mac),h=header(sm=mac))
 add('duplicate source MAC refused',packet((b'\x01\x01'+mac)*2),-720)
 add('single prefix',packet(pio()),h=header(1),rows=row())
 add('multiple prefix lengths normalized',packet(pio(bits=63)+pio(bits=128)),h=header(2),rows=row(bits=63)+row(bits=128))
 add('zero prefix ignores all host bits',packet(pio('fe80::1',0)),h=header(1),rows=row('fe80::1',0))
 add('linklocal prefix ignored',packet(pio('fe80::1234')))
 add('multicast prefix ignored',packet(pio('ff02::1')))
 add('overlong prefix ignored',packet(pio(bits=129)))
 add('wrong sized PIO ignored',packet(b'\x03\x01'+b'\0'*6))
 add('unknown option ignored',packet(b'\xfa\x01'+b'\x11'*6))
 add('zero option length refuses entire packet',packet(b'\xfa\0'+b'\0'*6),-720)
 add('truncated option refuses entire packet',packet(b'\xfa\x02'+b'\0'*6),-720)
 add('prefix capacity refusal atomic',packet(pio()),-831,cap=0,parg='0')
 add('four prefix capacity exact',packet(pio()*4),h=header(4),rows=row()*4)
 add('one beyond capacity atomic',packet(pio()*4),-831,cap=3)
 add('invalid preferred lifetime retained for independent L policy',packet(pio(valid=1,preferred=2)),h=header(1),rows=row(valid=1,preferred=2))
 add('infinite and full flags',packet(pio(flags=255,valid=4294967295,preferred=4294967295)),h=header(1),rows=row(flags=255,valid=4294967295,preferred=4294967295))
 def mo(v):return b'\x05\x01\0\0'+struct.pack('>I',v)
 add('valid MTU',packet(mo(1400)),h=header(mtu=1400))
 add('minimum MTU',packet(mo(1280)),h=header(mtu=1280))
 add('maximum link MTU',packet(mo(1500)),h=header(mtu=1500))
 add('too small MTU ignored',packet(mo(1279)))
 add('too large MTU ignored',packet(mo(1501)))
 add('invalid later MTU preserves valid option',packet(mo(1400)+mo(1200)),h=header(mtu=1400))
 add('later valid MTU supersedes earlier',packet(mo(1400)+mo(1450)),h=header(mtu=1450))
 add('wrong sized MTU ignored',packet(b'\x05\x02'+bytes(14)))
 add('overlapping outputs refused',packet(),-830,parg='@output[0]')
 add('overlapping local and output refused',packet(),-830,localarg='@output[0]')
 add('invalid interface MTU refused',packet(),-830,mtu=1279)
 add('negative capacity refused',packet(),-830,cap=-1)
 add('excess capacity refused',packet(),-830,cap=2049)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_neighbor.pbi"\nXIncludeFile "Anvil/Network/ipv6_router.pbi"\n'+r'''

Global Dim output.a[112]
Global Dim prefixes.a[256]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*512
 PokeI(p,rc)
 For i=0 To 111 : PokeA(p+8+i,output[i]) : Next
 For i=0 To 255 : PokeA(p+120+i,prefixes[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$524F5554)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=' For i=0 To 111 : output[i]=$A5 : Next\n For i=0 To 255 : prefixes[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Local',local)]+[(f'V{i}',b) for i,b in enumerate(vectors)]:
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
