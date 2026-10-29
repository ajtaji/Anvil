"""Owned canvas filtering with actual GPU nearest/linear pixels."""
import struct
from neon_idle_wsi_scope_check import check as scope_check

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(14000,14032,8)]==[0x4e434631,0,45,1]
 expected={3:1,4:-21341,5:1,8:1,10:-21342,19:1,25:1,30:-21342,31:-21342,42:-21343,45:-21342}
 for i in range(1,46):
  row=struct.unpack_from('<3q',report,14032+(i-1)*24)
  assert row==(i,expected.get(i,0),expected.get(i,0)),(i,row)
 pixels=[q(15600+i*8) for i in range(6)]
 assert pixels[:2]==[0xffff0000,0xff0000ff],pixels
 for got,want in zip(pixels[2:4],[0xff9f0060,0xff60009f]):
  assert got>>24==255 and (got>>8)&255==0,pixels
  assert abs(((got>>16)&255)-((want>>16)&255))<=1,pixels
  assert abs((got&255)-(want&255))<=1,pixels
 assert not any(report[14032+45*24:15600]) and not any(report[15648:])
 assert pixels[4:]==[0xff00ff00,0xff00ff00],pixels
 clean=bytearray(report);clean[14000:]=bytes(2384)
 result=scope_check(clean,picture)
 result.update(filter_checks=45,nearest_pixels=pixels[:2],linear_pixels=pixels[2:4],one_pixel_samples=pixels[4:],linear_channel_tolerance=1)
 return result
