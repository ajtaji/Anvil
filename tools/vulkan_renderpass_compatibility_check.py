"""Physical shader/compatible-pass oracle with exact target and UI regressions."""
import struct
from neon_canvas_targets_check import check as target_check

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(10304,10336,8)]==[0x4e414c31,0,24,1]
 for n,i in enumerate(range(500,524)):
  expected=-20004 if i==519 else 0
  row=struct.unpack_from('<3q',report,10368+n*24)
  assert row==(i,expected,expected),(i,row)
 assert not any(report[10336:10368]) and not any(report[10368+24*24:])
 b=bytearray(report);b[10304:]=bytes(16384-10304)
 assert q(6016)==164
 rows=[struct.unpack_from('<3q',report,6048+n*24) for n in range(164)]
 assert rows[12]==(400,0,0);del rows[12]
 struct.pack_into('<q',b,6016,163);b[6048:10008]=bytes(3960)
 for n,row in enumerate(rows):struct.pack_into('<3q',b,6048+n*24,*row)
 result=target_check(b,picture)
 result.update(target_pool_checks=164,compatibility_checks=24,public_pixels_checked=2*194*128,application_shader_draw_load_verified=True,framebuffer_creation_pass_destroyed=True,actual_recorded_pass_destruction_refused=True,engine_resume_verified=False)
 return result
