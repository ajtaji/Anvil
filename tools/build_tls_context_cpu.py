"""Compile TLS connection state isolation with real AES-GCM records."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    cases=['A0','B0','A1','B1']
    names=['Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/tls13_record.pbi','Anvil/Crypto/tls13_hs.pbi','Anvil/Crypto/x509.pbi','Anvil/Crypto/tls13_context.pbi']
    hs=(root/names[3]).read_text(encoding='utf8');x=(root/names[4]).read_text(encoding='utf8')
    declarations=[]
    for text,ee in [(hs,False),(x,True)]:
        for line in text.splitlines():
            if line.startswith('Global ') and (not ee or 'X509Ee' in line or ' xEePkey.' in line):declarations.append(line)
    s='\n'.join('XIncludeFile "'+n+'"' for n in names[:3])+'\n#TLS13_MAX_OFFERED=8\n#TLS13_MAX_CERTS=6\n#X_EEPKEY_SIZE=520\n'+'\n'.join(declarations)+'\n'
    copy=re.search(r'^Procedure TlsCopy\(.*?^EndProcedure',hs,re.M|re.S);assert copy
    s+=copy.group(0)+'\nXIncludeFile "Anvil/Crypto/tls13_context.pbi"\n'+r'''
Global Dim ctxA.a[#TLS13_CONTEXT_SIZE]
Global Dim ctxB.a[#TLS13_CONTEXT_SIZE]
Global Dim key.a[16]
Global Dim iv.a[12]
Global Dim plain.a[8]
Global Dim output.a[64]
Procedure Start(seed.i)
 Define i.i
 For i=0 To 15 : key[i]=seed+i : Next
 For i=0 To 11 : iv[i]=seed+32+i : Next
 Tls13RecReset() : Tls13RecSetWriteKey(@key[0],@iv[0])
 For i=0 To 519 : xEePkey[i]=(seed+i) & 255 : Next
 TlsAlpnOfferLen=seed : TlsAlpnSelectedLen=seed+2
 For i=0 To 255 : TlsAlpnOffer[i]=(seed+i)&255 : TlsAlpnSelected[i]=(seed+2*i)&255 : Next
 Tls13State=seed : TlsHsLen=seed+123 : TlsTrSnap[0]=seed+1
EndProcedure
Procedure Emit(index.i)
 Define n.i,i.i,p.i
 p=$E1C00100+index*128
 n=Tls13RecProtect(23,@plain[0],8,0,@output[0],64)
 PokeI(p,n) : PokeI(p+8,TlsWSeqLo) : PokeI(p+16,Tls13State)
 PokeI(p+24,TlsHsLen) : PokeI(p+32,TlsTrSnap[0])
 PokeI(p+40,xEePkey[0]) : PokeI(p+48,xEePkey[519])
 For i=0 To n-1 : PokeA(p+64+i,output[i]) : Next
 p=$E1C00800+index*64
 PokeI(p,TlsAlpnOfferLen) : PokeI(p+8,TlsAlpnSelectedLen)
 PokeI(p+16,TlsAlpnOffer[0]) : PokeI(p+24,TlsAlpnOffer[255])
 PokeI(p+32,TlsAlpnSelected[0]) : PokeI(p+40,TlsAlpnSelected[255])
EndProcedure
Procedure.i Main(services.i)
 Define i.i,n.i,ok.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$54435831)
 For i=0 To 7 : plain[i]=65+i : Next
 Start(1) : Emit(0) : n=Tls13ContextSave(@ctxA[0],#TLS13_CONTEXT_SIZE)
 Start(80) : Emit(1) : n=Tls13ContextSave(@ctxB[0],#TLS13_CONTEXT_SIZE)
 n=Tls13ContextRestore(@ctxA[0],#TLS13_CONTEXT_SIZE) : PokeI($E1C00008,TlsCipherInstalled) : Emit(2)
 n=Tls13ContextRestore(@ctxB[0],#TLS13_CONTEXT_SIZE) : PokeI($E1C00010,TlsCipherInstalled) : Emit(3)
 PokeI($E1C00018,Tls13ContextSave(@ctxA[0],#TLS13_CONTEXT_SIZE-1))
 PokeI($E1C00020,Tls13ContextRestore(0,#TLS13_CONTEXT_SIZE))
 n=Tls13ContextWipe(@ctxA[0],#TLS13_CONTEXT_SIZE) : ok=1
 For i=0 To #TLS13_CONTEXT_SIZE-1 : If ctxA[i]<>0 : ok=0 : EndIf : Next
 PokeI($E1C00028,ok) : PokeI($E1C00030,n)
 ProcedureReturn 0
EndProcedure
'''
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
