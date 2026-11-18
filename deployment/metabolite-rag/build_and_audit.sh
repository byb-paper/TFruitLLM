#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${ROOT:-/work/home/acuckjum5f/fruit}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HERE="${HERE:-$ROOT/23.metabolite_rag}"
QA_SOURCE="${QA_SOURCE:-$ROOT/13.sft_v16/data/sft_tpm.jsonl}"
CATALOG="${CATALOG:-$HERE/metabolites_13species.tsv}"
OUT="${OUT:-$ROOT/24.metabolite_rag_runtime}"
mkdir -p "$OUT"
args=("$PYTHON_BIN" "$HERE/build_metabolite_qa_rag.py" --catalog "$CATALOG" --qa "$QA_SOURCE" --output-db "$OUT/metabolite_rag.sqlite" --output-qa "$OUT/metabolite_qa.jsonl" --audit "$OUT/audit.json")
# Optional tab-separated manifest: one literature XLSX/CSV/TSV path per line.
if [[ -f "$HERE/literature_manifest.txt" ]]; then while IFS= read -r p; do [[ -z "$p" || "$p" == \#* ]] || args+=(--literature "$p"); done < "$HERE/literature_manifest.txt"; fi
# Optional PubTator BioC JSONL created from the corpus PMIDs.
if [[ -f "$HERE/pubtator_chemicals.jsonl" ]]; then args+=(--pubtator "$HERE/pubtator_chemicals.jsonl"); fi
"${args[@]}"
"$PYTHON_BIN" - <<PY
import json,sys
p='$OUT/audit.json'; a=json.load(open(p,encoding='utf-8'))
print('RAG passages:',a['rag_passages']); print('generated QA:',a['generated_qa']); print('missing catalog entries:',len(a['missing']))
if not a['rag_passages']: sys.exit('ERROR: no RAG passages built')
PY
echo "Outputs: $OUT/metabolite_rag.sqlite $OUT/metabolite_qa.jsonl $OUT/audit.json"
