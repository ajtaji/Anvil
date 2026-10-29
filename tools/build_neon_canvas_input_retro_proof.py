"""Build curved canvas input qualification for the physical CPU."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Tests/Vulkan/neon_canvas_input_retro_cpu.pbi';original=(root/name).read_bytes()
 source=original.decode('utf8')
 inputs={name:hashlib.sha256(original).hexdigest()};pending=[(source,None)]
 while pending:
  text,owner=pending.pop(0)
  for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',text):
   p=root/spelling
   if not p.is_file() and owner:p=(root/owner).parent/spelling
   p=p.resolve();assert p.is_relative_to(root);n=p.relative_to(root).as_posix()
   if n in inputs:continue
   blob=p.read_bytes();inputs[n]=hashlib.sha256(blob).hexdigest();pending.append((blob.decode('utf8'),n))
 (out/'proof.pi4').write_text(source,encoding='utf8',newline='\n');compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(out/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1200:]);assert q.returncode==0
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap');ranges['report']=['0xe1c00000','0xe1c03fff']
 assert inputs=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in inputs}
 blob=(out/'proof.img.pmf').read_bytes()
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
