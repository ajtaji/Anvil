#!/usr/bin/env python3
"""Independent mixed-font retained UI report and outline-reference checker.

FontTools parses the input fonts; MuPDF scan-converts their unhinted outlines.
Solid ink is selected with an independent 8x outline mask and a one-eighth-pixel
halo, matching the rasterizer's documented maximum curve approximation error.
Solid ink and distant exterior compare within one channel value; edge coverage
is implementation dependent. This is not whole-frame raster equality.
"""
from pathlib import Path
from io import BytesIO
import argparse,hashlib,json,math,re,struct
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
import pymupdf
import neon_retained_ui_gpu_proof_check as bitmap
DEJAVU_SHA='e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724'
PROBE_SHA='370233dbfcdd73441300cd76f8fc939f2c17688d63c86a4cbccea2c6f2787a75'
TAG=0x0001000000000000

def embedded(path,digest):
    source=path.read_text(encoding='utf-8-sig')
    raw=b''.join(bytes(int(v,16) for v in re.findall(r'\$([0-9a-fA-F]{2})',line.split(';',1)[0])) for line in source.splitlines() if re.match(r'\s*Data\.[ab] ',line))
    assert hashlib.sha256(raw).hexdigest()==digest,'font input changed'
    return raw

class Face:
    def __init__(self,data):
        self.font=TTFont(BytesIO(data));self.units=self.font['head'].unitsPerEm
        self.ascent=self.font['hhea'].ascent;self.glyphs=self.font.getGlyphSet();self.cmap=self.font.getBestCmap();self.cache={};self.lookups=[]
        if 'GPOS' in self.font:
            table=self.font['GPOS'].table
            scripts={s.ScriptTag:s.Script for s in table.ScriptList.ScriptRecord}
            script=scripts.get('latn',scripts.get('DFLT'))
            if script and script.DefaultLangSys:
                for i in script.DefaultLangSys.FeatureIndex:
                    feature=table.FeatureList.FeatureRecord[i]
                    if feature.FeatureTag=='kern':
                        for idx in feature.Feature.LookupListIndex:
                            if idx not in self.lookups:self.lookups.append(idx)
    def outline(self,name):
        if name not in self.cache:
            b=BoundsPen(self.glyphs);self.glyphs[name].draw(b)
            p=SVGPathPen(self.glyphs);self.glyphs[name].draw(p)
            self.cache[name]=(b.bounds,p.getCommands())
        return self.cache[name]
    def pair(self,left,right):
        values=[0]*8
        attrs=['XPlacement','YPlacement','XAdvance','YAdvance']
        if self.lookups:
            for idx in self.lookups:
                lookup=self.font['GPOS'].table.LookupList.Lookup[idx]
                subs=lookup.SubTable
                if lookup.LookupType==9:subs=[s.ExtSubTable for s in subs]
                else:assert lookup.LookupType==2,'unsupported independent reference lookup'
                for sub in subs:
                    if left not in sub.Coverage.glyphs:continue
                    rec=None
                    if sub.Format==2:
                        i=sub.ClassDef1.classDefs.get(left,0);j=sub.ClassDef2.classDefs.get(right,0)
                        rec=sub.Class1Record[i].Class2Record[j]
                    elif sub.Format==1:
                        i=sub.Coverage.glyphs.index(left)
                        rec=next((p for p in sub.PairSet[i].PairValueRecord if p.SecondGlyph==right),None)
                    else:raise AssertionError('unsupported pair format')
                    if rec:
                        for n,v in enumerate([rec.Value1,rec.Value2]):
                            for k,attr in enumerate(attrs):values[n*4+k]+=getattr(v,attr,0) if v else 0
                        break
        elif 'kern' in self.font:
            values[2]=sum(t.kernTable.get((left,right),0) for t in self.font['kern'].kernTables if t.version==0)
        return values
    def layout(self,text,size):
        names=[self.cmap[ord(c)] for c in text];advance=[self.font['hmtx'][n][0] for n in names]
        x=[0]*len(names);y=[0]*len(names)
        for i in range(len(names)-1):
            a=self.pair(names[i],names[i+1]);x[i]+=a[0];y[i]+=a[1];advance[i]+=a[2]
            x[i+1]+=a[4];y[i+1]+=a[5];advance[i+1]+=a[6]
        pen=0;placed=[]
        for i,name in enumerate(names):placed.append((name,(pen+x[i])*size/self.units,y[i]*size/self.units));pen+=advance[i]
        return placed,pen*size/self.units
    def width(self,text,size):return self.layout(text,size)[1]

