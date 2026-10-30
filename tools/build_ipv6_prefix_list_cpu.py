'''Physical tests for merged on-link IPv6 prefix state and expiry.'''
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_prefix_list.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 ips={'P1':'2001:db8:1:2::abcd','P2':'2001:db8:2:3::42','P4':'2001:db8::77','Alternate':'2001:db8:1:ffff::7','Same':'2001:db8:1:2::9999','LinkLocal':'fe80::1','Multicast':'ff02::1','Zero':'::'}
 cases=[];steps=[];state=[1,0,1];rows=[(None,0,0)]*3
 def wire():
  b=b''
  for name,bits,t in rows:b+=(ipaddress.IPv6Network((ips[name],bits),strict=False).network_address.packed if name else bytes(16))+struct.pack('<2q',bits,t)
  return b
 def add(name,code,rc,new=None,change=None,reset=False):
  nonlocal state,rows
  if new is not None:state=new
  if reset:rows=[(None,0,0)]*3
  if change:
   for i,v in change.items():rows[i]=v
  cases.append(dict(name=name,expected=[rc]+state,rows=wire().hex()));steps.append(code)
 def app(p,bits,t,secs,l=1,g=1):return f'rc=IPv6PrefixListApply(@ctx,{g},{t},?{p},{bits},{l},{secs})'
 def match(p,t,g=1):return f'rc=IPv6PrefixListMatch(@ctx,{g},{t},?{p})'
 def tick(t,g=1):return f'rc=IPv6PrefixListTick(@ctx,{g},{t})'
 add('initialize','rc=IPv6PrefixListInit(@ctx,1,@rows[0],3,0)',0)
 add('first router prefix',app('P1',64,0,10),0,[1,0,2],{0:('P1',64,10000)})
 add('second router prefix merges',app('P2',64,1,20),0,[1,1,3],{1:('P2',64,20001)})
 add('first prefix retained',match('P1',2),65,[1,2,3])
 add('overlapping shorter prefix',app('P1',48,3,30),0,[1,3,4],{2:('P1',48,30003)})
 add('longest prefix selected',match('P1',4),65,[1,4,4])
 add('shorter prefix reaches another subnet',match('Alternate',5),49,[1,5,4])
 add('L zero does not withdraw',app('P1',64,6,0,0),0,[1,6,4])
 add('withdraw only second prefix',app('P2',64,7,0),0,[1,7,5],{1:('P2',64,0)})
 add('withdrawn subnet absent',match('P2',8),0,[1,8,5])
 add('host bits do not duplicate identity',app('Same',64,9,15),0,[1,9,5],{0:('P1',64,15009)})
 add('host route reuses free slot',app('P4',128,10,1),0,[1,10,6],{1:('P4',128,1010)})
 add('capacity retains live prefixes',app('P2',64,11,10),1,[1,11,6])
 add('host route exact expiry',tick(1010),1,[1,1010,7],{1:('P4',128,0)})
 add('infinite default onlink prefix',app('Zero',0,1011,4294967295),0,[1,1011,8],{1:('Zero',0,9223372036854775807)})
 add('zero length match distinguishable from none',match('P2',1012),1,[1,1012,8])
 add('first independent expiry',tick(15009),1,[1,15009,9],{0:('P1',64,0)})
 add('shorter prefix remains',match('P1',15010),49,[1,15010,9])
 add('second independent expiry',tick(30003),1,[1,30003,10],{2:('P1',48,0)})
 add('infinite prefix remains',match('P1',30004),1,[1,30004,10])
 add('withdraw infinite prefix',app('Zero',0,30005,0),0,[1,30005,11],{1:('Zero',0,0)})
 add('non-octet prefix and largest finite seconds',app('P2',63,30006,4294967294),0,[1,30006,12],{0:('P2',63,4294967324006)})
 add('non-octet matching',match('P2',30007),64,[1,30007,12])
 add('linklocal advertisement ignored',app('LinkLocal',64,30008,100),0,[1,30008,12])
 add('multicast advertisement ignored',app('Multicast',16,30009,100),0,[1,30009,12])
 add('stale generation refused',app('P1',64,30010,1,g=2),-851)
 add('backwards clock refused',tick(30008),-850)
 add('invalid prefix length refused',app('P1',129,30010,1),-850)
 add('invalid L flag refused',app('P1',64,30010,1,2),-850)
 add('oversized lifetime refused',app('P1',64,30010,4294967296),-850)
 add('generation restart','rc=IPv6PrefixListInit(@ctx,2,@rows[0],3,0)',0,[2,0,1],reset=True)
 add('empty match',match('P1',0,2),0)
 add('unknown zero lifetime ignored',app('P1',64,1,0,g=2),0,[2,1,1])
 add('owned span alias refused','rc=IPv6PrefixListApply(@ctx,2,2,@rows[0],64,1,1)',-850)
 add('query span alias refused','rc=IPv6PrefixListMatch(@ctx,2,2,@rows[0])',-850)
 add('insufficient initial capacity refused','rc=IPv6PrefixListInit(@ctx,3,@rows[0],0,0)',-850)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_address.pbi"\nXIncludeFile "Anvil/Network/ipv6_prefix_list.pbi"\n'+r'''
Global ctx.IPv6PrefixList
Global Dim rows.a[112]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*256
 PokeI(p,rc) : PokeI(p+8,ctx\generation) : PokeI(p+16,ctx\lastNow) : PokeI(p+24,ctx\revision)
 For i=0 To 111 : PokeA(p+32+i,rows[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 For i=0 To 111 : rows[i]=$A5 : Next
 PokeI($E1C00000,$50524658)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,ip in ips.items():s+=name+':\n Data.a '+','.join(str(v) for v in ipaddress.IPv6Address(ip).packed)+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
