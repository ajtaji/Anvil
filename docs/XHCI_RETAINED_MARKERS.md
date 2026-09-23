# Retained reset markers

The board installs a separate xHCI trace hook that only calls MonPhaseMark. It does not invoke UART, display, allocation, or device polling. MonPhaseMark completes its cache clean with DSB SY before returning. This improves warm-reset retention, not survival of loss of DRAM power; cache maintenance still depends on a functioning memory system.

Existing 0600 family remains the public initialization phase. New families: 0900|phase immediately before UsbPhaseWord's ScreenServiceTick, 0A00|phase immediately after it. The trace hook remains installed for storage retry, independently of the temporary printable phase hook.

0800 detail low byte:

| Value | Boundary |
|---|---|
| 1 / 2 / 3 | Before halt / halt refused / halt returned successfully |
| 4 / 5 | Before / after initial USBCMD read |
| 6 / 7 | Before / after HCRST write |
| 8 / 9 | Before / after first HCRST polling read |
| 10 | HCRST timeout before error snapshot |
| 11 / 12 | Before / after first CNR polling read |
| 13 | CNR timeout before error snapshot |
| 14 | Reset completed |

Only the first poll is marked, avoiding cache maintenance on every iteration. A retained 0809 or 080C therefore cannot distinguish a later non-completing read from a loop whose clock stopped. Marks are diagnostics, not recovery mechanisms or proof of the physical fault.

Desk gates: tools/xhci_initial_readiness_check.py executes extracted real reset/readiness bodies and checks exact marker sequence with three negative controls. tools/xhci_phase_hook_check.py executes the actual UI hook, verifies both screen boundaries, and rejects removal of either. Both take --compiler pointing at the unified IDE. No complete monitor image or hardware run was performed for these changes.
