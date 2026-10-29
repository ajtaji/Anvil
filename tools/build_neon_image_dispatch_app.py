#!/usr/bin/env python3
"""Build legacy automatic image-loading qualification, with a literal include graph."""
from pathlib import Path
import argparse,json,hashlib,re,subprocess,os
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target);entry='Anvil/Graphics/Tests/neon_image_dispatch_app.pbi'
    paths=[];pending=[entry]
    while pending:
        n=pending.pop(0)
        if n in paths:continue
        assert len(paths)<64 and not Path(n).is_absolute() and '..' not in Path(n).parts
        paths.append(n)
        pending.extend(re.findall(r'(?mi)^\s*XIncludeFile\s+"([^"]+)"',(root/n).read_text(encoding='utf8')))
    paths.append('tools/neon_image_dispatch_cases.json')
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
    plan=json.loads((root/paths[-1]).read_text(encoding='utf8'))
    code='#NAE_REPORT=$'+format(layout['report'],'08X')+'\nXIncludeFile "'+entry+'"\nDataSection\n'
    for label,key in [('nadBmp24','bmp24'),('nadBmp32','bmp32')]:
        b=bytes.fromhex(plan[key]);code+=label+':\n  Data.a '+','.join(str(v) for v in b)+'\n'
        (out/(key+'.bmp')).write_bytes(b)
    code+='EndDataSection\n';(out/'proof.pbi').write_text(code,encoding='utf8',newline='\n')
    compiler=resolve_compiler(a.compiler);compiler_sha=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    cmd=[str(compiler),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')]
    q=subprocess.run(cmd,env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2200:])
    assert q.returncode==0
    assert hashes=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
    image=out/'proof.img.pmf';ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+8191)]
    assert compiler_sha==hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes=hashes,compiler_sha256=compiler_sha,checked_ranges=ranges,executed=False,scope='Actual legacy BMP/PNG service loading plus registry/file faults; native wrapper runtime is separate'),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
