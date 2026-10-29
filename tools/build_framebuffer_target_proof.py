#!/usr/bin/env python3
"""Compile the actual framebuffer object graph over the state-only backend.

Never runs an interpreter, emulator or board. Prospective layout checks do not
replace a live monitor map or establish hardware graphics support.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
    source=f'#FBQ_REPORT = ${layout["report"]:08X}\n'
    source+='XIncludeFile "Anvil/Graphics/Vulkan/Tests/framebuffer_target_proof.pbi"\n'
    source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#FBQ_REPORT+i,0) : Next
 rc=FramebufferTargetProof()
 PokeI(#FBQ_REPORT,$46425150) : PokeI(#FBQ_REPORT+8,rc)
 PokeI(#FBQ_REPORT+16,#PMF_CHIP) : PokeI(#FBQ_REPORT+24,fbqRecords)
 PokeI(#FBQ_REPORT+32,fbqFailures) : PokeI(#FBQ_REPORT+40,2)
 PokeI(#FBQ_REPORT+56,$50514246)
 ProcedureReturn rc
EndProcedure
'''
    (out/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1000:]);assert q.returncode==0
    ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Vulkan/vk_pipeline.pbi','Anvil/Graphics/Vulkan/vk_memory.pbi','Anvil/Graphics/Vulkan/vk_backend_test.pbi','Anvil/Graphics/Vulkan/Tests/framebuffer_target_proof.pbi']
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},checked_ranges=ranges,state_backend=True,executed=False),indent=2))
if __name__=='__main__':main()
