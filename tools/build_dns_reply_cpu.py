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
    def add(label, raw, rc, ttl=0, expected='example.test'):
        cases.append(dict(name=label,packet=raw.hex(),expected=expected,rc=rc,ttl=ttl,ip=0x01020304 if rc>0 else 0))
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
Procedure Run(index.i,bytes.i,expected.i)
 Define i.i,p.i,rc.i
 For i=0 To bytes-1 : Read.a wire[i] : Next
 p=$E1C00100+index*64
 rc=DnsParseReplyFor(@wire[0],bytes,$1234,expected)
 PokeI(p,rc) : PokeI(p+8,DnsError()) : PokeI(p+16,DnsResultCount())
 PokeI(p+24,DnsResultIp(0)) : PokeI(p+32,DnsResultTtl(0))
 PokeI(p+40,DnsResultTtl(-1)) : PokeI(p+48,DnsResultTtl(DnsResultCount()))
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
        s+=f' Restore Packet{i}\n Run({i},{len(bytes.fromhex(c["packet"]))},"{c["expected"]}")\n'
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
