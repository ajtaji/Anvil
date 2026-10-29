"""Check physical register lifetime observations against fixed expectations."""
import struct
EXPECTED=[0,1,0,1,4,1,0,1,1,1,16,14,24,28,0,4,0,1,14,28,-23405,-23405,-23405,10,12,0,0,17,1,24,1,2,1,1,0,0]
def check(report):
 assert len(report)==16384
 assert struct.unpack_from('<3q',report)==(0x52555331,len(EXPECTED),0)
 for i,value in enumerate(EXPECTED):
  assert struct.unpack_from('<2q',report,64+i*16)==(value,value),i
 assert not any(report[24:64]) and not any(report[64+len(EXPECTED)*16:4096]) and not any(report[4120:])
 from v3d42_qpu_decode import decode_program
 ins=decode_program(report[4096:4120])
 for i,dest in enumerate([14,15]):
  assert (ins[i].mul_op,ins[i].mul_magic,ins[i].mul_waddr,ins[i].raddr_a,ins[i].raddr_b)==('fmul',False,dest,18+i,18+i)
 assert (ins[2].add_op,ins[2].add_magic,ins[2].add_waddr,ins[2].raddr_a,ins[2].raddr_b)==('fadd/faddnf',False,17,14,15)
 return dict(checks=len(EXPECTED),live_aliases_preserved=True,dead_values_and_scratch_reused=True,constants_and_deferred_output_retained=True,register_limit_enforced=True,legacy_allocation_preserved=True)
