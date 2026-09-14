#!/usr/bin/env python3
"""Compile, execute, decode and mutate the isolated typed-IR V3D lowerer."""

from __future__ import annotations
import argparse, importlib.util, os, pathlib, subprocess, sys, tempfile

HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
MODULE=ROOT/'Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4'
GATE=ROOT/'Anvil/Graphics/Vulkan/Tests/vulkan_ir_v3d42_gate.pi4'
LOAD=0x400000; STACK=0x3000000; LR=0xDEAD0000; MMIO=0xFC000000
MAGIC=0x49523432; STEP_LIMIT=40_000_000

sys.path.insert(0,str(HERE))
from v3d42_qpu_decode import ProgramContract, decode_program, verify_program

MUTANTS=(
 ('refusal writes caller code','i = 0 : While i < codeBytes : PokeA(*t\\codeBase + i, PeekA(@avk42CodeScratch[0] + i))','i = 0 : While i < codeBytes : PokeA(*t\\codeBase + i, 0)'),
 ('role mismatch accepted','If (*m\\stage = #ANVIL_IR_STAGE_VERTEX) <> Bool(*t\\role = #ANVIL_IR_V3D42_ROLE_VERTEX)','If (*m\\stage = #ANVIL_IR_STAGE_VERTEX) = 2'),
 ('duplicate IO accepted','If *other\\variableId = *io\\variableId','If *other\\variableId = 0'),
 ('slot overlap accepted','If *io\\firstSlot < (*other\\firstSlot + *other\\components) And *other\\firstSlot < (*io\\firstSlot + *io\\components)','If *io\\firstSlot < 0 And *other\\firstSlot < (*io\\firstSlot + *io\\components)'),
 ('code alignment weakened','(*t\\codeBase & 7) <> 0','(*t\\codeBase & 3) <> 0'),
 ('32-bit texture pointer widened','*t\\textureStateAddress > $FFFFFFFF','*t\\textureStateAddress < 0'),
 ('TMUT/TMUS reversed','#V3DQ_WADDR_TMUT, 1','#V3DQ_WADDR_TMUS, 1'),
 ('TLBU/TLB reversed','#V3DQ_WADDR_TLBU, 1','#V3DQ_WADDR_TLB, 1'),
 ('VPM wait omitted','If rc = 0 : rc = V3dQpuAdd0(#V3DQ_A_VPMWT, #V3DQ_WADDR_NOP, 1) : EndIf','If rc = 0 : rc = V3dQpuNop() : EndIf'),
 ('relaxed precision accepted','If *d\\kind = #ANVIL_IR_DEC_RELAXED_PRECISION','If *d\\kind = 99'),
)

def locate(explicit,env,fallback):
 p=pathlib.Path(explicit) if explicit else pathlib.Path(os.environ[env]) if os.environ.get(env) else fallback
 if not p.is_file(): raise SystemExit(f'{env} not found: {p}')
 return p.resolve()
def loadmod(name,path):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def build(compiler,suffix):
 d=pathlib.Path(tempfile.mkdtemp(prefix='anvil_ir42_')); out=d/f'{suffix}.img'
 cmd=[str(compiler),'--compile',GATE.relative_to(ROOT).as_posix(),'-t','pi4','--load-addr',hex(LOAD),'-s','--stack-addr',hex(STACK),'--entry-returns','-o',str(out)]
 env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
 p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if p.returncode or 'pmfc: OK' not in p.stdout or not out.is_file(): raise SystemExit('IR V3D42 compile failed\n'+p.stdout)
 return out
def execute(a64,img):
 c=a64.A64();c.memory.update({LOAD+i:b for i,b in enumerate(img.read_bytes())});a64.attach_symbols(c,img,LOAD);c.pc=LOAD;c.sp=STACK;c.x[30]=LR
 def ld(a,n):
  c.align_guard(a,n,False)
  if a>=MMIO: raise SystemExit(f'IR V3D42 unexpected MMIO read {a:#x}')
  return sum(c.memory.get(a+i,0)<<(8*i) for i in range(n))
 def st(a,v,n):
  c.align_guard(a,n,True)
  if a>=MMIO: raise SystemExit(f'IR V3D42 unexpected MMIO write {a:#x}')
  for i in range(n): c.memory[a+i]=(v>>(8*i))&255
 c.load=ld;c.store=st
 for steps in range(STEP_LIMIT):
  if c.pc==LR:return c,c.x[0],steps
  c.step()
 raise SystemExit('IR V3D42 fixture timeout')
