'''Build physical qualification of IPv6 recursive DNS advertisement decoding.'''
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_rdnss.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/internet_checksum.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
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

 def option(addresses,seconds=600):
  return bytes([25,1+2*len(addresses),0,0])+struct.pack('>I',seconds)+b''.join(addr(a) for a in addresses)
 def records(addresses,seconds=600):return b''.join(addr(a)+struct.pack('<q',seconds) for a in addresses)
 cases=[];vectors=[];steps=[]
 def add(name,b,expected=b'',rc=None,cap=128,localarg='?Local',outarg='@output[0]',length=None):
  i=len(cases);vectors.append(b);rc=len(expected)//24 if rc is None else rc
  cases.append(dict(name=name,rc=rc,output=(expected+b'\xa5'*(3104-len(expected))).hex()))
  steps.append(f'rc=IPv6RdnssDecode(?V{i},{len(b) if length is None else length},{localarg},{outarg},{cap})')
 a=['fe80::53','2001:4860:4860::8888','fd12::53']
 add('no DNS option',packet())
 add('three unicast scopes',packet(option(a)),records(a))
 add('zero withdraw preserved',packet(option(a,0)),records(a,0))
 add('infinity preserved',packet(option(a,4294967295)),records(a,4294967295))
 add('separate lifetimes and duplicate order',packet(option(a[:1],2)+option(a,3)),records(a[:1],2)+records(a,3))
 add('assigned unicast destination',packet(option(a),dest=local),records(a))
 add('multicast before assignment',packet(option(a)),records(a),localarg='0')
 add('foreign unicast refused',packet(option(a),dest=addr('fe80::9999')),rc=-912)
 add('unicast without assignment refused',packet(option(a),dest=local),rc=-912,localarg='0')
 add('global RA source refused',packet(option(a),source=addr('2001:db8::1')),rc=-720)
 add('wrong hop limit',packet(option(a),hop=254),rc=-720)
 b=bytearray(packet(option(a)));b[-1]^=1;add('bad checksum',bytes(b),rc=-721)
 add('atomic fragment refused',packet(option(a),fragment=True),rc=-720)
 add('zero option length',packet(b'\x19\0'+bytes(6)),rc=-720)
 add('truncated option',packet(b'\x19\x03'+bytes(14)),rc=-720)
 add('short DNS option ignored',packet(b'\x19\x01'+bytes(6)))
 add('even option length ignored',packet(b'\x19\x04'+bytes(30)))
 add('multicast invalidates whole option',packet(option([a[0],'ff02::1'])))
 add('unspecified invalidates whole option',packet(option([a[0],'::'])))
 add('bad option does not discard later valid one',packet(option(['::'])+option(a)),records(a))
 add('unknown option ignored',packet(b'\xfa\x01'+bytes(6)+option(a)),records(a))
 add('exact capacity',packet(option(a)),records(a),cap=3)
 add('capacity refusal atomic',packet(option(a)),rc=-911,cap=2)
 add('zero capacity refuses records',packet(option(a)),rc=-911,cap=0,outarg='0')
 add('null zero capacity no records',packet(),cap=0,outarg='0')
 add('output aliases input refused',packet(option(a)),rc=-910,outarg='?V25')
 add('local aliases output refused',packet(option(a)),rc=-910,localarg='@output[0]')
 add('negative capacity refused',packet(),rc=-910,cap=-1)
 add('oversized capacity refused',packet(),rc=-910,cap=4097)
 add('maximum option length',packet(option([a[0]]*127)),records([a[0]]*127),cap=127)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_rdnss.pbi"\n'+r"""
Global Dim output.a[3104]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*4096 : PokeI(p,rc)
 For i=0 To 3103 : PokeA(p+8+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$52444E53)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 for k,code in enumerate(steps):s+=' For i=0 To 3103 : output[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
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
