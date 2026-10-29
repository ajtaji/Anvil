"""Independent event-contract oracle for curved canvas input."""
import struct
# rc, down, pressed, released, blocked, cancelled, x, y, wheel, ticks, retro, contact
ROWS=[
(0,0,0,0,0,0,-1,-1,0,0,1,-1),
(0,1,1,0,0,0,400,300,0,10,1,0),
(-22302,1,1,0,0,0,400,300,0,10,1,0),
(0,1,0,0,0,0,-12,-9,0,11,1,0),
(0,0,0,1,0,0,-12,-9,0,12,1,-1),
(0,0,0,0,1,0,-12,-9,0,13,1,-1),
(0,0,0,0,1,0,400,300,0,14,1,-1),
(0,0,0,0,0,0,400,300,0,15,1,-1),
(0,1,1,0,0,0,400,300,0,16,1,0),
(0,1,0,0,0,0,400,300,0,16,1,0),
(0,0,0,0,0,1,-1,-1,0,16,1,-1),
(0,0,0,0,0,0,-12,-9,0,18,1,-1),
(0,0,0,0,0,0,400,300,2,19,1,-1),
(0,0,0,0,0,0,-1,-1,0,19,0,-1),
(0,1,1,0,0,0,0,0,0,20,0,0)]
def check(blob):
 assert len(blob)>=64+len(ROWS)*96
 assert struct.unpack_from('<qq',blob)==(0x43495231,len(ROWS))
 for i,expected in enumerate(ROWS):
  actual=struct.unpack_from('<12q',blob,64+i*96)
  for k,(a,e) in enumerate(zip(actual,expected)):
   if k in (6,7):
    a=struct.unpack('<f',struct.pack('<I',a&0xffffffff))[0]
    assert abs(a-e)<0.001,(i,k,a,e)
   else:assert a==e,(i,k,a,e)
 return dict(rows=len(ROWS),fields=len(ROWS)*12)
