#!/usr/bin/env python3
"""Check physical compact vertices, shared VPM bounds and raw QPU records.

Decodes captured instruction fields; never executes an emulator.
"""
from pathlib import Path
from functools import lru_cache
import argparse,json,struct
from neon_line_contract_proof_check import expected_frame
from v3d42_qpu_decode import verify_program,ProgramContract

@lru_cache(None)
def oracle():
    table=[]
    for inputs in range(17):
        for outputs in range(4,15,2):
            for vary in range(0,9,2):
                table.append(max(1,(max(inputs,outputs)+7)//8)+int(vary>0))
    return expected_frame(),struct.pack('<510I',*table)

def check_code(report):
    metadata=struct.unpack_from('<4q',report,0x1f00)
    assert metadata[1:]==(608,592,228),'Wrong captured shader lengths or record.'
    for name,start,length in [('coordinate',0x1400,608),('vertex',0x1800,592)]:
        code=verify_program(report[start:start+length],ProgramContract(name,'vertex',16))
        assert all(i.kind=='alu' for i in code),'Unexpected control flow.'
        assert sum(i.mul_op=='fmul' for i in code)==10,'Missing scalar products or viewport operations.'
        assert sum(i.add_op=='fadd/faddnf' for i in code)==8,'Missing scalar additions.'
        for i in code:
            if i.signal_addr is not None and not i.signal_magic:
                assert i.signal_addr<32,'Signal writes outside four-way registers.'
            for active,magic,dst,muxes in [(i.add_active,i.add_magic,i.add_waddr,(i.add_mux_a,i.add_mux_b)),(i.mul_active,i.mul_magic,i.mul_waddr,(i.mul_mux_a,i.mul_mux_b))]:
                if active:
                    if not magic:assert dst<32,'ALU writes outside four-way registers.'
                    if 6 in muxes:assert i.raddr_a<32,'High source register.'
                    if 7 in muxes:assert i.raddr_b<32,'High source register.'

def verify(report,pixels):
    assert len(report)==8192 and len(pixels)==131072,'Incomplete captures.'
    w=struct.unpack_from('<64I',report)
    assert w[0]==0x4157564e and w[63]==0x4e565741,'Missing report markers.'
    assert w[1]==w[21]==w[36]==0 and w[37]==w[53]==1,'Setup or teardown failure.'
    assert w[51]==1 and w[52]==0,'Unexpected fault beyond intentional refused pipeline.'
    assert struct.unpack_from('<16q',report,0x1000)==(0,8,0,0,-8,-23403,80,62,2,0,0,0,0,0,0,510),'Pipeline boundary or frame count failed.'
    assert struct.unpack_from('<q',report,0x1188)[0]==0,'Live memory remains.'
    image,table=oracle()
    assert report[0x100:0x100+len(table)]==table,'Shared segment boundary table failed.'
    assert pixels==image*8,'Reference or compact GPU pixels disagree with independent oracle.'
    assert struct.unpack_from('<I',report,0x1c04)[0]==0x01020102,'Both shared segments must fit twelve input rows.'
    assert all((struct.unpack_from('<I',report,0x1c00+off)[0]&7)==7 for off in [20,28]),'Unexpected vertex execution mode.'
    selector=struct.pack('<16f',0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,1)
    assert report[0x1200:0x1240]==selector,'Wrong corner selection.'
    for k in range(12):
        address,kind,values,lo,hi,stride,last=struct.unpack_from('<I4B2I',report,0x1c00+36+k*16)
        assert address and address%4==0 and kind==9 and values==0x11 and hi==0,'Invalid float input record.'
        assert (stride,last,lo)==((16,3,0) if k<4 else (32,7,1)),'Wrong vertex/instance addressing.'
    check_code(report)
    return dict(frames=8,rotations=[0,90,180,270],exact_gpu_bytes=131072,shared_segment_cases=510,arithmetic_nodes=16,refused_nodes=17,final_live_memory=0)

def before_witness(before,before_pixels,after):
    assert len(before)==8192 and len(before_pixels)==131072
    assert struct.unpack_from('<15q',before,0x1000)==(0,8,0,0,-8,-23403,80,62,2,0,0,0,0,0,0)
    assert struct.unpack_from('<I',before,0x1c04)[0]==0x01010101
    assert before[0x1400:0x1c00]==after[0x1400:0x1c00],'Code changed across VPM-sizing comparison.'
    frame,_=oracle();clear=struct.pack('<I',0xff1a334d)*4096
    assert all(before_pixels[i*16384:(i+1)*16384]==(frame if i%2==0 else clear) for i in range(8))
    check_code(before)

def self_test(report,pixels):
    bad=[]
    for offset in [0,4,84,144,148,204,208,212,252,4096,4104,4128,4136,4144,4152,4160,4168,4216,4488,0x100,0x104,0x100+8*4,0x100+509*4,0x1204,0x1c04,0x1c14,0x1c1c,0x1c24+8,0x1f08]:
        r=bytearray(report);r[offset]^=1;bad.append((r,pixels))
    for start in [0x1400,0x1800]:
        r=bytearray(report);r[start+28*8+5]^=8;bad.append((r,pixels))
    for frame in range(8):
        p=bytearray(pixels);p[frame*16384+4*256+4*4]^=1;bad.append((report,p))
    bad.extend([(report[:-1],pixels),(report,pixels[:-4])])
    for r,p in bad:
        try:verify(r,p)
        except (AssertionError,ValueError):continue
        raise AssertionError('A corrupt proof was accepted.')
    return len(bad)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True)
    ap.add_argument('--before-report',type=Path);ap.add_argument('--before-pixels',type=Path);ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args();r=a.report.read_bytes();p=a.pixels.read_bytes();result=verify(r,p)
    if a.before_report:
        assert a.before_pixels is not None
        before_witness(a.before_report.read_bytes(),a.before_pixels.read_bytes(),r);result['unchanged_code_before_witness']=True
    if a.self_test:result['rejected_mutations']=self_test(r,p)
    print('Shared VPM proof PASS',json.dumps(result))
