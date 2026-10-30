"""Build physical URL and HTTPS request-component regression coverage."""
from pathlib import Path
import argparse,json,hashlib,subprocess,os,re
from pmf_compiler import resolve_compiler

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 # Independent URI examples: URL, default scheme, code, host, port, secure,
 # explicit port, target. Unsuccessful rows carry no usable output.
 cases=[
 ('https://Example.COM',0,0,'example.com',443,1,0,'/'),
 ('HTTP://example.com/a?b=1#frag',1,0,'example.com',80,0,0,'/a?b=1'),
 ('https://example.com?x=1',0,0,'example.com',443,1,0,'/?x=1'),
 ('https://example.com#part',0,0,'example.com',443,1,0,'/'),
 ('https://example.com:8443/a',0,0,'example.com',8443,1,1,'/a'),
 ('localhost:443?q=a%20b',1,0,'localhost',443,1,1,'/?q=a%20b'),
 ('h',1,0,'h',443,1,0,'/'),('a.',0,0,'a.',80,0,0,'/'),
 ('https://example.com/%2F?q=%23',1,0,'example.com',443,1,0,'/%2F?q=%23'),
 ('https://127.0.0.1:65535/',0,0,'127.0.0.1',65535,1,1,'/'),
 ('',1,-500),('ftp://example.com',1,-501),('xhttps://example.com',1,-501),
 ('https://',1,-502),('/relative',1,-502),('https://user@example.com',1,-502),
 ('https://[::1]/',1,0,'[::1]',443,1,0,'/'),('https://a:0',1,-503),('https://a:65536',1,-503),
 ('https://a:',1,-503),('https://a:12x',1,-503),('https://a:1:2',1,-503),
 ('https://-a/',1,-502),('https://a..b/',1,-502),('https://a-/x',1,-502),
 ('https://a/x\r\nInjected:1',1,-504),('https://a/%x0',1,-504),('https://a/%',1,-504),
 ('https://a/\\x',1,-504),('https://a/'+('x'*3072),1,-505),
 ('https://a/',2,-500),('https://a/<x>',1,-504),('https://a/é',1,-504),
 ]
 cases += [
 ('http://[FD3F::1234]:8080/health',0,0,'[fd3f::1234]',8080,0,1,'/health'),
 ('http://[2001:db8::1]?a=1#f',0,0,'[2001:db8::1]',80,0,0,'/?a=1'),
 ('http://[::ffff:192.0.2.1]/',0,0,'[::ffff:192.0.2.1]',80,0,0,'/'),
 ('http://[::1',0,-506),('http://[]/',0,-506),('http://[gg::1]/',0,-506),
 ('http://[::1]suffix/',0,-502),('http://[::1]:0/',0,-503),
 ('http://[::1]:65536/',0,-503),('http://[::1]:/',0,-503),
 ('http://[fe80::1%25wifi]/',0,-506),('http://[1:2:3]/',0,-506),
 ('http://[1::2::3]/',0,-506),('http://[::1]@evil/',0,-502)]
 s=(r/'Anvil/Network/web_url.pbi').read_text(encoding='utf8')+'\nGlobal parsed.WebUrl\nGlobal Dim hostBytes.a[256]\nGlobal Dim targetBytes.a[3072]\n'
 s+='''Procedure Save(index.i,text.i,bytes.i,secure.i)
 Define rc.i,p.i,i.i
 parsed\\host=@hostBytes[0] : parsed\\hostCapacity=256
 parsed\\target=@targetBytes[0] : parsed\\targetCapacity=3072
 rc=WebUrlParse(text,bytes,secure,@parsed) : p=$E1C00100+index*448
 For i=0 To 447 : PokeA(p+i,0) : Next
 PokeI(p,rc)
 If rc=0
  PokeI(p+8,parsed\\port) : PokeI(p+16,parsed\\secure) : PokeI(p+24,parsed\\explicitPort)
  PokeI(p+32,parsed\\hostLength) : PokeI(p+40,parsed\\targetLength)
  For i=0 To parsed\\hostLength : PokeA(p+48+i,PeekA(parsed\\host+i)) : Next
  For i=0 To parsed\\targetLength : PokeA(p+304+i,PeekA(parsed\\target+i)) : Next
 EndIf
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 32767 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$55524C31)
'''
 for i,c in enumerate(cases):s+=f' Save({i},?url{i},{len(c[0].encode())},{c[1]})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(cases):s+=f'url{i}:\n Data.a '+','.join(str(x) for x in c[0].encode()+b'\0')+'\n'
 s+='EndDataSection\n';p=d/'proof.pi4';p.write_text(s,encoding='utf8')
 c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1300:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c07fff']}
 p=d/'proof.img.pmf';names=['Anvil/Network/web_url.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi']
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':main()
