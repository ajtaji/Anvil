# USB local-flow review gate

The previous frame gate overstated its coverage. It did not implement local read-before-write or alias propagation. Its header and verdict now explicitly restrict their claims.

Run `python tools/usb_local_flow_check.py --report <scratch-report.json>` without building or touching hardware. Exit 2 means review is required, not a proved compiler or driver bug. `--selftest` runs six negative controls and a positive branch-initialization case.

The new scanner detects explicit scalar reads without a preceding definite source assignment, including assignments in only one If branch or only within a While loop. It tracks local-address taint through scalar assignments and conservatively reports forwarding calls, nonlocal stores and returns. Any call receiving an alias is a review boundary, even if that callee is actually synchronous and safe; it is not silently trusted. Aliases remain tainted across reassignment, intentionally over-reporting rather than losing branch taint.

Scope is the syntactic direct-call closure rooted at UsbEnumerate across Pi4 Board/Lib files. This includes its phase hooks only where their addresses appear syntactically as calls; dynamic dispatch is not resolved. Missing definitions, duplicate definitions, ASM and unsupported control-flow/array operations are listed explicitly. The scanner does not parse the entire language, solve pointer arithmetic, infer writes through output parameters, prove whole-program lifetimes, or resolve target/compiler conditionals. Consequently it must not certify the entire pre-USB path as safe.

Read-before-write means absence of explicit source initialization; generated frames are zero-filled, so a finding can represent intentional zero use rather than undefined behavior. Review findings individually before proposing production changes. The old direct spelling check remains useful but is not a substitute for this report or emitted execution.
