# What `launchctl` really does, and every state a job can get stuck in

Established 2026-08-04 on **macOS 26.5.1 (build 25F80)**. Every claim below is marked with how it is
known:

- **measured** — a read-only command run on that machine, output kept
- **manual** — `man launchctl`, `man launchd.plist`, or `launchctl help` on that machine
- **binary** — read out of `/bin/launchctl`, `/sbin/launchd` or `/usr/libexec/xpcproxy`. Decisive for
  this OS version, but it is reverse engineering and not documentation
- **reported** — a corroborated account from outside, verified at its source
- **unverified** — believed, and nobody has shown it

Nothing here was established by running a command that changes launchd state. Everything that would
have settled a question by *doing* it is marked unverified on purpose, and stays that way until it
can be done against a scratch install rather than the owner's machine.

This page exists because the requirement it serves is absolute: **a gateway must never be stuck.**
Not in an unknown state, and never locked out of being started. Every row of the failure table at
the bottom therefore has to end in a command that gets out of it, and a row that cannot is a state
the design has to make unreachable.

---

## The verbs

| Verb | Target | Sync? | Notes |
|---|---|---|---|
| `bootstrap <domain> <plist>` | domain + a file | mostly sync | registers the label. Fails 37 if already there |
| `bootout <domain>/<label>` | service | **async** | returns before the process has died — see below |
| `bootout --wait <domain>/<label>` | service | sync | **undocumented**: in `launchctl help bootout`, not in `man launchctl` (manual) |
| `kickstart [-k] [-p] <domain>/<label>` | service | sync | `-k` kills then restarts, atomically. No deregistration, so no race |
| `enable` / `disable <domain>/<label>` | service | sync | writes a store that outlives the plist. See §3 |
| `print <domain>[/<label>]` | either | sync | the truth, verbosely. 113 when the label is unknown |
| `print-disabled <domain>` | domain | sync | the only launchctl view of the disabled store |
| `list [label]` | — | sync | legacy, terser, and lies by omission more than `print` does |

`gui/<uid>` is the login domain and **exists only while that uid owns a live GUI session** (manual).
Over SSH it is not there, and the answer is 125 or 112 rather than anything about the job.

---

## 1. Error codes, and which are worth acting on

Confirmed by running `launchctl error N` (measured):

| Code | Means | Transient? |
|---|---|---|
| 5 | Input/output error | **no — it is a catch-all** |
| 37 | Operation already in progress | no — it is already bootstrapped |
| 108 | Invalid path | terminal |
| 112 | Could not find specified domain | terminal here |
| 113 | Could not find specified service | terminal — the label is not registered |
| 119 | Service is disabled | terminal until enabled |
| 122 | Path had bad ownership/permissions | terminal |
| 125 | Domain does not support specified action | terminal |
| 134 | Service cannot load in requested session | terminal |
| 159 | Sandbox restriction | terminal |
| 161 | Service cannot be launched because of BTM policy | terminal, and invisible — see §5 |

**Error 5 means "go and read the log".** It is returned for a disabled label, a plist with bad
ownership, a path under a TCC-protected directory, a sandboxed caller, and several other unrelated
things. `/bin/launchctl` itself carries the string `Try re-running the command as root for richer
errors.` (binary), which is where that widely-repeated advice comes from. **A command that reports 5
verbatim to a person has told them nothing**, so anything here that meets a 5 has to go and look.

**37 is the honest "already bootstrapped".** `/bin/launchctl` holds `%s: service already %s` with
`bootstrapped` and `disabled` as the two fill-ins (binary), and the code is confirmed in the field
(reported). So 37 is *not* an error for us: it is the state we wanted.

---

## 2. `bootout` is asynchronous, and that is the race

**This is the single most important mechanical fact on this page**, and it is the one the previous
build recorded as an incident: taking a job away returns before the machine has finished doing it,
and offering a replacement into that gap fails with an I/O error that says nothing about timing —
leaving no job at all, so the next attempt succeeds and the one after that fails, alternately, for
ever.

The mechanism, from this machine's own log (measured):

