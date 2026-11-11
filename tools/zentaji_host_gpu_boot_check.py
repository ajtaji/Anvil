"""Boot the counted monitor on zenwin's real host GPU, without a test app."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from zentaji_graphical_boot_check import ROOT, assert_logo


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zen-tools', type=Path, required=True)
    ap.add_argument('--keep', type=Path, required=True)
    ap.add_argument('--keyboard', action='store_true',
                    help='Exercise native HID editing and command dispatch in the booted monitor')
    args = ap.parse_args()
    from PIL import Image
    zt = args.zen_tools.resolve()
    td = args.keep.resolve()
    td.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(zt))
    import zen_native_fixture as F
    import zasm_ref as A

    image = ROOT / 'build/zentaji/anvil.zex'
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    meta = json.loads(Path(str(image) + '.boot.json').read_text())
    mapping = json.loads(Path(str(image) + '.zmap').read_text())
    assert digest == meta['image_sha256'] == mapping['image']
    for source in mapping['sources']:
        path = Path(source['path'])
        if not path.is_absolute():
            path = ROOT / path
        assert hashlib.sha256(path.read_bytes().replace(b'\r', b'')).hexdigest() == source['sha256'], path
    asm = A.Asm()
    asm.assemble(Path(str(image) + '.compiled.asm').read_text(encoding='utf-8-sig'))
    fixture = F.Fixture(ram_size=128 << 20, cores=2,
                        hostfiles=[['anvil.zex', bytearray(raw), False]],
                        display_modes=[(1024, 768, 60000)])
    if args.keyboard:
        # Native TIME_HZ is 100 MHz. Start at ten seconds, then deliver
        # distinct key-down/up events 20 ms apart through the input device.
        # The shared editor must correct READX to READY before dispatch.
        for index, ch in enumerate('echo GPU READX\bY\r'):
            if ch == '\r':
                usage, mods, text = 40, 0, 0
            elif ch == '\b':
                usage, mods, text = 42, 0, 0
            elif ch == ' ':
                usage, mods, text = 44, 0, 32
            else:
                usage, mods, text = 4 + ord(ch.lower()) - ord('a'), int(ch.isupper()), ord(ch)
            tick = 1_000_000_000 + index * 2_000_000
            fixture.input_feed(tick, 'key', usage, 1, mods, 0, text)
            fixture.input_feed(tick + 1_000_000, 'key', usage, 0, mods, 0, 0)
    fixture.power_on(0, 0)
    fixture.write(td)
    command = [str(zt / 'zenwin.exe'), str(td / 'machine.txt'),
               '--headless', '--live', '--fast', '--live-seconds', '20',
               '--max', '2000000000', '--stats',
               '--screenshot', str(td / 'frame.png'), '--ram', str(td / 'ram-final.bin')]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    output = run.stdout + run.stderr
    (td / 'run.log').write_text(output)
    # The resident monitor has no normal exit. This explicit observation
    # deadline is expected; every other failure remains a failure.
    errors = [line for line in output.splitlines() if line.startswith('error:')]
    assert run.returncode == 2 and errors == [
        'error: the live session did not finish within 20 s of host time.'], (run.returncode, errors, output[-2000:])
    serial = bytes.fromhex(re.search(r'^SERIAL0 ([0-9A-Fa-f]+)$', output, re.M)[1]).decode('utf-8')
    assert 'Type help for the available commands.' in serial and serial.endswith('pmf> '), serial
    if args.keyboard:
        # Require the command's output on its own line, not merely the
        # editor echoing the keys. No serial input is supplied by this check.
        assert '\r\nGPU READY\r\n' in serial, serial
    ram = (td / 'ram-final.bin').read_bytes()
    names = ('zngUp', 'zngFault', 'zngSuspended', 'avkFaultCount', 'avkZenNativeError', 'zgdSequence', 'zngGlintPhase')
    state = {name: int.from_bytes(ram[asm.sym['GLOBAL_' + name.upper()]:asm.sym['GLOBAL_' + name.upper()] + 8], 'little') for name in names}
    assert state['zngUp'] == 1 and state['zgdSequence'] >= 3, state
    assert all(state[name] == 0 for name in names[1:5]), state
    frame = Image.open(td / 'frame.png').convert('RGBA')
    assert frame.size == (1024, 768), frame.size
    bgra = frame.tobytes('raw', 'BGRA')
    for phase in range(8):
        try:
            assert_logo(bgra, 1024, phase)
            break
        except AssertionError:
            continue
    else:
        raise AssertionError('Shared banner logo/sparkle pixels did not match any phase')
    assert all(bgra[(114 * 1024 + x) * 4:(114 * 1024 + x) * 4 + 4] == bytes((48, 148, 255, 255)) for x in range(24, 1000)), 'Missing shared header rule'
    profiles = [{key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)} for line in output.splitlines() if line.startswith('PROFILE ')]
    assert profiles and profiles[-1]['watched_fetches'] + profiles[-1]['compared_fetches'] > 0, 'No host GPU submissions'
    result = dict(image_sha256=digest, state=state, presented_sparkle=phase,
                  profiles=profiles, observation_deadline=True,
                  keyboard_edit_dispatch=args.keyboard)
    (td / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS actual ROM -> Anvil prompt, host GPU, 1024x768 shared header/logo/sparkle, zero graphics faults')
    print(json.dumps(state))
    if args.keyboard:
        print('PASS native HID -> shared editor backspace correction -> echo command -> prompt')


if __name__ == '__main__':
    main()
