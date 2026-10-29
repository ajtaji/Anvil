#!/usr/bin/env python3
"""Check a resident loop report and its final confirmed display snapshot."""
import argparse,json,struct
from pathlib import Path
from PIL import Image
def check(raw,picture,scripted=True):
    assert len(raw)==4096
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x4E534C31,1,0,0),q[:4]
    assert q[4]>0 and q[5]==0 and q[6:8]==(90,90),q[4:8]
    assert q[8]>=0 and q[9]==int(scripted) and q[10]>=0 and q[13]==int(scripted),q[8:14]
    assert q[10]<=q[8],q[8:11]
    assert 2900000<=q[11]<=6200000,q[11]
    stages=469 if scripted else 456
    assert q[12]>=stages,q[12]
    if q[10]==0:assert q[12]==stages,q[12]
    starts=[]
    for i in range(90):
        start,rc=struct.unpack_from('<2q',raw,256+i*16)
        assert start>=0 and rc==0,(i,start,rc)
        if starts:assert start>starts[-1],(i,start,starts[-1])
        starts.append(start)
    assert starts[0]<100000 and starts[-1]+33333<=q[11]+100,starts[-1]
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    probes=[(10,10,(5,10,20)),(550,300,(5,10,20)),(690,300,(0,191,128)),
            (760,340,(0,191,128)),(800,300,(5,10,20)),(1000,650,(5,10,20))]
    for x,y,want in probes:
        got=im.getpixel((x,y));assert max(abs(a-b) for a,b in zip(got,want))<=1,(x,y,got,want)
    title=sum(1 for y in range(60,110) for x in range(60,900) if (lambda c:c[0]>180 and c[1]>130 and c[2]<100)(im.getpixel((x,y))))
    button=sum(1 for y in range(150,195) for x in range(160,320) if min(im.getpixel((x,y)))>180)
    assert title>300 and button>(650 if scripted else 400),(title,button)
    spans=[b-a for a,b in zip(starts,starts[1:])]
    work=list(struct.unpack_from('<90q',raw,2304))
    assert all(0<cost<200000 for cost in work),work
    for i,cost in enumerate(work):
        available=(starts[i+1] if i<89 else q[11])-starts[i]
        assert cost<=available,(i,cost,available)
    return dict(passed=True,frames=90,physical_ends=90,scripted_clicks=int(scripted),
                real_touch_records=q[8],real_ui_events=q[10],duration_us=q[11],
                frame_interval_us=dict(min=min(spans),max=max(spans),mean=sum(spans)/len(spans)),
                frame_work_us=dict(min=min(work),max=max(work),mean=sum(work)/len(work)),
                display_probes=len(probes),title_ink=title,button_ink=button,
                scope=('Real resident Vulkan/display loop plus labelled synthetic contact; physical finger actuation not asserted' if scripted else 'Real resident Vulkan/display loop, no injected input; physical finger actuation not asserted'))
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path);ap.add_argument('picture',type=Path)
    ap.add_argument('--scripted',action='store_true',help='expect the explicitly injected contact test')
    a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes(),a.picture,scripted=a.scripted),indent=2))
if __name__=='__main__':main()
