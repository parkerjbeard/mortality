from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

import anyio
from anyio import get_cancelled_exc_class

from mortality.experiments.base import LlmConfig
from mortality.experiments.registry import ExperimentRegistry
from mortality.llm.base import LLMProvider
from mortality.orchestration.runtime import MortalityRuntime
from mortality.telemetry.console import ConsoleTelemetrySink, MultiTelemetrySink
from mortality.telemetry.recorder import StructuredTelemetrySink


@dataclass
class RunOutcome:
    telemetry: MultiTelemetrySink
    experiment_slug: str
    experiment_description: str
    config: Any
    diaries: Dict[str, list[Dict[str, Any]]]
    metadata: Dict[str, Any]
    status: str


def main() -> None:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY must be set in environment")

    outcome = anyio.run(_run_emergent)
    system_prompt = _extract_system_prompt(outcome.config)
    bundle = outcome.telemetry.build_bundle(
        diaries=outcome.diaries,
        metadata=outcome.metadata,
        experiment={"slug": outcome.experiment_slug, "description": outcome.experiment_description},
        config=outcome.config.model_dump(),
        llm=outcome.config.llm.model_dump(),
        extra={"status": outcome.status},
        system_prompt=system_prompt,
    )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("runs", exist_ok=True)
    out = f"runs/emergent-{ts}.json"
    with open(out, "w") as f:
        json.dump(bundle, f, ensure_ascii=False)
    print(f"[{outcome.status}] wrote {out}")

    if outcome.status != "completed":
        raise SystemExit(130)


async def _run_emergent() -> RunOutcome:
    telemetry = MultiTelemetrySink([StructuredTelemetrySink(), ConsoleTelemetrySink()])
    runtime = MortalityRuntime(telemetry=telemetry)
    experiment = ExperimentRegistry().get("emergent-timers")

    spread_start = float(os.getenv("MORTALITY_EMERGENT_SPREAD_START", "5.0"))
    spread_end = float(os.getenv("MORTALITY_EMERGENT_SPREAD_END", "15.0"))
    tick_seconds = float(os.getenv("OPENROUTER_TICK_SECONDS", "20"))
    tick_seconds_max = float(
        os.getenv("OPENROUTER_TICK_SECONDS_MAX", str(tick_seconds))
    )
    if tick_seconds_max < tick_seconds:
        raise RuntimeError(
            "OPENROUTER_TICK_SECONDS_MAX must be greater than or equal to OPENROUTER_TICK_SECONDS"
        )

    models = _parse_unique_models(os.getenv("MORTALITY_EMERGENT_MODELS"))
    if len(models) < 4:
        raise RuntimeError(
            "MORTALITY_EMERGENT_MODELS must list at least four unique comma-separated model IDs"
        )

    replicas = int(os.getenv("MORTALITY_REPLICAS_PER_MODEL", "1"))
    if replicas != 1:
        raise RuntimeError("MORTALITY_REPLICAS_PER_MODEL must be 1 so each agent uses a different model")

    cfg = experiment.config_cls(
        llm=LlmConfig(provider=LLMProvider.OPENROUTER, model=models[0]),
        models=models,
        replicas_per_model=replicas,
        spread_start_minutes=spread_start,
        spread_end_minutes=spread_end,
        tick_seconds=tick_seconds,
        tick_seconds_max=tick_seconds_max,
        diary_limit=1,
    )

    cancel_exc = get_cancelled_exc_class()
    status = "completed"
    diaries: Dict[str, list[Dict[str, Any]]]
    metadata: Dict[str, Any]
    result = None

    routes_snapshot: Dict[str, Dict[str, Any]] = {}

    try:
        result = await experiment.run(runtime, cfg)
    except cancel_exc:
        diaries, metadata = _snapshot_interrupted(runtime, "cancelled by Ctrl+C")
        status = "interrupted"
    except KeyboardInterrupt:
        diaries, metadata = _snapshot_interrupted(runtime, "cancelled by Ctrl+C")
        status = "interrupted"
    finally:
        routes_snapshot = runtime.snapshot_agent_routes()
        await runtime.shutdown()

    if status == "completed":
        diaries = result.diaries
        metadata = dict(result.metadata)

    metadata.setdefault("status", status)
    metadata.setdefault("agent_ids", sorted(diaries.keys()))
    if routes_snapshot:
        metadata.setdefault("routed_models", routes_snapshot)

    return RunOutcome(
        telemetry=telemetry,
        experiment_slug=experiment.slug,
        experiment_description=experiment.description,
        config=cfg,
        diaries=diaries,
        metadata=metadata,
        status=status,
    )


def _parse_unique_models(raw: str | None) -> list[str]:
    if not raw:
        return []
    models: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        candidate = part.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            models.append(candidate)
    return models


def _extract_system_prompt(config: Any) -> str | None:
    for attr in ("system_prompt", "environment_prompt"):
        value = getattr(config, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _snapshot_interrupted(runtime: MortalityRuntime, reason: str) -> tuple[Dict[str, list[Dict[str, Any]]], Dict[str, Any]]:
    diaries = runtime.snapshot_diaries()
    metadata: Dict[str, Any] = {
        "status": "interrupted",
        "agent_ids": sorted(diaries.keys()),
        "interrupted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reason": reason,
    }
    routes = runtime.snapshot_agent_routes()
    if routes:
        metadata["routed_models"] = routes
    return diaries, metadata

if __name__ == "__main__":
    main()
