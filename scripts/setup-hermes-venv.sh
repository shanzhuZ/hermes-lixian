#!/usr/bin/env bash
# 为本仓库 hermes-agent 创建独立 venv（不依赖 hermes-xa）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="${REPO_ROOT}/hermes-agent"
VENV_DIR="${AGENT_DIR}/venv"

if command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PY="$(command -v python)"
else
  echo "未找到 python3/python" >&2
  exit 1
fi

echo "RepoRoot=${REPO_ROOT}"
echo "Python=${PY}"
"${PY}" --version

cd "${AGENT_DIR}"
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating venv ..."
  "${PY}" -m venv "${VENV_DIR}"
fi

PIP="${VENV_DIR}/bin/pip"
VENV_PY="${VENV_DIR}/bin/python"
"${VENV_PY}" -m pip install -U pip setuptools wheel

if command -v uv >/dev/null 2>&1; then
  echo "uv sync ..."
  uv sync --python "${VENV_PY}" || true
  uv pip install -e '.[messaging]' --python "${VENV_PY}"
else
  echo "pip install -e '.[messaging]' ..."
  "${PIP}" install -e '.[messaging]'
fi

HERMES="${VENV_DIR}/bin/hermes"
if [[ ! -x "${HERMES}" ]]; then
  echo "install finished but hermes missing: ${HERMES}" >&2
  exit 1
fi

echo ""
echo "OK: ${HERMES}"
"${HERMES}" --version
echo ""
echo "Next:"
echo "  1) 若同机有 hermes-xa，请把本仓库 API_SERVER_PORT 改成非 8642（如 8643）"
echo "  2) ./chat.sh gateway"
