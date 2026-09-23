# Pi 3 LAN9514 register, MAC and PHY transport

Status: desk-proven, not integrated into a board build and not silicon-proven.

`RaspberryPi3/Lib/lan9514_transport.pbi` is the serialized layer above the
validated `0424:ec00` child and `usb_control.pbi`. It provides exact four-byte
little-endian SMSC95xx vendor register reads (`$C0/$A1`) and writes
(`$40/$A0`), MAC ADDRL/ADDRH reads and writes, and MII PHY reads and writes.

MAC publication occurs only after both registers complete and the six bytes
are a nonzero, non-broadcast unicast address. PHY operations follow the pinned
`smsc95xx.c` order: prove MII_ADDR idle, issue `(phy << 11) | (reg << 6) |
BUSY` (plus WRITE for writes), poll BUSY clear, then read MII_DATA for reads.
Every busy delay, NAK, timeout and finite poll budget is returned to the
scheduler. An overlapping caller is refused without cancelling the owner.

Authority is the pinned Raspberry Pi Linux tree at commit
`7d1826930811232688a50c99c540fbb137aed081`, specifically
`drivers/net/usb/smsc95xx.c` and `drivers/net/usb/smsc95xx.h`. No upstream
implementation was copied.

Desk gate:

```text
python tools/pi3_lan9514_transport_check.py
```

Integration later must include the protocol, control and enumeration layers
first, attach the same coherent setup/data buffers, then give this transport a
scheduler owner. It does not claim CAP_USB, CAP_NET, a link, or hardware proof.
