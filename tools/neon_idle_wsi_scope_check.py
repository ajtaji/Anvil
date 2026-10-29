"""Exact idle WSI scope trace and rendered target oracle."""
import struct
from neon_canvas_targets_check import check as target_check
IDS=[950,951]
EXPECTED={}
for mode in range(4):
 base=1000+mode*50
 for offset in range(33):
  if mode==3 and offset==25:IDS.extend([1183,1184])
  i=base+offset;IDS.append(i);wanted=0
  if offset==8:wanted=2
  if offset in (9,16):wanted=1
  if offset==10:wanted=int(mode==1)
  if offset==11:wanted=-21202
  if offset==15:wanted=int(mode!=1)
  if offset==18 and mode>=2:wanted=-1000000000
  if offset==20:wanted=2 if mode>=2 else 0
  if offset==21:wanted=int(mode>=2)
  if offset==22:wanted=int(mode<2)
  if offset==23 and mode>=2:wanted=-1000000000
  if offset==24 and mode>=2:wanted=1
  if offset==27:wanted=int(mode<2)
  EXPECTED[i]=wanted
  if mode==0 and offset==28:IDS.extend([890,891])
IDS.extend([1200,1201,1202,1203])
for i in IDS:EXPECTED.setdefault(i,0)
assert len(IDS)==142

def check(report,picture):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert [q(o) for o in range(10304,10336,8)]==[0x4e414c31,0,len(IDS),1]
 for n,i in enumerate(IDS):
  row=struct.unpack_from('<3q',report,10368+n*24)
  assert row==(i,EXPECTED[i],EXPECTED[i]),(i,row,EXPECTED[i])
 assert not any(report[10336:10368]) and not any(report[10368+len(IDS)*24:])
 b=bytearray(report);b[10304:]=bytes(16384-10304)
 assert q(6016)==164
 rows=[struct.unpack_from('<3q',report,6048+n*24) for n in range(164)]
 assert rows[12]==(400,0,0);del rows[12]
 struct.pack_into('<q',b,6016,163);b[6048:10008]=bytes(3960)
 for n,row in enumerate(rows):struct.pack_into('<3q',b,6048+n*24,*row)
 result=target_check(b,picture)
 result.update(target_pool_checks=164,idle_wsi_scope_checks=len(IDS),parent_pixels_checked=193*127,actual_gpu_rendering=True,actual_wsi_core=True,physical_wsi_transfer=False)
 return result
