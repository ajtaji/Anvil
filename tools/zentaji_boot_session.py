"""Observe the real native debugger; fixtures and reads execute no Python CPU."""
import hashlib,json,os,queue,struct,subprocess,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def monitor(zen_tools):
 import zasm_ref
 path=ROOT/'build/zentaji/anvil.zex';raw=path.read_bytes()
 meta=json.loads(Path(str(path)+'.boot.json').read_text());mapping=json.loads(Path(str(path)+'.zmap').read_text())
 assert hashlib.sha256(raw).hexdigest()==meta['image_sha256']==mapping['image']
 for source in mapping['sources']:
  p=Path(source['path']);assert p.resolve().is_relative_to(ROOT.resolve()),p
  assert hashlib.sha256(p.read_bytes().replace(b'\r',b'')).hexdigest()==source['sha256'],p
 asm=zasm_ref.Asm();asm.assemble(Path(str(path)+'.compiled.asm').read_text(encoding='utf-8-sig'))
 return raw,meta,mapping,asm.sym

def source_pc(mapping,source,needle):
 source=source.resolve();line=next(i for i,row in enumerate(source.read_text().splitlines(),1) if needle in row)
 return next(int(row['pc'],16) for row in mapping['code'] if row['line']==line and Path(row['source']).resolve()==source)

class Session:
 def __init__(self,zen_tools,folder,timeout=900):
  self.folder=Path(folder);self.lines=[];self.replies=queue.Queue();self.deadline=time.monotonic()+timeout
  exe=Path(zen_tools)/('zenemu.exe' if os.name=='nt' else 'zenemu')
  self.process=subprocess.Popen([str(exe),str(self.folder/'machine.txt'),'--debug-stdio','--ram',str(self.folder/'final.bin')],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=0x08000000 if os.name=='nt' else 0)
  def reader():
   for row in self.process.stdout:self.replies.put(row)
   self.replies.put(None)
  self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
 def line(self):
  while time.monotonic()<self.deadline:
   try:row=self.replies.get(timeout=1)
   except queue.Empty:continue
   assert row is not None,('Native debugger exited',self.process.poll(),''.join(self.lines)[-3000:])
   self.lines.append(row);return row
  raise TimeoutError('Native session exceeded its observation deadline')
 def send(self,command):self.process.stdin.write(command+'\n');self.process.stdin.flush()
 def request(self,command):
  self.send(command);row=self.line();assert not row.startswith('error:'),row;return row
 def breakpoint(self,pc):return self.request(f'break 0 ${pc:X}')
 def run_to(self,pc,step=False):
  if step:self.request('step 1')
  self.request('run')
  while True:
   row=self.line()
   if row.startswith('DBG EVENT '):break
  assert 'DBG breakpoint ' in row and f'pc=${pc:X}' in row,row
 def memory(self,address,count):
  requests=[f'memory ${address+i:X} {min(256,count-i)}' for i in range(0,count,256)]
  self.process.stdin.write('\n'.join(requests)+'\n');self.process.stdin.flush();out=bytearray()
  for i in range(0,count,256):
   row=self.line();fields=row.split();assert fields[:2]==['DBG','MEMORY'] and int(fields[2][1:],16)==address+i,row
   data=bytes.fromhex(' '.join(fields[3:]));assert len(data)==min(256,count-i),row;out.extend(data)
  return bytes(out)
 def q(self,symbols,name):return struct.unpack('<q',self.memory(symbols['GLOBAL_'+name.upper()],8))[0]
 def frame(self,symbols):
  base,span,shown,pitch,w,h=[self.q(symbols,n) for n in ['zgdBase','zgdSpan','zgdShown','zgdPitch','zgdWidth','zgdHeight']]
  assert 0<=shown<3 and pitch>=w*4
  raw=self.memory(base+shown*span,pitch*h)
  return b''.join(raw[y*pitch:y*pitch+w*4] for y in range(h)),w,h
 def __enter__(self):
  assert self.line().strip()=='DBG READY 1';return self
 def __exit__(self,kind,value,trace):
  p=self.process
  try:
   if p.poll() is None:
    self.send('quit');p.stdin.close();p.wait(timeout=30)
   self.reader.join(timeout=10)
  finally:
   if p.poll() is None:p.kill();p.wait(timeout=10)
   while not self.replies.empty():
    row=self.replies.get_nowait()
    if row is not None:self.lines.append(row)
   (self.folder/'native.log').write_text(''.join(self.lines))
  if kind is None:assert p.returncode==0,p.returncode
