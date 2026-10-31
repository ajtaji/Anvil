"""Compile the shared ALPN wire codec and state guards for physical A64 tests.
Transcript append is a fixture stub: this does not claim certificate verification.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def cases():
    offer=b'\x02h2\x08http/1.1'
    def ext(body):return b'\x00\x10'+len(body).to_bytes(2,'big')+body
    def sel(name):return (len(name)+1).to_bytes(2,'big')+bytes([len(name)])+name
    def ee(exts):
        body=len(exts).to_bytes(2,'big')+exts
        return b'\x08'+len(body).to_bytes(3,'big')+body
    rows=[]
    def add(name,o,e,error=0,selected=b'',capacity=1024,null=False):
        rows.append(dict(name=name,offer=o.hex(),ee=ee(e).hex(),error=error,selected=selected.hex(),capacity=capacity,null=null))
    add('h2',offer,ext(sel(b'h2')),selected=b'h2')
    add('http1',offer,ext(sel(b'http/1.1')),selected=b'http/1.1')
    add('no-negotiation',offer,b'')
    add('legacy-no-offer',b'',b'')
    add('unoffered-extension',b'',ext(sel(b'h2')),51)
    add('unoffered-name',offer,ext(sel(b'h3')),55)
    add('duplicate',offer,ext(sel(b'h2'))*2,56)
    add('two-selected',offer,ext(b'\x00\x06\x02h2\x02h2'),54)
    add('empty-selected',offer,ext(b'\x00\x01\x00'),54)
    add('length-mismatch',offer,ext(b'\x00\x04\x02h2'),54)
    for n in range(4):add('short-selection-'+str(n),offer,ext(b'\x00'*n),54)
    add('empty-client-name',b'\x00',b'',54)
    add('truncated-client-name',b'\x03h2',b'',54)
    add('trailing-client-name',offer+b'\x01',b'',54)
    add('too-large-client-list',b'\x01a'*129,b'',54)
    add('null-client-list',offer,b'',54,null=True)
    add('short-client-buffer',offer,b'',4,capacity=256)
    binary=bytes(range(255));add('maximum-opaque-name',b'\xff'+binary,ext(sel(binary)),selected=binary)
    params=b'\x00\x08original\x0f\x07initial'
    def qp(data):return b'\x00\x39'+len(data).to_bytes(2,'big')+data
    for name,extensions,error in [('quic',ext(sel(b'h3'))+qp(params),0),('quic-missing',ext(sel(b'h3')),58),('quic-duplicate',ext(sel(b'h3'))+qp(params)*2,58),('quic-no-alpn',qp(params),58)]:
        add(name,b'\x02h3',extensions,error,selected=b'h3' if error==0 else b'');rows[-1].update(quic=True,params=params.hex(),peer_capacity=64,parameter_rc=1)
    add('quic-short-peer',b'\x02h3',ext(sel(b'h3'))+qp(params),57);rows[-1].update(quic=True,params=params.hex(),peer_capacity=2,parameter_rc=1)
    add('quic-no-offer',b'',qp(params),57);rows[-1].update(quic=True,params=params.hex(),peer_capacity=64,parameter_rc=1)
    add('legacy-quic-unsolicited',offer,qp(params),51)
    add('quic-invalid-parameters',b'\x02h3',ext(sel(b'h3'))+qp(b'\x0f\x00'),selected=b'h3');rows[-1].update(quic=True,params='0f00',peer_capacity=64,parameter_rc=-3387)
    return rows

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Crypto/tls13_hs.pbi','Anvil/Crypto/tls13_record.pbi'];hs,rec=[(root/n).read_text(encoding='utf8') for n in names]
    constants={}
    for t in [rec,hs]:
        for line in t.splitlines():
            m=re.match(r'^(#\w+)\s*=',line)
            if m and '#' not in line.split('=',1)[1].split(';',1)[0]:constants[m[1]]=line
    s='\n'.join(constants.values())+'\n'+'\n'.join(x for x in hs.splitlines() if x.startswith('Global '))+'\n'
    procs=['TlsFail','TlsRd8','TlsRd16','TlsRd24','TlsWr8','TlsWr16','TlsWr24','TlsCopy','TlsNoteOffered','TlsWasOffered','Tls13SetAlpn','Tls13Alpn','TlsAlpnReadSelection','Tls13SetQuicParameters','Tls13BuildClientHello','TlsHandleEncryptedExtensions']
    def extract(t,n):
        m=re.search(r'^Procedure(?:\.\w+)? '+n+r'\(.*?^EndProcedure',t,re.M|re.S);assert m,n;return m[0]+'\n'
    s+=extract(rec,'Tls13RecBuildPlainHeader')+'Procedure.i Tls13TranscriptAppend(p.i,n.i)\n ProcedureReturn 1\nEndProcedure\n'
    for n in procs:s+=extract(hs,n)
    names+=['Anvil/Network/quic_parameters.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi']
    s+='XIncludeFile "Anvil/Network/quic_parameters.pbi"\nGlobal job.QuicParameters\nGlobal Dim entries.a[2048]\nGlobal Dim config.a[48]\nGlobal Dim localParams.a[2]\nGlobal Dim peer.a[64]\n'
    s+='Global Dim input.a[512]\nGlobal Dim message.a[1024]\nGlobal Dim output.a[1024]\nGlobal Dim selected.a[256]\nProcedure.i Main(services.i)\n Define i.i,p.i,setrc.i,hello.i,eerc.i,early.i,late.i,short.i,prc.i,idsrc.i\n For i=0 To 65535 : PokeA($E1C00000+i,0) : Next\n PokeI($E1C00000,$414C5031)\n'
    rows=cases()
    for k,c in enumerate(rows):
        o=bytes.fromhex(c['offer']);e=bytes.fromhex(c['ee'])
        s+=f'p=$E1C00100+{k}*1024\nTls13State=#TLS13_ST_START : Tls13Err=0 : Tls13Alert=0 : TlsOfferedCount=0 : TlsAlpnOfferLen=0 : TlsAlpnSelectedLen=0\nTlsKeyShareLen=32 : TlsNameLen=0 : TlsSessionIdLen=0 : TlsGroup=#TLS_GROUP_X25519\n'
        s+='For i=0 To 1023 : output[i]=$A5 : Next\nFor i=0 To 255 : selected[i]=$A5 : Next\n'
        s+='TlsQuicConfig=0 : prc=-999 : idsrc=-999\nFor i=0 To 47 : config[i]=0 : Next\nFor i=0 To 63 : peer[i]=$A5 : Next\nlocalParams[0]=15 : localParams[1]=0\n'
        for i,v in enumerate(o):s+=f'input[{i}]={v}\n'
        for i,v in enumerate(e):s+=f'message[{i}]={v}\n'
        addr='0' if c['null'] else '@input[0]'
        s+=f'setrc=Tls13SetAlpn({addr},{len(o)}) : hello=0 : eerc=0 : early=-1 : late=-1 : short=-1\n'
        if c.get('quic'):s+=f'If setrc<>0 : setrc=Tls13SetQuicParameters(@config[0],@localParams[0],2,@peer[0],{c["peer_capacity"]}) : EndIf\n'
        s+=f'If setrc<>0\n hello=Tls13BuildClientHello(@output[0],{c["capacity"]})\n If hello>0\n eerc=TlsHandleEncryptedExtensions(@message[0],{len(e)})\n early=Tls13Alpn(@selected[0],256)\n If eerc<>0\n Tls13State=#TLS13_ST_CONNECTED\n short=Tls13Alpn(@selected[0],TlsAlpnSelectedLen-1)\n late=Tls13Alpn(@selected[0],256)\n EndIf\n EndIf\nEndIf\n'
        if c.get('quic'):s+='If eerc<>0\n For i=0 To SizeOf(QuicParameters)-1 : PokeA(@job+i,0) : Next\n prc=QuicParametersBegin(@job,@peer[0],PeekI(@config[32]),1,@entries[0],64)\n While prc=0 : prc=QuicParametersStep(@job) : Wend\n idsrc=QuicParametersCheckIds(@job,"initial",7,"original",8,0,0,0)\nEndIf\n'
        s+='PokeI(p+56,PeekI(@config[32])) : PokeI(p+64,PeekI(@config[40])) : PokeI(p+72,prc) : PokeI(p+80,idsrc)\nTlsCopy(p+960,@peer[0],64)\n'
        s+='PokeI(p,setrc) : PokeI(p+8,hello) : PokeI(p+16,eerc) : PokeI(p+24,Tls13Err) : PokeI(p+32,early) : PokeI(p+40,late) : PokeI(p+48,short)\nTlsCopy(p+128,@output[0],512) : TlsCopy(p+700,@selected[0],256)\n'
    s+='ProcedureReturn 0\nEndProcedure\n'
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
