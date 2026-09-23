; ======================================================================
;  sha256.pi4 - SHA-256, ON THE RASPBERRY PI 4 (BCM2711, AArch64)
; ======================================================================
;
;  Translated from BearSSL (c) 2016 Thomas Pornin - MIT licence.
;  The notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;
;     XIncludeFile "Anvil/Core/sha256.pbi"
;
;
;  SHA-256 (FIPS 180-4). This is RP2350/Lib/sha256.pico2's design on a
;  64-bit target. The names and the shape are deliberately identical -
;  Sha256Begin(), Sha256Update(), Sha256End(), Sha256Of(),
;  Sha256Snapshot(), Sha256Restore() - and the 104-byte snapshot image is
;  byte-for-byte the same layout, so a transcript hash written against
;  one family works against the other and a program ports by changing an
;  include line.
;
;  API (module-global context - one digest in progress at a time):
;    Sha256Begin()                 start a fresh digest
;    Sha256Update(src.i, len.i)    absorb len bytes at address src
;    Sha256End(dst.i)              finish; writes 32 bytes at dst
;    Sha256Of(src.i, len.i, dst.i) the one-shot: Begin + Update + End
;    Sha256Snapshot(dst.i)         save the 104-byte running state
;    Sha256Restore(src.i)          reload a 104-byte running state
;
;  DEPENDENCIES: NONE. This file includes no other library, per the house
;  rule - a library never includes a library, the MAIN file lists what it
;  needs. It touches no peripheral and reads no register.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO. The pragma
;  below is not file-scoped - every variable compiled after this include
;  must be declared before use as well. It is a loud error, not a silent
;  change, which is why it stays; a requirement a library puts on its
;  caller belongs in the header the caller reads.
;
;  CONSTANT TIME. SHA-256 has no data-dependent branch and no
;  secret-indexed table; the round function here is straight-line and
;  every control decision is driven by LENGTH, never by message bytes.
;
;  ======================================================================
;   .i IS 64 BITS HERE. WHAT THAT ACTUALLY BREAKS - MEASURED, NOT GUESSED
;  ======================================================================
;
;  SHA-256 IS DEFINED ON 32-BIT WORDS. Every addition in FIPS 180-4 is
;  "addition modulo 2^32" and every rotate is a rotate of a 32-bit word.
;  On the RP2040, the RP2350 and the RA4M1, .i is four bytes and both of
;  those came FREE. On this target .i is EIGHT bytes (2026-08-24), and
;  the obvious worry is that every one of them is now silently wrong.
;
;  THE OBVIOUS WORRY IS MOSTLY NOT TRUE, AND SAYING SO IS THE HONEST
;  RESULT. Each suspect change was BUILT AS A DELIBERATELY BROKEN
;  VARIANT and run against the full known-answer set on the project's
;  A64 oracle. A claim in this header that says "would be wrong" was
;  watched being wrong; a claim that says "reasoning" was not. The
;  scoreboard, out of 23 vectors:
;
;    variant under test                                      failures
;    ----------------------------------------------------    --------
;    D  hash words walked with PeekL and a stride of 4          23/23
;       (the RP2350 spelling, unchanged)
;    E  message bytes read with PeekB instead of PeekA          16/23
;    C  RP2350's shift spelling AND every 32-bit mask on
;       the additions removed - i.e. a straight copy-paste       0/23
;    B  mask-first shifts kept, addition masks removed           0/23
;    A  RP2350's shift spelling kept, addition masks kept        0/23
;    F  RP2350's hand-rolled 32-bit counter carry                0/23
;
;  SO THE TWO THINGS THAT ACTUALLY BREAK A DIGEST ARE THE STRIDE AND
;  THE SIGN OF A BYTE. Both are below. The masking is third, and it is
;  a weaker claim than it looks - which is exactly why it is written
;  down rather than taken as read.
;
;  ---- 1. THE STRIDE. FATAL, AND PROVED FATAL. ------------------------
;
;  The RP2350 file passes the eight hash words to the compression
;  function BY ADDRESS and reads them with PeekL(hv + i * 4), because
;  there Dim Sha256H.i[8] is 32 bytes. HERE IT IS 64 BYTES. Measured,
;  not assumed: @Sha256H[1] - @Sha256H[0] is 8 on this backend.
;
;  A straight copy of PeekL(hv + 4) reads THE HIGH HALF OF H[0] as if it
;  were H[1]. Nothing faults. Variant D above is exactly that file, and
;  it hashes the empty string to
;
;      4478bdc91db7bd556b599c72e04d17ce510e527f9b05688c1f83d9ab5be0cd19
;
;  which is deterministic, is stable across runs, round-trips through
;  Snapshot/Restore, and is not SHA-256. Note the tail: the last four
;  words are the FIPS initial values 510E527F 9B05688C 1F83D9AB
;  5BE0CD19, still sitting there untouched, because H[4..7] were never
;  read or written. That is the shape this bug makes.
;
;  So the state is walked with PeekI/PokeI and a stride of
;  #SHA256_HWORD. PeekI moves exactly one .i, which is exactly one array
;  element, so the accessor and the stride agree BY CONSTRUCTION rather
;  than by anyone remembering to keep two numbers in step.
;
;  The address-passing design is kept because it is what lets End() run
;  the compression on a scratch COPY of H while the live context is left
;  untouched - which is what makes Snapshot-after-End meaningful.
;
;  ---- 2. RAW BYTES ARE READ WITH PeekA, NEVER PeekB. -----------------
;
;  Ruled 2026-08-25: PeekB/PeekC/PeekW follow their type letters and
;  SIGN-EXTEND on every backend; PeekA and PeekU are the unsigned
;  spellings. A byte of $80 read with PeekB is -128, and on a 64-bit .i
;  that is $FFFFFFFFFFFFFF80 - so ORing it into a word does not set the
;  low eight bits, it sets thirty-two of them.
;
;  Variant E is this file with PeekB in the word-assembly line and
;  nothing else changed. 16 of 23 vectors fail. The 7 that pass are
;  instructive rather than reassuring: they are the cases where the only
;  byte with bit 7 set is the $80 pad byte and it lands in the TOP octet
;  of its word, where sign extension happens to leave the low 32 bits
;  right. The empty message is one of them. A test set that only hashed
;  short ASCII would have gone green.
;
;  Every raw byte read in this file - message bytes, restored state
;  bytes, key bytes in the files that build on it - is PeekA. The
;  trailing "& 255" on each one is redundant under that ruling and is
;  kept anyway: it costs one instruction the optimiser can see through,
;  and it states the width at the point of use.
;
;  ---- 3. THE BYTE COUNTER. BROKEN, BUT NOT PROVABLE FROM THIS BENCH. -
;
;  The RP2350 copy detects the 32-bit wrap of its byte counter by
;  flipping both sign bits and comparing, which is the standard trick
;  for an unsigned compare on a machine with no wider integer. ON THIS
;  TARGET THE LOW WORD NEVER WRAPS, so the comparison never fires, the
;  high word never increments, and the padded bit length in Sha256End()
;  is short by 2^32 bits.
;
;  Variant F is that trick, restored. IT PASSES ALL 23 VECTORS, because
;  reaching the defect needs a message of 4 GiB or more and this bench
;  cannot run one. THIS ONE IS REASONING, NOT A REPRODUCTION, and it is
;  labelled that way deliberately. Sha256Update() does the sum once at
;  full width instead; see its comment.
;
;  ---- 4. THE 32-BIT MASKS. KEPT, AND HERE IS THE HONEST CASE FOR THEM.
;
;  THE INVARIANT THIS FILE MAINTAINS:
;
;      EVERY VALUE THAT REPRESENTS A 32-BIT SHA-256 WORD IS HELD AS A
;      CLEAN NON-NEGATIVE NUMBER IN 0..$FFFFFFFF, AND EVERY OPERATION
;      THAT CAN LEAVE THAT RANGE IS MASKED WITH #SHA256_W32 IMMEDIATELY.
;
;  NO KNOWN-ANSWER TEST CAN TELL THAT INVARIANT FROM ITS ABSENCE.
;  Variants A, B and C say so: strip every addition mask, restore the
;  RP2350 shift spelling, do both at once - 23 of 23 still pass. It is
;  worth understanding WHY, because the reason is the thing that would
;  stop being true if someone edited this file:
;
;    * addition modulo 2^64 agrees with addition modulo 2^32 on the low
;      32 bits, and a carry only ever propagates UPWARD, so rubbish
;      above bit 31 can never reach a bit below it;
;    * a left shift has the same property;
;    * the RP2350's Sha256Shr masks with ((1 << (32 - n)) - 1), which is
;      EXACTLY the width of the surviving field, so the rubbish that a
;      right shift drags down from bits 32+ lands one bit above the mask
;      and is cut. That mask is better than it looks;
;    * and every value that finally leaves the algorithm leaves through
;      "& 255" on a bit below 32.
;
;  Four separate arguments, each of which has to keep holding. The masks
;  replace all four with one that can be checked a line at a time. That
;  is the whole case for them, it is a REVIEWABILITY case and not a
;  correctness case, and the measured cost of buying it is 1.5% more
;  instructions (2,739,467 steps against 2,698,283 over the vector set).
;
;  Do not remove them for speed. Equally, if you are hunting a wrong
;  digest, DO NOT START HERE - start at the stride and the byte signs,
;  which are the two that have ever actually been wrong.
;
;  Where the masks are and are not:
;
;    Sha256Shr    masks the INPUT, then shifts - correct for any x, not
;                 only a clean one.
;    Sha256Rotr   masks the OUTPUT; the left half, x << (32 - n), is
;                 what spills. n is 2,6,7,11,13,17,18,19,22,25 at every
;                 call site - never 0 and never 32 - so 32-n is always a
;                 legal 1..31.
;    Ch, Maj,
;    Bsg0/1,
;    Ssg0/1       NOT masked, on purpose: bitwise and XOR of clean words
;                 are clean. A mask here would imply one is needed, and
;                 which operations need one is the whole question.
;    W[16..63]    four additions, masked once on the total - the sum
;                 cannot approach 2^63, so one mask equals four.
;    W[0..15]     four zero-extended bytes; cannot exceed 32 bits.
;    t1, t2,
;    e, a         masked once each.
;    H[i] += x    masked on the way back into the state.
;    bit length   masked, but see Sha256End - those two are the weakest
;                 of the lot and the comment there says so.
;
;  ---- 5. FOUR-BYTE READS USE PeekN. PeekL WOULD BE THE SAME BUG AS
;          PeekB, ONE WIDTH UP. ---------------------------------------
;
;  The unsigned ladder was completed on 2026-08-25 with .n, an unsigned
;  32-bit type, and PeekN/PokeN. In the same change PeekL STOPPED being
;  the family's exception and now SIGN-EXTENDS like every other Peek
;  named after a signed type. Measured here, not taken from the
;  changelog: PeekN of $DEADBEEF gives $DEADBEEF, PeekL of the same four
;  bytes gives $FFFFFFFFDEADBEEF.
;
;  THAT MATTERS IN THIS FILE MORE THAN ALMOST ANYWHERE. Half the FIPS
;  180-4 round constants have bit 31 set - $B5C0FBCF, $E9B5DBA5,
;  $D807AA98 and thirty others - and so do three of the eight initial
;  hash values. Read with PeekL every one of them would arrive negative.
;  So every four-byte read of a constant or of saved state here is
;  PeekN, and every four-byte write of one is PokeN. There are SEVEN
;  such sites: the K-table load in Sha256Begin, three writes in
;  Sha256Snapshot, and three reads in Sha256Restore.
;
;  The "& #SHA256_W32" on each of those reads is now redundant - PeekN
;  zero-extends by definition - and is kept for the same reason the
;  "& 255" after each PeekA is kept: the invariant above says every
;  32-bit value is masked at the point it enters, and an exception "for
;  the ones where the accessor already does it" is an exception a future
;  edit gets to interpret.
;
;  ---- 6. WHY THIS FILE DOES NOT DECLARE A SINGLE .n VARIABLE ---------
;
;  .n IS THE TYPE SHA-256 IS DEFINED ON, and the obvious move on the day
;  it landed was to write the compression function in it and delete
;  every mask. THAT WOULD HAVE BEEN WRONG, and the reason is measured:
;
;      construct                            truncates to 32 bits?
;      ---------------------------------    ---------------------
;      .n ARRAY element store                        YES
;      PokeN                                         YES
;      .n GLOBAL scalar store                        NO   ($1FFFFFFFF
;                                                          stored and
;                                                          read back)
;      .n LOCAL store                                NO
;      Procedure.n return value                      NO
;      .n array read / PeekN                zero-extends, 4 bytes
;      unsigned compare on .n                        works
;
;  So .n on this backend is an unsigned LOAD, STORE, COMPARE and DIVIDE.
;  IT IS NOT A 32-BIT ARITHMETIC TYPE: "x.n = $FFFFFFFF : x = x + 2"
;  leaves $100000001 in x, not 1. A rotate written the way the standard
;  writes it would not wrap, and a reader would have every reason to
;  believe it did.
;
;  Using it for the state would therefore have put the masking IN THE
;  TYPE at the array stores and IN THE SOURCE everywhere else - the one
;  arrangement guaranteed to hide a wrong digest, because the rule for
;  where to look would have had an exception in it.
;
;  THE RULE THIS FILE FOLLOWS INSTEAD, and it has no exceptions:
;
;      ARITHMETIC IS .i, AND EVERY 32-BIT CONFINEMENT IS WRITTEN OUT.
;      .n APPEARS ONLY AS PeekN/PokeN, WHERE IT CHOOSES THE WIDTH AND
;      SIGNEDNESS OF A MEMORY ACCESS AND DOES NO ARITHMETIC AT ALL.
;
;  Grep this file for ".n" and you will find no declaration - only the
;  seven accessors. That is the whole story and it is meant to be
;  checkable in one grep.
;
;  (The .n global-scalar row above looks like a compiler defect rather
;  than a design: an .n GLOBAL is given eight bytes and does not
;  truncate, while an element of an .n ARRAY is given four and does.
;  Nothing in this file depends on either, but the next file to reach
;  for .n should know before it does.)
;
;  ======================================================================
;   THERE IS NO HARDWARE SHA BLOCK ON THIS PART, AND THERE WAS NONE TO
;   REMOVE FROM THE SOURCE EITHER
;  ======================================================================
;
;  The port brief warned that RP2350/Lib/sha256.pico2 drives the
;  RP2350's hardware SHA-256 accelerator and that those register pokes
;  would land in DRAM here, because $4xxxxxxx is memory on a Pi 4 and a
;  stray write there corrupts silently rather than faulting.
;
;  THAT IS NOT WHAT THE SOURCE FILE CONTAINS, and it was checked rather
;  than assumed. RP2350/Lib/sha256.pico2 has exactly ONE occurrence of a
;  SHA register name in its whole 426 lines, on line 52, inside a
;  comment:
;
;    ";  NOTE FOR THE PLAN: the RP2350 has a hardware SHA-256 block
;     ;  (SHA256_CSR/WDATA/SUM0 in rp2350_registers.def). A later
;     ;  .pico2-only accelerated path behind this same API is available
;     ;  if wanted; it is not in this module."
;
;  There is no accelerator path, no fallback flag, and no register
;  access of any kind: grepping that file for SHA256_, for CSR/WDATA/
;  SUM0 and for any $4xxxxxxx literal returns that one comment line and
;  four lines of the FIPS 180-4 K table whose constants merely happen to
;  begin with a 4 nibble ($428A2F98, $4A7484AA, $4D2C6DFC, $4ED8AA4A).
;  Those are round constants, not addresses.
;
;  So the software implementation below is not a REPLACEMENT for an
;  accelerated path - it is the same software implementation the RP2350
;  already ships, moved to a 64-bit word model. THE COMMENT DID NOT COME
;  ACROSS, because on the BCM2711 there is no equivalent block for a
;  future path to use: the peripheral manual's device list has no hash
;  engine, and the only cryptographic-adjacent block the device tree
;  names is rng@7e104000, which is a random number generator and not a
;  hash. See RaspberryPi4/Lib/drbg.pi4's header for what is and is not
;  known about that one.
;
;  ======================================================================
;   THE K TABLE IS REACHED WITH ?label, NOT WITH Restore/Read
;  ======================================================================
;
;  The RP2350 copy walks its round-constant table with Restore + Read.l,
;  and pays for it: Read and Restore share ONE PROGRAM-WIDE cursor, so
;  that file has to cache the table behind a Sha256KReady flag and its
;  self-tests have to call Sha256Begin() as a "warm-up" before walking
;  their own data sections. That is a real trap for a caller and it has
;  nothing to do with hashing.
;
;  Read.l WAS VERIFIED TO WORK on this backend before it was rejected -
;  a probe read $11223344 back out of a Data.l table correctly - so this
;  is a choice and not a workaround for a missing feature. The table is
;  taken by address with ?Sha256KTable and indexed with PeekN, which is
;  the same thing RaspberryPi4/Lib/display.pi4 does with its font and
;  for the same reason: an indexed table wants an index, not a cursor
;  that somebody else's loop can move.
;
;  The one-time load behind Sha256KReady is kept even so, because it is
;  free and it keeps Begin() cheap.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT - 2026-08-25
;  ======================================================================
;
;  PROVEN, by known-answer test - the only kind of test that counts for
;  a hash - under the project's own A64 oracle, tools/a64/a64_interp.py,
;  running a real image built for -t pi4 at $200000:
;
;    * FIPS 180-4: the empty message, "abc", and the 56-byte
;      "abcdbcdecdef..." multi-block message.
;        ""      e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
;        "abc"   ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
;        56-byte 248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1
;    * Block-boundary lengths 55, 56, 63, 64, 65, 119, 127 and 128 of
;      'a' - the padding cases, including the one where the length
;      spills into a second block.
;    * Every fixed vector run BOTH one-shot AND fed in 1-, 3-, 7- and
;      64-byte chunks, so a split point that changed an answer shows.
;      23 assertions in that set, all passing.
;    * Snapshot/Restore across a mid-block seam (37 + 63 of 'a')
;      matching the one-shot digest of the same 100 bytes.
;    * ALL 200 of the random-length vectors the other three families are
;      gated on (RP2350/Examples/Diagnostics/sha256Vectors.pico2),
;      lengths 0 to 300, one-shot. 200 of 200.
;
;  Every expected digest came from FIPS 180-4 or from the vectors the
;  RP2350/RP2040/RA4M1 stacks already treat as authoritative
;  (RP2350/Examples/Diagnostics/sha256SelfTest.pico2 and its generated
;  vector file), never from running this file and writing down what it
;  said. The vector file was itself re-checked against a host SHA-256
;  before use, so a corrupted table would have been caught rather than
;  agreed with.
;
;  NOT PROVEN:
;
;    * NOTHING HERE HAS RUN ON SILICON. The oracle is a model of the
;      instruction set, not of the chip. It has no caches, so nothing
;      here has been exercised against a real memory system, and no
;      timing claim in this file has been measured on hardware.
;      RE-CHECKED 2026-08-27 AND STILL TRUE: nothing under
;      RaspberryPi4/ includes this file, so no image that has booted
;      contains a line of it. Dated twice on purpose - an undated
;      "nothing has run" reads as present tense for ever, and an audit
;      on that date found nine banners in this directory that had gone
;      false exactly that way.
;    * THE 1,000,000 x 'a' VECTOR HAS NOT COMPLETED HERE. It is 15,625
;      compressions and the Python oracle runs at a few hundred thousand
;      instructions a second, so it is an hour-scale run rather than a
;      minute-scale one and it was not finished within this session. The
;      200-vector set above exercises the same code far more widely; the
;      one thing the million-'a' case adds is a byte count over 16 bits,
;      and the counter that carries it is the item flagged as reasoning
;      in point 3. Run it when there is a faster oracle, or on silicon.
;    * The three deliberately-broken variants A/B/C in the scoreboard
;      show the masks are not distinguishable by test. That is a
;      statement about the tests as much as about the masks.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====
EnableExplicit

