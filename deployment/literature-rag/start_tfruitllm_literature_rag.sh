#!/usr/bin/env bash
set -Eeuo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
MODEL_DIR="${MODEL_DIR:-/root/models}"
RAG_DIR="${RAG_DIR:-$MODEL_DIR/rag}"
DB="${RAG_DB:-$RAG_DIR/literature_rag.sqlite}"
TP_SIZE="${TP_SIZE:-2}"
export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0,1}"

[[ -f "$DB" ]] || { echo "ERROR: missing literature RAG database: $DB" >&2; exit 2; }
[[ -f "$MODEL_DIR/config.json" ]] || { echo "ERROR: missing base model: $MODEL_DIR/config.json" >&2; exit 2; }
[[ -f "$MODEL_DIR/lora/adapter_config.json" ]] || { echo "ERROR: missing LoRA adapter" >&2; exit 2; }

"$PYTHON_BIN" -u -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_DIR" --served-model-name QwenBase \
  --host 127.0.0.1 --port 6667 \
  --tensor-parallel-size "$TP_SIZE" --max-model-len 8192 --trust-remote-code \
  --enable-lora --max-lora-rank 64 --lora-modules "TFruitLLM=$MODEL_DIR/lora" &
MODEL_PID=$!
trap 'kill "$MODEL_PID" 2>/dev/null || true' EXIT INT TERM

exec "$PYTHON_BIN" -u "$RAG_DIR/literature_rag_gateway.py" \
  --db "$DB" --host 0.0.0.0 --port 6666 \
  --upstream http://127.0.0.1:6667 --model-name TFruitLLM
