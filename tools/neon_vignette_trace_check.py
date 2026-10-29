"""Check the captured combined fragment program's cached-one register."""
import struct
from v3d42_qpu_decode import decode_program
def check(blob):
 assert len(blob)==12288
 magic,size,words,registers=struct.unpack_from('<4q',blob)
 assert magic==0x54524331 and 0<size<=1024 and size%8==0
 assert 1<=words<=64 and 1<=registers<=64
 ins=decode_program(blob[256:256+size])
 cached_one=struct.unpack_from('<q',blob,1536+61*4*8)[0]
 assert struct.unpack_from('<q',blob,7712+61*8)[0]==1
 assert struct.unpack_from('<I',blob,1280+3*4)[0]==0x3f800000
 assert ins[17].signals==frozenset({'ldunifrf'}) and ins[17].signal_addr==cached_one
 for i in ins[18:]:
  assert i.signal_magic or i.signal_addr!=cached_one,(i.index,'signal overwrites cached one')
  assert i.add_magic or i.add_waddr!=cached_one,(i.index,'add overwrites cached one')
  assert i.mul_magic or i.mul_waddr!=cached_one,(i.index,'multiply overwrites cached one')
 assert ins[22].add_op=='fadd/faddnf' and not ins[22].add_magic
 assert ins[22].add_waddr!=cached_one
 return dict(code_bytes=size,uniform_words=words,register_count=registers,cached_one_register=cached_one,dot_accumulator=ins[22].add_waddr,cached_one_survives=True)
