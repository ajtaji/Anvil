# Pi 3 resident USB diagnostic

Desk-integrated only. The updater offers `usbdiag` after its existing SD mount,
running-generation confirmation and watchdog stop. USB never runs during that
health path or automatically at startup. The immutable loader is unchanged.
`CAP_USB` and `CAP_NET` remain disabled.

The command is one-shot per boot. It checks a confirmed idle updater, primary
EL2/EL3 with DAIF masked and MMU/data cache off, and resident BSS buffer bounds.
It then reports firmware power/core/PHY/FIFO initialization, root reset,
register values in decimal, each enumeration state, final errors and endpoints.
The BCM2837 bus alias comes from the pinned device-tree `dma-ranges`, not from
a Pi 4 translation. The 8-byte setup and 512-byte data buffers remain allocated
for the entire monitor lifetime. No SD writes occur in the diagnostic.

Enumeration is stepped serially with finite retry/poll budgets, 100 ms channel
timeouts, a 15-second overall timer limit and a separate iteration ceiling.
There is no interrupt reentry or background task. This is not a claim that the
full monitor scheduler or network stack is integrated.

After an acknowledged channel halt, DMA is disabled and read back before
returning to the prompt. An unacknowledged owner remains quarantined with its
buffers retained; the command refuses a second run. Standard update/status and
explicit reset commands remain available. No automatic reset is added.
An interconnect-stalled MMIO access cannot be bounded by a software loop:
hardware acceptance must account for that risk and preserve the known-good
confirmed slot and immutable loader recovery window.

## Command extension seam

`Pi3UpdateRegisterCommand(handler)` accepts one registration before serving.
The handler has the exact prototype `Procedure.i Handler()` and returns 1 for
a completely parsed/handled command or 0 for standard dispatch. The default
`Pi3NoCommandExtension()` is a real unhandled handler. Quarantined input never
reaches the extension; the outer line reader rejects overflow before dispatch.
After an unhandled result the standard parser cursor is restored. The USB
handler requires the exact full `usbdiag` command, including end-of-line.

## Reproducible desk evidence

Using the installed unified compiler via `--compile`:

```text
python tools/build.py pi3-updater --compiler <PureMetalForge.exe>
python tools/pi3_usb_diagnostic_check.py --image build/pi3/anvil.img
python tools/pi3_usb_native_check.py --compiler <PureMetalForge.exe>
python tools/pi3_usb_enumeration_check.py --compiler <PureMetalForge.exe>
python tools/pi3_update_transport_check.py --compiler <PureMetalForge.exe>
python tools/pi3_update_host_check.py
```

The candidate gate executes the emitted diagnostic orchestration with explicit
mocks at the separately tested native-host and enumeration boundaries: 14
cases, covering refusal, handled/unhandled commands, timeout, DMA shutdown and
quarantine. It is not a full hardware simulation. Native gate: 28 emitted and
9 hostile host scenarios, with a missing-barrier mutant rejected. Existing
receive/framing gate: 11 emitted cases; host update protocol: 61 checks.

Build 11 candidate (not deployed): raw 183724 bytes, SHA256
`f59a7a5e9d8bd69884cf7eb5f89bb7ac55e2ca633cfb6183dcdaf52e46c2379a`;
P3SLOT 183980 bytes, SHA256
`6d4eb9988a1e4e5802f85e6bdca8a59aeb7ef15e4f7143cdf1f09b12ba16b09f`.
Compiler SHA256
`5c87d98c096bd150e1eca45b7fa1a676ef0eaaff008a7a775a3fade9449fc374`.

Deployment remains pending explicit selection and transfer for silicon proof.
Normal A/B inactive-slot staging/readback/pending-trial semantics apply; never
overwrite the immutable loader or the confirmed fallback as part of this test.
