#!/usr/bin/env python3
"""Executable gate for Anvil/Core/settings.pbi - the KEY=VALUE store.

      python tools/a64/a64_settings_check.py
      python tools/a64/a64_settings_check.py --mutate

settings.pi4 has two halves and they need proving two different ways.

  THE PURE HALF - the table, the parser and the serialiser - touches no
  medium.  The fixtures for it are built HERE, poked into the program's
  tsrc[] array before Main runs, and every expected value is held in
  this file independently of the program that produces it.

  THE I/O HALF calls fat.pi4, so it needs a filesystem.  There is no SD
  card in this machine, so a FAT32 volume is fabricated in memory - the
  geometry, the boot sector, the FSInfo sector, the two FATs and the
  root directory all come from a64_fat_check, which already builds
  exactly this and is the file that proves them.  Reusing it is
  deliberate: a second, subtly different fabrication would be a second
  thing to get wrong, and a disagreement between the two would look like
  a settings bug.

TWO KINDS OF ASSERTION LIVE HERE AND THE DIFFERENCE MATTERS.

  * EXPECT is what the PROGRAM reported.  Good for return codes and
    refusals; it is still the program grading itself.

  * check_file() is the real evidence.  After the run it reads the
    finished medium back out of interpreter memory, walks the root
    directory, follows SETTINGS.TXT's cluster chain and parses the text
    the way a PC would - asking settings.pi4 nothing at all.

  * check_source() is a THIRD kind and it is small: one rule about the
    library's text, because the library is chip-free core and must not
    know that a block writer exists.  It is here because the runtime
    checks and this one fail differently - see its own docstring.

It also checks the thing the design is most likely to be quietly wrong
about: that NO SECTOR OUTSIDE fat.pi4's writable regions was touched,
compared byte for byte against what was fabricated.

AND IT ASSERTS THAT THE PASSWORD IS IN THE FILE IN PLAIN TEXT.  That is
not an oversight in the gate.  It is the documented design (see THE
PASSWORD in settings.pi4's header) and a change to it must break a test
rather than pass quietly as an improvement nobody reviewed.

Nothing here touches hardware, a serial port, or a card.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
# DERIVED FROM THIS FILE'S OWN LOCATION, NOT HARDCODED.
#
# This was an absolute path to one checkout. A gate that names the
# tree it tests cannot test any other tree - and worse, run from a
# git worktree it silently built and judged the MAIN checkout while
# reporting on the worktree's name. That is the silent-wrong-answer
# failure this project refuses everywhere else: the gate went red on
# code the worktree did not contain, and would equally have gone
# GREEN on a defect the worktree had introduced.
# a64_backend_check.py and a64_emulator_check.py already derived it;
# these did not. The value is identical when run from the main
# checkout, so nothing about that case changes.
#
# PMF_REPO overrides it deliberately, and the tree actually read is
# PRINTED below - a gate that names its tree cannot quietly measure the
# wrong one twice.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
sys.path.insert(0, str(HERE))

from a64_interp import A64                      # noqa: E402
import a64_fat_check as F                       # noqa: E402

LOAD = 0x200000
SEC = F.SEC

SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4SettingsSelfTest.pi4"
# THE STORE MOVED AND THIS LINE DID NOT. When the settings store became
# chip-free core it went to Anvil/Core; the docstring and the mutation's
# include-rewrite were both updated, this was not, so every mutant died on
# a missing file instead of running. A sabotage control that cannot be
# armed is not a control - the gate looked green while its teeth were gone.
LIB = ROOT / "Anvil" / "Core" / "settings.pbi"
WORK = ROOT / "_work"

# The program's own array geometry.  Mirrored here rather than read out
# of the source, so a change to one without the other is a failure.
TS_SLOTS = 8
TS_SLOT = 512

# The values the program stores.  Written once here; the program has its
# own copies as literals, which is the point - if the two disagree the
# gate goes red.
NETWORK = "Workshop"
PASSWORD = "correct-horse-9"
LONGPASS = "a-much-longer-passphrase-than-before"
BOOTFILE = "ANVIL.IMG"
BAUD = "1500000"


# =====================================================================
#  THE TEXT FIXTURES.  These are what a hand-edited SETTINGS.TXT looks
#  like when somebody has been at it with Notepad, and each awkward
#  thing in them is there on purpose.
# =====================================================================
BOM = b"\xEF\xBB\xBF"

FIXTURES = [
    # 0 - the everything file.  A byte-order mark Notepad added, both
    #     comment spellings, a blank line, CRLF endings, a LONE CR
    #     ending, tabs and spaces around the equals sign, a value whose
    #     own '=' characters must stay in the value, and a duplicate key
    #     whose LAST spelling must win.
    BOM
    + b"# Anvil settings, edited by hand\r\n"
    + b"; and a second comment, in the other spelling\n"
    + b"\n"
    + b"wifi.network = " + NETWORK.encode() + b"\r\n"
    + b"  wifi.password.plaintext=" + PASSWORD.encode() + b"\n"
    + b"console.baud\t=\t" + BAUD.encode() + b"\n"
    + b"some.base64 = YWJjZA==\n"
    + b"dup.key=first\r"
    + b"dup.key=second\n",

    # 1 - a line with no equals sign at all, and it is LINE 3.  The two
    #     good lines before it must be in the table; everything after it
    #     must not.
    #
    #     THE ENDINGS ARE CRLF ON PURPOSE and this fixture is the only
    #     place the line NUMBER is checked, which makes it the only test
    #     of "a CR LF pair is one line ending".  It was \n here first,
    #     and --mutate caught that: breaking the CRLF pairing left the
    #     gate GREEN, because nothing was counting lines in a file that
    #     had any.  A file saved by a Windows editor is the normal case,
    #     so an error message naming line 5 for a fault on line 3 would
    #     have shipped.
    b"a.one=1\r\n"
    b"b.two=2\r\n"
    b"this line has no equals sign\r\n"
    b"c.three=3\r\n",

    # 2 - nothing to the left of the equals, on line 2.
    b"a.one=1\n"
    b"=orphan\n",

    # 3 - a value one byte over the limit, on line 1.
    b"k=" + b"x" * 96 + b"\n",

    # 4 - a key one byte over the limit, on line 1.
    b"k" * 32 + b"=1\n",

    # 5 - comments and blanks only.  A legal, empty settings file.
    b"# one\n\n;two\n   \n",

    # 6 - unused; the program parses it with a length of zero, which is
    #     also a legal, empty settings file.
    b"",

    # 7 - spare.
    b"",
]


# =====================================================================
#  WHAT THE PROGRAM MUST REPORT, IN ORDER.
#
#  Held here, independently of the program.  A check that silently
#  stopped running is a length mismatch and not a pass - the program's
#  last entry is its own nres, so the two cannot drift apart.
# =====================================================================
EXPECT: list = []


def ex(label: str, *values: int) -> None:
    for v in values:
        EXPECT.append((label, v))


# error codes, spelled out here so the expectations read as English
E_NONE, E_NULL, E_NO_KEY, E_KEY_LONG, E_KEY_CHAR = 0, 1, 2, 3, 4
E_VALUE_LONG, E_VALUE_CHAR, E_VALUE_EDGE, E_FULL, E_NOTFOUND = 5, 6, 7, 8, 9
E_SYNTAX, E_TEXT_LONG, E_NO_FILE, E_FAT, E_READ_SHORT = 10, 11, 12, 13, 14
E_UNSAFE_SAVE, E_BAD_LEN, E_WIFI_NET, E_WIFI_PASS = 15, 16, 17, 18
E_WIFI_SLOT = 19             # a Wi-Fi slot number the store does not keep
FAT_NO_WRITER = 40           # #FAT_ERR_NO_WRITER, fat.pi4:1110. Kept
                             # because fat.pi4 still answers it; the
                             # settings store no longer reaches it - see
                             # HW_FILE_READONLY below.

# THE SEAM'S CODE FOR "readable here, not writable here", from
# Anvil/Hal/hal.pbi.  The settings store stopped calling fat.pi4 directly
# when the Arduino UNO Q arrived - it reaches a medium only through the
# HwFile* seam now - so the refusal an unwritable medium produces is this
# and no longer #FAT_ERR_NO_WRITER.
#
# THE PROPERTY UNDER TEST DID NOT CHANGE, only the code that names it: a
# medium that cannot be written must be refused WITHOUT A SECTOR BEING
# TOUCHED, and "AND NOT ONE SECTOR WAS WRITTEN" is still the line after
# each of them, which is the assertion that was ever load-bearing.
HW_FILE_READONLY = 5         # #HW_FILE_READONLY, Anvil/Hal/hal.pbi

# ---- phase 1, the table ---------------------------------------------
ex("the table starts empty", 0)
ex("a key is set", 1)
ex("and there is one of them", 1)
ex("and it reads back", 1)
ex("and the table is dirty", 1)
ex("the key is found in another case", 1)
ex("and is stored folded to lower case", 1)
ex("setting it again succeeds", 1)
ex("without adding a key", 1)
ex("with the new value", 1)
ex("an empty value is legal", 1)
ex("the key exists", 1)
ex("and its value is zero bytes long", 0)
ex("an absent key does not exist", 0)
ex("and has no length", -1)
ex("an empty key is refused", 0, E_NO_KEY)
ex("a key with a space is refused", 0, E_KEY_CHAR)
ex("a key with an equals sign is refused", 0, E_KEY_CHAR)
ex("a key of forty bytes is refused", 0, E_KEY_LONG)
ex("a value with a leading space is refused", 0, E_VALUE_EDGE)
ex("a value with a trailing space is refused", 0, E_VALUE_EDGE)
ex("and neither one created the key", 0)
ex("a value of exactly 95 bytes is accepted", 1, 95)
ex("a value of 96 bytes is refused", 0, E_VALUE_LONG)
ex("two more keys", 1, 1)
ex("five keys now", 5)
ex("one is removed", 1)
ex("four keys now", 4)
ex("and the order of the rest is unchanged", 1, 1, 1, 1)
ex("removing it again is refused", 0, E_NOTFOUND)
ex("a network name is not secret", 0)
ex("a password is", 1)
ex("in any case", 1)
ex("so is anything with 'secret' in the name", 1)
ex("and anything with 'passphrase' in it", 1)
ex("the mask is eight asterisks", 1)
ex("asking about a key leaves no error behind", E_NONE)

# The fan's six keys, added with the fan policy on 2026-09-06. They are
# ordinary keys and the point is that they ARE: a key name the store
# refuses would leave a fan forgetting its pin at every reset, silently,
# because the setter that wrote it has no way to notice.
ex("the fan's six keys are all accepted", 1, 1, 1, 1, 1, 1)
ex("and there are six of them", 6)
ex("and they read back", 1, 1)
ex("a fan setting is not a secret", 0, 0)
ex("and none of them left an error behind", E_NONE)
ex("an empty network name is refused", 0, E_WIFI_NET)
ex("a real one is accepted", 1, 1)
ex("a seven-character password is refused", 0, E_WIFI_PASS)
ex("an eight-character one is accepted", 1, 1)
ex("and the key it lands under says plaintext", 1)
ex("thirty-two keys all fit", 32, 32)
ex("the thirty-third is refused", 0, E_FULL)
ex("and did not displace anything", 32)

# ---- phase 2, the parser --------------------------------------------
ex("the everything file parses", 1, E_NONE, 1)
ex("five keys came out of it", 5)
ex("the network name", 1)
ex("the password", 1)
ex("the baud rate", 1)
ex("a value whose own equals signs survived", 1)
ex("a duplicate key, last one winning", 1)
ex("and the duplicate was counted", 1)
ex("a parse is not a change", 0)
ex("a line with no equals sign is refused", 0, E_SYNTAX, 3)
ex("the load is marked partial", 2)
ex("and what came before it is in the table", 2)
ex("an empty key is refused, on line 2", 0, E_NO_KEY, 2)
ex("an over-long value is refused, on line 1", 0, E_VALUE_LONG, 1)
ex("an over-long key is refused, on line 1", 0, E_KEY_LONG, 1)
ex("comments and blanks alone are a valid empty file", 1, 0)
ex("and so is nothing at all", 1, 0)
ex("a null buffer is refused", 0, E_NULL)

# ---- phase 3, the round trip ----------------------------------------
ex("the table serialises", 1, E_NONE)
ex("the first byte is a comment marker", 35)
ex("the last byte is a newline", 10)
ex("and it parses straight back", 1)
ex("with every key", 5)
ex("and every value", 1, 1, 1, 1, 1)
ex("and every key present", 1)
ex("in the same order", 1, 1)
ex("a destination too small refuses rather than truncating", -1, E_TEXT_LONG)
ex("and did not write one byte past the end of it", 1)

# ---- phase 4, the numbered Wi-Fi slots ------------------------------
#
#  wifi.N.ssid and wifi.N.password.plaintext for N in 1..4, with the old
#  flat pair answering to pseudo-slot 5 so that a stick written by the
#  previous build keeps working.  THE SLOT NUMBER IS THE PREFERENCE
#  ORDER, and the two properties worth breaking a build over are that
#  the legacy pair is LAST in it and that SettingsWifiFindSsid compares
#  BYTE FOR BYTE.
#
#  EVERY CREDENTIAL BELOW IS FAKE.  "testpass1" is not a passphrase for
#  anything and no real one may be written into this repository - see
#  the note at the top of pi4SettingsSelfTest.pi4.
ex("there are four slots", 4)
ex("and the legacy pair answers to the one past them", 5)
ex("the slot key names are built at run time", 1, 1, 1, 1)
ex("the longest one is 25 bytes against #SET_KEY_MAX 31", 25)
ex("and the ssid one is 11", 11)
ex("the pseudo-slot hands back the old flat names", 1, 1)
ex("a slot number the store does not keep gets no name", 0, 0, 0, 0)
ex("the two key buffers are separate", 1, 1)
ex("a slot ssid is not secret", 0)
ex("a numbered passphrase is, by the same substring rule", 1, 1, 1)
ex("and the built ssid key is not", 0)
ex("an empty slot reads as nothing", 0, 0)
ex("and leaves no error behind", E_NONE)
ex("it is not in use", 0)
ex("the walk finds none", 0)
ex("the count is none", 0)
ex("and no ssid is found", 0)
ex("still no error behind", E_NONE)
ex("a slot number that does not exist reads as nothing", 0)
ex("but DOES get its own code", E_WIFI_SLOT)
ex("a slot ssid is set", 1)
ex("and a slot passphrase", 1)
ex("under the keyed names", 1, 1)
ex("and they read back through the slot API", 1, 1)
ex("the slot is in use", 1)
ex("and it cost two keys", 2)
ex("an empty slot ssid is refused", 0, E_WIFI_NET)
ex("a seven-character slot passphrase is refused", 0, E_WIFI_PASS)
ex("and neither refusal changed what was there", 1, 1)
ex("slot zero is refused", 0, E_WIFI_SLOT)
ex("the legacy pseudo-slot cannot be WRITTEN", 0, E_WIFI_SLOT)
ex("nor its passphrase", 0, E_WIFI_SLOT)
ex("and none of that created the old flat key", 0)
ex("a 32-character ssid is accepted", 1, 32)
ex("a 33-character one is refused", 0, E_WIFI_NET)
ex("and did not disturb the 32", 32)
ex("a 63-character passphrase is accepted", 1, 63)
ex("a 64-character one is refused", 0, E_WIFI_PASS)
ex("and did not disturb the 63", 63)
ex("a 28-character ssid with a band suffix fits easily", 1, 28)
ex("four networks, two pairs of near-identical names", 1, 1, 1, 1)
ex("the one with the band suffix", 1)
ex("THE SUFFIX IS NOT STRIPPED", 2)
ex("the one-letter pair, first", 3)
ex("AND SECOND - a different network", 4)
ex("THE COMPARISON IS NOT CASE FOLDED", 0, 0)
ex("a prefix is not a match", 0)
ex("nor is a longer string starting with one", 0)
ex("AND NOTHING IS TRIMMED", 0)
ex("an unknown name is not found", 0)
ex("nor an empty one", 0)
ex("nor a null pointer", 0)
ex("and not one of those left an error behind", E_NONE)
ex("two slots and the old flat pair", 1, 1, 1, 1)
ex("three networks are stored", 3)
ex("the walk skips the empty slot", 2)
ex("and goes in order", 4)
ex("AND THE LEGACY PAIR COMES LAST, NOT FIRST", 5)
ex("and then there are no more", 0)
ex("the legacy pair reads through the slot API", 1, 1)
ex("a numbered network is found by name", 2)
ex("and so is the legacy one, as slot five", 5)
ex("a stick written by the previous build", 1, 1)
ex("holds one network", 1)
ex("which is the legacy pseudo-slot", 5)
ex("its name and its passphrase are both readable", 1, 1)
ex("it is found by name", 5)
ex("and the OLD accessors still answer", 1, 1)
ex("a slot is filled", 1, 1)
ex("costing two keys", 2)
ex("removing it succeeds", 1)
ex("AND TAKES BOTH KEYS", 0)
ex("removing it again does nothing", 0)
ex("and that is not an error", E_NONE)
ex("a passphrase with no name against it", 1, 1)
ex("does not count as a network", 0, 0)
ex("but is still removed entirely", 1, 0)
ex("removing a slot that does not exist is refused", 0, E_WIFI_SLOT)
ex("the legacy pair CAN be removed - that is the migration path", 1, 1, 1)
ex("and both its keys went", 0)
ex("all four slots fill", 8, 8)
ex("the old flat pair on top of them", 1, 1)
ex("is ten keys of thirty-two", 10)
ex("and five networks", 5)
ex("four slots with the same name: the FIRST wins", 1)
ex("the whole lot serialises", 1)
ex("and parses straight back", 1)
ex("with every key", 10)
ex("and every network", 5)
ex("the keyed names survived the parser", 1, 1)
ex("so did the flat pair", 1)
ex("the order survived too", 5)
ex("and the lookup", 5)
ex("a numbered passphrase is still masked afterwards", 1)
ex("and its ssid still is not", 0)

# ---- phase 5, the medium --------------------------------------------
ex("the fabricated volume mounts", 1)
ex("as FAT32", 32)
ex("there is no settings file yet", 0, E_NO_FILE)
ex("and the table is empty", 0)
ex("and nothing has been written", 0)
ex("a save to an unwritable medium is refused", 0, E_FAT, HW_FILE_READONLY)
ex("AND NOT ONE SECTOR WAS WRITTEN", 0)
# AND NOTHING WAS ARMED ON THE WAY TO THAT REFUSAL.  "No sector was
# written" and "nothing can now write one" are different facts, and the
# refusal paths are where the second one goes wrong, because they return
# before the backend reaches its own arm/disarm at all.
ex("and no block writer was installed on the way there", 0)
ex("with the writer armed, the save succeeds", 1, E_NONE)
ex("the table is no longer dirty", 0)
ex("sectors were written", 1)
ex("none outside the partition", 0)
ex("none misaligned", 0)
ex("a fresh table is empty", 0)
ex("and the file loads into it", 1)
ex("cleanly", 1)
ex("with three keys", 3)
ex("the network name", 1)
ex("the password, in plain text", 1)
ex("the baud rate", 1)
ex("a key is removed", 1)
ex("and the password replaced with a longer one", 1)
ex("the file is saved again", 1)
ex("and loads back", 1)
ex("with two keys", 2)
ex("the longer password", 1)
ex("and no baud rate", 0)
ex("a bad file leaves a partial load", 0, 2)
ex("saving after one is refused", 0, E_UNSAFE_SAVE)
ex("AND NOT ONE SECTOR WAS WRITTEN", 0)
ex("and no block writer either - this refusal is the earliest there is", 0)
ex("discarding the rest clears it", 1)
ex("and the save is allowed", 1)
ex("the final contents are saved", 1)
# The backend arms fat.pi4's block writer around its own single write and
# disarms it on every path out.  This asks fat.pi4 what it is holding
# afterwards, so the disarm is measured rather than assumed - between
# saves nothing in this monitor can reach the medium.
#
# ON ITS OWN THIS LINE CAUGHT NOTHING, and the mutation table below is
# what proved it.  "the library installs a block writer of its own" goes
# straight past a check placed here, because the success path ends inside
# HwFileWriteAll, which arms its own writer over the top of any other and
# disarms it on the way out - so this reads 0 whether the library
# interfered or not.  The assertion was written when the store reached
# the medium directly and it was sound then; the file seam moved the
# thing it was watching.  What "disarmed" means on the far side of that
# seam is: NO EXIT FROM A SAVE LEAVES A WRITER INSTALLED, and the three
# refusals are the exits that matter, because a refusal returns before
# the backend can tidy up after anybody.
ex("and the block writer is disarmed again", 0)
ex("with the medium unwritable the save is refused again", 0, HW_FILE_READONLY)
ex("AND NOT ONE SECTOR WAS WRITTEN", 0)
ex("and no writer is left armed as the program ends", 0)
ex("nothing outside the partition over the whole run", 0)
ex("and nothing misaligned over the whole run", 0)

ex("check count", len(EXPECT))     # the value of nres at that moment


# =====================================================================
#  The volume.  A CLEAN one - no SETTINGS.TXT, plenty of free clusters,
#  and an FSInfo sector whose hints are VALID, so the first allocation
#  does not have to rebuild the free count from a full pass over a
#  65525-entry FAT.  That rebuild is fat.pi4's business and is proved by
#  fat.pi4's own gate; paying 30 million interpreter steps for it here
#  would only make this gate slow.
# =====================================================================
def build_volume() -> F.Disk:
    d = F.Disk()

    d.put(0, 0x000, b"\xFA\x33\xC0\x8E\xD0")
    d.put(0, 0x1BE, F.mbr_entry(0x80, 0x0C, F.PART_LBA, F.PART_SECS))
    d.put(0, 0x1FE, bytes([0x55, 0xAA]))

    F.bpb(d, F.PART_LBA, F.TOT_SECS)

    # Cluster 2 is the root directory and is in use; 3 .. CLUSTERS+1 are
    # free.  The count and the hint are therefore both known and true.
    F.fsinfo(d, F.PART_LBA, F.CLUSTERS - 1, 3)

    for copy in range(F.NUM_FATS):
        base = F.FAT_BASE + copy * F.FAT_SECS
        d.u32(base, 0, 0x0FFFFFF8)      # media byte, [FATGEN]
        d.u32(base, 4, 0x0FFFFFFF)      # cluster 1, reserved
        d.u32(base, 8, F.EOC)           # cluster 2 - the root directory

    root = F.clus_lba(2)
    d.put(root, 0, F.dirent(b"PMFBOOT    ", 0x08, 0, 0))     # volume label
    d.put(root, 32, F.dirent(b"ANVIL   IMG", 0x20, 0, 0))    # a file that
    #                                                          must not move
    # Everything after that reads as $00 - never used - which is what a
    # directory scan stops at and what FatCreate takes its slot from.
    return d


def run_cmd(args: list[str]) -> str:
    r = subprocess.run(args, cwd=ROOT, env=BUILD_ENV, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    if r.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{r.stdout}")
    return r.stdout


def build_image(src: pathlib.Path, img: pathlib.Path) -> dict:
    out = run_cmd([str(PMFC), "--compile", str(src), "-t", "pi4",
                   "--load-addr", hex(LOAD), "-o", str(img), "-s"])
    if "pmfc: OK" not in out:
        raise SystemExit(out)
    symfile = img.parent / (img.name + ".sym")
    syms = dict(
        line.split("=", 1)
        for line in symfile.read_text(encoding="utf-8-sig").splitlines()
        if "=" in line
    )
    return {k: int(v) for k, v in syms.items()}


class Run:
    def __init__(self, cpu, sym, steps: int, fabricated: F.Disk) -> None:
        self.cpu = cpu
        self.steps = steps
        self.fabricated = fabricated

        n = cpu.load(sym["global_nres"], 8)
        base = sym["global_res"]
        self.res = [cpu.load(base + i * 8, 8) for i in range(n)]
        self.res = [v - (1 << 64) if v >= (1 << 63) else v for v in self.res]
        self.nres = n

        tb = sym["global_tdisk"]
        mem = cpu.memory
        self.disk = bytes(mem.get(tb + i, 0) for i in range(2048 * SEC))

    def sec(self, lba: int) -> bytes:
        return self.disk[lba * SEC:(lba + 1) * SEC]

    def fat_entry(self, copy: int, cl: int) -> int:
        off = (F.FAT_BASE + copy * F.FAT_SECS) * SEC + cl * 4
        return struct.unpack_from("<I", self.disk, off)[0] & 0x0FFFFFFF

    def chain(self, start: int, limit: int = 64) -> list:
        out = []
        cl = start
        while 2 <= cl <= F.CLUSTERS + 1 and len(out) < limit:
            out.append(cl)
            cl = self.fat_entry(0, cl)
        return out

    def root_entries(self):
        """Every 32-byte slot of the root directory, in order, stopping
        at the $00 end marker - the way any other implementation would
        read it."""
        out = []
        for cl in self.chain(2):
            lba = F.clus_lba(cl)
            for k in range(SEC // 32):
                e = self.disk[lba * SEC + k * 32:lba * SEC + (k + 1) * 32]
                if e[0] == 0x00:
                    return out
                out.append(e)
        return out


def execute(sym: dict, img: pathlib.Path) -> Run:
    blob = img.read_bytes()
    cpu = A64(pc=LOAD)
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b

    # Skip the BSS-zero loop: a fresh interpreter dict already reads as
    # zero everywhere, and the loop would wipe the fixtures poked below.
    cpu.pc = LOAD + sym["__a64_bss_done"]

    disk = build_volume()
    base = sym["global_tdisk"]
    for lba, data in disk.s.items():
        for i, b in enumerate(data):
            if b:
                cpu.memory[base + lba * SEC + i] = b

    tsrc = sym["global_tsrc"]
    tlen = sym["global_tsrclen"]
    for k, text in enumerate(FIXTURES[:TS_SLOTS]):
        if len(text) > TS_SLOT:
            raise SystemExit("fixture %d does not fit a slot" % k)
        for i, b in enumerate(text):
            if b:
                cpu.memory[tsrc + k * TS_SLOT + i] = b
        cpu.store(tlen + k * 8, len(text), 8)

    trap = LOAD + sym["_a64_end_trap"]
    steps = 0
    for steps in range(160_000_000):
        if cpu.pc == trap:
            break
        cpu.step()
    else:
        raise SystemExit("the test program never reached its end trap")
    return Run(cpu, sym, steps, disk)


# =====================================================================
#  What the program said
# =====================================================================
def check_reported(r: Run, fails: list) -> int:
    if r.nres != len(EXPECT):
        fails.append("the program made %d checks, this file expects %d"
                     % (r.nres, len(EXPECT)))
    n = min(r.nres, len(EXPECT))
    for i in range(n):
        label, want = EXPECT[i]
        if r.res[i] != want:
            fails.append("check %d (%s): got %d, expected %d"
                         % (i, label, r.res[i], want))
    return len(EXPECT)


# =====================================================================
#  THE REAL EVIDENCE.  Nothing below asks the program anything.
# =====================================================================
def parse_like_a_pc(text: bytes):
    """Read the file the way any other implementation would.  Not a copy
    of settings.pi4's parser: this one is deliberately written from the
    format description in the header rather than from that code."""
    out = {}
    body = text[3:] if text.startswith(BOM) else text
    for raw in body.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"):
        line = raw.strip()
        if not line or line[:1] in (b"#", b";"):
            continue
        if b"=" not in line:
            raise ValueError("a line with no equals sign: %r" % raw)
        k, v = line.split(b"=", 1)
        out[k.strip().decode()] = v.strip().decode()
    return out


def check_file(r: Run, fails: list) -> int:
    n = 0

    def want(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    # ---- the directory ------------------------------------------------
    ents = r.root_entries()
    names = [e[:11] for e in ents if e[0] != 0xE5 and e[0x0B] != 0x0F]
    want(b"SETTINGSTXT" in names,
         "SETTINGS.TXT is not in the root directory")
    want(b"ANVIL   IMG" in names,
         "ANVIL.IMG is no longer in the root directory - settings.pi4 "
         "disturbed a file it must never touch")
    want(b"PMFBOOT    " in names, "the volume label is gone")

    ent = None
    for e in ents:
        if e[:11] == b"SETTINGSTXT":
            ent = e
    if ent is None:
        fails.append("no SETTINGS.TXT entry to read")
        return n

    want(ent[0x0B] & 0x10 == 0, "SETTINGS.TXT is marked as a directory")
    size = struct.unpack_from("<I", ent, 0x1C)[0]
    first = (struct.unpack_from("<H", ent, 0x14)[0] << 16) | \
        struct.unpack_from("<H", ent, 0x1A)[0]
    want(size > 0, "SETTINGS.TXT is empty")
    want(2 <= first <= F.CLUSTERS + 1,
         "SETTINGS.TXT's first cluster is outside the volume")

    # ---- the bytes, off the chain -------------------------------------
    chain = r.chain(first)
    want(len(chain) * F.SEC_PER_CLUS * SEC >= size,
         "the chain is shorter than the directory's file size")
    blob = b""
    for cl in chain:
        blob += r.sec(F.clus_lba(cl))
    text = blob[:size]

    # ---- and what it says ---------------------------------------------
    want(text.startswith(b"#"),
         "the file does not begin with the banner comment")
    want(b"PLAIN TEXT" in text,
         "the banner no longer warns that the password is in plain text")
    want(b"\r" not in text,
         "the file was written with carriage returns - it must write LF only")
    want(text.endswith(b"\n"), "the file does not end with a newline")

    try:
        kv = parse_like_a_pc(text)
    except ValueError as e:
        fails.append("the finished file does not parse: %s" % e)
        return n + 1

    want(kv.get("wifi.network") == NETWORK,
         "wifi.network is %r, expected %r" % (kv.get("wifi.network"), NETWORK))
    want(kv.get("wifi.password.plaintext") == PASSWORD,
         "wifi.password.plaintext is %r, expected %r"
         % (kv.get("wifi.password.plaintext"), PASSWORD))
    want(kv.get("console.baud") == BAUD, "console.baud is wrong")
    want(kv.get("boot.file") == BOOTFILE, "boot.file is wrong")
    want(len(kv) == 4, "the file holds %d keys, expected 4" % len(kv))

    # THE PASSWORD IS IN THE CLEAR AND THAT IS THE DESIGN.  Asserted so
    # that a future change to it breaks a test instead of passing as an
    # improvement nobody reviewed.  See THE PASSWORD in settings.pi4.
    want(PASSWORD.encode() in text,
         "the password is not in the file in plain text - if that is now "
         "deliberate, settings.pi4's header and this gate both have to say so")
    # And the key name carries the warning, which is the only part of it
    # that survives the file being copied somewhere else.
    want(b"wifi.password.plaintext" in text,
         "the key name no longer says plaintext")

    # ---- nothing outside the writable regions moved --------------------
    moved = []
    for lba in range(2048):
        if F.allowed(lba):
            continue
        was = bytes(r.fabricated.s.get(lba, bytearray(SEC)))
        if r.sec(lba) != was:
            moved.append(lba)
    n += 1
    if moved:
        fails.append("sectors outside the FAT and data regions changed: %s"
                     % moved[:8])

    # ---- the two FAT copies still agree --------------------------------
    n += 1
    a = r.disk[F.FAT_BASE * SEC:(F.FAT_BASE + F.FAT_SECS) * SEC]
    b = r.disk[(F.FAT_BASE + F.FAT_SECS) * SEC:
               (F.FAT_BASE + 2 * F.FAT_SECS) * SEC]
    if a != b:
        fails.append("the two FAT copies disagree after the settings writes")

    # ---- and no live chain runs into a free cluster --------------------
    n += 1
    bad = [cl for cl in chain if self_free(r, cl)]
    if bad:
        fails.append("SETTINGS.TXT's chain runs through free clusters: %s" % bad)

    return n


def check_source(lib: pathlib.Path, fails: list) -> int:
    """The store must not know that a block writer exists.

    THE RUNTIME CHECKS ARE THE EVIDENCE; this is the rule they enforce,
    stated where a reader will find it and where a grep can hold it.  The
    two fail differently and that is why both are here: the runtime
    checks catch an arming that SURVIVES a save, this catches one at all
    - including one that some future backend happens to tidy away, which
    would be a store reaching past its seam and getting away with it
    because of an implementation detail on the other side.

    The store's own header has said since it was written that it never
    calls this and does not know such a thing exists.  A rule written
    only in a comment is a rule that gets edited out.

    COMMENTS ARE STRIPPED FIRST, because the header names the procedure
    in prose - it has to, that is where the rule is written down.  The
    strip is a plain split on the comment character, so a semicolon
    inside a string literal truncates that line early; that can only make
    this check quieter, never make it accuse a file that is innocent.
    """
    text = lib.read_text(encoding="utf-8", errors="replace")
    code = "\n".join(ln.split(";", 1)[0] for ln in text.splitlines())
    # Both spellings: FsSetBlockWriter is the filesystem dispatch that the
    # file seam arms, and it reaches FatSetBlockWriter underneath.
    n = code.count("FatSetBlockWriter") + code.count("FsSetBlockWriter")
    if n:
        fails.append(
            "%s CALLS a block-writer setter %d time(s) in code. The settings "
            "store is chip-free core: it reaches a medium through the "
            "file seam and the board's write-all arms and disarms the "
            "block writer around its own single write, which is the one "
            "place on that board able to touch the boot medium. A store "
            "that installs a writer of its own has reached past the seam "
            "to the filesystem, and on the refusal paths nothing then "
            "disarms it." % (lib.name, n))
    return 1


def self_free(r: Run, cl: int) -> bool:
    return r.fat_entry(0, cl) == 0


# =====================================================================
#  --mutate.  A gate that has only ever passed proves nothing about
#  itself, so the library is rebuilt with a deliberate defect in each of
#  these and every one must go RED.
# =====================================================================
MUTATIONS = [
    ("the first '=' rule reversed, so the LAST one splits the line", [
        ("    If PeekA(*buf + i) = #SET_CH_EQUALS\n      eq = i\n      Break\n    EndIf",
         "    If PeekA(*buf + i) = #SET_CH_EQUALS\n      eq = i\n    EndIf"),
    ]),
    ("the key case fold dropped", [
        ("    If c >= #SET_CH_UPPER_A And c <= #SET_CH_UPPER_Z\n      c = c + #SET_CASE_GAP\n    EndIf",
         "    If c >= #SET_CH_UPPER_A And c <= #SET_CH_UPPER_Z\n      c = c\n    EndIf"),
    ]),
    ("a CRLF counted as two lines, so every error line number is wrong", [
        ("      If c = #SET_CH_CR\n        i = i + 1\n        If i < len\n          If PeekA(*buf + i) = #SET_CH_LF\n            i = i + 1\n          EndIf\n        EndIf",
         "      If c = #SET_CH_CR\n        i = i + 1\n        If i < len\n          If PeekA(*buf + i) = #SET_CH_LF\n            i = i + 0\n          EndIf\n        EndIf"),
    ]),
    ("the byte-order mark not skipped", [
        ("          i = 3\n", "          i = 0\n"),
    ]),
    ("the partial-load guard removed, so a bad file's tail is deleted", [
        ("  If set_loadState = 2\n    ProcedureReturn set_Fail(#SET_ERR_UNSAFE_SAVE)\n  EndIf",
         "  If set_loadState = 3\n    ProcedureReturn set_Fail(#SET_ERR_UNSAFE_SAVE)\n  EndIf"),
    ]),
    ("the library installs a block writer of its own", [
        ("  If set_loadState = 2\n    ProcedureReturn set_Fail(#SET_ERR_UNSAFE_SAVE)\n  EndIf",
         "  FatSetBlockWriter(@FatMounted)\n  If set_loadState = 2\n    ProcedureReturn set_Fail(#SET_ERR_UNSAFE_SAVE)\n  EndIf"),
    ]),
    ("the banner no longer written, so the warning leaves the file", [
        ("  While i < #SET_BANNER_LINES\n", "  While i < 0\n"),
    ]),
    ("a value with edge spaces accepted, so it changes across a reboot", [
        ("  c = PeekA(*val)\n  If c = #SET_CH_SPACE Or c = #SET_CH_TAB\n    ProcedureReturn set_Fail(#SET_ERR_VALUE_EDGE)\n  EndIf",
         "  c = PeekA(*val)\n"),
    ]),
    ("the value length limit off by one", [
        ("  If n > #SET_VAL_MAX\n    ProcedureReturn set_Fail(#SET_ERR_VALUE_LONG)\n  EndIf",
         "  If n > 96\n    ProcedureReturn set_Fail(#SET_ERR_VALUE_LONG)\n  EndIf"),
    ]),
    ("the table emptied on a save instead of on a parse", [
        ("  SettingsReset()\n  set_loadState = 0\n", "  set_loadState = 0\n"),
    ]),
    ("secret keys no longer recognised", [
        ('  If set_Contains(@set_wantKey[0], "password") = 1\n    ProcedureReturn 1\n  EndIf',
         '  If set_Contains(@set_wantKey[0], "zzzzzzzz") = 1\n    ProcedureReturn 1\n  EndIf'),
    ]),
    ("the serialiser's bounds check removed", [
        ("  If (set_emitPos + n) > max\n    set_emitFit = 0\n    ProcedureReturn\n  EndIf",
         "  If (set_emitPos + n) > 999999\n    set_emitFit = 0\n    ProcedureReturn\n  EndIf"),
    ]),
]


def mutate_run(name: str, edits: list) -> bool:
    """Rebuild the library with a defect and require the gate to go red.
    Returns True when it does."""
    src = LIB.read_text(encoding="utf-8")
    for find, repl in edits:
        if find not in src:
            print("    (the mutation's anchor text is not in the library - "
                  "the gate cannot break it, so this proves nothing)")
            return False
        src = src.replace(find, repl, 1)

    mut_lib = WORK / "settings_mut.pi4"
    mut_lib.write_text(src, encoding="utf-8")
    prog = SRC.read_text(encoding="utf-8").replace(
        'XIncludeFile "Anvil/Core/settings.pbi"',
        'XIncludeFile "_work/settings_mut.pi4"')
    mut_prog = WORK / "settingsselftest_mut.pi4"
    mut_prog.write_text(prog, encoding="utf-8")

    img = WORK / "settingscheck_mut.img"
    try:
        sym = build_image(mut_prog, img)
        r = execute(sym, img)
    except SystemExit as e:
        print("    (it no longer builds or runs: %s)" % str(e)[:120])
        return True

    fails: list = []
    check_reported(r, fails)
    check_file(r, fails)
    check_source(mut_lib, fails)
    return bool(fails)


def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    args = ap.parse_args()

    globals()["PMFC"] = resolve_compiler(args.compiler)
    WORK.mkdir(exist_ok=True)
    img = WORK / "settingsselftest.img"
    sym = build_image(SRC, img)
    r = execute(sym, img)

    fails: list = []
    total = check_reported(r, fails)
    total += check_file(r, fails)
    total += check_source(LIB, fails)

    if fails:
        for f in fails:
            print("FAIL " + f)
        print("FAILED: %d of %d assertions, %d steps"
              % (len(fails), total, r.steps))
        return 1
    print("PASS: settings.pi4 parsed, serialised and round-tripped a "
          "KEY=VALUE file, and wrote SETTINGS.TXT onto a fabricated FAT32 "
          "volume - %d assertions, %d interpreter steps, nothing written "
          "outside the FAT and data regions" % (total, r.steps))

    if args.mutate:
        print()
        print("--mutate: breaking the library on purpose; each must go RED")
        bad = 0
        for name, edits in MUTATIONS:
            print("  * %s" % name)
            if mutate_run(name, edits):
                print("    RED, as required")
            else:
                print("    *** STILL GREEN - the gate does not catch this ***")
                bad += 1
        for leftover in ("settings_mut.pi4", "settingsselftest_mut.pi4",
                         "settingscheck_mut.img", "settingscheck_mut.img.dbg",
                         "settingscheck_mut.img.sym",
                         "settingscheck_mut.img.sym.meta",
                         "settingscheck_mut.img.asm"):
            p = WORK / leftover
            if p.exists():
                p.unlink()
        if bad:
            return 1
        print("  all %d mutations caught" % len(MUTATIONS))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
