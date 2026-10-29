"""Instrument an existing paired fixture through a private, hashed include graph.
Only literal dependencies recorded by its builder are read. Production files
are unchanged; procedure wrappers measure successful and refused returns.
"""
from pathlib import Path
import argparse,re,json,hashlib,subprocess,os
from pmf_compiler import resolve_compiler
from build_vulkan_viewport_packets import proc
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler',required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];base=a.base.resolve();d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 j=json.loads((base/'identity.json').read_text(encoding='utf8'));inputs=j['source_hashes']
 for n,h in inputs.items():assert hashlib.sha256((r/n).read_bytes()).hexdigest()==h,n
 mapping={n:d/f'include{i:03d}.txt' for i,n in enumerate(inputs)}
 replacements={}
 name='Anvil/Graphics/Vulkan/vk_pipeline.pbi';s=(r/name).read_text(encoding='utf8')
 names=['avkDrawListPreflight','avkDrawListRetain','avkDrawListRelease','avkDrawListSubmit']
 for i,n in enumerate(names):
  old=proc(s,n);typed=n in (names[0],names[3]);arg='' if i==3 else 'c.i';call='' if i==3 else 'c'
  renamed=old.replace(n+'(',n+'ProfileBody(',1)
  wrap=f'\nProcedure'+('.i' if typed else '')+f' {n}({arg})\n Define started.i,result.i\n started=V3dTicks()\n '
  wrap+=('result=' if typed else '')+f'{n}ProfileBody({call})\n submitProfileTicks[{i}]=submitProfileTicks[{i}]+V3dTicks()-started\n submitProfileCalls[{i}]=submitProfileCalls[{i}]+1\n'
  if typed:wrap+=' ProcedureReturn result\n'
  wrap+='EndProcedure'
  s=s.replace(old,renamed+wrap)
 replacements[name]=s
 name='RaspberryPi4/Tests/Vulkan/neon_paired_boxes.pbi';s=(r/name).read_text(encoding='utf8')
 s=s.replace('  beforeDraws=avkBackendDraws()', '  For i=0 To 3 : submitProfileTicks[i]=0 : submitProfileCalls[i]=0 : Next\n  beforeDraws=avkBackendDraws()')
 s=s.replace('  If kind=1\n', '  For i=0 To 3\n   PokeI(#NP_REPORT+2048+(kind*4+frame)*64+i*8,submitProfileTicks[i])\n   PokeI(#NP_REPORT+2048+(kind*4+frame)*64+32+i*8,submitProfileCalls[i])\n  Next\n  If kind=1\n')
 replacements[name]=s
 pattern=r'(?mi)^(\s*X?IncludeFile\s+)"([^"]+)"'
 def rewrite(text,owner=None):
  def replace(m):
   path=(r/m[2].replace('\\','/'))
   if not path.is_file() and owner:path=(r/owner).parent/m[2]
   n=path.resolve().relative_to(r).as_posix();assert n in mapping,n
   return m[1]+'"'+mapping[n].as_posix()+'"'
  return re.sub(pattern,replace,text)
 for n,dest in mapping.items():dest.write_text(rewrite(replacements.get(n,(r/n).read_text(encoding='utf-8-sig')),n),encoding='utf8')
 s='Global Dim submitProfileTicks.i[4]\nGlobal Dim submitProfileCalls.i[4]\n'+rewrite((base/'proof.pi4').read_text(encoding='utf8'))
 (d/'proof.pi4').write_text(s,encoding='utf8')
 compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap')
 for n,pair in j['checked_ranges'].items():
  if n not in ('code','bss','stack'):ranges[n]=pair
 spans=[(n,*(int(v,16) for v in pair)) for n,pair in ranges.items()]
 for i,(n,f,l) in enumerate(spans):
  for other,of,ol in spans[i+1:]:assert l<of or ol<f,n+' overlaps '+other
 p=d/'proof.img.pmf'
 generated={dest.name:hashlib.sha256(dest.read_bytes()).hexdigest() for dest in mapping.values()}
 generated['proof.pi4']=hashlib.sha256((d/'proof.pi4').read_bytes()).hexdigest()
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs,generated_hashes=generated,procedures=names,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),scope='Paired pixels plus per-frame portable submission phase timings; private diagnostic wrappers, no production source changes'),indent=2),encoding='utf8')
if __name__=='__main__':main()
