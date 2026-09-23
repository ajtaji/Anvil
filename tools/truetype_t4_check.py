"""Emitted T4 raster gate with synthetic winding and independent geometric oracle."""
from __future__ import annotations
import argparse
import bisect
from contextlib import nullcontext
import math
from pathlib import Path
import shutil
import struct
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, ROOT, LOAD, STACK  # noqa: E402
import a64_core_worker_check as base  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

GATE = ROOT / "RaspberryPi4/Tests/truetype_t4_gate.pi4"
META, FONT_BASE, MAGIC = 0x0F000000, 0x10000000, 0x54543452
OUT, COVER = 0x0F010000, 0x0F020000
LIMIT = 30_000_000
ALL_OFF = [(0,0,0),(7,0,0),(4,8,0)]

def simple_glyph(contours):
    points = [point for contour in contours for point in contour]
    if not points:
        return b""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    out = bytearray(struct.pack(">hhhhh", len(contours), min(xs), min(ys), max(xs), max(ys)))
    end = -1
    for contour in contours:
        end += len(contour)
        out += struct.pack(">H", end)
    out += b"\0\0"
    out += bytes(1 if on else 0 for _, _, on in points)
    prior = 0
    for x, _, _ in points:
        out += struct.pack(">h", x - prior)
        prior = x
    prior = 0
    for _, y, _ in points:
        out += struct.pack(">h", y - prior)
        prior = y
    if len(out) & 1:
        out += b"\0"
    return bytes(out)

