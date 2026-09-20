#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/ddm-train"
docker run --rm --name ddm-train-clean \
  --device nvidia.com/gpu=all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -e PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ -e PYTHONUNBUFFERED=1 \
  -v "$PWD/ddm:/workspace/ddm" -v "$PWD/data:/workspace/data" -v "$PWD/output:/workspace/output" \
  -v "$PWD/cache:/root/.cache" -v "$PWD/spark_clean.yaml:/workspace/spark_clean.yaml:ro" \
  -w /workspace/ddm nvcr.io/nvidia/pytorch:26.08-py3 \
  bash -c "pip install -q einops timm lightning omegaconf toml av tqdm ipdb matplotlib qwen-vl-utils transformers decord2 2>&1 | tail -3 && pip uninstall -y -q datasets 2>&1 | tail -1; \
           python -c \"import torch; print(\\\"torch\\\", torch.__version__, torch.cuda.get_device_name(0))\" && \
           python DDM-Net/train_sop_lightning.py --config /workspace/spark_clean.yaml"
