#!/usr/bin/env python3
r"""TLS 1.3 client on the Pi 4: the RFC 8448 section 3 trace, on the desk.

      py -3 -B tools/tls13_rfc8448_check.py --compiler <PureMetalForge.exe>
      py -3 -B tools/tls13_rfc8448_check.py --compiler <...> --mutate
      py -3 -B tools/tls13_rfc8448_check.py --compiler <...> --jobs 12

WHAT IS UNDER TEST

  RaspberryPi4/Lib/tls13_record.pi4 and RaspberryPi4/Lib/tls13_hs.pi4,
  built for -t pi4 with the Pi 4 include list those files' headers name
  (Anvil/Core/sha256.pbi, hmac, hkdf, entropy, drbg, Anvil/Crypto/aes.pbi,
  gcm, bignum, ec256, x25519, ecdsa, rsa, t0vm, x509_blob, x509 - every
  one the real Pi 4 copy, nothing stubbed, #X509_SIG_LINKED = 1), and run
  under the AArch64 model tools/a64/a64_interp.py.

  This is the Pi 4 replay of the RP2350's tls13SelfTest.pico2: the same
  RFC 8448 "Simple 1-RTT Handshake", the same checks, in the same nine
  sections - the key schedule end to end, the transcript, every handshake
  message parsed and VERIFIED (the trace's real RSA-PSS CertificateVerify
  checked against its real certificate through x509), the client Finished
  and both directions of record protection byte for byte against the
  published records, and the refusal table case by case, each refusal
  checked for its NAME. Added for this part: the 64-bit sequence-number
  carry and overflow (port change 2 in tls13_record.pi4), the
  unseeded-DRBG refusal (port change 2 in tls13_hs.pi4) and the hkdf
  verdict latch (port change 3).

WHERE THE EXPECTED VALUES COME FROM

  RFC 8448 literals, RE-DERIVED here by an independent python RFC 8446
  key schedule and record layer before anything runs (the derivation of
  tools/gen_tls13_vectors.py in the compiler repository). AES-GCM is a
  from-scratch python AES-128/GHASH, itself anchored to FIPS-197 C.1 and
  to the eight published RFC 8448 records - no third-party package is
  needed. A mistyped digit stops the gate before the model starts. The
  P-256 values come from tools/gen_ec_vectors.py's anchored oracle.

HOW IT RUNS, AND WHY THE STATE IS SNAPSHOTTED

  The harness is a thin dispatcher (Op) over the library's own
  procedures; arguments go in at #H_ARGS and every result is read back
  out of the library's OWN globals by their addresses in the image's
  .sym file - the same globals the Pico self-test reads. The model runs
  roughly 200k instructions a second, and one X25519 or one RSA-2048
  verify is tens of millions, so:
    * the sections run as independent jobs across processes (--jobs);
    * a machine state reached by a REAL computation (the trace's
      ServerHello processed, the full handshake completed) is snapshotted
      and each case that starts from it starts from a copy, instead of
      repeating the X25519 for every refusal case;
    * the trace's private key is written into the library's own
      secTlsPriv global by the harness - there is no runtime API that
      accepts a private key, and the harness is compiled into the image
      it tests, exactly as on the Pico.

  Where the Pico self-test re-ran Tls13Init to change the clock or the
  expected name for one case, this gate edits the caller-owned name bytes
  (as the Pico does) and the TlsUnixTime the Init stored, on a snapshot
  taken after the ServerHello. Tls13Init only stores those two values;
  the cases that test Init's own refusals (no clock, no anchor) call
  Tls13Init for real.

--mutate: copies of the two TLS files (and, for two cases, gcm.pi4) are
edited one thing at a time in a temporary directory and the gate is
re-run on each; every mutant marked "kill" must turn it red, and the one
marked "survive" (gcm regressed to the 32-bit verdict spelling, record
layer correct) must stay green - that one shows port change 1 doing its
job. No library file is ever opened for writing.

DESK ONLY. This gate touches no board. A green run here is a desk result:
the model and the code generator can share a defect that only the part
exposes. NOTHING HERE HAS RUN ON SILICON.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import hmac
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "a64"))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB = ROOT / "RaspberryPi4" / "Lib"
REC_SRC = LIB / "tls13_record.pi4"
HS_SRC = LIB / "tls13_hs.pi4"
GCM_SRC = LIB / "gcm.pi4"

LOAD, STACK, RETURN = 0x400000, 0x3000000, 0xDEAD0000
H_ARGS = 0x0A000000
H_DATA = 0x0B000000
REC, OUT, EXP, TMP, MSG, NAME = (0x0C000000, 0x0C001000, 0x0C002000,
                                 0x0C003000, 0x0C003800, 0x0C004000)
HSBUF, HSBUF_N = 0x0C010000, 4096
RECV, RECV_N = 0x0C020000, 768
STEP_LIMIT = 4_000_000_000
TIME_OK = 1500000000          # 2017-07-14, inside the trace cert's window

MASK64 = (1 << 64) - 1


class Fail(Exception):
    pass


# =====================================================================
#  AN INDEPENDENT AES-128-GCM (FIPS-197 / SP 800-38D), anchored below
# =====================================================================
def _rotl8(x, s):
    return ((x << s) | (x >> (8 - s))) & 0xFF


def _make_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        sbox[p] = q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4) ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


SBOX = _make_sbox()


def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def aes_keys(key):
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    rc = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rc
            rc = _xt(rc)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(11)]


def aes_block(rk, blk):
    s = [b ^ k for b, k in zip(blk, rk[0])]
    for r in range(1, 11):
        s = [SBOX[b] for b in s]
        s = [s[((c + rr) % 4) * 4 + rr] for c in range(4) for rr in range(4)]
        if r != 10:
            m = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                m += [_xt(a[0]) ^ _xt(a[1]) ^ a[1] ^ a[2] ^ a[3],
                      a[0] ^ _xt(a[1]) ^ _xt(a[2]) ^ a[2] ^ a[3],
                      a[0] ^ a[1] ^ _xt(a[2]) ^ _xt(a[3]) ^ a[3],
                      _xt(a[0]) ^ a[0] ^ a[1] ^ a[2] ^ _xt(a[3])]
            s = m
        s = [b ^ k for b, k in zip(s, rk[r])]
    return bytes(s)


def _gmul(x, y):
    z, v = 0, y
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= v
        v = (v >> 1) ^ (0xE1 << 120) if v & 1 else v >> 1
    return z


def _ghash(h, aad, ct):
    def blocks(b):
        b = b + b"\x00" * (-len(b) % 16)
        return [int.from_bytes(b[i:i + 16], "big") for i in range(0, len(b), 16)]
    y = 0
    for blk in blocks(aad) + blocks(ct) + [((len(aad) * 8) << 64) | (len(ct) * 8)]:
        y = _gmul(y ^ blk, h)
    return y


def _ctr(rk, j0, data):
    out = bytearray()
    ctr = int.from_bytes(j0[12:], "big")
    for i in range(0, len(data), 16):
        ctr = (ctr + 1) & 0xFFFFFFFF
        ks = aes_block(rk, j0[:12] + ctr.to_bytes(4, "big"))
        out += bytes(a ^ b for a, b in zip(data[i:i + 16], ks))
    return bytes(out)


def gcm_seal(key, iv, pt, aad):
    rk = aes_keys(key)
    h = int.from_bytes(aes_block(rk, bytes(16)), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    ct = _ctr(rk, j0, pt)
    s = _ghash(h, aad, ct) ^ int.from_bytes(aes_block(rk, j0), "big")
    return ct + s.to_bytes(16, "big")


def gcm_open(key, iv, ctag, aad):
    ct, tag = ctag[:-16], ctag[-16:]
    rk = aes_keys(key)
    h = int.from_bytes(aes_block(rk, bytes(16)), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    s = _ghash(h, aad, ct) ^ int.from_bytes(aes_block(rk, j0), "big")
    if s.to_bytes(16, "big") != tag:
        raise Fail("tag mismatch")
    return _ctr(rk, j0, ct)


def _anchor_aes():
    got = aes_block(aes_keys(bytes(range(16))), bytes.fromhex("00112233445566778899aabbccddeeff"))
    if got.hex() != "69c4e0d86a7b0430d8cdb78070b4c55a":
        raise SystemExit("the python AES oracle fails FIPS-197 C.1 - no vector is trusted")


# =====================================================================
#  THE TRACE (RFC 8448 section 3) AND EVERYTHING DERIVED FROM IT
# =====================================================================
def H(s):
    return bytes.fromhex("".join(s.split()))


def _load_ecv():
    spec = importlib.util.spec_from_file_location("gen_ec_vectors", ROOT / "tools" / "gen_ec_vectors.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build_vectors():
    _anchor_aes()
    V = {}
    CLIENT_PRIV = H("49 af 42 ba 7f 79 94 85 2d 71 3e f2 78 4b cb ca a7 91 1d e2 6a dc 56 42 cb 63 45 40 e7 ea 50 05")
    CLIENT_PUB = H("99 38 1d e5 60 e4 bd 43 d2 3d 8e 43 5a 7d ba fe b3 c0 6e 51 c1 3c ae 4d 54 13 69 1e 52 9a af 2c")
    SERVER_PUB = H("c9 82 88 76 11 20 95 fe 66 76 2b db f7 c6 72 e1 56 d6 cc 25 3b 83 3d f1 dd 69 b1 b0 4e 75 1f 0f")
    CH = H("""01 00 00 c0 03 03 cb 34 ec b1 e7 81 63 ba 1c 38 c6 da cb 19 6a 6d
ff a2 1a 8d 99 12 ec 18 a2 ef 62 83 02 4d ec e7 00 00 06 13 01 13 03 13
02 01 00 00 91 00 00 00 0b 00 09 00 00 06 73 65 72 76 65 72 ff 01 00 01
00 00 0a 00 14 00 12 00 1d 00 17 00 18 00 19 01 00 01 01 01 02 01 03 01
04 00 23 00 00 00 33 00 26 00 24 00 1d 00 20 99 38 1d e5 60 e4 bd 43 d2
3d 8e 43 5a 7d ba fe b3 c0 6e 51 c1 3c ae 4d 54 13 69 1e 52 9a af 2c 00
2b 00 03 02 03 04 00 0d 00 20 00 1e 04 03 05 03 06 03 02 03 08 04 08 05
08 06 04 01 05 01 06 01 02 01 04 02 05 02 06 02 02 02 00 2d 00 02 01 01
00 1c 00 02 40 01""")
    SH = H("""02 00 00 56 03 03 a6 af 06 a4 12 18 60 dc 5e 6e 60 24 9c d3 4c 95
93 0c 8a c5 cb 14 34 da c1 55 77 2e d3 e2 69 28 00 13 01 00 00 2e 00 33
00 24 00 1d 00 20 c9 82 88 76 11 20 95 fe 66 76 2b db f7 c6 72 e1 56 d6
cc 25 3b 83 3d f1 dd 69 b1 b0 4e 75 1f 0f 00 2b 00 02 03 04""")
    EE = H("""08 00 00 24 00 22 00 0a 00 14 00 12 00 1d 00 17 00 18 00 19 01 00
01 01 01 02 01 03 01 04 00 1c 00 02 40 01 00 00 00 00""")
    CERT = H("""0b 00 01 b9 00 00 01 b5 00 01 b0 30 82 01 ac 30 82 01 15 a0 03
02 01 02 02 01 02 30 0d 06 09 2a 86 48 86 f7 0d 01 01 0b 05 00 30 0e 31
0c 30 0a 06 03 55 04 03 13 03 72 73 61 30 1e 17 0d 31 36 30 37 33 30 30
31 32 33 35 39 5a 17 0d 32 36 30 37 33 30 30 31 32 33 35 39 5a 30 0e 31
0c 30 0a 06 03 55 04 03 13 03 72 73 61 30 81 9f 30 0d 06 09 2a 86 48 86
f7 0d 01 01 01 05 00 03 81 8d 00 30 81 89 02 81 81 00 b4 bb 49 8f 82 79
30 3d 98 08 36 39 9b 36 c6 98 8c 0c 68 de 55 e1 bd b8 26 d3 90 1a 24 61
ea fd 2d e4 9a 91 d0 15 ab bc 9a 95 13 7a ce 6c 1a f1 9e aa 6a f9 8c 7c
ed 43 12 09 98 e1 87 a8 0e e0 cc b0 52 4b 1b 01 8c 3e 0b 63 26 4d 44 9a
6d 38 e2 2a 5f da 43 08 46 74 80 30 53 0e f0 46 1c 8c a9 d9 ef bf ae 8e
a6 d1 d0 3e 2b d1 93 ef f0 ab 9a 80 02 c4 74 28 a6 d3 5a 8d 88 d7 9f 7f
1e 3f 02 03 01 00 01 a3 1a 30 18 30 09 06 03 55 1d 13 04 02 30 00 30 0b
06 03 55 1d 0f 04 04 03 02 05 a0 30 0d 06 09 2a 86 48 86 f7 0d 01 01 0b
05 00 03 81 81 00 85 aa d2 a0 e5 b9 27 6b 90 8c 65 f7 3a 72 67 17 06 18
a5 4c 5f 8a 7b 33 7d 2d f7 a5 94 36 54 17 f2 ea e8 f8 a5 8c 8f 81 72 f9
31 9c f3 6b 7f d6 c5 5b 80 f2 1a 03 01 51 56 72 60 96 fd 33 5e 5e 67 f2
db f1 02 70 2e 60 8c ca e6 be c1 fc 63 a4 2a 99 be 5c 3e b7 10 7c 3c 54
e9 b9 eb 2b d5 20 3b 1c 3b 84 e0 a8 b2 f7 59 40 9b a3 ea c9 d9 1d 40 2d
cc 0c c8 f8 96 12 29 ac 91 87 b4 2b 4d e1 00 00""")
    CV = H("""0f 00 00 84 08 04 00 80 5a 74 7c 5d 88 fa 9b d2 e5 5a b0 85 a6 10
