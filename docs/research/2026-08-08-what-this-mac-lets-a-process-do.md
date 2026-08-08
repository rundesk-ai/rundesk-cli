# Research: what this Mac lets a rundesk process do

**Date:** 2026-08-08
**Question it answers:** rundesk is about to grow a command that says what macOS permits it to do.
Nothing in the product has ever touched TCC, so every rule such a command would classify by is a
claim about the platform that nobody here has checked. Which of them are true?

**True of:** macOS **26.5.1**, build **25F80**, Darwin **25.5.0** — a version
[`macos.md`](macos.md) predates and which has no TCC section at all. Homebrew
`python@3.14` at **3.14.6**. One machine, one user account, one login session.

Everything marked **measured** was run and its output kept below. Everything marked **not settled**
was deliberately not run, and §8 says why — several of the remaining questions cannot be answered
without either opening a window on somebody's desktop or destroying a real grant, and neither is a
thing a research page gets to do unasked.

---

## 1. What TCC thinks a rundesk gateway *is*

**Measured.** A gateway is a launchd job whose `ProgramArguments[0]` is the per-agent shim
(`gateways/job.py:215-226`). The shim's last line is an `exec`:

```sh
exec /opt/homebrew/opt/python@3.14/bin/python3.14 -c '…' /Users/…/.rundesk/app/src marcus
```

`exec` replaces the process image, so by the time anything TCC-gated is called the per-agent name is
gone. What is actually running, read with `proc_pidpath` from inside the process:

```
/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python
```

`codesign -dv` on that bundle:

```
Identifier=org.python.python
Format=app bundle with Mach-O thin (arm64)
CodeDirectory v=20400 … flags=0x2(adhoc)
Signature=adhoc
TeamIdentifier=not set
```

### Two shims differing only in name are the same client

**Measured.** Two shims, `rundesk-gateway-alpha` and `rundesk-gateway-beta`, identical but for the
name, each reporting its own running image and responsible process:

```
=== shim: rundesk-gateway-alpha ===
  RUNNING IMAGE   : …/Python.app/Contents/MacOS/Python
  responsible pid : 45481   image: /Applications/iTerm.app/Contents/MacOS/iTerm2
=== shim: rundesk-gateway-beta  ===
  RUNNING IMAGE   : …/Python.app/Contents/MacOS/Python
  responsible pid : 45481   image: /Applications/iTerm.app/Contents/MacOS/iTerm2
```

**So the agent name is irrelevant to TCC, and one grant covers every gateway on the machine.** A
second agent needs no new grant. This is the opposite of what the shim's existence suggests, and §2
says why the suggestion is misleading rather than wrong.

### Login Items and TCC key on different things and give opposite answers

**Measured.** `launchctl list` and the job's own plist:

```
37185  0  ai.rundesk.5f394c47.gateway.marcus
ProgramArguments[0] = /Users/…/.rundesk/data/agents/marcus/rundesk-gateway-marcus
```

BTM names a background item by `ProgramArguments[0]`, which is the shim — a path launchd reads and
never cares that it exits. So **Login Items & Extensions shows one named row per agent**, which is
exactly what `job.py:228-266` built the shim for. TCC keys on the running process *after* `exec`,
so **the privacy panes show one anonymous `Python` row for the whole machine.**

Both are true at once. The shim solves the naming problem for the subsystem that reads a path and
cannot touch the one that reads a process. **Anything that wants a rundesk-named row in a privacy
pane has to be what python runs *as*, not another wrapper that execs away.**

### The grant is path-keyed and version-pinned

**Measured**, from the user database — `client_type` `1` means the client is an absolute path rather
than a bundle identifier:

