"""Physical source-policy and IPv6 HTTP authority wire checks."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_source.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(b);return f'?V{len(vectors)-1}'
 def add(name,code,rc,wire=b''):
  cases.append(dict(name=name,expected=[rc]+[-1]*9,wire=wire.hex()));steps.append(code)
 def compare(name,d,a,b,want,ad=0,bd=0,ap=64,bp=64):
  ps=[vec(ipaddress.IPv6Address(x).packed) for x in (d,a,b)]
  add(name,f'rc=IPv6SourceBetter({ps[0]},{ps[1]},{ad},{ap},{ps[2]},{bd},{bp})',want)
 compare('same address before deprecation','fd00::1','fd00::1','fd00::2',1,ad=1)
 compare('existing exact destination retained','fd00::1','fd00::2','fd00::1',0)
 compare('link scope before deprecation','fe80::9','fe80::1','fd00::1',1,ad=1)
 compare('adequate global scope wins','2001:db8::9','2001:db8::1','fe80::1',1)
 compare('insufficient candidate scope loses','2001:db8::9','fe80::1','fd00::1',0)
 compare('preferred before matching prefix','fd00:1::9','fd00:2::1','fd00:1::1',1,bd=1)
 compare('deprecated candidate loses','fd00:1::9','fd00:1::1','fd00:2::1',0,ad=1)
 compare('ULA label preferred for ULA','fd00:1::9','fd00:2::1','2001:db8::1',1)
 compare('global label preferred for global','2001:db8::9','2001:db9::1','fd00::1',1)
 compare('longer network prefix','fd00:1::9','fd00:1::1','fd00:2::1',1)
 compare('interface ID ignored by prefix cap','fd00:1::ff','fd00:1::fe','fd00:1::1',0)
 compare('scope link wins over site','fe80::9','fe80::1','fec0::1',1)
 compare('scope site insufficient for global','2001:db8::9','fec0::1','fd00::1',0)
 compare('bad prefix refused','fd00::9','fd00::1','fd00::2',-894,ap=129)
 compare('unspecified candidate refused','fd00::9','::','fd00::2',-894)
 compare('multicast source refused','fd00::9','ff02::1','fd00::2',-894)
 for name,url,expected in [
  ('IPv6 Host bracket and port','http://[FD3F::1234]:8080/health','GET /health HTTP/1.1\r\nHost: [fd3f::1234]:8080\r\nConnection: close\r\n\r\n'),
  ('IPv6 default port','http://[2001:db8::1]/a?q=x','GET /a?q=x HTTP/1.1\r\nHost: [2001:db8::1]\r\nConnection: close\r\n\r\n'),
  ('IPv4 serialization retained','http://192.0.2.1:8080/','GET / HTTP/1.1\r\nHost: 192.0.2.1:8080\r\nConnection: close\r\n\r\n'),
  ('DNS serialization retained','http://Example.COM/','GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n')]:
  p=vec(url.encode());code=f'rc=WebUrlParse({p},{len(url)},0,@url)\n If rc=0 : rc=WebRequestInit(@request,@url,"GET",3,0,0,@output[0],1514) : EndIf\n If rc=0 : rc=WebRequestFinishHeaders(@request) : EndIf'
  add(name,code,0,expected.encode())
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_source.pbi"\nXIncludeFile "Anvil/Network/web_request.pbi"\n'+r'''
Global Dim output.a[1514]
Global Dim host.a[256]
Global Dim target.a[3072]
Global url.WebUrl,request.WebRequest
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048 : PokeI(p,rc)
 For i=1 To 9 : PokeI(p+i*8,-1) : Next
 For i=0 To 1513 : PokeA(p+80+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$53454C36)
 url\host=@host[0] : url\hostCapacity=256 : url\target=@target[0] : url\targetCapacity=3072
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+='For i=0 To 1513 : output[i]=$A5 : Next\n'+code+f'\nSave({k},rc)\n'
 s+=f'PokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,b in enumerate(vectors):s+=f'V{i}:\n Data.a '+','.join(map(str,b))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
