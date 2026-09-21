#!/usr/bin/env bash
# 4-fold cross-validation of the whole ddm_vlm pipeline on the 12 sop-server-fan recordings, plus the
# untrained pure-VLM baseline on all 12. Every fold retrains DDM-Net and rebuilds the reference images from that
# fold's training recordings only, so a held-out recording is never seen by any component.
# Uses the praxiproof-ddm image (deploy/ddm/Dockerfile), which already contains the training dependencies.
# Resumable: a stage whose output already exists is skipped. Run on the DGX Spark:  deploy/ddm/cv/run_cv.sh
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
DATA="$HOME/datasets/sop-server-fan/server_fan"
TRAIN="$HOME/ddm-train"
CV="$TRAIN/data/cv"
OUT="$HOME/praxiproof-data/eval/cv"
LLM_MODEL="${LLM_MODEL:-qwen3.6:35b-a3b-q8_0}"
VLM_MODEL="${VLM_MODEL:-gemma4:31b}"
mkdir -p "$OUT" "$HOME/praxiproof-data/models/cv"
cd "$HOME/praxiproof"

fold_field() { python3 -c "import json,sys; print(' '.join(json.load(open('$CV/folds.json'))['fold$1']['$2']))"; }
have_summary() { [[ -f "$1" ]] && grep -q '"summary"' "$1"; }
write_settings() {  # dir backend checkpoint references
  mkdir -p "$1"
  python3 - "$@" <<'PY'
import json, os, sys
d, backend, ckpt, refs = sys.argv[1:5]
json.dump({"llm_model": os.environ["LLM_MODEL"], "vlm_model": os.environ["VLM_MODEL"], "vlm_thinking": False, "video_backend": backend,
           "sop_bp_url": None, "ddm_checkpoint": ckpt or None, "reference_dir": refs or None, "min_confidence": 0.5},
          open(f"{d}/settings.json", "w"), indent=2)
PY
}
export LLM_MODEL VLM_MODEL

for fold in 1 2 3 4; do
  if have_summary "$OUT/fold$fold.json"; then echo "fold$fold: done, skipping"; continue; fi
  echo "=== fold$fold $(date +%T)"
  ckpt="$HOME/praxiproof-data/models/cv/fold$fold.ckpt"
  if [[ ! -f "$ckpt" ]]; then
    sed -e "s#/workspace/data/train_clean.json#/workspace/data/cv/fold${fold}_train.json#" \
        -e "s#/workspace/data/val_clean.json#/workspace/data/cv/fold${fold}_val.json#" \
        -e "s#exp_name: \"server_fan_ddm_clean\"#exp_name: \"cv_fold${fold}\"#" "$TRAIN/spark_clean.yaml" > "$TRAIN/cv_fold$fold.yaml"
    grep -q "cv/fold${fold}_train.json" "$TRAIN/cv_fold$fold.yaml" && grep -q "cv/fold${fold}_val.json" "$TRAIN/cv_fold$fold.yaml" \
      && grep -q "cv_fold${fold}" "$TRAIN/cv_fold$fold.yaml" || { echo "fold$fold: yaml substitution failed"; exit 1; }
    ( cd "$TRAIN" && docker run --rm --name "ddm-cv-fold$fold" \
        --device nvidia.com/gpu=all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
        -e PYTHONUNBUFFERED=1 \
        -v "$PWD/ddm:/workspace/ddm" -v "$PWD/data:/workspace/data" -v "$PWD/output:/workspace/output" \
        -v "$PWD/cache:/root/.cache" -v "$PWD/cv_fold$fold.yaml:/workspace/fold.yaml:ro" \
        -w /workspace/ddm praxiproof-ddm:26.08 \
        python DDM-Net/train_sop_lightning.py --config /workspace/fold.yaml ) \
      > "$OUT/train_fold$fold.log" 2>&1
    best=$(grep -oP 'Best checkpoint: \K\S+' "$OUT/train_fold$fold.log" | tail -1)
    [[ -n "$best" ]] || { echo "fold$fold: training produced no checkpoint"; exit 1; }
    cp "${best/\/workspace\/output/$TRAIN/output}" "$ckpt"
    echo "fold$fold: $(basename "$(dirname "$best")")/$(basename "$best")" | tee "$OUT/ckpt_fold$fold.txt"
  fi
  refs="$HOME/praxiproof-data/references/cv_fold$fold"
  [[ -f "$refs/references.json" ]] || uv run praxiproof build-references --data "$DATA" --videos $(fold_field $fold train) \
      --held-out $(fold_field $fold held_out) --per-group 2 --out "$refs" > "$OUT/refs_fold$fold.log" 2>&1
  [[ -f "$refs/references.json" ]] || { echo "fold$fold: FAILED building reference images"; exit 1; }
  write_settings "$HOME/praxiproof-data-cv/fold$fold" ddm_vlm "$ckpt" "$refs"
  PRAXIPROOF_DATA_DIR="$HOME/praxiproof-data-cv/fold$fold" uv run praxiproof eval-sop --data "$DATA" --videos $(fold_field $fold held_out) --out "$OUT/fold$fold.json" > "$OUT/eval_fold$fold.log" 2>&1
  have_summary "$OUT/fold$fold.json" || { echo "fold$fold: eval FAILED $(date +%T)"; exit 1; }
  echo "fold$fold: eval ok $(date +%T)"
done

if ! have_summary "$OUT/local_vlm_all12.json"; then
  echo "=== pure VLM baseline on all 12 $(date +%T)"
  write_settings "$HOME/praxiproof-data-cv/local_vlm" local_vlm "" ""
  PRAXIPROOF_DATA_DIR="$HOME/praxiproof-data-cv/local_vlm" uv run praxiproof eval-sop --data "$DATA" \
    --videos Install_1 Install_3 Install_4 Install_5 Install_6 Install_7 Install_8 Install_9 Install_10 Install_11 Install_12 Install_13 \
    --out "$OUT/local_vlm_all12.json" > "$OUT/eval_local_vlm.log" 2>&1
  have_summary "$OUT/local_vlm_all12.json" || { echo "baseline eval FAILED"; exit 1; }
fi
echo "ALLDONE $(date +%T)"
