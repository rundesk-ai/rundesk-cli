# What the machine actually does

Distilled 2026-08-04 out of the previous build's friction log and the docstrings in its source —
both gitignored, reference-only, and expected to be deleted. Everything here is about the machine
rather than about rundesk: the filesystem, the keychain, the shells macOS ships, the interpreter it
ships, and what happens to a process. Unless a line says otherwise it was established on **macOS
25.5.0 (Darwin 25.5.0)** between 2026-07-24 and 2026-08-03. Each line says how it is known —
**measured** means somebody ran it and kept the output, **read** means it came from a manual, and
**unverified** means the old notes asserted it without saying which.

`launchd` is not here. It has its own page, [`launchd-on-macos.md`](launchd-on-macos.md), and the
exit-code contract a supervised process owes it is in [`the-old-build.md`](the-old-build.md).

---

## The filesystem

**`/var` is a symlink to `/private/var`, and anything that builds a key out of a path has to resolve
it first.** Measured, and found the expensive way: a probe looking for what one CLI writes under a
slug of the working directory built the slug from the path it had been given, inspected a directory
that had never existed, and reported that nothing was written. `os.path.realpath()` is the fix, and
the failure it prevents reads as an absent feature rather than as a wrong path.

**A rename that does not cross a filesystem cannot be partial.** This is why the old build wrote
every small file under a name beside its target and renamed it into place, and why the tree a
restore unpacked was built *inside* the destination directory rather than in a temporary one. Read
in the manual, and relied on throughout — this build does the same thing, and
[`docs/layout.md`](../concepts/layout.md) states the lock half of it.

**A swap made of two renames has a gap in it, and no `except` can see that gap.** Measured as a
design consequence rather than as an incident: the old restore moved `data/` aside and moved the new
tree in, and a process dying between the two leaves neither name where it belongs. What made it
recoverable was that the *presence of `data/`* answers which rename had already happened, so the
next run could finish the swap rather than guess at it. Anything doing a two-step move needs that
question to have an answer on disk.

**A cloud can take a file away and leave a placeholder named after it.** Measured on iCloud Drive:
the placeholder for `<name>` is `.<name>.icloud` in the same directory, so whether a backup archive
is really present is answerable without asking the cloud anything. That matters precisely because
the machine may be offline, which is when somebody reaches for a backup.

**Names differing only in case are one directory here and two on a case-sensitive volume.** Read off
the old build's own migration and naming code, and unverified against a real case-sensitive volume.
The consequence is that a scheme which lowercases a name cannot simply create today's spelling
beside an older one: on macOS it would silently address the old directory, and on a case-sensitive
machine it would make two identities out of one human name. The old build resolved it by trying the
exact spelling first, then an unambiguous case-insensitive match, and refusing outright when more
than one existing name matched. Refusing an ambiguous set is the part worth keeping — a rule that
picks one is a rule that picks the wrong one eventually.

**Accents have an ASCII spelling and emoji do not.** Read off the same code:
`unicodedata.normalize("NFKD", name).encode("ascii", "ignore")` turns `José` into `Jose` and turns a
name made only of emoji into the empty string, which has to be refused rather than allowed to
produce a directory called `-`. A name admitted by an older release that has no ASCII spelling at
all must stay reachable by its exact bytes.

---

## The keychain

**A per-user keychain item is looked up by account name, so an environment that was *built* rather
than inherited cannot find it.** Measured against one vendor CLI at two versions: its sign-in is the
keychain item `svce="Claude Code-credentials", acct="<username>"`, and with `USER` unset the same
signed-in machine reports itself logged out. `LOGNAME`, `SHELL`, `TMPDIR`, `XPC_SERVICE_NAME` and
`__CF_USER_TEXT_ENCODING` each leave it false; `USER` alone flips it. The general fact is the one to
carry: **anything reading the login keychain on the user's behalf may be keyed on the account name,
and a program started with a constructed environment has no account name unless something puts one
there.** The per-CLI detail, and the bisection that found it, is in
[`2026-07-26-claude-cli-as-a-brain.md`](2026-07-26-claude-cli-as-a-brain.md).

**`security find-generic-password -g` prints the secret.** Measured — it goes to *stderr*, which is
exactly where a script that was only checking for existence is least likely to be looking. Use it to
ask whether an item exists and never to read one.

---

## The shells it ships

macOS ships zsh as the login shell and bash 3.2 as `/bin/bash`. Five of these cost a real attempt
each; all five are measured.

**zsh does not word-split an unquoted variable.** `E="env -u A -u B python3"; $E
tests/test_thing.py` makes zsh look for one command whose name is the whole string, fail, and print
nothing a `| grep "^Ran"` would match — so three probes in a row reported no failure when none of
them had run a single case. Write the prefix out in full at each call.

**`path` is a special array tied to `PATH`.** Assigning a file path to a shell variable called
`path` replaces the command search path, and the next `git` or `curl` is `command not found`. Use a
task-specific name.

**`status` is read-only.** A verification script that captures an exit code into `status=$?` aborts
before its later checks run.

**Backticks inside double quotes are command substitution, including inside a commit message.** In
`git commit -m "…"` it does not even fail loudly: zsh runs the backticked word, prints `command not
found` among git's own output where it reads as noise, substitutes the empty string, and the commit
lands with the word silently missing. Measured — a body reading "``changing`` is dropped" was
committed as " is dropped". Write a message through a quoted heredoc (`git commit -F - <<'MSG'`),
where nothing is interpolated.

