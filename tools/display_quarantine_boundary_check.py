"""Execute actual board quarantine boundaries with named hardware-only stubs."""
import argparse,os,pathlib,re,subprocess,sys,tempfile
import screen_shot_emitted_check as shot
import build_count
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/a64'))
from a64_interp import A64
LOAD,STACK,RETURN=0x400000,0x3000000,0x7000000
BOARD=ROOT/'RaspberryPi4/Board'
def main():
 p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
 base=shot.FIXTURE.read_text().split('; @@BODY@@')[0]
 extra='''
Global gate_denied.i
Global gate_hw.i
Global gScrDsiStep.i
Global gScrDsiLine0.i
Global gScrDsiLine1.i
Dim gCurSave.i[4]
Dim gCurMask.i[2]
#CUR_W=2
#CUR_H=2
#CUR_COLOUR=123
#MON_FB_BYTES=384
#I2C_BUS_DISPLAY=0
#I2C_BUS_HEADER=1
Procedure.i DisplayMemorySafe() : ProcedureReturn Bool(gate_denied=0) : EndProcedure
Procedure.i DisplayBase() : ProcedureReturn #MON_FB_SCAN : EndProcedure
Procedure MmuCleanRange(a.i,n.i) : gate_hw=gate_hw+1 : EndProcedure
'''
 extra+='\n'.join(l for l in shot.SOURCE.read_text().splitlines() if l.startswith('#SCR_DSI_STEP'))+'\n'
 # These device leaves are explicit successful models. Any call is counted;
 # quarantine must reach none, while the positive reinit must reach HvsFill.
 funcs={'DsiDomainOn':0,'I2cSelectBus':1,'I2cUp':0,'DsiV2Begin':0,'DsiPanelRails':0,'DsiV2Backlight':1,'DsiModePlan':1,'DsiClocksSet':0,'DsiHostBringUp':0,'DsiIsUp':0,'DsiPanelPrepare':0,'DsiPanelSent':0,'HvsFill':4,'HvsMirror':2,'HvsUp':3,'PvUp':8,'PvEnable':0,'DsiVideoOn':0,'PvVideoOn':0,'DsiHsyncS':0,'DsiHsyncE':0,'DsiHtotal':0,'delay':1}
 for name,n in funcs.items():
  if re.search(r'Procedure(?:\.i)? '+name+r'\(',base,re.I):continue
  extra+=f"Procedure.i {name}({', '.join('p'+str(i)+'.i' for i in range(n))})\n gate_hw=gate_hw+1\n ProcedureReturn 1\nEndProcedure\n"
 extra+='Procedure.i HvsChannelLine() : gate_hw=gate_hw+1 : ProcedureReturn gate_hw : EndProcedure\n'
 specs=[(shot.SHOTARM,'ShotNextSeq'),(shot.SHOTARM,'ShotSeq')]+[(shot.GEOM,n) for n in ['ScrSideways','ScrLogicalW','ScrLogicalH','ScrMapX','ScrMapY','ScrCapturePixel']]+[(shot.SOURCE,n) for n in ['ScrCaptureSnapshot','ScrCaptureToArea','ScrDsiBringUp']]+[(BOARD/'banner_clock.pi4','PresentedOverlayPixel')]+[(BOARD/'cursor_input.pi4',n) for n in ['CursorSave','CursorRestore','CursorDraw']]
 bodies='\n'.join(shot.procedure(path,name) for path,name in specs)
 tail='''
Procedure Main()
 ScrCaptureToArea(1,0,0)
 ScrDsiBringUp()
 PresentedOverlayPixel(#MON_FB_SCAN,32,0,8,12,0,0,123)
 CursorSave(0,0)
 CursorRestore(0,0)
 CursorDraw(0,0)
EndProcedure
'''
 with tempfile.TemporaryDirectory(prefix='display-quarantine-') as td:
  def run(text):
   source=pathlib.Path(td)/'fixture.pi4';image=pathlib.Path(td)/'fixture.img';source.write_text(text)
   r=subprocess.run([a.compiler,'--compile',str(source),'-t','pi4','--entry-returns','--load-addr',hex(LOAD),'--bss-addr','0x800000','--stack-addr',hex(STACK),'-s','-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
   if r.returncode!=0 or not image.exists():raise RuntimeError(r.stdout+r.stderr)
   build_count.record_build(source,'pi4',image,by='tools/display_quarantine_boundary_check.py',compiler=a.compiler)
   syms={k:int(v,0) for k,v in (l.split('=',1) for l in pathlib.Path(str(image)+'.sym').read_text().splitlines() if '=' in l)}
   c=A64();c.memory.update({LOAD+i:b for i,b in enumerate(image.read_bytes())});access=[]
   ld,st=c.load,c.store
   def load(addr,size):
    if 0x7000000<=addr<0x7200000:access.append(('r',addr))
    return ld(addr,size)
   def store(addr,val,size):
    if 0x7000000<=addr<0x7200000:access.append(('w',addr))
    st(addr,val,size)
   c.load,c.store=load,store
   def put(name,v):st(syms['global_'+name.lower()],v,8)
   def get(name):return ld(syms['global_'+name.lower()],8)
   def call(name,*args):
    c.pc=LOAD+syms[name.lower()];c.sp=STACK;c.x[30]=RETURN
    for i,v in enumerate(args):c.x[i]=v
    for _ in range(300000):
     if c.pc==RETURN:return c.x[0]
     c.step()
    raise RuntimeError('boundary failed to return')
   put('gate_denied',1);put('gScrSrc',2);put('gScrDsiUp',1)
   put('gate_hdmiW',8);put('gate_hdmiH',12);put('gate_hdmiPitch',32)
   put('gCurMask',128)
   assert call('ScrCaptureToArea',1,0,0)==0
   assert call('ScrDsiBringUp')==0
   call('PresentedOverlayPixel',0x7000000,32,0,8,12,0,0,123)
   for name in ('CursorSave','CursorRestore','CursorDraw'):call(name,0,0)
   assert not access and get('gate_hw')==0,'quarantine allowed framebuffer or device access'
   put('gate_denied',0)
   assert call('ScrDsiBringUp')==1 and get('gate_hw')>0
   assert call('ScrCaptureToArea',1,0,0)==1
   call('PresentedOverlayPixel',0x7000000,32,0,8,12,0,0,123)
   assert any(kind=='w' for kind,addr in access)
  run(base+extra+bodies+tail)
  print('PASS: board capture/reinit/overlay/cursor refusal and positive controls execute.')
  # Each removed entry guard must be detected independently.
  for path,name in [(shot.SOURCE,'ScrCaptureToArea'),(shot.SOURCE,'ScrDsiBringUp'),(BOARD/'banner_clock.pi4','PresentedOverlayPixel'),(BOARD/'cursor_input.pi4','CursorRestore'),(BOARD/'cursor_input.pi4','CursorSave'),(BOARD/'cursor_input.pi4','CursorDraw')]:
   proc=shot.procedure(path,name)
   changed=re.sub(r'  If DisplayMemorySafe\(\) = 0(?: : ProcedureReturn 0 : EndIf|\n    ProcedureReturn\n  EndIf)','',proc,count=1)
   assert proc!=changed
   try:run(base+extra+bodies.replace(proc,changed)+tail)
   except AssertionError:print('PASS: removed '+name+' guard rejected.')
   else:raise AssertionError(name+' mutation escaped')
if __name__=='__main__':main()