15 b7 21 1f 82 4c d4 84 14 5a b3 ff 52 f1 fd a8 47 7b 0b 7a bc 90 db 78
e2 d3 3a 5c 14 1a 07 86 53 fa 6b ef 78 0c 5e a2 48 ee aa a7 85 c4 f3 94
ca b6 d3 0b be 8d 48 59 ee 51 1f 60 29 57 b1 54 11 ac 02 76 71 45 9e 46
44 5c 9e a5 8c 18 1e 81 8e 95 b8 c3 fb 0b f3 27 84 09 d3 be 15 2a 3d a5
04 3e 06 3d da 65 cd f5 ae a2 0d 53 df ac d4 2f 74 f3""")
    SFIN = H("""14 00 00 20 9b 9b 14 1d 90 63 37 fb d2 cb dc e7 1d f4 de da 4a
b4 2c 30 95 72 cb 7f ff ee 54 54 b7 8f 07 18""")
    CFIN = H("""14 00 00 20 a8 ec 43 6d 67 76 34 ae 52 5a c1 fc eb e1 1a 03 9e
c1 76 94 fa c6 e9 85 27 b6 42 f2 ed d5 ce 61""")
    NST = H("""04 00 00 c9 00 00 00 1e fa d6 aa c5 02 00 00 00 b2 2c 03 5d 82 93
59 ee 5f f7 af 4e c9 00 00 00 00 26 2a 64 94 dc 48 6d 2c 8a 34 cb 33 fa
90 bf 1b 00 70 ad 3c 49 88 83 c9 36 7c 09 a2 be 78 5a bc 55 cd 22 60 97
a3 a9 82 11 72 83 f8 2a 03 a1 43 ef d3 ff 5d d3 6d 64 e8 61 be 7f d6 1d
28 27 db 27 9c ce 14 50 77 d4 54 a3 66 4d 4e 6d a4 d2 9e e0 37 25 a6 a4
da fc d0 fc 67 d2 ae a7 05 29 51 3e 3d a2 67 7f a5 90 6c 5b 3f 7d 8f 92
f2 28 bd a4 0d da 72 14 70 f9 fb f2 97 b5 ae a6 17 64 6f ac 5c 03 27 2e
97 07 27 c6 21 a7 91 41 ef 5f 7d e6 50 5e 5b fb c3 88 e9 33 43 69 40 93
93 4a e4 d3 57 00 08 00 2a 00 04 00 00 04 00""")
    APPDATA = bytes(range(0x32))
    ALERT_CLOSE = H("01 00")
    REC_SH = H("16 03 03 00 5a") + SH
    REC_FLIGHT = H("""17 03 03 02 a2 d1 ff 33 4a 56 f5 bf f6 59 4a 07 cc 87 b5 80
23 3f 50 0f 45 e4 89 e7 f3 3a f3 5e df 78 69 fc f4 0a a4 0a a2 b8 ea 73
f8 48 a7 ca 07 61 2e f9 f9 45 cb 96 0b 40 68 90 51 23 ea 78 b1 11 b4 29
ba 91 91 cd 05 d2 a3 89 28 0f 52 61 34 aa dc 7f c7 8c 4b 72 9d f8 28 b5
ec f7 b1 3b d9 ae fb 0e 57 f2 71 58 5b 8e a9 bb 35 5c 7c 79 02 07 16 cf
b9 b1 18 3e f3 ab 20 e3 7d 57 a6 b9 d7 47 76 09 ae e6 e1 22 a4 cf 51 42
73 25 25 0c 7d 0e 50 92 89 44 4c 9b 3a 64 8f 1d 71 03 5d 2e d6 5b 0e 3c
dd 0c ba e8 bf 2d 0b 22 78 12 cb b3 60 98 72 55 cc 74 41 10 c4 53 ba a4
fc d6 10 92 8d 80 98 10 e4 b7 ed 1a 8f d9 91 f0 6a a6 24 82 04 79 7e 36
a6 a7 3b 70 a2 55 9c 09 ea d6 86 94 5b a2 46 ab 66 e5 ed d8 04 4b 4c 6d
e3 fc f2 a8 94 41 ac 66 27 2f d8 fb 33 0e f8 19 05 79 b3 68 45 96 c9 60
bd 59 6e ea 52 0a 56 a8 d6 50 f5 63 aa d2 74 09 96 0d ca 63 d3 e6 88 61
1e a5 e2 2f 44 15 cf 95 38 d5 1a 20 0c 27 03 42 72 96 8a 26 4e d6 54 0c
84 83 8d 89 f7 2c 24 46 1a ad 6d 26 f5 9e ca ba 9a cb bb 31 7b 66 d9 02
f4 f2 92 a3 6a c1 b6 39 c6 37 ce 34 31 17 b6 59 62 22 45 31 7b 49 ee da
0c 62 58 f1 00 d7 d9 61 ff b1 38 64 7e 92 ea 33 0f ae ea 6d fa 31 c7 a8
4d c3 bd 7e 1b 7a 6c 71 78 af 36 87 90 18 e3 f2 52 10 7f 24 3d 24 3d c7
33 9d 56 84 c8 b0 37 8b f3 02 44 da 8c 87 c8 43 f5 e5 6e b4 c5 e8 28 0a
2b 48 05 2c f9 3b 16 49 9a 66 db 7c ca 71 e4 59 94 26 f7 d4 61 e6 6f 99
88 2b d8 9f c5 08 00 be cc a6 2d 6c 74 11 6d bd 29 72 fd a1 fa 80 f8 5d
f8 81 ed be 5a 37 66 89 36 b3 35 58 3b 59 91 86 dc 5c 69 18 a3 96 fa 48
a1 81 d6 b6 fa 4f 9d 62 d5 13 af bb 99 2f 2b 99 2f 67 f8 af e6 7f 76 91
3f a3 88 cb 56 30 c8 ca 01 e0 c6 5d 11 c6 6a 1e 2a c4 c8 59 77 b7 c7 a6
99 9b bf 10 dc 35 ae 69 f5 51 56 14 63 6c 0b 9b 68 c1 9e d2 e3 1c 0b 3b
66 76 30 38 eb ba 42 f3 b3 8e dc 03 99 f3 a9 f2 3f aa 63 97 8c 31 7f c9
fa 66 a7 3f 60 f0 50 4d e9 3b 5b 84 5e 27 55 92 c1 23 35 ee 34 0b bc 4f
dd d5 02 78 40 16 e4 b3 be 7e f0 4d da 49 f4 b4 40 a3 0c b5 d2 af 93 98
28 fd 4a e3 79 4e 44 f9 4d f5 a6 31 ed e4 2c 17 19 bf da bf 02 53 fe 51
75 be 89 8e 75 0e dc 53 37 0d 2b""")
    REC_CFIN = H("""17 03 03 00 35 75 ec 4d c2 38 cc e6 0b 29 80 44 a7 1e 21 9c
56 cc 77 b0 51 7f e9 b9 3c 7a 4b fc 44 d8 7f 38 f8 03 38 ac 98 fc 46 de
b3 84 bd 1c ae ac ab 68 67 d7 26 c4 05 46""")
    REC_NST = H("""17 03 03 00 de 3a 6b 8f 90 41 4a 97 d6 95 9c 34 87 68 0d e5 13
4a 2b 24 0e 6c ff ac 11 6e 95 d4 1d 6a f8 f6 b5 80 dc f3 d1 1d 63 c7 58
db 28 9a 01 59 40 25 2f 55 71 3e 06 1d c1 3e 07 88 91 a3 8e fb cf 57 53
ad 8e f1 70 ad 3c 73 53 d1 6d 9d a7 73 b9 ca 7f 2b 9f a1 b6 c0 d4 a3 d0
3f 75 e0 9c 30 ba 1e 62 97 2a c4 6f 75 f7 b9 81 be 63 43 9b 29 99 ce 13
06 46 15 13 98 91 d5 e4 c5 b4 06 f1 6e 3f c1 81 a7 7c a4 75 84 00 25 db
2f 0a 77 f8 1b 5a b0 5b 94 c0 13 46 75 5f 69 23 2c 86 51 9d 86 cb ee ac
87 aa c3 47 d1 43 f9 60 5d 64 f6 50 db 4d 02 3e 70 e9 52 ca 49 fe 51 37
12 1c 74 bc 26 97 68 7e 24 87 46 d6 df 35 30 05 f3 bc e1 86 96 12 9c 81
53 55 6b 3b 6c 67 79 b3 7b f1 59 85 68 4f""")
    REC_CAPP = H("""17 03 03 00 43 a2 3f 70 54 b6 2c 94 d0 af fa fe 82 28 ba 55
cb ef ac ea 42 f9 14 aa 66 bc ab 3f 2b 98 19 a8 a5 b4 6b 39 5b d5 4a 9a
20 44 1e 2b 62 97 4e 1f 5a 62 92 a2 97 70 14 bd 1e 3d ea e6 3a ee bb 21
69 49 15 e4""")
    REC_SAPP = H("""17 03 03 00 43 2e 93 7e 11 ef 4a c7 40 e5 38 ad 36 00 5f c4
