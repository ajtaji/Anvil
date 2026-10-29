#!/usr/bin/env python3
"""Check actual Pi4 retained UI metadata, interior pixels and fixed-font cells.

No engine code executes here. Pixel expectations follow the reference widget
formulas and the independently read, pinned bitmap input, not a previous capture.
This samples geometry interiors and complete text cells, not every frame pixel.
"""
from pathlib import Path
import argparse,hashlib,json,struct,math
FONT_SHA="9febfa4ae253d0a60ac1632fb71b04ba8d0a4b9a89999e11c28a4ea6af7c72ea"
WIDTH=800;HEIGHT=1280;PITCH=3200;BYTES=PITCH*HEIGHT

def font_input(root):
    source=(root/'RaspberryPi4/Lib/display.pi4').read_text(encoding='utf-8-sig')
    assert source.count('dsp_font8x16:')==1,'font owner'
    rows=[]
    for line in source.split('dsp_font8x16:',1)[1].splitlines()[1:96]:
        body=line.split(';',1)[0].strip();assert body.startswith('Data.a '),'font row declaration'
        row=bytes(int(v.strip()[1:],16) for v in body[7:].split(','))
        assert len(row)==16,'font row size';rows.append(row)
    font=b''.join(rows);assert len(font)==1520 and hashlib.sha256(font).hexdigest()==FONT_SHA,'font input changed; review the oracle'
    return font

def channel(c):return int(math.floor(c*255+.5))
def rgba(r,g,b):return (channel(b),channel(g),channel(r),255)

def interior_probes(frame):
    probes=[
      ('clear',750,750,(0,0,0,255)),
      ('button-border',40,120,rgba(.4,.4,.4)),
      ('button-face',48,128,rgba(.15,.2,.6)),
      ('breadcrumb-line',50,90,rgba(.2,.4,.8)),
      ('slider-filled',80,245,rgba(0,.8,1)),
      ('slider-moving-fill',160,245,rgba(.1,.1,.15) if frame==0 else rgba(0,.8,1)),
      ('slider-old-handle',100,235,rgba(.6,.6,.6) if frame==0 else rgba(0,0,0)),
      ('slider-new-handle',220,235,rgba(0,0,0) if frame==0 else rgba(.6,.6,.6)),
      ('toggle-left',530,140,rgba(1,.5,.5) if frame==0 else rgba(.1,.1,.1)),
      ('toggle-right',560,140,rgba(.1,.1,.1) if frame==0 else rgba(.6,1,.6)),
      ('meter-lit',368,240,rgba(0,.8,.4)),
      ('meter-dark',542,240,rgba(0,.1,.05)),
      ('bank-border',41,350,rgba(.1,.1,.1)),
      ('bank-inner',46,350,rgba(.02,.02,.02)),
      ('carousel-background',370,345,rgba(.05,.05,.05)),
      ('cursor',700,700,rgba(1,0,0)),
    ]
    for i in range(4):
        active=(i%2==0) if frame==0 else (i%2!=0)
        x=50+i*40
        probes += [
          (f'dip{i}-top',x+8,365,rgba(.8,.9,1) if active else rgba(0,0,0)),
          (f'dip{i}-bottom',x+8,390,rgba(0,0,0) if active else rgba(.8,.9,1)),
          (f'dip{i}-led',x+10,350,rgba(.1,1,.2) if active else rgba(.3,0,0))]
    return probes

def text_cells(frame):
    black=rgba(0,0,0);face=rgba(.15,.2,.6);car=rgba(.05,.05,.05)
    cells=[('Anvil retained controls',40,40,rgba(1,.8,.2),black),
       ('Neon / Vulkan / UI',40,70,rgba(.4,.8,1),black),
       ('Start',120,132,rgba(.902,.902,.902),face),
       ('Volume',40,208,rgba(.6,.8,1),black),
       ('Sound',360,132,rgba(.8,.8,.8),black),
       ('Load',360,204,rgba(.8,.8,.8),black),
       ('Options',40,318,rgba(.8,.8,.8),black),
       ('<',376,352,rgba(.5,.5,.5),car),
       ('>',576,352,rgba(.5,.5,.5),car),
       ('Medium' if frame==0 else 'High',456 if frame==0 else 464,352,rgba(.902,.902,.902),car)]
    cells += [(str(i+1),56+i*40,415,rgba(.5,.5,.5),black) for i in range(4)]
    return cells

