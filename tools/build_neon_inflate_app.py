#!/usr/bin/env python3
"""Compile shared DEFLATE/zlib cases and decoded native sprite proof."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);p.add_argument('--compiler',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
 plan=json.loads((root/'tools/neon_inflate_cases.json').read_text(encoding='utf8'))
 paths=[];pending=['Anvil/Graphics/Tests/neon_inflate_app.pbi']
 while pending:
  name=pending.pop(0)
  if name in paths:continue
  assert len(paths)<64 and not Path(name).is_absolute() and '..' not in Path(name).parts
  paths.append(name);pending.extend(re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(encoding='utf8'),re.I|re.M))
 paths.append('tools/neon_inflate_cases.json');before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
 (out/'proof.pbi').write_text(f'#NIF_REPORT = ${layout["report"]:08X}\n#NIF_REPORT_BYTES = {plan["report_bytes"]}\nXIncludeFile "{paths[0]}"\n',encoding='utf8')
 q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:])
 if q.returncode:raise SystemExit(q.returncode)
 assert before=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
 ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+plan['report_bytes']-1)];image=out/'proof.img.pmf'
 (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=before,executed=False,scope='Raw DEFLATE/zlib decoding plus resident sprite presentation; PNG container/filter integration pending'),indent=2),encoding='utf8')
if __name__=='__main__':main()
