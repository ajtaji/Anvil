#!/usr/bin/env python3
"""Compile, execute, decode and mutate the isolated typed-IR V3D lowerer."""

from __future__ import annotations
import argparse, contextlib, hashlib, importlib.util, os, pathlib, shutil, subprocess, sys, tempfile

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
 ('sample fixed-register reservation removed',
  '    avk42NextReg = 14       ; sample rf0..3 and UV rf12..13',
  '    avk42NextReg = 4        ; sample rf0..3 and UV rf12..13'),
 ('UBO fixed-register reservation removed',
  '    avk42NextReg = 9        ; UBO result rf0..3 and address rf8',
  '    avk42NextReg = 4        ; UBO result rf0..3 and address rf8'),
 ('sample plus UBO result aliases rf0',
  '    first = 0\n    If avk42HasSample <> 0\n      ; A sample result owns rf0..3.',
  '    first = 0\n    If avk42HasSample = 0\n      ; A sample result owns rf0..3.'),
 ('sample result moved off rf0',
  '  first = 0\n  If avk42NextReg < 14 : avk42NextReg = 14 : EndIf',
  '  first = 4\n  If avk42NextReg < 14 : avk42NextReg = 14 : EndIf'),
 ('push R metadata aliases G','If k = 0 : *r\\pushRWord = pos : EndIf','If k = 0 : *r\\pushGWord = pos : EndIf'),
 ('UBO address metadata aliases config','*r\\uniformAddressWord = avk42AppendUniform(*t\\uniformBlockAddress)','*r\\uniformConfigWord = avk42AppendUniform(*t\\uniformBlockAddress)'),
 ('texture metadata aliases sampler','*r\\textureStateWord = avk42AppendUniform(*t\\textureStateAddress)','*r\\samplerStateWord = avk42AppendUniform(*t\\textureStateAddress)'),
 ('TLB metadata aliases sampler','*r\\tlbConfigWord = avk42AppendUniform(*t\\tlbConfig)','*r\\samplerStateWord = avk42AppendUniform(*t\\tlbConfig)'),
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
def sha256_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def remove_private_tree(path):
 if path.exists():shutil.rmtree(path)
 if path.exists():raise RuntimeError(f'private gate tree did not clean up: {path}')
def manifest_hash(root):
 h=hashlib.sha256()
 for path in sorted((p for p in root.rglob('*') if p.is_file()),key=lambda p:p.relative_to(root).as_posix()):
  rel=path.relative_to(root).as_posix().encode('utf-8');digest=hashlib.sha256(path.read_bytes()).digest()
  h.update(len(rel).to_bytes(4,'little'));h.update(rel);h.update(digest)
 return h.hexdigest()
def freeze_build_inputs():
 snapshot=pathlib.Path(tempfile.mkdtemp(prefix='anvil_ir42_snapshot_'))
 try:
  vulkan=snapshot/'Anvil/Graphics/Vulkan';tests=vulkan/'Tests';lib=snapshot/'RaspberryPi4/Lib'
  tests.mkdir(parents=True);lib.mkdir(parents=True)
  shutil.copy2(GATE,tests/GATE.name)
  shutil.copy2(MODULE,vulkan/MODULE.name)
  shutil.copy2(ROOT/'Anvil/Graphics/Vulkan/vk_ir.pbi',vulkan/'vk_ir.pbi')
  shutil.copy2(ROOT/'RaspberryPi4/Lib/v3dqpu.pi4',lib/'v3dqpu.pi4')
  shutil.copytree(ROOT/'RaspberryPi4/Intrinsics',snapshot/'RaspberryPi4/Intrinsics')
  shutil.copytree(ROOT/'Boards',snapshot/'Boards')
  shutil.copy2(ROOT/'keywords.def',snapshot/'keywords.def')
  return snapshot,manifest_hash(snapshot)
 except BaseException:
  remove_private_tree(snapshot)
  raise