def pixel(raw,x,y):return tuple(raw[y*PITCH+x*4:y*PITCH+x*4+4])
def compare(actual,expected,where):
    assert len(actual)==4 and all(abs(a-b)<=1 for a,b in zip(actual,expected)),(where,actual,expected)

def check_metadata(raw):
    assert len(raw)==4096,'report length'
    h=struct.unpack_from('<64I',raw);m=struct.unpack_from('<64q',raw,512)
    assert h[0]==0x4157564e and h[63]==0x4e565741,'diagnostic magic'
    for slot,value in {1:0,2:9,3:256,18:0,19:0,20:1,21:0,23:1,51:0,53:1}.items():assert h[slot]==value,('diagnostic',slot,h[slot],value)
    assert all(h[4:14]),'Vulkan object chain was not recorded'
    assert 0x063e8000<=h[14] and h[14]+BYTES<=0x06fe8000,'attachment leaves the declared Vulkan window'
    assert h[15]>=BYTES and h[14]+h[15]<=0x06fe8000 and h[16]==PITCH,'attachment extent/pitch'
    assert m[:14]==(0x4e524732,2,0,9,8,2,1,-1,0x07000000,0x07400000,3200,800,1280,BYTES),'scene header'
    assert m[14:16]==(8192000,8192000) and m[63]==0x3247524e,'scene padding/tail'
    for frame in range(2):
        a=m[16+frame*16:32+frame*16]
        assert a[0]==65 and 0<a[1]<=3072,('draw count/vertices',frame,a[:2])
        assert a[2:9]==(0,0,1,1,0,0,8),('frame retirement',frame,a[2:9])
        bits=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
        assert a[9:15]==(bits(.25 if frame==0 else .75),frame,5 if frame==0 else 10,bits(1.0 if frame==0 else 2.0),16,8),('control state/font metrics',frame,a[9:15])
        assert a[15]==BYTES,'frame copy length'
    assert m[17]-m[33]==12,'two fewer visible glyph quads in High than Medium'
    assert m[48:56]==(0,0,0,0,-20002,-20002,12345,0),'teardown or retired parent handles'
    assert not any(m[56:63]),'unused scene fields'
    assert not any(raw[256:512]) and not any(raw[1024:]),'report padding'
    return dict(draws=[m[16],m[32]],vertices=[m[17],m[33]],frames=2)

def check(raw,frames,font):
    result=check_metadata(raw);probes=0;cells=0;pixels=0
    assert len(frames)==2 and all(len(f)==BYTES for f in frames),'attachment length'
    for frame,f in enumerate(frames):
        for name,x,y,color in interior_probes(frame):compare(pixel(f,x,y),color,(frame,name,x,y));probes+=1
        for text,x,y,ink,bg in text_cells(frame):
            for i,ch in enumerate(text):
                assert 32<=ord(ch)<=126,'oracle character'
                glyph=font[(ord(ch)-32)*16:(ord(ch)-31)*16]
                for row,bits in enumerate(glyph):
                    for col in range(8):
                        expected=ink if bits&(128>>col) else bg
                        compare(pixel(f,x+i*8+col,y+row),expected,(frame,text,i,col,row));pixels+=1
            cells+=1
    result.update(passed=True,interior_probes=probes,text_runs=cells,text_pixels=pixels,scope='Interior geometry probes and complete bitmap text cells; not whole-frame equality')
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--frame0',type=Path,required=True);ap.add_argument('--frame1',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    print(json.dumps(check(a.report.read_bytes(),[a.frame0.read_bytes(),a.frame1.read_bytes()],font_input(root)),indent=2))
if __name__=='__main__':main()
