from types import SimpleNamespace

import pytest
from google import genai

from backend.providers import GeminiProvider, ProviderUnavailable


class APIError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("sensitive-provider-request-details")


def setup_fake(monkeypatch, responses):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-secret-not-a-real-key")
    monkeypatch.setattr("backend.providers.offline", lambda: False)
    monkeypatch.setattr("backend.providers.time.sleep", lambda _: None)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return SimpleNamespace(text=value)

    monkeypatch.setattr(genai, "Client", Client)
    return calls


@pytest.mark.parametrize("status", [401, 403])
def test_provider_auth_not_retried_or_leaked(monkeypatch, status):
    calls = setup_fake(monkeypatch, [APIError(status)])
    with pytest.raises(ProviderUnavailable) as error:
        GeminiProvider().extract({f"auth-{status}": "Не переходите по ссылке."})
    assert len(calls) == 1
    assert "fake-secret" not in str(error.value) and "sensitive" not in str(error.value)


def test_provider_temporary_retry_structured_result_and_cache(monkeypatch):
    body = '{"language":"ru","context":"warning","claims":[],"contradictions":[],"limitations":[]}'
    calls = setup_fake(monkeypatch, [APIError(503), body])
    first = GeminiProvider().extract({"retry-and-cache": "Осторожно."}, [b"test-png-bytes"])
    second = GeminiProvider().extract({"retry-and-cache": "Осторожно."}, [b"test-png-bytes"])
    assert len(calls) == 2
    assert first == second and first.context == "warning"
    assert len(calls[0]["contents"]) == 2
    assert calls[0]["config"].response_mime_type == "application/json"


def test_provider_invalid_schema_fails_closed(monkeypatch):
    calls = setup_fake(monkeypatch, ['{"crime_probability":1}'])
    with pytest.raises(ProviderUnavailable):
        GeminiProvider().extract({"invalid-schema": "Учебный пример."})
    assert len(calls) == 1
