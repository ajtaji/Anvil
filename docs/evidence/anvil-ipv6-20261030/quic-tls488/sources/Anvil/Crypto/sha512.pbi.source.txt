; ======================================================================
;  sha512.pbi - SHA-384 AND SHA-512, ON THE RASPBERRY PI 4 (BCM2711,
;               AArch64) AND EVERY OTHER 64-BIT ANVIL BOARD
; ======================================================================
;
;     XIncludeFile "Anvil/Crypto/sha512.pbi"
;
;  The SHA-512 family of FIPS 180-4: SHA-512 (section 6.4) and SHA-384
;  (section 6.5), which is SHA-512 with a different initial hash value
;  and the output cut to 48 bytes. One compression function serves both.
;
;  Shaped exactly like Anvil/Core/sha256.pbi and Anvil/Crypto/sha1.pbi -
;  the same procedure names with the digits changed, the same
;  address-passing compression function, the same snapshot/restore pair -
;  so a caller swaps hashes by swapping names, and the X.509 engine can
;  run several digests over one byte stream the way it already runs two
;  SHA-256 digests (Snapshot, Update, Restore around the one module-global
;  context).
;
;  API (module-global context - one digest in progress at a time):
;    Sha512Begin()                  start a fresh SHA-512 digest
;    Sha384Begin()                  start a fresh SHA-384 digest
;    Sha512Update(src.i, len.i)     absorb len bytes at address src
;    Sha384Update(src.i, len.i)     the same procedure, by the other name
;    Sha512End(dst.i)               finish; writes 64 bytes at dst
;    Sha384End(dst.i)               finish; writes 48 bytes at dst
;    Sha512Of(src.i, len.i, dst.i)  one-shot SHA-512
;    Sha384Of(src.i, len.i, dst.i)  one-shot SHA-384
;    Sha512Snapshot(dst.i)          save the 208-byte running state
;    Sha512Restore(src.i)           reload a 208-byte running state
;    Sha384Snapshot / Sha384Restore the same pair, by the other name
;
;  WHICH END TO CALL IS THE CALLER'S JOB. SHA-384 and SHA-512 differ in
;  two places only - the initial hash value Begin loads and how many
;  bytes End writes - so the running state does not record which of the
;  two it is. Calling Sha512End on a digest started with Sha384Begin
;  writes 64 bytes of something that is neither; that is a caller error,
;  stated here because nothing at run time can catch it.
;
;  DEPENDENCIES: NONE. This file includes no other library (house rule -
;  the MAIN file lists what it needs). It touches no peripheral and reads
;  no register.
;
;  THIS FILE TURNS EnableExplicit ON FOR YOUR PROGRAM TOO; the pragma is
;  not file-scoped.
;
;  CONSTANT TIME. No branch and no table index depends on message bytes;
;  every control decision is driven by LENGTH.
;
;  ======================================================================
;   .i IS 64 BITS HERE, AND FOR ONCE THAT IS EXACTLY THE WORD SIZE
;  ======================================================================
;
;  SHA-512 is defined on 64-bit words and every addition in FIPS 180-4
;  section 6.4 is "addition modulo 2^64". On this backend .i IS a 64-bit
;  register and `+` wraps modulo 2^64, so NO ADDITION IN THIS FILE IS
;  MASKED - the opposite of sha256.pbi, where every one is, and for the
;  opposite reason. A word whose top bit is set is simply a negative .i;
;  addition, XOR, AND, OR and left shift do not care.
;
;  THE ONE THING THAT DOES CARE IS THE RIGHT SHIFT. `>>` is ARITHMETIC on
;  this target: a word with bit 63 set drags ones in from the top. FIPS
;  180-4's SHR^n and the right half of ROTR^n are LOGICAL. So every right
;  shift here goes through Sha512Shr, which masks the result to its
;  surviving 64 - n bits - ((1 << (64 - n)) - 1) - and n is 1, 6, 7, 8,
;  14, 18, 19, 28, 34, 39, 41 or 61 at every call site, never 0 and
;  never 64, so the mask is always a legal shift. Half the words in any
;  digest have bit 63 set, so an unmasked shift would be wrong on the
;  first block of almost every message; the gate carries that mutation.
;
;  THE OTHER TWO SHAPES THE 32-BIT FILES PAID FOR:
;    * raw bytes are read with PeekA, never PeekB (a byte of $80 read
;      signed is -128, and ORed into a word it sets 56 bits, not 1);
;    * the hash state is walked with PeekI/PokeI at a stride of
;      #SHA512_HWORD = 8, which is the size of one .i - the accessor and
;      the stride are one fact.
;
;  THE CONSTANTS ARE STORED AS 32-BIT HALVES. The eighty round constants
;  and the sixteen initial hash words are 64-bit numbers, more than half
;  of them with bit 63 set. They are written as Data.l high/low pairs and
;  assembled once with PeekN (the zero-extending 32-bit read; PeekL
;  sign-extends since 2026-08-25 and would put ones over the high half).
;  That keeps every literal in this file inside 32 bits, where its
;  meaning does not depend on how the compiler reads a 16-digit hex
;  literal above $7FFFFFFFFFFFFFFF.
;
;  THE BYTE COUNTER is one .i of BYTES plus a high word for the carry.
;  FIPS 180-4 pads with a 128-bit BIT length; this file keeps the byte
;  count in Sha512CountLo, carries an unsigned overflow into
;  Sha512CountHi, and builds the 128-bit bit length from the pair in
;  Sha512End. Reaching the carry needs 2^64 bytes, which nothing will
;  ever hash; the carry is written out so the padding is right by
;  construction rather than by assumption. REASONING, NOT A
;  REPRODUCTION - no bench can hash 16 EiB.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT
;  ======================================================================
;
;  PROVEN 2026-10-14 under the A64 model (tools/a64/a64_interp.py) by
;  tools/a64/a64_sha512_check.py - 908 vectors, ALL PASS, 300,830,331
;  model instructions - against answers this file never produced:
;    * the FIPS 180-4 / NIST example digests ("abc" and the 112-byte
;      two-block message) for both SHA-384 and SHA-512, one shot and in
;      1-byte pieces;
;    * every length 0..300 one shot, both widths, plus 1000 and 4095,
;      against the host's hashlib;
;    * the padding boundaries 0, 1, 55, 63, 64, 111, 112, 113, 127, 128,
;      129, 239, 240, 241, 255, 256, 257 fed in 1-, 3-, 7-, 64-, 127- and
;      128-byte pieces, and snapshotted at three points each with the
;      live context destroyed by a whole digest of the OTHER width before
;      the restore;
;    * the 16 bytes after a SHA-384 digest left untouched (End writes 48
;      bytes, not 64);
;    * the eighty round constants and both initial hash values, read OUT
;      OF THIS FILE by the gate and compared against their definition
;      (the fractional parts of the cube and square roots of the first
;      primes, computed exactly in integer arithmetic);
;    * --mutate: 10 of 10 planted defects turn the gate red (arithmetic
;      shift, stride 4, signed byte, one constant bit, one SHA-384 IV
;      bit, the padding spill test, a rotate amount, the bit-length
;      shift, the snapshot counter offset, SHA-384 writing a 7th word).
;  NOT PROVEN: nothing here has run on silicon from the session that
;  wrote it; the model has no caches and no clock. The 2^64-byte counter
;  carry is reasoning, not a reproduction (see the counter note above).
; ======================================================================
EnableExplicit

