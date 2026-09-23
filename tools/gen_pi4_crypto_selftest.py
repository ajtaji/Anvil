#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_pi4_crypto_selftest.py - emit Anvil/Core/cryptotest_vectors.pbi,
# the known-answer table the ON-BOARD `crypto` self-test walks.
#
# ======================================================================
#  NOT ONE VECTOR IS TYPED IN THIS FILE
# ======================================================================
#
# Every byte below comes out of a table or a parser that ALREADY GATES
# this tree on the desktop:
#
#   sha256    tools/gen_sha256_vectors.py
#   sha1      tools/a64/a64_sha1_check.parse_rfc3174   (RFC 3174 section 7.3,
#             tools/a64/a64_sha1_check.parse_cavp       parsed off the disk)
#   hmac      tools/gen_hmac_vectors.RFC4231      (RFC 4231 cases 1-7)
#   hmacsha1  tools/a64/a64_hmacsha1_check.parse_rfc2202  (RFC 2202, parsed)
#   hkdf      tools/gen_hkdf_vectors.build_5869   (RFC 5869 appendix A)
#   pbkdf2    tools/a64/a64_pbkdf2_check.parse_rfc6070   (RFC 6070, parsed)
#   drbg      tools/gen_drbg_vectors.build_cases  (the NIST CAVP anchor)
#   aes       tools/a64/a64_aes_check.parse_fips_appendix_c (FIPS-197, parsed)
#             tools/a64/a64_aes_check.cavp_sample (NIST CAVP KAT_AES)
#   aesctr    derived here from AES-ECB by the `cryptography` package
#   gcm       tools/gen_gcm_vectors.KAT           (NIST/McGrew, the same
#                                                  table a64_gcm_check imports)
#   keywrap   tools/a64/a64_keywrap_check.parse_rfc3394  (RFC 3394 s.4, parsed)
#
# WHY THAT MATTERS ENOUGH TO BE THE FIRST THING IN THE FILE.
# RaspberryPi4/Examples/Diagnostics/pi4AesSelfTest.pi4 - the board
# diagnostic this one supersedes - says out loud that its vectors are
# TRANSCRIBED, "exactly the failure mode the desktop gates avoid by
# construction", and a64_keywrap_check.py grew a whole extra pass
# (check_diagnostic_vectors) whose only job is to catch a mistyped digit
# in it.  A mistyped digit on a board fails on silicon, looks like a
# silicon problem, and is not one.  Nothing here can be mistyped, so
# that hazard is gone rather than policed.
#
# ======================================================================
#  THE FORMAT ON THE BOARD
# ======================================================================
#
#   #CRY_VEC_COUNT        how many records
#   #CRY_META_STRIDE      bytes per meta record (40)
#   #CRY_MAX_A .. _F      the largest field of each slot, over the WHOLE
#                         table - the board sizes its buffers from these,
#                         so a vector that outgrows a buffer is not
#                         possible rather than merely unlikely
#   #CRY_MOD_*            the module ids
#
#   CryVecMeta:  ten Data.l per record -
#       0 module  1 vecid  2 la  3 lb  4 lc  5 ld  6 le  7 lf
#       8 param   9 data offset (bytes from CryVecData)
#
#   CryVecData:  per record, a || b || c || d || e || f, no padding.
#
# Slot `e` is ALWAYS the expected output.  What the other slots mean is
# per module and is written in the table in the board file's header, in
# this file's MODULES table, and again as a comment above every record
# below, so the three cannot drift apart silently.
#
# THE DATA IS REACHED WITH ?label AND PeekA, NEVER Read/Restore.  "Read
# strides 2 bytes whatever the element width" is an open compiler bug on
# every target, and Read/Restore share ONE
# program-wide cursor - Anvil/Core/sha256.pbi's header says why that is
# a trap for a caller.  The board file copies each field into an aligned
# buffer before use, because with the MMU off an unaligned wide access
# is a silent runaway on this part.
#
# Usage:  python tools/gen_pi4_crypto_selftest.py [out_file]
#         (default Anvil/Core/cryptotest_vectors.pbi)
# ----------------------------------------------------------------------
from __future__ import annotations

import hashlib
import hmac as _hmac
import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
A64 = TOOLS / "a64"
REF = ROOT / "RaspberryPi4" / "Reference"

MOD_SHA256, MOD_SHA1 = 1, 2
MOD_HMAC, MOD_HMACSHA1 = 3, 4
MOD_HKDF, MOD_PBKDF2, MOD_DRBG = 5, 6, 7
MOD_AES, MOD_AESCTR, MOD_GCM, MOD_KEYWRAP = 8, 9, 10, 11
# ---- PART TWO, the public-key half.  Same table, same record format,
# same rule: not one byte is typed here either.  Each of the seven
# imports the SAME oracle the desktop gate for that module imports, so a
# board line and a desk line are about one vector, never about two that
# happen to look alike.
MOD_BIGNUM, MOD_P256, MOD_X25519 = 12, 13, 14
MOD_ECDSA, MOD_RSA, MOD_T0VM, MOD_X509 = 15, 16, 17, 18

MODULES = [
    (MOD_SHA256,   "sha256",   "a=message                              e=digest(32)"),
    (MOD_SHA1,     "sha1",     "a=message unit  param=repeat count     e=digest(20)"),
    (MOD_HMAC,     "hmac",     "a=key b=message                        e=mac (len = le)"),
    (MOD_HMACSHA1, "hmacsha1", "a=key b=message                        e=mac (len = le)"),
    (MOD_HKDF,     "hkdf",     "a=salt b=ikm c=info d=prk(32)          e=okm"),
    (MOD_PBKDF2,   "pbkdf2",   "a=password b=salt  param=iterations    e=derived key"),
    (MOD_DRBG,     "drbg",     "a=seed b=reseed (may be empty)         e=generated bytes"),
    (MOD_AES,      "aes",      "a=key b=plaintext(16)                  e=ciphertext(16)"),
    (MOD_AESCTR,   "aes-ctr",  "a=key b=iv(16) c=plaintext             e=ciphertext"),
    (MOD_GCM,      "gcm",      "a=key b=iv c=aad d=plaintext  param=forge byte  e=ct f=tag(16)"),
    (MOD_KEYWRAP,  "keywrap",  "a=kek b=key data                       e=wrapped"),
    (MOD_BIGNUM,   "bignum",   "a=modulus b=x c=y|exponent  param=op   e=expected"),
    (MOD_P256,     "p256",     "a=point(65) b=scalar  param=op         e=point|sharedX"),
    (MOD_X25519,   "x25519",   "a=scalar(32) b=u(32)  param=derived    e=out(32)"),
    (MOD_ECDSA,    "ecdsa",    "a=q(65) b=hash(32) c=sig  param=kind|verdict|err|curve  e=(none)"),
    (MOD_RSA,      "rsa",      "a=n b=e c=sig d=message  param=kind|verdict|saltlen  e=recovered hash or (none)"),
    (MOD_T0VM,     "t0vm",     "a=step table  param=op                 e=16 bytes per step: result, t0_err"),
    (MOD_X509,     "x509",     "a=chain DER b=lengths(u16) c=header d=anchors f=server name  e=the expected code(1)"),
]


