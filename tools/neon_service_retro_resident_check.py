"""Check installed resident CRT rendering through the public client."""
import struct
from neon_resident_retro_gpu_check import check_picture
EXPECTED=[0,0,1280,800,1,0,0,0,0,0,0,-21503,0,-21503,0,0,0,1]
def check(report,picture):
    expected=bytearray(16384)
    for o,v in {0:0x4e525232,8:1,24:len(EXPECTED)}.items():struct.pack_into('<q',expected,o,v)
    for i,v in enumerate(EXPECTED):struct.pack_into('<2q',expected,1024+16*i,v,v)
    assert report==expected,'resident report differs: '+str([(i,struct.unpack_from('<q',report,i)[0],struct.unpack_from('<q',expected,i)[0]) for i in range(0,len(report),8) if report[i:i+8]!=expected[i:i+8]][:12])
    count=check_picture(picture)
    return dict(checks=len(EXPECTED),pixel_samples=count,scope='Installed minor12 resident provider; pure client with no GPU linked')
