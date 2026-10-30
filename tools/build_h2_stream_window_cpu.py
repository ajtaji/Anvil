"""Compile stream WINDOW_UPDATE error isolation on physical targets."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('eventKind.i\n','eventKind.i,ptr.i,j.i,resetCode.i,localError.i,deferred.i\n')
 replace('  If rc<0 : Break : EndIf\n',r'''  If rc<0 : Break : EndIf
  If mode=9 And deferred=0
   ptr=h2cStream(@c,1)
   If ptr<>0
    If PeekI(ptr+OffsetOf(H2Stream\deadlinePending))=1
     If H2ClientRelease(@c,1)<>#H2_BUSY : rc=-9701 : Break : EndIf
     For j=0 To 59
      ptr=h2cControl(@c,8,6,1,0) : If ptr<0 : rc=-9702 : Break : EndIf
      PokeI(ptr,$3837363534333231)
     Next
     deferred=1
    EndIf
   EndIf
  EndIf
''')
 replace('   If rc=#H2_RESET\n',r'''   If rc=#H2_RESET
    ptr=h2cStream(@c,c\eventStream)
    If ptr=0 Or c\eventStream<>1 Or c\state<>3 : rc=-9703 : Break : EndIf
    resetCode=PeekI(ptr+OffsetOf(H2Stream\resetCode))
    localError=PeekI(ptr+OffsetOf(H2Stream\localError))
''')
 replace(' H2ClientClose(@c) : PokeI(p+64,closeCalls)',r''' PokeI(p+72,resetCode) : PokeI(p+80,localError) : PokeI(p+88,deferred) : PokeI(p+96,c\state)
 H2ClientClose(@c) : PokeI(p+64,closeCalls)''')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_stream_window_cases.json').read_text())
 return build_client(compiler,out,rows,transform)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
