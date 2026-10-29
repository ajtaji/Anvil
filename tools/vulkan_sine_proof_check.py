"""Independent retained-record and emitted-instruction checks for GLSL Sin."""
import struct
from v3d42_qpu_decode import verify_program,ProgramContract

def check(report,cases):
 assert len(report)==16384 and len(cases)==12
 q=struct.unpack('<2048q',report);assert q[:3]==(0x53494e31,12,0),q[:3]
 results=[]
 for trial,c in enumerate(cases):
  row=q[8+trial*24:32+trial*24]
  if trial>=4:
   assert row[:6]==(c['expected'],0,-23201,0,-20001,0),(trial,row)
   assert not any(row[6:]),(trial,row)
   results.append(dict(name=c['name'],refused=row[0]));continue
  ty,ident,import_id,extended,arg=c['sub'];lanes=c['lanes'];temp=lanes+1
  assert row[:6]==(0,1,0,1,0,0x07230203),(trial,row)
  assert row[6:12]==(ident,12,ty,2,import_id,arg),(trial,row)
  assert row[12:17]==(13,ty,ident,arg,0),(trial,row)
  assert row[17]==0 and 0<row[18]<=1024 and row[18]%8==0,(trial,row)
  assert row[19:23]==(4,lanes+5,-23211,-23211),(trial,row)
  code=report[4096+trial*1024:4096+trial*1024+row[18]]
  decoded=verify_program(code,ProgramContract(c['name'],'fragment:constant-sine',4,False))
  sine=[i for i in decoded if i.add_op=='sin'];assert len(sine)==lanes
  for lane,ins in enumerate(sine):
   sequence=decoded[ins.index-3:ins.index+4]
   assert [i.add_op for i in sequence[1:]]==['fround/ftrunc','fsub','sin','ftoin','shl','xor'],(trial,sequence)
   mul=sequence[0];assert (mul.mul_op,mul.mul_waddr,mul.raddr_a,mul.raddr_b)==('fmul',1+lane,0,temp)
   expected=[(temp+2,1+lane,0),(1+lane,1+lane,temp+2),(1+lane,1+lane,0),(temp+3,temp+2,0),(temp+3,temp+3,temp+1),(1+lane,1+lane,temp+3)]
   for actual,(dest,a,b) in zip(sequence[1:],expected):
    assert (actual.add_magic,actual.add_waddr,actual.raddr_a,actual.raddr_b)==(False,dest,a,b),(trial,actual)
   # FROUND and FTOIN share opcode 245; their selectors must differ.
   assert sequence[1].add_mux_b==0 and sequence[4].add_mux_b==3
  uniform=struct.unpack_from('<4I',report,8192+trial*256)
  assert uniform==(0x3f800000,0x3ea2f983,31,0xffffffff),(trial,uniform)
  results.append(dict(name=c['name'],sine_lanes=lanes,code_bytes=row[18],register_count=row[20]))
 return dict(cases=results,scope='Physical CPU parsing and emitted instructions; GPU numeric accuracy not covered')
