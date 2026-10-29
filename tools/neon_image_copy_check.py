"""Independent two-pass GPU report and exact final sampled-pixel oracle."""
from pathlib import Path
import argparse,json,struct
PLAN=json.loads(Path(__file__).with_name('neon_image_copy_cases.json').read_text(encoding='utf8'))
def check(report,pixels):
    assert len(report)==16384
    wanted=bytearray(16384)
    for off,val in [(0,0x4e494331),(8,1),(24,len(PLAN['cases']))]:struct.pack_into('<q',wanted,off,val)
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',wanted,256+16*i,row['expected'],row['expected'])
    assert report==wanted,'literal checks, status, unused bytes or report size'
    assert len(pixels)==163840
    expected=bytearray()
    for phase in range(2):
        for y in range(64):
            for x in range(320):
                colour=0xff000000
                if x<64:colour=0xffff0000 if phase==0 else 0xff0000ff
                elif x<128:colour=0xff00ff00 if phase==0 else 0xffffff00
                elif 160<=x<224:colour=0xffff0000
                elif 224<=x<288:colour=0xff00ff00
                expected+=struct.pack('<I',colour)
    assert pixels==expected,'GPU copied/sampled pixels or untouched clear regions'
    return {'passed':True,'checks':len(PLAN['cases']),'sampled_pixels':40960,'scope':PLAN['scope']}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.pixels.read_bytes()),indent=2))
if __name__=='__main__':main()
