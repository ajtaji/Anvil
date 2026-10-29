"""Check the physical fragment register-boundary report without emulation."""
import struct

def check(report, _image=None):
 assert len(report)==16384
 words=struct.unpack('<2048q',report)
 assert words[:3]==(0x46524731,5,0),words[:3]
 result=[]
 for trial,n in enumerate((6,7,8,15,16)):
  row=words[8+trial*8:16+trial*8]
  assert row[0]==n,row
  if trial<4:
   assert row[1:4]==(0,0,4+4*n),row
   assert 0<row[4]<=1024 and row[4]%8==0 and row[5]==0,row
  else:
   assert row[1:6]==(-23405,-23405,0,0,1),row
   assert row[6:]==(46,4),row
  result.append(dict(requested_registers=4+4*n,result=row[1],published_registers=row[3],code_bytes=row[4],untouched=bool(row[5])))
 return dict(cases=result,scope='CPU lowering on Pi4; no GPU execution of these boundary programs')
