#!/usr/bin/env python3
"""t0gen.py - translate a BearSSL-generated T0 interpreter (.c) into a
house-dialect "blob" include that the portable t0vm core can run.

BearSSL writes each T0 program (the PEM decoder, the X.509 engine, the TLS
handshake) as threaded bytecode plus a per-program C interpreter. The
bytecode is portable; the interpreter is not, and its opcode NUMBERS are
assigned per program (the compiler sorts the words each program uses and
hands out numbers in order). So this generator does two jobs:

  1. lift the four constant blobs - code, data, caddr, and the opcode-name
     table - out of the .c, expanding the T0_INTn(offsetof(...)) macros
     against a caller-supplied field->offset map (our context-RAM layout);
  2. build an OPMAP that translates each raw opcode into the CANONICAL id
     the t0vm core understands, or a NATIVE id (>=128) the host services.

It fails loudly on anything it does not recognise - an unmapped struct
field, a macro it cannot expand - because a silently wrong blob is exactly
the class of bug this project refuses to ship.

The BearSSL C sources are NOT part of this tree. Point this tool at a
BearSSL checkout (MIT; the notice ships as licenses/BearSSL-LICENSE.txt).
The gates that use these helpers - tools/a64/a64_t0vm_check.py and
tools/a64/a64_x509_check.py - regenerate in process when the BEARSSL_SRC
environment variable names such a checkout, and say so when it does not.

Usage:
    python tools/t0gen.py [--native-ram] [--ext .pi4] <generated.c> \
        <ProgName> <out_stem> [field=offset ...]
Writes <out_stem><ext>. The blob is pure data, so copies for other
families are byte-identical below the header.
"""
import os, re, sys
from urllib.parse import unquote

# ----------------------------------------------------------------------
# Canonical primitive ids - MUST match the #T0OP_* constants in t0vm.
# ----------------------------------------------------------------------
GENERIC = {
    "+": 1, "-": 2, "neg": 3, "*": 4, "/": 5, "u/": 6, "%": 7, "u%": 8,
    "<": 9, "<=": 10, ">": 11, ">=": 12, "=": 13, "<>": 14,
    "u<": 15, "u<=": 16, "u>": 17, "u>=": 18,
    "and": 19, "or": 20, "xor": 21, "not": 22,
    "<<": 23, ">>": 24, "u>>": 25,
    "co": 26, "drop": 27, "dup": 28, "swap": 29, "over": 30,
    "rot": 31, "-rot": 32, "roll": 33, "pick": 34, "execute": 35,
    "data-get8": 36, "get8": 37, "set8": 38,
    "get16": 39, "set16": 40, "get32": 41, "set32": 42,
}
NATIVE_BASE = 128
# Every native word BearSSL's kern.t0 does NOT define is program-specific C.
CONTROL = {0, 1, 2, 3, 4, 5, 6}

# The six context-memory ops. The t0vm core services these against its
# fixed-size t0_ram region, which suits a small program (the PEM decoder).
# A program with a large context (the X.509 engine's key/signature/scratch
# buffers exceed that region) passes --native-ram so these are lifted as
# NATIVE words instead: the host then owns a context array of any size and
# services get8/set8/... itself. Additive and off by default - a run
# without the flag behaves exactly as before.
# data-get8 is NOT here: it reads the lifted constant DATA block, which
# the VM already owns.
MEM_WORDS = ("get8", "set8", "get16", "set16", "get32", "set32")


