# Panel and touch boot trace

On a Pi monitor containing this feature, type `touch trace` to read the
retained history of the panel/touch identity transactions from that boot.
The command takes no arguments. It does not initialize or select an I2C bus,
retry a probe, read a device register, or change panel power/reset state.
The ordinary `touch`, `touch points`, and `touch panel` commands have different
hardware behavior; they are not substitutes for this read-only viewer.

Capture is enabled immediately before `ScreenUp`, disabled immediately after
`TouchBoot`, and retained in RAM until the monitor restarts. The I2C library
defaults to tracing off; the Pi entry point explicitly opts in. There is no
trace file and no background storage write.

## Reading the records

| Edge | Meaning |
| --- | --- |
| BEGIN | Controller state before the existing transaction's preflight/status clearing. The result field is a placeholder. |
| FAULT | The first observed failure or non-idle preflight state, before cleanup. The status word is the one already observed by the polling code. |
| END | The transaction's real return code and final observed controller state. |
| TX | First TXD/TXW progress observed. |
| READST | Goodix read length and READ/ST command written. |
| RX | First RXD progress observed. |
| DONE | First DONE observed. |

Progress rows reuse the status word already loaded by the polling loop and add
no MMIO read. The viewer prints their C, DLEN and A fields as `not-sampled`.
BEGIN/FAULT/END retain their original nine-field layout and meanings.

`preflight` is meaningful on END only: `0` means no idle recovery was needed,
`1` means that recovery succeeded, and `-1` means it failed. It does not report
all later error-path cleanup. A FAULT followed by successful END is possible:
preflight can recover a non-idle controller before completing the transaction.

The named phases are the panel MCU's register `0x97` size, `0x98` identity and
`0x99` version pointer writes/reads, followed by the first Goodix identity read
at each attempted address, `0x5D` and `0x14`. A phase not attempted has no record.

Each row includes architectural counter ticks and raw C/S/DLEN/A values.
Ticks are not microseconds. Register reads are sequential, not an atomic
snapshot, and undocumented status bits are not assigned a guessed meaning.
The trace never samples the receive FIFO. Capturing still costs instructions
and safe register reads, so it can perturb timing; it is not proof that an
intermittent failure will reproduce identically with capture disabled.

The 64-record buffer preserves the earliest history without wrapping. A new
transaction is admitted only with room for BEGIN, four progress milestones,
optional FAULT and END.
The viewer reports saturation rather than silently presenting truncated
history as complete. No records means no matching transaction was captured;
it does not mean that the touch hardware passed.

## Validation and limits

The emitted-code checks are:

```text
python tools/a64/i2c_boot_trace_emitted_check.py --pmfc /path/to/pmfc
python tools/touch_trace_command_check.py --pmfc /path/to/pmfc
python tools/a64/touch_emitted_check.py --pmfc /path/to/pmfc
```

They check trace-off/trace-on wire equivalence in the controller model,
pre-cleanup faults, recovery outcomes, paired saturation, exact viewer output,
normal command routing and forbidden MMIO during readback. These are model
and emitted-code tests, not physical touch acceptance. Identity-read failures
alone do not prove that a part is absent, held in reset, or incorrectly wired.
