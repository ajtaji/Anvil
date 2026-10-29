from pathlib import Path
import sys,struct,json
mode=sys.argv[1];assert mode in ['old','fixed']
old=[
[1,0,0,0,1,0,0,0,0,0,1,-20004],
[2,0,1,1,0,1,1,0,0,0,0,0],
[3,0,0,0,0,1,0,0,0,0,0,0],
[4,0,0,0,0,0,0,0,0,0,0,0],
[5,0,0,0,0,0,0,0,0,0,0,0],
[6,0,0,0,0,0,0,0,0,0,0,0],
[7,0,0,0,0,1,0,0,1,0,0,0],
[8,0,1,1,0,1,1,1,0,0,0,0],
[9,-20004,0,0,1,0,0,0,0,0,1,-20004],
[10,-20002,0,0,0,0,0,0,0,0,0,0],
[11,-20002,0,0,0,0,0,0,0,0,0,0]]
fixed=[
[1,-20004,1,1,1,0,0,0,0,0,1,-20004],
[2,-20004,1,1,1,1,1,0,0,1,0,-20004],
[3,-20004,1,1,0,1,0,0,0,0,0,-20004],
[4,0,0,0,0,0,0,0,0,0,0,0],
[5,-20004,1,1,1,0,0,0,0,0,0,-20004],
[6,0,0,0,0,0,0,0,0,0,0,0],
[7,0,0,0,0,1,0,0,1,0,0,0],
[8,-20004,1,1,1,1,1,1,0,0,0,-20004],
[9,-20004,1,1,1,0,0,0,0,0,1,-20004],
[10,-20002,0,0,0,0,0,0,0,0,0,-20002],
[11,-20002,0,0,0,0,0,0,0,0,0,-20002]]
def expected(rows):
 b=struct.pack('<8q',0x50415254,0,11,12,0,0,0,0)+b''.join(struct.pack('<12q',*r) for r in rows)
 return b+bytes(4096-len(b))
want=expected(old if mode=='old' else fixed)
def verify(raw):
 assert raw==want,'Parent report mismatch at '+str(next((i for i,(a,b) in enumerate(zip(raw,want)) if a!=b),None))
if len(sys.argv)>2:verify(Path(sys.argv[2]).read_bytes())
try:verify(expected(fixed if mode=='old' else old))
except AssertionError:pass
else:raise AssertionError('Opposite implementation accepted')
for at in list(range(0,64+132*8,8))+[4095]:
 b=bytearray(want);b[at]^=1
 try:verify(bytes(b))
 except AssertionError:continue
 raise AssertionError('Corrupt parent report accepted')
print(json.dumps(dict(mode=mode,cases=11,state_words=132,synthetic_corruptions_rejected=141,opposite_rejected=True,controlled_backend=True)))
