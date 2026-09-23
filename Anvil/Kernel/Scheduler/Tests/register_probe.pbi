; ABI witness: preserve incoming callee state, seed distinct values, yield,
; then verify the actual native continuation before restoring caller state.
Global Dim probe_vectors.i[16]
ProcedureNaked RegisterProbe()
  ASM
    sub sp, sp, #256
    str x18, [sp, #0]
    str x19, [sp, #8]
    str x20, [sp, #16]
    str x21, [sp, #24]
    str x22, [sp, #32]
    str x23, [sp, #40]
    str x24, [sp, #48]
    str x25, [sp, #56]
    str x26, [sp, #64]
    str x27, [sp, #72]
    str x28, [sp, #80]
    str x29, [sp, #88]
    str x30, [sp, #96]
    str q8, [sp, #112]
    str q9, [sp, #128]
    str q10, [sp, #144]
    str q11, [sp, #160]
    str q12, [sp, #176]
    str q13, [sp, #192]
    str q14, [sp, #208]
    str q15, [sp, #224]
    movz x18, #274
    movz x19, #275
    movz x20, #276
    movz x21, #277
    movz x22, #278
    movz x23, #279
    movz x24, #280
    movz x25, #281
    movz x26, #282
    movz x27, #283
    movz x28, #284
    movz x29, #285
    adrp x9, global_probe_vectors
    add x9, x9, #:lo12:global_probe_vectors
    ldr q8, [x9, #0]
    ldr q9, [x9, #16]
    ldr q10, [x9, #32]
    ldr q11, [x9, #48]
    ldr q12, [x9, #64]
    ldr q13, [x9, #80]
    ldr q14, [x9, #96]
    ldr q15, [x9, #112]
    bl scyield
    cmp x0, #1
    b.ne probe_bad
    movz x0, #274
    cmp x18, x0
    b.ne probe_bad
    movz x0, #275
    cmp x19, x0
    b.ne probe_bad
    movz x0, #276
    cmp x20, x0
    b.ne probe_bad
    movz x0, #277
    cmp x21, x0
    b.ne probe_bad
    movz x0, #278
    cmp x22, x0
    b.ne probe_bad
    movz x0, #279
    cmp x23, x0
    b.ne probe_bad
    movz x0, #280
    cmp x24, x0
    b.ne probe_bad
    movz x0, #281
    cmp x25, x0
    b.ne probe_bad
    movz x0, #282
    cmp x26, x0
    b.ne probe_bad
    movz x0, #283
    cmp x27, x0
    b.ne probe_bad
    movz x0, #284
    cmp x28, x0
    b.ne probe_bad
    movz x0, #285
    cmp x29, x0
    b.ne probe_bad
    str q8, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1032
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2056
    cmp x0, x1
    b.ne probe_bad
    str q9, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1033
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2057
    cmp x0, x1
    b.ne probe_bad
    str q10, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1034
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2058
    cmp x0, x1
    b.ne probe_bad
    str q11, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1035
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2059
    cmp x0, x1
    b.ne probe_bad
    str q12, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1036
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2060
    cmp x0, x1
    b.ne probe_bad
    str q13, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1037
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2061
    cmp x0, x1
    b.ne probe_bad
    str q14, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1038
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2062
    cmp x0, x1
    b.ne probe_bad
    str q15, [sp, #240]
    ldr x0, [sp, #240]
    movz x1, #1039
    cmp x0, x1
    b.ne probe_bad
    ldr x0, [sp, #248]
    movz x1, #2063
    cmp x0, x1
    b.ne probe_bad
    movz x0, #1
    b probe_restore
probe_bad:
    movz x0, #0
probe_restore:
    ldr q8, [sp, #112]
    ldr q9, [sp, #128]
    ldr q10, [sp, #144]
    ldr q11, [sp, #160]
    ldr q12, [sp, #176]
    ldr q13, [sp, #192]
    ldr q14, [sp, #208]
    ldr q15, [sp, #224]
    ldr x18, [sp, #0]
    ldr x19, [sp, #8]
    ldr x20, [sp, #16]
    ldr x21, [sp, #24]
    ldr x22, [sp, #32]
    ldr x23, [sp, #40]
    ldr x24, [sp, #48]
    ldr x25, [sp, #56]
    ldr x26, [sp, #64]
    ldr x27, [sp, #72]
    ldr x28, [sp, #80]
    ldr x29, [sp, #88]
    ldr x30, [sp, #96]
    add sp, sp, #256
    ret
  ENDASM
EndProcedure

