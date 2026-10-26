"""Провайдеры моделей без внешних зависимостей (urllib).

Нейтральный формат сообщений:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "results": [{"id", "content": str}]}

Решение E3: каждый вызов получает остаток срока попытки (deadline); повторы укладываются в него.
Любая проблема с вызовом модели (сеть, HTTP, не-JSON, неожиданная структура) — LLMError:
это сбой инфраструктуры, а не решение модели.
"""
from __future__ import annotations

import hashlib
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
    request_hash: str = ""


class LLMError(Exception):
    """Сбой обращения к модели (инфраструктура). kind: network | http | timeout | bad_response | config"""

    def __init__(self, message: str, kind: str = "network"):
        super().__init__(message)
        self.kind = kind


class DeadlineExceeded(LLMError):
    def __init__(self, message="срок попытки истёк"):
        super().__init__(message, "timeout")


def _post(url: str, headers: dict, body: dict, deadline: float | None = None, attempts: int = 3, per_call: float = 120) -> dict:
    data = json.dumps(body).encode()
    for i in range(attempts):
        left = (deadline - time.time()) if deadline else per_call
        if left <= 1:
            raise DeadlineExceeded()
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=min(per_call, left)) as r:
                raw = r.read()
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise LLMError(f"ответ модели не JSON: {raw[:200]!r}", "bad_response") from None
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and i < attempts - 1:
                time.sleep(min((2 ** i) * (0.5 + random.random()), max(0, (deadline or 1e18) - time.time() - 1)))
                continue
            raise LLMError(f"HTTP {e.code}: {msg}", "http") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if isinstance(e, TimeoutError) or "timed out" in str(e):
                if deadline and deadline - time.time() <= 1:
                    raise DeadlineExceeded() from None
            if i < attempts - 1:
                time.sleep(min((2 ** i) * (0.5 + random.random()), max(0, (deadline or 1e18) - time.time() - 1)))
                continue
            raise LLMError(str(e), "network") from None
    raise LLMError("unreachable")


def _hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int = 1024, temperature=None, **_):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self.url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com") + "/v1/messages"
        self.last_request = None
        if not self.key:
            raise LLMError("ANTHROPIC_API_KEY не задан", "config")

    def complete(self, system: str, messages: list, tools: list | None = None, force_tool: str | None = None,
                 deadline: float | None = None) -> LLMResponse:
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
        self.last_request = body
        t0 = time.time()
        r = _post(self.url, {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, body, deadline)
        try:
            text = "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")
            calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in r["content"] if b["type"] == "tool_use"]
            u = r.get("usage", {})
        except (KeyError, TypeError) as e:
            raise LLMError(f"неожиданная структура ответа: {e!r}", "bad_response") from None
        return LLMResponse(text, calls, {"input": u.get("input_tokens"), "output": u.get("output_tokens")},
                           r.get("model", self.model), r.get("stop_reason", ""), round(time.time() - t0, 2), _hash(body))


class OpenAICompatLLM:
    """OpenAI, OpenRouter, Ollama (http://localhost:11434/v1), vLLM и т.п."""

    def __init__(self, model: str, max_tokens: int = 1024, temperature=None, base_url: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", **_):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.local = any(h in self.base for h in ("localhost", "127.0.0.1", "0.0.0.0"))
        self.key = os.environ.get(api_key_env)
        self.last_request = None
        if not self.key and not self.local:
            raise LLMError(f"{api_key_env} не задан для {self.base}", "config")

    def complete(self, system: str, messages: list, tools: list | None = None, force_tool: str | None = None,
                 deadline: float | None = None) -> LLMResponse:
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
        self.last_request = body
        t0 = time.time()
        headers = {"authorization": f"Bearer {self.key}"} if self.key else {}
        r = _post(self.base + "/chat/completions", headers, body, deadline)
        try:
            msg = r["choices"][0]["message"]
            calls = []
            for i, c in enumerate(msg.get("tool_calls") or []):
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = c["function"].get("arguments")  # строка — её отклонит валидатор схемы
                calls.append({"id": c.get("id") or f"tc{i}", "name": c["function"]["name"], "args": args})
            u = r.get("usage") or {}
            finish = r["choices"][0].get("finish_reason", "")
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"неожиданная структура ответа: {e!r}", "bad_response") from None
        return LLMResponse(msg.get("content") or "", calls, {"input": u.get("prompt_tokens"), "output": u.get("completion_tokens")},
                           r.get("model", self.model), finish, round(time.time() - t0, 2), _hash(body))


class ScriptedLLM:
    """Для тестов инфраструктуры: возвращает заранее заданные ответы. НЕ используется в сравнении."""

    def __init__(self, script: list, model: str = "scripted", **_):
        self.script, self.model, self.i = list(script), model, 0
        self.last_request = None

    def complete(self, system, messages, tools=None, force_tool=None, deadline=None) -> LLMResponse:
        self.last_request = {"system": system[:50], "messages": len(messages)}
        step = self.script[self.i] if self.i < len(self.script) else {"tool_calls": [{"name": "finish", "args": {"handled_requests": [], "summary": "end"}}]}
        self.i += 1
        if isinstance(step, Exception):
            raise step
        calls = [{"id": f"s{self.i}-{j}", "name": c["name"], "args": c["args"]} for j, c in enumerate(step.get("tool_calls", []))]
        return LLMResponse(step.get("text", ""), calls, {"input": 0, "output": 0}, self.model, "scripted", 0.0, "scripted")


def make_llm(cfg: dict):
    p = cfg.get("provider")
    if p == "anthropic":
        return AnthropicLLM(**cfg)
    if p == "openai_compat":
        return OpenAICompatLLM(**cfg)
    raise LLMError(f"Неизвестный provider: {p}", "config")


def preflight(cfg: dict, deadline_s: float = 120) -> str:
    """Один короткий вызов до батча: проверяет сервер, ключ и идентификатор модели (решения E1, E3)."""
    llm = make_llm(cfg)
    r = llm.complete("Ответь одним словом.", [{"role": "user", "content": "ping"}], deadline=time.time() + deadline_s)
    return r.model
