#!/usr/bin/env python3
"""Compile the real WSI core/bridge proof; no board, GPU or emulator is run."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
from neon_wsi_transaction_proof_check import expected_records
from neon_vk_chrome_acceptance_check import procedure_body

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target);assert 64+16*len(expected_records())<=4096
    chrome=(root/'Anvil/Graphics/Vulkan/neon_vk_chrome.pi4').read_text(encoding='utf8')
    production='\n\n'.join(procedure_body(chrome,name) for name in ['nvcFail','NeonVkChromeBegin'])
    calls=set(re.findall(r'\b(\w+)\s*\(',production))
    globals_=sorted(set(re.findall(r'\bnvc[A-Z]\w*\b',production))-calls)
    decl='\n'.join('Global '+name+'.i' for name in globals_)+'\n'
    spies='''
XIncludeFile "Anvil/Graphics/float_bits.pbi"
Procedure.i nvcAtlasRefresh()
 nwtBeforeRecordingWork=nwtBeforeRecordingWork+1
 ProcedureReturn -29999
EndProcedure
Procedure nvcBudgetReset() : nwtBeforeRecordingWork=nwtBeforeRecordingWork+1 : EndProcedure
Procedure nvcOutlineResetFrame() : nwtBeforeRecordingWork=nwtBeforeRecordingWork+1 : EndProcedure
Procedure NeonVkChromeScissorClear() : nwtBeforeRecordingWork=nwtBeforeRecordingWork+1 : EndProcedure
Procedure.i AnvilTrueTypeRasterCount() : nwtBeforeRecordingWork=nwtBeforeRecordingWork+1 : ProcedureReturn 0 : EndProcedure
'''
    for name in ['NEON_VK_CHROME_ERR_STATE','NEON_VK_CHROME_OK','NEON_VK_CHROME_F_ONE','NVC_PATH_NONE']:
        constants=re.findall(r'^#'+name+r'\s*=\s*([^;\r\n]+)',chrome,re.M)
        assert len(constants)==1,name
        spies='#'+name+'='+constants[0].strip()+'\n'+spies
    fixture=(root/'Anvil/Graphics/Vulkan/Tests/neon_wsi_transaction_proof.pbi').read_text(encoding='utf8')
    assert fixture.count('; @NWT_BEGIN_COMPOSITION@')==1
    source=f'#NWT_REPORT=${layout["report"]:08X}\n'+fixture.replace('; @NWT_BEGIN_COMPOSITION@',decl+spies+production)
    source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#NWT_REPORT+i,0) : Next
 rc=NeonWsiTransactionProof()
 PokeI(#NWT_REPORT,$4E575450) : PokeI(#NWT_REPORT+8,rc)
 PokeI(#NWT_REPORT+16,#PMF_CHIP) : PokeI(#NWT_REPORT+24,nwtRecords)
 PokeI(#NWT_REPORT+32,nwtFailures) : PokeI(#NWT_REPORT+40,2)
 PokeI(#NWT_REPORT+56,$5054574E)
 ProcedureReturn rc
EndProcedure
'''
    (out/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,
       '--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services',
       '-o',str(out/'proof.img')],env=env,capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1200:],flush=True)
    assert q.returncode==0
    ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Vulkan/Tests/neon_wsi_transaction_proof.pbi','Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pbi',
           'Anvil/Graphics/Vulkan/neon_vk_display.pbi','Anvil/Graphics/Vulkan/vk_wsi.pbi',
           'Anvil/Graphics/Vulkan/vk_backend_test.pbi','Anvil/Graphics/Vulkan/neon_vk_chrome.pi4',
           'Anvil/Graphics/float_bits.pbi','tools/neon_wsi_transaction_proof_check.py','tools/build_neon_wsi_transaction_proof.py']
    identity=dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
       checked_ranges=ranges,report_bytes=4096,planned_observations=len(expected_records()),executed=False,
       actual_wsi_core=True,actual_bridge=True,scanout_execution=False,gpu_execution=False,
       actual_begin_body=True,admitted_begin_uses_rejecting_atlas_spy=True,
       source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths})
    (out/'identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8')
if __name__=='__main__':main()
