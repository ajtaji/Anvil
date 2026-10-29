"""Independent expected transition counts and emitted state for CPU proof."""
import struct

def check(report):
 assert len(report)==16384,'length'
 want=bytearray([0xA5]*16384)
 struct.pack_into('<2Q',want,0,0x53434131,20)
 counts=[(1,1,1),(1,1,1),(1,1,2),(2,1,2),(3,1,2),(3,2,2),(3,3,3),(3,3,3),(3,3,3),(4,4,4),(5,4,4),(6,5,5),(7,6,6),(8,7,7),(9,8,8),(10,8,8),(10,8,8),(10,8,8),(10,8,8),(10,9,9)]
 for i,(sc,ds,pc) in enumerate(counts):
  rc=201 if i==16 else 202 if i in (17,18) else 0
  faults=0 if i<9 else 1 if i==9 else 2
  x=0 if i<3 else 4 if i<10 else 5 if i<15 else 11
  width=64 if i<4 else 32 if i<15 else 16
  descriptor=1 if i<5 else 2 if i<19 else 3
  layout=1 if i<6 else 2 if i<19 else 3
  colour=0x11223344 if i<2 else 0x22334455 if i<19 else 0x33445566
  struct.pack_into('<10Q',want,256+i*80,rc,sc,ds,pc,faults,x,width,descriptor,layout,colour)
 assert report==want,'state transition/report/guard mismatch at byte '+str(next((i for i,(a,b) in enumerate(zip(report,want)) if a!=b),-1))
 return dict(cases=20,exact_bytes=16384)
