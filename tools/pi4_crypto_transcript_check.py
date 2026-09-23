#!/usr/bin/env python3
"""pi4_crypto_transcript_check.py - is a silicon transcript evidence?

    python tools/pi4_crypto_transcript_check.py _work/pi4_crypto_silicon.txt

A transcript from this bench has to be checked before it is believed,
and not because the board is doubtful.  The USB serial adapter on COM7
intermittently stops delivering new bytes and hands back the last ones
it delivered, over and over; the capture that results still contains the
command, still contains the board's end marker, and is missing its
middle.  `tools/pi4_crypto_silicon.py` rejects and retakes a capture
like that while it is running.  THIS runs over the FILE afterwards, so
that the transcript that is kept as evidence has been checked by
something other than the program that produced it.

What it asserts, per `=== pmf> <command> ===` section:

  * no NUL byte anywhere - the monitor cannot print one;
  * no substantial line repeated three or more times - the adapter's
    signature (every self-test line carries its own id and tick count,
    so no two are equal);
  * every `crypto ...` section ends in its own totals line, and the
    number of PASS lines in it equals the number the totals line claims;
  * the EIGHTEEN per-module sections and the whole-sweep section agree:
    the same modules, the same vector counts, the same verdicts;
  * every GCM vector line says the forgery was REFUSED;
  * every `crypto speed` section carries a rate for all eleven symmetric
    modules AND all six public-key ones, in their own units, and ends in
    both of the board's end markers.  A throughput table with one module
    quietly missing is the same class of artefact as a vector sweep with
    a hole in the middle, and it reads just as well;
  * the image was hashed before and after and the two agree.
"""
from __future__ import annotations

import pathlib
import re
import sys

VEC = re.compile(r"^([a-z0-9-]+)\s+(\d+)\s+(PASS|FAIL)\b")
TOTALS = re.compile(r"crypto: (\d+) of (\d+) vectors PASS"
                    r"(?:, (\d+) forged GCM tags REFUSED)?"
                    r"(?:, (\d+) negatives REFUSED in all)?")

# THE EIGHTEEN, IN THE ORDER THE BOARD PRINTS THEM. Written out here
# rather than derived from the transcript, because a list derived from
# the file it is checking cannot notice that the file is short.
MODULES = ("sha256", "sha1", "hmac", "hmacsha1", "hkdf", "pbkdf2", "drbg",
           "aes", "aes-ctr", "gcm", "keywrap",
           "bignum", "p256", "x25519", "ecdsa", "rsa", "t0vm", "x509")
# The throughput run has TWO tables and they are in different units, so
# they are counted separately. Bytes a second is meaningless for a
# signature and operations a second is meaningless for a hash; a single
# list would have had to accept either unit for either module, which is
# how a row in the wrong unit gets through.
SPEED_SYM = ("sha256", "sha1", "hmac", "hmacsha1", "hkdf", "pbkdf2", "drbg",
             "aes", "aes-ctr", "gcm", "keywrap")
SPEED_PK = ("bignum", "p256", "x25519", "ecdsa", "rsa", "x509")
SPEED_MID = "throughput: 11 symmetric modules measured"
SPEED_END = "throughput: 6 public-key modules measured"
# A ROW MAY BE IN EITHER UNIT. The board switches to bytes a second
# below a kilobyte a second, because `bps / 1024` is an integer divide
# and a 686 bytes-a-second key wrap was printing "0 KB/s" - a working
# module reporting a rate of zero. Accepting only KB/s here would have
# made this checker green on exactly that line.
RATE = re.compile(r"^\s*\d+ bytes in \d+ ticks .*?, \d+ (?:KB/s|bytes/s)\s*$",
                  re.M)
# The public-key unit. Per-operation time FIRST and always, for the same
# reason the byte rate changes unit below a kilobyte: with the caches off
# a P-256 multiply is slower than one a second, so a bare rate would
# round to zero and read as a broken instrument.
OPRATE = re.compile(r"^\s*\d+ in \d+ ticks - \d+ us each, "
                    r"(?:\d+ per second|\d+ s per operation|"
                    r"faster than this counter can time one)\s*$", re.M)


def sections(text: str) -> list[tuple[str, str]]:
    out, name, buf = [], None, []
    for line in text.split("\n"):
        m = re.match(r"=== pmf> (.+) ===$", line.strip())
        if m:
            if name is not None:
                out.append((name, "\n".join(buf)))
            name, buf = m.group(1), []
            continue
        if name is not None:
            buf.append(line)
    if name is not None:
        out.append((name, "\n".join(buf)))
    return out


VECLINE = re.compile(r"^[a-z0-9-]+\s+\d+\s+(PASS|FAIL)\b")


