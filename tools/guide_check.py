#!/usr/bin/env python3
"""guide_check.py - the Anvil Guide cannot fall behind the code without this failing.

    python tools/guide_check.py              check; exit 0 PASS, 1 FAIL
    python tools/guide_check.py --write      regenerate docs/guide/24_every_command.txt, then check
    python tools/guide_check.py --hook       the pre-commit form: the same check, terse on PASS

WHY IT EXISTS. On 2026-10-21 the book was found weeks behind the monitor:
`programs` and run-by-name (e5f6339), booting from a path or 2:/ (build
251) and the bare-cable DHCP server (dhcpd.pbi) were all missing or
contradicted, and about 25 Pi 4 commands appeared nowhere in it. The rule
"the book is updated in the same commit" (docs/GUIDE.md) was written down
and nothing enforced it. This enforces it, and .githooks/pre-commit runs it
on every commit (git config core.hooksPath .githooks, once per clone).

WHAT IT CHECKS - each one prints how many things it examined, because a
check that examined nothing has not passed (chapter 10):

1. EVERY COMMAND IS DOCUMENTED. Each board's dispatcher (`If`/`ElseIf
   WordIs("...")` at the dispatch level of board.pi4, board.pi3,
   board.unoq) is read, and every command line must be documented: one of
   its words is an entry in that board's `help` (Core Help() plus the
   board's own help tail) or appears in the guide's prose. A gap that
   existed when this was written is listed in docs/guide/00_COMMANDS_OWED.txt
   and only reported; that list may only SHRINK - a new gap fails, and an
   owed entry that is now documented (or no longer a command) fails until
   it is struck off.

2. THE COMMAND CHAPTER IS THE MONITOR'S OWN HELP. docs/guide/24_every_command.txt
   is generated from Anvil/Core/help.pbi and each board's help tail. If the
   help text changes and the chapter is not regenerated (--write), this fails.

3. QUOTED MESSAGES STILL EXIST. A @FRAG whose preceding paragraph says
   "quoted from `path`" is a claim that the board prints those lines; each
   line must still be one the file prints, rebuilt from its Print/PrintN
   statements in order, with anything worked out at run time (an address,
   a name - <placeholders> in the book) matching anything. A reworded or
   deleted message fails here instead of living on in the book.

4. TOOL FLAGS STILL EXIST. Every --flag written on a line that names
   tools/<name>.py (or inside a @FRAG that follows one) must still be in
   that tool's source.

5. THE INDEX LISTS THE CHAPTERS. docs/GUIDE.md's table links every chapter
   file and nothing that is not one.

6. THE PDF IS THE CHAPTERS. tools/render_guide.py writes
   docs/guide/AnvilGuide.pdf.sources, the SHA-256 of the chapters the PDF
   was rendered from. A chapter edited without re-rendering fails here.
"""
import glob
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "docs", "guide")
GENERATED = os.path.join(GUIDE, "24_every_command.txt")
OWED = os.path.join(GUIDE, "00_COMMANDS_OWED.txt")
STAMP = os.path.join(GUIDE, "AnvilGuide.pdf.sources")
HELP = os.path.join(ROOT, "Anvil", "Core", "help.pbi")
BOARDS = [  # (key, title, dispatcher)
    ("pi4", "Raspberry Pi 4", os.path.join(ROOT, "RaspberryPi4", "Board", "board.pi4")),
    ("pi3", "Raspberry Pi 3", os.path.join(ROOT, "RaspberryPi3", "Board", "board.pi3")),
    ("unoq", "Arduino UNO Q", os.path.join(ROOT, "ArduinoQ", "Board", "board.unoq")),
]
# calls inside the help text whose output is worked out at run time
PLACEHOLDERS = {
    "PutAddr": "<address>",
    "PutWindows": "  <this board's payload windows, printed at run time>",
    "PutMonitorMap": "  <this board's memory map, printed at run time>",
    "PutWidthRule": "  <the .b/.w/.l width rule, worked out from the width table at run time>",
    "PrintDec": "<number>",
}
DISPATCH = re.compile(r'^    (?:Else)?If\b.*WordIs\("')


