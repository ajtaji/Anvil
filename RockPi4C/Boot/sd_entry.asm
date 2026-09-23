; Anvil's RK3399 direct-SD EL3 entry, at the beginning of the one Anvil image.
; Rockchip DDR/miniloader loads this single image at 0x40000. The complete
; runtime follows at 0x41000 and the embedded board data is at 0x1c0000.
_start:
  msr daifset, #15
  mrs x9, currentel
  cmp x9, #12
  b.ne park
  msr spsel, #1
  movz x9, #0x0500, lsl #16
  mov sp, x9
  ; UART2 is 0xff1a0000; firmware retains its clock, pinmux and baud.
  movz x20, #0xff1a, lsl #16
  ; Preserve and report the full incoming value before applying the narrow
  ; cache-off contract. Never clear M/C here: loader-written Anvil/DTB data
  ; may still be dirty in a cache, and no platform clean-to-PoC contract is
  ; available at this handoff.
  mrs x19, sctlr_el3
  movz w0, #83
  bl uart_byte
  movz w0, #67
  bl uart_byte
  movz w0, #84
  bl uart_byte
  movz w0, #76
  bl uart_byte
  movz w0, #82
  bl uart_byte
  movz w0, #95
  bl uart_byte
  movz w0, #69
  bl uart_byte
  movz w0, #76
  bl uart_byte
  movz w0, #51
  bl uart_byte
  movz w0, #61
  bl uart_byte
  mov x0, x19
  bl uart_hex64
  movz w0, #13
  bl uart_byte
  movz w0, #10
  bl uart_byte
  ; SCTLR_EL3.M/C are bits 0 and 2. If either is set, refuse and retain
  ; the complete value above for diagnosis; do not guess a translation/cache
  ; state or risk discarding dirty firmware writes.
  movz x10, #5
  and x9, x19, x10
  cbnz x9, contract_failed
  ; I-only is safe to disable with D-cache/MMU already proven off. Preserve
  ; every other SCTLR bit, complete earlier accesses, then synchronize the
  ; instruction stream after the control-register write.
  movz x10, #0x1000
  and x9, x19, x10
  cbz x9, sctlr_ready
  dsb sy
  movz x10, #0xefff
  movk x10, #0xffff, lsl #16
  movk x10, #0xffff, lsl #32
  movk x10, #0xffff, lsl #48
  and x19, x19, x10
  msr sctlr_el3, x19
  isb
sctlr_ready:
  ; Permit floating-point/SIMD at EL3 for the compiler's runtime.
  msr cptr_el3, xzr
  isb
  ; RK3399 secure timer uses the 24 MHz oscillator (Rockchip stimer contract).
  movz x9, #0x3600
  movk x9, #0x016e, lsl #16
  msr cntfrq_el0, x9
  movz x9, #0x80a0
  movk x9, #0xff86, lsl #16
  ldr w10, [x9, #0x1c]
  movz w11, #1
  and w10, w10, w11
  cbnz w10, timer_ready
  movz w10, #0xffff
  movk w10, #0xffff, lsl #16
  str w10, [x9, #0]
  str w10, [x9, #4]
  movz w10, #0
  str w10, [x9, #0x10]
  str w10, [x9, #0x14]
  movz w10, #1
  str w10, [x9, #0x1c]
timer_ready:
  dsb sy
  movz w0, #65
  bl uart_byte
  movz w0, #78
  bl uart_byte
  movz w0, #86
  bl uart_byte
  movz w0, #73
  bl uart_byte
  movz w0, #76
  bl uart_byte
  movz w0, #32
  bl uart_byte
  movz w0, #83
  bl uart_byte
  movz w0, #68
  bl uart_byte
  movz w0, #32
  bl uart_byte
  movz w0, #69
  bl uart_byte
  movz w0, #76
  bl uart_byte
  movz w0, #51
  bl uart_byte
  movz w0, #13
  bl uart_byte
  movz w0, #10
  bl uart_byte
  movz x0, #0x001c, lsl #16
  movz x1, #0
  movz x2, #0
  movz x3, #0
  movz x16, #0x1000
  movk x16, #0x0004, lsl #16
  isb
  br x16
contract_failed:
  movz w0, #33
  bl uart_byte
park:
  wfe
  b park
uart_byte:
  movz w11, #0x10, lsl #16
uart_wait:
  ldr w10, [x20, #0x14]
  movz w12, #0x20
  and w10, w10, w12
  cbnz w10, uart_send
  subs w11, w11, #1
  b.ne uart_wait
  b park
uart_send:
  str w0, [x20]
  ret
uart_hex64:
  mov x15, x30
  mov x14, x0
  movz x17, #16
hex_loop:
  lsr x12, x14, #60
  movz x13, #15
  and x12, x12, x13
  movz x13, #9
  cmp x12, x13
  b.hi hex_letter
  add x12, x12, #48
  b hex_emit
hex_letter:
  add x12, x12, #55
hex_emit:
  mov x0, x12
  bl uart_byte
  lsl x14, x14, #4
  subs x17, x17, #1
  b.ne hex_loop
  mov x30, x15
  ret
