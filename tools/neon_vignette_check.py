"""Compare composed curvature, scanline and vignette equation with GPU pixels."""
import math,struct
from neon_canvas_filter_check import check as filter_check
POINTS=[(10, 7), (10, 127), (33, 7), (33, 127), (127, 127), (230, 7)]

def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,25)
 for i in range(25):assert struct.unpack_from('<2q',report,15744+i*16)==(0,0),i
 pixels=struct.unpack_from('<18Q',report,16144);errors=[];expected=[]
 for i,pixel in enumerate(pixels):
  t=[0,.125,12.5][i//6];x,y=POINTS[i%6]
  u=2*(x+.5)/256-1;v=2*(y+.5)/256-1
  k=.015*(u*u+v*v);warped_u=(u+u*k)*.5+.5;warped_v=(v+v*k)*.5+.5
  column=max(0,min(63,math.floor(64*warped_u)))
  value=(160 if column%2 else 96)-255*.04*math.sin(warped_v*800-t*10)
  radius=math.hypot(warped_u-.5,warped_v-.5)
  blend=max(0,min(1,(radius-.3)/.5))
  value*=1-blend*blend*(3-2*blend)
  assert pixel>>24==255,(i,hex(pixel))
  for shift in [0,8,16]:
   error=abs(((pixel>>shift)&255)-value)
   assert error<=1,(i,t,y,hex(pixel),value,error)
   errors.append(error)
  expected.append(value)
 assert not any(report[15736:15744]) and not any(report[16288:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(vignette_pixels=list(pixels),vignette_times=[0,.125,12.5],vignette_points=POINTS,expected_channels=expected,max_channel_error=max(errors))
 return result
