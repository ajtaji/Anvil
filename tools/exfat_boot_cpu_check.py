import struct

def check(raw,cases):
 magic,hz=struct.unpack_from('<2q',raw);assert magic==0x424f4f54 and hz>0
 used=set(range(16));rows=[]
 for c in cases:
  at=512+c['index']*64;v=struct.unpack_from('<6q',raw,at)
  assert v[:5]==tuple(c[k] for k in ['result','error','calls','blocks','lba']),(c,v)
  assert v[5]>=0;used.update(range(at,at+48));rows.append(dict(case=c['index'],kind=c['kind'],microseconds=v[5]*1000000/hz,calls=v[2]))
 assert all(value==165 for i,value in enumerate(raw) if i not in used),'report guards'
 return dict(cases=len(rows),sector_sizes=[512,1024,2048,4096],primary_and_backup=True,rows=rows)