a4 69 32 fc 32 25 d0 5f 82 aa 1b 36 e3 0e fa f9 7d 90 e6 df fc 60 2d cb
50 1a 59 a8 fc c4 9c 4b f2 e5 f0 a2 1c 00 47 c2 ab f3 32 54 0d d0 32 e1
67 c2 95 5d""")
    REC_CALERT = H("17 03 03 00 13 c9 87 27 60 65 56 66 b7 4d 7f f1 15 3e fd 6d b6 d0 b0 e3")
    REC_SALERT = H("17 03 03 00 13 b5 8f d6 71 66 eb f5 99 d2 47 20 cf be 7e fa 7a 88 64 a9")
    P = dict(
        ecdhe=H("8b d4 05 4f b5 5b 9d 63 fd fb ac f9 f0 4b 9f 0d 35 e6 d6 3f 53 75 63 ef d4 62 72 90 0f 89 49 2d"),
        early=H("33 ad 0a 1c 60 7e c0 3b 09 e6 cd 98 93 68 0c e2 10 ad f3 00 aa 1f 26 60 e1 b2 2e 10 f1 70 f9 2a"),
        derived1=H("6f 26 15 a1 08 c7 02 c5 67 8f 54 fc 9d ba b6 97 16 c0 76 18 9c 48 25 0c eb ea c3 57 6c 36 11 ba"),
        hs=H("1d c8 26 e9 36 06 aa 6f dc 0a ad c1 2f 74 1b 01 04 6a a6 b9 9f 69 1e d2 21 a9 f0 ca 04 3f be ac"),
        th_sh=H("86 0c 06 ed c0 78 58 ee 8e 78 f0 e7 42 8c 58 ed d6 b4 3f 2c a3 e6 e9 5f 02 ed 06 3c f0 e1 ca d8"),
        c_hs=H("b3 ed db 12 6e 06 7f 35 a7 80 b3 ab f4 5e 2d 8f 3b 1a 95 07 38 f5 2e 96 00 74 6a 0e 27 a5 5a 21"),
        s_hs=H("b6 7b 7d 69 0c c1 6c 4e 75 e5 42 13 cb 2d 37 b4 e9 c9 12 bc de d9 10 5d 42 be fd 59 d3 91 ad 38"),
        derived2=H("43 de 77 e0 c7 77 13 85 9a 94 4d b9 db 25 90 b5 31 90 a6 5b 3e e2 e4 f1 2d d7 a0 bb 7c e2 54 b4"),
        master=H("18 df 06 84 3d 13 a0 8b f2 a4 49 84 4c 5f 8a 47 80 01 bc 4d 4c 62 79 84 d5 a4 1d a8 d0 40 29 19"),
        th_sf=H("96 08 10 2a 0f 1c cc 6d b6 25 0b 7b 7e 41 7b 1a 00 0e aa da 3d aa e4 77 7a 76 86 c9 ff 83 df 13"),
        c_ap=H("9e 40 64 6c e7 9a 7f 9d c0 5a f8 88 9b ce 65 52 87 5a fa 0b 06 df 00 87 f7 92 eb b7 c1 75 04 a5"),
        s_ap=H("a1 1a f9 f0 55 31 f8 56 ad 47 11 6b 45 a9 50 32 82 04 b4 f4 4b fb 6b 3a 4b 4f 1f 3f cb 63 16 43"),
        s_hs_key=H("3f ce 51 60 09 c2 17 27 d0 f2 e4 e8 6e e4 03 bc"),
        s_hs_iv=H("5d 31 3e b2 67 12 76 ee 13 00 0b 30"),
        c_hs_key=H("db fa a6 93 d1 76 2c 5b 66 6a f5 d9 50 25 8d 01"),
        c_hs_iv=H("5b d3 c7 1b 83 6e 0b 76 bb 73 26 5f"),
        s_ap_key=H("9f 02 28 3b 6c 9c 07 ef c2 6b b9 f2 ac 92 e3 56"),
        s_ap_iv=H("cf 78 2b 88 dd 83 54 9a ad f1 e9 84"),
        c_ap_key=H("17 42 2d da 59 6e d5 d9 ac d8 90 e3 c6 3f 50 51"),
        c_ap_iv=H("5b 78 92 3d ee 08 57 90 33 e5 23 d9"),
        s_finkey=H("00 8d 3b 66 f8 16 ea 55 9f 96 b5 37 e8 85 c3 1f c0 68 bf 49 2c 65 2f 01 f2 88 a1 d8 cd c1 9f c8"),
        c_finkey=H("b8 0a d0 10 15 fb 2f 0b d6 5f f7 d4 da 5d 6b f8 3f 84 82 1d 1f 87 fd c7 d3 c7 5b 5a 7b 42 d9 c4"),
    )

    def hk_extract(salt, ikm):
        return hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()

    def hk_expand(prk, info, n):
        out, t, i = b"", b"", 1
        while len(out) < n:
            t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
            out += t
            i += 1
        return out[:n]

    def expand_label(secret, label, ctx, n):
        full = b"tls13 " + label
        return hk_expand(secret, n.to_bytes(2, "big") + bytes([len(full)]) + full + bytes([len(ctx)]) + ctx, n)

    def sha(x):
        return hashlib.sha256(x).digest()

    def keyiv(secret):
        return expand_label(secret, b"key", b"", 16), expand_label(secret, b"iv", b"", 12)

    def nonce(iv, seq):
        return bytes(a ^ b for a, b in zip(iv, seq.to_bytes(12, "big")))

    def protect(key, iv, seq, ctype, plain, pad=0):
        inner = plain + bytes([ctype]) + b"\x00" * pad
        aad = bytes([23, 3, 3]) + (len(inner) + 16).to_bytes(2, "big")
        return aad + gcm_seal(key, nonce(iv, seq), inner, aad)

    def unprotect(key, iv, seq, rec):
        inner = gcm_open(key, nonce(iv, seq), rec[5:], rec[:5])
        i = len(inner) - 1
        while i >= 0 and inner[i] == 0:
            i -= 1
        return inner[i], inner[:i]

    fails = []

    def must(name, got, want):
        if got != want:
            fails.append("%s: got %s want %s" % (name, got.hex(), want.hex()))

    ecv = _load_ecv()
    ecv.anchor()
    must("x25519 client public", ecv.x25519(CLIENT_PRIV, (9).to_bytes(32, "little")), CLIENT_PUB)
    Z = ecv.x25519(CLIENT_PRIV, SERVER_PUB)
    must("ecdhe", Z, P["ecdhe"])
    EMPTYH = sha(b"")
    th_sh = sha(CH + SH)
    th_cert = sha(CH + SH + EE + CERT)
    th_cv = sha(CH + SH + EE + CERT + CV)
    th_sf = sha(CH + SH + EE + CERT + CV + SFIN)
    must("th CH..SH", th_sh, P["th_sh"])
    must("th CH..SF", th_sf, P["th_sf"])
    early = hk_extract(b"", bytes(32))
    must("early", early, P["early"])
    d1 = expand_label(early, b"derived", EMPTYH, 32)
    must("derived1", d1, P["derived1"])
    hs = hk_extract(d1, Z)
    must("hs", hs, P["hs"])
    c_hs = expand_label(hs, b"c hs traffic", th_sh, 32)
    s_hs = expand_label(hs, b"s hs traffic", th_sh, 32)
    must("c hs", c_hs, P["c_hs"])
    must("s hs", s_hs, P["s_hs"])
    d2 = expand_label(hs, b"derived", EMPTYH, 32)
    must("derived2", d2, P["derived2"])
    master = hk_extract(d2, bytes(32))
    must("master", master, P["master"])
    c_ap = expand_label(master, b"c ap traffic", th_sf, 32)
    s_ap = expand_label(master, b"s ap traffic", th_sf, 32)
    must("c ap", c_ap, P["c_ap"])
    must("s ap", s_ap, P["s_ap"])
    s_hs_k, s_hs_iv = keyiv(s_hs)
    c_hs_k, c_hs_iv = keyiv(c_hs)
    s_ap_k, s_ap_iv = keyiv(s_ap)
    c_ap_k, c_ap_iv = keyiv(c_ap)
    for nm, g, w in (("s hs key", s_hs_k, "s_hs_key"), ("s hs iv", s_hs_iv, "s_hs_iv"),
                     ("c hs key", c_hs_k, "c_hs_key"), ("c hs iv", c_hs_iv, "c_hs_iv"),
                     ("s ap key", s_ap_k, "s_ap_key"), ("s ap iv", s_ap_iv, "s_ap_iv"),
                     ("c ap key", c_ap_k, "c_ap_key"), ("c ap iv", c_ap_iv, "c_ap_iv")):
        must(nm, g, P[w])
    s_fk = expand_label(s_hs, b"finished", b"", 32)
    c_fk = expand_label(c_hs, b"finished", b"", 32)
    must("s finkey", s_fk, P["s_finkey"])
    must("c finkey", c_fk, P["c_finkey"])
    must("server Finished", b"\x14\x00\x00\x20" + hmac.new(s_fk, th_cv, hashlib.sha256).digest(), SFIN)
    must("client Finished", b"\x14\x00\x00\x20" + hmac.new(c_fk, th_sf, hashlib.sha256).digest(), CFIN)
    FLIGHT_PT = EE + CERT + CV + SFIN
    # THE GCM ORACLE'S ANCHOR: all eight published protected records
    must("flight record", protect(s_hs_k, s_hs_iv, 0, 22, FLIGHT_PT), REC_FLIGHT)
    must("SH record", b"\x16\x03\x03" + len(SH).to_bytes(2, "big") + SH, REC_SH)
    must("client Finished record", protect(c_hs_k, c_hs_iv, 0, 22, CFIN), REC_CFIN)
    must("NST record", protect(s_ap_k, s_ap_iv, 0, 22, NST), REC_NST)
    must("client appdata record", protect(c_ap_k, c_ap_iv, 0, 23, APPDATA), REC_CAPP)
    must("server appdata record", protect(s_ap_k, s_ap_iv, 1, 23, APPDATA), REC_SAPP)
    must("client alert record", protect(c_ap_k, c_ap_iv, 1, 21, ALERT_CLOSE), REC_CALERT)
    must("server alert record", protect(s_ap_k, s_ap_iv, 2, 21, ALERT_CLOSE), REC_SALERT)
    CV_CTX = b"\x20" * 64 + b"TLS 1.3, server CertificateVerify" + b"\x00"
    CV_MSGHASH = sha(CV_CTX + th_cert)
    CERT_DER = CERT[11:11 + int.from_bytes(CERT[8:11], "big")]
    ANCHOR_DN = H("30 0e 31 0c 30 0a 06 03 55 04 03 13 03 72 73 61")
    ANCHOR_N = CERT_DER[CERT_DER.index(H("02 81 81 00")) + 4:][:128]
    ANCHOR_E = H("01 00 01")
    if ANCHOR_DN not in CERT_DER:
        fails.append("anchor DN not inside the certificate")

    def reseal(pt):
        return protect(s_hs_k, s_hs_iv, 0, 22, pt)

    def flip(buf, off, mask=0x01):
        b = bytearray(buf)
        b[off] ^= mask
        return bytes(b)

    OFF_CERT = len(EE)
    OFF_CV = len(EE) + len(CERT)
    OFF_SFIN = OFF_CV + len(CV)
    NEG_TAG = flip(REC_FLIGHT, 40)
    NEG_CV = reseal(flip(FLIGHT_PT, OFF_CV + 12))
    _pt = bytearray(FLIGHT_PT)
    _pt[OFF_CV + 4] = 0x04
    _pt[OFF_CV + 5] = 0x01
    NEG_CVALG = reseal(bytes(_pt))
    NEG_FIN = reseal(flip(FLIGHT_PT, OFF_SFIN + 10))
    NEG_CERT = reseal(flip(FLIGHT_PT, FLIGHT_PT.index(ANCHOR_N, OFF_CERT) + 5))

    def ee_plus(extra):
        e = bytearray(EE)
        e[4:6] = (int.from_bytes(EE[4:6], "big") + len(extra)).to_bytes(2, "big")
        e[1:4] = (int.from_bytes(EE[1:4], "big") + len(extra)).to_bytes(3, "big")
        return bytes(e) + extra
    NEG_EARLY = reseal(ee_plus(H("00 2a 00 00")) + CERT + CV + SFIN)
    c = bytearray(CERT)
    c[-2:] = H("00 04")
    c = bytearray(bytes(c) + H("00 05 00 00"))
    c[1:4] = (len(c) - 4).to_bytes(3, "big")
    c[5:8] = (len(c) - 8).to_bytes(3, "big")
    NEG_CERTEXT = reseal(EE + bytes(c) + CV + SFIN)
    NEG_UNOFFERED = reseal(ee_plus(H("00 10 00 04 00 02 01 68")) + CERT + CV + SFIN)
    NEG_EEKEYSHARE = reseal(ee_plus(H("00 33 00 04 00 1d 00 00")) + CERT + CV + SFIN)
    for nm, rec in (("NegCv", NEG_CV), ("NegCvalg", NEG_CVALG), ("NegFin", NEG_FIN),
                    ("NegCert", NEG_CERT), ("NegEarly", NEG_EARLY), ("NegCertext", NEG_CERTEXT),
                    ("NegUnoffered", NEG_UNOFFERED), ("NegEekeyshare", NEG_EEKEYSHARE)):
        ct, pt = unprotect(s_hs_k, s_hs_iv, 0, rec)
        if ct != 22 or pt == FLIGHT_PT or pt[0] != 8 or pt[-36] != 20:
            fails.append("negative flight %s is malformed" % nm)
    try:
        unprotect(s_hs_k, s_hs_iv, 0, NEG_TAG)
        fails.append("NegTag opened under the trace key - it must not")
    except Fail:
        pass

    P256_PRIV = H("1d 33 40 40 2b 47 66 0f 9b 22 3c 4a 4b b1 2e 6a 6e 71 55 89 8f 3c 21 f7 ba 5b 6c cf 2d 34 71 07")
    P256_PEER_PRIV = H("7f 05 9c 6b 8a 3d 21 e0 44 9b c2 15 6d 7e 30 88 12 4a f6 3b 90 5e 17 cc 2b d8 41 09 e3 76 5a 22")
    a_, b_ = int.from_bytes(P256_PRIV, "big"), int.from_bytes(P256_PEER_PRIV, "big")
    P256_PUB = ecv.enc_point(ecv.pt_mul(a_, ecv.G))
    P256_PEER_PUB = ecv.enc_point(ecv.pt_mul(b_, ecv.G))
    s1 = ecv.pt_mul(a_, ecv.pt_mul(b_, ecv.G))
    if s1 != ecv.pt_mul(b_, ecv.pt_mul(a_, ecv.G)):
        fails.append("P-256 ECDH does not agree both ways")
    P256_SHARED = s1[0].to_bytes(32, "big")

    s_ap2 = expand_label(s_ap, b"traffic upd", b"", 32)
    c_ap2 = expand_label(c_ap, b"traffic upd", b"", 32)
    s_ap2_k, s_ap2_iv = keyiv(s_ap2)
    c_ap2_k, c_ap2_iv = keyiv(c_ap2)

    def sh_record(body):
        return b"\x16\x03\x03" + len(body).to_bytes(2, "big") + body
    HRR_RANDOM = H("cf 21 ad 74 e5 9a 61 11 be 1d 8c 02 1e 65 b8 91 c2 a2 11 16 7a bb 8c 5e 07 9e 09 e2 c8 a8 33 9c")
    s = bytearray(SH)
    s[6:38] = HRR_RANDOM
    SH_HRR = sh_record(bytes(s))
    s = bytearray(SH)
    s[30:38] = b"DOWNGRD\x01"
    SH_DOWNGRADE = sh_record(bytes(s))
    s = bytearray(SH)
    s[39:41] = H("13 02")
    SH_BADSUITE = sh_record(bytes(s))
    s = bytearray(SH)
    s[41] = 0x01
    SH_COMPRESS = sh_record(bytes(s))
    s = bytearray(SH)
    s[-2:] = H("03 03")
    SH_BADVER = sh_record(bytes(s))
    SH_BADLEGACY = sh_record(H("02 00 00 56 04 03") + SH[6:])
    ext = H("00 2b 00 02 03 04")
    body = SH[4:6 + 32] + b"\x00" + H("13 01") + b"\x00" + len(ext).to_bytes(2, "big") + ext
    SH_NOKS = sh_record(b"\x02" + len(body).to_bytes(3, "big") + body)
    extblock = SH[44:] + H("00 29 00 02 00 00")
    body = SH[4:42] + len(extblock).to_bytes(2, "big") + extblock
    SH_PSK = sh_record(b"\x02" + len(body).to_bytes(3, "big") + body)
    body = SH[4:38] + b"\x04\xde\xad\xbe\xef" + SH[39:]
    SH_SIDECHO = sh_record(b"\x02" + len(body).to_bytes(3, "big") + body)

    aad = bytes([23, 3, 3]) + (4 + 16).to_bytes(2, "big")
    NEG_ZEROPAD = aad + gcm_seal(s_hs_k, nonce(s_hs_iv, 0), b"\x00" * 4, aad)
    PADDED_FLIGHT = protect(s_hs_k, s_hs_iv, 0, 22, FLIGHT_PT, 23)
    ct, pt = unprotect(s_hs_k, s_hs_iv, 0, PADDED_FLIGHT)
    if ct != 22 or pt != FLIGHT_PT:
        fails.append("padded flight does not round-trip")
    BIGSEQ_NONCE = nonce(s_hs_iv, 0x0102030405060708)
    # THE 64-BIT CARRY (Pi 4 port change 2): the records at sequence
    # 2^32 - 1 and 2^32, and the AEAD nonce at 2^32.
    SEQ_LO_MAX = protect(c_ap_k, c_ap_iv, 0xFFFFFFFF, 23, APPDATA)
    SEQ_CARRY = protect(c_ap_k, c_ap_iv, 0x100000000, 23, APPDATA)
    SEQ_LO_MAX_READ = protect(s_ap_k, s_ap_iv, 0xFFFFFFFF, 23, APPDATA)
    SEQ_CARRY_READ = protect(s_ap_k, s_ap_iv, 0x100000000, 23, APPDATA)

    if fails:
        raise SystemExit("RFC 8448 ANCHOR MISMATCH - nothing was run:\n  " + "\n  ".join(fails))

    V.update(dict(
        Ch=CH, ShRec=REC_SH, Flight=REC_FLIGHT, NstRec=REC_NST, SappRec=REC_SAPP,
        SalertRec=REC_SALERT, CfinRec=REC_CFIN, CappRec=REC_CAPP, CalertRec=REC_CALERT,
        Cpriv=CLIENT_PRIV, Cpub=CLIENT_PUB, Ecdhe=P["ecdhe"], Early=P["early"],
        Derived1=P["derived1"], Hs=P["hs"], Chs=P["c_hs"], Shs=P["s_hs"],
        Derived2=P["derived2"], Master=P["master"], Cap=P["c_ap"], Sap=P["s_ap"],
        ThSh=th_sh, ThCert=th_cert, ThSf=th_sf, ShsKey=s_hs_k, ShsIv=s_hs_iv,
        ChsKey=c_hs_k, ChsIv=c_hs_iv, SapKey=s_ap_k, SapIv=s_ap_iv, CapKey=c_ap_k,
        CapIv=c_ap_iv, Appdata=APPDATA, AlertClose=ALERT_CLOSE, Nst=NST,
        FlightPt=FLIGHT_PT, Cfin=CFIN, CvMsgHash=CV_MSGHASH, EmptyHash=EMPTYH,
        AnchorDn=ANCHOR_DN, AnchorN=ANCHOR_N, AnchorE=ANCHOR_E,
        NegTag=NEG_TAG, NegCv=NEG_CV, NegCvalg=NEG_CVALG, NegFin=NEG_FIN,
        NegCert=NEG_CERT, NegEarly=NEG_EARLY, NegCertext=NEG_CERTEXT,
        NegZeropad=NEG_ZEROPAD, NegUnoffered=NEG_UNOFFERED, NegEekeyshare=NEG_EEKEYSHARE,
        P256Priv=P256_PRIV, P256Pub=P256_PUB, P256PeerPub=P256_PEER_PUB,
        P256Shared=P256_SHARED, P256Order=ecv.N.to_bytes(32, "big"),
        SapUpd=s_ap2, SapUpdKey=s_ap2_k, SapUpdIv=s_ap2_iv,
        CapUpd=c_ap2, CapUpdKey=c_ap2_k, CapUpdIv=c_ap2_iv,
        PaddedFlight=PADDED_FLIGHT, BigseqNonce=BIGSEQ_NONCE,
        SeqLoMax=SEQ_LO_MAX, SeqCarry=SEQ_CARRY, SeqCarryRead=SEQ_CARRY_READ, SeqLoMaxRead=SEQ_LO_MAX_READ,
        ShHrr=SH_HRR, ShDowngrade=SH_DOWNGRADE, ShBadsuite=SH_BADSUITE,
        ShCompress=SH_COMPRESS, ShBadver=SH_BADVER, ShBadlegacy=SH_BADLEGACY,
        ShNoks=SH_NOKS, ShPsk=SH_PSK, ShSidecho=SH_SIDECHO,
        DrbgSeed=bytes((i * 37 + 11) & 255 for i in range(48)),
    ))
    return V


# =====================================================================
#  THE HARNESS - a thin dispatcher over the library's own procedures
# =====================================================================
INCLUDES = """EnableExplicit
#X509_SIG_LINKED = 1
XIncludeFile "Anvil/Core/sha256.pbi"
XIncludeFile "RaspberryPi4/Lib/hmac.pi4"
XIncludeFile "RaspberryPi4/Lib/hkdf.pi4"
XIncludeFile "RaspberryPi4/Lib/entropy.pi4"
XIncludeFile "RaspberryPi4/Lib/drbg.pi4"
XIncludeFile "Anvil/Crypto/aes.pbi"
XIncludeFile "__GCM__"
XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
XIncludeFile "RaspberryPi4/Lib/x25519.pi4"
XIncludeFile "RaspberryPi4/Lib/ecdsa.pi4"
XIncludeFile "RaspberryPi4/Lib/rsa.pi4"
XIncludeFile "RaspberryPi4/Lib/t0vm.pi4"
XIncludeFile "RaspberryPi4/Lib/x509_blob.pi4"
XIncludeFile "RaspberryPi4/Lib/x509.pi4"
XIncludeFile "__REC__"
XIncludeFile "__HS__"
"""

HARNESS = r"""
; tls13 harness - GENERATED by tools/tls13_rfc8448_check.py. Not a source file.
#H_ARGS = $0A000000

