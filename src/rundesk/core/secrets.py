"""The values this install keeps for the things it talks to, and never gives back whole.

An owner places a token once — a Discord bot's, a Slack app's, an API key — and everything rundesk
starts can find it, with nobody having exported anything in a shell that a gateway will never see.

Four rules, and each of them closes a way a credential gets away from you:

**They are owner data, and copies carry them.** `paths.secrets()` places the store below `data/` so
a backup can restore a working install. The key and sealed values travel together, which means a
copy contains usable credentials and must be protected accordingly. Sealing is protection against
accidental plain-text exposure, not against somebody who can read the whole copy.

**Only the owner can read the file, from the moment it exists.** Written through `files`' private
mode, which opens the staging file at `0600` before a byte goes in — writing it at the umask and
tightening it afterwards leaves a window where the value is on disk and world-readable. The
directory is `0700` for the same reason, and both are repaired on every write, so a mode loosened
by something else does not stay loosened.

**A value never comes back whole to a person.** `hinted` is the only way this module will describe
one, and it is deliberately not reversible. A value that can be read back off a machine is one an
owner has to assume has been.

**A value never arrives as an argument.** The command reads it from a terminal without echoing, or
from a pipe — never from `argv`, which is in the shell's history file and visible in `ps` to every
other user on the machine while the command runs.

**A value is sealed on disk, and the honest limit of that is written here.** Each one is encrypted
with a key kept beside it in `key`, so nothing is stored as literal text: a disk image, a stray
copy, a `grep` across the machine turns up nothing readable. What it is *not* is protection from
anybody who can read the directory — the key is right there, because a gateway has to start at boot
with nobody typing anything, so there is nowhere else it could live. Someone with the owner's
account, or root, can open these values. Say that plainly rather than let the word "encrypted" do
work it has not earned.

What it does buy, precisely: a value never sits in plain text on a disk, in a screenshot, or in
whatever a filesystem hands back after the file is deleted. The file and directory permissions are
what stop another *user* on the machine; a backup needs protection of its own.

The construction, so it can be checked rather than trusted:

- One key of 32 random bytes in `key`, made on first use, `0600`.
- Two keys derived from it by `blake2b` with different personalisation — one to seal, one to sign —
  so the same bytes are never used for two purposes.
- A fresh 16-byte nonce for every value written, from `secrets.token_bytes`. Nothing is ever sealed
  twice under the same keystream, which is the mistake that breaks this kind of cipher outright.
- Keystream from keyed `blake2b` over the nonce and a counter, XORed with the value.
- **Encrypt-then-sign, over the name as well as the bytes**: an HMAC over the name, the nonce and
  the sealed bytes, checked with `compare_digest` *before* anything is unsealed. A value that has
  been tampered with, or that belongs to a different key, is refused rather than opened into
  nonsense — and so is one moved to a different name. Signing only the bytes let anybody who could
  edit the file swap two sealed values between names with no key at all, and both then opened
  cleanly: a program asking for its Discord token was handed the Slack one, which it would go on to
  send to Slack.

There is no fetching from an external keeper (`op read`, `pass show`, `gpg -d`) and no use of the
system keychain. The build this replaces grew the first; both are stronger than this, because in
both the value or the key stops living on this disk at all.
"""

import base64
import hashlib
import hmac
import re
import secrets as randomness
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

from rundesk.core import paths
from rundesk.utils import files, locking

#: The one file every value is kept in, below `paths.secrets()`.
KEPT_IN = "env.json"

#: The key everything here is sealed with, beside them. Lose it and the values are unreadable.
KEY_IN = "key"

#: How the sealed form is written down, so a later release can change it and still read this one.
SEALED = "v2"

#: A nonce per value, never reused. Sixteen bytes is far past the point where two collide.
NONCE = 16

#: What the keystream is drawn from. Personalised so the sealing key and the signing key can never
#: be the same bytes even though both come from one secret.
_TO_SEAL = b"rundesk-seal"
_TO_SIGN = b"rundesk-sign"

