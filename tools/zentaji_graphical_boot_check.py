"""Boot the counted Anvil image through the ROM and capture its graphical prompt."""
import argparse,hashlib,json,os,struct,subprocess,sys,tempfile,zlib,queue,threading,time,re
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
def expected_logo(phase=-1):
 logo=bytearray()
 for kind,row in re.findall(r'^\s*Data\.(a|b|w|l|q)\s+([^;\r\n]+)',(ROOT/'Anvil/Graphics/anvil_logo.pbi').read_text(encoding='utf-8'),re.M|re.I):
  size={'a':1,'b':1,'w':2,'l':4,'q':8}[kind.lower()]
  for token in row.split(','):
   token=token.strip();value=int(token[1:],16) if token.startswith('$') else int(token)
   logo.extend((value&((1<<(8*size))-1)).to_bytes(size,'little'))
 assert len(logo)==76*74*3,len(logo)
 result=bytearray()
 for i in range(0,len(logo),3):result.extend((logo[i+2],logo[i+1],logo[i],255))
 if phase>=0:
  positions=((13,17),(20,14),(27,11),(34,9),(41,10),(48,11),(55,13),(62,15))
  assert phase<len(positions),phase
  x,y=positions[phase]
  for dx,dy,colour in ((0,0,(64,176,255,255)),(-1,0,(240,232,226,255)),(1,0,(240,232,226,255)),(0,-1,(240,232,226,255)),(0,1,(240,232,226,255))):
   at=((y+dy)*76+x+dx)*4;result[at:at+4]=bytes(colour)
 return bytes(result)

