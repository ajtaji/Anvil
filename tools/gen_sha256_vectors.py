#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_sha256_vectors.py - emit a house-dialect DataSection include of
# random-length SHA-256 test vectors, each with its python-hashlib
# reference digest, for the M1 self-test (BearSSL TLS translation, LANE A).
#
# One forward-readable stream: a length table (Read.l) followed by, for
# every vector, its message bytes then its 32 expected digest bytes
# (Read.b). The self-test reads the lengths first, then walks the data
# section once, so a whole family's ~200 vectors never need to be buffered
# in RAM at once - which matters on the R4's 32 KB.
#
# Deterministic: a fixed seed means the same vectors every run, so a
# regenerate never silently changes what the gate proves.
#
# Usage:  python tools/gen_sha256_vectors.py [count] [maxlen] > out.inc
# ----------------------------------------------------------------------
import sys, random, hashlib

def emit(count=200, maxlen=300, seed=0x5A3C):
    rng = random.Random(seed)
    # A spread of lengths: force the block-boundary neighbours in, then
    # fill the rest at random across 0..maxlen so multi-block messages,
    # empty messages and partial tails are all exercised.
    forced = [0, 1, 2, 3, 55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129,
              191, 192, 193, 255, 256, 257]
    lens = [n for n in forced if n <= maxlen]
    while len(lens) < count:
        lens.append(rng.randint(0, maxlen))
    lens = lens[:count]

    msgs = []
    for n in lens:
        msgs.append(bytes(rng.randint(0, 255) for _ in range(n)))

    out = []
    out.append("; ======================================================================")
    out.append("; sha256 test vectors - AUTO-GENERATED, do not edit by hand.")
    out.append(";   generator: tools/gen_sha256_vectors.py   seed: 0x%04X" % seed)
    out.append(";   %d random-length messages (0..%d bytes) with hashlib digests." % (count, maxlen))
    out.append("; Each vector is its message bytes followed by its 32-byte expected")
    out.append("; digest; the lengths come first, in their own table, read whole.")
    out.append("; ======================================================================")
    out.append("#SHA256_VEC_COUNT = %d" % count)
    out.append("")
    out.append("DataSection")
    out.append("  Sha256VecLens:")
    for i in range(0, count, 12):
        chunk = lens[i:i+12]
        out.append("  Data.l " + ", ".join(str(x) for x in chunk))
    out.append("  Sha256VecData:")
    for n, m in zip(lens, msgs):
        dig = hashlib.sha256(m).digest()
        blob = m + dig
        out.append("  ; --- len %d ---" % n)
        for i in range(0, len(blob), 16):
            row = blob[i:i+16]
            out.append("  Data.b " + ", ".join(str(b) for b in row))
    out.append("EndDataSection")
    out.append("")
    return "\n".join(out)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    maxlen = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    sys.stdout.write(emit(count, maxlen))
