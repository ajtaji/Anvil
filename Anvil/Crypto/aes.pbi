; ======================================================================
;  aes.pbi - AES-128/192/256, ENCRYPT AND DECRYPT, ON THE RASPBERRY PI 4
;            (BCM2711, AArch64).  CONSTANT-TIME, BITSLICED, NO S-BOX
;            TABLE ANYWHERE IN THE FILE.
; ======================================================================
;
;     XIncludeFile "Anvil/Crypto/aes.pbi"
;
;  AES as FIPS-197 defines it - RaspberryPi4/Reference/fips197.pdf and
;  its extracted text fips197.txt, the 2023 update, which is the
;  normative document.  Every worked example this file is gated against
;  comes from RaspberryPi4/Reference/fips197-2001.txt instead, and the
;  reason is in "WHICH FIPS-197" below: the update DELETED the worked
;  examples.
;
;  API (module-global key schedule - one key installed at a time):
;    AesSetKey(key.i, keylen.i)     install a key; keylen is 16, 24 or
;                                   32.  Returns the round count (10, 12
;                                   or 14), or 0 for a bad length, in
;                                   which case NO key is installed.
;    AesEncryptBlock(src.i, dst.i)  one 16-byte block, ECB.  Returns 16,
;                                   or 0 if no key is installed.
;                                   src and dst may be the same address.
;    AesDecryptBlock(src.i, dst.i)  the inverse.  Same contract.
;    AesKeyBits()                   128, 192, 256, or 0 if no key.
;    AesWipe()                      zero the schedule and every scratch
;                                   buffer, and forget the key.
;
;  CTR MODE (added 2026-09-04 for gcm.pi4; see "CTR MODE" below):
;    AesCtrInit(key.i, keylen.i)    install a key.  Same contract as
;                                   AesSetKey, and it IS AesSetKey.
;    AesCtrCore(nonce.i, cc.i, src.i, dst.i, len.i)
;                                   CTR keystream XOR over len bytes.
;                                   nonce is 12 bytes, cc a 32-bit
;                                   counter; the block for counter c is
;                                   nonce || big-endian(c).  src and dst
;                                   may be the same address.  Returns the
;                                   counter after the last block, or -1
;                                   if no key is installed (and then it
;                                   writes nothing).
;    AesCtrRun(iv.i, src.i, dst.i, len.i)
;                                   the SP 800-38A entry: iv is the
;                                   16-byte initial counter block.
;
;  DEPENDENCIES: NONE.  House rule - a library never includes a library;
;  the MAIN file lists what it needs.  This file touches no peripheral
;  and reads no register.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO.  The pragma
;  below is not file-scoped; every variable compiled after this include
;  must be declared before use as well.  A requirement a library puts on
;  its caller belongs in the header the caller reads.
;
;  ======================================================================
;   WHERE THIS CAME FROM
;  ======================================================================
;
;  Translated from BearSSL (c) 2016 Thomas Pornin - MIT licence.  The
;  notice ships as licenses/BearSSL-LICENSE.txt (release condition).
;  The two sources are IN THIS REPO and every structural claim below
;  cites them by line:
;
;    RaspberryPi4/Reference/bearssl_aes_ct.c      - the forward S-box
;      circuit (:28-203), the orthogonalisation (:205-234), the round
;      constants (:236-238), SubWord (:240-254), the key schedule
;      (:256-310) and the compressed-schedule expansion (:312-327).
;    RaspberryPi4/Reference/bearssl_aes_ct_dec.c  - the inverse S-box
;      (:28-86), InvShiftRows (:98-112), InvMixColumns (:120-151) and
;      the decrypt round order (:154-170).
;
;  Reads-and-translates only: no C is linked and no foreign ABI is
;  followed.  RP2350/Lib/aes.pico2 is the same core on a 32-bit part and
;  was read first; this file is NOT a copy of it, for the two reasons in
;  "WHAT IS DIFFERENT FROM aes.pico2" below.
;
;  AND IT SHOULD HAVE BEEN MORE OF A COPY THAN IT IS.  Measured after the
;  fact: 451 of this file's 666 code lines are the shared forward core,
;  and AesSbox, AesOrtho and AesDec32le are IDENTICAL to aes.pico2's once
;  PeekL becomes PeekI and the stride goes 4 to 8.  Translating the C a
;  second time was not the cheapest route to them.  The full accounting -
;  including why the Picos should NOT gain this file's decrypt half - is
;  the vault's "AES - reconciling aes.pbi with aes.pico2 2026-08-28".
;  Before translating a published algorithm, grep the tree for its
;  procedure names; one command would have found this.
;
;  ======================================================================
;   WHY BITSLICED AND NOT TABLE-DRIVEN.  THE DECISION, WITH ITS REASONS.
;  ======================================================================
;
;  A table-driven AES is smaller, faster, far easier to read against
;  FIPS-197 section 5 line by line, and it is what almost every textbook
;  writes.  It was considered and REJECTED.  The argument, in the order
;  it actually matters here:
;
;  1. THE FIRST CALLER IS A WPA2 SUPPLICANT, AND THE KEY IS WORTH
;     STEALING.  This file exists to unblock the EAPOL four-way
;     handshake, whose message 3 carries its Key Data under AES Key Wrap
;     (RFC 3394) with the KEK half of the PTK.  That KEK is derived from
;     the PMK, the PMK is derived from the passphrase, and an attacker
;     who recovers it recovers the network.  A table-driven AES indexes
;     an array with a byte that is a function of the key.  That index is
;     the canonical AES side channel - Bernstein 2005, Osvik/Shamir/
;     Tromer 2006 - and it has been used to recover full keys from
;     across a machine.  It is not a theoretical objection.
;
;  2. "THE MMU IS OFF, SO THERE IS NO CACHE TO LEAK THROUGH" IS TRUE
;     TODAY AND IS NOT A REASON.  With the MMU disabled on ARMv8-A every
;     data access is Device-nGnRnE: uncached, unbuffered, un-reordered.
;     A table read would therefore cost the same however the key fell,
;     and the classic cache-timing attack genuinely does not apply to
;     the machine as it is configured right now.
;
;     THAT IS EXACTLY WHY IT IS THE WRONG THING TO DEPEND ON.
;     RaspberryPi4/Lib/mmu.pi4 exists, the vault's "MMU and caches -
;     staged plan 2026-08-26" is a plan to turn caching ON, and the day
;     it lands the table becomes a leak with nothing in the source
;     saying so.  A security property that holds because of a setting
;     somewhere else, and that no test can see change, is a property
;     that will be lost silently.  The bitsliced circuit has no
;     secret-dependent memory access AT ALL, so it is correct with the
;     MMU off, with the MMU on, with caches, without them, and on
;     whatever comes after this part.
;
;     There is also a second channel the MMU does not cover.  DRAM row
;     buffers and the memory controller's own scheduling are visible
;     even to uncached accesses, and 256 table entries span several
;     rows.  "Uncached" is not "constant time"; it is only "not the
;     cache".
;
;  3. THE FORWARD HALF WAS ALREADY WRITTEN AND ALREADY PROVEN, in this
;     dialect, in this tree - RP2350/Lib/aes.pico2, translated from the
;     same BearSSL core and passing FIPS-197 and SP 800-38A.  Choosing
;     the table would have thrown that away and started a second AES.
;
;  WHAT IT COSTS, said plainly rather than glossed over.  The bitsliced
;  S-box is 128 Boolean operations where a table is one load, so a block
;  is a few thousand instructions rather than a few hundred.  This file
;  is nobody's bulk cipher: the whole of a WPA2 message-3 unwrap is
;  about 6 * n block operations for n <= 14, so under a hundred blocks
;  once per association.  If something ever needs AES at line rate the
;  answer is the Cryptography Extensions (AESE/AESD/AESMC), which are
;  constant time IN HARDWARE and are the only correct way to make this
;  faster - not a table.  The BCM2711's Cortex-A72 does NOT implement
;  them, so on this part there is no such option and the trade above is
;  the only one available.
;
;  WHAT "CONSTANT TIME" CLAIMS HERE, AND WHAT IT DOES NOT.  Nothing in
;  this file branches on, or indexes with, a byte of key or plaintext.
;  The key schedule branches only on the PUBLIC key length; the round
;  loops are counted by the PUBLIC round count; there is no array read
;  at a computed index anywhere.  That is a property of the SOURCE and
;  it is checkable by reading it.  It is NOT a measurement: no cycle
;  counter has been put on this on silicon, the A64 model this is gated
;  under has no timing model, and the compiler could in principle turn
;  a masked select into a branch.  The instruction-count side of it IS
;  measured - tools/a64/a64_aes_check.py --timing runs SIX key and
;  plaintext pairs of very different Hamming weight (all zeroes, all
;  ones, a single bit set, and mixtures) through a key schedule, an
;  encrypt and a decrypt, and requires the step counts to be EXACTLY
;  equal. On 2026-08-28 all six were 265,799. That is the strongest
;  statement available without a board.
;
;  ======================================================================
;   WHICH FIPS-197, AND WHY BOTH ARE ON THE DISK
;  ======================================================================
;
;  FIPS-197 was updated in 2023 (FIPS 197-upd1).  The update is the
;  normative text and it is what fips197.txt is.  ITS APPENDIX C IS A
;  POINTER, NOT A TABLE: "The NIST Computer Security Resource Center
;  provides a website with 'examples with intermediate values' for AES"
;  - fips197.txt:1893-1897.  The original 2001 document carried those
;  examples in full, for AES-128, AES-192 and AES-256, for the cipher,
;  the inverse cipher and the equivalent inverse cipher, one hex string
;  per round step.  Those are the vectors that can catch a cipher which
;  is wrong in round 3 and right at the end, so the 2001 document is on
;  the disk too as fips197-2001.pdf / .txt and the gate parses its
;  Appendix C.  Appendix B - the round-by-round state table for one
;  AES-128 encryption - survives in BOTH and the gate reads it from the
;  2023 text (fips197.txt:1770-1868), so the current standard is not
;  merely cited but actually used.
;
;  ======================================================================
;   WHAT IS DIFFERENT FROM aes.pico2, AND WHY THIS IS NOT A COPY
;  ======================================================================
;
;  ---- 1. .i IS 64 BITS HERE, AND AES IS DEFINED ON 32-BIT WORDS. -----
;
;  Every bitslice word, every key-schedule word and every round key in
;  this file is a 32-bit quantity living in a 64-bit register.  The
;  invariant, and it is the same one sha1.pi4 and sha256.pi4 state:
;
;      EVERY VALUE THAT REPRESENTS A 32-BIT AES WORD IS HELD AS A CLEAN
;      NON-NEGATIVE NUMBER IN 0..$FFFFFFFF, AND EVERY OPERATION THAT CAN
;      LEAVE THAT RANGE IS MASKED WITH #AES_W32 AT THE POINT IT HAPPENS.
;
;  On the 32-bit families the register IS the word, so a left shift
;  throws its top bits away and that discard is part of the algorithm.
;  Here they land in bits 32..62 and stay there, and the next AND or
;  rotate drags them back down.  The bookkeeping is confined to THREE
;  procedures - AesLsr, AesLsl and AesRotr - and every shift in the file
;  goes through one of them.  Nothing else in this file shifts.  That is
;  a deliberate choice over sprinkling "& #AES_W32" through eighty
;  expressions: it means the width argument is made once, in twelve
;  lines that can be read in one sitting, instead of being re-derived at
;  every call site by whoever edits next.
;
;  WHICH SHIFTS ACTUALLY SPILL, since the answer is not "all of them"
;  and a reader checking this file deserves the list:
;
;    AesRotr          the left half of every rotate.  ALWAYS spills.
;    AesSwapN         does NOT spill.  (b & $55555555) << 1 cannot set a
;                     bit above 31 because the mask clears bit 31 first,
;                     and the same holds for $33333333 << 2 and
;                     $0F0F0F0F << 4.  It still goes through AesLsl,
;                     because "this one is safe" is a fact that has to
;                     be re-derived by every reader and re-checked after
;                     every edit.
;    AesShiftRows,
;    AesInvShiftRows  do NOT spill, same reason - every left shift is
;                     under a mask that clears the bits it would push
;                     out.  Also routed through AesLsl.
;    AesSkeyExpand    does NOT spill (x is masked with $55555555 first).
;    AesDec32le       does not shift left past bit 31 by construction.
;
;  ---- 1a. THE MASK SCOREBOARD. MEASURED, NOT ARGUED. ----------------
;
;  The claims above were tested rather than asserted, by building this
;  file with each mask removed and running the whole mutation vector
;  set (tools/a64/a64_aes_check.py --mutate, 290 vectors, 2026-08-28):
;
;    variant under test                                   failures
;    -------------------------------------------------    --------
;    AesLsl's OUTPUT mask removed                            0/290
;    AesLsr masking AFTER the shift instead of before        0/290
;    BOTH of them at once                                    RED
;    the stride constant 4 instead of 8                 ALIGNMENT FAULT
;
;  SO NEITHER WIDTH MASK IS INDIVIDUALLY OBSERVABLE, AND TOGETHER THEY
;  ARE. The reason, and it is worth having rather than being surprised
;  by twice: the ONLY call site that can spill is AesRotr's left half,
;  and the rubbish it leaves lives in bits 32..62. Nothing in this file
;  brings a bit back DOWN except a right shift, and AesLsr masks its
;  input BEFORE shifting - so with either mask in place the dirt is
;  unreachable by any caller. Remove both and it lands in the answer.
;
;  KEEP BOTH. The pair is not belt and braces, it is two halves of one
;  argument, and the file's invariant - every 32-bit value is clean at
;  the point it is produced - is what makes the pair checkable a line at
;  a time instead of by tracing where rubbish can travel. The scoreboard
;  is here so that nobody has to take that on trust, and so that a
;  future edit which makes one of them observable is recognised as news
;  rather than noise. The gate encodes both expectations and fails if
;  either changes. sha1.pi4's header records the identical shape for its
;  rotate; this is the second time it has been measured in this tree.
;
;  ---- 2. `>>` IS ARITHMETIC ON THIS TARGET. --------------------------
;
;  A right shift of a value with bit 63 set drags in ones.  Under the
;  invariant no value here ever has bit 63 set, so a bare `>>` would in
;  fact be correct - and AesLsr masks its input to 32 bits anyway,
;  BEFORE shifting, so it is right even when handed something dirty.
;  Mask first, then shift.  This is the opposite order from aes.pico2,
;  which masks AFTER the shift because on a signed 32-bit .i the sign
;  extension has already happened by then; the two spellings are not
;  interchangeable and copying that one across would have been wrong.
;
;  ---- 3. RAW BYTES ARE READ WITH PeekA, NEVER PeekB. -----------------
;
;  Project ruling 2026-08-25: a Peek follows its type letter and
;  PeekB/PeekC/PeekW SIGN-EXTEND on every backend; PeekA and PeekU are
;  the unsigned spellings.  A key byte of $80 read with PeekB is -128,
;  which in a 64-bit .i is $FFFFFFFFFFFFFF80, and ORing that into a word
;  sets fifty-seven bits instead of eight.  Half the AES key space has
;  the high bit set in its first byte, so this would fail loudly - but
;  the trailing "& 255" is kept at every PeekA anyway, because it is
;  what makes a later PeekA-to-PeekB slip harmless.  sha1.pi4's header
;  records measuring exactly that.
;
;  ---- 4. ARRAY STRIDE IS 8, AND PeekI/PokeI MOVE 8. ------------------
;
;  The bitslice words are passed BY ADDRESS - AesSbox(q), AesOrtho(q) -
;  so an accessor and a stride are needed, and Dim AesQ.i[8] on this
;  target is SIXTY-FOUR bytes, not thirty-two.  aes.pico2 walks it with
;  PeekL and a stride of 4, which is correct there and would read the
;  top half of q[0] as if it were q[1] here.  So the walk is PeekI/PokeI
;  at a stride of #AES_WORD, and the accessor and the stride agree BY
;  CONSTRUCTION because PeekI moves exactly one .i, which is exactly one
;  array element.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT - 2026-08-28
;  ======================================================================
;
;  PROVEN by known-answer test under the project's own A64 oracle
;  tools/a64/a64_interp.py, running a real image built by pmfc.exe for
;  -t pi4.  The gate is tools/a64/a64_aes_check.py and every expected
;  value in it is READ OFF THE DISK - parsed from a published document
;  or a NIST response file, never typed, and never taken from running
;  this file:
;
;    * FIPS-197 Appendix C, INTERMEDIATE VALUES, parsed from
;      fips197-2001.txt: for AES-128, AES-192 and AES-256, every
;      round[r].start, .s_box, .s_row, .m_col and .k_sch of the cipher,
;      and every round[r].istart, .is_row, .is_box, .ik_sch of the
;      inverse cipher.  The harness stops the round loop at a named step
;      and reports the state, so a cipher that is wrong in round 3 is
;      caught in round 3 and not by a final block that happens to
;      differ.
;    * FIPS-197 Appendix B, the round-by-round state table, parsed from
;      the 2023 fips197.txt.
;    * ALL 1,553 NIST CAVP AESAVS known-answer vectors, parsed from
;      RaspberryPi4/Reference/cavp_ECB*.rsp - GFSbox, KeySbox, VarKey
;      and VarTxt, at 128, 192 and 256 bits, ENCRYPT and DECRYPT.  The
;      whole set is 358 million model instructions and took 774 s on
;      2026-08-28; --quick samples every eighth and takes 133 s.
;    * THE KEY SCHEDULE, round by round, for all three key lengths -
;      every round[r].k_sch of Appendix C, read back out of the
;      expanded bitsliced schedule through the same AesOrtho the cipher
;      uses. The inverse cipher's round[r].ik_sch is checked too, and
;      the parse REQUIRES it to equal the forward round[Nr - r].k_sch,
;      which is what distinguishes the straight inverse cipher from the
;      equivalent one.
;
;  MUTATION-TESTED.  a64_aes_check.py --mutate rebuilds a COPY of this
;  file in _work/aes/<n>/ with one deliberate defect at a time and
;  requires the gate to go red for each.  The sweep FANS OUT across
;  os.cpu_count() - 2 workers, one per mutation, so it is 70 s rather
;  than the 821 s it was when it ran on one core.  TWENTY-FOUR
;  mutations on 2026-08-28:
;  twenty-one RED and three GREEN, and all three of the green ones are
;  recorded in the gate's table with the reason they cannot be seen -
;  two are the mask scoreboard above, the third reads bitslice lane 1
;  where lane 0 is meant and the two lanes are copies by construction.
;  A mutation whose harmlessness is recorded rather than deleted is one
;  a future edit can turn back into a defect loudly.
;
;  IT NEVER OPENS THIS FILE FOR WRITING - see the vault's "A mutation
;  gate edited a shared source file, and a commit caught it".  _work/ is
;  in .gitignore, so a mutant cannot reach a commit even if the sweep is
;  killed mid-run, which is exactly how that incident happened.
;
;  NOT PROVEN:
;
;    * NOTHING HERE HAS RUN ON SILICON.  The oracle is a model of the
;      instruction set: no caches, no real memory system, no clock.
;      RaspberryPi4/Examples/Diagnostics/pi4AesSelfTest.pi4 runs the
;      same vectors on the board and that is where silicon evidence will
;      come from.
;    * ANY TIMING CLAIM AS A MEASUREMENT ON HARDWARE.  See the
;      constant-time paragraph above for exactly what is and is not
;      being asserted.
;    * AES-192 and AES-256 have no caller in this tree.  They are gated
;      to the same standard as AES-128 and they are, as of today,
;      unused; see "WHY 192 AND 256 ARE HERE" below.
;
;  ======================================================================
;   WHY 192 AND 256 ARE HERE
;  ======================================================================
;
;  The task was AES-128.  192 and 256 cost SIX LINES between them - the
;  two extra arms of the keylen switch, and BearSSL's `nk > 6 And j = 4`
;  clause that adds the second SubWord for a 256-bit key - because the
;  key schedule is already written in terms of nk and nkf and the round
;  loops are already driven by a round count.  Everything else in the
;  file is untouched by key length.  So they were included, and they are
;  gated by the full CAVP set at both sizes rather than being asserted
;  to work.  Three of RFC 3394's six published vectors use a 192- or
;  256-bit KEK, so leaving them out would also have meant leaving half
;  the key-wrap gate unrunnable.
; ======================================================================
; ==== PORTABLE CORE A64 BEGIN ====
EnableExplicit

