#!/usr/bin/env python3
"""render_guide.py - render docs/guide/AnvilGuide.pdf and stamp what it was rendered from.

    python tools/render_guide.py [--pmf-repo DIR]

The renderer is the PureMetal compiler repository's tools/build_help_pdf.py
(docs/GUIDE.md, "Rendering the PDF"); this runs it with the book's own
arguments, so nobody has to remember them. DIR is that repository's
directory holding tools/ and Help/. Default: $PMF_REPO, else the folder of
$PMF_COMPILER (the compiler executable tools/build.py already uses, which
sits at that repository's root).

After a successful render it writes docs/guide/AnvilGuide.pdf.sources, the
SHA-256 of the chapters the PDF was rendered from. tools/guide_check.py
compares that with the chapters as they are, so a chapter edited without
re-rendering fails the check (and the pre-commit hook).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_check  # noqa: E402

TITLE = "The Anvil Guide"
SUBTITLE = "Build it, install it on a Raspberry Pi 4, write payloads for it, and use all four cores."


def pmf_repo():
    if "--pmf-repo" in sys.argv:
        return sys.argv[sys.argv.index("--pmf-repo") + 1]
    if os.environ.get("PMF_REPO"):
        return os.environ["PMF_REPO"]
    if os.environ.get("PMF_COMPILER"):
        return os.path.dirname(os.path.abspath(os.environ["PMF_COMPILER"]))
    sys.exit("render_guide: say where the PureMetal compiler repository is: --pmf-repo DIR, or set "
             "PMF_REPO (or PMF_COMPILER, the compiler at that repository's root).")


def main():
    repo = pmf_repo()
    renderer = os.path.join(repo, "tools", "build_help_pdf.py")
    if not os.path.exists(renderer):
        sys.exit("render_guide: %s is not there - --pmf-repo must be the folder holding tools/ and Help/."
                 % renderer)
    digest = guide_check.sources_digest()          # the chapters as they are when rendering starts
    pdf = os.path.join(guide_check.GUIDE, "AnvilGuide.pdf")
    cmd = [sys.executable, renderer, "--book", guide_check.GUIDE, "--out", pdf,
           "--title", TITLE, "--subtitle", SUBTITLE, "--section-nav"]
    print("render_guide: " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=repo)
    if r.returncode != 0:
        sys.exit("render_guide: the renderer failed (exit %d); the stamp was not written." % r.returncode)
    if guide_check.sources_digest() != digest:
        sys.exit("render_guide: a chapter changed while the PDF was rendering; run it again.")
    with open(guide_check.STAMP, "w", encoding="ascii", newline="\n") as f:
        f.write("sha256 of the chapters AnvilGuide.pdf was rendered from (tools/render_guide.py)\n%s\n" % digest)
    print("render_guide: %s, stamped %s" % (os.path.relpath(pdf, guide_check.ROOT), digest[:16]))


if __name__ == "__main__":
    main()