def build(compiler,suffix,snapshot,snapshot_hash,compiler_hash,module_bytes=None,runner=subprocess.run,compile_timeout=300):
 # Mutants are complete private build roots.  Never rewrite a production
 # source file: an interrupted compiler or checker can only strand its temp
 # copy, while the shared tree remains byte-for-byte untouched.
 if manifest_hash(snapshot)!=snapshot_hash:raise SystemExit('IR V3D42 frozen input snapshot changed before compile')
 if sha256_file(compiler)!=compiler_hash:raise SystemExit('IR V3D42 compiler changed before compile')
 work=pathlib.Path(tempfile.mkdtemp(prefix='anvil_ir42_'))
 try:
  shutil.copytree(snapshot,work,dirs_exist_ok=True)
  vulkan=work/'Anvil/Graphics/Vulkan';tests=vulkan/'Tests'
  if module_bytes is not None:(vulkan/MODULE.name).write_bytes(module_bytes)
  out=work/f'{suffix}.img'
  cmd=[str(compiler),'--compile',(tests/GATE.name).relative_to(work).as_posix(),'-t','pi4','--load-addr',hex(LOAD),'-s','--stack-addr',hex(STACK),'--entry-returns','-o',str(out)]
  env=os.environ.copy();env['PMF_ROOT']=str(work)
  p=runner(cmd,cwd=work,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=compile_timeout)
  if sha256_file(compiler)!=compiler_hash:raise RuntimeError('IR V3D42 compiler changed during compile')
  if manifest_hash(snapshot)!=snapshot_hash:raise RuntimeError('IR V3D42 frozen input snapshot changed during compile')
  if p.returncode or 'pmfc: OK' not in p.stdout or not out.is_file():raise RuntimeError('IR V3D42 compile failed\n'+p.stdout)
  return out,work
 except BaseException:
  remove_private_tree(work)
  raise
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
def grade_late_resource_spans(c,r):
 bad=[];words=0
 try:
  i=30;b=i*8;rc=q(c,r+b*8);addr=q(c,r+(b+1)*8);size=q(c,r+(b+2)*8);un=q(c,r+(b+4)*8)
  if rc or not size:raise ValueError(f'did not lower: rc={rc} bytes={size}')
  ins=decode_program(blob(c,addr,size));words+=len(ins)
  if sum(uniform_consumption(x) for x in ins)!=un or un!=11:raise ValueError(f'uniform consumption/count {un}')
  const0,const1,producer,sample,consumer=[q(c,r+(760+k)*8) for k in range(5)]
  if set(range(producer,producer+4)) & {12,13}:raise ValueError(f'live producer aliases sample UV rf12/rf13: rf{producer}..rf{producer+3}')
  if [const0,const1,producer,sample,consumer]!=[14,18,22,0,26]:raise ValueError(f'published register map {[const0,const1,producer,sample,consumer]}')
  first=[x for x in ins if x.add_op=='fadd/faddnf' and producer<=x.add_waddr<producer+4]
  if len(first)!=4 or any(x.add_magic or x.raddr_a!=const0+k or x.raddr_b!=const1+k for k,x in enumerate(first)):raise ValueError('pre-sample FAdd does not preserve both constant operands')
  uv=[x for x in ins if x.add_op=='fadd/faddnf' and x.add_waddr in (12,13)]
  if len(uv)!=2 or [x.add_waddr for x in uv]!=[12,13] or any(x.add_magic or x.add_mux_a!=5 or x.add_mux_b!=6 or x.raddr_a!=(10+k) or x.raddr_b!=0 for k,x in enumerate(uv)):raise ValueError('sample UV correction does not map R5 plus rf10/rf11 into rf12/rf13 exactly')
  request=[x for x in ins if x.add_op=='or' and x.add_magic and x.add_waddr in (34,33)]
  if len(request)!=2 or [(x.add_waddr,x.raddr_a) for x in request]!=[(34,13),(33,12)]:raise ValueError('TMUT/TMUS do not consume corrected rf13/rf12')
  loads=[x for x in ins if 'ldtmu' in x.signals]
  if len(loads)!=4 or any(x.signal_magic for x in loads) or [x.signal_addr for x in loads]!=[0,1,2,3]:raise ValueError('sample result does not load exactly nonmagic rf0..rf3')
  final=[x for x in ins if x.add_op=='fadd/faddnf' and consumer<=x.add_waddr<consumer+4]
  if len(final)!=4 or any(x.add_magic or x.raddr_a!=producer+k or x.raddr_b!=sample+k for k,x in enumerate(final)):raise ValueError('post-sample FAdd does not consume the live producer and sampled value')
  if not (max(x.index for x in first)<min(x.index for x in uv) and max(x.index for x in uv)<min(x.index for x in request) and max(x.index for x in request)<min(x.index for x in loads) and max(x.index for x in loads)<min(x.index for x in final)):raise ValueError('producer/UV/request/load/consumer order is not exact')
 except Exception as e:bad.append(f'case 30 late-sample decoder: {e}')
 try:
  i=31;b=i*8;rc=q(c,r+b*8);addr=q(c,r+(b+1)*8);size=q(c,r+(b+2)*8);un=q(c,r+(b+4)*8)
  if rc or not size:raise ValueError(f'did not lower: rc={rc} bytes={size}')
  ins=decode_program(blob(c,addr,size));words+=len(ins)
  if sum(uniform_consumption(x) for x in ins)!=un or un!=7:raise ValueError(f'uniform consumption/count {un}')
  const0,producer,ubo,consumer=[q(c,r+(770+k)*8) for k in range(4)]
  if 8 in range(producer,producer+4):raise ValueError(f'live producer aliases UBO address rf8: rf{producer}..rf{producer+3}')
  if [const0,producer,ubo,consumer]!=[9,13,0,17]:raise ValueError(f'published register map {[const0,producer,ubo,consumer]}')
  first=[x for x in ins if x.add_op=='fadd/faddnf' and producer<=x.add_waddr<producer+4]
  if len(first)!=4 or any(x.add_magic or x.raddr_a!=const0+k or x.raddr_b!=const0+k for k,x in enumerate(first)):raise ValueError('pre-UBO FAdd does not consume the constant twice exactly')
  address=[x for x in ins if 'ldunifrf' in x.signals and not x.signal_magic and x.signal_addr==8]
  if len(address)!=1:raise ValueError(f'expected one UBO address LDUNIFRF rf8, got {len(address)}')
  launches=[x for x in ins if x.add_op=='or' and x.add_magic and x.add_waddr==13 and x.raddr_a==8]
  if len(launches)!=1:raise ValueError(f'expected one TMUAU rf8 launch, got {len(launches)}')
  loads=[x for x in ins if 'ldtmu' in x.signals]
  if len(loads)!=4 or any(x.signal_magic for x in loads) or [x.signal_addr for x in loads]!=[0,1,2,3]:raise ValueError('UBO result does not load exactly nonmagic rf0..rf3')
  final=[x for x in ins if x.add_op=='fadd/faddnf' and consumer<=x.add_waddr<consumer+4]
  if len(final)!=4 or any(x.add_magic or x.raddr_a!=producer+k or x.raddr_b!=ubo+k for k,x in enumerate(final)):raise ValueError('post-UBO FAdd does not consume the live producer and UBO value')
  if not (max(x.index for x in first)<address[0].index<launches[0].index<min(x.index for x in loads)<=max(x.index for x in loads)<min(x.index for x in final)):raise ValueError('producer/address/TMUAU/load/consumer order is not exact')
 except Exception as e:bad.append(f'case 31 late-UBO decoder: {e}')
 return words,bad
