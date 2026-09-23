# Diagnostics that do not build against Anvil main

These Arduino UNO Q diagnostics were moved here unchanged apart from include paths
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
| `anvilqconprobe.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), which Anvil main does not carry. |
| `anvilqcoreproof.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), which Anvil main does not carry. If it is revived it also owes the rest of the map seam that `Anvil/Core/memrange.pbi` now asks every board for - HwMonBytes, HwMonStack, HwMonRegions and the region and payload-window procedures - answered from the windows it declares, as its HwMonLo/HwMonHi already are (compiler repository 488e2322). |
| `anvilqdrbg.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink) and ArduinoQ/Lib/qentropy_q.pi4 (the Q entropy source), neither of which Anvil main carries. |
| `anvilqefiprobe.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), which Anvil main does not carry. |
| `anvilqgpuprobe.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), which Anvil main does not carry. |
| `anvilqnetproof.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), ArduinoQ/Lib/qserial_q.pi4, ArduinoQ/Lib/qslip.pi4, ArduinoQ/Lib/qnetfile.pi4, ArduinoQ/Board/hw_link_q.pi4 and ArduinoQ/Board/hw_net_q.pi4, none of which Anvil main carries. |
| `anvilqslipbench.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), ArduinoQ/Lib/qgeniuart.pi4, ArduinoQ/Board/hw_serial_q.pi4, ArduinoQ/Lib/qslip.pi4, ArduinoQ/Lib/qnetfile.pi4, ArduinoQ/Board/hw_link_q.pi4 and ArduinoQ/Board/hw_net_q.pi4, none of which Anvil main carries. |
| `anvilqsliprxprobe.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), ArduinoQ/Lib/qgeniuart.pi4, ArduinoQ/Board/hw_serial_q.pi4, ArduinoQ/Lib/qslip.pi4, ArduinoQ/Lib/qnetfile.pi4, ArduinoQ/Board/hw_link_q.pi4 and ArduinoQ/Board/hw_net_q.pi4, none of which Anvil main carries. |
| `anvilqsliptcp.unoq` | It includes ArduinoQ/Board/qsink.pi4 (the Q console output sink), ArduinoQ/Lib/qgeniuart.pi4, ArduinoQ/Board/hw_serial_q.pi4, ArduinoQ/Lib/qslip.pi4, ArduinoQ/Lib/qnetfile.pi4, ArduinoQ/Board/hw_link_q.pi4 and ArduinoQ/Board/hw_net_q.pi4, none of which Anvil main carries. |