Procedure.i HA(k.i)
  ProcedureReturn PeekI(#H_ARGS + (k << 3))
EndProcedure

; The state the RFC 8448 client was in after sending its ClientHello: the
; trace's private key written into the library's own global (there is no
; API that takes one), the transcript switched to the trace's ClientHello,
; no legacy session id, and the trace's seven offered extensions.
Procedure HSetupTail(priv.i, derive.i, ch.i, chLen.i)
  TlsCopy(@secTlsPriv[0], priv, 32)
  If derive <> 0
    Tls13DeriveKeySharePublic()
  EndIf
  Tls13TranscriptReset()
  Tls13TranscriptAbsorb(ch, chLen)
  TlsSessionIdLen = 0
  TlsOfferedCount = 0
  TlsNoteOffered(0)
  TlsNoteOffered(10)
  TlsNoteOffered(13)
  TlsNoteOffered(43)
  TlsNoteOffered(51)
  TlsNoteOffered(28)
  TlsNoteOffered(45)
  Tls13State = #TLS13_ST_WAIT_SH
EndProcedure

; A record as the SERVER would send it after the handshake: the server
; application key on the write side too, both sequence numbers zeroed.
Procedure.i HServerRecord(msg.i, len.i, dst.i, dstmax.i)
  TlsKeyIvFrom(@secTlsSAp[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])
  Tls13RecSetWriteKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])
  Tls13RecSetReadKey(@secTlsKeyBuf[0], @secTlsIvBuf[0])
  ProcedureReturn Tls13RecProtect(#TLS_CT_HANDSHAKE, msg, len, 0, dst, dstmax)
EndProcedure

Procedure.i Op(op.i)
  Protected r.i
  r = 0
  Select op
    Case 1
      Tls13RecReset()
    Case 2
      Tls13RecSetReadKey(HA(0), HA(1))
    Case 3
      Tls13RecSetWriteKey(HA(0), HA(1))
    Case 4
      r = Tls13RecUnprotect(HA(0), HA(1))
    Case 5
      r = Tls13RecProtect(HA(0), HA(1), HA(2), HA(3), HA(4), HA(5))
    Case 6
      TlsRecNonce(HA(0), HA(1), HA(2))
    Case 11
      X509ResetAnchors()
    Case 12
      X509AddAnchorRSA(HA(0), HA(1), HA(2), HA(3), HA(4), HA(5), HA(6))
    Case 13
      Tls13SetHsBuffer(HA(0), HA(1))
    Case 14
      r = Tls13SetGroup(HA(0))
    Case 15
      r = Tls13Init(HA(0), HA(1), HA(2))
    Case 16
      HSetupTail(HA(0), HA(1), HA(2), HA(3))
    Case 20
      r = Tls13FeedRecord(HA(0), HA(1))
    Case 21
      r = Tls13BuildClientFinished(HA(0), HA(1))
    Case 22
      r = Tls13BuildAppRecord(HA(0), HA(1), HA(2), HA(3))
    Case 23
      r = Tls13BuildAlert(HA(0), HA(1), HA(2), HA(3))
    Case 24
      r = Tls13BuildKeyUpdate(HA(0), HA(1), HA(2))
    Case 25
      r = Tls13BuildClientHello(HA(0), HA(1))
    Case 26
      r = Tls13NewKeyShare()
    Case 27
      r = Tls13DeriveKeySharePublic()
    Case 28
      r = TlsComputeEcdhe()
    Case 29
      r = TlsScalarBelowOrder()
    Case 30
      Tls13TranscriptHash(HA(0))
    Case 31
      Tls13SetRecvBuffer(HA(0), HA(1))
    Case 32
      r = Tls13FeedBytes(HA(0), HA(1))
    Case 33
      r = DrbgInit(HA(0), HA(1))
    Case 34
      r = HServerRecord(HA(0), HA(1), HA(2), HA(3))
    Case 35
      r = Tls13Connected()
    Case 40
      TlsKdfFault = 0
      TlsExpandLabel(@secTlsSAp[0], @TlsLbl[#TLS_L_UPD], #TLS_L_UPD_N, 0, 0, HA(0), HA(1))
      r = TlsKdfFault
  EndSelect
  ProcedureReturn r
EndProcedure

Procedure.i Main()
  ProcedureReturn Op(0)
EndProcedure
"""


def harness_text(rec_inc, hs_inc, gcm_inc):
    return (INCLUDES.replace("__REC__", rec_inc).replace("__HS__", hs_inc)
            .replace("__GCM__", gcm_inc) + HARNESS)


def build(compiler, work: Path, name, rec_inc="RaspberryPi4/Lib/tls13_record.pi4",
          hs_inc="RaspberryPi4/Lib/tls13_hs.pi4", gcm_inc="RaspberryPi4/Lib/gcm.pi4"):
    src, img = work / (name + ".pi4"), work / (name + ".img")
    src.write_text(harness_text(rec_inc, hs_inc, gcm_inc), encoding="utf-8")
    r = subprocess.run([str(compiler), "--compile", str(src), "-t", "pi4", "--entry-returns",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
                       cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    if r.returncode or "pmfc: OK" not in out or not img.exists():
        raise Fail("fixture compile failed\n" + out[-3000:])
    entry = None
    for line in Path(str(img) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        f = line.split("|")
        if len(f) >= 4 and f[0] == "1" and f[1].isdigit() and f[2].lower() == "op":
            entry = LOAD + int(f[1])
    if entry is None:
        raise Fail("fixture has no Op entry in its .dbg")
    syms = {}
    for line in Path(str(img) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"global_(\w+)=(\d+)$", line.strip())
        if m:
            syms[m.group(1)] = int(m.group(2))
    return str(img), entry, syms


# =====================================================================
#  THE MACHINE
# =====================================================================
_A64 = None


def _interp():
    global _A64
    if _A64 is not None:
        return _A64
    spec = importlib.util.spec_from_file_location("tls13_a64", ROOT / "tools" / "a64" / "a64_interp.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["tls13_a64"] = m
    spec.loader.exec_module(m)
    _A64 = m
    return m


class Machine:
    def __init__(self, product, V):
        img, self.entry, self.syms = product
        A = _interp()
        self.cpu = A.A64()
        blob = Path(img).read_bytes()
        self.cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
        self.steps = 0
        self.V = V
        self.addr = {}
        p = H_DATA
        for k, v in V.items():
            self.addr[k] = p
            self.put_at(p, v)
            p += (len(v) + 15) & ~15

    # -- memory --
    def put_at(self, a, data):
        for i, b in enumerate(data):
            self.cpu.memory[a + i] = b

    def get_at(self, a, n):
        return bytes(self.cpu.memory.get(a + i, 0) for i in range(n))

    def sym(self, name):
        key = name.lower()
        if key not in self.syms:
            raise Fail("global %s is not in the image's .sym" % name)
        return self.syms[key]

    def g(self, name):
        v = int.from_bytes(self.get_at(self.sym(name), 8), "little")
        return v - (1 << 64) if v >> 63 else v

    def gb(self, name, n):
        return self.get_at(self.sym(name), n)

    def setg(self, name, value):
        self.put_at(self.sym(name), (value & MASK64).to_bytes(8, "little"))

    def setgb(self, name, data):
        self.put_at(self.sym(name), data)

    def load(self, key, at):
        self.put_at(at, self.V[key])
        return len(self.V[key])

    def snapshot(self):
        return dict(self.cpu.memory)

    def restore(self, snap):
        self.cpu.memory = dict(snap)

    # -- calls --
    def op(self, code, *args):
        for i, a in enumerate(args):
            self.put_at(H_ARGS + 8 * i, (a & MASK64).to_bytes(8, "little"))
        cpu = self.cpu
        cpu.pc, cpu.sp, cpu.x[30], cpu.x[0] = self.entry, STACK, RETURN, code
        n = 0
        while cpu.pc != RETURN:
            cpu.step()
            n += 1
            if n > STEP_LIMIT:
                raise Fail("Op(%d) did not return in %d model instructions" % (code, n))
        self.steps += n
        v = cpu.x[0] & MASK64
        return v - (1 << 64) if v >> 63 else v


# =====================================================================
#  THE CHECKS - one list per job, each entry a named result
# =====================================================================
C = dict(  # library constants the checks name (values are the library's)
    CT_CCS=20, CT_ALERT=21, CT_HS=22, CT_APP=23, MAX_PT=16384,
    REC_OK=0, NO_KEY=1, TOO_LONG=2, SEQ_OVERFLOW=3, BAD_TAG=4, SHORT=5, ALL_ZERO=6,
    BAD_OUTER=7, BUF_SMALL=8, LEN_MISMATCH=9,
    ST_WAIT_SH=2, ST_WAIT_EE=3, ST_SEND_FIN=7, ST_CONNECTED=8, ST_CLOSED=9, ST_FAILED=10,
    X25519=0x1D, P256=0x17,
)
R = dict(  # the #TLS13_REFUSE_* table
    OK=0, NO_TIME=1, NO_ANCHORS=2, BAD_GROUP=3, BUF_TOO_SMALL=4, KEYGEN_FAILED=7, KDF_FAILED=9,
    RECORD_LEN_MISMATCH=19, PLAINTEXT_AFTER_KEYS=15, UNEXPECTED_CCS=16, BAD_CCS_VALUE=17,
    BAD_RECORD_MAC=12, UNEXPECTED_MESSAGE=22, EMPTY_HANDSHAKE_RECORD=24,
    MESSAGE_HASH_SYNTHETIC=25, SH_LEGACY_VERSION=30, HELLO_RETRY_REQUEST=31,
    DOWNGRADE_SENTINEL=32, SESSION_ID_ECHO=33, CIPHER_SUITE=34, COMPRESSION_METHOD=35,
    NOT_TLS13=37, NO_KEY_SHARE=38, PSK_OFFERED=41, EARLY_DATA_ACCEPTED=50,
    UNOFFERED_EXTENSION=51, EXT_NOT_ALLOWED_HERE=52, CERT_EXTENSION_UNSOLICITED=63,
    CHAIN_INVALID=64, SIGALG_PKCS1_IN_CV=71, SIGNATURE_INVALID=73, FINISHED_MISMATCH=81,
    CLIENT_AUTH_REQUESTED=90, KEY_UPDATE_BAD_REQUEST=92, KEY_UPDATE_LENGTH=93,
    POST_HS_UNKNOWN=94,
)
X509ERR = dict(OK=32, EXPIRED=54, BAD_SERVER_NAME=56, NOT_TRUSTED=62)
ALERT = dict(CLOSE_NOTIFY=0, BAD_CERTIFICATE=42, CERTIFICATE_EXPIRED=45, UNKNOWN_CA=48,
             LEVEL_WARNING=1, LEVEL_FATAL=2)


class Checks:
    def __init__(self, job, stop=False):
        self.job = job
        self.results = []
        self.stop = stop

    def _add(self, label, ok, why):
        self.results.append((self.job + ": " + label, ok, why))
        if self.stop and not ok:
            raise Fail("stopped at the first failure")

    def eq(self, label, got, want):
        self._add(label, got == want, "" if got == want else "got %r want %r" % (got, want))

    def cmp(self, label, got, want):
        ok = got == want
        why = ""
        if not ok:
            i = next((k for k in range(min(len(got), len(want))) if got[k] != want[k]), min(len(got), len(want)))
            why = "first difference at byte %d: got %s want %s" % (i, got[i:i + 8].hex(), want[i:i + 8].hex())
        self._add(label, ok, why)

    def true(self, label, cond, detail=""):
        self._add(label, bool(cond), "" if cond else detail)


def setup_trace(m, name_len=3, unix=TIME_OK, derive=0):
    m.op(11)
    m.op(12, 0, m.addr["AnchorDn"], len(m.V["AnchorDn"]), m.addr["AnchorN"], len(m.V["AnchorN"]),
         m.addr["AnchorE"], len(m.V["AnchorE"]))
    m.op(13, HSBUF, HSBUF_N)
    m.op(14, C["X25519"])
    m.op(15, NAME, name_len, unix)
    m.op(16, m.addr["Cpriv"], derive, m.addr["Ch"], len(m.V["Ch"]))


def feed(m, key, n=None):
    ln = m.load(key, REC)
    return m.op(20, REC, ln if n is None else n)


def to_server_hello(m):
    setup_trace(m)
    return feed(m, "ShRec")


# ---------------------------------------------------------------- T1
def job_record(m, k):
    V = m.V
    m.load("ShsIv", TMP)
    m.op(6, TMP, 0, 0)
    k.cmp("nonce at sequence 0 is the iv", m.gb("TlsNonce", 12), V["ShsIv"])
    m.op(6, TMP, 0x01020304, 0x05060708)
    k.cmp("nonce right-aligned at a two-word sequence number", m.gb("TlsNonce", 12), V["BigseqNonce"])

    m.load("ShsKey", TMP)
    m.load("ShsIv", TMP + 16)
    m.op(1)
    m.op(2, TMP, TMP + 16)
    n = feed_unprotect(m, "Flight")
    k.eq("server flight opens to its plaintext length", n, len(V["FlightPt"]))
    k.eq("outer type on the wire is application_data", m.get_at(REC, 1)[0], C["CT_APP"])
    k.eq("recovered inner type is handshake", m.g("TlsRecInnerType"), C["CT_HS"])
    k.cmp("server flight plaintext", m.get_at(REC + 5, n if n > 0 else 0), V["FlightPt"])
    k.eq("accepting a record advances the read sequence (lo)", m.g("TlsRSeqLo"), 1)
    k.eq("read sequence (hi)", m.g("TlsRSeqHi"), 0)

    m.op(3, TMP, TMP + 16)
    m.load("FlightPt", EXP)
    n = m.op(5, C["CT_HS"], EXP, len(V["FlightPt"]), 0, OUT, 768)
    k.eq("sealing the flight gives the published length", n, len(V["Flight"]))
    k.cmp("sealed flight is the published record", m.get_at(OUT, len(V["Flight"])), V["Flight"])
    k.eq("write sequence steps", m.g("TlsWSeqLo"), 1)

    m.op(2, TMP, TMP + 16)
    n = feed_unprotect(m, "PaddedFlight")
    k.eq("23-byte padded flight opens to the same length", n, len(V["FlightPt"]))
    k.eq("padded flight inner type", m.g("TlsRecInnerType"), C["CT_HS"])
    k.cmp("padded flight plaintext", m.get_at(REC + 5, len(V["FlightPt"])), V["FlightPt"])
    m.op(3, TMP, TMP + 16)
    n = m.op(5, C["CT_HS"], EXP, len(V["FlightPt"]), 23, OUT, 768)
    k.eq("own padding: length", n, len(V["PaddedFlight"]))
    k.cmp("own padding: bytes", m.get_at(OUT, len(V["PaddedFlight"])), V["PaddedFlight"])

    m.op(2, TMP, TMP + 16)
    k.eq("tampered ciphertext refused", feed_unprotect(m, "NegTag"), -1)
    k.eq("tampered ciphertext: named BAD_TAG", m.g("Tls13RecErr"), C["BAD_TAG"])
    k.eq("a refused record does not advance the sequence", m.g("TlsRSeqLo"), 0)
    m.op(2, TMP, TMP + 16)
    k.eq("all-zero inner plaintext refused", feed_unprotect(m, "NegZeropad"), -1)
    k.eq("all-zero inner: named ALL_ZERO_INNER", m.g("Tls13RecErr"), C["ALL_ZERO"])
    m.op(2, TMP, TMP + 16)
    m.load("Flight", REC)
    m.put_at(REC, bytes([C["CT_HS"]]))
    k.eq("protected record not labelled application_data refused", m.op(4, REC, len(V["Flight"])), -1)
    k.eq("named BAD_OUTER_TYPE", m.g("Tls13RecErr"), C["BAD_OUTER"])
    m.load("Flight", REC)
    k.eq("header length disagreeing with the bytes refused", m.op(4, REC, len(V["Flight"]) - 1), -1)
    k.eq("named LEN_MISMATCH", m.g("Tls13RecErr"), C["LEN_MISMATCH"])
    k.eq("record too short for a tag refused", m.op(4, REC, 6), -1)
    k.eq("named SHORT_RECORD", m.g("Tls13RecErr"), C["SHORT"])
    k.eq("plaintext over 2^14 refused before any crypto", m.op(5, C["CT_APP"], EXP, C["MAX_PT"] + 1, 0, OUT, 768), 0)
    k.eq("named TOO_LONG", m.g("Tls13RecErr"), C["TOO_LONG"])
    k.eq("output buffer too small refused", m.op(5, C["CT_APP"], EXP, 100, 0, OUT, 50), 0)
    k.eq("named BUF_TOO_SMALL", m.g("Tls13RecErr"), C["BUF_SMALL"])
    m.op(1)
    k.eq("unkeyed protect refused", m.op(5, C["CT_APP"], EXP, 4, 0, OUT, 768), 0)
    k.eq("unkeyed protect: NO_KEY", m.g("Tls13RecErr"), C["NO_KEY"])
    k.eq("unkeyed unprotect refused", m.op(4, REC, len(V["Flight"])), -1)
    k.eq("unkeyed unprotect: NO_KEY", m.g("Tls13RecErr"), C["NO_KEY"])

    m.load("SapKey", TMP)
    m.load("SapIv", TMP + 16)
    m.op(1)
    m.op(2, TMP, TMP + 16)
    k.eq("NST record at read sequence 0", feed_unprotect(m, "NstRec"), len(V["Nst"]))
    k.eq("NST inner type", m.g("TlsRecInnerType"), C["CT_HS"])
    k.cmp("NST plaintext", m.get_at(REC + 5, len(V["Nst"])), V["Nst"])
    k.eq("server appdata at read sequence 1", feed_unprotect(m, "SappRec"), len(V["Appdata"]))
    k.eq("server appdata inner type", m.g("TlsRecInnerType"), C["CT_APP"])
    k.cmp("server appdata plaintext", m.get_at(REC + 5, len(V["Appdata"])), V["Appdata"])
    k.eq("server close_notify at read sequence 2", feed_unprotect(m, "SalertRec"), 2)
    k.eq("server alert inner type", m.g("TlsRecInnerType"), C["CT_ALERT"])
    k.eq("read sequence after three records", m.g("TlsRSeqLo"), 3)

    m.load("CapKey", TMP)
    m.load("CapIv", TMP + 16)
    m.op(1)
    m.op(3, TMP, TMP + 16)
    m.load("Appdata", EXP)
    k.eq("client appdata length", m.op(5, C["CT_APP"], EXP, len(V["Appdata"]), 0, OUT, 768), len(V["CappRec"]))
    k.cmp("client appdata record", m.get_at(OUT, len(V["CappRec"])), V["CappRec"])
    m.load("AlertClose", EXP)
    k.eq("client close_notify length", m.op(5, C["CT_ALERT"], EXP, 2, 0, OUT, 768), len(V["CalertRec"]))
    k.cmp("client close_notify record", m.get_at(OUT, len(V["CalertRec"])), V["CalertRec"])

    m.load("ChsKey", TMP)
    m.load("ChsIv", TMP + 16)
    m.op(1)
    m.op(3, TMP, TMP + 16)
    m.load("Cfin", EXP)
    k.eq("client Finished record length", m.op(5, C["CT_HS"], EXP, len(V["Cfin"]), 0, OUT, 768), len(V["CfinRec"]))
    k.cmp("client Finished record", m.get_at(OUT, len(V["CfinRec"])), V["CfinRec"])

    # ---- Pi 4 port change 2: the 64-bit sequence number carry ----
    m.load("CapKey", TMP)
    m.load("CapIv", TMP + 16)
    m.op(1)
    m.op(3, TMP, TMP + 16)
    m.setg("TlsWSeqLo", 0xFFFFFFFF)
    m.setg("TlsWSeqHi", 0)
    m.load("Appdata", EXP)
    m.op(5, C["CT_APP"], EXP, len(V["Appdata"]), 0, OUT, 768)
    k.cmp("record at write sequence 2^32-1", m.get_at(OUT, len(V["SeqLoMax"])), V["SeqLoMax"])
    k.eq("low half wraps to 0 (carry, not 2^32)", m.g("TlsWSeqLo"), 0)
    k.eq("carry lands in the high half", m.g("TlsWSeqHi"), 1)
    m.op(5, C["CT_APP"], EXP, len(V["Appdata"]), 0, OUT, 768)
    k.cmp("record at write sequence 2^32 (nonce from the high half)", m.get_at(OUT, len(V["SeqCarry"])), V["SeqCarry"])
    m.load("SapKey", TMP)
    m.load("SapIv", TMP + 16)
    m.op(2, TMP, TMP + 16)
    m.setg("TlsRSeqLo", 0xFFFFFFFF)
    m.setg("TlsRSeqHi", 0)
    k.eq("read side opens the record at sequence 2^32-1", feed_unprotect(m, "SeqLoMaxRead"), len(V["Appdata"]))
    k.eq("read low half wraps to 0", m.g("TlsRSeqLo"), 0)
    k.eq("read carry lands in the high half", m.g("TlsRSeqHi"), 1)
    k.eq("read side opens the record at sequence 2^32", feed_unprotect(m, "SeqCarryRead"), len(V["Appdata"]))
    # ---- the overflow refusal at 2^64 - 1, both directions. A record
    #      sealed at 2^64-2 opens; the one sealed at 2^64-1 is refused on
    #      the write side (the counter would wrap) and, fed back to a read
    #      side standing at 2^64-1, refused there for the same reason.
    m.op(3, TMP, TMP + 16)
    m.setg("TlsWSeqLo", 0xFFFFFFFE)
    m.setg("TlsWSeqHi", 0xFFFFFFFF)
    m.setg("TlsRSeqLo", 0xFFFFFFFE)
    m.setg("TlsRSeqHi", 0xFFFFFFFF)
    m.load("Appdata", EXP)
    n = m.op(5, C["CT_APP"], EXP, 4, 0, OUT, 768)
    k.eq("write at 2^64-2 accepted", n, 5 + 4 + 1 + 16)
    k.eq("read at 2^64-2 accepted", m.op(4, OUT, 5 + 4 + 1 + 16), 4)
    k.eq("both counters now all ones", (m.g("TlsWSeqLo"), m.g("TlsWSeqHi"), m.g("TlsRSeqLo"), m.g("TlsRSeqHi")),
         (0xFFFFFFFF,) * 4)
    k.eq("write at 2^64-1 refused (no wrap)", m.op(5, C["CT_APP"], EXP, 4, 0, OUT, 768), 0)
    k.eq("write: named SEQ_OVERFLOW", m.g("Tls13RecErr"), C["SEQ_OVERFLOW"])
    k.eq("write counter did not wrap", (m.g("TlsWSeqLo"), m.g("TlsWSeqHi")), (0xFFFFFFFF, 0xFFFFFFFF))
    k.eq("read at 2^64-1 refused (no wrap)", m.op(4, OUT, 5 + 4 + 1 + 16), -1)
    k.eq("read: named SEQ_OVERFLOW", m.g("Tls13RecErr"), C["SEQ_OVERFLOW"])


def feed_unprotect(m, key):
    ln = m.load(key, REC)
    return m.op(4, REC, ln)


# ---------------------------------------------------------------- T2 + T7
def job_handshake(m, k):
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m, derive=1)
    k.eq("setup: no error", m.g("Tls13Err"), R["OK"])
    k.eq("key share length", m.g("TlsKeyShareLen"), 32)
    k.cmp("public share from the trace's private key", m.gb("TlsKeyShare", 32), V["Cpub"])
    k.cmp("SHA-256(\"\") computed at init", m.gb("TlsEmptyHash", 32), V["EmptyHash"])
    k.cmp("early secret", m.gb("secTlsEarly", 32), V["Early"])
    k.cmp("derived (1)", m.gb("secTlsDerived", 32), V["Derived1"])
    k.eq("ServerHello accepted", feed(m, "ShRec"), 1)
    k.eq("state WAIT_EE", m.g("Tls13State"), C["ST_WAIT_EE"])
    k.cmp("ECDHE shared secret", m.gb("secTlsEcdhe", 32), V["Ecdhe"])
    m.op(30, TMP)
    k.cmp("transcript CH..SH", m.get_at(TMP, 32), V["ThSh"])
    for g, key in (("secTlsHsSec", "Hs"), ("secTlsCHs", "Chs"), ("secTlsSHs", "Shs"),
                   ("secTlsDerived", "Derived2"), ("secTlsMaster", "Master")):
        k.cmp(g, m.gb(g, 32), V[key])
    k.cmp("installed read key = server hs key", m.gb("secTlsRKey", 16), V["ShsKey"])
    k.cmp("installed read iv", m.gb("secTlsRIv", 12), V["ShsIv"])
    k.cmp("installed write key = client hs key", m.gb("secTlsWKey", 16), V["ChsKey"])
    k.cmp("installed write iv", m.gb("secTlsWIv", 12), V["ChsIv"])

    k.eq("encrypted server flight accepted", feed(m, "Flight"), 1)
    k.eq("flight: no error", m.g("Tls13Err"), R["OK"])
    k.eq("flight: x509 verdict OK", m.g("Tls13X509Err"), X509ERR["OK"])
    k.eq("state SEND_FINISHED", m.g("Tls13State"), C["ST_SEND_FIN"])
    k.eq("end-entity key decoded as RSA", m.g("X509EePkeyType"), 1)
    k.cmp("transcript CH..Certificate", m.gb("TlsThCert", 32), V["ThCert"])
    k.cmp("CertificateVerify signed-content hash", m.gb("TlsMsgHash", 32), V["CvMsgHash"])
    k.cmp("transcript CH..server Finished", m.gb("TlsThSf", 32), V["ThSf"])
    k.cmp("client application secret", m.gb("secTlsCAp", 32), V["Cap"])
    k.cmp("server application secret", m.gb("secTlsSAp", 32), V["Sap"])
    k.cmp("read key moved to server ap key", m.gb("secTlsRKey", 16), V["SapKey"])
    k.cmp("read iv", m.gb("secTlsRIv", 12), V["SapIv"])
    k.cmp("write key still client hs key", m.gb("secTlsWKey", 16), V["ChsKey"])

    n = m.op(21, OUT, 768)
    k.eq("client Finished record length", n, len(V["CfinRec"]))
    k.cmp("CLIENT FINISHED RECORD, BYTE FOR BYTE", m.get_at(OUT, len(V["CfinRec"])), V["CfinRec"])
    k.eq("state CONNECTED", m.g("Tls13State"), C["ST_CONNECTED"])
    k.eq("Tls13Connected()", m.op(35), 1)
    k.cmp("write key moved to client ap key", m.gb("secTlsWKey", 16), V["CapKey"])
    k.cmp("write iv", m.gb("secTlsWIv", 12), V["CapIv"])
    connected = m.snapshot()

    k.eq("NewSessionTicket accepted", feed(m, "NstRec"), 1)
    k.eq("ticket counted and discarded", m.g("Tls13TicketsDiscarded"), 1)
    k.eq("still CONNECTED", m.g("Tls13State"), C["ST_CONNECTED"])
    m.load("Appdata", TMP)
    n = m.op(22, OUT, 768, TMP, len(V["Appdata"]))
    k.eq("client appdata length", n, len(V["CappRec"]))
    k.cmp("client appdata record", m.get_at(OUT, len(V["CappRec"])), V["CappRec"])
    k.eq("server appdata accepted", feed(m, "SappRec"), 1)
    k.eq("Tls13AppLen", m.g("Tls13AppLen"), len(V["Appdata"]))
    k.cmp("application plaintext at Tls13AppAddr", m.get_at(m.g("Tls13AppAddr"), len(V["Appdata"])), V["Appdata"])
    n = m.op(23, OUT, 768, ALERT["LEVEL_WARNING"], ALERT["CLOSE_NOTIFY"])
    k.eq("client close_notify length", n, len(V["CalertRec"]))
    k.cmp("client close_notify record", m.get_at(OUT, len(V["CalertRec"])), V["CalertRec"])
    k.eq("server close_notify accepted", feed(m, "SalertRec"), 1)
    k.eq("state CLOSED", m.g("Tls13State"), C["ST_CLOSED"])
    k.eq("peer alert close_notify", m.g("Tls13PeerAlert"), ALERT["CLOSE_NOTIFY"])
    k.eq("a closed connection accepts nothing", feed(m, "SappRec"), 0)
    k.eq("and fails", m.g("Tls13State"), C["ST_FAILED"])

    # ---- T7, post-handshake, each case from the CONNECTED snapshot ----
    def server_msg(msg):
        m.restore(connected)
        m.put_at(MSG, msg)
        n = m.op(34, MSG, len(msg), OUT, 768)
        m.put_at(REC, m.get_at(OUT, n))
        return m.op(20, REC, n)

    k.eq("KeyUpdate(update_requested) accepted", server_msg(bytes([24, 0, 0, 1, 1])), 1)
    k.eq("KeyUpdatePending set", m.g("Tls13KeyUpdatePending"), 1)
    k.cmp("server ap secret advanced with 'traffic upd'", m.gb("secTlsSAp", 32), V["SapUpd"])
    k.cmp("read key re-derived", m.gb("secTlsRKey", 16), V["SapUpdKey"])
    k.cmp("read iv re-derived", m.gb("secTlsRIv", 12), V["SapUpdIv"])
    server_msg(bytes([24, 0, 0, 1, 2]))
    k.eq("KeyUpdate request byte 2 refused by name", m.g("Tls13Err"), R["KEY_UPDATE_BAD_REQUEST"])
    server_msg(bytes([24, 0, 0, 2, 0, 0]))
    k.eq("KeyUpdate wrong length refused by name", m.g("Tls13Err"), R["KEY_UPDATE_LENGTH"])
    server_msg(bytes([13, 0, 0, 2, 0, 0]))
    k.eq("CertificateRequest refused by name", m.g("Tls13Err"), R["CLIENT_AUTH_REQUESTED"])
    server_msg(bytes([99, 0, 0, 0]))
    k.eq("unknown post-handshake message refused", m.g("Tls13Err"), R["POST_HS_UNKNOWN"])
    m.restore(connected)
    m.put_at(REC, bytes([20, 3, 3, 0, 1, 1]))
    k.eq("CCS once connected refused", m.op(20, REC, 6), 0)
    k.eq("named UNEXPECTED_CCS", m.g("Tls13Err"), R["UNEXPECTED_CCS"])
    m.restore(connected)
    k.eq("own KeyUpdate record length", m.op(24, OUT, 768, 0), 5 + 5 + 1 + 16)
    k.cmp("client ap secret advanced", m.gb("secTlsCAp", 32), V["CapUpd"])
    k.cmp("write key re-derived", m.gb("secTlsWKey", 16), V["CapUpdKey"])
    k.cmp("write iv re-derived", m.gb("secTlsWIv", 12), V["CapUpdIv"])


# ---------------------------------------------------------------- T3
def refuse_sh(m, k, key, want):
    k.eq(key + " refused", feed(m, key), 0)
    k.eq(key + " state FAILED", m.g("Tls13State"), C["ST_FAILED"])
    k.eq(key + " named", m.g("Tls13Err"), R[want])
    alert = m.g("Tls13Alert")
    k.true(key + " has an alert to send", alert != 0, "Tls13Alert is 0")
    k.eq(key + " plaintext alert record length", m.op(23, OUT, 768, ALERT["LEVEL_FATAL"], alert), 7)
    out = m.get_at(OUT, 7)
    k.eq(key + " alert record type/level/desc", (out[0], out[5], out[6]), (C["CT_ALERT"], ALERT["LEVEL_FATAL"], alert & 255))


def job_sh_refusals(m, k):
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    for key, want in (("ShHrr", "HELLO_RETRY_REQUEST"), ("ShDowngrade", "DOWNGRADE_SENTINEL"),
                      ("ShBadsuite", "CIPHER_SUITE"), ("ShCompress", "COMPRESSION_METHOD"),
                      ("ShBadver", "NOT_TLS13"), ("ShBadlegacy", "SH_LEGACY_VERSION"),
                      ("ShNoks", "NO_KEY_SHARE"), ("ShPsk", "PSK_OFFERED"),
                      ("ShSidecho", "SESSION_ID_ECHO")):
        setup_trace(m)
        refuse_sh(m, k, key, want)


# ---------------------------------------------------------------- T4 / T5
def _from_ee(m, snap_box):
    if "ee" not in snap_box:
        for i, b in enumerate(b"rsa"):
            m.put_at(NAME + i, bytes([b]))
        to_server_hello(m)
        if m.g("Tls13State") != C["ST_WAIT_EE"]:
            raise Fail("the trace's ServerHello was not accepted (Tls13Err %d) - every "
                       "case after it would test nothing" % m.g("Tls13Err"))
        snap_box["ee"] = m.snapshot()
    m.restore(snap_box["ee"])


def job_flight_a(m, k):
    box = {}
    _from_ee(m, box)
    k.eq("tampered flight refused", feed(m, "NegTag"), 0)
    k.eq("tampered flight: BAD_RECORD_MAC", m.g("Tls13Err"), R["BAD_RECORD_MAC"])
    _from_ee(m, box)
    k.eq("CertificateVerify with a flipped signature bit refused", feed(m, "NegCv"), 0)
    k.eq("named SIGNATURE_INVALID", m.g("Tls13Err"), R["SIGNATURE_INVALID"])
    k.eq("state FAILED", m.g("Tls13State"), C["ST_FAILED"])
    _from_ee(m, box)
    k.eq("rsa_pkcs1_sha256 in CertificateVerify refused", feed(m, "NegCvalg"), 0)
    k.eq("named SIGALG_PKCS1_IN_CV", m.g("Tls13Err"), R["SIGALG_PKCS1_IN_CV"])


def job_flight_b(m, k):
    box = {}
    for key, want in (("NegFin", "FINISHED_MISMATCH"), ("NegEarly", "EARLY_DATA_ACCEPTED"),
                      ("NegUnoffered", "UNOFFERED_EXTENSION"), ("NegEekeyshare", "EXT_NOT_ALLOWED_HERE"),
                      ("NegCertext", "CERT_EXTENSION_UNSOLICITED")):
        _from_ee(m, box)
        k.eq(key + " refused", feed(m, key), 0)
        k.eq(key + " named", m.g("Tls13Err"), R[want])
    _from_ee(m, box)
    k.eq("certificate key no longer the anchor's: refused", feed(m, "NegCert"), 0)
    k.eq("named CHAIN_INVALID", m.g("Tls13Err"), R["CHAIN_INVALID"])
    k.eq("x509 says NOT_TRUSTED", m.g("Tls13X509Err"), X509ERR["NOT_TRUSTED"])
    k.eq("alert unknown_ca", m.g("Tls13Alert"), ALERT["UNKNOWN_CA"])


def job_policy(m, k):
    box = {}
    _from_ee(m, box)
    m.put_at(NAME, b"srv")
    k.eq("wrong expected server name refused", feed(m, "Flight"), 0)
    k.eq("named CHAIN_INVALID", m.g("Tls13Err"), R["CHAIN_INVALID"])
    k.eq("x509 says BAD_SERVER_NAME", m.g("Tls13X509Err"), X509ERR["BAD_SERVER_NAME"])
    k.eq("alert bad_certificate", m.g("Tls13Alert"), ALERT["BAD_CERTIFICATE"])
    _from_ee(m, box)
    m.setg("TlsUnixTime", 1800000000)
    k.eq("clock after notAfter refused", feed(m, "Flight"), 0)
    k.eq("named CHAIN_INVALID", m.g("Tls13Err"), R["CHAIN_INVALID"])
    k.eq("x509 says EXPIRED", m.g("Tls13X509Err"), X509ERR["EXPIRED"])
    k.eq("alert certificate_expired", m.g("Tls13Alert"), ALERT["CERTIFICATE_EXPIRED"])
    _from_ee(m, box)
    m.setg("TlsUnixTime", 1400000000)
    k.eq("clock before notBefore refused", feed(m, "Flight"), 0)
    k.eq("named CHAIN_INVALID", m.g("Tls13Err"), R["CHAIN_INVALID"])


# ---------------------------------------------------------------- set-up
def job_early(m, k):
    """The parts of section 2 and 5 that need no key exchange: the top of
    the schedule, Tls13Init's two refusals, and the hkdf verdict latch."""
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m)
    k.eq("setup: no error", m.g("Tls13Err"), R["OK"])
    k.eq("setup: state WAIT_SH", m.g("Tls13State"), C["ST_WAIT_SH"])
    k.cmp("SHA-256(\"\") computed at init", m.gb("TlsEmptyHash", 32), V["EmptyHash"])
    k.cmp("early secret", m.gb("secTlsEarly", 32), V["Early"])
    k.cmp("derived (1)", m.gb("secTlsDerived", 32), V["Derived1"])
    m.op(30, TMP)
    k.cmp("transcript after the trace ClientHello", m.get_at(TMP, 32), hashlib.sha256(V["Ch"]).digest())
    # Pi 4 port change 3: the hkdf verdict latch
    k.eq("hkdf latch fires on an unencodable length", m.op(40, TMP, 70000), 1)
    k.eq("hkdf latch quiet on a good one", m.op(40, TMP, 32), 0)
    # Tls13Init's own refusals, called for real
    m.op(11)
    m.op(12, 0, m.addr["AnchorDn"], len(m.V["AnchorDn"]), m.addr["AnchorN"], len(m.V["AnchorN"]),
         m.addr["AnchorE"], len(m.V["AnchorE"]))
    m.op(13, HSBUF, HSBUF_N)
    k.eq("NO CLOCK: Init refused", m.op(15, NAME, 3, 0), 0)
    k.eq("named NO_TIME", m.g("Tls13Err"), R["NO_TIME"])
    k.eq("state FAILED", m.g("Tls13State"), C["ST_FAILED"])
    m.op(11)
    k.eq("NO TRUST ANCHOR: Init refused", m.op(15, NAME, 3, TIME_OK), 0)
    k.eq("named NO_ANCHORS", m.g("Tls13Err"), R["NO_ANCHORS"])
    k.eq("state FAILED", m.g("Tls13State"), C["ST_FAILED"])



# ---------------------------------------------------------------- T6
def job_dispatch_a(m, k):
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m)
    m.put_at(REC, bytes([20, 3, 3, 0, 1, 9]))
    k.eq("CCS with payload 9 refused", m.op(20, REC, 6), 0)
    k.eq("named BAD_CCS_VALUE", m.g("Tls13Err"), R["BAD_CCS_VALUE"])
    setup_trace(m)
    m.load("ShRec", REC)
    k.eq("header length disagreeing refused", m.op(20, REC, len(V["ShRec"]) - 1), 0)
    k.eq("named RECORD_LEN_MISMATCH", m.g("Tls13Err"), R["RECORD_LEN_MISMATCH"])
    setup_trace(m)
    m.put_at(REC, bytes([22, 3, 3, 0, 4, 8, 0, 0, 0]))
    k.eq("EncryptedExtensions where a ServerHello belongs refused", m.op(20, REC, 9), 0)
    k.eq("named UNEXPECTED_MESSAGE", m.g("Tls13Err"), R["UNEXPECTED_MESSAGE"])
    setup_trace(m)
    m.put_at(REC, bytes([22, 3, 3, 0, 4, 254, 0, 0, 0]))
    k.eq("synthetic message_hash refused", m.op(20, REC, 9), 0)
    k.eq("named MESSAGE_HASH_SYNTHETIC", m.g("Tls13Err"), R["MESSAGE_HASH_SYNTHETIC"])
    setup_trace(m)
    m.put_at(REC, bytes([22, 3, 3, 0, 0]))
    k.eq("zero-length handshake fragment refused", m.op(20, REC, 5), 0)
    k.eq("named EMPTY_HANDSHAKE_RECORD", m.g("Tls13Err"), R["EMPTY_HANDSHAKE_RECORD"])
    # a CCS during the handshake is dropped, then the ServerHello lands
    setup_trace(m)
    m.put_at(REC, bytes([20, 3, 3, 0, 1, 1]))
    k.eq("CCS during the handshake dropped", m.op(20, REC, 6), 1)
    k.eq("still WAIT_SH", m.g("Tls13State"), C["ST_WAIT_SH"])
    k.eq("ServerHello after the CCS accepted", feed(m, "ShRec"), 1)
    k.cmp("CCS did not touch the transcript (c hs secret)", m.gb("secTlsCHs", 32), V["Chs"])
    k.eq("plaintext handshake after keys refused", feed(m, "ShRec"), 0)
    k.eq("named PLAINTEXT_AFTER_KEYS", m.g("Tls13Err"), R["PLAINTEXT_AFTER_KEYS"])


def job_dispatch_b(m, k):
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m)
    sh = V["ShRec"]
    n = 40
    m.put_at(REC, bytes([22, 3, 3, 0, n]) + sh[5:5 + n])
    k.eq("first half of a split ServerHello", m.op(20, REC, 5 + n), 1)
    k.eq("waits for more", m.g("Tls13State"), C["ST_WAIT_SH"])
    rest = len(sh) - 5 - n
    m.put_at(REC, bytes([22, 3, 3, 0, rest]) + sh[5 + n:])
    k.eq("second half completes it", m.op(20, REC, 5 + rest), 1)
    k.eq("state WAIT_EE", m.g("Tls13State"), C["ST_WAIT_EE"])
    k.cmp("same secrets as unsplit", m.gb("secTlsSHs", 32), V["Shs"])