```
kTCCServiceMediaLibrary|/opt/homebrew/Cellar/python@3.14/3.14.6/…/bin/python3.14|1|2
kTCCServicePhotos|/opt/homebrew/Cellar/python@3.14/3.14.6/…/bin/python3.14|1|2
kTCCServiceSystemPolicyDesktopFolder|/opt/homebrew/Cellar/python@3.14/3.14.6/…/bin/python3.14|1|2
kTCCServiceSystemPolicyDocumentsFolder|…|1|2
kTCCServiceSystemPolicyDownloadsFolder|…|1|2
kTCCServiceSystemPolicyAppData|…|1|5
kTCCServiceFileProviderDomain|…|1|2
kTCCServiceMediaLibrary|/Users/…/.local/share/uv/python/cpython-3.11.15-…/bin/python3.11|1|2
```

The path contains `3.14.6`. **A `brew upgrade python@3.14` to 3.14.7 moves the Cellar path and
changes the cdhash, and every grant above stops applying** — silently, with no error, until
something fails. Note also that the recorded path is the framework's `bin/python3.14`, not the
`Python.app` binary `proc_pidpath` reports; the two are different entry points into the same
install and TCC recorded whichever was running when the grant was made.

**Reference:** `auth_value` `2` = allowed, `0` = denied. `client_type` `0` = bundle identifier,
`1` = absolute path.

---

## 2. Lineage — the same probe answers differently depending on who started it

**Measured, and this is the finding the command is built around.** One probe, three ways to start it.

| Started by | Responsible process | Screen Recording | Accessibility |
|---|---|---|---|
| a shim, from iTerm | `/Applications/iTerm.app/Contents/MacOS/iTerm2` | **True** | **True** |
| a second shim, from iTerm | `…/iTerm2` | **True** | **True** |
| **the same shim, under `launchctl bootstrap`** | **itself** — `…/Python.app/Contents/MacOS/Python` | **False** | **False** |

macOS walks up to the nearest **app bundle** and makes it the responsible process. From a shell that
is the terminal emulator, which already holds grants because the user granted them once for
something else. Under launchd there is no app ancestor, so the process is its own responsible
process and the client becomes the Python binary — which holds none of these.

**⇒ A probe run from `rundesk ask` at a terminal reports READY for a gateway that cannot take a
screenshot.** Any answer that does not say which lineage it was proved in is a claim about nobody.

**⇒ On a fresh install every one of these is genuinely blocked for the gateway**, even on a Mac
whose terminal has everything.

### `start_new_session=True` does not move responsibility

**Measured.** Every probe will go through `utils/programs.py:run`, which sets
`start_new_session=True` (`programs.py:92`). Detaching the session was a plausible way to break the
responsibility chain. It does not:

```
from iTerm   : parent sees iTerm2, start_new_session child sees iTerm2
under launchd: parent sees itself,  start_new_session child sees itself
```

The child inherits the parent's responsible process in both lineages. **Nothing about the probe
harness changes the answer**, which is what makes probing from inside a turn a valid way for an
agent to learn its own gateway's grants.

---

## 3. Screen capture — running it **creates** the grant, which is why both earlier answers were wrong

This section was written three times, and the two wrong versions are kept because each is a reading
somebody will arrive at again. **The finding that settles it is that the probe was not passive:
asking macOS for a screenshot from a process with no Screen Recording grant made macOS write one.**

The evidence is a timestamp. Before any of this, the system TCC database held no row for the
Homebrew interpreter. Afterwards:

```
kTCCServiceScreenCapture|/opt/homebrew/Cellar/python@3.14/3.14.6/…/bin/python3.14|1|2|1786202353
                                                                        client_type↑  ↑auth_value=allowed
1786202353 = 2026-08-08 11:19:13 — during this session, and the only TCC change on the machine in two hours
```

So the three runs were not three measurements of one state. They were **one measurement, one state
change caused by it, and two measurements of the new state.**

| Run | Preflight | `screencapture` said | What was really true |
|---|---|---|---|
| first, under launchd | `False` | `exit 1`, *could not create image from rect*, **no file** | **the denied behaviour** |
| — | — | — | 11:19:13 — macOS writes an *allowed* grant for the interpreter |
| second, under launchd | (not asked) | `exit 0`, valid 8×8 and full-screen PNGs | granted by then |
| third, under launchd | (not asked) | menu bar byte-identical to the terminal's | granted by then |

