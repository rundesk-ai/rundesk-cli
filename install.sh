#!/usr/bin/env bash
# rundesk installer — put the `rundesk` command on your PATH, or take it off again.
#
# Install (no checkout needed):
#   curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
#
# From a local checkout, this symlinks THAT checkout, so development and installed
# use share one layout and there is no second copy to drift.
#   ./install.sh
#
# Uninstall:
#   ./install.sh --uninstall [--purge]
#   curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash -s -- --uninstall
#
# Env overrides: RUNDESK_INSTALL_DIR (default ~/.rundesk), RUNDESK_BIN_DIR.
#
# **The program and the data are two directories, not one.** `$RUNDESK_INSTALL_DIR/app` is
# the program — what this script lays down and what uninstall takes away, whole. Everything
# beside it is the owner's: their agents, and what their gateways wrote. Removal is then
# structurally incapable of touching data, rather than remembering not to: there was a list
# of names to spare, and a list is a thing that stops being true the day something is added.
set -euo pipefail

# Not overridable, and deliberately so. An install pointed at one repository updates itself
# from whichever one `rundesk update` is compiled to ask — there is nowhere on disk that
# remembers where a copy came from, so the two must be the same repository or an install
# silently drifts onto somebody else's releases. Kept in step by a test.
REPO_SLUG="rundesk-ai/rundesk-cli"
INSTALL_DIR="${RUNDESK_INSTALL_DIR:-$HOME/.rundesk}"
# The program, inside what rundesk owns. Nothing of the owner's is ever in here, which is the
# whole point of it having a name of its own (R-INS-13, R-RM-8).
APP_DIR="$INSTALL_DIR/app"
# And the other half: everything the owner keeps, in one directory the program is never inside.
# Two names rather than "app and whatever else is lying about" — removal keeps this by naming
# it, and what is kept can then be said one level in rather than as the single word "data".
DATA_DIR="$INSTALL_DIR/data"
MIN_PYTHON_MINOR=9

