import base64
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from praxiproof.config import Settings

Message = dict[str, Any]
log = logging.getLogger(__name__)


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

    # Cloud endpoints drop connections and rate-limit; a manual compile is minutes of work, so retry those.
    # Responses are streamed and `timeout` is the longest silence tolerated between two chunks, not the length of the
    # whole answer: a healthy generation streams steadily (measured: 5300 chunks in 111 s, largest gap 0.3 s) while a
    # stalled request has been seen to hang for 15 minutes on a call that normally takes two. A stall is retried
    # once; a merely slow generation never trips the timeout.
    _RETRY_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ConnectTimeout)
    _RETRY_STATUS = (429, 500, 502, 503, 504)
    _STALL_RETRIES = 1

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 60.0, attempts: int = 3, stream: bool = True, max_seconds: float = 480.0):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._stream = stream
        self._stall = timeout  # longest streaming silence, keep-alive comments not counted
        self._max_seconds = max_seconds  # ceiling for one streamed answer; the longest healthy compile seen took 209 s
        # Without streaming the timeout has to cover the whole answer, so it cannot be the short silence limit.
        read = timeout if stream else max(timeout, 300.0)
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(connect=10.0, read=read, write=60.0, pool=10.0), headers=headers)
        self._attempts = attempts

    def _send(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        """One request: (status, parsed body) — for a streamed 200, the body is rebuilt into the non-streamed shape."""
        if not self._stream:
            response = self._client.post(path, json=payload)
            return response.status_code, response.json() if response.status_code == 200 else response.text
        with self._client.stream("POST", path, json=payload | {"stream": True}) as response:
            if response.status_code != 200:
                return response.status_code, response.read().decode("utf-8", "replace")
            content, calls, reasoning, finish = [], {}, 0, None
            started = last_progress = time.monotonic()
            for line in response.iter_lines():
                now = time.monotonic()
                # httpx's read timeout restarts on any byte, and a stalled generation can keep the connection alive
                # with ": keep-alive" comments, so silence is measured from the last event that carried something.
                if now - started > self._max_seconds:
                    # Content keeps arriving, so this is not a stall but a generation that will not finish (a reasoning
                    # loop). At temperature 0 asking again repeats it, so it is reported instead of retried.
                    raise LLMError(f"response still streaming after {now - started:.0f}s; giving up (limit {self._max_seconds:.0f}s)")
                if now - last_progress > self._stall:
                    raise httpx.ReadTimeout(f"no content for {now - last_progress:.0f}s")
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue  # blank separators and comments
                for choice in json.loads(line[5:]).get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls") or choice.get("finish_reason"):
                        last_progress = now
                    finish = choice.get("finish_reason") or finish
                    reasoning += len(delta.get("reasoning_content") or "")
                    content.append(delta.get("content") or "")  # reasoning_content is the model thinking aloud, not the answer
                    for piece in delta.get("tool_calls") or []:
                        call = calls.setdefault(piece.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] = piece.get("id") or call["id"]
                        function = piece.get("function") or {}
                        call["function"]["name"] += function.get("name") or ""
                        call["function"]["arguments"] += function.get("arguments") or ""
            message: dict[str, Any] = {"role": "assistant", "content": "".join(content)}
            if calls:
                message["tool_calls"] = [calls[i] for i in sorted(calls)]
            return 200, {"choices": [{"message": message, "finish_reason": finish}], "reasoning_chars": reasoning}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        stalls = 0
        for attempt in range(1, self._attempts + 1):
            last = attempt == self._attempts
            try:
                status, body = self._send(path, payload)
            except self._RETRY_ERRORS as exc:
                if last:
                    raise LLMError(f"OpenAI-compatible request to {path} failed after {attempt} attempts: {exc}") from exc
            except httpx.ReadTimeout as exc:
                stalls += 1
                if last or stalls > self._STALL_RETRIES:
                    raise LLMError(f"OpenAI-compatible request to {path} stalled {stalls} time(s): {exc}") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"OpenAI-compatible request to {path} failed: {exc}") from exc
            else:
                if status == 200:
                    return body  # type: ignore[return-value]
                if status not in self._RETRY_STATUS or last:
                    raise LLMError(f"{path} returned {status}: {str(body)[:500]}")
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    _NUDGE = {"role": "user", "content": "Your reply had no answer text. Write your final answer now."}

    def _message(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """The assistant message. Some hosted reasoning models occasionally finish a turn having written their answer
        only into the reasoning channel, leaving the answer text empty. At temperature 0 sending the identical request
        again tends to repeat that, so the retries add a short instruction to answer, and give up after two."""
        for attempt in (1, 2, 3):
            body = payload if attempt == 1 else payload | {"messages": payload["messages"] + [self._NUDGE]}
            data = self._post(path, body)
            message = data["choices"][0]["message"]
            if (message.get("content") or "").strip() or message.get("tool_calls"):
                return message
            log.warning(
                "empty reply from %s (attempt %d): finish_reason=%s reasoning_chars=%s messages=%d last_role=%s",
                payload["model"], attempt, data["choices"][0].get("finish_reason"), data.get("reasoning_chars"),
                len(payload["messages"]), payload["messages"][-1].get("role"),
            )
        raise LLMError(f"model {payload['model']} returned an empty answer {attempt} times")

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
        content = self._message("/chat/completions", payload).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model {model} returned non-JSON output: {content[:500]}") from exc

    def chat(self, model: str, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> Message:
        # `tool_name` is Ollama's field for a tool result; strict OpenAI-style servers want only tool_call_id.
        messages = [{k: v for k, v in m.items() if k != "tool_name"} for m in messages]
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
        return self._message("/chat/completions", payload)


def build_llm(settings: "Settings") -> LLM:
    if settings.llm_provider == "openai":
        if not settings.openai_base_url:
            raise LLMError("openai_base_url must be set when PRAXIPROOF_LLM_PROVIDER=openai")
        return OpenAICompatibleClient(settings.openai_base_url, settings.openai_api_key, timeout=settings.openai_timeout, stream=settings.openai_stream)
    return OllamaClient(settings.ollama_url, settings.keep_alive)


def build_vlm(settings: "Settings", llm: LLM) -> LLM:
    """The client that sees video frames. With PRAXIPROOF_VLM_PROVIDER=ollama the frames stay on the local Ollama
    even when the text model is a cloud service, so only procedure text ever leaves the machine."""
    if settings.vlm_provider == "ollama" and settings.llm_provider != "ollama":
        return OllamaClient(settings.ollama_url, settings.keep_alive)
    return llm
