#!/usr/bin/env bash
# Run the ghost cases against each local model in turn, then print the results table.
#
#   LLAMA_SERVER=/opt/llama/llama-server MODELS=~/models scripts/run_bench.sh
#
# llama-server is started on 127.0.0.1 only and stopped again after each model.
set -euo pipefail
: "${LLAMA_SERVER:?set LLAMA_SERVER to the llama-server binary}"
: "${MODELS:?set MODELS to the folder with the .gguf files}"
PORT="${PORT:-8081}"
THREADS="${THREADS:-$(nproc 2>/dev/null || echo 6)}"
cd "$(dirname "$0")/.."
mkdir -p runtime results

runs=(
  "gemma-3-1b:gemma-3-1b-it-Q4_K_M.gguf"
  "qwen2.5-3b:qwen2.5-3b-instruct-q4_k_m.gguf"
  "gemma-3-4b:gemma-3-4b-it-Q4_K_M.gguf"
)

for run in "${runs[@]}"; do
  label="${run%%:*}"; file="${run#*:}"
  [[ -n "${ONLY:-}" && " $ONLY " != *" $label "* ]] && continue
  [[ -f "$MODELS/$file" ]] || { echo "missing model file: $MODELS/$file" >&2; exit 1; }
  echo "=== $label"
  "$LLAMA_SERVER" --model "$MODELS/$file" --host 127.0.0.1 --port "$PORT" --ctx-size 4096 --threads "$THREADS" --no-webui \
    >"runtime/server-$label.log" 2>&1 &
  pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT
  for _ in $(seq 1 180); do
    curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 "$pid" 2>/dev/null || { echo "llama-server exited early; see runtime/server-$label.log" >&2; exit 1; }
    sleep 1
  done
  python3 -m poltergeist bench --url "http://127.0.0.1:$PORT" --label "$label"
  kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true
  trap - EXIT
done

python3 -m poltergeist report results/*.json | tee results/TABLE.md
