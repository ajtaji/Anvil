# The Raspberry Pi 4 boot volume

Everything a Raspberry Pi 4 needs in order to boot Anvil, except the three
files Raspberry Pi publishes and this repository does not redistribute.

## How to lay the medium out

**Two partitions are what we recommend, and what this bench uses:**

| Partition | Size | Format | Holds |
|---|---|---|---|
| 1 | **1 GB** | **FAT32** | the boot set — firmware, `KERNEL8.IMG`, `CONFIG.TXT`, `SETTINGS.TXT`, the radio blobs, any kept recovery images |
| 2 | **all the rest** | **exFAT** | everything else — model weights, voices, dictionaries, payloads, audio, scratch |

The firmware can only read FAT, so partition 1 has to be FAT32 and has to be
first. It does not have to be large: a gigabyte holds the boot set several
times over, and a small partition mounts quickly and keeps the boot files
together where a recovery image is reachable by the firmware that needs it.
Everything else is better off on exFAT — **no 4 GB file limit**, long names,
and much larger clusters, which is why writing to it is faster here than
writing to the FAT32 partition.

Then tell the monitor where data lives, once:

```text
pmf> settings set data.path 2:/
pmf> settings save
```

After that a recipe writes `data:/models/...` and never a partition number, so
the same recipe works on either layout.

**One FAT32 partition still works.** Leave `data.path` alone and `data:/` means
the root of partition 1. Nothing here is required; the two-partition layout is
a recommendation, not a gate.

> **Repartitioning erases the medium.** Everything on it goes. Do this to a
> blank stick or card, or to one whose contents you have copied off first.

### Windows

`diskpart` in an elevated prompt — **check `list disk` twice and be certain
which number is the removable medium before `select`:**

```text
diskpart
list disk
select disk <N>
clean
convert mbr
create partition primary size=1024
format fs=fat32 quick label=PIBOOT
assign
create partition primary
format fs=exfat quick label=PIDATA
assign
exit
```

Disk Management does the same thing with a mouse: delete every volume on the
medium, then New Simple Volume twice with those sizes and formats.

### Linux

```sh
sudo parted /dev/sdX --script mklabel msdos \
  mkpart primary fat32 1MiB 1025MiB \
  mkpart primary 1025MiB 100%
sudo mkfs.vfat -F 32 -n PIBOOT /dev/sdX1
sudo mkfs.exfat -n PIDATA /dev/sdX2
```

### macOS

```sh
diskutil list
diskutil partitionDisk /dev/diskN MBR \
  MS-DOS\ FAT32 PIBOOT 1G \
  ExFAT PIDATA R
```

> **Never pull the medium while a `save` is running.** An exFAT write that is
> interrupted leaves the volume marked dirty, and Anvil then refuses to write
> to it at all — correctly, because a volume that may be inconsistent is not
> one to write more into. It says so in those words, and the way back is a
> repair from a computer: `chkdsk X: /f` on Windows, `fsck.exfat` on Linux.
> An on-board repair is planned; until it exists this is the one failure that
> needs another machine.

Put these at the root of **partition 1**:

| File | Where it comes from |
|---|---|
| `START4.ELF` | Raspberry Pi firmware. **Not in this repository.** |
| `FIXUP4.DAT` | Its matching file. **Not in this repository.** |
| `BCM2711-RPI-4-B.DTB` | The device tree. **Not in this repository.** |
| `CONFIG.TXT` | [`config.txt`](config.txt) here, renamed. |
| `KERNEL8.IMG` | [`kernel8.img`](kernel8.img) here, renamed. |
| `SETTINGS.TXT` | Optional. [`SETTINGS.TXT.example`](SETTINGS.TXT.example), renamed and edited. |
| `ARMSTUB8.BIN` | Required custom EL3 entry stub, built separately. |

[`SHA256SUMS`](SHA256SUMS) is not copied to the volume; it is here so the
image can be checked before it goes anywhere.

> **There is no `bootcode.bin` on a Pi 4.** It boots its second stage from an
> onboard EEPROM. `bootcode.bin` is a Pi 3 file, and copying a Pi 3 boot set
> onto a Pi 4 volume will not work and will waste your afternoon.

