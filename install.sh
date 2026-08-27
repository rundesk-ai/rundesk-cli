#!/usr/bin/env bash
#
# Put rundesk on this machine.
#
#     curl -fsSL https://raw.githubusercontent.com/rundesk-ai/rundesk-cli/main/install.sh | bash
#
# This script is a bootstrap and nothing else. It finds a Python, gets a copy of rundesk, and hands
# over to `rundesk install`, which makes every decision: where things go, what is written, what is
# refused, and whether the installed command really answers.
#
# It is deliberately small. The installer it replaces was eight hundred lines of shell holding real
# product behaviour — what an install is made of, which files belong to whom, what a purge may
# delete — none of which could be tested without running it on somebody's machine. All of that is
# Python now, and covered by tests/test_install.py.
#
# Environment:
#   RUNDESK_HOME      where rundesk is installed (default ~/.rundesk)
#   RUNDESK_BIN_DIR   where the `rundesk` command is linked (default: the first writable of
#                     /usr/local/bin, ~/.local/bin)

set -euo pipefail

REPO="rundesk-ai/rundesk-cli"
MIN_PYTHON_MINOR=9

die() { echo "install: $*" >&2; exit 1; }
say() { echo "$*" >&2; }

usage() {
  cat <<'USAGE'
Usage:
  ./install.sh              install the latest release, or this checkout
  ./install.sh -h|--help    print this usage and change nothing

Environment:
  RUNDESK_HOME      where rundesk is installed (default: ~/.rundesk)
  RUNDESK_BIN_DIR   where the rundesk command is linked

Uninstall with:
  rundesk uninstall --confirm [--purge --root <dir>]
USAGE
}

# Read the whole command line before finding an interpreter, fetching a release, or handing over.
# Inspection and refusal must be unable to enter any path that changes an install.
if (( $# == 1 )) && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
elif (( $# > 0 )); then
  unsupported="$1"
  if [[ "$unsupported" == "-h" || "$unsupported" == "--help" ]]; then
    unsupported="$2"
  fi
  echo "install: unsupported argument '${unsupported}'" >&2
  usage >&2
  exit 2
fi

# --- a Python that is new enough ---------------------------------------------------------------
# Asked of the interpreter rather than parsed out of `--version`, so the answer comes from the thing
# that will actually run rundesk.
find_python() {
  local candidate
  for candidate in python3 /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, ${MIN_PYTHON_MINOR}) else 1)" 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(find_python)" || die "rundesk needs python3.${MIN_PYTHON_MINOR} or newer, and this machine has none"

# --- a copy of rundesk to install from ----------------------------------------------------------
# Run from a checkout, that checkout is what gets installed — which is how a developer installs what
# they are working on. Otherwise fetch the newest published release.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CLEAN_UP=""
trap '[[ -n "$CLEAN_UP" ]] && rm -rf "$CLEAN_UP"' EXIT

if [[ -f "${HERE}/rundesk" && -d "${HERE}/src/rundesk" ]]; then
  SOURCE="$HERE"
  say "install: installing this checkout"
else
  command -v curl >/dev/null 2>&1 || die "curl is needed to fetch a release, and is not on this machine"
  command -v tar  >/dev/null 2>&1 || die "tar is needed to unpack a release, and is not on this machine"

  # The website's redirect rather than the API: the anonymous API allows sixty questions an hour,
  # and somebody installing should never meet that.
  LANDED="$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest")" \
    || die "could not reach GitHub to find the newest release"
  TAG="${LANDED##*/}"
  [[ "$TAG" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "GitHub did not name a release to install (got '${TAG}')"

  CLEAN_UP="$(mktemp -d)"
  say "install: fetching ${TAG}"
  curl -fsSL "https://github.com/${REPO}/releases/download/${TAG}/rundesk-cli.tar.gz" \
    -o "${CLEAN_UP}/release.tar.gz" \
    || die "could not download ${TAG}"
  tar -xzf "${CLEAN_UP}/release.tar.gz" -C "$CLEAN_UP" || die "${TAG} could not be unpacked"

  SOURCE=""
  for candidate in "${CLEAN_UP}"/*/; do
    if [[ -f "${candidate}rundesk" && -d "${candidate}src/rundesk" ]]; then
      SOURCE="${candidate%/}"
      break
    fi
  done
  [[ -n "$SOURCE" ]] || die "${TAG} does not contain a rundesk tree"
fi

# --- hand over --------------------------------------------------------------------------------
# Everything from here is Python, and `rundesk install` is what decides all of it. The source tree
# runs its own installer, so the release being installed is the one making the decisions.
ARGS=(install --source "$SOURCE")
[[ -n "${RUNDESK_BIN_DIR:-}" ]] && ARGS+=(--bin-dir "$RUNDESK_BIN_DIR")

exec "$PYTHON" "${SOURCE}/rundesk" "${ARGS[@]}"
