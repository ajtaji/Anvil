"""Independent reader of physical UDP owner observations."""
import struct
def check(report,cases):
 magic,count=struct.unpack_from('<2q',report)
 assert magic==0x55445331 and count==len(cases),(hex(magic),count,len(cases))
 failures=[]
 for i,c in enumerate(cases):
  actual=struct.unpack_from('<q',report,256+8*i)[0]
  if actual!=c['expected']:failures.append(dict(name=c['name'],actual=actual,expected=c['expected']))
 assert not failures,failures
 return dict(passed=count)
