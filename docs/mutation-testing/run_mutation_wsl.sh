#!/usr/bin/env bash
set -euo pipefail

# WSL-ready script to run mutmut and copy HTML reports back to the Windows workspace
# Usage: run this from WSL where /mnt/c/... points to the repo

REPO_WIN_PATH="/mnt/c/Users/Seraphindra/Desktop/sahulatkar"
REPO_WS_PATH="$REPO_WIN_PATH"
GATEWAY_DIR="$REPO_WS_PATH/apps/gateway"
REPORTS_DIR="$REPO_WS_PATH/docs/mutation-testing/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "[mutmut-wsl] repo: $REPO_WS_PATH"

# Create an isolated venv inside the repo for WSL runs
VENV_DIR="$REPO_WS_PATH/.wsl_venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install mutmut pytest pytest-cov

cd "$GATEWAY_DIR"

echo "[mutmut-wsl] Running pytest to confirm tests pass..."
python -m pytest tests/test_services/test_kyc_service_unit.py -q

echo "[mutmut-wsl] Running mutmut (this may take several minutes)..."
mutmut run

echo "[mutmut-wsl] Generating mutmut HTML report..."
mutmut html

HTML_SRC_DIR="$GATEWAY_DIR/html"
BASELINE_DST="$REPORTS_DIR/mutation_baseline/html_$TIMESTAMP"
FINAL_DST="$REPORTS_DIR/mutation_final/html_$TIMESTAMP"

mkdir -p "$BASELINE_DST" "$FINAL_DST"
cp -r "$HTML_SRC_DIR/"* "$BASELINE_DST/"
cp -r "$HTML_SRC_DIR/"* "$FINAL_DST/"

echo "[mutmut-wsl] Copied HTML report to:"
echo "  $BASELINE_DST"
echo "  $FINAL_DST"

echo "[mutmut-wsl] Done. If you want the latest folder without timestamp, you can copy or rename the html_* directory back in Windows." 
