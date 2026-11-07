; Compatibility include for the historical AArch64-only payload entry path.
; New board compositions select their ISA backend explicitly. This file does
; not select a payload mechanism for a new architecture.
XIncludeFile "Anvil/Kernel/AArch64/payload_call.pbi"