def job_dispatch_c(m, k):
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m)
    m.op(31, RECV, RECV_N)
    m.load("ShRec", EXP)
    n = 0
    total = len(V["ShRec"])
    while n < total:
        took = m.op(32, EXP + n, min(7, total - n))
        if took <= 0:
            k.true("transport pump took bytes", False, "Tls13FeedBytes returned %d at %d" % (took, n))
            return
        n += took
    k.eq("ServerHello pumped seven bytes at a time", m.g("Tls13State"), C["ST_WAIT_EE"])
    k.cmp("same secrets as one record", m.gb("secTlsSHs", 32), V["Shs"])


def job_kdf_fault(m, k):
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    setup_trace(m)
    m.setg("TlsKdfFault", 1)
    k.eq("ServerHello with a latched hkdf fault refused", feed(m, "ShRec"), 0)
    k.eq("named KDF_FAILED", m.g("Tls13Err"), R["KDF_FAILED"])
    k.eq("no read key installed", m.g("TlsRKeyed"), 0)
    k.eq("no write key installed", m.g("TlsWKeyed"), 0)


# ---------------------------------------------------------------- T8
def job_client_hello(m, k):
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    m.op(11)
    m.op(12, 0, m.addr["AnchorDn"], len(m.V["AnchorDn"]), m.addr["AnchorN"], len(m.V["AnchorN"]),
         m.addr["AnchorE"], len(m.V["AnchorE"]))
    m.op(13, HSBUF, HSBUF_N)
    m.op(14, C["X25519"])
    # Pi 4 port change 2: an UNSEEDED DRBG is refused by name, no share made
    k.eq("Init", m.op(15, NAME, 3, TIME_OK), 1)
    k.eq("NewKeyShare with an unseeded DRBG refused", m.op(26), 0)
    k.eq("named KEYGEN_FAILED", m.g("Tls13Err"), R["KEYGEN_FAILED"])
    k.eq("no key share left behind", m.g("TlsKeyShareLen"), 0)
    k.eq("DrbgInit with a fixed 48-byte seed", m.op(33, m.addr["DrbgSeed"], 48), 1)
    k.eq("Init", m.op(15, NAME, 3, TIME_OK), 1)
    k.eq("NewKeyShare", m.op(26), 1)
    k.eq("x25519 share length", m.g("TlsKeyShareLen"), 32)
    k.eq("ClientHello into 64 bytes refused", m.op(25, OUT, 64), 0)
    k.eq("named BUF_TOO_SMALL", m.g("Tls13Err"), R["BUF_TOO_SMALL"])
    k.eq("Init", m.op(15, NAME, 3, TIME_OK), 1)
    k.eq("NewKeyShare", m.op(26), 1)
    n = m.op(25, OUT, 768)
    k.true("ClientHello built", n > 100, "length %d" % n)
    k.eq("state WAIT_SH", m.g("Tls13State"), C["ST_WAIT_SH"])
    o = m.get_at(OUT, max(n, 0))
    if n <= 100:
        return
    k.eq("record type/version 0x0301", (o[0], o[1], o[2]), (22, 3, 1))
    k.eq("record length", (o[3] << 8) | o[4], n - 5)
    k.eq("ClientHello type", o[5], 1)
    k.eq("message length", (o[6] << 16) | (o[7] << 8) | o[8], n - 9)
    k.eq("legacy_version 0x0303", (o[9], o[10]), (3, 3))
    k.eq("32-byte session id", o[43], 32)
    k.eq("one cipher suite", (o[76] << 8) | o[77], 2)
    k.eq("TLS_AES_128_GCM_SHA256", (o[78] << 8) | o[79], 0x1301)
    k.eq("null compression only", (o[80], o[81]), (1, 0))
    p = 82
    ext_len = (o[p] << 8) | o[p + 1]
    p += 2
    k.eq("extension block closes the message", p + ext_len, n)
    count, saw = 0, 0
    ks = m.gb("TlsKeyShare", 32)
    while p < n:
        et, el = (o[p] << 8) | o[p + 1], (o[p + 2] << 8) | o[p + 3]
        p += 4
        if et == 51:
            k.eq("key_share group x25519", (o[p + 2] << 8) | o[p + 3], C["X25519"])
            k.eq("key_share length 32", (o[p + 4] << 8) | o[p + 5], 32)
            k.cmp("key_share bytes are the derived share", o[p + 6:p + 38], ks)
            saw = 1
        p += el
        count += 1
    k.eq("walk ends exactly", p, n)
    k.eq("five extensions", count, 5)
    k.eq("key_share present", saw, 1)
    k.eq("five offers recorded", m.g("TlsOfferedCount"), 5)


