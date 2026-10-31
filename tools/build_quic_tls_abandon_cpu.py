"""Retain QUIC output admission corpus and test abandonment inside a builder."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 base=root/'docs/evidence/anvil-ipv6-20261030/quic-output488/quic-output1524'
 s=(base/'proof.pi4').read_text(encoding='utf8')
 s=s.replace('Global probeActive.i,probeSeen.i,probeStep.i','Global probeActive.i,probeSeen.i,probeStep.i,abandonResult.i')
 s=s.replace('  probeStep=QuicTlsOutputStep(@job)', '''  If probeActive=2
   If probeSeen=1 : abandonResult=QuicTlsOutputAbandon(@job) : EndIf
  Else
   probeStep=QuicTlsOutputStep(@job)
  EndIf''')
 cases=json.loads((base/'identity.json').read_text())['cases']
 extra=[('abandon stream init',0),('builder refuses abandoned output',-3493),('abandon hook executed',1),('abandon verdict',-3493),('job stays terminal',-1),('stream stays poisoned',3),('unpublished byte count',0),('no retained output',0),('copy after abandon',-3493),('append after abandon',-3482),('TLS transcript was not rolled back',2),('repeat job abandon refused',-3492),('stream close idempotent',0)]
 code='''Prepare()
For i=0 To SizeOf(QuicTlsOutput)-1 : PokeA(@job+i,0) : Next
probeSeen=0 : abandonResult=0
'''
 expr=['QuicCryptoTxInit(@tx,0,@txData[0],32768,@txStates[0],8192)','QuicTlsOutputBegin(@job,@tx,@output[0],20000)','Bool(probeSeen>0)','abandonResult','job\\phase','tx\\phase','job\\bytes','tx\\tail','QuicTlsOutputStep(@job)','QuicCryptoTxAppend(@tx,@output[0],1)','Tls13State','QuicTlsOutputAbandon(@job)','QuicCryptoTxAbandon(@tx)']
 for i,e in enumerate(expr):
  if i==1:code+='probeActive=2 : Tls13PauseHook=@OutputYield\n'
  code+=f'PokeI($E1C00100+{(len(cases)+i)*8},{e})\n'
  if i==1:code+='probeActive=0 : Tls13PauseHook=@Yield\n'
 cases+=[dict(name=n,expected=v) for n,v in extra]
 s=s.replace('PokeI($E1C00008,79)',code+f'PokeI($E1C00008,{len(cases)})')
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1300:]);assert q.returncode==0
 names=re.findall(r'^XIncludeFile "([^"]+)"',s,re.M);todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile "([^"]+)"',(root/name).read_text(encoding='utf8'),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 names+=['tools/build_quic_tls_abandon_cpu.py',str((base/'proof.pi4').relative_to(root)),str((base/'identity.json').relative_to(root))]
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
