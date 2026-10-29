"""Strict report and kept-display oracle for resident offscreen targets."""
import struct
from PIL import Image

IDS=list(range(1,13))+list(range(100,116))+list(range(13,93))
EXPECTED={i:0 for i in IDS}
EXPECTED.update({1:-21501,2:-21504,6:1280,7:800,9:16,10:2048,12:-21500,14:-21507,16:-21505,18:8,19:8,20:-21503,26:1,27:-21506,28:1,32:-21503,35:160,36:100,50:1280,51:800,52:-21500,54:96,55:64,59:120,60:80,65:1,71:-21500,74:-21503,81:-21506,83:-21506,85:1})
EXPECTED.update({i:1 for i in range(100,116)})
EXPECTED.update({87:-21506,89:1,90:1,92:1280})
def check(report,image):
    assert len(report)==16384
    magic,failure,count,complete=struct.unpack_from('<4Q',report)
    assert (magic,failure,count,complete)==(0x4e535431,0,len(IDS),1),(magic,failure,count,complete)
    for n,i in enumerate(IDS):
        row=struct.unpack_from('<3q',report,256+n*24)
        assert row==(i,EXPECTED[i],EXPECTED[i]),(n,row,EXPECTED[i])
    assert not any(report[32:256])
    assert not any(report[256+count*24:])
    im=Image.open(image).convert('RGB');assert im.size==(1280,800)
    points={(120,120):(255,0,0),(340,120):(0,0,255),(220,140):(255,255,0),(560,160):(0,255,0),(79,120):(0,0,0),(80,120):(255,0,0),(442,282):(0,255,0),(446,282):(0,0,255)}
    for p,rgb in points.items():assert im.getpixel(p)==rgb,(p,im.getpixel(p),rgb)
    # White antialiased glyphs are linearly sampled twice. Require substantial
    # white coverage over the red/blue source; fully white texels are not required.
    ink=sum(1 for y in range(220,280) for x in range(80,400)
            if im.getpixel((x,y))[0]>=240 and min(im.getpixel((x,y))[1:])>=96)
    assert ink>30,ink
    return dict(checks=count,pixels=len(points),filtered_white_ink_pixels=ink,scope='Resident service through pure client; no physical input actuation or nested/mid-frame target claim')
