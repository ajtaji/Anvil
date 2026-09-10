#!/usr/bin/env python3
"""Execute the returning MCU pointer/READ diagnostic on a bounded BSC model.

This proves what the diagnostic does, not how the real MCU answers. Faults
are explicit modeled inputs; no GPIO, firmware, or hardware access is used.
"""
import argparse
import pathlib
import sys
import tempfile

import touch_emitted_check as touch

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOAD, BSS, STACK = 0x500000, 0x600000, 0x800000
I2C_CLKT = touch.lib_consts(touch.I2C_TEXT, ['I2C_CLKT'])['I2C_CLKT']


class IdentityMcu(touch.Slave):
    def __init__(self):
        super().__init__(0x45)
        self.writes, self.reads = [], []

    def write(self, data):
        self.writes.append(bytes(data))
        assert bytes(data) == b'\x97', 'only the identity pointer is permitted'
        return True

    def read(self, length):
        self.reads.append(length)
        assert self.writes == [b'\x97'] and length == 1
        return b'\xA6'


class ReadFaultBus(touch.Bsc):
    def __init__(self, mode='ok'):
        super().__init__(base=touch.C['BSC0_BASE'], abort_delay=3)
        self.mode = mode
        self.fifo_reads = 0
        self.regs[touch.C['BSC_C_OFF']] = touch.C['BSC_C_I2CEN']

    def _begin(self, is_read, repeated):
        super()._begin(is_read, repeated)
        if not is_read:
            return
        assert not repeated, 'READ must be STOP-separated'
        if self.mode == 'nack':
            self.err = True
        elif self.mode == 'clkt':
            self.clkt = True
        elif self.mode == 'done-with-data':
            self.done = True
        elif self.mode == 'stall':
            self.rxbuf.clear()

    def read32(self, offset):
        if offset == touch.C['BSC_FIFO_OFF']:
            self.fifo_reads += 1
        if (offset == touch.C['BSC_S_OFF'] and self.active and self.is_read
                and not self.abort_pending and not self.rxbuf
                and self.mode in ('stall', 'done-stall')):
            self.status_reads += 1
            return touch.C['BSC_S_TA'] | touch.C['BSC_S_TXE']
        return super().read32(offset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pmfc', required=True)
    args = ap.parse_args()
    touch.PMFC = pathlib.Path(args.pmfc).resolve()
    if not touch.PMFC.is_file():
        raise SystemExit('compiler not found')
    cases, steps_total = 0, 0
    with tempfile.TemporaryDirectory(prefix='anvil-i2c-read-gate-') as td:
        image = pathlib.Path(td) / 'mcu-read.img'
        touch.build('RaspberryPi4/Tests/i2c_mcu_read_timeline_probe.pi4', image,
                    bss_addr=BSS, load_addr=LOAD, stack_addr=STACK)
        symbols = touch.image_symbols(image)

        def execute(bus):
            nonlocal steps_total
            cpu, output, steps = touch.run(image, bus, load_addr=LOAD, stack_addr=STACK)
            steps_total += steps
            assert cpu.x[0] == 0
            def q(name):
                return touch.signed_u64(touch.memory_u64(cpu, symbols, name))
            assert q('probe_done') == 0x49324D52
            assert not bus.unknown_reads and not bus.unknown_writes
            return q

        for mode, expected, reads in (
                ('ok', 0, 1), ('done-with-data', 0, 1),
                ('nack', touch.C['I2C_NACK'], 0),
                ('clkt', I2C_CLKT, 0),
                ('stall', touch.C['I2C_TIMEOUT'], 0),
                ('done-stall', touch.C['I2C_TIMEOUT'], 1)):
            bus = ReadFaultBus(mode)
            dev = IdentityMcu()
            bus.add(dev)
            q = execute(bus)
            assert q('probe_write_result') == 0, mode
            assert q('probe_read_result') == expected, mode
            assert bus.starts == 2 and bus.repeated_starts == 0, mode
            assert dev.writes == [b'\x97'] and dev.reads == [1], mode
            assert bus.fifo_reads == reads and q('probe_received') == reads, mode
            assert q('probe_byte') == (0xA6 if reads else -1), mode
            assert q('probe_start_c') & touch.C['BSC_C_READ'], mode
            if expected == 0:
                assert q('probe_recover_result') == -1, mode
                assert q('probe_rxd_tick') > 0 and q('probe_done_tick') > 0, mode
            else:
                assert q('probe_recover_result') == 1, mode
                assert not bus.active and not bus.abort_pending, mode
            if mode in ('stall', 'done-stall'):
                assert touch.CNTFRQ // 50 <= q('probe_elapsed') < touch.CNTFRQ // 40, mode
            cases += 1

        # Write refusal must never turn into a speculative read.
        bus = ReadFaultBus()
        q = execute(bus)
        assert q('probe_write_result') == touch.C['I2C_NACK']
        assert q('probe_read_result') == -10 and bus.starts == 1 and bus.fifo_reads == 0
        cases += 1

        bus = ReadFaultBus()
        bus.regs[touch.C['BSC_C_OFF']] = 0
        q = execute(bus)
        assert q('probe_write_result') == -10 and bus.register_writes == []
        cases += 1

        bus = ReadFaultBus()
        bus.active = True
        bus.ta = True
        bus.stall_this = True
        q = execute(bus)
        assert q('probe_write_result') == -10 and bus.register_writes == []
        cases += 1
    print(f'i2c_mcu_read_timeline_check: PASS - {cases} cases, {steps_total:,} emitted instructions')
    print('  exact pointer/READ, RXD-only FIFO, error priority, bounded recovery and refusal')
    return 0


if __name__ == '__main__':
    sys.exit(main())
