# Pi 3 LAN9514 reset, link and frame runtime

Status: desk-proven and emitted-code-proven. It has not been integrated into a
Pi 3 board image, exercised on silicon, or used to claim `CAP_USB`/`CAP_NET`.

`RaspberryPi3/Lib/lan9514_runtime.pbi` is the scheduler-owned layer above the
committed register/MAC/PHY and USB enumeration transports. It performs the
SMSC9514 lite reset and the Linux-ordered configuration of MAC address, bulk
burst behavior, two-byte receive offset, interrupt status, chip identity,
LEDs, flow control, VLAN EtherType, PHY interrupt, TX and RX paths.

The integrated PHY is address 1. The runtime enables and restarts
autonegotiation without isolating the PHY, double-reads BMSR because link is
latch-low, waits for both link and autonegotiation completion with a caller
budget, then reads PHY_SPECIAL to publish 10/100 Mbps and half/full duplex.
The selected duplex is written to MAC_CR before RX/TX become ready.

Bulk TX prepends the two SMSC command words. Bulk RX validates the four-byte
status, two-byte offset, wire length, FCS exclusion and aggregate alignment.
DATA0/DATA1 state is independent and persistent per endpoint. A NAK after
partial progress resumes at the advanced DMA address and hardware-reported
PID. Zero-progress NAKs consume a visible caller budget. Disconnect, malformed
or short records fail closed. If a DWC2 channel cannot halt and retains
`p3usb_transfer_owner`, the runtime quarantines its buffers and refuses reuse.

The board integration owner must provide two non-overlapping coherent buffers:
at least 1,526 bytes for TX and 2,560 bytes for RX. Their 32-bit DMA bus
addresses must already use the BCM2837 coherent alias selected by the native
USB layer. Integration must call the layers in this order:

1. Native DWC2 init and root-port proof.
2. USB enumeration through the validated `0424:9514` hub to `0424:ec00`.
3. `Pi3LanTransportAttach` for the control buffer.
4. `Pi3LanRuntimeBuffers` for separately owned TX/RX buffers.
5. `Pi3LanRuntimeBegin`, then one `Pi3LanRuntimeStep(nowUs)` per scheduler turn.
6. Only after `P3_LAN_RUNTIME_READY`, schedule one TX or RX owner at a time.

The current USB diagnostic owner keeps DMA and IRQ disabled after its one-shot
proof. Runtime integration therefore remains a separate acceptance slice: it
must explicitly acquire coherent buffers and DMA ownership, and it must never
reuse them when the native transport retains its halt quarantine.

Authority is the pinned Raspberry Pi Linux tree at commit
`7d1826930811232688a50c99c540fbb137aed081`, especially
`drivers/net/usb/smsc95xx.c` and `smsc95xx.h`, plus the pinned U-Boot generic
MII definitions. No upstream implementation was copied.

Desk gate:

```text
python tools/pi3_lan9514_runtime_check.py
```

The gate covers reset polling, exact configuration values, latch-low link
handling, duplex publication, partial NAK resume, persistent endpoint toggles,
multi-frame RX aggregates, retry exhaustion, detach, short TX completion and
retained-owner quarantine. It also compiles and interprets the emitted A64.