; ----------------------------------------------------------------------
;  #AES_W32 is the 32-bit word mask and it is POSITIVE here: $FFFFFFFF
;  in a 64-bit .i is 4294967295, not -1.  That is exactly why masking
;  with it produces the clean non-negative words the invariant above is
;  stated in terms of.
;
;  #AES_WORD is the distance between two elements of a Dim .i array on
;  this target, which is also the width PeekI and PokeI move.  The two
;  are the same number because they are the same fact: the size of one
;  .i.  On the 32-bit families both would be 4.
;
;  #AES_QWORDS is 8 because the bitslice holds a 128-bit block as eight
;  words of "bit k of every byte" - and it holds TWO blocks at once,
;  which is what makes the low and high halves of each word separate
;  lanes.  See AesLoadBlock.
; ----------------------------------------------------------------------
#AES_W32      = $FFFFFFFF
#AES_WORD     = 8
#AES_QWORDS   = 8
#AES_BLOCK    = 16
#AES_MAXROUND = 14

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style (no structures).
;
;  THE `sec` PREFIX MEANS KEY MATERIAL, and it is not decoration: the
;  compressed schedule and the expanded schedule are the installed key
;  in another form, and AesWipe() exists because they outlive the call
;  that made them.
;
;  secAesKeyTmp HOLDS THE RAW ROUND KEYS AND IS NOT CLEARED WHEN
;  AesSetKey RETURNS.  It is scratch, but it is scratch containing the
;  key schedule in its plainest form, and it stays there until the next
;  AesSetKey overwrites it or AesWipe() zeroes it.  Clearing it early
;  would be theatre: secAesSkExp next door holds the same information
;  and has to survive, so the exposure is unchanged either way.  The
;  honest statement is this paragraph, not a wipe that looks like it
;  bought something.
;
;  SIZES.  120 words is 2 * ((14 + 1) * 4) - two entries per round-key
;  word for AES-256, which is the largest.  60 is (14 + 1) * 4 for the
;  compressed form.  On this target a .i array element is 8 bytes, so
;  the three schedules together are 2,400 bytes of .bss.  That is
;  nothing on a part with a gigabyte of DRAM and it buys the file the
;  ability to be read straight against BearSSL's index arithmetic.
; ----------------------------------------------------------------------
Global Dim AesRcon.a[10]                ; the ten AES round constants
Global Dim secAesKeyTmp.i[120]          ; key-schedule scratch, cleartext
Global Dim secAesCompSkey.i[60]         ; the installed compressed schedule
Global Dim secAesSkExp.i[120]           ; the expanded bitsliced schedule
Global AesNumRounds.i                   ; 10, 12, 14 - or 0 for "no key"
Global AesKeyLen.i                      ; 16, 24, 32 - or 0 for "no key"
Global Dim AesQ.i[8]                    ; the eight bitslice words
Global Dim secAesSubQ.i[8]              ; SubWord scratch (key schedule only)
Global Dim secAesKs.a[32]               ; two blocks of CTR keystream (secret)

