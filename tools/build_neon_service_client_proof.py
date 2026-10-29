#!/usr/bin/env python3
"""Compile the pure service client/controller proof; never run or emulate it."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    source=f'#NST_REPORT = ${layout["report"]:08X}\nXIncludeFile "Anvil/Graphics/Tests/neon_service_client_proof.pbi"\n'
    (d/'proof.pbi').write_text(source,encoding='utf8')
    paths=['Anvil/Graphics/Tests/neon_service_client_proof.pbi','Anvil/Hal/neon_service_api.pbi','Anvil/Graphics/neon_service_client.pbi','Anvil/Graphics/neon_service_retained.pbi','Anvil/Graphics/neon_retained_ui.pbi','Anvil/Math/float32.pbi']
    before={name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in paths}
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    (d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1600:]);assert q.returncode==0
    assert before=={name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in paths}
    text=(r/paths[0]).read_text(encoding='utf8').split('Procedure.i Main(services.i)',1)[1]
    image=d/'proof.img.pmf'
    j=dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=check_linked_layout(layout,q.stdout+q.stderr),source_hashes=before,expected_assertions=len(re.findall(r'\bNstCheck\(',text)),scope='Controlled provider and pure service-client/retained code only; no native driver/GPU implementation; real old-ABI refusal recorded separately',executed=False)
    (d/'identity.json').write_text(json.dumps(j,indent=2),encoding='utf8')
if __name__=='__main__':main()
