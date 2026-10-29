#!/usr/bin/env python3
"""Compile the shared controlled-provider binder proof; never boot or emulate it."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    source='XIncludeFile "Anvil/Graphics/Vulkan/Tests/neon_vk_lifecycle_binder_gate.pbi"\n'
    source+=f'#BINDER_REPORT = ${layout["report"]:08X}\n'
    source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#BINDER_REPORT+i,0) : Next
 rc=NeonVkLifecycleBinderGate()
 PokeI(#BINDER_REPORT,$42494E44) : PokeI(#BINDER_REPORT+8,rc)
 PokeI(#BINDER_REPORT+16,#PMF_CHIP) : PokeI(#BINDER_REPORT+24,1)
 PokeI(#BINDER_REPORT+32,binderNativeCalls)
 PokeI(#BINDER_REPORT+40,fakeCreateCount) : PokeI(#BINDER_REPORT+48,fakeDestroyCount)
 PokeI(#BINDER_REPORT+56,fakeBeginCount) : PokeI(#BINDER_REPORT+64,fakeEndCount)
 PokeI(#BINDER_REPORT+72,Neon_Ready()) : PokeI(#BINDER_REPORT+80,NeonDrawBackendActive())
 PokeI(#BINDER_REPORT+88,NeonVkLifecycleConfigured())
 PokeI(#BINDER_REPORT+96,gNeonLifecycleMode)
 PokeI(#BINDER_REPORT+104,fakeClear0) : PokeI(#BINDER_REPORT+112,fakeClear1)
 PokeI(#BINDER_REPORT+120,fakeClear2) : PokeI(#BINDER_REPORT+128,fakeClear3)
 PokeI(#BINDER_REPORT+136,$444E4942)
 ProcedureReturn rc
EndProcedure
'''
    (out/'proof.pbi').write_text(source,encoding='utf8')
    env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8')
    print((q.stdout+q.stderr)[-1100:]);assert q.returncode==0
    ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Vulkan/Tests/neon_vk_lifecycle_binder_gate.pbi','Anvil/Graphics/Vulkan/neon_vk_lifecycle.pbi','Anvil/Graphics/neon_lifecycle.pbi','Anvil/Graphics/neon_frontend.pbi','Anvil/Graphics/float_bits.pbi','Anvil/Graphics/neon_colour.pbi']
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},checked_ranges=ranges,controlled_providers=True,executed=False),indent=2))
if __name__=='__main__':main()
