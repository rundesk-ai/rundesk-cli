# What `launchctl` really does, and every state a job can get stuck in

Established 2026-08-04 against **macOS 26.5.1 (build 25F80)**, Darwin 25.5.0, arm64, `launchd`
`Darwin Bootstrapper 7.0.0`, session manager `Aqua`. Read-only throughout: no `bootstrap`, `bootout`,
`kickstart`, `enable`, `disable`, `load`, `unload`, `kill`, `start` or `stop` was run, and
`~/.rundesk` was not touched.

Every claim is marked with how it is known:

- **`[RAN]`** — a command executed on that machine; the output is what is reported
- **`[MAN]`** — `man launchctl`, `man 5 launchd.plist`, or `launchctl help <verb>` on that machine
- **`[BIN]`** — a format string read out of `/sbin/launchd`, `/bin/launchctl` or
  `/usr/libexec/xpcproxy`. Strong but inferential: it shows the message launchd *can* emit, not
  always the condition that emits it
- **`[RECALL]`** — believed and **not verified here**, because verifying it needs a state-changing
  command. Treat every one as a hypothesis to settle against a scratch label before relying on it

> **This page was rebuilt once.** An earlier draft carried outside citations that had not been read.
> They are gone. What follows is first-party — commands run here, manual pages here, strings from the
> binaries here — or explicitly marked `[RECALL]`. The reason to record that rather than quietly fix
> it is that a confident answer nobody earned is the exact failure this product exists to refuse, and
> the marks are only worth anything if they are applied when it is inconvenient.

This page exists to serve one absolute requirement: **a gateway must never be stuck** — not in an
unknown state, and never locked out of being started. So every state it can reach has to end in a
command that gets out of it. **One does not**, and designing around that one is the most important
thing on this page.

---

## 1. The verbs

| Verb | Target | Sync? | Notes |
|---|---|---|---|
| `bootstrap <domain> <plist-path…>` | **domain + path**, never a service target | accepts sync, **spawns async** | `[MAN]` |
| `bootout <service-target>` or `<domain> <path>` | either | **async by default** | `[MAN]` |
| `bootout --wait <service-target>` | **service target only** | sync | exists on 26.5.1 `[MAN]`, absent from the man page |
| `kickstart [-kps] <service-target>` | service | request sync, spawn async | `-k` kill-then-restart, `-p` print pid, `-s` start suspended (`-s` is in `help`, not the man page) `[MAN]` |
| `enable` / `disable <service-target>` | service | sync | writes a **persistent** override — §4 |
| `print <domain>` \| `<service-target>` | either | sync | `[MAN]`: *"This output is NOT API in any sense at all."* |
| `print-disabled <domain>` | **domain only** | sync | the only launchctl view of the override store |
| `list [label]` | **bare label**, no domain | sync | legacy, and misleading — §6 |
| `kill <sig> <service-target>` | service | sync request, async death | signals only; does not unload |
| `load` / `unload [-wF] <path>` | path | async | `[MAN]`: *"will only return a non-zero exit code due to improper usage. Otherwise, zero is always returned."* **Never use for status.** |

`gui/<uid>` is the login domain: `[RAN]` `gui/501 = { type = login, creator = loginwindow, session = Aqua }`.
It exists only while that uid owns a live GUI session.

---

## 2. Exit codes

`launchctl error <n>` decodes them; the whole 110–160 range was enumerated `[RAN]`.

