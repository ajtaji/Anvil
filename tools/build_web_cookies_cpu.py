"""Compile bounded cookie lifecycle fixtures for physical execution."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/web_url.pbi','Anvil/Network/web_request.pbi','Anvil/Network/web_cookie_date.pbi','Anvil/Network/web_cookies.pbi'];cases=[]
 origin='https://www.example.com/account/login'
 def add(name,fields,expected,url=origin,request=None,now=1700000000,requestTime=None,same=1,top=0,policy=0,slots=4,cap=512,codes=None):
  if isinstance(fields,str):fields=[fields]
  cases.append(dict(name=name,fields=fields,expected=expected,url=url,request=request or url,now=now,requestTime=now if requestTime is None else requestTime,same=same,top=top,policy=policy,slots=slots,cap=cap,codes=codes or [0]*len(fields)))
 add('host','sid=one','sid=one')
 add('other-host','sid=one','',request='https://example.com/account/login')
 add('subdomain','sid=one','',request='https://sub.www.example.com/account/login')
 add('default-path','sid=one','',request='https://www.example.com/other')
 add('path-boundary','sid=one; Path=/account','',request='https://www.example.com/accounting')
 add('query-boundary','sid=one; Path=/account','sid=one',request='https://www.example.com/account?q=1')
 add('secure-http','sid=one; Secure','',request='http://www.example.com/account/login')
 add('secure-origin','sid=one; Secure','',url='http://www.example.com/',codes=[-663])
 add('http-only','sid=one; HttpOnly','sid=one')
 add('replacement',['sid=one','sid=two'],'sid=two')
 add('ordering',['a=root; Path=/','a=deep; Path=/account','b=last; Path=/'],'a=deep; a=root; b=last')
 add('replacement-keeps-order',['a=1','b=2','a=3'],'a=3; b=2')
 add('delete',['sid=one','sid=x; Max-Age=0'],'')
 add('negative-age',['sid=one','sid=x; Max-Age=-10'],'')
 add('expiry','sid=one; Max-Age=10','',requestTime=1700000010)
 add('before-expiry','sid=one; Max-Age=10','sid=one',requestTime=1700000009)
 add('past-date','sid=one; Expires=Wed, 09 Jun 2021 10:18:14 GMT','')
 add('future-date','sid=one; Expires=Wed, 09 Jun 2038 10:18:14 GMT','sid=one')
 add('old-format','sid=one; Expires=Wednesday, 09-Jun-21 10:18:14 GMT','')
 add('age-overrides-date','sid=one; Max-Age=10; Expires=Wed, 09 Jun 2021 10:18:14 GMT','sid=one')
 add('invalid-age-keeps-date','sid=one; Max-Age=10x; Expires=Wed, 09 Jun 2021 10:18:14 GMT','')
 add('overflow-age','sid=one; Max-Age=999999999999999999999999','sid=one')
 add('pre-epoch','sid=one; Expires=Wed, 31 Dec 1969 23:59:59 GMT','')
 add('strict-cross-site','sid=one; SameSite=Strict','',same=0,top=1)
 add('lax-subresource','sid=one','',same=0)
 add('lax-navigation','sid=one','sid=one',same=0,top=1)
 add('none-secure','sid=one; SameSite=None; Secure','sid=one',same=0)
 add('none-insecure','sid=one; SameSite=None','',codes=[-663])
 add('valid-host-prefix','__Host-sid=one; Secure; Path=/','__Host-sid=one')
 add('invalid-host-prefix','__Host-sid=one; Secure','',codes=[-663])
 add('invalid-secure-prefix','__Secure-sid=one','',codes=[-663])
 add('foreign-domain','sid=one; Domain=evil.test','',codes=[-663])
 add('parent-needs-policy','sid=one; Domain=example.com','',codes=[-663])
 add('policy-domain','sid=one; Domain=.EXAMPLE.com','sid=one',policy=1,request='https://other.example.com/account/x')
 add('public-suffix-refused','sid=one; Domain=com','',policy=1,codes=[-663])
 add('equal-domain-narrowed','sid=one; Domain=www.example.com','',request='https://sub.www.example.com/account/x')
 add('partitioned','sid=one; Partitioned; Secure','',codes=[-664])
 add('injection','sid=one\r\nX:y','',codes=[-661])
 add('quoted','sid="one"','sid="one"')
 add('short-header','sid=one','sid=one',cap=3)
 add('full-jar',['a=1','b=2'],'a=1',slots=1,codes=[0,-662])
 add('invalid-name','a b=x','',codes=[-661])
 add('invalid-value','a=x,y','',codes=[-661])
 add('empty-value','a=','a=')
 add('empty-path','a=1; Path=','a=1')
 add('spaces','  a \t= \t1\t ; Path= /account\t ','a=1')
 add('short-target','a=1; Path=/account','',request='https://www.example.com/')
 add('leap-valid','a=1; Expires=Mon, 29 Feb 2032 00:00:00 GMT','a=1')
 add('expired-slot-reuse',['a=1; Max-Age=0','b=2'],'b=2',slots=1)
 for name,second,expected,code,policy in [('secure-overwrite','sid=bad; Path=/account','sid=good',-663,0),('secure-parent-overlay','sid=bad; Domain=example.com; Path=/account','sid=good',-663,1),('secure-deeper-overlay','sid=bad; Path=/account/login','sid=good',-663,0),('secure-wider-path','sid=wide; Path=/','sid=good; sid=wide',0,0)]:
  add(name,['sid=good; Secure; Path=/account',second],expected,codes=[0,code],policy=policy)
  cases[-1]['field_urls']=[origin,origin.replace('https:','http:')]
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global jar.WebCookies
Global u.WebUrl
Global Dim storage.a[4*#WEB_COOKIE_STRIDE]
Global Dim host.a[256]
Global Dim target.a[1024]
Global Dim field.a[8192]
Global Dim output.a[1024]
Procedure.i Allowed(domain.i,bytes.i)
 ProcedureReturn wckEqual(domain,bytes,"EXAMPLE.com",11,1)
EndProcedure
Procedure Url(v.i)
 Define n.i,rc.i
 n=0 : While PeekA(v+n)<>0 : n=n+1 : Wend
 u\host=@host[0] : u\hostCapacity=256 : u\target=@target[0] : u\targetCapacity=1024
 rc=WebUrlParse(v,n,1,@u)
EndProcedure
Procedure Store(p.i,n.i,now.i)
 Define i.i,rc.i
 For i=0 To n-1 : Read.a field[i] : Next
 rc=WebCookieStore(@jar,@u,@field[0],n,now) : PokeI(p,rc)
EndProcedure
Procedure CookieFixtureResult(p.i,now.i,same.i,top.i,capacity.i)
 Define i.i,n.i,query.i,wipe.i
 For i=0 To 1023 : output[i]=$A5 : Next
 query=WebCookieHeader(@jar,@u,now,same,top,0,0)
 n=WebCookieHeader(@jar,@u,now,same,top,@output[0],capacity)
 PokeI(p,n) : PokeI(p+8,query)
 For i=0 To 767 : PokeA(p+128+i,output[i]) : Next
 wipe=WebCookiesClear(@jar)
 For i=0 To jar\slots*#WEB_COOKIE_STRIDE-1 : If storage[i]<>0 : wipe=-999 : EndIf : Next
 PokeI(p+16,wipe)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i,policy.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$57434B31)
'''
 s+=f' PokeI($E1C00008,{len(cases)})\n'
 for i,c in enumerate(cases):
  s+=f' policy=0\n'
  if c['policy']:s+=' policy=@Allowed\n'
  s+=f' rc=WebCookiesInit(@jar,@storage[0],{c["slots"]},policy)\n Url("{c["url"]}")\n'
  for j,f in enumerate(c['fields']):
   if 'field_urls' in c:s+=f' Url("{c["field_urls"][j]}")\n'
   s+=f' Restore Case{i}_{j}\n Store($E1C00120+{i}*1024+{j}*8,{len(f.encode())},{c["now"]})\n'
  s+=f' Url("{c["request"]}")\n CookieFixtureResult($E1C00100+{i}*1024,{c["requestTime"]},{c["same"]},{c["top"]},{c["cap"]})\n'
 s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(cases):
  for j,f in enumerate(c['fields']):s+=f'Case{i}_{j}:\n Data.a '+','.join(map(str,f.encode()))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
