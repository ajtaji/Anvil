"""Validate bounded service timing accounting without imposing a latency claim."""
import re

def check(text):
 rows=[]
 for name,values in re.findall(r'^  ([^:\n]+): (\d+ / \d+ / \d+ / \d+)$',text,re.M):
  calls,total,maximum,worst=map(int,values.split(' / '))
  assert maximum<=total and (calls>0 or total==maximum==worst==0),(name,values)
  rows.append(dict(phase=name,calls=calls,total_us=total,max_us=maximum,worst_call_us=worst))
 assert len(rows)==14 and rows[0]['phase']=='whole service',rows
 whole=rows[0];assert whole['calls']>0 and whole['worst_call_us']==whole['max_us']
 assert sum(r['total_us'] for r in rows[1:])<=whole['total_us']
 assert sum(r['worst_call_us'] for r in rows[1:])<=whole['max_us']
 result=dict(rows=rows,service_max_us=whole['max_us'],accounting_passed=True)
 m=re.search(r'Root I/O maximum microseconds \(storage/open/read/close\): (\d+) / (\d+) / (\d+) / (\d+)',text)
 if m:result['root_io_max_us']=dict(zip(['storage','open','read','close'],map(int,m.groups())))
 storage=[]
 for name,values in re.findall(r'^  exFAT ([^:\n]+): (\d+ / \d+ / \d+)$',text,re.M):
  calls,total,maximum=map(int,values.split(' / '))
  assert maximum<=total and (calls>0 or total==maximum==0),(name,values)
  storage.append(dict(phase=name,calls=calls,total_us=total,max_us=maximum))
 if storage:
  assert len(storage)==7,storage
  result['exfat_phases']=storage
 if 'TLS arithmetic steps (calls / total us / maximum us):' in text:
  names=['P256 begin','P256 step','P384/P521 begin','P384/P521 step','RSA begin','RSA step','X25519 begin','X25519 step','GCM decrypt begin','GCM decrypt step','GCM encrypt begin','GCM encrypt step']
  jobs=[]
  for name in names:
   matches=re.findall(r'^  '+re.escape(name)+r': (\d+) / (\d+) / (\d+)$',text,re.M)
   assert len(matches)==1,(name,matches)
   calls,total,maximum=map(int,matches[0])
   assert maximum<=total and (calls>0 or total==maximum==0),(name,matches)
   jobs.append(dict(operation=name,calls=calls,total_us=total,max_us=maximum))
  result['tls_arithmetic']=jobs
  gap=re.search(r'TLS longest interval (?:between yield checks|without a yield check), microseconds: (\d+)',text)
  assert gap is not None
  result['tls_yield_check_gap_max_us']=int(gap[1])
  endpoint=re.search(r'TLS longest interval endpoints: (-?\d+) -> (-?\d+)',text)
  if endpoint:result['tls_yield_check_gap_endpoints']=list(map(int,endpoint.groups()))
 return result
