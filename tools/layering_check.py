"""The layering gate: one library, many boards, checked by name resolution.

A shared file under Anvil/ must not depend on a name that only one board
defines. The include graph cannot show that: this language's include model
is flat, so a shared file calls a board procedure with no include edge at
all - the name is simply in scope because the board composition pulled it
in earlier. Exactly one non-test file under Anvil/ includes a board path,
and there are thousands of downward calls behind it. A gate that walked
includes would report a clean tree.

So every rule here is NAME RESOLUTION over the tracked sources.

  1  NO DOWNWARD CALL       a shared file calling a name that only board
                            folders define, unless that name is declared
                            as a seam in Anvil/Hal/hal.pbi or seams.pbi
  2a NO DOWNWARD INCLUDE    a shared file including a board path
  2b NO BOARD EXTENSION     a .pi4/.pi3/.unoq/.rockpi4c file under Anvil/
  3  NO SECOND PROTOCOL     a fingerprint of a wire/container/hardware
                            protocol outside the file that owns it
  4  NO PRIVATE CROSSING    a lower-case-prefixed private name called
                            from outside the file that defines it
  5  ONE DEFINITION         one procedure name defined in two files that
                            can be linked into the same image

Every rule is a RATCHET. Today's findings are recorded per site in
tools/layering_ratchet.json. The gate FAILS when a new site appears or a
recorded count rises. It PASSES when counts fall, and says to refresh the
file with --update. --update may only shrink a count; growing one needs
--allow-growth with a written reason, which is printed loudly.

No compiler, no board, no third-party package. Static text analysis over
`git ls-files`, a few seconds.

    python tools/layering_check.py              run the gate
    python tools/layering_check.py --update     refresh after a fall
    python tools/layering_check.py --self-test  prove each rule goes red

What the parser does not see is written down in docs/LAYERING.md. Read it
before trusting a number here.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RATCHET = Path(__file__).resolve().parent / "layering_ratchet.json"

# The compiler keys off the extension, so the extension set IS the scope.
# .pi3 and .rockpi4c are in it because two other gates forgot them and went
# blind on two whole boards.
SOURCE_EXTS = (".pbi", ".pi4", ".pi3", ".unoq", ".rockpi4c", ".pb")

# A board extension inside the shared tree is the tree lying about itself.
BOARD_EXTS = (".pi4", ".pi3", ".unoq", ".rockpi4c")

SHARED_ROOT = "Anvil/"
BOARD_ROOTS = ("RaspberryPi3/", "RaspberryPi4/", "RockPi4C/", "ArduinoQ/")

# Where the seams are declared. They are declared in prose, in comments,
# beside their contracts - which is the only place a board implementor
# actually reads - so this file reads the comments.
SEAM_FILES = ("Anvil/Hal/hal.pbi", "Anvil/Hal/seams.pbi")

# Words that appear in a seam comment followed by "(" and are not seams.
SEAM_NOISE = {
    "and", "or", "not", "if", "for", "to", "the", "a", "an", "is", "it",
    "see", "note", "eg", "ie", "of", "in", "on", "at", "by", "so", "as",
    "procedure", "procedurereturn", "endprocedure", "macro", "endmacro",
    "select", "case", "default", "endselect", "while", "wend", "repeat",
    "until", "next", "else", "elseif", "endif", "break", "continue",
    "data", "datasection", "enddatasection", "global", "define", "dim",
    "protected", "static", "structure", "endstructure", "compilerif",
    "compilerelse", "compilerendif", "xincludefile", "includefile",
}

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
DEF_RE = re.compile(
    r"^[ \t]*Procedure(?:Naked|C|DLL|CDLL)?(?:\.[A-Za-z]+)?[ \t]+(" + IDENT + r")[ \t]*\(",
    re.IGNORECASE,
)
CALL_RE = re.compile(r"(?<![A-Za-z0-9_.])(@?)(" + IDENT + r")[ \t]*\(")
ADDR_RE = re.compile(r"(?<![A-Za-z0-9_.])@(" + IDENT + r")\b")
INCLUDE_RE = re.compile(r"\b(?:X?IncludeFile)[ \t]*\"([^\"]+)\"", re.IGNORECASE)
PRIVATE_RE = re.compile(r"^([a-z][a-z0-9]*)_[A-Za-z0-9_]", re.ASCII)
SEAM_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(" + IDENT + r")[ \t]*\(")
SEAM_GLOB_RE = re.compile(r"(?<![A-Za-z0-9_])(Hw[A-Za-z][A-Za-z0-9_]*)\*")
COND_OPEN_RE = re.compile(r"^[ \t]*Compiler(?:If|Select)\b", re.IGNORECASE)
COND_CLOSE_RE = re.compile(r"^[ \t]*Compiler(?:EndIf|EndSelect)\b", re.IGNORECASE)

# The one name every program must define once, in its own image.
PROGRAM_ENTRY = {"main"}


# ----------------------------------------------------------------------
#  RULE 3's TABLE. Each entry is one protocol, its owners, and the text
#  that proves a file implements it. The counts live in the ratchet file,
#  not here, so that refreshing a count never edits the definition of
#  what is being counted.
#
#  A pattern is matched against CODE ONLY - comments and string literals
#  are blanked first - because a protocol named in a sentence is a
#  reference and a protocol written in an expression is an implementation.
# ----------------------------------------------------------------------
FINGERPRINTS = (
    {
        "id": "crc32-polynomial",
        "what": "the reflected IEEE 802.3 CRC-32 polynomial in an expression",
        "owners": ("Anvil/Core/crc.pbi",),
        "pattern": r"\$EDB88320",
        # crc.pbi takes its polynomial from the includer on purpose and
        # documents it, so the one spelling it consumes is not a second
        # implementation. Any other spelling is.
        "exempt_line": r"^[ \t]*#CRC_POLY[ \t]*=",
    },
    {
        "id": "sha256-constants",
        "what": "the SHA-256 initial hash or round constants",
        "owners": ("Anvil/Core/sha256.pbi",),
        "pattern": r"\$(?:6A09E667|BB67AE85|428A2F98|71374491)\b",
    },
    {
        "id": "videocore-mailbox-registers",
        "what": "the VideoCore property mailbox register block",
        "owners": (),
        "pattern": r"\$[0-9A-Fa-f]{0,4}00B8[89AB][0-9A-Fa-f]\b",
    },
    {
        "id": "videocore-mailbox-request",
        "what": "the channel-8 property request word",
        "owners": (),
        "pattern": r"\$C0000008\b",
    },
    {
        "id": "dtb-magic",
        "what": "the flattened-device-tree magic",
        "owners": ("Anvil/Core/boot_cmd.pbi",),
        "pattern": r"\$D00DFEED\b",
    },
    {
        "id": "fat-dirent-longname",
        "what": "a FAT directory entry's attribute byte tested against the long-name value",
        "owners": ("Anvil/Storage/fat32.pbi",),
        "pattern": r"(?i)(?:attr[A-Za-z0-9_]*[ \t]*(?:<>|=|&)[ \t]*\$0F\b"
                   r"|\$0F[ \t]*(?:<>|=)[ \t]*attr)",
    },
    {
        "id": "pmfboot-container-magic",
        "what": "the PMFBOOT or P3SLOT header magic as a raw word",
        "owners": ("Anvil/Core/pmfboot.pbi", "Anvil/Storage/ab_record.pbi"),
        "pattern": r"\$0{0,4}544F4(?:F42464D50|C533350)\b",
    },
    {
        "id": "generic-timer-read",
        "what": "a private read of the AArch64 generic timer",
        "owners": ("RaspberryPi4/Lib/timer.pi4",),
        "pattern": r"(?i)\bmrs[ \t]+[a-z0-9]+[ \t]*,[ \t]*cnt(?:pct|vct|frq)_el0\b",
    },
    {
        "id": "aarch64-mmu-attributes",
        "what": "the MAIR value or the block-descriptor attribute words",
        "owners": ("RaspberryPi4/Lib/mmu.pi4",),
        "pattern": r"\$(?:FF440C0400|401|70D|711)(?![0-9A-Fa-f])",
    },
)


# ----------------------------------------------------------------------
#  Reading a source file: strings and comments out, line numbers kept.
# ----------------------------------------------------------------------
def strip_noncode(text):
    """Blank every string literal and comment, keeping every line's length.

    A ";" inside a string is not a comment and a '"' inside a comment does
    not open a string, so this is a character scan and not two regexes.
    """
    out = []
    for line in text.split("\n"):
        buf = []
        i = 0
        n = len(line)
        in_str = False
        escaped = False       # a ~"..." literal honours backslash escapes
        while i < n:
            c = line[i]
            if in_str:
                if escaped and c == "\\" and i + 1 < n:
                    buf.append(" ")
                    buf.append(" ")
                    i += 2
                    continue
                buf.append(" ")
                if c == '"':
                    in_str = False
                i += 1
                continue
            if c == '"':
                in_str = True
                escaped = i > 0 and line[i - 1] == "~"
                buf.append(" ")
                i += 1
                continue
            if c == ";":
                buf.append(" " * (n - i))
                break
            buf.append(c)
            i += 1
        out.append("".join(buf))
    return out


def strip_comments_only(text):
    """Drop comments, keep string literals - what the include rule reads."""
    out = []
    for line in text.split("\n"):
        i = 0
        n = len(line)
        in_str = False
        cut = n
        while i < n:
            c = line[i]
            if in_str:
                if c == '"':
                    in_str = False
                i += 1
                continue
            if c == '"':
                in_str = True
                i += 1
                continue
            if c == ";":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return out


def comment_lines(text):
    """The comment half of the same split, for reading the seam contracts."""
    out = []
    for line in text.split("\n"):
        i = 0
        n = len(line)
        in_str = False
        while i < n:
            c = line[i]
            if in_str:
                if c == '"':
                    in_str = False
                i += 1
                continue
            if c == '"':
                in_str = True
                i += 1
                continue
            if c == ";":
                out.append(line[i + 1:])
                break
            i += 1
    return out


# ----------------------------------------------------------------------
#  The tree.
# ----------------------------------------------------------------------
def tracked_sources(root, use_git):
    if use_git:
        raw = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root), stdout=subprocess.PIPE, check=True,
        ).stdout.decode("utf-8", "replace")
        names = [p for p in raw.split("\0") if p]
    else:
        names = []
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            for f in sorted(filenames):
                p = Path(dirpath, f).relative_to(root)
                names.append(p.as_posix())
    return sorted(p for p in names if p.endswith(SOURCE_EXTS))


def layer_of(path):
    if path.startswith(SHARED_ROOT):
        return "shared"
    for b in BOARD_ROOTS:
        if path.startswith(b):
            return b.rstrip("/")
    return "other"


class Tree(object):
    def __init__(self, root, use_git=True):
        self.root = Path(root)
        self.files = tracked_sources(self.root, use_git)
        self.code = {}
        self.comments = {}
        self.uncommented = {}
        for path in self.files:
            text = (self.root / path).read_text(encoding="utf-8", errors="replace")
            self.code[path] = strip_noncode(text)
            self.comments[path] = comment_lines(text)
            self.uncommented[path] = strip_comments_only(text)

        # name (lowercased - names are case-insensitive in this language)
        # -> the files that define a procedure of that name
        self.defs = {}
        self.def_sites = {}
        self.conditional = set()     # (path, lineno) inside a CompilerIf
        for path in self.files:
            depth = 0
            for lineno, line in enumerate(self.code[path], 1):
                if COND_OPEN_RE.match(line):
                    depth += 1
                elif COND_CLOSE_RE.match(line):
                    depth = max(0, depth - 1)
                m = DEF_RE.match(line)
                if m:
                    key = m.group(1).lower()
                    self.defs.setdefault(key, set()).add(path)
                    self.def_sites.setdefault(key, []).append((path, lineno, m.group(1)))
                    if depth:
                        self.conditional.add((path, lineno))

        self.seams = self.read_seams()

    def read_seams(self):
        """The names the seam files DECLARE, read out of their comments.

        A seam is declared in prose, beside its contract, because that is
        the only place a board implementor actually reads. The declaration
        has one shape and this reads exactly that shape: the name OPENS its
        line, with its arguments -

            ;                 UartDrain()            block, bounded, until
            ;                 HwLinkSend(kind, buf, n, ms)

        or it opens a whole family with a star -

            ;    HwGpio*   (#CAP_GPIO)  general-purpose I/O

        and several may share one line, separated by "/" -

            ;                 UartMessageBegin() / UartMessageEnd()

        A name that merely APPEARS in an English sentence is not a
        declaration. That matters: a loose reading here silently forgives
        real downward calls, and forgiving is the one failure a ratchet
        cannot recover from. The cost of the strict reading is that a
        contract written some other way is reported as a violation, which
        is loud and fixable - either reword the line or move the library.
        """
        names = set()
        globs = []
        for path in SEAM_FILES:
            if path not in self.comments:
                continue
            for line in self.comments[path]:
                for segment in line.split("/"):
                    segment = segment.lstrip(" \t")
                    m = re.match(r"(" + IDENT + r")[ \t]*\(", segment)
                    if m and m.group(1).lower() not in SEAM_NOISE:
                        names.add(m.group(1).lower())
                        continue
                    m = re.match(r"(Hw[A-Za-z][A-Za-z0-9_]*)\*", segment)
                    if m:
                        globs.append(m.group(1).lower())
        return names, sorted(set(globs))

    def is_seam(self, name):
        names, globs = self.seams
        low = name.lower()
        if low in names:
            return True
        for g in globs:
            if low.startswith(g):
                return True
        return False


# ----------------------------------------------------------------------
#  RULE 1 - no downward call.
# ----------------------------------------------------------------------
def rule_downward_call(tree):
    findings = {}
    details = []
    for path in tree.files:
        if layer_of(path) != "shared":
            continue
        for lineno, line in enumerate(tree.code[path], 1):
            if DEF_RE.match(line):
                continue
            seen = []
            for m in CALL_RE.finditer(line):
                seen.append(m.group(2))
            for m in ADDR_RE.finditer(line):
                seen.append(m.group(1))
            for raw in seen:
                key = raw.lower()
                owners = tree.defs.get(key)
                if not owners:
                    continue
                if any(layer_of(o) == "shared" for o in owners):
                    continue
                if tree.is_seam(raw):
                    continue
                canon = tree.def_sites[key][0][2]
                findings.setdefault(path, {})
                findings[path][canon] = findings[path].get(canon, 0) + 1
                details.append((path, lineno, canon, sorted(owners)))
    return findings, details


# ----------------------------------------------------------------------
#  RULE 2a - no downward include.  RULE 2b - no board extension under Anvil/.
# ----------------------------------------------------------------------
def resolve_include(includer, target):
    """An include path, as a repo-root path.

    A composition writes them repo-root relative and quoted, but not all of
    them: Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4 reaches its board file with
    "../../../RaspberryPi4/Lib/v3dqpu.pi4", and a gate that only understood
    the first spelling would have missed the single known violation of this
    rule in the whole tree.
    """
    target = target.replace("\\", "/")
    if target.startswith(SHARED_ROOT) or target.startswith(BOARD_ROOTS):
        return target
    joined = os.path.normpath(
        os.path.join(os.path.dirname(includer), target)).replace("\\", "/")
    return joined


def rule_downward_include(tree):
    findings = {}
    details = []
    for path in tree.files:
        if layer_of(path) != "shared":
            continue
        for lineno, line in enumerate(tree.uncommented[path], 1):
            for m in INCLUDE_RE.finditer(line):
                target = resolve_include(path, m.group(1))
                if layer_of(target) in ("shared", "other"):
                    continue
                findings.setdefault(path, {})
                findings[path][target] = findings[path].get(target, 0) + 1
                details.append((path, lineno, target))
    return findings, details


def rule_board_extension(tree):
    return sorted(p for p in tree.files
                  if p.startswith(SHARED_ROOT) and p.endswith(BOARD_EXTS))


# ----------------------------------------------------------------------
#  RULE 3 - no second implementation of a protocol.
# ----------------------------------------------------------------------
def rule_protocol(tree):
    findings = {}
    details = []
    for fp in FINGERPRINTS:
        pat = re.compile(fp["pattern"])
        exempt = re.compile(fp["exempt_line"]) if fp.get("exempt_line") else None
        for path in tree.files:
            if path in fp["owners"]:
                continue
            hits = 0
            for lineno, line in enumerate(tree.code[path], 1):
                if exempt is not None and exempt.match(line):
                    continue
                found = len(pat.findall(line))
                if found:
                    hits += found
                    details.append((fp["id"], path, lineno, line.strip()[:90]))
            if hits:
                findings.setdefault(fp["id"], {})[path] = hits
    return findings, details


# ----------------------------------------------------------------------
#  RULE 4 - no private-namespace crossing.
#
#  The prefix list is DERIVED, not written down: any procedure whose name
#  begins with a lower-case word and an underscore declares that word as a
#  private namespace, and the files that define such names own it. A call
#  to one of them from any other file has reached inside a library.
# ----------------------------------------------------------------------
def private_prefix(name):
    m = PRIVATE_RE.match(name)
    return m.group(1) if m else None


def rule_private_namespace(tree):
    owners = {}          # prefix -> set of files that define names in it
    member = {}          # lowercased name -> prefix
    for key, sites in tree.def_sites.items():
        prefix = private_prefix(sites[0][2])
        if prefix is None:
            continue
        member[key] = prefix
        for path, _, _ in sites:
            owners.setdefault(prefix, set()).add(path)

    findings = {}
    details = []
    for path in tree.files:
        for lineno, line in enumerate(tree.code[path], 1):
            if DEF_RE.match(line):
                continue
            seen = [m.group(2) for m in CALL_RE.finditer(line)]
            seen += [m.group(1) for m in ADDR_RE.finditer(line)]
            for raw in seen:
                key = raw.lower()
                prefix = member.get(key)
                if prefix is None:
                    continue
                if path in owners[prefix]:
                    continue
                canon = tree.def_sites[key][0][2]
                findings.setdefault(path, {})
                findings[path][canon] = findings[path].get(canon, 0) + 1
                details.append((path, lineno, canon, sorted(owners[prefix])))
    return findings, details


# ----------------------------------------------------------------------
#  RULE 5 - one definition per name, across files that can share an image.
#
#  Two board folders cannot be linked into one image, so the same name in
#  RaspberryPi3/ and RaspberryPi4/ is not a collision. Anything else is:
#  shared with shared, shared with a board, or twice inside one board.
# ----------------------------------------------------------------------
def is_program_root(path):
    """A file that is compiled as its own program, not included into one.

    Everything under a Tests/ or Examples/ directory is one image on its
    own. Two of those are never linked together, and one of them cannot be
    linked to a library it re-declares a name from - the compiler would
    refuse that, which is how this language reports it. So a stub inside a
    gate is not a second implementation of anything.
    """
    parts = path.split("/")
    return "Tests" in parts or "Examples" in parts


def can_share_an_image(a, b):
    if is_program_root(a) or is_program_root(b):
        return False
    la, lb = layer_of(a), layer_of(b)
    if la == "other" or lb == "other":
        return False
    if la == lb:
        return True
    return la == "shared" or lb == "shared"


def rule_one_definition(tree):
    findings = {}
    for key, sites in sorted(tree.def_sites.items()):
        if len(sites) < 2 or key in PROGRAM_ENTRY:
            continue
        # A declared seam has one implementation PER IMAGE, chosen when the
        # composition picks which backend it includes. Anvil/Storage's file
        # seam and the UNO Q's UEFI one are alternatives, not copies.
        if tree.is_seam(sites[0][2]):
            continue
        clash = []
        for i, (pa, na, canon) in enumerate(sites):
            for pb, nb, _ in sites[i + 1:]:
                if (pa, na) in tree.conditional or (pb, nb) in tree.conditional:
                    continue    # exclusive CompilerIf branches, one survives
                if can_share_an_image(pa, pb):
                    # The FILES, not file:line. A line number that shifts
                    # when somebody edits above a procedure is not a new
                    # definition, and a ratchet that thinks it is fails on
                    # every unrelated commit until people stop running it.
                    clash.append(pa)
                    clash.append(pb)
        if clash:
            findings[sites[0][2]] = sorted(set(clash))
    return findings


# ----------------------------------------------------------------------
#  The ratchet.
# ----------------------------------------------------------------------
EMPTY = {
    "downward_call": {},
    "downward_include": {},
    "board_extension_under_anvil": [],
    "protocol": {},
    "private_namespace": {},
    "one_definition": {},
}


def load_ratchet():
    if not RATCHET.exists():
        return dict((k, json.loads(json.dumps(v))) for k, v in EMPTY.items())
    data = json.loads(RATCHET.read_text(encoding="utf-8"))
    out = dict((k, json.loads(json.dumps(v))) for k, v in EMPTY.items())
    out.update(data.get("rules", {}))
    return out


def save_ratchet(rules, note):
    body = {
        "note": note,
        "rules": rules,
    }
    RATCHET.write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def widest(a, b):
    """Merge two rule sets, keeping whichever side records MORE.

    The baseline was built this way, from HEAD and from a working tree
    five lanes were live in at once, so that no lane could be failed by
    the gate for work that was already in flight the day it was written.
    Merging the other way - keeping the smaller - would have made the
    gate red on arrival for everyone, which is how a gate gets disabled.
    """
    out = {}
    for key in set(a) | set(b):
        x, y = a.get(key), b.get(key)
        if x is None or y is None:
            out[key] = x if y is None else y
        elif isinstance(x, list):
            out[key] = sorted(set(x) | set(y))
        elif isinstance(x, dict):
            out[key] = widest(x, y)
        else:
            out[key] = max(x, y)
    return out


def compare_nested(rule, current, recorded):
    """Two levels of {outer: {inner: count}}. Returns (new, grown, fallen)."""
    new, grown, fallen = [], [], []
    for outer in sorted(current):
        for inner in sorted(current[outer]):
            now = current[outer][inner]
            was = recorded.get(outer, {}).get(inner)
            if was is None:
                new.append((rule, outer, inner, 0, now))
            elif now > was:
                grown.append((rule, outer, inner, was, now))
            elif now < was:
                fallen.append((rule, outer, inner, was, now))
    for outer in sorted(recorded):
        for inner in sorted(recorded[outer]):
            if current.get(outer, {}).get(inner) is None:
                fallen.append((rule, outer, inner, recorded[outer][inner], 0))
    return new, grown, fallen


def compare_list(rule, current, recorded):
    cur, rec = set(current), set(recorded)
    new = [(rule, x, "", 0, 1) for x in sorted(cur - rec)]
    fallen = [(rule, x, "", 1, 0) for x in sorted(rec - cur)]
    return new, [], fallen


def compare_map(rule, current, recorded):
    """{name: [sites]} - a name is new, or its site list is longer."""
    new, grown, fallen = [], [], []
    for name in sorted(current):
        now = len(current[name])
        was = recorded.get(name)
        if was is None:
            new.append((rule, name, ", ".join(current[name]), 0, now))
        elif now > len(was):
            grown.append((rule, name, ", ".join(current[name]), len(was), now))
        elif now < len(was):
            fallen.append((rule, name, "", len(was), now))
    for name in sorted(recorded):
        if name not in current:
            fallen.append((rule, name, "", len(recorded[name]), 0))
    return new, grown, fallen


# ----------------------------------------------------------------------
#  Reporting.
# ----------------------------------------------------------------------
def total(nested):
    return sum(sum(inner.values()) for inner in nested.values())


def summarise(tree, results, details, out):
    dcall, dincl, bext, proto, priv, onedef = results
    seam_names, seam_globs = tree.seams

    out.append("LAYERING GATE")
    out.append("  tracked sources        %d" % len(tree.files))
    out.append("  procedure names        %d" % len(tree.def_sites))
    out.append("  seam names declared    %d, plus %d Hw* families"
               % (len(seam_names), len(seam_globs)))
    out.append("")

    out.append("RULE 1  no downward call")
    out.append("  shared files reaching down   %d" % len(dcall))
    out.append("  call sites                   %d" % total(dcall))
    names = {}
    for f in dcall:
        for n, c in dcall[f].items():
            names[n] = names.get(n, 0) + c
    out.append("  distinct board names called  %d" % len(names))
    ranked = sorted(dcall.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    out.append("  top 20 shared files:")
    for path, hits in ranked[:20]:
        out.append("    %5d  %-55s %d names"
                   % (sum(hits.values()), path, len(hits)))
    per_board = {}
    for path, lineno, name, owners in details[0]:
        for o in owners:
            per_board[layer_of(o)] = per_board.get(layer_of(o), 0) + 1
    out.append("  by defining board folder (a name on two boards counts on both):")
    for board in sorted(per_board):
        out.append("    %5d  %s" % (per_board[board], board))
    out.append("")

    out.append("RULE 2  no downward include, no board extension under %s" % SHARED_ROOT)
    out.append("  downward includes            %d" % total(dincl))
    for path in sorted(dincl):
        for target, count in sorted(dincl[path].items()):
            out.append("    %s -> %s (%d)" % (path, target, count))
    out.append("  board-extension files        %d" % len(bext))
    out.append("")

    out.append("RULE 3  no second implementation of a protocol")
    for fp in FINGERPRINTS:
        hits = proto.get(fp["id"], {})
        owners = ", ".join(fp["owners"]) if fp["owners"] else "NONE YET"
        out.append("  %-30s %4d sites in %2d files   owner: %s"
                   % (fp["id"], sum(hits.values()), len(hits), owners))
        for path in sorted(hits):
            out.append("      %4d  %s" % (hits[path], path))
    out.append("")

    out.append("RULE 4  no private-namespace crossing")
    out.append("  crossing sites               %d in %d files"
               % (total(priv), len(priv)))
    ranked = sorted(priv.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    for path, hits in ranked[:20]:
        out.append("    %5d  %-55s %s"
                   % (sum(hits.values()), path,
                      ", ".join(sorted(hits)[:4])))
    out.append("")

    out.append("RULE 5  one definition per name")
    out.append("  names defined more than once %d" % len(onedef))
    for name in sorted(onedef)[:20]:
        out.append("    %-28s %s" % (name, "  ".join(onedef[name])))
    out.append("")


def run(tree):
    dcall, d1 = rule_downward_call(tree)
    dincl, d2 = rule_downward_include(tree)
    bext = rule_board_extension(tree)
    proto, d3 = rule_protocol(tree)
    priv, d4 = rule_private_namespace(tree)
    onedef = rule_one_definition(tree)
    return (dcall, dincl, bext, proto, priv, onedef), (d1, d2, d3, d4)


def as_rules(results):
    dcall, dincl, bext, proto, priv, onedef = results
    return {
        "downward_call": dcall,
        "downward_include": dincl,
        "board_extension_under_anvil": bext,
        "protocol": proto,
        "private_namespace": priv,
        "one_definition": onedef,
    }


def check(results, recorded):
    rules = as_rules(results)
    new, grown, fallen = [], [], []
    for rule in ("downward_call", "downward_include", "protocol", "private_namespace"):
        a, b, c = compare_nested(rule, rules[rule], recorded.get(rule, {}))
        new += a
        grown += b
        fallen += c
    a, b, c = compare_list("board_extension_under_anvil",
                           rules["board_extension_under_anvil"],
                           recorded.get("board_extension_under_anvil", []))
    new += a
    grown += b
    fallen += c
    a, b, c = compare_map("one_definition", rules["one_definition"],
                          recorded.get("one_definition", {}))
    new += a
    grown += b
    fallen += c
    return new, grown, fallen


# ----------------------------------------------------------------------
#  The self-test. A throwaway tree with one planted violation of each rule
#  and one legal seam call, and every rule has to go red on its own plant
#  and stay quiet about the seam.
# ----------------------------------------------------------------------
SELF_TEST_TREE = {
    "Anvil/Hal/hal.pbi": (
        "; THE CONSOLE BYTES\n"
        ";     UartWriteStr(*s)   a NUL-terminated string\n"
        ";     HwGpio*  general-purpose I/O\n"
        ";         HwGpioWrite(pin, lvl)\n"
    ),
    "Anvil/Hal/seams.pbi": "#SVCCAP_STORAGE = 0\n",
    "Anvil/Core/legal.pbi": (
        "Procedure.i CoreSaysHello()\n"
        "  UartWriteStr(@\"hello\")\n"          # legal: declared seam
        "  HwGpioWrite(4, 1)\n"                 # legal: declared Hw* family
        "  ProcedureReturn 0\n"
        "EndProcedure\n"
    ),
    "Anvil/Core/reaches_down.pbi": (
        "Procedure.i CoreReachesDown()\n"
        "  BoardOnlyThing()\n"                  # RULE 1
        "  ProcedureReturn 0\n"
        "EndProcedure\n"
    ),
    "Anvil/Core/includes_down.pbi": (
        "XIncludeFile \"RaspberryPi4/Lib/board_lib.pi4\"\n"    # RULE 2a
    ),
    "Anvil/Graphics/Vulkan/includes_down_relative.pbi": (
        "XIncludeFile \"../../../RaspberryPi4/Lib/board_lib.pi4\"\n"   # RULE 2a
    ),
    "Anvil/Graphics/planted_backend.pi4": (      # RULE 2b
        "Procedure PlantedBackend()\n"
        "EndProcedure\n"
    ),
    "Anvil/Core/second_crc.pbi": (
        "Procedure.i SecondCrc(c.i)\n"
        "  c = (c >> 1) ! $EDB88320\n"          # RULE 3
        "  ProcedureReturn c\n"
        "EndProcedure\n"
    ),
    "Anvil/Core/comment_only.pbi": (
        "; the polynomial is $EDB88320 and this line is a comment\n"
        "Procedure CommentOnly()\n"
        "  Debug \"$EDB88320 in a string\"\n"
        "EndProcedure\n"
    ),
    "RaspberryPi4/Lib/board_lib.pi4": (
        "Procedure.i BoardOnlyThing()\n"
        "  ProcedureReturn 1\n"
        "EndProcedure\n"
        "Procedure.i zz_Helper()\n"
        "  ProcedureReturn 2\n"
        "EndProcedure\n"
        "Procedure.i UartWriteStr(s.i)\n"
        "  ProcedureReturn 0\n"
        "EndProcedure\n"
        "Procedure.i HwGpioWrite(pin.i, lvl.i)\n"
        "  ProcedureReturn 0\n"
        "EndProcedure\n"
        "Procedure.i TwiceDefined()\n"
        "  ProcedureReturn 0\n"
        "EndProcedure\n"
    ),
    "RaspberryPi4/Lib/crosses.pi4": (
        "Procedure.i Crosses()\n"
        "  ProcedureReturn zz_Helper()\n"       # RULE 4
        "EndProcedure\n"
        "Procedure.i TwiceDefined()\n"          # RULE 5
        "  ProcedureReturn 1\n"
        "EndProcedure\n"
    ),
}


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in sorted(SELF_TEST_TREE.items()):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        tree = Tree(root, use_git=False)
        (dcall, dincl, bext, proto, priv, onedef), _ = run(tree)

        def want(ok, label):
            print("  %-4s %s" % ("PASS" if ok else "FAIL", label))
            if not ok:
                failures.append(label)

        want("Anvil/Core/reaches_down.pbi" in dcall
             and "BoardOnlyThing" in dcall.get("Anvil/Core/reaches_down.pbi", {}),
             "rule 1 red on the planted downward call")
        want("Anvil/Core/legal.pbi" not in dcall,
             "rule 1 quiet on the declared console seam and the Hw* family")
        want(dincl.get("Anvil/Core/includes_down.pbi", {}).get(
             "RaspberryPi4/Lib/board_lib.pi4") == 1,
             "rule 2a red on the planted downward include")
        want(dincl.get("Anvil/Graphics/Vulkan/includes_down_relative.pbi", {}).get(
             "RaspberryPi4/Lib/board_lib.pi4") == 1,
             "rule 2a red on the same include written as a relative path")
        want(bext == ["Anvil/Graphics/planted_backend.pi4"],
             "rule 2b red on the planted board-extension file under Anvil/")
        crc = proto.get("crc32-polynomial", {})
        want(crc.get("Anvil/Core/second_crc.pbi") == 1,
             "rule 3 red on the planted second CRC-32")
        want("Anvil/Core/comment_only.pbi" not in crc,
             "rule 3 quiet on the same constant in a comment and a string")
        want(priv.get("RaspberryPi4/Lib/crosses.pi4", {}).get("zz_Helper") == 1,
             "rule 4 red on the planted private-namespace crossing")
        want("RaspberryPi4/Lib/board_lib.pi4" not in priv,
             "rule 4 quiet inside the namespace's own file")
        want("TwiceDefined" in onedef and len(onedef["TwiceDefined"]) == 2,
             "rule 5 red on the planted duplicate definition")
        want("UartWriteStr" not in onedef,
             "rule 5 quiet on one seam implementation per board")

        recorded = as_rules((dcall, dincl, bext, proto, priv, onedef))
        new, grown, fallen = check((dcall, dincl, bext, proto, priv, onedef), recorded)
        want(not new and not grown and not fallen,
             "the ratchet is quiet when the tree matches what it recorded")

        smaller = json.loads(json.dumps(recorded))
        smaller["downward_call"]["Anvil/Core/reaches_down.pbi"]["BoardOnlyThing"] = 0
        new, grown, fallen = check((dcall, dincl, bext, proto, priv, onedef), smaller)
        want(bool(grown) and not new,
             "the ratchet refuses a count that rose")

        bigger = json.loads(json.dumps(recorded))
        bigger["downward_call"]["Anvil/Core/reaches_down.pbi"]["BoardOnlyThing"] = 9
        new, grown, fallen = check((dcall, dincl, bext, proto, priv, onedef), bigger)
        want(bool(fallen) and not new and not grown,
             "the ratchet reports a count that fell and does not fail")

    print("")
    if failures:
        print("SELF-TEST FAILED: %d of the planted cases did not behave"
              % len(failures))
        return 1
    print("SELF-TEST PASSED: every rule goes red on its own planted violation,")
    print("the declared seam call is allowed, and the ratchet moves one way.")
    return 0


# ----------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="The layering gate. One library, many boards.")
    ap.add_argument("--update", action="store_true",
                    help="rewrite the ratchet file from the tree. Counts may "
                         "only fall.")
    ap.add_argument("--allow-growth", metavar="REASON", default=None,
                    help="with --update, record counts that ROSE. The reason "
                         "is printed and stored.")
    ap.add_argument("--self-test", action="store_true",
                    help="build a throwaway tree with one violation of each "
                         "rule and prove each one goes red.")
    ap.add_argument("--details", action="store_true",
                    help="print every site, file:line, instead of a summary.")
    ap.add_argument("--tree", metavar="DIR", default=None,
                    help="analyse this directory instead of the git index.")
    ap.add_argument("--also", metavar="DIR", default=None,
                    help="with --update, analyse DIR as well and record the "
                         "LARGER of the two counts. How the baseline covered "
                         "both HEAD and a working tree other lanes were live "
                         "in: git archive HEAD | tar -x -C DIR.")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    root = Path(args.tree) if args.tree else ROOT
    tree = Tree(root, use_git=args.tree is None)
    results, details = run(tree)

    out = []
    summarise(tree, results, details, out)
    print("\n".join(out))

    if args.details:
        print("DETAIL - every site")
        for path, lineno, name, owners in details[0]:
            print("  downward-call     %s:%d  %s  <- %s"
                  % (path, lineno, name, ", ".join(owners)))
        for path, lineno, target in details[1]:
            print("  downward-include  %s:%d  %s" % (path, lineno, target))
        for fid, path, lineno, text in details[2]:
            print("  protocol          %s:%d  [%s] %s" % (path, lineno, fid, text))
        for path, lineno, name, owners in details[3]:
            print("  private-crossing  %s:%d  %s  <- %s"
                  % (path, lineno, name, ", ".join(owners)))
        print("")

    recorded = load_ratchet()
    new, grown, fallen = check(results, recorded)

    if args.update:
        if grown and not args.allow_growth:
            print("REFUSED: --update may only shrink a count, and %d rose."
                  % len(grown))
            for rule, outer, inner, was, now in grown[:20]:
                print("    %s  %s  %s  %d -> %d" % (rule, outer, inner, was, now))
            print("")
            print("If the rise is deliberate, say why:")
            print("    python tools/layering_check.py --update "
                  "--allow-growth \"<reason>\"")
            return 1
        if new and not args.allow_growth:
            print("REFUSED: --update may only shrink, and %d new site%s appeared."
                  % (len(new), "" if len(new) == 1 else "s"))
            for rule, outer, inner, _was, now in new[:20]:
                print("    %s  %s  %s  (new, %d)" % (rule, outer, inner, now))
            print("")
            print("If the new sites are deliberate, say why:")
            print("    python tools/layering_check.py --update "
                  "--allow-growth \"<reason>\"")
            return 1
        note = "Recorded from the tree by tools/layering_check.py --update."
        if args.allow_growth:
            bar = "*" * 68
            print(bar)
            print("GROWTH ALLOWED. The layering ratchet has been LOOSENED.")
            print("REASON: %s" % args.allow_growth)
            print("%d new sites, %d counts raised." % (len(new), len(grown)))
            print(bar)
            note = "GROWTH ALLOWED: " + args.allow_growth
        rules = as_rules(results)
        if args.also:
            other, _ = run(Tree(Path(args.also), use_git=False))
            rules = widest(rules, as_rules(other))
            # The directory itself is not recorded: it is a scratch export
            # and a machine path has no business in a tracked file.
            note += " Widened against a second tree."
        save_ratchet(rules, note)
        print("Recorded %s" % RATCHET.relative_to(ROOT).as_posix())
        return 0

    if new or grown:
        print("LAYERING GATE FAILED")
        for rule, outer, inner, was, now in new:
            print("  NEW      %-24s %s  %s  (%d)" % (rule, outer, inner, now))
        for rule, outer, inner, was, now in grown:
            print("  ROSE     %-24s %s  %s  %d -> %d"
                  % (rule, outer, inner, was, now))
        print("")
        print("A shared file may not depend on one board. Move the library, or")
        print("declare the seam in Anvil/Hal/hal.pbi and call that. See")
        print("docs/LAYERING.md.")
        return 1

    if fallen:
        print("LAYERING GATE PASSED, and %d recorded sites are gone." % len(fallen))
        for rule, outer, inner, was, now in fallen[:20]:
            print("  FELL     %-24s %s  %s  %d -> %d"
                  % (rule, outer, inner, was, now))
        if len(fallen) > 20:
            print("  ... and %d more" % (len(fallen) - 20))
        print("")
        print("Refresh the ratchet in the same commit so the ground you won")
        print("cannot be given back:")
        print("    python tools/layering_check.py --update")
        return 0

    print("LAYERING GATE PASSED. Nothing new, nothing grown.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
