#!/usr/bin/env python3
"""Independent application-font ownership ledger and translated-raster oracle."""
from pathlib import Path
import argparse,json,struct
from PIL import Image

def check(raw,picture):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x4e464231,1,0,53),('header/assertions',q[:4])
    assert q[4]>0,'live context before scoped retirement'
    width=struct.unpack('<f',struct.pack('<I',q[5]))[0]
    assert 100<width<1000,('warm width',width)
    assert not any(raw[48:144]),'header padding'
    for n in range(53):
        a,e=struct.unpack_from('<qq',raw,144+16*n)
        assert a==e,('application check',n+1,a,e)
    assert not any(raw[144+53*16:]),'report tail'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    runs=[im.crop((50,y,800,y+64)) for y in [140,220,300]]
    assert runs[0].tobytes()==runs[1].tobytes(),'copied application font differs from independent file font'
    differences=sum(a!=b for a,b in zip(runs[0].getdata(),runs[2].getdata()))
    assert differences>1000,'application file font incorrectly falls back to embedded boot font'
    ink=[sum(any(c>0 for c in p) for p in run.getdata()) for run in runs]
    assert all(value>1500 for value in ink),('rendered glyph ink',ink)
    for x,y in [(30,30),(900,500),(60,400)]:assert im.getpixel((x,y))==(0,0,0),'clear exterior'
    return dict(passed=True,assertions=53,application_matches_preexisting=True,application_differs_from_boot=True,ink_per_run=ink,warm_width=width,scope='Real Core-copied font bytes, source reuse, explicit unload, preexisting face preservation, Close/reopen and kernel return retirement; one input font family')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
