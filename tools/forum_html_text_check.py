"""Execute native UTF-8 HTML encoding with guarded input/output spans; no board."""
import argparse
import html
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build import staged_compiler
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
LOAD, STACK, STOP, INPUT, OUTPUT = 0x400000, 0x3000000, 0x7000000, 0x7100000, 0x7200000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    spec = importlib.util.spec_from_file_location('html_a64', ROOT/'tools/a64/a64_interp.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    checks = 0
    with tempfile.TemporaryDirectory(prefix='anvil-html-text-') as tmp:
        tmp = Path(tmp)
        compiler = staged_compiler(args.compiler, tmp)
        source, image = tmp/'text.pi4', tmp/'text.img'
        source.write_text('XIncludeFile "Anvil/Applications/Forum/html_text.pbi"\n'
                          'Procedure.i Main()\nProcedureReturn ForumHtmlText(0,0,0,0)\nEndProcedure\n')
        result = subprocess.run([str(compiler), '--compile', str(source), '-t', 'pi4',
                                 '--entry-returns', '--load-addr', hex(LOAD), '--stack-addr', hex(STACK),
                                 '-o', str(image), '-s'], cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True)
        assert result.returncode == 0 and image.is_file(), result.stdout + result.stderr
        labels = dict(line.split('=', 1) for line in Path(str(image)+'.sym').read_text().splitlines() if '=' in line)
        blob = image.read_bytes()

        def check(data, expected, capacity=None, length=None, source_at=INPUT, destination_at=OUTPUT):
            nonlocal checks
            capacity = len(expected) if capacity is None and expected is not None else (128 if capacity is None else capacity)
            length = len(data) if length is None else length
            cpu = mod.A64()
            cpu.memory.update({LOAD+i: b for i, b in enumerate(blob)})
            cpu.memory.update({INPUT+i: b for i, b in enumerate(data)})
            cpu.pc, cpu.sp, cpu.x[30] = LOAD+int(labels['forumhtmltext']), STACK, STOP
            cpu.x[:4] = [source_at, length & ((1 << 64)-1), destination_at, capacity & ((1 << 64)-1)]
            read, write = cpu.load, cpu.store
            writes = []
            def load(at, size):
                if INPUT-16 <= at < INPUT+0x10000:
                    assert INPUT <= at and at+size <= INPUT+len(data), ('overread', at, size)
                return read(at, size)
            def store(at, value, size):
                if not STACK-0x10000 <= at < STACK:
                    assert destination_at <= at and at+size <= destination_at+max(capacity, 0), ('overwrite', at, size)
                    writes.append((at, size))
                return write(at, value, size)
            cpu.load, cpu.store = load, store
            for _ in range(2000000):
                if cpu.pc == STOP:
                    if expected is None:
                        assert cpu.x[0] == (1 << 64)-1, (data, cpu.x[0])
                        assert not writes, ('failure wrote output', data, writes)
                    else:
                        assert cpu.x[0] == len(expected), (data, cpu.x[0], len(expected))
                        actual = bytes(read(OUTPUT+i, 1) for i in range(len(expected)))
                        assert actual == expected, (data, actual, expected)
                    checks += 1
                    return
                cpu.step()
            raise AssertionError('Encoding exceeded instruction budget')

        for data in (b'', b'hello', b'<script>alert("x")</script>', b'&lt;', b"'\"&<>",
                     b'line\n\tindent\r\n', 'caf\u00e9 \u4e2d\u6587 \U0001f600'.encode(),
                     bytes(range(32, 127)), b'<'*200):
            expected = html.escape(data.decode(), quote=True).replace('&#x27;', '&#39;').encode()
            check(data, expected)
            check(data, expected, capacity=len(expected)+17)
            if expected:
                check(data, None, capacity=len(expected)-1)
        for data in (b'\0', b'\x01', b'\x7f', b'\x80', b'\xc0\xaf', b'\xc1\xbf', b'\xc2',
                     b'\xe0\x80\xaf', b'\xed\xa0\x80', b'\xf0\x80\x80\xaf',
                     b'\xf4\x90\x80\x80', b'\xf5\x80\x80\x80', b'\xe2\x82', b'abc\xf0\x9f\x98',
                     b'\xe2<\xac', b'\xe2\x82<'):
            check(data, None)
        for data in (b'\xc2\x80', b'\xdf\xbf', b'\xe0\xa0\x80', b'\xed\x9f\xbf',
                     b'\xf0\x90\x80\x80', b'\xf4\x8f\xbf\xbf'):
            check(data, data)
        check(b'x', None, length=-1)
        check(b'x', None, length=65537)
        check(b'x', None, capacity=-1)
        check(b'x', None, source_at=0)
        check(b'x', None, destination_at=0)
        check(b'abcd', None, destination_at=INPUT+1)
        check(b'x', None, destination_at=0x7fffffffffffffff, capacity=1)
    print(f'PASS: {checks} native HTML text checks; guarded spans and unchanged output on refusal. No board proof.')


if __name__ == '__main__':
    main()
