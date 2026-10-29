#!/usr/bin/env python3
"""Check legacy loader BMP regression, automatic PNG output and resident copies."""
from pathlib import Path
import argparse,json,struct
from PIL import Image
from neon_service_asset_app_check import check as bmp_check
PLAN=json.loads(Path(__file__).with_name('neon_image_dispatch_cases.json').read_text(encoding='utf8'))
def check(raw,picture):
    assert len(raw)==8192
    q=lambda off:struct.unpack_from('<q',raw,off)[0]
    assert (q(64),q(72),q(80))==(len(PLAN['cases']),0,0x4e494431)
    assert q(88)>0 and q(96)>q(88)
    legacy=bytearray(raw[:4096]);legacy[64:104]=b'\0'*40
    result=bmp_check(legacy,picture)
    for i,row in enumerate(PLAN['cases']):
        assert struct.unpack_from('<2q',raw,4096+i*16)==(row['expected'],row['expected']),row
    rgba=bytes.fromhex(PLAN['rgba']);assert len(rgba)==572
    mask=bytes(int(rgba[i]>0) for i in range(3,len(rgba),4))
    assert raw[6144:6716]==rgba and raw[6720:6863]==mask
    tail=bytearray(raw[4096:])
    for first,last in [(4096,4096+len(PLAN['cases'])*16),(6144,6716),(6720,6863)]:
        tail[first-4096:last-4096]=b'\0'*(last-first)
    assert not any(tail),'unused extended report bytes'
    im=Image.open(picture).convert('RGB');pixels=0
    for origin in [600,760]:
        for y in range(11):
            for x in range(13):
                r,g,b,a=rgba[(y*13+x)*4:(y*13+x+1)*4]
                expected=tuple(round((v*a+base*(255-a))/255) for v,base in zip((r,g,b),(0,0,255)))
                for yy in range(8):
                    for xx in range(8):
                        actual=im.getpixel((origin+x*8+xx,300+y*8+yy))
                        assert max(abs(v-w) for v,w in zip(actual,expected))<=1,('PNG',origin,x,y,actual,expected)
                        pixels+=1
    result.update(scope=PLAN['scope'],legacy_bmp_checks=133,decoder_checks=len(PLAN['cases']),png_rgba_bytes=572,png_mask_bytes=143,png_pixel_checks=pixels)
    return result
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
