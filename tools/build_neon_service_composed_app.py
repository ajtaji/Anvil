#!/usr/bin/env python3
"""Build the composed resident Neon application; touch injection is opt-in."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--scripted',action='store_true')
    ap.add_argument('--native-input',action='store_true',help='use resident ABI1.9 native input instead of raw touch')
    ap.add_argument('--assets',action='store_true',help='load the pinned PNG and font from board storage and exercise derived font policies')
    ap.add_argument('--retro',action='store_true',help='compose the full scene through the resident curved target; requires native input')
    ap.add_argument("--present-paced",action="store_true",help="use synchronized presentation cadence in the CRT test")
    a=ap.parse_args()
    if a.present_paced and not a.retro:ap.error("--present-paced requires --retro")
    if a.retro and not a.native_input:ap.error('--retro requires --native-input')
    if a.native_input and a.scripted:ap.error('--native-input and --scripted are mutually exclusive')
    root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    # Follow only literal includes reachable from the named entry; never enumerate directories.
    paths=[];pending=['Anvil/Graphics/Tests/neon_service_composed_app.pbi']
    while pending:
        p=pending.pop(0)
        if p in paths:continue
        assert len(paths)<64 and not Path(p).is_absolute() and '..' not in Path(p).parts
        paths.append(p)
        for child in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/p).read_text(encoding='utf8'),re.I|re.M):
            pending.append(child)
    if a.assets:paths.append('tools/neon_png_cases.json')
    before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    (out/'proof.pbi').write_text(f'#NCA_REPORT = ${layout["report"]:08X}\n#NCA_SCRIPTED = {int(a.scripted)}\n#NCA_ASSETS = {int(a.assets)}\n#NCA_NATIVE = {int(a.native_input)}\n#NCA_RETRO = {int(a.retro)}\n#NCA_PRESENT_PACED = {int(a.present_paced)}\nXIncludeFile "{paths[0]}"\n',encoding='utf8',newline='\n')
    compiler=resolve_compiler(a.compiler)
    compiler_sha=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    q=subprocess.run([str(compiler),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2000:])
    if q.returncode:raise SystemExit(q.returncode)
    assert before=={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    image=out/'proof.img.pmf';ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+16383)]
    assert compiler_sha==hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,scripted=a.scripted,assets=a.assets,native_input=a.native_input,retro=a.retro,present_paced=a.present_paced,graphics_protocol='1.13',bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=before,compiler_sha256=compiler_sha,executed=False,scope='Composed pure application; resident graphics and touch services required'),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