def fonts(root):
    a=Face(embedded(root/'RaspberryPi4/Monitor/anvil_boot_ttf.pi4',DEJAVU_SHA))
    b=Face(embedded(root/'RaspberryPi4/Tests/Vulkan/neon_retained_probe_font.pbi',PROBE_SHA))
    assert a.font.getGlyphID(a.cmap[65])==b.font.getGlyphID(b.cmap[65])==36
    assert a.font.getGlyphID(a.cmap[66])==b.font.getGlyphID(b.cmap[66])==37
    assert a.font['hmtx'][a.cmap[65]][0]!=b.font['hmtx'][b.cmap[65]][0]
    return a,b

def text_runs(frame,faces):
    a,b=faces;black=bitmap.rgba(0,0,0);face=bitmap.rgba(.15,.2,.6);car=bitmap.rgba(.05,.05,.05)
    runs=[('Anvil retained — café',40,40,a,24,bitmap.rgba(1,.8,.2),black),
      ('AB',40,70,b,16,bitmap.rgba(.4,.8,1),black),
      ('Start',40+(200-a.width('Start',32))/2,123,a,32,bitmap.rgba(.902,.902,.902),face),
      ('Volume',40,198,a,24,bitmap.rgba(.6,.8,1),black),
      ('Sound',360,131,a,16,bitmap.rgba(.8,.8,.8),black),
      ('Load',360,198,a,20,bitmap.rgba(.8,.8,.8),black),
      ('Options',40,316,a,16,bitmap.rgba(.8,.8,.8),black),
      ('<',380-a.width('<',24)/2,347,a,24,bitmap.rgba(.5,.5,.5),car),
      ('>',580-a.width('>',24)/2,347,a,24,bitmap.rgba(.5,.5,.5),car)]
    selected='Médium' if frame==0 else 'High'
    runs.append((selected,360+(240-a.width(selected,24))/2,347,a,24,bitmap.rgba(.902,.902,.902),car))
    runs += [(str(i+1),60+i*40-a.width(str(i+1),16)/2,415,a,16,bitmap.rgba(.5,.5,.5),black) for i in range(4)]
    return runs

def reference_mask(run,stable_ink=False):
    text,x,y,font,size,ink,bg=run;paths=[];bounds=[];scale=size/font.units
    glyphs,_=font.layout(text,size)
    for name,dx,dy in glyphs:
        box,path=font.outline(name)
        if box is None:continue
        xmin,ymin,xmax,ymax=box;bx=math.floor(xmin*scale);by=math.ceil(ymax*scale)
        left=math.floor(x+dx+bx+.5);top=math.floor(y+math.floor(font.ascent*scale)-dy-by+.5)
        base_x=left-bx;base_y=top+by
        bounds.append((base_x+xmin*scale,base_y-ymax*scale,base_x+xmax*scale,base_y-ymin*scale))
        paths.append(f'<path fill="white" d="{path}" transform="translate({base_x},{base_y}) scale({scale},{-scale})"/>')
    assert bounds,'empty reference run'
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="800pt" height="480pt" viewBox="0 0 800 480"><rect width="800" height="480" fill="black"/>'+''.join(paths)+'</svg>'
    doc=pymupdf.open(stream=svg.encode(),filetype='svg');pix=doc[0].get_pixmap(colorspace=pymupdf.csGRAY,alpha=False)
    assert (pix.width,pix.height,pix.n)==(800,480,1)
    roi=(max(1,math.floor(min(b[0] for b in bounds))-2),max(1,math.floor(min(b[1] for b in bounds))-2),min(799,math.ceil(max(b[2] for b in bounds))+2),min(479,math.ceil(max(b[3] for b in bounds))+2))
    mask=bytes(pix.samples)
    if not stable_ink:return mask,roi
    # A 1x antialiased pixel can round to 255 while a small part of its area is
    # still outside the outline. That is not a stable interior reference.
    # Independently scan-convert at 8x, excluding the bounded 1/8-pixel curve
    # neighborhood. This also leaves useful solid probes in 16px thin glyphs.
    hi=doc[0].get_pixmap(matrix=pymupdf.Matrix(8,8),clip=pymupdf.Rect(roi[0]-1,roi[1]-1,roi[2]+1,roi[3]+1),colorspace=pymupdf.csGRAY,alpha=False)
    samples=bytes(hi.samples);solid=bytearray(800*480)
    for y in range(roi[1],roi[3]):
        for x in range(roi[0],roi[2]):
            if mask[y*800+x]<252:continue
            if all(min(samples[(sy-hi.y)*hi.stride+x*8-hi.x-1:(sy-hi.y)*hi.stride+(x+1)*8-hi.x+1])>=252 for sy in range(y*8-1,(y+1)*8+1)):
                solid[y*800+x]=1
    return mask,roi,solid