**An unquoted `?` in an argument is a filename glob.** A URL ending `?ref=main` fails with `no
matches found` before the request is ever made. Quote the whole argument.

**`bash -n` on 3.2 misreports an apostrophe inside a heredoc inside `$( … )`.** Measured: an
embedded Python comment reading `the owner's` was reported as a syntax error dozens of lines away,
at whatever line happened to hold an unbalanced parenthesis. Write those comments without an
apostrophe, or keep the heredoc out of a command substitution.

---

## The tools it ships, and the two it does not

**There is no `timeout(1)`.** Measured. Anything driving a program with a deadline needs its own
kill timer, or `perl -e 'alarm shift; exec @ARGV' <seconds> …`, which is present.

**`tar` has no GNU `--wildcards`.** Measured — extracting one member by pattern fails before reading
the archive. List the archive, select the exact member name, and pass that name back.

**`ps` does not always answer.** Measured on a loaded machine at boot: a probe reading a process's
start time returned nothing for a `ps` that timed out or a fork that failed, and three separate
comparisons read that as a definite answer. The durable rule is broader than `ps` and is the one
thing on this page worth memorising: **before comparing anything a probe returned, ask what that
probe answers when it cannot answer** — and if that value is `None` or `{}`, the comparison needs a
third branch. The three failures it caused are in [`the-old-build.md`](the-old-build.md).

---

## Processes and signals

**A child put in a session of its own is in a process group of its own, so ending the group ends the
whole tree.** Read in the manual and relied on: this is what makes "everything rundesk starts
belongs to something" enforceable at all, and it is also why such a child *survives* its parent
being killed outright — it is out of reach of anything that ends the parent without warning. What
ends it then is whatever takes over the name it was started under.

**`killpg` degenerates at `0` and at `1`, and macOS hides the worse half.** Group `0` is the
caller's own; group `1` on Linux is `kill(-1, …)`, every process the user may signal. macOS returns
an error for `1` instead, so a test naming a real group passes here every time and takes a Linux CI
runner's own agent with it. The incident is recorded in [`the-old-build.md`](the-old-build.md); the
platform asymmetry is the part that belongs on this page.

**A shutdown that means it is SIGTERM to the group, a short grace, then SIGKILL to the group.** The
old build gave five seconds, chosen to sit well inside any supervisor's own patience, "because being
killed is how children get left behind".

**`pkill -f` matches how a process really appears in `argv`, not how you think of it.** Measured:
suites started as `python3 tests/test_turn.py` from the repository root carry the *relative* path,
so a pattern naming an absolute directory matched nothing and reported success while the suite ran
for another twenty minutes. Check with `pgrep -fl <pattern>` before trusting a kill.

**In a worktree more than one agent works in, a stray-looking process is usually not stray.**
Measured: a leftover `test_gateway.py` was a step inside somebody else's run, and killing it made
their check report a failure that never happened. Read the parent chain (`ps -o ppid= -p <pid>`) up
to whatever owns it before ending anything.

---

## The interpreter it ships

**`/usr/bin/python3` is 3.9.6, and that is the floor.** Measured. It is also the floor this build
pins, so everything below is live rather than historical.

**`#!/usr/bin/env python3` resolves to whoever's `PATH` ran it.** Measured: a developer's shell
finds Homebrew's 3.14 and a brain's tool shell finds `/usr/bin/python3`, so a virtualenv built by
one is refused by the other. Reproduce with `env PATH=/usr/bin:/bin ./rundesk …`. This build has no
virtualenv and no dependencies, which removes the failure rather than managing it — but the
resolution rule still holds for anything that shells out.

**A 3.9 interpreter that can see a 3.14 virtualenv does not fail like a version mismatch.**
Measured: 3.9 finds `.venv/lib/python3.14/site-packages`, imports a package built for another
Python, and dies inside a pure-Python fallback with `TypeError: unsupported operand type(s) for |` —
a PEP 604 annotation, not a `ModuleNotFoundError`, so nothing in the traceback says one interpreter
is reading another's environment.

**The system Python writes bytecode outside the tree, and reuses it on mtime *and size*.** Measured,
twice and in two different ways. It caches to `~/Library/Caches/com.apple.python/…` rather than to a
`__pycache__` beside the source, so clearing the repository's caches does nothing; and because a
`.pyc` is reused when the source's modification time and size both match what it recorded, breaking
a module for a probe and restoring it seconds later with a same-length edit keeps running the break
while `diff` says nothing is wrong. `touch` the file after restoring it. The same interpreter will
also create `Library/Caches/com.apple.python` under a test's scratch `HOME`, which correctly fails a
check for undeclared output — set `PYTHONDONTWRITEBYTECODE=1`, or point `PYTHONPYCACHEPREFIX`
somewhere disposable.

---

## Two numbers worth keeping

**A whole-directory copy legitimately holds a lock for a long time.** 120 MB across sixty thousand
files measured 9.2 seconds. That number is already carried in [`docs/layout.md`](../concepts/layout.md),
which is where it belongs, because it is the reason the wait for the install lock is the caller's to
choose rather than a constant.

**A grace of five seconds between SIGTERM and SIGKILL** was the old build's, chosen to be bounded
well under a supervisor's own patience rather than measured against anything. Unverified as an
optimum; carried because the reasoning behind it is sound and the alternative — no grace — is what
leaves children behind.
