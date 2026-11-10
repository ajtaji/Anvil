"""Public resident particles on the real ROM/CPU/GPU, against complete pixel oracles."""
import argparse,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
from pmf_compiler import TRACKED_COMPILER
from zentaji_graphical_boot_check import png
from zentaji_boot_session import ROOT,Session,monitor,source_pc
import zentaji_exfat_oracle as E

def expected(case):
 frame=bytearray(b'\0\0\0\xff'*(640*480))
 def pixel(x,y,colour):frame[(y*640+x)*4:(y*640+x)*4+4]=bytes(colour)
 if case==0:
  # Camera (8,4), unit zoom. Half-alpha green covers the right half of red.
  for y in range(8,16):
   for x in range(4,12):pixel(x,y,(0,0,255,255))
   for x in range(8,16):pixel(x,y,(0,128,127 if x<12 else 0,255))
  # A 45-degree square has a diamond footprint. Q16 sine/cosine round to
  # 46341; the Q8 diagonal radius is 1448. Pixel centres have a full margin
  # from these edges, so no epsilon/tolerance or second rasterizer is needed.
  for y in range(9,23):
   for x in range(25,39):
    if abs((x*256+128)-32*256)+abs((y*256+128)-16*256)<1448:pixel(x,y,(255,0,0,255))
  # White at (52,36) is outside the explicit x<40 scissor and must not appear.
 elif case in (1,2):
  colours=[(0,0,255,255),(0,255,0,255),(255,0,0,255),(255,255,255,255)]
  for row in range(100):
   for col in range(100):
    colour=colours[(row*100+col)%4]
    if case==1:
     for y in (row*4+1,row*4+2):
      for x in (col*4+1,col*4+2):pixel(x,y,colour)
    else:
     # Half zoom around (320,240), camera (8,4): centres become
     # (157.125+2*col,119.125+2*row), with half-size0.5.
     pixel(157+col*2,119+row*2,colour)
 else:assert case==3
 return bytes(frame)