die() { echo "error: $*" >&2; exit 1; }

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# A checkout is where this script sits next to the thing it installs. Nothing about where
# it sits: a clone that happens to live at the install path is still a clone, and an earlier
# version of this function said otherwise — it excluded `SCRIPT_DIR == INSTALL_DIR`, so
# running ./install.sh from a clone at ~/.rundesk deleted that clone, .git and all.
is_local_checkout() {
  [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/rundesk" && -d "$SCRIPT_DIR/src/rundesk" ]]
}

# Somebody's work, not ours. What the installer lays down is a plain tree unpacked from a
# release; a clone carries history. That is the whole difference, and it is the only thing
# standing between `rm -rf` and a directory this installer did not create.
is_someones_work() {
  [[ -e "$1/.git" ]]
}

# `rm -rf "$INSTALL_DIR"` runs below, and RUNDESK_INSTALL_DIR is a documented override, so a
# typo that drops the last segment must not be able to take a home directory with it. It could:
# setting it to $HOME wiped the home directory and then printed that rundesk was installed.
check_install_dir() {
  local dir depth
  dir="$INSTALL_DIR"
  [[ -n "$dir" ]] || die "RUNDESK_INSTALL_DIR is empty."
  [[ "$dir" == /* ]] || die "RUNDESK_INSTALL_DIR must be an absolute path; got '$dir'."
  # `/` first: it ends in a slash, so the next arm would otherwise catch it and refuse
  # the root of the filesystem by complaining about punctuation.
  [[ "$dir" != "/" ]] || die "refusing to install into '/'."
  case "$dir" in
    */) die "RUNDESK_INSTALL_DIR must not end in a slash; got '$dir'." ;;
    */.|*/..) die "RUNDESK_INSTALL_DIR must name a directory, not '$dir'." ;;
  esac
  [[ "$dir" != "${HOME%/}" ]] ||
    die "refusing to install into '$dir' — that is your home directory, not one program's."
  # /Users/you/.rundesk has two separators and is fine; /Users and /opt have none and are not.
  depth="$(printf '%s' "${dir#/}" | tr -cd '/' | wc -c | tr -d ' ')"
  [[ "$depth" -ge 1 ]] ||
    die "refusing to install into '$dir' — too close to the root of the filesystem."
}

choose_bindir() {
  if [[ -n "${RUNDESK_BIN_DIR:-}" ]]; then echo "$RUNDESK_BIN_DIR"; return; fi
  if [[ -w /usr/local/bin ]]; then echo /usr/local/bin; return; fi
  echo "$HOME/.local/bin"
}

require_python() {
  command -v python3 >/dev/null 2>&1 || die "python3 is required, and it was not found."
  local minor
  minor="$(python3 -c 'import sys; print(sys.version_info[1])')"
  [[ "$minor" -ge "$MIN_PYTHON_MINOR" ]] ||
    die "Python 3.$MIN_PYTHON_MINOR or newer is required; found $(python3 --version)."
}

# Stop every gateway this install is keeping, and take its job away — before anything is
# deleted. A job outlives the command it names: the gateway keeps running, because
# deleting a program does not stop one, and the machine goes on trying to start it again
# every few seconds and at every login, against a path that is no longer there.
stop_gateways() {
  local root="" candidate
  for candidate in "$APP_DIR" "$INSTALL_DIR" "${SCRIPT_DIR:-}"; do
    if [[ -n "$candidate" && -f "$candidate/src/rundesk/supervisor.py" ]]; then
      root="$candidate"; break
    fi
  done
  [[ -n "$root" ]] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "note: python3 is gone, so any gateway still running was left as it is."
    return 0
  fi
  # `cmd || echo …` would report the echo's success, not the command's failure — so the
  # refusal below never fired and uninstall deleted rundesk with gateways still running.
  if ! python3 - "$root" <<'STOP'
import sys
sys.path.insert(0, sys.argv[1] + "/src")
from rundesk import supervisor

if not supervisor.available():
    raise SystemExit(0)          # nothing of the kind on this machine
taken, stubborn = supervisor.take_all_back()
for name in taken:
    print(f"stopped gateway '{name}' and removed its job")
if stubborn:
    for name in stubborn:
        print(f"gateway '{name}' would not stop, and is still running")
    raise SystemExit(3)
STOP
  then
    echo "note: gateways could not be stopped; check: launchctl list | grep rundesk"
    return 1
  fi
}

# An install from before the program had a directory of its own put it directly in
# $INSTALL_DIR, beside the data. Take those entries away rather than leaving two rundesks in
# one place — a stale `src/` there is what `python3 -` below would find first.
#
# The names spared are the ones that were data in that layout, and this is the only place such
# a list is left: it describes a shape that no longer exists, so it cannot go out of date.
tidy_the_old_layout() {
  [[ -f "$INSTALL_DIR/rundesk" && ! -e "$INSTALL_DIR/.git" ]] || return 0
  local entry base
  for entry in "$INSTALL_DIR"/* "$INSTALL_DIR"/.[!.]*; do
    [[ -e "$entry" ]] || continue
    base="${entry##*/}"
    case "$base" in
      app|agents|logs|run|schedules) continue ;;
    esac
    rm -rf "$entry"
  done
  echo "took the program out of $INSTALL_DIR; your agents and what your gateways wrote stayed put"
}

# ---------------------------------------------------------------- uninstall
if [[ "${1:-}" == "--uninstall" ]]; then
  check_install_dir
  echo "removing rundesk"
  removed=0
  purge=0
  [[ "${2:-}" == "--purge" ]] && purge=1
  # Refused rather than continued: deleting the command while a gateway is still running
  # leaves an agent nobody can reach and takes away the very thing that could stop it.
  if ! stop_gateways; then
    die "something rundesk was keeping is still running, so nothing was removed.
