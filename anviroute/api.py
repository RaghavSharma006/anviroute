"""OpenAI-compatible upstream adapter and Anthropic response events."""

import json
import math
import urllib.error
import urllib.parse
import urllib.request
import uuid

from kagglelink.common import BridgeError, MAX_BODY, NoRedirect


def normalize_url(value):
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme not in ("https", "http") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise BridgeError("Enter an HTTP(S) API URL without credentials or query parameters")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise BridgeError("Public endpoints must use HTTPS; HTTP is allowed only for localhost")
    for suffix in ("/chat/completions", "/messages"):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
            break
    return value if value.endswith("/v1") else value + "/v1"


class UpstreamError(BridgeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if any(not isinstance(b, dict) or b.get("type") != "text" for b in value):
            raise BridgeError("This OpenAI adapter supports text tool results and text system prompts only")
        return "\n".join(b.get("text", "") for b in value)
    raise BridgeError("Expected text or text blocks")


def openai_payload(payload, model):
    messages = []
    if payload.get("system"):
        messages.append({"role": "system", "content": text_content(payload["system"])})
    for message in payload.get("messages", []):
        role = message["role"]
        if role not in ("user", "assistant"):
            raise BridgeError("Unsupported conversation role")
        blocks = message["content"]
        if isinstance(blocks, str):
            messages.append({"role": role, "content": blocks})
            continue
        parts, calls, results = [], [], []
        for block in blocks:
            kind = block.get("type")
            if kind == "text":
                parts.append({"type": "text", "text": block["text"]})
            elif kind == "image":
                source = block["source"]
                if source["type"] == "base64":
                    url = f"data:{source['media_type']};base64,{source['data']}"
                elif source["type"] == "url":
                    url = source["url"]
                else:
                    raise BridgeError("Unsupported image source")
                parts.append({"type": "image_url", "image_url": {"url": url}})
            elif kind == "tool_use" and role == "assistant":
                calls.append({"id": block["id"], "type": "function", "function": {
                    "name": block["name"], "arguments": json.dumps(block["input"])}})
            elif kind == "tool_result" and role == "user":
                results.append({"role": "tool", "tool_call_id": block["tool_use_id"],
                                "content": text_content(block.get("content", ""))})
            elif kind in ("thinking", "redacted_thinking") and role == "assistant":
                # Provider-specific thinking signatures cannot be replayed to Chat Completions.
                continue
            else:
                raise BridgeError(f"Unsupported content block: {kind}; use --api-format anthropic if supported")
        messages.extend(results)
        if parts or calls:
            content = parts
            if all(p["type"] == "text" for p in parts):
                content = "\n".join(p["text"] for p in parts) or None
            item = {"role": role, "content": content}
            if calls:
                item["tool_calls"] = calls
            messages.append(item)
    result = {"model": model, "messages": messages, "stream": False,
              "max_tokens": payload.get("max_tokens", 4096)}
    for key in ("temperature", "top_p"):
        if key in payload:
            result[key] = payload[key]
    if "stop_sequences" in payload:
        result["stop"] = payload["stop_sequences"]
    tools = payload.get("tools", [])
    if tools:
        if any("input_schema" not in t or "name" not in t for t in tools):
            raise BridgeError("Hosted/provider tools are not supported; use client-side tools")
        result["tools"] = [{"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t["input_schema"]}} for t in tools]
    choice = payload.get("tool_choice", {})
    if choice:
        kind = choice.get("type")
        if kind == "tool":
            result["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
        elif kind in ("auto", "any", "none"):
            result["tool_choice"] = {"any": "required"}.get(kind, kind)
        else:
            raise BridgeError("Unsupported tool choice")
        if choice.get("disable_parallel_tool_use"):
            result["parallel_tool_calls"] = False
    return result


def anthropic_response(response, model):
    try:
        choice = response["choices"][0]
        message = choice["message"]
        content = []
        if message.get("content"):
            if not isinstance(message["content"], str):
                raise ValueError("Expected text output")
            content.append({"type": "text", "text": message["content"]})
        for call in message.get("tool_calls", []):
            arguments = json.loads(call["function"]["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError("Tool input must be an object")
            content.append({"type": "tool_use", "id": call["id"],
                            "name": call["function"]["name"], "input": arguments})
        if message.get("refusal") and not content:
            content.append({"type": "text", "text": message["refusal"]})
        usage = response.get("usage", {})
        reason = choice.get("finish_reason")
        return {"id": response.get("id") or "msg_" + uuid.uuid4().hex,
                "type": "message", "role": "assistant", "model": model, "content": content,
                "stop_reason": "max_tokens" if reason == "length" else (
                    "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"),
                "stop_sequence": None, "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                                                    "output_tokens": usage.get("completion_tokens", 0)}}
    except (KeyError, IndexError, TypeError, ValueError):
        raise BridgeError("Upstream returned an invalid completion or malformed tool arguments") from None


def events(message):
    def emit(kind, data):
        return f"event: {kind}\ndata: {json.dumps({'type': kind, **data}, ensure_ascii=True)}\n\n".encode()

    usage = message.get("usage", {})
    yield emit("message_start", {"message": {**message, "content": [], "stop_reason": None,
                                              "stop_sequence": None,
                                              "usage": {**usage, "output_tokens": 0}}})
    for index, block in enumerate(message["content"]):
        kind = block["type"]
        start = dict(block)
        delta_type, key, value = None, None, ""
        if kind == "text":
            start["text"] = ""
            delta_type, key, value = "text_delta", "text", block["text"]
        elif kind == "tool_use":
            start["input"] = {}
            delta_type, key, value = "input_json_delta", "partial_json", json.dumps(block["input"])
        elif kind == "thinking":
            start["thinking"] = ""
            start.pop("signature", None)
            delta_type, key, value = "thinking_delta", "thinking", block["thinking"]
        yield emit("content_block_start", {"index": index, "content_block": start})
        for offset in range(0, len(value), 256):
            yield emit("content_block_delta", {"index": index,
                                                "delta": {"type": delta_type, key: value[offset:offset + 256]}})
        if kind == "thinking" and block.get("signature"):
            yield emit("content_block_delta", {"index": index,
                                                "delta": {"type": "signature_delta", "signature": block["signature"]}})
        yield emit("content_block_stop", {"index": index})
    yield emit("message_delta", {"delta": {"stop_reason": message.get("stop_reason", "end_turn"),
                                            "stop_sequence": message.get("stop_sequence")},
                                  "usage": {"output_tokens": usage.get("output_tokens", 0)}})
    yield emit("message_stop", {})


class API:
    def __init__(self, url, key, model, api_format="openai", timeout=110):
        self.url, self.key, self.model = normalize_url(url), key, model
        self.format, self.timeout = api_format, timeout
        if not key.isascii() or any(c in key for c in "\r\n"):
            raise BridgeError("API key must be ASCII without line breaks")

    def call(self, path, payload=None):
        headers = {"Accept": "application/json", "User-Agent": "AnviRoute/0.2",
                   "anthropic-version": "2023-06-01"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY:
                    raise BridgeError("Upstream response exceeds 16 MiB")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise UpstreamError(code, f"Upstream HTTP {code}; check URL, API key, model, or tunnel") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BridgeError("Upstream connection failed or timed out; check your Kaggle session") from None
        except ValueError:
            raise BridgeError("Endpoint did not return JSON; check the API URL and tunnel") from None

    def complete(self, payload):
        if self.format == "anthropic":
            result = self.call("/messages", {**payload, "model": self.model, "stream": False})
            if not isinstance(result, dict) or not isinstance(result.get("content"), list):
                raise BridgeError("Upstream did not return an Anthropic message")
            return {**result, "model": self.model}
        return anthropic_response(self.call("/chat/completions", openai_payload(payload, self.model)), self.model)

    def count_tokens(self, payload):
        if self.format == "anthropic":
            return self.call("/messages/count_tokens", {**payload, "model": self.model})
        # This is a context-size heuristic, never a billing/tokenizer count.
        return {"input_tokens": max(1, math.ceil(len(json.dumps(payload, ensure_ascii=False).encode()) / 4))}