#: Only the owner may look in the directory, let alone read what is in it.
ONLY_MINE = 0o700

#: What a name may be: what a shell would accept as a variable, because that is what these become
#: for the programs rundesk starts. Refused rather than mangled — a name that arrives one shape and
#: is used in another is a value nobody can find again.
NAMED = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: How much of a value is ever shown, at each end.
SHOWN = 3

#: Below this, nothing is shown at all. Six characters of an eight-character value is not a hint,
#: it is most of the value — and the short ones are exactly the ones worth guessing.
LONG_ENOUGH = 12

#: A fixed width, so what is shown says nothing about how long the value is. Length narrows a guess
#: and identifies which kind of token it is; there is no reason to give it away for a nicer table.
BETWEEN = "x" * 8


#: The same answer `locking` gives, named here as well because this is the module every caller of
#: these already imports — the family this belongs to re-exports it, and this one had not.
Stuck = locking.Stuck


class Refused(Exception):
    """A name that may not be used, or a value that may not be kept, said with why."""


class Held(NamedTuple):
    """What is kept under one name — and, when it could not be opened, why not.

    Three answers rather than two, the way everything in this product distinguishes them: a name
    nobody has placed, a name deliberately emptied, and a name holding something this install can
    no longer read. The third is not an empty value. It means the key is gone or the file was
    tampered with, and telling somebody their token is "not set" when it is really unreadable sends
    them to set it again over the top of something they may still want.
    """

    value: Optional[str]
    trouble: Optional[str]


def where(at: Optional[Path] = None) -> Path:
    """The file the values are kept in."""
    return (at or paths.secrets()) / KEPT_IN


def key_at(at: Optional[Path] = None) -> Path:
    """The file the key is kept in, beside the values it opens."""
    return (at or paths.secrets()) / KEY_IN


def name_trouble(key: str) -> str:
    """Why `key` may not name a value, or `""` when it may.

    A sentence rather than a `False`, because the caller has to tell somebody what to type instead.
    """
    if not key or not key.strip():
        return "a name cannot be empty"
    if not NAMED.match(key):
        return (f"{key} is not a name a program can be given — capitals, digits and underscores, "
                "starting with a letter, the way a shell variable is written")
    return ""


def kept(at: Optional[Path] = None) -> Dict[str, Held]:
    """Every name and what it holds, including the ones deliberately emptied.

    **A name that was cleared is kept, holding nothing.** Never having placed a value and having
    taken one away are different answers, and the second is the one worth being able to see: it is
    how somebody knows an integration was set up here and is now switched off, rather than never
    configured.
    """
    how, said = files.read_json(where(at))
    if how == files.UNREADABLE:
        raise Refused(f"{where(at)} is there and cannot be read")
    if how != files.READ or not isinstance(said, dict):
        return {}
    return {key: _opened(key, sealed, at) for key, sealed in said.items()}


def names(at: Optional[Path] = None) -> List[str]:
    """Every name there is, in the order a person reads a list."""
    return sorted(kept(at))


def value(key: str, at: Optional[Path] = None) -> Optional[str]:
    """What one name holds, or `None` when it holds nothing.

    **The one way the whole value leaves this module**, and it exists for the programs rundesk
    starts — an adapter reaching for its own token. Nothing that prints to a person calls it.
    """
    held = kept(at).get(key)
    return held.value if held else None


def placed(key: str, at: Optional[Path] = None) -> bool:
    """Whether that name holds a value that can be read now.

    A name that was cleared holds nothing, and so does one this install can no longer open — from
    a caller's side both mean "you cannot use this", which is the question being asked.
    """
    return value(key, at) is not None


def stated(key: str, said: str, at: Optional[Path] = None) -> None:
    """Keep a value under a name, replacing whatever was there."""
    trouble = name_trouble(key)
    if trouble:
        raise Refused(trouble)
    if not said:
        raise Refused(f"{key} was given nothing to keep — `rundesk env unset {key}` empties a name")
    _written({key: _sealed(key, said, at)}, at)


