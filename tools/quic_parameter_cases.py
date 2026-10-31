"""Independent RFC 9000 transport-parameter fixtures and expected refusals."""
from quic_wire_cases import integer,MAX
ARG,SHORT,VALUE,DUP,ROLE,LIMIT,MISSING,CID,STATE=range(-3381,-3390,-1)
NUMERIC={1,3,4,5,6,7,8,9,10,11,14}
def field(i,data):return integer(i)+integer(len(data))+data
def layout(wire):
 def read(pos):
  n=1<<(wire[pos]>>6);return int.from_bytes(wire[pos:pos+n],'big')&((1<<(8*n-2))-1),pos+n
 p=0;result=[]
 while p<len(wire):
  i,p=read(p);n,p=read(p);v=read(p)[0] if i in NUMERIC else -1
  result.append([i,p,n,v]);p+=n
 return result
def cases():
 rows=[];base=field(0,b'original')+field(15,b'initial');client=field(15,b'initial')
 pref=b'\x01\x02\x03\x04\x01\xbb'+b'\0'*16+b'\0\0'+b'\x03cid'+bytes(range(16))
 def add(name,wire=base,rc=1,**kw):
  c=dict(name=name,wire=wire.hex(),rc=rc,server=1,capacity=64,cancel=0,alias=0,initial='initial'.encode().hex(),original='original'.encode().hex(),retry='',used_retry=0,ids_rc=1)
  c.update(kw);c['entries']=layout(wire) if rc==1 else None;rows.append(c)
 add('server-minimal');add('client-minimal',client,server=0)
 add('zero-ids',field(0,b'')+field(15,b''),initial='',original='')
 extras=b''.join(field(i,integer(v)) for i,v in [(1,10000),(3,1452),(4,MAX),(5,999),(6,999),(7,999),(8,100),(9,100),(10,3),(11,25),(14,2)])
 add('all-defined',base+extras+field(2,bytes(range(16)))+field(12,b'')+field(13,pref)+field(16,b'retry'),retry=b'retry'.hex(),used_retry=1)
 for i,low,high in [(3,1199,1200),(8,1<<60,(1<<60)+1),(9,1<<60,(1<<60)+1),(10,20,21),(11,16383,16384),(14,1,2)]:
  for v in (low,high):add(f'range-{i}-{v}',base+field(i,integer(v)),rc=1 if ((i in (3,14) and v==high) or (i not in (3,14) and v==low)) else VALUE)
 for i in sorted(NUMERIC):add(f'empty-integer-{i}',base+field(i,b''),VALUE)
 add('trailing-integer',base+field(4,b'\x01\x00'),VALUE)
 add('nonminimal',base+integer(4,8)+integer(8,8)+integer(17,8))
 for i in (0,15,16):
  wire=(client if i==0 else field(0,b'original') if i==15 else base)+field(i,b'x'*21)
  add(f'long-id-{i}',wire,VALUE)
 add('missing-initial',field(0,b'original'),MISSING);add('missing-original',client,MISSING)
 add('duplicate-known',base+field(15,b'initial'),DUP)
 add('unknown-max',base+field(MAX,b'extension'))
 add('duplicate-unknown',base+field(MAX,b'a')+field(MAX,b'b'),DUP)
 for i,data in [(0,b'original'),(2,b'x'*16),(13,pref),(16,b'retry')]:add(f'client-server-only-{i}',client+field(i,data),ROLE,server=0)
 for n in (15,17):add(f'reset-token-{n}',base+field(2,b'x'*n),VALUE)
 add('migration-nonempty',base+field(12,b'x'),VALUE)
 for label,data in [('zero',pref[:24]+b'\0'+b'x'*16),('long',pref[:24]+b'\x15'+b'x'*37),('truncated',pref[:-1]),('extra',pref+b'x')]:add('preferred-'+label,base+field(13,data),VALUE)
 add('preferred-zero-initial',field(0,b'original')+field(15,b'')+field(13,pref),VALUE)
 for label,data in [('id',b'\xc0'),('length',b'\x1f\x80'),('value',b'\x1f\x08abcd')]:add('truncated-'+label,base+data,SHORT)
 add('wrong-initial',initial=b'wrong'.hex(),ids_rc=CID);add('wrong-original',original=b'wrong'.hex(),ids_rc=CID)
 add('missing-retry',used_retry=1,retry=b'retry'.hex(),ids_rc=MISSING)
 add('unexpected-retry',base+field(16,b'retry'),ids_rc=CID)
 add('wrong-retry',base+field(16,b'retry'),used_retry=1,retry=b'other'.hex(),ids_rc=CID)
 add('capacity-overflow',capacity=1,rc=LIMIT)
 add('capacity-64',base+b''.join(field(100+i,b'') for i in range(62)))
 add('capacity-65',base+b''.join(field(100+i,b'') for i in range(63)),LIMIT)
 add('cancel',rc=STATE,cancel=1)
 add('alias',rc=ARG,alias=1);add('bad-role',rc=ARG,server=2);add('bad-capacity',rc=ARG,capacity=0)
 return rows