def grade(c,r):
 if q(c,r+1000*8)!=MAGIC:return 0,['bad report magic']
 checks=q(c,r+1001*8); fails=q(c,r+1002*8)
 bad=[]
 # A direct varying fragment consumes exactly one TLB word and has no sampled
 # metadata. Diagnose a missing/aliased TLB index before the emitted aggregate.
 tlb=q(c,r+(1*8+7)*8);stream=q(c,r+(1*8+3)*8)
 if tlb!=0:bad.append(f'case 1 TLB metadata missing or aliased: index={tlb-(1<<64) if tlb&(1<<63) else tlb}, expected=0')
 elif u32(c,stream+4*tlb)!=0xffffffff:bad.append(f'case 1 TLB metadata names {u32(c,stream+4*tlb):#x}, expected 0xffffffff')
 words,span_bad=grade_late_resource_spans(c,r);bad.extend(span_bad)
 roles=(('vertex','fragment:varying','fragment:flat','fragment:uniform','fragment:sampled','vertex')
        +('vertex',)*12+('fragment:flat','fragment:uniform','fragment:sampled','fragment:varying'))
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
 if fails: bad.append(f'{fails} of {checks} emitted checks failed: '+','.join(str(i+1) for i in range(checks) if q(c,r+(256+i)*8)==0))
 return checks,bad+[f'__WORDS__={words}']
