"""Full resident CRT application: original report contract and transformed raster."""
import math,json,struct
from pathlib import Path
from PIL import Image
from neon_service_composed_app_check import check as composed_check

def check(report,picture,*,profile=False,presentation_paced=False,prewarmed=False):
    assert len(report)==16384
    assert not prewarmed or profile,'preparation timing requires its recorded profile'
    assert not presentation_paced or profile,'presentation pacing requires its recorded profile'
    magic,caps,generation,events=struct.unpack_from('<4q',report,13120)
    assert magic==0x4e4e4131 and 1<=caps<=7 and 1<=generation<=2147483647
    assert events==0,'Idle native integration expected; physical input needs separate acceptance'
    baseline=bytearray(report);baseline[13120:13152]=bytes(32)
    stages=[]
    if profile:
        assert struct.unpack_from('<2q',report,13312)==(0x4e435031,90),'profile header'
        for i in range(90):
            row=struct.unpack_from('<4q',report,13440+i*32)
            present=struct.unpack_from('<q',report,11272+i*16)[0]
            assert 0<row[0]<=row[1]<=row[2]<=row[3]<=present,('profile order',i,row,present)
            stages.append([row[0],row[1]-row[0],row[2]-row[1],row[3]-row[2]])
        assert struct.unpack_from("<q",report,13328)[0]==int(presentation_paced),"pacing mode"
        if prewarmed:
            assert struct.unpack_from('<q',report,13344)[0]==0x50524531,'preparation marker'
            prepare_us=struct.unpack_from('<q',report,13336)[0]
            assert 0<prepare_us<1000000,'preparation duration'
            baseline[13336:13352]=bytes(16)
        baseline[13312:13336]=bytes(24)
        baseline[13440:16320]=bytes(2880)
    result=composed_check(baseline,picture,False,True,report_only=True,presentation_paced=presentation_paced)
    if prewarmed:result['setup_retro_prepare_us']=prepare_us
    if presentation_paced:
        completed=[sum(struct.unpack_from('<q',report,4096+i*64+off)[0] for off in (0,32)) for i in range(90)]
        intervals=[b-a for a,b in zip(completed,completed[1:])]
        assert all(32000<=v<=34000 for v in intervals),('warm presentation cadence',min(intervals),max(intervals))
        result.update(presentation_paced=True,warm_completion_min_us=min(intervals),warm_completion_max_us=max(intervals),warm_fps=89e6/(completed[-1]-completed[0]))
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    def source(x,y):
        u=2*(x+.5)/1280-1;v=2*(y+.5)/800-1;k=.015*(u*u+v*v)
        u=(u+u*k)*.5+.5;v=(v+v*k)*.5+.5
        t=max(0,min(1,(math.hypot(u-.5,v-.5)-.3)/.5))
        return u*1280,v*800,1-t*t*(3-2*t),255*.04*math.sin(v*800)
    def output(sx,sy):
        a=2*(sx+.5)/1280-1;b=2*(sy+.5)/800-1;u=a;v=b
        for _ in range(16):
            k=1+.015*(u*u+v*v);u=a/k;v=b/k
        return round((u+1)*640-.5),round((v+1)*400-.5)
    probes=0
    def pixel(sx,sy,rgb):
        nonlocal probes
        x,y=output(sx,sy);_,_,shade,wave=source(x,y)
        wanted=[max(0,min(255,(c-wave)*shade)) for c in rgb]
        got=im.getpixel((x,y));assert max(abs(a-b) for a,b in zip(got,wanted))<=2,(sx,sy,x,y,got,wanted)
        probes+=1
    for x,y,c in [(500,10,(43,44,47)),(500,40,(33,34,37)),(246,72,(23,24,26)),(230,200,(11,14,19)),(626,280,(11,14,19)),(500,386,(11,14,19)),(370,190,(153,153,153)),(10,40,(37,38,41))]:pixel(x*2,y*2,c)
    for col,row in [(c,r) for c in (0,1,5,6) for r in range(4)]+[(7,0),(7,1)]:pixel((290+40*col)*2,(245+32*row)*2,(52,155,207))
    plan=json.loads(Path(__file__).with_name('neon_png_cases.json').read_text())
    case=plan['cases'][plan['file_fixture']['case_index']];assert (case['width'],case['height'],case['key'])==(13,11,-1)
    rgba=bytes.fromhex(case['rgba'])
    for y in range(11):
        for x in range(13):
            r,g,b,a=rgba[(y*13+x)*4:(y*13+x+1)*4]
            rgb=tuple(round((v*a+base*(255-a))/255) for v,base in zip((r,g,b),(11,14,19)))
            pixel(24+x*6+3,612+y*6+3,rgb)
    red=green=line=0
    for y in range(436,768,2):
        for x in range(488,1248,2):
            sx,sy,shade,wave=source(x,y);rgb=im.getpixel((x,y))
            if shade<=.1:continue
            recovered=[c/shade+wave for c in rgb]
            if recovered[0]>240 and rgb[1]<15 and rgb[2]<15:red+=1
            if recovered[1]>240 and rgb[0]<15 and rgb[2]<15:green+=1
            if max(abs(c-v) for c,v in zip(recovered,(51,102,166)))<2:line+=1
    assert red>125 and green>125 and line>250,(red,green,line)
    faint=0
    for y in range(144,200):
        for x in range(504,1200):
            _,_,shade,wave=source(x,y)
            recovered=[c/shade+wave for c in im.getpixel((x,y))]
            if max(abs(c-v) for c,v in zip(recovered,(111,117,127)))<=5:faint+=1
    assert faint>40,('placeholder palette ink',faint)
    for rect in [(40,208,416,580),(184,612,304,652),(184,664,304,704),(184,720,304,760)]:
        assert sum(min(p)>70 and max(p)-min(p)<8 for p in im.crop(rect).getdata())>40,rect
    for p in [(0,0),(1279,0),(0,799),(1279,799)]:assert im.getpixel(p)==(0,0,0)
    result.update(native_input=True,capabilities=caps,generation=generation,native_records=events,crt_probes=probes,sprite_red_samples=red,sprite_green_samples=green,static_line_samples=line,scope='Full resident CRT scene and idle native input; scripted controls separately qualified; no physical input actuation')
    if profile:
        names=('target_end','unbind_prepare','crt_present','rebind')
        result['stage_us']={n:dict(first=stages[0][j],warm_mean=sum(r[j] for r in stages[1:])/89,maximum=max(r[j] for r in stages)) for j,n in enumerate(names)}
        result['stage_rows_us']=stages
    return result
