"""Compile the published ECDSA validation corpus for timed physical Pi4 execution."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,edge_vectors=False,wide_curves=False):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Crypto/bignum.pbi','Anvil/Crypto/ec256.pbi','Anvil/Crypto/ecp.pbi','Anvil/Crypto/ecdsa.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Core/cryptotest_vectors.pbi']
    corpus=(root/names[-1]).read_text(encoding='utf8')
    meta=[list(map(int,x.split(','))) for x in re.findall(r'^\s*Data\.l ([^\r\n]+)',corpus,re.M)]
    blob=bytes(int(x.strip()) for line in re.findall(r'^\s*Data\.b ([^\r\n]+)',corpus,re.M) for x in line.split(','))
    cases=[x for x in meta if x[0]==15]
    if wide_curves:
        from cryptography.hazmat.primitives.asymmetric import ec,utils
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.exceptions import InvalidSignature
        cases=[];blob=b''
        fixture='tools/fixtures/ecp_vectors.json'
        for record in json.loads((root/fixture).read_text(encoding='utf8'))['records']:
            q=bytes.fromhex(record['q']);digest=bytes.fromhex(record['hash'])
            for field,kind in [('raw',4),('der',2)]:
                if not record.get(field) or (kind==2 and 'rule' in record):continue
                sig=bytes.fromhex(record[field]);want=record['expect']
                param=kind | (want<<8) | ((1-want)<<16) | (record['curve']<<24)
                cases.append([15,len(cases),len(q),len(digest),len(sig),0,0,0,param,len(blob)])
                blob+=q+digest+sig
        tables=(root/'Anvil/Crypto/ecp.pbi').read_text(encoding='utf8')
        for curve,tag,width,alg,number in [(ec.SECP384R1(),'384',48,hashes.SHA384(),24),(ec.SECP521R1(),'521',66,hashes.SHA512(),25)]:
            section=tables.split('  EcpDataP'+tag+':',1)[1].split('  EcpDataP',1)[0]
            raw=bytes(int(x,16) for line in re.findall(r'^\s*Data\.a ([^\r\n]+)',section,re.M) for x in re.findall(r'\$([0-9A-Fa-f]+)',line))
            order=int.from_bytes(raw[width:width*2],'big')
            for private,nonce,h in [(1,1,0),(1,2,1),(2,2,(1<<(alg.digest_size*8))-1),(3,3,123456789),(order-1,1,1)]:
                key=ec.derive_private_key(private,curve)
                q=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
                r=ec.derive_private_key(nonce,curve).public_key().public_numbers().x%order
                scalar=pow(nonce,-1,order)*(h+r*private)%order
                digest=h.to_bytes(alg.digest_size,'big')
                for rr,ss in [(r,scalar),(r,(scalar+1)%order),(1,1)]:
                    sig=rr.to_bytes(width,'big')+ss.to_bytes(width,'big');want=1
                    try:key.public_key().verify(utils.encode_dss_signature(rr,ss),digest,ec.ECDSA(utils.Prehashed(alg)))
                    except InvalidSignature:want=0
                    param=4 | (want<<8) | ((1-want)<<16) | (number<<24)
                    cases.append([15,len(cases),len(q),len(digest),len(sig),0,0,0,param,len(blob)])
                    blob+=q+digest+sig
    if edge_vectors:
        from cryptography.hazmat.primitives.asymmetric import ec,utils
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.exceptions import InvalidSignature
        order=0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
        for private in [1,2,3,order-1]:
            key=ec.derive_private_key(private,ec.SECP256R1())
            q=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
            for nonce in [1,2,order-1]:
                r=ec.derive_private_key(nonce,ec.SECP256R1()).public_key().public_numbers().x%order
                for h in [0,1,order-1,(-r*private)%order]:
                    scalar=pow(nonce,-1,order)*(h+r*private)%order
                    digest=h.to_bytes(32,'big');sig=r.to_bytes(32,'big')+scalar.to_bytes(32,'big')
                    want=1
                    try:key.public_key().verify(utils.encode_dss_signature(r,scalar),digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
                    except InvalidSignature:want=0
                    param=1 | (want<<8) | ((1-want)<<16)
                    cases.append([15,len(cases),65,32,64,0,0,0,param,len(blob)])
                    blob+=q+digest+sig
            # Force r*Q+h*G to infinity with s=1: valid encodings, bad signature.
            digest=((order-private)%order).to_bytes(32,'big')
            sig=(1).to_bytes(32,'big')*2
            try:key.public_key().verify(utils.encode_dss_signature(1,1),digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
            except InvalidSignature:pass
            else:raise AssertionError('infinity fixture unexpectedly verified')
            cases.append([15,len(cases),65,32,64,0,0,0,0x10001,len(blob)])
            blob+=q+digest+sig
    s='\n'.join('XIncludeFile "'+n+'"' for n in names[:-1])+r'''
Global wtable.i
Global *pet,*timer
Global Dim key.a[256]
Global Dim digest.a[128]
Global Dim signature.a[512]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure Run(index.i,q.i,qn.i,h.i,hn.i,s.i,sn.i,param.i)
 Define i.i,rc.i,t.i,elapsed.i,p.i,kind.i,curve.i,err.i
 For i=0 To qn-1 : key[i]=PeekA(q+i) : Next
 For i=0 To hn-1 : digest[i]=PeekA(h+i) : Next
 For i=0 To sn-1 : signature[i]=PeekA(s+i) : Next
 pet() : kind=param & 255 : curve=(param>>24) & 255
 t=timer()
 If kind=1
  rc=EcdsaVrfyRaw(@digest[0],hn,@key[0],qn,@signature[0],sn)
 ElseIf kind=2
  rc=EcdsaVrfy(curve,@digest[0],hn,@key[0],qn,@signature[0],sn)
 ElseIf kind=4
  rc=EcpVrfyRaw(curve,@digest[0],hn,@key[0],qn,@signature[0],sn)
 Else
  rc=EcdsaVrfyAsn1(@digest[0],hn,@key[0],qn,@signature[0],sn)
 EndIf
 err=EcdsaLastErr : If kind=4 : err=EcpLastErr : EndIf
 elapsed=timer()-t : p=$E1C00100+index*32
 PokeI(p,index) : PokeI(p+8,rc) : PokeI(p+16,err) : PokeI(p+24,elapsed)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$45434431)
 pet=PeekI(wtable+16+6*8) : timer=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
    data=[]
    for row in cases:
        _,idx,qn,hn,sn,_,_,_,param,off=row
        s+=f' Run({idx},?V{idx},{qn},?V{idx}+{qn},{hn},?V{idx}+{qn+hn},{sn},{param})\n'
        data.append((idx,blob[off:off+qn+hn+sn]))
    s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed() : ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for idx,raw in data:
        s+=f'V{idx}:\n'
        for j in range(0,len(raw),24):s+=' Data.b '+','.join(map(str,raw[j:j+24]))+'\n'
    s+='EndDataSection\n'
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
    if wide_curves:hashes[fixture]=hashlib.sha256((root/fixture).read_bytes()).hexdigest()
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes=hashes,cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--edge-vectors',action='store_true')
    ap.add_argument('--wide-curves',action='store_true')
    args=ap.parse_args();build(args.compiler,args.out.resolve(),args.edge_vectors,args.wide_curves)
