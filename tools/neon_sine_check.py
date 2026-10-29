"""GPU sine colour checks using independently evaluated binary32 inputs."""
import struct,math
from neon_canvas_filter_check import check as filter_check
BITS=[[0, 1070141403, 3217625051], [1078530011, 3226013659, 1083624420], [3231108068, 1087757479, 3235241127], [1145569280, 3293052928, 1123450880], [953267991, 3100751639, 1067030938], [1069973630, 1070309175, 3217792823]]
def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,40)
 assert not any(report[15736:16128])
 pixels=struct.unpack_from('<6Q',report,16128)
 errors=[];expected=[]
 for i,(pixel,row) in enumerate(zip(pixels,BITS)):
  assert pixel>>24==255,(i,hex(pixel))
  channels=[(pixel>>16)&255,(pixel>>8)&255,pixel&255]
  for channel,bits in zip(channels,row):
   radians=struct.unpack('<f',struct.pack('<I',bits))[0]
   value=128+255*.25*math.sin(radians)
   assert abs(channel-value)<=1.0,(i,radians,channel,value)
   expected.append(value);errors.append(abs(channel-value))
 assert not any(report[16176:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(sine_pixels=list(pixels),sine_channels=18,max_channel_error=max(errors),expected_channels=expected)
 return result
