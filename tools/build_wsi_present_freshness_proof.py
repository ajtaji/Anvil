#!/usr/bin/env python3
"""Compile actual WSI freshness tests; never runs a board, GPU or emulator."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--old-without-query',action='store_true',help='Baseline reproduction before the query exists: omits only new query-specific cases.')
    a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
    source=f'#WPF_REPORT=${layout["report"]:08X}\n#WPF_QUERY_AVAILABLE={0 if a.old_without_query else 1}\n'
    source+='XIncludeFile "Anvil/Graphics/Vulkan/Tests/wsi_present_freshness_proof.pbi"\n'
    source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 8191 : PokeA(#WPF_REPORT+i,0) : Next
 rc=WsiPresentFreshnessProof()
 PokeI(#WPF_REPORT,$57504650) : PokeI(#WPF_REPORT+8,rc)
 PokeI(#WPF_REPORT+16,#PMF_CHIP) : PokeI(#WPF_REPORT+24,wpfRecords)
 PokeI(#WPF_REPORT+32,wpfFailures) : PokeI(#WPF_REPORT+40,1)
 PokeI(#WPF_REPORT+56,$50465057)
 ProcedureReturn rc
EndProcedure
'''
    (out/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,
       '--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services',
       '-o',str(out/'proof.img')],env=env,capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1200:],flush=True);assert q.returncode==0
    if a.target=='pi4':layout['windows'][1]=(layout['report'],layout['report']+8191)
    ranges=check_linked_layout(layout,q.stdout+q.stderr);ranges['report'][1]=hex(layout['report']+8191)
    spans=[(k,int(v[0],16),int(v[1],16)) for k,v in ranges.items()]
    for i,(name,lo,hi) in enumerate(spans):
        assert any(low<=lo<=hi<=high for low,high in layout['windows']),name
        for other,ol,oh in spans[i+1:]:assert hi<ol or oh<lo,name+' overlaps '+other
    image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Vulkan/Tests/wsi_present_freshness_proof.pbi','Anvil/Graphics/Vulkan/vk_wsi.pbi',
       'Anvil/Graphics/Vulkan/neon_vk_wsi_bridge.pbi','Anvil/Graphics/Vulkan/neon_vk_display.pbi',
       'Anvil/Graphics/Vulkan/vk_backend_test.pbi','tools/wsi_present_freshness_proof_check.py','tools/build_wsi_present_freshness_proof.py']
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,
       sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,report_bytes=8192,
       planned_observations=222 if a.old_without_query else 334,omits_new_query_cases=a.old_without_query,
       executed=False,actual_wsi_core=True,state_backend=True,gpu_execution=False,scanout_execution=False,
       source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}),indent=2),encoding='utf8')
if __name__=='__main__':main()