def cleared(key: str, at: Optional[Path] = None) -> None:
    """Empty a name, leaving the name itself. See `kept` for why the name stays."""
    trouble = name_trouble(key)
    if trouble:
        raise Refused(trouble)
    _written({key: None}, at)


def hinted(held: Held) -> str:
    """As much of a value as anybody is ever shown: enough to recognise, not enough to use.

    Enough to answer "is this the token I think it is" after pasting one in, and nothing else. A
    short value shows nothing at all — six characters of eight is not a hint — and the width
    between is fixed, so the shape does not give away the length.

    A value that could not be opened says so instead of showing anything, because "not set" would
    send somebody to type a new one over something they may still want back.
    """
    if held.trouble:
        return held.trouble
    if held.value is None:
        return "not set"
    if len(held.value) < LONG_ENOUGH:
        return BETWEEN
    return f"{held.value[:SHOWN]}{BETWEEN}{held.value[-SHOWN:]}"


def _key(at: Optional[Path] = None) -> bytes:
    """The install's own key, made the first time anything is kept. `0600`, beside the values.

    Beside them because there is nowhere else it can be: a gateway starts at boot with nobody
    typing, so the key has to be readable without a person. That is the whole limit of this — see
    the module docstring, which says so rather than letting the word "encrypted" imply more.
    """
    made = key_at(at)
    _not_through_a_link(made.parent, "the directory the values are kept in")
    _not_through_a_link(made, "the key")
    there = _read_key(made)
    if there:
        return there

    # **Made under the lock, and asked for again once it is held.** Making it outside was a race
    # with a permanent consequence: two `env set` calls against a fresh install — an installer
    # piping several, or two terminals — each saw no key, each made a *different* one, and each
    # sealed its value with the one it had in hand. Whichever landed last is the key on disk, and
    # the other value can never be opened again. Nothing else about this feature is unrecoverable.
    made.parent.mkdir(parents=True, exist_ok=True)
    made.parent.chmod(ONLY_MINE)
    with locking.only_one(_install_lock(at), "this install",
                          locking.WHILE_A_DIRECTORY_MOVES):
        there = _read_key(made)
        if there:
            return there
        fresh = randomness.token_bytes(32)
        # Staged and renamed like everything else here rather than written in place: a crash
        # partway through leaves a key too short to use, which is a locked-out install.
        staging = files.incoming_of(made)
        files.discard(staging)
        opened = files.os.open(staging, files.os.O_CREAT | files.os.O_WRONLY | files.os.O_TRUNC,
                               files.ONLY_MINE)
        with files.os.fdopen(opened, "wb") as writing:
            writing.write(fresh)
        files.os.replace(staging, made)
    return fresh


def _read_key(made: Path) -> Optional[bytes]:
    """The key that is there, or `None` when there is not one yet. Too short is not "not there"."""
    if not made.exists():
        return None
    held = made.read_bytes()
    if len(held) < 32:
        raise Refused(f"{made} is not a key this release can use")
    return held


def _both_keys(master: bytes) -> Tuple[bytes, bytes]:
    """One key to seal with and another to sign with, so no bytes do two jobs."""
    return (hashlib.blake2b(master, digest_size=32, person=_TO_SEAL).digest(),
            hashlib.blake2b(master, digest_size=32, person=_TO_SIGN).digest())


def _keystream(sealing: bytes, nonce: bytes, wanted: int) -> bytes:
    """As many bytes as asked for, from keyed `blake2b` over the nonce and a counter.

    A counter, so no block of the stream repeats within one value; the nonce, so no stream is ever
    the same between two values. Reusing a keystream is the one mistake that breaks this outright.
    """
    out = bytearray()
    counter = 0
    while len(out) < wanted:
        out += hashlib.blake2b(nonce + counter.to_bytes(8, "big"), key=sealing,
                               digest_size=64).digest()
        counter += 1
    return bytes(out[:wanted])


