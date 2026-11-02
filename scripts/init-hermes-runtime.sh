#!/usr/bin/env bash
# Init Hermes runtime dir var/hermes (HERMES_HOME)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_HOME="${REPO_ROOT}/var/hermes"

echo "RepoRoot=${REPO_ROOT}"
echo "RuntimeHome=${RUNTIME_HOME}"

mkdir -p "${RUNTIME_HOME}"

SKILLS_LINK="${RUNTIME_HOME}/skills"
SKILLS_TARGET="${REPO_ROOT}/skills"
if [[ -L "${SKILLS_LINK}" ]]; then
  echo "Symlink exists: ${SKILLS_LINK}"
elif [[ -e "${SKILLS_LINK}" ]]; then
  echo "Path exists and is not a symlink: ${SKILLS_LINK}" >&2
  exit 1
else
  ln -sfn "${SKILLS_TARGET}" "${SKILLS_LINK}"
  echo "Created symlink: ${SKILLS_LINK} -> ${SKILLS_TARGET}"
fi

cp -f "${REPO_ROOT}/config.yaml" "${RUNTIME_HOME}/config.yaml"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  cp -f "${REPO_ROOT}/.env" "${RUNTIME_HOME}/.env"
fi
if [[ -f "${REPO_ROOT}/SOUL.md" ]]; then
  cp -f "${REPO_ROOT}/SOUL.md" "${RUNTIME_HOME}/SOUL.md"
fi

echo ""
echo "Done. Start with: ./chat.sh gateway  (HERMES_HOME=${RUNTIME_HOME})"
