"""Build physical qualification of shared per-prefix IPv6 address lifetimes."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_slaac.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];inf=0x7fffffffffffffff
 state=[1,1000,0,0,0]
 def add(name,code,rc,new=None,address='20010db8000100021122334455667788'):
  nonlocal state
  if new is not None:state=new
  cases.append(dict(name=name,expected=[rc]+state,address=address));steps.append(code)
 def apply(t,l,a,v,p,auth=0,g=1):return f'rc=IPv6SlaacApply(@ctx,{g},{t},{l},{a},{v},{p},{auth})'
 def status(t,g=1):return f'rc=IPv6SlaacStatus(@ctx,{g},{t})'
 add('empty entry','rc=IPv6SlaacInit(@ctx,1,?Prefix,?Iid,1000)',0)
 add('new address needs DAD',apply(1000,1,1,10000,5000),1,[1,1000,10001000,10001000,5001000])
 add('preferred valid onlink',status(1000),7)
 add('zero lifetime clamps address but removes route',apply(2000,1,1,0,0),0,[1,2000,2000,7202000,2000])
 add('deprecated but valid',status(2000),1)
 add('short update preserves remaining validity',apply(3000,0,1,60,30),0,[1,3000,2000,7202000,33000])
 add('preferred deadline exact',status(33000),1,[1,33000,2000,7202000,33000])
 add('authenticated short remaining lifetime invalidates',apply(34000,0,1,0,0,1),0,[1,34000,2000,34000,34000])
 add('invalid exact deadline',status(34000),0)
 add('recreated address requires DAD again',apply(35000,0,1,100,50),1,[1,35000,2000,135000,85000])
 add('autonomous without onlink',status(35000),3)
 add('onlink independent of autonomous',apply(36000,1,0,10,100),0,[1,36000,46000,135000,85000])
 add('route expiry does not expire address',status(46000),3,[1,46000,46000,135000,85000])
 add('preferred expiry',status(85000),1,[1,85000,46000,135000,85000])
 add('valid expiry',status(135000),0,[1,135000,46000,135000,85000])
 add('infinite lifetimes',apply(136000,1,1,4294967295,4294967295),1,[1,136000,inf,inf,inf])
 add('infinite to short clamps two hours',apply(137000,0,1,1,1),0,[1,137000,inf,7337000,138000])
 add('long lifetime replaces clamp',apply(138000,0,1,9000,8000),0,[1,138000,inf,9138000,8138000])
 add('invalid autonomous lifetime still updates route',apply(139000,1,1,2,3),0,[1,139000,141000,9138000,8138000])
 add('short route expires independently',status(141000),3,[1,141000,141000,9138000,8138000])
 add('neither flag leaves lifetime state',apply(142000,0,0,0,0),0,[1,142000,141000,9138000,8138000])
 add('largest finite lifetime converted in 64 bits',apply(143000,0,1,4294967294,0),0,[1,143000,141000,4294967437000,143000])
 add('authenticated long remaining reduction follows rule three',apply(144000,0,1,0,0,1),0,[1,144000,141000,7344000,144000])
 add('stale generation refused',apply(145000,1,1,1,1,g=2),-821)
 add('backwards time refused',status(143999),-820)
 add('negative lifetime refused',apply(145000,1,1,-1,0),-820)
 add('lifetime exceeds wire width refused',apply(145000,1,1,4294967296,0),-820)
 add('invalid authentication flag refused',apply(145000,1,1,1,1,2),-820)
 add('invalid onlink flag refused',apply(145000,2,1,1,1),-820)
 add('invalid autonomous flag refused',apply(145000,1,2,1,1),-820)
 add('clock overflow refused',status(9223372036854775807),-820)
 add('generation restart','rc=IPv6SlaacInit(@ctx,2,?Prefix,?Iid,0)',0,[2,0,0,0,0])
 add('zero initial lifetime creates nothing',apply(1,1,1,0,0,g=2),0,[2,1,1,0,0])
 add('overlapping init refused','rc=IPv6SlaacInit(@ctx,3,@ctx,?Iid,0)',-820)
 add('same generation init refused','rc=IPv6SlaacInit(@ctx,2,?Prefix,?Iid,0)',-821)
 add('linklocal prefix refused','rc=IPv6SlaacInit(@ctx,3,?LinkLocal,?Iid,0)',-820)
 add('multicast prefix refused','rc=IPv6SlaacInit(@ctx,3,?Multicast,?Iid,0)',-820)
 add('absent interface ID refused','rc=IPv6SlaacInit(@ctx,3,?Prefix,0,0)',-820)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_address.pbi"\nXIncludeFile "Anvil/Network/ipv6_slaac.pbi"\n'+r'''
Global ctx.IPv6Slaac
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*128
 PokeI(p,rc)
 For i=0 To 55 : PokeA(p+8+i,PeekA(@ctx+i)) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$534C4141)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,b in [('Prefix',bytes.fromhex('20010db800010002ffffffffffffffff')),('Iid',bytes.fromhex('1122334455667788')),('LinkLocal',bytes.fromhex('fe800000000000000000000000000000')),('Multicast',bytes.fromhex('ff020000000000000000000000000001'))]:s+=name+':\n Data.a '+','.join(str(v) for v in b)+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
