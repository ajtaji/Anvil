; ======================================================================
;  t0vm.pi4 - the T0 threaded-bytecode virtual machine, ON THE
;             RASPBERRY PI 4 (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2016 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "RaspberryPi4/Lib/t0vm.pi4"
;
;  THE PORTABLE CORE, A64.  This file carries the "PORTABLE CORE A64"
;  BEGIN/END markers below and NOT the 32-bit families' plain
;  "PORTABLE CORE" pair, because the region between them
;  is NOT byte-identical to t0vm.pico / .pico2 / .unor4 and cannot be:
;  `.i` is 64 bits here and a T0 cell is defined on int32.  Per the twin
;  checker's own rule - an intentional divergence RENAMES the markers,
;  never quietly edits one copy - the rename is the declaration, and
;  `tools/check_tls_twins.py --cross t0vm` is the gate that replaces the
;  byte compare: same procedure set, same declaration order, same
;  parameter lists, plus one declared addition with its reason.
;
;  PROOF STATUS (Raspberry Pi 4 / Cortex-A72, AArch64): builds clean for
;  pi4; runs the SAME T0-generated PEM decoder bytecode the three 32-bit
;  families run, over the SAME certificates, PEM->DER byte-for-byte
;  against the python base64 oracle, under tools/a64/a64_t0vm_check.py's
;  A64 model; the context-RAM bounds guard is proven by the 30 checks of
;  RP2350/Examples/Diagnostics/rp2350T0vmBoundsProbe.pico2 plus crafted
;  hostile blobs whose refusal is OBSERVED; mutation-swept under
;  --mutate.  NOTHING HERE HAS RUN ON SILICON.
;
; ======================================================================
;  WHAT T0 IS, AND WHY THIS FILE EXISTS
; ----------------------------------------------------------------------
;  BearSSL's X.509 certificate decoder and its TLS handshake are not
;  written as ordinary C.  They are written in a small Forth-like
;  language ("T0") and compiled AHEAD OF TIME into a table of threaded
;  bytecode plus a tiny interpreter.  This file is that interpreter,
;  translated once into the house dialect so the X.509 engine and the
;  handshake can both RUN their bytecode on it.
;
;  The machine is a classic Forth engine:
;    * a DATA STACK of 32-bit cells (operands),
;    * a RETURN STACK of 32-bit cells (call frames AND local variables),
;    * an instruction pointer stepping through a byte array of opcodes.
;  There is NO host recursion: a T0 word calling another T0 word pushes a
;  frame on the return stack and the SAME loop keeps running.
;
;  CONSTANT TIME DOES NOT APPLY HERE.  This VM parses PUBLIC data -
;  certificates and handshake framing are on the wire in the clear - so
;  nothing in this file is CT-hardened, and nothing should be.  The
;  secret work (the i15 big-ints, AES, GHASH) lives in other modules and
;  is reached only through native callbacks; those modules carry their
;  own CT discipline.
;
; ======================================================================
;  THE CONTRACT - how a host program uses this VM
; ----------------------------------------------------------------------
;  Unchanged from the 32-bit copies.  In call order:
;
;    1. LOAD A PROGRAM.  A generated "<name>_blob" include (from
;       tools/t0gen.py) defines a loader that fills the descriptor
;       globals t0_cp, t0_datap, t0_caddrp, t0_opp, t0_interp, t0_entry.
;       That include is PURE DATA and byte-identical across families.
;    2. T0Start()  once, to enter the entry word.
;    3. T0Run()    in a loop.  It returns
;         #T0_HALT    the program returned from its top frame - done.
;         #T0_YIELD   the bytecode executed `co`.  Service it and call
;                     T0Run() again to resume, or stop.
;         #T0_NATIVE  t0_native_id says which native word.  Run it,
;                     moving operands with T0Pop() / T0Push(), and call
;                     T0Run() again.  THE VM NEVER CALLS HOST CODE; the
;                     host drives.
;    4. CONTEXT RAM.  get8/set8/get16/set16/get32/set32 read and write
;       t0_ram; data-get8 reads the constant DATA block.  EVERY t0_ram
;       ACCESS IS BOUNDS-CHECKED - see the guard below.
;
;  ONE ADDITION TO THE CONTRACT ON THIS PART.  A host native word that
;  pushes a value which is not a sign-extended int32 puts a cell into
;  the machine that the VM's own arithmetic will not agree with.  Push
;  T0Norm(v) if the value can exceed 31 bits.  Every native the PEM
;  decoder, X.509 and the handshake actually use pushes a byte, a small
;  count, or -1, all of which are already canonical.
;
; ======================================================================
;  DIALECT NOTES a reader needs
; ----------------------------------------------------------------------
;  * `>>` is ARITHMETIC (sign-smearing).  T0's `>>` word is defined on
;    int32 and is arithmetic too, so with the cell convention below the
;    two agree exactly.  T0's logical shift `u>>` is written here
;    `(x >> c) & mask` with the sign bits masked off.
;  * XOR is spelled `!`.  Bitwise NOT is NOT spelled `x ! $FFFFFFFF`
;    here - see SHAPE 5.
;  * Comparisons are SIGNED.  T0's signed compares map straight across;
;    its unsigned compares are done by masking both operands to 32 bits,
;    which a 64-bit register makes exact - see SHAPE 5.
;  * THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO (the pragma
;    is not file-scoped).  Declare your variables.
;  * REQUIRES NOTHING and includes nothing (house rule: a library never
;    includes a library - the main file lists them).  It needs only
;    PeekA and arithmetic.
;
;  ======================================================================
;   THE CELL WIDTH DECISION, AND ITS REASON
;  ======================================================================
;
;  A T0 CELL IS 32 BITS, EMULATED, AND STORED SIGN-EXTENDED INTO THE
;  64-BIT HOST WORD.  Canonically: every cell on the data stack, on the
;  return stack, and in a local holds the int64 VALUE of the int32 it
;  represents, so -1 is $FFFFFFFFFFFFFFFF and never $00000000FFFFFFFF.
;
;  WHY 32-BIT-EMULATED AND NOT NATIVELY 64-BIT.  T0 and everything
;  compiled to it - the PEM decoder, the X.509 engine, the handshake -
;  is defined on int32.  BearSSL's own generated interpreter carries the
;  cells in `uint32_t` and its `>>` is a signed 32-bit shift.  A native
;  64-bit cell would silently change what `<<`, `>>`, `u>>`, `not`, the
;  unsigned compares and every literal MEAN, in bytecode this file is
;  not allowed to recompile.  A wider cell is a different machine, not a
;  port of this one.
;
;  WHY SIGN-EXTENDED AND NOT ZERO-EXTENDED (masked to the low 32 bits).
;  This is the load-bearing half of the decision and it is what makes
;  the port small:
;
;    * with sign-extended cells the host's 64-bit `+ - * / % < <= > >=
;      = <> & | ! >>` agree EXACTLY with the int32 operations, for every
;      operand in range.  Only the operations that can LEAVE the int32
;      range need bringing back, and there are six of them;
;    * T0NextS already produces exactly this form.  Its accumulator is
;      seeded with all-ones for a negative literal and the reconstruction
;      x = x*128 + g is the signed value, at any width.  A zero-extended
;      convention would have to mask every literal;
;    * AND FORUM 517'S NEGATIVE-OFFSET TEST DEPENDS ON IT.  This one is
;      stated carefully, because the sweep corrected a stronger claim
;      that was written here first.  T0RamInRange's first test is
;      `addr < 0`, and the offset it tests is a CELL the T0 program
;      computed out of the bytes of a certificate.  UNDER THIS
;      CONVENTION that test is the only thing that refuses an offset
;      that underflowed: `addr > #T0_RAM_SIZE - n` does not fire on a
;      negative, and mutation M2, which deletes the negative half,
;      DIES.  Under a ZERO-EXTENDED convention the same offset would
;      arrive as a large positive number, `addr < 0` would become DEAD
;      CODE THAT STILL READS AS THOUGH IT WORKS, and the refusal would
;      happen by accident on the upper bound instead.  That is measured,
;      not argued: mutation M13 makes T0Norm a zero-extend and the
;      crafted negative-offset blob G3 is STILL REFUSED, by the other
;      half.  So a zero-extended VM would not have a hole here today -
;      it would have half a guard doing nothing, resting on an accident,
;      which is how one arrives.  What M13 does kill is 23 other jobs:
;      the arithmetic, the signed comparisons, `not`, the shifts and the
;      PEM decode itself, which is the real measure of how much of this
;      file the convention is holding up.
;
;  Renormalising is one procedure, T0Norm, written ONCE and called at
;  the six sites where an int32 operation can overflow: `+`, `-`, `neg`,
;  `*`, `/` and `<<`, plus get32 (whose top byte carries bit 31) and
;  T0NextS's return (so a malformed code block cannot inject a wider
;  cell).  T0Norm is the file's only addition and it is declared in
;  tools/check_tls_twins.py with this reason.
;
;  ======================================================================
;   .i IS 64 BITS HERE.  THE FOUR-SHAPE AUDIT, PLUS THE FIFTH
;  ======================================================================
;
;  The ways a 32-bit portable core breaks on this part were measured in
;  Anvil/Core/sha256.pbi, RaspberryPi4/Lib/gcm.pi4 and
;  RaspberryPi4/Lib/bignum.pi4.  Every one was looked for here and the
;  finding is recorded either way - "not present" is a result, not a
;  silence.
;
;  SHAPE 1 - AN ARRAY ELEMENT IS EIGHT BYTES, NOT FOUR.
;      PRESENT AS A RISK, AND IT DOES NOT BITE, FOR A REASON WORTH
;      WRITING DOWN.  This VM has THREE arrays and two of them are the
;      shape's favourite target:
;          Global Dim t0_ds.i[#T0_DS_DEPTH]   the DATA stack
;          Global Dim t0_rs.i[#T0_RS_DEPTH]   the RETURN stack
;          Global Dim t0_ram.a[#T0_RAM_SIZE]  the context RAM
;      The two `.i` arrays are element EIGHT bytes here and element FOUR
;      on the Picos.  Nothing breaks because NOTHING IN THIS FILE OR ITS
;      CALLERS ADDRESSES THEM BY BYTE.  Every single access is written
;      `t0_ds[i]` / `t0_rs[i]`, so the compiler scales the index; there
;      is no `@t0_ds[0] + i * 4` anywhere in the core, in
;      t0vmPemProof.*, or in pemdec_blob.* (audited by grep across all
;      three families).  The whole file was searched for `* 4` and the
;      only hits are inside T0PrimMem's byte assembly, which is
;      arithmetic on VALUES, not addresses.
;      t0_ram is `.a` - ONE byte per element on every family - so the
;      guard's arithmetic, `#T0_RAM_SIZE - n`, means the same thing here.
;      WHAT THIS DOES COST is memory: the two stacks are 6 KB here
;      against 3 KB on a Pico.  That is recorded in the sizes block
;      below and it is the only visible consequence.
;      A CALLER MUST NOT reach into t0_ds or t0_rs with a pointer.  Use
;      T0Push / T0Pop / T0Peek, which is what every existing caller does.
;
;  SHAPE 2 - PeekL SIGN-EXTENDS.
;      NOT PRESENT.  There is no PeekL and no PeekB in this file and
;      never was - which is luckier than it sounds, because a T0 VM
;      reads its bytecode out of a blob and EVERY opcode, literal byte,
;      caddr byte and opmap byte is a Peek.  All eight of them are
;      PeekA (unsigned 8-bit) and all eight are masked `& 255` on top:
;          T0NextByte  T0NextU  T0NextS (twice)  T0CaddrGet (twice)
;          T0PrimMem's data-get8   T0Run's opmap fetch
;      The 32-bit copies already used PeekA because a raw opcode read
;      signed would have been wrong on them too.  No 16-bit or 32-bit
;      read of the blob exists at all: T0CaddrGet assembles its
;      little-endian 16-bit pair out of two PeekA bytes by hand, so
;      there is nowhere for PeekU or PeekN to be needed either.
;
;  SHAPE 3 - `<<` DOES NOT DISCARD AT BIT 31.
;      PRESENT, IN THE OBVIOUS PLACE AND IN ONE THAT IS NOT.
;        * T0PrimBit's `<<` opcode is the obvious one: `x << c` with x a
;          cell.  Masked back through T0Norm.  On a 32-bit register the
;          discard was free and the 32-bit copies rely on it.
;        * The LITERAL DECODERS are the one that is not.  T0NextU and
;          T0NextS both accumulate `x = (x << 7) | (y & $7F)` and a
;          7-bit continuation encoding shifts left repeatedly - five
;          bytes for a full-width literal, which is 35 bits of shifting.
;          T0NextS needs NO mask and that is proved rather than assumed:
;          seeded with 0 or -1, the recursion x = x*128 + g reconstructs
;          exactly the signed value at any register width, so for every
;          literal a T0 compiler can emit (all int32-representable) the
;          64-bit answer IS the sign-extended 32-bit answer.  The mask
;          on its RETURN is there for a malformed code block, not for a
;          legal one.  T0NextU's accumulator is masked to #T0_W32.
;        * T0PrimMem's get32 assembles `... | (b3 << 24)`, at most
;          $FF000000 - which is POSITIVE at 64 bits and NEGATIVE at 32.
;          This one is not cosmetic: a get32 of a context word with bit
;          31 set used to come back negative and now comes back as
;          +4278190080, and the very next signed compare or `>>` in the
;          T0 program takes the other branch.  Routed through T0Norm.
;        * `(hi << 8)` in T0CaddrGet, `(lnum << 16)` in T0EnterSlot and
;          `(1 << (32 - c))` in u>> are all bounded well under 2^32 and
;          need nothing.  Recorded so nobody has to re-derive it.
;
;  SHAPE 4 - A 32-BIT COUNTER NEVER WRAPS.
;      NOT PRESENT AS A CARRY TRICK - there is no carry reconstruction
;      anywhere in this file.  It IS present in the weaker form that the
;      T0 arithmetic opcodes `+`, `-`, `neg`, `*` and `/` are DEFINED to
;      wrap at 32 bits (BearSSL computes them in uint32_t) and here they
;      do not.  That is the same fact wearing a different hat and it is
;      answered by the same T0Norm.  Nothing in the PEM decoder overflows
;      - which is exactly why the gate cannot see it and why the
;      OP_CELL opcode-conformance jobs exist.
;
;  ---- THE FIFTH THING, WHICH IS THE ONE THAT ACTUALLY BITES ----------
;
;  `>> 31` AS A SIGN TEST and `x ! $FFFFFFFF` AS A LOGICAL NOT.
;
;      `>> 31`: NOT PRESENT.  There is no `>> 31` in the 32-bit core.
;      Searched for; the only shifts are the opcode implementations and
;      the frame unpack `(frame >> 16) & $FFFF`, which is a field
;      extract from a value that is always a small positive.
;
;      `! $FFFFFFFF` and its sibling `! $80000000`: PRESENT, SIX SITES,
;      AND THIS IS THE SAME DEFECT THAT MADE GcmDecrypt ACCEPT A FORGED
;      TAG.  Under the cell convention above, XOR-ing a cell against a
;      32-bit constant leaves bits 32..63 untouched, so the result is
;      not a cell at all:
;
;        1. T0PrimBit, the `not` opcode: `T0Push(a ! $FFFFFFFF)`.
;           DOES NOT SURVIVE.  not(0) must be -1 and produces
;           +4294967295; not(-1) must be 0 and produces
;           $FFFFFFFF00000000, which is NOT ZERO - so a `jump-if-not`
;           on it takes the wrong branch.  That is the tag verdict's
;           exact shape, in a certificate parser.  Written `a ! -1`,
;           the full-width complement, which for a canonical cell is
;           canonical.  Mutation M7.
;        2-5. T0PrimCmp's four unsigned compares, `u<`, `u<=`, `u>`,
;           `u>=`, each spelled `T0Pop() ! $80000000` on both operands
;           so a SIGNED compare implements an UNSIGNED one.
;           DO NOT SURVIVE.  Bit 31 is not the sign bit here, so the
;           trick flips a middle bit and the comparison answers about
;           the wrong quantity - for example u<($80000000, $7FFFFFFF)
;           is FALSE and the naive port returns TRUE.  Rewritten as
;           `T0Pop() & #T0_W32` on both operands: two values in
;           0..2^32-1 held in a 64-bit signed register compare exactly,
;           with no trick at all.  This is the same rewrite bignum.pi4's
;           BnGt got and for the same reason.  Mutation M8.
;        6. The comparison TRUE mask, `T0Push($FFFFFFFF)`.
;           DOES NOT SURVIVE as a cell, though it survives most uses.
;           T0's true is int32 -1; on a Pico the constant $FFFFFFFF IS
;           -1 and here it is +4294967295.  It stays truthy, so
;           `jump-if` still works and a known-answer test that only
;           branches on comparisons cannot see it - but `true not`,
;           `true >>`, `true <` and storing true through set32 all
;           differ.  Written `T0Push(-1)`.  Mutation M6, and it is
;           killed by the opcode-conformance jobs and NOT by the PEM
;           proof, which is the point of having both.
;
;      SO: of the six sites, ZERO survive a naive width change as
;      CELLS, and one of the six (the true mask) survives every use the
;      PEM decoder makes of it.  That last distinction is why this file
;      claims nothing about survival by assertion - each of the six is a
;      mutation with a recorded expected verdict and the sweep is what
;      says so.
;
;      A T0 VM ALSO SIGN-EXTENDS ITS OWN LITERALS, and that is
;      T0NextS, audited under SHAPE 3 above: it needs no change, which
;      is the one piece of good news in this list.
;
;  ======================================================================
;   THE CONTEXT-RAM BOUNDS GUARD - FORUM TOPIC 517
;  ======================================================================
;
;  IT IS NOT AN ADDITION HERE.  The guard already lives in the portable
;  core: it was added to the 32-bit copies on 2026-08-22 and the record
;  of it is
;      RP2350/Examples/Diagnostics/rp2350T0vmBoundsProbe.pico2
;  whose report line ends "tid 517 fixed."  That probe is the silicon
;  witness for the guard's logic and it names where the guard belongs:
;  on EVERY t0_ram touch - T0RamGet, T0RamPut, and the GET8/SET8/GET16/
;  SET16/GET32/SET32 cases of T0PrimMem - never on the callers.
;
;  WHAT IT REFUSES AND WHY.  A T0 program COMPUTES its get8/set8/...
;  offsets out of the bytes it is parsing, and the bytes this engine
;  parses are X.509 certificates - the one input on this device a
;  stranger controls.  A bare indexed access lets a computed offset read
;  or WRITE whatever global sits beside the array and answer as though
;  nothing happened.
;
;  THE GUARD IS WIDTH-AWARE and it has TWO HALVES, because a guard that
;  refused everything would pass every out-of-range test and be useless:
;    REFUSALS   one past the end, far past the end, NEGATIVE offsets,
;               and the width cases - a 32-bit access three bytes from
;               the end and a 16-bit access one byte from the end, which
;               a check that looked only at the first byte would wave
;               through.
;    ACCEPTANCE the last LEGAL offset at every width still reads back
;               what was written.
;  Refusal is LOUD AND NAMED: t0_err = #T0ERR_RAM_BOUNDS (900) and
;  t0_ip = -1, so the very next T0Run() returns #T0_HALT and the host
;  sees a terminal state instead of a wrong answer.
;
;  ON THIS PART `addr < 0` ONLY DOES WORK BECAUSE A CELL IS
;  SIGN-EXTENDED.  See the cell width decision above; mutation M2
;  deletes that half and dies, and mutation M13 shows what a
;  zero-extended VM would have instead.
;
;  WHAT IS STILL UNGUARDED, SAID OUT LOUD.  data-get8 reads the constant
;  DATA block at `t0_datap + addr` with NO check, on every family.  The
;  VM is not told the block's length by any descriptor it has, and forum
;  517 is about context RAM, so this file does not invent a second
;  guard - it records the gap.  The DATA block is compiled-in constant
;  bytes, so a read off its end is a read of adjacent constants rather
;  than a write, and the T0 programs in scope index it only with
;  compile-time literals.  If x509 ever hands data-get8 a parsed offset,
;  that is the day this needs a descriptor and a check.
;
;  ======================================================================
;   WHAT x509.pi4 WILL NEED FROM THIS FILE
;  ======================================================================
;
;  CALL ORDER.  Include the generated x509_blob first (it defines
;  T0LoadX509 and the #T0N_* ids), then, once per chain:
;      T0LoadX509()          fills t0_cp / t0_datap / t0_caddrp / t0_opp
;                            / t0_interp / t0_entry
;      T0Start()             clears both stacks, t0_err, and enters the
;                            entry word
;      T0Run()               in a loop, servicing
;          #T0_NATIVE  -> run the word t0_native_id names, moving
;                         operands with T0Pop() / T0Push()
;          #T0_YIELD   -> feed the next chunk, or stop at a cert boundary
;          #T0_HALT    -> terminal; check t0_err
;  There is NO global to initialise before T0LoadX509(): every
;  descriptor is written by the loader and T0Start() resets the run
;  state.  T0Norm(v) is exported for a native that pushes a value wider
;  than 31 bits; none of x509's do.
;
;  TWO THINGS THAT WILL BITE, RECORDED HERE BECAUSE THEY ARE THIS
;  FILE'S BUSINESS AND NOT THAT FILE'S:
;
;    * THE X.509 BLOB IS GENERATED WITH t0gen's --native-ram, SO IT DOES
;      NOT USE t0_ram AND FORUM 517's GUARD NEVER RUNS FOR IT.  The six
;      context-memory opcodes are lifted as NATIVE words (see
;      #T0N_set8 = 24 in RP2350/Lib/x509_blob.pico2) because the
;      engine's context is 2 KB and this VM's region is 512 bytes, so
;      the engine owns its own array and services get8/set8/... itself.
;      In the 32-bit copies those accessors - Xr8, XrSet8, Xr16,
;      XrSet16 and the 32-bit pair, at RP2350/Lib/x509.pico2:200
;      onwards - are BARE INDEXED ACCESSES with no range test and no
;      width test, which is precisely the code shape forum 517
;      replaced, in the one module the guard was written for.  The Pi 4
;      copy must carry the guard in those accessors; do not assume this
;      file is protecting it.
;    * SHAPE 1 REACHES x509's PUBLIC API.  X509ValidateChain walks its
;      caller's address array with `PeekI(certsAddr + i * 4)`
;      (RP2350/Lib/x509.pico2:882).  PeekI reads EIGHT bytes here and a
;      cell-sized array element IS eight bytes, so that stride must
;      become 8 - or the array must be indexed rather than walked - and
;      the harness that builds it must declare `.i`, not `.w`.
;
;  ======================================================================
;   PROVEN BY
;  ======================================================================
;    python tools/check_tls_twins.py --cross t0vm
;    python tools/a64/a64_t0vm_check.py
;    python tools/a64/a64_t0vm_check.py --mutate
;  The gate imports its bytecode blob and its PEM/DER expectations from
;  the shared generators (tools/t0gen.py, tools/t0_pemproof_gen.py)
;  rather than carrying copies, and it splices the PEM driver
;  procedures - Base64Val, T0Native, DecodeCurrent - verbatim out of
;  tools/t0_pemproof_gen.py's emitted body, so "the Pi 4 is driven the
;  same way the Picos are" is a fact about the source.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====

; ----------------------------------------------------------------------
;  Return codes from T0Run().
; ----------------------------------------------------------------------
#T0_HALT   = 0
#T0_YIELD  = 1
#T0_NATIVE = 2

; ----------------------------------------------------------------------
;  Canonical primitive ids stored in the per-program OPMAP. The generator
;  translates each program's raw opcode numbers into these. Native words
;  are any id >= #T0_NATIVE_BASE; the host services those.
; ----------------------------------------------------------------------
#T0OP_ADD      = 1
#T0OP_SUB      = 2
#T0OP_NEG      = 3
#T0OP_MUL      = 4
#T0OP_DIV      = 5
#T0OP_UDIV     = 6
#T0OP_MOD      = 7
#T0OP_UMOD     = 8
#T0OP_LT       = 9
#T0OP_LE       = 10
#T0OP_GT       = 11
#T0OP_GE       = 12
#T0OP_EQ       = 13
#T0OP_NE       = 14
#T0OP_ULT      = 15
#T0OP_ULE      = 16
#T0OP_UGT      = 17
#T0OP_UGE      = 18
#T0OP_AND      = 19
#T0OP_OR       = 20
#T0OP_XOR      = 21
#T0OP_NOT      = 22
#T0OP_SHL      = 23
#T0OP_SHR      = 24
#T0OP_USHR     = 25
#T0OP_CO       = 26
#T0OP_DROP     = 27
#T0OP_DUP      = 28
#T0OP_SWAP     = 29
#T0OP_OVER     = 30
#T0OP_ROT      = 31
#T0OP_NROT     = 32
#T0OP_ROLL     = 33
#T0OP_PICK     = 34
#T0OP_EXECUTE  = 35
#T0OP_DATAGET8 = 36
#T0OP_GET8     = 37
#T0OP_SET8     = 38
#T0OP_GET16    = 39
#T0OP_SET16    = 40
#T0OP_GET32    = 41
#T0OP_SET32    = 42

#T0_NATIVE_BASE = 128

; ----------------------------------------------------------------------
;  Stack and state sizes. Flat global arrays, house style. The PEM decoder
;  needs only a few cells of each; X.509 and the handshake nest deeper, so
;  these are sized generously.
;
;  SHAPE 1: A CELL IS EIGHT BYTES HERE, NOT FOUR. The depths below are
;  the same NUMBERS the 32-bit copies use, deliberately - the machine
;  must nest exactly as deep on every family or a program that fits on
;  a Pico would not fit here - but t0_ds and t0_rs cost 2 KB and 4 KB
;  instead of 1 KB and 2 KB. On the R4 (32 KB) the whole engine budgets
;  ~20 KB and this was ~5 KB of it; here it is ~6.5 KB of a gigabyte,
;  which is why the depths were not cut. Nothing indexes either array
;  by byte, so the width costs memory and nothing else - see the
;  header's SHAPE 1 audit.
; ----------------------------------------------------------------------
#T0_DS_DEPTH = 256          ; data-stack cells
#T0_RS_DEPTH = 512          ; return-stack cells (frames + locals)
#T0_RAM_SIZE = 512          ; context RAM bytes (get8/set8 target region)

Global Dim t0_ds.i[#T0_DS_DEPTH]
Global Dim t0_rs.i[#T0_RS_DEPTH]
Global Dim t0_ram.a[#T0_RAM_SIZE]

; Machine registers (indexes/offsets, not host pointers).
Global t0_dp.i              ; data-stack pointer: index of next free cell
Global t0_rp.i             ; return-stack pointer: index of next free cell
Global t0_ip.i             ; instruction pointer: BYTE OFFSET into the code block (-1 = halted)

; Program descriptor - filled by the generated loader before T0Start().
Global t0_cp.i             ; code block base address
Global t0_datap.i          ; data block base address
Global t0_caddrp.i         ; caddr table base address (LE 16-bit pairs)
Global t0_opp.i            ; opmap base address (one byte per raw opcode)
Global t0_interp.i         ; T0_INTERPRETED threshold
Global t0_entry.i          ; entry-word slot

; Cross-call outputs.
Global t0_native_id.i      ; which native word, when T0Run() returns #T0_NATIVE
Global t0_err.i            ; 0 = ok; otherwise a loud fault code (see T0Run)

; ----------------------------------------------------------------------
;  THE CELL, AND THE ONE PROCEDURE THIS FILE ADDS.
;
;  A T0 cell is 32 bits and is stored SIGN-EXTENDED into the 64-bit host
;  word: every cell holds the int64 value of the int32 it represents, so
;  -1 is $FFFFFFFFFFFFFFFF and never $00000000FFFFFFFF. Under that
;  convention the host's 64-bit +, -, *, /, %, the signed compares, &,
;  |, ! and the arithmetic >> all agree EXACTLY with the int32
;  operations, and only the operations that can leave the int32 range
;  need bringing back.
;
;  T0Norm brings one back. It is the file's only addition to the
;  portable core and it is declared, with this reason, in
;  tools/check_tls_twins.py's A64_MODULES. It is called at exactly eight
;  sites - +, -, neg, *, /, <<, get32, and T0NextS's return - and the
;  header's audit says why each one needs it and why no other does.
;
;  A HOST NATIVE WORD pushing a value wider than 31 bits must push
;  T0Norm(v). Every native in scope pushes a byte, a small count or -1.
; ----------------------------------------------------------------------
#T0_W32 = $FFFFFFFF

Procedure.i T0Norm(v.i)
  ; Branchless sign-extend of the low 32 bits: fold bit 31 up to the
  ; sign. No branch, no CompilerIf, and it is the same three operations
  ; a 32-bit register performs for free.
  ProcedureReturn ((v & #T0_W32) ! $80000000) - $80000000
EndProcedure

; ----------------------------------------------------------------------
;  Data-stack API - also used by host native words.
; ----------------------------------------------------------------------
Procedure T0Push(v.i)
  t0_ds[t0_dp] = v
  t0_dp = t0_dp + 1
EndProcedure

Procedure.i T0Pop()
  t0_dp = t0_dp - 1
  ProcedureReturn t0_ds[t0_dp]
EndProcedure

Procedure.i T0Peek(n.i)
  ProcedureReturn t0_ds[t0_dp - 1 - n]
EndProcedure

; ----------------------------------------------------------------------
;  CONTEXT-RAM BOUNDS - the one check that stands between a hostile input
;  and the globals next door.
;
;  A T0 program COMPUTES its own get8/set8/get16/... offsets from the bytes
;  it is parsing, and the bytes this engine parses are certificates handed
;  over by a stranger. A bare indexed access into t0_ram therefore lets a
;  computed offset read - or WRITE - whatever global happens to sit beside
;  the array, and answer as if nothing happened. That is the silent-wrong
;  failure this project refuses on principle.
;
;  So every t0_ram touch goes through T0RamInRange first, and an offset
;  outside the array is a LOUD, NAMED refusal: #T0ERR_RAM_BOUNDS lands in
;  t0_err and the machine halts (t0_ip = -1), so the very next T0Run()
;  returns #T0_HALT and the host sees a terminal state instead of a wrong
;  answer. Same shape as the OID-length guard in the RSA PKCS#1 unpadder,
;  which refuses rather than let a length byte drive buffer writes.
;
;  n is the access width in bytes (1, 2 or 4). The highest byte touched is
;  addr + n - 1, so the last legal offset is #T0_RAM_SIZE - n; a 32-bit
;  access at #T0_RAM_SIZE - 1 is rejected, not truncated.
;
;  ON THIS PART `addr < 0` ONLY DOES WORK BECAUSE A CELL IS
;  SIGN-EXTENDED. addr arrives as a CELL the T0 program computed from
;  the bytes it is parsing, and a length subtraction that underflows
;  produces a negative one. Cells are sign-extended int32 here (see
;  T0Norm), so it really is negative, and THIS line is the only one that
;  refuses it - `addr > #T0_RAM_SIZE - n` does not fire on a negative.
;  Mutation M2 deletes this half and dies.
;  Under a zero-extended convention the same offset would arrive as a
;  large positive number: this line would become DEAD CODE THAT STILL
;  READS AS THOUGH IT WORKS, and the upper bound would refuse the access
;  by accident. Measured, not argued - mutation M13 makes T0Norm a
;  zero-extend and the crafted negative-offset blob is still refused, by
;  the other half. Not a hole; half a guard resting on an accident,
;  which is how one arrives.
; ----------------------------------------------------------------------
#T0ERR_RAM_BOUNDS = 900

Procedure.i T0RamInRange(addr.i, n.i)
  If addr < 0 Or addr > (#T0_RAM_SIZE - n)
    t0_err = #T0ERR_RAM_BOUNDS
    t0_ip = -1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  Context-RAM helpers, so a native word can share the get8/set8 region.
;  A refused read answers 0, but t0_err is already set and the machine is
;  already halted, so the 0 can never be mistaken for data.
; ----------------------------------------------------------------------
Procedure.i T0RamGet(addr.i)
  If T0RamInRange(addr, 1) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn t0_ram[addr] & 255
EndProcedure

Procedure T0RamPut(addr.i, v.i)
  If T0RamInRange(addr, 1) = 0
    ProcedureReturn
  EndIf
  t0_ram[addr] = v & 255
EndProcedure

; ----------------------------------------------------------------------
;  Bytecode readers. All operate on the global instruction pointer t0_ip
;  and the code base t0_cp, advancing t0_ip.
; ----------------------------------------------------------------------
Procedure.i T0NextByte()
  Protected b.i
  b = PeekA(t0_cp + t0_ip) & 255
  t0_ip = t0_ip + 1
  ProcedureReturn b
EndProcedure

; Unsigned 7-bit varint: high bit set means "more bytes follow".
Procedure.i T0NextU()
  Protected x.i
  Protected y.i
  x = 0
  Repeat
    y = PeekA(t0_cp + t0_ip) & 255
    t0_ip = t0_ip + 1
    ; SHAPE 3: a 7-bit continuation encoding shifts left repeatedly and
    ; a 32-bit register discarded the overflow for free. Masked so the
    ; accumulator holds the SAME NUMBER the 32-bit copies hold. No
    ; u-varint a T0 compiler emits comes close - they are local counts
    ; and local indices - but the mask costs one instruction and the
    ; alternative is an unenforced claim about the code block.
    x = ((x << 7) | (y & $7F)) & #T0_W32
    If y < $80
      Break
    EndIf
  ForEver
  ProcedureReturn x
EndProcedure

; Signed 7-bit varint. The accumulator is pre-loaded with all-ones when
; the sign bit (bit 6 of the first byte) is set, so the value arrives
; already sign-extended - which is exactly the int32 T0 emits.
;
; SHAPE 3, AND THE ONE PIECE OF GOOD NEWS IN THIS FILE: the accumulation
; needs NO mask, and that is proved rather than assumed. Seeded with 0
; or -1, the recursion x = x * 128 + g reconstructs the signed value at
; ANY register width, so for every literal a T0 compiler can emit - all
; of them int32-representable - the 64-bit answer IS the sign-extended
; 32-bit answer. Worked at the widest case: -2147483648 encodes as
; $78 $00 $00 $00 $00, and -1, -8, -1024, -131072, -16777216,
; -2147483648 is exactly the sequence the loop walks.
; The T0Norm on the RETURN is therefore not for a legal code block. It
; is so a MALFORMED one - a six-byte varint - cannot inject a cell wider
; than 32 bits into the machine. Mutation M12 removes it and is an
; expected survivor, with that argument recorded in the table.
Procedure.i T0NextS()
  Protected x.i
  Protected y.i
  Protected neg.i
  neg = (PeekA(t0_cp + t0_ip) >> 6) & 1
  x = 0 - neg
  Repeat
    y = PeekA(t0_cp + t0_ip) & 255
    t0_ip = t0_ip + 1
    x = (x << 7) | (y & $7F)
    If y < $80
      Break
    EndIf
  ForEver
  ProcedureReturn T0Norm(x)
EndProcedure

; caddr[idx] - the code offset of interpreted word (slot = idx + t0_interp),
; stored as a little-endian 16-bit pair.
Procedure.i T0CaddrGet(idx.i)
  Protected lo.i
  Protected hi.i
  lo = PeekA(t0_caddrp + idx * 2) & 255
  hi = PeekA(t0_caddrp + idx * 2 + 1) & 255
  ProcedureReturn lo | (hi << 8)
EndProcedure

; ----------------------------------------------------------------------
;  Enter an interpreted word: reserve its locals, push a return frame, and
;  jump to its body. The frame packs the return offset in its low 16 bits
;  and the local count in its high 16 bits, exactly as the generated C
;  interpreter does; a return offset of 0 is the top-of-program sentinel.
; ----------------------------------------------------------------------
Procedure T0EnterSlot(slot.i)
  Protected newip.i
  Protected lnum.i
  Protected retoff.i
  newip = T0CaddrGet(slot - t0_interp)
  retoff = t0_ip                       ; return address = current ip
  t0_ip = newip                        ; read the local count from the word head
  lnum = T0NextU()
  newip = t0_ip                         ; body starts after the local count
  t0_ip = retoff                        ; restore for the frame word
  t0_rp = t0_rp + lnum                  ; reserve locals below the frame
  t0_rs[t0_rp] = (t0_ip & $FFFF) | (lnum << 16)
  t0_rp = t0_rp + 1
  t0_ip = newip
EndProcedure

; ----------------------------------------------------------------------
;  Start a loaded program: clear the stacks and enter the entry word.
; ----------------------------------------------------------------------
Procedure T0Start()
  t0_dp = 0
  t0_rp = 0
  t0_ip = 0
  t0_err = 0
  T0EnterSlot(t0_entry)
EndProcedure

; ----------------------------------------------------------------------
;  Primitive groups. The dispatch is SPLIT into small procedures on
;  purpose: one giant Select builds a branch whose target is thousands of
;  bytes away, and the RA4M1 assembler's branch relaxation cannot reach a
;  conditional target past ~2 KB (the RP2040/RP2350 assemblers relax it
;  fine - this is an RA4M1 backend limit, noted in the landing report).
;  Small procedures keep every branch target near, and read better anyway.
;  All state is global, so a group procedure needs no arguments beyond the
;  canonical op id.
; ----------------------------------------------------------------------
; SHAPE 4, WEARING A DIFFERENT HAT. BearSSL computes T0's +, -, neg, *
; and / in uint32_t, so they are DEFINED to wrap at 32 bits; a 64-bit
; register does not wrap and the results stop being cells. Each of the
; five is brought back through T0Norm. `%` is NOT, and that is a finding
; rather than an omission: |a % b| < |b| <= 2^31, so the remainder of
; two in-range cells is always in range, including the INT32_MIN % -1
; case, which is 0 at both widths.
Procedure T0PrimArith(op.i)
  Protected a.i
  Protected b.i
  Select op
    Case #T0OP_ADD
      b = T0Pop()
      a = T0Pop()
      T0Push(T0Norm(a + b))
    Case #T0OP_SUB
      b = T0Pop()
      a = T0Pop()
      T0Push(T0Norm(a - b))
    Case #T0OP_NEG
      a = T0Pop()
      T0Push(T0Norm(0 - a))
    Case #T0OP_MUL
      b = T0Pop()
      a = T0Pop()
      T0Push(T0Norm(a * b))
    Case #T0OP_DIV
      b = T0Pop()
      a = T0Pop()
      T0Push(T0Norm(a / b))
    Case #T0OP_MOD
      b = T0Pop()
      a = T0Pop()
      T0Push(a % b)
    Default
      ; #T0OP_UDIV / #T0OP_UMOD - deferred (no program in scope uses them).
      t0_err = 1000 + op
      t0_ip = -1
  EndSelect
EndProcedure

; A comparison result is 0 (false) or -1 (true), which is what T0's
; comparison words push. r carries 1/0 out of the per-op test; the tail
; turns it into the full-width mask once.
;
; THE FIFTH SHAPE, TWICE OVER.
;   * The 32-bit copies push the TRUE mask as the constant $FFFFFFFF,
;     which on them IS -1. Here it is +4294967295: still truthy, so
;     every `jump-if` still works and a known-answer test that only
;     branches on comparisons cannot see the difference - but `true
;     not`, `true >>`, `true <` and `true set32` all differ. Written
;     -1, which is the cell. Mutation M6.
;   * The unsigned compares are the dangerous half. The 32-bit copies
;     flip bit 31 of both operands with `! $80000000` so a SIGNED
;     comparison implements an UNSIGNED one. BIT 31 IS NOT THE SIGN BIT
;     HERE - it is a middle bit - so the trick answers about the wrong
;     quantity, and u< ($80000000, $7FFFFFFF) comes back TRUE when it
;     is FALSE. This is the shape that made GcmDecrypt accept a forged
;     tag. Rewritten by masking both operands to 32 bits: two values in
;     0..2^32-1 in a 64-bit signed register compare exactly, with no
;     trick at all. Same rewrite, same reason, as bignum.pi4's BnGt.
;     Mutation M8.
Procedure T0PrimCmp(op.i)
  Protected a.i
  Protected b.i
  Protected r.i
  r = 0
  Select op
    Case #T0OP_LT
      b = T0Pop()
      a = T0Pop()
      If a < b
        r = 1
      EndIf
    Case #T0OP_LE
      b = T0Pop()
      a = T0Pop()
      If a <= b
        r = 1
      EndIf
    Case #T0OP_GT
      b = T0Pop()
      a = T0Pop()
      If a > b
        r = 1
      EndIf
    Case #T0OP_GE
      b = T0Pop()
      a = T0Pop()
      If a >= b
        r = 1
      EndIf
    Case #T0OP_EQ
      b = T0Pop()
      a = T0Pop()
      If a = b
        r = 1
      EndIf
    Case #T0OP_NE
      b = T0Pop()
      a = T0Pop()
      If a <> b
        r = 1
      EndIf
    Case #T0OP_ULT
      b = T0Pop() & #T0_W32
      a = T0Pop() & #T0_W32
      If a < b
        r = 1
      EndIf
    Case #T0OP_ULE
      b = T0Pop() & #T0_W32
      a = T0Pop() & #T0_W32
      If a <= b
        r = 1
      EndIf
    Case #T0OP_UGT
      b = T0Pop() & #T0_W32
      a = T0Pop() & #T0_W32
      If a > b
        r = 1
      EndIf
    Case #T0OP_UGE
      b = T0Pop() & #T0_W32
      a = T0Pop() & #T0_W32
      If a >= b
        r = 1
      EndIf
  EndSelect
  If r <> 0
    T0Push(-1)
  Else
    T0Push(0)
  EndIf
EndProcedure

Procedure T0PrimBit(op.i)
  Protected a.i
  Protected b.i
  Protected c.i
  Protected x.i
  Protected mask.i
  Select op
    Case #T0OP_AND
      b = T0Pop()
      a = T0Pop()
      T0Push(a & b)
    Case #T0OP_OR
      b = T0Pop()
      a = T0Pop()
      T0Push(a | b)
    Case #T0OP_XOR
      b = T0Pop()
      a = T0Pop()
      T0Push(a ! b)
    Case #T0OP_NOT
      a = T0Pop()
      ; THE FIFTH SHAPE, AT ITS WORST. `a ! $FFFFFFFF` leaves bits
      ; 32..63 untouched: not(0) would be +4294967295 instead of -1,
      ; and not(-1) would be $FFFFFFFF00000000, which is NOT ZERO - so
      ; a `jump-if-not` on it takes the wrong branch. That is the
      ; GcmDecrypt forged-tag verdict, in a certificate parser. The
      ; full-width complement of a cell IS a cell.
      T0Push(a ! -1)
    Case #T0OP_SHL
      c = T0Pop()
      x = T0Pop()
      ; SHAPE 3. A 32-bit register discarded at bit 31 for free.
      ; For c of 32..63 both widths give 0, which T0Norm reproduces.
      ; For c >= 64 AArch64's shift uses only the low 6 bits and would
      ; give x back where a 32-bit ARM gives 0 - no T0 program in scope
      ; shifts that far, and this is recorded rather than guarded,
      ; because inventing a clamp the 32-bit copies do not have is a
      ; divergence with nothing behind it.
      T0Push(T0Norm(x << c))
    Case #T0OP_SHR
      c = T0Pop()
      x = T0Pop()
      T0Push(x >> c)                 ; arithmetic, matches T0's int32 >>
    Case #T0OP_USHR
      c = T0Pop()
      x = T0Pop()
      If c <= 0
        T0Push(x)
      ElseIf c >= 32
        T0Push(0)
      Else
        ; SURVIVES THE WIDTH CHANGE UNCHANGED, and it is worth saying
        ; why: for a canonical cell x and c in 1..31 the arithmetic
        ; `>>` smears the sign as far as bit 63, and the mask - at most
        ; $7FFFFFFF, so a small positive at either width - clears every
        ; one of those bits along with the sign bits inside the low 32.
        ; The result is in 0..2^31-1, which is already a cell.
        ; Mutation M19 removes the mask and dies.
        mask = (1 << (32 - c)) - 1    ; clear the sign bits >> drags in
        T0Push((x >> c) & mask)
      EndIf
  EndSelect
EndProcedure

Procedure T0PrimStack(op.i)
  Protected a.i
  Protected c.i
  Protected x.i
  Select op
    Case #T0OP_DROP
      T0Pop()
    Case #T0OP_DUP
      T0Push(T0Peek(0))
    Case #T0OP_SWAP
      a = t0_ds[t0_dp - 2]
      t0_ds[t0_dp - 2] = t0_ds[t0_dp - 1]
      t0_ds[t0_dp - 1] = a
    Case #T0OP_OVER
      T0Push(T0Peek(1))
    Case #T0OP_ROT
      ; ( a b c -- b c a )
      a = t0_ds[t0_dp - 3]
      t0_ds[t0_dp - 3] = t0_ds[t0_dp - 2]
      t0_ds[t0_dp - 2] = t0_ds[t0_dp - 1]
      t0_ds[t0_dp - 1] = a
    Case #T0OP_NROT
      ; ( a b c -- c a b )
      a = t0_ds[t0_dp - 1]
      t0_ds[t0_dp - 1] = t0_ds[t0_dp - 2]
      t0_ds[t0_dp - 2] = t0_ds[t0_dp - 3]
      t0_ds[t0_dp - 3] = a
    Case #T0OP_ROLL
      ; ( x_n ... x_0 n -- x_(n-1) ... x_0 x_n )
      a = T0Pop()                     ; n
      x = t0_ds[t0_dp - 1 - a]        ; x_n
      c = a
      While c > 0
        t0_ds[t0_dp - 1 - c] = t0_ds[t0_dp - c]
        c = c - 1
      Wend
      t0_ds[t0_dp - 1] = x
    Case #T0OP_PICK
      a = T0Pop()
      T0Push(T0Peek(a))
  EndSelect
EndProcedure

Procedure T0PrimMem(op.i)
  Protected addr.i
  Protected x.i
  Select op
    Case #T0OP_DATAGET8
      addr = T0Pop()
      T0Push(PeekA(t0_datap + addr) & 255)
    Case #T0OP_GET8
      addr = T0Pop()
      If T0RamInRange(addr, 1) = 0
        T0Push(0)
      Else
        T0Push(t0_ram[addr] & 255)
      EndIf
    Case #T0OP_SET8
      addr = T0Pop()
      x = T0Pop()
      If T0RamInRange(addr, 1) <> 0
        t0_ram[addr] = x & 255
      EndIf
    Case #T0OP_GET16
      addr = T0Pop()
      If T0RamInRange(addr, 2) = 0
        T0Push(0)
      Else
        T0Push((t0_ram[addr] & 255) | ((t0_ram[addr + 1] & 255) << 8))
      EndIf
    Case #T0OP_SET16
      addr = T0Pop()
      x = T0Pop()
      If T0RamInRange(addr, 2) <> 0
        t0_ram[addr] = x & 255
        t0_ram[addr + 1] = (x >> 8) & 255
      EndIf
    Case #T0OP_GET32
      addr = T0Pop()
      If T0RamInRange(addr, 4) = 0
        T0Push(0)
      Else
        ; SHAPE 3, AND NOT COSMETIC. The top byte shifts to bit 24..31,
        ; so a context word with bit 31 set assembles to at most
        ; $FF000000 - NEGATIVE on a 32-bit register and POSITIVE here.
        ; Without T0Norm a get32 of such a word comes back as
        ; +4278190080 and the very next signed compare or `>>` in the
        ; T0 program takes the other branch. Mutation M9.
        T0Push(T0Norm((t0_ram[addr] & 255) | ((t0_ram[addr + 1] & 255) << 8) | ((t0_ram[addr + 2] & 255) << 16) | ((t0_ram[addr + 3] & 255) << 24)))
      EndIf
    Case #T0OP_SET32
      addr = T0Pop()
      x = T0Pop()
      If T0RamInRange(addr, 4) <> 0
        t0_ram[addr] = x & 255
        t0_ram[addr + 1] = (x >> 8) & 255
        t0_ram[addr + 2] = (x >> 16) & 255
        t0_ram[addr + 3] = (x >> 24) & 255
      EndIf
  EndSelect
EndProcedure

; ----------------------------------------------------------------------
;  The fixed control opcodes 0..6. Returns 1 if the program halted (top
;  frame returned), else 0.
; ----------------------------------------------------------------------
Procedure.i T0Control(t0x.i)
  Protected a.i
  Protected off.i
  Protected frame.i
  Select t0x
    Case 0            ; ret
      t0_rp = t0_rp - 1
      frame = t0_rs[t0_rp]
      t0_rp = t0_rp - ((frame >> 16) & $FFFF)
      off = frame & $FFFF
      If off = 0
        t0_ip = -1
        ProcedureReturn 1
      EndIf
      t0_ip = off
    Case 1            ; literal constant
      T0Push(T0NextS())
    Case 2            ; read local
      a = T0NextU()
      T0Push(t0_rs[t0_rp - 2 - a])
    Case 3            ; write local
      a = T0NextU()
      t0_rs[t0_rp - 2 - a] = T0Pop()
    Case 4            ; jump
      off = T0NextS()
      t0_ip = t0_ip + off
    Case 5            ; jump if
      off = T0NextS()
      a = T0Pop()
      If a <> 0
        t0_ip = t0_ip + off
      EndIf
    Case 6            ; jump if not
      off = T0NextS()
      a = T0Pop()
      If a = 0
        t0_ip = t0_ip + off
      EndIf
  EndSelect
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  The dispatch loop. Runs until the program halts, yields, or reaches a
;  native word; returns the reason. See the CONTRACT header.
; ----------------------------------------------------------------------
Procedure.i T0Run()
  Protected t0x.i
  Protected op.i

  If t0_ip < 0
    ProcedureReturn #T0_HALT
  EndIf

  Repeat
    t0x = T0NextByte()

    If t0x <= 6
      If T0Control(t0x) <> 0
        ProcedureReturn #T0_HALT
      EndIf

    ElseIf t0x < t0_interp
      op = PeekA(t0_opp + t0x) & 255
      If op >= #T0_NATIVE_BASE
        t0_native_id = op - #T0_NATIVE_BASE
        ProcedureReturn #T0_NATIVE
      ElseIf op = #T0OP_CO
        ProcedureReturn #T0_YIELD
      ElseIf op = #T0OP_EXECUTE
        T0EnterSlot(T0Pop())
      ElseIf op <= 8
        T0PrimArith(op)
      ElseIf op <= 18
        T0PrimCmp(op)
      ElseIf op <= 25
        T0PrimBit(op)
      ElseIf op <= 34
        T0PrimStack(op)
      ElseIf op <= 42
        T0PrimMem(op)
      Else
        ; A primitive this VM does not implement. Loud stop.
        t0_err = 1000 + op
        t0_ip = -1
        ProcedureReturn #T0_HALT
      EndIf
      If t0_ip < 0
        ProcedureReturn #T0_HALT       ; a group procedure raised a fault
      EndIf

    Else
      ; raw opcode >= t0_interp: call an interpreted word
      T0EnterSlot(t0x)
    EndIf
  ForEver
EndProcedure

; ==== PORTABLE CORE A64 END ====