# ======================================================================
#  Importing the existing generators and gates
# ======================================================================
#  They are imported by path rather than by package, because tools/ is
#  not a package and tools/a64 is not either.  Importing a GATE runs its
#  module-level code, which prints one "[gate] tree under test" line to
#  stderr and touches nothing - every gate guards its real work behind
#  __name__ == "__main__".  That line is left visible on purpose: if a
#  gate is ever imported here that DOES do work at import time, it will
#  be obvious rather than mysterious.
def _load(path: pathlib.Path, name: str):
    if not path.exists():
        raise SystemExit(
            "the vector source is missing: %s\n"
            "This generator deliberately owns no vectors of its own. Do not\n"
            "replace the missing file with typed values - find out why it is\n"
            "gone." % path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(A64))
sys.path.insert(0, str(TOOLS))


# ======================================================================
#  THE RECORD BUILDERS, ONE PER MODULE
# ======================================================================
class Table:
    def __init__(self):
        self.recs = []          # (module, vecid, [a,b,c,d,e,f], param, note)
        self._n = {}

    def add(self, module, fields, param, note):
        assert len(fields) == 6
        vid = self._n.get(module, 0)
        self._n[module] = vid + 1
        self.recs.append((module, vid, [bytes(f) for f in fields], param, note))

    def count(self, module):
        return self._n.get(module, 0)


def build_sha256(t: Table, count: int):
    """The block-boundary lengths out of gen_sha256_vectors' own forced
    list, in its own order, with hashlib digests computed the same way
    the generator computes them.

    WHY THE FORCED PREFIX AND NOT A RANDOM SAMPLE.  That generator
    starts every emission with 21 hand-chosen lengths - 0, 1, 2, 3, 55,
    56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 191, 192, 193, 255,
    256, 257 - which are the padding cases: the empty message, the one
    where the length spills into a second block, and the neighbours of
    every 64-byte boundary.  The 179 random lengths after them exercise
    nothing those do not, and each one costs its own bytes in a boot
    image.  The desktop gate runs all 200; this runs the 21 that can
    actually distinguish a padding bug.
    """
    gen = _load(TOOLS / "gen_sha256_vectors.py", "gen_sha256_vectors")
    text = gen.emit(count=count, maxlen=300)
    # The generator emits its lengths and its bytes; re-deriving the
    # messages here from the same seed would be a second copy of its
    # logic.  Parse its own output instead, so the two cannot disagree.
    lens, data = _parse_len_data(text, "Sha256VecLens", "Sha256VecData")
    p = 0
    for n in lens:
        msg, dig = data[p:p + n], data[p + n:p + n + 32]
        p += n + 32
        assert hashlib.sha256(msg).digest() == dig, \
            "gen_sha256_vectors emitted a digest hashlib disagrees with"
        t.add(MOD_SHA256, (msg, b"", b"", b"", dig, b""), 0,
              "gen_sha256_vectors, message of %d bytes" % n)


def _parse_len_data(text: str, lens_label: str, data_label: str):
    """Read a two-section DataSection emission back into python.

    The generators are the source of truth for the vectors AND for the
    order they come in, so this reads what they actually wrote rather
    than re-running their random walk with the same seed and hoping.
    """
    lens, data, where = [], bytearray(), None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(lens_label + ":"):
            where = "l"
            continue
        if s.startswith(data_label + ":"):
            where = "d"
            continue
        if s.startswith("EndDataSection"):
            where = None
            continue
        if where is None or not s.startswith("Data."):
            continue
        body = s.split(None, 1)[1]
        body = body.split(";")[0]
        vals = [int(v) for v in body.split(",") if v.strip()]
        if where == "l":
            lens += vals
        else:
            data += bytes(vals)
    if not lens or not data:
        raise SystemExit("%s / %s: the emission no longer has the shape this "
                         "reader expects. Fix the reader, do not type the "
                         "vectors." % (lens_label, data_label))
    return lens, bytes(data)


