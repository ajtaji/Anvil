# VL805 cold-start firmware notification

The genuine PCIe cold path asserted PERST and enumerated the endpoint without
notifying VideoCore to restore VL805 firmware. This is a source-level omission;
it has not been proven to cause the intermittent USB boot hang in topic767.

`MailboxNotifyVl805Reset` uses the existing mailbox property-buffer lifecycle:
tag0x30058, four-byte request/response and BDF0x100000 (bus1,device0,function0).
Mailbox errors remain available through `MailboxError`.

`PcieEnumerate` calls `PcieColdFirmwareReady` only after endpoint/bridge register
readbacks and before publishing successful enumeration. The helper returns
immediately for trained-link adoption: no firmware reload, timer read or delay.
On the cold path it validates counter frequency, submits the notification,
then waits at least200 microseconds using the architectural counter. A fixed
iteration escape refuses a stalled counter instead of waiting forever.
Failure leaves enumeration incomplete and returns PCIe error-15 with a complete
diagnostic sentence. This makes mailbox.pi4 an explicit PCIe dependency; callers
include it first, as the board composition already does.

The settle duration follows [U-Boot's notification implementation](https://github.com/u-boot/u-boot/blob/master/arch/arm/mach-bcm283x/msg.c),
which uses200 microseconds. [Linux's reset driver](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/reset/reset-raspberrypi.c)
uses200–1000 microseconds after the same property. [U-Boot host probe](https://github.com/u-boot/u-boot/blob/master/drivers/usb/host/xhci-pci.c)
performs that reset before host registration. These sources were consulted for
protocol facts and ordering; no implementation was copied.

`tools/vl805_firmware_check.py --compiler <unified-IDE>` executes the production
mailbox wrapper and cold helper with a modeled wire/counter. It verifies the
tag/address, notification-before-settle, skipped adoption, begin/send failures
and invalid-frequency refusal. Independently compiled missing-notification and
wrong-order mutants must fail the behavioral checks. Structural assertions
also require the call after mapping readbacks and before enumeration success.
This does not claim actual firmware delivery, stopped-counter hardware testing,
or silicon acceptance. No board reset or full monitor build was performed.
