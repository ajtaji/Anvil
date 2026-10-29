"""Check actual positive/negative texture-coordinate shifts on the GPU."""
import struct
from neon_canvas_filter_check import check as filter_check

def check(report,picture):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,25)
 for i in range(25):
  row=struct.unpack_from('<2q',report,15744+i*16)
  assert row==(0,0),(i,row)
 pixels=struct.unpack_from('<6Q',report,16240)
 assert pixels==(0xff0000ff,0xff0000ff,0xffff0000,0xffff0000,0xffff0000,0xff0000ff),pixels
 assert not any(report[15736:15744]) and not any(report[16144:16240]) and not any(report[16288:])
 clean=bytearray(report);clean[15712:]=bytes(16384-15712)
 result=filter_check(clean,picture)
 result.update(computed_uv_checks=25,offsets=[0.5,-0.5,0.0],offset_pixels=list(pixels))
 return result
