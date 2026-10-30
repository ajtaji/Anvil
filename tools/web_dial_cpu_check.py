"""Verify both-family fallback, race cleanup, ABI compatibility and cancellation."""
import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==131072 and q(0)==0x4449414c and q(8)==18
 used=set(range(16));rows=[]
 # rc, winning handle, open4 calls, open6 calls, closed4, closed6, closedTLS
 expected=[(1,1,1,0,1,0,0),(-105,0,0,0,0,0,0),(1,2,0,1,0,1,0),
 (1,2,1,1,1,1,0),(1,1,1,1,1,1,0),(0,0,1,1,1,1,0),
 (-105,0,0,0,0,0,0),(1,2,0,1,0,1,0),(1,1,1,1,1,1,0),
 (1,1,1,0,1,0,0),(1,1,1,1,1,1,0),(1,1,3,0,1,0,0),
 (-105,0,0,0,0,0,0),(1,1,1,0,1,0,0),(1,1,1,0,1,0,0),
 (1,3,0,0,0,0,1),(1,1,2,0,2,0,0),(1,2,1,1,1,1,0)]
 for i in cases:
  p=256+i*128;v=[q(p+j*8) for j in range(14)];used.update(range(p,p+112))
  actual=tuple(v[j] for j in [0,1,2,3,6,7,8]);assert actual==expected[i],(i,actual,expected[i],v)
  assert v[9:12]==[0,0,0],('leaked handle',i,v)
  if i in (0,1,6,7,14,15):assert v[5]==0,('unexpected AAAA',i,v)
  if i in (3,4,5,8,9,17):assert v[12]>=250,(i,v)
  if i in (0,1,6,14):assert v[13]==0,(i,v)
  rows.append(dict(case=i,result=v[0],winner=v[1],time_ms=v[12],dns4=v[4],dns6=v[5]))
 assert all(v==165 for i,v in enumerate(data) if i not in used),'report guards'
 return rows
