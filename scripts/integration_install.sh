#!/usr/bin/env bash
# usage: scripts/integration_install.sh <package> [ref]
# Installs <package> with its test extra, then replaces every Bazis package it depends on
# with the code of its repository at <ref> (default: main), cloned with tags so that
# setuptools-scm computes the versions. CORE_DIR: a checkout of the core to use instead.
set -euo pipefail
PACKAGE=$1
REF=${2:-main}
SRC=${SRC:-src}

clone() {
  # the core of the checked-out repository (e.g. the pull request), if given
  if [ "$1" = bazis ] && [ -n "${CORE_DIR:-}" ] && [ ! -e "$SRC/bazis" ]; then
    ln -s "$CORE_DIR" "$SRC/bazis"
  fi
  if [ ! -d "$SRC/$1" ]; then
    git clone --quiet --branch "$REF" "https://github.com/ecofuture-tech/$1" "$SRC/$1" \
      || git clone --quiet "https://github.com/ecofuture-tech/$1" "$SRC/$1"
  fi
}

mkdir -p "$SRC"
clone "$PACKAGE"
uv pip install -e "$SRC/$PACKAGE[test]"

# the Bazis packages the package needs (resolved from PyPI above)
DEPS=$(uv pip list --format json | python -c '
import json, sys
names = sorted({p["name"].lower().replace("_", "-") for p in json.load(sys.stdin)})
print(" ".join(n for n in names if n == "bazis" or n.startswith("bazis-")))
')
ARGS=()
for dep in $DEPS; do
  [ "$dep" = "$PACKAGE" ] && continue
  clone "$dep"
  ARGS+=(-e "$SRC/$dep")
done
if [ ${#ARGS[@]} -gt 0 ]; then
  uv pip install "${ARGS[@]}" -e "$SRC/$PACKAGE[test]"
fi
uv pip list | grep -i '^bazis'
