"""Validate sample properties, retained handles, refusals and snapshot guards."""
import struct
def check(report):
    if len(report)!=81920:raise ValueError('length')
    b=report[65536:];expected=bytearray([0xa5])*16384
    magic,count,base,image,sampler,view,rewrite,reuse=struct.unpack_from('<8Q',b)
    if (magic,count)!=(0x534e5031,22):raise ValueError('completion')
    if not 0x06200000<=base<0x06300000 or base%4096:raise ValueError('allocation')
    if not min(image,sampler,view,rewrite,reuse)>0 or len({sampler,rewrite,reuse})!=3:raise ValueError('handle generations')
    struct.pack_into('<8Q',expected,0,magic,count,base,image,sampler,view,rewrite,reuse)
    sample=(base,64,1,1,64,44,5,1,0,1,0,1,1)
    for row in range(22):
        at=512+row*512;valid=row in (0,17,18,21)
        struct.pack_into('<QQ',expected,at,int(valid),int(valid))
        if row!=16:
            values=sample if valid else (0,)*13
            struct.pack_into('<13Q',expected,at+64,*values)
            struct.pack_into('<13Q',expected,at+256,*values)
        if row!=17:
            refs=(image,rewrite if row==18 else reuse if row==21 else sampler,view) if valid else (0,0,0)
            struct.pack_into('<3Q',expected,at+192,*refs)
    if b!=expected:
        bad=[i for i,(x,y) in enumerate(zip(b,expected)) if x!=y]
        raise ValueError(('snapshot data/guards',len(bad),bad[:8]))
    return dict(cases=22,guarded_bytes=16384,public_setup=True,stale_generation_and_rewrite=True)
