"""Compare original spatial/time scanline equation with GPU pixels."""
import math,struct
from neon_canvas_filter_check import check as filter_check
YS=[7,33,64,127,192,247]
def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,25)
 for i in range(25):assert struct.unpack_from('<2q',report,15744+i*16)==(0,0),i
 pixels=struct.unpack_from('<18Q',report,16144);errors=[];expected=[]
 for i,pixel in enumerate(pixels):
  t=[0,.125,12.5][i//6];y=YS[i%6]
  value=128-255*.04*math.sin((y+.5)/256*800-t*10)
  assert pixel>>24==255,(i,hex(pixel))
  for shift in [0,8,16]:
   error=abs(((pixel>>shift)&255)-value)
   assert error<=1,(i,t,y,hex(pixel),value,error)
   errors.append(error)
  expected.append(value)
 assert not any(report[15736:15744]) and not any(report[16288:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(scanline_pixels=list(pixels),scanline_times=[0,.125,12.5],scanline_rows=YS,expected_channels=expected,max_channel_error=max(errors))
 return result