# ---------------------------------------------------------------- T9
def job_p256(m, k):
    V = m.V
    for i, b in enumerate(b"rsa"):
        m.put_at(NAME + i, bytes([b]))
    m.op(11)
    m.op(12, 0, m.addr["AnchorDn"], len(V["AnchorDn"]), m.addr["AnchorN"], len(V["AnchorN"]),
         m.addr["AnchorE"], len(V["AnchorE"]))
    m.op(13, HSBUF, HSBUF_N)
    k.eq("SetGroup secp256r1", m.op(14, C["P256"]), 1)
    k.eq("SetGroup 0x0018 refused", m.op(14, 0x18), 0)
    k.eq("named BAD_GROUP", m.g("Tls13Err"), R["BAD_GROUP"])
    k.eq("group left at secp256r1", m.g("TlsGroup"), C["P256"])
    k.eq("Init", m.op(15, NAME, 3, TIME_OK), 1)
    m.setgb("secTlsPriv", V["P256Priv"])
    k.eq("derive P-256 public", m.op(27), 1)
    k.eq("share length 65", m.g("TlsKeyShareLen"), 65)
    k.cmp("P-256 public share", m.gb("TlsKeyShare", 65), V["P256Pub"])
    m.setgb("TlsPeerShare", V["P256PeerPub"])
    m.setg("TlsPeerShareLen", 65)
    k.eq("P-256 ECDHE", m.op(28), 1)
    k.cmp("P-256 shared secret (X coordinate)", m.gb("secTlsEcdhe", 32), V["P256Shared"])
    m.setg("TlsPeerShareLen", 32)
    k.eq("peer share of the wrong length refused", m.op(28), 0)
    bad = bytearray(V["P256PeerPub"])
    bad[10] ^= 1
    m.setgb("TlsPeerShare", bytes(bad))
    m.setg("TlsPeerShareLen", 65)
    k.eq("off-curve peer point refused", m.op(28), 0)
    m.setgb("secTlsPriv", V["P256Order"])
    k.eq("scalar = n is out of range", m.op(29), 0)
    k.eq("and the derive refuses rather than reduce", m.op(27), 0)
    m.setgb("secTlsPriv", bytes(32))
    k.eq("scalar 0 out of range", m.op(29), 0)
    nm1 = bytearray(V["P256Order"])
    nm1[31] -= 1
    m.setgb("secTlsPriv", bytes(nm1))
    k.eq("scalar n-1 in range", m.op(29), 1)


