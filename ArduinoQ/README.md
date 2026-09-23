# Anvil on Arduino UNO Q

The UNO Q port is experimental and does not boot the board by itself. Its
current artifact is an AArch64 UEFI application at
[`Boards/ArduinoQ/uefi/anvil.efi`](../Boards/ArduinoQ/uefi/anvil.efi); it must
be launched by an existing compatible UEFI environment. The current entry is
EL1, below Anvil's required EL3 runtime level, so the port is not yet compliant
with the execution-level policy. No exception is approved. Preserve the
existing launch path while an EL3-capable boot path is developed.

Build with `python tools/build.py unoq`. The package manifest and `SHA256SUMS`
identify the current compiled application; they do not establish standalone
boot or EL3 hardware acceptance.