def font_bytes():
    ring = [[(0,0,1),(8,0,1),(8,8,1),(0,8,1)], [(2,2,1),(2,6,1),(6,6,1),(6,2,1)]]
    start_on_end_off = [[(0,0,1),(8,0,1),(4,8,0)]]
    all_off = [ALL_OFF]
    glyf = simple_glyph(ring) + simple_glyph(start_on_end_off) + simple_glyph(all_off)
    # Glyph zero and glyph four are empty. Short loca stores big-endian offsets / 2.
    offsets = [0, 0, len(simple_glyph(ring)), len(simple_glyph(ring))+len(simple_glyph(start_on_end_off)), len(glyf), len(glyf)]
    loca = b"".join(struct.pack(">H", offset//2) for offset in offsets)
    head=bytearray(54); struct.pack_into(">I",head,0,0x00010000); struct.pack_into(">I",head,12,0x5F0F3CF5); struct.pack_into(">H",head,18,16); struct.pack_into(">h",head,50,0)
    maxp=bytearray(32); struct.pack_into(">IH",maxp,0,0x00010000,5)
    hhea=bytearray(36); struct.pack_into(">I",hhea,0,0x00010000); struct.pack_into(">H",hhea,34,5)
    hmtx=b"".join(struct.pack(">Hh",8,0) for _ in range(5))
    tables=[(b"head",bytes(head)),(b"maxp",bytes(maxp)),(b"hhea",bytes(hhea)),(b"hmtx",hmtx),(b"loca",loca),(b"glyf",glyf)]
    count=len(tables); out=bytearray(12+16*count); struct.pack_into(">IHHHH",out,0,0x00010000,count,0,0,0)
    directory=[]
    for tag,data in tables:
        while len(out)&3: out.append(0)
        offset=len(out); out.extend(data)
        padded=data+b"\0"*((-len(data))&3)
        words=struct.unpack(">"+"I"*(len(padded)//4),padded)
        checksum=sum(words)&0xffffffff
        if tag==b"head":
            checkdata=bytearray(padded); checkdata[8:12]=b"\0"*4
            checksum=sum(struct.unpack(">"+"I"*(len(checkdata)//4),checkdata))&0xffffffff
        directory.append((tag,checksum,offset,len(data)))
    for i,record in enumerate(directory): struct.pack_into(">4sIII",out,12+i*16,*record)
    return bytes(out)

def run_image(symbols, blob, extra=None):
    cpu=base.load_interp(base.INTERP).A64(); cpu.sp=STACK
    cpu.memory={LOAD+i:b for i,b in enumerate(blob)}
    if extra: cpu.memory.update(extra)
    cpu.pc=LOAD+symbols["main"]; cpu.x[30]=base.RETURN_PC
    for steps in range(LIMIT):
        if cpu.pc==base.RETURN_PC: return cpu.x[0],steps,cpu
        cpu.step()
    raise SystemExit(f"T4 emitted gate exceeded {LIMIT} instructions")

def fixture_memory(font):
    meta=struct.pack("<2I",MAGIC,len(font))
    memory={META+i:b for i,b in enumerate(meta)}
    memory.update({FONT_BASE+i:b for i,b in enumerate(font)})
    return memory

def real_font_memory(path,glyph_id,pixel_height):
    font=path.read_bytes(); meta=struct.pack("<5I",MAGIC,len(font),1,glyph_id,pixel_height)
    memory={META+i:b for i,b in enumerate(meta)}
    memory.update({FONT_BASE+i:b for i,b in enumerate(font)})
    return memory

def pixel_grid(cpu,glyph,width,height):
    offset=COVER+(glyph-1)*4096
    return [[cpu.memory.get(offset+y*width+x,0)&255 for x in range(width)] for y in range(height)]

def contour_polyline(contour, subdivisions=96):
    if contour[0][2]: start=contour[0]; sequence=contour[1:]
    elif contour[-1][2]: start=contour[-1]; sequence=contour[:-1]
    else: start=((contour[-1][0]+contour[0][0])/2,(contour[-1][1]+contour[0][1])/2,1); sequence=contour
    points=[(float(start[0]),float(start[1]))]; current=points[0]; i=0
    while i<len(sequence):
        p=sequence[i]
        if p[2]: current=(float(p[0]),float(p[1])); points.append(current); i+=1; continue
        nxt=sequence[i+1] if i+1<len(sequence) else start
        if nxt[2]: end=(float(nxt[0]),float(nxt[1])); advance=2
        else: end=((p[0]+nxt[0])/2,(p[1]+nxt[1])/2); advance=1
        for j in range(1,subdivisions+1):
            t=j/subdivisions; u=1-t
            points.append((u*u*current[0]+2*u*t*p[0]+t*t*end[0],u*u*current[1]+2*u*t*p[1]+t*t*end[1]))
        current=end; i+=advance
    if points[-1]!=points[0]: points.append(points[0])
    return points

def reference_mask(contours,pixel_height,units,left,top,width,height,samples=16):
    # Independent ray casting from every sample to the right. Curves are
    # flattened densely once; each row then reuses sorted crossing events.
    polylines=[contour_polyline(contour) for contour in contours]
    edges=[]
    for poly in polylines:
        for (x1,y1),(x2,y2) in zip(poly,poly[1:]):
            edges.append((x1*pixel_height/units-left,top-y1*pixel_height/units,
                          x2*pixel_height/units-left,top-y2*pixel_height/units))
    counts=[[0 for _ in range(width)] for _ in range(height)]
    for sy_index in range(height*samples):
        sy=(sy_index+.5)/samples; crossings=[]
        for x1,y1,x2,y2 in edges:
            if y1<=sy<y2:
                crossings.append((x1+(sy-y1)*(x2-x1)/(y2-y1),1))
            elif y2<=sy<y1:
                crossings.append((x1+(sy-y1)*(x2-x1)/(y2-y1),-1))
        crossings.sort()
        xs=[item[0] for item in crossings]
        prefix=[0]
        for _,direction in crossings: prefix.append(prefix[-1]+direction)
        total=prefix[-1]; py=sy_index//samples
        for sx_index in range(width*samples):
            sx=(sx_index+.5)/samples
            first_right=bisect.bisect_right(xs,sx)
            if total-prefix[first_right]: counts[py][sx_index//samples]+=1
    denom=samples*samples
    return [[(value*255+denom//2)//denom for value in row] for row in counts]

def pointwise_reference(contours,pixel_height,units,left,top,width,height,samples=4):
    """Slow direct ray-cast oracle for tiny synthetic glyphs only."""
    polys=[contour_polyline(contour) for contour in contours]
    result=[]
    for py in range(height):
        row=[]
        for px in range(width):
            count=0
            for syi in range(samples):
                y=py+(syi+.5)/samples
                for sxi in range(samples):
                    x=px+(sxi+.5)/samples; winding=0
                    for poly in polys:
                        for (x1,y1),(x2,y2) in zip(poly,poly[1:]):
                            x1=x1*pixel_height/units-left; x2=x2*pixel_height/units-left
                            y1=top-y1*pixel_height/units; y2=top-y2*pixel_height/units
                            cross=(x2-x1)*(y-y1)-(x-x1)*(y2-y1)
                            if y1<=y<y2 and cross>0: winding+=1
                            elif y2<=y<y1 and cross<0: winding-=1
                    if winding: count+=1
            row.append((count*255+samples*samples//2)//(samples*samples))
        result.append(row)
    return result

def segment_rect_distance_sq(a,b,xmin,ymin,xmax,ymax):
    """Squared distance between one segment and a pixel rectangle."""
    dx,dy=b[0]-a[0],b[1]-a[1]
    lo,hi=0.0,1.0
    for p,q in ((-dx,a[0]-xmin),(dx,xmax-a[0]),(-dy,a[1]-ymin),(dy,ymax-a[1])):
        if p==0:
            if q<0: break
        else:
            t=q/p
            if p<0: lo=max(lo,t)
            else: hi=min(hi,t)
    else:
        if lo<=hi: return 0.0
    def point_rect(px,py):
        rx=max(xmin-px,0.0,px-xmax); ry=max(ymin-py,0.0,py-ymax)
        return rx*rx+ry*ry
    def point_segment(px,py):
        den=dx*dx+dy*dy
        t=0.0 if den==0 else max(0.0,min(1.0,((px-a[0])*dx+(py-a[1])*dy)/den))
        return (a[0]+t*dx-px)**2+(a[1]+t*dy-py)**2
    best=min(point_rect(*a),point_rect(*b))
    for corner in ((xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax)):
        best=min(best,point_segment(*corner))
    return best

def pixel_near_outline(contours,pixel_height,units,left,top,px,py):
    # Include the pixel square and a 1/8px envelope for adaptive chord error.
    margin=0.125
    rect=(px-margin,py-margin,px+1+margin,py+1+margin)
    for contour in contours:
        poly=contour_polyline(contour)
        for (x1,y1),(x2,y2) in zip(poly,poly[1:]):
            a=(x1*pixel_height/units-left,top-y1*pixel_height/units)
            b=(x2*pixel_height/units-left,top-y2*pixel_height/units)
            if segment_rect_distance_sq(a,b,*rect)==0: return True
    return False

def mutant_rejected(compiler,temp,font):
    stage=temp/"mutant"
    for rel in ("Anvil/Graphics/truetype.pbi","Anvil/Graphics/truetype_metrics.pbi","Anvil/Graphics/truetype_outlines.pbi","Anvil/Graphics/truetype_raster.pbi","Anvil/Graphics/truetype_raster_neon.pbi","RaspberryPi4/Tests/truetype_t4_gate.pi4","RaspberryPi4/Intrinsics/bcm2711_hardware.def","Boards/Raspberry_Pi_4.board"):
        target=stage/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,target)
    module=stage/"Anvil/Graphics/truetype_raster.pbi"; text=module.read_text(); anchor="capacity<width*height"
    if anchor not in text: raise SystemExit("T4 capacity mutant anchor missing")
    module.write_text(text.replace(anchor,"capacity>width*height",1))
    image=temp/"truetype_t4_mutant.img"; symbols,blob=compile_gate(compiler,stage,stage/"RaspberryPi4/Tests/truetype_t4_gate.pi4",image)
    result,_,_=run_image(symbols,blob,fixture_memory(font)); return result!=0

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--compiler",required=True); parser.add_argument("--work-dir",type=Path); parser.add_argument("--reuse-image",action="store_true"); parser.add_argument("--skip-mutant",action="store_true"); parser.add_argument("--mutant-only",action="store_true"); args=parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler=Path(args.compiler).expanduser().resolve(); font=font_bytes()
    if args.work_dir:
        args.work_dir.mkdir(parents=True,exist_ok=True)
        temp_context=nullcontext(str(args.work_dir.resolve()))
    else:
        temp_context=tempfile.TemporaryDirectory(prefix="anvil-truetype-t4-")
    with temp_context as tempname:
        temp=Path(tempname); image=temp/"truetype_t4.img"
        if args.reuse_image:
            if not image.is_file(): raise SystemExit(f"T4 reusable image missing: {image}")
            symbols,blob=base.parse_symbols(image),image.read_bytes()
        else:
            symbols,blob=compile_gate(compiler,ROOT,GATE,image)
        if args.mutant_only:
            if not mutant_rejected(compiler,temp,font): raise SystemExit("T4 weakened capacity source mutant was not rejected")
            print("PASS: T4 weakened raster capacity mutant rejected")
            return 0
        result,steps,cpu=run_image(symbols,blob,fixture_memory(font))
        if result: raise SystemExit(f"T4 emitted gate failed case {result}")
        dims={g:struct.unpack("<6q",bytes(cpu.memory.get(OUT+(g-1)*48+k,0) for k in range(48))) for g in range(1,5)}
        ring=dims[1]; w,h=ring[0],ring[1]; grid=pixel_grid(cpu,1,w,h)
        expected=[[255 if not (2<=x<6 and 2<=y<6) else 0 for x in range(8)] for y in range(8)]
        if (w,h)!=(8,8) or grid!=expected: raise SystemExit("T4 reversed-winding two-contour ring coverage mismatch")
        if dims[2][0:2]!=(8,8): raise SystemExit("T4 start-on/end-off contour has wrong bounds")
        if dims[3][0:2]!=(28,32): raise SystemExit("T4 low-UPEM/high-size all-offcurve bounds mismatch")
        if dims[4][0:2]!=(0,0): raise SystemExit("T4 empty glyph must have zero bitmap extent")
        references={2: [[(0,0,1),(8,0,1),(4,8,0)]],3: [ALL_OFF]}
        for glyph,contours in references.items():
            width,height=dims[glyph][0:2]; size=16 if glyph==2 else 64
            actual=pixel_grid(cpu,glyph,width,height)
            reference4=reference_mask(contours,size,16,0,8*size//16,width,height,samples=4)
            if reference4!=pointwise_reference(contours,size,16,0,8*size//16,width,height,samples=4):
                raise SystemExit(f"T4 reference implementations disagree for glyph {glyph}")
            errors4=[abs(actual[y][x]-reference4[y][x]) for y in range(height) for x in range(width)]
            maximum4=max(errors4,default=0); mean4=sum(errors4)/max(1,len(errors4))
            # The rasterizer adaptively flattens each quadratic to a maximum
            # 1/8-pixel chord error; the 4x4 reference uses exact dense curves.
            # Allow at most three 1/16-alpha sample quanta in any one pixel.
            if maximum4>48 or mean4>2:
                mismatches=[(x,y,actual[y][x],reference4[y][x]) for y in range(height) for x in range(width) if actual[y][x]!=reference4[y][x]]
                actual_ascii="/".join("".join("#" if v>127 else "." for v in row) for row in actual)
                ref_ascii="/".join("".join("#" if v>127 else "." for v in row) for row in reference4)
                raise SystemExit(f"T4 emitted mask differs from independent 4x4 sample oracle: glyph {glyph}, max={maximum4}, mean={mean4:.2f}, first={mismatches[:20]}, actual={actual_ascii}, reference={ref_ascii}")
            reference32=reference_mask(contours,size,16,0,8*size//16,width,height,samples=32)
            high_errors=[abs(actual[y][x]-reference32[y][x]) for y in range(height) for x in range(width)]
            maximum32=max(high_errors,default=0); mean32=sum(high_errors)/max(1,len(high_errors))
            print(f"MEASURE: T4 synthetic glyph {glyph}: 4x4 reference max {maximum4}, mean {mean4:.2f}; 32x high-res deviation max {maximum32}, mean {mean32:.2f} (all /255)")
        # Compare emitted real-font coverage to a separately flattened and
        # supersampled fontTools glyf outline, with a stated edge-sampling bound.
        vendored=ROOT/"_work/fonttools-20260918"
        if vendored.is_dir(): sys.path.insert(0,str(vendored))
        from fontTools.ttLib import TTFont
        corpus=[ROOT/"_work/truetype-fonts-20260918/abel/Abel-Regular.ttf",
                ROOT/"_work/truetype-fonts-20260918/bangers/Bangers-Regular.ttf"]
        real_count=0
        for path in corpus:
            if not path.is_file():
                print(f"SKIP: missing real T4 font {path.name}"); continue
            tt=TTFont(path); glyf=tt["glyf"]; order=tt.getGlyphOrder(); ids={n:i for i,n in enumerate(order)}
            cmap=tt.getBestCmap() or {}; units=tt["head"].unitsPerEm
            for cp in (0x4F,0xE9):
                name=cmap.get(cp)
                if not name: continue
                coords,ends,flags=glyf[name].getCoordinates(glyf)
                if not coords or not ends: continue
                contours=[]; first=0
                for end in ends:
                    contours.append([(int(coords[i][0]),int(coords[i][1]),int(bool(flags[i]&1))) for i in range(first,end+1)])
                    first=end+1
                xs=[x for contour in contours for x,_,_ in contour]; ys=[y for contour in contours for _,y,_ in contour]
                for pixel_height in (16,32):
                    extra=real_font_memory(path,ids[name],pixel_height)
                    result,steps,real_cpu=run_image(symbols,blob,extra)
                    if result: raise SystemExit(f"T4 real-font gate failed {path.name} U+{cp:04X} size {pixel_height}: case {result}")
                    values=struct.unpack("<6q",bytes(real_cpu.memory.get(OUT+k,0) for k in range(48)))
                    width,height,stride,left,top,_=values
                    scaled_min=math.floor(min(xs)*pixel_height/units)
                    scaled_max=math.ceil(max(xs)*pixel_height/units)
                    scaled_bottom=math.floor(min(ys)*pixel_height/units)
                    scaled_top=math.ceil(max(ys)*pixel_height/units)
                    if (width,height,stride,left,top)!=(scaled_max-scaled_min,scaled_top-scaled_bottom,scaled_max-scaled_min,scaled_min,scaled_top):
                        raise SystemExit(f"T4 fontTools bounds mismatch {path.name} U+{cp:04X} at {pixel_height}px")
                    got=pixel_grid(real_cpu,1,width,height)
                    ref4=reference_mask(contours,pixel_height,units,left,top,width,height,samples=4)
                    if path.name=="Abel-Regular.ttf" and cp==0x4F and pixel_height==16:
                        direct=pointwise_reference(contours,pixel_height,units,left,top,width,height,samples=4)
                        if direct!=ref4: raise SystemExit("T4 optimized crossing oracle disagrees with direct ray-cast oracle on Abel O")
                    errors4=[abs(got[y][x]-ref4[y][x]) for y in range(height) for x in range(width)]
                    maximum4=max(errors4,default=0); mean4=sum(errors4)/max(1,len(errors4))
                    if maximum4>48:
                        mismatches=[(x,y,got[y][x],ref4[y][x]) for y in range(height) for x in range(width) if got[y][x]!=ref4[y][x]]
                        raise SystemExit(f"T4 {path.name} U+{cp:04X} {pixel_height}px exceeds three 4x4 sample quanta: bounds={width}x{height}, points={len(coords)}, contours={len(ends)}, max={maximum4}, mean={mean4:.2f}, first={mismatches[:12]}")
                    mismatches=[(x,y) for y in range(height) for x in range(width) if got[y][x]!=ref4[y][x]]
                    outside=[(x,y) for x,y in mismatches if not pixel_near_outline(contours,pixel_height,units,left,top,x,y)]
                    if outside: raise SystemExit(f"T4 coverage differs away from the 1/8px flatten envelope: {path.name} U+{cp:04X} {pixel_height}px {outside[:12]}")
                    ref32=reference_mask(contours,pixel_height,units,left,top,width,height,samples=32)
                    high=[abs(got[y][x]-ref32[y][x]) for y in range(height) for x in range(width)]
                    max32=max(high,default=0); mean32=sum(high)/max(1,len(high))
                    print(f"MEASURE: T4 fontTools {path.name} U+{cp:04X} {pixel_height}px: 4x4 max {maximum4}, mean {mean4:.2f}; 32x deviation max {max32}, mean {mean32:.2f} (all /255); {steps} instructions")
                    real_count+=1
        if real_count==0: raise SystemExit("T4 real fontTools outline oracle did not run")
        if not args.skip_mutant and not mutant_rejected(compiler,temp,font): raise SystemExit("T4 weakened capacity source mutant was not rejected")
        print(f"PASS: T4 emitted raster gate; ring multi-contour topology, start-on/end-off, all-offcurve midpoint at 64px, empty glyph; {steps} instructions")
        print("PASS: reversed-winding hole exact mask; capacity mutant rejected; coverage bound checked on emitted pixels")

if __name__=="__main__": raise SystemExit(main())
