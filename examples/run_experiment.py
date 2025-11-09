#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mortality import ExperimentRegistry, MortalityRuntime
from mortality.experiments.base import LlmConfig
from mortality.telemetry.recorder import StructuredTelemetrySink


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mortality experiments")
    parser.add_argument("--experiment", required=True, help="Experiment slug (countdown-self, staggered-deaths, respawn-diaries)")
    parser.add_argument(
        "--llm-provider",
        required=True,
        help="LLM provider (openai, anthropic, grok, gemini, openrouter)",
    )
    parser.add_argument("--llm-model", required=True, help="Model name for the provider")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--config", type=str, default="{}", help="JSON with experiment-specific overrides")
    parser.add_argument("--ui-export", type=Path, help="Write a structured telemetry bundle for the GUI to this path")
    parser.add_argument("--ui-export-pretty", action="store_true", help="Pretty-print the exported bundle JSON")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    registry = ExperimentRegistry()
    experiment = registry.get(args.experiment)
    telemetry = StructuredTelemetrySink()
    runtime = MortalityRuntime(telemetry=telemetry)
    base_llm = LlmConfig(
        provider=args.llm_provider,
        model=args.llm_model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
    )
    extra = json.loads(args.config)
    extra["llm"] = base_llm
    config = experiment.config_cls(**extra)
    result = await experiment.run(runtime, config)
    payload = result.model_dump()
    print(json.dumps(payload, indent=2))
    if args.ui_export:
        export = _build_ui_export(
            telemetry,
            diaries=payload["diaries"],
            metadata=payload["metadata"],
            experiment={"slug": experiment.slug, "description": getattr(experiment, "description", "")},
            config=config.model_dump(),
            llm=base_llm.model_dump(),
            cli_args=_stringify_cli_args(args),
        )
        args.ui_export.parent.mkdir(parents=True, exist_ok=True)
        args.ui_export.write_text(json.dumps(export, indent=2 if args.ui_export_pretty else None))
        print(f"[ui-export] wrote {args.ui_export}")


def _build_ui_export(
    telemetry: StructuredTelemetrySink,
    *,
    diaries: dict,
    metadata: dict,
    experiment: dict,
    config: dict,
    llm: dict,
    cli_args: dict,
) -> dict:
    bundle = telemetry.build_bundle(
        diaries=diaries,
        metadata=metadata,
        experiment=experiment,
        config=config,
        llm=llm,
        extra={"cli_args": cli_args},
    )
    return bundle


def _stringify_cli_args(args: argparse.Namespace) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in vars(args).items():
        if isinstance(value, Path):
            output[key] = str(value)
        else:
            output[key] = value
    return output


if __name__ == "__main__":
    asyncio.run(main())
