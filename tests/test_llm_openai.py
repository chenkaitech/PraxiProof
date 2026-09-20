from dataclasses import replace

import pytest

from praxiproof.llm import LLMError, OllamaClient, OpenAICompatibleClient, build_llm


def test_chat_returns_message_from_choices(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", api_key="k")
    seen = {}

    def post(path, payload):
        seen["path"], seen["payload"] = path, payload
        return {"choices": [{"message": {"role": "assistant", "content": "hi", "tool_calls": []}}]}

    monkeypatch.setattr(client, "_post", post)
    tools = [{"type": "function", "function": {"name": "f", "parameters": {}}}]
    reply = client.chat("step-2", [{"role": "user", "content": "hello"}], tools=tools)

    assert reply == {"role": "assistant", "content": "hi", "tool_calls": []}
    assert seen["path"] == "/chat/completions"
    assert seen["payload"]["tools"] == tools
    assert seen["payload"]["model"] == "step-2"


def test_chat_json_uses_json_schema_response_format_and_parses_content(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    seen = {}

    def post(path, payload):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(client, "_post", post)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    result = client.chat_json("step-2", [{"role": "user", "content": "go"}], schema)

    assert result == {"ok": True}
    fmt = seen["payload"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["schema"] == schema


def test_chat_json_raises_on_non_json_content(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    monkeypatch.setattr(client, "_post", lambda path, payload: {"choices": [{"message": {"content": "not json"}}]})
    with pytest.raises(LLMError, match="non-JSON"):
        client.chat_json("step-2", [{"role": "user", "content": "go"}], {"type": "object"})


def test_images_are_sent_as_content_parts(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    seen = {}

    def post(path, payload):
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(client, "_post", post)
    client.chat_json("vlm", [{"role": "user", "content": "describe"}], {"type": "object"}, images=[b"\x89PNG"])

    parts = seen["payload"]["messages"][-1]["content"]
    assert parts[0] == {"type": "text", "text": "describe"}
    assert parts[1]["type"] == "image_url" and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_build_llm_selects_provider_from_settings(settings):
    ollama = build_llm(settings)
    assert isinstance(ollama, OllamaClient)

    openai_settings = replace(settings, llm_provider="openai", openai_base_url="https://api.stepfun.com/v1", openai_api_key="sk-test")
    client = build_llm(openai_settings)
    assert isinstance(client, OpenAICompatibleClient)


def test_build_llm_requires_base_url_for_openai_provider(settings):
    with pytest.raises(LLMError, match="openai_base_url"):
        build_llm(replace(settings, llm_provider="openai", openai_base_url=None))


def _client_with(monkeypatch, outcomes):
    """A client whose HTTP layer plays back `outcomes` (an exception to raise, or a status code to return)."""
    import httpx

    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", attempts=3)
    monkeypatch.setattr("praxiproof.llm.time.sleep", lambda s: None)
    calls = []

    def post(path, json):
        calls.append(path)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(client._client, "post", post)
    return client, calls


def test_transient_disconnect_and_rate_limit_are_retried(monkeypatch):
    import httpx

    client, calls = _client_with(monkeypatch, [httpx.RemoteProtocolError("dropped"), 429, 200])
    assert client.chat("m", [{"role": "user", "content": "x"}])["content"] == "ok"
    assert len(calls) == 3


def test_retries_are_bounded_and_client_errors_are_not_retried(monkeypatch):
    import httpx

    client, calls = _client_with(monkeypatch, [httpx.ConnectError("down")] * 3)
    with pytest.raises(LLMError, match="after 3 attempts"):
        client.chat("m", [{"role": "user", "content": "x"}])
    assert len(calls) == 3

    client, calls = _client_with(monkeypatch, [401])
    with pytest.raises(LLMError, match="401"):
        client.chat("m", [{"role": "user", "content": "x"}])
    assert len(calls) == 1


def test_tool_results_carry_tool_call_id_and_openai_client_drops_tool_name(monkeypatch):
    from praxiproof.runtime.tool import tool_message

    call = {"id": "call_1", "function": {"name": "get_verification_report"}}
    msg = tool_message(call, "get_verification_report", {"ok": True})
    assert msg["tool_call_id"] == "call_1" and msg["tool_name"] == "get_verification_report"
    assert "tool_call_id" not in tool_message({"function": {"name": "x"}}, "x", {})  # Ollama calls have no id

    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    seen = {}

    def post(path, payload):
        seen["messages"] = payload["messages"]
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(client, "_post", post)
    client.chat("m", [{"role": "user", "content": "q"}, msg])
    assert seen["messages"][1] == {"role": "tool", "tool_call_id": "call_1", "content": msg["content"]}
