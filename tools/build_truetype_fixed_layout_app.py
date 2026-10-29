#!/usr/bin/env python3
"""Build the shared TrueType fixed layout proof; no emulation."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
 ap.add_argument('--baseline-entry',type=Path);ap.add_argument('--baseline-owner',type=Path);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 assert bool(a.baseline_entry)==bool(a.baseline_owner),'Baseline requires both explicit entry and original owner paths'
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 layout=state_proof_layout(a.target);paths=[];pending=[str(a.baseline_entry.resolve()) if a.baseline_entry else 'Anvil/Graphics/Tests/truetype_fixed_layout_app.pbi']
 while pending:
  name=pending.pop(0)
  if name in paths:continue
  assert len(paths)<64 and '..' not in Path(name).parts
  if Path(name).is_absolute():assert a.baseline_entry and Path(name) in [a.baseline_entry.resolve(),a.baseline_owner.resolve()]
  paths.append(name)
  pending.extend(re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(encoding='utf8'),re.I|re.M))
 paths.append('tools/truetype_fixed_layout_cases.json')
 before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
 (out/'proof.pbi').write_text(f'#TFX_REPORT = ${layout["report"]:08X}\n#TFX_REPORT_BYTES = 65536\nXIncludeFile "{paths[0]}"\n',encoding='utf8',newline='\n')
 compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-1500:])
 assert q.returncode==0
 assert before=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
 ranges=check_linked_layout(layout,log);ranges['report']=[hex(layout['report']),hex(layout['report']+65535)]
 payload=(out/'proof.img.pmf').read_bytes()
 (out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes=before,executed=False,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),scope='Shared procedural TrueType fixed layout copies'),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
