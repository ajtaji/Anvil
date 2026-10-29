# Wider-curve TLS verification on the physical Pi 4

The public joint two-bit window covers P-384 and P-521. Baseline and window
payloads each ran 30 independently checked cases (captures 240 and 241).
The complete retained raw/DER corpus plus those derived cases passed 116
verdict/diagnostic checks (capture 243). The first expanded harness wrongly
supplied empty DER strings as signatures; capture 242 is a harness failure,
not a passed result. Corrected selection omits absent DER representations.

Typical nontrivial positive cases improved 7-11%; small-scalar cases can be
about 1-3% slower because they also pay table setup. These are per-signature
measurements, not whole HTTPS latency. The table adds 6,912 bytes to the
shared register file. All inputs are public verification data; this is not
private-key arithmetic. Pi 3 and Rock Pi shared proofs compile, without a
claim of physical execution on those boards.

Compressed artifacts retain exact source, binary, identity and reports.
The installed resident image is recorded separately from the RAM-only tests.
