import base64
import json
from typing import Any, Protocol

import httpx

Message = dict[str, Any]


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def chat_json(
        self, model: str, messages: list[Message], schema: dict[str, Any], images: list[bytes] | None = None
    ) -> dict[str, Any]: ...

    def chat(self, model: str, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> Message: ...


class OllamaClient:
    def __init__(self, base_url: str, keep_alive: str = "5m", timeout: float = 900.0, num_ctx: int = 32768):
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._keep_alive = keep_alive
        self._options = {"temperature": 0, "num_ctx": num_ctx}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request to {path} failed: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"Ollama {path} returned {response.status_code}: {response.text[:500]}")
        return response.json()

    def chat_json(
        self, model: str, messages: list[Message], schema: dict[str, Any], images: list[bytes] | None = None
    ) -> dict[str, Any]:
        messages = [dict(m) for m in messages]
        if images:
            messages[-1]["images"] = [base64.b64encode(img).decode() for img in images]
        data = self._post(
            "/api/chat",
            {
                "model": model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "keep_alive": self._keep_alive,
                "options": self._options,
            },
        )
        content = data.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model {model} returned non-JSON output: {content[:500]}") from exc

    def chat(self, model: str, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> Message:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": self._options,
        }
        if tools:
            payload["tools"] = tools
        return self._post("/api/chat", payload)["message"]


    def ping(self) -> list[str]:
        try:
            response = self._client.get("/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable: {exc}") from exc
        return [m["name"] for m in response.json().get("models", [])]
