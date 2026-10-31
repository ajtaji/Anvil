"""Independent UDP fixture peer; deliberately not a TLS or HTTP/3 server."""
import json,socket,threading,time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from quic_crypto_cases import CID,keys,protect
from quic_wire_cases import long

class Peer:
 def __init__(self,path):
  self.path=path;self.events=[];self.errors=[];self.acks=0;self.stop=threading.Event()
 def __enter__(self):
  self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:
   self.socket.bind(('192.168.1.104',55442));self.socket.settimeout(0.2)
   self.worker=threading.Thread(target=self.run);self.worker.start()
  except BaseException:
   self.socket.close();raise
  return self
 def run(self):
  try:
   opened=False
   while not self.stop.is_set():
    try:wire,address=self.socket.recvfrom(65535)
    except socket.timeout:continue
    self.events.append(dict(direction='receive',peer=address,wire=wire.hex(),time=time.time()))
    assert address==('192.168.1.114',55013),address
    if not opened:
     assert wire==b'QH01',wire.hex()
     opened=True
     plain=b'\x06\x00\x03abc\x01'+bytes(1151)
     header=long(0,dcid=b'abcdefgh',scid=b'WXYZ',pn=1,pnbytes=4,cipher=len(plain)+16)
     good=protect(header,plain,1,keys(CID,1));bad=good[:-1]+bytes([good[-1]^1])
     assert len(good)==1200
     for name,packet in [('bad tag',bad),('valid',good),('duplicate',good)]:
      assert self.socket.sendto(packet,address)==1200
      self.events.append(dict(direction='send',name=name,wire=packet.hex(),time=time.time()))
    else:
     assert self.acks==0,'Unexpected additional reply'
     assert len(wire)==1200,len(wire)
     secret,key,iv,hp=keys(CID,0)
     # These fixed offsets belong only to this fixture's two known CIDs and
     # four-byte packet number. No production parser is used as the oracle.
     mask=Cipher(algorithms.AES(hp),modes.ECB()).encryptor().update(wire[26:42])
     header=bytearray(wire[:26]);header[0]^=mask[0]&15
     for i in range(4):header[22+i]^=mask[1+i]
     assert bytes(header)==long(0,dcid=b'WXYZ',scid=b'abcdefgh',pn=0,pnbytes=4,cipher=1174)
     plain=AESGCM(key).decrypt(iv,wire[26:],bytes(header))
     assert plain==b'\x02\x01\x00\x00\x00'+bytes(1153)
     self.acks+=1
     # ACK the Pi's padded Initial, using a fresh server packet number. This
     # ACK-only packet must not start an acknowledgment response loop.
     reply=b'\x02\x00\x00\x00\x00'+bytes(1153)
     header=long(0,dcid=b'abcdefgh',scid=b'WXYZ',pn=2,pnbytes=4,cipher=1174)
     packet=protect(header,reply,2,keys(CID,1))
     assert self.socket.sendto(packet,address)==1200
     self.events.append(dict(direction='send',name='acknowledge Pi packet zero',wire=packet.hex(),time=time.time()))
  except Exception as e:self.errors.append(repr(e))
 def check(self):
  assert not self.errors,self.errors
  assert self.acks==1,self.acks
 def __exit__(self,*exc):
  self.stop.set();self.worker.join(timeout=3);self.socket.close()
  if self.worker.is_alive():self.errors.append('Peer failed to stop')
  self.path.write_text(json.dumps(dict(events=self.events,errors=self.errors,acks=self.acks),indent=2))
