#!/usr/bin/env python3
"""Compile, execute, decode and mutate the isolated typed-IR V3D lowerer."""

from __future__ import annotations
import argparse, contextlib, importlib.util, os, pathlib, subprocess, sys, tempfile

HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
MODULE=ROOT/'Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4'
GATE=ROOT/'Anvil/Graphics/Vulkan/Tests/vulkan_ir_v3d42_gate.pi4'
LOAD=0x400000; STACK=0x3000000; LR=0xDEAD0000; MMIO=0xFC000000
MAGIC=0x49523432; STEP_LIMIT=40_000_000

sys.path.insert(0,str(HERE))
from v3d42_qpu_decode import ProgramContract, decode_program, verify_program, uniform_consumption

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
 ('FAdd replaced by integer OR','V3dQpuAdd2(#V3DQ_A_FADD, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B','V3dQpuAdd2(#V3DQ_A_OR, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B'),
 ('FMul replaced by SMul24','V3dQpuMul(#V3DQ_M_FMUL, first + k','V3dQpuMul(#V3DQ_M_SMUL24, first + k'),
 ('FAdd destination made magic','V3dQpuAdd2(#V3DQ_A_FADD, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B','V3dQpuAdd2(#V3DQ_A_FADD, first + k, 1, #V3DQ_MUX_A, #V3DQ_MUX_B'),
 ('FAdd mux A replaced by mux B','V3dQpuAdd2(#V3DQ_A_FADD, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B','V3dQpuAdd2(#V3DQ_A_FADD, first + k, 0, #V3DQ_MUX_B, #V3DQ_MUX_B'),
 ('FMul destination made magic','V3dQpuMul(#V3DQ_M_FMUL, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B)','V3dQpuMul(#V3DQ_M_FMUL, first + k, 1, #V3DQ_MUX_A, #V3DQ_MUX_B)'),
 ('FMul mux A replaced by mux B','V3dQpuMul(#V3DQ_M_FMUL, first + k, 0, #V3DQ_MUX_A, #V3DQ_MUX_B)','V3dQpuMul(#V3DQ_M_FMUL, first + k, 0, #V3DQ_MUX_B, #V3DQ_MUX_B)'),
 ('LDVPM input slot shifted','V3dQpuLdvpm(#V3DQ_A_LDVPMV_IN, reg, #V3DQ_MUX_A, slot)','V3dQpuLdvpm(#V3DQ_A_LDVPMV_IN, reg, #V3DQ_MUX_A, slot + 1)'),
 ('STVPM output slot shifted','V3dQpuStvpm(#V3DQ_A_STVPMV, #V3DQ_MUX_A, #V3DQ_MUX_B, slot, reg)','V3dQpuStvpm(#V3DQ_A_STVPMV, #V3DQ_MUX_A, #V3DQ_MUX_B, slot + 1, reg)'),
 ('constant uniform word changed','avk42AppendUniform(*c\\word0)','avk42AppendUniform(*c\\word0 + 1)'),
 ('constant load register shifted','V3dQpuNopSig(#V3DQ_SIG_LDUNIFRF, first, 0)','V3dQpuNopSig(#V3DQ_SIG_LDUNIFRF, first + 1, 0)'),
 ('dead SSA resource emitted','If *n\\sourceId > 0 And avk42Live[*n\\sourceId] = 0','If *n\\sourceId > 0 And avk42Live[*n\\sourceId] < 0'),
 ('duplicate varying load consumes FIFO twice','If priorId > 0','If priorId < 0'),
 ('nonzero block member accepted','If *v = 0 Or member <> 0','If *v = 0 Or member = 12345'),
 ('missing Block decoration accepted','If avk42Decoration(*m, *block\\sourceId, -1, #ANVIL_IR_DEC_BLOCK) < 0','If avk42Decoration(*m, *block\\sourceId, -1, #ANVIL_IR_DEC_BLOCK) < -1'),
 ('missing or nonzero member Offset accepted','If avk42Decoration(*m, *block\\sourceId, 0, #ANVIL_IR_DEC_OFFSET) <> 0','If avk42Decoration(*m, *block\\sourceId, 0, #ANVIL_IR_DEC_OFFSET) = 12345'),
 ('integer block scalar accepted','*scalar\\kind <> #ANVIL_IR_TYPE_FLOAT','*scalar\\kind = 12345'),
 ('two live push loads accepted','If pushLoads > 1','If pushLoads > 2'),
 ('two live UBO loads accepted','If uniformLoads > 1','If uniformLoads > 2'),
 ('two live samples accepted','If liveSamples > 1','If liveSamples > 2'),
 ('fixed TMU register reservation removed',
  '  If liveSamples > 0\n    avk42NextReg = 14       ; sample rf0..3 and UV rf12..13\n  ElseIf uniformLoads > 0\n    avk42NextReg = 9        ; UBO result rf0..3 and address rf8',
  '  If liveSamples > 0\n    avk42NextReg = 4        ; sample rf0..3 and UV rf12..13\n  ElseIf uniformLoads > 0\n    avk42NextReg = 4        ; UBO result rf0..3 and address rf8'),
 ('sample plus UBO result aliases rf0',
  '    first = 0\n    If avk42HasSample <> 0\n      ; A sample result owns rf0..3.',
  '    first = 0\n    If avk42HasSample = 0\n      ; A sample result owns rf0..3.'),
 ('sample result moved off rf0',
  '  first = 0\n  If avk42NextReg < 14 : avk42NextReg = 14 : EndIf',
  '  first = 4\n  If avk42NextReg < 14 : avk42NextReg = 14 : EndIf'),
 ('push R metadata aliases G','If k = 0 : *r\\pushRWord = pos : EndIf','If k = 0 : *r\\pushGWord = pos : EndIf'),
 ('UBO address metadata aliases config','*r\\uniformAddressWord = avk42AppendUniform(*t\\uniformBlockAddress)','*r\\uniformConfigWord = avk42AppendUniform(*t\\uniformBlockAddress)'),
 ('texture metadata aliases sampler','*r\\textureStateWord = avk42AppendUniform(*t\\textureStateAddress)','*r\\samplerStateWord = avk42AppendUniform(*t\\textureStateAddress)'),
 ('prepare publishes metadata before transaction commits','avk42PrepareAndEmit(*m, *t, @avk42PendingResult)','avk42PrepareAndEmit(*m, *t, *r)'),
 ('resource validation reads caller result','avk42ValidateResourceUse(*m, *t, @avk42PendingResult)','avk42ValidateResourceUse(*m, *t, *r)'),
)

