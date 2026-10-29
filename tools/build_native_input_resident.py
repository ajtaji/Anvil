#!/usr/bin/env python3
"""Build portable input client qualification with a controlled provider."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    layout=state_proof_layout(a.target)
    entry='Anvil/Core/Tests/native_input_resident.pbi';paths=[];pending=[entry]
    while pending:
        n=pending.pop(0)
        if n in paths:continue
        assert len(paths)<32 and not Path(n).is_absolute() and '..' not in Path(n).parts
        paths.append(n)
        pending.extend(re.findall(r'(?mi)^\s*XIncludeFile\s+"([^"]+)"',(r/n).read_text(encoding='utf8')))
    paths.append('tools/native_input_resident_cases.json')
    before={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in paths}
    s='#NIP_REPORT=$'+format(layout['report'],'08X')+'\nXIncludeFile "'+entry+'"\n'
    (d/'proof.pbi').write_text(s,encoding='utf8',newline='\n')
    compiler=resolve_compiler(a.compiler);compiler_sha=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    q=subprocess.run([str(compiler),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2200:])
    assert q.returncode==0
    assert before=={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in paths}
    assert compiler_sha==hashlib.sha256(Path(compiler).read_bytes()).hexdigest()
    ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+8191)]
    image=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes=before,compiler_sha256=compiler_sha,checked_ranges=ranges,executed=False,scope='Actual resident service boundary and return cleanup; device polling without physical actuation claim'),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
