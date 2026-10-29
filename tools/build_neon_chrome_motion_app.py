#!/usr/bin/env python3
"""Build keyed easing and drawn hover-region acceptance."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--scene',choices=['basic','menu','overflow'],default='basic')
    a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    # Follow only literal includes reachable from the named entry; never enumerate directories.
    paths=[];pending=['Anvil/Graphics/Tests/neon_chrome_motion_app.pbi']
    while pending:
        p=pending.pop(0)
        if p in paths:continue
        assert len(paths)<64 and not Path(p).is_absolute() and '..' not in Path(p).parts
        paths.append(p)
        for child in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/p).read_text(encoding='utf8'),re.I|re.M):
            pending.append(child)
    before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    (out/'proof.pbi').write_text(f'#NMR_REPORT = ${layout["report"]:08X}\n#NMR_SCENE = {dict(basic=1,menu=2,overflow=3)[a.scene]}\nXIncludeFile "{paths[0]}"\n',encoding='utf8')
    q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:])
    if q.returncode:raise SystemExit(q.returncode)
    assert before=={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    image=out/'proof.img.pmf';ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+16383)]
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,scene=a.scene,graphics_protocol='1.4',bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=before,executed=False,scope='Keyed chrome easing and drawn hover regions; resident graphics required'),indent=2),encoding='utf8')
if __name__=='__main__':main()
