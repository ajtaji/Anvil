"""Observe real Anvil keyboard editing, clock ticks and preserved native pixels."""
import argparse,hashlib,json,re,struct,sys,time
from pathlib import Path
from zentaji_boot_session import ROOT,Session,source_pc
from zentaji_graphical_boot_check import png,assert_logo


def outside_equal(old,new,width,height,rows,line_height,clock):
 """Pixels outside independent row bands and the published clock band must survive."""
 cx,cy,cw,ch=clock
 for y in range(height):
  if y>=128 and (y-128)//line_height in rows:continue
  if 12<=y<86:
   spans=((0,width-88),(width-12,width))
  elif cy<=y<cy+ch:
   spans=((0,cx),(cx+cw,width))
  else:spans=((0,width),)
  for left,right in spans:
   at=(y*width+left)*4;end=(y*width+right)*4
   assert new[at:end]==old[at:end],('Pixels changed outside console/clock damage',y,left,right)


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--boot-proof',type=Path,required=True);ap.add_argument('--keep',type=Path,required=True)
 ap.add_argument('--reference-boot',type=Path,help='optional earlier qualified native boot, for exact static-header preservation')
 a=ap.parse_args();zt=a.zen_tools.resolve();td=a.keep.resolve();proof=a.boot_proof.resolve();td.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(zt))
 import zen_native_fixture as F
 image=ROOT/'build/zentaji/anvil.zex';raw=image.read_bytes();meta=json.loads(Path(str(image)+'.boot.json').read_text());mapping=json.loads(Path(str(image)+'.zmap').read_text())
 boot=json.loads((proof/'result.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
 assert sha(raw)==meta['image_sha256']==mapping['image']==boot['image_sha256']
 symbol_bytes=(proof/'symbols.json').read_bytes();assert sha(symbol_bytes)==boot['symbols_sha256'];symbols=json.loads(symbol_bytes)
 for source in mapping['sources']:
  path=Path(source['path']).resolve();assert path.is_relative_to(ROOT.resolve())
  assert sha(path.read_bytes().replace(b'\r',b''))==source['sha256'],path
 reference_frame=None
 if a.reference_boot:
  rp=a.reference_boot.resolve();rr=json.loads((rp/'result.json').read_text());rs=json.loads((rp/'symbols.json').read_text());ram=(rp/'final.bin').read_bytes()
  def rq(n):return struct.unpack_from('<q',ram,rs['GLOBAL_'+n.upper()])[0]
  rb,span,shown,pitch,rw,rh=[rq(n) for n in ('zgdBase','zgdSpan','zgdShown','zgdPitch','zgdWidth','zgdHeight')]
  assert (rw,rh)==(640,480)
  at=rb+shown*span;reference_frame=b''.join(ram[at+y*pitch:at+y*pitch+rw*4] for y in range(rh))
  assert sha(reference_frame)==rr['frame_sha256']
 tick=int(re.search(r'^END .* time=([0-9A-Fa-f]+)',(proof/'native.log').read_text(),re.M)[1],16)
 prompt=source_pc(mapping,ROOT/'Anvil/Core/command_loop.pbi','ReadLine()')
 frame_pc=source_pc(mapping,ROOT/'Zentaji/Board/neon_console.pbi','native monitor frame checkpoint')
 m=F.Fixture(ram_size=128<<20,cores=2,hostfiles=[['anvil.zex',bytearray(raw),False]],display_modes=[(640,480,60000)])
 def key(at,char):
  if char=='\r':usage,mods,scalar=40,0,0
  elif char=='\b':usage,mods,scalar=42,0,0
  elif char==' ':usage,mods,scalar=44,0,32
  else:usage,mods,scalar=4+ord(char.lower())-97,int(char.isupper()),ord(char)
  m.input_feed(at,'key',usage,1,mods,0,scalar);m.input_feed(at+100000,'key',usage,0,mods,0,0)
 key(tick+20000000,'X');key(tick+80000000,'\b')
 for index,char in enumerate('echo ROW TESTX\bY\r'):key(tick+140000000+index*4000000,char)
 m.power_on(0,0);m.write(td)
 frames=[];first=None;previous=None;saw_x=False;saw_undo=False;clock_frames=0;glint_frames=0;prompts=0;phases=set()
 with Session(zt,td,timeout=300) as s:
  s.breakpoint(prompt);s.breakpoint(frame_pc);first_run=True
  # The command can finish before the 2.8-second animation cycle. Keep
  # observing the idle prompt until every phase has actually been presented.
  while prompts<2 or phases!=set(range(8)):
   if not first_run:s.request('step 1')
   first_run=False;started=time.monotonic();s.request('run')
   while True:
    event=s.line()
    if event.startswith('DBG EVENT '):break
   elapsed=time.monotonic()-started
   assert 'DBG breakpoint ' in event,event
   pc=int(re.search(r'pc=\$([0-9A-Fa-f]+)',event)[1],16)
   if pc==prompt:
    prompts+=1
    if prompts==1:assert first is not None
    continue
   assert pc==frame_pc,event
   assert len(frames)<160,'Unexpected excessive repainting before the second real prompt'
   assert s.q(symbols,'zngFault')==0 and s.q(symbols,'avkFaultCount')==0
   cols,rows,lh=[s.q(symbols,n) for n in ('gConCols','gConRows','zngLineHeight')]
   mask=s.memory(symbols['GLOBAL_ZNGROWS'],rows);dirty={i for i,v in enumerate(mask) if v}
   clock=struct.unpack('<4q',s.memory(symbols['GLOBAL_ZNGBANNER']+80,32))
   cx,cy,cw,ch=clock;assert cx>=52 and (cy,ch)==(94,16) and cw>0 and cx+cw==640-76-28,clock
   frame,w,h=s.frame(symbols);assert (w,h)==(640,480)
   phase=s.q(symbols,'zngGlintPhase');phases.add(phase);assert_logo(frame,w,phase)
   glint_time=s.q(symbols,'zngGlintTime')
   if frames and phase!=frames[-1]['glint_phase']:
    assert phase==(frames[-1]['glint_phase']+1)%8
    assert glint_time-frames[-1]['glint_time_us']>=350000
   text=s.memory(symbols['GLOBAL_GCONGRID'],cols*rows).decode('ascii',errors='replace')
   cursor=s.q(symbols,'zngCursorRow');line=text[cursor*cols:(cursor+1)*cols].rstrip() if 0<=cursor<rows else ''
   draw=s.q(symbols,'nvcDrawCount');vertices=s.q(symbols,'nvcVertices')
   caption=s.memory(symbols['GLOBAL_ZNGCLOCKTEXT'],128).split(b'\0')[0].decode('utf-8')
   record=dict(index=len(frames),glint_phase=phase,glint_time_us=glint_time,dirty_rows=sorted(dirty),draws=draw,vertices=vertices,clock=clock,caption=caption,cursor_line=line,native_run_seconds=elapsed,frame_sha256=sha(frame))
   if first is None:
    assert dirty==set(range(rows));first=frame;first_draw=draw;first_vertices=vertices
    if reference_frame is not None:outside_equal(reference_frame,frame,w,92,set(),lh,(0,0,0,0))
    png(td/'anvil-boot.png',frame,w,h)
   else:
    outside_equal(previous,frame,w,h,dirty,lh,clock)
    assert s.q(symbols,'nvcContinuationPass')!=0,'Changed frames did not use the existing LOAD pass'
    if not dirty:
     assert frame!=previous,'Clock-only paint changed no displayed pixel'
     if caption!=frames[-1]['caption']:clock_frames+=1
     if phase!=frames[-1]['glint_phase']:glint_frames+=1
    if line=='pmf> X' and not saw_x:
     assert len(dirty)==1 and cursor in dirty
     assert draw<first_draw and vertices<first_vertices
     changed=sum(first[i:i+4]!=frame[i:i+4] for y in range(128+cursor*lh,128+(cursor+1)*lh) for i in range(y*w*4,(y+1)*w*4,4))
     assert changed>=16,'Typed X produced no substantive glyph ink'
     png(td/'typed-x.png',frame,w,h);saw_x=True;record['typed_x']=True
    if line=='pmf>' and saw_x and not saw_undo:
     outside_equal(first,frame,w,h,set(),lh,clock)
     png(td/'backspace-restored.png',frame,w,h);saw_undo=True;record['backspace_restored']=True
   frames.append(record);previous=frame
   print('Native monitor frame',record['index'],'rows',record['dirty_rows'],'draws',draw,'vertices',vertices,'line',repr(line),flush=True)
  assert saw_x and saw_undo and clock_frames>=1 and glint_frames>=1 and phases==set(range(8)),(saw_x,saw_undo,clock_frames,glint_frames,sorted(phases))
  assert s.q(symbols,'zngFault')==0 and s.q(symbols,'avkFaultCount')==0 and s.q(symbols,'nvcInFrame')==0 and s.q(symbols,'neon_inFrame')==0
  assert s.q(symbols,'ziUp')==1 and s.q(symbols,'ziOwned')==0 and s.q(symbols,'ziFencing')==0
  cols,rows=[s.q(symbols,n) for n in ('gConCols','gConRows')]
  text=s.memory(symbols['GLOBAL_GCONGRID'],cols*rows).decode('ascii',errors='replace');lines=[text[i*cols:(i+1)*cols].rstrip() for i in range(rows)]
  assert any('echo ROW TESTY' in line for line in lines) and 'ROW TESTY' in lines and text.rstrip().endswith('pmf>'),lines
  assert not any('TESTX' in line for line in lines),lines
  frame,w,h=s.frame(symbols);png(td/'anvil-command-prompt.png',frame,w,h);(td/'console.txt').write_text('\n'.join(lines))
 assert (td/'hostfile0.bin').read_bytes()==raw
 result=dict(image_sha256=meta['image_sha256'],static_header_pixels_verified=640*92 if reference_frame is not None else None,frames=frames,typed_x=saw_x,backspace_restored=saw_undo,clock_only_frames=clock_frames,glint_frames=glint_frames,glint_phases=sorted(phases),real_keyboard_command='echo ROW TESTX<Backspace>Y<Enter>',expected_output='ROW TESTY',application_compiled=False,physical_input=False)
 (td/'result.json').write_text(json.dumps(result,indent=2))
 print('PASS actual Anvil: preserved pixels, live clock-only frames, native keyboard X/Backspace exact restoration, corrected echo and clean prompt.',flush=True)
if __name__=='__main__':main()
