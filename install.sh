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
set -euo pipefail

# Not overridable, and deliberately so. An install pointed at one repository updates itself
# from whichever one `rundesk update` is compiled to ask — there is nowhere on disk that
# remembers where a copy came from, so the two must be the same repository or an install
# silently drifts onto somebody else's releases. Kept in step by a test.
REPO_SLUG="rundesk-ai/rundesk-cli"
INSTALL_DIR="${RUNDESK_INSTALL_DIR:-$HOME/.rundesk}"
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
  [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/rundesk" && -d "$SCRIPT_DIR/src/rundesk_cli" ]]
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
  case "$dir" in
    */) die "RUNDESK_INSTALL_DIR must not end in a slash; got '$dir'." ;;
    */.|*/..) die "RUNDESK_INSTALL_DIR must name a directory, not '$dir'." ;;
  esac
  [[ "$dir" != "/" ]] || die "refusing to install into '/'."
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
  for candidate in "$INSTALL_DIR" "${SCRIPT_DIR:-}"; do
    if [[ -n "$candidate" && -f "$candidate/src/rundesk_cli/supervisor.py" ]]; then
      root="$candidate"; break
    fi
  done
  [[ -n "$root" ]] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    echo "note: python3 is gone, so any gateway still running was left as it is."
    return 0
  fi
  python3 - "$root" <<'STOP' || echo "note: gateways could not be stopped; check: launchctl list | grep rundesk"
import sys
sys.path.insert(0, sys.argv[1] + "/src")
from rundesk_cli import supervisor

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
}

# ---------------------------------------------------------------- uninstall
if [[ "${1:-}" == "--uninstall" ]]; then
  check_install_dir
  echo "removing rundesk"
  removed=0
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
    if [[ "$target" == "$INSTALL_DIR/rundesk" || ( -n "$SCRIPT_DIR" && "$target" == "$SCRIPT_DIR/rundesk" ) ]]; then
      rm -f "$dir/rundesk"; echo "removed $dir/rundesk"; removed=1
    fi
  done
  [[ "$removed" == 0 ]] && echo "No rundesk symlink pointing at a rundesk install was found on PATH."

  config_dir="$HOME/.config/rundesk"
  if [[ "${2:-}" == "--purge" && -d "$config_dir" ]]; then
    rm -rf "$config_dir"; echo "removed $config_dir"
  elif [[ -d "$config_dir" ]]; then
    echo "Settings in $config_dir were left alone (add --purge to delete them)."
  fi

  # The virtualenv is the installer's, wherever it put it — a checkout does not come with one.
  for venv in "$INSTALL_DIR/.venv" "${SCRIPT_DIR:-/nonexistent}/.venv"; do
    [[ -d "$venv" ]] && { rm -rf "$venv"; echo "removed what rundesk installed for itself: $venv"; removed=1; }
  done

  # Only a directory this installer laid down is its to delete. A clone carries history and
  # is somebody's work, wherever it happens to sit.
  if [[ -d "$INSTALL_DIR" ]]; then
    if is_someones_work "$INSTALL_DIR"; then
      echo "left $INSTALL_DIR alone — it is a checkout, not something this installer created."
    else
      rm -rf "$INSTALL_DIR"; echo "removed $INSTALL_DIR"; removed=1
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
  echo "installing into $INSTALL_DIR"
  command -v curl >/dev/null 2>&1 || die "curl is required to download rundesk."
  command -v tar  >/dev/null 2>&1 || die "tar is required to unpack rundesk."
  # Before anything is fetched: what is already there may not be ours to replace.
  if is_someones_work "$INSTALL_DIR"; then
    die "$INSTALL_DIR is a checkout, and replacing it would take its history and any
uncommitted work with it. Move it aside, or set RUNDESK_INSTALL_DIR somewhere else."
  fi
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  # The newest *published release*, not whatever is on the branch. Installing the branch
  # would hand someone a version that was never released, reporting a number no release
  # carries — and then `rundesk update` would offer to move them backwards onto it.
  echo "looking up the newest rundesk release"
  # The `|| true` is load-bearing. `set -e` aborts on a failing assignment and `-o pipefail`
  # fails this pipeline whenever curl does — a repository with no releases (404), a rate
  # limit (403), a dropped connection. Without it the fallback below is unreachable and the
  # install dies on exit 56 having printed nothing at all, not even a message.
  tag="$(curl -fsSL "https://api.github.com/repos/$REPO_SLUG/releases/latest" 2>/dev/null |
         sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)"
  if [[ -n "$tag" ]]; then
    echo "downloading ${tag}"
    source_url="https://github.com/$REPO_SLUG/archive/refs/tags/$tag.tar.gz"
  else
    # Nothing published yet — a repository can be perfectly usable before its first release.
    echo "no release published yet; taking the main branch instead."
    source_url="https://github.com/$REPO_SLUG/archive/refs/heads/main.tar.gz"
  fi
  curl -fsSL "$source_url" -o "$work/rundesk.tar.gz" ||
    die "could not download rundesk from $REPO_SLUG."
  echo "unpacking $(du -h "$work/rundesk.tar.gz" | cut -f1 | tr -d ' ')"
  tar -xzf "$work/rundesk.tar.gz" -C "$work"
  extracted="$(find "$work" -maxdepth 1 -type d -name 'rundesk-cli-*' | head -1)"
  [[ -n "$extracted" ]] || die "the downloaded archive did not look like a rundesk release."
  rm -rf "$INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  mv "$extracted" "$INSTALL_DIR"
  REPO_ROOT="$INSTALL_DIR"
fi

# Anything beyond the standard library goes into the install's own virtualenv. The machine's
# Python is never written to — modern ones refuse it anyway, and a tool that needs its user to
# reason about that has already lost them.
REQUIREMENTS="${RUNDESK_REQUIREMENTS:-$REPO_ROOT/requirements.txt}"
if [[ -f "$REQUIREMENTS" ]] && grep -qvE '^\s*(#|$)' "$REQUIREMENTS"; then
  echo "installing what rundesk needs into $REPO_ROOT/.venv — this is the slow part"
  python3 -m venv "$REPO_ROOT/.venv" || die "could not create the virtualenv rundesk keeps its dependencies in."
  "$REPO_ROOT/.venv/bin/python" -m pip install --quiet --upgrade pip ||
    die "could not prepare the virtualenv's installer."
  "$REPO_ROOT/.venv/bin/python" -m pip install --quiet -r "$REQUIREMENTS" ||
    die "could not install what rundesk needs (see $REQUIREMENTS)."
  echo "checking they fit together"
  # Installed is not the same as usable: pip will happily leave a set of packages that
  # cannot satisfy each other. Better to fail here than at the first turn.
  "$REPO_ROOT/.venv/bin/python" -m pip check --quiet ||
    die "what rundesk needs was installed, but the versions do not fit together."
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
