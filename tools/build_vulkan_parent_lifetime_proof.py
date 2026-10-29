"""Compile returning Vulkan parent lifetime proofs; no emulator or board access."""
from pathlib import Path
import argparse,json,hashlib,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--core-only',action='store_true');a=ap.parse_args()
 d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
 name='RaspberryPi4/Tests/'+('vulkan_parent_core_only_proof.pbi' if a.core_only else 'vulkan_parent_lifetime_proof.pbi')
 source=(ROOT/name).read_text(encoding='utf8');assert source.count('avkTbHeapBase=$6200000')==1
 source=source.replace('avkTbHeapBase=$6200000','avkTbHeapBase='+str(layout['heap']))
 (d/'proof.pbi').write_text('#TC_REPORT='+str(layout['report'])+'\n'+source,encoding='utf8')
 env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
 q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,encoding='utf8',timeout=120)
 (d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print(q.stdout+q.stderr);assert q.returncode==0
 ranges=check_linked_layout(layout,q.stdout+q.stderr);p=d/'proof.img.pmf'
 names=[name,'Anvil/Graphics/Vulkan/vk_foundation.pbi','Anvil/Graphics/Vulkan/vk_command.pbi','Anvil/Graphics/Vulkan/vk_api.pbi','Anvil/Graphics/Vulkan/vk_backend_test.pbi']
 names.extend(['Anvil/Graphics/Vulkan/vk_wsi.pbi','Anvil/Graphics/Vulkan/vk_surface.pbi'])
 i=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),layout=layout,checked_ranges=ranges,executed=False,controlled_backend=True,core_only=a.core_only,source_hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})
 (d/'identity.json').write_text(json.dumps(i,indent=2),encoding='utf8')
if __name__=='__main__':main()
