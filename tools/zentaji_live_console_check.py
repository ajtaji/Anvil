"""Drive the actual GPU-backed Anvil monitor over a live UART TCP cable."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zen-tools', type=Path, required=True)
    parser.add_argument('--keep', type=Path, required=True)
    args = parser.parse_args()
    zt, td = args.zen_tools.resolve(), args.keep.resolve()
    td.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(zt))
    import zen_native_fixture as F
    from zen_console import Console
    image = ROOT / 'build/zentaji/anvil.zex'
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    meta = json.loads(Path(str(image)+'.boot.json').read_text())
    assert digest == meta['image_sha256']
    stage = (meta['image_end'] + 4095) & -4096
    fixture = F.Fixture(ram_size=128 << 20, cores=2,
                        hostfiles=[['anvil.zex', bytearray(raw), False]],
                        display_modes=[(1024, 768, 60000)])
    fixture.power_on(0, 0)
    fixture.write(td)
    command = [str(zt/'zenwin.exe'), str(td/'machine.txt'), '--headless', '--live',
               '--fast', '--max', '2000000000', '--live-seconds', '60',
               '--serial-listen', '0', '--screenshot', str(td/'frame.png')]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    lines, received = [], queue.Queue()
    def reader():
        for line in process.stdout:
            lines.append(line)
            received.put(line)
        received.put(None)
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    client = None
    transcript = []
    try:
        deadline = time.monotonic()+30
        while True:
            line = received.get(timeout=max(.01, deadline-time.monotonic()))
            assert line is not None, ''.join(lines)
            match = re.fullmatch(r'SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0\n', line)
            if match:
                port = int(match[1])
                break
        client = Console(port, 25)
        transcript.append(client.prompt().decode())
        assert 'Type help for the available commands.' in transcript[-1]
        # A second client cannot interleave bytes with the owner.
        with socket.create_connection(('127.0.0.1', port), 3) as extra:
            extra.settimeout(3)
            assert extra.recv(1) == b''
        for command, expected in [('echo LIVE FIRST', 'LIVE FIRST'),
                                  ('version', 'PureMetal'),
                                  ('echo LIVE SECOND', 'LIVE SECOND')]:
            reply = client.command(command).decode()
            transcript.append(reply)
            if command.startswith('echo'):
                assert expected in reply.splitlines(), reply
            else:
                assert expected in reply, reply
        # Exercise the shared memory handlers in the live payload window.
        # Check resulting bytes through an independently computed CRC.
        expected_crc = zlib.crc32(bytes([0xA5]) * 16)
        for word in (f'fill.b {stage:X} A5 10',
                     f'copy.b {stage:X} {stage+0x20:X} 10',
                     f'compare.b {stage:X} {stage+0x20:X} 10',
                     f'md.b {stage:X} 10'):
            reply = client.command(word).decode()
            transcript.append(reply)
            assert '!!' not in reply and 'does not know the command' not in reply, reply
            if word.startswith('compare'):
                assert 'are the same.' in reply, reply
            if word.startswith('md'):
                assert 'A5 A5 A5 A5' in reply.upper(), reply
        for address in (stage, stage+0x20):
            reply = client.command(f'crc32 {address:X} 10').decode()
            transcript.append(reply)
            assert f'The CRC32 is {expected_crc:08X}.' in reply, reply
        reply = client.command(f'write {stage+0x40:X} 12345678').decode()
        transcript.append(reply)
        assert '!!' not in reply and 'does not know the command' not in reply, reply
        word_crc = zlib.crc32(bytes.fromhex('78563412'))
        reply = client.command(f'crc32 {stage+0x40:X} 4').decode()
        transcript.append(reply)
        assert f'The CRC32 is {word_crc:08X}.' in reply, reply
        transcript.append(client.command(f'base {stage:X}').decode())
        reply = client.command('md.b 0 10').decode()
        transcript.append(reply)
        assert 'A5 A5 A5 A5' in reply.upper(), reply
        transcript.append(client.command('base 0').decode())
        reply = client.command('fill.b 1000 A5 10').decode()
        transcript.append(reply)
        assert 'runs into the monitor itself' in reply and 'Nothing was written' in reply, reply
        reply = client.command('fill.b 8000000 A5 10').decode()
        transcript.append(reply)
        assert 'was refused' in reply and 'beyond the RAM fitted' in reply, reply
        # Real transport fragments, including editor correction, not timed fixtures.
        client.socket.sendall(b'echo LIVE READX')
        time.sleep(.05)
        client.socket.sendall(b'\x08Y\r')
        transcript.append(client.prompt().decode())
        assert 'LIVE READY' in transcript[-1].splitlines(), transcript[-1]
        transcript.append(client.command('no_such_zentaji_command').decode())
        assert 'does not know the command' in transcript[-1], transcript[-1]
        # No unsolicited prompt: an absolute timeout must fail rather than hang.
        client.timeout = .15
        try:
            client.prompt()
        except TimeoutError:
            pass
        else:
            raise AssertionError('Missing-reply timeout did not fire')
        client.close()
        client = None
        time.sleep(.1)
        client = Console(port, 10)
        history = client.prompt().decode()
        assert 'LIVE FIRST' in history and 'LIVE READY' in history
        transcript.append(client.command('echo RECONNECTED').decode())
        assert 'RECONNECTED' in transcript[-1].splitlines()
        # Ordinary command failure is distinct from transport completion.
        client.close()
        client = None
        time.sleep(.1)
        run = subprocess.run([sys.executable, str(zt/'zen_console.py'), '--port', str(port),
                              '--command', 'echo VERIFIED', '--expect-line', 'MISSING'],
                             capture_output=True, text=True, timeout=15)
        assert run.returncode == 1, (run.returncode, run.stdout, run.stderr)
        assert json.loads(run.stdout)['prompt_returned'] is True
        time.sleep(.1)
        client = Console(port, 10)
        client.prompt()
        client.socket.sendall(b'halt\r')
        assert process.wait(timeout=20) == 0, ''.join(lines)[-2000:]
        thread.join(timeout=3)
        serial = bytes.fromhex(re.search(r'^SERIAL0 ([0-9A-Fa-f]+)$', ''.join(lines), re.M)[1]).decode()
        assert 'Anvil stopped.' in serial and 'HOST_GPU_REFUSED' not in ''.join(lines)
        (td/'result.json').write_text(json.dumps(dict(passed=True, image_sha256=digest,
            port=port, transcript=transcript, checks=['sequential commands','exclusive client', 'shared memory commands and CRC',
            'fragmented input and backspace','unknown command','timeout','reconnect',
            'expected-line failure status','clean halt']), indent=2)+'\n')
        print('PASS actual Anvil: live UART commands, editing, replies, timeout, reconnect, clean halt')
    finally:
        if client:
            client.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        thread.join(timeout=3)
        (td/'run.log').write_text(''.join(lines))


if __name__ == '__main__':
    main()
