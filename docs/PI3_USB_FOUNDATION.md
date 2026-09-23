# Pi3 USB/Ethernet foundation: native host desk slice, not boot-wired

Desk-only original source, not boot-wired. `usb_host_core.pbi` implements the
consumable cold-owner reset transaction for pre-4.20 DWC2 cores. It refuses DMA,
global interrupts or enabled host channels before writes, bounds reset/AHB-idle
polling by elapsed microseconds plus a frozen-timer backstop, and retains failed
ownership after a submitted reset. It does not seize a firmware-owned controller.

The same library now constructs HPRT0 writes without reflecting its three
write-one-to-clear change bits, constructs HCCHAR/HCTSIZ values under the
BCM2835 driver's 65,535-byte and 511-packet limits, and classifies every channel
halt as complete, retryable NAK/NYET, or a distinct fatal cause. These are data
and state boundaries shared by the transfer owner below.

`usb_transfer.pbi` submits one serialized buffer-DMA host-channel transaction.
It programs interrupt clear, split state, transfer size, DMA address and HCCHAR
in that order; publishes actual length and next PID only after a terminal halt;
leaves NAK/NYET retry to the scheduler; and performs the DWC2 CHDIS+CHENA halt
protocol on timeout. It accepts only a validated 32-bit DMA bus address and does
not turn an arbitrary source pointer into one.

Named services `Pi3UsbRead`, `Pi3UsbWrite`, `Pi3UsbTime` are supplied by the caller.
The new native adapter establishes its primary-core, power and ordered-access
contract below before using this core. Software
deadlines cannot recover an interconnect transaction that never completes.

`usb_protocol.pbi` now owns the USB chapter-9 and hub-class byte protocol. It
builds exact setup packets, validates device and hub descriptors, builds hub
port power/reset/status requests, walks a bounded configuration descriptor and
publishes a SMSC95xx endpoint set only after the whole stream is valid. It
binds only a vendor-specific interface with one unambiguous bulk-IN/bulk-OUT
pair; it never treats an arbitrary bulk device as Ethernet.

`lan9514_protocol.pbi` encodes the eight-byte vendor control request for
four-byte register access, identifies the Pi 3's EC00 SMSC95xx function, builds
the two-word bulk-OUT prefix with hardware padding/FCS left enabled, and decodes
bounded aggregate bulk-IN records with the two-byte receive offset and FCS
removed from the exported Ethernet length. Error-summary frames, impossible
lengths and truncated aggregates are rejected before a frame pointer is
published. Checksum offload is deliberately absent from this first explicit
contract.

Native DMA adaptation, control-transfer composition,
exact-length control completion, disconnect cancellation,
register ownership, MAC/PHY setup and Ethernet traffic remain unimplemented.
Buffers must be valid caller-owned coherent RAM; nonzero pointers are not a
memory-safety proof.

Facts consulted in official Raspberry Pi Linux commit
`7d1826930811232688a50c99c540fbb137aed081`: `drivers/usb/dwc2/hw.h`, `core.c`,
`drivers/net/usb/smsc95xx.c`, `smsc95xx.h`. These supply register bits, old/new
reset completion semantics and vendor-request framing, not copied implementation.
The separate reference checkout is not part of the public source.

Host gate: compile `RaspberryPi3/Tests/usb_foundation_host.pb` with host PureBasic,
then run the console executable. Exit zero proves six reset scenarios (success,
identity refusal, DMA ownership refusal, idle timeout, sticky reset timeout,
active channel refusal), HPRT0 W1C ownership, transfer-word bounds and halt
classification. It also proves exact standard/hub setup packets, hostile
descriptor rejection, topology identity, endpoint discovery, SMSC register
requests and TX/RX frame boundaries. The current passing host executable SHA256
is `37c46669f99d527c1d9edea37a0b42c522181e5e36f128b0feceee9ba8c372be`.

`RaspberryPi3/Tests/usb_protocol.pi3` is the emitted-code fixture. The unified
IDE application compiled it with `--compile`, explicit `-t pi3` and
`--entry-returns`: 14,884 raw bytes, SHA256
`bc00bde318faaf46bf57040c7cc1068fc1e4f9cde2a43a5b7b45ece544a2116c`.
The focused gate executes four paths from that emitted image, including core
reset and bounded channel-timeout recovery, in 18,525 interpreted A64
instructions. This proves that the production includes are valid PureMetal
target source and that those paths execute; it does not touch hardware.

Run both levels together with:

```text
python tools/pi3_usb_foundation_check.py --compiler <PureMetalForge.exe>
```

The named executable must be the unified IDE application. The gate never
invokes or falls back to the retired separate console compiler.

Numeric error codes remain in the hardware libraries because PureMetal targets
cannot return strings. The future console boundary must print full sentences:
core -1 consumed ownership, -2 identity/revision, -3 existing DMA/IRQ/channel
owner, -4 AHB not idle, -5 reset failed, -6 invalid transfer, -7 AHB channel
fault, -8 endpoint stall, -9 babble, -10 transaction/frame/toggle error, -11
cause-less halt, -12 bounded transfer timeout with successful channel halt, -13
channel halt failure requiring controller recovery. USB protocol -1 storage,
-2 request range, -3 truncation, -4
malformed descriptor, -5 wrong identity, -6 duplicate endpoints, -7 missing
bulk pair. LAN -1 storage/request, -2 transmit length, -3 truncated record, -4
receive error summary, -5 impossible receive length.

