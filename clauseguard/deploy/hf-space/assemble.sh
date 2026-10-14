#!/usr/bin/env bash
set -euo pipefail

OUT="${1:?usage: assemble.sh <output-dir>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CG="$(cd "$HERE/../.." && pwd)"

rm -rf "$OUT"
mkdir -p "$OUT"
cd "$CG"

git ls-files -co --exclude-standard -z -- \
    clauseguard ui requirements-runtime.txt Dockerfile .dockerignore LICENSE \
    data/personas data/extracted data/demo data/adversarial/pdf data/policies/real \
    data/real \
  | grep -zvE '^data/real/(raw|riplay)/|^data/real/insuranceqa_questions\.jsonl$|__pycache__|\.pyc$' \
  | xargs -0 -I{} cp --parents {} "$OUT/"

cp "$HERE/README.md" "$OUT/README.md"
echo "assembled $(find "$OUT" -type f | wc -l) files, $(du -sh "$OUT" | cut -f1) in $OUT"