### What each wrong version claimed, and why it looked right

**Version one: the silent-success trap.** Read the differing byte counts between a granted and an
"ungranted" full-screen capture as wallpaper-versus-content. They were the desktop clock changing
between runs, and by then both runs were granted anyway.

**Version two: `screencapture` is Apple-signed and bypasses the caller's grant.** Read the
byte-identical menu-bar captures as proof that an ungranted process sees the real screen. The
captures were identical because **both processes were granted** — the second one by the first.

The mechanism is real for other tools and the reasoning was sound; the premise was false.

### What is actually true, as far as this went

- **A denied capture fails outright**: `exit 1`, `could not create image from rect`, no file. The
  exit code does track the grant on 26.5.1, and neither earlier version believed that.
- **`CGPreflightScreenCaptureAccess` agreed at every point**, before and after. It is the reliable
  reading and it is non-prompting.
- **Asking for a capture without the grant changes the machine.** Whether macOS prompted and
  something accepted, or whether it added an allowed row on first use, was not established — but the
  row is `auth_value=2` and nobody deliberately granted it.

### ⇒ The probe may not shell out before asking

This is the design consequence and it is not a small one. **A probe that grants the permission it was
asked to report on is worse than useless**: it answers `ready` about a machine it has just changed,
and it alters the owner's privacy settings without being asked. `capabilities.proving._a_capture`
therefore reads the preflight **first** and runs nothing at all when the answer is no.

It also generalises past this one probe: *prove it by doing it* is right only where doing it is
inert, and **whether a probe is inert is a claim that has to be checked rather than assumed.** Every
other probe here is a preflight or a read for that reason.

### The rest of §3, kept because it was measured either way

### The reading that looked right, and was not

`screencapture` run under launchd with `CGPreflightScreenCaptureAccess()` answering `False`, against
the same commands from iTerm where it answers `True`:

```
### UNDER LAUNCHD — no screen recording grant
  rect-8px     exit=0 file=1052B     png=True 8x8
  fullscreen   exit=0 file=2918825B  png=True 5120x1440
### FROM ITERM — grant present
  rect-8px     exit=0 file=1052B     png=True 8x8
  fullscreen   exit=0 file=2960993B  png=True 5120x1440
```

Exit `0` both ways, a real PNG both ways, correct dimensions both ways, and a **different byte
count**. That reads exactly like the documented silent-success trap: a capture with no grant returns
the desktop picture only, which is smaller because it has no windows in it. It was written up as
proven on that basis.

### What a content check actually showed

**Measured.** Capturing a fixed region that is definitely *not* wallpaper — a strip across the menu
bar — and hashing the bytes:

```
                     FROM ITERM (granted)          UNDER LAUNCHD (no grant)
  menubar   8105B  sha=3e96163bf3579c48     8105B  sha=3e96163bf3579c48
  window    2000B  sha=3cc77870bcf8238b     2000B  sha=3cc77870bcf8238b
```

**Byte-identical.** A process holding no Screen Recording grant captured the menu bar, and captured a
named window by id, and got exactly what the granted process got. The fullscreen byte differences
were the screen changing between runs — the desktop clock alone guarantees that — and reading them as
wallpaper-versus-content was a coincidence mistaken for a mechanism.

### Why

`/usr/sbin/screencapture` is a **separate Apple-signed binary with its own TCC identity**. Shelling
out to it does not perform the capture as the caller; it performs the capture as itself. So the
caller's Screen Recording grant is not consulted, and `CGPreflightScreenCaptureAccess` — which
answers about *the calling process* — is answering a different question from the one the shell-out
asks.

**The two are both real and they measure different things:**

| Question | Answered by | Ungranted result |
|---|---|---|
| Can this agent get a screenshot **by running `screencapture`**? | run it, decode it, check the dimensions | **yes** |
| Does this **process** hold Screen Recording, for in-process capture (ScreenCaptureKit, `CGDisplayStream`) or anything that must not shell out? | `CGPreflightScreenCaptureAccess` | **no** |

