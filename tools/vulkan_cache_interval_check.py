import struct
import json
from pathlib import Path
CASES=json.loads((Path(__file__).with_name('vulkan_cache_interval_cases.json')).read_text())

def union(items):
 out=[]
 for a,b in sorted(items):
  if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(b,out[-1][1]))
  else:out.append((a,b))
 return out

def check(report):
 if len(report)!=8192:raise ValueError('length')
 words=struct.unpack('<1024Q',report);n=words[1]
 if words[0]!=0x43494e31 or not 1<=n<=len(CASES):raise ValueError('header')
 if words[2:7]!=(1,1,0,1,92160):raise ValueError('reset or capacity')
 expected=[]
 for i,(a,length) in enumerate(CASES):
  valid=int(a>0 and length>0 and a+length<=0x100000000)
  if words[8+i]!=valid:raise ValueError(('admission',i))
  if valid:expected.append((a,a+length))
 actual=[tuple(words[256+i*2:258+i*2]) for i in range(n)]
 if any(not 0<a<b<=0x100000000 for a,b in actual):raise ValueError('invalid ledger')
 if union(actual)!=union(expected):raise ValueError('physical union changed')
 if words[224:226]!=(32768,36864):raise ValueError('stale lookup reset')
 return dict(cases=len(CASES),physical_intervals=n,union_intervals=len(union(actual)),passed=True)