JOBS = [
    ("early", job_early), ("record", job_record), ("handshake", job_handshake), ("sh-refusals", job_sh_refusals),
    ("flight-a", job_flight_a), ("flight-b", job_flight_b), ("policy", job_policy),
    ("dispatch-a", job_dispatch_a), ("dispatch-b", job_dispatch_b),
    ("dispatch-c", job_dispatch_c), ("kdf-fault", job_kdf_fault),
    ("client-hello", job_client_hello), ("p256", job_p256),
]


def run_job(args):
    name, product, V = args[:3]
    stop = args[3] if len(args) > 3 else False
    fn = dict(JOBS)[name]
    m = Machine(product, V)
    k = Checks(name, stop)
    t0 = time.time()
    try:
        fn(m, k)
    except Fail as e:
        k.results.append((name + ": job aborted", False, str(e)))
    except Exception as e:      # a model fault is a failure, with its message
        k.results.append((name + ": job raised", False, "%s: %s" % (type(e).__name__, e)))
    return name, k.results, m.steps, time.time() - t0


def run_all(product, V, jobs, only=None, quiet=False):
    names = [n for n, _ in JOBS if only is None or n in only]
    results, steps = [], 0
    with cf.ProcessPoolExecutor(max_workers=max(1, min(jobs, len(names)))) as ex:
        for name, res, st, secs in ex.map(run_job, [(n, product, V) for n in names]):
            results += res
            steps += st
            if not quiet:
                bad = sum(1 for r in res if not r[1])
                print("  job %-13s %3d checks  %d failed  %12d model instructions  %6.0f s"
                      % (name, len(res), bad, st, secs), flush=True)
    return results, steps


