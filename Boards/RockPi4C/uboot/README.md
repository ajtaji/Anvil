# ROCK Pi 4C U-Boot image package

`Image` is an experimental flat Anvil image for an external U-Boot stage. It
does not boot the board by itself. Load it through a compatible U-Boot
configuration; the current board entry requires EL2 and therefore remains
below Anvil's mandatory EL3 runtime policy. EL3 entry is pending and no
exception is approved.

Verify the artifact with `sha256sum -c SHA256SUMS`. `BUILD-MANIFEST.json`
records the current build identity and image hash. Hardware results for older
builds do not establish validation of this artifact.
