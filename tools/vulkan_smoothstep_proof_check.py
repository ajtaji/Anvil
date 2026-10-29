"""Independent retained-record and QPU operand checks for SmoothStep."""
import struct
from v3d42_qpu_decode import verify_program,ProgramContract
def check(report,cases):
 assert len(report)==16384 and len(cases)==12
 q=struct.unpack('<2048q',report);assert q[:3]==(0x534d5431,12,0),q[:3]
 results=[]
 for trial,c in enumerate(cases):
  row=q[8+trial*24:32+trial*24]
  if trial>=4:
   assert row[:6]==(c['expected'],0,-23201,0,-20001,0),(trial,row)
   assert not any(row[6:]),(trial,row)
   results.append(dict(name=c['name'],refused=row[0]));continue
  ty,ident,import_id,extended,left,right,x=c['sub'];lanes=c['lanes'];first=2;temp=first+lanes;const=temp+2
  assert row[:6]==(0,1,0,1,0,0x07230203),(trial,row)
  assert row[6:12]==(ident,12,ty,4,import_id,left),(trial,row)
  assert row[12:17]==(15,ty,ident,left,right),(trial,row)
  assert row[17]==0 and 0<row[18]<=1024 and row[18]%8==0,(trial,row)
  assert row[19:24]==(7,lanes+8,-23205,-23211,x),(trial,row)
  code=report[4096+trial*1024:4096+trial*1024+row[18]]
  ins=verify_program(code,ProgramContract(c['name'],'fragment:constant-smoothstep',7,False))
  for lane in range(lanes):
   f=first+lane
   expected=[('fsub',f,0,0),('fsub',temp,1,0),('recip',temp,temp,None),('nop',None,None,None),('fmul',f,f,temp),('fmax',f,f,const),('fmin',f,f,const+1),('fmul',temp,f,f),('fmul',temp+1,const+2,f),('fsub',temp+1,const+3,temp+1),('fmul',f,temp,temp+1)]
   for i,(op,dst,a,b) in enumerate(expected):
    item=ins[6+lane*11+i]
    if op=='nop':assert item.add_op==item.mul_op=='nop';continue
    if op=='fmul':assert (item.mul_op,item.mul_magic,item.mul_waddr,item.mul_mux_a,item.mul_mux_b)==(op,False,dst,6,7)
    elif op in ('fmin','fmax'):
     mux=(6,7) if op=='fmin' else (7,6)
     assert (item.add_op,item.add_magic,item.add_waddr,item.add_mux_a,item.add_mux_b)==('fmin/fmax',False,dst,*mux)
    else:
     assert (item.add_op,item.add_magic,item.add_waddr,item.add_mux_a)==(op,False,dst,6)
     if b is not None:assert item.add_mux_b==7
    assert item.raddr_a==a,(trial,i,item)
    if b is not None:assert item.raddr_b==b,(trial,i,item)
  assert struct.unpack_from('<7I',report,8192+trial*256)==(0x3f800000,0x40000000,0,0x3f800000,0x40000000,0x40400000,0xffffffff)
  results.append(dict(name=c['name'],lanes=lanes,code_bytes=row[18],register_count=row[20]))
 return dict(cases=results,scope='Physical CPU parsing and emitted instructions; GPU numeric accuracy not covered')
