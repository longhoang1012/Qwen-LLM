import pytest

from qwen_test_automation.llm.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_generate_returns_response_text():
    def fake_post(url, json, timeout):
        assert url == "http://localhost:11434/api/generate"
        assert json["model"] == "qwen2.5:7b"
        assert json["prompt"] == "hello"
        return FakeResponse(200, {"response": "hi there"})

    client = OllamaClient(post=fake_post)
    assert client.generate(model="qwen2.5:7b", prompt="hello") == "hi there"


def test_generate_raises_connection_error_when_post_raises():
    import requests

    def fake_post(url, json, timeout):
        raise requests.ConnectionError("refused")

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaConnectionError):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_raises_response_error_on_non_200():
    def fake_post(url, json, timeout):
        return FakeResponse(500, {"error": "boom"})

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaResponseError):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_raises_timeout_error_when_post_times_out():
    import requests

    def fake_post(url, json, timeout):
        raise requests.Timeout("timed out")

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaTimeoutError):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_connection_error_message_has_actionable_hint():
    import requests

    def fake_post(url, json, timeout):
        raise requests.ConnectionError("refused")

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaConnectionError, match="ollama serve"):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_response_error_includes_body_error_detail():
    def fake_post(url, json, timeout):
        return FakeResponse(404, {"error": "model 'x' not found, try pulling it first"})

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaResponseError, match="not found"):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_raises_response_error_on_missing_response_field():
    def fake_post(url, json, timeout):
        return FakeResponse(200, {"not_response": "oops"})

    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaResponseError):
        client.generate(model="qwen2.5:7b", prompt="hello")


def test_generate_custom_timeout_is_passed_to_post():
    captured = {}

    def fake_post(url, json, timeout):
        captured["timeout"] = timeout
        return FakeResponse(200, {"response": "ok"})

    client = OllamaClient(post=fake_post, timeout=30)
    client.generate(model="qwen2.5:7b", prompt="hello")
    assert captured["timeout"] == 30
