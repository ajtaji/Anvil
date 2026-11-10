"""Run the existing composed Neon application on the native Zentaji machine."""
import argparse,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
from pmf_compiler import TRACKED_COMPILER
from zentaji_boot_session import ROOT,Session,monitor,source_pc
from zentaji_graphical_boot_check import png
import zentaji_exfat_oracle as E

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--zen-tools',required=True,type=Path);ap.add_argument('--keep',required=True,type=Path)
 a=ap.parse_args();zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A
 raw,meta,mapping,symbols=monitor(zt)
 src=td/'composed.zentaji';app=td/'composed.zex';report=0x4000000
 src.write_text('#NCA_REPORT=$4000000\n#NCA_SCRIPTED=0\n#NCA_ASSETS=0\n#NCA_NATIVE=1\n#NCA_RETRO=0\n#NCA_PRESENT_PACED=1\n#NCA_FONT_SLOT=4\nXIncludeFile "Anvil/Graphics/Tests/neon_service_composed_app.pbi"\n')
 r=subprocess.run([str(TRACKED_COMPILER),'--compile',str(src),'--entry-returns','--wants-services','--load-addr','0x3000008','--stack-addr','0x3800000','-o',str(app)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,timeout=180)
 (td/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
 asm=A.Asm();_,body=asm.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'));assert body==app.read_bytes()[64:]
 appmap=json.loads(Path(str(app)+'.zmap').read_text());appsource=ROOT/'Anvil/Graphics/Tests/neon_service_composed_app.pbi'
 capture=source_pc(appmap,appsource,'p=#NCA_REPORT+4096+i*64')
 prompt=source_pc(mapping,ROOT/'Anvil/Core/command_loop.pbi','ReadLine()')
 medium=E.build(4096,cluster_shift=6);pmf=Path(str(app)+'.pmf').read_bytes();E.seed_file(medium,pmf,'APP.PMF');assert E.root_files(medium)=={'APP.PMF':pmf}
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],disks={0:(medium,False)},display_modes=[(640,480,60000)])
 m.serial[0].incoming=[(600000000,b) for b in b'boot APP.PMF\r']
 m.power_on(0,0);m.write(td)
 with Session(zt,td,timeout=1800) as s:
  s.breakpoint(prompt);s.breakpoint(capture);s.run_to(prompt)
  print('Native ROM graphical prompt reached; loading composed application.',flush=True)
  s.request('step 1');s.request('run')
  while True:
   row=s.line()
   if row.startswith('DBG EVENT '):break
  assert 'DBG breakpoint ' in row,row
  if f'pc=${capture:X}' in row:
   frame,w,h=s.frame(symbols);png(td/'composed-first.png',frame,w,h)
   controls=s.request('controls 0');(td/'first-controls.txt').write_text(controls)
   print('Composed first frame captured; '+controls,flush=True)
   s.request(f'unbreak 0 ${capture:X}');s.run_to(prompt,step=True)
  else:assert f'pc=${prompt:X}' in row,row
  header=s.memory(report,16384);(td/'report.bin').write_bytes(header)
  values=struct.unpack_from('<34q',header)
  result=dict(image_sha256=meta['image_sha256'],application_sha256=hashlib.sha256(pmf).hexdigest(),failure=values[2],rc=values[3],frames=values[4],ends=values[5],duration_us=values[11],return_code=s.q(symbols,'gGoRc'),gpu_faults=s.q(symbols,'avkFaultCount'))
  result.update(button_events=values[13],running=values[33],input_records=values[7],edit_text=header[2048:2304].split(b'\0')[0].decode('utf-8'),button_text=header[2304:2432].split(b'\0')[0].decode('utf-8'),scopes_retired=all(s.q(symbols,n)==0 for n in ('avsContext','nvstContext','gsrScope')),graphics_restored=s.q(symbols,'zngUp')==1 and s.q(symbols,'zngSuspended')==0 and s.q(symbols,'zngFault')==0)
  (td/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
  frame,w,h=s.frame(symbols);png(td/'restored-prompt.png',frame,w,h)
  assert result['failure']==0 and result['return_code']==0 and result['frames']==90 and result['ends']==90 and result['gpu_faults']==0 and result['scopes_retired'] and result['graphics_restored'],result
 assert (td/'disk0.img').read_bytes()==medium and (td/'hostfile0.bin').read_bytes()==raw
 print('PASS: existing composed application completed90 synchronized frames and returned.',flush=True)
if __name__=='__main__':main()
