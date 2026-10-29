"""Independent result oracle for random service refusals and crypto state isolation."""
import struct,hashlib,hmac
def check(data,cases=None):
 assert struct.unpack_from('<Q',data)[0]==0x524e4731
 values=struct.unpack_from('<38q',data,256)
 expected={0:-101,1:-101,2:-102,3:0,4:-103,5:-102,6:-102,7:-102,8:-110,9:-105,10:-105,11:-105,12:-105,13:16,14:-103,15:1,16:-109,17:-109,18:-109,19:0,26:16,27:1,28:-105,29:0,30:16,31:16,32:-105,33:0,34:16,35:16,36:4,37:0}
 for i in range(21,26):expected[i]=0
 for i,e in expected.items():assert values[i]==e,(i,values[i],e)
 assert data[1024:1056]==hashlib.sha256(b'prefixsuffix').digest(),'SHA state changed'
 assert data[1056:1088]==hmac.new(b'key',b'firstlast',hashlib.sha256).digest(),'HMAC state changed'
 # Independent HMAC_DRBG state oracle: first short entropy read is refused;
 # second seed is bytes2..49; two16-byte requests, failed reseed, good reseed4..35.
 k=bytes(32);v=bytes([1])*32
 def mac(key,msg):return hmac.new(key,msg,hashlib.sha256).digest()
 def update(seed):
  nonlocal k,v
  k=mac(k,v+b'\0'+seed);v=mac(k,v)
  if seed:k=mac(k,v+b'\1'+seed);v=mac(k,v)
 def generate():
  nonlocal v
  v=mac(k,v);out=v[:16];update(b'');return out
 update(bytes(range(2,50)));generate();second=generate()
 assert data[1088:1104]==second,'DRBG output differs'
 update(bytes(range(4,36)));third=generate()
 assert data[1104:1120]==third,'reseed output differs'
 return {'cases':len(expected),'sha256':True,'hmac':True,'drbg':True,'reseed':True}
