#!/usr/bin/env python3
"""Compile actual WSI commit/provider state tests; never enters a board or emulator."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
    source=f'#WCR_REPORT=${layout["report"]:08X}\nXIncludeFile "Anvil/Graphics/Vulkan/Tests/wsi_commit_revalidation_proof.pbi"\n'
    source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#WCR_REPORT+i,0) : Next
 rc=WsiCommitRevalidationProof()
 PokeI(#WCR_REPORT,$57435250) : PokeI(#WCR_REPORT+8,rc)
 PokeI(#WCR_REPORT+16,#PMF_CHIP) : PokeI(#WCR_REPORT+24,wcrRecords)
 PokeI(#WCR_REPORT+32,wcrFailures) : PokeI(#WCR_REPORT+40,1)
 PokeI(#WCR_REPORT+56,$50524357)
 ProcedureReturn rc
EndProcedure
'''
    (out/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,
       '--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services',
       '-o',str(out/'proof.img')],env=env,capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1200:],flush=True);assert q.returncode==0
    ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Vulkan/Tests/wsi_commit_revalidation_proof.pbi','Anvil/Graphics/Vulkan/vk_wsi.pbi',
           'Anvil/Graphics/Vulkan/vk_backend_test.pbi','tools/wsi_commit_revalidation_proof_check.py','tools/build_wsi_commit_revalidation_proof.py']
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,
       sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,report_bytes=4096,
       planned_observations=201,cases=7,executed=False,actual_wsi_core=True,state_backend=True,
       gpu_execution=False,scanout_execution=False,
       source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}),indent=2),encoding='utf8')
if __name__=='__main__':main()
