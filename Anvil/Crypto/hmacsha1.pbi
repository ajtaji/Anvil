; ======================================================================
;  hmacsha1.pbi - HMAC-SHA1 (RFC 2104), ON THE RASPBERRY PI 4
; ======================================================================
;
;     XIncludeFile "RaspberryPi4/Lib/sha1.pi4"      ; REQUIRED, FIRST
;     XIncludeFile "Anvil/Crypto/hmacsha1.pbi"
;
;
;  HMAC as RFC 2104 defines it, over SHA-1:
;
;      HMAC(K, text) = H((K0 XOR opad) || H((K0 XOR ipad) || text))
;
;  This is RaspberryPi4/Lib/hmac.pi4's design with SHA-256 swapped for
;  SHA-1. The two files are meant to sit side by side in one program -
;  every global here is prefixed secHmacS1 and every procedure carries
;  Sha1 in its name, so nothing collides.
;
;  API:
;    HmacSha1Key(key.i, keylen.i)        set the key and begin a MAC
;    HmacSha1Begin()                     begin another MAC on that key
;    HmacSha1Update(src.i, len.i)        absorb len message bytes
;    HmacSha1End(dst.i, outlen.i)        finish; returns bytes written
;    HmacSha1Of(key, keylen, msg, msglen, dst)   one-shot, full 20 bytes
;
;  DEPENDENCIES: RaspberryPi4/Lib/sha1.pi4, and it is NOT included from
;  here. House rule 10: a library never includes a library; the MAIN
;  source file lists what it needs, in order. If sha1.pi4 is missing the
;  build fails on an undefined Sha1Begin, which names the gap.
;
;  IT DOES NOT DEFINE CtEqual. RaspberryPi4/Lib/hmac.pi4 already does,
;  and a second definition would collide in any program that wants both
;  MACs - which is exactly the program this file exists for, since the
;  Wi-Fi stack needs HMAC-SHA1 for WPA2 and SHA-256 for everything else.
;  A caller that needs a constant-time compare includes hmac.pi4 as well
;  or writes its own.
;
;  ======================================================================
;   WHY IT IS SHA-1 AND NOT SHA-256
;  ======================================================================
;
;  Because IEEE 802.11 says so, and for no other reason. WPA2-PSK's
;  passphrase mapping is PBKDF2-HMAC-SHA1 and its four-way handshake
;  PRF and EAPOL-Key MIC are HMAC-SHA1. sha1.pi4's header sets out at
;  length why a collision-broken hash is in this tree at all; the short
;  version is that HMAC-SHA1 is not broken for the two properties in
;  use here, and that there is no way to associate with a WPA2 access
;  point without computing it. DO NOT REACH FOR THIS FILE FOR ANYTHING
;  ELSE. RaspberryPi4/Lib/hmac.pi4 is next to it.
;
;  ======================================================================
;   THE ONE THING THAT MAKES THIS FILE FAST ENOUGH TO SHIP
;  ======================================================================
;
;  A naive HMAC hashes the 64-byte ipad block and the 64-byte opad block
;  on every single MAC. PBKDF2 at 4096 iterations, twice over for a
;  256-bit PMK, computes 8192 MACs from ONE key. Re-hashing the pads
;  would be 16,384 extra compressions - more than half the total work -
;  for a value that cannot have changed.
;
;  So HmacSha1Key absorbs each pad block ONCE and snapshots the running
;  SHA-1 state (Sha1Snapshot, 92 bytes). HmacSha1Begin restores the ipad
;  state instead of re-hashing it, and HmacSha1End restores the opad
;  state the same way. Measured in compressions, one PBKDF2 iteration
;  costs 2 instead of 4.
;
;  THIS IS ONLY SOUND BECAUSE Sha1End RUNS ON A COPY. It finalises into
;  scratch buffers and leaves the live context untouched, so restoring
;  the opad state immediately after taking the inner digest is clean.
;  That property of sha1.pi4 is load-bearing here and is stated in its
;  header for this reason; if anyone ever "optimises" Sha1End to
;  finalise in place, this file breaks silently and every MAC after the
;  first is wrong.
;
;  ======================================================================
;   THE SIGN TRAP, AGAIN, AND WHY RFC 2202 IS THE RIGHT GATE
;  ======================================================================
;
;  Every key byte and every message byte here is read with PeekA.
;  PeekB sign-extends (project ruling 2026-08-25) and a key byte of $AA
;  read with PeekB is a negative number whose XOR with $36 sets
;  fifty-odd bits.
;
;  RFC 2202's HMAC-SHA-1 cases are unusually good at finding that:
;  case 3 is a 20-byte key of $AA against 50 bytes of $DD, case 4 is 50
;  bytes of $CD, and cases 6 and 7 are 80-byte keys of $AA - bit 7 set
;  on every byte of all of them. A test set built only from "Hi There"
;  and "Jefe" would go green with a signed read.
;
;  AND YET, MEASURED 2026-08-28: A SIGNED READ IN THIS FILE IS HARMLESS,
;  AND SAYING SO IS MORE USEFUL THAN THE WARNING ABOVE ON ITS OWN. The
;  mutation sweep built this file with PeekB in the pad loop and the
;  "& 255" removed with it, and all 103 vectors still passed. The
;  reason is not luck: secHmacS1Blk is a BYTE array, so the store
;  truncates to eight bits, and the XOR operand is $36 or $5C - both
;  below 256 - so nothing above bit 7 can change what is stored.
;  (PeekA(x) & 255) ! $5C and PeekB(x) ! $5C are the same function of
;  the same input, in the low octet, which is all that survives.
;
;  SO THE PeekA IS A CONVENTION HERE AND NOT A DEFENCE. It stays,
;  because the rule "every raw byte is read with PeekA" is worth having
;  without exceptions and because the next edit to this loop might not
;  store into a byte array. But do not go hunting a wrong MAC here on a
;  sign-extension theory: the two places where the sign genuinely bites
;  are inside RaspberryPi4/Lib/sha1.pi4, and its own gate mutates them.
;
;  ======================================================================
;   WHAT HAS BEEN PROVEN, AND WHAT HAS NOT - 2026-08-28
;  ======================================================================
;
;  PROVEN by known-answer test under the project's A64 oracle
;  tools/a64/a64_interp.py, on a real image built by pmfc.exe for
;  -t pi4. The gate is tools/a64/a64_hmacsha1_check.py:
;
;    * ALL SEVEN RFC 2202 section 3 test cases, PARSED OUT OF
;      RaspberryPi4/Reference/rfc2202.txt rather than transcribed -
;      keys, data and digests. Case 5's 96-bit truncated digest is
;      checked too, so the truncation path in HmacSha1End is a tested
;      path and not an untested convenience.
;    * Every case run one-shot AND streamed a byte at a time, so a
;      partial-block bug in the inner hash would show.
;    * Every case run TWICE from one HmacSha1Key, to prove the cached
;      ipad and opad states survive a completed MAC. That is the
;      property PBKDF2 depends on 8192 times over and the one a naive
;      implementation gets away with never testing.
;    * ALL 300 HMAC-SHA-1 vectors in the [L=20] section of NIST's own
;      CAVP set, RaspberryPi4/Reference/cavp_HMAC.rsp - key lengths of
;      10, 32, 64, 70 and 80 bytes and tag lengths of 10, 12, 16 and
;      20. THEY ARE HERE BECAUSE THE MUTATION SWEEP DEMANDED THEM: RFC
;      2202 has no 64-byte key, so moving the long-key test from
;      `> #HMACSHA1_BLOCK` to `>=` was invisible with RFC 2202 alone.
;      Klen = 64 is that exact boundary and Tlen = 16 is the EAPOL-Key
;      MIC length.
;    * Requests for MORE than the MAC's 20 bytes, and for 0, which the
;      API defines as "all of it". Both must clamp to 20 and report 20.
;      Without those the clamp is unreachable code, and unreachable is
;      not the same as safe.
;
;  343 assertions in that set, all passing.
;
;  MUTATION-TESTED: the gate is run with --mutate, which rebuilds this
;  file with one deliberate defect at a time and requires the gate to go
;  red for each. The list is in the gate's header.
;
;  NOT PROVEN: nothing here has run on silicon yet. The oracle models
;  the instruction set, not the chip.
; ======================================================================
EnableExplicit

