"""Compile adversarial duplex exchanges using the shared WebClient fixture."""
from pathlib import Path
import argparse,json
from build_web_auto_cpu import build as build_auto

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Global inBytes.i,inAt.i','Global stalled.i,held.i,heldAt.i,advanced.i\nGlobal inBytes.i,inAt.i')
 replace('Define i.i,n.i\n sendCalls=', '''Define i.i,n.i,at.i,length.i
 If mode>=24 And inAt<inBytes
  at=24
  While at+9<=outBytes
   length=(outgoing[at]<<16)|(outgoing[at+1]<<8)|outgoing[at+2]
   If outgoing[at+3]=0 And outBytes>=at+22 And outBytes<at+9+length
    stalled=1
    If mode=25 : ProcedureReturn -110 : EndIf
    ProcedureReturn 0
   EndIf
   If at+9+length>outBytes : Break : EndIf
   at=at+9+length
  Wend
 EndIf
 sendCalls=''')
 replace('recvCalls=recvCalls+1 :', '''If mode>=24 And inAt>=18 And stalled=0 : ProcedureReturn 0 : EndIf
 If mode=28 And inAt>=18 : ProcedureReturn 0 : EndIf
 recvCalls=recvCalls+1 :''')
 replace('inAt=0 : outBytes=0 :','stalled=0 : held=0 : heldAt=0 : advanced=0 : inAt=0 : outBytes=0 :')
 replace('Or mode=23 : method=', 'Or mode=23 Or mode>=24 : method=')
 replace('If mode=13 : timeout=250','If mode>=24 : timeout=2000 : EndIf\n If mode=13 : timeout=250')
 replace('   rc=WebClientStep(@client,',r'''   If mode=26 And c\event=#H2_DATA And held<20
    If held=0 : heldAt=outBytes : EndIf
    capacity=0 : held=held+1
   EndIf
   rc=WebClientStep(@client,''')
 replace('   position=position+client\\consumed', r'''   If mode=26 And held=20 And outBytes>heldAt : advanced=1 : EndIf
   If mode=29 And stalled<>0 : rc=WebClientCancel(@client) : EndIf
   position=position+client\consumed''')
 replace('PokeI(p+176,client\\sent)', 'PokeI(p+200,stalled) : PokeI(p+224,advanced) : PokeI(p+232,c\\window) : PokeI(p+240,c\\controlLength) : PokeI(p+176,client\\sent)')
 replace('wireAt=p+512\n If outBytes>16384 : wireAt=$E1CE0000 : EndIf','wireAt=$E1C40000+index*100000')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_duplex_cases.json').read_text())
 assert len(rows)==7 and [r['mode'] for r in rows]==list(range(24,31))
 build_auto(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