def q(c,a): return sum(c.memory.get(a+i,0)<<(8*i) for i in range(8))
def blob(c,a,n): return bytes(c.memory.get(a+i,0) for i in range(n))
def grade(c,r):
 bad=[]
 if q(c,r+200*8)!=MAGIC:return 0,['bad report magic']
 checks=q(c,r+201*8); fails=q(c,r+202*8)
 if fails: bad.append(f'{fails} of {checks} emitted checks failed: '+','.join(str(i+1) for i in range(checks) if q(c,r+(64+i)*8)==0))
 roles=('vertex','fragment:varying','fragment:flat','fragment:uniform','fragment:sampled','vertex')
 words=0
 for i,role in enumerate(roles):
  b=i*8;rc=q(c,r+b*8);addr=q(c,r+(b+1)*8);size=q(c,r+(b+2)*8);un=q(c,r+(b+4)*8)
  if rc or not size: bad.append(f'case {i} did not lower: rc={rc} bytes={size}');continue
  try: ins=verify_program(blob(c,addr,size),ProgramContract(f'ir42/{i}',role,un));words+=len(ins)
  except Exception as e: bad.append(f'case {i} decoder: {e}')
 return checks,bad+[f'__WORDS__={words}']
def sourcecheck(text):
 need=('AnvilVkIrVerify(*m)','@avk42CodeScratch[0]','avk42RangesOverlap(','#ANVIL_IR_V3D42_TMU_VEC4','V3dQpuLastThrsw()','V3dQpuProgramEnd()','#ANVIL_IR_DEC_RELAXED_PRECISION','If *other\\variableId = *io\\variableId')
 return [f'missing {x}' for x in need if x not in text]
def runone(compiler,a64,suffix):
 c,r,steps=execute(a64,build(compiler,suffix));checks,items=grade(c,r);words=int(items[-1].split('=')[1]);return checks,words,steps,items[:-1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler');ap.add_argument('--interp');ap.add_argument('--mutate',action='store_true');a=ap.parse_args()
 compiler=locate(a.compiler,'PMF_COMPILER',pathlib.Path(r'C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe'))
 interp=locate(a.interp,'PMF_A64_INTERP',ROOT/'tools/a64/a64_interp.py');a64=loadmod('ir42_a64',interp)
 original=MODULE.read_text(encoding='utf-8');bad=sourcecheck(original)
 if bad:
  print('vulkan_ir_v3d42_check: FAIL');print('\n'.join('  '+x for x in bad));return 1
 checks,words,steps,bad=runone(compiler,a64,'base')
 if bad:
  print('vulkan_ir_v3d42_check: FAIL');print('\n'.join('  '+x for x in bad));return 1
 print(f'vulkan_ir_v3d42_check: PASS - {checks} emitted checks, {words} independently decoded QPU words, {steps:,} A64 instructions')
 if not a.mutate:return 0
 missed=0
 for name,old,new in MUTANTS:
  if original.count(old)!=1: print(f'  STALE {name} ({original.count(old)})');missed+=1;continue
  MODULE.write_text(original.replace(old,new,1),encoding='utf-8')
  try:
   static_red=sourcecheck(MODULE.read_text(encoding='utf-8'))
   if static_red:caught=True;detail=static_red[0]
   else:_,_,_,red=runone(compiler,a64,'mutant');caught=bool(red);detail=red[0] if red else ''
  except (SystemExit,Exception) as e:caught=True;detail=str(e).splitlines()[0]
  finally:MODULE.write_text(original,encoding='utf-8')
  print(f"  {'RED' if caught else 'GREEN'} {name}"+(f' - {detail[:110]}' if detail else ''))
  if not caught:missed+=1
 if missed:print(f'vulkan_ir_v3d42_check: FAIL - {missed} mutants escaped');return 1
 print(f'vulkan_ir_v3d42_check: all {len(MUTANTS)} mutations rejected');return 0
if __name__=='__main__':raise SystemExit(main())
