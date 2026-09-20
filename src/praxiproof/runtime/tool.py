import json
from typing import Any

STRING = {"type": "string"}


def tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def tool_message(call: dict[str, Any], name: str, result: Any) -> dict[str, Any]:
    """The tool-result message for one tool call. Carries `tool_call_id` (required by the OpenAI protocol)
    alongside `tool_name` (Ollama's field); providers that use one ignore the other."""
    message = {"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)[:12000]}
    if call.get("id"):
        message["tool_call_id"] = call["id"]
    return message