An agent asked for a screenshot will shell out, so the first is what usually decides whether it can
do the job. The second still matters and is not redundant: a library-based capture, continuous
recording, and anything running where `screencapture` is unavailable all need the real grant.

**⇒ They stay two probes, for a different reason than version two gave.** `screen/grant` reads the
preflight and is the authority. `screen/capture` proves the pipeline end to end — that a real image
comes back and decodes at the size asked for — which a boolean cannot, since a granted machine with
a broken capture path would still preflight `True`. But it runs **only after** the grant is
confirmed, because of what the attempt does otherwise.

### Window titles are not withheld either

**Measured.** `CGWindowListCopyWindowInfo` with `kCGWindowListOptionOnScreenOnly`:

```
FROM ITERM     windows=38  with a readable title=37
UNDER LAUNCHD  windows=37  with a readable title=36
```

On earlier macOS versions the window *name* was withheld from a process without Screen Recording,
which made the window list a cheap discriminator. **It is not one on 26.5.1** — the titles come back
either way. Recorded because it is the obvious next thing to try and it does not work.

### The failure that was read as a sleeping display

`exit 1` / *could not create image from rect* / no file was first written up here as a transient — a
display that had gone to sleep — because it happened once and the next run worked. **It was the
denied answer**, and the next run worked because the grant had appeared in between. A single
observation explained by the most convenient hypothesis available is how both wrong versions of this
section were written.

The `UNPROVEN` third state stays in the design, because a capture genuinely can fail for reasons that
are not permission and a two-branch classifier would have to call such a case allowed or denied. But
it is now **reasoned rather than measured**, and this page should stop claiming otherwise.

### The failure that was read as a sleeping display

`exit 1` / *could not create image from rect* / no file was first written up here as a transient — a
display that had gone to sleep — because it happened once and the next run worked. **It was the
denied answer**, and the next run worked because the grant had appeared in between. A single
observation explained by the most convenient hypothesis available is how both wrong versions of this
section were written.

The `UNPROVEN` third state stays in the design, because a capture genuinely can fail for reasons that
are not permission and a two-branch classifier would have to call such a case allowed or denied. But
it is now **reasoned rather than measured**, and this page should stop claiming otherwise.

---

## 4. Files — TCC denial is `EPERM`, and three folders are not protected here

**Measured**, from the ungranted launchd lineage:

```
  ~/Desktop      read
  ~/Documents    read
  ~/Downloads    read
  FDA canary     PermissionError errno=1     (~/Library/…/com.apple.TCC/TCC.db)
  app-data       PermissionError errno=1     (~/Library/Application Support/…)
```

Two findings, and the second was not expected.

1. **A TCC refusal is `EPERM` (errno 1), not `EACCES` (13).** So a probe can tell a privacy refusal
   from an ordinary filesystem-permission refusal by the errno alone, and the two have completely
   different fixes. This is what the `files` probes classify on.
2. **`~/Desktop`, `~/Documents` and `~/Downloads` read fine from a process holding no grant for
   them.** The protection did not engage for a bare launchd-started executable. *Marked
   uncertain* — this was measured once, on one account, and the mechanism is not established. It may
   differ for a hardened runtime, a sandboxed process, or another account. The probes stay, because
   the honest thing is to report what the machine actually answers rather than what the pane implies;
   but they are not the blockers the design assumed, and **the real blockers for a gateway are the
   four control grants, screen capture, Full Disk Access and app-data.**

---

## 5. The whole surface, enumerated

**Measured** — `select distinct service from access` against both databases. This is the list the
probe set was built from, rather than from recollection.

**System database** (`/Library/Application Support/com.apple.TCC/TCC.db`, needs admin to change):

```
kTCCServiceAccessibility        kTCCServiceScreenCapture
kTCCServiceListenEvent          kTCCServicePostEvent
kTCCServiceDeveloperTool        kTCCServiceSystemPolicyAllFiles
```

**User database** (`~/Library/Application Support/com.apple.TCC/TCC.db`):

