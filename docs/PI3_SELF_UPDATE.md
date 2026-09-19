# Pi 3 SD update: card-stays-in-board development

The target is BCM2837 AArch64. Firmware continues loading `kernel8.img` at
`0x80000`. The existing diagnostic entry remains separate. The permanent
first-stage loader and replaceable updater are built and checked on the desk.
One explicit provisioning pass installs them on an already prepared Pi boot
volume. After that, ordinary Anvil images can travel over the Pi 3 PL011
serial link or the LAN9514 Ethernet port; the card stays in the board. Both
transports enter the same storage, hash and A/B transaction boundary.

## Storage boundary

`RaspberryPi3/Lib/sdhost.pbi` owns the BCM2835 SDHOST at `0x3F202000`.
It does not alias the Pi 4 EMMC2 controller. Original implementation, with
register/transaction behavior checked against the pinned
[Linux v6.12 BCM2835 SDHOST driver](https://github.com/torvalds/linux/blob/v6.12/drivers/mmc/host/bcm2835.c).
No Linux source code was copied into this MIT implementation.

Only SD v2 high-capacity cards are admitted. Identification and transfer waits
have both counter deadlines and finite iteration ceilings. Errors invalidate
the controller's ready state; there is no silent retry or guessed capacity.
PIO transfers are single 512-byte blocks. Every buffer, card LBA, and write
window is checked before controller mutation. The write window starts disabled.

### CSD response order is controller-specific

Linux v6.12 reads the four long-response registers as
`resp[3-i] = SDRSP0[i]`. Consequently SDRSP3 contains CSD bits 127..96,
SDRSP2 bits 95..64, SDRSP1 bits 63..32 and SDRSP0 bits 31..0. This is not
the shifted SDHCI response representation. For CSD v2, bits 127..126 must
equal one, and `C_SIZE = ((SDRSP2 & 0x3f) << 16) | (SDRSP1 >> 16)`.
Capacity in 512-byte blocks is `(C_SIZE + 1) * 1024`.

The emitted SDHOST test uses both a small capacity and `C_SIZE=0x123456`,
which crosses the response-register boundary, plus an invalid-version case.
Write tests refuse both the card-capacity endpoint and either side of the
mounted FAT data window before any MMIO write.

## Shared FAT ownership

`Anvil/Storage/fat32.pbi` is the byte-preserving move of the existing FAT
implementation. `RaspberryPi4/Lib/fat.pi4` remains a compatibility include.
The updater uses FAT only to mount and resolve preallocated extents. It does
not create, truncate, rename, delete, allocate clusters, or update FAT metadata.

The required files are `ANVILA.BIN`, `ANVILB.BIN`, `P3CTRLA.BIN`,
`P3CTRLB.BIN`, and immutable `KERNEL8.IMG`. Slot capacities are equal and
sector aligned. Control files are one sector. Every chain must be contiguous,
end exactly where expected, lie within the partition data area, and be disjoint
from every other owned file and every root-directory cluster. The block driver's
independent write fence is capped at reported card capacity. This is not a
general-purpose writable filesystem service.

The cold loader performs an iterative ownership walk of the complete directory
tree, including files below `overlays/`. Every foreign file and directory
cluster is checked against all five owned extents. Regular-file chains must end
exactly at the cluster implied by file size; directory FAT loops, shared
directory metadata, graph cycles, malformed or missing `.`/`..` links, and
duplicate owned root names are refused. There is no recursion or allocation:
fixed BSS holds at most 256 directories and 8192 directory clusters, with depth
8, 16384 occupied directory slots, 4096 directory sectors, and 65536 total
foreign chain hops as independent hard limits. A refusal occurs while the block
writer and write window are still disabled.

## Container and boot transaction

Raw blobs are refused. `P3SLOT` version 1 is a 128-byte little-endian wrapper
around the compiler's 128-byte `PMFBOOT` version 2 header and image:

| Offset | Field |
|---|---|
| 0 | Eight bytes `P3SLOT` followed by two NULs |
| 8, 12 | u32 version 1, wrapper length 128 |
| 16, 20 | u32 target 2837, ISA 64 |
| 24 | u64 stack top `0x1F00000` |
| 32 | u64 complete PMF header+image length |
| 40 | 32-byte SHA256 of complete PMF |
| 72..127 | Zero |

Inner PMF load/entry must both be `0x200000`, its image must end before
`0x1000000`, BSS must start at `0x1100000` and end by `0x1E00000`.
The PMF extension must identify AArch64, target BCM2837 (`2837`), stack top
`0x1F00000`, and contain only zero reserved bytes.
Flags and reserved word are zero: nonreturning, no service-table dependency.
The Pi3 wrapper defines DTB handoff; the current compiler does not emit the
reserved PMF DTB flag. Inner image SHA and wrapper PMF SHA are both required.
Metadata and hashes establish integrity/compatibility, not code authenticity
or a guarantee that an arbitrary correctly labeled program cannot hang.

Control records are version 2: magic u32 `0x42413350` at 0, version at 4,
generation u64 at 8, container length u64 at 16, slot u32 at 24, fixed load
u32 at 28, complete-container SHA256 at 32, state u32 at 64, CRC32 of bytes
0..507 at 508. States are PENDING=1, TRIED=2, CONFIRMED=3.

Mount selects a hash/structure-valid confirmed baseline. Commit writes and
verifies only the other slot, then publishes it PENDING. Loader writes and
reads back TRIED before any trial branch. A subsequent boot skips unconfirmed
TRIED and selects the confirmed baseline. Confirmation only follows successful
SD mount and serial prompt output, and identifies the running slot/generation
from the loader's CRC-protected handoff at `0x1FF0000`. It never guesses the
newest record. That handoff is consumed once. Both-invalid volumes stop rather
than inventing a blank initial state.

The running updater uses `Pi3UpdateMountHandoff`, not the cold loader's full
hashing/tree-walk mount. It rechecks the exact mapped extents and
TRIED/CONFIRMED record against the loader's immediately prior verified identity,
then confirms without rereading the nested tree or payload sectors under the
15-second watchdog. The handoff is version 2, 128 bytes: slot at 12,
generation at 16, DTB at 24, record state at 32, container length at 40, record
SHA at 48, CRC32 of bytes 0..123 at 124. This is a trusted-loader handoff, not
an authentication mechanism for hostile code. The maximum-size gate admits
14 MiB slot metadata and confirms with zero SHA calls and zero payload-sector
reads; normal cold mount retains complete hash/structure verification.

The loader offers a three-second U recovery / F fallback window. U runs the
serial updater without booting the pending slot. F selects the explicit
confirmed baseline when a pending candidate exists, or an older confirmed
slot for an ordinary confirmed boot; absence of a fallback is a refusal.
Commit never resets automatically.
The separate ASCII command is exactly `reset`. It refuses while receiving or
while storage/confirmation state is uncertain. A successful request prints
`resetting` plus CRLF, drains PL011 BUSY, then requests a ten-tick full watchdog
reset. If UART output/drain fails, no reset is requested. Reaching code after
the bounded reset wait prints an explicit failure rather than claiming reboot.

After its bounded recovery menu, the immutable loader arms one 15-second
BCM2835 PM watchdog before the selected-slot load. It does not feed or restart that timer while it
verifies the slot, writes and reads back TRIED, reverifies, copies, writes the
handoff or branches. The updater disarms it only after confirmation.
Register/password/reset semantics
are checked against the pinned
[Linux v6.12 watchdog driver](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/bcm2835_wdt.c)
and [U-Boot v2025.01](https://github.com/u-boot/u-boot/blob/v2025.01/drivers/watchdog/bcm2835_wdt.c).
The immutable loader first stops/adopts reset residue. It then arms a separate,
never-fed 15-second early-storage watchdog before the firmware maximum-core-
clock request, native SDHOST initialization and cold A/B mount. Milestones
`E0` through `E6` distinguish arm, clock request/reply, SDHOST entry/ready,
mount and positive stop. An explicitly returned failure stops that early timer
and remains parked for diagnosis; a genuinely wedged call is reset by it. The
timer is positively stopped before the three-second U/F recovery window, and
the independent 15-second trial window is armed afterward. This closes the
pre-watchdog hang reproduced by deployed loader build 7 and recorded in forum
topic 788 without feeding either timer or weakening the A/B state rules.

WRCFG bits are configuration, not a foreign-active-owner test; arming replaces
them with the documented read-modify-write. The trial updater does not call
the cold-stop or early-arm paths. Serial milestones `L0` through `L6` name the
trial watchdog, first verify, TRIED write/readback, reverify, copy, handoff and
branch boundaries. Alternating status-LED states preserve a coarse last
boundary if serial is lost. `C0: candidate Main entered` is the candidate's first
source-level action, before SD context, mailbox, mount or confirmation work.
No RSTS/firmware partition-selection writes are made. There is no unlimited
watchdog feeding; reaching the health point within 15 seconds for a maximum
size slot, and actual firmware watchdog recovery, remain silicon gates.

This protection is first-stage behavior. An ordinary A/B monitor update cannot
repair an older `kernel8.img` whose watchdog begins after slot loading, and
neither transport can reach the first-stage image at all, so the card has to
come out of the board. The new loader must pass the desk gates and then be
installed by the loader-only replacement below, which writes that one file and
proves both slot images and both control records are byte-identical afterwards.
Provisioning is the wrong tool for this: it recreates both slots and both
control records and restarts the generation count at 1, which throws away
whichever slot is currently confirmed. The already deployed loader remains
immutable until that separate, user-authorized replacement.

## Composition and memory

`pi3-loader` builds immutable `build/pi3/kernel8.img` from `loader.pi3`.
Source directives own load `0x80000`, BSS `0x180000`, stack `0x200000`.
Image end must be at most `0x180000`, BSS end at most `0x1F0000`, leaving
at least 64 KiB downward stack space. `pi3-updater` builds `anvil.img` and
its compiler `.pmf` sidecar with the slot layout above. This is the autonomous
serial and Ethernet update monitor, not a claim of complete Pi3
networking/Anvil services.
`pi3` builds all three of this board's programs; `pi3-monitor` is the
monitor alone, and it replaced `pi3-diagnostic` on 2026-09-18 when
`board.pi3` stopped being a parked cold-entry diagnostic and became the
composition.
Each real loader/updater build has its own central build counter.

Firmware ARM RAM must cover the fixed arenas. The DTB remains at 16 MiB,
handoff page below 32 MiB, staging is 32..46 MiB. `boot_memory.pbi` checks
the DTB reservation map and fixed reserved-memory child ranges before use,
following the [DTSpec flattened format](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html).
Malformed/overlapping reservations refuse boot. Dynamic reserved-memory
requests without a fixed reg are not allocated by this boot environment.
Only the immutable loader allocates the initial framebuffer; the serial
updater does not allocate a second framebuffer or claim display adoption.

## Build, provision and update

Build both source-owned images with the same PureMetal Forge application used
as the IDE:

```
python tools/build.py pi3 --compiler <PureMetalForge.exe>
```

The one-time, deliberately explicit card operation is:

```
python tools/pi3_provision.py --card-root X:\ --loader build/pi3/kernel8.img --loader-pmf build/pi3/kernel8.img.pmf --monitor build/pi3/anvil-slot.img --yes-replace-kernel8
```

The tool never discovers, selects, partitions or formats a disk. `X:\` must be
the already mounted Pi boot volume. It proves the pinned firmware set, exact
`config.txt`, loader PMF target/placement/stack and raw-image identity before
replacing exact named files. Normal later updates use:

```
python tools/pi3_update.py build/pi3/anvil-slot.img --port <the board's port> --reboot
```

The port is whichever COM number the board's USB serial adapter enumerates as
on the host, and it moves when the adapter is replugged or the host changes;
it is COM30 on the current bench and was COM7 when this file was first written.
Omit `--port` only when exactly one serial port is present.

Replacing the first-stage loader is a separate operation, and the only one that
needs the card in a computer. It writes exactly one file:

```
python tools/pi3_loader_replace.py --card-root X:\ --loader build/pi3/kernel8.img --backup <a new file on the PC> --yes-replace-kernel8
```

It refuses a directory that is not the prepared boot volume, a card whose A/B
slot layout is not the one the loader expects, a sidecar that does not describe
the loader, and a backup path that already exists. It keeps the outgoing loader
at `--backup` before writing anything, reads the replacement back off the
medium and compares its hash, then re-hashes every slot image, control record
and firmware file and fails if any of them moved. Replacing a loader with
itself writes nothing.

Once the monitor prints the DHCP address and UDP port 5556, Ethernet updates
use the same validated `P3SLOT` file:

```
python tools/pi3_net_update.py build/pi3/anvil-slot.img --host <pi3-address> --reboot
```

The host address is explicit and the board obtains its address by DHCP; no
laptop subnet or old board address is compiled in. The host tool binds every
request to a fresh random session and the board binds that session to the
sender IP and UDP port. Lost BEGIN, DATA and COMMIT replies are replay-safe.
This protects transaction ownership and stale datagrams but is not
authentication against a hostile machine on the same LAN. Do not expose UDP
5556 outside a trusted development network.

Omit `--reboot` to stage and commit without resetting immediately. A failed
trial is recovered by the immutable loader's watchdog and confirmed fallback;
hold `U` during its three-second window for the serial recovery monitor or `F`
for a one-shot confirmed fallback.

### The window comes before storage

The three-second window is offered as soon as the port, the processor state and
memory are up, and **before anything reads the card**. It used to be printed
only after the cold mount returned, which meant a card the mount could not get
through locked the board out completely: thirteen consecutive boots were
observed resetting inside the mount and the recovery line never appeared once.
The choice needs no storage, so it no longer waits for any.

`U` therefore serves the prompt with the card **not mounted**, and says so on
the screen as well as the port. `mount` then brings storage up as an explicit
command, with the early watchdog and the E0-E6 markers exactly as the normal
path runs them, so a slow or damaged card fails where somebody asked for it and
is watching rather than as silence during boot. After a successful `mount` the
accepted serial A/B update path works exactly as before.

### An early fault says what it was

The boot chain installs the shared primary-core exception vectors before it
validates memory, allocates a framebuffer or touches storage - it does not carry
a second set of vectors of its own. Until it did, there was no vector base
register write anywhere in this tree, so a synchronous abort and a wedged
peripheral were the same silence on the wire, and one of them was chased for a
week. A fault now prints its vector slot, ESR, ELR, FAR, SPSR and SP on the
PL011 as a sentence that says what those mean, then stops. The reporter writes
only to the port, never through the framebuffer path, because the framebuffer
may be exactly what faulted.

## Reproducible desk gates

Run from the repository root, using the installed unified IDE executable:

```
python tools/pi3_sdhost_check.py --compiler <PureMetalForge.exe>
python tools/pi3_update_check.py --compiler <PureMetalForge.exe>
python tools/pi3_update_boot_check.py --compiler <PureMetalForge.exe>
python tools/pi3_loader_window_check.py --compiler <PureMetalForge.exe>
python tools/pi3_update_transport_check.py --compiler <PureMetalForge.exe>
python tools/pi3_net_update_host_check.py
python tools/pi3_ethernet_update_check.py --image <compiled-updater.img>
python tools/pi3_lan9514_transport_check.py
python tools/pi3_lan9514_runtime_check.py
python tools/pi3_usb_enumeration_check.py
python tools/pi3_reset_check.py --compiler <PureMetalForge.exe>
python tools/pi3_drain_host_check.py
python tools/pi3_update_layout_check.py
python tools/pi3_loader_replace_check.py
python tools/pi3_build_count_check.py
python tools/pi3_usb_diagnostic_check.py --image <compiled-updater.img>
python tools/fat_shared_equivalence_check.py --compiler <PureMetalForge.exe>
python tools/fat_readat_emitted_check.py --compiler <PureMetalForge.exe>
```

At this checkpoint SDHOST passes 547 checks, twelve of them refusals and one a
mutant that removes the ranged writer's window pre-check and is required to go
red; updater passes 189 checks including
cut/tear, trial/confirmation, malformed containers, root and nested cross-links,
directory graph/FAT cycles, exact chain lengths, dot links, depth and handoff;
boot admission/watchdog passes 30 checks. The receive/framing gate executes
eleven success/replay/FIN/failure cases, and reset ordering passes five cases.
The exact drain procedure also runs natively under PureBasic with a frozen
timer through all 2,000,000 polling iterations, then quarantines RX. Partial
header failures drain too. If no quiet interval can be proved, the command
loop stops instead of treating residual binary bytes as commands.
The layout gate executes actual cold
startup to Main and verifies stack, DTB preservation, BSS initialization and
PMF placement for both counted images. Shared FAT emits byte-identical
29,672-byte fixture images against the pinned pre-extraction commit;
the existing FAT read-at gate passes 19 cases and rejects three mutants.
The Ethernet host framing/retry gate passes 11 cases and the emitted updater
gate passes 12 peer/session/A-B/replay cases. LAN9514 transport, runtime and
USB enumeration hostile gates all pass, including emitted AArch64 execution.
The loader watchdog gate passes 41 emitted register/state checks; the whole-
window gate executes four early-storage success/refusal paths and rejects nine
ordering/ownership mutants. The loader-only replacement gate passes 30 checks
over throwaway boot volumes, and the count gate additionally sweeps every Pi 3
tool that invokes the compiler and fails if one of them builds a board image
without raising its build number. The candidate diagnostic gate passes 16
emitted orchestration cases, including the one where the controller is already
owned by the boot-time network bring-up: the command reports the live
controller and leaves its one-shot unspent instead of entering a cold path it
cannot take. The candidate immutable loader is now build 12,
151,676 bytes, SHA-256
`16f50ce29eb1075e9326b00951b1e67ba9df97de53af61deab3670001ab775e9`;
its PMF is 151,804 bytes, SHA-256
`06cf63c94a97f32c8f20c81b655c6c74b01c4bf0f72dee6e168939de95f4f1a5`.
It was built from a clean export of the commit that carries it. It has not
replaced the deployed build-7 loader, which is the one silicon fault still
open: putting build 12 on the card is the only way to get the early storage
watchdog and the E0-E6 markers onto the boot path, and it needs the card in a
computer. The earlier build-9 candidate, 136,652 bytes SHA-256
`2ad3e750c3303d3f1ae38e250f25035b90c801cfe6d484e01b6dc56be3e7c70c`, is
superseded and must not be installed.
Compiler SHA256:
`5898e744e6e688528abb0e3f704404e52afe3a1967ac4c7ad1113b276b0c2194`.

Updater execution uses actual emitted FAT, CRC and transaction code with a
sparse sector device. SHA is an explicitly substituted host reference dependency
in that gate, not claimed native SHA execution. SDHOST execution uses modeled
MMIO and card responses, not electrical/timing proof. The integrated real
SDHOST/FAT/SHA/transport fixture also compiles, but is never run on hardware.

The build-12 Ethernet updater image has since been observed RUNNING on the
board as confirmed slot B generation 5, reached without anyone typing: it was
tried by the deployed loader, confirmed itself and cleared the pending
selection. That proves the A/B trial path and the monitor's own start-up, and
it proves nothing about Ethernet. There is no cable on this board at present,
so silicon acceptance of the network path still needs LAN9514 enumeration/link,
DHCP acquisition, a read-only STATUS exchange, identification/capacity
agreement, read-only filesystem inspection, an explicitly designated
inactive-slot write/readback, power-interruption recovery and candidate
confirmation. Card internal FTL
behavior and power-loss durability cannot be established by these desk models.
No tool may auto-select or format a physical disk.