Next: silicon admission of the native host slice below; control-transfer
composition over the bounded buffer-DMA primitive; enumerate 0424:9514,
power/reset its port 1, then
enumerate 0424:ec00; exact-length SMSC register transport, reset, MAC/PHY/link
and bulk packet movement; then named Pi3 HAL integration and the shared network
stack. The onboard Ethernet function is high-speed behind the high-speed hub;
the implementation must still retain split-transaction fields for future
full/low-speed devices rather than silently assuming every hub child is high
speed.

Do not advertise `CAP_USB` or `CAP_NET` before actual enumeration, repeated
transfers, network traffic, disconnect/reconnect and recovery pass on the Pi 3
Model B v1.2. This work does not yet make remote SD updating possible; it makes
the byte and state contracts underneath that transport testable without the
board.

## Native host desk slice (2026-09-12)

`usb_native.pbi` supplies `Pi3UsbPowerAcquire`, `Pi3UsbRead`, `Pi3UsbWrite`
and `Pi3UsbTime`. Include the real timer and mailbox first. The adapter refuses
before device access unless it measures primary affinity zero (including upper
affinity levels), EL2 or EL3, masked DAIF and disabled MMU/data cache. This is a
cold uncached ownership contract, **not** cached DMA admission. Reads/writes are
32-bit, aligned, limited to the controller register page at ARM physical
`0x3F980000`, and surrounded by DSB SY / ISB. It never treats the Pi4 xHCI map as
the Pi3 USB device.

Power acquisition uses firmware USB HCD device 3 with SET_POWER_STATE ON+WAIT,
validates the response tag/length/device/state, and retains failed ownership.
It never switches the domain off or cycles another controller owner. The
mailbox library retains an outstanding timed-out request buffer until reboot.
Firmware support, a valid resident mailbox buffer and exclusive boot-time use
remain prerequisites; no software deadline can recover a stalled interconnect.

`usb_host_init.pbi`, included after the adapter and `usb_host_core.pbi`, exposes:

- `Pi3UsbHostInit()`: validate/reset the cold owner; require internal DMA
  architecture, dynamic FIFO support and UTMI capability; select a supported
  UTMI width, reset after PHY selection, require measured host mode, restart
  the PHY clock, configure host mode and bounded FIFO regions, flush TX/RX,
  power the root port. The BCM RX allocation is 774 words. TX depths come from
  hardware registers and all three regions must fit reported FIFO RAM.
- `Pi3UsbRootPortReset()`: refuse active DMA/IRQ/channels, require a connected
  non-overcurrent port, assert/reset with readback, hold for 50 ms using the
  timer, deassert with readback, and wait boundedly for connection+enable.

The host slice deliberately leaves global interrupts and DMA disabled. It is
not an enumerating USB host and cannot yet carry Ethernet. The next transfer
owner must establish coherent buffer lifetimes before enabling buffer DMA.
No board includes, `CAP_USB` or `CAP_NET` were changed.

Host state is 0/unstarted, 1/ready, -1/consumed or failed. Failures do not retry
or silently reacquire hardware. An owned PHY re-reset is explicit through
`Pi3UsbCoreResetMode(1)` and requires an existing successful core owner; the
legacy no-argument reset remains the cold-only entry. Error text at a future
console boundary must describe the cause: -20 context, -21 firmware power,
-22 MMIO admission, -30 host ownership, -31 power acquisition, -32 unsupported
hardware shape, -33 write readback, -34 host-mode timeout, -35 FIFO capacity,
-36 FIFO flush/delay, -37 connection/overcurrent/speed, -38 reset hold timer,
-39 reset completion. Existing core codes are propagated where applicable.

`python tools/pi3_usb_native_check.py --compiler <PureMetalForge.exe>` passes
nine hostile native-host scenarios and 28 checks executing actual emitted A64,
including EL2/EL3, upper-affinity refusal, MMU/cache/DAIF refusal, malformed
firmware replies, width/address/barrier checks and a missing-DSB binary mutant.
The frozen timer's finite spin ceiling is exercised in the native host test;
the interpreter does not claim a real interconnect or PHY model.

The existing foundation gate also passes seven emitted cases, including three
HPRT0 regression cases. [Bug 780](https://forum.ajtaji.com/topic/780) was logged
before correction: ordinary control writes must clear ENA as well as the three
change bits, because reflecting ENA disables an enabled port.

Primary references (facts only; no implementation copied): pinned Raspberry Pi
Linux `7d1826930811232688a50c99c540fbb137aed081`,
[`hw.h`](https://github.com/raspberrypi/linux/blob/7d1826930811232688a50c99c540fbb137aed081/drivers/usb/dwc2/hw.h),
[`core.c`](https://github.com/raspberrypi/linux/blob/7d1826930811232688a50c99c540fbb137aed081/drivers/usb/dwc2/core.c),
[`hcd.c`](https://github.com/raspberrypi/linux/blob/7d1826930811232688a50c99c540fbb137aed081/drivers/usb/dwc2/hcd.c),
[`hcd.h`](https://github.com/raspberrypi/linux/blob/7d1826930811232688a50c99c540fbb137aed081/drivers/usb/dwc2/hcd.h),
[`params.c`](https://github.com/raspberrypi/linux/blob/7d1826930811232688a50c99c540fbb137aed081/drivers/usb/dwc2/params.c),
and the [firmware power protocol](https://github.com/raspberrypi/firmware/wiki/Mailbox-property-interface#power).

Remaining silicon proof: verify firmware power response and controller identity,
capabilities/FIFO sizes, host-mode/PHY transition and connected root-port reset
on the actual Pi3B v1.2. Then implement and prove control transfers, LAN9514 hub
and EC00 function enumeration, DMA buffers, MAC/PHY configuration, repeated
Ethernet traffic and disconnect recovery. No reset, deployment or board access
was performed for this desk slice.