; ----------------------------------------------------------------------
;  #HMACSHA1_BLOCK is 64 because that is SHA-1's block size, which is
;  the B of RFC 2104 section 2. #HMACSHA1_MAC is 20, SHA-1's digest.
;
;  #HMACSHA1_SNAP is 92 and it MUST equal #SHA1_SNAPSHOT in
;  RaspberryPi4/Lib/sha1.pi4. It is written out again rather than
;  referenced so that this file states the size of the buffers it
;  declares; if sha1.pi4's image ever changes width, the arrays below
;  are too small and the failure is a silent overwrite of whatever
;  follows them in memory. There is no compile-time way to assert the
;  two agree in this language, so it is said here instead: KEEP THESE
;  TWO NUMBERS EQUAL.
; ----------------------------------------------------------------------
#HMACSHA1_BLOCK = 64
#HMACSHA1_MAC   = 20
#HMACSHA1_SNAP  = 92

; ----------------------------------------------------------------------
;  STATE - flat Global arrays, house style.
;
;  EVERY ONE OF THESE HOLDS KEY-DERIVED MATERIAL and the sec prefix says
;  so, matching hmac.pi4's convention. secHmacS1Ipad and secHmacS1Opad
;  in particular are SHA-1 states that have already absorbed the key;
;  recovering the key from one is not easy, but they are not public
;  values either and nothing should print them.
; ----------------------------------------------------------------------
Global Dim secHmacS1KeyBuf.a[20]     ; a long key, hashed down to 20 bytes
Global Dim secHmacS1Blk.a[64]        ; the pad block under construction
Global Dim secHmacS1Ipad.a[92]       ; SHA-1 state after ipad, snapshotted
Global Dim secHmacS1Opad.a[92]       ; SHA-1 state after opad, snapshotted
Global Dim secHmacS1Inner.a[20]      ; inner hash SHA1(ipad || message)
Global Dim secHmacS1Mac.a[20]        ; the finished MAC

