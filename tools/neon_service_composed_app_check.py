#!/usr/bin/env python3
"""Composed application pointer ledger, interaction, timing and integration raster checks."""
from pathlib import Path
import argparse,json,struct,math,statistics
from PIL import Image,ImageChops
EXPECTED=(104, -22300, 0, 0, 100, 50, 1, 1, -22302, 0, 0, 1, 0, 0, 0, 1, 0, 200, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, -22300, 0, -22302, -22304, 640, 0, 1, 400, 1, -22302, -22304, 1, 0, 0, -22301)

def check(report,picture,scripted,assets=False,*,report_only=False,presentation_paced=False):
    assert len(report)==16384
    q=lambda p:struct.unpack_from('<q',report,p)[0]
    bits=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
    extra=(-21501,0,0,0,0,bits(48.0),bits(54.0),0,0,0,bits(46.5),None,0,-21500,-21500,-21500,-21500,-21500,bits(-1.0),-21504,0,-21310) if assets else ()
    expected=EXPECTED+extra
    assert (q(0),q(8),q(16),q(24))==(0x4e434131,1,0,0),[q(p) for p in (0,8,16,24)]
    assert (q(32),q(40),q(48),q(56),q(64),q(72))==(90,90,int(scripted),0,len(expected),0),'frames/injection/real-contact/core ledger'
    for i,e in enumerate(expected):
        pair=struct.unpack_from('<2q',report,512+i*16)
        if e is None:
            assert pair[0]==pair[1] and 0<=pair[0]<=0x7f7fffff
            width=struct.unpack('<f',struct.pack('<I',pair[0]))[0];assert math.isfinite(width) and 0<width<100
        else:assert pair==(e,e),('assertion',i+1,pair,e)
    target=(2,2,1,20,3,4,0,3,1,1) if scripted else (0,0,0,10,0,1,0,0,0,1)
    assert tuple(q(p) for p in range(104,184,8))==target,('interaction',tuple(q(p) for p in range(104,184,8)),target)
    assert q(80)==(27 if scripted else 0) and (0 if presentation_paced else 90*33333)<=q(88)<8000000 and q(96)>1000
    slider=struct.unpack_from('<f',report,184)[0];assert math.isfinite(slider) and abs(slider-(276/360 if scripted else .35))<.00001
    assert (q(192),q(200),q(208),q(240),q(248))==(0,0,6 if scripted else 0,15 if assets else 3,0)
    for pos,s in [(2048,b'Arcade' if scripted else b''),(2304,b'Pause')]:assert report[pos:pos+len(s)+1]==s+b'\0'
    assert all(q(p)>0 for p in (216,224,232)) and q(224)&65535==1 and q(232)&65535==2
    assert q(256)==10,'retained box count'
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    interior=f32(f32(.15)+f32(.2))
    expected_boxes=[(240,116,144,38,0,1,1,None),(248,124,136,30,0,0,0,.4),(244,120,136,30,.4,.4,.4,1),(246,122,132,26,interior,.2,.6,1),(564,125,60,20,.1,.1,.1,1),(594,125,30,20,.2,.9,.2,1),(594,125,30,20,.6,1,.6,1),(244,185,360,10,.1,.1,.15,1),(244,185,276 if scripted else 126,10,0,.8,1,1),(512 if scripted else 362,178,16,24,.6,.6,.6,1)]
    for i,row in enumerate(expected_boxes):
        raw=report[10240+i*64:10304+i*64];got=struct.unpack_from('<8f',raw)
        assert all(math.isfinite(v) for v in got) and not any(raw[32:])
        for j,v in enumerate(row):
            if v is None:assert 0<=got[j]<=1
            else:assert struct.pack('<f',got[j])==struct.pack('<f',v),('retained box',i,j,got[j],v)
    assert q(264)==1
    phase=0.0
    for frame in range(90):
        speed=f32(.35)
        if scripted and frame==56:speed=f32(116/360)
        elif scripted and frame>=57:speed=f32(276/360)
        if not scripted or frame<=40 or frame>=73:
            phase=f32(phase+f32(f32(f32(.2)+f32(speed*f32(1.8)))*f32(1/30)))
    actual_phase=struct.unpack_from('<f',report,272)[0]
    assert math.isfinite(actual_phase) and abs(actual_phase-phase)<.00001,('simulation phase',actual_phase,phase)
    timings=[]
    for i in range(90):
        row=struct.unpack_from('<8q',report,4096+i*64);offset,inp,prep,draw,total,rc,state,menu=row
        assert 0<=offset<8000000 and all(v>=0 for v in (inp,prep,draw,total)) and total==inp+prep+draw and rc==0
        assert total<1000000 and menu in (0,1) and state in (10,20,310,320,1010,1020,1310,1320)
        if i:assert offset-timings[-1][0]>= (timings[-1][4] if presentation_paced else 33333)
        if not scripted:assert state==1010 and menu==0
        if scripted:
            active=10 if i<22 else 20
            top=3 if i>=70 else 0
            running=int(i<=40 or i>=73)
            assert state==active+100*top+1000*running and menu==int(8<=i<=11 or i>=80),('interaction timeline',i,state,menu)
        recording,present=struct.unpack_from('<2q',report,11264+i*16)
        assert recording>=0 and present>=0 and recording+present==draw,('record/present timing',i,recording,present,draw)
        timings.append(row)
    assert q(88)>=timings[-1][0]+timings[-1][4]
    unused=bytearray(report)
    for a,b in [(0,184),(184,188),(192,276),(10240,10880),(11264,11264+90*16),(512,512+16*len(expected)),(2048,2055 if scripted else 2049),(2304,2310),(4096,4096+90*64)]:unused[a:b]=b'\0'*(b-a)
    if assets:
        want=bytearray(256)
        for off,value in [(0,0x4e434132),(8,q(12808)),(16,q(12816)),(24,q(12824)),(32,13),(40,11),(48,943),(56,572),(64,656568),(72,1),(80,1)]:
            struct.pack_into('<q',want,off,value)
        assert report[12800:13056]==want
        assert q(12808)>0 and q(12816)>0 and q(12824)>0 and q(12816)&65535==3 and q(12824)&65535==4
        assert q(224)>>16>0 and all(q(p)>>16==q(224)>>16 for p in (232,12816,12824)),'font context ownership'
        unused[12800:13056]=b'\0'*256
    assert not any(unused),'unused bytes'
    if report_only:
        work=[r[4] for r in timings]
        return dict(assertions=len(expected),frames=90,work_mean_us=statistics.mean(work),work_max_us=max(work),target_30fps_met=max(work)<=33333,measured_fps=89e6/(timings[-1][0]-timings[0][0]),scope='Report only; caller must validate its rendering separately')
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    probes=0
    def pixel(x,y,c,tol=0):
        nonlocal probes
        p=(math.floor(x*2+.5),math.floor(y*2+.5));got=im.getpixel(p);assert max(abs(a-b) for a,b in zip(got,c))<=tol,(p,got,c);probes+=1
    pixel(500,10,(43,44,47));pixel(500,40,(33,34,37));pixel(246,72,(23,24,26));pixel(230,200,(11,14,19));pixel(626,280,(11,14,19));pixel(500,386,(11,14,19))
    pixel(520 if scripted else 370,190,(153,153,153),1)
    pixel(10,40,(43,44,47) if scripted else (37,38,41))
    if not scripted:pixel(10,27,(90,189,208))
    # Particle centres outside both sprite bounds: independently expected alpha blend.
    for col,row in [(c,r) for c in (0,1,5,6) for r in range(4)]+[(7,0),(7,1)]:pixel(290+40*col,245+32*row,(52,155,207),1)
    # Only the first untinted texture can produce pure red/green in this world clip.
    world=im.crop((488,436,1248,768));red=[];green=[];line=0
    for yy in range(world.height):
        for xx in range(world.width):
            c=world.getpixel((xx,yy))
            if c==(255,0,0):red.append((244+xx/2,218+yy/2))
            elif c==(0,255,0):green.append((244+xx/2,218+yy/2))
            elif c==(51,102,166):line+=1
    cx=420+math.sin(phase*2)*40
    assert len(red)>500 and len(green)>500 and line>1000,('sprite/static-line ink',len(red),len(green),line)
    assert all(abs(x-cx)<49 and abs(y-280)<49 for x,y in red+green),'sprite placement/order'
    # Ink must survive both the list/editor scissors and the final menu layer.
    for rect,bg in [((504,144,1200,200),(23,24,26)),((40,208,416,580),(30,31,34))]:
        cell=im.crop(rect);assert sum(p!=bg for p in cell.getdata())>200,'empty composed label area'
    png_pixels=0;policy_pixels=0
    if assets:
        plan=json.loads(Path(__file__).with_name('neon_png_cases.json').read_text(encoding='utf8'))
        case=plan['cases'][plan['file_fixture']['case_index']]
        assert case['key']==-1 and (case['width'],case['height'])==(13,11)
        rgba=bytes.fromhex(case['rgba'])
        for y in range(11):
            for x in range(13):
                r,g,b,a=rgba[(y*13+x)*4:(y*13+x+1)*4]
                want=tuple(round((v*a+base*(255-a))/255) for v,base in zip((r,g,b),(11,14,19)))
                for yy in range(6):
                    for xx in range(6):
                        got=im.getpixel((24+x*6+xx,612+y*6+yy))
                        assert max(abs(v-w) for v,w in zip(got,want))<=1,('PNG',x,y,xx,yy,got,want)
                        png_pixels+=1
        for y in [306,332,360]:
            left=im.crop((184,y*2,304,y*2+40));right=im.crop((312,y*2,432,y*2+40))
            assert all(v[1]==0 for v in ImageChops.difference(left,right).getextrema()),('font policy',y)
            assert sum(min(c)>100 and max(c)-min(c)<5 for c in left.getdata())>100
            policy_pixels+=120*40
    recording=[struct.unpack_from('<q',report,11264+i*16)[0] for i in range(90)];present=[struct.unpack_from('<q',report,11272+i*16)[0] for i in range(90)]
    work=[r[4] for r in timings];draw=[r[3] for r in timings];prep=[r[2] for r in timings];inp=[r[1] for r in timings]
    return dict(passed=True,frames=90,assertions=len(expected),pointer_checks=len(EXPECTED),drive_assets=assets,png_pixels=png_pixels,font_policy_pixels=policy_pixels,scripted=scripted,real_touch_records=0,geometry_probes=probes,world_red_pixels=len(red),world_green_pixels=len(green),static_line_pixels=line,recording_mean_us=statistics.mean(recording),submit_present_mean_us=statistics.mean(present),input_mean_us=statistics.mean(inp),prepare_mean_us=statistics.mean(prep),draw_mean_us=statistics.mean(draw),work_mean_us=statistics.mean(work),work_max_us=max(work),first_frame_us=work[0],warm_max_us=max(work[1:]),late_frame_indices=[i for i,v in enumerate(work) if v>33333],over_33333_us=sum(v>33333 for v in work),target_30fps_met=max(work)<=33333,measured_fps=89e6/(timings[-1][0]-timings[0][0]))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--scripted',action='store_true');ap.add_argument('--assets',action='store_true');ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture,a.scripted,a.assets),indent=2))
if __name__=='__main__':main()
