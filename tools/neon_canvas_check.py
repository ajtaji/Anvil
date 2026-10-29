"""Literal canvas lifecycle and independent full-image letterbox oracle."""
from pathlib import Path
import argparse,json,struct
PLAN=json.loads(Path(__file__).with_name('neon_canvas_cases.json').read_text(encoding='utf8'))
def expected_pixels():
    out=bytearray();tolerance=bytearray()
    for rotation in [0,90,180,270]:
        for y in range(240):
            for x in range(320):
                colour=0xff000000;blend=False;local=None;extent=None
                if rotation in [0,180] and 40<=y<200:
                    local=x if rotation==0 else 319-x;extent=320
                elif rotation in [90,270] and 100<=x<220:
                    local=y if rotation==90 else 239-y;extent=240
                if local is not None:
                    # Texel centres: u*64-0.5. Only the red/green join has
                    # differing neighbours; compute its ideal bilinear weight.
                    denominator=2*extent
                    numerator=max(0,min(denominator,(2*local+1)*64-63*extent))
                    green=(255*numerator+denominator//2)//denominator
                    colour=0xff000000|((255-green)<<16)|(green<<8)
                    blend=0<numerator<denominator
                out+=struct.pack('<I',colour)
                tolerance+=bytes([0,int(blend),int(blend),0])
    return bytes(out),bytes(tolerance)
_PIXELS,_TOLERANCE=expected_pixels()
def check(report,pixels):
    assert len(report)==16384
    wanted=bytearray(16384)
    for off,val in [(0,0x4e435631),(8,1),(24,len(PLAN['cases']))]:struct.pack_into('<q',wanted,off,val)
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',wanted,256+i*16,row['expected'],row['expected'])
    if report!=wanted:
        i=next(i for i,(a,b) in enumerate(zip(report,wanted)) if a!=b)
        raise AssertionError(('report mismatch',i,report[i],wanted[i]))
    assert len(pixels)==len(_PIXELS)
    errors=[abs(a-b) for a,b in zip(pixels,_PIXELS)]
    assert all(e<=t for e,t in zip(errors,_TOLERANCE)),'full sampled attachment/rotation/letterbox/linear-filter mismatch'
    return {'passed':True,'checks':len(PLAN['cases']),'checked_pixels':307200,'rotations':4,'max_channel_error':max(errors),'filter':'linear min/mag, clamp-to-edge','tolerance':'one UNORM level only in interpolated red/green transition channels; other bytes exact','scope':PLAN['scope']}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.pixels.read_bytes()),indent=2))
if __name__=='__main__':main()
