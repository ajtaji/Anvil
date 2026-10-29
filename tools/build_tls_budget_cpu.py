"""Build bounded TLS transport scheduling checks for a physical Pi 4.
Crypto dispatch and TCP sends are controlled doubles; framing and client loops
are extracted unchanged from the production owners. This does not test crypto.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler

def procedure(source,name):
    m=re.search(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',source,re.M|re.S)
    assert m,name
    return m.group(0)+'\n'

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Crypto/tls13_hs.pbi','Anvil/Core/tls_client.pbi']
    hs=(root/names[0]).read_text(encoding='utf8');client=(root/names[1]).read_text(encoding='utf8')
    cases=list(range(14))
    s=r'''
#TLS_REC_HDR=5
#TLS_MAX_CIPHERTEXT=16640
#TLS13_REFUSE_NO_RECV_BUFFER=1
#TLS13_REFUSE_RECORD_TOO_LONG=2
#TLS_ALERT_INTERNAL_ERROR=80
#TLS_ALERT_RECORD_OVERFLOW=22
#SVC_EIO=-105
#TLSC_RING=65536
#TLSC_APP_CHUNK=16384
Global TlsRecvAddr.i,TlsRecvSize.i,TlsRecvLen.i,Tls13AppLen.i,Tls13AppAddr.i
Global calls.i,failRecord.i,appRecord.i,failure.i,sendCalls.i,sendMode.i
Global tlsc_inOff.i,tlsc_inLen.i,tlsc_txOff.i,tlsc_txLen.i,tlsc_tcp.i,tlsc_ringHead.i,tlsc_ringTail.i
Global Dim storage.a[17000]
Global Dim tlsc_in.a[64]
Global Dim tlsc_tx.a[64]
Global Dim tlsc_ring.a[65536]
Procedure.i TlsFail(code.i,alert.i)
 failure=code : ProcedureReturn 0
EndProcedure
Procedure tlsc_Refuse(code.i,why.i)
 failure=code
EndProcedure
Procedure TlsCopy(dst.i,src.i,n.i)
 Define i.i
 For i=0 To n-1 : PokeA(dst+i,PeekA(src+i)) : Next
EndProcedure
Procedure.i TlsRd16(p.i)
 ProcedureReturn (PeekA(p)<<8)|PeekA(p+1)
EndProcedure
Procedure.i Tls13FeedRecord(p.i,n.i)
 calls=calls+1
 If failRecord : ProcedureReturn 0 : EndIf
 If appRecord : Tls13AppAddr=p+5 : Tls13AppLen=n-5 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i PayNetTcpSend(h.i,p.i,n.i)
 sendCalls=sendCalls+1
 If sendMode=-1 : ProcedureReturn -103 : EndIf
 If sendMode=1 : ProcedureReturn n+1 : EndIf
 If sendMode=2 : ProcedureReturn 0 : EndIf
 If n>3 : ProcedureReturn 3 : EndIf
 ProcedureReturn n
EndProcedure
'''
    for n in ['Tls13FeedBytesLimited','Tls13FeedBytes']:s+=procedure(hs,n)
    for n in ['tlsc_RingUsed','tlsc_RingFree','tlsc_Flush','tlsc_Feed']:s+=procedure(client,n)
    s+=r'''
Procedure Reset()
 Define i.i
 TlsRecvAddr=@storage[0] : TlsRecvSize=17000 : TlsRecvLen=0
 Tls13AppLen=0 : calls=0 : failRecord=0 : appRecord=0 : failure=0
 sendCalls=0 : sendMode=0 : tlsc_txOff=0 : tlsc_txLen=10 : tlsc_tcp=1
 tlsc_inOff=0 : tlsc_inLen=21 : tlsc_ringHead=0 : tlsc_ringTail=0
 For i=0 To 2
  tlsc_in[i*7]=22 : tlsc_in[i*7+1]=3 : tlsc_in[i*7+2]=3
  tlsc_in[i*7+3]=0 : tlsc_in[i*7+4]=2
  tlsc_in[i*7+5]=65+i : tlsc_in[i*7+6]=97+i
 Next
EndProcedure
Procedure Save(index.i,rc.i,extra.i)
 Define p.i
 p=$E1C00100+index*64
 PokeI(p,rc) : PokeI(p+8,calls) : PokeI(p+16,TlsRecvLen) : PokeI(p+24,failure)
 PokeI(p+32,tlsc_inOff) : PokeI(p+40,tlsc_txOff) : PokeI(p+48,sendCalls) : PokeI(p+56,extra)
EndProcedure
Procedure.i Main(services.i)
 Define rc.i,i.i,k.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$544C4231) : PokeI($E1C00008,14)
 Reset() : rc=Tls13FeedBytesLimited(@tlsc_in[0],21,1) : Save(0,rc,0)
 Reset() : rc=Tls13FeedBytesLimited(@tlsc_in[0],21,2) : Save(1,rc,0)
 Reset() : rc=Tls13FeedBytes(@tlsc_in[0],21) : Save(2,rc,0)
 Reset() : rc=Tls13FeedBytesLimited(@tlsc_in[0],21,0) : Save(3,rc,0)
 Reset() : rc=Tls13FeedBytesLimited(@tlsc_in[0],3,1) : Save(4,rc,0)
 rc=Tls13FeedBytesLimited(@tlsc_in[3],18,1) : Save(5,rc,0)
 Reset() : failRecord=1 : rc=Tls13FeedBytesLimited(@tlsc_in[0],21,1) : Save(6,rc,0)
 Reset() : tlsc_in[3]=255 : rc=Tls13FeedBytesLimited(@tlsc_in[0],21,1) : Save(7,rc,0)
 Reset() : appRecord=1 : rc=tlsc_Feed() : Save(8,rc,tlsc_RingUsed())
 rc=tlsc_Feed() : rc=tlsc_Feed() : Save(9,rc,tlsc_RingUsed())
 Reset() : rc=tlsc_Flush() : Save(10,rc,tlsc_txLen)
 Reset() : sendMode=2 : rc=tlsc_Flush() : Save(11,rc,tlsc_txLen)
 Reset() : sendMode=1 : rc=tlsc_Flush() : Save(12,rc,tlsc_txLen)
 Reset() : For k=0 To 3 : rc=tlsc_Flush() : Next : Save(13,rc,tlsc_txLen)
 ProcedureReturn 0
EndProcedure
'''
    source=out/'proof.pi4';source.write_text(s,encoding='utf8')
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
