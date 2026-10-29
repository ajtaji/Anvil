"""GPU distance colour checks using independently evaluated binary32 inputs."""
import struct,math
from neon_canvas_filter_check import check as filter_check
BITS=[[1048576000, 1048576000, 1048576000, 1048576000], [0, 0, 0, 0], [1057803469, 1059481190, 1048576000, 1048576000], [1048576000, 1048576000, 1057803469, 1059481190], [3175926989, 3189348762, 1048576000, 1048576000], [1036831949, 1045220557, 1050253722, 1053609165]]
def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,40)
 assert not any(report[15736:16128])
 pixels=struct.unpack_from('<6Q',report,16128)
 errors=[];expected=[]
 for i,(pixel,row) in enumerate(zip(pixels,BITS)):
  assert pixel>>24==255,(i,hex(pixel))
  channels=[(pixel>>16)&255,(pixel>>8)&255,pixel&255]
  vector=[struct.unpack('<f',struct.pack('<I',bits))[0] for bits in row]
  distance=math.sqrt(sum((v-.25)**2 for v in vector))
  value=128+255*.25*(distance-.5)
  for channel in channels:
   assert abs(channel-value)<=1.0,(i,vector,channel,value)
   expected.append(value);errors.append(abs(channel-value))
 assert not any(report[16176:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(distance_pixels=list(pixels),distance_channels=18,max_channel_error=max(errors),expected_channels=expected)
 return result
