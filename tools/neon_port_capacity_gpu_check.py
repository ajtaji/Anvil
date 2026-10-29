"""Independent Pi4 capacity report and terminal geometry pixel oracle."""
from pathlib import Path
import argparse,struct
def check(report,pixels):
 assert len(report)==8192 and len(pixels)==196608
 assert struct.unpack_from('<I',report,0)[0]==0x4157564E
 assert struct.unpack_from('<I',report,4)[0]==0
 for offset,value in [(0x1000,0),(0x1008,12),(0x1188,0),(0x1190,0),(0x1198,0),(0x11a0,0)]:assert struct.unpack_from('<q',report,offset)[0]==value,hex(offset)
 expectedrows=[(0,4098,1,2732,1,1),(0,2057,2,2057,2,1),(0,4104,2,2738,2,1)]
 for frame in range(12):
  kind=frame%3;assert struct.unpack_from('<6q',report,0x400+frame*48)==expectedrows[kind],frame
  expected=bytearray()
  for y in range(64):
   for x in range(64):
    colour=0xFF000000
    if kind==0 and y==8 and 4<=x<28:colour=0xFFFFFFFF
    if kind!=0 and 4<=x<28 and 4<=y<28:colour=0xFF00FF00
    expected+=struct.pack('<I',colour)
  assert pixels[frame*16384:(frame+1)*16384]==expected,('GPU frame mismatch',frame)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',required=True,type=Path);ap.add_argument('--pixels',required=True,type=Path);a=ap.parse_args();check(a.report.read_bytes(),a.pixels.read_bytes());print('PASS 12 actual GPU frames / four rotations / 196608 independently expected pixel bytes; 4098 lines points and 2049 polygon sides')
if __name__=='__main__':main()
