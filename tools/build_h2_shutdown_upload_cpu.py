"""Compile upload regression with graceful shutdown already requested."""
from pathlib import Path
import argparse,json
from build_h2_upload_cpu import build as build_upload

def transform(s):
 def replace(a,b):
  nonlocal s
  assert a in s,a
  s=s.replace(a,b)
 replace('  If rc>0\n','  If rc=#H2_DRAINED : rc=0 : Break : EndIf\n  If rc>0\n')
 replace('  If ended<>0 And c\\txLength=0 And c\\controlLength=0 : rc=0 : Break : EndIf', '  ; Keep pumping until graceful close has completed.')
 replace('   submitted=1',r'''   submitted=1
   rc=H2ClientShutdown(@c,tick,100000) : If rc<>0 : Break : EndIf
   If H2ClientGet(@c,"/refused",8)<>#H2_STATE Or H2ClientRequest(@c,@request)<>#H2_STATE : rc=-9701 : Break : EndIf''')
 replace('PokeI(p+72,c\\nextStream)', 'PokeI(p+88,c\\state) : PokeI(p+96,c\\shutdownQueued) : PokeI(p+72,c\\nextStream)')
 return s

def build(compiler,out):
 build_upload(compiler,out,transform=transform)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
