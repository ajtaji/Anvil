"""Check the physical kept image, complete GPU/scanout word equality and frame timings."""
from pathlib import Path
import argparse,json,statistics,struct,hashlib
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('neon_canvas_display_cases.json').read_text(encoding='utf8'))
def check(report,picture):
    assert len(report)==16384
    failure,count=struct.unpack_from('<2q',report,16)
    if failure:
        if 1<=failure<=count<=len(PLAN['cases']):
            row=PLAN['cases'][failure-1];actual,wanted=struct.unpack_from('<2q',report,1024+16*(failure-1))
            raise AssertionError(('device check refused',failure,row['label'],actual,wanted))
        raise AssertionError(('device refusal',failure,count))
    assert count==len(PLAN['cases']),'incomplete device check sequence'
    image=Image.open(picture).convert('RGB');assert image.size==(1280,800)
    expected=bytearray(16384)
    fixed={0:0x4e434431,8:2,24:len(PLAN['cases']),64:54000000,72:3,80:48,88:800,96:600,104:107,112:0,120:1066,128:800,176:4096000,224:1920000}
    for off,val in fixed.items():struct.pack_into('<q',expected,off,val)
    words,mismatches=struct.unpack_from('<2q',report,136)
    assert words==512000 and mismatches==0,'GPU/scanout BGRA word equality'
    before=struct.unpack_from('<q',report,152)[0];after=struct.unpack_from('<q',report,48)[0]
    assert 0<=before==after<32,'new Vulkan teardown fault'
    assert hashlib.sha256(image.tobytes()).hexdigest()=='de97dd26942c1a9b6f6bc65e7b461ceb49d7e0c1f786d033626a6795afac6c7d','kept RGB image differs from pre-optimization hardware reference'
    vertices=struct.unpack_from('<q',report,184)[0];assert 600<=vertices<=2000
    create=struct.unpack_from('<q',report,192)[0];assert 0<create<10*54000000
    for off in [48,136,144,152,160,184,192]:expected[off:off+8]=report[off:off+8]
    timings=[];previous=0
    for i in range(3):
        times=struct.unpack_from('<4q',report,256+i*32)
        assert 0<times[0]<times[1]<times[2]<times[3] and times[0]>previous
        assert times[3]-times[0]<2*54000000
        previous=times[3];expected[256+i*32:288+i*32]=report[256+i*32:288+i*32]
        timings.append({'source_ms':(times[1]-times[0])/54000,'final_ms':(times[2]-times[1])/54000,'display_ms':(times[3]-times[2])/54000,'frame_ms':(times[3]-times[0])/54000})
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',expected,1024+16*i,row['expected'],row['expected'])
    if report!=expected:
        pos=next(i for i,(a,b) in enumerate(zip(report,expected)) if a!=b)
        raise AssertionError(('report mismatch',pos,report[pos],expected[pos]))
    assert image.crop((0,0,107,800)).getbbox() is None,'left letterbox'
    assert image.crop((1173,0,1280,800)).getbbox() is None,'right letterbox'
    assert image.getpixel((640,760))==(33,34,37),'scene background'
    assert image.getpixel((200,650))==(32,160,240),'final animated bar'
    assert image.getpixel((450,650))==(33,34,37),'bar background'
    ink=sum(min(px)>180 and max(px)-min(px)<15 for px in image.crop((170,205,350,245)).getdata());assert ink>40,'native scene text missing'
    return {'passed':True,'checks':len(PLAN['cases']),'frames':3,'display_pixels_verified_by_reference_sha256':1024000,'gpu_scanout_bgra_bytes_equal':4096000,'vertices_observed':vertices,'setup_ms':create/54000,'timings':timings,'median_frame_ms':statistics.median(t['frame_ms'] for t in timings),'max_frame_ms':max(t['frame_ms'] for t in timings),'text_ink_pixels':ink,'new_teardown_faults':after-before,'scope':PLAN['scope']}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',required=True,type=Path);ap.add_argument('--picture',required=True,type=Path)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
