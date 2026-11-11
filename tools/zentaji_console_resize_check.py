"""Resize the actual ROM-booted Anvil monitor and inspect its native frames."""
import argparse,hashlib,json,re,sys
from pathlib import Path
from zentaji_boot_session import ROOT,Session,source_pc,monitor
from zentaji_graphical_boot_check import png

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keep',type=Path,required=True)
 ap.add_argument('--boot-proof',type=Path)
 a=ap.parse_args();zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F
 if a.boot_proof:
  image=ROOT/'build/zentaji/anvil.zex';raw=image.read_bytes()
  meta=json.loads(Path(str(image)+'.boot.json').read_text());mapping=json.loads(Path(str(image)+'.zmap').read_text())
  proof=json.loads((a.boot_proof/'result.json').read_text());data=(a.boot_proof/'symbols.json').read_bytes()
  assert hashlib.sha256(raw).hexdigest()==meta['image_sha256']==mapping['image']==proof['image_sha256']
  assert hashlib.sha256(data).hexdigest()==proof['symbols_sha256'];symbols=json.loads(data)
  for source in mapping['sources']:
   path=Path(source['path']).resolve();assert path.is_relative_to(ROOT.resolve())
   assert hashlib.sha256(path.read_bytes().replace(b'\r',b'')).hexdigest()==source['sha256'],path
 else:raw,meta,mapping,symbols=monitor(zt)
 checkpoint=source_pc(mapping,ROOT/'Zentaji/Board/neon_console.pbi','native monitor frame checkpoint')
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],display_modes=[(640,480,60000)])
 m.input_feed(1000000000,'key',27,1,1,0,88)
 m.input_feed(1000100000,'key',27,0,1,0,0)
 m.power_on(0,0);m.write(td)
 with (td/'machine.txt').open('a') as f:
  f.write('\ndisplay-size 640 480\nresize 1500000000 1024 768\nresize 2000000000 800 600\n')
 results=[];saved_lines=None;first=True;seen=set()
 with Session(zt,td,timeout=1200) as s:
  s.breakpoint(checkpoint)
  for count in range(40):
   s.run_to(checkpoint,step=not first);first=False
   assert s.q(symbols,'zngFault')==0 and s.q(symbols,'avkFaultCount')==0
   w,h=[s.q(symbols,n) for n in ('zgdWidth','zgdHeight')]
   cols,rows=[s.q(symbols,n) for n in ('gConCols','gConRows')]
   text=s.memory(symbols['GLOBAL_GCONGRID'],cols*rows).decode('ascii')
   lines=[text[r*cols:(r+1)*cols].rstrip() for r in range(rows)]
   lines=[line for line in lines if line]
   if not lines or not lines[-1].endswith('pmf> X'):continue
   if saved_lines is None:saved_lines=lines
   assert lines==saved_lines,('Session text changed during resize',w,h,lines,saved_lines)
   if (w,h) in seen:continue
   frame,fw,fh=s.frame(symbols);assert (w,h)==(fw,fh)
   assert frame[:4]==bytes((40,0,0,255))
   assert all(frame[(114*w+x)*4:(114*w+x)*4+4]==bytes((48,148,255,255)) for x in range(24,w-24))
   # The immutable logo occupies the same76x74 pixels at the new right edge.
   logo=b''.join(frame[((y+12)*w+w-88)*4:((y+12)*w+w-12)*4] for y in range(74))
   if results:assert hashlib.sha256(logo).hexdigest()==results[0]['logo_sha256']
   assert s.q(symbols,'znsWidth')==w and s.q(symbols,'znsHeight')==h
   assert s.q(symbols,'zgdPitch')==w*4 and s.q(symbols,'zgdEnabled')==1
   png(td/f'anvil-{w}x{h}.png',frame,w,h)
   results.append(dict(width=w,height=h,logo_sha256=hashlib.sha256(logo).hexdigest(),frame_sha256=hashlib.sha256(frame).hexdigest()))
   seen.add((w,h));print('Observed real Anvil resize',w,h,'with preserved prompt and logo.',flush=True)
   if seen=={(640,480),(1024,768),(800,600)}:break
  assert [(r['width'],r['height']) for r in results]==[(640,480),(1024,768),(800,600)],results
 (td/'result.json').write_text(json.dumps(dict(image_sha256=meta['image_sha256'],frames=results,console_lines=saved_lines),indent=2))
 print('PASS actual Anvil resize:640x480 ->1024x768 ->800x600; header, typed prompt, native scanout and zero Vulkan faults.')

if __name__=='__main__':main()