; ----------------------------------------------------------------------
;  THE TWO NUMBERS THIS PORT TURNS ON.
;
;  #SHA256_W32 is the 32-bit word mask. It is a POSITIVE value here -
;  $FFFFFFFF in a 64-bit .i is 4294967295, not -1 - which is exactly why
;  masking with it produces the clean non-negative words the file's
;  invariant is stated in terms of.
;
;  #SHA256_HWORD is the distance between two elements of a Dim .i array
;  on this target, which is also the width PeekI and PokeI move. The two
;  are the same number because they are the same fact: the size of one
;  .i. On the RP2350 copy both are 4.
; ----------------------------------------------------------------------
#SHA256_W32   = $FFFFFFFF
#SHA256_HWORD = 8

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style (no structures).
;
;  The snapshot/restore pair serialises exactly these into 104 bytes:
;  8x4 H, then the 64-byte partial block, then the byte counter as two
;  32-bit words (lo, hi). THAT IMAGE IS 32-BIT ON EVERY TARGET even
;  though the variables holding it are 64-bit here - it is a wire format
;  shared with the other three families, so it does not get wider just
;  because this CPU did.
;
;  Every .i below that holds a SHA-256 word holds it clean: 0..$FFFFFFFF,
;  never negative, never with anything above bit 31.
; ----------------------------------------------------------------------
Global Dim Sha256H.i[8]             ; the eight running hash words H0..H7
Global Dim Sha256Blk.a[64]          ; the current 64-byte input block
Global Sha256CountLo.i              ; total BYTE count, low 32 bits
Global Sha256CountHi.i              ; total BYTE count, high 32 bits

