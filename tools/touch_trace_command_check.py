#!/usr/bin/env python3
"""Execute the real touch trace dispatcher/viewer without permitting MMIO."""
import argparse
from pathlib import Path
import re
import tempfile

import dsi_diag_read_safety_check as emitted

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'RaspberryPi4/Board/touch_cmd.pi4'
I2C = ROOT / 'RaspberryPi4/Lib/i2c.pi4'
BOARD = ROOT / 'RaspberryPi4/Board/board.pi4'


TRACE_RECORDS = (
    # BEGIN and FAULT precede recovery, so their result/preflight fields are
    # deliberately placeholders/current observations. END owns the outcome.
    (1, 1, 0, 0, 101, 0x00008000, 0x00000050, 0, 0x45),
    (3, 1, -4, 0, 202, 0x00008001, 0xF00000A9, 1, 0x45),
    (2, 1, -4, -1, 303, 0x00000000, 0x40000051, 0, 0x45),
    # A later transaction can encounter a non-idle preflight, recover it,
    # and still complete. Keep +1 independently visible from the -1 case.
    (1, 8, 0, 0, 404, 0x00000000, 0x40000051, 1, 0x14),
    (4, 8, 0, 0, 420, -1, 0x00000014, -1, -1),
    (5, 8, 0, 0, 430, -1, 0x00000015, -1, -1),
    (6, 8, 0, 0, 440, -1, 0x00000020, -1, -1),
    (7, 8, 0, 0, 450, -1, 0x00000002, -1, -1),
    (3, 8, -4, 0, 505, 0x00008000, 0x40000051, 1, 0x14),
    (2, 8, 0, 1, 606, 0x00008000, 0x00000052, 0, 0x14),
)


EXPECTED_RECORD_LINES = (
    '0 BEGIN MCU97 pointer result=0 preflight=0 tick=101 '
    'C=00008000 S=00000050 DLEN=00000000 A=00000045',
    '1 FAULT MCU97 pointer result=-4 preflight=0 tick=202 '
    'C=00008001 S=F00000A9 DLEN=00000001 A=00000045',
    '2 END   MCU97 pointer result=-4 preflight=-1 tick=303 '
    'C=00000000 S=40000051 DLEN=00000000 A=00000045',
    '3 BEGIN Goodix14 identity result=0 preflight=0 tick=404 '
    'C=00000000 S=40000051 DLEN=00000001 A=00000014',
    '4 TX    Goodix14 identity result=0 preflight=0 tick=420 '
    'C=not-sampled S=00000014 DLEN=not-sampled A=not-sampled',
    '5 READST Goodix14 identity result=0 preflight=0 tick=430 '
    'C=not-sampled S=00000015 DLEN=not-sampled A=not-sampled',
    '6 RX    Goodix14 identity result=0 preflight=0 tick=440 '
    'C=not-sampled S=00000020 DLEN=not-sampled A=not-sampled',
    '7 DONE  Goodix14 identity result=0 preflight=0 tick=450 '
    'C=not-sampled S=00000002 DLEN=not-sampled A=not-sampled',
    '8 FAULT Goodix14 identity result=-4 preflight=0 tick=505 '
    'C=00008000 S=40000051 DLEN=00000001 A=00000014',
    '9 END   Goodix14 identity result=0 preflight=1 tick=606 '
    'C=00008000 S=00000052 DLEN=00000000 A=00000014',
)


def constant(name):
    match = re.search(r'^#' + re.escape(name) + r'\s*=\s*(\d+)',
                      I2C.read_text(encoding='utf-8'), re.M)
    if not match:
        raise AssertionError('trace constant missing: ' + name)
    return int(match[1])


class RamOnly(dict):
    def get(self, address, default=None):
        if address >= 0xFC000000:
            raise AssertionError('diagnostic read MMIO: ' + hex(address))
        return super().get(address, default)

    def __setitem__(self, address, value):
        if address >= 0xFC000000:
            raise AssertionError('diagnostic wrote MMIO: ' + hex(address))
        super().__setitem__(address, value)


def source_checks():
    text = BOARD.read_text(encoding='utf-8')
    start = text.index('Procedure Main()')
    end = text.index('EndProcedure', start)
    main = text[start:end]
    expected = re.compile(
        r'I2cTraceEnable\(1\)\s*\n\s*ScreenUp\(\).*?'
        r'TouchBoot\(\)\s*\n\s*I2cTraceEnable\(0\)', re.S)
    if expected.search(main) is None:
        raise AssertionError(
            'Main must enable immediately before ScreenUp and disable '
            'immediately after TouchBoot')
    statements = [line.strip() for line in main.splitlines()
                  if line.strip() and not line.lstrip().startswith(';')]
    positions = [statements.index(statement) for statement in
                 ('I2cTraceEnable(1)', 'ScreenUp()', 'TouchBoot()',
                  'I2cTraceEnable(0)')]
    if positions != sorted(positions):
        raise AssertionError('boot trace capture boundary order changed')