| Code | Text | What it means here | Class |
|---|---|---|---|
| 3 | No such process | `bootout` by path, label already gone | terminal, **benign** |
| 5 | Input/output error | launchd's catch-all. In practice: bootstrapping into a domain still tearing down the previous instance of that label | **transient** for the race; terminal if it repeats |
| 17 | File exists | already bootstrapped `[RECALL]` | terminal, **benign** |
| 36 / 37 | Operation now / already in progress | a request is mid-flight | **transient** — wait and re-poll, do not re-issue |
| 110 / 111 | Invalid or missing service identifier / Program | bad plist | terminal |
| 112 | Could not find specified domain | **no GUI session for this uid** | terminal *in this session* |
| **113** | Could not find specified service | launchd does not know this label | **terminal and ambiguous — §6** |
| **119** | Service is disabled | the override store says so | **terminal until `enable`** |
| 122 | Path had bad ownership/permissions | plist not ours, or group/world-writable | terminal |
| 124 | Domain is tearing down | logging out | terminal for this session |
| 125 | Domain does not support specified action | wrong domain for the verb | terminal |
| 133 | Multiple errors were returned | several plist paths given | terminal — parse stderr per path |
| 134 | Service cannot load in requested session | `LimitLoadToSessionType` mismatch | terminal |
| 155 | Refusing to execute/trust quarantined program | `com.apple.quarantine` on the interpreter or script | terminal |
| 159 | Sandbox restriction | | terminal |

Measured exactly `[RAN]`:

```
print gui/501/ai.hermes.gateway        -> 0
print gui/501/ai.openclaw.gateway      -> 113   (plist exists on disk)
print gui/501/totally.made.up.label    -> 113   (byte-identical)
print gui/9999/whatever                -> 112
print-disabled gui/501                 -> 0
```

launchctl's envelopes, for parsing `[BIN]`: `Bootstrap failed: %d: %s`, `Boot-out failed: %d: %s`,
`Could not kickstart service "%s": %d: %s`, `%s: service already %s`. **Prefer the process exit code
to the text** — it is the same number and it does not get reworded.

> **A trap that cost the researcher an hour, and would cost us a wrong answer.** Piping `launchctl`
> through anything makes `$?` the *pipe's* exit code: a command that really returned 113 read as 0.
> In `subprocess`, never pipe launchctl through a filter — capture it and post-process in Python.

---

## 3. Idempotency, and the race this build already hit once

**`bootout` is asynchronous, and this was observed directly** `[RAN]`. Taking down a real running
gateway (`ExitTimeOut = 25`) on 2026-08-04:

```
$ launchctl bootout gui/501/<label>      -> rc=0
$ launchctl print   gui/501/<label>      -> rc=0        still registered
$ ps -p <pid>                            -> STILL ALIVE
```

**`bootout` reported success while the label was still registered and the process still running.**
A build that treated rc 0 as "it is gone" and bootstrapped next would have hit exactly the recorded
I/O error. Polling `print` then showed the label released a moment later, once SIGTERM had landed:

```
$ launchctl print gui/501/<label>        -> rc=113      gone
$ ps -p <pid>                            -> gone
```

**And `bootout` on a label that was never loaded** `[RAN]` — previously `[RECALL]`:

```
$ launchctl bootout gui/501/<never-loaded-label>
Boot-out failed: 3: No such process       -> rc=3
```

So **0, 3 and 113 all mean "it is not there any more"** and an uninstall treats all three as success.
What an uninstall must *not* do is treat rc 0 as "the process has stopped".

`launchctl help bootout` on this machine `[MAN]`:

> `--wait` — Waits for bootout to complete before returning. Only applicable to a single service
> target. (WARNING: this may block indefinitely).

So the correct cycle is `bootout --wait` (service-target form is required for `--wait`), then
`bootstrap`, with our own ceiling around it because of that warning. The fallback is to poll
`print` until it answers 113 — never `sleep(2)`, which is the shape that produced the previous
build's recorded I/O error and left it with no job at all.

That teardown is genuinely multi-stage `[BIN]`: `Service did not exit %u seconds after SIGTERM.
Sending SIGKILL.`, `exceeded sigkill timeout: %u`, `service is still not a zombie, abandoning`,
`Cannot safely abandon service instance. Leaving it to languish.` **If the gateway ignores SIGTERM,
`bootout --wait` blocks for the whole `ExitTimeOut`.**

**Overwriting the plist while the job is loaded does nothing.** launchd holds an imported in-memory
copy; nothing watches the file `[MAN + RECALL]`. Worse, and this is the finding that matters most
in this section `[BIN]`:

