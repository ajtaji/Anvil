"""Verify ordered GPU clears within LOAD and refusal atomicity on the Pi."""
import struct
from vulkan_attachment_load_check import check as empty_check

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(10304,10336,8)]==[0x4e414c31,0,105,1]
 for n,i in enumerate(range(400,443)):
  expected=-20004 if i in (409,438) else 0
  row=struct.unpack_from('<3q',report,10368+(62+n)*24)
  assert row==(i,expected,expected),(i,row)
 assert not any(report[10368+105*24:])
 b=bytearray(report);struct.pack_into('<q',b,10320,62)
 b[10368+62*24:]=bytes(16384-(10368+62*24))
 result=empty_check(b,picture)
 result.update(public_load_checks=57,public_pixels_checked=193*127+5*194*128,ordered_clear_load_verified=True,whole_clear_override_verified=True,reset_load_restored=True,wrong_layout_submit_refused=True,stale_framebuffer_submit_refused=True,refused_pixels_unchanged=True,application_shader_draw_load_verified=False,engine_resume_verified=False)
 return result