#SHA512_HWORD = 8                   ; bytes between two .i array elements
#SHA512_BLOCK = 128                 ; bytes per compression
#SHA512_SNAP  = 208                 ; 8x8 H + 128 block + 8 lo + 8 hi

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style (no structures).
; ----------------------------------------------------------------------
Global Dim Sha512H.i[8]             ; the eight running hash words
Global Dim Sha512Blk.a[128]         ; the current 128-byte input block
Global Sha512CountLo.i              ; total BYTE count (unsigned 64-bit)
Global Sha512CountHi.i              ; carry out of CountLo

Global Dim Sha512K.i[80]            ; round constants, assembled once
Global Dim Sha512IV.i[16]           ; IV: 0..7 SHA-512, 8..15 SHA-384
Global Sha512KReady.i               ; 0 until the tables are assembled
Global Dim Sha512W.i[80]            ; message schedule scratch

Global Dim Sha512OutBlk.a[128]      ; End() works on COPIES, so the live
Global Dim Sha512OutH.i[8]          ; state survives it untouched

; ----------------------------------------------------------------------
;  Sha512Shr(x, n) - the 64-bit LOGICAL right shift, SHR^n.
;
;  `>>` is arithmetic here. The mask is exactly the width of the field
;  that survives the shift, so whatever the sign bit dragged in is cut.
;  (1 << (64 - n)) - 1 for n = 1 is (1 << 63) - 1, which wraps from the
;  most negative value to $7FFFFFFFFFFFFFFF - the intended mask.
; ----------------------------------------------------------------------
Procedure.i Sha512Shr(x.i, n.i)
  ProcedureReturn (x >> n) & ((1 << (64 - n)) - 1)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Rotr(x, n) - the 64-bit rotate right, ROTR^n. The left half
