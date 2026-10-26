#!/usr/bin/env python3
"""Independent full-frame oracle for four-rotation immediate and bulk lines."""
from fractions import Fraction as F
from pathlib import Path
import argparse
import json
import struct

# Deliberately specified input geometry, independent of vertex lowering.
SEGMENTS=((4,4,28,4),(28,8,4,8),(4,12,4,28),(8,28,8,12),
          (12,12,12,12),(20,16,52,24),(20,32,28,60),(60,44,28,36))

def contains(x,y,segment):
    a,b,c,d=segment
    if a==c and b==d:
        return a<=x<a+1 and b<=y<b+1
    if abs(c-a)>=abs(d-b):
        if not min(a,c)<=x<max(a,c):
            return False
        edge=b+(x-a)*F(d-b,c-a)
        return edge<y<edge+1
    if not min(b,d)<=y<max(b,d):
        return False
    edge=a+(y-b)*F(c-a,d-b)
    return edge<x<edge+1

def expected_frame():
    # These inputs avoid rasterizer edge ties for every sampled pixel center.
    result=bytearray()
    for y in range(64):
        for x in range(64):
            covered=any(contains(F(2*x+1,2),F(2*y+1,2),s) for s in SEGMENTS)
            result+=struct.pack('<I',0xffffffff if covered else 0xff1a334d)
    return bytes(result)

def verify(report,pixels):
    assert len(report)==8192, 'Report length is wrong.'
    words=struct.unpack_from('<64I',report)
    assert words[0]==0x4157564e and words[63]==0x4e565741, 'Report markers are wrong.'
    assert words[1]==0 and words[21]==0 and words[53]==1, 'Setup or teardown failed.'
    assert words[36]==0 and words[37]==1 and words[51]==0, 'Backend, display or validation fault.'
    assert struct.unpack_from('<2q',report,0x1000)==(0,8), 'Eight frames did not complete.'
    assert len(pixels)==131072, 'All eight complete 64x64 captures are required.'
    expected=expected_frame()
    for frame in range(8):
        assert pixels[frame*16384:(frame+1)*16384]==expected, f'Pixel mismatch at rotation {90*(frame//2)}, path {frame%2}.'
    return dict(frames=8,rotations=[0,90,180,270],paths=['immediate','bulk'],exact_gpu_bytes=131072)

def self_test(report,pixels):
    variants=[]
    for offset in (0,4,84,144,148,204,212,252,4096,4104):
        bad=bytearray(report);bad[offset]^=1;variants.append((bad,pixels))
    for frame in range(8):
        bad=bytearray(pixels);bad[frame*16384+4*256+4*4]^=1;variants.append((report,bad))
    variants.extend(((report,pixels[:-4]),(report[:-1],pixels)))
    for bad_report,bad_pixels in variants:
        try:
            verify(bad_report,bad_pixels)
        except AssertionError:
            continue
        raise AssertionError('A corrupted proof was accepted.')
    return len(variants)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--pixels',type=Path,required=True)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args();report=args.report.read_bytes();pixels=args.pixels.read_bytes()
    result=verify(report,pixels)
    if args.self_test:
        result['rejected_mutations']=self_test(report,pixels)
    print('Neon line contract PASS',json.dumps(result))
