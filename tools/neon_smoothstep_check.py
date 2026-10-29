"""GPU SmoothStep colour checks using independently evaluated binary32 inputs."""
import struct,math
from neon_canvas_filter_check import check as filter_check
BITS=[[3212836864, 1050253722, 1061997773, 0], [0, 1057803469, 1065353216, 0], [1051931443, 1053609165, 1055286886, 0], [1056964608, 1058642330, 1060320051, 0], [1061980996, 1062014550, 1050220167, 0], [1050287276, 1061158912, 1059481190, 0]]
def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,40)
 assert not any(report[15736:16128])
 pixels=struct.unpack_from('<6Q',report,16128)
 errors=[];expected=[]
 for i,(pixel,row) in enumerate(zip(pixels,BITS)):
  assert pixel>>24==255,(i,hex(pixel))
  channels=[(pixel>>16)&255,(pixel>>8)&255,pixel&255]
  edge0=struct.unpack('<f',struct.pack('<I',0x3e99999a))[0]
  edge1=struct.unpack('<f',struct.pack('<I',0x3f4ccccd))[0]
  for channel,bits in zip(channels,row[:3]):
   x=struct.unpack('<f',struct.pack('<I',bits))[0]
   t=max(0,min(1,(x-edge0)/(edge1-edge0)))
   value=128+255*.25*t*t*(3-2*t)
   assert abs(channel-value)<=1.0,(i,x,channel,value)
   expected.append(value);errors.append(abs(channel-value))
 assert not any(report[16176:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(smoothstep_pixels=list(pixels),smoothstep_channels=18,max_channel_error=max(errors),expected_channels=expected)
 return result
