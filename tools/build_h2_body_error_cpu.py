"""Compile malformed response-body isolation and connection credit checks."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client
from build_h2_stream_window_cpu import transform as window_transform

def transform(s):
 s=window_transform(s)
 anchor=' n=inBytes-inAt : If n>bytes : n=bytes : EndIf'
 assert anchor in s
 s=s.replace(anchor,r''' If inAt=9
  at=h2cStream(@c,1)
  If at<>0
   If mode=30 : PokeI(at+OffsetOf(H2Stream\headOnly),1) : EndIf
   If mode=31 : PokeI(at+OffsetOf(H2Stream\window),1) : EndIf
  EndIf
  If mode=32 : c\window=1 : EndIf
 EndIf
'''+anchor)
 anchor=' PokeI(p+72,resetCode)'
 assert anchor in s
 s=s.replace(anchor,r''' PokeI(p+104,c\discardCredit) : PokeI(p+112,c\window)
'''+anchor)
 return s

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_body_error_cases.json').read_text())
 return build_client(compiler,out,rows,transform)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
