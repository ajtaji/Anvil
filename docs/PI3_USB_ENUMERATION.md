# Pi 3 USB control and LAN9514 enumeration

Status: desk-proven controller-independent layer; not yet wired into the boot
board and not yet proved on Pi 3 silicon.

## Scope and ownership

`RaspberryPi3/Lib/usb_control.pbi` composes a USB control transfer from exact
SETUP, optional data, and opposite-direction status stages.  Each call to
`Pi3UsbControlStep()` submits at most one transaction to the existing bounded
`Pi3UsbChannelTransfer()` transport.  NAK/NYET returns
`P3_USB_CONTROL_RETRY`; timeout and other fatal transport results return as
errors.  There is no hidden retry or wait loop.

An acknowledged prefix followed by NAK is resumed at the advanced DMA address
using the DWC2-reported next PID.  SETUP and status cannot report partial
progress.  OUT data must complete in full; a short IN data stage is retained
for the caller to validate against the descriptor it requested.

`RaspberryPi3/Lib/usb_enumeration.pbi` owns the fixed Pi 3 topology walk:

1. Validate the already reset root port as connected, enabled and high speed.
2. Read the first eight bytes at address zero and require EP0 max packet 64.
3. Assign address 1, expose a 10 ms scheduler deadline, then require the full
   device identity `0424:9514` and a validated hub configuration.
4. Configure the hub and validate its class descriptor and port count.
5. Power hub port 1 and expose `max(100 ms, bPwrOn2PwrGood * 2 ms)` as a
   scheduler deadline.
6. Read port status, issue port reset, expose reset poll deadlines and a
   caller-chosen finite poll budget, then require connection, enable, power,
   high speed and reset-clear.  A disconnect or over-current fails closed.
7. Clear reported reset, connection and enable change features.
8. Read the child at address zero, assign address 2, and require identity
   `0424:ec00`.
9. Validate the complete descriptor stream into private endpoint candidates,
   configure the child, and re-read hub port status.
10. Publish the bulk-IN, bulk-OUT and optional interrupt-IN endpoint set only
    after that final connection/status validation has passed with no pending
    connection/reset/enable change.

The scheduler calls `Pi3UsbEnumerationStep(nowUs)`.  Its positive results are
`P3_USB_ENUM_PROGRESS`, `P3_USB_ENUM_RETRY`, `P3_USB_ENUM_WAIT`, and
`P3_USB_ENUM_READY`.  The next time deadline is
`p3usb_enum_wait_until`.  Remaining budgets are available through
`Pi3UsbEnumerationRetriesLeft()` and `Pi3UsbEnumerationPollsLeft()`.

The caller owns two distinct address pairs:

- an 8-byte CPU setup pointer and aligned 32-bit setup DMA bus address;
- a CPU data pointer of at least 512 bytes and its aligned 32-bit DMA bus
  address.

They must name the same resident, DMA-coherent storage as viewed by the CPU and
DWC2.  This layer deliberately performs no arbitrary ARM/bus address
translation and no cache maintenance; those remain properties of the bounded
channel transport and its allocation owner.

## Authorities

The implementation was derived from local pinned sources, not guessed from
the observed board:

- `Datasheets/pi3/raspberrypi-linux-reference`, commit
  `7d1826930811232688a50c99c540fbb137aed081`
  - `arch/arm/boot/dts/broadcom/bcm2837-rpi-3-b.dts`
  - `arch/arm/boot/dts/broadcom/bcm283x-rpi-smsc9514.dtsi`
  - `drivers/usb/dwc2/hw.h`
  - `drivers/usb/dwc2/hcd.c`
  - `drivers/net/usb/smsc95xx.c`
- `RaspberryPi4/Reference/rpi-6.12.y_usb_core_message.c`
- `RaspberryPi4/Reference/rpi-6.12.y_usb_core_hub.c`
- `RaspberryPi4/Reference/v2025.01_usb_defs.h`
- `RaspberryPi4/Reference/v2025.01_uboot_usb.c`
- `RaspberryPi4/Reference/v2025.01_uboot_usb_hub.c`

The pinned device tree fixes hub address path port 1 and its Ethernet child at
hub port 1.  The pinned SMSC95xx table identifies `0424:ec00`.  Linux/U-Boot
define recipient-other hub port requests, change-feature numbers, status bits,
power-good units, address-settle delay, reset delays, and complete reset status
requirements.  DWC2 `HCTSIZ` defines SETUP as PID value 3 and DATA1 as 2.

## Desk gate

Run:

```text
python tools/pi3_usb_enumeration_check.py
```

The gate compiles and runs the original PureBasic state machines on the host,
then compiles the emitted fixture with the unified `PureMetalForge.exe` and
executes four cases in the AArch64 interpreter.  Hostile cases cover wrong hub
and LAN identities, malformed and oversized descriptor streams, a short full
configuration response, duplicate endpoints, disconnect during reset,
disconnect/change before publication, NAK exhaustion and continuation,
partial-progress NAK resumption, transport timeout, invalid root state and an
undersized data buffer.  The static part refuses a loop inside the control
step and confirms the pinned topology source remains present.

No desk result is hardware proof.  Integration still needs a coherent buffer
allocation, inclusion after `usb_transfer.pbi`, a scheduler owner, and a
separate reviewed board build before any Pi 3 test.

