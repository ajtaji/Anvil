"""RAM-only all-scene status and full-pixel qualification (no display claim)."""
import struct,hashlib
from pathlib import Path
from vulkan_neon_all15_corpus_check import corpus_from_slab,GOLDEN,EXPECTED_SHA

def check(report,slab):
 assert len(report)==16384,'report length'
 words=struct.unpack('<64I',report[:256])
 expected={0:0x4157564e,1:0,2:9,3:256,17:0,18:0,19:0,20:1,21:0,22:0,23:1,36:0,51:0,53:1,62:3505,63:0x4e565741}
 for slot,value in expected.items():assert words[slot]==value,f'report slot {slot}: {words[slot]} != {value}'
 assert report[256:]==bytes(len(report)-256),'report tail guard'
 candidate=corpus_from_slab(slab)
 reference=Path(__file__).resolve().parents[1]/'docs/evidence/neon-atlas-shared-pi4-20261026/all15-slab.bin'
 ref=reference.read_bytes()
 assert hashlib.sha256(ref).hexdigest()=='509caea582bc61f0b0710dd7d3aa73a46ac9902c8803aafe70ae490e6e3bee43','current contract reference integrity'
 current=corpus_from_slab(ref)
 historic=GOLDEN.read_bytes()
 assert hashlib.sha256(historic).hexdigest()==EXPECTED_SHA,'historical native integrity'
 for scene in range(15):
  start=scene*16384;end=start+16384
  if scene not in (4,5):assert current[start:end]==historic[start:end],f'non-line reference drift {scene}'
  assert candidate[start:end]==current[start:end],f'current contract scene {scene} differs'
 count=len(candidate)
 return dict(exact_bytes=count,scenes=15,capacity_boxes=words[62],shutdown=words[53],scope='All 15 current-contract scenes exact; 13 also historical native exact; line scenes 4/5 use accepted October 26 reference. No fresh native, display/input or sustained timing claim')
