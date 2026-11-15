# Debugging C++

Use these mechanics with the hypothesis loop in `SKILL.md`. Keep language rules and prevention in
`using-cpp`; this reference chooses evidence and explains what the tools can mislead you about.

## Match the symptom to the first useful evidence

| Symptom | First evidence |
|---|---|
| Compiler or linker failure | Complete diagnostic plus the exact compile or link command |
| Crash | Signal or exception, faulting thread, and a symbolized all-thread backtrace |
| Hang or deadlock | All thread backtraces from one stop; take a later snapshot if progress is unclear |
| Memory, undefined-behavior, or race symptom | The sanitizer workflow in `using-cpp`, then its first complete report |
| Optimization-only wrong result | Original optimized artifact, then a separate instrumented run of the same input |
| A value changes unexpectedly | A data watchpoint on the smallest stable field or address |
| Exception appears far from its throw | An exception catchpoint, then the first caller in project code |
| Iterator, bounds, or container contract failure | A fully rebuilt standard-library debug or hardening variant |

Pick the instrument that can distinguish the leading hypotheses, then reduce the failing input or
call path. Line-by-line stepping before that decision produces volume without testing a cause.

Read `cpp-patterns/references/tooling.md` for sanitizer selection, build flags, report handling, and
proof. Return here with the instrumented artifact and report; do not maintain a second sanitizer
recipe in this reference.

## Prove what was built

Preserve the failing executable before rebuilding. Record its compiler and linker versions, target
architecture, build configuration, shared-library set, debug-symbol artifact, exact input, and
exact command. A rebuilt binary with the same filename is not the same evidence.

Inspect the commands the build system actually ran. With CMake, `cmake --build <dir> --verbose`
shows them. A debug flag that appears in the shell but not that command is not evidence.

```sh
# Good: keep the failing tree intact and configure a distinct evidence build.
cmake -S . -B build/debug-evidence -DCMAKE_BUILD_TYPE=Debug
cmake --build build/debug-evidence --verbose

# Bad: this does not prove a cached tree was rebuilt with these flags.
CXXFLAGS="-g" cmake --build build
```

Prefer the project's checked-in preset or sanitizer target. If none exists, add flags through the
project's build graph so every relevant translation unit and the final link use the same variant.

| Symptom | Cause | Preferred replacement | Proof |
|---|---|---|---|
| Existing CMake tree ignores new `CXXFLAGS` | The environment initializes the cache only on first configuration | Use a distinct configured tree or checked-in preset | Verbose output shows the intended flag on compile and final link |
| `CMAKE_BUILD_TYPE=Debug` has no effect | The generator is multi-config | Build with `--config Debug` | The selected artifact and command identify `Debug` |
| Release fails; debug passes | Optimization, layout, or timing changed the execution | Preserve the release artifact; create a second instrumented build | The original still reproduces and the second build tests one named hypothesis |

Debug information and optimization are independent. For a source-stepping build, GCC recommends
`-Og` with `-g` when no other optimization level is required. For a release-only failure, retain the
shipping optimization and symbols first; an unoptimized rebuild may remove the failure you need to
explain.

## Run a read-first debugger loop

Use the debugger that matches the platform and artifact. These are the small command sets worth
remembering:

| Question | GDB | LLDB |
|---|---|---|
| Launch with arguments | `gdb --args ./app arg` | `lldb -- ./app arg` |
| Stop at source | `break file.cpp:42` | `breakpoint set -f file.cpp -l 42` |
| Start or continue | `run` / `continue` | `run` / `continue` |
| See every thread | `thread apply all bt full` | `thread backtrace all` |
| Select a frame | `frame 3` | `frame select 3` |
| Read frame values | `info args`; `info locals` | `frame variable` |
| Stop on a write | `watch -location field` | `watchpoint set variable field` |
| Stop at a C++ throw | `catch throw` | `breakpoint set -E c++` |

At each stop, record the stop reason, thread, frame, arguments, locals, and one predicted next
observation. Move the breakpoint to the last correct boundary instead of collecting an unbounded
step transcript.

If inspecting a value changes behavior, suspect debugger expression evaluation: GDB's `print` may
call target functions and temporarily changes target state. Prefer raw frame values and disable
calls when the session must remain observational:

```text
(gdb) set may-call-functions off
(gdb) info locals
(lldb) frame variable state.index

Bad: print cache[key]
Bad: expression cache[key]
```

The bad expressions may invoke an overloaded `operator[]` and mutate the program. A repeated stop
with raw values unchanged is the proof that observation did not create the transition. Keep
breakpoint conditions to side-effect-free scalar comparisons for the same reason.

A watchpoint that slows dramatically or misses a cross-thread write is likely a software fallback,
or it watches storage an object move invalidated. Set it after storage is stable and confirm the
debugger reports a hardware watchpoint; the proof is a stop at the exact writing instruction.

`catch throw` stops in the C++ runtime on supported GDB targets. Move `up` to project code before
assigning cause, and remember that a caught exception may be expected control flow.

## Preserve and inspect postmortem evidence

A core is a process memory image. Treat it as sensitive: store it in an approved location, restrict
access, and do not upload or paste it into external tools. Preserve the exact executable, matching
debug symbols, and relevant shared libraries with it.

```sh
# Safer default for an artifact that did not come from a trusted build tree.
gdb -nx -iex "set auto-load off" ./app core

# Trusted LLDB session.
lldb ./app -c core
```

Then capture the signal, faulting thread, all thread stacks, registers at the fault, and project
frames. GDB uses build IDs or debug links to match separate symbols. On Apple platforms, analyze the
complete OS crash report only after symbolication and verify that the binary and `dSYM` UUIDs match.

If Linux reports a crash but no `core` file exists, inspect the process core-size limit and
`/proc/sys/kernel/core_pattern`; a pipe there may route the dump to `systemd-coredump` instead of the
working directory. Prefer the routed artifact or an approved per-process capture. Changing
host-wide dump policy unattended can expose other processes' memory and changes more than this
investigation requires.

Attaching is operationally invasive: GDB stops the process immediately and debugger commands can
modify its memory. Obtain authority and confirm availability impact before attaching. Detach when
finished; never use `run` in an attached session because GDB kills the attached process.

## Interpret optimized evidence

| Symptom | Cause | Preferred replacement | Proof |
|---|---|---|---|
| Source line is skipped or repeated | Optimizer reordered, combined, or removed statements | Follow machine state; use disassembly only for the disputed boundary | Instruction flow explains the stop without changing the artifact |
| Value is `<optimized out>` | The debugger cannot recover its current storage | Infer it from preserved inputs/state or use a separate lower-optimization build | The independent evidence predicts the later state |
| A caller or local frame is absent | Inlining or a tail call changed the stack | Inspect inline/tail-call metadata and adjacent frames | The mapped call path accounts for the missing source frame |
| Crash disappears at `-O0` | Optimization, timing, and layout all changed | Reproduce the original; test UB, timing, and layout one at a time | One controlled change predicts presence or absence of the failure |
| `_GLIBCXX_DEBUG` creates impossible container failures | Debug and release template layouts crossed a binary boundary | Rebuild every translation unit that exchanges affected objects | One mode across the boundary removes the introduced ABI mismatch |

```text
Good: reproduce in the original optimized binary, then test one UB hypothesis in a separate
instrumented build.

Bad: rebuild with -O0, observe that the crash disappears, and report an optimizer bug.
```

Finish with the original artifact or configuration: rerun the exact reproduction, the focused
proof, and nearby failure cases. Report which build and tool produced each observation so evidence
from different variants is never mistaken for one execution.
