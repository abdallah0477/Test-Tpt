"""Configuration: root config.toml defaults, then environment overrides.

Named overrides: DATA_DIR, EXCHANGE_DIR, LOG_LEVEL, OLLAMA_BASE_URL, RUNNER_URL, CLOUD_ENABLED.
Any other key: TPT__<SECTION>__<KEY>=<toml value>, e.g.
    TPT__INSPECTION__LOAD_TIMEOUT_MS=45000
    TPT__ASSISTANT__MAX_RETRIES=3
Secrets (e.g. GROQ_API_KEY) are read from the environment by the code that needs
them and are never part of this config.
"""

import os
import tomllib
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"

NAMED_ENV = {
    "DATA_DIR": ("storage", "data_dir"),
    "EXCHANGE_DIR": ("runner", "exchange_dir"),
    "LOG_LEVEL": ("logging", "level"),
    "OLLAMA_BASE_URL": ("ollama", "base_url"),
    "RUNNER_URL": ("runner", "url"),
    "CLOUD_ENABLED": ("cloud", "enabled"),
}
GENERIC_PREFIX = "TPT__"


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StorageConfig(Section):
    data_dir: Path = Path("data")


class LoggingConfig(Section):
    level: str = "INFO"


class OllamaConfig(Section):
    base_url: str = "http://host.docker.internal:11434"
    keep_alive: str = "30m"  # keep the model loaded between calls
    request_timeout_ms: int = 300_000
    hardware: str = ""  # shown in usage records' `setup`, e.g. "RTX 3060 Laptop 6GB" (TPT__OLLAMA__HARDWARE)
    warmup: bool = True  # health-check and warm the assistant model at startup


class RunnerConfig(Section):
    url: str = "http://runner:8100"
    job_timeout_ms: int = 120_000
    exchange_dir: Path = Path("exchange")  # shared volume: out/{job_id}/result.json + DONE (AD-19)


class InspectionConfig(Section):
    load_timeout_ms: int = 30_000


class AssistantConfig(Section):
    max_retries: int = 2


class ClarificationConfig(Section):
    threshold: float = 0.7


class MatchingConfig(Section):
    margin: float = 0.1
    threshold: float = 0.6


class ExecutionConfig(Section):
    test_timeout_ms: int = 60_000


class ModelRole(Section):
    provider: Literal["ollama", "cloud"] = "ollama"
    model: str = "qwen3:4b-instruct-2507-q4_K_M"
    think: bool = False
    num_ctx: int = 8192
    temperature: float = 0.2
    num_predict: int = 1536  # output tokens; also reserved from num_ctx by the prompt budget


class ModelsConfig(Section):
    assistant: ModelRole = ModelRole()
    codegen: ModelRole = ModelRole()


class CloudConfig(Section):
    enabled: bool = False
    provider: str = "groq"
    model: str = ""
    base_url: str = "https://api.groq.com/openai/v1"
    rpm_limit: int = 30
    tpm_limit: int = 6000


class Config(Section):
    storage: StorageConfig = StorageConfig()
    logging: LoggingConfig = LoggingConfig()
    ollama: OllamaConfig = OllamaConfig()
    runner: RunnerConfig = RunnerConfig()
    inspection: InspectionConfig = InspectionConfig()
    assistant: AssistantConfig = AssistantConfig()
    clarification: ClarificationConfig = ClarificationConfig()
    matching: MatchingConfig = MatchingConfig()
    execution: ExecutionConfig = ExecutionConfig()
    models: ModelsConfig = ModelsConfig()
    cloud: CloudConfig = CloudConfig()


def _parse_env_value(raw: str) -> Any:
    """Read an env value as a TOML literal (numbers, booleans); fall back to a plain string."""
    try:
        return tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        return raw


def _set(data: dict, keys: tuple[str, ...], value: Any) -> None:
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    data[keys[-1]] = value


def load_config(path: Path | None = None, env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    path = Path(env.get("CONFIG_PATH", path or DEFAULT_CONFIG_PATH))
    data: dict[str, Any] = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))

    for name, keys in NAMED_ENV.items():
        if env.get(name):
            value = env[name] if name in ("DATA_DIR", "EXCHANGE_DIR", "LOG_LEVEL") else _parse_env_value(env[name])
            _set(data, keys, value)
    for name, raw in env.items():
        if name.startswith(GENERIC_PREFIX):
            keys = tuple(part.lower() for part in name[len(GENERIC_PREFIX) :].split("__"))
            _set(data, keys, _parse_env_value(raw))

    config = Config.model_validate(data)
    # A relative directory from config.toml is relative to the config file;
    # one from DATA_DIR / EXCHANGE_DIR is relative to the working directory.
    config.storage.data_dir = _absolute(config.storage.data_dir, path, env.get("DATA_DIR"))
    config.runner.exchange_dir = _absolute(config.runner.exchange_dir, path, env.get("EXCHANGE_DIR"))
    return config


def _absolute(directory: Path, config_path: Path, from_env: str | None) -> Path:
    if directory.is_absolute():
        return directory
    base = Path.cwd() if from_env else config_path.parent
    return (base / directory).resolve()


@lru_cache
def get_config() -> Config:
    """Process-wide config. Tests call `get_config.cache_clear()` after changing env."""
    return load_config()
