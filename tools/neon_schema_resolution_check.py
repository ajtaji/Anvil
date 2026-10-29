"""Exact old/new schema decisions and independent handle lookup counts."""
import struct

def check(report):
 assert len(report)==16384,'report length'
 expected=bytearray([0xA5]*16384)
 struct.pack_into('<2Q',expected,0,0x53434831,20)
 results=[1,1,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0]
 calls=[6,6,1,1,1,1,1,1,1,2,3,4,5,6,0,4,6,1,1,1]
 for i,(result,count) in enumerate(zip(results,calls)):
  struct.pack_into('<4Q',expected,256+i*32,result,result,count,0 if count==0 else 1)
 assert report==expected,'schema decision/count/guard mismatch at '+str(next((i for i,(a,b) in enumerate(zip(report,expected)) if a!=b),-1))
 return dict(cases=20,exact_bytes=16384,normal_old_lookups=6,normal_new_lookups=1)
