#!/usr/bin/env bash
# Fetch the AMT PAS compiler (the PDF engine this app wraps).
# It is treated as a read-only dependency — never edit files under compiler/.
set -euo pipefail
cd "$(dirname "$0")"

REPO="${PAS_COMPILER_REPO:-https://github.com/airandblueamt-Claude/amt-pas-compiler.git}"
DIR="compiler"

if [ -d "$DIR/.git" ]; then
  echo "Updating existing compiler in ./$DIR ..."
  git -C "$DIR" pull --ff-only
else
  echo "Cloning compiler from $REPO ..."
  git clone --depth 1 "$REPO" "$DIR"
fi
echo "Compiler ready at ./$DIR"