# =====================================================================
#  MUTATIONS - each must turn the gate red, except the one control
# =====================================================================
MUTANTS = [
    # (label, which file(s), [(find, replace)], expect, the jobs that judge it)
    ("nonce built from the sequence halves swapped", "rec",
     [("TlsRecNonce(@secTlsWIv[0], TlsWSeqHi, TlsWSeqLo)", "TlsRecNonce(@secTlsWIv[0], TlsWSeqLo, TlsWSeqHi)")],
     "kill", ["record"]),
    ("sequence carry unmasked (the 32-bit spelling, Pi 4 change 2)", "rec",
     [("  TlsWSeqLo = (TlsWSeqLo + 1) & #TLSREC_W32\n", "  TlsWSeqLo = TlsWSeqLo + 1\n")], "kill", ["record"]),
    ("overflow test back to the 32-bit -1 spelling (Pi 4 change 2)", "rec",
     [("If TlsWSeqLo = #TLSREC_W32 And TlsWSeqHi = #TLSREC_W32", "If TlsWSeqLo = -1 And TlsWSeqHi = -1"),
      ("If TlsRSeqLo = #TLSREC_W32 And TlsRSeqHi = #TLSREC_W32", "If TlsRSeqLo = -1 And TlsRSeqHi = -1")],
     "kill", ["record"]),
    ("tag verdict ignored", "rec", [("  If ok <> #TLSREC_W32\n", "  If 0\n")], "kill", ["record"]),
    ("Pico verdict test `ok = 0` against a gcm with the 32-bit mask spelling (Pi 4 change 1)", "rec+gcm",
     [("  If ok <> #TLSREC_W32\n", "  If ok = 0\n")], "kill", ["record"]),
    ("CONTROL: gcm with the 32-bit mask spelling, record layer as shipped", "gcm", [], "survive", ["record"]),
    ("additional data carries the inner length", "rec",
     [("  TlsRecAad(fraglen)\n", "  TlsRecAad(innerlen)\n")], "kill", ["record"]),
    ("all-zero inner plaintext accepted", "rec",
     [("  If i < 0\n    Tls13RecErr = #TLSREC_ERR_ALL_ZERO_INNER",
       "  If i < -1\n    Tls13RecErr = #TLSREC_ERR_ALL_ZERO_INNER")], "kill", ["record"]),
    ("'derived' context is SHA-256 of one byte, not of nothing", "hs",
     [("Sha256Of(@TlsScratch[0], 0, @TlsEmptyHash[0])", "Sha256Of(@TlsScratch[0], 1, @TlsEmptyHash[0])")],
     "kill", ["early"]),
    ("CertificateVerify without RsaSetPubKey (Pi 4 change 1)", "hs",
     [("    RsaSetPubKey(X509EeNAddr, X509EeNLen, X509EeEAddr, X509EeELen)\n", "")], "kill", ["flight-b"]),
    ("CertificateVerify verdict ignored", "hs",
     [("  If ok <> 1\n    ProcedureReturn TlsFail(#TLS13_REFUSE_SIGNATURE_INVALID",
       "  If 0\n    ProcedureReturn TlsFail(#TLS13_REFUSE_SIGNATURE_INVALID")], "kill", ["flight-a"]),
    ("server Finished not compared", "hs",
     [("  If CtEqual(@TlsVerifyData[0], msg + 4, 32) <> 1\n", "  If 0\n")], "kill", ["flight-b"]),
    ("DRBG verdicts ignored (the Pico shape, Pi 4 change 2)", "hs",
     [("  If DrbgGenerate(@TlsClientRandom[0], 32) <> 32\n", "  If 0\n"),
      ("  If DrbgGenerate(@TlsSessionId[0], 32) <> 32\n", "  If 0\n"),
      ("    If DrbgGenerate(@secTlsPriv[0], 32) <> 32\n", "    If 0\n")], "kill", ["client-hello"]),
    ("no-clock refusal removed", "hs", [("  If unixTime <= 0\n", "  If 0\n")], "kill", ["early"]),
    ("no-anchor refusal removed", "hs", [("  If xNumAnchors <= 0\n", "  If 0\n")], "kill", ["early"]),
    ("HelloRetryRequest sentinel not checked", "hs", [("  If same <> 0\n", "  If 0\n")], "kill", ["sh-refusals"]),
    ("hkdf verdict latch removed (Pi 4 change 3)", "hs",
     [("  If HkdfExpandLabel(secret, 32, label, labellen, context, ctxlen, dst, outlen) <> outlen\n    TlsKdfFault = 1\n",
       "  If HkdfExpandLabel(secret, 32, label, labellen, context, ctxlen, dst, outlen) <> outlen\n    TlsKdfFault = 0\n")],
     "kill", ["early"]),
    ("ServerHello installs keys despite an hkdf fault (Pi 4 change 3)", "hs",
     [("  TlsKeyIvFrom(@secTlsSHs[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])\n  If TlsKdfFault <> 0\n",
       "  TlsKeyIvFrom(@secTlsSHs[0], @secTlsKeyBuf[0], @secTlsIvBuf[0])\n  If 0\n")], "kill", ["kdf-fault"]),
]

GCM_32BIT = (("  neq = ((diff | (- diff)) >> 63) & #GCM_W32\n  ProcedureReturn neq ! #GCM_W32\n",
              "  neq = (diff | (- diff)) >> 31\n  ProcedureReturn neq ! $FFFFFFFF\n"),)


def _edit(text, edits, what):
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit("mutation anchor found %d times in %s (want 1):\n%r" % (text.count(old), what, old))
        text = text.replace(old, new, 1)
    return text


def run_mutant(args):
    i, compiler, workdir, V = args
    label, which, edits, expect, judges = MUTANTS[i]
    work = Path(workdir) / ("m%02d" % i)
    work.mkdir(parents=True, exist_ok=True)
    inc = {}
    for key, src in (("rec", REC_SRC), ("hs", HS_SRC), ("gcm", GCM_SRC)):
        text = src.read_text(encoding="utf-8")
        if key in which.split("+"):
            text = _edit(text, GCM_32BIT if key == "gcm" else edits, src.name)
        out = work / src.name
        out.write_text(text, encoding="utf-8")
        inc[key] = out.as_posix()
    try:
        product = build(compiler, work, "fixture", inc["rec"], inc["hs"], inc["gcm"])
    except Fail as e:
        return i, ["build: " + str(e)[:200]]
    bad = []
    for name in judges:
        _n, res, _st, _s = run_job((name, product, V, expect == "kill"))
        bad += [r[0] + " - " + r[2] for r in res if not r[1]]
    return i, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--only", nargs="*", help="run only these jobs (names as printed)")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    V = build_vectors()
    print("[gate] RFC 8448 anchors re-derived: %d vectors, every published value matched "
          "(AES oracle anchored to FIPS-197 C.1 and the eight RFC 8448 records)" % len(V))
    rc = 0
    with tempfile.TemporaryDirectory(prefix="tls13-8448-") as td:
        t0 = time.time()
        product = build(compiler, Path(td), "fixture")
        print("[gate] built the -t pi4 fixture (Pi 4 include list, #X509_SIG_LINKED = 1) in %.0f s" % (time.time() - t0))
        results, steps = run_all(product, V, a.jobs, a.only)
        fails = [r for r in results if not r[1]]
        for label, _ok, why in fails:
            print("FAIL", label, "-", why)
        print("tls13_rfc8448_check: %d checks, %d failed, %d model instructions, %.0f s"
              % (len(results), len(fails), steps, time.time() - t0))
        rc = 1 if fails or not results else 0
        if a.mutate:
            if fails:
                print("[gate] mutations not run: the unmutated tree is red")
                return 1
            print("[gate] %d mutations, %d at a time" % (len(MUTANTS), a.jobs))
            ok = 0
            with cf.ProcessPoolExecutor(max_workers=a.jobs) as ex:
                for i, bad in ex.map(run_mutant, [(i, compiler, td, V) for i in range(len(MUTANTS))]):
                    label, _w, _e, expect, _j = MUTANTS[i]
                    died = bool(bad)
                    good = died if expect == "kill" else not died
                    ok += good
                    print("MUTANT %-72s %s%s" % (label, ("killed" if died else "survived"),
                                                 "" if good else "   <-- WRONG, expected " + expect)
                          + (" (%s)" % bad[0][:110] if died else ""), flush=True)
            print("mutants: %d/%d behaved as expected" % (ok, len(MUTANTS)))
            rc |= 0 if ok == len(MUTANTS) else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
