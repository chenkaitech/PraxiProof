#!/usr/bin/env bash
# Sync to the DGX Spark, install, run tests, and (re)start the user service on port 8090.
# Usage: deploy/deploy.sh [--skip-tests]   Extra pytest args via PYTEST_ARGS="-m spark".
set -euo pipefail

HOST="${SPARK_HOST:-chenaki@192.168.71.111}"
KEY="${SPARK_KEY:-$HOME/.ssh/spark_id}"
REMOTE_DIR="${REMOTE_DIR:-praxiproof}"
RUN_TESTS=1
[[ "${1:-}" == "--skip-tests" ]] && RUN_TESTS=0

cd "$(dirname "$0")/.."
rsync -az --delete -e "ssh -i $KEY -o BatchMode=yes" \
  --exclude "._*" --exclude .DS_Store --exclude "demo/manuals/*.pdf" --exclude .venv --exclude .git --exclude data --exclude __pycache__ --exclude .pytest_cache \
  ./ "$HOST:$REMOTE_DIR/"

ssh -i "$KEY" -o BatchMode=yes "$HOST" \
  REMOTE_DIR="$REMOTE_DIR" RUN_TESTS="$RUN_TESTS" PYTEST_ARGS="${PYTEST_ARGS:-}" \
  UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://mirrors.aliyun.com/pypi/simple/}" bash -s <<'REMOTE'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH" UV_DEFAULT_INDEX
cd "$HOME/$REMOTE_DIR"
uv sync --quiet
if [[ "$RUN_TESTS" == 1 ]]; then
  uv run pytest -q $PYTEST_ARGS
fi
mkdir -p "$HOME/.config/systemd/user" "$HOME/praxiproof-data"
cp deploy/praxiproof.service "$HOME/.config/systemd/user/praxiproof.service"
systemctl --user daemon-reload
systemctl --user enable --quiet praxiproof.service
systemctl --user restart praxiproof.service
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8090/health; then echo; exit 0; fi
  sleep 1
done
journalctl --user -u praxiproof -n 60 --no-pager
exit 1
REMOTE
