from __future__ import annotations

import requests


class OllamaError(Exception):
    pass


class OllamaConnectionError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        post=requests.post,
        timeout: int = 120,
    ):
        self.base_url = base_url
        self.post = post
        self.timeout = timeout

    def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        try:
            resp = self.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "images": images, "stream": False},
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            raise OllamaTimeoutError(
                f"Ollama did not respond within {self.timeout}s: {e}"
            ) from e
        except requests.RequestException as e:
            raise OllamaConnectionError(
                f"could not connect to Ollama at {self.base_url} — is it running? "
                f"try `ollama serve`. ({e})"
            ) from e

        if resp.status_code != 200:
            raise OllamaResponseError(
                f"Ollama returned HTTP {resp.status_code}: {self._error_detail(resp)}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise OllamaResponseError(f"Ollama returned a non-JSON response: {e}") from e

        if not isinstance(payload, dict) or "response" not in payload:
            raise OllamaResponseError(f"Ollama response missing 'response' field: {payload!r}")

        return payload["response"]

    @staticmethod
    def _error_detail(resp) -> str:
        try:
            payload = resp.json()
            if isinstance(payload, dict) and "error" in payload:
                return str(payload["error"])
        except ValueError:
            pass
        return getattr(resp, "text", str(resp))
