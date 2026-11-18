#!/usr/bin/env bash
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITERATURE_ROOT="${LITERATURE_ROOT:-/work/home/acuckjum5f/fruit/literature}"
OUT="${OUT:-$HERE/output}"
mkdir -p "$OUT"

QA_ARGS=()
for path in "$@"; do QA_ARGS+=(--qa "$path"); done

python3 "$HERE/build_literature_qa_rag.py" \
  --literature-root "$LITERATURE_ROOT" \
  --taxonomy "$HERE/topic_taxonomy.json" \
  "${QA_ARGS[@]}" \
  --output-db "$OUT/literature_rag.sqlite" \
  --output-qa "$OUT/literature_qa.jsonl" \
  --audit "$OUT/literature_topic_audit.json" \
  --max-unclassified-rate "${MAX_UNCLASSIFIED_RATE:-0.30}"

echo "Built: $OUT/literature_rag.sqlite"
echo "QA:    $OUT/literature_qa.jsonl"
echo "Audit: $OUT/literature_topic_audit.json"
