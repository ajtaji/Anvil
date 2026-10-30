"""Compile bounded graceful HTTP/2 shutdown qualification."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Procedure.i FakeDrain(handle.i)\n ProcedureReturn 1',r"""Procedure.i FakeDrain(handle.i)
 drainCalls=drainCalls+1
 If mode=30 : ProcedureReturn 0 : EndIf
 If mode=31 : ProcedureReturn -9298 : EndIf
 If mode=29 And drainCalls<=5 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1""")
 replace('Global inBytes.i,inAt.i','Global stopping.i,drainCalls.i\nGlobal inBytes.i,inAt.i')
 replace('inAt=0 : outBytes=0 :','drainCalls=0 : webpTlsDrain=@FakeDrain : If mode=32 : webpTlsDrain=0 : EndIf : stopping=0 : inAt=0 : outBytes=0 :')
 replace('eventKind.i\n','eventKind.i,limit.i,byteBefore.i,j.i,ptr.i\n')
 replace('  rc=H2ClientStep(@c,tick)',r'''  If stopping=0 And c\state=3 And ((sent=wanted And mode<>26) Or (mode=26 And c\event=#H2_DATA))
   limit=20000 : If mode=23 Or mode=30 : limit=200 : EndIf
   If mode=27
    If H2ClientDeadline(@c,1,tick,1)<>0 : rc=-9601 : Break : EndIf
   EndIf
   If mode=28
    For j=0 To 59
     ptr=h2cControl(@c,8,6,1,0) : If ptr<0 : rc=-9610 : Break : EndIf
     PokeI(ptr,0)
    Next
   EndIf
   rc=H2ClientShutdown(@c,tick,limit) : If rc<>0 : Break : EndIf
   If H2ClientShutdown(@c,tick,0)<>#H2_ARGUMENT : rc=-9602 : Break : EndIf
   If H2ClientShutdown(@c,tick+10,30000)<>0 Or c\shutdownStarted<>tick Or c\shutdownTimeout<>limit : rc=-9603 : Break : EndIf
   If H2ClientGet(@c,"/refused",8)<>#H2_STATE : rc=-9604 : Break : EndIf
   stopping=1
   If mode=24 : rc=H2ClientCancel(@c) : Break : EndIf
  EndIf
  rc=H2ClientStep(@c,tick)''')
 replace('  If rc>0\n',r'''  If rc=#H2_DRAINED
   If c\state<>5 Or c\connection\handle<>0 Or H2ClientStep(@c,tick+$10000000)<>#H2_DRAINED : rc=-9605 : Break : EndIf
   rc=0 : Break
  EndIf
  If rc>0
   If mode=26 And rc=#H2_DATA And stopping=0
    byteBefore=PeekA(c\data)
    If H2ClientShutdown(@c,tick,20000)<>0 : rc=-9606 : Break : EndIf
    stopping=1
    If H2ClientStep(@c,tick)<>#H2_DATA Or PeekA(c\data)<>byteBefore : rc=-9607 : Break : EndIf
   EndIf
''')
 replace('If busy<>#H2_BUSY And c\\goaway=0', 'If busy<>#H2_BUSY And c\\goaway=0 And c\\shutdown=0')
 replace('   If rc=#H2_GOAWAY : Break : EndIf','   If rc=#H2_GOAWAY : rc=H2ClientConsume(@c) : If rc<>0 : Break : EndIf : EndIf')
 replace('  If ended=wanted And c\\txLength=0 And c\\controlLength=0 : rc=0 : Break : EndIf','  ; Completion is H2_DRAINED, not only the last response event.')
 replace(' PokeI(p,rc) :', ' PokeI(p+96,drainCalls) : PokeI(p+72,stopping) : PokeI(p+80,c\\state) : PokeI(p+88,c\\shutdownQueued)\n PokeI(p,rc) :')
 return s

def build(compiler,out,cases=None):
 rows=json.loads((Path(__file__).parent/'h2_shutdown_cases.json').read_text()) if cases is None else cases
 assert 1<=len(rows)<=16
 build_client(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
