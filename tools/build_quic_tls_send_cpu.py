"""Physical TLS output admission/retention with independent handshake bytes."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi
from build_tls_quic_crypto_cpu import finished
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

def hello(params):
 def u(n):return n.to_bytes(2,'big')
 def ext(n,b):return u(n)+u(len(b))+b
 pub=X25519PrivateKey.from_private_bytes(bytes(range(1,33))).public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
 extensions=ext(57,params)+ext(16,b'\0\3\2h3')+ext(10,b'\0\4\0\x1d\0\x17')
 extensions+=ext(13,b'\0\x0e'+b''.join(u(n) for n in [0x403,0x503,0x603,0x804,0x401,0x501,0x601]))
 extensions+=ext(43,b'\2\3\4')+ext(51,u(36)+u(29)+u(32)+pub)
 body=b'\3\3'+bytes(32)+b'\0\0\2\x13\1\1\0'+u(len(extensions))+extensions
 return b'\1'+len(body).to_bytes(3,'big')+body

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=[]
 # This deterministic fixture supplies explicit key material and exercises no
 # hardware entropy path. Resolve the historical Pi 4 list to shared owners.
 for name in re.findall(r';     XIncludeFile "([^"]+)"',(root/'Anvil/Crypto/tls13_hs.pbi').read_text()):
  if name=='RaspberryPi4/Lib/entropy.pi4':continue
  if name=='RaspberryPi4/Lib/drbg.pi4':
   names.append('Anvil/Crypto/drbg.pbi');continue
  if name.startswith('RaspberryPi4/Lib/'):
   shared=re.findall(r'^XIncludeFile "(Anvil/[^\"]+)"',(root/name).read_text(),re.M)
   assert len(shared)==1,(name,shared)
   name=shared[0]
  names.append(name)
 names+=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/quic_tls_send.pbi']
 steps=[];cases=[]
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def fnv(b):
  h=2166136261
  for x in b:h=((h^x)*16777619)&0xffffffff
  return h
 def prepare(level=0,cap=32768):
  code('Prepare()\nFor i=0 To 19999 : output[i]=$A5 : Next\nFor i=0 To SizeOf(QuicTlsOutput)-1 : PokeA(@job+i,0) : Next')
  check('stream init',f'QuicCryptoTxInit(@tx,{level},@txData[0],{cap},@txStates[0],8192)',0)
 def begin(cap=20000,want=1):check('output begin',f'QuicTlsOutputBegin(@job,@tx,@output[0],{cap})',want)
 def drain(message,offset=0):
  code('total=0 : high=0\nFor i=0 To 199\n rc=QuicTlsOutputStep(@job)\n If rc<=0 : Break : EndIf\n total=total+rc : If rc>high : high=rc : EndIf\nNext')
  for n,e,v in [('terminal','rc',0),('job done','job\\phase',2),('bytes','total',len(message)),('bounded copy','high',min(256,len(message))),('tail','tx\\tail',offset+len(message)),('copied','job\\copied',len(message))]:check(n,e,v)
  check('exact TLS output','Hash(@output[0],20000)',fnv(message+b'\xa5'*(20000-len(message))))
  expected=b'\6'+vi(offset)+vi(len(message))+message
  if len(message)<=16384:
   check('retained frame',f'QuicCryptoTxFrame(@tx,{offset},{len(message)},@frame[0],20032)',len(expected))
   check('retained exact bytes',f'Hash(@frame[0],{len(expected)})',fnv(expected))
  else:
   # Independently check retention across both the Append limit and copy steps.
   check('retained large bytes',f'Hash(@txData[0],{len(message)})',fnv(message))
  code('Tls13TranscriptHash(@digest[0])');check('transcript', 'Hash(@digest[0],32)',fnv(hashlib.sha256(message).digest()))
 ch=hello(b'\x0f\0')
 prepare(cap=4096)
 check('read-only capacity','Tls13ClientHelloCapacity()',271);check('ready QUIC capacity','Tls13QuicOutputCapacity()',271)
 code('saved=Hash(@TlsTrSnap[0],104)')
 begin(270,-3485)
 for name,e,v in [('TLS unchanged','Tls13State',1),('session unchanged','TlsSessionIdLen',32),('error unchanged','Tls13Err',0),('job untouched','job\\phase',0),('queue empty','tx\\tail',0),('transcript unchanged','Bool(saved=Hash(@TlsTrSnap[0],104))',1)]:check(name,e,v)
 check('buffer unchanged','Hash(@output[0],20000)',fnv(b'\xa5'*20000))
 code('tx\\level=2');begin(want=-3492);code('tx\\level=0')
 check('output alias','QuicTlsOutputBegin(@job,@tx,@txData[0],4096)',-3481)
 code('TlsKeyShareLen=0');begin(want=0);check('no key share does not fault','Tls13Err',0);code('TlsKeyShareLen=32')
 check('fill queue','QuicCryptoTxAppend(@tx,@filler[0],4090)',4090);begin(want=-3483)
 check('full queue leaves TLS','Tls13State',1);check('full queue leaves transcript','Bool(saved=Hash(@TlsTrSnap[0],104))',1)
 code('rc=QuicCryptoTxSent(@tx,0,4090) : rc=QuicCryptoTxAck(@tx,0,4090) : rc=QuicCryptoTxReclaim(@tx,4096)')
 code('job\\phase=3');begin(want=-3492);code('job\\phase=0')
 code('probeActive=1 : Tls13PauseHook=@OutputYield')
 begin();code('probeActive=0 : Tls13PauseHook=@Yield')
 check('builder hook ran','Bool(probeSeen>0)',1);check('building cannot step','probeStep',-3492)
 check('build advances TLS once','Tls13State',2);check('admitted offset','job\\offset',4090);check('not copied yet','tx\\tail',4090)
 begin(want=-3492);drain(ch,4090);begin(want=0)
 # Maximum permitted opaque transport-parameter length exceeds one Append.
 prepare();code('For i=0 To 16383 : localParams[i]=0 : Next\nrc=Tls13SetQuicParameters(@config[0],@localParams[0],16384,@peer[0],64)')
 large=hello(bytes(16384));begin();drain(large)
 # Cancel after a real partial copy: TLS is already advanced and must close.
 prepare();code('For i=0 To 599 : localParams[i]=0 : Next\nrc=Tls13SetQuicParameters(@config[0],@localParams[0],600,@peer[0],64)')
 begin();check('one bounded slice','QuicTlsOutputStep(@job)',256);check('cancel','QuicTlsOutputCancel(@job)',-3493)
 check('stream poisoned','tx\\phase',3);check('partial data retained','tx\\tail',256);check('cancel sticky','QuicTlsOutputStep(@job)',-3493)
 check('poison refuses append','QuicCryptoTxAppend(@tx,@filler[0],1)',-3482)
 # An interleaved append cannot silently shift this TLS message's offsets.
 prepare();begin();code('rc=QuicCryptoTxAppend(@tx,@filler[0],1)')
 check('interleaved append detected','QuicTlsOutputStep(@job)',-3492);check('interleave poisoned','tx\\phase',3)
 # Real Finished HMAC with known transcript; queue admission must precede it.
 prepare(2);code('Tls13TranscriptReset() : rc=Tls13TranscriptAppend("quic fixture",12)\nSha256Of("quic fixture",12,@TlsThSf[0])\nFor i=0 To 31 : secTlsCHs[i]=i : secTlsCAp[i]=32+i : Next\nTls13State=#TLS13_ST_SEND_FINISHED')
 check('Finished capacity','Tls13QuicOutputCapacity()',36);begin(35,-3485);check('Finished not advanced','Tls13State',7)
 begin();cf=finished(bytes(range(32)))
 code('rc=QuicTlsOutputStep(@job)');check('Finished retained','rc',36);check('Finished connected','Tls13State',8)
 check('Finished exact bytes','Hash(@txData[0],36)',fnv(cf));check('Finished output guard','Hash(@output[0],20000)',fnv(cf+b'\xa5'*19964))
 code('Tls13TranscriptHash(@digest[0])');check('Finished transcript','Hash(@digest[0],32)',fnv(hashlib.sha256(b'quic fixture'+cf).digest()))
 # Builder failure is fatal after admission, not a retryable queue refusal.
 prepare();code('TlsAlpnOfferLen=0');begin(want=-3491);check('builder failure poisons','tx\\phase',3);check('builder failure sticky','QuicTlsOutputStep(@job)',-3491)
 # Ordinary TLS mode remains outside this QUIC adapter.
 prepare();code('TlsQuicConfig=0');check('legacy capacity','Tls13ClientHelloCapacity()',265);begin(want=0);check('legacy unchanged','Tls13State',1)
 assert len(cases)*8+256<=65536
 template=(root/'tools/build_tls_quic_crypto_cpu.py').read_text()
 setup=template[template.index('Global Dim config.a[48]'):template.index('Procedure Run(index.i')]
 setup=setup.replace('localParams.a[2]','localParams.a[16384]').replace('output.a[1024]','output.a[20000]').replace(' n=Tls13BuildClientHello(@output[0],1024)\n','')
 source=out/'proof.pi4';source.write_text('#X509_SIG_LINKED=1\n'+'\n'.join('XIncludeFile "'+n+'"' for n in names)+'\n'+setup+r'''
Global tx.QuicCryptoTx,job.QuicTlsOutput
Global Dim txData.a[32768]
Global Dim txStates.a[8192]
Global Dim filler.a[4090]
Global Dim frame.a[20032]
Global Dim digest.a[32]
Global probeActive.i,probeSeen.i,probeStep.i
Procedure.i OutputYield()
 pet()
 If probeActive<>0
  probeSeen=probeSeen+1
  probeStep=QuicTlsOutputStep(@job)
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i Main()
 Define rc.i,i.i,total.i,high.i,saved.i
 CaptureTable() : *pet=PeekI(table+16+6*8)
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 Tls13PauseHook=@Yield : Tls13SetupPauseHook=@Yield
 TlsInitTables() : X25519Init()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\nquic_alpn:\nData.a 2,104,51\nEndDataSection\n')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
