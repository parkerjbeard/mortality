# just recipes for Mortality

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := true

# Paths and tools
VENV := ".venv"
BIN := ".venv/bin"
PY := ".venv/bin/python"
PIP := ".venv/bin/pip"
RUFF := ".venv/bin/ruff"

default: help

help:
  @echo "Mortality – available recipes"
  @just --list

# --- Python setup ---

venv:
  if [ ! -d "{{VENV}}" ]; then python3 -m venv "{{VENV}}"; fi
  {{PIP}} -V || (echo "venv missing pip; retrying" && python3 -m venv "{{VENV}}")

install: venv
  {{PIP}} install --upgrade pip setuptools wheel
  # Base package with useful extras for experiments and tests
  {{PIP}} install -e ".[test,openai,anthropic,grok,gemini,autogen]"
  # Dev tools used in this repo
  {{PIP}} install ruff

env:
  if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; else echo ".env already exists"; fi

# --- Quality ---

lint: venv
  {{RUFF}} check src tests
  npm run lint --prefix ui/observer

fmt: venv
  {{RUFF}} --fix src tests
  npx --yes prettier --write "ui/observer/**/*.{ts,tsx,css,md}" || true

test: venv
  PYTHONPATH=src {{PY}} -m pytest -q

check: lint test

# --- UI ---

ui-install:
  npm ci --prefix ui/observer

ui-dev:
  npm run dev --prefix ui/observer

ui-build:
  npm run build --prefix ui/observer

# --- Demos ---

autogen-demo: install env
  : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required for autogen-demo}"
  : "${OPENROUTER_MODEL:?OPENROUTER_MODEL is required for autogen-demo}"
  : "${OPENROUTER_REASONING:=low}"
  PYTHONPATH=src {{PY}} -c $'import os\nimport anyio\nfrom mortality.experiments.base import LlmConfig\nfrom mortality.experiments.autogen_emergent import AutoGenEmergentExperiment, AutoGenEmergentConfig\nfrom mortality.llm.base import LLMProvider\nfrom mortality.orchestration.runtime import MortalityRuntime\n\nasync def main():\n    runtime = MortalityRuntime()\n    experiment = AutoGenEmergentExperiment()\n    model = os.getenv("MORTALITY_DEFAULT_MODEL") or os.getenv("OPENROUTER_MODEL")\n    if not model:\n        raise RuntimeError("Set OPENROUTER_MODEL or MORTALITY_DEFAULT_MODEL before running autogen-demo")\n    cfg = AutoGenEmergentConfig(llm=LlmConfig(provider=LLMProvider.OPENROUTER, model=model, temperature=0.2, top_p=0.9, max_output_tokens=512), rounds=2)\n    result = await experiment.run(runtime, cfg)\n    await runtime.shutdown()\n    print({"participants": list(result.diaries.keys()), "messages": len(result.metadata.get("messages", []))})\n\nanyio.run(main)\n'

# --- 15-minute Emergent Timer Run (OpenRouter) ---

emergent-run: install env
  provider="${MORTALITY_EMERGENT_PROVIDER:-openrouter}"; \
  if [ "$provider" = "openrouter" ]; then : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required for emergent-run when provider=openrouter}"; fi
  : "${OPENROUTER_REASONING:=low}"
  : "${OPENROUTER_TICK_SECONDS:=20}"
  : "${MORTALITY_EMERGENT_SPREAD_START:=5.0}"
  : "${MORTALITY_EMERGENT_SPREAD_END:=15.0}"
  : "${MORTALITY_REPLICAS_PER_MODEL:=1}"
  PYTHONPATH=src {{PY}} scripts/run_emergent.py

# --- Emergent Timer Run with Live Dashboard ---

emergent-live: install env
  provider="${MORTALITY_EMERGENT_PROVIDER:-openrouter}"; \
  if [ "$provider" = "openrouter" ]; then : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required for emergent-live when provider=openrouter}"; fi
  @echo "[live] Starting experiment with live dashboard on ws://localhost:${MORTALITY_WS_PORT:-8765}"
  @echo "[live] Open the UI at http://localhost:5173 and click 'Live' to connect"
  MORTALITY_LIVE_DASHBOARD=1 PYTHONPATH=src {{PY}} scripts/run_emergent.py