```
kTCCServiceAppleEvents                    kTCCServiceSystemPolicyAppBundles
kTCCServiceSystemPolicyAppData            kTCCServiceSystemPolicyDesktopFolder
kTCCServiceSystemPolicyDocumentsFolder    kTCCServiceSystemPolicyDownloadsFolder
kTCCServiceSystemPolicyNetworkVolumes     kTCCServiceSystemPolicyRemovableVolumes
kTCCServiceAddressBook                    kTCCServiceCalendar
kTCCServicePhotos                         kTCCServiceMediaLibrary
kTCCServiceCamera                         kTCCServiceMicrophone
kTCCServiceUbiquity                       kTCCServiceFocusStatus
kTCCServiceBluetoothAlways                kTCCServiceLiverpool
kTCCServiceFileProviderDomain             kTCCServiceWebBrowserPublicKeyCredential
```

**Screen Recording, Accessibility and Full Disk Access are in the system database**, which is why
they have no rows in the user one and why granting them needs an administrator.

---

## 6. Driving the machine is four grants, not one

**Measured.** All four preflights exist, are reachable through `ctypes`, and **none of them
prompts** — they answer a question rather than asking one:

```
                                      iTerm   launchd
CGPreflightScreenCaptureAccess         True    False
CGPreflightPostEventAccess             True    False
CGPreflightListenEventAccess           True    False
AXIsProcessTrusted                     True    False
```

`AXIsProcessTrusted` is Accessibility — reading and driving UI elements. `CGPreflightPostEventAccess`
is synthesizing clicks and keystrokes. `CGPreflightListenEventAccess` is Input Monitoring, reading
global input. They are separate services with separate rows, so **an agent granted only Accessibility
still cannot synthesize a keystroke**, and a check that reported "control: blocked" as one line would
send somebody to fix one of three different things.

The prompting variants exist and are deliberately not used: `CGRequestScreenCaptureAccess` and
`AXIsProcessTrustedWithOptions` with the prompt key raise a dialog, which a background gateway must
never do.

---

## 7. Apple Events is per (client, target) pair

**Measured.** The `access` table carries `indirect_object_identifier`, and one client holds one row
per application it may script:

```
com.googlecode.iterm2 | com.apple.Preview            | 2
com.googlecode.iterm2 | com.apple.QuickTimePlayerX   | 2
com.googlecode.iterm2 | com.apple.finder             | 2
com.googlecode.iterm2 | com.apple.systemevents       | 2
com.googlecode.iterm2 | com.google.Chrome            | 2
com.googlecode.iterm2 | org.mozilla.firefox          | 2
com.googlecode.iterm2 | de.beyondco.herd             | 2
com.googlecode.iterm2 | com.openai.sky.CUAService    | 2
com.anthropic.claudefordesktop | com.apple.AddressBook | 2
com.openai.codex      | com.apple.systemevents       | 2
```

**Granting Chrome grants nothing about System Events**, and vice versa. Eight rows for one client is
eight separate approvals the user gave, one per target. A probe set therefore needs one probe per
target, not one for "automation".

### And the targets have to be discovered

**Measured.** Counting `.app` bundles carrying a `.sdef` under `/Applications` and
`/System/Applications`: **26 scriptable applications** on this machine. Which of them matter is a
fact about the machine and the owner's work, so hardcoding a list would produce a probe set that is
right here and wrong everywhere else.

---

## 8. Not settled, and why

Ordered by how much each would change the design.

1. **The exact stderr for a denied Apple Event.** `-1743` is *recalled*, not measured. Establishing
   it needs either `tccutil reset AppleEvents <client>` — which destroys a real grant the owner
   gave — or probing a target the current client lacks, which raises a consent dialog whose wrong
   button writes a **denial** that persists. Neither was run. **The browser and system-events
   classification tables rest on this string and must be verified before they ship.**