Stop it and try again, or see what is running with: rundesk status"
  fi
  for dir in /usr/local/bin "$HOME/.local/bin" "${RUNDESK_BIN_DIR:-}"; do
    [[ -n "$dir" && -L "$dir/rundesk" ]] || continue
    target="$(readlink "$dir/rundesk")"
    # Only ours: a `rundesk` on PATH that points somewhere else is not this install's
    # to remove, and removing it would be the installer breaking someone else's tool.
    if [[ "$target" == "$APP_DIR/rundesk" || "$target" == "$INSTALL_DIR/rundesk" \
          || ( -n "$SCRIPT_DIR" && "$target" == "$SCRIPT_DIR/rundesk" ) ]]; then
      rm -f "$dir/rundesk"; echo "removed $dir/rundesk"; removed=1
    fi
  done
  [[ "$removed" == 0 ]] && echo "No rundesk symlink pointing at a rundesk install was found on PATH."

  config_dir="$HOME/.config/rundesk"
  if [[ "$purge" == 1 && -d "$config_dir" ]]; then
    rm -rf "$config_dir"; echo "removed $config_dir"
  elif [[ -d "$config_dir" ]]; then
    echo "Settings in $config_dir were left alone (add --purge to delete them)."
  fi

  # The virtualenv is the installer's, wherever it put it — a checkout does not come with one.
  for venv in "$APP_DIR/.venv" "$INSTALL_DIR/.venv" "${SCRIPT_DIR:-/nonexistent}/.venv"; do
    [[ -d "$venv" ]] && { rm -rf "$venv"; echo "removed what rundesk installed for itself: $venv"; removed=1; }
  done

  # Only a directory this installer laid down is its to delete. A clone carries history and
  # is somebody's work, wherever it happens to sit.
  #
  # **The program goes whole, and nothing else is looked at.** It used to be taken entry by
  # entry out of a directory that was part program and part data, spared by a list of names —
  # so `rm -rf "$INSTALL_DIR"` once took every gateway log and every schedule, and the fix was
  # a list that would stop being true the day anything was added beside it. The program has a
  # directory of its own now, so removal cannot reach data even by mistake (R-RM-8).
  if is_someones_work "$INSTALL_DIR"; then
    echo "left $INSTALL_DIR alone — it is a checkout, not something this installer created."
  else
    # An install from before the program had a directory of its own is removed too, or
    # somebody updating and then removing would be left with the older rundesk still there
    # and still on their PATH.
    # Asked here rather than trusted to the function's own guard: it returns success when
    # there is nothing to do, and `&& removed=1` on that reported having removed rundesk from
    # a machine that had none of it.
    if [[ -f "$INSTALL_DIR/rundesk" ]]; then
      tidy_the_old_layout >/dev/null
      echo "removed the older rundesk from $INSTALL_DIR"
      removed=1
    fi
    if [[ -d "$APP_DIR" ]]; then
      if is_someones_work "$APP_DIR"; then
        echo "left $APP_DIR alone — it is a checkout, not something this installer created."
      else
        rm -rf "$APP_DIR"; echo "removed rundesk from $APP_DIR"; removed=1
      fi
    fi
  fi
  # Everything beside the program is the owner's: their agents, and what their gateways wrote
  # (R-RM-4, R-RM-10, R-GW-18, R-AGT-3). A reinstall after trouble is exactly the moment the
  # account of what went wrong matters most, and it was being deleted by the command somebody
  # runs to fix the trouble.
  if [[ -d "$INSTALL_DIR" ]] && ! is_someones_work "$INSTALL_DIR"; then
    if [[ "$purge" == 1 ]]; then
      rm -rf "$INSTALL_DIR"; echo "removed everything rundesk kept: $INSTALL_DIR"; removed=1
    else
      theirs=""
      # Named one level in. With everything of the owner's under `data/`, listing the top
      # level would say the single word "data" and tell them nothing about what is being
      # kept. The top level is still walked for anything an older layout left beside it.
      for entry in "$DATA_DIR"/* "$DATA_DIR"/.[!.]* "$INSTALL_DIR"/* "$INSTALL_DIR"/.[!.]*; do
        [[ -e "$entry" ]] || continue
        case "${entry##*/}" in app|data) continue ;; esac
        theirs="${theirs:+$theirs, }${entry##*/}"
      done
      if [[ -n "$theirs" ]]; then
        echo "kept your agents and what your gateways wrote ($theirs) — add --purge to delete them."
      else
        rmdir "$INSTALL_DIR" 2>/dev/null && echo "removed $INSTALL_DIR"
      fi
    fi
  fi
  if [[ "$removed" == 0 ]]; then
    echo "nothing of rundesk was found on this machine; nothing to remove."
  else
    echo "rundesk uninstalled."
  fi
  exit 0