```
bootout initiated by: launchctl[…]
signaled service: Terminated: 15
scheduling cleanup in 5 sec after sending Terminated: 15
exited due to SIGTERM | sent by launchd[1], ran for 15835ms
removing service: <label>
```

The label stays registered until the process actually dies, and `exit timeout = 5` is the
SIGTERM→SIGKILL grace window. **A job that ignores SIGTERM keeps its label alive for up to five
seconds after `bootout` has returned.**

Three ways out, in the order this build should prefer them:

1. **`kickstart -k` for a restart.** It stops and starts atomically and never deregisters, so the
   race does not exist. This is why `gateways restart` uses it rather than stop-then-start.
2. **`bootout --wait` when the label really must go** (uninstall, removal). Undocumented but real
   and implemented — the request carries a `no-einprogress` key, and `launchctl` refuses
   `--wait` for more than one service with `--wait can only be used for booting-out a single
   service.` (binary + manual). Its own help warns it **may block indefinitely**, so it still needs
   a ceiling of ours around it.
3. **Poll until `print` answers 113.** The exit code is confirmed (measured). Treating it as a
   settled convention is not — nobody outside documents it (unverified). Use it as the backstop
   behind a bounded wait, never as the only thing.

---

## 3. Disabled — the state that locks a gateway out of starting

This is exactly the failure the owner named, and it is worse than it looks.

- The state lives in **`/var/db/com.apple.xpc.launchd/disabled.<uid>.plist`**, a flat
  `label => bool` map owned by root (measured). It **persists across reboots** (manual).
- **It is independent of the plist file.** An entry survives deleting the plist entirely — verified
  on this machine, where `ai.rundesk.gateway` appears in the store as `enabled` while no plist of
  that name exists at all (measured). A label that has ever been installed leaves a record behind.
- `bootstrap` against a disabled label fails — reported as **5** in one well-documented case and as
  **119** in another (reported). **Expect either and handle both.**
- Being disabled no longer means unloaded. `launchctl help load` states it outright (manual):
  > In previous versions of launchd, being disabled meant that a service was not loaded. Now,
  > services are always loaded. If a service is disabled, launchd does not advertise its service
  > endpoints.
- The in-plist `Disabled` key still sets an initial default, but **the external store wins** —
  `man launchd.plist` says this state "is kept externally" (manual). Writing `Disabled: false` into
  our plist would therefore be a comforting no-op, which is why this build does not write the key
  at all.
- `print-disabled gui/<uid>` and `print-disabled user/<uid>` return the **same** set: the store is
  per-uid, not per-domain (measured).

**Detection and the way out:** `launchctl print-disabled gui/<uid>` names it, and
`launchctl enable gui/<uid>/<label>` clears it. Anything in this build that starts a gateway has to
ask, because otherwise `start` reports a success while nothing runs — which is the exact shape of
failure this product exists to refuse.

**The System Settings connection.** macOS's Login Items pane writes into this same store: this
machine's `disabled.501.plist` holds precisely its Login Items roster, and the log shows
`Setting service … to disabled (initiated by smd[…])` (measured). So a person toggling a switch in
System Settings can disable a gateway, and `print-disabled` is how we see that they did.

---

## 4. Throttling — it never gives up, and nothing can bypass it

- Default `ThrottleInterval` is 10 seconds (manual). Setting it to `0` is ignored, with
  `/sbin/launchd` carrying the string `ThrottleInterval set to zero. You're not that important.
  Ignoring.` (binary).
- The delay is measured from **launch** time, so the push-out is `minimum runtime − actual runtime`.
  Real lines from this machine (measured):
  ```
  Service only ran for 2 seconds. Pushing respawn out by 8 seconds.
  service spawn deferred by 8 seconds due to throttle
  ```
- Modern launchd adds **exponential** backoff: `interval = base << (crashes − grace)`, hard-capped
  at **1200 seconds** (binary). **There is no code path that stops rescheduling.** The string is
  `service exceeded successive crash limit. launch will be throttled` — throttled, not abandoned.
  The old "may be suspended and not launched again" language survives only in Apple's *archived*
  launchd1 documentation and those strings are absent from the shipping binary; do not design
  against it.
