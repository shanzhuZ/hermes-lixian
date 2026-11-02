#!/usr/bin/env bash
# hermes-lixian launcher (Linux/macOS)
# - HERMES_HOME 强制指向本仓库 var/hermes
# - hermes 优先用本仓库 hermes-agent/venv（不依赖 hermes-xa）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_HOME="${REPO_ROOT}/var/hermes"
LOCAL_HERMES="${REPO_ROOT}/hermes-agent/venv/bin/hermes"

if [[ ! -d "${RUNTIME_HOME}" ]]; then
  echo "First run: init var/hermes ..."
  bash "${REPO_ROOT}/scripts/init-hermes-runtime.sh"
fi

export HERMES_HOME="${RUNTIME_HOME}"
export LIXIAN_ROOT="${REPO_ROOT}"

# MCP 用解释器：优先本仓库 venv，其次 python3/python
if [[ -z "${LIXIAN_PYTHON:-}" ]]; then
  if [[ -x "${REPO_ROOT}/hermes-agent/venv/bin/python" ]]; then
    export LIXIAN_PYTHON="${REPO_ROOT}/hermes-agent/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    export LIXIAN_PYTHON="$(command -v python3)"
  else
    export LIXIAN_PYTHON="$(command -v python)"
  fi
fi

echo "HERMES_HOME=${HERMES_HOME}"
echo "LIXIAN_ROOT=${LIXIAN_ROOT}"
echo "LIXIAN_PYTHON=${LIXIAN_PYTHON}"

# 解析 hermes：HERMES_BIN > 本仓库 venv > PATH
HERMES_BIN_RESOLVED=""
if [[ -n "${HERMES_BIN:-}" && -x "${HERMES_BIN}" ]]; then
  HERMES_BIN_RESOLVED="${HERMES_BIN}"
  echo "HERMES_BIN(env)=${HERMES_BIN_RESOLVED}"
elif [[ -x "${LOCAL_HERMES}" ]]; then
  HERMES_BIN_RESOLVED="${LOCAL_HERMES}"
elif command -v hermes >/dev/null 2>&1; then
  HERMES_BIN_RESOLVED="$(command -v hermes)"
fi

if [[ -z "${HERMES_BIN_RESOLVED}" ]]; then
  cat <<EOF
本仓库尚未安装 hermes CLI。请先执行：
  cd ${REPO_ROOT}/hermes-agent
  python3 -m venv venv
  ./venv/bin/python -m pip install -U pip
  ./venv/bin/pip install -e '.[messaging]'
然后再运行: ./chat.sh gateway
或设置 HERMES_BIN 指向本仓库的 hermes。
EOF
  exit 1
fi

echo "HERMES_BIN=${HERMES_BIN_RESOLVED}"
echo "skills:"
if [[ -d "${HERMES_HOME}/skills" ]]; then
  ls -1 "${HERMES_HOME}/skills" 2>/dev/null || true
fi

# 同步根目录最新 config / .env / SOUL 到运行时
cp -f "${REPO_ROOT}/config.yaml" "${RUNTIME_HOME}/config.yaml"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  cp -f "${REPO_ROOT}/.env" "${RUNTIME_HOME}/.env"
fi
if [[ -f "${REPO_ROOT}/SOUL.md" ]]; then
  cp -f "${REPO_ROOT}/SOUL.md" "${RUNTIME_HOME}/SOUL.md"
fi

exec "${HERMES_BIN_RESOLVED}" "$@"