def repeated_line(text: str, times: int = 3, minlen: int = 12):
    """A substantial line the capture prints three or more times.

    A FAILURE EXPLANATION IS NOT A REPEAT SIGNATURE.  The monitor prints
    the same fixed `!!` block once per failing vector, on purpose, so a
    run with fourteen failures in one module contains fourteen identical
    five-line blocks.  Counting those made this check - and the same
    check inside tools/pi4_crypto_silicon.py - call a truthful capture of
    a real failure "the adapter handing back its own tail", and the
    capturing tool then RETRIED it five times.  Explanation blocks are
    therefore skipped by structure: a block opens on a line starting `!!`
    and closes at the next per-vector line, blank line or prompt.
    Everything else is still counted, including the per-vector lines
    themselves, which carry an id and a tick count and so cannot repeat
    unless the link is duplicating bytes.
    """
    counts: dict[str, int] = {}
    in_explanation = False
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("pmf>") or VECLINE.match(line):
            in_explanation = False
        elif line.startswith("!!"):
            in_explanation = True
        if in_explanation:
            continue
        if len(line) >= minlen:
            counts[line] = counts.get(line, 0) + 1
    worst = max(counts.items(), key=lambda kv: kv[1], default=None)
    return worst if worst and worst[1] >= times else None


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                        else "_work/pi4_crypto_silicon.txt")
    text = path.read_text(encoding="utf-8", errors="replace")
    print("checking %s (%d bytes)" % (path, len(text)))
    bad: list[str] = []

    per_module: dict[str, list[tuple[int, str]]] = {}
    sweep: list[tuple[str, int, str]] = []
    forged_total = 0
    speed_seen = 0

    for name, body in sections(text):
        if "\x00" in body:
            bad.append("%s: contains NUL bytes" % name)
        rep = repeated_line(body)
        if rep:
            bad.append("%s: the line %r appears %d times - the adapter's "
                       "repeat signature" % (name, rep[0][:50], rep[1]))
        # THE THROUGHPUT SECTIONS ARE JUDGED SEPARATELY AND THEY HAVE TO
        # BE, because they carry no vector lines and no totals line at
        # all - fall through to the vector code and every one of them is
        # reported as "the sweep did not finish", which is how a check
        # that cries wolf teaches its reader to skip it.
        if name.startswith("crypto speed"):
            speed_seen += 1
            if SPEED_MID not in body:
                bad.append("%s: the symmetric table's end marker is missing, "
                           "so those eleven rows are a fragment" % name)
            if SPEED_END not in body:
                bad.append("%s: no end marker, so the throughput run did "
                           "not finish and the rows above it are a "
                           "fragment" % name)
            # A ROW WITHOUT A RATE HAS TWO QUITE DIFFERENT CAUSES AND
            # THIS USED TO REPORT BOTH AS THE FIRST ONE. The monitor
            # prints "no rate: the counter is not moving" when
            # CNTPCT_EL0 did not advance - an instrument failure that
            # invalidates every number in the section - and "the timed
            # run FAILED where the sweep passed" when the module
            # returned an error, which invalidates nothing else and is a
            # far more interesting finding. Naming the wrong one sends
            # the reader to the wrong place, which is what an error
            # written as a full sentence naming its cause exists to
            # prevent.
            if "the counter is not moving" in body:
                bad.append("%s: a module could not compute a rate because the "
                           "architectural counter was not advancing, so NOTHING "
                           "in this section is timed. Check that CNTPCT_EL0 is "
                           "readable at this exception level before reading any "
                           "row here" % name)
            if "the timed run FAILED where the sweep passed" in body:
                bad.append("%s: a module's timed run RETURNED AN ERROR where the "
                           "vector sweep passed, so that row has no rate. The "
                           "other rows are still timed; what this says is that "
                           "one image answered two different ways on two runs, "
                           "which matters more than the missing rate. Check the "
                           "module's runner and the vector the speed row picks, "
                           "in that order" % name)
            # A ZERO RATE IS A REGRESSION, NOT A MEASUREMENT. Every row
            # here did its work and reported a tick count, so a rate of
            # 0 can only come from the integer divide truncating - the
            # defect the board found the first time this measured a
            # module slower than a kilobyte a second.
            if re.search(r", 0 (?:KB/s|bytes/s)\s*$", body, re.M):
                bad.append("%s: a throughput row reports a rate of ZERO for a "
                           "module that finished and printed a tick count - "
                           "that is the integer divide truncating, not a "
                           "measurement" % name)
            if re.search(r"- \d+ us each, 0 per second", body):
                bad.append("%s: a public-key row reports ZERO operations a "
                           "second for a module that finished and printed a "
                           "per-operation time - that is the integer divide "
                           "truncating, not a measurement" % name)
            heads = [ln.split()[0] for ln in body.replace("\r", "").split("\n")
                     if ln[:1].strip() and ln.split()]
            missing = [m for m in SPEED_SYM + SPEED_PK if m not in heads]
            if missing:
                bad.append("%s: no throughput row for %s - a table with a "
                           "module quietly absent from it reads exactly "
                           "like a complete one"
                           % (name, ", ".join(missing)))
            # The two tables are counted apart. A public-key row that came
            # out in bytes a second, or a hash row in operations a second,
            # would balance a single total and be wrong in both halves.
            rates = len(RATE.findall(body))
            prf = body.count("HMAC-SHA-1 calls a second")
            if rates + prf != len(SPEED_SYM):
                bad.append("%s: %d byte-rate rows and %d iteration rows, and "
                           "there are %d symmetric modules"
                           % (name, rates, prf, len(SPEED_SYM)))
            ops = len(OPRATE.findall(body))
            if ops != len(SPEED_PK):
                bad.append("%s: %d operations-a-second rows, and there are %d "
                           "public-key modules"
                           % (name, ops, len(SPEED_PK)))
            continue

        if not name.startswith("crypto ") or name == "crypto list":
            continue

        rows = []
        for raw in body.replace("\r", "").split("\n"):
            m = VEC.match(raw.strip())
            if m:
                rows.append((m.group(1), int(m.group(2)), m.group(3)))
                if m.group(1) == "gcm" and "forged tag REFUSED" not in raw:
                    bad.append("%s: gcm vector %s does not say the forgery "
                               "was refused" % (name, m.group(2)))
        t = TOTALS.search(body)
        if not t:
            bad.append("%s: no totals line, so the sweep did not finish"
                       % name)
            continue
        passes, total = int(t.group(1)), int(t.group(2))
        forged = int(t.group(3) or 0)
        if len(rows) != total:
            bad.append("%s: the totals line claims %d vectors and the "
                       "section has %d lines" % (name, total, len(rows)))
        if passes != total:
            bad.append("%s: %d of %d PASS" % (name, passes, total))
        if any(v == "FAIL" for _, _, v in rows):
            bad.append("%s: a FAIL line" % name)

        if name == "crypto vectors":
            sweep = rows
            forged_total = forged
            print("  the whole sweep: %d of %d PASS, %d forgeries refused"
                  % (passes, total, forged))
        else:
            mod = name.split(None, 1)[1]
            per_module[mod] = [(i, v) for _, i, v in rows]
            print("  %-9s %3d of %3d PASS%s"
                  % (mod, passes, total,
                     ", %d forgeries refused" % forged if forged else ""))

    # THE TWO VIEWS MUST AGREE. The per-module runs and the single sweep
    # are separate executions of the same table; if they disagree about
    # which vectors ran or how they came out, one of them is not what it
    # says it is.
    if sweep and per_module:
        from collections import defaultdict
        by_mod = defaultdict(list)
        for m, i, v in sweep:
            by_mod[m].append((i, v))
        for mod, rows in sorted(per_module.items()):
            if by_mod.get(mod) != rows:
                bad.append("the %s section and the whole sweep disagree: "
                           "%d rows alone, %d in the sweep"
                           % (mod, len(rows), len(by_mod.get(mod, []))))
        if sum(len(v) for v in by_mod.values()) != len(sweep):
            bad.append("the sweep's rows do not add up")
        n_gcm = len(by_mod.get("gcm", []))
        if forged_total != n_gcm:
            bad.append("the sweep refused %d forgeries and has %d gcm "
                       "vectors" % (forged_total, n_gcm))

    # A PASS WITH NO THROUGHPUT SECTION AT ALL is not a pass. The rates
    # are the half of this exercise the desktop model cannot produce, so
    # a transcript that is missing them has proved only the half that was
    # already proved at the desk.
    if speed_seen == 0:
        bad.append("no `crypto speed` section anywhere in this transcript, "
                   "so the one measurement only the part can make was "
                   "never taken")
    else:
        print("  %d throughput section(s), all seventeen measured modules in each"
              % speed_seen)

    before = re.search(r"board\s+(\d+) bytes\s+crc32 ([0-9A-F]{8})\s+"
                       r"sha256 ([0-9a-f]{64})", text)
    after = None
    tail = text[text.find("after the results"):] if \
        "after the results" in text else ""
    if tail:
        after = re.search(r"board\s+(\d+) bytes\s+crc32 ([0-9A-F]{8})\s+"
                          r"sha256 ([0-9a-f]{64})", tail)
    if before and after:
        if before.groups() != after.groups():
            bad.append("the image on the board CHANGED during the pass: "
                       "%s then %s" % (before.groups(), after.groups()))
        else:
            print("  the image hashed the same before and after: %s bytes, "
                  "crc32 %s" % (before.group(1), before.group(2)))
    else:
        bad.append("the transcript does not hash the image both before and "
                   "after")

    print("-" * 66)
    if bad:
        print("NOT EVIDENCE - %d problem(s):" % len(bad))
        for b in bad:
            print("  * %s" % b)
        return 1
    print("THE TRANSCRIPT IS EVIDENCE: no NULs, no repeat signature, every "
          "crypto section finished, the per-module runs and the whole sweep "
          "agree, every GCM forgery refused, every throughput table carries "
          "every measured module in its own unit, and the image is the same "
          "before and after.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
