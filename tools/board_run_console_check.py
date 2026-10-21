"""Host UDP protocol checks; no board connection or processor emulation."""
import time
from unittest.mock import patch
import board_run as br

class Socket:
    def __init__(self):
        self.data = []
        self.sent = []
    def sendto(self, data, addr):
        self.sent.append(data)
    def recvfrom(self, count):
        return self.data.pop(0), ('192.168.1.114', 5555)

def console():
    c = br.NetConsole.__new__(br.NetConsole)
    c.addr = ('192.168.1.114', 5555)
    c.name = 'host protocol check'
    c.sock = Socket()
    c.transcript = []
    c.accepted_datagrams = []
    c.command_open = False
    c.keepalives = 0
    return c

def receive(c, *chunks):
    c.sock.data.extend(chunks)
    for _ in chunks:
        c._recv_peer()

c = console()
c.send('net recv 5001 1000000')
receive(c, b'pmf> net recv 5001 1000000\r\nListening on port 5001\r\n')
assert c.command_open
c.last_sent = time.monotonic() - br.KEEPALIVE_SECONDS - 1
c.keepalive()
assert c.sock.sent[-1] == b'' and c.keepalives == 1
receive(c, b'sha256 verified\r\np', b'mf> ')
assert not c.command_open
sent = len(c.sock.sent)
c.last_sent = time.monotonic() - br.KEEPALIVE_SECONDS - 1
c.keepalive()
assert len(c.sock.sent) == sent, 'Idle prompt must not emit keepalives'

c = console()
c.send('version')
receive(c, b'pmf> \r\n')
assert c.command_open, 'An earlier prompt cannot complete an unseen echo'
receive(c, b'ver', b'sion\r\n', b'build 328\r\n')
assert c.command_open, 'Do not reconsider a stale prompt after finding the echo'
receive(c, b'pm', b'f>\r\n')
assert not c.command_open

c = console()
c.send('map')
receive(c, b'map\n' + b'x' * 4096, b'pmf>\n')
assert c.command_open, 'A prompt substring inside a long line is not a prompt'
receive(c, b'\npmf>\n')
assert not c.command_open

print('PASS: leading/stale prompts, split echo/prompt, active keepalive, idle silence, bounded tails')

class TcpSocket:
    def __init__(self):
        self.data = bytearray()
        self.receives = 0
        self.half_closed = False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def settimeout(self, value): pass
    def setsockopt(self, level, option, value):
        assert (level, option, value) == (br.socket.SOL_SOCKET, br.socket.SO_SNDBUF, 16384)
    def send(self, data):
        assert len(data) <= 16384
        count = min(97, len(data))
        self.data.extend(data[:count])
        return count
    def shutdown(self, how):
        assert how == br.socket.SHUT_WR
        self.half_closed = True
    def recv(self, count):
        self.receives += 1
        if self.receives < 3: raise br.socket.timeout()
        return b''

tcp = TcpSocket()
payload = bytes(range(256)) * 1000
alive = []
with patch.object(br, 'local_bind_for', return_value='192.168.1.104'), \
     patch.object(br.socket, 'create_connection', return_value=tcp):
    br.stream_file('192.168.1.114', 5001, payload,
                   keepalive=lambda: alive.append(tcp.receives))
assert tcp.data == payload and tcp.half_closed
assert 1 in alive and 2 in alive, 'Keep UDP flow alive across TCP FIN timeouts'
print('PASS: partial TCP sends preserve bytes and service keepalive during FIN waits')
