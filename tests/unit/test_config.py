import pytest

from app.config import Settings


@pytest.mark.unit
def test_settings_use_defaults_when_environment_is_empty(monkeypatch):
    for name in (
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key is None
    assert settings.gemini_model == "gemini-2.5-flash"


@pytest.mark.unit
def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key == "test-key"
    assert settings.gemini_model == "test-model"


@pytest.mark.unit
def test_missing_key_disables_gemini_client(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm.settings, "gemini_api_key", None)
    assert llm._get_genai_client() is None