fi

# ---------------------------------------------------------------- install
require_python
check_install_dir

echo "installing rundesk"

if is_local_checkout; then
  REPO_ROOT="$SCRIPT_DIR"
  echo "installing from this checkout: $REPO_ROOT"
else
  echo "installing into $APP_DIR"
  command -v curl >/dev/null 2>&1 || die "curl is required to download rundesk."
  command -v tar  >/dev/null 2>&1 || die "tar is required to unpack rundesk."
  # Before anything is fetched: what is already there may not be ours to replace. Both
  # places, because an install from before the program had a directory of its own is at
  # $INSTALL_DIR and a clone could be sitting at either.
  for standing in "$APP_DIR" "$INSTALL_DIR"; do
    if is_someones_work "$standing"; then
      die "$standing is a checkout, and replacing it would take its history and any
uncommitted work with it. Move it aside, or set RUNDESK_INSTALL_DIR somewhere else."
    fi
  done
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  # The newest *published release*, not whatever is on the branch (R-INS-15).
  # Installing the branch would hand someone a version that was never released,
  # reporting a number no release carries — and then `rundesk update` would offer
  # to move them backwards onto it.
  echo "looking up the newest rundesk release"
  # **Asked of the website, not the API.** `api.github.com` allows sixty calls an
  # hour *per IP* to anyone without a token — and an IP is shared by everyone behind
  # one office router, one VPN, or one CI provider's runners. Installing rundesk is
  # exactly the moment somebody has no token and no patience, and "could not
  # determine the newest release; check the connection" sends them to look at a
  # connection that is fine.
  #
  # `releases/latest` on github.com redirects to `releases/tag/<tag>`, so following
  # it and reading where it landed gives the same answer off an ordinary web request.
  # The API is kept as a second try, because a redirect is a shape that could change
  # and being wrong in two ways at once is unlikely.
  #
  # No token is read from the environment on purpose: a machine that happens to have
  # one exported must not have it spent on a lookup nobody asked to authenticate.
  tag=""
  landed="$(curl -fsSL -o /dev/null -w '%{url_effective}' \
            "https://github.com/$REPO_SLUG/releases/latest" 2>/dev/null || true)"
  case "$landed" in
    */releases/tag/*) tag="${landed##*/releases/tag/}" ;;
  esac
  if [ -z "$tag" ]; then
    release="$work/release.json"
    if curl -fsSL "https://api.github.com/repos/$REPO_SLUG/releases/latest" \
         -o "$release" 2>/dev/null; then
      tag="$(python3 - "$release" <<'TAG' || true
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as response:
        tag = json.load(response).get("tag_name")
except (AttributeError, json.JSONDecodeError, OSError, UnicodeError):
    raise SystemExit(1)
if not isinstance(tag, str) or not tag:
    raise SystemExit(1)
print(tag)
TAG
)"
    fi
  fi
  if [ -z "$tag" ]; then
    die "could not determine the newest release. GitHub may be rate-limiting this
