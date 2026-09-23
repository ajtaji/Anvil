# New board ports: Pi 3 B v1.2 and ROCK Pi 4C v1.2

These are intentionally non-bootable source stubs. Existing Pi 4 and UNO Q
builds are unchanged. Both ports reuse `Anvil/Core` and the existing HAL
contracts; neither gets a private copy of the kernel or protocol stacks.

| Port | Identity and capability stub | Status |
|---|---|---|
| Raspberry Pi 3 B v1.2 | `RaspberryPi3/Board/platform.pbi` | All services unavailable |
| ROCK Pi 4C v1.2 | `RockPi4C/Board/platform.pbi` | All services unavailable |

## Implementation order

1. Document the real firmware handoff: CPU mode, primary core, parked cores,
   device tree, RAM/reservations, loaded image, stack and cache ownership.
   Start on removable media with a documented recovery path; do not write SPI
   flash, eMMC or an existing installation as part of initial bring-up.
2. Add explicit compiler/startup target support using the shared AArch64
   emitter. Do not alias either board to BCM2711. Define and validate placement
   before adding an executable board file or a `tools/build.py` target.
3. Implement early display and diagnostic output, counter/timer and exception
   reporting. Bring the screen up as early as its real dependencies permit,
   before network waits; report boot progress as it happens.
4. Compose the shared core through the existing HAL seams. Implement actual
   reset, address validation, cache/DMA ownership and monotonic time; no dummy
   success, guessed cache state or fake reboot procedure.
5. Add storage and payload loading, then USB and networking. Keep per-interface
   addresses, DHCP/renewal/reconnect and transport-independent console behavior
   in the shared stack. Enable capability flags only after the service works.
6. Add input/touch, modules and secondary-core scheduling as supported. GPU
   acceleration follows separately: VideoCore IV and Mali are not V3D. Never
   advertise Vulkan compatibility on the strength of a CPU port alone.

## Gates before claiming support

- Explicit target refuses incompatible board includes; no Pi 4 startup fallback.
- Build numbering uses the repository's build ledger once images can be built.
- Cold boot and reset repeatedly reach a usable console; faults are visible.
- Early display, timers and DMA/cache operations are proven on the actual board.
- Payload load, execution and return leave Anvil usable.
- Each enabled service has positive and failure-path tests; networking also
  survives disconnect/reconnect and lease renewal without manual recovery.
- Test both available Pi 3 boards. No hardware results exist for these stubs.

Until then, keep the stubs outside `Boards/*.board` discovery and `TARGETS` in
the build wrapper. There is no upload command, generated image or flashing step
for either port yet. Host-side structure checks are not silicon proof.
