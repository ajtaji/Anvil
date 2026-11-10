"""Boot the counted Anvil image through the ROM and capture its graphical prompt."""
import argparse,hashlib,json,os,struct,subprocess,sys,tempfile,zlib,queue,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def png(path,bgra,w,h):
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 rows=bytearray()
 for y in range(h):
  rows.append(0)
  for x in range(w):
   at=(y*w+x)*4;rows.extend((bgra[at+2],bgra[at+1],bgra[at]))
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keep',type=Path,required=True);ap.add_argument('--exercise',action='store_true');a=ap.parse_args()
 zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A
 image=ROOT/'build/zentaji/anvil.zex';raw=image.read_bytes();meta=json.loads(Path(str(image)+'.boot.json').read_text());mapping=json.loads(Path(str(image)+'.zmap').read_text())
 assert hashlib.sha256(raw).hexdigest()==meta['image_sha256']==mapping['image']
 for source in mapping['sources']:
  path=Path(source['path']);path=path if path.is_absolute() else ROOT/path
  assert hashlib.sha256(path.read_bytes().replace(b'\r',b'')).hexdigest()==source['sha256'],path
 source=ROOT/'Anvil/Core/command_loop.pbi';line=next(i for i,text in enumerate(source.read_text().splitlines(),1) if text.strip()=='ReadLine()')
 pc=next(int(row['pc'],16) for row in mapping['code'] if Path(row['source']).resolve()==source.resolve() and row['line']==line)
 ref=A.Asm();ref.assemble(Path(str(image)+'.compiled.asm').read_text(encoding='utf-8-sig'))
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],display_modes=[(640,480,60000)])
 if a.exercise:
  from pmf_compiler import TRACKED_COMPILER
  import zentaji_exfat_oracle as E
  stage=(meta['image_end']+4095)&-4096;marker=stage+0x100000
  appsrc=td/'return.zentaji';app=td/'return.zex'
  appsrc.write_text(f'Procedure.q Main()\n PokeQ(${marker:X},PeekQ(${marker:X})+1)\n ProcedureReturn 42\nEndProcedure\n')
  compiled=subprocess.run([str(TRACKED_COMPILER),'--compile',str(appsrc),'--entry-returns','--load-addr',hex(stage+8),'--stack-addr',hex(stage+0x200000),'-o',str(app)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
  assert compiled.returncode==0,(compiled.stdout,compiled.stderr)
  medium=E.build(4096);E.seed_file(medium,Path(str(app)+'.pmf').read_bytes(),'APP.PMF')
  m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],disks={0:(bytearray(medium),False)},display_modes=[(640,480,60000)])
  # Feed real serial bytes through the hardware FIFO; the debugger only stops execution.
  m.serial[0].incoming=[(600000000,b) for b in b'echo GRAPHICS READY\rboot APP.PMF\r']
 m.power_on(0,0);m.write(td)
 p=subprocess.Popen([str(zt/'zenemu.exe'),str(td/'machine.txt'),'--debug-stdio','--ram',str(td/'final.bin')],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=0x08000000 if os.name=='nt' else 0)
 replies=queue.Queue();lines=[]
 def reader():
  for row in p.stdout:replies.put(row)
  replies.put(None)
 worker=threading.Thread(target=reader,daemon=True);worker.start();deadline=time.monotonic()+900
 def next_line():
  while time.monotonic()<deadline:
   try:row=replies.get(timeout=1)
   except queue.Empty:continue
   assert row is not None,('native debugger exited',p.poll(),''.join(lines)[-4000:])
   lines.append(row);return row
  raise TimeoutError('Actual Anvil boot did not reach its input prompt within 900s')
 def send(command):p.stdin.write(command+'\n');p.stdin.flush()
 try:
  while 'DBG READY 1' not in next_line():pass
  send(f'break 0 ${pc:X}');reply=next_line();assert 'error:' not in reply,reply
  send('run');print('Running actual ROM-loaded Anvil to its first graphical input prompt.',flush=True)
  events=[]
  for stop in range(3 if a.exercise else 1):
   while True:
    reply=next_line()
    if 'DBG EVENT ' in reply:break
   events.append(reply)
   if 'DBG breakpoint ' not in reply:break
   if stop < (2 if a.exercise else 0):
    send('step 1');reply=next_line();assert 'error:' not in reply,reply
    send('run')
  send('quit');p.stdin.close();p.wait(timeout=30);worker.join(timeout=10)
  while not replies.empty():
   row=replies.get_nowait()
   if row is not None:lines.append(row)
  out=''.join(lines);assert p.returncode==0,(p.returncode,out[-4000:]);assert len(events)==(3 if a.exercise else 1) and all('DBG breakpoint ' in item for item in events),out[-4000:]
 finally:
  if p.poll() is None:p.kill();p.wait()
  (td/'native.log').write_text(''.join(lines))
 ram=(td/'final.bin').read_bytes()
 def q(name):return struct.unpack_from('<q',ram,ref.sym['GLOBAL_'+name.upper()])[0]
 assert q('zngUp')==1 and q('zngFault')==0 and q('zngSuspended')==0,(q('zngUp'),q('zngFault'))
 assert q('znsState')==2 and q('zgdEnabled')==1 and q('zgdSequence')>=1
 assert q('zenTextCells')==0 and q('avkFaultCount')==0
 if a.exercise:assert struct.unpack_from('<q',ram,marker)[0]==1 and q('gGoRc')==42,(struct.unpack_from('<q',ram,marker)[0],q('gGoRc'))
 cols,rows=q('gConCols'),q('gConRows');at=ref.sym['GLOBAL_GCONGRID'];text=ram[at:at+cols*rows].decode('ascii',errors='replace');assert 'pmf> ' in text and 'Anvil' in text,text
 if a.exercise:assert 'GRAPHICS READY' in text and 'The payload returned' in text,text
 base,span,shown,pitch,w,h=[q(n) for n in ['zgdBase','zgdSpan','zgdShown','zgdPitch','zgdWidth','zgdHeight']]
 assert (w,h,pitch)==(640,480,2560) and 0<=shown<3
 at=base+shown*span;frame=b''.join(ram[at+y*pitch:at+y*pitch+w*4] for y in range(h))
 colours={frame[i:i+4] for i in range(0,len(frame),4)};assert len(colours)>17,len(colours)
 png(td/'anvil-graphical-prompt.png',frame,w,h);(td/'console.txt').write_text(text)
 (td/'result.json').write_text(json.dumps(dict(image_sha256=meta['image_sha256'],entry=meta['entry'],breakpoint=pc,width=w,height=h,shown=shown,frames=q('zgdSequence'),font='Anvil shared TrueType boot font',colours=len(colours),frame_sha256=hashlib.sha256(frame).hexdigest()),indent=2))
 print('PASS actual ROM-loaded counted Anvil image: shared TrueType/Neon graphical prompt, native display enabled, cell-text disabled, no Vulkan faults; screenshot '+str(td/'anvil-graphical-prompt.png'))
if __name__=='__main__':main()
