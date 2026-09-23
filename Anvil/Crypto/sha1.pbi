; ======================================================================
;  sha1.pbi - SHA-1, ON THE RASPBERRY PI 4 (BCM2711, AArch64)
; ======================================================================
;
;     XIncludeFile "Anvil/Crypto/sha1.pbi"
;
;
;  SHA-1 (FIPS 180-4 section 6.1; the same algorithm is written out in
;  full, with a reference implementation, in RFC 3174, which IS ON THIS
;  DISK at RaspberryPi4/Reference/rfc3174.txt and is what every constant
;  below cites). This file is deliberately shaped like
;  Anvil/Core/sha256.pbi - same procedure names one digit apart,
;  same address-passing compression function, same snapshot/restore
;  pair - so that a reader who has understood one has understood both
;  and a caller can swap hashes by swapping an include.
;
;  API (module-global context - one digest in progress at a time):
;    Sha1Begin()                 start a fresh digest
;    Sha1Update(src.i, len.i)    absorb len bytes at address src
;    Sha1End(dst.i)              finish; writes 20 bytes at dst
;    Sha1Of(src.i, len.i, dst.i) the one-shot: Begin + Update + End
;    Sha1Snapshot(dst.i)         save the 92-byte running state
;    Sha1Restore(src.i)          reload a 92-byte running state
;
;  DEPENDENCIES: NONE. This file includes no other library, per the
;  house rule - a library never includes a library, the MAIN file lists
;  what it needs. It touches no peripheral and reads no register.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO. The pragma
;  below is not file-scoped; every variable compiled after this include
;  must be declared before use as well. A requirement a library puts on
;  its caller belongs in the header the caller reads.
;
;  CONSTANT TIME. SHA-1 has no data-dependent branch and no
;  secret-indexed table; the round function here is straight-line and
;  every control decision is driven by LENGTH, never by message bytes.
;  That matters more here than it did for SHA-256, because the first
;  caller of this file feeds it a Wi-Fi passphrase 8192 times over.
;
;  ======================================================================
;   WHY A BROKEN PRIMITIVE IS IN THIS TREE AT ALL
;  ======================================================================
;
;  SHA-1 IS BROKEN FOR COLLISION RESISTANCE and nothing in this file
;  argues otherwise. SHAttered (2017) produced a real colliding pair and
;  the chosen-prefix attack (2020) made that cheap. DO NOT REACH FOR
;  THIS FILE FOR A SIGNATURE, A CERTIFICATE, A FIRMWARE DIGEST OR A
;  TRANSCRIPT HASH. Anvil/Core/sha256.pbi is next to it and is
;  what every one of those wants.
;
;  IT IS HERE FOR EXACTLY ONE REASON: WPA2-PSK IS DEFINED ON IT.
;  IEEE 802.11 fixes PBKDF2-HMAC-SHA1 for the passphrase-to-PMK mapping
;  and HMAC-SHA1 for the four-way handshake's PRF and EAPOL-Key MIC.
;  There is no version of "join this access point" that does not compute
;  SHA-1, and the collision attacks do not touch the two properties that
;  are actually being used here - PBKDF2 needs a pseudorandom function
;  and HMAC needs unforgeability, and HMAC-SHA1 remains unbroken for
;  both. That is the whole justification, it is narrow on purpose, and
;  any use of this file outside that role wants challenging.
;
;  ======================================================================
;   .i IS 64 BITS HERE, AND SHA-1 IS DEFINED ON 32-BIT WORDS
;  ======================================================================
;
;  Everything sha256.pi4's header established about that mismatch
;  applies unchanged, and the same three traps are the ones that bite.
;  They are restated rather than cross-referenced, because a reader
;  debugging a wrong digest in THIS file should not have to open
;  another one first.
;
;  ---- 1. THE STRIDE IS 8, NOT 4. -------------------------------------
;
;  Sha1Round takes the hash state BY ADDRESS so that Sha1End can run the
;  final compression on a scratch copy while the live context survives.
;  An address means an accessor, and Dim Sha1H.i[5] on this target is
;  FORTY bytes, not twenty. PeekL(hv + 4) would read the top half of
;  H[0] as if it were H[1] - deterministic, stable across runs, and not
;  SHA-1. The shape that bug makes is unmistakable and is worth knowing:
;  the tail of the digest comes out as the untouched FIPS initial values
;  (see sha256.pi4's header, where exactly this was measured).
;
;  So the state is walked with PeekI/PokeI at a stride of #SHA1_HWORD.
;  PeekI moves exactly one .i, which is exactly one array element, so
;  the accessor and the stride agree BY CONSTRUCTION and not because
;  someone kept two numbers in step.
;
;  ---- 2. RAW BYTES ARE READ WITH PeekA, NEVER PeekB. -----------------
;
;  Project ruling 2026-08-25: PeekB/PeekC/PeekW follow their type
;  letters and SIGN-EXTEND on every backend; PeekA and PeekU are the
;  unsigned spellings. A byte of $80 read with PeekB is -128, which on a
;  64-bit .i is $FFFFFFFFFFFFFF80 - ORing that into a word sets
;  thirty-two bits, not eight.
;
;  This file gets hit harder by that than sha256.pi4 did. HMAC's ipad
;  and opad blocks are $36 and $5C - safe - but RFC 2202's HMAC-SHA1
;  cases 3, 4, 6 and 7 are eighty bytes of $AA, fifty bytes of $DD, and
;  keys of 80 and 131 bytes of $AA. Every one of those has bit 7 set on
;  every byte. A PeekB here would fail those loudly, which is the good
;  case; what it would ALSO do is pass the short ASCII vectors, which is
;  how a test set gets written that never sees it.
;
;  Every raw byte read here is PeekA. The trailing "& 255" is redundant
;  under that ruling and is kept: it costs one instruction the optimiser
;  sees through, and it states the width at the point of use.
;
;  ---- 3. FOUR-BYTE READS USE PeekN, NEVER PeekL. ---------------------
;
;  PeekL sign-extends as of 2026-08-25. THREE OF THE FIVE SHA-1 INITIAL
;  VALUES have bit 31 set - $EFCDAB89, $98BADCFE, $C3D2E1F0 - and so do
;  two of the four round constants, $8F1BBCDC and $CA62C1D6. Read with
;  PeekL every one would arrive negative, and a negative H poisons the
;  next rotate. The initial values and the round constants are written
;  as literals below rather than read from a table, so the only PeekN
;  sites in this file are the three in Sha1Restore, matching the three
;  PokeN in Sha1Snapshot.
;
;  ---- 4. THE 32-BIT MASK INVARIANT ------------------------------------
;
;      EVERY VALUE THAT REPRESENTS A 32-BIT SHA-1 WORD IS HELD AS A
;      CLEAN NON-NEGATIVE NUMBER IN 0..$FFFFFFFF, AND EVERY OPERATION
;      THAT CAN LEAVE THAT RANGE IS MASKED WITH #SHA1_W32 IMMEDIATELY.
;
;  Where the masks are and are not, and this list differs from
;  sha256.pi4's in one interesting place:
;
;    Sha1Rotl     masks the OUTPUT. THE LEFT SHIFT IS THE WHOLE PROBLEM
;                 and SHA-1 is a rotate-LEFT algorithm, so unlike
;                 SHA-256 - where two of the three shifts were rightward
;                 and self-cleaning - EVERY rotate in this file spills.
;                 There is no correct-by-accident path here.
;    Sha1Ch,
;    Sha1Par,
;    Sha1Maj      NOT masked, on purpose: bitwise AND, OR and XOR of
;                 clean words are clean. A mask here would imply one is
;                 needed, and which operations need one is the whole
;                 question.
;    W[16..79]    the XOR of four clean words is clean and Sha1Rotl
;                 masks what it returns, so the schedule needs nothing.
;    W[0..15]     four zero-extended bytes; cannot exceed 32 bits.
;    temp         FIVE additions, masked once on the total. The running
;                 sum reaches at most 5 * (2^32 - 1), about 2^34.3,
;                 nowhere near overflowing a 64-bit register, so one
;                 mask on the total is exactly equal to five masks.
;    H[i] += x    masked on the way back into the state.
;    bit length   masked; the same weak case as sha256.pi4 states, since
;                 every extraction below ends in "& 255" on a bit below
;                 32 and the masks buy nothing a test can see.
;
;  ---- 4a. THE MASK SCOREBOARD. MEASURED, NOT ARGUED. -----------------
;
;  The claims in point 4 were tested rather than asserted, by building
;  this file with each mask removed and running the whole gate. Out of
;  388 vectors (tools/a64/a64_sha1_check.py --mutate, 2026-08-28):
;
;    variant under test                                   failures
;    -------------------------------------------------    --------
;    Sha1Rotl's OUTPUT mask removed                          0/388
;    Sha1Rotl's INPUT mask removed (right half goes
;      arithmetic)                                           0/388
;    BOTH of Sha1Rotl's masks removed at once              385/388
;    stride of 4 instead of 8                              388/388
;    PeekB, unmasked, on the block's low byte              359/388
;    K(0..19) off by one nibble                            388/388
;    Sha1Par where Sha1Maj belongs (t = 40..59)            388/388
;    S^2 in the message schedule                           388/388
;    79 rounds                                             388/388
;    the padding spill test off by one                       7/388
;    the snapshot counter four bytes low                   186/388
;
;  SO NEITHER ROTATE MASK IS INDIVIDUALLY OBSERVABLE, AND TOGETHER THEY
;  ARE. Each is redundant GIVEN THE OTHER: with the output mask in
;  place every value reaching Sha1Rotl is clean, so the input mask has
;  nothing to clean; with the input mask in place the rubbish the
;  output mask would have removed can only travel upward and never
;  reaches a bit any caller reads. Remove both and dirt from bits
;  32..62 is dragged straight back down into the digest.
;
;  KEEP BOTH. The pair is not belt and braces, it is two halves of one
;  argument, and the file's invariant - every 32-bit value is clean at
;  the point it is produced - is what makes the pair checkable a line
;  at a time instead of by tracing where rubbish can travel. The
;  scoreboard is here so that nobody has to take that on trust, and so
;  that a future edit which makes one of them observable is recognised
;  as news rather than noise. The gate encodes both expectations and
;  fails if either changes.
;
;  ONE MORE THING THE SWEEP TAUGHT, and it is the opposite of what
;  sha256.pi4's header assumes. The trailing "& 255" after each PeekA
;  is described there as redundant. IT IS NOT REDUNDANT HERE - it is
;  what makes a PeekA-to-PeekB slip harmless. Swapping the accessor and
;  LEAVING the mask changes nothing at all, in this file and in
;  hmacsha1.pbi, because the mask cuts the sign extension off before
;  anything sees it. The mutation only bites when the accessor AND the
;  mask both go. That is an argument for keeping the mask that is
;  stronger than the reviewability one it was kept for.
;
;  ---- 5. THE BYTE COUNTER IS SUMMED AT FULL WIDTH --------------------
;
;  The 32-bit families detect the wrap of their low counter word by
;  flipping both sign bits and comparing, because they have no wider
;  integer. THAT TRICK IS SILENTLY WRONG ON THIS TARGET: nothing wraps
;  at 32 bits here, the comparison never fires, the high word never
;  increments, and the padded bit length is short by 2^32 for any
;  message over 4 GiB. Since .i IS the 64-bit accumulator the trick was
;  emulating, Sha1Update does the sum once at full width and splits
;  afterwards. This was measured on sha256.pi4 (variant F: the trick
;  restored, all 23 vectors still green) and is REASONING here, not a
;  reproduction - no bench in this project can hash 4 GiB.
;
;  The counter is still STORED as two 32-bit words because the snapshot
;  is a wire format.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT - 2026-08-28
;  ======================================================================
;
;  PROVEN by known-answer test - the only kind that counts for a hash -
;  under the project's own A64 oracle tools/a64/a64_interp.py, running a
;  real image built by pmfc.exe for -t pi4. The gate is
;  tools/a64/a64_sha1_check.py and every expected digest in it is READ
;  OFF THE DISK, never typed and never taken from running this file:
;
;    * ALL 65 NIST CAVP SHA1ShortMsg vectors (lengths 0 to 64 bytes),
;      parsed out of RaspberryPi4/Reference/cavp_SHA1ShortMsg.rsp.
;    * ALL 64 NIST CAVP SHA1LongMsg vectors (lengths 1 KiB to 6400
;      bytes), parsed out of RaspberryPi4/Reference/cavp_SHA1LongMsg.rsp.
;    * The three short RFC 3174 section 7.3 vectors, parsed out of
;      RaspberryPi4/Reference/rfc3174.txt line 1030 - "abc", the 56-byte
;      "abcdbcdecdef..." two-block message, and ten repeats of the
;      80-character digit string.
;    * Every short vector also fed in 1-, 3-, 7- and 64-byte chunks, so
;      a split point that changed an answer would show.
;    * Snapshot/Restore across a mid-block seam matching the one-shot
;      digest of the same bytes.
;
;  The CAVP files are NIST's own validation vectors, generated by NIST
;  and not by anything in this tree, which is the property that makes
;  them worth having. They cover every message length from 0 to 64
;  bytes - which is every distinct padding case there is, including the
;  two that spill into a second block (55/56 and 63/64) - and they were
;  downloaded on 2026-08-28 from
;  csrc.nist.gov/.../shs/shabytetestvectors.zip.
;
;  MUTATION-TESTED. The gate is run with --mutate, which rebuilds this
;  file with one deliberate defect at a time and REQUIRES the gate to go
;  red for each. See the gate's own header for the list; the point of it
;  is that a gate nobody has watched fail is a gate nobody has a reason
;  to believe.
;
;  NOT PROVEN:
;
;    * NOTHING HERE HAS RUN ON SILICON YET. The oracle is a model of the
;      instruction set, not of the chip: no caches, no real memory
;      system, and no timing claim in this file is measured on hardware.
;      RaspberryPi4/Examples/Diagnostics/pi4WifiJoin.pi4 runs the same
;      vectors on the board and that is where the silicon evidence will
;      come from.
;    * The 1,000,000 x 'a' vector (RFC 3174 case 3) HAS NOT BEEN RUN
;      HERE. It is 15,625 compressions against a Python oracle at about
;      half a million instructions a second, so it is an hour-scale run.
;      The 129 CAVP vectors exercise the same code far more widely; the
;      one thing the million-byte case adds is a byte count over 16
;      bits, which is the item flagged as reasoning in point 5.
;    * SHA-1's own security properties. See the second section above.
; ======================================================================
EnableExplicit

