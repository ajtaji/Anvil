#!/usr/bin/env python3
"""Shared parallel driver for the A64 gates' --mutate sweeps.

WHY THIS FILE EXISTS

  A --mutate run is N INDEPENDENT GATE RUNS.  Each applies one edit to a
  COPY of a library, builds an image, executes it under the model and
  scores it.  No two share a byte of state, so running them one at a time
  on a many-core bench spends wall clock for nothing: fifteen mutations at
  a few minutes each is most of an hour for what is one mutation's worth
  of work when they run side by side.

  GATES SHARE THIS ONE FILE rather than each growing a pool of its own,
  because the interesting part - a worker per mutation, a directory per
  worker, verdicts collected in a stable order, and the pool reaped
  afterwards - is identical between them and is exactly the part that is
  easy to get subtly wrong twice.

HOW IT WORKS, AND WHY IT IS SUBPROCESSES RATHER THAN AN IN-PROCESS POOL

  Each mutation is run by a FRESH `python <gate> --mutate-one N
  --mutate-dir D` plus whatever arguments the gate passes through (the
  compiler, for one).  Three reasons, and the third is load-bearing:

    * The gates' model objects carry closures over live memory dicts.
      Nothing about them is picklable, so a multiprocessing pool over
      in-process callables would have to rebuild them in the child anyway.
    * On Windows the spawn start method re-imports __main__, which for a
      script-shaped gate means re-running argument parsing.  A separate
      invocation makes that explicit instead of accidental.
    * A child that wedges is killed by killing a process.  The STEP BUDGET
      inside each gate catches a non-terminating mutant, but a genuinely
      hung interpreter would be unkillable inside a thread.

  ONE DIRECTORY PER WORKER.  `<root>/<n>/` holds that worker's mutated
  copy, its generated harness and its image.  Without that the builds
  collide on output filenames and the sweep scores whichever image
  happened to be on disk last - a failure that looks like a flaky gate and
  is not.

  THE LIBRARY IS NEVER OPENED FOR WRITING.  Only copies under the worker
  directories are, and those live in a temporary directory outside the
  tree, so a sweep killed halfway cannot leave a mutant where a concurrent
  build or commit picks it up.

  AND THE POOL IS REAPED.  `run_parallel` joins every worker and
  `report_reaped` counts what is still alive, which must be zero.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

VERDICT = "V\t"


def worker_count() -> int:
    """os.cpu_count() - 2: leave a core for the machine and one for
    whatever else is running on it.

    PMF_MUTATE_JOBS, when set to a positive whole number, is used instead,
    so a bench shared with other work can cap a sweep."""
    requested = os.environ.get("PMF_MUTATE_JOBS", "").strip()
    if requested:
        if not requested.isdigit() or int(requested) < 1:
            raise SystemExit(
                "PMF_MUTATE_JOBS is set to %r, which is not a positive whole "
                "number. Set it to a worker count of 1 or more, or unset it."
                % requested)
        return int(requested)
    return max(1, (os.cpu_count() or 4) - 2)


def apply_edits(src, old, new, count):
    """Apply one mutation to src; return (mutated, None) or (None, why).

    old/new may be single strings or matching tuples - a mutation is
    sometimes more than one edit, and applying the halves separately is
    a different experiment from applying them together.  count is how
    many times each anchor must occur; an anchor that has silently
    stopped matching is a mutation that has stopped testing anything, so
    it is reported rather than skipped.
    """
    olds = old if isinstance(old, tuple) else (old,)
    news = new if isinstance(new, tuple) else (new,)
    counts = count if isinstance(count, tuple) else (count,) * len(olds)
    out = src
    for o, w, c in zip(olds, news, counts):
        n = out.count(o)
        if n != c:
            return None, ("anchor %r occurs %d times, expected %d"
                          % (o[:44], n, c))
        out = out.replace(o, w)
    return out, None


def child_dir(root: pathlib.Path, idx: int) -> pathlib.Path:
    """A clean, empty directory for one worker."""
    d = root / str(idx)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_parallel(gate: pathlib.Path, cwd: pathlib.Path, count: int,
                 root: pathlib.Path, procs=None, label: str = "mutation",
                 extra_args=None):
    """Run --mutate-one i for i in range(count), procs at a time.

    Returns the children's verdict lines IN INDEX ORDER, whatever order
    they finished in, so two runs of the same sweep produce comparable
    output.  A child that writes nothing, or dies, becomes an explicit
    ERROR line rather than a gap - a missing verdict must never read as
    a pass.
    """
    if count == 0:
        return []
    if procs is None:
        procs = worker_count()
    procs = max(1, min(procs, count))
    root.mkdir(parents=True, exist_ok=True)
    results = [None] * count
    started = time.time()
    done = [0]
    extra = list(extra_args or [])

    def one(i):
        d = child_dir(root, i)
        cmd = [sys.executable, str(gate), "--mutate-one", str(i),
               "--mutate-dir", str(d)] + extra
        try:
            r = subprocess.run(cmd, cwd=str(cwd), text=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
            lines = [ln for ln in r.stdout.splitlines()
                     if ln.startswith(VERDICT)]
            if lines:
                results[i] = lines[-1]
            else:
                tail = r.stdout.strip().splitlines()[-3:]
                results[i] = (VERDICT + "ERROR\tthe worker printed no "
                              "verdict (exit %d): %s"
                              % (r.returncode, " | ".join(tail)))
        except Exception as exc:                         # noqa: BLE001
            results[i] = VERDICT + "ERROR\tthe worker could not run: %r" % (exc,)
        done[0] += 1
        print("    [%2d/%2d] %s %d finished, %.0f s elapsed"
              % (done[0], count, label, i, time.time() - started), flush=True)

    # A THREAD pool over SUBPROCESSES.  The threads only ever wait in
    # subprocess.run, so the interpreter lock is irrelevant and the
    # parallelism is real; nothing has to be picklable and there is no
    # spawn re-import to reason about.
    with ThreadPoolExecutor(max_workers=procs) as pool:
        list(pool.map(one, range(count)))

    return [r if r is not None else VERDICT + "ERROR\tno verdict"
            for r in results]


def report_reaped(compiler=None) -> int:
    """Count leftover compiler processes started from `compiler`.  Must be 0.

    ThreadPoolExecutor's context manager has joined every thread and
    subprocess.run has reaped every child, so this is a CHECK on that
    rather than an action.  Returns -1 if it could not look.

    ONLY PROCESSES RUNNING THE SAME EXECUTABLE ARE COUNTED.  A bench with
    several trees building at once has other compiler processes that are
    none of this sweep's business, and counting them would fail a clean
    sweep on somebody else's build.  The executable path comes from CIM,
    because `tasklist` cannot report one; where that query is unavailable
    the answer is -1, printed as "could not look" rather than as a clean
    zero, because a check that silently degrades into a check of something
    else is worse than one that says it could not run.
    """
    if compiler is None:
        return -1
    given = pathlib.Path(compiler)
    # A DIRECTORY instead of an executable means "compiles of this tree":
    # the compiler lives outside the tree, so what ties a process to the
    # tree is its command line, which names a source or output under it.
    by_tree = given.is_dir()
    want = str(given.resolve()).lower()
    name = "PureMetalForge.exe" if by_tree else given.name.replace("'", "")
    field = "CommandLine" if by_tree else "ExecutablePath"
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='%s'\" "
             "| ForEach-Object { $_.%s }" % (name, field)],
            text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=30).stdout
    except Exception:                                    # noqa: BLE001
        return -1
    n = 0
    for line in out.splitlines():
        p = line.strip().lower()
        if not p:
            continue
        if by_tree:
            if want in p or want.replace("\\", "/") in p:
                n += 1
        elif p == want:
            n += 1
    return n
