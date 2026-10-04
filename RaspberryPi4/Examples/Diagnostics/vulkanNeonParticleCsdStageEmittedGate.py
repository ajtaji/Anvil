"""Check that A64 StageRecords skips X and Y conversions on cache hits.

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
    check_bypass(lines, x_calls, "X")
    check_bypass(lines, y_calls, "Y")
    return len(lines), len(x_calls), len(y_calls)


def check_bypass(lines: list[str], calls: list[int], axis: str) -> None:
    miss_labels = [(i, line[:-1]) for i, line in enumerate(lines[:calls[0]])
                   if re.fullmatch(r"__L\d+:", line)]
    assert miss_labels, f"missing {axis}-cache miss block"
    miss_index, miss_label = miss_labels[-1]
    joins = [(i, line[:-1]) for i, line in enumerate(lines[calls[1] + 1:], calls[1] + 1)
             if re.fullmatch(r"__L\d+:", line)]
    assert joins, f"missing {axis}-cache join block"
    join_index, join_label = joins[0]
    prefix = lines[max(0, miss_index - 160):miss_index]
    assert f"  b {join_label}" in prefix, f"cache hit does not jump past both {axis} calls"
    assert any(re.fullmatch(rf"  b\.[a-z]+ {re.escape(miss_label)}", line) for line in prefix), (
        f"{axis}-cache miss is not reached through a conditional branch"
    )
    assert calls[0] < calls[1] < join_index


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdStageEmittedGate.py PROFILE.img.asm")
        return 2
    lines, x_calls, y_calls = validate(Path(sys.argv[1]).read_text())
    print(f"A64 StageRecords pass: {lines} lines, {x_calls} X and {y_calls} Y call sites; "
          "conditional hit paths bypass both X and Y calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