; ----------------------------------------------------------------------
;  HmacSha1Key(key, keylen) - set the key and begin the first MAC.
;
;  RFC 2104 section 2, and the two rules that matter:
;
;    * A KEY LONGER THAN ONE BLOCK IS HASHED FIRST. K0 becomes
;      SHA1(key), twenty bytes. RFC 2202 cases 6 and 7 use an 80-byte
;      key precisely to exercise this, and their names say so out loud
;      ("Test Using Larger Than Block-Size Key - Hash Key First").
;    * A SHORTER KEY IS ZERO-PADDED TO THE BLOCK. That is what the two
;      "While i < 64" loops below do by writing the bare pad byte:
;      $36 is 0 XOR $36, and $5C is 0 XOR $5C. Writing it that way
;      rather than zeroing and then XORing saves a pass and is the same
;      value; the comment is here because the zeros are invisible
;      otherwise.
;
;  A key of EXACTLY 64 bytes is used as-is, not hashed - the rule is
;  "longer than the block size", so the test is > 64 and not >= 64. An
;  off-by-one there is a MAC that disagrees with every other
;  implementation on exactly one key length, which is the kind of bug
;  that ships.
;
;  ONLY THE KEY LENGTH DRIVES THE LOOPS. The key BYTES are XORed
;  straight-line and are never branched on, never used as an index, and
;  never compared. Timing here depends on keylen alone, which the
;  attacker already knows.
;
;  THE KEY IS READ WITH PeekA - see the header. It matters most in the
;  long-key branch, where the 80 bytes of $AA in RFC 2202 cases 6 and 7
;  go through Sha1Of, and again in the XOR loops, where a sign-extended
;  byte would corrupt the pad word it lands in.
; ----------------------------------------------------------------------
Procedure HmacSha1Key(key.i, keylen.i)
  Protected i.i
  Protected kb.i
  Protected klen.i

  If keylen > #HMACSHA1_BLOCK
    Sha1Of(key, keylen, @secHmacS1KeyBuf[0])
    kb = @secHmacS1KeyBuf[0]
    klen = #HMACSHA1_MAC
  Else
    kb = key
    klen = keylen
  EndIf

  ; A negative length is a caller error. Treat it as an empty key
  ; rather than running the loop below backwards off the front of the
  ; buffer; RFC 2104 permits a key of any length including zero.
  If klen < 0
    klen = 0
  EndIf

  ; ipad block: key XOR $36, then $36 padding.
  i = 0
  While i < klen
    secHmacS1Blk[i] = (PeekA(kb + i) & 255) ! $36
    i = i + 1
  Wend
  While i < #HMACSHA1_BLOCK
    secHmacS1Blk[i] = $36
    i = i + 1
  Wend
  Sha1Begin()
  Sha1Update(@secHmacS1Blk[0], #HMACSHA1_BLOCK)
  Sha1Snapshot(@secHmacS1Ipad[0])

  ; opad block: key XOR $5C, then $5C padding.
  i = 0
  While i < klen
    secHmacS1Blk[i] = (PeekA(kb + i) & 255) ! $5C
    i = i + 1
  Wend
  While i < #HMACSHA1_BLOCK
    secHmacS1Blk[i] = $5C
    i = i + 1
  Wend
  Sha1Begin()
  Sha1Update(@secHmacS1Blk[0], #HMACSHA1_BLOCK)
  Sha1Snapshot(@secHmacS1Opad[0])

  HmacSha1Begin()
EndProcedure

; ----------------------------------------------------------------------
;  HmacSha1Begin() - start another MAC on the key cached by the last
;  HmacSha1Key.
;
;  Restores the ipad SHA-1 state - one 64-byte block already absorbed,
;  byte count 64 - so the HmacSha1Update calls that follow continue the
;  inner hash SHA1(ipad || message). No pad block is re-hashed.
;
;  CALLING THIS BEFORE ANY HmacSha1Key RESTORES A ZEROED BUFFER, which
;  is a SHA-1 state with H = 0 and a byte count of 0. That is not a
;  valid state and it is not an error either - it is a MAC under a key
;  nobody chose. It is the caller's job to set a key first, and every
;  entry point that needs one says so.
; ----------------------------------------------------------------------
Procedure HmacSha1Begin()
  Sha1Restore(@secHmacS1Ipad[0])
EndProcedure

; ----------------------------------------------------------------------
;  HmacSha1Update(src, len) - absorb len message bytes into the inner
;  hash. Arbitrary split points behave exactly like one shot; that is
;  SHA-1's property, and the gate asserts it rather than assuming it by
;  running every RFC 2202 case a byte at a time as well as in one shot.
; ----------------------------------------------------------------------
Procedure HmacSha1Update(src.i, len.i)
  Sha1Update(src, len)
EndProcedure

; ----------------------------------------------------------------------
;  HmacSha1End(dst, outlen) - finish the MAC.
;
;  inner = SHA1(ipad || message); then, from the cached opad state,
;  MAC = SHA1(opad || inner). Writes min(outlen, 20) bytes; outlen <= 0
;  means the full 20. Returns the number of bytes written.
;
;  THE TRUNCATION IS RFC 2104 SECTION 5, and it is not a convenience:
;  RFC 2202 case 5 publishes a 96-bit answer for exactly this, and
;  WPA2's EAPOL-Key MIC is HMAC-SHA1 truncated to 128 bits. Truncation
;  always takes the LEADING bytes.
;
;  THE FULL MAC IS ALWAYS COMPUTED, then copied out short. Computing
;  fewer bytes is not possible for a hash and pretending otherwise
;  would be the kind of "optimisation" that returns the right prefix of
;  the wrong value.
;
;  THE LIVE CONTEXT IS LEFT HOLDING THE OPAD STATE, not the ipad state.
;  A caller that wants another MAC on the same key calls HmacSha1Begin,
;  which restores ipad. Leaving it on opad rather than helpfully
;  re-beginning is deliberate: an implicit re-begin would make
;  "End then Update" silently mean something, and it should not.
; ----------------------------------------------------------------------
Procedure.i HmacSha1End(dst.i, outlen.i)
  Protected i.i
  Protected n.i

  Sha1End(@secHmacS1Inner[0])
  Sha1Restore(@secHmacS1Opad[0])
  Sha1Update(@secHmacS1Inner[0], #HMACSHA1_MAC)
  Sha1End(@secHmacS1Mac[0])

  n = outlen
  If n <= 0
    n = #HMACSHA1_MAC
  EndIf
  If n > #HMACSHA1_MAC
    n = #HMACSHA1_MAC
  EndIf
  i = 0
  While i < n
    PokeB(dst + i, secHmacS1Mac[i] & 255)
    i = i + 1
  Wend
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  HmacSha1Of(key, keylen, msg, msglen, dst) - one-shot full 20-byte MAC.
;
;  Convenient, and WRONG FOR A LOOP: it re-derives the pad states on
;  every call. PBKDF2 does not use it - see RaspberryPi4/Lib/pbkdf2.pi4,
;  which calls HmacSha1Key once and HmacSha1Begin 8192 times.
; ----------------------------------------------------------------------
Procedure HmacSha1Of(key.i, keylen.i, msg.i, msglen.i, dst.i)
  HmacSha1Key(key, keylen)
  HmacSha1Update(msg, msglen)
  HmacSha1End(dst, #HMACSHA1_MAC)
EndProcedure
