import pytest
from app.vlm import VlmSettings


@pytest.fixture(autouse=True)
def isolate_vlm_credentials(monkeypatch):
    # Tests must never read the developer's credentials or call a paid API.
    monkeypatch.setitem(VlmSettings.model_config, 'env_file', None)
    monkeypatch.delenv('QWEN_API_KEY', raising=False)
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