def locate(explicit,env,fallback):
 p=pathlib.Path(explicit) if explicit else pathlib.Path(os.environ[env]) if os.environ.get(env) else fallback
 if not p.is_file(): raise SystemExit(f'{env} not found: {p}')
 return p.resolve()
def loadmod(name,path):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
@contextlib.contextmanager
def checker_lock():
 p=pathlib.Path(tempfile.gettempdir())/'anvil_vk_pipeline_check.lock'
 with p.open('a+b') as f:
  f.seek(0,os.SEEK_END)
  if f.tell()==0:f.write(b'0');f.flush()
  f.seek(0)
  if os.name=='nt':
   import msvcrt
   msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
   try:yield
   finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
  else:
   import fcntl
   fcntl.flock(f.fileno(),fcntl.LOCK_EX)
   try:yield
   finally:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
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
def u32(c,a): return sum(c.memory.get(a+i,0)<<(8*i) for i in range(4))
def blob(c,a,n): return bytes(c.memory.get(a+i,0) for i in range(n))
def grade(c,r):
 bad=[]
 if q(c,r+1000*8)!=MAGIC:return 0,['bad report magic']
 checks=q(c,r+1001*8); fails=q(c,r+1002*8)
 if fails: bad.append(f'{fails} of {checks} emitted checks failed: '+','.join(str(i+1) for i in range(checks) if q(c,r+(256+i)*8)==0))
 roles=(('vertex','fragment:varying','fragment:flat','fragment:uniform','fragment:sampled','vertex')
        +('vertex',)*12+('fragment:flat','fragment:uniform','fragment:sampled','fragment:varying'))
 words=0
 for i,role in enumerate(roles):
  b=i*8;rc=q(c,r+b*8);addr=q(c,r+(b+1)*8);size=q(c,r+(b+2)*8);un=q(c,r+(b+4)*8)
  if rc or not size:
   eb=900+i*3
   bad.append(f'case {i} did not lower: rc={rc} bytes={size} source={q(c,r+eb*8)} opcode={q(c,r+(eb+1)*8)} stage={q(c,r+(eb+2)*8)}');continue
  try:
    if 14<=i<18:
     # These constants intentionally retain a dead input Load in IR, but the
     # Store-root executable has no attribute read. Decode the exact program
     # below without imposing the generic vertex "must LDVPM" contract.
     ins=verify_program(blob(c,addr,size),ProgramContract(f'ir42/{i}','vertex',un,requires_vpm_load=False))
    else:ins=verify_program(blob(c,addr,size),ProgramContract(f'ir42/{i}',role,un))
    words+=len(ins)
    if 6<=i<18:
     is_const=i>=14
     lanes=(1 if i<16 else 4) if is_const else (i-6)//2+1
     is_add=((i-6)&1)==0
     ar=[x for x in ins if x.add_op=='fadd/faddnf'] if is_add else [x for x in ins if x.mul_op=='fmul']
     if len(ar)!=lanes:raise ValueError(f'ir42/{i}: expected {lanes} arithmetic words, got {len(ar)}')
     dest=[x.add_waddr if is_add else x.mul_waddr for x in ar]
     if dest!=list(range(2*lanes,3*lanes)):raise ValueError(f'ir42/{i}: arithmetic destinations {dest}')
     if any(x.raddr_a!=lane or x.raddr_b!=lanes+lane for lane,x in enumerate(ar)):raise ValueError(f'ir42/{i}: arithmetic operand order is not exact')
     if is_add and any(((x.word>>24)&255)!=5 or x.add_magic or x.add_mux_a!=6 or x.add_mux_b!=7 for x in ar):raise ValueError(f'ir42/{i}: FAdd encoding is not exact')
     if not is_add and any(((x.word>>58)&63)!=21 or x.mul_magic or x.mul_mux_a!=6 or x.mul_mux_b!=7 for x in ar):raise ValueError(f'ir42/{i}: FMul encoding is not exact')
     constant_loads=[x for x in ins if 'ldunifrf' in x.signals]
     if is_const:
      if [x.index for x in constant_loads]!=list(range(2*lanes)):raise ValueError(f'ir42/{i}: constant loads are not the first contiguous phase')
      if [x.signal_addr for x in constant_loads]!=list(range(2*lanes)):raise ValueError(f'ir42/{i}: constant load registers are not exact')
      expected=[0x3fc00000,0x3f000000] if lanes==1 else [0x3f800000,0x40000000,0x40800000,0x41000000,0x3f000000,0x3e800000,0x3e000000,0x3d800000]
      actual=[u32(c,q(c,r+(b+3)*8)+(4*k)) for k in range(un)]
      if actual!=expected:raise ValueError(f'ir42/{i}: uniform words {actual!r}')
     elif constant_loads:raise ValueError(f'ir42/{i}: unexpected constant uniform loads')
     ar_start=2*lanes
     if [x.index for x in ar]!=list(range(ar_start,ar_start+lanes)):raise ValueError(f'ir42/{i}: arithmetic is not the third contiguous phase')
     ld=[x for x in ins if x.add_op=='ldvpmv_in']
     if len(ld)!=(0 if is_const else 2*lanes):raise ValueError(f'ir42/{i}: wrong LDVPM lane count')
     ld_start=3*lanes if is_const else 0
     if [x.index for x in ld]!=list(range(ld_start,ld_start+len(ld))):raise ValueError(f'ir42/{i}: LDVPM phase is not contiguous/in order')
     if any(x.add_waddr!=(3*lanes+lane if is_const else lane) or x.add_magic or x.add_mux_a!=6 or x.add_mux_b!=0 or x.raddr_a!=lane for lane,x in enumerate(ld)):raise ValueError(f'ir42/{i}: LDVPM destination/slot order is not exact')
     st=[x for x in ins if x.add_op=='stvpmv']
     st_start=3*lanes if is_const else 3*lanes
     if [x.index for x in st]!=list(range(st_start,st_start+lanes)):raise ValueError(f'ir42/{i}: STVPM phase is not contiguous/in order')
     if any(x.add_waddr!=0 or x.add_magic or x.add_mux_a!=6 or x.add_mux_b!=7 or x.raddr_a!=lane or x.raddr_b!=2*lanes+lane for lane,x in enumerate(st)):raise ValueError(f'ir42/{i}: STVPM source/slot order is not exact')
     waits=[x for x in ins if x.add_op=='vpmwt']
     wait_index=4*lanes if is_const else 4*lanes
     if len(waits)!=1 or waits[0].index!=wait_index:raise ValueError(f'ir42/{i}: VPM wait does not follow the final store')
  except Exception as e: bad.append(f'case {i} decoder: {e}')
 # Resource-combination programs use valid fragment mechanics but deliberately
 # exceed the old single-family decoder roles. Decode their exact physical
 # register and uniform metadata contracts directly.
 for i in range(22,30):
  b=i*8;rc=q(c,r+b*8);addr=q(c,r+(b+1)*8);size=q(c,r+(b+2)*8);un=q(c,r+(b+4)*8)
  if rc or not size:
   eb=900+i*3
   bad.append(f'case {i} mixed resources did not lower: rc={rc} bytes={size} source={q(c,r+eb*8)} opcode={q(c,r+(eb+1)*8)} stage={q(c,r+(eb+2)*8)}');continue
  try:
   ins=decode_program(blob(c,addr,size));words+=len(ins)
   if sum(uniform_consumption(x) for x in ins)!=un:raise ValueError('uniform consumption does not match returned word count')
   mb=600+i*10
   meta=[q(c,r+(mb+k)*8) for k in range(10)]
   meta=[x-(1<<64) if x&(1<<63) else x for x in meta]
   push=i in (22,23,24,25,28,29);ubo=i in (22,23,26,27,28,29);sample=i in (24,25,26,27,28,29)
   present=[meta[9]]
   if push:
    if meta[0]!=min(meta[1:5]):raise ValueError(f'pushFirst does not identify first semantic push word: {meta[:5]}')
    if meta[0]<0 or meta[0]>=un:raise ValueError(f'pushFirst out of range: {meta[0]}, words={un}')
    present+=meta[1:5]
   elif any(x!=-1 for x in meta[:5]):raise ValueError(f'unused push metadata {meta[:5]}')
   if ubo: present+=meta[5:7]
   elif any(x!=-1 for x in meta[5:7]):raise ValueError(f'unused UBO metadata {meta[5:7]}')
   if sample: present+=meta[7:9]
   elif any(x!=-1 for x in meta[7:9]):raise ValueError(f'unused sample metadata {meta[7:9]}')
   if any(x<0 or x>=un for x in present) or len(set(present))!=len(present):raise ValueError(f'indices not unique/in range: {meta}, words={un}')
   if sorted(present)!=list(range(un)):raise ValueError(f'metadata does not cover exact stream: {present}, words={un}')
   stream=q(c,r+(b+3)*8)
   if push:
    expected=(0x3f800000,0x40000000,0x40400000,0x3f800000)
    for pos,value in zip(meta[1:5],expected):
     if u32(c,stream+4*pos)!=value:raise ValueError(f'push semantic word {pos} is {u32(c,stream+4*pos):#x}, expected {value:#x}')
   if ubo:
    if u32(c,stream+4*meta[5])!=0x00102000:raise ValueError('UBO address metadata does not name the supplied address')
    if u32(c,stream+4*meta[6])!=0xffffff7c:raise ValueError('UBO config metadata does not name vec4 configuration')
   if sample:
    if u32(c,stream+4*meta[7])!=0x00200000:raise ValueError('texture metadata does not name supplied state')
    if u32(c,stream+4*meta[8])!=0x00200100:raise ValueError('sampler metadata does not name supplied state')
   if u32(c,stream+4*meta[9])!=0xffffffff:raise ValueError('TLB metadata does not name exact configuration')
   rb=400+i*5
   preg,ureg,sreg,areg0,areg1=[q(c,r+(rb+k)*8) for k in range(5)]
   regs=[]
   if push:regs.append(('push',preg))
   if ubo:regs.append(('ubo',ureg))
   if sample:regs.append(('sample',sreg))
   for ai,(name0,r0),(name1,r1) in [(areg0,regs[0],regs[1])]:
    ar=[x for x in ins if x.add_op=='fadd/faddnf' and x.add_waddr in range(ai,ai+4)]
    if len(ar)!=4 or any(x.raddr_a!=r0+k or x.raddr_b!=r1+k for k,x in enumerate(ar)):
     raise ValueError(f'first arithmetic aliases/reorders {name0}/{name1}: regs={regs}, dest={ai}')
   if len(regs)==3:
    ar=[x for x in ins if x.add_op=='fadd/faddnf' and x.add_waddr in range(areg1,areg1+4)]
    if len(ar)!=4 or any(x.raddr_a!=areg0+k or x.raddr_b!=regs[2][1]+k for k,x in enumerate(ar)):
     raise ValueError(f'second arithmetic aliases/reorders prior/{regs[2][0]}')
   ranges=[set(range(v,v+4)) for _,v in regs]
   if any(ranges[a]&ranges[b] for a in range(len(ranges)) for b in range(a+1,len(ranges))):raise ValueError(f'resource register alias {regs}')
   if sample and sreg!=0:raise ValueError(f'sample result is not rf0..3: {sreg}')
   if sample and push and preg<14:raise ValueError(f'sample+push result overlaps reserved sample/UV registers: {preg}')
   if sample and ubo and ureg<14:raise ValueError(f'sample+UBO result not disjoint/reserved: {ureg}')
   if i==28 and meta!=[2,2,3,4,5,6,7,0,1,8]:raise ValueError(f'triple canonical metadata {meta}')
  except Exception as e:bad.append(f'case {i} mixed decoder: {e}')
 # Duplicate live input loads must consume one four-lane varying FIFO value
 # and both SSA IDs must map to the same semantic registers.
 try:
  b=21*8;ins=decode_program(blob(c,q(c,r+(b+1)*8),q(c,r+(b+2)*8)))
  varying=[x.signal_addr for x in ins if 'ldvary' in x.signals]
  if varying!=[0,1,2,3]:raise ValueError(f'varying FIFO consumed {varying}')
  first=[q(c,r+(550+k)*8) for k in range(4)]
  second=[q(c,r+(554+k)*8) for k in range(4)]
  if first!=[0,1,2,3] or second!=first:raise ValueError(f'duplicate SSA lane mappings differ: {first} vs {second}')
 except Exception as e:bad.append(f'case 21 duplicate-input decoder: {e}')
 return checks,bad+[f'__WORDS__={words}']
def sourcecheck(text):
 need=('AnvilVkIrVerify(*m)','@avk42CodeScratch[0]','avk42RangesOverlap(','#ANVIL_IR_V3D42_TMU_VEC4','V3dQpuLastThrsw()','V3dQpuProgramEnd()','#ANVIL_IR_DEC_RELAXED_PRECISION','If *other\\variableId = *io\\variableId','#ANVIL_IR_OP_FADD','#ANVIL_IR_OP_FMUL')
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
if __name__=='__main__':
 with checker_lock():raise SystemExit(main())