def caller_records(case):
 if case==0:
  return b''.join(struct.pack('<8f',*row) for row in [(16,16,8,0,1,0,0,1),(20,16,8,0,0,1,0,0.5),(40,20,8,0.7853981633974483,0,0,1,1),(60,40,6,0,1,1,1,1)])
 if case==1:
  colours=[(1,0,0,1),(0,1,0,1),(0,0,1,1),(1,1,1,1)]
  return b''.join(struct.pack('<8f',(i%100)*4+2.25,(i//100)*4+2.25,2,0,*colours[i%4]) for i in range(10000))
 return struct.pack('<8f',-1000,-1000,2,0,0,0,0,0)*10000

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',required=True,type=Path);ap.add_argument('--keep',required=True,type=Path);a=ap.parse_args()
 zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A
 raw,meta,mapping,symbols=monitor(zt);stage=(meta['image_end']+4095)&-4096;report=stage+0x400000
 appfile=ROOT/'Zentaji/Tests/neon_service_particles.zentaji';src=td/'particles.zentaji';app=td/'particles.zex'
 src.write_text(f'#ZPP_REPORT=${report:X}\nXIncludeFile "Zentaji/Tests/neon_service_particles.zentaji"\n')
 compiled=subprocess.run([str(TRACKED_COMPILER),'--compile',str(src),'--entry-returns','--wants-services','--load-addr',hex(stage+8),'--stack-addr',hex(stage+0x200000),'-o',str(app)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
 (td/'compile.log').write_text(compiled.stdout+compiled.stderr);assert compiled.returncode==0,(compiled.stdout,compiled.stderr)
 appasm=A.Asm();_,body=appasm.assemble(Path(str(app)+'.asm').read_text(encoding='utf-8-sig'));assert body==app.read_bytes()[64:]
 appmap=json.loads(Path(str(app)+'.zmap').read_text());capture=source_pc(appmap,appfile,'native debugger frame checkpoint')
 prompt=source_pc(mapping,ROOT/'Anvil/Core/command_loop.pbi','ReadLine()')
 medium=E.build(4096,cluster_shift=3);pmf=Path(str(app)+'.pmf').read_bytes();E.seed_file(medium,pmf,'APP.PMF');assert E.root_files(medium)=={'APP.PMF':pmf}
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],disks={0:(medium,False)},display_modes=[(640,480,60000)])
 m.serial[0].incoming=[(600000000,b) for b in b'boot APP.PMF\r'];m.power_on(0,0);m.write(td)
 results=[];tail=None;vertex_base=None
 with Session(zt,td) as s:
  s.breakpoint(prompt);s.breakpoint(capture);s.run_to(prompt)
  print('Actual ROM graphical prompt reached; running the public particle application.',flush=True)
  for case,checks in enumerate((16,22,28,33)):
   s.run_to(capture,step=True)
   header=struct.unpack('<9q',s.memory(report,72));assert header[:4]==(0x3150505A,1,checks,0) and header[5:]==(case+1,10000,32,8),header
   records=caller_records(case);assert s.memory(appasm.sym['GLOBAL_ZPPITEMS'],len(records))==records,'Caller records violate the explicit 32-byte float32 wire layout'
   assert s.q(symbols,'nvcDrawCount')==(0 if case==3 else 1)
   assert s.q(symbols,'nvcVertices')==(24 if case==0 else 0 if case==3 else 60000)
   mapped=s.q(symbols,'nvcMapped');guard=s.memory(mapped+60000*24,256)
   if tail is None:tail=guard;vertex_base=mapped
   else:assert mapped==vertex_base and guard==tail,'Particle vertices wrote beyond their maximum extent'
   actual,w,h=s.frame(symbols);assert (w,h)==(640,480);png(td/f'particle-frame-{case}.png',actual,w,h)
   oracle=expected(case);(td/f'particle-frame-{case}.bgra').write_bytes(actual)
   if actual!=oracle:
    bad=next(i for i,(x,y) in enumerate(zip(actual,oracle)) if x!=y);raise AssertionError(('Particle pixel mismatch',case,(bad//4)%640,(bad//4)//640,actual[bad//4*4:bad//4*4+4],oracle[bad//4*4:bad//4*4+4]))
   assert s.q(symbols,'avkFaultCount')==0
   results.append(dict(case=case,checks=checks,draws=0 if case==3 else 1,vertices=24 if case==0 else 0 if case==3 else 60000,frame_sha256=hashlib.sha256(actual).hexdigest()))
   print('PASS public particle frame '+str(case)+': all307200 pixels exact; vertex tail unchanged.',flush=True)
  s.run_to(prompt,step=True)
  assert s.q(symbols,'gGoRc')==0 and s.q(symbols,'avsContext')==0 and s.q(symbols,'nvstContext')==0 and s.q(symbols,'gsrScope')==0
  assert s.q(symbols,'zngUp')==1 and s.q(symbols,'zngFault')==0 and s.q(symbols,'zngSuspended')==0 and s.q(symbols,'avkFaultCount')==0
  assert s.q(symbols,'nvcParticleImage')==0 and s.q(symbols,'nvcParticleMapped')==0 and s.q(symbols,'nvcReady')==1
  cols,rows=s.q(symbols,'gConCols'),s.q(symbols,'gConRows');text=s.memory(symbols['GLOBAL_GCONGRID'],cols*rows).decode('ascii',errors='replace');assert text.rstrip().endswith('pmf>') and 'The payload returned' in text,text
  frame,w,h=s.frame(symbols);png(td/'restored-prompt.png',frame,w,h)
 assert (td/'disk0.img').read_bytes()==medium and (td/'hostfile0.bin').read_bytes()==raw
 (td/'result.json').write_text(json.dumps(dict(image_sha256=meta['image_sha256'],application_sha256=hashlib.sha256(pmf).hexdigest(),frames=results,checks=33,maximum_particles=10000,returned=0,scopes_retired=True),indent=2))
 print('PASS public resident particle service:33 checks, four exact native GPU frames,10k limit, copied input, retired resources and graphical prompt restored.',flush=True)
if __name__=='__main__':main()
