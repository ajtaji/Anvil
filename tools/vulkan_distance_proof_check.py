"""Independent retained-record and emitted-instruction checks for Distance."""
import struct
from v3d42_qpu_decode import verify_program,ProgramContract

def check(report,cases):
 assert len(report)==16384 and len(cases)==12
 q=struct.unpack('<2048q',report);assert q[:3]==(0x44535431,12,0),q[:3]
 results=[]
 for trial,c in enumerate(cases):
  row=q[8+trial*24:32+trial*24]
  if trial>=4:
   assert row[:6]==(c['expected'],0,-23201,0,-20001,0),(trial,row)
   assert not any(row[6:]),(trial,row)
   results.append(dict(name=c['name'],refused=row[0]));continue
  ty,ident,import_id,extended,left,right=c['sub'];lanes=c['lanes'];acc=lanes+2
  assert row[:6]==(0,1,0,1,0,0x07230203),(trial,row)
  assert row[6:12]==(ident,12,ty,3,import_id,left),(trial,row)
  assert row[12:17]==(14,ty,ident,left,right),(trial,row)
  assert row[17]==0 and 0<row[18]<=1024 and row[18]%8==0,(trial,row)
  assert row[19:23]==(3,lanes+3,-23205,-23211),(trial,row)
  code=report[4096+trial*1024:4096+trial*1024+row[18]]
  decoded=verify_program(code,ProgramContract(c['name'],'fragment:constant-arithmetic',3,False))
  for lane in range(lanes):
   sub,mul=decoded[2+lane*2:4+lane*2]
   assert (sub.add_op,sub.add_magic,sub.add_waddr,sub.add_mux_a,sub.add_mux_b,sub.raddr_a,sub.raddr_b)==('fsub',False,2+lane,6,7,0,1)
   assert (mul.mul_op,mul.mul_magic,mul.mul_waddr,mul.mul_mux_a,mul.mul_mux_b,mul.raddr_a,mul.raddr_b)==('fmul',False,2+lane,6,7,2+lane,2+lane)
  at=2+lanes*2;copy=decoded[at]
  assert (copy.add_op,copy.add_waddr,copy.add_mux_a,copy.add_mux_b,copy.raddr_a)==('or',acc,6,6,2)
  for lane in range(1,lanes):
   add=decoded[at+lane]
   assert (add.add_op,add.add_waddr,add.raddr_a,add.raddr_b)==('fadd/faddnf',acc,acc,2+lane)
  rsqrt,nop,recip,nop2=decoded[at+lanes:at+lanes+4]
  for ins,op in [(rsqrt,'rsqrt'),(recip,'recip')]:
   assert (ins.add_op,ins.add_magic,ins.add_waddr,ins.add_mux_a,ins.raddr_a)==(op,False,acc,6,acc)
  assert nop.add_op==nop.mul_op==nop2.add_op==nop2.mul_op=='nop'
  assert struct.unpack_from('<3I',report,8192+trial*256)==(0x3f800000,0x40000000,0xffffffff)
  results.append(dict(name=c['name'],distance_lanes=lanes,code_bytes=row[18],register_count=row[20]))
 return dict(cases=results,scope='Physical CPU parsing and emitted instructions; GPU numeric accuracy not covered')