> **Names on the volume are 8.3.** Anvil's own filesystem code writes short
> directory entries only and generates no long-name chains, so a file it writes
> is `KERNEL8.IMG`, `SETTINGS.TXT`, `CONFIG.BAK`. Anything you put there with a
> longer name will not be visible to the board the way you expect. The
> lower-case names in this folder are a Git convention; rename them in 8.3 as
> you copy.

## Where to get the firmware files

From the official **[Raspberry Pi firmware
repository](https://github.com/raspberrypi/firmware)**, under `boot/`:

- [`start4.elf`](https://github.com/raspberrypi/firmware/blob/master/boot/start4.elf)
- [`fixup4.dat`](https://github.com/raspberrypi/firmware/blob/master/boot/fixup4.dat)
- [`bcm2711-rpi-4-b.dtb`](https://github.com/raspberrypi/firmware/blob/master/boot/bcm2711-rpi-4-b.dtb)

They are **deliberately not copied into this repository.** They are
Raspberry Pi's files under Raspberry Pi's terms, and
[`docs/THIRD_PARTY_NOTICES.md`](../../../docs/THIRD_PARTY_NOTICES.md) does not
cover them — it cites the device-tree *source* (`bcm2711-rpi-4-b.dts`) as a
hardware reference, which is a different thing from shipping the compiled
binary. Anything this repository does redistribute is listed there with its
upstream path and hash. There is also no pinned Pi 4 firmware manifest here to
check a download against; the Pi 3 is the only target whose boot files are
pinned by hash.

Any recent firmware release works. If you already have a working Raspberry Pi
OS card, the three files are on its boot partition and can be copied straight
across.

### Does Anvil need the device tree?

Not for itself. Anvil's hardware knowledge is compiled in — the device tree was
read during development and the values it yielded are constants in the sources,
cited in the comments. Anvil parses no device tree at runtime.

It captures the pointer, though. The firmware loads the `.dtb` and passes its
address in `x0`; Anvil stores that in its very first instruction
(`RaspberryPi4/Board/hw_boot.pi4`) and keeps it, so that the `booti` command
can hand the firmware's own device tree to an arm64 Linux kernel later.
`booti` refuses if there is no device tree or if it does not start with the FDT
magic — it will not jump into memory it cannot identify.

So: include the `.dtb`. It is standard on every Pi 4 boot volume, and without
it the one command that needs it refuses.

## Wi-Fi, if you want it

Two more files, from this repository:

```text
Firmware/CYW43455/brcmfmac43455-sdio.bin       ->  BRCMFW.BIN
Firmware/CYW43455/brcmfmac43455-sdio.clm_blob  ->  BRCMCLM.BLB
```

A third, the NVRAM file, is **deliberately not bundled** because it may carry
board calibration and identity data. Supply a board-appropriate one as
`BRCMNV.TXT`. The radio firmware is separately licensed and is **not MIT** —
see [`docs/LICENSING.md`](../../../docs/LICENSING.md) and
[`Firmware/CYW43455/README.txt`](../../../Firmware/CYW43455/README.txt) for the
redistribution terms on all three.

[`SHA256SUMS`](SHA256SUMS) here checksums both radio firmware files above,
alongside the monitor image, the stub and the config, so `sha256sum -c
SHA256SUMS` verifies everything this repository ships for the medium in one
command (forum 926). `BRCMNV.TXT` has no line of its own — it is
board-specific and not part of this repository, so there is nothing to pin a
hash against.

Ethernet needs none of this. Nothing in the list above is required to reach the
board over a cable.

## The monitor image

`kernel8.img` here is **Anvil build 212** for the Raspberry Pi 4:

```text
4,200,128 bytes
sha256 d6d40968e176aba4d69501119d5a84c0f6d221763d7fbc3c4a285721c253294f
```

Verify it before you copy it:

```sh
sha256sum -c SHA256SUMS
```

which should answer `kernel8.img: OK`.

A rebuild will not reproduce these bytes. The build number is stamped into the
image and [every build raises it](../../../docs/BUILD_NUMBER.md), so your own
build is 213 or later and differs there. The hash identifies this package's
image; use the manifest to verify the matching stub and configuration too.

> **Keep a way back before you replace a working image.** Put a known-good
> image on the medium under its own name and know the command that restores it:
> `load SCALEOK.IMG 800000`, `save KERNEL8.IMG 800000 <length-in-hex>`, `reset`.
> `save` takes an address and a **length**, not an end address.

## If a boot fails, send this

Every boot records the steps of its configuration half - the PCI Express and USB
host bring-up, each SCSI command to the USB stick and what came back, each block
read, the filesystem mount - with the millisecond each happened, in memory that a
reset does not erase. `trail` prints them: `TRAIL 0` lines are this boot,
`TRAIL 1` lines are the boot before it.

A boot that STOPS in that half is reset once by a 15-second watchdog, and the
boot after it prints, before USB starts, on the screen and the serial line:

```text
!! THE PREVIOUS BOOT STOPPED. Its last steps, the final one being where:
```

followed by those steps. When that happens, or whenever a boot does not reach
`pmf>`, please send:

1. the `!! THE PREVIOUS BOOT STOPPED` line and the lines under it (a photo of
   the screen is fine);
2. the output of `trail` typed at the prompt of the boot that did come up;
3. `version`, and what is plugged into the USB ports.

A boot that is merely slow is not reset: every USB wait is at most five seconds
and records a step as it starts, so the watchdog only fires when nothing at all
has happened for 15 seconds. It is never armed on the boot straight after a
stopped one, so it can cost at most one extra reset, never a board that resets
over and over. A power cut clears the record.

## First boot

Wire a **3.3 V** USB-to-serial adapter to three consecutive pins on the
even-numbered header row:

```text
adapter GND  ->  pin 6    GND
adapter RX   ->  pin 8    GPIO14 / TXD0
adapter TX   ->  pin 10   GPIO15 / RXD0
```

**115200 baud, 8 data bits, no parity, one stop bit, no flow control.** RX and
TX cross: the adapter's receive takes the Pi's transmit.

> **Leave the adapter's VCC disconnected.** The Pi powers itself. Back-feeding
> 5 V onto the header is how boards die. Never attach an RS-232 voltage-level
> port directly to these pins.

Power the board. Anvil prints its banner, then one line per thing it starts —
so if it hangs, the last line printed is the thing that hung, and that is
usually the whole diagnosis. Then `pmf>`.

Two commands first:

```text
pmf> version        which image is this, and how big
pmf> map            what memory is mine
```

Read `map` before staging anything anywhere. Every host tool that writes to the
board parses a validated `map` response from the running monitor rather than
carrying a staging address of its own. Do not copy an address out of an
example, a previous build, or this file.

## The network console

The monitor listens on **UDP port 5555** as soon as it holds an address, on
whichever interface has one — and on more than one at once if more than one
has an address. Whoever sends it a datagram becomes the peer: everything the
monitor prints comes back as UDP, and every line sent is fed into its command
input, exactly like the serial console.

```sh
python3 ../../../tools/anvil_wifi.py --find          # broadcast; who answers
python3 ../../../tools/anvil_wifi.py <board-ip>      # interactive
python3 ../../../tools/anvil_wifi.py <board-ip> "info"
```

> A Pi 4 on a bare Ethernet cable into a laptop answers its console after a
> reset with **nothing typed on the board and nothing changed on the laptop**.
> No DHCP server, no connection sharing, no static address, no firewall rule.
> Both ends take a link-local address the way the standard says to, and the
> board's is seeded from its hardware address — so it is the same one across
> flashes.

The tool is called `anvil_wifi.py` for historical reasons and the name is kept
so older notes still work. It is the network console: same port, same
datagrams, over either link.

### Running something on it

```sh
python3 ../../../tools/board_run.py payload.pmf --console-ip <board-ip>
```

One run is: ask the board where to stage (`map`), stream the container, **prove
it landed** by comparing the board's own SHA-256 of its memory against the file
on disk, arm the deadman, `boot mem <addr> shot`, wait for the return value,
and read the picture back. It writes `<name>.png`, `<name>.json` and
`<name>.txt`, and exits non-zero if the payload did not return zero or if no
picture came back. See [`docs/BOARD_RUN.md`](../../../docs/BOARD_RUN.md).

The other host tools are in [`tools/`](../../../tools/):
`pi4_upload.py` for bulk transfers with a hash verdict, `anvil_putfile.py` to
put a file on the boot medium with a read-back check, `anvil_update.py` to
replace the monitor itself, `pmfshot.py` for a screenshot over the serial line.

> Do not run `python tools/anvil.py --help`. It has no argument parser and
> constructs its serial driver for any argument, so `--help` opens the serial
> port. A bare `python tools/anvil.py` is safe and prints the usage.

## SETTINGS.TXT

Optional, and the board boots to a prompt without it — a missing file is
explicitly not a fault, and the console says so in those words. Every setting
has a defined behaviour when absent. The easiest way to get one is to type what
you want at the prompt and then `settings save`, which writes it to the boot
medium.

[`SETTINGS.TXT.example`](SETTINGS.TXT.example) is a commented tour of every key
that has code behind it. Rename it `SETTINGS.TXT` and delete what you do not
want.

```text
key=value        one to a line; the FIRST '=' splits
keys             lower case, a-z 0-9 . - _ , at most 31 bytes
values           printable ASCII, at most 95 bytes, no leading or
                 trailing space (a refusal, not a trim)
# or ;           a comment line
```

At most 32 keys and 6144 bytes. A bad line **stops** the load, names its line
number, and blocks the next save until you type `settings discard` — because a
save rewrites the whole file from the table in memory, and saving a half-read
table would silently delete every line below the bad one.

> **`settings save` does not keep your comments.** It rewrites the file from
> memory, so the first save replaces anything you hand-wrote with Anvil's own
> banner. That is why the example lives here beside the source rather than
> being the file itself.

The monitor attempts to read `SETTINGS.TXT` during boot after storage starts.
If the file is missing, the board continues with defaults; if it is malformed,
the load reports the refusal and blocks accidental overwrite. After editing
the file on a computer, type `settings load` to reload it without resetting.

The keys, by group: `net.address` / `netmask` / `gateway` / `server` / `dns`;
`wifi.N.ssid` and `wifi.N.password.plaintext` for slots 1–4, where the slot
number is the order they are tried in; `clock.utc`, `clock.zone`,
`ntp.server`; `boot.file`, `boot.delay`, `boot.maxfails`, `boot.fails`;
`fan.pin`, `fan.mode`, `fan.lowF`, `fan.highF`, `fan.hystF`, `fan.hz`;
`screen.rotate`, `screen.scale`, `touch.axes`.

> **A Wi-Fi passphrase is stored in plain text**, deliberately: the radio needs
> the passphrase itself, and hiding it on a medium whose reader also holds the
> key would only look like protection. Anyone who can plug the card into a
> computer can read it. Anvil also caches the derived key as `wifi.N.pmk.secret`
> after a successful handshake, to skip a ten-second derivation at the next
> boot — that value joins the network just as well as the passphrase does, so
> never copy one between boards or into a file you share. Any key whose name
> contains `password`, `passphrase` or `secret` is masked in `settings` output,
> because that output also goes to the screen and into the next screenshot
> anybody takes; `settings reveal <name>` is the deliberate keystroke that puts
> one in the clear.

## The required EL3 stub

`ARMSTUB8.BIN` is required. It keeps the monitor at EL3, and the monitor refuses
the stock firmware's EL2 entry. It is 512 bytes, a source translation of
Raspberry Pi's own stub pinned to a named upstream commit, and it keeps its
upstream BSD-3-Clause notice. The package contains this stub and its hash is in
`SHA256SUMS`.

> **A monitor watchdog cannot repair a bad firmware-stage stub.** If the board
> fails before Anvil starts, nothing on the board can help you and you are
> restoring files from a host. Keep physical access to the medium and a known
> good copy of the image, stub, and configuration before updating.

Copy the monitor, stub, and `CONFIG.TXT` from one verified package. Keep the
firmware files provided for this board. Verify the package with
`sha256sum -c SHA256SUMS`; ensure the config contains `armstub=armstub8.bin`.
Do not test the new monitor at EL2 first: Anvil refuses that entry level. If
boot fails before the prompt, restore the complete known-good image, stub, and
configuration from the host. Removing the stub directive is not an Anvil
fallback.

## More

- [Chapter 3 of the Anvil Guide](../../../docs/guide/03_installing_on_a_pi4.txt)
  — the long version of this page, with the reasons.
- [Chapter 4](../../../docs/guide/04_the_console.txt) — every console command.
- [Chapter 6](../../../docs/guide/06_running_from_the_host.txt) — running
  payloads from a host machine.
- [Chapter 8](../../../docs/guide/08_updating_the_monitor.txt) — replacing the
  monitor in place, and the two points after which you must not reset.
- [The whole book as a PDF](../../../docs/guide/AnvilGuide.pdf).
