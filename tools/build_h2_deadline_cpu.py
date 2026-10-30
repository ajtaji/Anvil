"""Compile physical per-stream deadline tests using the shared H2 fixture."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Global inBytes.i,inAt.i', 'Global baseTime.i,nowTick.i,held.i,resetMask.i,deadlineErrors.i,queueDeferred.i\nGlobal inBytes.i,inAt.i')
 replace('inAt=0 : outBytes=0 :', 'baseTime=0 : nowTick=0 : held=0 : resetMask=0 : deadlineErrors=0 : queueDeferred=0 : inAt=0 : outBytes=0 :')
 replace('eventKind.i\n', 'eventKind.i,ptr.i,j.i,oldByte.i\n')
 replace('  pet()\n', '  pet() : nowTick=(baseTime+tick) & $FFFFFFFF\n')
 replace('H2ClientStep(@c,tick)', 'H2ClientStep(@c,nowTick)')
 replace('  If rc>0\n',r'''  If mode=17 And queueDeferred=0
   ptr=h2cStream(@c,1)
   If ptr<>0
    If PeekI(ptr+OffsetOf(H2Stream\deadlinePending))=1
     If H2ClientRelease(@c,1)<>#H2_BUSY : rc=-9501 : Break : EndIf
     queueDeferred=1
    EndIf
   EndIf
  EndIf
  If rc>0
   If held=0 And c\eventStream=1 And ((mode=11 And rc=#H2_DATA) Or (mode=12 And rc=#H2_FIELD))
    If rc=#H2_DATA : oldByte=PeekA(c\data) : Else : oldByte=PeekA(c\name) : EndIf
    st=rc
    If H2ClientDeadline(@c,1,nowTick,1)<>0 : rc=-9502 : Break : EndIf
    baseTime=baseTime+2 : nowTick=nowTick+2
    If H2ClientStep(@c,nowTick)<>st : rc=-9503 : Break : EndIf
    If st=#H2_DATA
     If PeekA(c\data)<>oldByte : rc=-9504 : Break : EndIf
    Else
     If PeekA(c\name)<>oldByte : rc=-9504 : Break : EndIf
    EndIf
    If H2ClientRelease(@c,1)<>#H2_BUSY : rc=-9505 : Break : EndIf
    held=1 : rc=st
   EndIf
''')
 replace('   If rc=#H2_RESET\n',r'''   If rc=#H2_RESET
    resetMask=resetMask|(1<<c\eventStream)
    ptr=h2cStream(@c,c\eventStream)
    If ptr=0 : rc=-9506 : Break : EndIf
    If PeekI(ptr+OffsetOf(H2Stream\localError))<>#H2_TIMEOUT Or PeekI(ptr+OffsetOf(H2Stream\resetCode))<>8 : rc=-9507 : Break : EndIf
    deadlineErrors=deadlineErrors+1
''')
 # The retained deadline-expired stream is no longer active; its cancel call is STATE.
 replace('    If H2ClientCancelStream(@c,c\\eventStream)<>#H2_BUSY : rc=-9206 : Break : EndIf',r'''    busy=H2ClientCancelStream(@c,c\eventStream)
    If held<>0 And c\eventStream=1
     If busy<>#H2_STATE : rc=-9206 : Break : EndIf
    Else
     If busy<>#H2_BUSY : rc=-9206 : Break : EndIf
    EndIf''')
 replace('    sent=sent+1\n',r'''    sent=sent+1
    If sent=2
     If mode=10 Or mode=16 Or mode=17
      If H2ClientDeadline(@c,1,nowTick,1)<>0 : rc=-9508 : Break : EndIf
     EndIf
     If mode=16
      If H2ClientDeadline(@c,3,nowTick,1)<>0 : rc=-9509 : Break : EndIf
     EndIf
     If mode=13 Or mode=14
      If H2ClientDeadline(@c,1,nowTick,1)<>0 : rc=-9510 : Break : EndIf
      If H2ClientDeadline(@c,1,nowTick,-1)<>#H2_ARGUMENT Or H2ClientDeadline(@c,99,nowTick,1)<>#H2_STATE : rc=-9511 : Break : EndIf
      n=0 : If mode=14 : n=10000 : EndIf
      If H2ClientDeadline(@c,1,nowTick,n)<>0 : rc=-9512 : Break : EndIf
     EndIf
     If mode=15
      baseTime=$FFFFFFFE-tick : nowTick=$FFFFFFFE : c\started=nowTick
      If H2ClientDeadline(@c,1,nowTick,3)<>0 : rc=-9513 : Break : EndIf
     EndIf
     If mode=17
      For j=0 To 59
       ptr=h2cControl(@c,8,6,1,0)
       If ptr<0 : rc=-9514 : Break : EndIf
       PokeI(ptr,0)
      Next
     EndIf
    EndIf
''')
 replace('eventKind.i,ptr.i,j.i,oldByte.i', 'eventKind.i,ptr.i,j.i,oldByte.i,n.i')
 replace('PokeI(p+64,closeCalls)', 'PokeI(p+64,closeCalls) : PokeI(p+72,resetMask) : PokeI(p+80,deadlineErrors) : PokeI(p+88,held) : PokeI(p+96,queueDeferred)')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_deadline_cases.json').read_text())
 assert len(rows)==8 and [r['mode'] for r in rows]==list(range(10,18))
 build_client(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
