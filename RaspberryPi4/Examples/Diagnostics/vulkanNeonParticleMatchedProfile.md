# Matched Pi 4 particle timing profiles

`vulkanNeonParticleMatchedCpuProfile.pi4` and `vulkanNeonParticleMatchedCsdProfile.pi4` are returning RAM payloads built from one common source. Both use 10,000 identical green 4×4 particles, an 800×800 offscreen target, the same 16 MiB Vulkan window (`0x063E8000..0x073E8000`), four Chrome draw slots, 10,000 Chrome shared vertex quads, one warm frame, three measured frames, and the same 20,000-pixel final oracle. CPU mode calls `NeonVkChromeParticlesPrepare` and `DrawPrepared`; CSD mode calls the opt-in producer's `Prepare` and `Draw`. Each frame starts at a verified Vulkan idle boundary, ends with Chrome End and present consume, and checks exactly one draw and 60,000 vertices. The GPU producer's separate output buffer is the deliberate algorithmic difference in this matched comparison.

The report returned in `x0` is 64 little-endian words (256 bytes). Words 16–18, 19–21, 22–24, and 43–45 are the three measured Prepare, Draw, End, and full-frame times in microseconds. In CSD mode, words 34–36, 37–39, and 40–42 hold CSD, input staging, and palette times. Word 14 is elapsed through pixel validation; word 15 is elapsed after safe teardown. The checker verifies state, allocations, draw/render counters, pixels, faults, and deadlines, then reports median frame and phase times. A paired invocation prints CSD minus CPU median frame time; no speed claim follows from a single run.

An operator must arm a **15-second deadman** before booting either payload and keep sole board ownership until return or reset. Confirm the resident image map does not overlap the payload before upload. Build each with `--entry-returns --load-addr 8388608`; verify PMFBOOT v2 load and entry `0x800000`, container hash, and report symbol. Normal execution gates setup at 5 seconds, frame work at 10 seconds, pixel checking at 11 seconds, and completed teardown at 14 seconds. Any uncertain CSD, Vulkan submission, or idle state leaves allocations live and holds the payload until the deadman resets the board. The checker accepts only a clean report with completed teardown by 14 seconds.

From the repository root:

```
PureMetalForge.exe --compile RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedCpuProfile.pi4 --entry-returns --load-addr 8388608 -o <cpu-output>.img
PureMetalForge.exe --compile RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedCsdProfile.pi4 --entry-returns --load-addr 8388608 -o <csd-output>.img
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileGate.py
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCheckTest.py
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCheck.py CPU-REPORT.BIN CSD-REPORT.BIN
```

The `.img.pmf` containers are the upload artifacts. Record their hashes and the report address in the run manifest after each build.
