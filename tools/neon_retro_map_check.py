"""Independent continuous-coordinate oracle for CRT pointer mapping."""
from pathlib import Path
import json,struct
CASES=json.loads(Path(__file__).with_name('neon_retro_map_cases.json').read_text())
def check(data):
    assert len(data)==16384 and struct.unpack_from('<2q',data)==(0x43525431,len(CASES))
    assert not any(data[16:64]) and not any(data[64+32*len(CASES):])
    for i,(cw,ch,tw,th,x,y) in enumerate(CASES):
        w,h=(tw,tw*ch//cw) if tw*ch<=th*cw else (th*cw//ch,th)
        left,top=(tw-w)//2,(th-h)//2
        nx,ny=2*(x-left)/w-1,2*(y-top)/h-1
        radius=nx*nx+ny*ny
        u,v=(nx*(1+.015*radius)+1)/2,(ny*(1+.015*radius)+1)/2
        inside=left<=x<left+w and top<=y<top+h and 0<=u<=1 and 0<=v<=1
        fit,rc,ox,oy=struct.unpack_from('<4q',data,64+32*i)
        assert fit==0 and rc==int(inside),(i,fit,rc,inside)
        if inside:assert abs(ox-u*cw*65536)<=64 and abs(oy-v*ch*65536)<=64,(i,ox,oy,u,v)
        else:assert (ox,oy)==(1234567,-7654321),i
    return dict(cases=len(CASES),tolerance_canvas_pixels=1/1024)
