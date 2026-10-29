#!/usr/bin/env python3
"""Compile the shared retained control/state proof; never boot or emulate it."""
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
    source='EnableFloatingPoint\n'
    source+=f'#NRT_REPORT = ${layout["report"]:08X}\n'
    source+='XIncludeFile "Anvil/Graphics/Tests/neon_retained_ui_proof.pbi"\n'
    (out/'proof.pbi').write_text(source,encoding='utf8')
    env=os.environ.copy();env['PMF_ROOT']=str(root)
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8')
    print((q.stdout+q.stderr)[-1100:]);assert q.returncode==0
    ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
    paths=['Anvil/Graphics/Tests/neon_retained_ui_proof.pbi','Anvil/Graphics/neon_retained_ui.pbi','Anvil/Math/float32.pbi']
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},checked_ranges=ranges,controlled_providers=True,executed=False),indent=2))
if __name__=='__main__':main()
