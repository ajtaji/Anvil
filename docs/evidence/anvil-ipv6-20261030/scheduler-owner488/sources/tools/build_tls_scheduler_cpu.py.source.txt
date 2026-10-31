"""TLS worker selection with an unrelated ready task and existing crypto corpus."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 base=root/'docs/evidence/anvil-tls-jobs-20261029/key-encrypt432'
 s=(base/'proof-source.txt').read_text(encoding='utf8')
 s=s.replace('Global ctxRootCancelled.i','''Global ctxRootCancelled.i
Global *Tls13PauseHook,*Tls13SetupPauseHook,*tlsc_profileHook
Global background.i,backgroundRuns.i,backgroundClean.i
; Diagnostic-only entry points are tripwires, not part of this qualification.
Global unexpectedProfile.i
Procedure str_print_at(address.i)
 unexpectedProfile=unexpectedProfile+1
EndProcedure
Procedure PrintDec(value.i)
 unexpectedProfile=unexpectedProfile+1
EndProcedure
Procedure PrintNl()
 unexpectedProfile=unexpectedProfile+1
EndProcedure
Procedure.i HwMicros()
 ProcedureReturn A64CounterReadOrdered()/(A64CounterFrequency()/1000000)
EndProcedure
Procedure.i BackgroundTask()
 backgroundRuns=backgroundRuns+1
 backgroundClean=Bool(X509PauseHook=0 And TlsRootsPauseHook=0 And TlsRecDecryptHook=0 And TlsRecEncryptHook=0 And Tls13PauseHook=0 And Tls13SetupPauseHook=0 And EcdsaVerifyHook=0 And RsaPublicHook=0 And X25519ComputeHook=0)
 ProcedureReturn 711
EndProcedure''')
 s=s.replace('ctxRootCancelled=0','''ctxRootCancelled=0
 backgroundRuns=0 : backgroundClean=0 : background=ScCreate(@BackgroundTask,0)
 If background=0 : ctxVerdict=-994 : ProcedureReturn : EndIf''')
 s=s.replace('If TlsRecEncryptHook<>0 Or', 'If backgroundRuns<>0 Or Tls13PauseHook<>0 Or Tls13SetupPauseHook<>0 Or TlsRecEncryptHook<>0 Or')
 needle='If tlsw_fault<>0 Or ctxCancelled=0 Or ctxOther<>ctxSteps : ctxVerdict=-996 : EndIf'
 assert s.count(needle)==1
 s=s.replace(needle,needle+'''
 If tlsw_handle<>0 : tlsw_Cancel(tlsc_handles[tlsw_slot]) : EndIf
 If backgroundRuns<>0 Or SchedState(background)<>#SCHED_READY : ctxVerdict=-994 : EndIf
 If ScRunHandle(background)<>background Or backgroundRuns<>1 Or backgroundClean<>1 Or ScResult(background)<>711 : ctxVerdict=-993 : EndIf
 If ScReap(background)<>1 : ctxVerdict=-992 : EndIf
 If unexpectedProfile<>0 : ctxVerdict=-991 : EndIf''')
 names=re.findall(r'^XIncludeFile "([^"]+)"',s,re.M)
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1500:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile "([^"]+)"',(root/name).read_text(encoding='utf8'),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 names+=['tools/build_tls_scheduler_cpu.py',str((base/'proof-source.txt').relative_to(root)),str((base/'identity.json').relative_to(root))]
 payload=(out/'proof.img.pmf').read_bytes();cases=json.loads((base/'identity.json').read_text())['cases']
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
