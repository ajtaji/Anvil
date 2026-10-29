"""Build retained SPIR-V and typed subtraction qualification for the physical CPU."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 source_name='RaspberryPi4/Tests/Vulkan/vulkan_computed_uv_cpu.pbi';original=(root/source_name).read_bytes()
 import struct
 import vulkan_spirv_ir_adapter_check as fixtures
 def chunks(blob):
  w=list(struct.unpack('<%dI'%(len(blob)//4),blob));parts=[];at=5
  while at<len(w):
   n=w[at]>>16;parts.append(w[at:at+n]);at+=n
  return w[:5],parts
 cases=[]
 base=fixtures.oracle.fragment_sampled();ins=fixtures.oracle.ins
 def build(kind):
  header,parts=chunks(base);header[3]=25
  const=[ins(43,3,19,0x3e800000),ins(43,3,20,0x3f000000),ins(44,4,21,19,20)]
  if kind in (1,2,4):
   at=next(i for i,p in enumerate(parts) if p[0]&65535==54);parts[at:at]=const
  at=next(i for i,p in enumerate(parts) if p[0]&65535==87)
  coord=17
  if kind==1:coord=22;parts[at:at]=[ins(129,4,22,17,21)]
  if kind==2:coord=21
  if kind==3:
   coord=24;parts[at:at]=[ins(81,3,22,17,0),ins(81,3,23,17,1),ins(80,4,24,23,22)]
  if kind==4:coord=19
  if kind==5:coord=25
  if kind==6:coord=18
  sample=next(p for p in parts if p[0]&65535==87);sample[4]=coord
  words=header+[v for p in parts for v in p]
  return struct.pack('<%dI'%len(words),*words),sample[1:]
 for kind,name in enumerate(['direct vec2','offset vec2','constant vec2','reconstructed vec2']):
  blob,sample=build(kind);cases.append(dict(name=name,blob=blob,sample=sample))
 for kind,name,expected in [(4,'scalar coordinate',-20005),(5,'bound coordinate',-20001),(6,'self coordinate',-20005)]:
  blob,_=build(kind);cases.append(dict(name=name,blob=blob,expected=expected))
 cases.append(dict(name='vec3 coordinate',blob=fixtures.oracle.fragment_sampled(coord_components=3),expected=-20005))
 lines=['Procedure.i LoadCoordinateCase(trial.i,where.i)','  Select trial']
 for i,c in enumerate(cases):
  lines.append('    Case '+str(i))
  words=struct.unpack('<%dI'%(len(c['blob'])//4),c['blob'])
  for k,value in enumerate(words):lines.append('      PokeL(where+'+str(k*4)+',$'+format(value,'X')+')')
  lines.append('      ProcedureReturn '+str(len(c['blob'])))
 lines+=['  EndSelect','  ProcedureReturn 0','EndProcedure']
 source='\n'.join(lines)+'\n'+original.decode('utf8')
 (out/'cases.json').write_text(json.dumps([{k:v for k,v in c.items() if k!='blob'} for c in cases],indent=2),encoding='utf8')
 inputs={source_name:hashlib.sha256(original).hexdigest()};pending=[(source,None)]
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
