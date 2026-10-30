"""Qualify explicit DNS resolver selection without changing leases or routes."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Core/dns_policy.pbi','Anvil/Core/netfmt.pbi']
 fmt=(root/names[1]).read_text();parse=re.search(r'^Procedure.i ParseDotted\(.*?^EndProcedure',fmt,re.M|re.S).group(0)
 s=parse+'\nXIncludeFile "Anvil/Core/dns_policy.pbi"\n'+r'''
Global fixtureSetting.i,fixtureRoute.i,fixtureLease.i
Procedure.i SettingsGet(key.i)
 ProcedureReturn fixtureSetting
EndProcedure
Procedure.i EthKeyDns()
 ProcedureReturn "net.dns"
EndProcedure
Procedure.i NetIfForDest(ip.i)
 ProcedureReturn fixtureRoute
EndProcedure
Procedure.i NetIfDns(kind.i)
 ProcedureReturn fixtureLease
EndProcedure
Procedure PolicyFixture(index.i,setting.i,route.i,lease.i,kind.i)
 Define p.i
 fixtureSetting=setting : fixtureRoute=route : fixtureLease=lease
 p=$E1C00100+index*32
 PokeI(p,NetDnsResolverFor(kind)) : PokeI(p+8,fixtureLease) : PokeI(p+16,fixtureRoute)
EndProcedure
Procedure.i Main()
 Define i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$444E5350) : PokeI($E1C00008,12)
 PolicyFixture(0,0,1,$08080808,1)
 PolicyFixture(1,"1.1.1.1",1,$08080808,1)
 PolicyFixture(2,"1.1.1.1",2,$08080808,1)
 PolicyFixture(3,"1.1.1.1",2,$08080808,2)
 PolicyFixture(4,"bad",1,$08080808,1)
 PolicyFixture(5,"255.255.255.255",1,$08080808,1)
 PolicyFixture(6,"0.0.0.0",1,$08080808,1)
 PolicyFixture(7,"1.1.1.1",0,$08080808,1)
 PolicyFixture(8,0,1,$08080808,1)
 PolicyFixture(9,0,1,0,1)
 PolicyFixture(10,"1.1.1.1",0,$08080808,0)
 PolicyFixture(11,0,2,$08080404,2)
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=list(range(12))),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
