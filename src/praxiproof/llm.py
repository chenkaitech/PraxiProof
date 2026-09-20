import base64
import json
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from praxiproof.config import Settings

Message = dict[str, Any]


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def chat_json(
        self,
        model: str,
        messages: list[Message],
        schema: dict[str, Any],
        images: list[bytes] | None = None,
        think: bool | None = None,
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
        self,
        model: str,
        messages: list[Message],
        schema: dict[str, Any],
        images: list[bytes] | None = None,
        think: bool | None = None,
    ) -> dict[str, Any]:
        messages = [dict(m) for m in messages]
        if images:
            messages[-1]["images"] = [base64.b64encode(img).decode() for img in images]
        payload = {
            "model": model,
            "messages": messages,
            "format": schema,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": self._options,
        }
        if think is not None:
            payload["think"] = think
        data = self._post("/api/chat", payload)
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


    def models(self) -> list[dict[str, Any]]:
        catalog = []
        for name in self.ping():
            try:
                info = self._post("/api/show", {"model": name})
            except LLMError:
                continue
            details = info.get("details", {})
            catalog.append(
                {
                    "name": name,
                    "capabilities": info.get("capabilities", []),
                    "parameter_size": details.get("parameter_size"),
                    "quantization": details.get("quantization_level"),
                    "family": details.get("family"),
                }
            )
        return catalog

    def ping(self) -> list[str]:
        try:
            response = self._client.get("/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable: {exc}") from exc
        return [m["name"] for m in response.json().get("models", [])]


def _with_images(messages: list[Message], images: list[bytes] | None) -> list[Message]:
    if not images:
        return messages
    messages = [dict(m) for m in messages]
    last = dict(messages[-1])
    parts = [{"type": "text", "text": last.get("content", "")}]
    parts += [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(img).decode()}"}}
        for img in images
    ]
    last["content"] = parts
    messages[-1] = last
    return messages


class OpenAICompatibleClient:
    """Any server that speaks the OpenAI /v1/chat/completions API: a cloud provider (e.g. StepFun's
    platform.stepfun.com) or a local server (vLLM, llama.cpp, etc.) — same client, different
    base_url/api_key. api_key is optional since most local servers don't check one.

    `think` (Ollama's thinking-mode toggle) has no standard OpenAI equivalent and is ignored here.
    """

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 900.0):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI-compatible request to {path} failed: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"{path} returned {response.status_code}: {response.text[:500]}")
        return response.json()

    def chat_json(
        self,
        model: str,
        messages: list[Message],
        schema: dict[str, Any],
        images: list[bytes] | None = None,
        think: bool | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": _with_images(messages, images),
            "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "response", "schema": schema, "strict": True}},
        }
        data = self._post("/chat/completions", payload)
        content = data["choices"][0]["message"].get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model {model} returned non-JSON output: {content[:500]}") from exc

    def chat(self, model: str, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> Message:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
        return self._post("/chat/completions", payload)["choices"][0]["message"]


def build_llm(settings: "Settings") -> LLM:
    if settings.llm_provider == "openai":
        if not settings.openai_base_url:
            raise LLMError("openai_base_url must be set when PRAXIPROOF_LLM_PROVIDER=openai")
        return OpenAICompatibleClient(settings.openai_base_url, settings.openai_api_key)
    return OllamaClient(settings.ollama_url, settings.keep_alive)
