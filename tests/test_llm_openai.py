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

    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", attempts=3, stream=False)
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


def test_a_stalled_request_is_retried_once_and_then_gives_up(monkeypatch):
    import httpx

    client, calls = _client_with(monkeypatch, [httpx.ReadTimeout("stalled"), 200])
    assert client.chat("m", [{"role": "user", "content": "x"}])["content"] == "ok" and len(calls) == 2

    client, calls = _client_with(monkeypatch, [httpx.ReadTimeout("stalled")] * 3)
    with pytest.raises(LLMError, match="stalled 2 time"):
        client.chat("m", [{"role": "user", "content": "x"}])
    assert len(calls) == 2  # one retry, not three waits


def test_openai_timeout_comes_from_settings(settings):
    from dataclasses import replace

    client = build_llm(replace(settings, llm_provider="openai", openai_base_url="http://x/v1", openai_timeout=42.0))
    assert client._client.timeout.read == 42.0  # streaming: the longest silence between chunks
    whole = build_llm(replace(settings, llm_provider="openai", openai_base_url="http://x/v1", openai_timeout=42.0, openai_stream=False))
    assert whole._client.timeout.read == 300.0  # not streaming: must cover the whole answer


def _sse(*events):
    import json

    return "".join(f"data: {json.dumps(e)}\n\n" if isinstance(e, dict) else f"{e}\n\n" for e in events)


def _streaming_client(handler):
    import httpx

    client = OpenAICompatibleClient("http://api.test/v1", api_key="k", attempts=3)
    client._client = httpx.Client(base_url="http://api.test/v1", transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer k"})
    return client


def test_streamed_answer_is_reassembled_and_reasoning_is_ignored():
    import httpx

    seen = {}

    def handler(request):
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=_sse(
            {"choices": [{"delta": {"role": "assistant", "reasoning_content": "thinking..."}}]},
            ": keep-alive",
            {"choices": [{"delta": {"content": '{"a": '}}]},
            {"choices": [{"delta": {"content": "1}"}}]},
            {"choices": []},
            "data: [DONE]",
        ), headers={"content-type": "text/event-stream"})

    client = _streaming_client(handler)
    assert client.chat_json("m", [{"role": "user", "content": "x"}], {"type": "object"}) == {"a": 1}
    assert seen["body"]["stream"] is True and seen["body"]["response_format"]["type"] == "json_schema"


def test_streamed_tool_calls_are_assembled_from_fragments():
    import httpx

    def handler(request):
        return httpx.Response(200, text=_sse(
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "get_report", "arguments": '{"run'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '_id": "V-1"}'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "call_2", "function": {"name": "other", "arguments": "{}"}}]}}]},
            "data: [DONE]",
        ))

    reply = _streaming_client(handler).chat("m", [{"role": "user", "content": "x"}], tools=[{"type": "function", "function": {"name": "get_report", "parameters": {}}}])
    assert [(c["id"], c["function"]["name"], c["function"]["arguments"]) for c in reply["tool_calls"]] == [
        ("call_1", "get_report", '{"run_id": "V-1"}'), ("call_2", "other", "{}")]


def test_streamed_errors_and_stalls_follow_the_same_retry_rules(monkeypatch):
    import httpx

    monkeypatch.setattr("praxiproof.llm.time.sleep", lambda s: None)
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, text="slow down")
        if len(calls) == 2:
            raise httpx.ReadTimeout("no data for 60 s")
        return httpx.Response(200, text=_sse({"choices": [{"delta": {"content": "ok"}}]}, "data: [DONE]"))

    assert _streaming_client(flaky).chat("m", [{"role": "user", "content": "x"}])["content"] == "ok" and len(calls) == 3

    def denied(request):
        return httpx.Response(401, text="bad key")

    with pytest.raises(LLMError, match="401.*bad key"):
        _streaming_client(denied).chat("m", [{"role": "user", "content": "x"}])


def test_an_empty_reply_is_requested_once_more_and_then_reported(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    sent = []
    replies = iter([{"content": ""}, {"content": "  "}, {"content": "the answer"}])

    def post(path, payload):
        sent.append(payload["messages"])
        return {"choices": [{"message": next(replies)}]}

    monkeypatch.setattr(client, "_post", post)
    assert client.chat("m", [{"role": "user", "content": "x"}])["content"] == "the answer"
    assert len(sent) == 3 and len(sent[0]) == 1 and sent[1][-1] == sent[2][-1] == OpenAICompatibleClient._NUDGE  # asked to answer on retries

    monkeypatch.setattr(client, "_post", lambda path, payload: {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(LLMError, match="empty answer 3 times"):
        client.chat("m", [{"role": "user", "content": "x"}])


def test_a_reply_that_is_only_tool_calls_is_not_empty(monkeypatch):
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1")
    calls = []

    def post(path, payload):
        calls.append(1)
        return {"choices": [{"message": {"content": "", "tool_calls": [{"id": "c", "function": {"name": "f", "arguments": "{}"}}]}}]}

    monkeypatch.setattr(client, "_post", post)
    assert client.chat("m", [{"role": "user", "content": "x"}])["tool_calls"] and len(calls) == 1


def test_keep_alive_comments_do_not_hide_a_stalled_stream(monkeypatch):
    import httpx

    monkeypatch.setattr("praxiproof.llm.time.sleep", lambda s: None)
    clock = iter(range(0, 10_000, 20))  # every look at the clock is 20 s later
    monkeypatch.setattr("praxiproof.llm.time.monotonic", lambda: next(clock))

    def handler(request):
        return httpx.Response(200, content=b": keep-alive\n\n" * 50, headers={"content-type": "text/event-stream"})

    client = _streaming_client(handler)
    with pytest.raises(LLMError, match="stalled 2 time.*no content for"):
        client.chat("m", [{"role": "user", "content": "x"}])


def test_a_stream_that_keeps_producing_content_is_not_cut_off(monkeypatch):
    import httpx

    clock = iter(range(0, 10_000, 10))  # 10 s per line: slow, but every line is real content
    monkeypatch.setattr("praxiproof.llm.time.monotonic", lambda: next(clock))
    events = [{"choices": [{"delta": {"reasoning_content": "thinking"}}]}] * 20 + [{"choices": [{"delta": {"content": "done"}}]}, "data: [DONE]"]
    client = _streaming_client(lambda request: httpx.Response(200, text=_sse(*events)))
    assert client.chat("m", [{"role": "user", "content": "x"}])["content"] == "done"


def test_a_generation_that_never_finishes_is_reported_not_retried(monkeypatch):
    import httpx

    clock = iter(range(0, 100_000, 10))  # content arrives every 10 s, so there is never a stall
    monkeypatch.setattr("praxiproof.llm.time.monotonic", lambda: next(clock))
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text=_sse(*[{"choices": [{"delta": {"reasoning_content": "still thinking"}}]}] * 200))

    client = _streaming_client(handler)
    with pytest.raises(LLMError, match="still streaming after"):
        client.chat("m", [{"role": "user", "content": "x"}])
    assert len(calls) == 1
