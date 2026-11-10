"""Real ROM/PMF applications must pin resident graphics after foreign ownership."""
import argparse,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
from pmf_compiler import TRACKED_COMPILER
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',required=True,type=Path);ap.add_argument('--keep',required=True,type=Path);ap.add_argument('--particles',action='store_true',help='Retain a real particle palette and staging allocation before changing ownership');a=ap.parse_args()
 zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A
 image=ROOT/'build/zentaji/anvil.zex';raw=image.read_bytes();meta=json.loads(Path(str(image)+'.boot.json').read_text());mapping=json.loads(Path(str(image)+'.zmap').read_text())
 assert hashlib.sha256(raw).hexdigest()==meta['image_sha256']==mapping['image']
 for source in mapping['sources']:
  p=Path(source['path']);assert hashlib.sha256(p.read_bytes().replace(b'\r',b'')).hexdigest()==source['sha256'],p
 ref=None
 stage=(meta['image_end']+4095)&-4096;results=[]
 for name,address in [('dma',0xFFFF000000080490),('gpu',0xFFFF0000000E0040),('display',0xFFFF0000000C0078)]:
  case=td/name;case.mkdir(exist_ok=True);src=case/'foreign.zentaji';app=case/'foreign.zex'
  src.write_text(f'#ZEN_SERVICE_FOREIGN_REG=${address:X}\n#ZEN_SERVICE_FOREIGN_PARTICLES={int(a.particles)}\nXIncludeFile "Zentaji/Tests/neon_service_foreign.zentaji"\n')
  compiled=subprocess.run([str(TRACKED_COMPILER),'--compile',str(src),'--entry-returns','--wants-services','--load-addr',hex(stage+8),'--stack-addr',hex(stage+0x200000),'-o',str(app)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
  (case/'compile.log').write_text(compiled.stdout+compiled.stderr);assert compiled.returncode==0,(name,compiled.stdout,compiled.stderr)
  if ref is None:
   ref=A.Asm();ref.assemble(Path(str(image)+'.compiled.asm').read_text(encoding='utf-8-sig'))
  medium=E.build(4096,cluster_shift=2);pmf=Path(str(app)+'.pmf').read_bytes();E.seed_file(medium,pmf,'APP.PMF');assert E.root_files(medium)=={'APP.PMF':pmf}
  m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],disks={0:(medium,False)},display_modes=[(640,480,60000)])
  m.serial[0].incoming=[(600000000,b) for b in b'boot APP.PMF\r'];m.power_on(0,0);m.write(case)
  print('Running real resident '+name+' ownership-return refusal.',flush=True)
  run=subprocess.run([str(zt/'zenemu.exe'),str(case/'machine.txt'),'--max','800000000','--ram',str(case/'final.bin')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
  (case/'native.log').write_text(run.stdout+run.stderr);assert run.returncode==0,(name,run.returncode,run.stdout[-3000:],run.stderr)
  fields=dict(item.split('=',1) for item in next(row for row in run.stdout.splitlines() if row.startswith('END ')).split()[1:]);assert fields['exit']!='-' and int(fields['exit'],16)==0x5B07,(name,fields)
  serial=bytes.fromhex(next(row.split(' ',1)[1] for row in run.stdout.splitlines() if row.startswith('SERIAL0 ')))
  assert serial.count(b'pmf> ')==1 and b'0x5B07' in serial and b'The payload returned' not in serial,(name,serial)
  ram=(case/'final.bin').read_bytes()
  def q(key):return struct.unpack_from('<q',ram,ref.sym['GLOBAL_'+key.upper()])[0]
  assert q('gsrScope')==2 and q('gsrFailure')<0 and q('avsContext')==1 and q('avsReady')==0
  assert q('nvstContext')==1 and q('nvcReady')==1 and q('nvcDevice')>0,'Foreign ownership retired live resources'
  if a.particles:assert q('nvcParticleImage')>0 and q('nvcParticleMapped')>0,'Foreign ownership retired particle resources'
  assert q('zngSuspended')==2 and q('znsState')==2 and q('avkFaultCount')==0
  assert (case/'disk0.img').read_bytes()==medium and (case/'hostfile0.bin').read_bytes()==raw
  results.append(dict(case=name,exit=0x5B07,context_retained=q('avsContext'),target_scope_retained=q('nvstContext'),chrome_ready=q('nvcReady'),vulkan_faults=q('avkFaultCount')))
  print('PASS '+name+': fail-stop 5B07, no second prompt, context/targets/Chrome pinned, no Vulkan faults',flush=True)
 (td/'result.json').write_text(json.dumps(dict(image_sha256=meta['image_sha256'],particle_resources=a.particles,cases=results),indent=2))
if __name__=='__main__':main()
