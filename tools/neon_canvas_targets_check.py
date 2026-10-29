"""Validate actual multi-target GPU colors, lifecycle and unchanged keyboard output."""
import struct
from neon_canvas_keyboard_check import check as keyboard_check
def check(report,picture):
    assert len(report)==16384
    q=lambda o:struct.unpack_from('<q',report,o)[0]
    ids=[*range(1,5),*range(200,208),*range(5,24),*range(300,329),*range(330,333),*range(60,72),*range(50,58),*range(24,40),*range(80,85),*range(40,50),*range(100,132),*range(140,157)]
    expected={i:0 for i in ids}
    for i in [6,7,9,10,11,12,33,131]:expected[i]=-21342
    for i in [24,26]:expected[i]=-21341
    for i in [61,62,63,68,69]:expected[i]=-21343
    for i in [5,15,16,25,31,42]:expected[i]=1
    for i in [302,303,304,307,308]:expected[i]=-21342
    expected[300]=expected[332]=-21202
    expected[311]=expected[317]=6
    expected[321]=2
    expected[313]=expected[319]=4294967040
    expected[205]=4278190335;expected[207]=4278190335
    expected.update({18:4294901760,23:4278255360,28:97,29:65,39:4278255360,47:4294901760,55:4294901760,57:4278255360,84:4278255360})
    assert q(6000)==0x4e435431 and q(6008)==0 and q(6016)==163 and q(6024)==1,(q(6008),q(6016))
    for n,i in enumerate(ids):
        row=struct.unpack_from('<3q',report,6048+n*24)
        assert row==(i,expected[i],expected[i]),(n,row,i,expected[i])
    assert not any(report[6032:6048]) and not any(report[6048+163*24:16384])
    original=bytearray(report);original[6000:16384]=bytes(10384)
    result=keyboard_check(original,picture)
    result.update(target_pool_checks=163,retained_small_targets=16,cross_target_sampled_pixels=5,blank_first_and_odd_tail_texels=True,scoped_float_particle_and_abort=True,external_rebind_staleness_preserved=True,scope='GPU offscreen target lifecycle, resize, multi-target sampling and scripted keyboard scene. No resident offscreen service or physical input claim.')
    return result

if __name__=='__main__':
    from pathlib import Path
    import argparse,json
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--picture',type=Path,required=True)
    args=ap.parse_args()
    print(json.dumps(check(args.report.read_bytes(),args.picture),indent=2))
