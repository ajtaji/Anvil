"""Physical QUIC/TLS boundaries using full shared TLS, real X25519/HKDF/Finished.
Deterministic fixture keys/states; no certificate-chain or live peer claim.
"""
from pathlib import Path
import argparse,hashlib,hmac,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def expand(secret,label,context=b'',n=32):
 label=b'tls13 '+label;info=n.to_bytes(2,'big')+bytes([len(label)])+label+bytes([len(context)])+context
 return hmac.digest(secret,info+b'\1','sha256')[:n]
def finished(secret):return b'\x14\0\0\x20'+hmac.digest(expand(secret,b'finished'),hashlib.sha256(b'quic fixture').digest(),'sha256')
def cases():
 def hs(t,b):return bytes([t])+len(b).to_bytes(3,'big')+b
 sh=hs(2,b'\x03\x03'+bytes(range(32))+b'\0\x13\x01\0'+b'\0\x2e'+b'\0\x2b\0\x02\x03\x04'+b'\0\x33\0\x24\0\x1d\0\x20'+b'\x09'+b'\0'*31)
 tp=b'\0\x08original\x0f\x07initial';ext=b'\0\x10\0\x05\0\x03\x02h3'+b'\0\x39'+len(tp).to_bytes(2,'big')+tp
 ee=hs(8,len(ext).to_bytes(2,'big')+ext)
 sf=finished(bytes(range(64,96)));cf=finished(bytes(range(32)))
 rows=[]
 def add(name,mode,data=b'',error=0,state=4,**kw):rows.append(dict(name=name,mode=mode,input=data.hex(),error=error,state=state,**kw))
 add('initial-to-handshake',0,sh+ee,consumed=len(sh+ee))
 add('fragmented-one-byte',1,sh+ee,consumed=len(sh+ee))
 add('initial-cannot-carry-ee',2,sh+ee,59,10,consumed=len(sh))
 add('wrong-first-level',3,sh,59,10,consumed=0)
 add('partial-header-level-change',4,sh,59,10,consumed=2)
 add('application-ticket-256-bound',5,hs(4,b'x'*600),state=8,consumed=604)
 add('quic-keyupdate-refused',6,hs(24,b'\0'),59,10,consumed=4)
 th=hashlib.sha256(b'quic fixture'+sf).digest()
 secrets=expand(bytes(range(96,128)),b'c ap traffic',th)+expand(bytes(range(96,128)),b's ap traffic',th)
 add('server-finished',7,sf,state=7,consumed=36,secrets=secrets.hex())
 bad=sf[:-1]+bytes([sf[-1]^1]);add('bad-server-finished',7,bad,81,10,consumed=4)
 add('raw-client-finished',8,state=8,output=cf.hex())
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 header=b'\x17\x03\x03\0\x35';wire=header+AESGCM(b'\0'*16).encrypt(b'\0'*12,cf+b'\x16',header)
 add('legacy-client-finished',9,state=8,output=wire.hex())
 add('short-client-finished',10,error=4,state=10,output='')
 add('record-input-refused',11,error=59,state=10)
 add('record-stream-refused',12,error=59,state=10)
 add('raw-feed-legacy-refused',13,b'\0',57,10,consumed=0)
 return rows

def build(compiler,out,transform=None):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 hs=(root/'Anvil/Crypto/tls13_hs.pbi').read_text()
 names=re.findall(r';     XIncludeFile "([^"]+)"',hs)+['RaspberryPi4/Lib/mmu.pi4']
 s='#X509_SIG_LINKED=1\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global Dim config.a[48]
Global Dim localParams.a[2]
Global Dim peer.a[64]
Global Dim incoming.a[2048]
Global Dim handshakes.a[2048]
Global Dim output.a[1024]
Global Dim zero.a[16]
Global table.i,*pet
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Yield()
 pet() : ProcedureReturn 1