Global Dim Sha256K.i[64]            ; round constants, copied from the table
Global Sha256KReady.i               ; 0 until the K table has been loaded once
Global Dim Sha256W.i[64]            ; message schedule scratch (not state)

Global Dim Sha256OutBlk.a[64]       ; finalisation works on a COPY, so the
Global Dim Sha256OutH.i[8]          ; live state survives End() untouched

; ----------------------------------------------------------------------
;  Sha256Shr(x, n) - the 32-bit LOGICAL right shift, SHR^n of FIPS 180-4
;  section 3.2.
;
;  MASK FIRST, THEN SHIFT. `>>` is arithmetic on this target, so on a
;  value with bit 63 set it drags in ones; (x & W32) is non-negative, so
;  shifting it right brings in zeros and the result is already confined
;  to 32 bits, whatever the caller handed in.
;
;  THE RP2350 SPELLING IS ALSO CORRECT AND THAT WAS CHECKED. It reads
;  (x >> n) & ((1 << (32 - n)) - 1), and that trailing mask is exactly
;  the width of the surviving field, so any rubbish shifted down from
;  bits 32+ lands one bit above it and is cut. Variant A in the header
;  is that spelling and it passes all 23 vectors. This form is preferred
;  only because it is correct for one visible reason instead of one that
;  needs the mask width worked out - not because the other is wrong.
;
;  n is a constant at every call site (3 and 10) - never message data -
;  so control here is length-driven only.
; ----------------------------------------------------------------------
Procedure.i Sha256Shr(x.i, n.i)
  ProcedureReturn (x & #SHA256_W32) >> n
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Rotr(x, n) - the 32-bit rotate right, ROTR^n of FIPS 180-4
;  section 3.2.
;
;  THE LEFT HALF IS THE ONE THAT BREAKS ON A 64-BIT REGISTER. On a
;  32-bit machine x << (32 - n) throws its top bits off the end of the
;  word, which IS the rotate. Here they land in bits 32..62 and stay
;  there, so the OR below would return a value with real data above bit
;  31 and every later operation would carry it forward. The outer mask
;  is the discard the narrow register used to do for free.
;
;  n is 2, 6, 7, 11, 13, 17, 18, 19, 22 or 25 at every call site in this
;  file - never 0, never 32 - so (32 - n) is always a legal shift of
;  1..31. A rotate by 0 would need x << 32, which this does not attempt
;  and does not need to.
; ----------------------------------------------------------------------
Procedure.i Sha256Rotr(x.i, n.i)
  ProcedureReturn (((x & #SHA256_W32) >> n) | (x << (32 - n))) & #SHA256_W32
EndProcedure

; ----------------------------------------------------------------------
;  Ch and Maj - FIPS 180-4 section 4.1.2, in BearSSL's algebraically
;  equivalent form (fewer temporaries, same truth table).
;
;  NOT MASKED, ON PURPOSE. Both are pure bitwise functions of their
;  arguments: no carry propagates, no bit moves. Given clean 32-bit
;  inputs - which the file's invariant guarantees - the output cannot
;  have a bit set above 31. Adding a mask here would suggest to the next
;  reader that one is NEEDED, and the interesting question is which
;  operations genuinely need one.
; ----------------------------------------------------------------------
Procedure.i Sha256Ch(x.i, y.i, z.i)
  ProcedureReturn ((y ! z) & x) ! z
EndProcedure

Procedure.i Sha256Maj(x.i, y.i, z.i)
  ProcedureReturn (y & z) | ((y | z) & x)
EndProcedure

; ----------------------------------------------------------------------
;  The four sigma functions - FIPS 180-4 section 4.1.2.
;
;    BSIG0(x) = ROTR^2(x)  ^ ROTR^13(x) ^ ROTR^22(x)
;    BSIG1(x) = ROTR^6(x)  ^ ROTR^11(x) ^ ROTR^25(x)
;    SSIG0(x) = ROTR^7(x)  ^ ROTR^18(x) ^ SHR^3(x)
;    SSIG1(x) = ROTR^17(x) ^ ROTR^19(x) ^ SHR^10(x)
;
;  Unmasked for the same reason as Ch/Maj: XOR of clean words is clean.
;  The masking that these depend on has already happened inside Rotr and
;  Shr.
; ----------------------------------------------------------------------
Procedure.i Sha256Bsg0(x.i)
  ProcedureReturn (Sha256Rotr(x, 2) ! Sha256Rotr(x, 13)) ! Sha256Rotr(x, 22)
EndProcedure

Procedure.i Sha256Bsg1(x.i)
  ProcedureReturn (Sha256Rotr(x, 6) ! Sha256Rotr(x, 11)) ! Sha256Rotr(x, 25)
EndProcedure

Procedure.i Sha256Ssg0(x.i)
  ProcedureReturn (Sha256Rotr(x, 7) ! Sha256Rotr(x, 18)) ! Sha256Shr(x, 3)
EndProcedure

Procedure.i Sha256Ssg1(x.i)
  ProcedureReturn (Sha256Rotr(x, 17) ! Sha256Rotr(x, 19)) ! Sha256Shr(x, 10)
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Round(blk, hv) - one 64-byte compression, FIPS 180-4 s6.2.2.
;
;  blk is the ADDRESS of 64 message bytes (a .a array, stride 1, read
;  with PeekA). hv is the ADDRESS of eight hash words (a .i array,
;  stride #SHA256_HWORD, read with PeekI). Reading the words through the
;  address lets End() run this on a scratch copy while the live state is
;  left alone.
;
;  THE STRIDE IS 8 AND NOT 4. See the header. PeekI/PokeI move one .i,
;  which is one element of a Dim .i array, which is #SHA256_HWORD bytes;
;  using PeekL and 4 here - as the 32-bit copies correctly do - would
;  read the high half of H[0] as if it were H[1].
;
;  There is not one branch on message content in here: the two schedule
;  loops and the round loop are counted, and the round function is
;  straight-line.
; ----------------------------------------------------------------------
Procedure Sha256Round(blk.i, hv.i)
  Protected i.i
  Protected t1.i
  Protected t2.i
  Protected a.i
  Protected b.i
  Protected c.i
  Protected d.i
  Protected e.i
  Protected f.i
  Protected g.i
  Protected h.i

  ; W[0..15]: sixteen BIG-ENDIAN words out of the block. PeekA is the
  ; unsigned spelling, so no byte arrives negative; four zero-extended
  ; bytes cannot exceed 32 bits, so no mask is needed on the assembly.
  i = 0
  While i < 16
    Sha256W[i] = ((PeekA(blk) & 255) << 24) | ((PeekA(blk + 1) & 255) << 16) | ((PeekA(blk + 2) & 255) << 8) | (PeekA(blk + 3) & 255)
    blk = blk + 4
    i = i + 1
  Wend

  ; W[16..63]: the message schedule.
  ;   W[i] = SSIG1(W[i-2]) + W[i-7] + SSIG0(W[i-15]) + W[i-16]  mod 2^32
  ; FOUR additions of clean 32-bit words: the running sum can reach at
  ; most 4*(2^32 - 1), which is nowhere near overflowing a 64-bit
  ; register, so ONE mask on the total is exactly equal to masking after
  ; each add. This is the "modulo 2^32" that used to be free.
  i = 16
  While i < 64
    Sha256W[i] = (((Sha256Ssg1(Sha256W[i - 2]) + Sha256W[i - 7]) + Sha256Ssg0(Sha256W[i - 15])) + Sha256W[i - 16]) & #SHA256_W32
    i = i + 1
  Wend

  ; The working variables. The masks are belt-and-braces: the state is
  ; already clean by the invariant, and PeekI reads a full .i so there
  ; is no sign question to answer.
  a = PeekI(hv)                      & #SHA256_W32
  b = PeekI(hv + #SHA256_HWORD)      & #SHA256_W32
  c = PeekI(hv + #SHA256_HWORD * 2)  & #SHA256_W32
  d = PeekI(hv + #SHA256_HWORD * 3)  & #SHA256_W32
  e = PeekI(hv + #SHA256_HWORD * 4)  & #SHA256_W32
  f = PeekI(hv + #SHA256_HWORD * 5)  & #SHA256_W32
  g = PeekI(hv + #SHA256_HWORD * 6)  & #SHA256_W32
  h = PeekI(hv + #SHA256_HWORD * 7)  & #SHA256_W32

  ; The sixty-four rounds. Five additions in t1, two in t2, one each in
  ; e and a - every one of them modulo 2^32, every one of them masked.
  i = 0
  While i < 64
    t1 = (((((h + Sha256Bsg1(e)) + Sha256Ch(e, f, g)) + Sha256K[i]) + Sha256W[i])) & #SHA256_W32
    t2 = (Sha256Bsg0(a) + Sha256Maj(a, b, c)) & #SHA256_W32
    h = g
    g = f
    f = e
    e = (d + t1) & #SHA256_W32
    d = c
    c = b
    b = a
    a = (t1 + t2) & #SHA256_W32
    i = i + 1
  Wend

  ; H[i] = H[i] + working[i], modulo 2^32. Eight more masks.
  PokeI(hv,                     (PeekI(hv)                     + a) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD,     (PeekI(hv + #SHA256_HWORD)     + b) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 2, (PeekI(hv + #SHA256_HWORD * 2) + c) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 3, (PeekI(hv + #SHA256_HWORD * 3) + d) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 4, (PeekI(hv + #SHA256_HWORD * 4) + e) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 5, (PeekI(hv + #SHA256_HWORD * 5) + f) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 6, (PeekI(hv + #SHA256_HWORD * 6) + g) & #SHA256_W32)
  PokeI(hv + #SHA256_HWORD * 7, (PeekI(hv + #SHA256_HWORD * 7) + h) & #SHA256_W32)
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Begin() - start a fresh digest.
;
;  Loads the FIPS 180-4 section 5.3.3 initial hash value - the first
;  thirty-two bits of the fractional parts of the square roots of the
;  first eight primes - and, ONCE, the sixty-four round constants.
;
;  THE K TABLE IS TAKEN BY ADDRESS, not walked with Read/Restore. See
;  the header for why.
;
;  PeekN, NOT PeekL. Thirty-two of the sixty-four round constants have
;  bit 31 set, starting with $B5C0FBCF at index 2, and PeekL sign-extends
;  on this target as of 2026-08-25. The mask would have saved it; the
;  right accessor means the mask does not have to.
; ----------------------------------------------------------------------
Procedure Sha256Begin()
  Protected i.i
  Protected base.i

  Sha256H[0] = $6A09E667
  Sha256H[1] = $BB67AE85
  Sha256H[2] = $3C6EF372
  Sha256H[3] = $A54FF53A
  Sha256H[4] = $510E527F
  Sha256H[5] = $9B05688C
  Sha256H[6] = $1F83D9AB
  Sha256H[7] = $5BE0CD19

  Sha256CountLo = 0
  Sha256CountHi = 0

  If Sha256KReady = 0
    base = ?Sha256KTable
    i = 0
    While i < 64
      Sha256K[i] = PeekN(base + i * 4) & #SHA256_W32
      i = i + 1
    Wend
    Sha256KReady = 1
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Update(src, len) - absorb len bytes at address src.
;
;  Arbitrary split points behave exactly like one shot: the only control
;  here is driven by LEN and by how full the block already is, never by
;  the bytes themselves.
;
;  THE BYTE COUNTER STOPPED BEING A HAND-ROLLED CARRY. The RP2350 copy
;  adds len to a 32-bit low word and detects the wrap by flipping both
;  sign bits and comparing - the standard trick for an unsigned compare
;  on a machine with no 64-bit integer. THAT TRICK IS WRONG HERE and
;  wrong in the quiet direction: nothing wraps at 32 bits on this
;  target, so the comparison never fires, the high word never
;  increments, and the padded length in Sha256End() is short by 2^32
;  bits for any message over 4 GiB. It would have been a correct-looking
;  digest of a 5 GiB file.
;
;  THIS ONE IS REASONING AND NOT A REPRODUCTION. The old trick was put
;  back (variant F in the header) and it passed all 23 vectors, because
;  no vector this bench can run is 4 GiB long. Believe the argument, not
;  the green result, and if a way to hash 4 GiB here ever exists, run it.
;
;  Since .i IS the 64-bit accumulator that trick was emulating, the sum
;  is done once at full width and split afterwards. That is also the one
;  place this port is strictly BETTER than its 32-bit siblings: it is
;  correct for a single Update call longer than 4 GiB, which the carry
;  trick could not have been.
;
;  The counter is still STORED as two 32-bit words because the 104-byte
;  snapshot is a wire format shared with the other families.
; ----------------------------------------------------------------------
Procedure Sha256Update(src.i, len.i)
  Protected ptr.i
  Protected clen.i
  Protected total.i
  Protected k.i

  ; A negative length is a caller error, not a wrap. Ignoring it beats
  ; adding it to the counter and corrupting the padded length.
  If len > 0
    ptr = Sha256CountLo & 63

    total = Sha256CountLo + len
    Sha256CountLo = total & #SHA256_W32
    Sha256CountHi = (Sha256CountHi + ((total >> 32) & #SHA256_W32)) & #SHA256_W32

    While len > 0
      clen = 64 - ptr
      If clen > len
        clen = len
      EndIf
      k = 0
      While k < clen
        Sha256Blk[ptr + k] = PeekA(src + k) & 255
        k = k + 1
      Wend
      ptr = ptr + clen
      src = src + clen
      len = len - clen
      If ptr = 64
        Sha256Round(@Sha256Blk[0], @Sha256H[0])
        ptr = 0
      EndIf
    Wend
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  Sha256End(dst) - finish, writing 32 bytes (eight big-endian words).
;
;  Runs on a COPY of the block and of H, so the live context is
;  unchanged and a Snapshot taken afterwards still reflects the absorbed
;  message. The padding rule (FIPS 180-4 section 5.1.1) is length-driven:
;  a $80 byte, zeros, and the 64-bit BIT length in the last eight bytes,
;  spilling into a second block when the $80 leaves no room for it.
;
;  THE TWO MASKS ON THE BIT LENGTH ARE THE WEAKEST IN THE FILE, and that
;  is said here rather than left for someone to discover. CountLo << 3
;  does put three bits above bit 31 on a 64-bit register where a 32-bit
;  register would have dropped them - but every one of the eight
;  extractions below ends in "& 255" on a bit position below 32, so
;  those spilled bits are never read either way. The masks buy nothing
;  a test can see. They are here so that bitHi and bitLo satisfy the
;  file's stated invariant like everything else, and so that a reader
;  checking "is every 32-bit value clean" does not have to make an
;  exception for these two.
;
;  WHAT IS LOAD-BEARING IN THIS PROCEDURE is that Sha256CountLo and
;  Sha256CountHi arrive correct, which is Sha256Update's job and is
;  where the real 64-bit counter fix lives.
; ----------------------------------------------------------------------
Procedure Sha256End(dst.i)
  Protected ptr.i
  Protected i.i
  Protected bitLo.i
  Protected bitHi.i

  ptr = Sha256CountLo & 63

  i = 0
  While i < ptr
    Sha256OutBlk[i] = Sha256Blk[i]
    i = i + 1
  Wend
  i = 0
  While i < 8
    Sha256OutH[i] = Sha256H[i]
    i = i + 1
  Wend

  Sha256OutBlk[ptr] = $80
  ptr = ptr + 1
  If ptr > 56
    While ptr < 64
      Sha256OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
    Sha256Round(@Sha256OutBlk[0], @Sha256OutH[0])
    i = 0
    While i < 56
      Sha256OutBlk[i] = 0
      i = i + 1
    Wend
  Else
    While ptr < 56
      Sha256OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
  EndIf

  ; bit length = byte count * 8, as a 64-bit big-endian value.
  bitHi = ((Sha256CountHi << 3) | ((Sha256CountLo >> 29) & 7)) & #SHA256_W32
  bitLo = (Sha256CountLo << 3) & #SHA256_W32
  Sha256OutBlk[56] = (bitHi >> 24) & 255
  Sha256OutBlk[57] = (bitHi >> 16) & 255
  Sha256OutBlk[58] = (bitHi >> 8) & 255
  Sha256OutBlk[59] = bitHi & 255
  Sha256OutBlk[60] = (bitLo >> 24) & 255
  Sha256OutBlk[61] = (bitLo >> 16) & 255
  Sha256OutBlk[62] = (bitLo >> 8) & 255
  Sha256OutBlk[63] = bitLo & 255

  Sha256Round(@Sha256OutBlk[0], @Sha256OutH[0])

  i = 0
  While i < 8
    PokeB(dst + i * 4,     (Sha256OutH[i] >> 24) & 255)
    PokeB(dst + i * 4 + 1, (Sha256OutH[i] >> 16) & 255)
    PokeB(dst + i * 4 + 2, (Sha256OutH[i] >> 8) & 255)
    PokeB(dst + i * 4 + 3, Sha256OutH[i] & 255)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Of(src, len, dst) - the one-shot convenience: Begin, Update, End.
; ----------------------------------------------------------------------
Procedure Sha256Of(src.i, len.i, dst.i)
  Sha256Begin()
  Sha256Update(src, len)
  Sha256End(dst)
EndProcedure

; ----------------------------------------------------------------------
;  Sha256Snapshot(dst) / Sha256Restore(src) - 104-byte state round-trip.
;
;  Layout, and it is IDENTICAL on all four families by design:
;    +0    H[0..7], eight 32-bit words, native (little) endian
;    +32   the 64-byte partial block
;    +96   the byte counter, low 32 bits
;    +100  the byte counter, high 32 bits
;
;  THE IMAGE STAYS 32-BIT EVEN THOUGH .i DID NOT. Widening it to eight
;  bytes a word would have made a Pi 4 snapshot unreadable by an RP2350
;  and would have changed a wire format for no benefit; PokeN writes the
;  low four bytes of a value the invariant already confines to 32 bits,
;  so nothing is lost.
;
;  Snapshot captures the whole block buffer; only its first (count & 63)
;  bytes are ever live, so stale trailing bytes are harmless and the
;  image round-trips MID-BLOCK exactly.
;
;  BOTH SIDES USE THE UNSIGNED ACCESSOR. Three of the eight initial hash
;  values have bit 31 set - $BB67AE85, $A54FF53A, $9B05688C - and so does
;  any running H that has absorbed anything. Read back with PeekL each
;  would arrive NEGATIVE, and a negative H poisons every rotate that
;  follows it. Restore also masks every word, which is now belt to
;  PeekN's braces; see point 5 in the header for why the belt stays.
; ----------------------------------------------------------------------
Procedure Sha256Snapshot(dst.i)
  Protected i.i
  i = 0
  While i < 8
    PokeN(dst + i * 4, Sha256H[i])
    i = i + 1
  Wend
  i = 0
  While i < 64
    PokeB(dst + 32 + i, Sha256Blk[i])
    i = i + 1
  Wend
  PokeN(dst + 96, Sha256CountLo)
  PokeN(dst + 100, Sha256CountHi)
EndProcedure

Procedure Sha256Restore(src.i)
  Protected i.i
  i = 0
  While i < 8
    Sha256H[i] = PeekN(src + i * 4) & #SHA256_W32
    i = i + 1
  Wend
  i = 0
  While i < 64
    Sha256Blk[i] = PeekA(src + 32 + i) & 255
    i = i + 1
  Wend
  Sha256CountLo = PeekN(src + 96) & #SHA256_W32
  Sha256CountHi = PeekN(src + 100) & #SHA256_W32
EndProcedure

; ----------------------------------------------------------------------
;  The sixty-four round constants of FIPS 180-4 section 4.2.2: the first
;  thirty-two bits of the fractional parts of the cube roots of the
;  first sixty-four primes.
;
;  Data.l, so each entry occupies four bytes and PeekN(base + i * 4)
;  lands on element i. Reached with ?Sha256KTable - never with
;  Restore/Read, see the header. Data.l is the right DECLARATION even
;  though the read is PeekN: Data has no unsigned spelling, and what is
;  being asked of it is a four-byte slot, not a sign.
;
;  FOUR OF THESE START WITH A 4 NIBBLE ($428A2F98, $4A7484AA, $4D2C6DFC,
;  $4ED8AA4A). They are cube roots, not addresses. A grep for $4xxxxxxx
;  in a crypto file on this part is a sensible thing to do - $40000000
;  and up is DRAM here, not peripheral space, so a stray poke corrupts
;  instead of faulting - and these four are what it finds. There is no
;  Poke in this table's neighbourhood at all.
; ----------------------------------------------------------------------
DataSection
  Sha256KTable:
  Data.l $428A2F98, $71374491, $B5C0FBCF, $E9B5DBA5
  Data.l $3956C25B, $59F111F1, $923F82A4, $AB1C5ED5
  Data.l $D807AA98, $12835B01, $243185BE, $550C7DC3
  Data.l $72BE5D74, $80DEB1FE, $9BDC06A7, $C19BF174
  Data.l $E49B69C1, $EFBE4786, $0FC19DC6, $240CA1CC
  Data.l $2DE92C6F, $4A7484AA, $5CB0A9DC, $76F988DA
  Data.l $983E5152, $A831C66D, $B00327C8, $BF597FC7
  Data.l $C6E00BF3, $D5A79147, $06CA6351, $14292967
  Data.l $27B70A85, $2E1B2138, $4D2C6DFC, $53380D13
  Data.l $650A7354, $766A0ABB, $81C2C92E, $92722C85
  Data.l $A2BFE8A1, $A81A664B, $C24B8B70, $C76C51A3
  Data.l $D192E819, $D6990624, $F40E3585, $106AA070
  Data.l $19A4C116, $1E376C08, $2748774C, $34B0BCB5
  Data.l $391C0CB3, $4ED8AA4A, $5B9CCA4F, $682E6FF3
  Data.l $748F82EE, $78A5636F, $84C87814, $8CC70208
  Data.l $90BEFFFA, $A4506CEB, $BEF9A3F7, $C67178F2
EndDataSection
; ==== PORTABLE CORE A64 END ====
