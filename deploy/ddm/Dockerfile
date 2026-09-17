# DDM-Net boundary inference for PraxiProof on DGX Spark (arm64, GB10).
FROM nvcr.io/nvidia/pytorch:26.08-py3
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir einops timm lightning omegaconf toml av tqdm ipdb matplotlib qwen-vl-utils transformers decord2 \
 && pip uninstall -y datasets
ENV PYTHONUNBUFFERED=1
