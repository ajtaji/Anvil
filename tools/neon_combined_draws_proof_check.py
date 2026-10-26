#!/usr/bin/env python3
"""Check physical 6144-draw capacity, smaller caller limits and GPU pixels."""
import argparse
import json
from pathlib import Path
import struct

EXPECTED=(0,4096,2048,6144,36864,0,-21203,1,0,6144,2,12,6142,-21203,1,0,6144)

def verify(report,pixels):
    assert len(report)==8192, 'Full native report required.'
    w=struct.unpack_from('<64I',report)
    assert w[0]==0x4157564e and w[63]==0x4e565741, 'Wrong report markers.'
    assert w[1]==0 and w[21]==0 and w[53]==1, 'Setup or teardown failed.'
    assert w[36]==0 and w[37]==1 and w[51]==0, 'Backend, display or validation fault.'
    assert struct.unpack_from('<17q',report,0x1000)==EXPECTED, 'Capacity, refusal atomicity, reuse or final teardown failed.'
    assert len(pixels)==32768, 'Two full 64x64 captures required.'
    glyph=report[0x1800:0x1810]
    expected=bytearray()
    for y in range(64):
        for x in range(64):
            colour=0xff00ff00 if x<8 and y<16 and glyph[y]&(0x80>>x) else 0xffff0000
            expected+=struct.pack('<I',colour)
    for y in range(64):
        for x in range(64):
            colour=0xff0000ff if x==0 and y==0 else 0xffffffff if x==1 and y==0 else 0xff1a334d
            expected+=struct.pack('<I',colour)
    assert pixels==expected, 'GPU bytes differ from independent opaque-colour and input-glyph oracle.'
    return dict(mixed_draws=6144,flat_calls=4096,textured_calls=2048,refused_next_draw=True,smaller_limit_preserved=2,exact_gpu_bytes=32768,final_memory_allocations=0,final_free_draw_records=6144)

def self_test(report,pixels):
    variants=[]
    for off in [0,4,84,144,148,204,212,252]+list(range(0x1000,0x1088,8)):
        bad=bytearray(report);bad[off]^=1;variants.append((bad,pixels))
    for off in [0,2048,16384,32767]:
        bad=bytearray(pixels);bad[off]^=1;variants.append((report,bad))
    variants.extend(((report,pixels[:-4]),(report[:-1],pixels)))
    for r,p in variants:
        try:
            verify(r,p)
        except AssertionError:
            continue
        raise AssertionError('Corrupted proof accepted.')
    return len(variants)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--pixels',type=Path,required=True)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args();report=args.report.read_bytes();pixels=args.pixels.read_bytes()
    result=verify(report,pixels)
    if args.self_test:result['rejected_mutations']=self_test(report,pixels)
    print('Neon combined draws PASS',json.dumps(result))
