#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_drbg_vectors.py - emit a house-dialect DataSection include of
# HMAC-DRBG (SHA-256) test vectors for the M2 DRBG self-test (LANE A).
#
# The oracle is a from-scratch python reimplementation of HMAC-DRBG per
# NIST SP 800-90A, independent of the library under test. It is anchored to
# a real NIST CAVP HMAC_DRBG SHA-256 known-answer vector (the reseed case
# below), whose 64-byte ReturnedBits is asserted here at generation time -
# so the oracle is proven NIST-correct before generating any other case.
#
# Every case follows the CAVP known-answer shape:
#   Instantiate(entropy+nonce+perso); [Reseed(entropy_reseed);]
#   Generate(genlen) -> discarded; Generate(genlen) -> the returned bits.
#
# Layout: a meta table (seedlen, reseedlen, genlen per case, Read.l;
# reseedlen 0 means no reseed) then, per case, the seed material bytes, the
# reseed bytes, and genlen expected bytes.
#
# Deterministic. Usage: python tools/gen_drbg_vectors.py [randcount] > out.inc
# ----------------------------------------------------------------------
import sys, random, hmac, hashlib

HLEN = 32

class HmacDrbg:
    def __init__(self, seed):
        self.K = b"\x00" * HLEN
        self.V = b"\x01" * HLEN
        self._update(seed)

    def _hmac(self, key, msg):
        return hmac.new(key, msg, hashlib.sha256).digest()

    def _update(self, seed):
        self.K = self._hmac(self.K, self.V + b"\x00" + seed)
        self.V = self._hmac(self.K, self.V)
        if len(seed) == 0:
            return
        self.K = self._hmac(self.K, self.V + b"\x01" + seed)
        self.V = self._hmac(self.K, self.V)

    def reseed(self, seed):
        self._update(seed)

    def generate(self, n):
        out = b""
        while len(out) < n:
            self.V = self._hmac(self.K, self.V)
            out += self.V
        self._update(b"")
        return out[:n]

# Real NIST CAVP HMAC_DRBG SHA-256 vector (PredictionResistance=False, with
# reseed, no additional input). seed material = entropy + nonce + perso.
NIST_ENTROPY = bytes.fromhex("fa0ee1fe39c7c390aa94159d0de97564342b591777f3e5f6a4ba2aea342ec840")
NIST_NONCE   = bytes.fromhex("dd0820655cb2ffdb0da9e9310a67c9e5")
NIST_PERSO   = bytes.fromhex("f2e58fe60a3afc59dad37595415ffd318ccf69d67780f6fa0797dc9aa43e144c")
NIST_RESEED  = bytes.fromhex("e0629b6d7975ddfa96a399648740e60f1f9557dc58b3d7415f9ba9d4dbb501f6")
NIST_RETURN  = bytes.fromhex(
    "f92d4cf99a535b20222a52a68db04c5af6f5ffc7b66a473a37a256bd8d298f9b"
    "4aa4af7e8d181e02367903f93bdb744c6c2f3f3472626b40ce9bd6a70e7b8f93"
    "992a16a76fab6b5f162568e08ee6c3e804aefd952ddd3acb791c50f2ad69e9a0"
    "4028a06a9c01d3a62aca2aaf6efe69ed97a016213a2dd642b4886764072d9cbe")

def cavp_kat(seed, reseed, genlen):
    d = HmacDrbg(seed)
    if reseed is not None:
        d.reseed(reseed)
    d.generate(genlen)          # first generate, discarded per CAVP KAT
    return d.generate(genlen)   # second generate, the returned bits

def build_cases(randcount, seed=0x90A):
    # case 0: the anchored NIST reseed vector
    nist_seed = NIST_ENTROPY + NIST_NONCE + NIST_PERSO
    got = cavp_kat(nist_seed, NIST_RESEED, len(NIST_RETURN))
    assert got == NIST_RETURN, "NIST DRBG anchor mismatch: %s" % got.hex()
    cases = [(nist_seed, NIST_RESEED, len(NIST_RETURN), NIST_RETURN)]

    # case 1: a no-reseed variant built from the same oracle
    no_reseed_out = cavp_kat(nist_seed, None, 128)
    cases.append((nist_seed, b"", 128, no_reseed_out))

    rng = random.Random(seed)
    for _ in range(randcount):
        slen = rng.randint(16, 64)
        do_reseed = rng.randint(0, 1)
        genlen = rng.randint(1, 160)   # crosses several 32-byte blocks
        sd = bytes(rng.randint(0, 255) for _ in range(slen))
        if do_reseed:
            rs = bytes(rng.randint(0, 255) for _ in range(slen))
            cases.append((sd, rs, genlen, cavp_kat(sd, rs, genlen)))
        else:
            cases.append((sd, b"", genlen, cavp_kat(sd, None, genlen)))
    return cases

def emit(randcount=20, seed=0x90A):
    cases = build_cases(randcount, seed)
    out = []
    out.append("; ======================================================================")
    out.append("; HMAC-DRBG SHA-256 test vectors - AUTO-GENERATED, do not edit by hand.")
    out.append(";   generator: tools/gen_drbg_vectors.py   seed: 0x%03X" % seed)
    out.append(";   case 0 is a real NIST CAVP known-answer vector (with reseed);")
    out.append(";   case 1 a no-reseed variant; then %d random cases, oracle anchored" % randcount)
    out.append(";   to NIST. Every case: Instantiate; optional Reseed; Generate twice,")
    out.append(";   return the second (the CAVP KAT shape).")
    out.append("; Meta: seedlen, reseedlen (0=no reseed), genlen per case (Read.l).")
    out.append(";   Data stream: seed bytes, reseed bytes, then genlen expected bytes.")
    out.append("; ======================================================================")
    out.append("#DRBG_VEC_COUNT = %d" % len(cases))
    out.append("")
    out.append("DataSection")
    out.append("  DrbgVecMeta:")
    for sd, rs, genlen, _ in cases:
        out.append("  Data.l %d, %d, %d" % (len(sd), len(rs), genlen))
    out.append("  DrbgVecData:")
    for idx, (sd, rs, genlen, want) in enumerate(cases):
        blob = sd + rs + want
        out.append("  ; --- case %d: seedlen %d reseedlen %d genlen %d ---"
                   % (idx, len(sd), len(rs), genlen))
        if len(blob) == 0:
            continue
        for i in range(0, len(blob), 16):
            row = blob[i:i+16]
            out.append("  Data.b " + ", ".join(str(b) for b in row))
    out.append("EndDataSection")
    out.append("")
    return "\n".join(out)

if __name__ == "__main__":
    randcount = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sys.stdout.write(emit(randcount))
