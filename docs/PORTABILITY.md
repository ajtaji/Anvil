# Portability and build contract

## Include resolution

All source includes are repository-root-relative and use forward slashes, for
example:

```text
XIncludeFile "Anvil/Core/state.pbi"
```

`tools/build.py` sets `PMF_ROOT` to the checkout root. With that pin active,
the compiler searches only this tree. A missing file therefore fails the build
instead of being satisfied by a copy beside the compiler or in another working
directory.

The current compiler has one exception: it discovers `Boards/*.board` beside
its own executable. The build wrapper therefore makes an ephemeral copy of the
external compiler and places this repository's `Boards/` directory beside that
copy. The temporary directory is removed when the build ends. This keeps the
board profile explicit without checking in a private compiler binary.

`PROVENANCE.json` preserves the exact recursive closure copied for each board
during the initial migration. Those historical counts are not current release
limits. `tools/verify_export.py` recalculates both closures from the selected
Git tree and requires every resolved include to be tracked.

## Extension choices

- `.pbi`: neutral shared include; no target is inferred.
- `.pi4`: Raspberry Pi 4 source.
- `.unoq`: Arduino UNO Q source; the command-line compiler already selects
  `QCM2290`/`unoq` from this extension.

The current desktop IDE does not list `.unoq` as a source type or default save
extension, even though the command-line target contract recognizes it. The
compiler's cross-chip include guard also does not classify UNO Q source yet.
Those are narrow compiler-integration gaps outside this repository. Builds here
must use the command-line compiler with an explicit `-t` as the build wrapper
does.

The advertised generic `.avrb` spelling is not used for the shared AArch64
core: its include classification currently treats it as classic AVR. `.pbi`
avoids that mismatch without requiring a compiler change.

## External dependencies

- The PureMetal application (`PureMetalForge.exe`, or `PureMetalForge.linux`
  on Linux) in command-line mode, supplied separately. The editor and the
  compiler are one program; `--compile` selects a build with no window.
- Python 3 for the host build and verification scripts (standard library only).
- UNO Q UEFI wrapping uses `tools/unoq_efi_wrap.py` (standard library only).
- Emitted AArch64 development gates additionally require the independently
  supplied interpreter named by `PMF_A64_INTERP`, unless the documented
  repository-local interpreter is present.

The repository does not contain the private compiler implementation or a
compiler executable.

## Shipped guest runtime closure

Current Forge injects `Shared/A64/string.pmi` when an AArch64 program uses
string expressions. Because `PMF_ROOT` deliberately forbids a fallback outside
this checkout, that shipped guest library is included here and required by the
export manifest. Its origin revision and digest are recorded in
`PROVENANCE.json`. This is runtime source for the guest, not a second compiler
or private compiler implementation. `.pmi` files receive the same public-source
boundary and hygiene checks as `.pbi` files.


The Zentaji console also explicitly includes `Shared/A64/string_out.pmi`, the
existing pure-source 64-bit integer/text output library, with its exact shipped
bytes preserved. Its historical folder name does not impose an ARM ABI: it
calls the composition's PrintChar procedure and contains no assembly or register
access. PROVENANCE records the source revision/hash and requires the file, so
PMF_ROOT can keep all guest runtime resolution inside the standalone checkout.


## Clock provenance across architectures

`Anvil/Core/wallclock.pbi` uses only the monotonic `Ticks()`/`TickHz()` seam.
Hardware RTC provenance is admitted by a board through `WallClockRtcAdmit(1)`
after validating its provider. It starts disabled and can be revoked with 0;
revocation removes RTC trust without erasing the inspected anchor. Its HAL UTC
record is withheld and zeroed until re-admission. The Pi5
backend performs registration after its range/floor checks. Shared clock policy
does not require `#PMF_CHIP`, and a new architecture must not impersonate an ARM
chip to include it. This registration is a provider contract, not a hardware
probe or automatic assertion that a virtual RTC holds correct civil time.


## Shared command vocabulary

Storage command names and aliases are dispatched by `DispatchStorageCommand()`
in the shared `Anvil/Core/fs_cmd.pbi`, after the caller establishes the ordinary
parsed word state. Pi4, Pi3, Arduino Q and the Zentaji command composition use
that procedure; board loops continue to own their other command families and
startup. A new architecture supplies memory/storage seams and reuses the shared
handlers rather than copying the word chain or filesystem logic. Rock Pi's
separate recovery-console composition has not been migrated by this change.