```
Attempt to re-bootstrap service from different path, will use existing:
  service = %s, existing = %s, conflicting = %s
```

**launchd keeps the existing definition and ignores the new plist, without failing.** A build that
rewrote a plist and bootstrapped over it would go on running the old program for ever with nothing
on the command line saying so.

> **Design rule taken from this: every plist write is followed by an unconditional
> `bootout --wait` → `bootstrap` cycle.** Never bootstrap over a live job, and always compare
> `print`'s `path =` against the plist we just wrote.

---

## 4. Disabled — and two other lockouts, one with no way out

### Where it lives, and that it outlives the plist

`[RAN]` `/var/db/com.apple.xpc.launchd/disabled.501.plist`, root-owned `0644`.
`[MAN 5 launchd.plist]` on `Disabled`: *"Previous Darwin operating systems would modify the
configuration file's value for this key, but now this state is kept externally."*
`[MAN launchctl]`: *"This state persists across boots of the device."*

Proven on this machine `[RAN]`:

```
$ plutil -p /var/db/com.apple.xpc.launchd/disabled.501.plist
  "ai.rundesk.gateway" => false      <-- no plist of that name exists anywhere
```

**A previous rundesk install wrote that record and uninstalling did not clear it.** So a stale
`disable` from an install that is long gone can silently poison a future one that reuses the label.

**Measured a second time, deliberately** `[RAN]`. On 2026-08-04 the machine's Hermes agents were
removed: both jobs booted out, and both plists deleted from `~/Library/LaunchAgents`. Afterwards:

```
$ launchctl print-disabled gui/501 | grep hermes
		"ai.hermes.daily-backup" => enabled
```

The plist is gone from the disk and the record is still there. **Removing a plist does not remove
the label from launchd's override store, and nothing on the command line does** — there is an
`enable` and a `disable` verb, and no verb that deletes an entry. The best an uninstall can do is
leave it `enabled`, which is inert; what it must never do is leave it `disabled`, because that is a
decision the next install inherits from an install nobody remembers.

> **Two design rules from this.** Install **unconditionally `enable`s the label before
> bootstrapping** — it is cheap, and it is the only defence against an override nobody remembers.
> And uninstall **clears the override**, because leaving a record behind is how the next install
> inherits a decision nobody made.

### `launchctl print` does not show disabled state

The complete `properties` flag vocabulary was read out of the binary `[BIN]`: `keepalive`,
`runatload`, `launch only once`, `inferred program`, `supports transactions`,
`supports pressured exit`, `penalty box`, `exponential throttling`, `wait for debugger`,
`event monitor`, `abandon process group`, `role account`, `untrusted`. **`disabled` is not among
them.** The only renderings are `disabled services = { … }` on the *domain* print.

**So a disabled job prints as a perfectly healthy job that will never start.** Disabled state must
be queried separately, every time.

```
$ launchctl print-disabled gui/501
	disabled services = {
		"com.apple.Siri.agent" => disabled
		"ai.rundesk.gateway" => enabled
		...
	}
```
**Absence from that block means enabled.** `[RAN]`

Clearing it — `[MAN]` says `enable`/`disable` *"may only target services within the system domain or
user and user-login domains"*. `gui/<uid>` is a user-login domain, so it is legal; fall back to
`user/<uid>` on 125. **`enable` starts nothing** — bootstrap after it.

### How a gateway gets disabled without anybody meaning to

**`launchctl unload -w`** `[MAN launchctl help unload]`: *"`-w` Additionally disables the service
such that future load operations will result in a service which launchd tracks but **cannot be
launched or discovered in any way**."* That is verbatim the "start appears to work and nothing runs"
case. Any old blog post, install script or troubleshooting session does it.

No path was found where launchd disables a job on its own `[BIN]`.

### The lockout with no command: Background Task Management

`[RAN]` `/var/db/com.apple.backgroundtaskmanagement/BackgroundItems-v16.btm` is world-readable, and
**every plist in `~/Library/LaunchAgents` on this machine is registered in it**. `[BIN]` launchd
carries:

