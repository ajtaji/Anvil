"""Exact WSI ownership trace plus existing target/UI image oracle."""
import struct
from neon_canvas_targets_check import check as target_check
IDS=[700,701]
EXPECTED={}
for mode in range(3):
 base=710+mode*50
 for offset in range(34):
  i=base+offset;IDS.append(i);wanted=0
  if offset in (6,10,11,18,19):wanted=1
  if offset==13:wanted=-21202
  if offset==23:wanted=[0,-1000000000,-1000001004][mode]
  if offset==24:wanted=int(mode==0)
  if offset==25:wanted=int(mode!=0)
  if offset in (28,29):wanted=int(mode==0)
  EXPECTED[i]=wanted
  if mode==0 and offset==6:IDS.extend(range(850,856))
  if mode==0 and offset==29:IDS.extend([890,891])
IDS.extend(range(910,925))
IDS.extend([900,901,902,903])
for i in IDS:EXPECTED.setdefault(i,0)
EXPECTED.update({852:1,854:1,855:1,917:-21202,919:1})
assert len(IDS)==131

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
 result.update(target_pool_checks=164,wsi_continuation_checks=len(IDS),parent_pixels_checked=193*127,actual_gpu_rendering=True,actual_wsi_core=True,physical_wsi_transfer=False)
 return result
