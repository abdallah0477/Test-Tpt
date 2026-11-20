import httpx
import pytest

from app.utils import agent_loop, model_client, runner_client
from app.utils.config import get_config


def _no_network(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no network in unit tests", request=request)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch, request):
    """Every test gets its own empty data/ and exchange directories, and no Runner or model network."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EXCHANGE_DIR", str(tmp_path / "exchange"))
    monkeypatch.setattr(runner_client, "transport", None)
    if "ollama" not in request.keywords:
        monkeypatch.setenv("TPT__OLLAMA__WARMUP", "false")
        monkeypatch.setattr(model_client, "transport", httpx.MockTransport(_no_network))
        monkeypatch.setattr(model_client, "cloud_transport", httpx.MockTransport(_no_network))
    model_client.reset()
    agent_loop.clear_cache()
    get_config.cache_clear()
    yield tmp_path / "data"
    get_config.cache_clear()
