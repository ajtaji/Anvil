#!/usr/bin/env python3
"""Compile the controlled pure sprite protocol proof; no emulator or board."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','unoq','pi3','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    paths=['Anvil/Graphics/Tests/neon_service_sprite_proof.pbi','Anvil/Hal/neon_service_api.pbi','Anvil/Graphics/neon_service_client.pbi','Anvil/Graphics/neon_service_sprite.pbi','Anvil/Math/float32.pbi']
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    (out/'proof.pbi').write_text(f'#NSP_REPORT = ${layout["report"]:08X}\nXIncludeFile "{paths[0]}"\n',encoding='utf8')
    result=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=result.stdout+result.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert result.returncode==0
    assert hashes=={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    image=out/'proof.img.pmf'
    identity=dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes=hashes,checked_ranges=check_linked_layout(layout,log),expected_assertions=len(re.findall(r'\bNspCheck\(', (root/paths[0]).read_text(encoding='utf8').split('Procedure.i Main(services.i)',1)[1])),executed=False,gpu=False)
    (out/'identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8')
if __name__=='__main__':main()
