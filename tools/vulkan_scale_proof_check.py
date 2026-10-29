"""Independent retained-record and emitted-byte oracle for vector scaling."""
import struct
from v3d42_qpu_decode import decode_program,verify_program,ProgramContract

def check(report,cases):
 assert len(report)==16384 and len(cases)==8
 q=struct.unpack('<2048q',report);assert q[:3]==(0x53434c31,8,0),q[:3]
 results=[]
 for trial,c in enumerate(cases):
  row=q[8+trial*24:32+trial*24]
  if trial>=4:
   assert row[:6]==(c['expected'],0,-23201,0,-20001,0),(trial,row)
   assert all(x==0 for x in row[6:]),(trial,row)
   results.append(dict(name=c['name'],refused=row[0]));continue
  ty,ident,left,right=c['sub'];lanes=c['lanes']
  assert row[:6]==(0,1,0,1,0,0x07230203),(trial,row)
  assert row[6:12]==(ident,142,ty,2,left,right),(trial,row)
  assert row[12:17]==(12,ty,ident,left,right),(trial,row)
  assert row[17]==0 and 0<row[18]<=1024 and row[18]%8==0,(trial,row)
  assert row[19:23]==(3,lanes+2,-23205,-23211),(trial,row)
  code=report[4096+trial*1024:4096+trial*1024+row[18]]
  decoded=verify_program(code,ProgramContract(c['name'],'fragment:constant-arithmetic',3,False))
  muls=[ins for ins in decoded if ins.mul_op=='fmul']
  assert len(muls)==lanes,(trial,muls)
  for lane,ins in enumerate(muls):
   assert (ins.mul_magic,ins.mul_waddr,ins.mul_mux_a,ins.mul_mux_b,ins.raddr_a,ins.raddr_b)==(False,2+lane,6,7,lane%2,1),(trial,ins)
  uniform=struct.unpack_from('<3I',report,8192+trial*256)
  assert uniform==(0xbf800000 if trial==3 else 0x3f800000,0x40000000,0xffffffff),(trial,uniform)
  results.append(dict(name=c['name'],scaled_lanes=len(muls),code_bytes=row[18],register_count=row[20],retained_after_input_destroyed=True))
 return dict(cases=results,scope='Retained parser, typed verifier and decoded QPU bytes; CPU proof on physical Pi4')
