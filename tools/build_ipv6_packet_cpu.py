"""Build returning physical IPv6 header and extension parsing fixtures."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_packet.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Network/internet_checksum.pbi']
 src=ipaddress.IPv6Address('2001:db8::1').packed;dst=ipaddress.IPv6Address('fe80::abcd').packed
 def packet(proto,data):return struct.pack('!IHBB',0x6a512345,len(data),proto,64)+src+dst+data
 cases=[];vectors=[]
 def add(name,p,rc=0,offset=40,proto=None,length=None,action=0):
  c=dict(name=name,rc=rc,action=action)
  if rc==0:c.update(header=p[:40].hex(),packet_bytes=40+int.from_bytes(p[4:6],'big'),offset=offset,protocol=p[6] if proto is None else proto,payload_bytes=len(p)-offset if length is None else length)
  cases.append(c);vectors.append(p)
 add('UDP payload',packet(17,b'hello'))
 add('no next header ignores tail',packet(59,b'ignored'),length=0)
 add('empty no next',packet(59,b''),length=0)
 add('unknown transport delivered',packet(250,b'abc'))
 add('hop options padding',packet(0,bytes([17,0,0,1,3,0,0,0])+b'abc'),offset=48,proto=17)
 add('destination skip option',packet(60,bytes([6,0,30,2,4,5,0,0])+b'123'),offset=48,proto=6)
 for action in [1,2,3]:add('unknown option action '+str(action),packet(60,bytes([17,0,action*64,0,0,0,0,0])),rc=-705,action=action)
 add('bad option length',packet(60,bytes([17,0,30,7,0,0,0,0])),rc=-701)
 add('routing ignored zero segments',packet(43,bytes([17,0,77,0,0,0,0,0])+b'x'),offset=48,proto=17)
 add('deprecated route zero segments',packet(43,bytes([17,0,0,0,0,0,0,0])+b'x'),offset=48,proto=17)
 add('routing requires forwarding',packet(43,bytes([17,0,77,1,0,0,0,0])),rc=-706)
 add('atomic fragment',packet(44,struct.pack('!BBHI',17,0,0,1234)+b'abc'),offset=48,proto=17)
 for flags in [1,8,65529]:add('fragment flags '+str(flags),packet(44,struct.pack('!BBHI',17,0,flags,1234)+b'abc'),rc=-704)
 add('duplicate fragment',packet(44,struct.pack('!BBHI',44,0,0,1234)+struct.pack('!BBHI',17,0,0,1234)),rc=-703)
 add('hop header wrong position',packet(60,bytes([0,0,0,0,0,0,0,0])+bytes([17,0,0,0,0,0,0,0])),rc=-703)
 add('nine extensions',packet(60,bytes([60,0,0,0,0,0,0,0])*8+bytes([17,0,0,0,0,0,0,0])),rc=-707)
 for proto in [50,51]:add('unsupported security '+str(proto),packet(proto,b'abcdefghi'),rc=-703)
 add('extension too long',packet(60,bytes([17,2,0,0,0,0,0,0])),rc=-701)
 add('extension too short',packet(60,b'abc'),rc=-701)
 normal=packet(17,b'hello')
 for n in range(40):add('truncated header '+str(n),normal[:n],rc=-701)
 add('truncated payload',normal[:-1],rc=-701)
 add('wrong version',bytes([0x4a])+normal[1:],rc=-702)
 add('ethernet padding ignored',normal+b'padding',length=5)
 s='\n'.join('XIncludeFile "'+names[i]+'"' for i in [0,2])+'\n'+r'''
Global wtable.i
Global *pet
Global view.IPv6PacketView
Global Dim header.a[64]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure PacketFixture(index.i,data.i,n.i)
 Define p.i,rc.i,i.i,small.i,built.i,guards.i,plen.i,proto.i
 p=$E1C00100+index*256
 rc=IPv6PacketParse(data,n,@view)
 PokeI(p,rc) : PokeI(p+64,view\errorOffset) : PokeI(p+72,view\optionAction)
 If rc=0
  PokeI(p+8,view\packetBytes) : PokeI(p+16,view\payload-data) : PokeI(p+24,view\payloadBytes)
  PokeI(p+32,view\protocol) : PokeI(p+40,view\hopLimit) : PokeI(p+48,view\trafficClass) : PokeI(p+56,view\flowLabel)
  For i=0 To 63 : header[i]=$A5 : Next
  plen=NetReadBE16(data+4) : proto=PeekA(data+6)
  small=IPv6PacketHeader(@header[0],39,view\source,view\destination,plen,proto,64,165,$12345)
  guards=1
  If small<>#IPV6_PACKET_ARGUMENT : guards=0 : EndIf
  For i=0 To 63 : If header[i]<>$A5 : guards=0 : EndIf : Next
  built=IPv6PacketHeader(@header[0],64,view\source,view\destination,plen,proto,64,165,$12345)
  For i=40 To 63 : If header[i]<>$A5 : guards=0 : EndIf : Next
  PokeI(p+80,built) : PokeI(p+88,guards)
  For i=0 To 39 : PokeA(p+128+i,header[i]) : Next
  For i=0 To 15 : PokeA(p+176+i,PeekA(view\source+i)) : PokeA(p+192+i,PeekA(view\destination+i)) : Next
 EndIf
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$49503632)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,p in enumerate(vectors):s+=f' PacketFixture({i},?IPv6PacketVector{i},{len(p)})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,p in enumerate(vectors):
  s+=f'IPv6PacketVector{i}:\n'
  for j in range(0,len(p)+1,24):s+=' Data.a '+','.join(str(x) for x in (p+b'Z')[j:j+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