- `launchctl print` has **no "waiting for throttle" line.** The complete state table is
  `not running` · `spawn scheduled` · `spawning` · `running` · `SIGTERMed` · `SIGKILLed` ·
  `languishing` · `exited` (binary). **`state = spawn scheduled` is the throttle window**, confirmed
  by a live transition in the log (measured). The other tell is `minimum runtime` having grown past
  `base minimum runtime`.
- **`kickstart` cannot unthrottle.** The request carries an `unthrottle` flag, but `launchctl` only
  sets it for a `-u` option that is not in kickstart's getopt string — dead code, with no way to
  reach it from the command line (binary). `-k` does not help either: the kill is an exit, which
  re-arms the window.

**What this means for us.** A gateway that crashes on start is retried for ever at up to twenty
minutes apart, and no command shortens that. So the design cannot rely on being able to force a
retry — it has to make the *first* start correct, and it has to be able to say "this is throttled,
it crashed N times, here is the log" rather than appearing to hang.

A different state, **the penalty box**, is for *spawn* failures rather than crash loops — an
unreadable executable, a bad user, a bad architecture. It generally needs bootout/bootstrap to clear
(reported).

---

## 5. What launchctl cannot see at all

**Background Task Management** can block a job with no trace in any launchctl output. The failure
appears only in the unified log (reported):

```
Service could not initialize: Unable to verify trusted spawn(…), error 0xa1
  - Service cannot be launched because of BTM policy
Untrusted service was denied launch by BTM. Removing.
```

`launchctl error 0xa1` is 161 (measured). There are two shapes: the job registers and every spawn
dies with 161 logged, or the job is **never registered at boot at all** — the plist is on disk and
launchd has no record of it, so `print` answers 113 with nothing anywhere mentioning BTM. A manual
`bootstrap` then works for the session and does not survive a reboot, because BTM's own database is
untouched.

`sudo sfltool dumpbtm` is the only authoritative read, and it needs root. **So this build must never
report "not loaded" as a fact when it might be this.** It is the clearest case in the whole design
for the third answer: *cannot tell*, plus where to look.

---

## 6. Standard output, and the trap that eats every log

**launchd does create the parent directory of `StandardOutPath` / `StandardErrorPath`** — the common
belief that it does not is wrong. `/usr/libexec/xpcproxy` calls `mkpath_np(dirname, 0766)` before
staging the spawn, and logs `Unable to create stdout directory (%s)` when it cannot (binary).

**But it creates it before dropping privileges**, so for a job running as another user the directory
lands root-owned at `0766 & ~022 = 0744` — no execute bit for group or other, so the job cannot
traverse into the directory its own configuration just created, and no output ever appears
(reported, with a matching account from Apple). That is why everybody believes launchd does not
create it: they are describing the symptom.

If the file cannot be opened, **the job does not spawn at all** — `xpcproxy` exits 78 (`EX_CONFIG`),
and repeated failures land it in the penalty box.

**So this build creates the agent's `logs/` directory itself, with its own ownership and mode,
before it ever writes a plist.** Those two files are the only account of a start that died before
our own logger existed; a design that let launchd create them is a design where the evidence of the
failure is the thing that failed.

Where to look when it happens:

```sh
log show --last 1h --predicate 'process == "launchd" OR process == "xpcproxy"' --info --style compact
```

`xpcproxy` matters as much as `launchd` here, because the stdio failures come from it.

---

## 7. Ownership, permissions and symlinks

- An agent's plist in `~/Library/LaunchAgents` must be owned by the loading user and **must disallow
  group and world writes** (manual, stated under the legacy `load` section but enforced by
  `bootstrap` in every field report). Read bits do not matter — a working mix of `0644` and `0600`
  is present on this machine (measured). **We write `0600`.**
- Bad ownership surfaces as **122**, or as **5** with the real reason only in the log (reported).
- **Symlinks are loaded by an explicit `bootstrap` and ignored at login from macOS 14 onwards**
  (reported, consistent community testing, no Apple statement either way). This kills the tidy idea
  of keeping the real plist under `RUNDESK_HOME` and linking it into `~/Library/LaunchAgents`: it
  would work when tested by hand and silently fail to survive a reboot, which is the worst of both.
  **We write a real file.**

