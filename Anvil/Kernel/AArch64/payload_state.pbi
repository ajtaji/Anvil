; Private AArch64 payload context, selected by ARM board compositions.
; Shared Core state owns only the portable entry address and returned value.
; These are BSS slots because a payload may disturb its own stack. The
; architecture trampoline restores the saved monitor stack before returning.
; See docs/ABI_AARCH64.md for the existing register/privilege contract.
Global gSp.i                   ; monitor SP saved across payload execution
Global gGoX0.i                 ; entry x0: service-table address or zero

Global gPayloadDidEnter.i ; set only at the actual CPU branch, never by RunAt preparation
