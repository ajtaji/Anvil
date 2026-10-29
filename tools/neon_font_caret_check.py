"""Check fixed and proportional caret pixels against independent positions."""
from pathlib import Path
import json,struct
EXPECTED=json.loads(Path(__file__).with_name('neon_font_caret_expected.json').read_text())
PROPORTIONAL=json.loads(Path(__file__).with_name('neon_font_caret_proportional.json').read_text())
def check(report,picture,pixels):
 assert len(report)==16384 and len(pixels)==122912
 assert struct.unpack_from('<I',report,4)[0]==0,'Scene failed'
 assert struct.unpack_from('<4q',report,512)==(0x43465031,1,0,len(EXPECTED))
 for i,want in enumerate(EXPECTED):
  actual,expected=struct.unpack_from('<2q',report,1024+i*16)
  assert (actual,expected)==(want,want),(i+1,actual,expected,want)
 assert not any(report[1024+len(EXPECTED)*16:])
 assert pixels[:16]==b'\xa5'*16 and pixels[-16:]==b'\xa5'*16
 green=bytes([0,255,0,255]);white=bytes([255,255,255,255])
 marker_rows=[list(range(0,193,32)),[(q*2+32768)//65536 for q in PROPORTIONAL['positions_q16']]]
 for row,positions in enumerate(marker_rows):
  start=16+row*61440
  left,right=pixels[start:start+30720],pixels[start+30720:start+61440]
  assert left==right,('Text/caret crop differs from independent positions',row)
  for col,position in enumerate(positions):
   for y in [28,29]:
    for x in [position,position+1]:
     assert left[(y*240+x)*4:(y*240+x)*4+4]==green,(row,col,x,y)
  assert sum(left[i:i+4]==white for i in range(0,28*240*4,4))>30,('Missing text',row)
 return dict(checks=len(EXPECTED),equal_crop_bytes=61440,markers=14,
             proportional_pairs=PROPORTIONAL['pair_adjustments'],
             frame_raster_upload_delta=0,scope='Actual Vulkan fixed/proportional text and caret markers; no physical input routing claim')