def sourcecheck(text):
 need=('AnvilVkIrVerify(*m)','@avk42CodeScratch[0]','avk42RangesOverlap(','#ANVIL_IR_V3D42_TMU_VEC4','V3dQpuLastThrsw()','V3dQpuProgramEnd()','#ANVIL_IR_DEC_RELAXED_PRECISION','If *other\\variableId = *io\\variableId','#ANVIL_IR_OP_FADD','#ANVIL_IR_OP_FMUL')
 return [f'missing {x}' for x in need if x not in text]
def runone(compiler,a64,suffix,snapshot,snapshot_hash,compiler_hash,module_bytes=None,runner=subprocess.run,execute_fn=execute):
 image,work=build(compiler,suffix,snapshot,snapshot_hash,compiler_hash,module_bytes,runner=runner)
 try:
  c,r,steps=execute_fn(a64,image);checks,items=grade(c,r);words=int(items[-1].split('=')[1]);return checks,words,steps,items[:-1]
 finally:remove_private_tree(work)
def infra_self_test(compiler):
 temp=pathlib.Path(tempfile.gettempdir())
 before={p.resolve() for p in temp.glob('anvil_ir*') if p.is_dir()};source_hash=sha256_file(MODULE)
 snapshot,snapshot_hash=freeze_build_inputs();compiler_hash=sha256_file(compiler)
 rejected=0;failure_abort=False;timeout_abort=False;drift_abort=False;execute_abort=False
 def failed_runner(*args,**kwargs):return subprocess.CompletedProcess(args[0],1,'injected compiler failure')
 def timeout_runner(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],kwargs['timeout'])
 def success_runner(*args,**kwargs):
  out=pathlib.Path(args[0][args[0].index('-o')+1]);out.write_bytes(b'injected image')
  return subprocess.CompletedProcess(args[0],0,'pmfc: OK')
 def execute_failure(*args,**kwargs):raise RuntimeError('injected execute failure')
 fake_dir=pathlib.Path(tempfile.mkdtemp(prefix='anvil_ir42_compiler_'));fake=fake_dir/'compiler.exe';fake.write_bytes(b'frozen compiler')
 def drift_runner(*args,**kwargs):
  fake.write_bytes(b'changed compiler')
  return success_runner(*args,**kwargs)
 try:
  try:build(compiler,'infra_fail',snapshot,snapshot_hash,compiler_hash,runner=failed_runner)
  except RuntimeError as e:failure_abort='injected compiler failure' in str(e)
  try:build(compiler,'infra_timeout',snapshot,snapshot_hash,compiler_hash,runner=timeout_runner,compile_timeout=.01)
  except subprocess.TimeoutExpired:timeout_abort=True
  try:build(fake,'infra_drift',snapshot,snapshot_hash,sha256_file(fake),runner=drift_runner)
  except RuntimeError as e:drift_abort='compiler changed during compile' in str(e)
  try:runone(compiler,None,'infra_execute',snapshot,snapshot_hash,compiler_hash,runner=success_runner,execute_fn=execute_failure)
  except RuntimeError as e:execute_abort='injected execute failure' in str(e)
 finally:
  remove_private_tree(snapshot);remove_private_tree(fake_dir)
 after={p.resolve() for p in temp.glob('anvil_ir*') if p.is_dir()}
 unchanged=sha256_file(MODULE)==source_hash
 if not all((failure_abort,timeout_abort,drift_abort,execute_abort,unchanged)) or rejected!=0 or after!=before:raise RuntimeError(f'infrastructure self-test failed: failure={failure_abort} timeout={timeout_abort} drift={drift_abort} execute={execute_abort} source={unchanged} rejected={rejected} leaked={sorted(str(p) for p in after-before)}')
 print(f'vulkan_ir_v3d42_check: infra self-test PASS - compiler failure abort, timeout abort, hash-drift abort, execute abort, source unchanged, rejected={rejected}, temp-before={len(before)}, temp-after={len(after)}')
 return 0
