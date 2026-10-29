"""Check public no-draw LOAD preservation plus the complete native regression."""
import struct
from neon_attachment_load_check import check as native_check

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(10304,10336,8)]==[0x4e414c31,0,62,1]
 for n,i in enumerate(range(300,314)):
  expected=-20005 if i==303 else 0
  row=struct.unpack_from('<3q',report,10368+(48+n)*24)
  assert row==(i,expected,expected),(i,row)
 assert not any(report[10368+62*24:])
 b=bytearray(report)
 struct.pack_into('<q',b,10320,48)
 b[10368+48*24:]=bytes(16384-(10368+48*24))
 result=native_check(b,picture)
 result.update(public_vulkan_load=True,public_load_scope='Empty pass only; full alpha/pixel preservation and undefined-layout refusal',public_load_checks=14,public_pixels_checked=193*127,draw_load_verified=False,engine_resume_verified=False)
 return result
