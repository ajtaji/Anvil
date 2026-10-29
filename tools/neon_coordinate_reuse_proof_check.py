#!/usr/bin/env python3
"""Check every captured coordinate word against an independent rational oracle.

This validates CPU-side descriptor transactions, not GPU execution or timing.
"""
from fractions import Fraction
from functools import cache
from pathlib import Path
import argparse,json,struct

def bits(value):
    if not value:return 0
    sign=0x80000000 if value<0 else 0;value=abs(value);exponent=0
    while value<1:value*=2;exponent-=1
    while value>=2:value/=2;exponent+=1
    scaled=value*(1<<23);mantissa=(scaled.numerator*2+scaled.denominator)//(2*scaled.denominator)
    if mantissa==(1<<24):mantissa>>=1;exponent+=1
    return sign|((exponent+127)<<23)|(mantissa&0x7fffff)

@cache
def table(size):
    return [bits(Fraction(n-size-size//2,size//2)) for n in range(size*3)]

@cache
def expected():
    # rc, active W/H, spare W/H, builds/reuses, physical W/H,
    # logical W/H, rotation, ready, surface base/pitch/bytes.
    a=(800,1280);b=(800,800);huge=(4097,8)
    rows=[(0,a,(0,0),1,0,a,a,0,1,0x3000000,3200,4096000),
          (0,b,a,2,0,b,b,0,1,0x3800000,3200,2560000),
          (0,a,b,2,1,a,a,0,1,0x3000000,3200,4096000),
          (0,b,a,2,2,b,b,0,1,0x3800000,3200,2560000),
          (2,b,a,2,2,b,b,0,1,0x3800000,3200,2560000),
          (4,b,a,2,2,b,b,0,1,0x3800000,3200,2560000),
          (0,a,b,2,3,a,(1280,800),90,1,0x3000000,3200,4096000),
          (0,huge,a,3,3,huge,huge,0,1,0x3800000,16388,131104),
          (0,a,(0,0),3,4,a,a,0,1,0x3000000,3200,4096000),
          (0,(0,0),(0,0),3,4,a,a,0,0,0x3000000,3200,4096000)]
    result=bytearray(655360);words=0
    for slot,(rc,active,spare,builds,reuses,physical,logical,rot,ready,base,pitch,length) in enumerate(rows):
        x,y=map(table,active);words+=len(x)+len(y)
        def checksum(values):
            h=2166136261
            for v in values:h=(h*33+v)&0xffffffff
            return h
        header=[rc,*active,*spare,builds,reuses,checksum(x),checksum(y),*physical,*logical,rot,ready,
                physical[1],physical[0],base,pitch,length,base,pitch,length,1,1,1,
                0x13579bdf,0x2468ace0,0x89abcdef,0x10203040,0x43525247,slot]
        assert len(header)==32
        at=slot*65536;data=struct.pack('<'+'I'*(32+len(x)+len(y)),*header,*x,*y)
        assert len(data)<=65536;result[at:at+len(data)]=data
    return bytes(result),words

def verify(data):
    want,words=expected();assert len(data)==len(want),(len(data),len(want))
    if data!=want:
        at=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
        raise AssertionError(f'slot {at//65536}, byte {at%65536}: got {data[at]:02x}, expected {want[at]:02x}')
    return dict(records=10,exact_coordinate_words=words,checked_bytes=len(data),builds=3,reuses=4,
                preflight_refusals=1,post_begin_rollback_refusals=1,gpu_execution=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--self-test',action='store_true');args=ap.parse_args();data=args.report.read_bytes();result=verify(data)
    if args.self_test:
        count=0
        # Header fields, both endpoints and an interior word in every nonempty
        # axis, guards, completion markers, zero padding and truncation.
        for slot in range(10):
            w,h=struct.unpack_from('<II',data,slot*65536+4)
            positions=[slot*65536+n*4 for n in range(32)]+[slot*65536+65535]
            at=slot*65536+128
            for dim in [w,h]:
                if dim:positions.extend([at,at+dim*6,at+dim*12-1])
                at+=dim*12
            for pos in positions:
                mutant=bytearray(data);mutant[pos]^=1
                try:verify(mutant)
                except AssertionError:count+=1
                else:raise AssertionError(f'accepted corruption at {pos}')
        try:verify(data[:-1])
        except AssertionError:count+=1
        else:raise AssertionError('accepted truncation')
        result['rejected_corruptions']=count
    print(json.dumps(result,indent=2))
