# Debugging Python

Python gives you an unusually good traceback and a debugger in the standard library — most Python
debugging goes wrong by not using either.

## Read the traceback properly

The traceback is the highest-information artifact you will get. Read it in this order:

1. **The last line** — the exception type and message. `KeyError: 'user_id'` and
   `TypeError: 'NoneType' object is not subscriptable` are different investigations.
2. **The bottom frame** — where it raised. Often library code, and often not the bug.
3. **Upward to the last frame in your code** — this is usually where the wrong value was introduced.
4. **`during handling of the above exception, another exception occurred`** — you are looking at a
   second failure inside an `except` block. The first one is the real one.
5. **`the above exception was the direct cause`** — an explicit `raise … from exc`; the chain is
   deliberate and both halves matter.

Preserve the whole thing. `except Exception as e: print(e)` throws away the frames and leaves you a
message with no location — the most common self-inflicted wound in Python debugging. Use
`logger.exception(...)` inside the handler, which captures the traceback automatically.

## Turn on the checks the runtime already has

```sh
python -X dev your_script.py          # development mode
python -X dev -X tracemalloc=5 app.py # plus allocation traces for resource warnings
```

Development mode enables the default warning filter (`DeprecationWarning`, `ResourceWarning` and
friends), memory-allocator debug hooks, encoding-argument validation, logging of exceptions in
`IOBase` destructors, and **faulthandler** — which dumps a Python traceback on `SIGSEGV`, `SIGFPE`,
`SIGABRT`, `SIGBUS`, and `SIGILL`.

The caveat matters: faulthandler "does **not** prevent or catch hangs." It explains crashes, not
freezes — see py-spy below for those.

`ResourceWarning` alone will find unclosed files and sockets that otherwise present as a slow leak
under load, and with `-X tracemalloc=5` it tells you where each was allocated.

## Use the debugger, not print

`breakpoint()` drops you into pdb at that line. `PYTHONBREAKPOINT=0` disables every one of them
without editing code, which makes it safe to leave one in a branch you are iterating on.

The commands that actually matter:

| Command | Does |
|---|---|
| `n` / `s` | next line / step into |
| `c` | continue |
| `ll` | list the whole current function — better than `l` |
| `w` (`bt`) | the stack; `u` / `d` to move frames |
| `p` / `pp` | print / pretty-print an expression |
| `args` | this frame's arguments |
| `display x` | show `x` every time execution stops |
| `break file.py:42, x > 5` | conditional breakpoint — the one that saves an hour |
| `until 60` | run to a line past the loop you are stuck in |
| `interact` | a full REPL in the current frame |

Run a whole script or module under the debugger without editing it:

```sh
python -m pdb -m yourpackage.cli args…
python -m pdb -c "break yourmod.py:42" -c continue script.py
python -m pdb -p 1234          # attach to a running process (3.14+)
```

A conditional breakpoint on the iteration that goes wrong beats a thousand printed lines, and it lets
you inspect everything in scope rather than only what you thought to print.

## Post-mortem: debug the failure that already happened

You do not need to reproduce a crash inside the debugger — you can enter the debugger at the point of
the exception that already occurred:

```python
import pdb; pdb.pm()             # after an exception, in the same REPL session
python -m pdb -c continue app.py # run to completion; drop into pdb on an unhandled exception
```

This is the fastest route from "I have a traceback" to "I can see the values." `pdb.post_mortem(tb)`
takes a specific traceback if you captured one.

## Symptom to first tool

| Symptom | First tool |
|---|---|
| Exception with a traceback | Read it, then `pdb.pm()` or `python -m pdb -c continue` |
| Hang or deadlock | `py-spy dump --pid <pid>` — prints every thread's stack, no code changes, safe on production |
| Slow, cause unknown | `py-spy top`, or `cProfile` + `pstats`. Measure before optimizing |
| Segfault | `-X dev` (faulthandler) for the Python traceback at the crash |
| Memory grows over time | `tracemalloc` — snapshot, run the workload, snapshot again, `compare_to()` |
| `ResourceWarning`, leaked file handles | `-X dev -X tracemalloc=5` |
| Import fails or is slow | `python -X importtime -c 'import app'`; for circular imports see the traps below |
| Works in tests, fails in production | Compare environment, working directory, installed versions, and `sys.path` — not the code |
| Intermittent test failure | Fix the seed and the order; run the single test alone before believing it |
| Wrong value, no exception | `breakpoint()` at the last point you know the value is right, then step forward |

`py-spy` is worth knowing specifically because it attaches to a running process without modifying it
and is "designed to be safe for production use" — it is the only practical answer to a hung worker
you cannot restart.

## Debugging tests

```sh
pytest -x                  # stop at the first failure
pytest --lf                # re-run only what failed last time
pytest --pdb               # drop into pdb at the failure, with the frame intact
pytest -q --tb=short       # readable output while iterating
python -m unittest -f -v   # unittest's fail-fast
```

`--pdb` is the highest-value flag: it puts you in the failing frame with every local available,
rather than in a diff of two reprs.

For an intermittent failure, hold everything constant and vary one thing: run the test alone, then in
its class, then in the file. A test that passes alone and fails in the suite is shared state or
ordering, not the test.

## Traps that send you the wrong way

- **`except Exception as e: print(e)`** discards the traceback. You lose the file, the line, and the
  chain. `logger.exception()` keeps all three.
- **A bare `except:`** also catches `KeyboardInterrupt` and `SystemExit`, so Ctrl-C during a hang
  gets swallowed and the program looks unkillable.
- **`assert` is removed under `-O`.** A check that "cannot be failing" may not be running.
- **`print` from a subprocess, a thread, or a crashed process may never flush.** Use
  `print(..., flush=True)`, or logging, or you will conclude the code never reached that line.
- **The mutable-default and late-binding traps produce wrong values with no error**, which reads as
  "the logic is wrong" rather than "the language did something." Check `using-python`'
  `documented-traps.md` before rewriting the logic.
- **A circular import fails only in one direction.** CPython's FAQ: circular imports "are fine where
  both modules use the `import <module>` form… they fail when the 2nd module wants to grab a name out
  of the first (`from module import name`) and the import is at the top level."
- **`importlib.reload()` does not update existing instances** — they keep referencing the old class,
  so `isinstance` starts returning `False`. Restart the REPL.
- **A stale `.pyc` or a shadowing local file** named like a stdlib module produces impossible
  behaviour. Check `module.__file__`.
- **The virtualenv you are debugging may not be the one running the code.** `python -c 'import sys;
  print(sys.executable, sys.path)'` in the failing context.

## Don't

- Don't add `try/except` to make a traceback go away. You are deleting the only evidence you have.
- Don't scatter `print` and then delete them. Use `logging` at `debug` level, or the debugger — both
  survive to the next occurrence.
- Don't `pip install --upgrade` a dependency to see if it helps. That changes many variables at once
  and destroys the causal evidence, exactly as `SKILL.md` warns.
- Don't paper over an intermittent test with a `sleep` or a retry unless the contract genuinely
  requires it.
- Don't leave `breakpoint()` in committed code. Ruff's `T100` flags it; make the linter own this.
