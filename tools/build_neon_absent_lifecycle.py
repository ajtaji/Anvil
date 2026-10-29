from pathlib import Path
import sys,os,subprocess,hashlib,json,re
import argparse
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ap=argparse.ArgumentParser(description='Build physical CPU qualification of the absent native lifecycle')
ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
R=Path(__file__).resolve().parents[1];C=Path(resolve_compiler(a.compiler))
d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
source='XIncludeFile "Anvil/Graphics/Tests/neon_absent_lifecycle.pbi"\nProcedure.i Main()\n  Protected i.i\n  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next\n  ProcedureReturn NeonAbsentLifecycleProof($E1C00000)\nEndProcedure\n'
(d/'proof.pi4').write_text(source,encoding='utf8',newline='\n')
pending=[(source,None)];inputs={}
while pending:
 s,owner=pending.pop(0)
 for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',s):
  p=R/spelling
  if not p.is_file() and owner:p=(R/owner).parent/spelling
  p=p.resolve();assert p.is_relative_to(R)
  n=p.relative_to(R).as_posix()
  if n in inputs:continue
  b=p.read_bytes();inputs[n]=hashlib.sha256(b).hexdigest();pending.append((b.decode('utf-8-sig'),n))
q=subprocess.run([str(C),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(R)),capture_output=True,text=True,encoding='utf8',timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');assert q.returncode==0,log[-4000:]
ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges['report']=['0xe1c00000','0xe1c03fff']
b=(d/'proof.img.pmf').read_bytes()
(d/'identity.json').write_text(json.dumps(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),compiler_sha256=hashlib.sha256(C.read_bytes()).hexdigest(),source_hashes=inputs,checked_ranges=ranges,executed=False,scope='CPU-only absent native lifecycle refusal; no graphics device operation'),indent=2),encoding='utf8',newline='\n')
print(len(b),hashlib.sha256(b).hexdigest())
