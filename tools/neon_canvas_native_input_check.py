"""Validate the real input session, bounded event log and physical canvas output."""
from pathlib import Path
import argparse,json,struct,math,collections
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('neon_canvas_native_input_cases.json').read_text(encoding='utf8'))
def check(report,picture):
    assert len(report)==16384
    q=lambda o:struct.unpack_from('<q',report,o)[0]
    assert q(0)==0x4e4c4931 and q(8)==1
    if q(16):
        i=q(16)-1
        pair=struct.unpack_from('<2q',report,1024+i*16) if 0<=i<448 else None
        raise AssertionError(('device refusal',q(16),q(24),pair))
    frames,events,caps,polls,idles=q(72),q(80),q(160),q(208),q(216)
    assert 1<=frames<=20 and 0<=events<=128 and 1<=caps<=7
    assert polls==events+idles and polls>0 and idles>=0
    assert q(232)>0 and q(240)==0,'input context not closed'
    assert q(40)==q(200)==0 and 0<=q(48)==q(152)<32
    assert q(136)==512000 and q(144)==0
    assert 24<=q(184)<=2000 and 0<q(192)<10*54000000
    assert q(8192)==0x4e4c4931 and q(8192+24)==events
    assert 0<=q(8192+8)<=events and 0<=q(8192+16)<=events
    assert q(8192+32) in [0,1] and q(8192+40) in [0,77]
    opened,seen=q(8192+48),q(8192+56)
    assert opened>0 and q(168)>=opened
    assert seen==(q(168) if events else 0)
    assert q(8192+88)==5*54000000 and 0<q(8192+96)<7*54000000
    assert 0<=q(8192+104)<=q(8192+96) and 0<q(8192+112)<=q(8192+96)
    assert q(8192+120)==128 and q(8192+192)==caps and q(8192+200)==20
    assert q(8192+208)==frames and q(8192+216)==q(8192+224)==0
    assert q(8192+232)==events*48
    for off in [8192+72,8192+80]:
        bits=q(off);assert 0<=bits<=0xffffffff
        value=struct.unpack('<f',struct.pack('<I',bits))[0]
        assert math.isfinite(value) and -1000<=value<=1000
    text=report[8192+128:8192+192]
    end=text.find(b'\0');assert 0<=end<=63 and all(32<=c<=126 for c in text[:end])
    kinds=collections.Counter();sources=collections.Counter();generation=opened;records=[]
    for i in range(events):
        kind,source,code,mods,x,y,buttons,value,ticks,gen,reserved=struct.unpack_from('<8iq2i',report,10240+i*48)
        assert 1<=kind<=7 and 0<=mods<=15 and ticks>=0 and reserved==0
        if kind==4:assert gen>=generation;generation=gen
        else:assert gen==generation
        if kind<=4:
            assert 1<=source<=3 and x==y==-1 and buttons==value==0
            if kind==1:assert 32<=code<=126
            elif kind in [2,3]:assert 1<=code<=15
            else:assert 0<=code<=8
            if source==1 and kind!=4:assert caps&1
        elif kind==7:
            assert source==1 and caps&1 and 1<=code<=255 and x==y==-1 and buttons==0 and value in [0,1]
        else:
            assert source in [4,5] and caps&(2 if source==4 else 4) and 0<=buttons<=7
            if kind==5 and value==3:
                assert x==y==-1 and buttons==0 and -1<=code<=65535
                assert (source!=4 or code in [-1,0]) and (source!=5 or code!=0)
            else:
                assert 0<=x<1280 and 0<=y<800
                if kind==6:assert source==4 and code==0 and -32768<=value<=32767
                else:
                    assert 0<=code<=65535 and 0<=value<=4
                    assert source!=4 or code==0
                    assert source!=5 or (code>0 and value!=4 and buttons<=1)
                    assert (buttons!=0 if value in [0,1] else buttons==0)
        kinds[kind]+=1;sources[source]+=1
        records.append(dict(kind=kind,source=source,code=code,value=value,ticks=ticks,generation=gen))
    assert generation==q(168)
    for kind in range(1,8):assert q(8192+256+kind*8)==kinds[kind]
    assert q(8192+320)==sources[4] and q(8192+328)==sources[5]
    if events==0:
        assert frames==1 and q(8192+8)==q(8192+16)==q(8192+32)==q(8192+40)==q(8192+64)==0
        assert q(8192+72)==q(8192+80)==0xbf800000 and text==b'LIVE'+bytes(60)
        assert q(8192+96)>=5*54000000
    elif frames<20 and events<128 and not any(r['kind']==2 and r['code']==9 for r in records):
        assert q(8192+96)>=5*54000000
    expected=bytearray(16384)
    fixed={0:0x4e4c4931,8:1,64:54000000,88:800,96:600,104:107,120:1066,128:800,136:512000,176:4096000,224:1920000}
    rows=PLAN['setup']+PLAN['frame']*frames+PLAN['final']
    assert q(24)==len(rows)
    fixed[24]=len(rows)
    for off,value in fixed.items():struct.pack_into('<q',expected,off,value)
    for off in [48,72,80,152,160,168,184,192,208,216,232]:expected[off:off+8]=report[off:off+8]
    previous=0;timings=[];total=0
    for i in range(frames):
        off=256+32*i;t=[q(off+8*k) for k in range(4)]
        assert previous<t[0]<t[1]<t[2]<t[3] and t[3]-t[0]<2*54000000
        previous=t[3];total+=t[3]-t[0];timings.append((t[3]-t[0])/54000)
        expected[off:off+32]=report[off:off+32]
    assert total<=q(8192+112)<=total+frames*5400000
    for i,row in enumerate(rows):struct.pack_into('<2q',expected,1024+16*i,row['expected'],row['expected'])
    for off in list(range(8192,8192+240,8))+list(range(8192+264,8192+336,8)):
        expected[off:off+8]=report[off:off+8]
    expected[10240:10240+events*48]=report[10240:10240+events*48]
    assert expected==report,'unexpected report bytes'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    assert im.crop((0,0,107,800)).getbbox() is None and im.crop((1173,0,1280,800)).getbbox() is None
    assert im.getpixel((680,310))==(32,160,240) and im.getpixel((640,760))==(33,34,37)
    ink=sum(min(p)>180 for p in im.crop((220,300,280,335)).getdata())
    if events==0:assert ink>30,ink
    return dict(checks=len(rows),frames=frames,events=events,opened_capabilities=caps,keyboard=bool(caps&1),mouse=bool(caps&2),touch=bool(caps&4),polls=polls,idle_polls=idles,input_closed=True,elapsed_ms=q(8192+96)/54000,poll_ms=q(8192+104)/54000,render_ms=q(8192+112)/54000,frame_ms=timings,received_records=records,scope='Idle live-client integration only; no physical input effect proved' if events==0 else PLAN['scope'])
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',required=True,type=Path);ap.add_argument('--picture',required=True,type=Path);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
