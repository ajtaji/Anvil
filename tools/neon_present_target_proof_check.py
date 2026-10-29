from pathlib import Path
import struct,json,sys
rows=[
[1,0,101,202,303,404,123,0,800,1280],
[2,-81,0,0,0,0,1,0,800,1280],
[3,-82,101,0,0,0,12,0,800,1280],
[4,-83,101,202,0,0,123,0,800,1280],
[5,0,0,0,0,0,456,0,0,0],
[6,-84,101,202,303,404,4,0,0,0],
[7,-85,101,202,0,404,45,0,0,0],
[8,-86,101,0,0,404,456,0,0,0],
[9,0,101,202,303,404,789,1,0,0],
[10,1,101,202,303,404,7,0,0,0],
[11,-20004,101,202,303,404,0,0,0,0],
[12,-20003,101,202,303,404,780,0,0,0],
[13,-89,101,202,303,404,7890,0,0,0],
[14,-80,101,202,303,404,7890,1,0,0],
[15,-84,101,202,303,404,4,1,0,0],
[16,-20004,101,202,303,404,0,0,0,0],
[17,-20001,0,0,0,0,0,0,0,0]]
want=struct.pack('<8q',0x57535450,0,17,10,0,0,0,0)+b''.join(struct.pack('<10q',*row) for row in rows)
want+=bytes(4096-len(want))
def verify(raw):
 assert raw==want,'Controlled target report mismatch at '+str(next((i for i,(a,b) in enumerate(zip(raw,want)) if a!=b),None))
if len(sys.argv)>1:verify(Path(sys.argv[1]).read_bytes())
for offset in list(range(0,64+170*8,8))+[4095]:
 bad=bytearray(want);bad[offset]^=1
 try:verify(bytes(bad))
 except AssertionError:continue
 raise AssertionError('corruption accepted')
print(json.dumps(dict(cases=17,state_words=170,synthetic_corruptions_rejected=179,controlled_providers=True)))