```
Untrusted service was denied launch by BTM. Removing.
```

**A BTM denial does not merely block the launch — it removes the service from launchd**, after which
`print` returns 113, indistinguishable from never having been installed.

**There is no `launchctl` command, and no user-level command of any kind, that re-enables a
BTM-disabled item.** `sfltool dumpbtm` is root-only and read-only. The user must toggle it back on
in System Settings → General → Login Items & Extensions.

And here is the part that makes it likely rather than theoretical. `[RAN]` BTM names each row by the
**executable's basename**, not by the label:

```
name='python'  id='8.ai.hermes.gateway'       disposition=9 (enabled|notified)
name='sh'      id='8.ai.openclaw.gateway'     disposition=9
name='bash'    id='8.ai.hermes.daily-backup'  disposition=9
```

**Under the plist as originally designed, every rundesk gateway would appear to the owner as an
anonymous `python` row** — several identical `python` rows for several gateways — and one careless
toggle kills them all. After which `print` says 113, `print-disabled` says `enabled`, and a command
that trusted either would confidently report "not installed".

> **The change this forces, and it is the highest-value line on the page:** make
> `ProgramArguments[0]` a **named per-install shim** rather than a bare interpreter, so the Login
> Items row reads something the owner recognises instead of `python`. It costs one file and it is
> the only real mitigation for the one failure mode with no command.
>
> Second: **detect it.** The BTM store is world-readable and parseable with `plistlib` (an
> `NSKeyedArchiver` archive — walk `$objects` for dicts with a `disposition`, match `8.<label>`,
> bit `0x1` = enabled). The format is undocumented, so guard it and **degrade to "cannot tell"**
> rather than guessing. `[RAN]` for the format; the bit meaning is inference consistent with all
> five agents on this machine.

**Quarantine** is a third lockout: error 155, if the install root was ever unzipped from a download.
`xattr -dr com.apple.quarantine <root>` clears it.

---

## 5. Throttling

`[RAN]` `ThrottleInterval` renders in `print` as **`minimum runtime`** — a live job with
`ThrottleInterval => 30` prints `minimum runtime = 30`.

`[MAN 5 launchd.plist]`: *"by default, jobs will not be spawned more than once every 10 seconds."*
**So `ThrottleInterval: 10` buys nothing — it is the default.** A gateway that dies inside ten
seconds is broken rather than busy, so this build sets something meaningful or drops the key.

Escalation is real `[BIN]`:

```
Service only ran for %llu seconds. Pushing respawn out by %llu seconds.
service exceeded successive crash limit. launch will be throttled
Exponential throttling is in effect for %llu seconds.
cannot spawn: service is throttled  /  canceling throttled spawn
successive crashes = %u   /   exponential throttling grace limit = %u
```

Flat deferral first, then exponential backoff past a successive-crash limit. **It never stops
rescheduling** — the word is *throttled*, not abandoned — but the interval grows, and a crash-looping
gateway can end up minutes apart and simply look dead.

**What `print` shows:** `state = spawn scheduled`, no `pid =` line, and `successive crashes = N`
(the field is omitted when zero). The full state enum `[BIN]` is `not running | spawn scheduled |
spawning | running | SIGTERMed | SIGKILLed | languishing | exited`.

**Does `kickstart -k` bypass the throttle?** `[BIN, strong]` yes — launchd's kick-request handler
carries `unthrottle` in its key table, adjacent to `service spawned with pid: %d`. So
`launchctl kickstart -kp gui/<uid>/<label>` is the "start it now regardless" command, and it is what
`start` should run after bootstrapping rather than trusting `RunAtLoad`. *(An earlier draft claimed
the opposite from a retracted source. Treat this as strong inference, not proof, and do not build
anything that only works if it is true.)*

**The penalty box** is a separate, harder stop `[BIN]`: `attempt to launch while in penalty box`,
`cannot spawn: service is in penalty box`. What puts a user agent into it, and what gets it out, is
**unverified** — flagged rather than guessed.

