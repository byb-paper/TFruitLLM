# Metabolite QA + KG-RAG deployment

This module makes metabolite evidence from all 13 species available to both QA training and live RAG. It does not claim that a metabolite is present unless a source passage is available.

## 1. Upload

Upload this directory to:

`/work/home/acuckjum5f/fruit/23.metabolite_rag`

Add one source file per line to `literature_manifest.txt`. XLSX, CSV and TSV are supported. Keep the existing SFT file at `/work/home/acuckjum5f/fruit/13.sft_v16/data/sft_tpm.jsonl`.

For exhaustive discovery, fetch PubTator BioC chemical annotations for all corpus PMIDs. Chemical annotations automatically expand the seed catalog, so the pipeline is not limited to mangiferin or the bundled examples:

```bash
python fetch_pubtator_chemicals.py \
  --source /path/to/mango_literature.xlsx \
  --source /path/to/other_species_literature.xlsx \
  --output pubtator_chemicals.jsonl
```

## 2. Build

```bash
cd /work/home/acuckjum5f/fruit/23.metabolite_rag
bash build_and_audit.sh
```

Outputs:

- `/work/home/acuckjum5f/fruit/24.metabolite_rag_runtime/metabolite_qa.jsonl`
- `/work/home/acuckjum5f/fruit/24.metabolite_rag_runtime/metabolite_rag.sqlite`
- `/work/home/acuckjum5f/fruit/24.metabolite_rag_runtime/audit.json`

Review `audit.json`. Every catalog entry with zero evidence is listed in `missing`; do not pretend missing entries are covered. Add sources and rebuild until the required coverage is achieved.

## 3. Add QA to the next SFT run

```bash
cat /work/home/acuckjum5f/fruit/24.metabolite_rag_runtime/metabolite_qa.jsonl \
  >> /work/home/acuckjum5f/fruit/13.sft_v16/data/sft_tpm_metabolite.jsonl
```

Prefer building a new training file rather than overwriting the completed run. Deduplicate before retraining.

## 4. Model-management mount

Create a runtime directory containing:

```text
/root/models/                 base model + lora/
/root/rag/rag_gateway.py
/root/rag/metabolite_rag.sqlite
/root/rag/start_tfruitllm_rag.sh
```

Use this startup command:

```bash
bash /root/rag/start_tfruitllm_rag.sh
```

Keep service port `6666`. The gateway starts vLLM internally on `6667`, retrieves evidence, injects it into the prompt, and requires `[E1]` citations plus an Evidence list.

## 5. Acceptance tests

```bash
curl -s http://127.0.0.1:6666/health
curl -s http://127.0.0.1:6666/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"TFruitLLM","messages":[{"role":"user","content":"芒果苷在芒果中的研究证据有哪些？请列出来源。"}],"max_tokens":700}'
```

The answer passes only when concrete claims contain `[E#]` references and the final Evidence list includes PMID, DOI or a source path. Run analogous tests for all 13 species and review `audit.json` before publication.
