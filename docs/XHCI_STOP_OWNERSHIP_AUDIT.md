# xHCI stop ownership audit

2026-09-12. Read-only source audit during the integrated-build freeze. No board observation, production edit, or claim that this explains the intermittent USB boot hang.

## Confirmed boundary gap

`RaspberryPi4/Lib/xhci.pi4` has one production caller of `XhciStop`: `xh_FailStop` (2786). `XhciInitAt` calls that wrapper after failures in Locate (2851), ReadCaps (2860), Reset (2865), MemInit (2880), DMA enable (2885), and Start (2889). Line numbers describe the current working tree and may move.

`XhciStop` (2917) clears software readiness, then silently returns if `xh_Reset` fails (2925). Reset (1867) first calls `xh_Halt`; halt can fail initial CNR or the HCHalted deadline. Thus clearing `xh_ready` is not proof that the controller has stopped bus-mastering. The wrapper comment promising stopped hardware is stronger than the implementation.

The particularly relevant path is successful ring installation and BME enable, failed `xh_Start`, then failed halt during cleanup. Initialization returns failure without an explicit unsafe-ownership state. This is a source-reachable failure path, not a silicon reproduction. HCRST/CNR failure after a successfully observed halt must be distinguished from failure to establish halt in the first place.

## Caller consequences and limits

- `Board/cursor_input.pi4:468` reports failed host initialization and returns to boot.
- `Board/storage.pi4:103` tries the unified enumeration first; its dedicated fallback calls `XhciInit` again at 143 if necessary. Boot can continue toward the SD fallback after failure.
- A retry resets `xh_brk` metadata before reset, but actual `xh_MemInit` and ring/context writes are gated by a successful `xh_Reset`. **This audit does not demonstrate a retry overwriting live rings.** Preserve that gate.
- Repository search found no production direct `XhciStop` caller outside `xh_FailStop`. The payload boundary in `Board/cache.pi4` does not call it. Therefore this is not a demonstrated stop-call-to-payload-return chain. It is an unrepresented unsafe state that normal boot can carry forward; any proposed payload restriction must trace actual payload memory ownership first.
- The static arena remains allocated. Failure alone is not evidence it is freed. Do not replace this finding with an unsupported claim of use-after-free.

## Separate status acknowledgement issue

`XhciStop:2929` writes USBSTS as `t & ~XHCI_STS_EINT`. EINT is RW1C: this does not acknowledge EINT and can acknowledge other sampled writable-one-to-clear events instead. Treat this independently from DMA ownership and do not claim it caused the cold hang. The source already identifies the primary specification: Intel xHCI revision 1.2b, USBSTS register definition, https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf .

## Proposed API work, subject to supervisor approval

1. Return a checked stop result and track hardware ownership separately from driver readiness. Distinguish proven halted, reset-complete/ready, and quiescence unknown; retain original initialization error and separate cleanup error.
2. Propagate that result through failstop and host initialization. An unavailable host and an unsafe host must not be silently identical to callers.
3. Require proven quiescence before arena/context reuse or ownership handoff. Audit externally exposed ring operations against the new state. Do not blindly clear BME while transactions may remain in flight, or invent reset sequences without hardware specification support.
4. Correct USBSTS acknowledgement using the intended RW1C mask and preserve unrelated events.

## Candidate emitted regression

Extend the existing `tools/xhci_initial_readiness_check.py` extraction approach with actual Stop/FailStop and initialization bodies, named leaf stubs, and an explicit register timeline. Cases: already halted; RUN refuses to halt; initial CNR stuck; halt succeeds but HCRST sticks; reset clears but CNR sticks; Start failure followed by failed cleanup; subsequent retry fails reset with zero ring writes; subsequent proven reset permits writes. Assert separate ownership/error results and no false stopped report. Model PCI command BME independently of `xh_ready`. For RW1C, set EINT plus another event, execute actual acknowledgement and assert only EINT clears. Mutating the halt gate or acknowledgement mask must make the test fail. This candidate has not been implemented or executed in this audit.
