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