---

## 6. Detecting truth — and when to say "cannot tell"

### Parsing traps, both measured

**`launchctl list <label>` reports the raw `wait(2)` status.** `[RAN]` a job whose exit code was 75
shows `"LastExitStatus" = 19200`, and `19200 >> 8 == 75`. The aggregate `launchctl list` had already
decoded the same number to `75`. **Two launchctl surfaces report one number in two encodings.**
Shift by 8 for the code, mask `& 0x7f` for the signal.

**`last exit code` coexists with a running pid.** `[RAN]` a healthy gateway prints `pid = 71237`,
`runs = 2`, **and** `last exit code = 75: EX_TEMPFAIL` — that 75 is from the previous run. Reading it
as "the gateway is failing" without checking `state` and `pid` is a wrong answer about a working
machine.

Also: `print`'s `path =` is the plist launchd *imported*, which may not be the plist on disk (§3);
and `[MAN]` warns outright that the output *"is NOT API in any sense at all"* and that these commands
*"are intended for use by human developers and system administrators, not for automation."* Parse
defensively, and treat an unparseable print as **cannot tell**, never as **no**.

### 113 is ambiguous three ways, proven

`[RAN]` byte-identical stderr for three entirely different situations:

1. `ai.openclaw.gateway` — **plist on disk, never bootstrapped**
2. `ai.rundesk.gateway` — **no plist, but a persistent override record**
3. `totally.made.up.label` — **never existed**

And `[BIN]` launchd has paths that *delete* a service that was successfully installed:
`Removed service on spawn failure` and `Untrusted service was denied launch by BTM. Removing.` So
113 can also mean *"it was installed, it tried to start, and launchd threw it away."*

**Status must therefore be a three-way decision over three independent sources:**

```
rc == 112                        -> "cannot tell — no GUI session for this uid"
rc == 0                          -> read state / pid / properties
rc == 113 and no plist on disk   -> "not installed"          <- the ONLY safe "no"
rc == 113 and plist on disk      -> "cannot tell — installed, and launchd has no record"
```

**`rc == 112` must never be reported as "not running".** Over SSH into a machine nobody has logged
into at the desktop, *every* gateway looks absent.

---

## 7. Permissions and symlinks

- `~/Library/LaunchAgents` is `drwx------` and needs nothing special `[RAN]`.
- `[MAN]` agent plists *"must be owned by the user loading them"* and *"must disallow group and world
  writes"*. Violation is error 122, with `Caller specified a plist with bad ownership/permissions`
  in the log `[BIN]`. `[MAN load -F]` notes the modern `-F` **no longer** bypasses the check.
- Both `0600` and `0644` work `[RAN]`. Write the mode explicitly: `O_CREAT`'s mode is masked by the
  umask, so create then `fchmod`, or a permissive umask lands `0664` and it is refused.
- **Symlinked plist: no evidence either way.** No `O_NOFOLLOW`/`realpath` handling was found in the
  import strings, and it cannot be tested read-only `[RECALL, low confidence]`. **Write a real file.
  There is no upside**, and the ownership check makes a second file's ownership a question nobody
  needs to have.

---

## 8. Standard output — better than feared, with two traps

**launchd does create the parent directories.** `/usr/libexec/xpcproxy` imports `_mkpath_np` and
carries `Unable to create stdout directory (%s)` / `…stderr…` `[BIN]`. Create them anyway: one
`makedirs(exist_ok=True)` costs nothing and removes a dependency on undocumented behaviour.

**The files are opened `O_CREAT|O_RDWR|O_APPEND|O_CLOEXEC`, mode 0666** `[BIN]`, corroborated by
`[MAN 5 launchd.plist]`: *"this file is opened as readable and writable as mandated by the POSIX
specification for unclear reasons."*

> **`O_APPEND`, never `O_TRUNC`, and launchd never rotates them.** In a crash loop every throttled
> restart appends another traceback, for ever. **`gateway.out` and `gateway.err` must be rotated by
> us** — they are outside the day-stamped scheme, so they need their own answer.

