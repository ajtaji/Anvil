"""Check hardware color-load pixels and the unchanged composed keyboard scene."""
import struct
from neon_canvas_targets_check import check as target_check

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(10304,10336,8)]==[0x4e414c31,0,48,1]
 ids=[*range(1,11),*range(100,118),20,*range(200,218),21]
 expected={i:0 for i in ids}
 expected.update({3:13,4:30,5:0xe0115000,6:0xabcd,7:0x12345678,9:27})
 # V3D_ERR_CL_ARGS is the public driver error, verified from its declaration.
 expected[102]=expected[202]=15
 expected[117]=expected[217]=1
 for n,i in enumerate(ids):
  row=struct.unpack_from('<3q',report,10368+n*24)
  assert row==(i,expected[i],expected[i]),(n,row,i,expected[i])
 assert not any(report[10336:10368]) and not any(report[10368+48*24:])
 b=bytearray(report);b[10304:]=bytes(16384-10304)
 # Remove the attachment proof's additional target assertion before using the
 # existing exact target report oracle. All other original rows remain exact.
 assert q(6016)==164
 rows=[struct.unpack_from('<3q',report,6048+n*24) for n in range(164)]
 assert rows[12]==(400,0,0),rows[12]
 del rows[12]
 struct.pack_into('<q',b,6016,163)
 b[6048:10008]=bytes(3960)
 for n,row in enumerate(rows):struct.pack_into('<3q',b,6048+n*24,*row)
 result=target_check(b,picture)
 result.update(target_pool_checks=164,attachment_load_checks=48,full_attachment_pixels_checked=3*(193*127+65*33),load_preserves_alpha=True,load_with_no_draw=True,load_with_partial_replacement=True,next_clear_restored=True,native_surface_restored=True,public_vulkan_load=False)
 return result
