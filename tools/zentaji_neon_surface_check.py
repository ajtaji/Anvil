"""Real shared Neon/TrueType surface on the production compiler and native GPU."""
import argparse,hashlib,json,os,re,struct,subprocess,sys,tempfile
from fractions import Fraction
from pathlib import Path
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
ROOT=Path(__file__).resolve().parents[1]
def expected():
 oracle=json.loads(Path(__file__).with_name('zentaji_neon_glyph_oracle.json').read_text())
 asset=ROOT/'RaspberryPi4/Monitor/anvil_boot_ttf.pi4'
 raw=bytes(int(v,16) for v in re.findall(r'\$([0-9A-Fa-f]{2})(?=[,\s])',asset.read_text()))
 assert hashlib.sha256(raw).hexdigest()==oracle['font_sha256']
 frame=bytearray(b'\0\0\0\xff'*(64*64));pen=Fraction(4);baseline=1+oracle['hhea']['ascent']*16//2048
 for g in oracle['glyphs']:
  x=pen+g['bearing_x'];left=(x.numerator*2+x.denominator)//(x.denominator*2);top=baseline-g['bearing_y']
  coverage=bytes.fromhex(g['coverage_hex']);assert hashlib.sha256(coverage).hexdigest()==g['coverage_sha256']
  for y in range(g['height']):
   for col in range(g['width']):
    a=coverage[y*g['width']+col];at=((top+y)*64+left+col)*4;frame[at:at+4]=bytes([a,a,a,255])
  pen+=Fraction(g['advance_units']*16,2048)
 return bytes(frame)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keep',type=Path);args=ap.parse_args()
 cc=resolve_compiler(args.compiler);zt=args.zen_tools.resolve();sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A,zexpack
 def run(argv,timeout):
  p=subprocess.run(list(map(str,argv)),cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
  assert p.returncode==0,(p.returncode,p.stdout[-5000:],p.stderr);return p.stdout+p.stderr
 with tempfile.TemporaryDirectory(prefix='zen-neon-surface-') as tmp:
  td=args.keep.resolve() if args.keep else Path(tmp);td.mkdir(parents=True,exist_ok=True)
  image=td/'surface.zex';src=ROOT/'Zentaji/Tests/neon_surface.zentaji'
  (td/'compile.log').write_text(run([cc,'--compile',src,'--entry-returns','-o',image],600))
  mapping=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig'));assert mapping['image']==hashlib.sha256(image.read_bytes()).hexdigest()
  for row in mapping['sources']:
   path=Path(row['path']);assert path.is_relative_to(ROOT),path
   assert hashlib.sha256(path.read_bytes().replace(b'\r',b'')).hexdigest()==row['sha256'],path
  ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'));assert image.read_bytes()==zexpack.header(origin,origin,data)+data
  wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=mapping)
  machine=F.Fixture(ram_size=128<<20,cores=2,display_modes=[(64,64,60000)]);machine.load_image(wrapped);machine.write(td)
  out=run([zt/'zenemu.exe',td/'machine.txt','--max','400000000','--ram',td/'final.bin'],300);(td/'native.log').write_text(out)
  ram=(td/'final.bin').read_bytes();report=struct.unpack_from('<32q',ram,ref.sym['GLOBAL_REPORT']);end=next(s for s in out.splitlines() if s.startswith('END '))
  (td/'report.json').write_text(json.dumps(dict(report=report,end=end,image_sha256=mapping['image']),indent=2))
  assert ' exit=2A ' in end and report[0]==5,(end,report)
  assert report[3:7]==(0,1,1,2) and report[9:15]==(4,0,0,0,0,0),report
  assert report[15:17]==(256,12000) and 1728000<=report[17]<1732096 and report[19:22]==(1,2,3084),report
  white=expected();red=bytearray(white)
  for i in range(0,len(red),4):red[i]=red[i+1]=0
  base,span=report[1:3];assert span==len(white)==16384
  assert ram[base:base+span]==white,'white frame differs from independent glyph geometry'
  assert ram[base+span:base+2*span]==red,'red frame or preserved first plane differs'
  assert ram[base+2*span:base+3*span]==bytes(span),'untouched plane changed'
  for name,at in [('white',base),('red',base+span)]: (td/(name+'.bgra')).write_bytes(ram[at:at+span])
 print('PASS production shared TrueType/Neon/native GPU: two exact geometry-oracle frames, 514 glyph quads in two draw records, independent 12000-quad VBO, tail canary, presentation ownership and clean shutdown')
if __name__=='__main__':main()
