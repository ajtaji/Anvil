# UNO Q UEFI application package

`anvil.efi` is an experimental AArch64 UEFI application, not a complete
standalone boot image. Copy it to `/EFI/anvil/anvil.efi` on an ESP only when a
compatible UEFI environment is already available to launch it. The current
application enters at EL1, below Anvil's mandatory EL3 runtime policy; EL3
entry and physical acceptance remain pending.

Verify the artifact with `sha256sum -c SHA256SUMS`. `BUILD-MANIFEST.json`
records the build identity and PE/COFF validation result.
