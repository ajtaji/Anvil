"""Compile the exact production retirement guard with a controlled idle call.

This is a returning CPU contract test, not GPU fault injection or emulation.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',required=True,choices=['pi4','unoq'])
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
    r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    p=r/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi';raw=p.read_bytes();text=raw.decode('utf8')
    bodies=[]
    for name in ['nvcFail','NeonVkChromeExternalProducerDetach']:
        hits=list(re.finditer(r'(?mi)^Procedure\.i\s+'+name+r'\([^\n]*\n[\s\S]*?^EndProcedure',text));assert len(hits)==1,name
        bodies.append(hits[0].group())
    layout=state_proof_layout(a.target);rows=[];lines=[]
    def ck(expr,expected,label):
        rows.append({'actual':expr,'expected':expected,'label':label});lines.append(f'  NprCheck({expr},{expected})')
    def reset(ready=0):
        lines.append('  nvcDevice=7 : nvcReady='+str(ready)+' : nvcInFrame=0 : nvcFramePending=0 : nvcFrameAbortable=0 : nvcExternalProducerAttached=1 : nvcExternalProducerQuarantined=0 : nvcError=0 : NprIdleResult=0 : NprIdleCalls=0')
    for ready in [1,0]:
        reset(ready);ck('NeonVkChromeExternalProducerDetach()',0,'idle permits release ready='+str(ready))
        ck('nvcExternalProducerAttached',0,'ownership released');ck('NprIdleCalls',1,'idle actually checked');ck('nvcError',0,'success status')
    reset();lines.append('  NprIdleResult=-4')
    ck('NeonVkChromeExternalProducerDetach()',-4,'failed idle refuses');ck('nvcExternalProducerAttached',1,'failed idle preserves ownership');ck('NprIdleCalls',1,'failed idle called')
    lines.append('  NprIdleResult=0');ck('NeonVkChromeExternalProducerDetach()',0,'retry after idle completes');ck('nvcExternalProducerAttached',0,'retry releases');ck('NprIdleCalls',2,'retry checked idle again')
    for field,val in [('nvcDevice',0),('nvcInFrame',1),('nvcFramePending',1),('nvcFrameAbortable',1),('nvcExternalProducerQuarantined',1),('nvcExternalProducerAttached',0)]:
        reset();lines.append('  '+field+'='+str(val))
        ck('NeonVkChromeExternalProducerDetach()',-21202,'guard '+field)
        ck('nvcExternalProducerAttached',0 if field=='nvcExternalProducerAttached' else 1,'guard preserves owner')
        ck('NprIdleCalls',0,'guard makes no idle call')
    source='''#VK_SUCCESS=0
#NEON_VK_CHROME_OK=0
#NEON_VK_CHROME_ERR_STATE=-21202
Global nvcDevice.i,nvcReady.i,nvcInFrame.i,nvcFramePending.i,nvcFrameAbortable.i,nvcExternalProducerAttached.i,nvcExternalProducerQuarantined.i,nvcError.i
Global NprIdleResult.i,NprIdleCalls.i,NprChecks.i,NprFailure.i
Procedure.i vkDeviceWaitIdle(device.i)
  NprIdleCalls=NprIdleCalls+1 : ProcedureReturn NprIdleResult
EndProcedure
'''+('\n'.join(bodies))+f'''
Procedure NprCheck(actual.i,expected.i)
  PokeI(${layout['report']+256:X}+NprChecks*16,actual)
  PokeI(${layout['report']+264:X}+NprChecks*16,expected)
  NprChecks=NprChecks+1
  If actual<>expected And NprFailure=0 : NprFailure=NprChecks : EndIf
EndProcedure
Procedure.i Main()
  Protected i.i
  For i=0 To 4095 : PokeA(${layout['report']:X}+i,0) : Next
'''+('\n'.join(lines))+f'''
  PokeI(${layout['report']:X},$4E505231) : PokeI(${layout['report']+8:X},1)
  PokeI(${layout['report']+16:X},NprFailure) : PokeI(${layout['report']+24:X},NprChecks)
  ProcedureReturn NprFailure
EndProcedure
'''
    (d/'proof.pbi').write_text(source,encoding='utf8',newline='\n');(d/'cases.json').write_text(json.dumps(rows,indent=2),encoding='utf8',newline='\n')
    compiler=resolve_compiler(a.compiler);ch=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    q=subprocess.run([str(compiler),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-1500:]);assert q.returncode==0
    assert raw==p.read_bytes() and ch==hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    pmf=d/'proof.img.pmf';j={'target':a.target,'bytes':pmf.stat().st_size,'sha256':hashlib.sha256(pmf.read_bytes()).hexdigest(),'checked_ranges':check_linked_layout(layout,log),'source_hashes':{'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi':hashlib.sha256(raw).hexdigest()},'production_bodies':{name:hashlib.sha256(body.encode()).hexdigest() for name,body in zip(['nvcFail','NeonVkChromeExternalProducerDetach'],bodies)},'compiler_sha256':ch,'checks':len(rows),'executed':False,'scope':'Exact production detach/fail bodies with controlled idle-call outcomes; CPU retirement contract only, not GPU hardware fault recovery.'}
    (d/'identity.json').write_text(json.dumps(j,indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
