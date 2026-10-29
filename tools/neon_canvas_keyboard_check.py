"""Check real text-field keyboard semantics and the physical canvas output."""
from pathlib import Path
import argparse,json,struct
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('neon_canvas_keyboard_cases.json').read_text(encoding='utf8'))
def check(report,picture):
    assert len(report)==16384
    q=lambda o:struct.unpack_from('<q',report,o)[0]
    assert q(0)==0x4e434431 and q(8)==2
    if q(16):
        i=q(16)-1;assert 0<=i<len(PLAN['cases']);raise AssertionError((i+1,PLAN['cases'][i],struct.unpack_from('<2q',report,1024+i*16)))
    assert q(24)==len(PLAN['cases']) and q(48)==q(152)
    assert 24<=q(184)<=1000 and 0<q(192)<10*54000000
    expected=bytearray(16384)
    fixed={0:0x4e434431,8:2,24:len(PLAN['cases']),64:54000000,72:13,88:800,96:600,104:107,120:1066,128:800,136:512000,176:4096000,224:1920000}
    for o,v in fixed.items():struct.pack_into('<q',expected,o,v)
    for o in [48,152,184,192]:expected[o:o+8]=report[o:o+8]
    expected[256:672]=report[256:672];timings=[]
    for i in range(13):
        t=[q(256+i*32+k*8) for k in range(4)];assert 0<t[0]<t[1]<t[2]<t[3]
        ms=(t[3]-t[0])/54000;assert 0<ms<2000;timings.append(ms)
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',expected,1024+16*i,row['expected'],row['expected'])
    assert report==expected,'report bytes differ'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    assert im.crop((0,0,107,800)).getbbox() is None and im.crop((1173,0,1280,800)).getbbox() is None
    assert im.getpixel((680,310))==(32,160,240),'submitted final ZA state not rendered'
    assert im.getpixel((640,760))==(33,34,37),'background'
    ink=sum(min(p)>180 for p in im.crop((220,300,265,335)).getdata());assert ink>20,ink
    return dict(checks=len(PLAN['cases']),frames=13,final_text='ZA',submissions=1,final_focus=0,gpu_scanout_equal_bytes=4096000,frame_ms=timings,scope=PLAN['scope'])
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path);p.add_argument('--picture',required=True,type=Path);a=p.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