def _sealed(key: str, said: str, at: Optional[Path] = None) -> str:
    """One value, sealed and signed *under its name*, in the form it is written down."""
    sealing, signing = _both_keys(_key(at))
    nonce = randomness.token_bytes(NONCE)
    plain = said.encode("utf-8")
    body = bytes(a ^ b for a, b in zip(plain, _keystream(sealing, nonce, len(plain))))
    return ":".join([SEALED, _b64(nonce), _b64(_signature(signing, key, nonce, body)), _b64(body)])


def _signature(signing: bytes, key: str, nonce: bytes, body: bytes) -> bytes:
    """What a sealed value is signed as, which includes the name it is filed under.

    **The name is in here, and that is not decoration.** Signed over the bytes alone, a tag says
    only "these bytes were sealed by this install" — not "…and they are this one's value". Anybody
    who could edit the file could then swap two sealed values between names, with no key and no
    decryption, and both would verify. The separator is a null byte, which cannot occur in a name,
    so no two different names can produce the same signed input.
    """
    return hmac.new(signing, key.encode("utf-8") + b"\0" + nonce + body, hashlib.sha256).digest()


def _opened(key: str, sealed: object, at: Optional[Path] = None) -> Held:
    """One value read back, or why it could not be. Never opened before its signature is checked."""
    if sealed is None:
        return Held(None, None)
    if not isinstance(sealed, str):
        return Held(None, "cannot be read — it is not in a shape this release wrote")
    parts = sealed.split(":")
    if len(parts) != 4 or parts[0] != SEALED:
        return Held(None, f"cannot be read — it was written as {parts[0]!r}, not {SEALED}")
    try:
        nonce, tag, body = (base64.b64decode(one) for one in parts[1:])
        sealing, signing = _both_keys(_key(at))
    except (ValueError, OSError, Refused):
        return Held(None, "cannot be read with the key this install has")
    # Checked before anything is unsealed, and with `compare_digest` so the check itself says
    # nothing about how nearly it matched.
    if not hmac.compare_digest(tag, _signature(signing, key, nonce, body)):
        return Held(None, "cannot be read with the key this install has")
    try:
        return Held(bytes(a ^ b for a, b in zip(body, _keystream(sealing, nonce, len(body))))
                    .decode("utf-8"), None)
    except UnicodeDecodeError:
        return Held(None, "cannot be read — what came back is not text")


def _not_through_a_link(one: Path, called: str) -> None:
    """Refuse to write through a symlink, whatever it points at.

    **A link decides where the bytes land, and here that defeats the placement outright.** A
    dangling `key` can send the master key — the one thing that opens every sealed value — outside
    the install's owned tree. `open` with `O_CREAT` follows a symlink and creates at the target, and
    `mkdir(exist_ok=True)` and `chmod` both follow one too, so nothing here notices on its own.

    Refused rather than resolved: a link where rundesk expects a directory of its own is not a
    configuration to accommodate, and following it is how a structural guarantee becomes a
    policy one.
    """
    if one.is_symlink():
        raise Refused(f"{one} is a link, and {called} may not be reached through one")


def _b64(raw: bytes) -> str:
    """Bytes as one line of text, so the whole thing fits in a JSON string."""
    return base64.b64encode(raw).decode("ascii")


def _install_lock(at: Optional[Path]) -> Path:
    """The lock for this store: the ambient install, or the root above an explicit store."""
    return paths.lock(at.parent) if at is not None else paths.lock()


def _written(values: Dict[str, Optional[str]], at: Optional[Path]) -> None:
    """Change what is kept, under the install's lock, privately, repairing the modes as it goes."""
    directory = at or paths.secrets()
    _not_through_a_link(directory, "the directory the values are kept in")
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(ONLY_MINE)
    with locking.only_one(_install_lock(at), "this install",
                          locking.WHILE_A_DIRECTORY_MOVES):
        with files.changing_json(where(at), empty={}, private=True) as held:
            settled = dict(held[0]) if isinstance(held[0], dict) else {}
            settled.update(values)
            held[0] = settled
