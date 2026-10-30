"""Compile RSA padding corpus and X25519 vectors with cooperative scheduling."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out,context=False):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Core/sha256.pbi','Anvil/Crypto/bignum.pbi','Anvil/Crypto/bignum_job.pbi','Anvil/Crypto/rsa.pbi','Anvil/Crypto/rsa_job.pbi','Anvil/Crypto/x25519.pbi','Anvil/Crypto/x25519_job.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Core/cryptotest_vectors.pbi']
 corpus=(root/names[-1]).read_text(encoding='utf8')
 meta=[list(map(int,x.split(','))) for x in re.findall(r'^\s*Data\.l ([^\r\n]+)',corpus,re.M)]
 blob=bytes(int(x.strip()) for line in re.findall(r'^\s*Data\.b ([^\r\n]+)',corpus,re.M) for x in line.split(','))
 cases=[];data=[]
 for row in meta:
  if row[0] not in (14,16):continue
  mod,idx,a,b,c,d,e,f,param,off=row
  raw=blob[off:off+a+b+c+d+e+f]
  expected=raw[a+b+c+d:a+b+c+d+e].hex()
  cases.append(dict(module=mod,vector=idx,lengths=[a,b,c,d,e,f],param=param,expected=expected))
  data.append(raw)
 assert len(cases)<63
 s='\n'.join('XIncludeFile "'+n+'"' for n in names[:-1])+r'''
Global wtable.i
Global *pet,*timer
Global Dim hash.a[64]
Global Dim recovered.a[64]
Global Dim output.a[64]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure KeyJobRsa(index.i,v.i,an.i,bn.i,cn.i,dn.i,param.i)
 Define i.i,rc.i,t.i,start.i,maximum.i,steps.i,verdict.i,kind.i,p.i,n.i,elapsed.i
 kind=param & 255 : n=an
 For i=0 To 63 : recovered[i]=$A5 : Next
 Sha256Of(v+an+bn+cn,dn,@hash)
 If kind=4 : n=0 : EndIf
 start=timer() : rc=RsaJobBegin(v+an+bn,cn,v,n,v+an,bn) : maximum=timer()-start
 steps=0
 While rc=0
  t=timer() : rc=RsaJobStep() : elapsed=timer()-t
  If elapsed>maximum : maximum=elapsed : EndIf
  steps=steps+1 : pet()
 Wend
 verdict=RsaJobResult
 If verdict=1
  If kind=1
   verdict=RsaPssVrfyUnpad(@RsaSig,@hash,32,(param>>16) & 255,v,an)
  Else
   verdict=RsaPkcs1SigUnpad(@RsaSig,cn,RsaOidSha256(),32,@recovered)
   If kind=0
    If verdict<>0 : verdict=RsaMemEq(@recovered,@hash,32) : EndIf
   EndIf
  EndIf
 EndIf
 p=$E1C00100+index*1024
 PokeI(p,verdict) : PokeI(p+8,maximum) : PokeI(p+16,steps) : PokeI(p+24,timer()-start)
 For i=0 To 63 : PokeA(p+128+i,recovered[i]) : Next
 RsaJobCancel()
 PokeI(p+32,RsaJobStep())
EndProcedure
Procedure KeyJobX(index.i,v.i)
 Define i.i,rc.i,t.i,start.i,maximum.i,steps.i,p.i,elapsed.i,wipe.i
 For i=0 To 63 : output[i]=$A5 : Next
 ; Explicit cancellation after entering the secret ladder, then restart.
 rc=X25519JobBegin(@output,v,v+32)
 For i=0 To 12 : rc=X25519JobStep() : Next
 X25519JobCancel()
 wipe=1
 For i=0 To 31
  If PeekA(@SecK+i)<>0 Or PeekA(@XWG+i)<>0 Or output[i]<>$A5 : wipe=0 : EndIf
 Next
 start=timer() : rc=X25519JobBegin(@output,v,v+32) : maximum=timer()-start
 steps=0
 While rc=0
  t=timer() : rc=X25519JobStep() : elapsed=timer()-t
  If elapsed>maximum : maximum=elapsed : EndIf
  steps=steps+1 : pet()
 Wend
 p=$E1C00100+index*1024
 PokeI(p,rc) : PokeI(p+8,maximum) : PokeI(p+16,steps) : PokeI(p+24,timer()-start)
 PokeI(p+32,X25519JobStep()) : PokeI(p+40,wipe)
 For i=0 To 63 : PokeA(p+128+i,output[i]) : Next
 For i=0 To 31
  If PeekA(@SecK+i)<>0 Or PeekA(@XWG+i)<>0 : wipe=0 : EndIf
 Next
 PokeI(p+48,wipe)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4B4A4231)
 pet=PeekI(wtable+16+6*8) : timer=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,c in enumerate(cases):
  a,b,cc,d,e,f=c['lengths']
  if c['module']==14:s+=f' KeyJobX({i},?V{i})\n'
  else:s+=f' KeyJobRsa({i},?V{i},{a},{b},{cc},{d},{c["param"]})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed() : ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,b in enumerate(data):
  s+=f'V{i}:\n'
  for j in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[j:j+24]))+'\n'
 s+='EndDataSection\n'
 if context:
  extra=['Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/gcm_job.pbi','Anvil/Crypto/ec256.pbi','Anvil/Crypto/ecp.pbi','Anvil/Crypto/ecdsa.pbi','Anvil/Crypto/ecdsa_job.pbi','Anvil/Crypto/ecp_job.pbi','Anvil/Hal/aarch64_counter.pbi','Anvil/Kernel/Scheduler/scheduler.pbi','Anvil/Kernel/Scheduler/cooperative_a64.pbi']
  names+=extra+['Anvil/Core/tls_cooperative.pbi']
  pos=s.index('Procedure CaptureTable()')
  s=s[:pos]+'\n'.join('XIncludeFile "'+n+'"' for n in extra)+'\n'+r'''
#TLSC_CONNECTIONS=4
#TLSC_PREPARE=7
Global *X509PauseHook,*TlsRootsPauseHook,*TlsRecDecryptHook
#TLSC_RESOLVING=1
#TLSC_TCP=2
#TLSC_HS=3
#TLSC_HS_MS=20000
#SVC_EIO=-101
#SVC_EBUSY=-103
Global tlsc_slot.i,tlsc_state.i,tlsc_t0.i
Global Dim tlsc_handles.i[4]
Global *tlsc_advanceHook,*tlsc_closeHook
Global ctxKind.i,ctxV.i,ctxA.i,ctxB.i,ctxC.i,ctxVerdict.i
Global ctxMaximum.i,ctxSteps.i,ctxOther.i,ctxCancelled.i
Global ctxRootCancelled.i
Procedure TlsRootsCancelLoad()
 ctxRootCancelled=ctxRootCancelled+1
EndProcedure
Procedure tlsc_Select(slot.i)
 tlsc_slot=slot
EndProcedure
Procedure tlsc_Refuse(code.i,why.i)
 ctxVerdict=code
EndProcedure
Procedure.i millis()
 ProcedureReturn A64CounterReadOrdered()/(A64CounterFrequency()/1000)
EndProcedure
Procedure tlsc_AdvanceWork()
 Define marker.i
 marker=$123456789
 If ctxKind=14
  ctxVerdict=X25519(@output,ctxV,ctxV+32)
 Else
  ctxVerdict=RsaPublic(@RsaSig,ctxC,ctxV,ctxA,ctxV+ctxA,ctxB)
 EndIf
 If marker<>$123456789 : ctxVerdict=-998 : EndIf
EndProcedure
XIncludeFile "Anvil/Core/tls_cooperative.pbi"
Procedure KeyContextRun(kind.i,v.i,an.i,bn.i,cn.i)
 Define i.i,t.i,elapsed.i,caller.i
 ctxKind=kind : ctxV=v : ctxA=an : ctxB=bn : ctxC=cn
 ctxMaximum=0 : ctxSteps=0 : ctxOther=0 : ctxVerdict=0 : ctxCancelled=1
 ctxRootCancelled=0
 For i=0 To cn-1 : RsaSig[i]=PeekA(v+an+bn+i) : Next
 ; Discard one suspended secret-key task and restart from original input.
 If kind=14
  tlsw_Advance()
  If tlsw_handle=0
   ctxCancelled=0
  Else
   tlsw_Cancel(tlsc_handles[tlsw_slot])
   If tlsw_handle<>0 Or X25519JobPhase<>0 Or X25519ComputeHook<>0 : ctxCancelled=0 : EndIf
   If ctxRootCancelled<>1 : ctxCancelled=0 : EndIf
  EndIf
 EndIf
 Repeat
  caller=ctxSteps & 1 : tlsc_Select(caller)
  t=timer() : tlsw_Advance() : elapsed=timer()-t
  If elapsed>ctxMaximum : ctxMaximum=elapsed : EndIf
  If tlsc_slot<>caller : ctxVerdict=-997 : Break : EndIf
  If TlsRecDecryptHook<>0 Or X509PauseHook<>0 Or TlsRootsPauseHook<>0 Or EcdsaVerifyHook<>0 Or RsaPublicHook<>0 Or X25519ComputeHook<>0
   ctxVerdict=-995 : Break
  EndIf
  ctxOther=ctxOther+1 : ctxSteps=ctxSteps+1 : pet()
  If tlsw_handle=0 : Break : EndIf
 Until ctxSteps>10000
 If tlsw_fault<>0 Or ctxCancelled=0 Or ctxOther<>ctxSteps : ctxVerdict=-996 : EndIf
EndProcedure
'''+s[pos:]
  a=s.index(' start=timer() : rc=RsaJobBegin');b=s.index(' If verdict=1',a)
  s=s[:a]+''' start=timer() : KeyContextRun(16,v,n,bn,cn)
 maximum=ctxMaximum : steps=ctxSteps : verdict=ctxVerdict
'''+s[b:]
  a=s.index(' start=timer() : rc=X25519JobBegin');b=s.index(' p=$E1C00100+index*1024',a)
  s=s[:a]+''' start=timer() : KeyContextRun(14,v,0,0,0)
 maximum=ctxMaximum : steps=ctxSteps : rc=ctxVerdict
'''+s[b:]
  s=s.replace(' MmuEnableCached()', ''' MmuEnableCached()
 rc=TlsCooperativeInstall($1000000,$80000) : If rc<>1 : MmuDisableCachedFlushed() : ProcedureReturn 3 : EndIf
 tlsc_handles[0]=1 : tlsc_handles[1]=2 : tlsc_state=4
''')
  for c in cases:c['cooperative_context']=True
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--context',action='store_true')
 args=ap.parse_args();build(args.compiler,args.out.resolve(),args.context)