EndProcedure
Procedure Prepare()
 Define i.i,n.i
 Tls13State=#TLS13_ST_START : Tls13Err=0 : Tls13Alert=0 : TlsKdfFault=0 : TlsQuicConfig=0
 Tls13TicketsDiscarded=0 : TlsHsAddr=@handshakes[0] : TlsHsSize=2048 : TlsHsLen=0
 TlsNameLen=0 : TlsGroup=#TLS_GROUP_X25519 : TlsSessionIdLen=32
 Tls13RecReset() : Tls13TranscriptReset()
 For i=0 To 31 : secTlsPriv[i]=i+1 : Next
 n=Tls13DeriveKeySharePublic()
 localParams[0]=15 : localParams[1]=0
 n=Tls13SetAlpn(?quic_alpn,3)
 n=Tls13SetQuicParameters(@config[0],@localParams[0],2,@peer[0],64)
 Sha256Of("",0,@TlsEmptyHash[0]) : TlsScheduleEarly()
 n=Tls13BuildClientHello(@output[0],1024)
EndProcedure
Procedure Run(index.i,mode.i,bytes.i)
 Define i.i,p.i,n.i,pos.i,level.i,offered.i,maxTaken.i,rc.i
 p=$E1C00100+index*2048
 Prepare()
 For i=0 To bytes-1 : Read.a incoming[i] : Next
 For i=0 To 1023 : output[i]=$A5 : Next
 If mode=5 Or mode=6 : Tls13State=#TLS13_ST_CONNECTED : EndIf
 If mode=7 Or mode=8 Or mode=9 Or mode=10
  Tls13TranscriptReset() : rc=Tls13TranscriptAppend("quic fixture",12)
  Sha256Of("quic fixture",12,@TlsThSf[0])
  For i=0 To 31
   secTlsCHs[i]=i : secTlsCAp[i]=32+i : secTlsSHs[i]=64+i : secTlsMaster[i]=96+i
  Next
  Tls13State=#TLS13_ST_WAIT_FINISHED
 EndIf
 If mode=13 : TlsQuicConfig=0 : EndIf
 If mode<8 Or mode=13
  While pos<bytes
   pet() : level=2
   If Tls13State=#TLS13_ST_WAIT_SH : level=0 : EndIf
   If Tls13State=#TLS13_ST_CONNECTED : level=3 : EndIf
   If mode=2 : level=0 : EndIf
   If mode=3 : level=2 : EndIf
   If mode=4 And pos>0 : level=2 : EndIf
   offered=bytes-pos : If mode=1 : offered=1 : EndIf
   If mode=4 And pos=0 : offered=2 : EndIf
   n=Tls13FeedQuic(level,@incoming[pos],offered)
   If n>maxTaken : maxTaken=n : EndIf
   If n<=0 : Break : EndIf
   pos=pos+n
  Wend
 ElseIf mode=8 Or mode=9 Or mode=10
  Tls13State=#TLS13_ST_SEND_FINISHED
  If mode=9
   TlsQuicConfig=0 : Tls13RecReset() : Tls13RecSetWriteKey(@zero[0],@zero[0])
  EndIf
  offered=1024 : If mode=10 : offered=35 : EndIf
  n=Tls13BuildClientFinished(@output[0],offered)
 ElseIf mode=11
  n=Tls13FeedRecord(0,0)
 ElseIf mode=12
  n=Tls13FeedBytesLimited(0,0,1)
 EndIf
 PokeI(p,Tls13Err) : PokeI(p+8,Tls13State) : PokeI(p+16,pos) : PokeI(p+24,maxTaken) : PokeI(p+32,n)
 PokeI(p+40,Tls13TicketsDiscarded) : PokeI(p+48,TlsHsLen)
 TlsCopy(p+128,@output[0],128) : TlsCopy(p+256,@secTlsCAp[0],32) : TlsCopy(p+288,@secTlsSAp[0],32)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable() : *pet=PeekI(table+16+6*8)
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$51544331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 Tls13PauseHook=@Yield : Tls13SetupPauseHook=@Yield
 TlsInitTables() : X25519Init()
'''
 rows=cases()
 if transform is not None:s,rows,names=transform(s,rows,names)
 s+=f' PokeI($E1C00008,{len(rows)})\n'
 for i,c in enumerate(rows):s+=f' Restore QuicTlsCase{i}\n Run({i},{c["mode"]},{len(bytes.fromhex(c["input"]))})\n'
 s+=' MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\nquic_alpn:\n Data.a 2,104,51\n'
 for i,c in enumerate(rows):s+=f'QuicTlsCase{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['input']) or b'\0'))+'\n'
 s+='EndDataSection\n';src=out/'proof.pi4';src.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(src),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},checked_ranges=ranges,cases=rows),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args();build(a.compiler,a.out.resolve())