; ----------------------------------------------------------------------
;  THE TWO NUMBERS THIS PORT TURNS ON, both for the reasons sha256.pi4
;  sets out at length.
;
;  #SHA1_W32 is the 32-bit word mask, and it is a POSITIVE value here:
;  $FFFFFFFF in a 64-bit .i is 4294967295, not -1. That is exactly why
;  masking with it produces the clean non-negative words the invariant
;  above is stated in terms of.
;
;  #SHA1_HWORD is the distance between two elements of a Dim .i array on
;  this target, which is also the width PeekI and PokeI move. The two
;  are the same number because they are the same fact: the size of one
;  .i. On the 32-bit families both would be 4.
; ----------------------------------------------------------------------
#SHA1_W32   = $FFFFFFFF
#SHA1_HWORD = 8

; ----------------------------------------------------------------------
;  #SHA1_DIGEST is 20 because SHA-1 produces a 160-bit message digest -
;  RaspberryPi4/Reference/rfc3174.txt:378, "the message digest is the
;  160-bit string represented by the 5 words H0 H1 H2 H3 H4".
;
;  #SHA1_BLOCK is 64 because the message is padded to a multiple of 512
;  bits and processed in 512-bit blocks - rfc3174.txt:357-361.
;
;  #SHA1_SNAPSHOT is 20 + 64 + 8: the five state words, the partial
;  block, and the two halves of the byte counter. It is twelve bytes
;  shorter than sha256.pi4's 104 for the one reason that SHA-1 carries
;  five state words where SHA-256 carries eight.
; ----------------------------------------------------------------------
#SHA1_DIGEST   = 20
#SHA1_BLOCK    = 64
#SHA1_SNAPSHOT = 92

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style (no structures).
;
;  Every .i below that holds a SHA-1 word holds it clean: 0..$FFFFFFFF,
;  never negative, never with anything above bit 31.
;
;  Sha1W is 80 entries and not 64. RFC 3174 line 399 offers the
;  sixteen-word circular queue as the memory-saving alternative and the
;  eighty-word array as the straightforward one; the eighty-word array
;  is taken, because 640 bytes is nothing on a part with a gigabyte of
;  DRAM and the circular form makes the schedule's indices arithmetic
;  that has to be re-derived by every reader. The queue would save
;  memory this target does not need in exchange for the one thing this
;  file most wants to keep, which is a line-by-line match with the
;  standard's own equations.
; ----------------------------------------------------------------------
Global Dim Sha1H.i[5]               ; the five running hash words H0..H4
Global Dim Sha1Blk.a[64]            ; the current 64-byte input block
Global Sha1CountLo.i                ; total BYTE count, low 32 bits
Global Sha1CountHi.i                ; total BYTE count, high 32 bits

