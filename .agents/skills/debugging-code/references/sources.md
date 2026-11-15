# Debugging source basis

This package is a Rundesk synthesis of framework documentation, the debugging tools each ecosystem
ships, and practitioner writing on debugging as a skill. `SKILL.md` holds the language-agnostic
workflow; the per-framework references hold the mechanics. Use this file to audit or update a claim.

**Read in this order of authority.** Framework documentation states what a tool reports; practitioner
sources carry the judgement about which observation to make next. Verified in **August 2026**,
against GCC 15.3, GDB 17.2, Clang/LLDB 24 development documentation, CMake 4.4, Laravel 13,
Laravel Herd 1.28.0, Vue 3.5 / Nuxt 4, and Python 3.14.

## Debugging as a skill

- [Some ways to get better at debugging](https://jvns.ca/blog/2022/08/30/a-way-to-categorize-debugging-skills/) —
  **Julia Evans**. The five categories: learn the codebase, learn the system, learn your tools, learn
  strategies, get experience. Her finding that experts do not use different strategies but "formed
  more correct hypotheses and were more efficient at finding the fault" is why `SKILL.md` is a
  hypothesis loop rather than a tool list.
- [A debugging manifesto](https://jvns.ca/blog/2022/12/08/a-debugging-manifesto/) and
  [The Pocket Guide to Debugging](https://jvns.ca/blog/2022/12/21/new-zine--the-pocket-guide-to-debugging/) —
  reproduce the bug, be rigorous, divide the problem space in half, print stuff out. Also the
  argument for leaving the bug in place and understanding it before fixing it.
- [What does debugging a program look like?](https://jvns.ca/blog/2019/06/23/a-few-debugging-resources/)

## Laravel

- [Error handling](https://laravel.com/docs/13.x/errors) — the `bootstrap/app.php` exception handler,
  `report()` and `render()` callbacks, global and per-exception log context, log levels, `dontReport`,
  throttling, and the `APP_DEBUG` production warning.
- [Logging](https://laravel.com/docs/13.x/logging) · [Queues](https://laravel.com/docs/13.x/queues) —
  `queue:failed`, the `failed()` hook, `afterCommit`, timeout versus retry_after.
- [Telescope](https://laravel.com/docs/13.x/telescope) — the request-level recorder, and the
  statement that it "is not recommended for production environments."
- [Pulse](https://laravel.com/docs/13.x/pulse) — the production-safe performance view.
- [Nightwatch versus Telescope](https://nightwatch.laravel.com/nightwatch-vs-telescope) — which tool
  answers which question.
- [Configuration](https://laravel.com/docs/13.x/configuration) — the `config:cache` / `env()`
  warning, which is the mechanism behind "works locally, null in production."
- [Eloquent](https://laravel.com/docs/13.x/eloquent) — `preventLazyLoading` as an N+1 detector, and
  mass operations firing no model events.
- [Debugging and logging in Laravel applications](https://laravel-news.com/debugging-and-logging-in-laravel-applications) —
  Laravel News.

## Laravel Herd

- Herd command line for [macOS](https://herd.laravel.com/docs/macos/advanced-usage/herd-cli) and
  [Windows](https://herd.laravel.com/docs/windows/advanced-usage/command-line), plus
  [PHP versions](https://herd.laravel.com/docs/macos/technology/php-versions) — map the exact site,
  isolated PHP binary and ini, debugger, logs, TLS state, and service status before changing the
  application. They support the good/bad runtime-identity pair in `herd.md`. Verified on August 7,
  2026 against the Herd 1.28.0 command surface recorded by the changelog below.
- [Sites](https://herd.laravel.com/docs/macos/getting-started/sites) and
  [managing sites](https://herd.laravel.com/docs/macos/sites/managing-sites) — parked directories,
  explicit links, per-site isolation, and the documented destructive Site Manager delete action;
  the [changelog](https://herd.laravel.com/docs/macos/changelog/index) records `herd link`
  updating `.env` `APP_URL` and later adding `--update-env` to force that rewrite.
- Herd's [macOS](https://herd.laravel.com/docs/macos/troubleshooting/common-issues) and
  [Windows](https://herd.laravel.com/docs/windows/troubleshooting/common-issues) troubleshooting
  pages — a Herd 404, bad gateway, or DNS failure precedes Laravel; the underlying resolver and
  helper differ by platform.
- [Dumps](https://herd.laravel.com/docs/macos/debugging/dumps) — Herd's extension injects during
  early bootstrap, supporting the disable-and-repeat experiment when capture changes behavior.
- [Browser-versus-CLI PHP mismatch](https://github.com/beyondcode/herd-community/issues/831) and
  [CLI ini mismatch](https://github.com/beyondcode/herd-community/issues/267) — Herd maintainers
  traced reproduced failures to an older PHP earlier on `PATH` and to the wrong CLI ini; both
  support comparing plain commands with Herd's site-aware proxies before changing code.

## Vue and Nuxt

- [Vue DevTools features](https://devtools.vuejs.org/getting-started/features) — what each tab
  answers, including the Vite inspector that maps a DOM node to the component that rendered it.
- [Vue DevTools FAQ](https://devtools-v6.vuejs.org/guide/faq) — lazy reactivity, and why the force
  refresh button exists. This is a real source of false conclusions.
- [Reactivity in depth](https://vuejs.org/guide/extras/reactivity-in-depth) — `onRenderTracked` and
  `onRenderTriggered`, and the documented recommendation to put a `debugger` statement in the
  callback.
- [Composition API lifecycle hooks](https://vuejs.org/api/composition-api-lifecycle) ·
  [Watchers](https://vuejs.org/guide/essentials/watchers.html) — `onTrack` / `onTrigger`.
- [Server-side rendering](https://vuejs.org/guide/scaling-up/ssr.html) — the three documented
  hydration-mismatch causes, and that Vue recovers automatically "at a performance loss," which is
  why the warning gets ignored.
- [Performance](https://vuejs.org/guide/best-practices/performance.html) — `app.config.performance`.
- [Nuxt data fetching](https://nuxt.com/docs/4.x/getting-started/data-fetching) — the documented
  double-fetch when `$fetch` is used bare in `setup`.
- [Debugging guide: why your Vue component isn't updating](https://michaelnthiessen.com/debugging-guide-why-your-component-isnt-updating) —
  **Michael Thiessen**. The practical checklist behind the symptom table.

## Python

- [`pdb`](https://docs.python.org/3/library/pdb.html) — `breakpoint()`, `PYTHONBREAKPOINT`,
  `pdb.pm()` and `post_mortem()`, conditional breakpoints, `display`, `interact`, running a module
  under the debugger, and attaching to a process on 3.14+.
- [Python Development Mode](https://docs.python.org/3/library/devmode.html) — every check `-X dev`
  enables, and the explicit caveat that faulthandler "does not prevent or catch hangs."
- [`faulthandler`](https://docs.python.org/3/library/faulthandler.html) ·
  [`tracemalloc`](https://docs.python.org/3/library/tracemalloc.html) — snapshot comparison for leaks.
- [`traceback`](https://docs.python.org/3/library/traceback.html) ·
  [`logging`](https://docs.python.org/3/library/logging.html) ·
  [`profile` / `cProfile`](https://docs.python.org/3/library/profile.html).
- [Python Programming FAQ](https://docs.python.org/3/faq/programming.html) — the circular-import
  asymmetry, and `importlib.reload()` leaving existing instances on the old class.
- [py-spy](https://github.com/benfred/py-spy) — **the answer for a hung process.** `dump` prints every
  thread's stack without modifying the program, with `--locals` for frame variables, and is designed
  to be safe against production traffic.
- [pytest — how to invoke](https://docs.pytest.org/en/stable/how-to/usage.html) — `-x`, `--lf`,
  `--pdb`.

## C++

### Build identity and optimized code

- [GCC 15.3 debugging options](https://gcc.gnu.org/onlinedocs/gcc-15.3.0/gcc/Debugging-Options.html) and
  [GDB 17.2: optimized code](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Optimized-Code.html) —
  `-g` is independent of optimization; GCC recommends `-Og` when no other optimization is required;
  optimized code can remove variables, reorder statements, inline calls, and break the apparent
  source-to-machine sequence. Verified on 2026-08-07.
- [CMake `CXXFLAGS`](https://cmake.org/cmake/help/latest/envvar/CXXFLAGS.html),
  [`GENERATOR_IS_MULTI_CONFIG`](https://cmake.org/cmake/help/latest/prop_gbl/GENERATOR_IS_MULTI_CONFIG.html),
  and [`cmake --build`](https://cmake.org/cmake/help/latest/manual/cmake.1.html#build-a-project) —
  `CXXFLAGS` initializes the cache only on first configuration, multi-config generators ignore
  `CMAKE_BUILD_TYPE`, and `--config` / `--verbose` select and expose the actual build. Verified
  against CMake 4.4.2 on 2026-08-07.

### GDB and LLDB mechanics

- [GDB 17.2 command summary](https://sourceware.org/gdb/download/onlinedocs/gdb.html/gdb-man.html),
  [watchpoints](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Set-Watchpoints.html), and
  [C++ catchpoints](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Set-Catchpoints.html) —
  launch, break, backtrace, inspect, watch, and catch-throw syntax; software-watchpoint cost and
  multi-thread limits; an exception catchpoint stopping in the runtime before project frames.
- [GDB 17.2: calling program functions](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Calling.html),
  [attaching](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Attach.html), and
  [auto-loading](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Auto_002dloading.html) —
  expression evaluation can call target code and alter or crash the process; attach stops the
  process; `run` after attach kills it; `-nx` plus early `set auto-load off` avoids scripts from an
  untrusted artifact. Verified on 2026-08-07; the
  [release documentation index](https://sourceware.org/gdb/download/onlinedocs/) identified 17.2 as
  the latest release manual.
- [LLDB tutorial](https://lldb.llvm.org/use/tutorial.html) and
  [GDB-to-LLDB command map](https://lldb.llvm.org/use/map.html), plus the
  [LLDB breakpoint option source](https://github.com/llvm/llvm-project/blob/main/lldb/source/Commands/Options.td) —
  precise breakpoints including the C++ exception form, watchpoints, all-thread backtraces, frame
  selection, and `frame variable` as the non-expression path for frame data. Pages were checked on
  2026-08-07 against LLDB 24 development docs; `breakpoint set -E c++` was also verified with Apple
  LLDB 2100.0.17.108 command help.

### Optimized and checked-library evidence

- [GNU libstdc++ debug mode](https://gcc.gnu.org/onlinedocs/libstdc%2B%2B/manual/debug_mode_using.html) —
  `_GLIBCXX_DEBUG` changes standard-template sizes and behavior, so debug and release translation
  units cannot exchange affected container instantiations safely. Verified with GCC 15.3 docs on
  2026-08-07.
- [What Every C Programmer Should Know About Undefined Behavior](https://blog.llvm.org/2011/05/what-every-c-programmer-should-know.html) —
  **Chris Lattner**, LLVM project founder, 2011. Maintainer explanation of how UB licenses
  optimization transformations inherited by C++; supports treating optimization-only behavior as
  a UB lead rather than proof of an optimizer defect. Checked 2026-08-07.

### Cores and crash reports

- [GDB 17.2 core files](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Files.html) and
  [separate debug files](https://sourceware.org/gdb/download/onlinedocs/gdb.html/Separate-Debug-Files.html) —
  postmortem loading and build-ID/debug-link matching between an executable and symbols.
- Linux man-pages [`core(5)`](https://man7.org/linux/man-pages/man5/core.5.html) and
  [`systemd-coredump(8)`](https://man7.org/linux/man-pages/man8/systemd-coredump.8.html) — dump
  suppression causes, `core_pattern` routing, and core files as process memory images. The catalog's
  sensitive-artifact rule is the safety conclusion from that memory-image contract. Checked
  2026-08-07.
- Apple [Analyzing a crash report](https://developer.apple.com/documentation/xcode/analyzing-a-crash-report)
  and [Adding identifiable symbol names](https://developer.apple.com/documentation/xcode/adding-identifiable-symbol-names-to-a-crash-report) —
  use the complete OS report, require full symbolication, and match binary / `dSYM` UUIDs. Checked
  2026-08-07.

## Related skills in this catalog

The framework references here deliberately stop at *how to observe*. The rules a symptom violates
live with the language:

- `using-laravel` — especially queues, Eloquent, and performance.
- `using-vuejs` — especially reactivity, SSR, and separation of concerns.
- `using-python` — especially `documented-traps.md`, which explains the failures behind several
  symptoms listed here.
- `using-cpp` — especially `tooling.md` and `undefined-behavior.md`, for build integration and
  the language rules behind sanitizer and optimization symptoms.
- `testing-code` and `reviewing-code` own the surrounding process: proving a correction with a
  test that fails without it, and judging a completed change.

## What this package deliberately does not cite

- Tool round-ups that list every debugger without saying which question each answers.
- Version-specific screenshots and UI walkthroughs, which age faster than the tools.
- "Top N debugging tips" posts with no mechanism behind the advice.


## Herd

- Herd command line for [macOS](https://herd.laravel.com/docs/macos/advanced-usage/herd-cli) and
  [Windows](https://herd.laravel.com/docs/windows/advanced-usage/command-line) — site, PHP, TLS,
  debugging, logging, and service commands; verified against Herd 1.28.0 on August 7, 2026
- [Sites](https://herd.laravel.com/docs/macos/getting-started/sites) and
  [managing sites](https://herd.laravel.com/docs/macos/sites/managing-sites) — parked versus linked
  directories, per-site isolation, and the destructive Site Manager delete action; the
  [changelog](https://herd.laravel.com/docs/macos/changelog/index) records `herd link` updating
  `.env` `APP_URL` and later adding `--update-env` to force that rewrite
- [macOS common issues](https://herd.laravel.com/docs/macos/troubleshooting/common-issues) and
  [Windows common issues](https://herd.laravel.com/docs/windows/troubleshooting/common-issues) —
  platform-specific 404, bad gateway, DNS, helper, and log evidence
- [Dumps](https://herd.laravel.com/docs/macos/debugging/dumps) — early PHP extension injection and
  capture-feature isolation
- [Browser-versus-CLI PHP mismatch](https://github.com/beyondcode/herd-community/issues/831) and
  [CLI ini mismatch](https://github.com/beyondcode/herd-community/issues/267) — Herd maintainer
  diagnoses of real failures caused by a different PHP or ini on the command path

## Laravel

- [Error handling](https://laravel.com/docs/13.x/errors) — the `bootstrap/app.php` handler, `report()`, log context, log levels, throttling, and the `APP_DEBUG` production warning
- [Logging](https://laravel.com/docs/13.x/logging) · [Telescope](https://laravel.com/docs/13.x/telescope) — "not recommended for production environments" · [Pulse](https://laravel.com/docs/13.x/pulse)
- [Queues](https://laravel.com/docs/13.x/queues) — failed jobs, `failed()`, `afterCommit`, timeout vs retry_after
- [Configuration](https://laravel.com/docs/13.x/configuration) — the `config:cache` / `env()` warning
- [Eloquent](https://laravel.com/docs/13.x/eloquent) — `preventLazyLoading`, and mass operations not firing events
- [Nightwatch vs Telescope](https://nightwatch.laravel.com/nightwatch-vs-telescope) — which tool answers which question
- [Debugging and logging in Laravel applications](https://laravel-news.com/debugging-and-logging-in-laravel-applications) — Laravel News
- `using-laravel` in this catalog for the underlying rules these symptoms violate

## Python

- [`pdb`](https://docs.python.org/3/library/pdb.html) — `breakpoint()`, `PYTHONBREAKPOINT`, post-mortem, conditional breakpoints, `display`, `interact`, `-m pdb -p`
- [Python Development Mode](https://docs.python.org/3/library/devmode.html) — every check `-X dev` enables, and the faulthandler caveat about hangs
- [`faulthandler`](https://docs.python.org/3/library/faulthandler.html) · [`tracemalloc`](https://docs.python.org/3/library/tracemalloc.html) — snapshot comparison for leaks
- [`traceback`](https://docs.python.org/3/library/traceback.html) · [`logging`](https://docs.python.org/3/library/logging.html) — `logger.exception`
- [`profile` and `cProfile`](https://docs.python.org/3/library/profile.html) — measure before optimizing
- [py-spy](https://github.com/benfred/py-spy) — `dump` for hung processes, `--locals`, production safety
- [Python Programming FAQ](https://docs.python.org/3/faq/programming.html) — circular imports, `importlib.reload` and stale instances
- [pytest — how to invoke](https://docs.pytest.org/en/stable/how-to/usage.html) — `-x`, `--lf`, `--pdb`
- `using-python` in this catalog, especially `documented-traps.md`, for the failures behind these symptoms

## React

- [React Developer Tools](https://react.dev/learn/react-developer-tools) and
  [`<Profiler>`](https://react.dev/reference/react/Profiler) establish the Components and Profiler
  panels, render attribution, and that profiling adds overhead.
- [`<StrictMode>`](https://react.dev/reference/react/StrictMode) establishes exactly what is
  double-invoked and that it is development-only.
- [`useSyncExternalStore`](https://react.dev/reference/react/useSyncExternalStore) establishes the
  cached-snapshot requirement, the `getSnapshot should be cached` error and its loop, and the
  server-snapshot contract behind the hydration case.
- [`hydrateRoot`](https://react.dev/reference/react-dom/client/hydrateRoot) establishes hydration
  mismatch reporting and per-element suppression.
- [`createRoot`](https://react.dev/reference/react-dom/client/createRoot) establishes
  `onUncaughtError` and `onCaughtError`, and the
  [React 19 upgrade guide](https://react.dev/blog/2024/04/25/react-19-upgrade-guide) establishes that
  render errors are no longer re-thrown and now reach `window.reportError` or `console.error`.
- [Error boundaries](https://react.dev/reference/react/Component#static-getderivedstatefromerror)
  establish fallback capture, which is why a boundary can hide a failure.
- The [error decoder](https://react.dev/errors) maps a minified production error code to its message.

The symptom-ordering tables and the trap list are this package's operational conclusions, not claims
made by those pages. Links checked 23 August 2026.

## Vue

- [Vue DevTools features](https://devtools.vuejs.org/getting-started/features) — what each tab answers
- [Vue DevTools FAQ](https://devtools-v6.vuejs.org/guide/faq) — lazy reactivity and force refresh
- [Reactivity in depth](https://vuejs.org/guide/extras/reactivity-in-depth) — `onRenderTracked` / `onRenderTriggered` and the `debugger` technique
- [Composition API lifecycle hooks](https://vuejs.org/api/composition-api-lifecycle) · [Watchers](https://vuejs.org/guide/essentials/watchers.html) — `onTrack` / `onTrigger`
- [Server-side rendering](https://vuejs.org/guide/scaling-up/ssr.html) — the three documented mismatch causes and the automatic-recovery cost
- [Performance](https://vuejs.org/guide/best-practices/performance.html) — `app.config.performance`, prop stability
- [Nuxt data fetching](https://nuxt.com/docs/4.x/getting-started/data-fetching) — the double-fetch warning
- [Debugging guide: why your Vue component isn't updating](https://michaelnthiessen.com/debugging-guide-why-your-component-isnt-updating) — **Michael Thiessen**; the practical checklist this page's first table is built on
- `using-vuejs` in this catalog for the underlying rules these symptoms violate
## Attribution

This package adapts `skills/debugging-code/` from the Rundesk skills catalog at
<https://github.com/rundesk-ai/rundesk-skills>, commit
`680e3d720547dbb563e6e15808e15c8f5bdd4083`, published by Rundesk AI under the MIT License.

Material modifications: the routing description narrowed against its neighbouring packages in this
catalog; stack pointers retargeted to the `using-` packages and marked as non-dependencies;
`references/react.md` added, written from React's official documentation, because the upstream
package covered Vue but not React; and a maintainer validation record added.
