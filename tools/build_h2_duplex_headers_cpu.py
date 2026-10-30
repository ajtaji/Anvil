"""Compile overlapping inbound HPACK and outbound CONTINUATION qualification."""
from pathlib import Path
import argparse,json
from build_h2_upload_cpu import build as build_upload

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('Global inBytes.i,inAt.i','Global firstSent.i,overlap.i,secondStarted.i,secondFinished.i\nGlobal inBytes.i,inAt.i')
 replace('inAt=0 : outBytes=0 :','firstSent=0 : overlap=0 : secondStarted=0 : secondFinished=0 : inAt=0 : outBytes=0 :')
 replace('If mode=5', 'If mode=5 Or mode=9')
 replace('  If at+9+length>outBytes : Break : EndIf', '''  If mode=9 And NetReadBE32(@outgoing[at+5])=3
   If outBytes>=at+22 : secondStarted=1 : EndIf
   If at+9+length<=outBytes And (outgoing[at+4] & 4)<>0 : secondFinished=1 : EndIf
  EndIf
  If at+9+length>outBytes : Break : EndIf''')
 replace(' required=-1', ''' If mode=9
  If inAt>=18 And secondStarted=0 : ProcedureReturn 0 : EndIf
  If inAt>=gateAt[0] And secondFinished=0 : ProcedureReturn 0 : EndIf
 EndIf
 required=-1''')
 replace('  If rc>0\n',r'''  If rc>0
   If mode=9 And rc=#H2_FIELD And c\eventStream=1 And c\requestHeaderBytes<>0 : overlap=1 : EndIf
''')
 replace('If rc=#H2_END : ended=1', 'If rc=#H2_END : ended=ended+1')
 replace('If ended<>0 And c\\txLength=0 And c\\controlLength=0', 'If ((mode=9 And ended=2) Or (mode<>9 And ended<>0)) And c\\txLength=0 And c\\controlLength=0')
 replace('   rc=H2ClientRequest(@c,@request)\n   If rc<0 : Break : EndIf\n   If rc<>1 : rc=-9303 : Break : EndIf\n   submitted=1',r'''   If mode=9 And firstSent=0
    rc=H2ClientGet(@c,"/first",6)
    If rc<>1 : rc=-9401 : Break : EndIf
    firstSent=1
   Else
    rc=H2ClientRequest(@c,@request)
    If rc<0 : Break : EndIf
    If (mode=9 And rc<>3) Or (mode<>9 And rc<>1) : rc=-9303 : Break : EndIf
    submitted=1
   EndIf''')
 replace('PokeI(p+72,c\\nextStream)', 'PokeI(p+88,overlap) : PokeI(p+96,ended) : PokeI(p+72,c\\nextStream)')
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_duplex_headers_cases.json').read_text())
 assert len(rows)==1 and rows[0]['mode']==9
 build_upload(compiler,out,rows,transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