2. **Whether the five `x-apple.systempreferences:` anchors still resolve on 26.5.1**
   (`Privacy_Automation`, `Privacy_Accessibility`, `Privacy_ScreenCapture`, `Privacy_FilesAndFolders`,
   `Privacy_AllFiles`). Not run — each opens System Settings on the owner's screen. This is the most
   user-visible claim in the design: every fix line prints one.
3. **How an owner adds a bare executable path to Screen Recording or Accessibility.** Those panes are
   built around applications, and the client here is a path to an interpreter inside a Homebrew
   Cellar. Whether the `+` button will even accept it is unknown, and if it will not, **the fix lines
   for the two most important grants have nothing to say.** This is the largest open risk.
4. **Whether a never-asked client can be told from a denied one.** Designed as "a timeout in a
   lineage that can prompt", which is an inference. Would need §8.1's `tccutil reset`.
5. **Whether `path to application id` launches an application that is not running.** If it does, the
   browser probe is not the non-invasive thing it claims to be.
6. **Whether `PostEvent` and `ListenEvent` have their own System Settings panes**, or fold into
   Accessibility and Input Monitoring. Decides what three of the four control fix lines say.
7. **Whether the System Events script needs Accessibility or only Automation.** Both are `True` here,
   so the case that separates them cannot be produced without revoking one.
8. **A non-prompting way to ask about `DeveloperTool`, `Camera`, `Microphone`** and the personal-data
   services. Where there is none, the probe answers `UNPROVEN` and is never shipped as a guess.
9. **Whether stills and video are one TCC service.** Recalled, not measured. §3 makes this less
    pressing than it looked — `screencapture -v` would be a shell-out too — but a library-based
    recorder would still need the grant.
10. **Why `~/Desktop` was readable without a grant** (§4). Measured once; mechanism unknown.
11. **Whether §3's shell-out bypass holds for the other services.** `screencapture` is Apple-signed
    with its own identity, and `osascript` is too — so a shelled-out AppleScript may likewise be
    attributed to `osascript` rather than to the caller. **If it is, the whole `apps` group is
    measuring the wrong client** and the Automation results would be about `osascript`, not about
    rundesk. Not measured, because separating them needs an ungranted target and therefore a dialog.
    **This is now the most important open question**, because §3 proves the mechanism exists.

---

## 9. What this means for the command

- **Lineage is part of every answer, not a heading.** §2 is the measured failure that makes this
  structural: same probe, same machine, opposite answers.
- **Screen is two probes, and the order between them is load-bearing** (§3): `screen/grant` reads
  `CGPreflightScreenCaptureAccess` and is the authority; `screen/capture` then proves the pipeline
  end to end, and **runs nothing when the grant is absent**, because the attempt writes the grant.
- **Prove it by doing it — only where doing it is inert, and check that it is.** The rule survives
  §3; what §3 added is the qualifier. A probe's side effects are a claim like any other, and this one
  was assumed rather than checked for three rewrites of the same section.
- **`control` is four probes with four fixes** (§6).
- **`apps` is one probe per target, targets discovered from the machine** (§7).
- **`files` classifies on errno**: `EPERM` is TCC, `EACCES` is the filesystem (§4).
- **Nothing may prompt.** Every query used above is a preflight or a read. Where no non-prompting
  query exists, the answer is `UNPROVEN` (§8.8).
- **Two hazards to document rather than solve**: the grant belongs to an interpreter shared with
  every other script run by it, and it dies on the next `brew upgrade` (§1).

## How the measurements were taken

Two harnesses, both disposable:

- **The granted lineage** — a shim run straight from iTerm, whose responsible process is iTerm and
  which therefore holds whatever the owner has granted their terminal.
- **The ungranted lineage** — the same shim under a throwaway
  `launchctl bootstrap gui/$UID <plist>` job, booted out afterwards and verified gone, with the plist
  kept outside `~/Library/LaunchAgents` so it could never survive a login. **This is what makes the
  denied answers reachable at all**: no grant, no app ancestor, and no way to get one.

Nothing was granted, revoked or reset. `tccutil` was never run. `~/.rundesk` was not written to.
