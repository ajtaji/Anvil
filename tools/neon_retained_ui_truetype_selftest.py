#!/usr/bin/env python3
"""Reject corrupt metadata and image probes using an accepted physical fixture."""
from pathlib import Path
import argparse,json,functools,struct
import neon_retained_ui_truetype_check as oracle

def check(raw,frames,faces):
    # Reuse the independently rasterized masks, not comparison verdicts.
    original=oracle.reference_mask
    oracle.reference_mask=functools.lru_cache(maxsize=64)(original)
    rejected=0
    def refuses(action,label):
        nonlocal rejected
        try:action()
        except AssertionError:rejected+=1;return
        raise AssertionError(('corruption accepted',label))
    try:
        basis=oracle.check(raw,frames,faces)
        offsets=[k*4 for k in [0,1,2,3,18,19,20,21,23,51,53,63]]
        offsets += [512+k*8 for k in range(64)]
        offsets += [1024+k*8 for k in range(128) if k not in [4,5]]
        offsets += [256,504,2048,4088]
        for offset in offsets:
            bad=bytearray(raw);bad[offset]^=1
            refuses(lambda:oracle.check_metadata(bad,faces),('metadata',offset))
        for size in [0,4095,4097]:
            bad=(raw+bytes(4097))[:size]
            refuses(lambda:oracle.check_metadata(bad,faces),('length',size))
        bad=bytearray(raw);struct.pack_into('<q',bad,1024+5*8,struct.unpack_from('<q',raw,1024+4*8)[0])
        refuses(lambda:oracle.check_metadata(bad,faces),'no prewarm raster work')
        pixel_cases=0
        for frame in range(2):
            for run in oracle.text_runs(frame,faces):
                mask,(x0,y0,x1,y1),solid=oracle.reference_mask(run,stable_ink=True)
                for kind in ['ink','exterior']:
                    found=None
                    for y in range(y0,y1):
                        for x in range(x0,x1):
                            if kind=='ink':eligible=bool(solid[y*800+x])
                            else:eligible=all(mask[(y+dy)*800+x+dx]==0 for dy in [-1,0,1] for dx in [-1,0,1])
                            if eligible:found=(x,y);break
                        if found:break
                    assert found,('no independent mutation probe',frame,run[0],kind)
                    x,y=found;bad=bytearray(frames[frame]);at=y*3200+x*4
                    bad[at:at+4]=bytes([0,0,0,0]) if kind=='ink' else bytes([255,255,255,255])
                    altered=list(frames);altered[frame]=bad
                    refuses(lambda:oracle.check(raw,altered,faces),(frame,run[0],kind,x,y))
                    pixel_cases+=1
        return dict(passed=True,basis=basis,rejected_corruptions=rejected,metadata_cases=rejected-pixel_cases,pixel_cases=pixel_cases,scope='Synthetic corruption rejection on physical fixture; no new board execution')
    finally:oracle.reference_mask=original

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True);ap.add_argument('--frame0',type=Path,required=True);ap.add_argument('--frame1',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    print(json.dumps(check(a.report.read_bytes(),[a.frame0.read_bytes(),a.frame1.read_bytes()],oracle.fonts(root)),indent=2))
if __name__=='__main__':main()
