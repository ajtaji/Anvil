#!/usr/bin/env python3
"""Execute the returning MCU pointer/READ diagnostic on a bounded BSC model.

This proves what the diagnostic does, not how the real MCU answers. Faults
are explicit modeled inputs; no GPIO, firmware, or hardware access is used.
"""
import argparse
import os
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
        # These are explicit broken-controller observations, not normal BSC
        # semantics. The base model completes from wire-side DLEN progress.
        elif self.mode == 'one-byte-no-done':
            self.rxbuf = bytearray(b'\xA6')
        elif self.mode == 'threshold-no-done':
            # Reproduce the anomalous RXR/data-without-DONE shape without
            # asserting that a correct DLEN=1 controller would receive 12.
            self.rxbuf = bytearray(b'\xA6' * 12)

    # The FIFO read is counted by the base model (one place, unconditional),
    # and this subclass used to count it a second time on its way past - so
    # every expectation here was off by a factor of two. Nothing caught it
    # because the gate could not be run from a sweep at all: it demanded its
    # compiler as an option and ignored the environment every other gate uses.
    def read32(self, offset):
        if (offset == touch.C['BSC_S_OFF'] and self.active and self.is_read
                and not self.abort_pending
                and self.mode in ('stall', 'one-byte-no-done', 'threshold-no-done')):
            self.status_reads += 1
            status = touch.C['BSC_S_TA'] | touch.C['BSC_S_TXE']
            if self.rxbuf:
                status |= touch.C['BSC_S_RXD']
            if len(self.rxbuf) >= 12:
                status |= touch.C['BSC_S_RXR']
            return status
        return super().read32(offset)


def main():
    ap = argparse.ArgumentParser()
    # Every other gate in this tree takes the compiler from PMF_COMPILER when
    # the option is absent, so a whole-set sweep sets it once. This one asked
    # for the option and nothing else, which made it the single gate a sweep
    # could not run.
    ap.add_argument('--compiler', default=os.environ.get('PMF_COMPILER'))
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit('i2c MCU read timeline gate: pass --compiler or set '
                         'PMF_COMPILER')
    touch.PMF_COMPILER = pathlib.Path(args.compiler).resolve()
    if not touch.PMF_COMPILER.is_file():
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
                ('ok', 0, 1),
                ('nack', touch.C['I2C_NACK'], 0),
                ('clkt', I2C_CLKT, 0),
                ('stall', touch.C['I2C_TIMEOUT'], 0),
                ('one-byte-no-done', touch.C['I2C_TIMEOUT'], 0),
                ('threshold-no-done', touch.C['I2C_TIMEOUT'], 1)):
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
                assert not bus.done and bus.regs[touch.C['BSC_C_OFF']] == touch.C['BSC_C_I2CEN'], mode
            else:
                assert q('probe_recover_result') == 1, mode
                assert not bus.active and not bus.abort_pending, mode
            if mode in ('stall', 'one-byte-no-done', 'threshold-no-done'):
                assert touch.CNTFRQ // 50 <= q('probe_elapsed') < touch.CNTFRQ // 40, mode
            cases += 1

        # READ may remain asserted after a completed transfer. No TA means
        # that it is idle, not a speculative attempt to repair a busy bus.
        bus = ReadFaultBus()
        bus.regs[touch.C['BSC_C_OFF']] |= touch.C['BSC_C_READ']
        bus.done = True
        bus.add(IdentityMcu())
        q = execute(bus)
        assert q('probe_read_result') == 0 and bus.fifo_reads == 1
        assert not bus.done and bus.regs[touch.C['BSC_C_OFF']] == touch.C['BSC_C_I2CEN']
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
    print('  exact pointer/READ, RXD plus DONE/RXR FIFO service, error priority, bounded recovery and refusal')
    return 0


if __name__ == '__main__':
    sys.exit(main())