**If the path is unwritable the spawn fails**, and the reason goes to the unified log *only* — it
cannot go to `StandardErrorPath`, which is the thing that failed to open `[BIN]`:

```
%s spawn failed: %d: %s   /   Could not spawn process %s: %d: %s
Missing executable detected. Job: '%s' Executable: '%s'
Removed service on spawn failure
```

That last line is how a correctly-installed gateway becomes a 113.

**The recovery command, for "I started it and nothing happened":**

```sh
log show --last 10m --predicate 'process == "launchd" OR process == "xpcproxy"' --style compact | grep <label>
```

`[RAN]` two caveats: on a healthy machine this returns **nothing** — launchd is quiet, so silence is
not evidence of health — and it can take tens of seconds, so give it a ceiling.

> **A design consequence worth more than it looks.** The very first thing the gateway process does —
> before parsing arguments, before reading anything — is write one line with a timestamp and its own
> pid. If `gateway.out` is empty while `runs` is non-zero, the failure is upstream of our code and
> belongs in the unified log. That one line turns "cannot tell" into "look here."

---

## 9. Login, reboot, and why writing a plist installs nothing

**Proven on this machine** `[RAN]`. Boot was 14 days ago; every plist below was written after login:

```
ai.hermes.gateway              print -> 0     (its installer bootstrapped it)
ai.hermes.daily-backup         print -> 113
ai.openclaw.gateway            print -> 113
com.google.GoogleUpdater.wake  print -> 113
```

**Three plists have sat on disk for two weeks doing nothing at all.** Writing the file is not
installing the job; `bootstrap` is.

At login, loginwindow creates `gui/<asid>` and bootstraps the `LaunchAgents` directories `[MAN + BIN]`,
so `RunAtLoad` then starts the gateway with no action from us — provided the label is not in
`disabled.<uid>.plist` and BTM has not disabled it.

**Jobs do not survive logout**: a `gui/` agent's domain is the login session, and logout tears it
down (error 124; `denying spawn, domain shutting down` `[BIN]`).

**`load`/`unload` still matter in one way:** `[MAN]` they *"will only return a non-zero exit code due
to improper usage"* — a user's failed `load` reports success — and `unload -w` writes the persistent
disable that is sitting on this machine right now.

---

## 10. The environment a job actually gets

Measured from a live job's own `print` `[RAN]`:

```
inherited environment = { SSH_AUTH_SOCK => /var/run/com.apple.launchd.…/Listeners }
default environment   = { PATH => /usr/bin:/bin:/usr/sbin:/sbin }
```

**That is the whole of it.** No `HOME`, no `USER`, no `SHELL`, no `LANG`, no `TMPDIR`, no shell rc
files, no Homebrew, no `~/.local/bin`. `launchctl getenv PATH` is empty `[RAN]`.

**This is the exact explanation of the previous build's lost provider.** `~/.local/bin` is absent
from `/usr/bin:/bin:/usr/sbin:/sbin`, so a tool installed there is invisible to the job while `which`
in the owner's login shell — which sourced his rc files — finds it instantly. The two PATHs have
nothing to do with each other, and **you cannot diagnose this by asking somebody to run `which`.**

`[MAN]` `EnvironmentVariables`: *"Values other than strings will be ignored."* An accidental `int`
disappears without a word — coerce everything with `str()`.

---

## The failure table

`$U = id -u`, `$L` = label, `$P = ~/Library/LaunchAgents/$L.plist`.