;  needs no mask: a 64-bit register discards what leaves the top, which
;  IS the rotate on a 64-bit word.
; ----------------------------------------------------------------------
Procedure.i Sha512Rotr(x.i, n.i)
  ProcedureReturn Sha512Shr(x, n) | (x << (64 - n))
EndProcedure

; ----------------------------------------------------------------------
;  The four sigma functions, FIPS 180-4 section 4.1.3.
; ----------------------------------------------------------------------
Procedure.i Sha512Bsg0(x.i)
  ProcedureReturn (Sha512Rotr(x, 28) ! Sha512Rotr(x, 34)) ! Sha512Rotr(x, 39)
EndProcedure

Procedure.i Sha512Bsg1(x.i)
  ProcedureReturn (Sha512Rotr(x, 14) ! Sha512Rotr(x, 18)) ! Sha512Rotr(x, 41)
EndProcedure

Procedure.i Sha512Ssg0(x.i)
  ProcedureReturn (Sha512Rotr(x, 1) ! Sha512Rotr(x, 8)) ! Sha512Shr(x, 7)
EndProcedure

Procedure.i Sha512Ssg1(x.i)
  ProcedureReturn (Sha512Rotr(x, 19) ! Sha512Rotr(x, 61)) ! Sha512Shr(x, 6)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Word(addr) / Sha512LoadTables() - assemble the round constants
;  and the two initial hash values from their 32-bit halves, once. PeekN
;  zero-extends, so the low half cannot spill ones into the high half
;  when the two are ORed.
;
;  EACH HALF LANDS IN A .i LOCAL BEFORE IT IS SHIFTED, AND THAT IS
;  LOAD-BEARING. Measured on this backend (2026-10-14): the expression
;  `PeekN(a) << 32` is evaluated at the 32-bit width of .n and answers 0
;  - the high half shifted clean out of a 32-bit register - with no
;  diagnostic. `hi = PeekN(a)` then `hi << 32` with hi a .i answers the
;  64-bit value. (A PeekA operand does NOT do this: `PeekA(p) << 56` is
;  computed at 64 bits, which is what Sha512Round relies on - also
;  measured, and the gate would see it if it changed.) The first build of
;  this file wrote the one-line form and every digest came out wrong.
; ----------------------------------------------------------------------
Procedure.i Sha512Word(addr.i)
  Protected hi.i
  Protected lo.i
  hi = PeekN(addr)
  lo = PeekN(addr + 4)
  ProcedureReturn (hi << 32) | lo
EndProcedure

