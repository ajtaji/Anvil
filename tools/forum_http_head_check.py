#!/usr/bin/env python3
"""Execute the native request-head admission code; no sockets or board access."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOAD, STACK, RETURN, INPUT, OUTPUT = 0x400000, 0x3000000, 0x7000000, 0x7100000, 0x7200000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('forum_a64', ROOT/'tools/a64/a64_interp.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix='anvil-forum-http-') as tmp:
        tmp = Path(tmp)
        source, image = tmp/'head.pi4', tmp/'head.img'
        source.write_text('XIncludeFile "Anvil/Applications/Forum/http_head.pbi"\nProcedure.i Main()\nProcedureReturn ForumHttpHead(0,0,0,0,0)\nEndProcedure\n')
        result = subprocess.run([args.compiler, '--compile', str(source), '-t', 'pi4',
                                 '--entry-returns', '--load-addr', hex(LOAD),
                                 '--stack-addr', hex(STACK), '-o', str(image), '-s'],
                                cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        assert result.returncode == 0 and image.is_file(), result.stdout+result.stderr
        labels = dict(line.split('=', 1) for line in Path(str(image)+'.sym').read_text().splitlines() if '=' in line)
        blob = image.read_bytes()
        def check(data, expected, max_head=32768, max_body=65536, available=None):
            cpu = mod.A64()
            cpu.memory.update({LOAD+i:b for i,b in enumerate(blob)})
            cpu.memory.update({INPUT+i:b for i,b in enumerate(data)})
            cpu.pc, cpu.sp, cpu.x[30] = LOAD+int(labels['forumhttphead']), STACK, RETURN
            cpu.x[:5] = [INPUT, len(data) if available is None else available, max_head, max_body, OUTPUT]
            old_load = cpu.load
            admitted = len(data) if available is None else max(0, available)
            def guarded_load(at, size):
                if INPUT-16 <= at < INPUT+65536:
                    assert INPUT <= at and at+size <= INPUT+admitted, 'request-buffer overread'
                return old_load(at, size)
            cpu.load = guarded_load
            for _ in range(1000000):
                if cpu.pc == RETURN:
                    assert cpu.x[0] == expected, (data, cpu.x[0], expected)
                    fields = tuple(cpu.load(OUTPUT+i*8,8) for i in range(5))
                    if expected == 1:
                        assert fields[0] == data.index(b'\r\n\r\n')+4
                        assert data[fields[2]:fields[2]+fields[3]].startswith(b'/')
                        assert fields[4] == data.index(b' '), fields
                        assert fields[4] == data.index(b' ')
                    else:
                        assert fields == (0,)*5, fields
                    return fields
                cpu.step()
            raise AssertionError('Head parser did not return within its instruction budget.')
        get = b'GET /topic/1?x=2 HTTP/1.1\r\nHost: forum.test\r\n\r\n'
        cases = [(get,1), (get+b'NEXT',1),
                 (b'POST / HTTP/1.1\r\nHost: forum.test\r\nContent-Length: 4\r\n\r\ndata',1),
                 (b'GET / HTTP/1.1\r\nhOsT:\tforum.test \t\r\n\r\n',1),
                 (b'GET / HTTP/1.1\r\n\r\n',400),
                 (b'GET / HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n',400),
                 (b'GET / HTTP/1.1\r\nHost : a\r\n\r\n',400),
                 (b'GET / HTTP/1.1\r\nHost: \r\n\r\n',400),
                 (b'GET / HTTP/1.1\r\nHost: a b\r\n\r\n',400),
                 (b'GET / HTTP/1.1\nHost: a\n\n',400),
                 (b'GET / HTTP/1.1\rX',400),
                 (b'GET  / HTTP/1.1\r\n',400),
                 (b'GET /#fragment HTTP/1.1\r\n',400),
                 (b'GET http://forum.test/ HTTP/1.1\r\n',400),
                 (b'GET / HTTP/1.0\r\n',505),
                 (b'GET / HTTP/1.1\r\nHost: a\r\n folded: x\r\n\r\n',400)]
        prefix = b'POST / HTTP/1.1\r\nHost: a\r\n'
        cases += [(prefix+b'Content-Length: '+v+b'\r\n\r\n',400)
                  for v in (b'-1',b'+1',b'1,1',b'1x',b'')]
        cases += [(prefix+b'Content-Length: 2\r\nContent-Length: 2\r\n\r\n',400),
                  (prefix+b'Transfer-Encoding: chunked\r\n\r\n',501),
                  (prefix+b'Transfer-Encoding: chunked\r\nContent-Length: 1\r\n\r\n',400),
                  (prefix+b'Content-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n',400),
                  (prefix+b'Content-Length: 999999999999999999999999\r\n\r\n',413),
                  (get.replace(b'Host:', b'Ho\x00st:'),400)]
        cases += [(prefix+b'Transfer-Encoding : chunked\r\n\r\n',400),
                  (prefix+b'Transfer-Encoding:\tchunked\r\n\r\n',501),
                  (prefix+b'tRaNsFeR-EnCoDiNg: identity\r\n\r\n',501),
                  (prefix+b'Transfer-Encoding:\r\nContent-Length: 0\r\n\r\n',400),
                  (prefix+b'Content-Length: 0\r\n\tTransfer-Encoding: chunked\r\n\r\n',400),
                  (prefix+b'Content-Length:\t0004\t\r\n\r\n',1),
                  (prefix+b'Content-Length: 4\x00\r\n\r\n',400),
                  (prefix+b'Content-Length: 4\v\r\n\r\n',400),
                  (prefix+b'X: x\x7f\r\n\r\n',400),
                  (b'GET\t/ HTTP/1.1\r\nHost: a\r\n\r\n',400),
                  (b'GET / HTTP/1.1 \r\nHost: a\r\n\r\n',400)]
        for data, expected in cases:
            fields = check(data,expected)
            if data.endswith(b'\r\n\r\ndata'):
                assert fields[1] == 4
        for n in range(len(get)):
            check(get[:n],0)
            check(get,0,available=n)
        check(get,1,max_head=len(get))
        check(get,431,max_head=len(get)-1)
        check(prefix+b'Content-Length: 0\r\n\r\n',1,max_body=0)
        check(prefix+b'Content-Length: 1\r\n\r\n',413,max_body=0)
        check(get,431,max_head=16)
        check(prefix+b'Content-Length: 65536\r\n\r\n',1)
        check(prefix+b'Content-Length: 65537\r\n\r\n',413)
        check(get,500,available=-1)
        print(f'forum_http_head_check: PASS {len(cases)} grammar/framing cases, {2*len(get)} partial-buffer/available checks, eight bounds; input reads guarded against available. No server/body/TLS claim.')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('This gate requires enabled Python assertions.')
    main()
