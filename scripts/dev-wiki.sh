#!/bin/sh
# scripts/dev-wiki.sh
set -eu
WIKI_VERSION=v0.8.0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec uvx --from "git+https://github.com/timothymarois/wiki-builder@$WIKI_VERSION" \
     wiki "$@" --root "$ROOT"
