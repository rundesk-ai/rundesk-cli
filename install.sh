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
# Env overrides: RUNDESK_INSTALL_DIR (default ~/.rundesk), RUNDESK_BIN_DIR, RUNDESK_REPO_SLUG.
set -euo pipefail

REPO_SLUG="${RUNDESK_REPO_SLUG:-rundesk-ai/rundesk-cli}"
INSTALL_DIR="${RUNDESK_INSTALL_DIR:-$HOME/.rundesk}"
MIN_PYTHON_MINOR=9

die() { echo "error: $*" >&2; exit 1; }

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# A checkout is where this script sits next to the thing it installs — and is not the
# directory the installer itself created. Without that last clause, uninstalling from a
# downloaded install looks exactly like uninstalling from somebody's clone, and the
# installer politely refuses to remove its own directory.
is_local_checkout() {
  [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/rundesk" && -d "$SCRIPT_DIR/src/rundesk_cli" &&
     "$SCRIPT_DIR" != "$INSTALL_DIR" ]]
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

# ---------------------------------------------------------------- uninstall
if [[ "${1:-}" == "--uninstall" ]]; then
  removed=0
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
    [[ -d "$venv" ]] && { rm -rf "$venv"; echo "removed $venv"; }
  done

  # A checkout is yours; only a directory this installer created is its to delete.
  if [[ -d "$INSTALL_DIR" ]] && ! is_local_checkout; then
    rm -rf "$INSTALL_DIR"; echo "removed $INSTALL_DIR"
  fi
  echo "rundesk uninstalled."
  exit 0
fi

# ---------------------------------------------------------------- install
require_python

if is_local_checkout; then
  REPO_ROOT="$SCRIPT_DIR"
  echo "installing from this checkout: $REPO_ROOT"
else
  command -v curl >/dev/null 2>&1 || die "curl is required to download rundesk."
  command -v tar  >/dev/null 2>&1 || die "tar is required to unpack rundesk."
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  # The newest *published release*, not whatever is on the branch. Installing the branch
  # would hand someone a version that was never released, reporting a number no release
  # carries — and then `rundesk update` would offer to move them backwards onto it.
  echo "looking up the newest rundesk release"
  tag="$(curl -fsSL "https://api.github.com/repos/$REPO_SLUG/releases/latest" 2>/dev/null |
         sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
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
  echo "installing what rundesk needs, into $REPO_ROOT/.venv"
  python3 -m venv "$REPO_ROOT/.venv" || die "could not create the virtualenv rundesk keeps its dependencies in."
  "$REPO_ROOT/.venv/bin/python" -m pip install --quiet --upgrade pip ||
    die "could not prepare the virtualenv's installer."
  "$REPO_ROOT/.venv/bin/python" -m pip install --quiet -r "$REQUIREMENTS" ||
    die "could not install what rundesk needs (see $REQUIREMENTS)."
  # Installed is not the same as usable: pip will happily leave a set of packages that
  # cannot satisfy each other. Better to fail here than at the first turn.
  "$REPO_ROOT/.venv/bin/python" -m pip check --quiet ||
    die "what rundesk needs was installed, but the versions do not fit together."
fi

SHIM="$REPO_ROOT/rundesk"
[[ -f "$SHIM" ]] || die "the install is missing its entry point ($SHIM)."
chmod +x "$SHIM"

BINDIR="$(choose_bindir)"
mkdir -p "$BINDIR"
ln -sf "$SHIM" "$BINDIR/rundesk"
echo "linked $BINDIR/rundesk -> $SHIM"

# Refuse to claim success until the command actually answers: an installer that
# reports done and leaves something that cannot run is the worst of both.
"$BINDIR/rundesk" version >/dev/null 2>&1 || die "rundesk was installed but would not run."

case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo; echo "note: $BINDIR is not on your PATH. Add it:"; echo "  export PATH=\"$BINDIR:\$PATH\"" ;;
esac

echo
"$BINDIR/rundesk" version
echo "Run 'rundesk' to see what it can do."