def check_metadata(raw,faces):
    assert len(raw)==4096,'report length'
    h=struct.unpack_from('<64I',raw);m=struct.unpack_from('<64q',raw,512);t=struct.unpack_from('<128q',raw,1024)
    assert h[0]==0x4157564e and h[63]==0x4e565741
    for k,v in {1:0,2:9,3:256,18:0,19:0,20:1,21:0,23:1,51:0,53:1}.items():assert h[k]==v,('diagnostic',k,h[k],v)
    assert all(h[4:14]) and 0x063e8000<=h[14] and h[14]+h[15]<=0x06fe8000 and h[15]>=4096000 and h[16]==3200
    assert m[:16]==(0x4e524732,3,0,9,8,2,1,0,0x07000000,0x07400000,3200,800,1280,4096000,8192000,8192000)
    counts=[]
    for frame in range(2):
        a=m[16+frame*16:32+frame*16];glyphs=sum(sum(font.outline(name)[0] is not None for name,_,_ in font.layout(text,size)[0]) for text,x,y,font,size,ink,bg in text_runs(frame,faces));vertices=46*6+5*18+glyphs*6;counts.append(vertices)
        assert a[:9]==(65,vertices,0,0,1,1,0,0,8),('frame',frame,a[:9],vertices)
        bits=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
        assert a[9:]==(bits(.25 if frame==0 else .75),frame,5 if frame==0 else 10,bits(1.0 if frame==0 else 2.0),18,8,4096000)
    assert m[48:56]==(0,0,0,0,-20002,-20002,12345,0) and not any(m[56:63]) and m[63]==0x3247524e
    assert t[:4]==(0x4e524754,1,0,39),('font setup checks',t[:4])
    assert t[5]>t[4]>=4 and t[6:8]==(0,-21405),'prewarm/mutation guard'
    for i in range(5):
        a=t[8+i*8:16+i*8];slot=0 if i<4 else 1;role=i if i<4 else 1;size=[24,16,20,32,16][i];font=faces[slot]
        expected=[slot,3,role,size,size+2]
        expected += [font.font['hmtx'][font.cmap[ord(ch)]][0]*size*65536//font.units for ch in 'AB']
        expected += [0];assert a==tuple(expected),('font',i,a,expected)
    ids=[TAG|(2<<16)|i for i in range(1,6)]
    controls=[(1,ids[0],40,40,0,0),(2,ids[4],40,70,0,0),(3,ids[3],40,120,200,40),(4,ids[0],40,230,240,30),(5,ids[1],360,120,220,40),(6,ids[2],360,230,240,30),(7,ids[1],40,340,180,70),(8,ids[0],360,340,240,40)]
    for i,(ident,font,x,y,w,hgt) in enumerate(controls):
        a=t[48+i*8:56+i*8];expected=(ident,font,*[struct.unpack('<I',struct.pack('<f',float(v)))[0] for v in [x,y,w,hgt]],0,0)
        assert a==expected,('control font/geometry',i,a,expected)
    assert t[112:115]==(1,0,0),'prepared alternate face was not switched for drawing'
    assert not any(t[115:]) and not any(raw[256:512]) and not any(raw[2048:])
    return dict(frames=2,draws=[65,65],vertices=counts,setup_checks=39,mixed_loaded_faces=2,font_references=5)

def check(raw,frames,faces):
    result=check_metadata(raw,faces);assert len(frames)==2 and all(len(f)==bitmap.BYTES for f in frames)
    ink_count=0;bg_count=0;probes=0;runs=0
    for frame,pixels in enumerate(frames):
        for name,x,y,color in bitmap.interior_probes(frame):
            if name=='breadcrumb-line':y=92
            bitmap.compare(bitmap.pixel(pixels,x,y),color,(frame,name,x,y));probes+=1
        for run in text_runs(frame,faces):
            mask,(x0,y0,x1,y1),solid=reference_mask(run,stable_ink=True);ink=run[-2];bg=run[-1];run_ink=0
            for y in range(y0,y1):
                for x in range(x0,x1):
                    alpha=mask[y*800+x];actual=bitmap.pixel(pixels,x,y)
                    if solid[y*800+x]:
                        bitmap.compare(actual,ink,('reference ink',frame,run[0],x,y))
                        ink_count+=1;run_ink+=1
                    elif alpha==0 and all(mask[(y+dy)*800+x+dx]==0 for dx in [-1,0,1] for dy in [-1,0,1]):
                        bitmap.compare(actual,bg,('reference exterior',frame,run[0],x,y));bg_count+=1
            assert run_ink>=1,('no stable ink coverage',run[0]);runs+=1
    result.update(passed=True,interior_probes=probes,text_runs=runs,stable_ink_pixels=ink_count,stable_exterior_pixels=bg_count,scope='Independent FontTools outlines/MuPDF 8x stable ink with 1/8-pixel halo; one-channel-unit interior/exterior tolerance; antialias boundary excluded; not whole-frame equality')
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--frame0',type=Path,required=True);ap.add_argument('--frame1',type=Path,required=True);a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    print(json.dumps(check(a.report.read_bytes(),[a.frame0.read_bytes(),a.frame1.read_bytes()],fonts(root)),indent=2))
if __name__=='__main__':main()
