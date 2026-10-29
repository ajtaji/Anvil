"""Build retained SPIR-V and typed dot product qualification for the physical CPU."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout, check_linked_layout

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Tests/Vulkan/vulkan_dot_cpu.pbi';original=(root/name).read_bytes()
 import struct
 import vulkan_spirv_ir_adapter_check as fixtures
 def chunks(blob):
  w=list(struct.unpack('<%dI'%(len(blob)//4),blob));parts=[];at=5
  while at<len(w):
   n=w[at]>>16;parts.append(w[at:at+n]);at+=n
  return w[:5],parts
 cases=[]
 for trial,lanes in enumerate([2,3,4,4]):
  header,parts=chunks(fixtures.arithmetic(131,lanes))
  sub=next(p for p in parts if p[0]&65535==131)
  f32=next(p[1] for p in parts if p[0]&65535==22)
  vec4=next(p[1] for p in parts if p[0]&65535==23 and p[3]==4)
  sub[0]=(5<<16)|148;sub[1]=f32
  if trial==3:
   for part in parts:
    if part[0]&65535==43 and part[1]==f32:part[3]^=0x80000000;break
  colour=header[3];header[3]+=1
  extra=[(7<<16)|80,vec4,colour,sub[2],sub[2],sub[2],sub[2]]
  at=next(i for i,p in enumerate(parts) if p[0]&65535==62);parts[at][2]=colour;parts[at:at]=[extra]
  words=header+[v for p in parts for v in p];blob=struct.pack('<%dI'%len(words),*words)
  cases.append(dict(name='dot width '+str(lanes)+(' negative' if trial==3 else ''),blob=blob,lanes=lanes,sub=sub[1:]))
 base=cases[3]['blob'];header,parts=chunks(base)
 scalar=next(p[2] for p in parts if p[0]&65535==43)
 for label,blob,code in [('self use',fixtures.arithmetic_self_use(base,148),-20001),('mixed operand type',fixtures.mutate_arithmetic(base,148,3,scalar),-20005),('bound result id',fixtures.mutate_arithmetic(base,148,2,header[3]),-20001),('after return',fixtures.move_after_return(base,148),-20005)]:
  cases.append(dict(name=label,blob=blob,expected=code))
 lines=['Procedure.i LoadDotCase(trial.i,where.i)','  Select trial']
 for i,c in enumerate(cases):
  lines.append('    Case '+str(i))
  words=struct.unpack('<%dI'%(len(c['blob'])//4),c['blob'])
  for k,value in enumerate(words):lines.append('      PokeL(where+'+str(k*4)+',$'+format(value,'X')+')')
  lines.append('      ProcedureReturn '+str(len(c['blob'])))
 lines+=['  EndSelect','  ProcedureReturn 0','EndProcedure']
 source='\n'.join(lines)+'\n'+original.decode('utf8')
 (out/'cases.json').write_text(json.dumps([{k:v for k,v in c.items() if k!='blob'} for c in cases],indent=2),encoding='utf8')
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