Procedure Sha512LoadTables()
  Protected i.i
  Protected base.i
  base = ?Sha512KTable
  i = 0
  While i < 80
    Sha512K[i] = Sha512Word(base + i * 8)
    i = i + 1
  Wend
  base = ?Sha512IVTable
  i = 0
  While i < 16
    Sha512IV[i] = Sha512Word(base + i * 8)
    i = i + 1
  Wend
  Sha512KReady = 1
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Round(blk, hv) - one 128-byte compression, FIPS 180-4 6.4.2.
;  blk is the ADDRESS of 128 message bytes, hv the ADDRESS of eight hash
;  words at a stride of #SHA512_HWORD. Through the address, End() runs it
;  on a scratch copy while the live state is left alone.
;
;  No addition is masked: + is modulo 2^64 on this register. See the
;  header.
; ----------------------------------------------------------------------
Procedure Sha512Round(blk.i, hv.i)
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

  ; W[0..15]: sixteen BIG-ENDIAN 64-bit words. PeekA zero-extends each
  ; byte, so the ORs assemble exactly 64 bits; a top byte of $80 or more
  ; makes the word negative, which is the right bit pattern.
  i = 0
  While i < 16
    Sha512W[i] = ((PeekA(blk) & 255) << 56) | ((PeekA(blk + 1) & 255) << 48) | ((PeekA(blk + 2) & 255) << 40) | ((PeekA(blk + 3) & 255) << 32) | ((PeekA(blk + 4) & 255) << 24) | ((PeekA(blk + 5) & 255) << 16) | ((PeekA(blk + 6) & 255) << 8) | (PeekA(blk + 7) & 255)
    blk = blk + 8
    i = i + 1
  Wend

  ; W[16..79]: the message schedule, modulo 2^64.
  i = 16
  While i < 80
    Sha512W[i] = Sha512Ssg1(Sha512W[i - 2]) + Sha512W[i - 7] + Sha512Ssg0(Sha512W[i - 15]) + Sha512W[i - 16]
    i = i + 1
  Wend

  a = PeekI(hv)
  b = PeekI(hv + #SHA512_HWORD)
  c = PeekI(hv + #SHA512_HWORD * 2)
  d = PeekI(hv + #SHA512_HWORD * 3)
  e = PeekI(hv + #SHA512_HWORD * 4)
  f = PeekI(hv + #SHA512_HWORD * 5)
  g = PeekI(hv + #SHA512_HWORD * 6)
  h = PeekI(hv + #SHA512_HWORD * 7)

  ; The eighty rounds. Ch(e,f,g) = ((f ! g) & e) ! g and
  ; Maj(a,b,c) = (b & c) | ((b | c) & a), the same algebraic forms
  ; sha256.pbi uses; bitwise, so no width question arises.
  i = 0
  While i < 80
    t1 = h + Sha512Bsg1(e) + (((f ! g) & e) ! g) + Sha512K[i] + Sha512W[i]
    t2 = Sha512Bsg0(a) + ((b & c) | ((b | c) & a))
    h = g
    g = f
    f = e
    e = d + t1
    d = c
    c = b
    b = a
    a = t1 + t2
    i = i + 1
  Wend

  PokeI(hv,                     PeekI(hv)                     + a)
  PokeI(hv + #SHA512_HWORD,     PeekI(hv + #SHA512_HWORD)     + b)
  PokeI(hv + #SHA512_HWORD * 2, PeekI(hv + #SHA512_HWORD * 2) + c)
  PokeI(hv + #SHA512_HWORD * 3, PeekI(hv + #SHA512_HWORD * 3) + d)
  PokeI(hv + #SHA512_HWORD * 4, PeekI(hv + #SHA512_HWORD * 4) + e)
  PokeI(hv + #SHA512_HWORD * 5, PeekI(hv + #SHA512_HWORD * 5) + f)
  PokeI(hv + #SHA512_HWORD * 6, PeekI(hv + #SHA512_HWORD * 6) + g)
  PokeI(hv + #SHA512_HWORD * 7, PeekI(hv + #SHA512_HWORD * 7) + h)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512BeginIV(first) - load eight words of the IV table from index
;  first (0 = SHA-512, 8 = SHA-384) and zero the counter.
; ----------------------------------------------------------------------
Procedure Sha512BeginIV(first.i)
  Protected i.i
  If Sha512KReady = 0
    Sha512LoadTables()
  EndIf
  i = 0
  While i < 8
    Sha512H[i] = Sha512IV[first + i]
    i = i + 1
  Wend
  Sha512CountLo = 0
  Sha512CountHi = 0
EndProcedure

; FIPS 180-4 section 5.3.5: the first 64 bits of the fractional parts of
; the square roots of the first eight primes.
Procedure Sha512Begin()
  Sha512BeginIV(0)
EndProcedure

; FIPS 180-4 section 5.3.4: the same, for the ninth through sixteenth
; primes.
Procedure Sha384Begin()
  Sha512BeginIV(8)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Update(src, len) - absorb len bytes at address src. Split points
;  behave exactly like one shot. A negative length is a caller error and
;  is ignored rather than added to the counter.
;
;  THE COUNTER CARRY. CountLo is an UNSIGNED 64-bit byte count held in a
;  signed register. The sum wrapped iff it is unsigned-below the old
;  value; flipping bit 63 of both turns that into a signed compare.
; ----------------------------------------------------------------------
Procedure Sha512Update(src.i, len.i)
  Protected ptr.i
  Protected clen.i
  Protected total.i
  Protected k.i
  Protected sgn.i

  If len > 0
    ptr = Sha512CountLo & 127

    sgn = 1 << 63
    total = Sha512CountLo + len
    If (total ! sgn) < (Sha512CountLo ! sgn)
      Sha512CountHi = Sha512CountHi + 1
    EndIf
    Sha512CountLo = total

    While len > 0
      clen = #SHA512_BLOCK - ptr
      If clen > len
        clen = len
      EndIf
      k = 0
      While k < clen
        Sha512Blk[ptr + k] = PeekA(src + k) & 255
        k = k + 1
      Wend
      ptr = ptr + clen
      src = src + clen
      len = len - clen
      If ptr = #SHA512_BLOCK
        Sha512Round(@Sha512Blk[0], @Sha512H[0])
        ptr = 0
      EndIf
    Wend
  EndIf
EndProcedure

Procedure Sha384Update(src.i, len.i)
  Sha512Update(src, len)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Final(dst, outWords) - finish on COPIES of the block and the
;  state, then write outWords big-endian 64-bit words at dst (8 for
;  SHA-512, 6 for SHA-384). The live context is unchanged, so a Snapshot
;  taken after End still reflects the absorbed message.
;
;  Padding (FIPS 180-4 5.1.2): a $80 byte, zeros, and the 128-bit BIT
;  length in the last sixteen bytes, spilling into a second block when
;  the $80 leaves fewer than sixteen.
; ----------------------------------------------------------------------
Procedure Sha512Final(dst.i, outWords.i)
  Protected ptr.i
  Protected i.i
  Protected bitLo.i
  Protected bitHi.i
  Protected w.i

  ptr = Sha512CountLo & 127

  i = 0
  While i < ptr
    Sha512OutBlk[i] = Sha512Blk[i]
    i = i + 1
  Wend
  i = 0
  While i < 8
    Sha512OutH[i] = Sha512H[i]
    i = i + 1
  Wend

  Sha512OutBlk[ptr] = $80
  ptr = ptr + 1
  If ptr > 112
    While ptr < 128
      Sha512OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
    Sha512Round(@Sha512OutBlk[0], @Sha512OutH[0])
    i = 0
    While i < 112
      Sha512OutBlk[i] = 0
      i = i + 1
    Wend
  Else
    While ptr < 112
      Sha512OutBlk[ptr] = 0
      ptr = ptr + 1
    Wend
  EndIf

  ; bit length = byte count * 8, 128 bits: hi = (CountHi << 3) | the top
  ; three bits of CountLo (a LOGICAL shift by 61), lo = CountLo << 3.
  bitHi = (Sha512CountHi << 3) | Sha512Shr(Sha512CountLo, 61)
  bitLo = Sha512CountLo << 3
  ; Seven shifted bytes and one unshifted one, written out: a shift of 0
  ; must never reach Sha512Shr, whose mask would be (1 << 64) - 1 and a
  ; 64-bit shift is taken modulo 64 by the instruction - a mask of 0.
  i = 0
  While i < 7
    Sha512OutBlk[112 + i] = Sha512Shr(bitHi, 56 - i * 8) & 255
    Sha512OutBlk[120 + i] = Sha512Shr(bitLo, 56 - i * 8) & 255
    i = i + 1
  Wend
  Sha512OutBlk[119] = bitHi & 255
  Sha512OutBlk[127] = bitLo & 255

  Sha512Round(@Sha512OutBlk[0], @Sha512OutH[0])

  i = 0
  While i < outWords
    w = Sha512OutH[i]
    PokeB(dst + i * 8,     Sha512Shr(w, 56) & 255)
    PokeB(dst + i * 8 + 1, Sha512Shr(w, 48) & 255)
    PokeB(dst + i * 8 + 2, Sha512Shr(w, 40) & 255)
    PokeB(dst + i * 8 + 3, Sha512Shr(w, 32) & 255)
    PokeB(dst + i * 8 + 4, Sha512Shr(w, 24) & 255)
    PokeB(dst + i * 8 + 5, Sha512Shr(w, 16) & 255)
    PokeB(dst + i * 8 + 6, Sha512Shr(w, 8) & 255)
    PokeB(dst + i * 8 + 7, w & 255)
    i = i + 1
  Wend
EndProcedure

Procedure Sha512End(dst.i)
  Sha512Final(dst, 8)
EndProcedure

Procedure Sha384End(dst.i)
  Sha512Final(dst, 6)
EndProcedure

Procedure Sha512Of(src.i, len.i, dst.i)
  Sha512Begin()
  Sha512Update(src, len)
  Sha512End(dst)
EndProcedure

Procedure Sha384Of(src.i, len.i, dst.i)
  Sha384Begin()
  Sha512Update(src, len)
  Sha384End(dst)
EndProcedure

; ----------------------------------------------------------------------
;  Sha512Snapshot(dst) / Sha512Restore(src) - the 208-byte running state.
;    +0    H[0..7], eight 64-bit words, native (little) endian
;    +64   the 128-byte partial block
;    +192  the byte counter, low 64 bits
;    +200  the byte counter, high 64 bits
;  The whole block is captured; only its first (count & 127) bytes are
;  live, so the image round-trips mid-block exactly. A SHA-384 state and
;  a SHA-512 state have the same image - see the header for which End.
; ----------------------------------------------------------------------
Procedure Sha512Snapshot(dst.i)
  Protected i.i
  i = 0
  While i < 8
    PokeI(dst + i * 8, Sha512H[i])
    i = i + 1
  Wend
  i = 0
  While i < 128
    PokeB(dst + 64 + i, Sha512Blk[i])
    i = i + 1
  Wend
  PokeI(dst + 192, Sha512CountLo)
  PokeI(dst + 200, Sha512CountHi)
EndProcedure

Procedure Sha512Restore(src.i)
  Protected i.i
  i = 0
  While i < 8
    Sha512H[i] = PeekI(src + i * 8)
    i = i + 1
  Wend
  i = 0
  While i < 128
    Sha512Blk[i] = PeekA(src + 64 + i) & 255
    i = i + 1
  Wend
  Sha512CountLo = PeekI(src + 192)
  Sha512CountHi = PeekI(src + 200)
EndProcedure

Procedure Sha384Snapshot(dst.i)
  Sha512Snapshot(dst)
EndProcedure

Procedure Sha384Restore(src.i)
  Sha512Restore(src)
EndProcedure

; ----------------------------------------------------------------------
;  THE TABLES. Each 64-bit constant is a Data.l pair, HIGH half first,
;  read with PeekN(base + i*8) and PeekN(base + i*8 + 4). Reached with
;  ?label, never with Restore/Read, so no caller's Read cursor moves.
;
;  Sha512KTable: FIPS 180-4 section 4.2.3, the first 64 bits of the
;  fractional parts of the cube roots of the first eighty primes.
;  Sha512IVTable: FIPS 180-4 sections 5.3.5 (SHA-512, entries 0..7) and
;  5.3.4 (SHA-384, entries 8..15).
;  tools/a64/a64_sha512_check.py parses both tables out of this file and
;  recomputes every entry from its definition before any digest runs.
; ----------------------------------------------------------------------
DataSection
  Sha512KTable:
  Data.l $428A2F98, $D728AE22, $71374491, $23EF65CD, $B5C0FBCF, $EC4D3B2F, $E9B5DBA5, $8189DBBC
  Data.l $3956C25B, $F348B538, $59F111F1, $B605D019, $923F82A4, $AF194F9B, $AB1C5ED5, $DA6D8118
  Data.l $D807AA98, $A3030242, $12835B01, $45706FBE, $243185BE, $4EE4B28C, $550C7DC3, $D5FFB4E2
  Data.l $72BE5D74, $F27B896F, $80DEB1FE, $3B1696B1, $9BDC06A7, $25C71235, $C19BF174, $CF692694
  Data.l $E49B69C1, $9EF14AD2, $EFBE4786, $384F25E3, $0FC19DC6, $8B8CD5B5, $240CA1CC, $77AC9C65
  Data.l $2DE92C6F, $592B0275, $4A7484AA, $6EA6E483, $5CB0A9DC, $BD41FBD4, $76F988DA, $831153B5
  Data.l $983E5152, $EE66DFAB, $A831C66D, $2DB43210, $B00327C8, $98FB213F, $BF597FC7, $BEEF0EE4
  Data.l $C6E00BF3, $3DA88FC2, $D5A79147, $930AA725, $06CA6351, $E003826F, $14292967, $0A0E6E70
  Data.l $27B70A85, $46D22FFC, $2E1B2138, $5C26C926, $4D2C6DFC, $5AC42AED, $53380D13, $9D95B3DF
  Data.l $650A7354, $8BAF63DE, $766A0ABB, $3C77B2A8, $81C2C92E, $47EDAEE6, $92722C85, $1482353B
  Data.l $A2BFE8A1, $4CF10364, $A81A664B, $BC423001, $C24B8B70, $D0F89791, $C76C51A3, $0654BE30
  Data.l $D192E819, $D6EF5218, $D6990624, $5565A910, $F40E3585, $5771202A, $106AA070, $32BBD1B8
  Data.l $19A4C116, $B8D2D0C8, $1E376C08, $5141AB53, $2748774C, $DF8EEB99, $34B0BCB5, $E19B48A8
  Data.l $391C0CB3, $C5C95A63, $4ED8AA4A, $E3418ACB, $5B9CCA4F, $7763E373, $682E6FF3, $D6B2B8A3
  Data.l $748F82EE, $5DEFB2FC, $78A5636F, $43172F60, $84C87814, $A1F0AB72, $8CC70208, $1A6439EC
  Data.l $90BEFFFA, $23631E28, $A4506CEB, $DE82BDE9, $BEF9A3F7, $B2C67915, $C67178F2, $E372532B
  Data.l $CA273ECE, $EA26619C, $D186B8C7, $21C0C207, $EADA7DD6, $CDE0EB1E, $F57D4F7F, $EE6ED178
  Data.l $06F067AA, $72176FBA, $0A637DC5, $A2C898A6, $113F9804, $BEF90DAE, $1B710B35, $131C471B
  Data.l $28DB77F5, $23047D84, $32CAAB7B, $40C72493, $3C9EBE0A, $15C9BEBC, $431D67C4, $9C100D4C
  Data.l $4CC5D4BE, $CB3E42B6, $597F299C, $FC657E2A, $5FCB6FAB, $3AD6FAEC, $6C44198C, $4A475817
  Sha512IVTable:
  Data.l $6A09E667, $F3BCC908, $BB67AE85, $84CAA73B, $3C6EF372, $FE94F82B, $A54FF53A, $5F1D36F1
  Data.l $510E527F, $ADE682D1, $9B05688C, $2B3E6C1F, $1F83D9AB, $FB41BD6B, $5BE0CD19, $137E2179
  Data.l $CBBB9D5D, $C1059ED8, $629A292A, $367CD507, $9159015A, $3070DD17, $152FECD8, $F70E5939
  Data.l $67332667, $FFC00B31, $8EB44A87, $68581511, $DB0C2E0D, $64F98FA7, $47B5481D, $BEFA4FA4
EndDataSection