Global Dim Sha1W.i[80]              ; message schedule scratch (not state)

Global Dim Sha1OutBlk.a[64]         ; finalisation works on a COPY, so the
Global Dim Sha1OutH.i[5]            ; live state survives End() untouched

; ----------------------------------------------------------------------
;  Sha1Rotl(x, n) - the 32-bit circular left shift, S^n(X) of
;  RaspberryPi4/Reference/rfc3174.txt:195:
;
;      S^n(X)  =  (X << n) OR (X >> 32-n)
;
;  with the standard's own note (rfc3174.txt:198-202) that the right
;  half is a LOGICAL shift bringing in zeroes.
;
;  BOTH HALVES NEEDED FIXING FOR A 64-BIT REGISTER, and this is the one
;  procedure in the file where the width really bites:
;
;    * the LEFT half. On a 32-bit machine (X << n) throws its top n bits
;      off the end of the word, and that discard IS the rotate. Here
;      they land in bits 32..62 and stay there. The outer & #SHA1_W32 is
;      that discard, put back by hand.
;
;    * the RIGHT half. `>>` is ARITHMETIC on this target, so on a value
;      with bit 63 set it drags in ones. Masking x first makes it
;      non-negative, so the shift brings in zeroes and matches the
;      standard's logical shift. Mask first, then shift.
;
;  Note the asymmetry with sha256.pi4's Sha256Shr, which masks its input
;  and needs no output mask because a right shift cannot push rubbish
;  upward. A left rotate has no such free lunch: it needs both.
;
;  n is 1, 5 or 30 at every call site in this file - never 0, never 32 -
;  so (32 - n) is always a legal shift of 31, 27 or 2. A rotate by 0
;  would need x << 32 and is neither attempted nor needed. n is a
;  compile-time constant at every one of those sites and is never
;  message data, so control here is length-driven only.
; ----------------------------------------------------------------------
Procedure.i Sha1Rotl(x.i, n.i)
  ProcedureReturn ((x << n) | ((x & #SHA1_W32) >> (32 - n))) & #SHA1_W32
EndProcedure

; ----------------------------------------------------------------------
;  The three round functions f(t;B,C,D) of
;  RaspberryPi4/Reference/rfc3174.txt:294-300.
;
;    t  0..19   f = (B AND C) OR ((NOT B) AND D)     - Sha1Ch
;    t 20..39   f = B XOR C XOR D                    - Sha1Par
;    t 40..59   f = (B AND C) OR (B AND D) OR (C AND D) - Sha1Maj
;    t 60..79   f = B XOR C XOR D                    - Sha1Par again
;
;  Sha1Ch AND Sha1Maj ARE WRITTEN IN THEIR ALGEBRAICALLY EQUIVALENT
;  FORMS, character for character the same expressions sha256.pi4 uses
;  for Sha256Ch and Sha256Maj - the two hashes genuinely share these two
;  functions, which is why the SHA-256 spelling can be reused rather
;  than a second spelling of the same truth table invented here.
;
;  THE Ch FORM ALSO AVOIDS A BITWISE NOT, AND THAT IS THE POINT, NOT A
;  BONUS. "(NOT B) AND D" as written would complement all sixty-four
;  bits of B on this target. The AND with a clean D does cut the
;  rubbish back off again, so it would in fact be correct - but it would
;  be correct for a reason that has to be re-derived, and it would put
;  a value with bits above 31 into the middle of a file whose stated
;  invariant is that no such value exists. ((C XOR D) AND B) XOR D
;  never leaves the 32-bit range at all.
;
;  NONE OF THE THREE IS MASKED, on purpose. Bitwise AND, OR and XOR of
;  clean words are clean: no carry propagates and no bit moves. A mask
;  here would suggest to the next reader that one is NEEDED, and which
;  operations genuinely need one is the whole question this file's
;  header is about.
; ----------------------------------------------------------------------
Procedure.i Sha1Ch(b.i, c.i, d.i)
  ProcedureReturn ((c ! d) & b) ! d
EndProcedure

Procedure.i Sha1Par(b.i, c.i, d.i)
  ProcedureReturn (b ! c) ! d
EndProcedure

Procedure.i Sha1Maj(b.i, c.i, d.i)
  ProcedureReturn (c & d) | ((c | d) & b)
EndProcedure

; ----------------------------------------------------------------------
;  Sha1Round(blk, hv) - one 64-byte compression,
;  RaspberryPi4/Reference/rfc3174.txt:356-380 step by step.
;
;  blk is the ADDRESS of 64 message bytes (a .a array, stride 1, read
;  with PeekA). hv is the ADDRESS of five hash words (a .i array, stride
;  #SHA1_HWORD, read with PeekI). Reading the words through the address
;  is what lets Sha1End run this on a scratch copy while the live state
;  is left alone, which in turn is what makes a Snapshot taken after
;  End() still describe the absorbed message.
;
;  THE STRIDE IS 8 AND NOT 4 - see point 1 of the header. Using PeekL
;  and 4 here, as the 32-bit families correctly do, would read the high
;  half of H[0] as if it were H[1].
;
;  THE ROUND CONSTANTS ARE WRITTEN AS LITERALS IN FOUR SEPARATE LOOPS
;  rather than looked up in a table indexed by t / 20. There are only
;  four of them and the standard states them as four ranges
;  (rfc3174.txt:305-311), so four loops is the form that can be checked
;  against the document by eye. It also removes a table read, a divide,
;  and any question of what happens at t = 80. The cost is that the
;  round body appears four times; that is accepted, and the four copies
;  are identical except for the constant and the f function so a diff
;  between any two of them is one line.
;
;  There is not one branch on message content in here: all six loops are
;  counted and the round body is straight-line.
; ----------------------------------------------------------------------
Procedure Sha1Round(blk.i, hv.i)
  Protected i.i
  Protected temp.i
  Protected a.i
  Protected b.i
  Protected c.i
  Protected d.i
  Protected e.i

  ; W[0..15]: sixteen BIG-ENDIAN words out of the block - rfc3174.txt:359,
  ; "W(0) is the left-most word". PeekA is the unsigned spelling, so no
  ; byte arrives negative; four zero-extended bytes cannot exceed 32
  ; bits, so the assembly needs no mask.
  i = 0
  While i < 16
    Sha1W[i] = ((PeekA(blk) & 255) << 24) | ((PeekA(blk + 1) & 255) << 16) | ((PeekA(blk + 2) & 255) << 8) | (PeekA(blk + 3) & 255)
    blk = blk + 4
    i = i + 1
  Wend

  ; W[16..79]: the message schedule - rfc3174.txt:364,
  ;   W(t) = S^1(W(t-3) XOR W(t-8) XOR W(t-14) XOR W(t-16))
  ; The XOR of four clean words is clean, and Sha1Rotl masks what it
  ; returns, so there is nothing left for a mask here to do.
  i = 16
  While i < 80
    Sha1W[i] = Sha1Rotl(((Sha1W[i - 3] ! Sha1W[i - 8]) ! Sha1W[i - 14]) ! Sha1W[i - 16], 1)
    i = i + 1
  Wend

  ; A..E = H0..H4 - rfc3174.txt:366. The masks are belt-and-braces: the
  ; state is already clean by the invariant, and PeekI reads a full .i so
  ; there is no sign question to answer.
  a = PeekI(hv)                    & #SHA1_W32
  b = PeekI(hv + #SHA1_HWORD)      & #SHA1_W32
  c = PeekI(hv + #SHA1_HWORD * 2)  & #SHA1_W32
  d = PeekI(hv + #SHA1_HWORD * 3)  & #SHA1_W32
  e = PeekI(hv + #SHA1_HWORD * 4)  & #SHA1_W32

  ; The eighty rounds - rfc3174.txt:370-372:
  ;   TEMP = S^5(A) + f(t;B,C,D) + E + W(t) + K(t)
  ;   E = D;  D = C;  C = S^30(B);  B = A;  A = TEMP
  ; Five additions modulo 2^32, masked once on the total.

  ; t = 0..19, K = $5A827999 - rfc3174.txt:305
  i = 0
  While i < 20
    temp = ((((Sha1Rotl(a, 5) + Sha1Ch(b, c, d)) + e) + Sha1W[i]) + $5A827999) & #SHA1_W32
    e = d
    d = c
    c = Sha1Rotl(b, 30)
    b = a
    a = temp
    i = i + 1
  Wend

  ; t = 20..39, K = $6ED9EBA1 - rfc3174.txt:307
  While i < 40
    temp = ((((Sha1Rotl(a, 5) + Sha1Par(b, c, d)) + e) + Sha1W[i]) + $6ED9EBA1) & #SHA1_W32
    e = d
    d = c
    c = Sha1Rotl(b, 30)
    b = a
    a = temp
    i = i + 1
  Wend

  ; t = 40..59, K = $8F1BBCDC - rfc3174.txt:309
  While i < 60
    temp = ((((Sha1Rotl(a, 5) + Sha1Maj(b, c, d)) + e) + Sha1W[i]) + $8F1BBCDC) & #SHA1_W32
    e = d
    d = c
    c = Sha1Rotl(b, 30)
    b = a
    a = temp
    i = i + 1
  Wend

  ; t = 60..79, K = $CA62C1D6 - rfc3174.txt:311
  While i < 80
    temp = ((((Sha1Rotl(a, 5) + Sha1Par(b, c, d)) + e) + Sha1W[i]) + $CA62C1D6) & #SHA1_W32
    e = d
    d = c
    c = Sha1Rotl(b, 30)
    b = a
    a = temp
    i = i + 1
  Wend

  ; H[i] = H[i] + working[i], modulo 2^32 - rfc3174.txt:374.
  PokeI(hv,                   (PeekI(hv)                   + a) & #SHA1_W32)
  PokeI(hv + #SHA1_HWORD,     (PeekI(hv + #SHA1_HWORD)     + b) & #SHA1_W32)
  PokeI(hv + #SHA1_HWORD * 2, (PeekI(hv + #SHA1_HWORD * 2) + c) & #SHA1_W32)
  PokeI(hv + #SHA1_HWORD * 3, (PeekI(hv + #SHA1_HWORD * 3) + d) & #SHA1_W32)
  PokeI(hv + #SHA1_HWORD * 4, (PeekI(hv + #SHA1_HWORD * 4) + e) & #SHA1_W32)
EndProcedure

; ----------------------------------------------------------------------
;  Sha1Begin() - start a fresh digest.
;
;  Loads the initial hash value of
;  RaspberryPi4/Reference/rfc3174.txt:346-354. Unlike SHA-256's, these
;  five words are not derived from anything - they are the same nothing-
;  up-my-sleeve counting pattern MD4 and MD5 use, $67452301 ascending
;  and $EFCDAB89 descending, with $C3D2E1F0 appended for the fifth.
;
;  THERE IS NO K TABLE TO LOAD. sha256.pi4 caches sixty-four round
;  constants behind a ready flag; here there are four and they are
;  literals in the round loops, so Begin() is five stores and two zeroes
;  and has no first-call special case at all.
; ----------------------------------------------------------------------
Procedure Sha1Begin()
  Sha1H[0] = $67452301
  Sha1H[1] = $EFCDAB89
  Sha1H[2] = $98BADCFE
  Sha1H[3] = $10325476
  Sha1H[4] = $C3D2E1F0

  Sha1CountLo = 0
  Sha1CountHi = 0
EndProcedure

; ----------------------------------------------------------------------
;  Sha1Update(src, len) - absorb len bytes at address src.
;
;  Arbitrary split points behave exactly like one shot: the only control
;  here is driven by LEN and by how full the block already is, never by
;  the bytes themselves. The gate asserts that rather than assuming it -
;  every short vector is run in 1-, 3-, 7- and 64-byte chunks as well as
;  in one shot.
;
;  THE BYTE COUNTER IS SUMMED AT FULL WIDTH. See point 5 of the header
;  for why the 32-bit families' sign-flip carry trick is silently wrong
;  on this target, and why believing the argument rather than the green
;  test result is the correct response.
;
;  A negative length is a caller error, not a wrap. Ignoring it beats
;  adding it to the counter and corrupting the padded length.
; ----------------------------------------------------------------------
Procedure Sha1Update(src.i, len.i)
  Protected ptr.i
  Protected clen.i
  Protected total.i
  Protected k.i

  If len > 0
    ptr = Sha1CountLo & 63

    total = Sha1CountLo + len
    Sha1CountLo = total & #SHA1_W32
    Sha1CountHi = (Sha1CountHi + ((total >> 32) & #SHA1_W32)) & #SHA1_W32

    While len > 0
      clen = 64 - ptr
      If clen > len
        clen = len
      EndIf
      k = 0
      While k < clen
        Sha1Blk[ptr + k] = PeekA(src + k) & 255
        k = k + 1
      Wend
      ptr = ptr + clen
      src = src + clen
      len = len - clen
      If ptr = 64
        Sha1Round(@Sha1Blk[0], @Sha1H[0])
        ptr = 0
      EndIf
    Wend
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  Sha1End(dst) - finish, writing 20 bytes (five big-endian words).
;
;  Runs on a COPY of the block and of H, so the live context is
;  unchanged and a Snapshot taken afterwards still reflects the absorbed
;  message. That property is what
;  RaspberryPi4/Lib/hmacsha1.pbi is built on and what makes
;  PBKDF2's 8192 MACs affordable, so it is not a convenience.
;
;  THE PADDING RULE IS rfc3174.txt:264-283 AND IT IS LENGTH-DRIVEN: a
;  single $80 byte, then zeroes, then the 64-bit BIT length in the last
;  eight bytes, spilling into a second block when the $80 leaves fewer
;  than eight bytes of room. The "> 56" test below is that spill: after
;  ptr has been incremented past the $80, a ptr above 56 means the
;  length field will not fit.
;
;  THE TWO MASKS ON THE BIT LENGTH ARE THE WEAKEST IN THE FILE and that
;  is said here rather than left for someone to find. CountLo << 3 does
;  put three bits above bit 31 on a 64-bit register where a 32-bit one
;  would have dropped them - but all eight extractions below end in
;  "& 255" on a bit position below 32, so those spilled bits are never
;  read either way. The masks buy nothing a test can see. They are here
;  so that bitHi and bitLo satisfy the file's stated invariant like
;  everything else, and so a reader checking "is every 32-bit value
;  clean" does not have to make an exception for two of them.
;
;  WHAT IS LOAD-BEARING is that Sha1CountLo and Sha1CountHi arrive
;  correct, which is Sha1Update's job.
; ----------------------------------------------------------------------
Procedure Sha1End(dst.i)
  Protected ptr.i
  Protected i.i
  Protected bitLo.i
  Protected bitHi.i

  ptr = Sha1CountLo & 63

  i = 0
  While i < ptr
    Sha1OutBlk[i] = Sha1Blk[i]
    i = i + 1
  Wend
  i = 0
  While i < 5
    Sha1OutH[i] = Sha1H[i]
    i = i + 1
  Wend

  Sha1OutBlk[ptr] = $80
  ptr = ptr + 1
  If ptr > 56
    While ptr < 64
      Sha1OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
    Sha1Round(@Sha1OutBlk[0], @Sha1OutH[0])
    i = 0
    While i < 56
      Sha1OutBlk[i] = 0
      i = i + 1
    Wend
  Else
    While ptr < 56
      Sha1OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
  EndIf

  ; bit length = byte count * 8, as a 64-bit big-endian value.
  bitHi = ((Sha1CountHi << 3) | ((Sha1CountLo >> 29) & 7)) & #SHA1_W32
  bitLo = (Sha1CountLo << 3) & #SHA1_W32
  Sha1OutBlk[56] = (bitHi >> 24) & 255
  Sha1OutBlk[57] = (bitHi >> 16) & 255
  Sha1OutBlk[58] = (bitHi >> 8) & 255
  Sha1OutBlk[59] = bitHi & 255
  Sha1OutBlk[60] = (bitLo >> 24) & 255
  Sha1OutBlk[61] = (bitLo >> 16) & 255
  Sha1OutBlk[62] = (bitLo >> 8) & 255
  Sha1OutBlk[63] = bitLo & 255

  Sha1Round(@Sha1OutBlk[0], @Sha1OutH[0])

  i = 0
  While i < 5
    PokeB(dst + i * 4,     (Sha1OutH[i] >> 24) & 255)
    PokeB(dst + i * 4 + 1, (Sha1OutH[i] >> 16) & 255)
    PokeB(dst + i * 4 + 2, (Sha1OutH[i] >> 8) & 255)
    PokeB(dst + i * 4 + 3, Sha1OutH[i] & 255)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  Sha1Of(src, len, dst) - the one-shot convenience: Begin, Update, End.
; ----------------------------------------------------------------------
Procedure Sha1Of(src.i, len.i, dst.i)
  Sha1Begin()
  Sha1Update(src, len)
  Sha1End(dst)
EndProcedure

; ----------------------------------------------------------------------
;  Sha1Snapshot(dst) / Sha1Restore(src) - 92-byte state round-trip.
;
;  Layout, and it is sha256.pi4's layout with three words removed:
;    +0    H[0..4], five 32-bit words, native (little) endian
;    +20   the 64-byte partial block
;    +84   the byte counter, low 32 bits
;    +88   the byte counter, high 32 bits
;
;  THE IMAGE IS 32-BIT PER WORD EVEN THOUGH .i IS NOT. Widening it would
;  have changed a format for no benefit; PokeN writes the low four bytes
;  of a value the invariant already confines to 32 bits, so nothing is
;  lost.
;
;  THIS PAIR IS NOT A CONVENIENCE HERE - IT IS THE PERFORMANCE STORY.
;  HMAC-SHA1 keys are set once and used thousands of times by PBKDF2;
;  snapshotting the ipad and opad states after their single pad block
;  means each later MAC restores a state instead of re-hashing 64 bytes
;  of pad. That halves the compressions in the inner loop, and at 4096
;  iterations times two output blocks it is the difference between a
;  join that takes a moment and one that does not finish.
;
;  Snapshot captures the whole block buffer; only its first (count & 63)
;  bytes are ever live, so stale trailing bytes are harmless and the
;  image round-trips MID-BLOCK exactly.
;
;  BOTH SIDES USE THE UNSIGNED ACCESSOR - see point 3 of the header.
;  Three of the five initial values have bit 31 set, and so does any
;  running H that has absorbed anything. Restore also masks every word,
;  which is belt to PeekN's braces and stays for the same reason the
;  "& 255" after each PeekA stays.
; ----------------------------------------------------------------------
Procedure Sha1Snapshot(dst.i)
  Protected i.i
  i = 0
  While i < 5
    PokeN(dst + i * 4, Sha1H[i])
    i = i + 1
  Wend
  i = 0
  While i < 64
    PokeB(dst + 20 + i, Sha1Blk[i])
    i = i + 1
  Wend
  PokeN(dst + 84, Sha1CountLo)
  PokeN(dst + 88, Sha1CountHi)
EndProcedure

Procedure Sha1Restore(src.i)
  Protected i.i
  i = 0
  While i < 5
    Sha1H[i] = PeekN(src + i * 4) & #SHA1_W32
    i = i + 1
  Wend
  i = 0
  While i < 64
    Sha1Blk[i] = PeekA(src + 20 + i) & 255
    i = i + 1
  Wend
  Sha1CountLo = PeekN(src + 84) & #SHA1_W32
  Sha1CountHi = PeekN(src + 88) & #SHA1_W32
EndProcedure
