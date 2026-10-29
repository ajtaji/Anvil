"""Compare CRT curvature sampling against the original radial equation."""
import math,struct
from neon_canvas_filter_check import check as filter_check
POINTS=[(10,7),(10,127),(33,7),(33,127),(230,7),(230,127)]
def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,25)
 for i in range(25):assert struct.unpack_from('<2q',report,15744+i*16)==(0,0),i
 expected=[];texels=[]
 for coefficient in [0.015,-0.015,0.0]:
  for x,y in POINTS:
   u=2*(x+0.5)/256-1;v=2*(y+0.5)/256-1
   warped=(u+u*(u*u+v*v)*coefficient)*0.5+0.5
   texel=max(0,min(63,math.floor(64*warped)));texels.append(texel)
   expected.append(0xff0000ff if texel%2 else 0xffff0000)
 pixels=struct.unpack_from('<18Q',report,16144);assert pixels==tuple(expected),(pixels,expected,texels)
 assert not any(report[15736:15744]) and not any(report[16288:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(curvature_coefficients=[0.015,-0.015,0.0],curvature_pixels=list(pixels),expected_texel_columns=texels,curvature_api_checks=25)
 return result