def check(image, a64):
    source_checks()
    syms = emitted.parse_symbols(image)
    fields = constant('I2C_TRACE_FIELDS')
    cases, total = 0, 0
    for line, count, expected, overflow in (
            ('trace', 10, [], 0), ('TrAcE', 10, [], 1), ('trace  ', 0, [], 0),
            ('trace extra', 10, [], 0), ('traceable', 10, ['usage'], 0),
            ('help', 10, ['usage'], 0), ('nonesuch', 10, ['usage'], 0),
            ('', 10, ['select', 'up', 'status', 'select'], 0),
            ('points', 10, ['select', 'up', 'live', 'select'], 0),
            ('panel', 10, ['select', 'up', 'panel', 'select'], 0),
            ('axes', 10, ['mapping'], 0),
            ('bus', 10, ['select', 'saybus', 'select'], 0)):
        cpu = emitted.fresh_cpu(a64, image)
        cpu.memory = RamOnly(cpu.memory)
        for index, byte in enumerate(line.encode('ascii') + b'\0'):
            cpu.memory[syms['global_gline'] + index] = byte
        emitted.put64(cpu.memory, syms['global_gpos'], 0)
        emitted.put64(cpu.memory, syms['global_gtouchbus'], constant('I2C_BUS_HEADER'))
        emitted.put64(cpu.memory, syms['global_i2c_trace_count'], count)
        emitted.put64(cpu.memory, syms['global_i2c_trace_overflow'], overflow)
        base = syms['global_i2c_trace_words']
        for index, values in enumerate(TRACE_RECORDS):
            for field, value in enumerate(values):
                emitted.put64(cpu.memory, base + (index * fields + field) * 8, value)
        original = bytes(cpu.memory.get(base + i, 0)
                         for i in range(len(TRACE_RECORDS) * fields * 8))
        meta_original = bytes(
            cpu.memory.get(address + byte, 0)
            for address in (syms['global_i2c_trace_count'],
                            syms['global_i2c_trace_overflow'])
            for byte in range(8))
        output, events = [], []
        hooks = {}

        def write_string(inner):
            pointer = inner.x[0]
            raw = []
            for offset in range(2048):
                byte = inner.memory.get(pointer + offset, 0)
                if byte == 0:
                    output.append(bytes(raw).decode('ascii'))
                    return
                raw.append(byte)
            raise AssertionError('unterminated output string')

        hooks[emitted.LOAD + syms['uartwritestr']] = write_string
        hooks[emitted.LOAD + syms['uartwrite']] = lambda inner: output.append(chr(inner.x[0] & 255))
        hooks[emitted.LOAD + syms['printnl']] = lambda inner: output.append('\n')
        hooks[emitted.LOAD + syms['printdec']] = lambda inner: output.append(str(
            inner.x[0] if inner.x[0] < (1 << 63) else inner.x[0] - (1 << 64)))
        hooks[emitted.LOAD + syms['puthexn']] = lambda inner: output.append(f'{inner.x[0]:08X}')
        for name, event in (('i2cselectbus', 'select'), ('i2cup', 'up'),
                            ('touchsaypads', 'pads'), ('touchstatus', 'status'),
                            ('touchlive', 'live'), ('touchpanel', 'panel'),
                            ('touchsaymapping', 'mapping'),
                            ('touchsaybus', 'saybus'), ('touchusage', 'usage')):
            def record(inner, label=event):
                events.append(label)
                inner.x[0] = 1
            hooks[emitted.LOAD + syms[name]] = record
        cpu.pc = emitted.LOAD + syms['cmdtouch']
        cpu.sp = emitted.STACK
        cpu.x[30] = emitted.RETURN_PC
        total += emitted.run_until_return(cpu, hooks)
        if events != expected:
            raise AssertionError(f'{line!r}: hardware route {events}, expected {expected}')
        after = bytes(cpu.memory.get(base + i, 0)
                      for i in range(len(TRACE_RECORDS) * fields * 8))
        if original != after:
            raise AssertionError('viewing mutated retained trace')
        meta_after = bytes(
            cpu.memory.get(address + byte, 0)
            for address in (syms['global_i2c_trace_count'],
                            syms['global_i2c_trace_overflow'])
            for byte in range(8))
        if meta_original != meta_after:
            raise AssertionError('viewing mutated trace count/overflow')
        printed = ''.join(output)
        if line.strip().lower() == 'trace':
            if count:
                record_lines = tuple(part.rstrip('\r') for part in printed.split('\n')
                                     if re.match(r'^\d+ ', part))
                if record_lines != EXPECTED_RECORD_LINES:
                    raise AssertionError(
                        'trace records were not rendered exactly in B/F/E order:\n' +
                        '\n'.join(record_lines))
                for phrase in (
                        'TX/READST/RX/DONE are first progress observations; '
                        'their result=0 is a placeholder.',
                        'On progress rows C/DLEN/A=not-sampled; '
                        'S is the already-read status.',
                        'BEGIN result is a placeholder; FAULT is the observed failure; '
                        'END is the final result.',
                        'preflight outcome is meaningful on END only: 0=not needed, '
                        '1=recovered, -1=failed.'):
                    if phrase not in printed:
                        raise AssertionError('missing trace explanation: ' + phrase)
                if ('saturated' in printed) != bool(overflow):
                    raise AssertionError('overflow reporting mismatch')
            elif 'No panel/touch transaction' not in printed:
                raise AssertionError('empty trace fabricated records')
        elif line == 'trace extra':
            if 'takes no arguments' not in printed or 'Boot I2C trace:' in printed:
                raise AssertionError('malformed trace request was not refused')
        cases += 1
    print(f'touch_trace_command_check: PASS {cases} emitted routes, {total:,} instructions')
    print('  actual parser/viewer, retained RAM unchanged, MMIO forbidden; normal routes preserved')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pmfc')
    ap.add_argument('--image', type=Path, help='already-built full Pi monitor image and symbol sidecar')
    args = ap.parse_args()
    a64 = emitted.load_interpreter(emitted.INTERP)
    if args.image:
        check(args.image.resolve(), a64)
    else:
        with tempfile.TemporaryDirectory(prefix='anvil-touch-trace-command-') as td:
            check(emitted.build(emitted.anvil_build.find_compiler(args.pmfc), Path(td)), a64)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
