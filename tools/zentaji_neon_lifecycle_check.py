"""Native CPU proof of shared lifecycle routing/capacities; controlled providers, no GPU proof."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Anvil/Graphics/Vulkan/Tests/neon_vk_lifecycle_binder_gate.pbi"
Global Dim report.q[8]
Procedure.i Main()
 Protected rc.i=NeonVkLifecycleBinderGate()
 report[0]=fakeCreateCount : report[1]=fakeDestroyCount
 report[2]=fakeCapacityCreates : report[3]=fakeDrawBudget : report[4]=fakeVertexBudget
 report[5]=binderNativeCalls : report[6]=NeonVkLifecycleConfigured() : report[7]=nvlMaxVertexQuads
 If rc<>0 : ProcedureReturn rc+100 : EndIf
 ProcedureReturn 42
EndProcedure
'''
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keep',type=Path)
 a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A,zexpack
 def run(argv):
  p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
  assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
  return p.stdout
 with tempfile.TemporaryDirectory(prefix='zen-lifecycle-') as tmp:
  td=a.keep.resolve() if a.keep else Path(tmp);td.mkdir(parents=True,exist_ok=True)
  src=td/'binder.zentaji';image=td/'binder.zex';src.write_text(SOURCE)
  (td/'build.log').write_text(run([cc,'--compile',src,'-o',image]))
  mapping=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig'));assert mapping['image']==hashlib.sha256(image.read_bytes()).hexdigest()
  ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
  assert image.read_bytes()==zexpack.header(origin,origin,data)+data
  m=F.Fixture(ram_size=32<<20);m.load_image(image.read_bytes());m.write(td)
  out=run([zt/'zenemu.exe',td/'machine.txt','--max','1000000','--ram',td/'final.bin']);(td/'native.log').write_text(out)
  ram=(td/'final.bin').read_bytes();report=struct.unpack_from('<8q',ram,ref.sym['GLOBAL_REPORT'])
  end=next(s for s in out.splitlines() if s.startswith('END '))
  assert ' exit=2A ' in end and report==(4,4,1,256,12000,0,0,0),(end,report)
 print('PASS native shared lifecycle CPU contract: legacy/custom budgets, 256 draws/12000 vertex quads, failed init/cleanup ownership, callback routing, negative refusal and reset to legacy; controlled provider only, no GPU execution claimed')
if __name__=='__main__':main()