; ======================================================================
;  THE THREE SHIFT PRIMITIVES.  EVERY SHIFT IN THIS FILE GOES THROUGH
;  ONE OF THEM.  See point 1 of the header for why they exist at all.
; ======================================================================

; ----------------------------------------------------------------------
;  AesLsr(x, n) - logical shift right inside 32 bits.
;
;  MASK FIRST, THEN SHIFT.  Masking makes x non-negative, so the
;  arithmetic `>>` brings in zeroes and matches the logical shift AES is
;  defined on.  Doing it the other way round - shifting and then masking
;  the result, which is what aes.pico2 must do on a signed 32-bit .i -
;  would be wrong here for a dirty input, because the sign bits would
;  already have been dragged into the bits the mask keeps.
;
;  n is a public constant at every call site: 1, 2, 4, 8 or 16.  Never
;  0, never 32.
; ----------------------------------------------------------------------
Procedure.i AesLsr(x.i, n.i)
  ProcedureReturn (x & #AES_W32) >> n
EndProcedure

; ----------------------------------------------------------------------
;  AesLsl(x, n) - logical shift left inside 32 bits.
;
;  The outer mask is the discard a 32-bit register performs for free and
;  a 64-bit one does not.  Several call sites cannot actually spill (see
;  the list in the header) and they still come through here, on purpose:
;  a shift that is safe for a reason is a shift whose reason has to be
;  rechecked after every edit, and routing all of them through one
;  masked primitive removes the question.
; ----------------------------------------------------------------------
Procedure.i AesLsl(x.i, n.i)
  ProcedureReturn (x << n) & #AES_W32
EndProcedure

; ----------------------------------------------------------------------
;  AesRotr(x, n) - rotate right inside 32 bits.
;
;  Three separate things in the BearSSL sources are this one function
;  and are written as this one function here:
;    * rotr16() in aes_ct_dec.c:114-118 and its twin in the forward
;      MixColumns  ->  AesRotr(x, 16)
;    * (q >> 8) | (q << 24), the column rotate in both MixColumns
;      variants                                    ->  AesRotr(x, 8)
;    * (tmp << 24) | (tmp >> 8), the key schedule's RotWord
;      (aes_ct.c:281)                              ->  AesRotr(x, 8)
;
;  The third one is worth a sentence because it does not look like the
;  others.  RotWord takes [a0 a1 a2 a3] to [a1 a2 a3 a0]; tmp holds the
;  word LITTLE-ENDIAN, so a0 is in the low byte, and moving every byte
;  down one position with a0 wrapping to the top IS a 32-bit rotate
;  right by 8.  Writing it as one shared primitive rather than three
;  open-coded pairs is what makes that visible.
;
;  n is 8 or 16 at every call site, so 32 - n is 24 or 16 and both
;  halves are legal shifts.  A rotate by 0 would need x << 32 and is
;  neither attempted nor needed.
; ----------------------------------------------------------------------
Procedure.i AesRotr(x.i, n.i)
  ProcedureReturn AesLsl(x, 32 - n) | AesLsr(x, n)
EndProcedure

; ----------------------------------------------------------------------
;  Little-endian 32-bit load and store over RAW BYTES.
;
;  BYTE ACCESSORS, NOT PeekN, AND THAT IS LOAD-BEARING.  Keys, blocks
;  and wrapped key data arrive at whatever address the caller has, and
;  with the MMU off an unaligned wide access on this part is a silent
;  runaway rather than a fault (see the vault's "Unaligned access with
;  the MMU off 2026-08-27").  Four PeekA cannot be misaligned.  The
;  internal word arrays are a different matter and are walked with
;  PeekI, which is safe because they are Dim .i and therefore aligned.
;
;  PeekA and the trailing "& 255" - see point 3 of the header.
; ----------------------------------------------------------------------
Procedure.i AesDec32le(p.i)
  ProcedureReturn (PeekA(p) & 255) | ((PeekA(p + 1) & 255) << 8) | ((PeekA(p + 2) & 255) << 16) | ((PeekA(p + 3) & 255) << 24)
EndProcedure

Procedure AesEnc32le(p.i, x.i)
  PokeB(p,     x & 255)
  PokeB(p + 1, AesLsr(x, 8) & 255)
  PokeB(p + 2, AesLsr(x, 16) & 255)
  PokeB(p + 3, AesLsr(x, 24) & 255)
EndProcedure

; ----------------------------------------------------------------------
;  AesSwap32(x) - byte-reverse a 32-bit word.  The CTR input block is
;  nonce[0..11] || BIG-endian(counter) while the bitslice is fed
;  little-endian words, so the counter and only the counter is swapped.
;  Every shift goes through the masked primitives, so a dirty input
;  cannot leak above bit 31.
; ----------------------------------------------------------------------
Procedure.i AesSwap32(x.i)
  ProcedureReturn AesLsl(x, 24) | AesLsl(x & $0000FF00, 8) | (AesLsr(x, 8) & $0000FF00) | AesLsr(x, 24)
EndProcedure

; ======================================================================
;  THE S-BOX, AS A BOOLEAN CIRCUIT
; ======================================================================

; ----------------------------------------------------------------------
;  AesSbox(q) - the bitsliced AES S-box, a straight-line Boolean circuit
;  (the Boyar-Peralta minimisation).  q is the ADDRESS of eight words.
;
;  THERE IS NOT ONE BRANCH AND NOT ONE TABLE READ IN HERE.  This is the
;  constant-time heart of the file and the reason it is shaped the way
;  it is.  If you are ever tempted to write an AES S-box ARRAY in this
;  file, STOP and read the "WHY BITSLICED" section again - a table index
;  on a key byte is exactly the defect this avoids by construction.
;
;  Translated from bearssl_aes_ct.c:28-203.  NOT is spelled `! #AES_W32`
;  rather than a bitwise-NOT operator, because a NOT on this target
;  would complement all sixty-four bits and break the invariant; XOR
;  with the 32-bit mask complements exactly the thirty-two that exist.
;
;  The 108 Protected locals are what a straight-line circuit looks like.
;  They are named exactly as the published circuit names them so the two
;  can be diffed; do not tidy them into an array, because an array index
;  is the one thing this procedure must not contain.
; ----------------------------------------------------------------------
Procedure AesSbox(q.i)
  Protected x0.i
  Protected x1.i
  Protected x2.i
  Protected x3.i
  Protected x4.i
  Protected x5.i
  Protected x6.i
  Protected x7.i
  Protected y1.i
  Protected y2.i
  Protected y3.i
  Protected y4.i
  Protected y5.i
  Protected y6.i
  Protected y7.i
  Protected y8.i
  Protected y9.i
  Protected y10.i
  Protected y11.i
  Protected y12.i
  Protected y13.i
  Protected y14.i
  Protected y15.i
  Protected y16.i
  Protected y17.i
  Protected y18.i
  Protected y19.i
  Protected y20.i
  Protected y21.i
  Protected z0.i
  Protected z1.i
  Protected z2.i
  Protected z3.i
  Protected z4.i
  Protected z5.i
  Protected z6.i
  Protected z7.i
  Protected z8.i
  Protected z9.i
  Protected z10.i
  Protected z11.i
  Protected z12.i
  Protected z13.i
  Protected z14.i
  Protected z15.i
  Protected z16.i
  Protected z17.i
  Protected t0.i
  Protected t1.i
  Protected t2.i
  Protected t3.i
  Protected t4.i
  Protected t5.i
  Protected t6.i
  Protected t7.i
  Protected t8.i
  Protected t9.i
  Protected t10.i
  Protected t11.i
  Protected t12.i
  Protected t13.i
  Protected t14.i
  Protected t15.i
  Protected t16.i
  Protected t17.i
  Protected t18.i
  Protected t19.i
  Protected t20.i
  Protected t21.i
  Protected t22.i
  Protected t23.i
  Protected t24.i
  Protected t25.i
  Protected t26.i
  Protected t27.i
  Protected t28.i
  Protected t29.i
  Protected t30.i
  Protected t31.i
  Protected t32.i
  Protected t33.i
  Protected t34.i
  Protected t35.i
  Protected t36.i
  Protected t37.i
  Protected t38.i
  Protected t39.i
  Protected t40.i
  Protected t41.i
  Protected t42.i
  Protected t43.i
  Protected t44.i
  Protected t45.i
  Protected t46.i
  Protected t47.i
  Protected t48.i
  Protected t49.i
  Protected t50.i
  Protected t51.i
  Protected t52.i
  Protected t53.i
  Protected t54.i
  Protected t55.i
  Protected t56.i
  Protected t57.i
  Protected t58.i
  Protected t59.i
  Protected t60.i
  Protected t61.i
  Protected t62.i
  Protected t63.i
  Protected t64.i
  Protected t65.i
  Protected t66.i
  Protected t67.i
  Protected s0.i
  Protected s1.i
  Protected s2.i
  Protected s3.i
  Protected s4.i
  Protected s5.i
  Protected s6.i
  Protected s7.i

  x0 = PeekI(q + 7 * #AES_WORD)
  x1 = PeekI(q + 6 * #AES_WORD)
  x2 = PeekI(q + 5 * #AES_WORD)
  x3 = PeekI(q + 4 * #AES_WORD)
  x4 = PeekI(q + 3 * #AES_WORD)
  x5 = PeekI(q + 2 * #AES_WORD)
  x6 = PeekI(q + 1 * #AES_WORD)
  x7 = PeekI(q)

  y14 = x3 ! x5
  y13 = x0 ! x6
  y9 = x0 ! x3
  y8 = x0 ! x5
  t0 = x1 ! x2
  y1 = t0 ! x7
  y4 = y1 ! x3
  y12 = y13 ! y14
  y2 = y1 ! x0
  y5 = y1 ! x6
  y3 = y5 ! y8
  t1 = x4 ! y12
  y15 = t1 ! x5
  y20 = t1 ! x1
  y6 = y15 ! x7
  y10 = y15 ! t0
  y11 = y20 ! y9
  y7 = x7 ! y11
  y17 = y10 ! y11
  y19 = y10 ! y8
  y16 = t0 ! y11
  y21 = y13 ! y16
  y18 = x0 ! y16

  t2 = y12 & y15
  t3 = y3 & y6
  t4 = t3 ! t2
  t5 = y4 & x7
  t6 = t5 ! t2
  t7 = y13 & y16
  t8 = y5 & y1
  t9 = t8 ! t7
  t10 = y2 & y7
  t11 = t10 ! t7
  t12 = y9 & y11
  t13 = y14 & y17
  t14 = t13 ! t12
  t15 = y8 & y10
  t16 = t15 ! t12
  t17 = t4 ! t14
  t18 = t6 ! t16
  t19 = t9 ! t14
  t20 = t11 ! t16
  t21 = t17 ! y20
  t22 = t18 ! y19
  t23 = t19 ! y21
  t24 = t20 ! y18

  t25 = t21 ! t22
  t26 = t21 & t23
  t27 = t24 ! t26
  t28 = t25 & t27
  t29 = t28 ! t22
  t30 = t23 ! t24
  t31 = t22 ! t26
  t32 = t31 & t30
  t33 = t32 ! t24
  t34 = t23 ! t33
  t35 = t27 ! t33
  t36 = t24 & t35
  t37 = t36 ! t34
  t38 = t27 ! t36
  t39 = t29 & t38
  t40 = t25 ! t39

  t41 = t40 ! t37
  t42 = t29 ! t33
  t43 = t29 ! t40
  t44 = t33 ! t37
  t45 = t42 ! t41
  z0 = t44 & y15
  z1 = t37 & y6
  z2 = t33 & x7
  z3 = t43 & y16
  z4 = t40 & y1
  z5 = t29 & y7
  z6 = t42 & y11
  z7 = t45 & y17
  z8 = t41 & y10
  z9 = t44 & y12
  z10 = t37 & y3
  z11 = t33 & y4
  z12 = t43 & y13
  z13 = t40 & y5
  z14 = t29 & y2
  z15 = t42 & y9
  z16 = t45 & y14
  z17 = t41 & y8

  t46 = z15 ! z16
  t47 = z10 ! z11
  t48 = z5 ! z13
  t49 = z9 ! z10
  t50 = z2 ! z12
  t51 = z2 ! z5
  t52 = z7 ! z8
  t53 = z0 ! z3
  t54 = z6 ! z7
  t55 = z16 ! z17
  t56 = z12 ! t48
  t57 = t50 ! t53
  t58 = z4 ! t46
  t59 = z3 ! t54
  t60 = t46 ! t57
  t61 = z14 ! t57
  t62 = t52 ! t58
  t63 = t49 ! t58
  t64 = z4 ! t59
  t65 = t61 ! t62
  t66 = z1 ! t63
  s0 = t59 ! t63
  s6 = t56 ! (t62 ! #AES_W32)
  s7 = t48 ! (t60 ! #AES_W32)
  t67 = t64 ! t65
  s3 = t53 ! t66
  s4 = t51 ! t66
  s5 = t47 ! t65
  s1 = t64 ! (s3 ! #AES_W32)
  s2 = t55 ! (t67 ! #AES_W32)

  PokeI(q + 7 * #AES_WORD, s0)
  PokeI(q + 6 * #AES_WORD, s1)
  PokeI(q + 5 * #AES_WORD, s2)
  PokeI(q + 4 * #AES_WORD, s3)
  PokeI(q + 3 * #AES_WORD, s4)
  PokeI(q + 2 * #AES_WORD, s5)
  PokeI(q + 1 * #AES_WORD, s6)
  PokeI(q, s7)
EndProcedure

; ----------------------------------------------------------------------
;  AesInvSbox(q) - the INVERSE S-box.  bearssl_aes_ct_dec.c:28-86.
;
;  IT DOES NOT HAVE A CIRCUIT OF ITS OWN, and the reason is worth
;  understanding rather than taking on faith, because "the inverse
;  S-box is the forward S-box with some XORs around it" reads like a
;  mistake until you see why it is true.
;
;      S(x)  = A(I(x)) ^ $63
;
;  where I() is inversion in GF(256) - with 0 defined as its own inverse
;  - and A() is an affine (bit-linear) transform.  Inversion is an
;  INVOLUTION: I(I(x)) = x.  So if B() is the inverse of A(),
;
;      iS(x) = B(S(B(x ^ $63)) ^ $63)
;
;  and the check is direct: iS(S(y)) = B(A(I(B(A(I(y)) ^ $63 ^ $63))) ^
;  $63 ^ $63) = y, the two $63 pairs cancelling and B undoing A.
;
;  B() is bit-linear, so in the bitsliced domain it is nothing but XORs
;  of whole words, and the "^ $63" folds into complementing the four
;  bit-planes where $63 has a one bit - planes 0, 1, 5 and 6.  That is
;  the eight-line block below, applied before AND after the forward
;  circuit.
;
;  WHAT THIS COSTS AND WHY IT IS ACCEPTED.  Merging B() into the S-box
;  circuit would be faster, and BearSSL's own comment says so
;  (aes_ct_dec.c:42-47).  It would also mean a SECOND minimised circuit
;  in this file that no published document states and that could only
;  be checked by running it.  Sixteen XOR-of-three-words and eight NOTs
;  per round is a price worth paying for a decrypt path whose only novel
;  content is an algebraic identity written out above.
;
;  THE TWO BLOCKS ARE IDENTICAL, deliberately, and are NOT factored into
;  a helper.  They are the same transform applied twice with the forward
;  circuit between them; a helper would hide that they are the same and
;  would add a call in the middle of the one procedure in this file that
;  most wants to be read as straight-line code.
; ----------------------------------------------------------------------
Procedure AesInvSbox(q.i)
  Protected q0.i
  Protected q1.i
  Protected q2.i
  Protected q3.i
  Protected q4.i
  Protected q5.i
  Protected q6.i
  Protected q7.i

  ; ---- B(), and the ^ $63 as four complemented bit-planes -----------
  q0 = PeekI(q + 0 * #AES_WORD) ! #AES_W32
  q1 = PeekI(q + 1 * #AES_WORD) ! #AES_W32
  q2 = PeekI(q + 2 * #AES_WORD)
  q3 = PeekI(q + 3 * #AES_WORD)
  q4 = PeekI(q + 4 * #AES_WORD)
  q5 = PeekI(q + 5 * #AES_WORD) ! #AES_W32
  q6 = PeekI(q + 6 * #AES_WORD) ! #AES_W32
  q7 = PeekI(q + 7 * #AES_WORD)
  PokeI(q + 7 * #AES_WORD, (q1 ! q4) ! q6)
  PokeI(q + 6 * #AES_WORD, (q0 ! q3) ! q5)
  PokeI(q + 5 * #AES_WORD, (q7 ! q2) ! q4)
  PokeI(q + 4 * #AES_WORD, (q6 ! q1) ! q3)
  PokeI(q + 3 * #AES_WORD, (q5 ! q0) ! q2)
  PokeI(q + 2 * #AES_WORD, (q4 ! q7) ! q1)
  PokeI(q + 1 * #AES_WORD, (q3 ! q6) ! q0)
  PokeI(q + 0 * #AES_WORD, (q2 ! q5) ! q7)

  AesSbox(q)

  ; ---- and B() again, on the way out --------------------------------
  q0 = PeekI(q + 0 * #AES_WORD) ! #AES_W32
  q1 = PeekI(q + 1 * #AES_WORD) ! #AES_W32
  q2 = PeekI(q + 2 * #AES_WORD)
  q3 = PeekI(q + 3 * #AES_WORD)
  q4 = PeekI(q + 4 * #AES_WORD)
  q5 = PeekI(q + 5 * #AES_WORD) ! #AES_W32
  q6 = PeekI(q + 6 * #AES_WORD) ! #AES_W32
  q7 = PeekI(q + 7 * #AES_WORD)
  PokeI(q + 7 * #AES_WORD, (q1 ! q4) ! q6)
  PokeI(q + 6 * #AES_WORD, (q0 ! q3) ! q5)
  PokeI(q + 5 * #AES_WORD, (q7 ! q2) ! q4)
  PokeI(q + 4 * #AES_WORD, (q6 ! q1) ! q3)
  PokeI(q + 3 * #AES_WORD, (q5 ! q0) ! q2)
  PokeI(q + 2 * #AES_WORD, (q4 ! q7) ! q1)
  PokeI(q + 1 * #AES_WORD, (q3 ! q6) ! q0)
  PokeI(q + 0 * #AES_WORD, (q2 ! q5) ! q7)
EndProcedure

; ======================================================================
;  ORTHOGONALISATION - moving between the packed and the bitsliced
;  layout.  Public masks and public shift amounts only; no data
;  dependence anywhere.  bearssl_aes_ct.c:205-234.
; ======================================================================
Procedure AesSwapN(q.i, ia.i, ib.i, cl.i, ch.i, s.i)
  Protected a.i
  Protected b.i
  a = PeekI(q + ia * #AES_WORD)
  b = PeekI(q + ib * #AES_WORD)
  PokeI(q + ia * #AES_WORD, (a & cl) | AesLsl(b & cl, s))
  PokeI(q + ib * #AES_WORD, AesLsr(a & ch, s) | (b & ch))
EndProcedure

; ----------------------------------------------------------------------
;  AesOrtho(q) - its own inverse.  Calling it twice returns the words
;  unchanged, which is why the same procedure serves on the way in and
;  on the way out of the cipher.
; ----------------------------------------------------------------------
Procedure AesOrtho(q.i)
  AesSwapN(q, 0, 1, $55555555, $AAAAAAAA, 1)
  AesSwapN(q, 2, 3, $55555555, $AAAAAAAA, 1)
  AesSwapN(q, 4, 5, $55555555, $AAAAAAAA, 1)
  AesSwapN(q, 6, 7, $55555555, $AAAAAAAA, 1)

  AesSwapN(q, 0, 2, $33333333, $CCCCCCCC, 2)
  AesSwapN(q, 1, 3, $33333333, $CCCCCCCC, 2)
  AesSwapN(q, 4, 6, $33333333, $CCCCCCCC, 2)
  AesSwapN(q, 5, 7, $33333333, $CCCCCCCC, 2)

  AesSwapN(q, 0, 4, $0F0F0F0F, $F0F0F0F0, 4)
  AesSwapN(q, 1, 5, $0F0F0F0F, $F0F0F0F0, 4)
  AesSwapN(q, 2, 6, $0F0F0F0F, $F0F0F0F0, 4)
  AesSwapN(q, 3, 7, $0F0F0F0F, $F0F0F0F0, 4)
EndProcedure

; ----------------------------------------------------------------------
;  AesSubWord(x) - the key schedule's SubWord, done through the SAME
;  bitsliced S-box, so it too has no table.  bearssl_aes_ct.c:240-254.
;
;  IT RUNS ON KEY MATERIAL, which is why it matters that it is the
;  constant-time circuit and not a lookup.  A table-driven key schedule
;  with a bitsliced cipher would leak the key at install time and be
;  constant-time for everything afterwards, which is the worst of both
;  and easy to write by accident.
;
;  The word is broadcast into all eight lanes because the circuit works
;  on eight bit-planes at once and only one byte's worth of answer is
;  wanted; orthogonalising, substituting and orthogonalising back leaves
;  the substituted word in lane 0.
; ----------------------------------------------------------------------
Procedure.i AesSubWord(x.i)
  Protected i.i
  i = 0
  While i < #AES_QWORDS
    secAesSubQ[i] = x
    i = i + 1
  Wend
  AesOrtho(@secAesSubQ[0])
  AesSbox(@secAesSubQ[0])
  AesOrtho(@secAesSubQ[0])
  ProcedureReturn secAesSubQ[0]
EndProcedure

; ======================================================================
;  THE ROUND STEPS
; ======================================================================

; ----------------------------------------------------------------------
;  AesShiftRows(q) / AesInvShiftRows(q).
;
;  In the bitsliced layout a row of the AES state is a field of bits
;  inside every word, so ShiftRows is a fixed permutation of bit
;  positions and is written as masks and shifts rather than as byte
;  moves.  bearssl_aes_ct.c ShiftRows and aes_ct_dec.c:98-112.
;
;  THE TWO ARE MIRROR IMAGES AND THE MASKS ARE THE PLACE TO CHECK IT.
;  Forward:  $0000FC00 >> 2, $00000300 << 6  (row 1 left by one byte)
;  Inverse:  $00003F00 << 2, $0000C000 >> 6  (row 1 right by one byte)
;  Row 2's pair ($00F00000 / $000F0000, shift 4) is symmetric in both
;  because rotating a four-element row by two is its own inverse; only
;  rows 1 and 3 differ.  If a future edit makes the two identical, that
;  is the bug.
; ----------------------------------------------------------------------
Procedure AesShiftRows(q.i)
  Protected i.i
  Protected x.i
  i = 0
  While i < #AES_QWORDS
    x = PeekI(q + i * #AES_WORD)
    PokeI(q + i * #AES_WORD, (x & $000000FF) | AesLsr(x & $0000FC00, 2) | AesLsl(x & $00000300, 6) | AesLsr(x & $00F00000, 4) | AesLsl(x & $000F0000, 4) | AesLsr(x & $C0000000, 6) | AesLsl(x & $3F000000, 2))
    i = i + 1
  Wend
EndProcedure

Procedure AesInvShiftRows(q.i)
  Protected i.i
  Protected x.i
  i = 0
  While i < #AES_QWORDS
    x = PeekI(q + i * #AES_WORD)
    PokeI(q + i * #AES_WORD, (x & $000000FF) | AesLsl(x & $00003F00, 2) | AesLsr(x & $0000C000, 6) | AesLsl(x & $000F0000, 4) | AesLsr(x & $00F00000, 4) | AesLsl(x & $03000000, 6) | AesLsr(x & $FC000000, 2))
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  AesMixColumns(q) - the forward MixColumns, bitsliced.
;
;  Multiplying a column by the MDS matrix is, plane by plane, a fixed
;  pattern of XORs of the plane with itself rotated - which is what
;  these eight lines are.  r_k is plane k rotated right by one byte;
;  AesRotr(_, 16) is the rotation by two bytes.  There is no GF(256)
;  multiply table and no xtime chain because in this representation
;  there is nothing to multiply: the carry structure of xtime is already
;  baked into which planes appear in which output.
; ----------------------------------------------------------------------
Procedure AesMixColumns(q.i)
  Protected q0.i
  Protected q1.i
  Protected q2.i
  Protected q3.i
  Protected q4.i
  Protected q5.i
  Protected q6.i
  Protected q7.i
  Protected r0.i
  Protected r1.i
  Protected r2.i
  Protected r3.i
  Protected r4.i
  Protected r5.i
  Protected r6.i
  Protected r7.i
  q0 = PeekI(q + 0 * #AES_WORD)
  q1 = PeekI(q + 1 * #AES_WORD)
  q2 = PeekI(q + 2 * #AES_WORD)
  q3 = PeekI(q + 3 * #AES_WORD)
  q4 = PeekI(q + 4 * #AES_WORD)
  q5 = PeekI(q + 5 * #AES_WORD)
  q6 = PeekI(q + 6 * #AES_WORD)
  q7 = PeekI(q + 7 * #AES_WORD)
  r0 = AesRotr(q0, 8)
  r1 = AesRotr(q1, 8)
  r2 = AesRotr(q2, 8)
  r3 = AesRotr(q3, 8)
  r4 = AesRotr(q4, 8)
  r5 = AesRotr(q5, 8)
  r6 = AesRotr(q6, 8)
  r7 = AesRotr(q7, 8)
  PokeI(q + 0 * #AES_WORD, q7 ! r7 ! r0 ! AesRotr(q0 ! r0, 16))
  PokeI(q + 1 * #AES_WORD, q0 ! r0 ! q7 ! r7 ! r1 ! AesRotr(q1 ! r1, 16))
  PokeI(q + 2 * #AES_WORD, q1 ! r1 ! r2 ! AesRotr(q2 ! r2, 16))
  PokeI(q + 3 * #AES_WORD, q2 ! r2 ! q7 ! r7 ! r3 ! AesRotr(q3 ! r3, 16))
  PokeI(q + 4 * #AES_WORD, q3 ! r3 ! q7 ! r7 ! r4 ! AesRotr(q4 ! r4, 16))
  PokeI(q + 5 * #AES_WORD, q4 ! r4 ! r5 ! AesRotr(q5 ! r5, 16))
  PokeI(q + 6 * #AES_WORD, q5 ! r5 ! r6 ! AesRotr(q6 ! r6, 16))
  PokeI(q + 7 * #AES_WORD, q6 ! r6 ! r7 ! AesRotr(q7 ! r7, 16))
EndProcedure

; ----------------------------------------------------------------------
;  AesInvMixColumns(q) - bearssl_aes_ct_dec.c:120-151.
;
;  The inverse MDS matrix has entries 0e 0b 0d 09 where the forward one
;  has 02 03 01 01, so the XOR patterns are much denser - that is the
;  whole difference and it is why this procedure is four times the text
;  of the forward one.  It is copied structurally from the source cited
;  above rather than re-derived, because re-deriving eight rows of a
;  bitsliced matrix product by hand is exactly the kind of work that
;  produces something that passes half the vectors.
; ----------------------------------------------------------------------
Procedure AesInvMixColumns(q.i)
  Protected q0.i
  Protected q1.i
  Protected q2.i
  Protected q3.i
  Protected q4.i
  Protected q5.i
  Protected q6.i
  Protected q7.i
  Protected r0.i
  Protected r1.i
  Protected r2.i
  Protected r3.i
  Protected r4.i
  Protected r5.i
  Protected r6.i
  Protected r7.i
  q0 = PeekI(q + 0 * #AES_WORD)
  q1 = PeekI(q + 1 * #AES_WORD)
  q2 = PeekI(q + 2 * #AES_WORD)
  q3 = PeekI(q + 3 * #AES_WORD)
  q4 = PeekI(q + 4 * #AES_WORD)
  q5 = PeekI(q + 5 * #AES_WORD)
  q6 = PeekI(q + 6 * #AES_WORD)
  q7 = PeekI(q + 7 * #AES_WORD)
  r0 = AesRotr(q0, 8)
  r1 = AesRotr(q1, 8)
  r2 = AesRotr(q2, 8)
  r3 = AesRotr(q3, 8)
  r4 = AesRotr(q4, 8)
  r5 = AesRotr(q5, 8)
  r6 = AesRotr(q6, 8)
  r7 = AesRotr(q7, 8)

  PokeI(q + 0 * #AES_WORD, q5 ! q6 ! q7 ! r0 ! r5 ! r7 ! AesRotr(q0 ! q5 ! q6 ! r0 ! r5, 16))
  PokeI(q + 1 * #AES_WORD, q0 ! q5 ! r0 ! r1 ! r5 ! r6 ! r7 ! AesRotr(q1 ! q5 ! q7 ! r1 ! r5 ! r6, 16))
  PokeI(q + 2 * #AES_WORD, q0 ! q1 ! q6 ! r1 ! r2 ! r6 ! r7 ! AesRotr(q0 ! q2 ! q6 ! r2 ! r6 ! r7, 16))
  PokeI(q + 3 * #AES_WORD, q0 ! q1 ! q2 ! q5 ! q6 ! r0 ! r2 ! r3 ! r5 ! AesRotr(q0 ! q1 ! q3 ! q5 ! q6 ! q7 ! r0 ! r3 ! r5 ! r7, 16))
  PokeI(q + 4 * #AES_WORD, q1 ! q2 ! q3 ! q5 ! r1 ! r3 ! r4 ! r5 ! r6 ! r7 ! AesRotr(q1 ! q2 ! q4 ! q5 ! q7 ! r1 ! r4 ! r5 ! r6, 16))
  PokeI(q + 5 * #AES_WORD, q2 ! q3 ! q4 ! q6 ! r2 ! r4 ! r5 ! r6 ! r7 ! AesRotr(q2 ! q3 ! q5 ! q6 ! r2 ! r5 ! r6 ! r7, 16))
  PokeI(q + 6 * #AES_WORD, q3 ! q4 ! q5 ! q7 ! r3 ! r5 ! r6 ! r7 ! AesRotr(q3 ! q4 ! q6 ! q7 ! r3 ! r6 ! r7, 16))
  PokeI(q + 7 * #AES_WORD, q4 ! q5 ! q6 ! r4 ! r6 ! r7 ! AesRotr(q4 ! q5 ! q7 ! r4 ! r7, 16))
EndProcedure

; ----------------------------------------------------------------------
;  AesAddRoundKey(q, sk) - eight XORs.  sk is the ADDRESS of eight
;  expanded schedule words.
; ----------------------------------------------------------------------
Procedure AesAddRoundKey(q.i, sk.i)
  Protected i.i
  i = 0
  While i < #AES_QWORDS
    PokeI(q + i * #AES_WORD, PeekI(q + i * #AES_WORD) ! PeekI(sk + i * #AES_WORD))
    i = i + 1
  Wend
EndProcedure

; ======================================================================
;  THE TWO CIPHERS
; ======================================================================

; ----------------------------------------------------------------------
;  AesBitsliceEncrypt(q) - FIPS-197 section 5.1's Cipher, on the two
;  blocks currently bitsliced in q.
;
;      AddRoundKey(0)
;      for round = 1 to Nr-1:  SubBytes ShiftRows MixColumns AddRoundKey
;      SubBytes ShiftRows AddRoundKey(Nr)
;
;  The last round has no MixColumns.  That omission is the single most
;  commonly mistranslated line in AES and it is why FIPS-197 Appendix
;  C's round[10] entry has an s_row and a k_sch but no m_col: the gate
;  checks exactly that.
;
;  The loop bound is the PUBLIC round count.  Nothing in here sees a
;  data bit.
; ----------------------------------------------------------------------
Procedure AesBitsliceEncrypt(q.i)
  Protected u.i
  AesAddRoundKey(q, @secAesSkExp[0])
  u = 1
  While u < AesNumRounds
    AesSbox(q)
    AesShiftRows(q)
    AesMixColumns(q)
    AesAddRoundKey(q, @secAesSkExp[0] + u * #AES_QWORDS * #AES_WORD)
    u = u + 1
  Wend
  AesSbox(q)
  AesShiftRows(q)
  AesAddRoundKey(q, @secAesSkExp[0] + AesNumRounds * #AES_QWORDS * #AES_WORD)
EndProcedure

; ----------------------------------------------------------------------
;  AesBitsliceDecrypt(q) - FIPS-197 section 5.3's InvCipher.
;  bearssl_aes_ct_dec.c:154-170.
;
;      AddRoundKey(Nr)
;      for round = Nr-1 downto 1:
;          InvShiftRows InvSubBytes AddRoundKey(round) InvMixColumns
;      InvShiftRows InvSubBytes AddRoundKey(0)
;
;  THIS IS THE STRAIGHT INVERSE CIPHER, NOT THE EQUIVALENT ONE.  FIPS-197
;  section 5.3.5 offers an "equivalent inverse cipher" that reorders the
;  steps to match the forward cipher's shape, at the price of a SECOND
;  key schedule with InvMixColumns applied to every round key.  This
;  file does not do that: it uses the forward schedule, read in reverse
;  round order, exactly as written above.
;
;  The choice matters for one practical reason and one honest one.  The
;  practical one: one schedule means AesSetKey serves encrypt and
;  decrypt alike, and RFC 3394 unwrap - the caller this file was written
;  for - never encrypts, so a second schedule would be pure cost.  The
;  honest one: FIPS-197 Appendix C prints the intermediate values of
;  BOTH forms separately, and the gate can therefore tell which one is
;  implemented rather than accepting either.  Note the AddRoundKey and
;  InvMixColumns order inside the loop - key first, then mix - which is
;  the part that differs from the equivalent form and the part a
;  "tidying" edit would swap.
; ----------------------------------------------------------------------
Procedure AesBitsliceDecrypt(q.i)
  Protected u.i
  AesAddRoundKey(q, @secAesSkExp[0] + AesNumRounds * #AES_QWORDS * #AES_WORD)
  u = AesNumRounds - 1
  While u > 0
    AesInvShiftRows(q)
    AesInvSbox(q)
    AesAddRoundKey(q, @secAesSkExp[0] + u * #AES_QWORDS * #AES_WORD)
    AesInvMixColumns(q)
    u = u - 1
  Wend
  AesInvShiftRows(q)
  AesInvSbox(q)
  AesAddRoundKey(q, @secAesSkExp[0])
EndProcedure

; ======================================================================
;  THE KEY SCHEDULE
; ======================================================================

; ----------------------------------------------------------------------
;  AesKeysched(key, keylen) - FIPS-197 section 5.2, through the
;  bitsliced S-box.  bearssl_aes_ct.c:256-310.  Returns the round count,
;  or 0 for a bad length.  Fills secAesCompSkey.
;
;  THE ONLY CONTROL DECISION IS THE SWITCH ON keylen, WHICH IS PUBLIC.
;  A key's LENGTH is not a secret - it is in the protocol - while its
;  BYTES are, and nothing below branches on a byte.
;
;  THE COMPRESSED FORM.  Each round-key word is stored twice during
;  construction (once per bitslice lane) and then squeezed into one word
;  by keeping the even bits of one copy and the odd bits of the other.
;  That is not a space optimisation for its own sake: it is what lets
;  AesSkeyExpand rebuild both lanes with two masks and two shifts,
;  instead of re-running the orthogonalisation on every block.
; ----------------------------------------------------------------------
Procedure.i AesKeysched(key.i, keylen.i)
  Protected numRounds.i
  Protected nk.i
  Protected nkf.i
  Protected tmp.i
  Protected i.i
  Protected j.i
  Protected k.i

  numRounds = 0
  If keylen = 16
    numRounds = 10
  EndIf
  If keylen = 24
    numRounds = 12
  EndIf
  If keylen = 32
    numRounds = 14
  EndIf
  If numRounds = 0
    ProcedureReturn 0
  EndIf

  nk = keylen >> 2
  nkf = (numRounds + 1) << 2

  ; The key itself, decoded little-endian into both lanes.
  tmp = 0
  i = 0
  While i < nk
    tmp = AesDec32le(key + i * 4)
    secAesKeyTmp[i * 2] = tmp
    secAesKeyTmp[i * 2 + 1] = tmp
    i = i + 1
  Wend

  ; The expansion.  j counts within the current nk-word group and k
  ; indexes Rcon.  `nk > 6 And j = 4` is the AES-256-only second SubWord
  ; of FIPS-197 section 5.2 - it can only fire for nk = 8, and it is the
  ; entire difference between the 192-bit and the 256-bit schedule.
  i = nk
  j = 0
  k = 0
  While i < nkf
    If j = 0
      tmp = AesRotr(tmp, 8)
      tmp = AesSubWord(tmp) ! AesRcon[k]
    Else
      If nk > 6 And j = 4
        tmp = AesSubWord(tmp)
      EndIf
    EndIf
    tmp = tmp ! secAesKeyTmp[(i - nk) * 2]
    secAesKeyTmp[i * 2] = tmp
    secAesKeyTmp[i * 2 + 1] = tmp
    j = j + 1
    If j = nk
      j = 0
      k = k + 1
    EndIf
    i = i + 1
  Wend

  ; Orthogonalise the round keys four words at a time, then compress.
  i = 0
  While i < nkf
    AesOrtho(@secAesKeyTmp[0] + (i * 2) * #AES_WORD)
    i = i + 4
  Wend

  i = 0
  While i < nkf
    secAesCompSkey[i] = (secAesKeyTmp[i * 2] & $55555555) | (secAesKeyTmp[i * 2 + 1] & $AAAAAAAA)
    i = i + 1
  Wend

  ProcedureReturn numRounds
EndProcedure

; ----------------------------------------------------------------------
;  AesSkeyExpand() - rebuild the two lanes from the compressed schedule.
;  bearssl_aes_ct.c:312-327.  Straight-line over the public round count.
; ----------------------------------------------------------------------
Procedure AesSkeyExpand()
  Protected u.i
  Protected v.i
  Protected n.i
  Protected x.i
  Protected y.i
  n = (AesNumRounds + 1) << 2
  u = 0
  v = 0
  While u < n
    x = secAesCompSkey[u] & $55555555
    secAesSkExp[v] = x | AesLsl(x, 1)
    y = secAesCompSkey[u] & $AAAAAAAA
    secAesSkExp[v + 1] = y | AesLsr(y, 1)
    u = u + 1
    v = v + 2
  Wend
EndProcedure

; ======================================================================
;  THE PUBLIC SURFACE
; ======================================================================

; ----------------------------------------------------------------------
;  AesSetKey(key, keylen) - install a key.  Returns the round count (10,
;  12 or 14) or 0.
;
;  A BAD LENGTH IS A REFUSAL, NOT A CLAMP, and it LEAVES NO KEY
;  INSTALLED.  A caller that passes 20 has a bug; silently treating it
;  as 16 would encrypt with three quarters of the intended key and
;  produce a ciphertext that decrypts perfectly at both ends of a
;  broken pair.  Refusing means AesEncryptBlock and AesDecryptBlock also
;  refuse until a real key arrives, so the bug surfaces at the first
;  block instead of at the far end of a network.
;
;  THE ROUND CONSTANTS ARE LOADED HERE, not in a DataSection and not at
;  file scope, because a Global Dim has no initialiser in this dialect.
;  Ten stores per key installation is not a cost anybody can measure.
; ----------------------------------------------------------------------
Procedure.i AesSetKey(key.i, keylen.i)
  AesRcon[0] = $01
  AesRcon[1] = $02
  AesRcon[2] = $04
  AesRcon[3] = $08
  AesRcon[4] = $10
  AesRcon[5] = $20
  AesRcon[6] = $40
  AesRcon[7] = $80
  AesRcon[8] = $1B
  AesRcon[9] = $36

  AesNumRounds = 0
  AesKeyLen = 0
  AesNumRounds = AesKeysched(key, keylen)
  If AesNumRounds = 0
    ProcedureReturn 0
  EndIf
  AesKeyLen = keylen
  AesSkeyExpand()
  ProcedureReturn AesNumRounds
EndProcedure

; ----------------------------------------------------------------------
;  AesKeyBits() - 128, 192, 256, or 0 when no key is installed.
; ----------------------------------------------------------------------
Procedure.i AesKeyBits()
  ProcedureReturn AesKeyLen * 8
EndProcedure

; ----------------------------------------------------------------------
;  AesLoadBlock(src) / AesStoreBlock(dst) - the packed/bitsliced seam.
;
;  THE BITSLICE HOLDS TWO BLOCKS AND WE ONLY WANT ONE.  Before
;  orthogonalisation the eight words are lane 0's four state words at
;  even indices and lane 1's at odd ones; the two lanes then run through
;  the whole cipher in the same instructions, because a bitslice
;  operates on bit-planes and a plane is 32 bits wide with 16 bits per
;  lane.
;
;  THE SECOND LANE IS FILLED WITH A COPY OF THE FIRST.  It costs nothing
;  - the cipher runs at exactly the same speed either way - and the
;  alternative of leaving it holding whatever the last call left there
;  means key-derived plaintext sitting in a global between calls.  It
;  also gives the gate a free consistency check: the two lanes must come
;  out identical, and a bug that mixes the lanes (a mask off by one bit
;  in AesSwapN, say) shows up as a mismatch rather than as a wrong
;  answer that has to be recognised.
;
;  HALF THE THROUGHPUT IS LEFT ON THE TABLE and that is deliberate.  A
;  two-block entry point would be the right thing for a bulk mode; RFC
;  3394 is strictly serial - block t+1's input contains block t's output
;  - so it could not use one, and this file has no other caller.  Adding
;  it now would be an unused API with an untested second path.
; ----------------------------------------------------------------------
Procedure AesLoadBlock(src.i)
  Protected w0.i
  Protected w1.i
  Protected w2.i
  Protected w3.i
  w0 = AesDec32le(src)
  w1 = AesDec32le(src + 4)
  w2 = AesDec32le(src + 8)
  w3 = AesDec32le(src + 12)
  AesQ[0] = w0
  AesQ[1] = w0
  AesQ[2] = w1
  AesQ[3] = w1
  AesQ[4] = w2
  AesQ[5] = w2
  AesQ[6] = w3
  AesQ[7] = w3
  AesOrtho(@AesQ[0])
EndProcedure

Procedure AesStoreBlock(dst.i)
  AesOrtho(@AesQ[0])
  AesEnc32le(dst,      AesQ[0])
  AesEnc32le(dst + 4,  AesQ[2])
  AesEnc32le(dst + 8,  AesQ[4])
  AesEnc32le(dst + 12, AesQ[6])
EndProcedure

; ----------------------------------------------------------------------
;  AesEncryptBlock(src, dst) / AesDecryptBlock(src, dst) - one 16-byte
;  block each, ECB, using the installed key.  Return #AES_BLOCK, or 0
;  when no key is installed.
;
;  ECB IS NOT A MODE OF OPERATION AND MUST NOT BE USED AS ONE.  These
;  are the raw block cipher.  Encrypting more than one block with them
;  directly leaks equality between blocks and is the mistake behind
;  every "ECB penguin" picture ever published.  They are exposed
;  because RFC 3394 is defined in terms of single-block AES with a
;  chaining structure of its own, because FIPS-197 and the CAVP
;  known-answer vectors are single-block, and for no other reason.  A
;  caller that wants to protect a message wants an AEAD.
;
;  src AND dst MAY BE THE SAME ADDRESS.  The whole block is loaded into
;  the bitslice before anything is written back, so in-place is safe by
;  construction rather than by accident.  Partially overlapping buffers
;  are not - and cannot be detected here - so do not.
; ----------------------------------------------------------------------
Procedure.i AesEncryptBlock(src.i, dst.i)
  If AesNumRounds = 0
    ProcedureReturn 0
  EndIf
  AesLoadBlock(src)
  AesBitsliceEncrypt(@AesQ[0])
  AesStoreBlock(dst)
  ProcedureReturn #AES_BLOCK
EndProcedure

Procedure.i AesDecryptBlock(src.i, dst.i)
  If AesNumRounds = 0
    ProcedureReturn 0
  EndIf
  AesLoadBlock(src)
  AesBitsliceDecrypt(@AesQ[0])
  AesStoreBlock(dst)
  ProcedureReturn #AES_BLOCK
EndProcedure

; ======================================================================
;  CTR MODE - THE ONE MODE OF OPERATION THIS FILE OFFERS
; ======================================================================
;
;  WHY IT IS HERE AT ALL.  Until now this file was the raw block cipher
;  plus a key schedule, because its only callers were RFC 3394 key wrap
;  and the CAVP known-answer vectors, and both are single-block.  GCM is
;  not: the AEAD needs a keystream, needs E_K(0) for the GHASH key, and
;  needs the tag mask, and all three are CTR.  Putting CTR in gcm.pi4
;  instead would have put a second copy of the bitslice seam in a second
;  file, which is how two AES implementations end up in one image and
;  only one of them gets gated.
;
;  IT IS THE SAME SHAPE AS THE OTHER FAMILIES' AesCtrCore, deliberately,
;  because it is the same algorithm and a reader comparing the copies
;  should not have to also compare two designs.  What differs is forced
;  by the target and is listed in point 1 of this file's header: `.i` is
;  eight bytes here, so every value that stands for a 32-bit word goes
;  through AesLsl/AesLsr and is masked with #AES_W32.
;
;  TWO BLOCKS PER PASS, NOT ONE.  AesEncryptBlock fills both bitslice
;  lanes with the SAME block and throws half the work away, which is the
;  right trade for a serial mode.  CTR is not serial - counter c and
;  counter c+1 are independent - so this loop puts c in lane 0 and c + 1
;  in lane 1 and gets both keystream blocks out of one cipher call.  That
;  is the whole reason the two-lane design was kept.
;
;  CONSTANT TIME.  The only control here is driven by the PUBLIC byte
;  length.  No branch, no index and no shift amount depends on the key or
;  on the data, so two keys or two plaintexts of the same length run in
;  exactly the same number of instructions.  The gate checks that.
;
;  THE COUNTER IS THIRTY-TWO BITS AND IS MASKED TO THIRTY-TWO BITS.
;  On a 32-bit `.i` the increment wrapped for free at 2^32, which is what
;  SP 800-38A and GCM's J0 arithmetic both specify.  Here it would not
;  wrap, so `cc` is masked at every increment.  Reaching the wrap needs
;  64 GiB under one nonce and no caller should ever be near it, but a
;  counter that silently stops being 32 bits is exactly the kind of
;  difference that shows up years later as an interop failure.
; ----------------------------------------------------------------------

; ----------------------------------------------------------------------
;  AesCtrInit(key, keylen) - install a key for CTR.  Returns the round
;  count (10, 12 or 14) or 0 for a refused length.
;
;  IT IS AesSetKey AND NOTHING ELSE.  The name exists because the other
;  families' CTR callers spell it this way and because a caller that has
;  only ever used the AEAD should not have to know that key installation
;  is shared with the key-wrap path.  A separate entry point that did
;  something different would be a second key schedule to gate.
; ----------------------------------------------------------------------
Procedure.i AesCtrInit(key.i, keylen.i)
  ProcedureReturn AesSetKey(key, keylen)
EndProcedure

; ----------------------------------------------------------------------
;  AesCtrCore(nonce, cc, src, dst, len) - CTR keystream XOR.  The AES
;  input block for counter value c is nonce[0..11] || big-endian(c).
;  dst = src XOR keystream; src and dst MAY be the same address.  Returns
;  the counter value that follows the last block used.
;
;  NO KEY IS A REFUSAL AND IT WRITES NOTHING.  Returns -1, which is not a
;  legal counter value, where a real run returns 0..$FFFFFFFF.  The other
;  families' copies do not check, because there the only caller is GCM
;  and GCM has already checked; this file is included by the monitor and
;  by key wrap as well, so the check is worth its two instructions.  A
;  CTR with no key installed would encrypt under whatever schedule was
;  left in .bss - which for a freshly cleared image is an all-zero key,
;  and a keystream from an all-zero key is not a failure anybody notices
;  by looking at the output.
;
;  src AND dst MAY ALIAS EXACTLY.  Each output byte is written after its
;  input byte is read, one byte at a time, so in-place is safe.  Partial
;  overlap is not, and cannot be detected here.
; ----------------------------------------------------------------------
Procedure.i AesCtrCore(nonce.i, cc.i, src.i, dst.i, len.i)
  Protected iv0.i
  Protected iv1.i
  Protected iv2.i
  Protected u.i
  Protected n.i

  If AesNumRounds = 0
    ProcedureReturn -1
  EndIf

  AesSkeyExpand()
  iv0 = AesDec32le(nonce)
  iv1 = AesDec32le(nonce + 4)
  iv2 = AesDec32le(nonce + 8)
  cc = cc & #AES_W32

  While len > 0
    AesQ[0] = iv0
    AesQ[1] = iv0
    AesQ[2] = iv1
    AesQ[3] = iv1
    AesQ[4] = iv2
    AesQ[5] = iv2
    AesQ[6] = AesSwap32(cc)
    AesQ[7] = AesSwap32((cc + 1) & #AES_W32)
    AesOrtho(@AesQ[0])
    AesBitsliceEncrypt(@AesQ[0])
    AesOrtho(@AesQ[0])
    AesEnc32le(@secAesKs[0],      AesQ[0])
    AesEnc32le(@secAesKs[0] + 4,  AesQ[2])
    AesEnc32le(@secAesKs[0] + 8,  AesQ[4])
    AesEnc32le(@secAesKs[0] + 12, AesQ[6])
    AesEnc32le(@secAesKs[0] + 16, AesQ[1])
    AesEnc32le(@secAesKs[0] + 20, AesQ[3])
    AesEnc32le(@secAesKs[0] + 24, AesQ[5])
    AesEnc32le(@secAesKs[0] + 28, AesQ[7])

    n = len
    If n > 32
      n = 32
    EndIf
    u = 0
    While u < n
      PokeB(dst + u, (PeekA(src + u) & 255) ! (secAesKs[u] & 255))
      u = u + 1
    Wend

    If len <= 32
      cc = (cc + 1) & #AES_W32
      If len > 16
        cc = (cc + 1) & #AES_W32
      EndIf
      len = 0
    Else
      src = src + 32
      dst = dst + 32
      len = len - 32
      cc = (cc + 2) & #AES_W32
    EndIf
  Wend

  ProcedureReturn cc
EndProcedure

; ----------------------------------------------------------------------
;  AesCtrRun(iv, src, dst, len) - the house-style CTR entry: iv is a
;  16-byte initial counter block (12-byte nonce || 4-byte big-endian
;  counter), as SP 800-38A specifies.  Splits it and calls the core.
; ----------------------------------------------------------------------
Procedure.i AesCtrRun(iv.i, src.i, dst.i, len.i)
  Protected cc.i
  cc = ((PeekA(iv + 12) & 255) << 24) | ((PeekA(iv + 13) & 255) << 16) | ((PeekA(iv + 14) & 255) << 8) | (PeekA(iv + 15) & 255)
  ProcedureReturn AesCtrCore(iv, cc, src, dst, len)
EndProcedure

; ----------------------------------------------------------------------
;  AesWipe() - zero every buffer in this file and forget the key.
;
;  NOT AUTOMATIC, for the reason pbkdf2.pi4 gives about its own wipe:
;  the caller decides when the key stops being needed, and a library
;  that wiped on the way out of every block would be unusable.  Call it
;  when the KEK is finished with.
;
;  IT WIPES AesQ TOO.  That array holds the last plaintext or ciphertext
;  block in bitsliced form, which for a key wrap IS key material.
; ----------------------------------------------------------------------
Procedure AesWipe()
  Protected i.i
  i = 0
  While i < 120
    secAesKeyTmp[i] = 0
    secAesSkExp[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < 60
    secAesCompSkey[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #AES_QWORDS
    AesQ[i] = 0
    secAesSubQ[i] = 0
    i = i + 1
  Wend
  ; The CTR keystream is key material by any useful definition: XORed
  ; against a captured ciphertext it IS the plaintext.
  i = 0
  While i < 32
    secAesKs[i] = 0
    i = i + 1
  Wend
  AesNumRounds = 0
  AesKeyLen = 0
EndProcedure
; ==== PORTABLE CORE A64 END ====
