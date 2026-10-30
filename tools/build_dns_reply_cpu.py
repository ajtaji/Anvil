"""Build DNS answer ownership and cache expiry checks for a physical Pi 4."""
from pathlib import Path
import argparse, hashlib, json, os, re, struct, subprocess
from pmf_compiler import resolve_compiler


def name(text):
    return b''.join(bytes([len(x)]) + x.encode('ascii') for x in text.rstrip('.').split('.')) + b'\0'


def answer(owner, kind, data, ttl=60):
    return owner + struct.pack('>HHIH', kind, 1, ttl, len(data)) + data


def packet(records, question='example.test', flags=0x8180, qtype=1, qd=1):
    return struct.pack('>6H', 0x1234, flags, qd, len(records), 0, 0) + name(question) + struct.pack('>HH', qtype, 1) + b''.join(records)


def build(compiler, out):
    root=Path(__file__).resolve().parents[1]
    out.mkdir(parents=True,exist_ok=False)
    ptr=b'\xc0\x0c'; ip=b'\x01\x02\x03\x04'; alias=name('alias.test')
    a=lambda owner=ptr,ttl=60:answer(owner,1,ip,ttl)
    cn=lambda owner=ptr,target=alias,ttl=7:answer(owner,5,target,ttl)
    cases=[]
    def add(label, raw, rc, ttl=0, expected='example.test', qtype=1, ip6=''):
        cases.append(dict(name=label,packet=raw.hex(),expected=expected,rc=rc,ttl=ttl,ip=0x01020304 if rc>0 and qtype==1 else 0,qtype=qtype,ip6=ip6 if rc>0 else ''))
    add('matching',packet([a()]),1,60)
    add('case-and-trailing-dot',packet([a()],question='ExAmPlE.TeSt'),1,60,'EXAMPLE.TEST.')
    add('wrong-question',packet([a()],question='another.test'),-208)
    add('unrelated-address',packet([a(name('unrelated.test'))]),0)
    add('address-before-alias',packet([a(alias,30),cn()]),1,7)
    add('alias-before-address',packet([cn(),a(alias,30)]),1,7)
    add('two-aliases',packet([cn(alias,name('last.test'),3),a(name('last.test'),30),cn()]),1,3)
    add('zero-ttl',packet([a(ttl=0)]),1,0)
    add('high-bit-ttl',packet([a(ttl=0x80000001)]),1,0)
    add('rrset-minimum',packet([a(ttl=60),a(ttl=15)]),2,15)
    add('nxdomain',packet([],flags=0x8183),-206)
    add('wrong-question-nxdomain',packet([],question='another.test',flags=0x8183),-208)
    add('truncated-response',packet([a()],flags=0x8380),-209)
    add('malformed-after-valid',packet([a(),a()])[:-1],-207)
    add('owner-pointer-loop',packet([a(b'\xc0\x1e')]),-207)
    add('wrong-type',packet([a()],qtype=28),-208)
    add('no-question',packet([a()],qd=0),-208)
    add('wrong-opcode',packet([a()],flags=0x8980),-205)
    add('conflicting-alias',packet([cn(),cn(target=name('other.test'))]),-210)
    add('alias-cycle',packet([cn(),cn(alias,name('example.test'))]),-210)
    add('alias-and-address',packet([cn(),a()]),-210)
    add('alias-trailing-byte',packet([cn(target=alias+b'\0'),a(alias)]),-207)
    add('alias-zero-ttl',packet([cn(ttl=0),a(alias)]),1,0)
    add('alias-high-bit-ttl',packet([cn(ttl=0xffffffff),a(alias)]),1,0)
    add('duplicate-alias-minimum',packet([cn(ttl=30),cn(ttl=4),a(alias)]),1,4)
    add('eight-results-minimum-in-ninth',packet([a(ttl=60)]*8+[a(ttl=1)]),8,1)
    add('unrelated-alias-ignored',packet([a(),cn(name('other.test'),name('missing.test'),0)]),1,60)
    add('too-many-answers',packet([a()]*65),-207)
    add('wrong-id',b'\x43\x21'+packet([a()])[2:],-204)
    add('short-header',b'\0'*11,-203)
    ip6=bytes.fromhex('20010db800000000123456789abcdef0')
    a6=lambda owner=ptr,ttl=60,data=ip6:answer(owner,28,data,ttl)
    def add6(label,records,rc=1,ttl=60,**kw):
        add(label,packet(records,qtype=28,**kw),rc,ttl if rc>0 else 0,qtype=28,ip6=ip6.hex())
    add6('aaaa-direct',[a6()])
    add6('aaaa-alias',[cn(),a6(alias)],ttl=7)
    add6('aaaa-order',[a6(alias),cn()],ttl=7)
    add6('aaaa-ignore-a',[a(),a6()])
    add6('aaaa-only-a',[a()],rc=0)
    add6('aaaa-short',[a6(data=ip6[:-1])],rc=-207)
    add6('aaaa-long',[a6(data=ip6+b'\0')],rc=-207)
    add6('aaaa-wrong-host',[a6()],rc=-208,question='wrong.test')
    add6('aaaa-unrelated',[a6(name('wrong.test'))],rc=0)
    add6('aaaa-alias-conflict',[cn(),a6()],rc=-210)
    add6('aaaa-cycle',[cn(),cn(alias,name('example.test'))],rc=-210)
    add6('aaaa-truncated',[a6()],rc=-209,flags=0x8380)
    add6('aaaa-ttl-zero',[a6(ttl=0)],ttl=0)
    add6('aaaa-minimum-ninth',[a6()]*8+[a6(ttl=2)],rc=8,ttl=2)
    add('aaaa-question-a',packet([a6()]),-208,qtype=28)
    names=['Anvil/Network/byte_order.pbi','Anvil/Network/dns_codec.pbi','Anvil/Core/payload_net.pbi']
    owner=(root/names[2]).read_text(encoding='utf8')
    start=owner.index('Procedure.i paynet_Lower(')
    end=owner.index('; ======================================================================',owner.index('Procedure paynet_CachePut(',start))
    cache=owner[start:end]
    s='XIncludeFile "Anvil/Network/dns_codec.pbi"\n'+r'''
#PAYNET_DNS_NAME=256
#PAYNET_DNS_CACHE=4
#PAYNET_DNS_CACHE_MS=300000
#PAYNET_DNS_TRY_MS=1500
#PAYNET_DNS_TRIES=3
Global Dim paynet_cacheName.a[1024]
Global Dim paynet_cacheIp.i[4]
Global Dim paynet_cacheAt.i[4]
Global Dim paynet_cacheMs.i[4]
Global Dim paynet_cacheUsed.i[4]
Global paynet_cacheNext.i
Global Dim wire.a[4096]
'''+cache+r'''
Procedure Run(index.i,bytes.i,expected.i,qtype.i)
 Define i.i,p.i,rc.i
 For i=0 To bytes-1 : Read.a wire[i] : Next
 p=$E1C00100+index*64
 rc=DnsParseReplyTypeFor(@wire[0],bytes,$1234,expected,qtype)
 PokeI(p,rc) : PokeI(p+8,DnsError()) : PokeI(p+16,DnsResultCount())
 PokeI(p+24,DnsResultIp(0)) : PokeI(p+32,DnsResultTtl(0))
 PokeI(p+40,DnsResultTtl(-1)) : PokeI(p+48,DnsResultTtl(DnsResultCount()))
 p=$E1C02000+index*32
 PokeI(p,DnsResultIp6(0,p+8))
EndProcedure
Procedure Cache(index.i,ttl.i,at.i,first.i,second.i)
 Define i.i,p.i
 For i=0 To 3 : paynet_cacheUsed[i]=0 : Next
 paynet_cacheNext=0
 paynet_CachePut("example.test",$01020304,at,ttl)
 p=$E1C01000+index*32
 PokeI(p,paynet_CacheFind("EXAMPLE.TEST",first))
 PokeI(p+8,paynet_CacheFind("example.test",second))
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$444E5332)
'''
    s+=f' PokeI($E1C00008,{len(cases)})\n'
    for i,c in enumerate(cases):
        s+=f' Restore Packet{i}\n Run({i},{len(bytes.fromhex(c["packet"]))},"{c["expected"]}",{c["qtype"]})\n'
    queries=[('example.test',28,30,0),('example.test',1,30,0),('example.test',15,0,-200),('a'*64,28,0,-202),('.bad',28,0,-202),('bad..name',28,0,-202),('.'.join(['a'*63]*3+['a'*61]),28,271,0),('.'.join(['a'*63]*3+['a'*62]),28,0,-201)]
    for i,(text,kind,want,err) in enumerate(queries):
        s+=f' PokeI($E1C03000+{i}*32,DnsBuildQueryType("{text}",$1234,{kind}))\n PokeI($E1C03008+{i}*32,DnsError())\n PokeI($E1C03010+{i}*32,DnsQueryLen())\n'
    s+=''' Cache(0,2,1000,2999,3000)
 Cache(1,0,1000,1001,1002)
 Cache(2,0,1000,5500,5501)
 Cache(3,2,$FFFFFF00,$100,$6D0)
 Cache(4,$7FFFFFFF,1000,300999,301000)
 ProcedureReturn 0
EndProcedure
DataSection
'''
    for i,c in enumerate(cases):
        s+=f'Packet{i}:\n'
        data=bytes.fromhex(c['packet'])
        for j in range(0,len(data),24): s+=' Data.a '+','.join(map(str,data[j:j+24]))+'\n'
    s+='EndDataSection\n'
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes()
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
