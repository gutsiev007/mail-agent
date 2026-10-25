"""Провайдеры моделей без внешних зависимостей (urllib).

Нейтральный формат сообщений:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "results": [{"id", "content": str}]}
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""
    stop_reason: str = ""
    duration_s: float = 0.0


class LLMError(Exception):
    pass


def _post(url: str, headers: dict, body: dict, timeout: int = 120, attempts: int = 4) -> dict:
    data = json.dumps(body).encode()
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and i < attempts - 1:
                time.sleep((2 ** i) * (0.5 + random.random()))
                continue
            raise LLMError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if i < attempts - 1:
                time.sleep((2 ** i) * (0.5 + random.random()))
                continue
            raise LLMError(str(e)) from None
    raise LLMError("unreachable")


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int = 1024, temperature=None, **_):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self.url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com") + "/v1/messages"
        if not self.key:
            raise LLMError("ANTHROPIC_API_KEY не задан")

    def complete(self, system: str, messages: list, tools: list | None = None, force_tool: str | None = None) -> LLMResponse:
        msgs = []
        for m in messages:
            if m["role"] == "user":
                msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in m.get("tool_calls", [])]
                msgs.append({"role": "assistant", "content": blocks})
            else:
                msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]} for r in m["results"]]})
        body = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": msgs}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
        if force_tool:
            body["tool_choice"] = {"type": "tool", "name": force_tool}
        t0 = time.time()
        r = _post(self.url, {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, body)
        text = "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")
        calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in r["content"] if b["type"] == "tool_use"]
        u = r.get("usage", {})
        return LLMResponse(text, calls, {"input": u.get("input_tokens"), "output": u.get("output_tokens")},
                           r.get("model", self.model), r.get("stop_reason", ""), round(time.time() - t0, 2))


class OpenAICompatLLM:
    """OpenAI, OpenRouter, Ollama (http://localhost:11434/v1), vLLM и т.п."""

    def __init__(self, model: str, max_tokens: int = 1024, temperature=None, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY", **_):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.key = os.environ.get(api_key_env, "ollama")
        if "openrouter" in self.base and not os.environ.get(api_key_env):
            raise LLMError(f"{api_key_env} не задан")

    def complete(self, system: str, messages: list, tools: list | None = None, force_tool: str | None = None) -> LLMResponse:
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                mm = {"role": "assistant", "content": m.get("text") or None}
                if m.get("tool_calls"):
                    mm["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in m["tool_calls"]]
                msgs.append(mm)
            else:
                msgs += [{"role": "tool", "tool_call_id": r["id"], "content": r["content"]} for r in m["results"]]
        body = {"model": self.model, "max_tokens": self.max_tokens, "messages": msgs}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if force_tool:
            body["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
        t0 = time.time()
        r = _post(self.base + "/chat/completions", {"authorization": f"Bearer {self.key}"}, body)
        msg = r["choices"][0]["message"]
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed": c["function"].get("arguments")}
            calls.append({"id": c.get("id") or f"tc{i}", "name": c["function"]["name"], "args": args})
        u = r.get("usage") or {}
        return LLMResponse(msg.get("content") or "", calls, {"input": u.get("prompt_tokens"), "output": u.get("completion_tokens")},
                           r.get("model", self.model), r["choices"][0].get("finish_reason", ""), round(time.time() - t0, 2))


class ScriptedLLM:
    """Для тестов инфраструктуры: возвращает заранее заданные ответы. НЕ используется в сравнении."""

    def __init__(self, script: list, model: str = "scripted", **_):
        self.script, self.model, self.i = list(script), model, 0

    def complete(self, system, messages, tools=None, force_tool=None) -> LLMResponse:
        step = self.script[self.i] if self.i < len(self.script) else {"tool_calls": [{"name": "finish", "args": {"handled_requests": [], "summary": "end"}}]}
        self.i += 1
        calls = [{"id": f"s{self.i}-{j}", "name": c["name"], "args": c["args"]} for j, c in enumerate(step.get("tool_calls", []))]
        return LLMResponse(step.get("text", ""), calls, {"input": 0, "output": 0}, self.model, "scripted", 0.0)


def make_llm(cfg: dict):
    p = cfg.get("provider")
    if p == "anthropic":
        return AnthropicLLM(**cfg)
    if p == "openai_compat":
        return OpenAICompatLLM(**cfg)
    raise LLMError(f"Неизвестный provider: {p}")
