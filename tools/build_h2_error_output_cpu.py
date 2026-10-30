"""Fail a connection while real request frames are partially transmitted."""
from pathlib import Path
import argparse,json
from build_h2_upload_cpu import build as build_upload

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Global inBytes.i,inAt.i','Global seen.i,partialOffset.i,headerBytes.i,drainRecv.i,outAtError.i\nGlobal inBytes.i,inAt.i')
 replace('inAt=0 : outBytes=0 :','seen=0 : partialOffset=0 : headerBytes=0 : drainRecv=0 : outAtError=0 : inAt=0 : outBytes=0 :')
 replace('If mode=5','If mode=5 Or mode=9')
 replace('required.i,kind.i,flags.i','required.i,kind.i,flags.i,partialReady.i')
 replace('  If at+9+length>outBytes : Break : EndIf',r'''
  If at+9+length>outBytes
   If outBytes>at+9
    If mode=0 And outgoing[at+3]=0 : partialReady=1 : EndIf
    If (mode=5 Or mode=9) And outgoing[at+3]=1 : partialReady=1 : EndIf
   EndIf
   Break
  EndIf''')
 replace(' required=-1',' If inAt>=9 And partialReady=0 : ProcedureReturn 0 : EndIf\n required=-1')
 replace('  pet() : rc=H2ClientStep(@c,tick)',r'''
  If c\state=#H2_STATE_ERROR_DRAIN And seen=0
   seen=1 : partialOffset=c\txOffset : headerBytes=c\requestHeaderBytes : drainRecv=recvCalls : outAtError=outBytes
   If mode=9
    For i=0 To 59
     p=h2cControl(@c,8,6,1,0)
     For n=0 To 7 : PokeA(p+n,49+n) : Next
    Next
   EndIf
  EndIf
  pet() : rc=H2ClientStep(@c,tick)''')
 replace(r'If submitted<>0 And request\state<>2 And ended=0',r'If c\state=3 And submitted<>0 And request\state<>2 And ended=0')
 replace(' PokeI(p,rc)',r'''
 PokeI(p+88,partialOffset) : PokeI(p+96,headerBytes) : PokeI(p+104,drainRecv) : PokeI(p+112,recvCalls)
 PokeI(p+120,seen) : PokeI(p+128,c\error) : PokeI(p+136,c\state) : PokeI(p+144,outAtError)
 PokeI(p,rc)''')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_error_output_cases.json').read_text())
 return build_upload(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
