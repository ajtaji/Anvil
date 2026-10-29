"""Check physical TLS record/send budgeting report (crypto is a test double)."""
import struct

def check(raw,cases=None):
    assert len(raw)==16384
    assert struct.unpack_from('<QQ',raw)==(0x544c4231,14)
    expected=[
      (7,1,0,0,0,0,0,0),(14,2,0,0,0,0,0,0),(21,3,0,0,0,0,0,0),
      (0,0,0,0,0,0,0,0),(3,0,3,0,0,0,0,0),(4,1,0,0,0,0,0,0),
      (-1,1,0,0,0,0,0,0),(-1,0,5,2,0,0,0,0),
      (0,1,0,0,7,0,0,2),(0,3,0,0,0,0,0,6),
      (0,0,0,0,0,3,1,10),(0,0,0,0,0,0,1,10),
      (-1,0,0,-105,0,0,1,10),(0,0,0,0,0,0,4,0)]
    for i,want in enumerate(expected):
        actual=struct.unpack_from('<8q',raw,256+i*64)
        assert actual==want,(i,actual,want)
    return dict(cases=len(expected),passed=True,crypto='controlled double')
