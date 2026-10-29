#!/usr/bin/env python3
"""Independent immediate scrollbar state/callback and whole-raster oracle."""
from pathlib import Path
import argparse,json,struct
from PIL import Image
EXPECTED_VALUES=(80, 0, -21601, -21600, 0, -21601, 0, 0, 7, 0, 0, 7, 0, 1, 40, 0, 1, 80, 0, 1, 0, 0, 0, 0, 1, 20, 0, 0, 20, 0, 0, 1, 0, 0, 1, 80, 1, 0, 0, 0, 9, 0, 1, 40, 0, 9, 0, 0, 0, 0, 0, 50, -21600, -21600, -21600, -21600, -21600, -21600, -21600, 0, -21777, 10, 0, -21777, 1, 30, -21603, 30, 0, 0, -21602, 0, -21602, -21602, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

def check(report,picture):
    assert len(report)==4096,'report bytes'
    words=struct.unpack('<512q',report)
    assert words[:5]==(0x4e534131,1,0,len(EXPECTED_VALUES),2),words[:5]
    assert not any(words[5:34]),'unused header'
    for i,e in enumerate(EXPECTED_VALUES):
        assert words[34+i*2:36+i*2]==(e,e),(i+1,words[34+i*2:36+i*2],e)
    assert not any(report[272+len(EXPECTED_VALUES)*16:3072]),'ledger padding'
    assert not any(report[3136:]),'report tail'
    geometry=[(500,100,200,20,.129,.133,.145,1),(580,102,40,16,.31,.33,.36,1)]
    for i,row in enumerate(geometry):assert report[3072+i*32:3104+i*32]==struct.pack('<8f',*row),('callback packet',i)
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800),im.size
    # Independent screen rectangles from virtual-canvas scale 2 and thumb ratios.
    expected=Image.new('RGB',im.size,(0,0,0))
    bg=(33,34,37);thumb=(79,84,92)
    for rect,colour in [((100,120,120,440),bg),((104,260,116,340),thumb),((200,600,600,620),bg),((400,604,500,616),thumb),((800,100,840,500),bg),((1000,600,1020,620),bg),((1004,600,1016,620),thumb)]:expected.paste(colour,rect)
    if im.tobytes()!=expected.tobytes():
        for y in range(800):
            for x in range(1280):assert im.getpixel((x,y))==expected.getpixel((x,y)),(x,y,im.getpixel((x,y)),expected.getpixel((x,y)))
    return dict(checks=len(EXPECTED_VALUES),callback_packets=2,exact_pixels=1280*800,passed=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
