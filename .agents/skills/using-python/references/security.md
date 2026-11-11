# Python security traps

The classes of vulnerability that static analysis already knows how to find. Rule codes are Ruff's
`S` family, which reimplements Bandit — a finding here is reportable and checkable.

Run the check rather than relying on review: `ruff check --select S` finds most of this in a second.

## Executing things

**`subprocess` with `shell=True` and any untrusted input is command injection.** The subprocess docs:
"if the shell is invoked explicitly, via `shell=True`, it is the application's responsibility to
ensure that all whitespace and metacharacters are quoted appropriately to avoid shell injection
vulnerabilities."

```python
# Bad: a filename containing "; rm -rf ~" is a command.
subprocess.run(f"convert {path} out.png", shell=True)

# Good: the argument list never reaches a shell.
subprocess.run(["convert", path, "out.png"], check=True)
```

The list form is the fix, not escaping. Where a shell is genuinely required, `shlex.quote()` each
interpolated value — and on Windows, note the docs' separate warning that `.bat`/`.cmd` files may be
launched through a shell regardless.

Rules: `S602`–`S607` (subprocess and shell), `S609` (wildcard injection), `S601` (Paramiko).

**`eval()` and `exec()` on anything a user can influence execute arbitrary code** (`S307`, `S102`).
For data, `ast.literal_eval()` parses literals only. If you are reaching for `exec` to build classes
or dispatch, use a dict of callables.

**SQL built by string formatting is injection** (`S608`). Parameterize — every driver supports it —
and never interpolate identifiers from user input; validate them against an allowlist instead. This is
the same rule `using-sqlite` and `using-postgres` state for their engines.

## Deserializing things

**`pickle` executes code on load** (`S301`, `S403`). It "can be unsafe when used to deserialize
untrusted data" — meaning any pickle from a network, a cache another process can write, an upload, or
a file a user controls. Use JSON, or a schema-validated format. The same applies to `marshal`
(`S302`) and `shelve`, which is pickle underneath.

**`yaml.load()` without a safe loader instantiates arbitrary objects** (`S506`). Use
`yaml.safe_load()`.

**`tarfile.extractall()` can write outside the destination** (`S202`) — the "tar slip" traversal. On
3.12+ pass `filter="data"`; otherwise validate every member path before extracting. `zipfile` has the
same problem with crafted entry names.

## Secrets and randomness

**`random` is not cryptographic** (`S311`). "Standard pseudo-random generators are not suitable for
cryptographic purposes." Use `secrets` for tokens, password resets, session ids, and anything else an
attacker would like to predict.

**MD5 and SHA-1 are not secure hashes** (`S303`, `S324`), and no plain hash is a password hash. Use
`argon2`, `bcrypt`, or `hashlib.scrypt`/`pbkdf2_hmac` with a real cost factor. Where a fast hash is
genuinely just a checksum, say so — `hashlib.md5(data, usedforsecurity=False)` marks the intent and
silences the finding honestly.

**Hardcoded credentials** (`S105`–`S107`) — in a literal, a default argument, or a comparison. Read
them from the environment or a secret store. This includes test fixtures that get copied into
production code.

**Compare secrets with `hmac.compare_digest()`**, not `==`, wherever a timing difference would leak
whether a prefix matched.

## Files and paths

**`tempfile.mktemp()` is a race** (`S306`). It returns a name, not a file, and something else can
create it first. Use `NamedTemporaryFile`, `mkstemp`, or `TemporaryDirectory`.

**A hardcoded `/tmp/...` path** (`S108`) is world-writable and predictable.

**Permissive modes** (`S103`) — `chmod 0o777` on anything, and secrets written with the default umask.
A credential file should be `0600` inside a `0700` directory, and the mode should be set at creation.

**Path traversal:** joining a user-supplied name onto a base directory can escape it. Resolve and
check containment:

```python
target = (base / user_name).resolve()
if not target.is_relative_to(base.resolve()):
    raise ValueError("path escapes the base directory")
```

Use `pathlib` throughout (`PTH` family) — it makes this expressible.

## Network and transport

**`requests` without a timeout hangs forever** (`S113`). Not strictly a vulnerability, but an
availability bug and a denial-of-service amplifier. Always pass `timeout=`.

**`verify=False` disables certificate checking** (`S501`), which turns TLS into obfuscation. So does
an unverified SSL context (`S323`).

**Binding to `0.0.0.0`** (`S104`) exposes a service on every interface — usually not what a local
development server intended.

**`urlopen` with a user-supplied URL** (`S310`) can be pointed at `file://`, at internal addresses, or
at a metadata endpoint. Validate the scheme and the host — this is SSRF.

**`Flask(debug=True)` in production** (`S201`) serves an interactive debugger that executes code.

## Parsing untrusted input

**Standard-library XML parsers are vulnerable to entity-expansion and external-entity attacks**
(`S313`–`S320`). Use `defusedxml` for anything you did not generate yourself.

**Jinja2 with `autoescape=False`** (`S701`) is XSS by default; Mako (`S702`) escapes nothing by
default.

**Regexes on untrusted input can backtrack catastrophically.** Bound the input length, avoid nested
quantifiers, and prefer a parser where the grammar is real.

## Validation that disappears

**`assert` is removed by `-O`** (`S101`, `B011`). Anything enforcing a security property must raise:

```python
# Bad: vanishes under python -O
assert user.is_admin, "not authorized"

# Good
if not user.is_admin:
    raise PermissionError("not authorized")
```

This one is worth checking for specifically, because the code reads as correct and the deployment flag
that breaks it is set somewhere else entirely.

**`try/except/pass` around a security check** (`S110`) turns a failure into a pass.

## Review order

1. **Executing or deserializing untrusted input** — injection and pickle are the ones that end badly.
2. **Validation that can vanish** — `assert`, swallowed exceptions.
3. **Secrets** — hardcoded, weakly hashed, predictably generated, or world-readable.
4. **Transport** — disabled verification, missing timeouts, unintended binding.
5. **Parsers** — XML, templates, regex.

State the concrete failure — what an attacker sends, and what happens — rather than naming a rule
code. A finding nobody can picture does not get fixed.