def build_sha1(t: Table, cavp_count: int):
    """RFC 3174 section 7.3's own driver table, plus a spread of NIST
    CAVP short messages.

    TEST3 - one million 'a' - IS LEFT OUT AND THAT IS A DECISION.  It is
    not a padding case the other vectors miss; it is a LENGTH case, and
    the on-board throughput run below hashes 64 KB per pass on real
    silicon, which walks the same streaming path far more times than a
    single one-megabyte vector would.  What it would cost is the whole
    emulator gate: a million one-byte Sha1Update calls is a few hundred
    million model instructions before anything else runs.  The desktop
    gate keeps it, behind `a64_sha1_check.py --million`.
    """
    sha1 = _load(A64 / "a64_sha1_check.py", "a64_sha1_check")
    for name, unit, rep, md in sha1.parse_rfc3174():
        total = len(unit) * rep
        if total > 4096:
            continue
        assert hashlib.sha1(unit * rep).digest() == md
        t.add(MOD_SHA1, (unit, b"", b"", b"", md, b""), rep,
              "RFC 3174 %s" % name)
    short = sha1.parse_cavp(REF / "cavp_SHA1ShortMsg.rsp")
    step = max(1, len(short) // cavp_count)
    for bitlen, msg, md in short[::step][:cavp_count]:
        assert hashlib.sha1(msg).digest() == md
        t.add(MOD_SHA1, (msg, b"", b"", b"", md, b""), 1,
              "CAVP SHA1ShortMsg Len %d" % bitlen)


def build_hmac(t: Table):
    """RFC 4231 cases 1-7, out of gen_hmac_vectors' own table.  Case 5
    is the 128-bit truncation case and its outlen is 16, which is the
    one place the board has to honour a short output."""
    gen = _load(TOOLS / "gen_hmac_vectors.py", "gen_hmac_vectors")
    for i, (key, msg, outlen, pub) in enumerate(gen.RFC4231):
        want = bytes.fromhex(pub)
        assert _hmac.new(key, msg, hashlib.sha256).digest()[:outlen] == want
        t.add(MOD_HMAC, (key, msg, b"", b"", want, b""), 0,
              "RFC 4231 case %d (outlen %d)" % (i + 1, outlen))


def build_hmacsha1(t: Table):
    """RFC 2202 section 3, parsed off the disk by the SHA-1 HMAC gate."""
    g = _load(A64 / "a64_hmacsha1_check.py", "a64_hmacsha1_check")
    for c in g.parse_rfc2202():
        key, data, dig = c["key"], c["data"], c["digest"]
        assert _hmac.new(key, data, hashlib.sha1).digest() == dig
        t.add(MOD_HMACSHA1, (key, data, b"", b"", dig, b""), 0,
              "RFC 2202 case %d" % c["case"])


def build_hkdf(t: Table, extra: int):
    """RFC 5869 appendix A's three SHA-256 anchors, then a few of the
    generator's random cases so a length that is not a multiple of 32 is
    covered."""
    gen = _load(TOOLS / "gen_hkdf_vectors.py", "gen_hkdf_vectors")
    cases = gen.build_5869(extra)
    for i, (salt, ikm, info, L, prk, okm) in enumerate(cases):
        tag = "RFC 5869 A.%d" % (i + 1) if i < 3 else \
              "gen_hkdf_vectors random %d" % (i - 2)
        t.add(MOD_HKDF, (salt, ikm, info, prk, okm, b""), 0,
              "%s (L = %d)" % (tag, L))


def build_pbkdf2(t: Table, iter_cap: int):
    """RFC 6070, parsed off the disk, with the c = 16777216 vector left
    out by an ITERATION CAP rather than by an index - so if the RFC ever
    gains a cheap vector it comes in, and if it gains an expensive one
    it stays out, with no edit here.

    That vector is 33 million SHA-1 compressions.  On the board it is
    seconds; in the model that gates this before it is flashed it is
    hours, and a gate nobody waits for is a gate nobody runs.
    """
    g = _load(A64 / "a64_pbkdf2_check.py", "a64_pbkdf2_check")
    for i, v in enumerate(g.parse_rfc6070()):
        if v["c"] > iter_cap:
            continue
        assert hashlib.pbkdf2_hmac("sha1", v["P"], v["S"], v["c"],
                                   v["dkLen"]) == v["DK"]
        t.add(MOD_PBKDF2, (v["P"], v["S"], b"", b"", v["DK"], b""), v["c"],
              "RFC 6070 vector %d (c = %d, dkLen = %d)"
              % (i + 1, v["c"], v["dkLen"]))


def build_drbg(t: Table, extra: int):
    """The NIST CAVP HMAC_DRBG anchor and the generator's variants.  The
    board's call order is the CAVP KAT's: init, reseed if there is one,
    generate and DISCARD, generate and keep."""
    gen = _load(TOOLS / "gen_drbg_vectors.py", "gen_drbg_vectors")
    for i, (seed, reseed, genlen, out) in enumerate(gen.build_cases(extra)):
        assert len(out) == genlen
        tag = ("NIST CAVP HMAC_DRBG SHA-256 anchor" if i == 0 else
               "the same seed with no reseed" if i == 1 else
               "gen_drbg_vectors random %d" % (i - 1))
        t.add(MOD_DRBG, (seed, reseed, b"", b"", out, b""), 0,
              "%s (%d bytes out)" % (tag, genlen))


def build_aes(t: Table, cavp: bool):
    """FIPS-197 appendix C's three worked examples, parsed out of the
    2001 document, then NIST CAVP KAT_AES blocks from the ends and the
    middle of every file at every key size."""
    g = _load(A64 / "a64_aes_check.py", "a64_aes_check")
    for v in g.parse_fips_appendix_c():
        t.add(MOD_AES, (v["key"], v["pt"], b"", b"", v["ct"], b""), 0,
              "FIPS-197 %s" % v["name"])
    if cavp:
        for name, bits, key, pt, ct in g.cavp_sample():
            t.add(MOD_AES, (key, pt, b"", b"", ct, b""), 0, name)


def build_aesctr(t: Table, long_len: int):
    """CTR is the mode that was ADDED to aes.pi4 for GCM, so it has no
    published table of its own in this tree.  It is derived here from
    the block cipher by a second implementation, which is what the GCM
    generator does for its own extra cases.

    THE LONG VECTOR IS THE POINT OF THIS MODULE.  259 blocks carries the
    big-endian counter word past 255 and makes byte 1 non-zero.  The GCM
    mutation sweep proved that matters: a byte dropped from AesSwap32 is
    INVISIBLE to every published GCM vector, because the longest of them
    is 64 bytes and the counter never leaves 0..5.  One vector on this
    board covers the same ground for a fifth of the bytes, because CTR
    reaches AesCtrCore directly instead of through the AEAD.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    specs = [(16, 16, "one block, AES-128"),
             (16, 31, "a partial trailing block"),
             (24, 64, "four blocks, AES-192"),
             (32, 64, "four blocks, AES-256"),
             (16, long_len, "%d bytes - %d blocks, which carries the counter "
                            "past 255" % (long_len, (long_len + 15) // 16))]
    for idx, (klen, plen, why) in enumerate(specs):
        key = bytes((idx * 37 + i * 7 + 3) & 0xFF for i in range(klen))
        iv = bytes((idx * 41 + i * 11 + 5) & 0xFF for i in range(12)) + \
            b"\x00\x00\x00\x01"
        pt = bytes((idx * 43 + i * 31 + 17) & 0xFF for i in range(plen))
        enc = Cipher(algorithms.AES(key), modes.CTR(iv),
                     backend=default_backend()).encryptor()
        ct = enc.update(pt) + enc.finalize()
        t.add(MOD_AESCTR, (key, iv, pt, b"", ct, b""), 0,
              "SP 800-38A CTR, %s" % why)


def build_gcm(t: Table):
    """The NIST/McGrew KAT table imported out of tools/gen_gcm_vectors.py
    - the same object a64_gcm_check.py imports - plus that generator's
    own AAD-only, single-byte and long-IV cases, each re-derived by a
    second implementation inside build_vectors().

    THE FORGE BYTE ALTERNATES BETWEEN 0 AND 15.  The GCM mutation sweep
    found that a tag compare which stops early was invisible while every
    forgery flipped byte 0: the early exit cost one iteration in every
    run, so nothing differed.  Alternating the position is what makes
    the board's forgery refusals evidence about the whole compare.
    """
    gen = _load(TOOLS / "gen_gcm_vectors.py", "gen_gcm_vectors")
    for i, (key, iv, aad, pt, ct, tag) in enumerate(gen.build_vectors()):
        t.add(MOD_GCM, (key, iv, aad, pt, ct, tag), 0 if i % 2 == 0 else 15,
              "NIST/McGrew KAT %d" % i if i < len(gen.KAT) else
              "gen_gcm_vectors generated case %d" % (i - len(gen.KAT)))


def build_keywrap(t: Table):
    """RFC 3394 section 4, parsed out of the document by the key wrap
    gate - which also validates its own parse against the intermediates
    the RFC prints, so a mis-parse cannot reach this table."""
    g = _load(A64 / "a64_keywrap_check.py", "a64_keywrap_check")
    for v in g.parse_rfc3394():
        t.add(MOD_KEYWRAP, (v["kek"], v["kd"], b"", b"", v["ct"], b""), 0,
              v["name"])


# ======================================================================
#  PART TWO - THE PUBLIC-KEY HALF
# ======================================================================
#  Seven more builders, written to the same rule as the eleven above:
#  every byte comes out of the oracle that already gates the module on
#  the desktop, and the desktop gate for each one is named beside it.
#
#  THE ONE THING THAT IS DIFFERENT, AND IT IS WORTH SAYING ONCE.  The
#  eleven modules above answer with BYTES, so slot e is the answer and a
#  wrong answer is a byte index.  Four of the seven below answer with a
#  VERDICT - 1, 0, -1, or an #X509ERR_* code - and a verdict has no
#  bytes.  Those records carry the expected verdict in `param` and leave
#  slot e empty (or, where the module also hands back bytes - RSA's
#  certificate seam recovers the signed hash - slot e holds those bytes
#  and BOTH are checked).  The board file's runners say which is which,
#  and the failure sentences name the verdict convention, because three
#  of them now live in one family on this part.
# ======================================================================
BN_OP_MONTMUL, BN_OP_MODPOW, BN_OP_REDUCE = 1, 2, 3
BN_OP_DECRED, BN_OP_MODPOW2 = 4, 5

EC_OP_MULGEN, EC_OP_MUL, EC_OP_ECDH, EC_OP_NEG = 1, 2, 3, 4

ECDSA_K_RAW, ECDSA_K_SEAM, ECDSA_K_ASN1 = 1, 2, 3
ECDSA_V_ZERO, ECDSA_V_ONE, ECDSA_V_MINUS1 = 0, 1, 2

RSA_K_NOKEY = 4          # the generator's K_PKCS1/K_PSS/K_SEAM are 0/1/2

T0_OP_STEPS = 1
T0_S_CLEAR, T0_S_PUT, T0_S_GET, T0_S_NORM = 0, 1, 2, 3

# The largest i15 buffers the bignum runner needs, filled in by
# build_bignum and emitted next to #CRY_MAX_A..F for the same reason:
# the board declares its arrays from these, so a vector that outgrows a
# buffer cannot be added by regenerating - the buffer grows with it, in
# the same edit.
BN_LIMITS = {"m": 0, "x": 0}


def _i15_words(n: int) -> int:
    return (n.bit_length() + 14) // 15


def build_bignum(t: Table):
    """The i15 big-integer core, on the SHARED table
    (tools/gen_bignum_vectors.py) plus the DERIVED full-limb modulus that
    tools/a64/a64_bignum_check.py added for mutation M22.

    WHY THE DERIVED MODULUS IS NOT OPTIONAL HERE.  Every modulus in the
    shared table is 256, 2048 or 3072 bits, and the i15 announced length
    rounds each one up to a whole number of 15-bit words, so R is about
    2^14 times the modulus and BnMontmul's final conditional subtraction
    fires about once in 16,384 multiplies.  The desk gate ran ten
    thousand of them and did not notice the correction was missing.
    2^270 - 3 is exactly eighteen full limbs, so R/m is 1.0 and the
    correction fires on about a fifth of random operands - and the
    (m-1)^2 case was checked to need it before it was written down.
    A board pass that skipped it would be a weaker proof than the desk's.
    """
    g = _load(TOOLS / "gen_bignum_vectors.py", "gen_bignum_vectors")
    bg = _load(A64 / "a64_bignum_check.py", "a64_bignum_check")

    def note_of(mi, n, what):
        return ("modulus %d (%d bits%s): %s"
                % (mi, n.bit_length(),
                   ", DERIVED - every limb full" if mi >= len(g.MODS) else "",
                   what))

    def track(mod_int, *vals):
        BN_LIMITS["m"] = max(BN_LIMITS["m"], _i15_words(mod_int))
        for v in vals:
            BN_LIMITS["x"] = max(BN_LIMITS["x"], _i15_words(v))

    def add(mi, n, op, a, b, c, e, what):
        track(n, int.from_bytes(b, "big") if b else 0,
              int.from_bytes(c, "big") if c else 0)
        t.add(MOD_BIGNUM, (a, b, c, b"", e, b""), op, note_of(mi, n, what))

    # ---- the four shared moduli, one job of each shape each ----------
    for mi, n in enumerate(g.MODS):
        mbytes = g.mod_bytes(n)
        mod = g.be(n, g.bytelen(n))

        for (xi, a_b, mb, r_b) in [r for r in g.reduce if r[0] == mi][:1]:
            add(mi, n, BN_OP_REDUCE, mod, a_b, b"", r_b,
                "BnReduce, %d-byte value" % len(a_b))
            add(mi, n, BN_OP_DECRED, mod, a_b, b"", r_b,
                "BnDecodeReduce, the same value through the decoder")

        for (xi, a_b, b_b, mb, r_b) in [r for r in g.montmul if r[0] == mi][:1]:
            add(mi, n, BN_OP_MONTMUL, mod, a_b, b_b, r_b,
                "BnToMonty + BnMontmul + BnFromMonty")

        for (xi, base, e_b, mb, r_b) in [r for r in g.modpow if r[0] == mi][:1]:
            add(mi, n, BN_OP_MODPOW, mod, base, e_b, r_b,
                "BnModpow, %d-bit exponent" % (len(e_b) * 8))

        for (xi, base, e_b, mb, r_b) in [r for r in g.modpow2 if r[0] == mi][:1]:
            add(mi, n, BN_OP_MODPOW2, mod, base, e_b, r_b,
                "BnModpow2, the windowed ladder")

    # ---- the derived full-limb modulus, exactly a64_bignum_check's ---
    n = bg.DERIVED_MOD
    mi = len(g.MODS)
    mbytes = g.mod_bytes(n)
    mod = g.be(n, g.bytelen(n))
    if _i15_words(n) * 15 != n.bit_length() + (15 - n.bit_length() % 15) % 15 \
            or n.bit_length() % 15 == 0:
        pass                       # 270 bits is exactly 18 limbs; see below
    if n % 2 == 0 or n.bit_length() % 15 != 0:
        raise SystemExit(
            "the derived modulus a64_bignum_check.DERIVED_MOD is no longer "
            "an odd, exact multiple of 15 bits, so it no longer forces "
            "BnMontmul's final conditional subtraction. Do not paper over "
            "this by dropping the case - find out what changed.")

    a = b = n - 1
    add(mi, n, BN_OP_MONTMUL, mod, g.be(a, g.bytelen(a)), g.be(b, g.bytelen(b)),
        g.be((a * b) % n, mbytes),
        "(m-1)^2 - NEEDS BnMontmul's final conditional subtraction")
    a2, b2 = (n - 1) // 3, (n - 2) // 5
    add(mi, n, BN_OP_MONTMUL, mod, g.be(a2, g.bytelen(a2)),
        g.be(b2, g.bytelen(b2)), g.be((a2 * b2) % n, mbytes),
        "ordinary operands against the same full-limb modulus")
    x = (n - 1) * (n - 1)
    add(mi, n, BN_OP_REDUCE, mod, g.be(x, g.bytelen(x)), b"",
        g.be(x % n, mbytes), "BnReduce of (m-1)^2")
    add(mi, n, BN_OP_DECRED, mod, g.be(x, g.bytelen(x)), b"",
        g.be(x % n, mbytes), "BnDecodeReduce of (m-1)^2")

    e_bits = max(_i15_words(v) for v in (n, max(g.MODS)))
    BN_LIMITS["m"] = max(BN_LIMITS["m"], e_bits)


def build_ec(t: Table):
    """P-256 and X25519, on the shared table (tools/gen_ec_vectors.py)
    with both DERIVED cases tools/a64/a64_ec_check.py added.

    THE TWO DERIVED CASES ARE THE ONES THAT REACH A LINE NO SHARED
    VECTOR REACHES, and each is here for a mutation that survived the
    shared set:

      * `$04 || p || sqrt(b)` - the ONLY non-canonical P-256 encoding
        whose reduction is on the curve, so the range test is the only
        thing left that can refuse it.  The shared `X = p` negative
        keeps its original Y and is refused by the on-curve test
        instead, which is why deleting the range check survived.
      * RFC 7748 KAT 1 with the scalar's bit 254 CLEARED.  Every shared
        scalar already has that bit set, so the clamp's `or` is a no-op
        on all of them.  A correct library puts the bit back and returns
        the published answer unchanged.

    Both refuse to become no-ops: if p stops being 3 mod 4, or b stops
    being a residue, or the chosen KAT's bit 254 is already clear, the
    gate's own helper returns None and this raises rather than quietly
    dropping the only case that reaches the line it defends.
    """
    ec = _load(TOOLS / "gen_ec_vectors.py", "gen_ec_vectors")
    eg = _load(A64 / "a64_ec_check.py", "a64_ec_check")
    ec.anchor()                       # the oracle proves itself first
    mulgen, mul, ecdh, neg = ec.build_ec256()
    kats, iters = ec.build_x25519()   # SAME ORDER AS THE GENERATOR'S main()

    for i, (k, pt) in enumerate(mulgen):
        t.add(MOD_P256, (b"", k, b"", b"", pt, b""), EC_OP_MULGEN,
              "EcP256Mulgen, gen_ec_vectors mulgen %d" % i)
    for i, (inpt, k, outpt, r) in enumerate(mul):
        assert r == 1
        t.add(MOD_P256, (inpt, k, b"", b"", outpt, b""), EC_OP_MUL,
              "EcP256Mul, gen_ec_vectors mul %d (BearSSL P256_carry KAT)" % i)
    for i, (priv, peer, sharedx, r) in enumerate(ecdh):
        assert r == 1
        t.add(MOD_P256, (peer, priv, b"", b"", sharedx, b""), EC_OP_ECDH,
              "EcP256Mul as ECDH, gen_ec_vectors ecdh %d - X only" % i)
    for i, (pt, k, r) in enumerate(neg):
        assert r == 0
        t.add(MOD_P256, (pt, k, b"", b"", b"", b""), EC_OP_NEG,
              "MUST BE REFUSED: %s" % eg.NEG_WHY[i])

    derived_pt = eg.derived_range_point(ec)
    if derived_pt is None:
        raise SystemExit(
            "a64_ec_check.derived_range_point declined to build the "
            "X = p, Y = sqrt(b) encoding, which is the only P-256 "
            "negative whose reduction is on the curve. Without it the "
            "board never reaches the coordinate range test. Find out "
            "why it declined; do not ship the table without the case.")
    t.add(MOD_P256, (derived_pt, mulgen[0][0], b"", b"", b"", b""), EC_OP_NEG,
          "MUST BE REFUSED: DERIVED - X = p with Y = sqrt(b), the one "
          "non-canonical encoding whose REDUCTION is on the curve, so "
          "only the coordinate range check can refuse it")

    for i, (sc, u, out) in enumerate(kats):
        t.add(MOD_X25519, (sc, u, b"", b"", out, b""), 0,
              "RFC 7748 section 5.2 KAT %d" % (i + 1) if i < 2 else
              "gen_ec_vectors generated case %d" % (i - 1))

    unclamped = eg.derived_unclamped_scalar(ec, kats[0][0])
    if unclamped is None:
        raise SystemExit(
            "a64_ec_check.derived_unclamped_scalar declined: RFC 7748 "
            "KAT 1's scalar no longer has bit 254 set, so clearing it "
            "proves nothing about the clamp. Find another KAT that does; "
            "do not drop the case.")
    t.add(MOD_X25519, (unclamped, kats[0][1], b"", b"", kats[0][2], b""), 1,
          "DERIVED - RFC 7748 KAT 1 with the scalar's bit 254 CLEARED: "
          "the clamp must put it back, so the published answer is unchanged")


def build_ecdsa(t: Table):
    """Every one of the shared table's records
    (tools/gen_ecdsa_vectors.py), through the entry point the desktop
    gate sends it through, with the same expected verdict AND the same
    expected EcdsaLastErr.

    THE NEGATIVES ARE THE POINT.  Nine of the records verify and
    thirty-seven must be refused; a signature checker that cannot be
    made to say no is not a signature checker.  The last of the fifteen
    malformed-DER records is the exception the gate documents: it is
    well-formed DER carrying r = s = 1, so it reaches the curve and is
    refused as a BAD SIGNATURE (1) rather than as a MALFORMED ENCODING
    (3).  Those two outcomes are identical in the return value and only
    EcdsaLastErr tells them apart, which is why it is checked.

    AND THE CURVE GATE, which is the easiest part of this to get
    wrong: P-384 and P-521 answer -1, never 0, because 0 means
    "this signature is bad" and saying that about a curve the module
    cannot compute is a wrong answer wearing a verdict's clothes.
    """
    eg = _load(TOOLS / "gen_ecdsa_vectors.py", "gen_ecdsa_vectors")
    ag = _load(A64 / "a64_ecdsa_check.py", "a64_ecdsa_check")
    eg.anchor()
    raw, asn1, der = eg.build()

    def param(kind, verdict, err, curve=0):
        return kind | (verdict << 8) | (err << 16) | (curve << 24)

    for (q, h, sig, expect, tag, note) in raw:
        t.add(MOD_ECDSA, (q, h, sig, b"", b"", b""),
              param(ECDSA_K_RAW,
                    ECDSA_V_ONE if expect else ECDSA_V_ZERO,
                    ag.ERR_OK if expect else ag.ERR_BADSIG),
              "EcdsaVrfyRaw, raw case %d: %s" % (tag, note))

    for (q, h, sig, expect, tag, note) in asn1:
        t.add(MOD_ECDSA, (q, h, sig, b"", b"", b""),
              param(ECDSA_K_SEAM,
                    ECDSA_V_ONE if expect else ECDSA_V_ZERO,
                    ag.ERR_OK if expect else ag.ERR_BADSIG, 23),
              "EcdsaVrfy (the certificate seam, curve 23), asn1 case %d: %s"
              % (tag, note))

    for i, (q, h, sig, expect, tag, note) in enumerate(der):
        last = (i == len(der) - 1)
        t.add(MOD_ECDSA, (q, h, sig, b"", b"", b""),
              param(ECDSA_K_ASN1, ECDSA_V_ZERO,
                    ag.ERR_BADSIG if last else ag.ERR_MALFORMED),
              "EcdsaVrfyAsn1, malformed der case %d: %s" % (tag, note))

    q, h, sig, expect, tag, note = asn1[0]
    for cid, name in ((24, "P-384"), (25, "P-521"), (0, "curve id 0"),
                      (29, "curve id 29")):
        t.add(MOD_ECDSA, (q, h, sig, b"", b"", b""),
              param(ECDSA_K_SEAM, ECDSA_V_MINUS1, ag.ERR_CURVE, cid),
              "curve gate: %s must answer -1 (cannot answer), never 0 "
              "(a verdict)" % name)
    t.add(MOD_ECDSA, (q, h, sig, b"", b"", b""),
          param(ECDSA_K_SEAM, ECDSA_V_ONE, ag.ERR_OK, 23),
          "curve gate: P-256 on the same record still answers 1")


def build_rsa(t: Table):
    """The shared RSA table
    (tools/gen_rsa_vectors.py, loaded through the gate's own
    a64_rsa_check.load_records so the builders are called in main()'s
    ORDER - the generator seeds one Random, and any other order is a
    different, quietly non-shared vector set).

    PKCS#1 v1.5 and PSS, valid and tampered, at 2048, 3072 and 4096
    bits, plus the real BearSSL root certificate's own signature at
    e = 65537 through the certificate seam.

    AND JOB d10, THE FORGOTTEN SETUP STEP, MEASURED RATHER THAN ARGUED.
    RsaSetPubKey is a setup call the caller must remember, and the
    module's header claims that forgetting it is safe rather than
    silent.  The record installs a ZERO key and requires all three entry
    points to return 0 AND the recovery buffer to come back holding
    nothing but the $A5 sentinel - so a refusal that returns 0 and
    writes anyway fails as loudly as a wrong verdict.
    """
    rg = _load(A64 / "a64_rsa_check.py", "a64_rsa_check")
    g = rg.load_records()

    kindname = {g.K_PKCS1: "PKCS#1 v1.5", g.K_PSS: "PSS",
                g.K_SEAM: "the certificate seam (RsaVrfy, recovers the hash)"}

    seam_positive = None
    for i, (kind, expect, n, e, sig, msg, saltlen) in enumerate(g.RECORDS):
        want = b""
        if kind == g.K_SEAM and expect:
            # The seam RECOVERS the signed hash for the caller to compare,
            # so this record has bytes as well as a verdict and the board
            # checks both.  hashlib is the second implementation.
            want = hashlib.sha256(msg).digest()
        t.add(MOD_RSA, (n, e, sig, msg, want, b""),
              kind | (expect << 8) | (saltlen << 16),
              "%s, %d-bit modulus, e = %s, %s (gen_rsa_vectors record %d)"
              % (kindname.get(kind, "kind %d" % kind), len(n) * 8,
                 int.from_bytes(e, "big"),
                 "MUST VERIFY" if expect else "MUST BE REFUSED", i))
        if kind == g.K_PKCS1 and expect and len(n) * 8 == 2048:
            seam_positive = (n, e, sig, msg, saltlen)

    if seam_positive is None:
        raise SystemExit(
            "the shared RSA table no longer contains a positive 2048-bit "
            "PKCS#1 v1.5 record, and job d10 re-points one of those at a "
            "zero key. Find the record; do not synthesise one here.")
    n, e, sig, msg, saltlen = seam_positive
    t.add(MOD_RSA, (b"", b"", sig, msg, bytes([0xA5]) * 32, b""),
          RSA_K_NOKEY | (0 << 8) | (g.HLEN << 16),
          "d10 NO KEY INSTALLED: every entry point must refuse and write "
          "nothing - the 32-byte $A5 sentinel must come back unbroken")


def build_t0vm(t: Table, ram_probe_pad: int):
    """The T0 bytecode machine's RAM bounds guard and its
    64-bit cell contract, as a table of steps the board replays.

    WHY A STEP TABLE AND NOT A TRANSCRIBED SEQUENCE.  The bounds
    contract is five lines in RaspberryPi4/Lib/t0vm.pi4 - an access of
    `n` bytes at `addr` is legal exactly when `0 <= addr <= RAM_SIZE - n`
    - and both numbers are read OUT OF THAT FILE here, by the desktop
    gate's own reader (a64_t0vm_check.module_constants).  Every
    expectation below is then computed from the contract rather than
    copied from a run, so a table that disagrees with the file is a
    generation-time error and not a silent board failure.

    WHAT IS NOT HERE, AND IT IS THE LARGER HALF.  The desktop gate also
    runs the SHARED PEM DECODER BYTECODE over three real certificates.
    That needs the pemdec blob, and this tree carries no board copy of
    it.  The board therefore proves the VM's guard, its cell
    width and its interpreter through the X.509 module below, which
    drives the same VM over the x509 bytecode on every chain, and the
    PEM half stays a desk result.  Said plainly rather than left as an
    absence.
    """
    tg = _load(A64 / "a64_t0vm_check.py", "a64_t0vm_check")
    K = tg.module_constants()
    N = K["T0_RAM_SIZE"]
    E = K["T0ERR_RAM_BOUNDS"]
    if N <= 0 or E <= 0:
        raise SystemExit(
            "a64_t0vm_check.module_constants could not read #T0_RAM_SIZE "
            "and #T0ERR_RAM_BOUNDS out of RaspberryPi4/Lib/t0vm.pi4, so "
            "every expectation below would be invented. Fix the reader.")

    steps, want = bytearray(), bytearray()

    def step(op, width, addr, value, result, err):
        steps.extend(bytes([op & 255, width & 255, 0, 0]))
        steps.extend((addr & 0xFFFFFFFF).to_bytes(4, "little"))
        steps.extend((value & 0xFFFFFFFF).to_bytes(4, "little"))
        want.extend((result & ((1 << 64) - 1)).to_bytes(8, "little"))
        want.extend((err & ((1 << 64) - 1)).to_bytes(8, "little"))

    def clear():
        step(T0_S_CLEAR, 0, 0, 0, 0, 0)

    # THE SENTINEL HAS TO SIT WHERE NO LEGAL WRITE IN THIS TABLE LANDS,
    # and the first draft put it at offset 3 - which the four-byte write
    # at offset 0 covers. The board would then have read the low byte of
    # 0x12345678 and the table would have insisted on $A5. The gate's
    # own second-opinion pass caught it before anything was built, which
    # is what that pass is for; the address is checked here rather than
    # chosen carefully and hoped over.
    sentinel_at, sentinel = 100, 0xA5
    for w in (1, 2, 4):
        for base in (0, N - w):
            if base <= sentinel_at < base + w:
                raise SystemExit(
                    "the t0vm bounds table's sentinel at offset %d is inside "
                    "the %d-byte legal write at %d, so the 'the refused write "
                    "did not land' check would be reading a byte this table "
                    "legitimately changed. Move the sentinel."
                    % (sentinel_at, w, base))
    clear()
    step(T0_S_PUT, 1, sentinel_at, sentinel, 0, 0)

    for w, mask in ((1, 0xFF), (2, 0xFFFF), (4, 0xFFFFFFFF)):
        v = (0x12345678 & mask)
        # ---- the two legal ends of the range ------------------------
        for addr, why in ((0, "offset 0"), (N - w, "the LAST legal offset")):
            clear()
            step(T0_S_PUT, w, addr, v, 0, 0)
            step(T0_S_GET, w, addr, 0, v, 0)
        # ---- and every way out of it --------------------------------
        for addr in (-1, -w, N - w + 1, N, N + ram_probe_pad):
            clear()
            step(T0_S_PUT, w, addr, v ^ mask, 0, E)
            clear()
            # A REFUSED READ ANSWERS 0, not the byte next door.
            step(T0_S_GET, w, addr, 0, 0, E)
            clear()
            # ...and the refused WRITE must not have landed anywhere:
            # the sentinel is still what it was set to at the top.
            step(T0_S_GET, 1, sentinel_at, 0, sentinel, 0)

    # ---- T0Norm: a cell is a SIGN-EXTENDED int32 ---------------------
    # -1 must be $FFFFFFFFFFFFFFFF and never $00000000FFFFFFFF. This is
    # the family's one declared addition and it is a contract, not an
    # optimisation, so the board states it in numbers.
    for v in (0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFFFFFE):
        clear()
        step(T0_S_NORM, 0, 0, v, ((v & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000,
             0)

    nsteps = len(steps) // 12
    assert len(want) == nsteps * 16
    t.add(MOD_T0VM, (bytes(steps), b"", b"", b"", bytes(want), b""),
          T0_OP_STEPS,
          "forum 517's RAM bounds guard and the 64-bit cell contract: "
          "%d steps, RAM_SIZE %d, refusal code %d, all three widths at "
          "both ends of the range and five ways out of it" % (nsteps, N, E))


def build_x509(t: Table):
    """The certificate chain validator, on mode C of
    tools/a64/a64_x509_check.py - the image no 32-bit family can build,
    with BOTH halves of the signature seam linked and nothing stubbed.

    A REAL CHAIN VERIFIES AND A TAMPERED ONE IS REFUSED BY NAME.  The
    gate checks the NAME of every refusal rather than merely that a
    refusal happened, and so does the board: a validator that answers
    the wrong non-OK code still looks like a working validator to a
    caller that only asks "did it fail".  Five of the thirteen cases
    below are tampered - a flipped last signature byte on the
    end-entity and on the intermediate, an EC signature TLV tag walked
    to and corrupted, and the two RSA equivalents - and THEY DO NOT ALL
    ANSWER THE SAME CODE, which is the reason the name is checked at
    all.  A corrupt END-ENTITY signature is 52
    (#X509ERR_BAD_SIGNATURE): it is verified explicitly against the
    issuer's key.  A corrupt INTERMEDIATE signature is 62
    (#X509ERR_NOT_TRUSTED): that step is the TRUST decision, and the
    walk finishing without an anchor validating is what a corrupt CA
    signature causes.  This docstring said "every one of them must come
    back 52, not 62" until 2026-09-05, and the BOARD is what corrected
    it - see the note in a64_x509_check.load_modeC.

    NOT ONE CERTIFICATE BYTE IS TYPED.  The chains, the anchors, the
    server names and the tampered copies all come out of
    tools/x509_proof_gen.py and tools/ecdsa_x509_gen.py through the
    gate's own loaders, and the tamper functions preserve length by
    construction, which the gate asserts.

    THE SLOTS, because this module needs more scalars than `param`
    holds and the alternative was a second meta field that every reader
    of this table would then have to know about:
        a  every certificate's DER, in chain order, end-entity first
        b  their lengths, one unsigned 16-bit little-endian each
        c  a 16-byte case header: unixTime (i64), serverLen (i32),
           anchor type, isCA, curve, anchor count
        d  the anchors, each framed u16 dnLen || dn || u16 aLen || a ||
           u16 bLen || b   (a = the modulus or the point, b = the RSA
           exponent, empty for EC)
        e  ONE BYTE: the expected #X509ERR_* code
        f  the server name, empty when serverLen is negative
        param  the certificate count
    """
    x5 = _load(A64 / "a64_x509_check.py", "a64_x509_check")
    x5.check_blob_identity()
    cases, blobs = x5.load_modeC()
    names = x5.name_cases(cases, "C")

    for case, nm in zip(cases, names):
        chain = b"".join(blobs[lab] for lab, ln in case["certs"])
        for lab, ln in case["certs"]:
            if len(blobs[lab]) != ln:
                raise SystemExit(
                    "x509 case %s declares %s as %d bytes and the blob is "
                    "%d. The tamper helpers preserve length by "
                    "construction, so this is a real disagreement."
                    % (nm, lab, ln, len(blobs[lab])))
        lens = b"".join(ln.to_bytes(2, "little") for lab, ln in case["certs"])

        anchors = case["anchors"]
        atype = anchors[0]["type"] if anchors else 0
        isCA = anchors[0]["isCA"] if anchors else 0
        curve = anchors[0]["curve"] if anchors else 0
        hdr = ((case["time"] & ((1 << 64) - 1)).to_bytes(8, "little")
               + (case["srvlen"] & 0xFFFFFFFF).to_bytes(4, "little")
               + bytes([atype & 255, isCA & 255, curve & 255, len(anchors)]))

        abody = bytearray()
        for a in anchors:
            dn = blobs[a["dn"]]
            key = blobs[a["a"]]
            exp = blobs[a["b"]] if a["b"] else b""
            for part in (dn, key, exp):
                abody.extend(len(part).to_bytes(2, "little"))
                abody.extend(part)

        srv = blobs[case["server"]] if case["server"] else b""
        if case["srvlen"] >= 0 and len(srv) != case["srvlen"]:
            raise SystemExit(
                "x509 case %s asks for a %d-byte server name and the blob "
                "is %d bytes." % (nm, case["srvlen"], len(srv)))

        t.add(MOD_X509,
              (chain, lens, hdr, bytes(abody),
               bytes([case["expect"] & 255]), srv),
              len(case["certs"]),
              "%s -> %s (%d)" % (nm, x5.verdict(case["expect"]),
                                 case["expect"]))


# ======================================================================
#  EMISSION
# ======================================================================
def emit(t: Table) -> str:
    maxes = [0] * 6
    for _, _, fields, _, _ in t.recs:
        for k in range(6):
            maxes[k] = max(maxes[k], len(fields[k]))

    names = {m: n for m, n, _ in MODULES}
    out = []
    A = out.append
    A("; ======================================================================")
    # The header names the table by the file name it had when Anvil main's
    # copy was generated. It is kept so a regeneration is byte-identical to
    # the committed table; rename it here and regenerate in the same change.
    A(";  cryptotest_vectors.pi4 - GENERATED by tools/gen_pi4_crypto_selftest.py")
    A(";  NOT A SOURCE FILE. DO NOT EDIT. Regenerate it; do not patch it.")
    A("; ======================================================================")
    A(";")
    A(";  Every vector here was read out of a published document or out of a")
    A(";  generator that already gates this tree; not one was typed. The")
    A(";  generator's header names the source of each module and says why that")
    A(";  matters more than it looks.")
    A(";")
    A(";  TEN Data.l PER RECORD, then the bytes:")
    A(";      0 module  1 vecid  2 la  3 lb  4 lc  5 ld  6 le  7 lf")
    A(";      8 param   9 offset of this record's bytes from CryVecData")
    A(";  Slot e is ALWAYS the expected output. The rest are per module:")
    A(";")
    for m, n, meaning in MODULES:
        A(";    %-2d %-9s %s" % (m, n, meaning))
    A(";")
    A(";  REACH THIS DATA WITH ?CryVecMeta / ?CryVecData AND PeekA, NEVER WITH")
    A(";  Read/Restore. Read strides two bytes whatever the element width")
    A(";  (an open bug on every target), and Read and Restore share one")
    A(";  program-wide cursor that any other loop in the image can move.")
    A(";")
    A("; ======================================================================")
    A("")
    A("#CRY_VEC_COUNT   = %d" % len(t.recs))
    A("#CRY_META_STRIDE = 40")
    A("")
    A("; The largest field in each slot over the WHOLE table. The board sizes")
    A("; its buffers from these, so a vector that outgrows a buffer cannot be")
    A("; added by regenerating - the buffer grows with it, in the same edit.")
    for k in range(6):
        A("#CRY_MAX_%s = %d" % ("ABCDEF"[k], maxes[k]))
    A("")
    A("; The bignum runner's i15 arrays, in WORDS, from the widest modulus")
    A("; and the widest value in the table above - same argument as the")
    A("; six lines before it. The +1 is the announced-length header word")
    A("; every i15 array carries, and it is added here rather than in the")
    A("; board file so a reader of either one sees the same number.")
    A("#CRY_BN_MWORDS = %d" % (BN_LIMITS["m"] + 2))
    A("#CRY_BN_XWORDS = %d" % (max(BN_LIMITS["m"], BN_LIMITS["x"]) + 2))
    A("")
    for m, n, _ in MODULES:
        A("#CRY_MOD_%-8s = %d   ; %d vectors" %
          (n.upper().replace("-", ""), m, t.count(m)))
    A("")
    A("DataSection")
    A("  CryVecMeta:")
    off = 0
    offsets = []
    for module, vid, fields, param, note in t.recs:
        offsets.append(off)
        A("  ; %-9s %3d  %s" % (names[module], vid, note))
        A("  Data.l %d, %d, %d, %d, %d, %d, %d, %d, %d, %d"
          % (module, vid, len(fields[0]), len(fields[1]), len(fields[2]),
             len(fields[3]), len(fields[4]), len(fields[5]), param, off))
        off += sum(len(f) for f in fields)
    A("")
    A("  CryVecData:")
    for (module, vid, fields, param, note), o in zip(t.recs, offsets):
        A("  ; ---- %s %d at +%d : %s ----" % (names[module], vid, o, note))
        blob = b"".join(fields)
        if not blob:
            A("  ; (this record carries no bytes at all)")
            continue
        for i in range(0, len(blob), 16):
            A("  Data.b " + ", ".join(str(b) for b in blob[i:i + 16]))
    A("EndDataSection")
    A("")
    return "\n".join(out)


def main() -> int:
    t = Table()
    build_sha256(t, 21)
    build_sha1(t, 10)
    build_hmac(t)
    build_hmacsha1(t)
    build_hkdf(t, 5)
    build_pbkdf2(t, 4096)
    build_drbg(t, 5)
    build_aes(t, cavp=True)
    build_aesctr(t, 4144)
    build_gcm(t)
    build_keywrap(t)
    build_bignum(t)
    build_ec(t)
    build_ecdsa(t)
    build_rsa(t)
    build_t0vm(t, 4096)
    build_x509(t)

    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
        ROOT / "Anvil" / "Core" / "cryptotest_vectors.pbi"
    text = emit(t)
    out.write_text(text, encoding="utf-8", newline="\n")

    names = {m: n for m, n, _ in MODULES}
    total = sum(sum(len(f) for f in r[2]) for r in t.recs)
    print("wrote %d vectors, %d bytes of vector data -> %s"
          % (len(t.recs), total, out))
    for m, n, _ in MODULES:
        print("   %-9s %3d" % (n, t.count(m)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
