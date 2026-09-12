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
The immutable loader first stops/adopts reset residue before SD mount or its
recovery wait. WRCFG bits are configuration, not a foreign-active-owner test;
arming replaces them with the documented read-modify-write. The trial updater
does not call the cold-stop path. Serial milestones `L0` through `L6` name the
watchdog, first verify, TRIED write/readback, reverify, copy, handoff and branch
boundaries. Alternating status-LED states preserve a coarse last boundary if
serial is lost. `C0: candidate Main entered` is the candidate's first
source-level action, before SD context, mailbox, mount or confirmation work.
No RSTS/firmware partition-selection writes are made. There is no unlimited
watchdog feeding; reaching the health point within 15 seconds for a maximum
size slot, and actual firmware watchdog recovery, remain silicon gates.

This protection is first-stage behavior. An ordinary A/B monitor update cannot
repair an older `kernel8.img` whose watchdog begins after slot loading. The new
loader must pass the desk gates and then be installed through the explicit
card provisioning/replacement path while preserving both confirmed slots and
control records. The already deployed loader remains immutable until that
separate, user-authorized replacement.

## Composition and memory

`pi3-loader` builds immutable `build/pi3/kernel8.img` from `loader.pi3`.
Source directives own load `0x80000`, BSS `0x180000`, stack `0x200000`.
Image end must be at most `0x180000`, BSS end at most `0x1F0000`, leaving
at least 64 KiB downward stack space. `pi3-updater` builds `anvil.img` and
its compiler `.pmf` sidecar with the slot layout above. This is the autonomous
serial and Ethernet update monitor, not a claim of complete Pi3
networking/Anvil services.
`pi3` and explicit `pi3-diagnostic` retain the earlier diagnostic source.
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
python tools/pi3_update.py build/pi3/anvil-slot.img --port COM7 --reboot
```

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
python tools/fat_shared_equivalence_check.py --compiler <PureMetalForge.exe>
python tools/fat_readat_emitted_check.py --compiler <PureMetalForge.exe>
```

At this checkpoint SDHOST passes 149 checks; updater passes 189 checks including
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
Compiler SHA256:
`36b322210c55af58d37305d905394d52d741299604bf17e7712d0eee8fe4bc07`.

Updater execution uses actual emitted FAT, CRC and transaction code with a
sparse sector device. SHA is an explicitly substituted host reference dependency
in that gate, not claimed native SHA execution. SDHOST execution uses modeled
MMIO and card responses, not electrical/timing proof. The integrated real
SDHOST/FAT/SHA/transport fixture also compiles, but is never run on hardware.

No Ethernet updater image was flashed at this checkpoint. Silicon acceptance
still needs LAN9514 enumeration/link, DHCP acquisition, a read-only STATUS
exchange, identification/capacity agreement, read-only
filesystem inspection, an explicitly designated inactive-slot write/readback,
power-interruption recovery and candidate confirmation. Card internal FTL
behavior and power-loss durability cannot be established by these desk models.
No tool may auto-select or format a physical disk.
