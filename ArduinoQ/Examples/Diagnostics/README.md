# ArduinoQ diagnostics - in-house instruments. NEVER SHIPPED.

Everything in this directory exists to prove OUR code is correct on the
Arduino UNO Q. None of it is a how-to and none of it goes in a release
(rule 19). `tools/stage_release.py`'s `copy()` refuses any path with a
`Diagnostics` segment, and the finished stage is swept again afterwards, so
the guard and the proof the guard worked are not the same line of code. This
README is inside that segment too, which is why the internal detail below can
live here and not in `../README.md`.

| File | What it proves |
|---|---|
| `anvilqprobe.unoq` | **first light.** A PureMetal-built A64 image executing on the UNO Q's Cortex-A53, launched by the board's own UEFI firmware. Validates the EFI SystemTable, records `MIDR_EL1`, `CNTFRQ_EL0`, `CurrentEL` and two `CNTPCT_EL0` reads into a non-volatile UEFI variable, then cold-resets back to Debian |
| `NotBuilding/anvilqcoreproof.unoq` | **the Anvil portable core computes correctly on the A53.** `Anvil/Core/crc.pbi`'s crc32 over the fixed 4096-byte pattern gives `0x399208A7` on the board, matching the host-computed value. Also re-confirms the memmap predictions in `ArduinoQ/Board/memmap_q.unoq` |

## Where these came from

Both moved here from `ArduinoQ/Board/` on 2026-09-02. They were never how-tos;
they sat beside the HAL backends because that is where the bring-up worker was
standing. Their includes were already root-relative
(`XIncludeFile "ArduinoQ/Board/memmap_q.unoq"`, `"Anvil/Core/crc.pbi"`), so the
extra directory level cost them nothing - which is the whole reason rule 19
requires that spelling.

## Building and running them

```
bash tools/build_unoq_probe.sh          # -> anvilqprobe.efi
bash tools/build_unoq_coreproof.sh      # -> anvilqcoreproof.efi
bash tools/deploy_unoq_coreproof.sh     # stage on the ESP, one-shot boot, reset back
python tools/read_anvil_proof.py        # decode anvilqprobe's UEFI variable
python tools/read_qcore_proof.py        # decode anvilqcoreproof's, PASS/FAIL verdict
```

The build is `PureMetalForge.exe --compile -t unoq` -> a flat position-independent A64 image ->
`tools/unoq_efi_wrap.py` -> a PE/COFF AArch64 `EFI_APPLICATION`. The `.img`
and `.efi` are build output, written under `build/unoq/diagnostics/`, which is
gitignored; regenerate them, do not commit them.

Most of the probes that used to live here are in `NotBuilding/`: they include
libraries Anvil main does not carry, and `NotBuilding/README.md` names them.
`anvilqcoreproof` is one of them, so its build script fails today.

The board is reached over SSH as `arduino@<ip>` with the key recorded in the
vault (`CompilerEmbedded/Arduino UNO Q/SSH access to the Arduino Q.md`). **No
key and no password is stored in this repo.**

Defects found here are filed on the forum in **Arduino UNO Q bugs**,
category 114.