def slurp(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def get_define(text, name):
    m = re.search(r"#define\s+%s\s+(\d+)" % re.escape(name), text)
    if not m:
        sys.exit("t0gen: no #define %s was found in the generated C; check "
                 "that the input is a BearSSL T0 interpreter file" % name)
    return int(m.group(1))


def get_entry_slot(text):
    m = re.search(r"T0_DEFENTRY\(\s*\w+\s*,\s*(\d+)\s*\)", text)
    if not m:
        sys.exit("t0gen: no T0_DEFENTRY(...) entry point was found; check "
                 "that the input is a BearSSL T0 interpreter file")
    return int(m.group(1))


def array_body(text, decl):
    """Return the text between '{' and '}' of a named array declaration."""
    m = re.search(re.escape(decl) + r"\s*=\s*\{", text)
    if not m:
        sys.exit("t0gen: the array %s was not found; check that the input "
                 "is a BearSSL T0 interpreter file" % decl)
    i = m.end()
    depth = 1
    j = i
    while j < len(text) and depth:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    return text[i:j - 1]


def split_top(body):
    """Split a C array body on top-level commas (parens are nested)."""
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [t.strip() for t in out if t.strip()]


def eval_int(expr, fields, seen_fields):
    """Evaluate a codeblock integer expression: offsetof(), named constants
    and arithmetic. The symbol map (fields) supplies both struct-field RAM
    offsets AND the value of any bare named constant the T0 program embedded
    (error codes, key-type ids, buffer-size caps). Anything left unresolved
    is a loud stop - a silently wrong blob is exactly what this refuses."""
    def repl(m):
        fld = m.group(1).strip()
        seen_fields.add(fld)
        if fld not in fields:
            sys.exit("t0gen: struct field '%s' has no RAM offset - pass "
                     "%s=<offset> on the command line" % (fld, fld))
        return str(fields[fld])
    expr = re.sub(r"offsetof\(\s*\w+\s*,\s*([^)]+)\)", repl, expr)
    # Substitute any bare C identifier that names a supplied constant.
    def repl_id(m):
        nm = m.group(0)
        if nm in fields:
            seen_fields.add(nm)
            return str(fields[nm])
        return nm
    expr = re.sub(r"[A-Za-z_]\w*", repl_id, expr)
    expr = expr.strip()
    if not re.fullmatch(r"[0-9xXa-fA-F+\-*/() \t]+", expr):
        sys.exit("t0gen: cannot evaluate codeblock expr: %r - pass any named "
                 "constant it contains as NAME=<value> on the command line"
                 % expr)
    return int(eval(expr, {"__builtins__": {}}, {})) & 0xFFFFFFFF


def macro_bytes(name, val):
    def vbyte(x, n):
        return ((x >> n) & 0x7F) | 0x80
    def fbyte(x, n):
        return (x >> n) & 0x7F
    def sbyte(x):
        return (((x >> 28) + 0xF8) ^ 0xF8) & 0xFF
    if name == "T0_INT1":
        return [fbyte(val, 0)]
    if name == "T0_INT2":
        return [vbyte(val, 7), fbyte(val, 0)]
    if name == "T0_INT3":
        return [vbyte(val, 14), vbyte(val, 7), fbyte(val, 0)]
    if name == "T0_INT4":
        return [vbyte(val, 21), vbyte(val, 14), vbyte(val, 7), fbyte(val, 0)]
    if name == "T0_INT5":
        return [sbyte(val), vbyte(val, 21), vbyte(val, 14), vbyte(val, 7),
                fbyte(val, 0)]
    sys.exit("t0gen: the macro %s is not one this generator can expand; "
             "only T0_INT1 to T0_INT5 are known" % name)


def parse_bytes(body, fields, seen_fields):
    out = []
    for tok in split_top(body):
        m = re.fullmatch(r"(T0_INT[1-5])\((.*)\)", tok, re.S)
        if m:
            val = eval_int(m.group(2), fields, seen_fields)
            out.extend(macro_bytes(m.group(1), val))
        else:
            out.append(int(tok, 0) & 0xFF)
    return out


def parse_caddr(text):
    body = array_body(text, "static const uint16_t t0_caddr[]")
    return [int(t, 0) for t in split_top(body)]


def opcode_names(text, n_interp):
    """Map raw opcode -> word name, from the 'case K: /* name */' comments."""
    names = {}
    # single-line: case 0: /* ret */
    for m in re.finditer(r"case\s+(\d+):\s*(?:\{)?\s*/\*\s*(.+?)\s*\*/", text):
        k = int(m.group(1))
        if k < n_interp and k not in names:
            # BearSSL's T0 compiler percent-escapes some word names in the
            # generated comment (e.g. '%' -> '%25'); undo that so the name
            # matches the real T0 word.
            names[k] = unquote(m.group(2).strip())
    return names


def sanitize(name):
    s = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_")
    return s or "op"


def main():
    argv = list(sys.argv[1:])
    native_ram = False
    if "--native-ram" in argv:
        native_ram = True
        argv.remove("--native-ram")
    ext = ".pi4"
    if "--ext" in argv:
        k = argv.index("--ext")
        if k + 1 >= len(argv):
            sys.exit("t0gen: --ext needs a value, for example --ext .pi4")
        ext = argv[k + 1]
        del argv[k:k + 2]
    if len(argv) < 3:
        sys.exit(__doc__)
    cpath, prog, stem = argv[0], argv[1], argv[2]
    tag = sanitize(os.path.basename(stem))      # label-safe identifier base

    # Word->canonical id map for this run. With --native-ram the context
    # memory ops leave the map, so they lift as host natives (see MEM_WORDS).
    generic = dict(GENERIC)
    if native_ram:
        for w in MEM_WORDS:
            generic.pop(w, None)

    fields = {}
    for a in argv[3:]:
        k, _, v = a.partition("=")
        fields[k.strip()] = int(v, 0)

    text = slurp(cpath)
    n_interp = get_define(text, "T0_INTERPRETED")
    entry = get_entry_slot(text)

    seen_fields = set()
    data_bytes = parse_bytes(array_body(text,
                    "static const unsigned char t0_datablock[]"),
                    fields, seen_fields)
    code_bytes = parse_bytes(array_body(text,
                    "static const unsigned char t0_codeblock[]"),
                    fields, seen_fields)
    caddr = parse_caddr(text)
    names = opcode_names(text, n_interp)

    # Build the opmap and the native-word list.
    opmap = [0] * n_interp
    natives = []            # (native_index, raw_opcode, name)
    name_to_nid = {}
    for k in range(7, n_interp):
        nm = names.get(k)
        if nm is None:
            sys.exit("t0gen: opcode %d has no name comment in the generated "
                     "C, so it cannot be mapped" % k)
        if nm in generic:
            opmap[k] = generic[nm]
        else:
            nid = len(natives)
            natives.append((nid, k, nm))
            name_to_nid[nm] = nid
            opmap[k] = NATIVE_BASE + nid

    # ---- emit ----
    L = []
    w = L.append
    w("; ======================================================================")
    w("; %s%s - T0 program blobs for '%s', generated by tools/t0gen.py"
      % (os.path.basename(stem), ext, prog))
    w(";   DO NOT EDIT BY HAND. Regenerate from the BearSSL-generated C.")
    w(";   source: %s" % os.path.basename(cpath))
    w("; ----------------------------------------------------------------------")
    w(";   This file is PURE DATA: copies for other families are")
    w(";   byte-identical below this header. It is loaded by the t0vm core;")
    w(";   include t0vm first, then this file, then call T0Load%s()." % prog)
    w(";   Requires: t0vm (for the descriptor globals and #T0_NATIVE_BASE).")
    w("; ----------------------------------------------------------------------")
    w(";   T0_INTERPRETED = %d   entry slot = %d   interpreted words = %d" % (n_interp, entry, len(caddr)))
    w(";   code %d bytes   data %d bytes   natives %d" % (len(code_bytes), len(data_bytes), len(natives)))
    w("; ======================================================================")
    w("")
    w("#T0_%s_INTERP = %d" % (prog.upper(), n_interp))
    w("#T0_%s_ENTRY  = %d" % (prog.upper(), entry))
    w("")
    w("; ---- native word ids (the host's T0Native must service these) ----")
    for nid, k, nm in natives:
        w("#T0N_%s = %d" % (sanitize(nm), nid))
    if not natives:
        w("; (this program uses no native words)")
    w("")
    w("Procedure T0Load%s()" % prog)
    w("  t0_cp      = ?t0_%s_code" % tag)
    w("  t0_datap   = ?t0_%s_data" % tag)
    w("  t0_caddrp  = ?t0_%s_caddr" % tag)
    w("  t0_opp     = ?t0_%s_opmap" % tag)
    w("  t0_interp  = #T0_%s_INTERP" % prog.upper())
    w("  t0_entry   = #T0_%s_ENTRY" % prog.upper())
    w("EndProcedure")
    w("")
    w("DataSection")

    def emit_bytes(label, arr):
        w("%s:" % label)
        for i in range(0, len(arr), 12):
            w("  Data.a " + ", ".join(str(b) for b in arr[i:i + 12]))
        if not arr:
            w("  Data.a 0")

    emit_bytes("t0_%s_code" % tag, code_bytes)
    emit_bytes("t0_%s_data" % tag, data_bytes if data_bytes else [0])
    # caddr as little-endian 16-bit pairs
    caddr_pairs = []
    for v in caddr:
        caddr_pairs.append(v & 0xFF)
        caddr_pairs.append((v >> 8) & 0xFF)
    emit_bytes("t0_%s_caddr" % tag, caddr_pairs)
    emit_bytes("t0_%s_opmap" % tag, opmap)
    w("EndDataSection")
    w("")

    outp = stem + ext
    with open(outp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")

    # report to stderr
    unref = [f for f in fields if f not in seen_fields]
    print("t0gen: wrote %s" % outp, file=sys.stderr)
    print("  T0_INTERPRETED=%d entry=%d words=%d code=%dB data=%dB natives=%d"
          % (n_interp, entry, len(caddr), len(code_bytes), len(data_bytes),
             len(natives)), file=sys.stderr)
    print("  native words: %s" % ", ".join(nm for _, _, nm in natives),
          file=sys.stderr)
    if seen_fields:
        print("  context fields used: %s"
              % ", ".join("%s@%d" % (f, fields[f]) for f in sorted(seen_fields)),
              file=sys.stderr)
    if unref:
        print("  NOTE unused field maps: %s" % ", ".join(unref), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
