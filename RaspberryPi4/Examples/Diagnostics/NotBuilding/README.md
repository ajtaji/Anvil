# Diagnostics that do not build against Anvil main

These Raspberry Pi 4 diagnostics were moved here unchanged apart from include paths
renamed to Anvil's layout. Each one includes a library that exists only in the
older copy of the monitor and is not part of Anvil main, so none of them
compiles today. They are kept rather than dropped so that the instrument and
what it proved are not lost; a diagnostic comes back up one directory when the
library it needs is restated in Anvil or the diagnostic is rewritten against
an interface Anvil main has.

The diagnostic build gate, `tools/a64/a64_diag_build_check.py`, does not build
this directory.

| File | What it needs that Anvil main does not have |
|---|---|
| `pi4Atomics.pi4` | It includes RaspberryPi4/Lib/atomic.pi4 (the atomic primitives library), which Anvil main does not carry. |
| `pi4DamageSelfTest.pi4` | It includes RaspberryPi4/Lib/damage.pi4 (the damage-rectangle tracker), which Anvil main does not carry. |
| `pi4FaultProbe.pi4` | It includes RaspberryPi4/Lib/fault.pi4 (the fault-vector reporting library), which Anvil main does not carry. |
| `pi4GicProbe.pi4` | It includes RaspberryPi4/Lib/gic.pi4 (the GIC-400 registration library), which Anvil main does not carry; Anvil main's interrupt support is RaspberryPi4/Lib/interrupts.pi4 with a different interface. |
| `pi4GicTimer.pi4` | It includes RaspberryPi4/Lib/fault.pi4 and RaspberryPi4/Lib/gic.pi4, neither of which Anvil main carries. |
| `pi4HciProbe.pi4` | It includes RaspberryPi4/Lib/bluetooth.pi4 (the Bluetooth HCI transport), which Anvil main does not carry. |
| `pi4HdmiAudioProbe.pi4` | It includes RaspberryPi4/Lib/hdmiaudio.pi4 (the HDMI audio driver), which Anvil main does not carry. |
| `pi4HdmiAudioTone.pi4` | It includes RaspberryPi4/Lib/hdmiaudio.pi4 (the HDMI audio driver), which Anvil main does not carry. |
| `pi4KokoroAudioCompile.pi4` | It includes RaspberryPi4/Lib/hdmiaudio.pi4, RaspberryPi4/Lib/kokoro_audio.pi4 and MathLib/onnx/pcm_fp32.pmi, none of which Anvil main carries. |
| `pi4NeonLiar.pi4` | It includes RaspberryPi4/Lib/damage.pi4 (the damage-rectangle tracker), which Anvil main does not carry. |
| `pi4RtcProbe.pi4` | It includes RaspberryPi4/Lib/rtc.pi4 (the real-time clock driver), which Anvil main does not carry. |
| `pi4SchedProbe.pi4` | It includes RaspberryPi4/Lib/sched.pi4 (the cooperative scheduler library), which Anvil main does not carry. |
| `pi4SimdSelfTest.pi4` | It includes RaspberryPi4/Lib/simd.pi4 (the SIMD kernel library), which Anvil main does not carry. |
| `pi4SimdThroughput.pi4` | It includes RaspberryPi4/Lib/simd.pi4 (the SIMD kernel library), which Anvil main does not carry. |
| `pi4SmpWake.pi4` | It includes RaspberryPi4/Lib/smp.pi4 (the secondary-core wake library), which Anvil main does not carry. |
| `pi4StringF32.pi4` | It includes RaspberryPi4/Lib/string_f32.pi4 (the float-to-string formatter), which Anvil main does not carry. |
| `pi4TouchProbe.pi4` | It includes RaspberryPi4/Lib/dsi_panel.pi4 (the first-generation DSI panel driver), which Anvil main does not carry; Anvil main has dsi_panel_v2.pi4 with a different interface. |
