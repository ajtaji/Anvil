#!/usr/bin/env python3
"""Verify physical Neon triangle-fan and capability-masked fallback evidence."""
from pathlib import Path
import argparse,json,struct

def verify(report,pixels,masked=False):
    assert len(report)==8192, 'Complete native report required.'
    w=struct.unpack_from('<64I',report)
    assert w[0]==0x4157564e and w[63]==0x4e565741, 'Report markers differ.'
    assert w[1]==0 and w[21]==0 and w[53]==1, 'Setup or teardown did not complete.'
    assert w[36]==0 and w[37]==1 and w[51]==int(masked), 'Unexpected backend, display or validation status.'
    mode=0 if masked else 1
    assert struct.unpack_from('<10q',report,0x1000)==(0,mode,8,27-mode*4,9-mode*4,(2-mode)*6,0 if mode else -20005,0,0,6 if mode else 0), 'Vertex cost, tight refusal, capability validation or retirement failed.'
    assert len(pixels)==131072, 'Eight complete GPU frames required.'
    expected=bytearray()
    for frame in range(8):
        for y in range(64):
            for x in range(64):
                word=0xff1a334d
                if 4<=x<28 and 4<=y<28:word=0xff00ff00
                if frame%2==0 and x<4 and y<4:word=0xffff0000
                if frame%2==0 and (32<=x<40 or 48<=x<56) and 32<=y<40:word=0xff0000ff
                expected+=struct.pack('<I',word)
    assert pixels==expected, 'GPU output differs from the independent complete rectangle oracle.'
    return dict(fan_capability=bool(mode),rotations=[0,90,180,270],frames=8,fan_vertices=9-mode*4,tight_capacity=(2-mode)*6,exact_gpu_bytes=131072,final_memory=0,final_pipelines=0)

def self_test(report,pixels,masked):
    variants=[]
    for off in [0,4,84,144,148,204,212,252]+list(range(0x1000,0x1050,8)):
        bad=bytearray(report);bad[off]^=1;variants.append((bad,pixels))
    for frame in range(8):
        bad=bytearray(pixels);bad[frame*16384+8*256+8*4]^=1;variants.append((report,bad))
    variants.extend(((report[:-1],pixels),(report,pixels[:-4])))
    for r,p in variants:
        try:verify(r,p,masked)
        except AssertionError:continue
        raise AssertionError('Corrupted proof accepted.')
    return len(variants)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--pixels',type=Path,required=True)
    ap.add_argument('--masked',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args();report=args.report.read_bytes();pixels=args.pixels.read_bytes()
    result=verify(report,pixels,args.masked)
    if args.self_test:result['rejected_mutations']=self_test(report,pixels,args.masked)
    print('Neon triangle fan PASS',json.dumps(result))
