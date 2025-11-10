from __future__ import annotations

import json
import os
from datetime import datetime

import anyio

from mortality.experiments.base import LlmConfig
from mortality.experiments.registry import ExperimentRegistry
from mortality.llm.base import LLMProvider
from mortality.orchestration.runtime import MortalityRuntime
from mortality.telemetry.recorder import StructuredTelemetrySink
from mortality.telemetry.console import ConsoleTelemetrySink, MultiTelemetrySink


async def main() -> None:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY must be set in environment")

    # Emit both: structured bundle for later UI + live, colorized console logs.
    telemetry = MultiTelemetrySink([StructuredTelemetrySink(), ConsoleTelemetrySink()])
    runtime = MortalityRuntime(telemetry=telemetry)
    experiment = ExperimentRegistry().get("emergent-timers")

    spread_start = float(os.getenv("MORTALITY_EMERGENT_SPREAD_START", "5.0"))
    spread_end = float(os.getenv("MORTALITY_EMERGENT_SPREAD_END", "30.0"))
    tick_seconds = float(os.getenv("OPENROUTER_TICK_SECONDS", "30"))
    replicas = int(os.getenv("MORTALITY_REPLICAS_PER_MODEL", "2"))

    # Resolve models from environment with robust fallbacks.
    # Prefer an explicit list in MORTALITY_EMERGENT_MODELS (comma-separated),
    # otherwise use a single default from MORTALITY_DEFAULT_MODEL or
    # OPENROUTER_MODEL. As a last resort, use "openrouter/auto".
    raw_models = os.getenv("MORTALITY_EMERGENT_MODELS", "").strip()
    models: list[str] = []
    if raw_models:
        parts = [p.strip() for p in raw_models.split(",")]
        models = [p for p in parts if p]

    default_model = (
        os.getenv("MORTALITY_DEFAULT_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or "openrouter/auto"
    )

    cfg = experiment.config_cls(
        llm=LlmConfig(provider=LLMProvider.OPENROUTER, model=default_model),
        models=models,
        replicas_per_model=replicas,
        spread_start_minutes=spread_start,
        spread_end_minutes=spread_end,
        tick_seconds=tick_seconds,
        diary_limit=1,
    )

    result = await experiment.run(runtime, cfg)
    await runtime.shutdown()

    bundle = telemetry.build_bundle(
        diaries=result.diaries,
        metadata=result.metadata,
        experiment={"slug": experiment.slug, "description": experiment.description},
        config=cfg.model_dump(),
        llm=cfg.llm.model_dump(),
    )
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("runs", exist_ok=True)
    out = f"runs/emergent-{ts}.json"
    with open(out, "w") as f:
        json.dump(bundle, f, ensure_ascii=False)
    print("wrote", out)


if __name__ == "__main__":
    anyio.run(main)