| State | Detection | The way out |
|---|---|---|
| Healthy | `print` 0, `state = running`, `pid` present | — |
| Plist written, never bootstrapped **(3 live examples on this machine)** | `print` 113 **and** `$P` exists | `bootstrap gui/$U "$P"` |
| Not installed | `print` 113 **and** no `$P` | write plist, bootstrap |
| Stale — plist edited under a live job | `print` 0 but `path`/`arguments` ≠ what we wrote | `bootout --wait` then `bootstrap` |
| **Loaded from a different plist path, silently** | `print`'s `path =` ≠ `$P` | same — bootout first is **mandatory** |
| Bootout→bootstrap race, `Bootstrap failed: 5` | bootstrap 5 after a bootout | `bootout --wait`, or poll `print` for 113; retry bootstrap on 5/37 |
| Already bootstrapped | bootstrap 17 (or 37) | nothing — verify with `print` |
| **Disabled** | `print-disabled` says `disabled`. **`print` looks normal** | `enable gui/$U/$L` (fall back to `user/$U/$L` on 125), then bootout→bootstrap→kickstart |
| **Stale override from a prior install** (live on this machine) | 113 + an entry in `print-disabled` | `enable` **before** bootstrapping — unconditionally |
| Throttled | `state = spawn scheduled`, no pid, `successive crashes = N` | `kickstart -kp` — and fix the crash |
| Penalty box | `properties` contains `penalty box` | **unverified.** bootout+bootstrap is the obvious attempt |
| Bad plist ownership/mode | 122 | `chmod 0644`, `chown`, bootstrap |
| Quarantined interpreter | 155 | `xattr -dr com.apple.quarantine <root>` |
| **Spawn failed → launchd removed it** | 113 **with `$P` present**; `log show` shows `spawn failed` | fix the cause, bootstrap again — **only findable in the unified log** |
| **No GUI session (SSH)** | `print` 112 | none from here. **Report "cannot tell", never "not running"** |
| Gateway ignores SIGTERM, `--wait` hangs | `state = SIGTERMed` then `languishing` | `kill -KILL`, then bootout — **and handle SIGTERM** |
| **Disabled in System Settings (BTM)** | 113 + `$P` present + `print-disabled` says `enabled` + the BTM store's enabled bit is clear | 🔴 **NONE.** The owner must re-enable it in System Settings → General → Login Items & Extensions |

---

## What this changes in the plist as designed

1. **`ThrottleInterval: 10` is the default and buys nothing.** Set something meaningful or drop it.
2. **`KeepAlive {SuccessfulExit: false}` implies `RunAtLoad`** `[MAN]` — *"the job needs to run at
   least once before an exit status can be determined."* So **bootstrapping is starting**: there is
   no "install it stopped" at the launchd layer, and the command surface must not imply one.
3. **The exit-0 contract has a sharp edge.** `SuccessfulExit: false` means restart unless exit was 0.
   But an uncaught Python exception exits 1 — so a gateway refusing to run **must reach exit 0 on
   every path, including when the refusal check itself raises.** Otherwise a permanent condition
   becomes an infinite restart loop that escalates into exponential throttling and looks like a hang.
4. **`ProgramArguments[0]` becomes a named per-install shim**, not a bare interpreter — the BTM
   naming problem in §4.
5. **Set `ExitTimeOut` explicitly.** It bounds SIGTERM→SIGKILL, and `bootout --wait` blocks for that
   whole window.
6. **`PATH` must be complete and explicit**, `HOME` too, every value a `str`. Consider `LANG` — a
   POSIX locale makes 3.9 misbehave on non-ASCII — and `TMPDIR`, which is not inherited.
7. **Rotate `gateway.out` / `gateway.err` ourselves.** `O_APPEND` for ever, otherwise.
8. **Label and filename must match** `[MAN]`, and the agent name must be restricted to
   `[A-Za-z0-9._-]`: a label containing `<` cannot have its disable state persisted at all `[BIN]`.

## Still unverified — to settle against a scratch label, never the owner's machine

- The exact code for bootstrapping an already-bootstrapped label (17 or 37 — sources disagree).
- Whether bootstrapping a **disabled** label fails with 119 or succeeds-and-does-not-run. **Test
  this first**; it is the most load-bearing unknown here.
- Whether `--wait` closes the EIO race or merely narrows it.
- What puts a job in the penalty box, and what gets it out.
- Symlinked plist behaviour.
- The BTM archive's disposition bits — consistent with all five agents here, which is not proof.