def read(path):
    return open(path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")


def chapters():
    """The rendered chapters: 00_ files are the book's own notes and are never rendered."""
    return sorted(c for c in glob.glob(os.path.join(GUIDE, "[0-9][0-9]_*.txt"))
                  if not os.path.basename(c).startswith("00_"))


# ---------------------------------------------------------------- the help text

def string_value(expr):
    """A PureBasic string expression of literals and Chr(n) joined by +, or None."""
    out, pos, want_term = "", 0, True
    for m in re.finditer(r'\s*(?:"([^"]*)"|Chr\((\d+)\)|(\+))\s*', expr):
        if m.start() != pos:
            return None
        pos = m.end()
        if m.group(3):
            if want_term:
                return None
            want_term = True
            continue
        if not want_term:
            return None
        out += m.group(1) if m.group(1) is not None else chr(int(m.group(2)))
        want_term = False
    if pos != len(expr) or want_term:
        return None
    return out


def help_lines(stmts):
    """Statements (source lines) -> the lines they print, with placeholders."""
    lines, cur = [], ""
    for raw in stmts:
        s = raw.strip()
        if not s or s.startswith(";"):
            continue
        m = re.fullmatch(r"(PrintN|Print)\((.*)\)", s)
        if m:
            v = string_value(m.group(2))
            cur += v if v is not None else "<...>"
            if m.group(1) == "PrintN":
                lines.append(cur.rstrip())
                cur = ""
            continue
        if s == "PrintNl()":
            lines.append(cur.rstrip())
            cur = ""
            continue
        m = re.fullmatch(r"CompilerIf #CAP_(\w+) = 1", s)
        if m:
            if cur:
                lines.append(cur.rstrip())
                cur = ""
            lines.append("(only on a board with %s:)" % m.group(1))
            continue
        if s in ("CompilerEndIf", "CompilerElse"):
            continue
        m = re.fullmatch(r"(\w+)\(.*\)", s)
        if m and m.group(1) in PLACEHOLDERS:
            ph = PLACEHOLDERS[m.group(1)]
            if ph.startswith("  "):
                if cur:
                    lines.append(cur.rstrip())
                    cur = ""
                lines.append(ph)
            else:
                cur += ph
            continue
        cur += "<...>"
    if cur:
        lines.append(cur.rstrip())
    return lines


def core_help():
    text = read(HELP).split("\n")
    start = next(i for i, l in enumerate(text) if l.startswith("Procedure Help()"))
    end = next(i for i in range(start, len(text)) if text[i].startswith("EndProcedure"))
    return help_lines(text[start + 1:end])


def board_help_tail(path):
    """The lines a board's help arm prints after Help(), up to the next dispatcher arm."""
    text = read(path).split("\n")
    for i, l in enumerate(text):
        if DISPATCH.match(l) and 'WordIs("help")' in l:
            body = []
            for k in range(i + 1, len(text)):
                if re.match(r"^    (ElseIf|Else|EndIf)\b", text[k]):
                    break
                body.append(text[k])
            body = [b for b in body if b.strip() != "Help()"]
            return help_lines(body)
    return []


def help_entries(lines):
    """Command words a help text documents: the first word of an entry line, and its [aliases]."""
    words = set()
    for l in lines:
        m = re.match(r"^ {2,6}([A-Za-z0-9_.?-]+)(\s|$)", l)
        if m:
            words.add(m.group(1))
        m = re.search(r"\[([^\]]+)\]\s*$", l)
        if m:
            words.update(w.strip() for w in m.group(1).split(","))
    return words


def generated_chapter():
    out = [
        "; GENERATED by tools/guide_check.py --write from Anvil/Core/help.pbi and each",
        "; board's help tail. Do not edit: change the help text and regenerate.",
        "@CHAPTER Every command",
        "",
        "@INTRO This is the monitor's own `help`, as each board prints it, so it can never say less than the board does.",
        "",
        "Every command the monitor accepts is listed here with the text its",
        "`help` prints. The chapters before this one explain the commands",
        "people use most and show what they print; this chapter is the",
        "complete list. It is generated from the help text itself by",
        "`tools/guide_check.py --write`, and the same tool fails a commit that",
        "changes the help without regenerating it. Lines in angle brackets are",
        "worked out by the board when it prints them, and a line saying",
        "\"only on a board with\" marks text a board prints only when it has",
        "that capability.",
        "",
        "@SECTION Every board",
        "",
        "@FRAG",
    ] + core_help() + ["@ENDFRAG", ""]
    for key, title, path in BOARDS:
        tail = board_help_tail(path)
        if any(t.strip() for t in tail):
            out += ["@SECTION %s adds" % title, "", "@FRAG"] + tail + ["@ENDFRAG", ""]
    # a @FRAG line may not start with @ (it would be markup); none does today
    return "\n".join(out).rstrip("\n") + "\n"


# ---------------------------------------------------------------- the checks

def check_commands(guide_text, fails, notes):
    owed = {}
    if os.path.exists(OWED):
        for l in read(OWED).split("\n"):
            l = l.split(";")[0].strip()
            if l:
                b, w = l.split()[:2]
                owed[(b, w)] = True
    core = help_entries(core_help())
    seen_gaps, examined = set(), 0
    for key, title, path in BOARDS:
        documented = core | help_entries(board_help_tail(path))
        for line in read(path).split("\n"):
            if not DISPATCH.match(line):
                continue
            words = re.findall(r'WordIs\("([^"]+)"\)', line)
            if not words:
                continue
            examined += 1
            ok = any(w in documented for w in words) or any(
                re.search(r"`" + re.escape(w) + r"(\s[^`]*)?`", guide_text) for w in words)
            if ok:
                continue
            gap = (key, words[0])
            seen_gaps.add(gap)
            if gap in owed:
                notes.append("owed: %s `%s` is in neither the board's help nor the guide" % gap)
            else:
                fails.append("%s: the command `%s` (%s) is in neither the board's help nor the guide. "
                             "Add it to help (Anvil/Core/help.pbi, or the board's help tail) and run "
                             "tools/guide_check.py --write." % (title, words[0], "/".join(words)))
    for gap in sorted(owed):
        if gap not in seen_gaps:
            fails.append("00_COMMANDS_OWED.txt lists %s `%s`, which is documented now or no longer a "
                         "command: strike it off the list." % gap)
    return examined


def check_generated(fails, write):
    want = generated_chapter()
    have = read(GENERATED) if os.path.exists(GENERATED) else None
    if write and have != want:
        open(GENERATED, "w", encoding="utf-8", newline="\r\n").write(want)
        print("guide_check: wrote %s" % os.path.relpath(GENERATED, ROOT))
        return
    if have != want:
        fails.append("docs/guide/24_every_command.txt is not the current help text: run "
                     "tools/guide_check.py --write, then tools/render_guide.py.")


def blocks(text):
    """(kind, lines, paragraph-before) for every @FRAG in a chapter."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "@FRAG":
            k = i - 1                          # the paragraph just above it
            while k >= 0 and not lines[k].strip():
                k -= 1
            para = []
            while k >= 0 and lines[k].strip() and not lines[k].startswith(("@", ";")):
                para.insert(0, lines[k].strip())
                k -= 1
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != "@ENDFRAG":
                body.append(lines[i])
                i += 1
            out.append((body, " ".join(para)))
        i += 1
    return out


def printed_lines(path):
    """Every line a source file prints, rebuilt from its Print/PrintN statements in order, with
    whatever is worked out at run time (a call, a variable, an If between two Prints) as <...>."""
    out = []
    for proc in re.split(r"(?m)^\s*(?:Procedure|EndProcedure)\b.*$", read(path)):
        out += help_lines(proc.split("\n"))
    return [l for l in out if l.strip()]


WILD = re.compile(r"<[^<>]*>")


def quoted_line_ok(line, printed):
    """The frag line is one of the printed lines, a run-time part (<...>) matching anything."""
    want = WILD.sub("\x01", line.rstrip())
    for p in printed:
        parts = WILD.split(p.rstrip())
        if len(re.sub(r"\s", "", "".join(parts))) < 4:   # (nearly) all run-time: it would match anything
            continue
        if wild_match(parts, want):
            return True
    return False


def wild_match(parts, s):
    """s is parts joined by runs of anything (a glob with only *). Linear: the first part anchors the
    start, the last the end, and each middle part is taken at its first place in between - a regex
    of many .*? backtracks exponentially on the long run-time lines a source file prints."""
    if len(parts) == 1:
        return s == parts[0]
    first, last = parts[0], parts[-1]
    if len(first) + len(last) > len(s) or not s.startswith(first) or not s.endswith(last):
        return False
    pos, end = len(first), len(s) - len(last)
    for p in parts[1:-1]:
        k = s.find(p, pos, end)
        if k < 0:
            return False
        pos = k + len(p)
    return True


def check_quotes(fails):
    examined = 0
    for ch in chapters():
        for body, para in blocks(read(ch)):
            m = re.findall(r"quoted from\s+`([^`]+)`", para)
            if not m:
                continue
            src = os.path.join(ROOT, *m[-1].split("/"))
            if not os.path.exists(src):
                fails.append("%s quotes `%s`, which does not exist." % (os.path.basename(ch), m[-1]))
                continue
            printed = printed_lines(src)
            for l in body:
                if not l.strip():
                    continue
                examined += 1
                if not quoted_line_ok(l, printed):
                    fails.append("%s: a line it says is quoted from %s is not in that file any more:\n"
                                 "      %s" % (os.path.basename(ch), m[-1], l.strip()))
    return examined


def check_flags(fails):
    """--flags on a command line for tools/<name>.py: in a @FRAG, the line naming the tool and the
    option listing right under it (lines starting with --); in prose, inside a `code span` that
    names the tool. argparse's own -h/--help is always there."""
    examined = 0
    tool_re = re.compile(r"tools[/\\]([A-Za-z0-9_]+)\.py")
    flag_re = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")

    def check(ch, tool, text, line):
        nonlocal examined
        src = os.path.join(ROOT, "tools", tool + ".py")
        if not os.path.exists(src):
            fails.append("%s names tools/%s.py, which does not exist." % (os.path.basename(ch), tool))
            return
        code = read(src)
        for flag in flag_re.findall(text):
            if flag == "--help":
                continue
            examined += 1
            if ('"%s"' % flag) not in code and ("'%s'" % flag) not in code:
                fails.append("%s: tools/%s.py has no %s any more (the line: %s)"
                             % (os.path.basename(ch), tool, flag, line.strip()))

    for ch in chapters():
        current, in_frag = None, False
        for l in read(ch).split("\n"):
            s = l.strip()
            if s.startswith(";"):
                continue
            if s == "@FRAG":
                in_frag, current = True, None
                continue
            if s == "@ENDFRAG":
                in_frag, current = False, None
                continue
            if in_frag:
                names = tool_re.findall(l)
                if names:
                    current = names[-1]
                    check(ch, current, l, l)
                elif current and s.startswith("--"):
                    check(ch, current, s.split()[0], l)
                else:
                    current = None
            else:
                for span in re.findall(r"`([^`]*)`", l):
                    names = tool_re.findall(span)
                    if names:
                        check(ch, names[-1], span, l)
    return examined


def check_table(fails):
    """docs/GUIDE.md's chapter table lists every chapter, and nothing that is not one."""
    index = read(os.path.join(ROOT, "docs", "GUIDE.md"))
    linked = set(n for n in re.findall(r"\(guide/([0-9][0-9]_[^)]+\.txt)\)", index)
                 if not n.startswith("00_"))
    have = set(os.path.basename(c) for c in chapters())
    for name in sorted(have - linked):
        fails.append("docs/GUIDE.md's chapter table does not list guide/%s: add its row." % name)
    for name in sorted(linked - have):
        fails.append("docs/GUIDE.md's chapter table links guide/%s, which does not exist." % name)
    return len(linked)


def sources_digest():
    h = hashlib.sha256()
    for ch in chapters():
        h.update(os.path.basename(ch).encode())
        h.update(read(ch).encode("utf-8"))
    return h.hexdigest()


def check_pdf(fails):
    want = sources_digest()
    have = read(STAMP).strip().split()[-1] if os.path.exists(STAMP) else None
    if have != want:
        fails.append("docs/guide/AnvilGuide.pdf was not rendered from the chapters as they are now: "
                     "run tools/render_guide.py.")


def main():
    write = "--write" in sys.argv
    hook = "--hook" in sys.argv
    fails, notes = [], []
    check_generated(fails, write)
    guide_text = "\n".join(read(c) for c in chapters())
    n_cmd = check_commands(guide_text, fails, notes)
    n_quote = check_quotes(fails)
    n_flag = check_flags(fails)
    check_table(fails)
    check_pdf(fails)
    counts = ("%d dispatcher command lines on %d boards, %d quoted lines, %d tool flags, %d chapters"
              % (n_cmd, len(BOARDS), n_quote, n_flag, len(chapters())))
    if n_cmd == 0 or not chapters():
        fails.append("examined nothing - the dispatchers or the chapters were not found.")
    if fails:
        print("guide_check: FAIL - the Anvil Guide is behind the code (%s)" % counts)
        for f in fails:
            print("  !! " + f)
        if notes and not hook:
            print("  (%d commands still owed, docs/guide/00_COMMANDS_OWED.txt)" % len(notes))
        sys.exit(1)
    if hook:
        print("guide_check: PASS (%s; %d owed)" % (counts, len(notes)))
    else:
        print("guide_check: PASS - %s" % counts)
        for n in notes:
            print("  " + n)
    sys.exit(0)


if __name__ == "__main__":
    main()
