"""Short-lived IPv6 DNS test endpoint forwarding unchanged queries to public DNS.

This is test equipment, not a production resolver. It accepts only the fixed
qualification name and records wire bytes to prove the actual transport.
"""
import socket, struct, threading, ipaddress
from http.server import HTTPServer, BaseHTTPRequestHandler

class Forwarder:
    def __init__(self, address):
        self.address=address
        self.rows=[];self.errors=[];self.done=threading.Event()
        self.sock=socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
        self.sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
        self.sock.bind((address,53));self.sock.listen(4);self.sock.settimeout(.2)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    @staticmethod
    def read(sock,n):
        out=bytearray()
        while len(out)<n:
            chunk=sock.recv(n-len(out))
            if not chunk:raise EOFError('incomplete DNS frame')
            out.extend(chunk)
        return bytes(out)
    def run(self):
        while not self.done.is_set():
            try:c,peer=self.sock.accept()
            except socket.timeout:continue
            except OSError:break
            try:
                with c:
                    c.settimeout(4);length=self.read(c,2);n=struct.unpack('!H',length)[0]
                    if not 12<=n<=512:raise ValueError('unexpected query size')
                    query=self.read(c,n)
                    question=query[12:-4]
                    if query[-4:] not in (b'\0\1\0\1',b'\0\x1c\0\1'):raise ValueError('unexpected query type')
                    upstream_name='1.1.1.1:53'
                    if question==b'\x0aanvil-ipv6\x04test\0':
                        is6=query[-4:-2]==b'\0\x1c'
                        reply=query[:2]+struct.pack('!5H',0x8180,1,int(is6),0,0)+query[12:]
                        if is6:reply+=b'\xc0\x0c'+struct.pack('!HHIH',28,1,0,16)+ipaddress.IPv6Address(self.address).packed
                        size=struct.pack('!H',len(reply));upstream_name='controlled local test zone'
                    elif question==b'\x03one\x03one\x03one\x03one\0':
                        with socket.create_connection(('1.1.1.1',53),timeout=4) as upstream:
                            upstream.sendall(length+query)
                            size=self.read(upstream,2);reply=self.read(upstream,struct.unpack('!H',size)[0])
                    else:raise ValueError('unexpected qualification name')
                    c.sendall(size+reply)
                    self.rows.append(dict(family=6,peer=peer[0],upstream=upstream_name,query=query.hex(),reply=reply.hex()))
            except Exception as e:self.errors.append(str(e))
    def close(self):
        self.done.set();self.sock.close();self.thread.join(10)
        if self.thread.is_alive():raise RuntimeError('DNS forwarder did not stop')

class WebFixture:
    def __init__(self,address):
        self.rows=[];rows=self.rows
        class Server(HTTPServer):
            address_family=socket.AF_INET6
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=bytes(32+i%95 for i in range(20000))
                rows.append(dict(peer=self.client_address[0],host=self.headers.get('Host'),target=self.path,bytes=len(body)))
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.send_header('Connection','close');self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        self.server=Server((address,8088),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(5)
        if self.thread.is_alive():raise RuntimeError('HTTP test server did not stop')
