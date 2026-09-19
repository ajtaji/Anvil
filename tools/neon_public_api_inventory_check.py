#!/usr/bin/env python3
"""Fail when the public Neon API or its known callers drift from the ledger."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = Path(__file__).with_name("neon_public_api_inventory.py")
MANIFEST = ROOT / "RaspberryPi4" / "Tests" / "neon_public_api_compatibility_manifest.json"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "neon_public_api_compatibility_compile.pi4"
KEYS = ("schema", "source", "api_sha256", "public_procedure_count", "public_procedures", "public_structures", "public_constants", "caller_file_count", "callers", "unresolved_neon_calls")

def compare(actual, expected):
    return [key for key in KEYS if actual.get(key) != expected.get(key)]

def load_actual(path=None):
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(subprocess.check_output([sys.executable, str(INVENTORY)], cwd=ROOT, text=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    expected = json.loads(args.manifest.read_text(encoding="utf-8"))
    actual = load_actual(args.inventory)
    if args.self_test:
        mutations = [("missing symbol", lambda x: x["public_procedures"].pop()), ("signature drift", lambda x: x["public_procedures"][0].update(params="mutated")), ("missing caller", lambda x: x["callers"].pop(next(iter(x["callers"])) )), ("classification drift", lambda x: x["public_procedures"][0].update(category="native-only diagnostic")), ("renderer classification drift", lambda x: x["public_procedures"][0].update(renderer_classification="backend-dispatched"))]
        for label, mutate in mutations:
            candidate = json.loads(json.dumps(actual))
            mutate(candidate)
            if not compare(candidate, expected):
                print("self-test failed: " + label)
                return 1
        print("Neon public API inventory self-tests: PASS (5 mutation controls)")
        return 0
    errors = compare(actual, expected)
    allow = set(expected.get("known_external_neon_calls", []))
    unexpected = sorted(set(actual.get("unresolved_neon_calls", [])) - allow)
    if unexpected:
        errors.append("unexpected unresolved Neon calls: " + ", ".join(unexpected))
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    covered = {row["name"] for row in actual["public_procedures"] if row["renderer_classification"] != "native-only-diagnostic" and (row["name"] + "(") in fixture_text}
    required = {row["name"] for row in actual["public_procedures"] if row["renderer_classification"] != "native-only-diagnostic"}
    if covered != required:
        errors.append("compile fixture does not cover every renderer-neutral/backend-dispatched signature")
    if errors:
        print("Neon public API compatibility: FAIL")
        for error in errors:
            print("  changed: " + error)
        return 1
    print(f"Neon public API compatibility: PASS ({actual['public_procedure_count']} procedures, {actual['caller_file_count']} caller files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
