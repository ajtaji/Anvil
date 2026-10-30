"""Qualify bounded connection-error GOAWAY using fragmented, stalled and failed I/O."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Procedure.i FakeDrain(handle.i)\n ProcedureReturn 1',r"""Procedure.i FakeDrain(handle.i)
 If c\state=#H2_STATE_ERROR_DRAIN
  drainCalls=drainCalls+1
  If mode=21 : ProcedureReturn -9298 : EndIf
  If mode=22 Or drainCalls<=4 : ProcedureReturn 0 : EndIf
 EndIf
 ProcedureReturn 1""")
 replace('Global inBytes.i,inAt.i', 'Global drainCalls.i,drainSeen.i,originalError.i,drainRecv.i,partialOffset.i,refused.i\nGlobal inBytes.i,inAt.i')
 replace('inAt=0 : outBytes=0 :','drainCalls=0 : webpTlsDrain=@FakeDrain : drainSeen=0 : originalError=0 : drainRecv=0 : partialOffset=0 : refused=0 : inAt=0 : outBytes=0 :')
 replace(' Define i.i,n.i\n sendCalls=',r'''
 Define i.i,n.i
 If c\state=#H2_STATE_ERROR_DRAIN
  If mode=11 : ProcedureReturn 0 : EndIf
  If mode=12 : ProcedureReturn -9299 : EndIf
 EndIf
 sendCalls=''')
 replace('  rc=H2ClientStep(@c,tick)',r'''
  If (mode=17 Or mode=18) And c\state=3 And sent=1 And c\txLength=0 And c\controlLength=0 And c\shutdown=0
   rc=H2ClientShutdown(@c,tick,1000) : If rc<>0 : Break : EndIf
  EndIf
  If c\state=#H2_STATE_ERROR_DRAIN And drainSeen=0
   drainSeen=1 : originalError=c\error : drainRecv=recvCalls : partialOffset=c\txOffset
   refused=H2ClientGet(@c,"/forbidden",10)
   If mode=10
    For i=0 To 59
     at=h2cControl(@c,8,6,1,0)
     For st=0 To 7 : PokeA(at+st,49+st) : Next
    Next
   EndIf
   If mode=11 : c\timeout=tick+8 : EndIf
   If mode=22 : c\timeout=tick+80 : EndIf
   If mode=23 : webpTlsDrain=0 : EndIf
   If mode=13 : forceClosed=1 : EndIf
   If mode=14 : rc=H2ClientCancel(@c) : Break : EndIf
   If mode=15 : H2ClientClose(@c) : rc=0 : Break : EndIf
   If mode=16 : c\errorSteps=65536 : EndIf
   If mode=18 : rc=H2ClientStep(@c,c\shutdownStarted+c\shutdownTimeout) : Break : EndIf
  EndIf
  rc=H2ClientStep(@c,tick)''')
 replace(' PokeI(p,rc)',r'''
 PokeI(p+160,drainCalls)
 PokeI(p+72,drainSeen) : PokeI(p+80,originalError) : PokeI(p+88,drainRecv) : PokeI(p+96,recvCalls)
 PokeI(p+104,partialOffset) : PokeI(p+112,c\shutdownQueued) : PokeI(p+120,c\errorSteps) : PokeI(p+128,c\state) : PokeI(p+136,refused)
 PokeI(p,rc)''')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_error_goaway_cases.json').read_text())
 return build_client(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
