"""Runner settings, read once from environment variables.

| Variable          | Default      | Meaning                                         |
| ----------------- | ------------ | ----------------------------------------------- |
| EXCHANGE_DIR      | ./exchange   | Shared volume; results go to out/{job_id}/      |
| RUNNER_HEADLESS   | false        | true for tests/CI; the container runs headed    |
| JOB_TIMEOUT_MS    | 120000       | Hard limit for one whole job                    |
| RUNNER_MAX_CROPS  | 300          | Crops taken per inspection (the rest get none)  |
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    exchange_dir: Path
    headless: bool
    job_timeout_ms: int
    max_crops: int
    viewport_width: int = 1280
    viewport_height: int = 800


def load_settings() -> Settings:
    return Settings(
        exchange_dir=Path(os.environ.get("EXCHANGE_DIR", "./exchange")),
        headless=_bool(os.environ.get("RUNNER_HEADLESS"), default=False),
        job_timeout_ms=int(os.environ.get("JOB_TIMEOUT_MS", "120000")),
        max_crops=int(os.environ.get("RUNNER_MAX_CROPS", "300")),
    )