network, or there may be nothing published yet — both look the same from here.
Retrying in a few minutes usually settles it."
  fi
  echo "downloading ${tag}"
  source_url="https://github.com/$REPO_SLUG/archive/refs/tags/$tag.tar.gz"
  curl -fsSL "$source_url" -o "$work/rundesk.tar.gz" ||
    die "could not download rundesk from $REPO_SLUG."
  echo "unpacking $(du -h "$work/rundesk.tar.gz" | cut -f1 | tr -d ' ')"
  tar -xzf "$work/rundesk.tar.gz" -C "$work"
  extracted="$(find "$work" -maxdepth 1 -type d -name 'rundesk-cli-*' | head -1)"
  [[ -n "$extracted" ]] || die "the downloaded archive did not look like a rundesk release."
  tidy_the_old_layout
  rm -rf "$APP_DIR"
  mkdir -p "$INSTALL_DIR"
  mv "$extracted" "$APP_DIR"
  REPO_ROOT="$APP_DIR"
fi

# Anything beyond the standard library goes into the install's own virtualenv. The machine's
# Python is never written to — modern ones refuse it anyway, and a tool that needs its user to
# reason about that has already lost them.
REQUIREMENTS="${RUNDESK_REQUIREMENTS:-$REPO_ROOT/requirements.txt}"
if [[ -f "$REQUIREMENTS" ]] && grep -qvE '^\s*(#|$)' "$REQUIREMENTS"; then
  echo "installing what rundesk needs into $REPO_ROOT/.venv — this is the slow part"
  # **Asked of `rundesk.dependencies`, which is also what an update builds against.** The
  # same work written twice — once here in shell and once in Python — is how an install and
  # an update come to disagree about what "installed" means, and only one of them was
  # checking that what landed is what was declared. Called the way `stop_gateways` above
  # calls into the tree, because this is the same kind of thing: product behaviour that the
  # installer asks for rather than contains.
  if ! python3 - "$REPO_ROOT" "$REQUIREMENTS" <<'DEPS'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1] + "/src")
from rundesk import dependencies

why = dependencies.provision(Path(sys.argv[1]), requirements=Path(sys.argv[2]))
if why:
    print(why, file=sys.stderr)
    raise SystemExit(1)
DEPS
  then
    die "could not install what rundesk needs (see $REQUIREMENTS)."
  fi
  echo "everything rundesk needs is in place"
fi

SHIM="$REPO_ROOT/rundesk"
[[ -f "$SHIM" ]] || die "the install is missing its entry point ($SHIM)."
chmod +x "$SHIM"

BINDIR="$(choose_bindir)"
mkdir -p "$BINDIR"
# `ln -sf` unlinks whatever is already there. The uninstall path reads the link before
# removing it, precisely so it never takes somebody else's tool; the install path used to
# overwrite without looking. /usr/local/bin is user-writable on a Homebrew mac, so a
# collision with an unrelated `rundesk` is an ordinary thing, not a contrived one.
if [[ -e "$BINDIR/rundesk" && ! -L "$BINDIR/rundesk" ]]; then
  die "$BINDIR/rundesk already exists and is not a link this installer placed. Move it aside first."
fi
if [[ -L "$BINDIR/rundesk" ]]; then
  case "$(readlink "$BINDIR/rundesk")" in
    */rundesk) ;;
    *) die "$BINDIR/rundesk points at $(readlink "$BINDIR/rundesk"), which is not a rundesk. Move it aside first." ;;
  esac
fi
ln -sf "$SHIM" "$BINDIR/rundesk"
echo "linked $BINDIR/rundesk -> $SHIM"

# Refuse to claim success until the command actually answers: an installer that
# reports done and leaves something that cannot run is the worst of both.
"$BINDIR/rundesk" version >/dev/null 2>&1 || die "rundesk was installed but would not run."
echo "checked that it runs"

case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo; echo "note: $BINDIR is not on your PATH. Add it:"; echo "  export PATH=\"$BINDIR:\$PATH\"" ;;
esac

echo
"$BINDIR/rundesk" version
echo "Run 'rundesk' to see what it can do."
