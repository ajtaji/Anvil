"""Check that A64 StageRecords really skips both Y conversions on a cache hit.

Build the matched CSD payload with `-S` and pass its generated `.img.asm`.
"""

import re
import sys
from pathlib import Path


def validate(assembly: str) -> tuple[int, int, int]:
    start = assembly.index("\nnvpcStageRecords:\n") + 1
    end = assembly.index("\nNeonVkParticleCsdPrepare:\n", start)
    lines = assembly[start:end].splitlines()
    x_calls = [i for i, line in enumerate(lines) if line.strip() == "bl nvcparticleclipxbits"]
    y_calls = [i for i, line in enumerate(lines) if line.strip() == "bl nvcparticleclipybits"]
    assert len(x_calls) == 2 and len(y_calls) == 2, "unexpected fast-path clip call sites"
    miss_labels = [(i, line[:-1]) for i, line in enumerate(lines[:y_calls[0]])
                   if re.fullmatch(r"__L\d+:", line)]
    assert miss_labels, "missing Y-cache miss block"
    miss_index, miss_label = miss_labels[-1]
    joins = [(i, line[:-1]) for i, line in enumerate(lines[y_calls[1] + 1:], y_calls[1] + 1)
             if re.fullmatch(r"__L\d+:", line)]
    assert joins, "missing Y-cache join block"
    join_index, join_label = joins[0]
    prefix = lines[max(0, miss_index - 80):miss_index]
    assert f"  b {join_label}" in prefix, "cache hit does not jump past both Y calls"
    assert any(re.fullmatch(rf"  b\.[a-z]+ {re.escape(miss_label)}", line) for line in prefix), (
        "cache miss is not reached through a conditional branch"
    )
    assert y_calls[0] < y_calls[1] < join_index
    return len(lines), len(x_calls), len(y_calls)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdStageEmittedGate.py PROFILE.img.asm")
        return 2
    lines, x_calls, y_calls = validate(Path(sys.argv[1]).read_text())
    print(f"A64 StageRecords pass: {lines} lines, {x_calls} X and {y_calls} Y call sites; "
          "conditional hit path bypasses both Y calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