def assert_logo(frame,width,phase=-1):
 actual=b''.join(frame[((y+12)*width+width-88)*4:((y+12)*width+width-12)*4] for y in range(74))
 wanted=expected_logo(phase)
 assert actual==wanted,('Missing/corrupt Anvil logo or sparkle',phase)
 return hashlib.sha256(actual).hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--keep',type=Path,required=True);ap.add_argument('--exercise',action='store_true');ap.add_argument('--keyboard',action='store_true',help='Exercise native keyboard events and Backspace editing instead of UART commands (requires --exercise)');ap.add_argument('--resident',action='store_true',help='Run the existing shared retained-UI service application twice and inspect its real frames');a=ap.parse_args()
 if a.resident:a.exercise=True
 if a.resident and a.keyboard:ap.error('--resident and --keyboard are separate input scenarios')
 if a.keyboard and not a.exercise:ap.error('--keyboard requires --exercise')
 zt=a.zen_tools.resolve();td=a.keep.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F,zasm_ref as A
 image=ROOT/'build/zentaji/anvil.zex';raw=image.read_bytes();meta=json.loads(Path(str(image)+'.boot.json').read_text());mapping=json.loads(Path(str(image)+'.zmap').read_text())
 assert hashlib.sha256(raw).hexdigest()==meta['image_sha256']==mapping['image']
 for source in mapping['sources']:
  path=Path(source['path']);path=path if path.is_absolute() else ROOT/path
  assert hashlib.sha256(path.read_bytes().replace(b'\r',b'')).hexdigest()==source['sha256'],path
 source=ROOT/'Anvil/Core/command_loop.pbi';line=next(i for i,text in enumerate(source.read_text().splitlines(),1) if text.strip()=='ReadLine()')
 # Resolve each distinct source once: the full monitor map contains hundreds
 # of thousands of code records referring to the same small set of paths.
 source_paths={row['path']:Path(row['path']).resolve() for row in mapping['sources']}
 pc=next(int(row['pc'],16) for row in mapping['code'] if row['line']==line and source_paths[row['source']]==source.resolve())
 ref=A.Asm();ref.assemble(Path(str(image)+'.compiled.asm').read_text(encoding='utf-8-sig'))
 (td/'symbols.json').write_text(json.dumps(ref.sym))
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],display_modes=[(640,480,60000)])
 if a.exercise:
  from pmf_compiler import TRACKED_COMPILER
  import zentaji_exfat_oracle as E
  stage=(meta['image_end']+4095)&-4096;marker=stage+0x100000
  appsrc=td/'return.zentaji';app=td/'return.zex'
  if a.resident:
   report=stage+0x400000
   appsrc.write_text(f'#NSA_REPORT=${report:X}\nXIncludeFile "Anvil/Graphics/Tests/neon_service_resident_app.pbi"\n')
  else:appsrc.write_text(f'Procedure.q Main()\n PokeQ(${marker:X},PeekQ(${marker:X})+1)\n ProcedureReturn 42\nEndProcedure\n')
  compiled=subprocess.run([str(TRACKED_COMPILER),'--compile',str(appsrc),'--entry-returns','--load-addr',hex(stage+8),'--stack-addr',hex(stage+0x200000),*(['--wants-services'] if a.resident else []),'-o',str(app)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600 if a.resident else 45)
  assert compiled.returncode==0,(compiled.stdout,compiled.stderr)
  if a.resident:
   appmap=json.loads(Path(str(app)+'.zmap').read_text());appfile=ROOT/'Anvil/Graphics/Tests/neon_service_resident_app.pbi'
   app_line=next(i for i,text in enumerate(appfile.read_text().splitlines(),1) if 'PokeI(#NSA_REPORT + 80,' in text)
   apppc=next(int(row['pc'],16) for row in appmap['code'] if row['line']==app_line and Path(row['source']).resolve()==appfile.resolve())
  medium=E.build(4096,cluster_shift=2 if a.resident else 0);E.seed_file(medium,Path(str(app)+'.pmf').read_bytes(),'APP.PMF')
  m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],disks={0:(bytearray(medium),False)},display_modes=[(640,480,60000)])
  if a.keyboard:
   # Real HID usages/text go through the native device, board normalizer and
   # shared editor. Backspace must repair READX to READY before dispatch.
   # Separate the commands so the prompt's held-key fence cannot consume
   # the next command while returning ownership from the previous one.
   for tick,command in [(600000000,'echo GRAPHICS READX\bY\r'),(2000000000,'boot APP.PMF\r')]:
    for ch in command:
     if ch=='\r':usage,mods,text=40,0,0
     elif ch=='\b':usage,mods,text=42,0,0
     elif ch==' ':usage,mods,text=44,0,32
     elif ch=='.':usage,mods,text=55,0,46
     else:usage,mods,text=4+ord(ch.lower())-ord('a'),int(ch.isupper()),ord(ch)
     m.input_feed(tick,'key',usage,1,mods,0,text)
     m.input_feed(tick,'key',usage,0,mods,0,0)
  else:
   # Feed real serial bytes through the hardware FIFO; the debugger only stops execution.
   if a.resident:
    # Input arriving during PMF hashing is a real cancellation request. Do
    # not queue the second command while the larger UI payload is verified.
    m.serial[0].incoming=[(tick,b) for tick in (600000000,6000000000) for b in b'boot APP.PMF\r']
   else:m.serial[0].incoming=[(600000000,b) for b in b'echo GRAPHICS READY\rboot APP.PMF\r']
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
 def memory(address,count):
  data=bytearray()
  # The reader thread drains replies concurrently. Batch paused inspection
  # requests so a full display does not incur thousands of pipe wakeups.
  requests=[f'memory ${address+offset:X} {min(256,count-offset)}' for offset in range(0,count,256)]
  p.stdin.write('\n'.join(requests)+'\n');p.stdin.flush()
  for offset in range(0,count,256):
   take=min(256,count-offset)
   row=next_line();fields=row.split();assert fields[:2]==['DBG','MEMORY'] and int(fields[2][1:],16)==address+offset,row
   part=bytes.fromhex(' '.join(fields[3:]));assert len(part)==take,row;data.extend(part)
  return bytes(data)
 def observed_q(name):return struct.unpack('<q',memory(ref.sym['GLOBAL_'+name.upper()],8))[0]
 resident_frames=[]
 def resident_frame():
  print('Inspecting resident application frame '+str(len(resident_frames)+1)+'.',flush=True)
  values=struct.unpack('<512q',memory(report,4096))
  assert values[:5]==(0x4E534131,1,0,22,1) and values[5]>=8,values[:6]
  positive={3,4,5,6,11,12}
  for index in range(1,23):
   actual,expected=struct.unpack('<2q',memory(report+128+index*16,16));want=int(index in positive)
   assert (actual,expected)==(want,want),(index,actual,expected,want)
  assert (values[6],values[7],values[8],values[9])==(len(resident_frames)+1,640,480,((len(resident_frames)+1)<<16)|1),values[6:10]
  base,span,shown,pitch=[observed_q(n) for n in ['zgdBase','zgdSpan','zgdShown','zgdPitch']]
  frame=memory(base+shown*span,pitch*480);assert pitch==640*4,pitch
  png(td/f'resident-application-{len(resident_frames)+1}.png',frame,640,480)
  for x,y,rgb in [(10,10,(5,10,20)),(520,160,(0,191,128)),(620,190,(0,191,128)),(570,300,(230,102,26)),(60,140,(102,102,102)),(70,150,(38,51,153))]:
   b,g,r,_=frame[(y*640+x)*4:(y*640+x)*4+4]
   assert max(abs(a-b) for a,b in zip((r,g,b),rgb))<=1,(x,y,(r,g,b),rgb)
  def ink(x0,y0,x1,y1,predicate):
   return sum(predicate(frame[(y*640+x)*4:(y*640+x)*4+3]) for y in range(y0,y1) for x in range(x0,x1))
  assert ink(60,60,640,110,lambda bgr:bgr[2]>180 and bgr[1]>130 and bgr[0]<100)>200,'Missing TrueType title ink'
  assert ink(180,150,300,195,lambda bgr:min(bgr)>180)>50,'Missing TrueType button ink'
  if resident_frames:assert frame==resident_frames[0],'Identical retained application produced a different second frame'
  resident_frames.append(frame)
 try:
  while 'DBG READY 1' not in next_line():pass
  send(f'break 0 ${pc:X}');reply=next_line();assert 'error:' not in reply,reply
  if a.resident:
   send(f'break 0 ${apppc:X}');reply=next_line();assert 'error:' not in reply,reply
  send('run');print('Running actual ROM-loaded Anvil to its first graphical input prompt.',flush=True)
  events=[]
  stops=5 if a.resident else 3 if a.exercise else 1
  for stop in range(stops):
   while True:
    reply=next_line()
    if 'DBG EVENT ' in reply:break
   events.append(reply)
   if 'DBG breakpoint ' not in reply:break
   expected_pc=apppc if a.resident and stop in (1,3) else pc
   if f'pc=${expected_pc:X}' not in reply:
    if a.resident:
     observed=memory(report,4096);(td/'unexpected-application-report.bin').write_bytes(observed)
     print('Unexpected stop; application report header',struct.unpack_from('<12q',observed),'return',observed_q('gGoRc'),flush=True)
    send('quit');p.stdin.close();p.wait(timeout=30);worker.join(timeout=10)
    while not replies.empty():
     row=replies.get_nowait()
     if row is not None:lines.append(row)
    raise AssertionError(reply)
   if a.resident and stop in (1,3):resident_frame()
   if stop < stops-1:
    send('step 1');reply=next_line();assert 'error:' not in reply,reply
    send('run')
  send('quit');p.stdin.close();p.wait(timeout=30);worker.join(timeout=10)
  while not replies.empty():
   row=replies.get_nowait()
   if row is not None:lines.append(row)
  out=''.join(lines);assert p.returncode==0,(p.returncode,out[-4000:]);assert len(events)==stops and all('DBG breakpoint ' in item for item in events),out[-4000:]
 finally:
  if p.poll() is None:p.kill();p.wait()
  (td/'native.log').write_text(''.join(lines))
 ram=(td/'final.bin').read_bytes()
 def q(name):return struct.unpack_from('<q',ram,ref.sym['GLOBAL_'+name.upper()])[0]
 assert q('zngUp')==1 and q('zngFault')==0 and q('zngSuspended')==0,(q('zngUp'),q('zngFault'))
 assert q('znsState')==2 and q('zgdEnabled')==1 and q('zgdSequence')>=1
 assert q('zenTextCells')==0 and q('avkFaultCount')==0
 if a.resident:assert len(resident_frames)==2 and q('gGoRc')==0 and q('avsEpoch')==2 and q('avsContext')==0 and q('nvstContext')==0 and q('gsrScope')==0
 elif a.exercise:assert struct.unpack_from('<q',ram,marker)[0]==1 and q('gGoRc')==42,(struct.unpack_from('<q',ram,marker)[0],q('gGoRc'))
 cols,rows=q('gConCols'),q('gConRows');at=ref.sym['GLOBAL_GCONGRID'];text=ram[at:at+cols*rows].decode('ascii',errors='replace')
 assert text.rstrip().endswith('pmf>'),text
 # Two verbose filesystem/hash/ABI transcripts legitimately scroll the boot
 # banner off this viewport. Their application frames verify Anvil's title.
 if not a.resident:assert 'Anvil' in text,text
 if a.exercise:assert (a.resident or 'GRAPHICS READY' in text) and 'The payload returned' in text,text
 if a.keyboard:
  assert 'GRAPHICS READX' not in text,text
  assert q('ziUp')==1 and q('ziOwned')==0 and q('ziFencing')==0
 base,span,shown,pitch,w,h=[q(n) for n in ['zgdBase','zgdSpan','zgdShown','zgdPitch','zgdWidth','zgdHeight']]
 assert (w,h,pitch)==(640,480,2560) and 0<=shown<3
 at=base+shown*span;frame=b''.join(ram[at+y*pitch:at+y*pitch+w*4] for y in range(h))
 colours={frame[i:i+4] for i in range(0,len(frame),4)};assert len(colours)>17,len(colours)
 png(td/'anvil-graphical-prompt.png',frame,w,h);(td/'console.txt').write_text(text)
 # Verify the actual boot header, independently of the generic text grid.
 # Read immutable RGB asset literals; no second CPU or renderer is executed.
 assert_logo(frame,w,q('zngGlintPhase'))
 assert frame[0:4]==bytes((40,0,0,255)),'Missing banner background'
 assert all(frame[(114*w+x)*4:(114*w+x)*4+4]==bytes((48,148,255,255)) for x in range(24,w-24)),'Missing orange header rule'
 assert q('gConRows')==(h-128-8)//q('zngLineHeight'),'Console overlaps the header band'
 print('PASS real Anvil boot header:5624 exact logo pixels, banner background/rule, reserved console band.',flush=True)
 (td/'result.json').write_text(json.dumps(dict(image_sha256=meta['image_sha256'],entry=meta['entry'],breakpoint=pc,width=w,height=h,shown=shown,frames=q('zgdSequence'),font='Anvil shared TrueType boot font',symbols_sha256=hashlib.sha256((td/'symbols.json').read_bytes()).hexdigest(),header_logo_pixels=5624,glint_phase=q('zngGlintPhase'),header_console_top=128,colours=len(colours),frame_sha256=hashlib.sha256(frame).hexdigest(),exercise=a.exercise,input_transport='keyboard' if a.keyboard else 'uart',payload_marker=struct.unpack_from('<q',ram,marker)[0] if a.exercise and not a.resident else None,payload_return=q('gGoRc') if a.exercise else None,resident_sessions=len(resident_frames),resident_frame_sha256=hashlib.sha256(resident_frames[0]).hexdigest() if resident_frames else None),indent=2))
 print('PASS actual ROM-loaded counted Anvil image: shared TrueType/Neon graphical prompt, native display enabled, cell-text disabled, no Vulkan faults; screenshot '+str(td/'anvil-graphical-prompt.png'))
 if a.resident:print('PASS existing shared retained-UI service application twice: 22 assertions per session, real matching native frames, return=0, retired scopes, graphical prompt restored')
 elif a.exercise:print('PASS '+('native keyboard with Backspace editing' if a.keyboard else 'UART')+': GRAPHICS READY command, filesystem PMF application, RAM marker=1, return=42, graphical prompt restored')
if __name__=='__main__':main()
