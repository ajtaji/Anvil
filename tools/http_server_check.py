#!/usr/bin/env python3
"""Run the emitted native HTTP engine with a test-only transport adapter."""
import argparse
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import build_count

ROOT=Path(__file__).resolve().parents[1]
BASE,STACK,RETURN=0x400000,0x3000000,0x7000000

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('http_a64',ROOT/'tools/a64/a64_interp.py')
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix='anvil-http-') as td:
        image=Path(td)/'http.img'; source=ROOT/'Anvil/Services/Http/Tests/engine.pi4'
        result=subprocess.run([args.compiler,'--compile',str(source),'-t','pi4','--load-addr',hex(BASE),
                               '--stack-addr',hex(STACK),'--entry-returns','-o',str(image),'-s'],cwd=ROOT,
                              env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert result.returncode==0 and image.exists(),result.stdout+result.stderr
        build_count.record_build(source,'pi4',image,by='tools/http_server_check.py',compiler=args.compiler)
        labels={k:int(v)+BASE for k,v in (line.split('=',1) for line in Path(str(image)+'.sym').read_text().splitlines() if '=' in line)}
        blob=image.read_bytes()
        class Engine:
            def __init__(self,transport):
                self.cpu=mod.A64(); self.cpu.memory.update({BASE+i:b for i,b in enumerate(blob)})
                self.transport=transport
            def poll(self,now):
                cpu=self.cpu; cpu.pc=labels['hspoll']; cpu.sp=STACK; cpu.x[30]=RETURN; cpu.x[0]=now
                for _ in range(1000000):
                    if cpu.pc==RETURN: return cpu.x[0]
                    name=next((n for n in ('htaccept','htread','htwrite','htclose') if cpu.pc==labels[n]),None)
                    if name:
                        h,p,n=cpu.x[:3]
                        if name=='htaccept': value=self.transport.accept()
                        elif name=='htread':
                            value=self.transport.read(h,n)
                            if isinstance(value,bytes):
                                cpu.memory.update({p+i:b for i,b in enumerate(value)}); value=len(value)
                        elif name=='htwrite': value=self.transport.write(h,bytes(cpu.load(p+i,1) for i in range(n)))
                        else: self.transport.close(h); value=0
                        cpu.x[0]=value & ((1<<64)-1); cpu.pc=cpu.x[30]
                    else: cpu.step()
                raise AssertionError('Poll exceeded its instruction bound.')
        class Fake:
            def __init__(self,data): self.data=data; self.offset=0; self.out=b''; self.closed=0; self.accepted=False; self.writes=0
            def accept(self):
                if self.accepted:return 0
                self.accepted=True;return 1
            def read(self,h,n):
                fragment=7 if len(self.data)<512 else 512
                out=self.data[self.offset:self.offset+min(n,fragment)];self.offset+=len(out);return out
            def write(self,h,data):
                self.writes+=1
                if self.writes%3==0:return 0
                data=data[:11];self.out+=data;return len(data)
            def close(self,h):self.closed+=1
        def request(raw,status,head=False):
            t=Fake(raw); e=Engine(t)
            for now in range(4000):
                assert e.poll(now)==1
                if t.closed:break
            assert t.closed==1,t.out
            headers,body=t.out.split(b'\r\n\r\n',1)
            assert headers.startswith(f'HTTP/1.1 {status} '.encode()),t.out
            size=int(next(line.split(b':')[1] for line in headers.split(b'\r\n') if line.startswith(b'Content-Length:')))
            assert len(body)==(0 if head else size),(len(body),size)
            assert b'Connection: close' in headers
            return t.out
        persistent=b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n'
        get=persistent.replace(b'\r\n\r\n',b'\r\nConnection: close\r\n\r\n')
        assert b'<h1>Anvil web server</h1>' in request(get,200)
        request(get.replace(b'GET',b'HEAD'),200,True)
        request(get.replace(b'/ HTTP',b'/health HTTP'),200)
        request(get.replace(b'/ HTTP',b'/missing HTTP'),404)
        request(get.replace(b'GET',b'HEAD').replace(b'/ HTTP',b'/missing HTTP'),404,True)
        request(get.replace(b'GET',b'POST'),405)
        request(b'GET / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n',501)
        request(b'HEAD / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n',501,True)
        request(b'GET / HTTP/1.1\r\nHost: x\r\nContent-Length: 1025\r\n\r\n',413)
        request(b'GET / HTTP/1.1\r\nHost: x\r\nX: '+b'a'*4100+b'\r\n\r\n',431)
        request(b'GET / HTTP/1.1\nHost: x\n\n',400)
        request(b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\nConnection: close\r\n\r\nabc',405)
        request(b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\nExpect: 100-continue\r\n\r\n',417)
        assert request(get+get,200).count(b'HTTP/1.1')==1
        print('PASS: explicit-close request and rejection cases.',flush=True)
        # Persistent requests use one handle; fragmented/queued successors
        # retain framing and output order, and the explicit close wins.
        def pipeline(raw, statuses, transport=Fake, heads=()):
            t=transport(raw);e=Engine(t)
            for now in range(9000):
                e.poll(now)
                if t.closed:break
            assert t.closed==1,t.out
            remaining=t.out
            for i,status in enumerate(statuses):
                headers,remaining=remaining.split(b'\r\n\r\n',1)
                assert headers.startswith(f'HTTP/1.1 {status} '.encode()),headers
                size=int(next(x.split(b':')[1] for x in headers.split(b'\r\n') if x.startswith(b'Content-Length:')))
                if i in heads:size=0
                assert len(remaining)>=size
                remaining=remaining[size:]
                assert (b'Connection: close' in headers)==(i==len(statuses)-1),headers
            assert remaining==b'',remaining
            print(f'PASS: persistent framing {len(statuses)} responses.',flush=True)
        pipeline(persistent+get.replace(b'/ HTTP',b'/health HTTP'),[200,200])
        health=persistent.replace(b'/ HTTP',b'/health HTTP')
        pipeline(health*15+get.replace(b'/ HTTP',b'/health HTTP'),[200]*16)
        pipeline(health*17,[200]*16) # bounded request count, final response closes
        pipeline(persistent+b'GET / HTTP/1.1\nHost: x\n\n',[200,400])
        request(persistent.replace(b'\r\n\r\n',b'\r\nConnection: keep-alive, ClOsE\r\n\r\n'),200)
        request(persistent.replace(b'\r\n\r\n',b'\r\nConnection: keep-alive\r\nConnection: close\r\n\r\n'),200)
        # Body bytes that resemble requests must not become another request.
        body=persistent
        post=b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        pipeline(post+get,[405,200])
        class HalfClosed(Fake):
            def read(self,h,n):
                if self.offset==len(self.data):return -1
                out=self.data[self.offset:self.offset+n];self.offset+=len(out);return out
        pipeline(persistent+get,[200,200],HalfClosed)
        pipeline(persistent.replace(b'GET',b'HEAD')+get,[200,200],heads=(0,))
        t=Fake(persistent);e=Engine(t)
        for now in range(400):e.poll(now)
        assert t.closed==0 and b'Connection: keep-alive' in t.out
        t.data+=get # sequential request arriving after prior response
        for now in range(400,800):e.poll(now)
        assert t.closed==1 and t.out.count(b'HTTP/1.1 200')==2
        t=Fake(persistent);e=Engine(t)
        for now in range(400):e.poll(now)
        assert t.closed==0
        e.poll(10400);assert t.closed==1 # absolute idle/request deadline
        t=Fake(b'GET /');e=Engine(t);assert e.poll(0)==1;assert e.poll(10000)==1;assert t.closed==1 and not t.out
        assert e.poll(9999)==0
        class Multi:
            def __init__(self):self.next=0;self.clients={i:Fake(get) for i in range(1,6)}
            def accept(self):
                if self.next==5:return 0
                self.next+=1;return self.next
            def read(self,h,n):return self.clients[h].read(h,n)
            def write(self,h,data):return 0 if h==1 else self.clients[h].write(h,data)
            def close(self,h):self.clients[h].close(h)
        t=Multi();e=Engine(t)
        for now in range(400):e.poll(now)
        assert t.next==5 and t.clients[1].closed==0
        assert all(t.clients[i].closed==1 and b'HTTP/1.1 200' in t.clients[i].out for i in range(2,6))
        e.poll(11000);assert t.clients[1].closed==1
        class Bad(Fake):
            def write(self,h,data):return len(data)+1
        t=Bad(get);e=Engine(t)
        for now in range(20):e.poll(now)
        assert t.closed==1
        print('PASS: fragmented requests, partial writes, four-slot progress, output timeout and provider/clock refusals; keepalive sequential/pipelined/body-framing/half-close, close tokens, limit16 and idle deadline.')
        # Test-only host sockets bridge the actual emitted engine, not a product server.
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(4);listener.setblocking(False)
        received=[]
        def client():
            with socket.create_connection(listener.getsockname(),timeout=20) as s:
                s.sendall(get);chunks=[]
                while True:
                    b=s.recv(4096)
                    if not b:break
                    chunks.append(b)
                received.append(b''.join(chunks))
        class Local:
            def __init__(self):self.connections={};self.next=0
            def accept(self):
                try:s,_=listener.accept()
                except BlockingIOError:return 0
                s.setblocking(False);self.next+=1;self.connections[self.next]=s;return self.next
            def read(self,h,n):
                try:b=self.connections[h].recv(min(n,23));return b if b else -1
                except BlockingIOError:return 0
            def write(self,h,data):
                try:return self.connections[h].send(data[:17])
                except BlockingIOError:return 0
            def close(self,h):self.connections.pop(h).close()
        t=Local();e=Engine(t);worker=threading.Thread(target=client);worker.start()
        try:
            for now in range(9000):
                e.poll(now)
                if received:break
            worker.join(2)
            assert received and b'<h1>Anvil web server</h1>' in received[0],received
        finally:
            for s in t.connections.values():s.close()
            listener.close()
        print('PASS: actual localhost TCP request served by emitted native engine through test-only host transport.')
if __name__=='__main__':main()
