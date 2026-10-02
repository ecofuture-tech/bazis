#!/usr/bin/env bash
# usage: scripts/integration_install.sh <package> [ref]
# Installs <package> with its test extra and every Bazis package it depends on (also through
# the others) from the code of their repositories at <ref> (default: main; main where <ref>
# is missing or not based on main), cloned with tags so that setuptools-scm computes the
# versions. The checkouts override the requirements on them: a change can raise the minimal
# version of a Bazis package to the one it is about to release.
# CORE_DIR: a checkout of the core to use instead of its repository.
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
    git clone --quiet "https://github.com/ecofuture-tech/$1" "$SRC/$1"
    # the branch of the change if the repository has it and it is based on the current main
    # (a branch that was merged and left behind is ignored)
    if [ "$REF" != main ] && git -C "$SRC/$1" rev-parse -q --verify "origin/$REF" >/dev/null \
        && git -C "$SRC/$1" merge-base --is-ancestor origin/main "origin/$REF"; then
      git -C "$SRC/$1" checkout --quiet "$REF"
    fi
    echo "$1: $(git -C "$SRC/$1" rev-parse --abbrev-ref HEAD)"
  fi
}

# the Bazis packages a checkout requires (its dependencies and its test extra)
bazis_deps() {
  python - "$SRC/$1/pyproject.toml" <<'PY'
import re, sys, tomllib
project = tomllib.load(open(sys.argv[1], 'rb'))['project']
requirements = project.get('dependencies', []) + project.get('optional-dependencies', {}).get('test', [])
names = {re.match(r'[A-Za-z0-9_.-]+', r).group().lower().replace('_', '-') for r in requirements}
print(' '.join(sorted(n for n in names if n == 'bazis' or n.startswith('bazis-'))))
PY
}

mkdir -p "$SRC"
clone "$PACKAGE"
DONE=" $PACKAGE "
TODO=$(bazis_deps "$PACKAGE")
OVERRIDES="$SRC/overrides.txt"
: > "$OVERRIDES"
while [ -n "${TODO// /}" ]; do
  NEXT=""
  for dep in $TODO; do
    case "$DONE" in *" $dep "*) continue ;; esac
    DONE="$DONE$dep "
    clone "$dep"
    echo "$dep @ file://$(cd "$SRC/$dep" && pwd -P)" >> "$OVERRIDES"
    NEXT="$NEXT $(bazis_deps "$dep")"
  done
  TODO=$NEXT
done
uv pip install --override "$OVERRIDES" -e "$SRC/$PACKAGE[test]"
uv pip list | grep -i '^bazis'