---

## 8. The environment a job actually gets

A `gui/` agent inherits almost nothing. The previous build recorded losing a working provider
because `~/.local/bin` was missing from the job's `PATH` while `which` in the owner's shell answered
perfectly well — rundesk had installed itself into a directory it then refused to look in.

So `EnvironmentVariables` carries everything the job needs. For this build that is exactly three
things — `RUNDESK_HOME`, `HOME`, and a `PATH` that includes `~/.local/bin` — and the shortness of
that list is the point. The previous build baked in **nine** `RUNDESK_*_DIR` variables and was still
wrong, because a tenth was added later and nothing caught it.

---

## The failure table

Every state a gateway can be in, how to tell, and the command that gets out.

| State | How it is detected | The way out |
|---|---|---|
| Running normally | flock held, `print` says `state = running` | — |
| Stopped, job loaded | flock free, `print` succeeds | `rundesk gateways start <agent>` |
| Job not registered | `print` → 113 | `rundesk gateways start <agent>` — writes the plist and bootstraps |
| Already bootstrapped | `bootstrap` → 37 | nothing to do; it is the state we wanted |
| Plist stale (points at a moved program) | `print` shows the old path | `rundesk gateways start <agent>` rewrites the plist, boots out and back |
| Crash-looping / throttled | `print` shows `state = spawn scheduled`, `minimum runtime` grown | read the log; fix the cause. **No command shortens the throttle** |
| Wedged (alive, not beating) | flock held, beat older than 3 intervals | `rundesk gateways restart <agent> --force` → `kickstart -k` |
| Disabled | `print-disabled gui/<uid>` names it | `launchctl enable gui/<uid>/<label>` — and `start` does this itself |
| Spawn failure / penalty box | `print` shows `penalty box`, log shows the reason | bootout then bootstrap — what `start` does anyway |
| Bad plist ownership | `bootstrap` → 122, or 5 with the reason in the log | `start` rewrites it `0600`, owned by us |
| Log directory unwritable | job never spawns; `xpcproxy` exits 78 | `start` creates `logs/` itself before writing the plist |
| **Blocked by BTM** | **nothing in launchctl. Log shows 161** | **System Settings → General → Login Items. `sudo sfltool dumpbtm` to confirm** |
| No GUI session (SSH) | `bootstrap` → 125 or 112 | log in at the desktop, or run `rundesk gateways run <agent>` in the foreground |

**The two rows with no command of ours in them are BTM and the throttle**, and they are the two the
design has to answer differently rather than fix:

- **BTM** is why `rundesk gateways` reports the job as *cannot tell* rather than *not loaded* when
  the plist is present and launchd has no record of it. Reporting "not loaded" there would be a
  confident wrong answer, and the person would go on to reinstall something that is not broken.
- **The throttle** is why a gateway that refuses to run **exits 0**. With
  `KeepAlive: {SuccessfulExit: false}`, exiting 0 means *do not bring me back* — so a gateway that
  cannot run says why, once, and stops. Exiting non-zero would have the machine retry it for ever at
  up to twenty minutes apart, which is the closest thing to permanently stuck that launchd offers.

---

## What is still unverified, and how to settle it

None of these can be answered without running a state-changing command, and none of them will be run
against the owner's machine. They are settled against a scratch install with a fingerprinted label,
during the real run at the end of this work.

- Whether `bootout --wait` waits for the whole teardown or only for the process to exit.
- Whether `kickstart` on a disabled service really answers 119.
- What `print` shows for a job genuinely sitting inside its throttle window.
- Whether writing the plist alone triggers the BTM notification, or only bootstrapping does.
- The precise boundary between 112 and 125 for a session with no GUI.

## One incidental measurement worth keeping

On this machine, `ai.rundesk.gateway` appears in `disabled.501.plist` as `enabled` while **no plist
of that name exists** (measured). A label that has ever been installed leaves a record in launchd's
store that removing the plist does not clear.

That is not a leak worth chasing — the entry is inert and says `enabled` — but it is the concrete
proof of §3's claim that the store is independent of the file, and it is a reason removal should say
what it took rather than assume the label is gone once the file is.