def campaign(a,compiler,a64,compiler_hash,snapshot,snapshot_hash):
 original_bytes=(snapshot/MODULE.relative_to(ROOT)).read_bytes();original_hash=hashlib.sha256(original_bytes).hexdigest()
 original=original_bytes.decode('utf-8');native_newline='\r\n' if original.count('\r\n')>=original.count('\n')-original.count('\r\n') else '\n'
 def shared_source_unchanged():
  actual=hashlib.sha256(MODULE.read_bytes()).hexdigest()
  if actual!=original_hash:raise RuntimeError(f'shared lowerer SHA-256 changed: {actual} != {original_hash}')
 try:
  print(f'vulkan_ir_v3d42_check: compiler={compiler} sha256={compiler_hash}',flush=True)
  print(f'vulkan_ir_v3d42_check: frozen-input-manifest={snapshot_hash}',flush=True)
  print(f'vulkan_ir_v3d42_check: lowerer-sha256={original_hash}',flush=True)
  bad=sourcecheck(original)
  if bad:
   print('vulkan_ir_v3d42_check: FAIL');print('\n'.join('  '+x for x in bad));return 1
  checks,words,steps,bad=runone(compiler,a64,'base',snapshot,snapshot_hash,compiler_hash)
  if bad:
   print('vulkan_ir_v3d42_check: FAIL');print('\n'.join('  '+x for x in bad));return 1
  print(f'vulkan_ir_v3d42_check: PASS - {checks} emitted checks, {words} independently decoded QPU words, {steps:,} A64 instructions',flush=True)
  if not a.mutate:return 0
  selected=MUTANTS
  if a.only_mutation:
   wanted=set(a.only_mutation);selected=tuple(m for m in MUTANTS if m[0] in wanted)
   missing=wanted-{m[0] for m in selected}
   if missing:raise SystemExit('unknown mutation(s): '+', '.join(sorted(missing)))
  missed=0
  for name,old,new in selected:
   old_bytes=old.replace('\n',native_newline).encode('utf-8');new_bytes=new.replace('\n',native_newline).encode('utf-8')
   if original_bytes.count(old_bytes)!=1: print(f'  STALE {name} ({original_bytes.count(old_bytes)})');missed+=1;continue
   shared_source_unchanged()
   at=original_bytes.index(old_bytes);mutant=original_bytes[:at]+new_bytes+original_bytes[at+len(old_bytes):]
   if mutant[:at]!=original_bytes[:at] or mutant[at+len(new_bytes):]!=original_bytes[at+len(old_bytes):]:raise RuntimeError(f'non-anchor bytes changed for {name}')
   try:
    _,_,_,red=runone(compiler,a64,'mutant',snapshot,snapshot_hash,compiler_hash,mutant);caught=bool(red);detail=red[0] if red else ''
   finally:shared_source_unchanged()
   print(f"  {'RED' if caught else 'GREEN'} {name}"+(f' - {detail[:110]}' if detail else ''),flush=True)
   if not caught:missed+=1
  if missed:print(f'vulkan_ir_v3d42_check: FAIL - {missed} mutants escaped');return 1
  print(f'vulkan_ir_v3d42_check: all {len(selected)} mutations rejected');return 0
 finally:
  shared_source_unchanged()
  if manifest_hash(snapshot)!=snapshot_hash:raise RuntimeError('frozen input snapshot changed before cleanup')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--compiler');ap.add_argument('--interp');ap.add_argument('--mutate',action='store_true');ap.add_argument('--only-mutation',action='append',default=[]);ap.add_argument('--self-test-infra',action='store_true');a=ap.parse_args()
 compiler=locate(a.compiler,'PMF_COMPILER',pathlib.Path(r'C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe'))
 if a.self_test_infra:return infra_self_test(compiler)
 interp=locate(a.interp,'PMF_A64_INTERP',ROOT/'tools/a64/a64_interp.py');a64=loadmod('ir42_a64',interp)
 compiler_hash=sha256_file(compiler);snapshot,snapshot_hash=freeze_build_inputs()
 try:return campaign(a,compiler,a64,compiler_hash,snapshot,snapshot_hash)
 finally:remove_private_tree(snapshot)
if __name__=='__main__':
 with checker_lock():raise SystemExit(main())
