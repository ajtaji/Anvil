"""Retained typed coordinate and emitted texture request qualification."""
import struct
from v3d42_qpu_decode import verify_program,ProgramContract

def check(report,cases):
 assert len(report)==16384 and len(cases)==8
 q=struct.unpack('<2048q',report);assert q[:3]==(0x55564331,8,0),q[:3]
 results=[]
 for trial,c in enumerate(cases):
  row=q[8+trial*24:32+trial*24]
  if trial>=4:
   assert row[:6]==(c['expected'],0,-23201,0,-20001,0),(trial,row)
   assert all(x==0 for x in row[6:]),(trial,row)
   results.append(dict(name=c['name'],refused=row[0]));continue
  ty,ident,sampler,coord=c['sample']
  assert row[:6]==(0,1,0,1,0,0x07230203),(trial,row)
  assert row[6:12]==(ident,87,ty,2,sampler,coord),(trial,row)
  assert row[12:17]==(5,ty,ident,sampler,coord),(trial,row)
  assert row[17]==0 and 0<row[18]<=1024 and row[18]%8==0,(trial,row)
  assert row[21:23]==(-23205,-23211),(trial,row)
  count=5 if trial in (1,2) else 3
  assert row[19]==count,(trial,row)
  code=report[4096+trial*1024:4096+trial*1024+row[18]]
  decoded=verify_program(code,ProgramContract(c['name'],'fragment:computed-sampled',count,False))
  requests=[i for i in decoded if i.add_magic and i.add_waddr in (34,33)]
  assert len(requests)==2,(trial,requests)
  expected=[(13,12),(17,16),(15,14),(12,13)][trial]
  for ins,reg in zip(requests,expected):
   assert ins.add_mux_a==6 and ins.raddr_a==reg,(trial,ins,reg)
  uniform=struct.unpack_from('<%dI'%count,report,8192+trial*256)
  wanted=((0x3e800000,0x3f000000) if count==5 else ())+(0x200000,0x200100,0xffffffff)
  assert uniform==wanted,(trial,uniform)
  results.append(dict(name=c['name'],code_bytes=row[18],register_count=row[20],retained_after_input_destroyed=True))
 return dict(cases=results,scope='Retained coordinate data flow and decoded texture request; physical CPU proof')
