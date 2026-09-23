#!/usr/bin/env python3
"""Static gate: every Anvil tool that takes a compiler path must resolve it
through the shared, validating lookup (tools/pmf_compiler.py resolve_compiler()).

This is pattern-based, not semantic: a tool is "in scope" when it reads the
PMF_COMPILER environment variable or defines a --compiler command-line flag -
the two inputs the "--compile opened the IDE window" defect (forum 977) came
through. An in-scope tool must contain a literal
``from pmf_compiler import resolve_compiler`` (any import alias) somewhere in
its source; a tool that only mentions PureMetalForge.exe in a docstring, a
process-name lookup, or a hash-pinned constant with no --compiler/PMF_COMPILER
input of its own is out of scope and is not flagged.

Usage:
    python tools/pmf_compiler_usage_check.py
Exits 1 and lists offenders if any in-scope tool builds a compiler path
without going through resolve_compiler(); exits 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
MODULE_FILE = TOOLS_DIR / "pmf_compiler.py"
SELF_FILE = Path(__file__).resolve()

ENV_TRIGGER = re.compile(r'os\.environ(?:\.get)?\s*\(\s*["\']PMF_COMPILER["\']')
FLAG_TRIGGER = re.compile(r'add_argument\(\s*["\']--compiler["\']')
IMPORT_OK = re.compile(r'from\s+pmf_compiler\s+import\s+resolve_compiler\b')


def is_in_scope(text: str) -> bool:
    return bool(ENV_TRIGGER.search(text) or FLAG_TRIGGER.search(text))


def goes_through_resolver(text: str) -> bool:
    return bool(IMPORT_OK.search(text))


def check_python_files():
    violations = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        if path.resolve() in (MODULE_FILE.resolve(), SELF_FILE):
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            violations.append((path, f"could not read file: {exc}"))
            continue
        if is_in_scope(text) and not goes_through_resolver(text):
            violations.append((path, "reads PMF_COMPILER or defines --compiler "
                                      "but never imports resolve_compiler from "
                                      "pmf_compiler"))
    return violations


def check_shell_scripts():
    violations = []
    for pattern in ("*.ps1", "*.cmd"):
        for path in sorted(TOOLS_DIR.rglob(pattern)):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                violations.append((path, f"could not read file: {exc}"))
                continue
            if is_in_scope(text):
                violations.append((path, "shell script names PMF_COMPILER/--compiler "
                                          "directly; route it through "
                                          "tools/pmf_compiler.py resolve_compiler() "
                                          "(e.g. via a python -c call) instead"))
    return violations


def main() -> int:
    violations = check_python_files() + check_shell_scripts()
    if not violations:
        print("pmf_compiler_usage_check: OK - every in-scope tool resolves the "
              "compiler through pmf_compiler.resolve_compiler()")
        return 0
    print("pmf_compiler_usage_check: FAIL - %d tool(s) build a compiler path "
          "without going through resolve_compiler():" % len(violations))
    for path, reason in violations:
        try:
            rel = path.relative_to(TOOLS_DIR.parent)
        except ValueError:
            rel = path
        print(f"  {rel}: {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
