"""Check scripted interaction through real native widgets and physical canvas output."""
from pathlib import Path
import argparse,json,struct
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('neon_canvas_ui_input_cases.json').read_text(encoding='utf8'))
def check(report,picture):
    assert len(report)==16384
    q=lambda offset:struct.unpack_from('<q',report,offset)[0]
    assert q(0)==0x4e434431 and q(8)==2
    failure,count=q(16),q(24)
    if failure:
        assert 1<=failure<=count<=len(PLAN['cases'])
        row=PLAN['cases'][failure-1];raise AssertionError((failure,row,struct.unpack_from('<2q',report,1024+16*(failure-1))))
    assert count==len(PLAN['cases'])
    for i,row in enumerate(PLAN['cases']):assert struct.unpack_from('<2q',report,1024+16*i)==(row['expected'],row['expected']),(i,row)
    assert q(32)==q(40)==q(200)==0 and q(48)==q(152)
    assert q(72)==8 and q(136)==512000 and q(144)==0
    assert [q(o) for o in [88,96,104,112,120,128]]==[800,600,107,0,1066,800]
    timings=[]
    for i in range(8):
        t=[q(256+32*i+8*k) for k in range(4)];assert 0<t[0]<t[1]<t[2]<t[3]
        ms=(t[3]-t[0])*1000/q(64);assert 0<ms<2000;timings.append(ms)
    assert 24<=q(184)<=1000 and 0<q(192)<10*q(64)
    expected=bytearray(16384)
    fixed={0:0x4e434431,8:2,24:len(PLAN['cases']),64:54000000,72:8,88:800,96:600,104:107,120:1066,128:800,136:512000,176:4096000,224:1920000}
    for off,value in fixed.items():struct.pack_into('<q',expected,off,value)
    for off in [48,152,184,192]:expected[off:off+8]=report[off:off+8]
    expected[256:512]=report[256:512]
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',expected,1024+16*i,row['expected'],row['expected'])
    assert expected==report,'unexpected report bytes'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    assert im.crop((0,0,107,800)).getbbox() is None
    assert im.crop((1173,0,1280,800)).getbbox() is None
    assert im.getpixel((680,180))==(32,160,240),'two real button activations not rendered'
    assert im.getpixel((640,760))==(33,34,37),'background'
    # Native theme's lit label is RGB(150,208,221), not neutral white.
    ink=sum(c==(150,208,221) for c in im.crop((230,175,430,205)).getdata());assert ink>30,ink
    return dict(checks=count,frames=8,button_activations=2,gpu_scanout_equal_bytes=4096000,frame_ms=timings,scope=PLAN['scope'])
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
