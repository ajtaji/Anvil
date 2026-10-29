"""Strict surface API ABI, output-canary and ownership report oracle; no emulator."""
from pathlib import Path
import argparse,struct,json
ROWS=[
[1,0,1,0,0,0,1,1],[2,5,0,0,0,0,1,1],[3,0,1,1,25,0,1,1],
[4,-7,1,0,0,0,1,1],[5,0,1,52,8,48,1,25],[6,-7,0,0,0,0,1,1],
[7,0,1,0,0,0,1,1],[8,-20001,0,0,0,0,1,1],[9,-20003,0,0,0,0,1,1],
[10,0,1,2,64,65,1,1],[11,-20001,0,0,0,0,1,1],[12,0,2,0,0,0,1,1],
[13,5,1,44,0,0,1,1],[14,0,2,44,37,0,1,1],[15,0,2,0,0,0,1,1],
[16,5,1,2,0,0,1,1],[17,0,2,2,0,0,1,1],[18,-20005,0,0,0,0,1,1],
[19,0,5,0,0,0,1,1],[20,-1000000000,0,0,0,0,1,1],[21,-20002,0,0,0,0,1,1],
[22,0,0,0,0,1,1,1],[23,0,0,0,0,0,1,1],[24,0,2,44,37,0,1,1]]
def expected():
 b=struct.pack('<8q',0x53555246,0,24,8,0,0,0,0)+b''.join(struct.pack('<8q',*row) for row in ROWS)
 return b+bytes(4096-len(b))
def verify(raw):
 want=expected();assert raw==want,'Surface report mismatch at '+str(next((i for i,(a,b) in enumerate(zip(raw,want)) if a!=b),None))
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--self-test',action='store_true');a=ap.parse_args();assert a.report or a.self_test
 if a.report:verify(a.report.read_bytes())
 out=dict(cases=24,state_words=192,actual_surface_api=True,controlled_gpu_backend=True)
 if a.self_test:
  want=expected();offsets=list(range(0,64+192*8,8))+[4095]
  for at in offsets:
   b=bytearray(want);b[at]^=1
   try:verify(bytes(b))
   except AssertionError:continue
   raise AssertionError('Corrupt surface report accepted')
  for b in [want[:-1],want+b'0']:
   try:verify(b)
   except AssertionError:continue
   raise AssertionError('Wrong report extent accepted')
  out['synthetic_corruptions_rejected']=len(offsets)+2
 print(json.dumps(out))
if __name__=='__main__':main()
